---
id: docker-deployment
domain: ops
tags:
  - deployment
  - docker
  - operations
  - infrastructure
related:
  - restore
  - architecture-structure
  - technical-specification
  - migration-workflow
  - seed-workflow
  - media-store-operations
  - rollback
---

## Purpose

Documentation for deploying and operating the Mko Bazuna platform using Docker. Covers the
Makefile-driven Compose project isolation model, local development setup, production deployment,
environment configuration, the service startup dependency chain, routine operational procedures,
and troubleshooting.

## Main Concepts

- **Two-process architecture:** Web (gunicorn WSGI) and bot (aiogram) share one Django project
  and PostgreSQL database
- **Migrations run exactly once** before both services start (via an advisory-locked one-shot
  service)
- **Compose project isolation:** Dev and test environments use separate Compose project names
  (`mko-bazuna-dev` and `mko-bazuna-test`) so they never collide on service names, networks, or
  named volumes
- **Seed auto-runs in dev:** The dev override clears the `seed` profile gate so the seed one-shot
  container starts automatically on `make up`
- **Media storage:** Local `MEDIA_ROOT` volume served via nginx
- **TLS termination:** Handled by nginx; HTTPS mandatory for login deep-links and secure cookies
- **Redis cache service (production):** `redis:7.4.11-alpine` (the pin in `docker-compose.yml`) provides a shared cache backend across web gunicorn workers (3) and the bot process. `LocMemCache` is per-process only and cannot share rate-limit counters or cache invalidations. Dev/test settings override `CACHES` to `LocMemCache`, so no Redis is needed for local development or testing.

## Compose Project Isolation

The Makefile is the primary interface for all Docker operations. It uses **GNU Make target-specific
variable exports** to assign `COMPOSE_PROJECT_NAME` per target group, eliminating project-name
mismatch between `make up`, `make down`, and `make test`:

```makefile
up down build restart lint typecheck shell makemigrations create-admin \
    load-catalog seed logs backup restore prune-backups clean db-shell migrate: \
    export COMPOSE_PROJECT_NAME = mko-bazuna-dev

test test-db test-down test-logs test-recreate: \
    export COMPOSE_PROJECT_NAME = mko-bazuna-test
```

This means every dev target operates on the `mko-bazuna-dev` project and every test target operates
on `mko-bazuna-test`. You can run `make up` (dev, port 8000) and `make test` simultaneously
without service-name, network, or named-volume collisions. Each project gets its own `postgres_data`
and `uv_cache` volumes, prefixed by the project name.

### Exact invocation forms

| Environment | Compose project name | Full invocation | Env file |
|-------------|---------------------|-----------------|----------|
| Dev | `mko-bazuna-dev` | `docker compose --env-file .env.dev -f docker-compose.yml -f docker-compose.dev.override.yml <cmd>` | `.env.dev` |
| Test | `mko-bazuna-test` | `docker compose --env-file .env.test -f docker-compose.yml -f docker-compose.test.yml <cmd>` | `.env.test` |

> **Note:** Test recipes pass `--env-file .env.test` and services use `env_file: [.env.test]` in
> `docker-compose.test.yml`. Test credentials and settings come from `.env.test` and are bind-mounted
> into containers as `src/.env`.

> **Warning:** A plain `docker compose up` (without `make` or `--env-file`) silently falls back to
> the directory-name default project `mko_bazuna`. This causes a project-name mismatch with
> Makefile-managed containers and leads to stale, orphaned containers. Always use `make` or
> replicate the exact invocation form above with the correct `COMPOSE_PROJECT_NAME`.

### Environment files

| File | Purpose | Tracked in git |
|------|---------|----------------|
| `.env.dev` | App secrets/creds; passed via `--env-file` and bind-mounted into containers as `src/.env` (also used via `env_file:` in compose) | No (runtime secrets, gitignored) |
| `.env.dev.example` | Template for `.env.dev`; committed to git with placeholder values; copy to `.env.dev` and fill in real values | Yes (template, placeholders only) |

Never set `DATABASE_URL` in `.env.dev` — Compose constructs it from the `POSTGRES_*` variables so
the inter-container hostname (`db`) is correct.

### Windows / non-`make` operation

`make` is not available in a default Windows 11 PowerShell shell, so `make up`,
`make down`, `make build`, and `make test` will not run as-is. Use one of:

- **PowerShell parity script:** `.\Makefile.ps1 <target>` — provides project-name
  isolation equivalent to the Makefile (`up`, `down`, `build`, `test`, `test-db`,
  `clean`, …). Run `.\Makefile.ps1 help` for the full target list.
- **Manual invocation:** Pass `--project-name` explicitly to `docker compose`. This
  is shell-agnostic and is exactly equivalent to the `make` targets.

  ```powershell
  # IMPORTANT: On Windows, write each command on a SINGLE line.
  # The `\` line-continuation is a bash feature; PowerShell treats a trailing `\`
  # as a literal backslash, which makes `docker compose` reject the path/fragment.
  # These examples are single-line PowerShell-ready commands.

  # Start dev (equiv. to: make up)
  docker compose --project-name mko-bazuna-dev --env-file .env.dev -f docker-compose.yml -f docker-compose.dev.override.yml up -d

  # Stop dev (equiv. to: make down)
  docker compose --project-name mko-bazuna-dev --env-file .env.dev -f docker-compose.yml -f docker-compose.dev.override.yml down

   # Rebuild Docker images (equiv. to: make build)
   docker compose --project-name mko-bazuna-dev --env-file .env.dev -f docker-compose.yml -f docker-compose.dev.override.yml build

   # Full environment reset (equiv. to: make clean for dev only; use `make fullclean` to also stop test project, wipe volumes, and prune all images + build cache)
  docker compose --project-name mko-bazuna-dev --env-file .env.dev -f docker-compose.yml -f docker-compose.dev.override.yml down -v --remove-orphans
  docker compose -p mko-bazuna-dev --env-file .env.dev -f docker-compose.yml -f docker-compose.dev.override.yml down --rmi all -v
  # Start test DB on host:5433 (equiv. to: make test-db)
  docker compose --project-name mko-bazuna-test -f docker-compose.yml -f docker-compose.test.yml up -d db

  # Run tests, one-shot (equiv. to: make test)
  docker compose --project-name mko-bazuna-test -f docker-compose.yml -f docker-compose.test.yml run --rm test
  ```

  Omitting `--project-name` falls back to the directory-name default `mko_bazuna`, which
  collides with any `make`/`Makefile.ps1`-managed stack and reuses the wrong volume (see
  [Recovery from stale project names](#recovery-from-stale-project-names)).

## Startup Dependency Chain

On `make up`, the Compose `depends_on` directives run one-shot services in a strict order before
starting the long-lived web and bot processes. The full chain is:

```
db (healthy, pg_isready)
  → migrate (one-shot, advisory-locked, exits 0)
    → load_catalog (one-shot, loads categories.yaml)
      → web (gunicorn, long-lived)
      → bot (aiogram, long-lived)
      → create_admin (one-shot, skipped if ADMIN_PASSWORD is empty)
      → seed (one-shot, auto-runs in dev)
```

- **`db`** — PostgreSQL 18 with a `pg_isready` healthcheck. `web` and `bot` both block on
  downstream one-shot services completing successfully.
- **`migrate`** — runs `apps.core.utils.migrate_locked.main` (all three required steps — `migrate --run-syncdb`,
  `setup_search_triggers`, `load_exchange_rates` — plus an optional `backfill_translations` step
  when `RUN_TRANSLATION_BACKFILL=true` — under a session-scoped advisory lock ID 100) so
  concurrent runs are serialized. Each step is dispatched via `subprocess.run(check=False,
  timeout=settings.SCHEDULER_COMMAND_TIMEOUT)`; a step that exceeds the timeout (`TimeoutExpired`)
  is logged and skipped so the remaining steps still run and the lock is released (ENT-001).
  Exits 0 on success (including a fresh DB with no pending
  migrations). See [the migration workflow](migration-workflow.md) for details.
- **`load_catalog`** — loads the category tree from `apps/categories/catalog/categories.yaml`.
  Depends on `migrate` completing successfully.
- **`create_admin`** — creates a Django superuser if `ADMIN_PASSWORD` is set; skipped silently
  otherwise. Depends on `load_catalog`.
- **`seed`** — populates the database with demo data. In dev this runs **automatically** because
  `docker-compose.dev.override.yml` sets `profiles: !reset []` on the `seed` service, clearing the
  base `["seed"]` profile gate from `docker-compose.yml`. In production the profile gate is
  retained, so seed only runs on explicit `--profile seed` demand. See
  [the seed data workflow](seed-workflow.md) for details.

## Local Development Setup

### Prerequisites

- Docker + Docker Compose
- Python 3.14+ with `uv` package manager (for host-side commands like `make consolidate`)
- A Telegram bot token from @BotFather

### Quick Start

```bash
# Configure environment: copy .env.dev.example to .env.dev and fill in your real values
#   - BOT_TOKEN: your Telegram bot token from @BotFather
#   - DJANGO_SECRET_KEY: python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
#   - POSTGRES_PASSWORD: database password

# Start dev environment (project: mko-bazuna-dev)
make up

# The dependency chain runs automatically:
# db → migrate → load_cities → load_catalog → create_admin → seed → web, bot
# Web is served at http://localhost:8000 (hot-reload enabled)
```

### Database Configuration

Docker Compose automatically constructs `DATABASE_URL` from the `POSTGRES_*` variables using the
`db` service hostname:

```
postgres://${POSTGRES_USER}:${POSTGRES_PASSWORD}@db:5432/${POSTGRES_DB}
```

**Important:** Do NOT set `DATABASE_URL` in `.env.dev` — the compose files build it from the
individual database variables (`POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`), ensuring the
correct hostname (`db`) is used for inter-container communication.

### Development Services

| Service | Port | Description |
|---------|------|-------------|
| `web` | 8000 | Django development server (hot-reload enabled) |
| `bot` | — | Telegram bot (logs to stdout) |
| `db` | — | PostgreSQL 18 (internal, no host port) |
| `nginx` | 80/443 | Optional; use `profiles: ["use-nginx"]` to enable |

**Build cache:** `make build` now uses Docker's layer cache and the Dockerfile's
`--mount=type=cache` mounts (for apt and uv) for faster incremental builds. Subsequent
builds are significantly faster when only source code changes (the uv dependency layer is
the primary win). Run `make fullclean` to clear the build cache if builds behave unexpectedly.

**Bind-mount scope in dev:** The `.:/app` source bind-mount (hot-reload) is applied to the
six services `web`, `bot`, `load_catalog`, `load_cities`, `create_admin`, and `seed` via
`docker-compose.dev.override.yml`. Model changes, new migration files, and source code edits
to these services are picked up at runtime. `migrate` has **no `volumes:` key at all** in the
override — it inherits only the base service's `.env.dev` file, so it receives **no source
code bind-mount**. `nginx` is **not** `.:/app`-bound either: it binds `media_volume` read-only
at `/media_volume`, the dev configuration `nginx.dev.conf` at `/etc/nginx/nginx.conf`, and the
`certs/` directory at `/etc/nginx/certs`. A source code change that affects any service without
a bind-mount still requires `make build`.

Secret-validation bypass is split across two distinct flags:
- **`DJANGO_BUILD=1`** — set **only** in the Dockerfile during the image build stage (build-time `collectstatic --noinput`) and in `Makefile`'s `restore-test` target, so the build-placeholder `SECRET_KEY` passes. It is **never** set for runtime one-shot services, and `config.settings.prod` honours it unconditionally (the build stage has no `.env` and cannot be distinguished by a settings module).
- **`DJANGO_ONESHOT=1`** — set only on the dev one-shot services `migrate`, `load_cities`, `load_catalog`, `create_admin`, and `seed` (via `docker-compose.dev.override.yml`). These services resolve `DJANGO_SETTINGS_MODULE=config.settings.oneshot` — a bootstrap module that star-imports `prod` and re-pins `DEBUG=False` — and the flag is honoured **only** because that module is not a `*.prod` module. They carry dev placeholder/dummy secrets from `.env.dev` and do not serve web traffic, so the production fail-fast guards are bypassed during dev bootstrap.

In production, **neither** flag is set: `docker-compose.prod.yml` one-shot services run full secret validation against the real `.env.prod` values. `DJANGO_ONESHOT` is inert under `config.settings.prod` — if it appears there (e.g. copied out of the dev override into `.env.prod`) it does **not** suppress any guard and a boot-time warning (`DJANGO_ONESHOT is set but ignored`) explains the situation. The long-lived `web` and `bot` services never set either flag, so real secrets are always enforced at their boot. See [Deployment Checks](#deployment-checks) for the full validation scope.

**Startup behavior:** `make up` starts services in the background (`up -d`, non-blocking).
The `depends_on` chain still enforces correct startup ordering (`db` → `migrate` →
`load_catalog` → `create_admin` → `seed` → `web`, `bot`), but the command returns immediately
without waiting for seed (600 ads) to finish. Use `make logs -f seed` or `docker compose ps`
to check seed progress.

### Full environment reset

If you encounter stale containers or build issues:

```bash
# 1. Stop and remove all dev containers and volumes
# Windows: .\Makefile.ps1 down  — or single-line:
#   docker compose --project-name mko-bazuna-dev --env-file .env.dev -f docker-compose.yml -f docker-compose.dev.override.yml down -v

make down    # or: docker compose --env-file .env.dev \
             #      -f docker-compose.yml -f docker-compose.dev.override.yml down -v

# 2. Remove dangling images, containers, networks, and volumes
docker system prune -f --volumes

# 3. (Optional) Remove all unused images
docker image prune -a -f

# 4. Clear build cache (important for uv layer issues)
docker builder prune -a -f

# 5. Rebuild and start fresh
make build
make up
# Windows: .\Makefile.ps1 build ; .\Makefile.ps1 up
```

Or use the single-command shortcut for a complete reset:

```bash
make fullclean
```

This stops both dev and test Compose projects (wiping volumes), then runs
`docker system prune -f --volumes`, `docker image prune -a -f`, and
`docker builder prune -a -f` — equivalent to steps 1-4 above.

### Production-like Development

For full production parity with nginx TLS termination, see
[Local HTTPS with mkcert](local-https-mkcert.md) for certificate setup.

```bash
# Run without nginx (direct web access on port 8000)
make up

# Or run with nginx for production-like HTTPS (requires mkcert setup)
COMPOSE_PROJECT_NAME=mko-bazuna-dev docker compose --env-file .env.dev \
  -f docker-compose.yml -f docker-compose.dev.override.yml --profile use-nginx up -d
```

Windows (PowerShell 5.1+) — single line, no `\` continuation:

```powershell
# Windows equivalents:
.\Makefile.ps1 up

# Or with nginx for production-like HTTPS (requires mkcert setup):
docker compose --project-name mko-bazuna-dev --env-file .env.dev -f docker-compose.yml -f docker-compose.dev.override.yml --profile use-nginx up -d
```

**Note:** Running with `--profile use-nginx` requires TLS certificates. Follow the mkcert setup
guide for local HTTPS development.

Once nginx is up, verify the dev `/media/` rate-limit gate with
[`dev-nginx-media-gate.md`](dev-nginx-media-gate.md) — it runs the read-only
`.\Makefile.ps1 verify-nginx` command and never starts the container itself.

## Production Deployment

### Docker Compose Production

```bash
# Copy .env.prod.example to .env.prod and fill in production values
# Then start services:
docker compose --env-file .env.prod -f docker-compose.yml -f docker-compose.prod.yml up -d

# Apply migrations (run once)
docker compose --env-file .env.prod -f docker-compose.yml -f docker-compose.prod.yml run --rm migrate
```

### Automated Deployment (GitHub Actions)

Production deploys are automated via the `deploy.yml` workflow (`.github/workflows/deploy.yml`,
finding 12-OPS-005). Triggered manually via `workflow_dispatch` with a `production`
environment approval gate, the workflow performs a backup-then-pull-then-health-check
procedure over SSH:

1. **Pre-deploy backup** — `pg_dump -F c` into `./backups/` (safety net before each deploy)
2. **Pull** the CI-built SHA-tagged image (`ghcr.io/mko-bazuna/mko_bazuna:${SHA}`)
3. **Recreate** all services (`docker compose up -d --remove-orphans`)
4. **Health-check gate** — poll `/health/ready/` until HTTP 200 or 60-second timeout;
   on failure the workflow exits `1` and references the
   [rollback runbook](rollback.md#4-health-check-gated-validation)

Use the manual `docker compose` command above for emergency deploys or when the
GitHub Actions runner cannot reach the production host.

### Production Services

In production the application services are **prebuilt GHCR images**, not local
builds: `docker-compose.prod.yml` overrides each one with
`image: ${REGISTRY}/${REPOSITORY}:${IMAGE_TAG:?…}` and declares **no `build:`**
for it, so `docker compose pull` fetches the CI-built artefact and the deploy
workflow never builds (12-OPS-002). The `db` and `nginx` services come from
upstream images; `backup` and `pgbouncer` carry their own images; `scheduler`,
`backup` and `pgbouncer` are profile-gated and off by default (the `pgbouncer`
profile is BLOCKED — see below).

| Service | Image/Command | Notes |
|---------|---------------|-------|
| `db` | `postgres:18.6-alpine` (upstream) | Persistent volume `postgres_data` |
| `migrate` | Prebuilt GHCR image, runs `migrate_locked.main` | One-shot service: runs `migrate --run-syncdb`, `setup_search_triggers`, `load_exchange_rates` under advisory lock ID 100, with optional `backfill_translations` when `RUN_TRANSLATION_BACKFILL=true`. Each step is bounded by `SCHEDULER_COMMAND_TIMEOUT` (`check=False, timeout=...`); a timed-out step is logged and skipped (ENT-001) |
| `create_admin` | Prebuilt GHCR image, creates admin user | One-shot service, idempotent |
| `seed` | Prebuilt GHCR image, `entrypoint-seed.sh` | One-shot service, gated by `profiles: ["seed"]`. Populates database with demo data. See [Seed Data](#seed-data) below. |
| `web` | Prebuilt GHCR image, gunicorn | Port 8000 not published; nginx proxies |
| `bot` | Prebuilt GHCR image, `python -m telegram_bot.main` | Restarts on failure; dual liveness marker: file-based (`docker/healthcheck-bot.sh` checks PID + `/tmp/mko_bazuna_bot_alive` marker freshness via `BOT_HEALTH_STALE_SECONDS`, the primary bot alert) **and** Redis-based `bot:liveness` key (written by `LivenessMiddleware` in `telegram_bot/lifecycle.py`, read by the web `/health/ready/` probe via `BOT_HEALTH_CHECK_ENABLED`, which defaults off so the probe reports bot as `"disabled"` and does not gate web readiness) |
| `scheduler` | Prebuilt GHCR image, `entrypoint-scheduler.sh` | Profile-gated (`profiles: ["scheduler"]`); long-lived, `restart: unless-stopped` |
| `backup` | `postgres:18.6-alpine` (upstream) | Profile-gated (`profiles: ["backup"]`); daily `pg_dump` with 7-day retention |
| `pgbouncer` | `edoburu/pgbouncer:1.25.2` (upstream) | Profile-gated (`profiles: ["pgbouncer"]`) and **BLOCKED** — do not enable; the pinned tag does not resolve. See [PgBouncer is opt-in and currently unusable](#pgbouncer-is-opt-in-and-currently-unusable) |
| `nginx` | `nginx:1.30.5` (upstream) | Ports 80/443; TLS termination |

### TLS Configuration

Mount TLS certificates at `/etc/nginx/certs/` in the nginx container:

```bash
# Using Let's Encrypt certificates
docker compose --env-file .env.prod -f docker-compose.yml -f docker-compose.prod.yml up -d
```

The production override file (`docker-compose.prod.yml`) includes:
- HTTPS listener on port 443
- HTTP to HTTPS redirect on port 80
- TLS certificate paths configurable via `TLS_CERT_PATH`

> **Deferred decision (09-API-016): the host certificate path is not yet decided.**
> The production host filesystem and the CI-runner filesystem are not visible from this
> repository, so only the owner can name the real path. The candidate namespaced path is
> `deploy/secrets/mko_bazuna.crt` (namespaced rather than a bare filename, which would be
> ambiguous). Do **not** treat the current default (`/etc/nginx/certs`) as a decided path,
> and do not add a certificate copy step until the owner rules. Note the failure mode this
> guards against: Docker auto-creates a missing bind-mount source as an **empty directory**,
> so a forgotten export does not fail at mount time — nginx starts, mounts empty, then aborts
> with `cannot load certificate`.

### Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `DJANGO_SECRET_KEY` | Yes | Django secret key for signing sessions and CSRF tokens. Generate with: `python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"`. Rotate this key if it may have been committed to VCS or exposed. After rotation, restart the `web` and `bot` containers together — all signed tokens (sessions and CSRF tokens) are invalidated. |
| `LOG_MASK_KEY` | Yes (prod) | HMAC key for the Telegram-ID log mask (`mask_telegram_id`, `apps/core/utils/sanitize.py`). Generate with: `python -c "import secrets; print(secrets.token_hex(32))"` — minimum **32 bytes** (RFC 2104 §3). **Required in production**: `prod.py` fail-fast rejects an empty, placeholder (`<…>`) or too-short value at boot, so `web` and `bot` will not start until it is real. It is an **independent** secret, deliberately **not** derived from `DJANGO_SECRET_KEY` — a shared key would give one leak two blast radii and leave no scoped revocation. Empty outside production is accepted: the mask then falls back to a **per-process random** key (stable within the process, changed on every restart) and logs one warning, so masked values are **not** correlatable across processes. Rotate **only on suspected compromise, never on a schedule** — see [Rotating Secrets](#rotating-secrets). |
| `DEBUG` | No (default: `False`) | Django debug mode. Must be `True` only in dev (`docker-compose.dev.override.yml` sets this inline). Production must keep `False` |
| `BOT_TOKEN` | Yes | Telegram bot token from @BotFather (placeholder `<...>` values are rejected at boot). An **empty** value is legal in development: the bot logs `BOT_TOKEN not set - skipping bot startup (development mode)` and the rest of the stack runs normally. A *placeholder* value is rejected by the bot entrypoint (`telegram_bot/main.py`) and fails the bot process only — it no longer aborts the whole dev stack at Django settings import. Rotate if compromised: get a new token from @BotFather, update `BOT_TOKEN` in `.env.prod`, then run `docker compose ... up -d bot`. This project uses long-polling (not webhooks), so no Telegram-side URL reconfiguration is needed. After rotation, the old token is immediately invalidated. |
| `BOT_USERNAME` | Yes (prod) | Telegram handle without `@`; 3-32 chars, `[A-Za-z0-9_]` only. **Required in production**: `prod.py` rejects an empty, placeholder (`<your-bot-username>`) or malformed value at boot, so `web` and `bot` will not start until it is real. It is also a seed value only — migration `0003` copies it into the `SiteConfig` singleton once and no render path reads the env var afterwards, so a value that was wrong at migration time leaves a dead `t.me/` row behind. Correct an already-seeded row with `manage.py repair_bot_username` (or the Django admin) — see [`contact-us.md`](../01-spec/contact-us.md). |
| `ALLOWED_HOSTS` | Yes (prod) | Comma-separated list of host/domain names the app can serve. `prod.py` raises `ValueError` if empty |
| `SITE_URL` | Yes* | Public site URL for absolute links in Telegram alerts (no trailing slash). Example: `https://mko-bazuna.example.com` |
| `EMAIL_HOST` | No (warned) | SMTP host for the **one** transactional email the application sends — the Telegram support-ticket notification (`send_support_notification_email`, the sole `send_mail` call site). Not required to boot: `config/settings/prod.py` logs a **loud `WARNING`** when it is empty and the import succeeds, matching the fail-open delivery path. The accepted cost (Product Owner ruling 2026-10-03, 09-API-009): a host that never notices the warning loses seller escalations to the admin inbox silently. `EMAIL_BACKEND` is pinned to `smtp.EmailBackend` in production, so SMTP is the only supported transport. |
| `IMMEDIATE_ALERTS_ENABLED` | No (default: `false`) | Enable near-real-time publish-time Telegram alerts to buyers with matching saved searches. Daily backfill runs regardless |
| `POSTGRES_USER` | Yes | Database username |
| `POSTGRES_PASSWORD` | Yes | Database password |
| `POSTGRES_DB` | Yes | Database name |
| `POSTGRES_HOST` | No (default: `db`) | Database host. Set inline to `db` (compose service name) in all services; documents the Django `DATABASES` fallback for local non-Docker development |
| `POSTGRES_PORT` | No (default: `5432`) | Database port. Used by Django `DATABASES` fallback and the prod backup service |
| `REDIS_URL` | Yes (prod) | Redis connection for cache and rate-limiting. Set inline to `redis://redis:6379/0` in all prod Compose services. Required in production (`config/settings/prod.py` fail-fast guard raises `ImproperlyConfigured` if empty, preventing silent fallback to `MemoryStorage`/`LocMemCache`). Empty in dev/test (falls back to locmem) |
| `GOOGLE_TRANSLATE_API_KEY` | Yes (prod) | Google Cloud Translation API v2 key used by `apps.core.services.translation.translate_text()`. Required in production (`config/settings/prod.py` fail-fast guard; placeholder `<...>` values are rejected at boot). Empty in `.env.dev`. Rotate if committed to VCS or exposed. After rotation, restart the `bot` container — the translation service reads the key at call time via `settings.GOOGLE_TRANSLATE_API_KEY`. |
| `PLAUSIBLE_HOST` | No | Analytics host for Plausible traffic tracking (cookieless, no consent banner). Empty disables analytics |
| `TLS_CERT_PATH` | No (default: `/etc/nginx/certs/`) | Path to TLS certificates (fullchain.pem / privkey.pem) mounted into nginx. **The host path is DEFERRED, not decided** (09-API-016): the candidate namespaced path is `deploy/secrets/mko_bazuna.crt`; only the owner can name the real path because the host and CI-runner filesystems are not visible from this repository. Docker auto-creates a missing bind-mount source as an empty directory, so a forgotten export yields a crash-looping nginx whose compose output looks successful. |
| `ADMIN_USERNAME` | No (default: `admin`) | Django admin username for the `create_admin` one-shot service |
| `ADMIN_PASSWORD` | No* | Admin password; required for `create_admin` auto-creation. Create manually if not set |
| `ADMIN_TELEGRAM_ID` | No (default: `-1`) | Placeholder telegram_id for the admin user (negative avoids collision with real Telegram IDs) |
| `SEED_USERS` | No (default: `10`) | Number of demo users to generate (seed service) |
| `SEED_ADS` | No (default: `30`) | Number of demo ads to generate (seed service) |
| `PROMETHEUS_MULTIPROC_DIR` | No (default: `/tmp/prometheus_multiproc`) | Directory for Prometheus multiprocess metrics mode (web service only). Required for accurate per-worker metric collection under gunicorn when `PROMETHEUS_MULTIPROC_DIR` is set; see [Prometheus Metrics](#prometheus-metrics) |
| `SCHEDULER_COMMAND_TIMEOUT` | No (default: `1800`) | Per-command timeout (seconds) for `subprocess.run` dispatch in the scheduler (`apps.core.utils.scheduler`) and in `migrate_locked.main`. Bounds a hung management command so it cannot stall the hourly cycle or the migration bootstrap; a timed-out command is logged and skipped (ENT-001). The default sits safely under the scheduler healthcheck staleness window (`SCHEDULER_HEALTH_STALE_SECONDS` env var, `7200` in prod). |
| `MEDIA_STAGING_BYTE_BUDGET` | No (default: `2147483648` = 2 GiB) | Global cap on bytes held in `MEDIA_ROOT/staging/`. A bot upload is refused **before** any byte is written when `staging_bytes_used()` is at or above this value. **Global, not per-seller** — staging keys are `uuid4()` and carry no owner, so per-seller attribution is infeasible and one seller can exhaust the shared budget. Lowering it protects disk at the cost of refusing legitimate sellers; see [`media-store-operations.md`](media-store-operations.md#staging-byte-budget). |
| `DB_MEM_LIMIT` | No (compose default `1g`) | Memory cgroup limit for the `db` service (`mem_limit: ${DB_MEM_LIMIT:-1g}` in `docker-compose.yml`). **Deliberately not set by `.env.prod.example`**, so **1 GB is the shipped production profile**. It is a cgroup **hard limit**, not a hint: a query whose working set exceeds it is **OOM-killed** (SIGKILL on the backend), which takes the whole PostgreSQL cluster into **crash recovery** — it does not surface as a slow request. Changing it is a **capacity decision requiring review**, not a tuning knob; declare it in `.env.prod` only as part of that decision. (08-VAL-001, 08-SRCH-001) |
| `DB_CPUS` | No (compose default `2.0`) | CPU quota for the `db` service (`cpus: ${DB_CPUS:-2.0}` in `docker-compose.yml`). **Deliberately not set by `.env.prod.example`**, so **2.0 CPU is the shipped production profile**. Like `DB_MEM_LIMIT` it is a cgroup **hard limit**, and changing it is a **capacity decision requiring review**. (08-VAL-001, 08-SRCH-001) |

**Note:** `DATABASE_URL` is automatically constructed from `POSTGRES_*` variables in Docker
containers. Do not set `DATABASE_URL` in `.env.prod` — the compose files build it from the
individual database variables.

*Required for automatic admin creation via `create_admin` service. Can be created manually if not set.

### Rotating Secrets

All production secrets live in `.env.prod`. Each has a different blast radius, so rotate only what is necessary.
The procedure for each secret follows the same pattern: generate a new value, update the variable in `.env.prod`,
restart the affected container(s), and account for the consequences.

**`DJANGO_SECRET_KEY`** — rotate if the key may have been committed to VCS or exposed.

1. Generate a new key:
   ```bash
   python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
   ```
2. Update `DJANGO_SECRET_KEY` in `.env.prod`.
3. Restart `web` and `bot` together:
   ```bash
   docker compose --env-file .env.prod -f docker-compose.yml -f docker-compose.prod.yml up -d web bot
   ```
4. All signed tokens (sessions and CSRF tokens) are invalidated; users must re-authenticate. Telegram `LoginToken` rows are unaffected — a `LoginToken` is a database row identified by `token_hash`, not a token signed with `DJANGO_SECRET_KEY`.

**`BOT_TOKEN`** — rotate if the token is compromised or exposed.

1. Request a new token from @BotFather in Telegram.
2. Update `BOT_TOKEN` in `.env.prod`.
3. Restart the `bot` container:
   ```bash
   docker compose --env-file .env.prod -f docker-compose.yml -f docker-compose.prod.yml up -d bot
   ```
4. The old token is immediately invalidated. This project uses long-polling (not webhooks), so no Telegram-side URL reconfiguration is required.

**`GOOGLE_TRANSLATE_API_KEY`** — rotate if the key may have been committed to VCS or exposed in logs.

1. Generate or rotate the key in Google Cloud Console (Cloud Translation API v2).
2. Update `GOOGLE_TRANSLATE_API_KEY` in `.env.prod`.
3. Restart the `bot` container:
   ```bash
   docker compose --env-file .env.prod -f docker-compose.yml -f docker-compose.prod.yml up -d bot
   ```
4. The translation service reads the key at call time via `settings.GOOGLE_TRANSLATE_API_KEY`, so no other containers need restarting and no user-facing state is invalidated.

**`LOG_MASK_KEY`** — rotate **only if the key may have been committed to VCS or exposed**. There
is deliberately **no rotation schedule**: this key's only job is to make the Telegram-ID log mask
unverifiable without it, and a scheduled rotation would cost permanent loss of correlation across
the log history while shortening no exposure window.

1. Generate a new key:
   ```bash
   python -c "import secrets; print(secrets.token_hex(32))"
   ```
2. Update `LOG_MASK_KEY` in `.env.prod`.
3. Restart `web` and `bot` together. Both processes mask IDs (`bot` on every masked log call, `web`
   on the login/consent paths), so a partial restart leaves two mask families in the same log.
   ```bash
   docker compose --env-file .env.prod -f docker-compose.yml -f docker-compose.prod.yml up -d web bot
   ```

**The rotation trade-off.** Rotating changes **every** masked value in the log history: old and new
lines stop being correlatable, and a `tg_…` value from before the rotation cannot be joined to one
from after it. That is the entire cost. What it is **not** is a data migration — **nothing persists
a masked value** (no model field, no session, no cache key, no Redis key), so there is no stored
data to rewrite and no rollback beyond restoring the old key. A retained key also means the value is
**pseudonymised, not anonymised**: the operator who still holds the key can re-derive a candidate
Telegram ID from a mask, which is precisely why the key's own compromise is the thing to rotate
on.

**Where the key is wired, and why a new one is a four-file change.** `LOG_MASK_KEY` is enforced at
four points, and they move together — this is what makes a typo in a template fail loudly instead of
silently degrading the mask to an enumerable digest:

| Point | File | What it enforces |
|---|---|---|
| Allowlist | `config/settings/base.py` (`ALLOWED_ENV_VARS`) | the variable is readable at all; a name absent here logs an unknown-env-var warning |
| Templates | `.env.example`, `.env.dev.example`, `.env.prod.example`, `.env.test.example` | the operator-facing contract. `.env.example` / `.env.prod.example` carry the placeholder `prod.py` rejects; `.env.dev.example` is empty by design (per-process random fallback); `.env.test.example` carries a non-placeholder ≥32-byte value because every settings test importing the production module reads it |
| CI | `.github/workflows/ci.yml`, `deploy-check.env` | the blocking `manage.py check --deploy` job runs against `config.settings.prod`, so the fail-fast guard must pass in CI too. Never set `DJANGO_BUILD` / `DJANGO_ONESHOT` there: either one suppresses the guard and the gate passes without checking anything |
| Boot guard | `config/settings/prod.py` → `validate_log_mask_key()` in `config/settings/secret_validation.py` | rejects **empty**, then **placeholder**, then **< 32 bytes**, each with a value-free message. Skipped under `DJANGO_BUILD=1` (image build) and for dev bootstrap one-shots (`config.settings.oneshot` + `DJANGO_ONESHOT=1`) |

On rollback, revert the settings entry **and** its `ALLOWED_ENV_VARS` entry **together**; the two
allowlist tests (`test_env_allowlist.py`, `test_env_allowlist_reverse.py`) gate in both directions
and will fail on a one-sided revert.

### Lock timeouts (`canceling statement due to lock timeout`)

Every process opens its connections with a connection-level `lock_timeout`
(`LOCK_TIMEOUT_SECONDS`, default 10 s, rendered as libpq's
`options="-c lock_timeout=10s"` in `DATABASES["default"]["OPTIONS"]`). The log
line to search for is:

```
canceling statement due to lock timeout        # SQLSTATE 55P03
```

A lock timeout means a **long transaction is holding the lock**, usually a
queued `delete_sweep` / `purge_deleted_ads` run contending with an `Ad` row lock
held by a web edit or bot action.

A **`statement_timeout` remains unset** and is the other half of `03-DB-004`
(owner: phase 03, the same finding that landed `LOCK_TIMEOUT_SECONDS`). It bounds
statement **duration** (SQLSTATE 57014) and is deliberately **not** shipped here;
`LOCK_TIMEOUT_SECONDS` bounds lock **waits** (SQLSTATE 55P03) only. Do not read
the two as one policy — a statement that runs long without waiting on a lock is
**not** bounded by `LOCK_TIMEOUT_SECONDS`, and until `statement_timeout` is set
that residue is covered only by the `db` cgroup limits above.

`archive_sweep` and `recompute_normalized_prices` batch in 500-row transactions
(`03-DB-008`), so a batch transaction is bounded rather than tens of seconds.
Per command: `recompute`'s worst observed batch is **well under a second**
(≈358 ms), which holds comfortably under the 10 s bound. `archive_sweep`'s worst
observed batch is ≈3.1 s (≈3.2× headroom) and its hold scales with
**per-statement latency**, because each row costs **two round-trips**
(`transition_to` reads and writes per row) — at 500 rows that is ~1000
round-trips per batch, so an increase in round-trip time (a busier host, a
pooler, a slower link) moves the batch hold toward the bound. `archive_sweep`
uses a session-scoped advisory lock
(`pg_advisory_lock`) because a transaction-scoped lock would be released at the
first batch commit; **this is not PgBouncer transaction-mode safe — revisit both
commands before enabling the pgbouncer profile.**

**A non-zero exit from `archive_sweep` now means partial success, not total
failure:** batches 1..N-1 are committed and the failed batch is rolled back. The
command's own log carries the batch index and cursor
(`archive_sweep batch %d: …`, `archive_sweep aborted at batch %d …`); the
scheduler only reports "exited with code 1" and cannot supply that detail. The
next hourly tick re-derives the eligible set from scratch and finishes the work
— nothing is lost.

Two bounds, two different things: `SCHEDULER_COMMAND_TIMEOUT` (1800 s) kills the
**child process** so one command cannot stall the cycle; `LOCK_TIMEOUT_SECONDS`
(10 s) bounds **one lock wait** on one connection. Do not raise
`LOCK_TIMEOUT_SECONDS` to work around a lock wait — find the contention. A larger
value only lengthens the stall. Hourly sweeps are retried on the next tick by
construction; a web request returns a 503 with `Retry-After: 30`; the bot answers
a busy message.

> **BLOCKED — do not enable the `pgbouncer` profile yet.** Enabling it with only
> the `ignore_startup_parameters` env var produces **silent unbounded lock
> waits** (see below): the pooler discards the `options` bound and nothing logs
> it. Enabling the profile additionally requires a **server-side** `lock_timeout`
> default (`ALTER DATABASE mko_bazuna SET lock_timeout = '10s'`, or
> `postgresql.conf`), which is **not** shipped in this repo — it is phase 12's
> (production-ops) decision. Until that default exists, leaving the profile off
> is required. The pinned image tag (`edoburu/pgbouncer:1.25.2`) also does not
> resolve on Docker Hub, so `docker compose pull` aborts as a whole if the
> profile is activated — the deploy path (`deploy.yml`) therefore excludes it
> (12-OPS-007).

### PgBouncer is opt-in and currently unusable

If PgBouncer is enabled (opt-in `--profile pgbouncer`), the pooler must list
`options` in `ignore_startup_parameters`. The variable is **unprefixed**
(`IGNORE_STARTUP_PARAMETERS=options,extra_float_digits` in
`docker-compose.prod.yml`): this image's ini template is
`ignore_startup_parameters = ${IGNORE_STARTUP_PARAMETERS:-…}`, which the
entrypoint reads from the bare env name — a `PGBOUNCER_`-prefixed name is
silently dropped and the pooler then refuses every client with
`FATAL: unsupported startup parameter in options: lock_timeout`.

Listing `options` is **necessary but not sufficient**. PgBouncer discards the
whole `options` startup parameter, so the client's connection-level
`lock_timeout` is gone: `SHOW lock_timeout` on a pooled connection returns `0`
(unbounded). `track_extra_parameters = lock_timeout` does **not** substitute on
PgBouncer 1.25.2. The bound only survives a pooler through a **server-side**
default — `ALTER DATABASE mko_bazuna SET lock_timeout = '10s'` or
`postgresql.conf` — and that default is deliberately not shipped here (phase 12
owns it). Consequently the `pgbouncer` service in `docker-compose.prod.yml` is
present but not usable, for reasons outside BLOCK 5 (its `PGBOUNCER_*`/`POSTGRES_*`
env shape is also wrong for this image).

### Deployment Checks

Deployment configuration is validated via Django's `manage.py check --deploy`:
- **CI:** A dedicated `deploy-check` job in `.github/workflows/ci.yml` runs `check --deploy --fail-level WARNING` against `config.settings.prod` (not the test settings). It sets all required production env vars to valid non-secret placeholders — `DJANGO_SECRET_KEY` (a 50+ character literal), `BOT_TOKEN`, `BOT_USERNAME` (a handle matching `^[A-Za-z0-9_]{3,32}$`), `LOG_MASK_KEY` (a non-placeholder ≥32-byte literal), `GOOGLE_TRANSLATE_API_KEY`, `SITE_URL=https://example.com`, `ALLOWED_HOSTS=example.com`, `CSRF_TRUSTED_ORIGINS=https://example.com`, `EMAIL_HOST=smtp.example.com`, `REDIS_URL=redis://localhost:6379/0`, and `DATABASE_URL` for `env.db()` parsing — so the full production settings import path is exercised. No PostgreSQL service container is required (`check --deploy` is static). Because `--fail-level WARNING` is used and the step has no `continue-on-error`, any W-series finding fails the build. This replaces the previous `test`-job step that ran against `config.settings.test` and produced 6 false-positive warnings (W008, W009, W012, W016, W018, W021) which masked real deployment gaps.
- **Drift gate:** that `env:` block is a contract, not just fixtures. `config/settings/tests/test_deploy_check_env_parity.py` parses it out of `ci.yml` and imports `config.settings.prod` with exactly that set, so a new production guard fails the test suite until its key is added to the block in the same change. Never add `DJANGO_BUILD` or `DJANGO_ONESHOT` there: either one suppresses the guards and makes the gate pass while checking nothing.
- **Boot:** Both `web` and `bot` entrypoints call `check --deploy` after the database is reachable and before starting the application server. The call is non-fatal — it logs a `WARNING` and continues if any checks fail, so boot is never blocked by a deploy warning.
- This complements the `${VAR:?}` presence guards in `docker-compose.yml`. Additionally, `prod.py` enforces import-time validation on nine variables; **eight** of them are gated on the `_SKIP_SECRET_VALIDATION` block, while `ALLOWED_HOSTS` is checked unconditionally (`if not ALLOWED_HOSTS: raise ValueError(...)` below the gate). `DJANGO_BUILD=1` therefore bypasses the eight secret guards but **not** the `ALLOWED_HOSTS` check — a load-bearing fact for the Docker builder stage, whose `collectstatic` environment must still supply a non-empty `ALLOWED_HOSTS`:

  | Variable | Rule | Failure |
  |---|---|---|
  | `DJANGO_SECRET_KEY` | non-empty; not a `<...>` placeholder or the `dev-only-dummy` sentinel; ≥ 50 characters | `ImproperlyConfigured` |
  | `BOT_TOKEN` | non-empty; not a `<...>` placeholder | `ImproperlyConfigured` |
  | `BOT_USERNAME` | non-empty; not a `<...>` placeholder; `^[A-Za-z0-9_]{3,32}$` (it is persisted into `SiteConfig.bot_username`, and a bad value makes every `t.me/` deep link dead) | `ImproperlyConfigured` |
  | `LOG_MASK_KEY` | non-empty; not a `<...>` placeholder; ≥ 32 bytes. An empty or weak value would silently reduce the Telegram-ID log mask to an enumerable digest, so the fix must not ship as a false security property | `ImproperlyConfigured` |
  | `GOOGLE_TRANSLATE_API_KEY` | non-empty; not a `<...>` placeholder | `ImproperlyConfigured` |
  | `SITE_URL` | non-empty | `ImproperlyConfigured` |
  | `REDIS_URL` | non-empty (otherwise silent fallback to `MemoryStorage`/`LocMemCache`) | `ImproperlyConfigured` |
  | `ALLOWED_HOSTS` | non-empty | `ValueError` |
  | `CSRF_TRUSTED_ORIGINS` | non-empty | `ValueError` |

  `EMAIL_HOST` is deliberately **not** in this table: per the Product Owner ruling of 2026-10-03 (Q1, 09-API-009) an empty `EMAIL_HOST` logs a **loud `WARNING`** and the import succeeds — it is not a boot gate. The site serves normally; only the support-desk notification degrades, which is what the delivery path already does.

  A non-empty placeholder or weak key is rejected at boot, preventing session and CSRF token forgery. `EMAIL_BACKEND` is also **pinned** unconditionally to `smtp.EmailBackend` — it is not operator-configurable in production, so a console backend cannot be injected. A hand-set `EMAIL_BACKEND` in `.env.prod` is still **read** by `base.py` and then **silently discarded** by the `prod.py` pin, with no boot warning; SMTP is the only supported production transport until a closed transport set exists. (Do not "adopt the `StrEnum` path first" — that set was deliberately never built.)

  The validation is bypassed in two cases: during the Docker image build (`DJANGO_BUILD=1`, build-time `collectstatic`), and for dev one-shot services, which run the bootstrap module `config.settings.oneshot` with `DJANGO_ONESHOT=1` (set on `migrate`, `load_cities`, `load_catalog`, `create_admin`, and `seed` in `docker-compose.dev.override.yml`) — these do not serve HTTP and are fed placeholder/dummy tokens from `.env.dev` during bootstrap. Under `config.settings.prod` the `DJANGO_ONESHOT` flag is ignored (with a boot warning) and the guards always run. In production, `docker-compose.prod.yml` one-shot services run **full** secret validation against the real `.env.prod` values (no bypass flag); the long-lived `web` and `bot` services also never set either flag, so the real secret values are enforced at boot.

> **CI security scanning (SAST):** The CI `security` job runs `bandit` (finding
> 12-OPS-001) from the repository root against `src/backend` and
> `src/telegram_bot` per the `[tool.bandit]` config in `pyproject.toml`. The
> config's `exclude_dirs` excludes the four test trees
> (`src/backend/apps/*/tests/*`, `src/backend/config/settings/tests/*`,
> `src/backend/tests/*`, `src/telegram_bot/tests/*`); `B101` (assert) and `B105`
> (hardcoded password strings) are skipped as pre-existing/mitigated. Running
> from `src/backend` previously resolved the scan roots and config path to
> absent files, so bandit aborted with exit 2 and scanned zero files. This
> complements the existing `pip-audit`, Trivy filesystem scan, and Gitleaks
> secret scan that also run in the `security` job.

### Image tag policy

`docker-compose.prod.yml` requires `IMAGE_TAG` (`${IMAGE_TAG:?...}`) on every application
service — `web`, `bot`, `migrate`, `create_admin`, `seed`, `load_cities`, `load_catalog` and
`scheduler`. It deliberately has **no `latest` default**: a floating default let
`docker compose pull` on two hosts running "the same compose file" move the whole
application to different code with no repository change (09-API-016). `.env.prod.example`
ships a concrete dated tag (`IMAGE_TAG=2026.10.03`), not `latest`.

The deploy job (`.github/workflows/deploy.yml`) overrides `IMAGE_TAG` with the CI commit SHA
and only **pulls** — it must not build. Keep it that way: the image is built and pushed by
CI, and a build step in the deploy job would reintroduce the untraceable-tag problem.

### Deployment Rollback

If a deployment introduces a regression, follow the [Deployment Rollback Runbook](rollback.md).
The runbook covers image-tag rollback (changing `IMAGE_TAG` in `.env.prod` and
re-deploying), config rollback (editing `.env.prod` on the host — the file is
gitignored, so there is no git history to check out),
schema rollback (forward-only Django migrations require a backup restore +
corrective `migrate` step), health-check-gated validation (curl `/health/ready/`
until 200; the probe checks database and cache only — a bot fault does not fail
the gate), rollback-test cadence in staging, and
the failure escalation path. This addresses finding
  [12-OPS-007](../../.ai/plans/12-production-ops-remediation.md).

## Makefile Commands

The project includes a Makefile (`Makefile` for Linux/macOS, `Makefile.ps1` for Windows) that
manages Compose project names automatically. Use `make <target>` — do not call `docker compose`
directly unless you have set `COMPOSE_PROJECT_NAME` explicitly (see
[Compose Project Isolation](#compose-project-isolation)).

### Dev targets (project: `mko-bazuna-dev`)

| Target | Description |
|--------|-------------|
| `make up` | Start dev environment with hot-reload (port 8000) |
| `make down` | Stop and remove dev containers |
| `make build` | Rebuild Docker images |
| `make restart` | Restart the web service |
| `make clean` | Stop containers and remove volumes (`down -v --remove-orphans`) |
| `make fullclean` | Full reset: stop dev+test projects (wipe volumes), prune all unused images, volumes, and build cache |
| `make logs` | Follow dev container logs |
| `make backup` | Create database backup (7-day rotation) |
| `make restore BACKUP_FILE=...` | Restore database from backup |
| `make prune-backups` | Delete backups older than 7 days |

### Django / catalog targets (project: `mko-bazuna-dev`)

| Target | Description |
|--------|-------------|
| `make migrate` | Apply migrations (one-shot, advisory-locked) |
| `make makemigrations` | Create new migration files from model changes |
| `make create-admin` | Create admin user manually |
| `make load-catalog` | Load categories.yaml into DB (one-shot) |
| `make seed` | Re-run seed manually (dev: also auto-runs on `make up`) |
| `make shell` | Open shell in web container |
| `make db-shell` | Open psql in database |
| `make lint` | Run ruff linter |
| `make typecheck` | Run basedpyright type checker |

### Consolidation targets (host-side, project: `mko-bazuna-dev`)

| Target | Description |
|--------|-------------|
| `make consolidate` | Reset apps exceeding 8 migration files back to initial |
| `make consolidate-force` | Reset all migrations unconditionally |

> See [the migration workflow](migration-workflow.md) for full details on consolidation logic and
> rules.

### Test targets (project: `mko-bazuna-test`)

| Target | Description |
|--------|-------------|
| `make test` | Run tests (auto-starts test DB on :5433; uses `--reuse-db`) |
| `make test-db` | Start long-running test PostgreSQL (port 5433, persistent) |
| `make test-down` | Stop test environment (preserves DB for `--reuse-db`) |
| `make test-clean-db` | Drop stale test databases (`test_mko_bazuna*` + `gw*` shards) from the persistent test PG volume |
| `make test-logs` | Follow test environment logs |
| `make test-recreate` | Drop and rebuild test DB schema (`--create-db`) — runs `test-clean-db` first |

## Test Environment

The test environment is fully isolated from the running dev environment via a separate Compose
project name (`mko-bazuna-test`). You can run `make up` (dev, port 8000) and `make test`
simultaneously without service-name, network, or named-volume collisions.

### Architecture comparison

| Aspect | Dev (`mko-bazuna-dev`) | Test (`mko-bazuna-test`) |
|--------|------------------------|--------------------------|
| Compose files | `docker-compose.yml` + `docker-compose.dev.override.yml` | `docker-compose.yml` + `docker-compose.test.yml` |
| Env file | `--env-file .env.dev` | `--env-file .env.test` |
| DB host port | *(not published)* | **5433** → container 5432 |
| DB credentials | `POSTGRES_*` from `.env.dev` | `postgres` / `postgres` / `mko_bazuna` |
| Persistent volume | `mko-bazuna-dev_postgres_data` | `mko-bazuna-test_postgres_data` |
| Source binding | `.:/app` (hot-reload) | `.:/app` (no image rebuild needed) |
| `DEBUG` | `True` | `True` |
| Settings module | `config.settings.dev` | `config.settings.test` |

### Quick start

```bash
# 1. Start the long-running test PostgreSQL (persistent, port 5433)
make test-db

# 2. Run tests (starts test DB if not running; reuses the cached schema)
make test

# 3. (When done) stop the test environment, keeping the DB for the next session
make test-down
```

### Lifecycle commands

| Target | Description |
|--------|-------------|
| `make test-db` | Start only the test PostgreSQL on port `5433` (`restart: unless-stopped`, persistent volume). Idempotent. |
| `make test` | Start the test DB if not running, then run the one-shot `test` container (dev-dependency sync + pytest; the test DB schema and reference data are restored by the autouse conftest fixture). |
| `make test-down` | Stop and remove test containers/networks. The DB **volume is preserved** so `--reuse-db` survives between sessions. |
| `make test-clean-db` | Drop stale `test_mko_bazuna*` and `gw*` databases (from crashed xdist workers) from the persistent test PG volume. Pre-flight for `test-recreate`. |
| `make test-recreate` | Drop and rebuild the test DB schema, ignoring the `--reuse-db` cache (`--create-db`). Runs `test-clean-db` first to clear stuck connections. |
| `make test-logs` | Follow logs from the test project (db + test run output). |

### `--reuse-db` strategy

The `mko-bazuna-test_postgres_data` volume persists across `make test` / `make test-down` cycles.
The `entrypoint-test.sh` script runs:

```bash
uv run pytest --reuse-db --tb=short --durations=10 -n auto --dist loadgroup
```

- `--reuse-db` caches the `test_mko_bazuna` schema between runs (skips the ~1.5 s migration replay).
- `--create-db` forces a full schema drop+rebuild; it is **not** in the entrypoint default. `make test-recreate` adds `--create-db -n auto --maxprocesses=4 --dist loadgroup` to bypass the cache when the schema is stale.
- The test DB has its own named volume (`mko-bazuna-test_postgres_data`) because the test override
  does **not** override the base `volumes:` key — Compose prefixes it with the project name,
  yielding the persistent volume above.
- `--reuse-db` is intentionally **Docker-only**; it is not added to `pyproject.toml` `addopts`, so
  host-side and CI runs (which build a fresh DB each time) are unaffected.

To bypass the cache when the schema is stale:

```bash
make test-recreate   # runs: pytest --create-db --tb=short -n auto --maxprocesses=4 --dist loadgroup
```

### Fast iteration

- The `test` service **bind-mounts the source tree** (`.:/app`) and the entrypoint scripts into
  the container, so changing Python/Django code and re-running `make test` does **not** require
  rebuilding the Docker image. Only `make build` (the full Tailwind CSS + collectstatic builder
  stage) rebuilds the image.
- `init: true` is set on the `test` service for proper signal handling (Ctrl+C propagation) and
  zombie reaping.

### Debugging the test database

The test PostgreSQL is published on host port **5433** (vs. the dev database, which has no host
port). Connect directly for inspection:

```bash
psql -h 127.0.0.1 -p 5433 -U postgres -d mko_bazuna
# password: postgres
```

The test database name is `mko_bazuna`; pytest-django creates the actual `test_mko_bazuna` database
inside the same container, which is what `--reuse-db` caches.

### Recovery from stale project names

If you previously ran `docker compose up` without `make` (or before the `COMPOSE_PROJECT_NAME`
exports existed), containers may be stranded under the default project name `mko_bazuna` (dev) or a
stray `mko_pg_test` container may hold port 5433 (test). `make down` or `make test-db` will then
report "No stopped containers" or a port-conflict error.

**Recovery steps:**

1. **Remove stale dev project** (project `mko_bazuna`):

```bash
docker compose -p mko_bazuna -f docker-compose.yml -f docker-compose.dev.override.yml down --remove-orphans
```

Add `-v` to also wipe its volumes if dev data is regenerable via seed:

```bash
docker compose -p mko_bazuna -f docker-compose.yml -f docker-compose.dev.override.yml down -v --remove-orphans
```

2. **Clear port 5433** (stray `mko_pg_test` container):

```bash
docker rm -f mko_pg_test
```

3. **Recreate under the correct project names:**

```bash
make up         # recreates dev under mko-bazuna-dev
make test-db    # recreates test DB under mko-bazuna-test
```

## Scheduled Jobs

### Scheduler Service (Production)

The scheduler is a production service (`--profile scheduler`) defined in
`docker-compose.yml` and `docker-compose.prod.yml`. It runs **10 hourly sweep
commands + 3 daily commands** in a loop. The dispatch logic is implemented by the
extracted module `apps.core.utils.scheduler` (`src/backend/apps/core/utils/scheduler.py`),
invoked via `python -m apps.core.utils.scheduler` from
`docker/entrypoint-scheduler.sh` (which delegates to `main()`). The scheduler depends on `load_catalog`
completing successfully (`depends_on: condition: service_completed_successfully`).

In `docker-compose.prod.yml` the scheduler service uses `image:` (a pre-built image
from the registry) instead of `build:`, matching every other production service. The
healthcheck script `docker/healthcheck-scheduler.sh` is COPY'd into the image by the
Dockerfile and is referenced by the `healthcheck:` block on the scheduler service.

Scheduler deploy parity — that the service uses `image:` (never `build:`), is gated by
`profiles: ["scheduler"]`, and ships an executable entrypoint — is enforced by CI tests
in `src/backend/tests/test_compose_hardening.py` (finding 12-OPS-009), so the production
compose override stays consistent with this documented configuration.

Each command dispatched by the scheduler is executed via
`subprocess.run(check=False, timeout=settings.SCHEDULER_COMMAND_TIMEOUT)` (default `1800`
seconds); a command that exceeds the timeout raises `TimeoutExpired`, is logged at `ERROR`,
and is skipped so the hourly/daily cycle continues without stalling (ENT-001). Configure
the bound via the `SCHEDULER_COMMAND_TIMEOUT` environment variable (see
[Environment Variables](#environment-variables)).

**Daily dispatch marker.** The three daily commands (`send_alerts`, `rollup_daily_metrics`,
`purge_consent_records`) fire once per calendar day per successful dispatch, not once per process.
`run_scheduler` reads the last successful date from the `scheduler_daily_state` singleton
(`pk=1`) on start-up, and `run_one_cycle` records it only after every daily command
exited `0` with no stop request. A restart mid-day therefore does **not** re-fire the set;
a day whose set failed is retried on the next hourly tick (bounded ~16 attempts). If the
marker cannot be read or written the scheduler **re-runs** the set and never skips it
silently. `send_alerts` additionally exits non-zero if every attempted user failed, which
keeps an all-failed day from being recorded as a success. Every daily command therefore
treats its own exit code as load-bearing and returns `0` on all non-exceptional outcomes —
`purge_consent_records` returns `0` even for an empty eligible set and for `--dry-run` —
because a non-zero exit clears `hourly_marker` and re-runs the whole daily set hourly.
Inspect with `SELECT last_daily, last_daily_completed_at FROM scheduler_daily_state;`.

On `SIGTERM` / `SIGINT` (e.g. `docker stop`), the scheduler installs handlers
(`_handle_shutdown_signal`) that set a module-level stop flag (`_stop_event`). The
inter-cycle wait is **interruptible** — it blocks on that stop event, so the flag ends the
wait immediately instead of at the end of the hour. A stop arriving *during* a cycle
short-circuits the commands that have not started yet; the command already in flight is
never interrupted and runs to completion under `SCHEDULER_COMMAND_TIMEOUT`. The loop then
breaks at its next top-of-iteration check, and `main()` runs `_shutdown()` in a `finally`
block — closing all Django DB connections and logging — so no DB connections leak and a
stop is bounded by one in-flight command rather than by the interval. Skipped sweeps are
not lost work: the loop runs a full cycle on its first iteration after start, and the
service is restarted immediately after a graceful stop (ENT-002).

| Task | Purpose | Schedule |
|------|---------|----------|
| `archive_sweep` | Archive ads older than 2 months | Hourly |
| `delete_sweep` | Hard-delete ads older than 4 months | Hourly |
| `consent_hard_delete` | Erase PII after 30-day withdrawal | Hourly |
| `sweep_drafts` | Delete abandoned DRAFT ads | Hourly |
| `sweep_orphaned_media` | Reclaim orphaned files in MEDIA_ROOT. Bare invocation is the **destructive** default; `--check` is the read-only store/database reconciliation report and exits non-zero on any mismatch (07-MEDIA-012). Advisory lock 103 | Hourly |
| `cleanup_login_tokens` | Remove expired login tokens | Hourly |
| `purge_failed_ads` | Delete failed moderation ads (7 days) | Hourly |
| `purge_rejected_ads` | Delete rejected ads (90 days) | Hourly |
| `purge_deleted_ads` | Purge soft-deleted ads (120 days) | Hourly |
| `purge_media_deletion_errors` | Delete `MediaDeletionError` rows older than `--older-than` days (default 30 — the one operator-overridable retention window). **Irreversible**: run `--dry-run` first. Advisory lock 15. See [`db-retention.md`](../02-database/db-retention.md#purge_media_deletion_errors-07-media-010) | Hourly |
| `send_alerts` | Deliver pending search alerts | Daily at 08:00 UTC (first hourly tick ≥ 08:00 UTC; only if not already completed today) — one digest per user per day, max 10 ads |
| `rollup_daily_metrics` | Roll up daily analytics metrics | Daily at 08:00 UTC |
| `purge_consent_records` | `ConsentRecord` per-field retention: clear the fingerprint fields at 90 d; irreversibly anonymise the actor (`initiated_by`) 12 months after the action unless `legal_hold` is set; retain the consent-event fields. All windows are **project decisions, not legal requirements**. **Never deletes rows** — advisory lock 14. See [`db-retention.md`](../02-database/db-retention.md#purge_consent_records-06-pii-116) | Daily at 08:00 UTC |

Per-user digest fairness note: the 10-ad per-user cap is applied at **collection** time
(in `_collect_alerts`, so the notification rows and the rendered digest are the same set),
in the iteration order of `SavedSearch.objects.filter(is_active=True)` — `saved_searches`,
which has no `Meta.ordering`. A user with two saved searches that each match 10 ads always
receives the first search's ten and defers the second's ten to a later run —
deterministic in practice, but a known fairness wart, not a bug (suppressed ads carry no
notification row and are collected by the next run).

### Scheduler Healthcheck

The scheduler container is monitored by `docker/healthcheck-scheduler.sh`
(`docker-compose.prod.yml` `healthcheck:` block, interval 30s, `start_period: 600s`).
It performs three checks:

1. **PID 1 alive** — `kill -0 1`
2. **Readiness marker exists** — `SCHEDULER_LIVENESS_FILE` (default
   `/tmp/mko_bazuna_scheduler_alive`), written by `apps.core.utils.scheduler` after
   each clean cycle completes via `settings.SCHEDULER_LIVENESS_FILE`
3. **Marker freshness** — if `SCHEDULER_HEALTH_STALE_SECONDS > 0` (read from the environment by `healthcheck-scheduler.sh`; default `0` disables the
   check, set to `7200` on the prod scheduler service), the marker's mtime must be
   within that window (detects retry-loop / stuck scheduler or a failing cycle)

In test settings, `SCHEDULER_LIVENESS_FILE = ""` disables the marker so the scheduler
loop never blocks on file writes during testing.

`start_period` is 600 s because the marker is a success signal, refreshed only after a
cycle in which every dispatched command exited `0` (plus an unconditional refresh on the
process's first cycle). A legitimately slow first cycle — a full hourly set, each command
bounded by `SCHEDULER_COMMAND_TIMEOUT` — would otherwise consume the `3 × 30 s` retry
budget and mark a healthy container `unhealthy`.

#### What `unhealthy` means and how to respond

An `unhealthy` status now means the scheduler is not producing the success signal the
healthcheck expects: either the daily or hourly set is failing, or the scheduler loop
itself is stuck (so no clean cycle has refreshed the marker within the staleness window).

Crucially, this failure is **neither self-healing nor self-announcing**. Docker's
`restart: unless-stopped` policy fires on *container process exit*, not on health status,
and plain `docker compose up` does **not** restart a container that merely reports
`unhealthy` — only Swarm/Kubernetes reconcile on health. The scheduler container therefore
**keeps running** indefinitely in a failing or stuck state until a human intervenes; a
persistently failing cycle does not trigger any automatic restart.

To diagnose:

```bash
docker inspect --format '{{.RestartCount}} {{.State.Health.Status}}' <scheduler-container>
```

`RestartCount` tells you whether the process has actually exited and been restarted (a
separate, louder failure mode), while `State.Health.Status` reflects the liveness-marker
signal. The only place the *reason* appears is the scheduler's own `ERROR` log lines (for
example `Command ... exited with code ...` from a failing dispatched command) — inspect the
service logs for those before acting.

### Running Sweeps

```bash
# Run manually (uses the dev project name automatically)
make shell
# then: python src/backend/manage.py archive_sweep

# Or via docker compose directly
docker compose --env-file .env.dev \
  -f docker-compose.yml -f docker-compose.dev.override.yml \
  run --rm web uv run python src/backend/manage.py archive_sweep

# Or via systemd (bare metal)
# /etc/systemd/system/mko-bazuna-scheduler.service
```

## Nginx Configuration

The nginx configuration (`docker/nginx/nginx.conf`) includes:

### Rate Limiting

Four `limit_req_zone`s are declared in `http{}`, all keyed on `$binary_remote_addr`:
`login_limit` 10r/s, `search_limit` 20r/s, `browse_limit` 20r/s, and `csp_report_limit` 1r/s
(dedicated sink budget, added by 09-API-015). `limit_req_status 429` is set once in `http{}`,
so every limited location answers **429**, not nginx's default 503.

> The zone key is the nginx-observed peer address (`$binary_remote_addr`). That is a
> **different** mechanism from the Django-side peer gate described in
> [Client IP Trust Model](#client-ip-trust-model), which governs how *Django* resolves a
> client IP from forwarding headers — see that section for the application-side rules.

| Location | Zone | Rate | Burst |
|----------|------|------|-------|
| `/login/` | `login_limit` | 10 req/s | 20 |
| `/csp-report/` | `csp_report_limit` | 1 req/s | 5 |
| `/search/` | `search_limit` | 20 req/s | 40 |
| `/` (catch-all) | `browse_limit` | 20 req/s | 40 |
| `/media/` | `browse_limit` | 20 req/s | 40 |
| `/moderation/` | `browse_limit` | 20 req/s | 40 |

**`browse_limit` is ONE shared per-IP bucket, not three separate budgets** — page navigation
and image fetches compete for the same 20r/s. `/media/` uses `burst=40` because one listing
page renders `PER_PAGE = 24` ads (`apps/ads/services/listings_query.py`), so a full grid of
thumbnails fits the burst without a 429 (07-MEDIA-006).

Unrated by design: `/health/`, `/static/`, `/protected-media/` (nginx `internal`; reachable
only after Django's access check issues an `X-Accel-Redirect`), the `~*` script-deny regex
(403 before any limit applies) and `= /metrics` (localhost-only via `allow 127.0.0.1; deny all`).

To measure the **deployed** stack's `/media/` limiting, follow
[`ops-nginx-rate-limit-gate.md`](ops-nginx-rate-limit-gate.md): it aggregates an nginx log capture
into counts for a human to rule on. The ratifying criterion is not restated here — it lives in
[`../99-agent/nginx-rate-limit-attribution-record.md`](../99-agent/nginx-rate-limit-attribution-record.md).

### Security Headers

All responses include:
- `Strict-Transport-Security: max-age=31536000; includeSubDomains; preload`
- `X-Content-Type-Options: nosniff`
- `X-Frame-Options: DENY`
- `Referrer-Policy: strict-origin-when-cross-origin`
- `Permissions-Policy: geolocation=(), microphone=(), camera=()`
- `Content-Security-Policy: default-src 'none'; img-src 'self' data:; object-src 'none'`

### Media Access Control

The `/protected-media/` location serves media files only after Django validates ad status:

```nginx
location /protected-media/ {
    internal;
    alias /media_volume/;
    # ... security headers ...
}
```

### Media Security

- Script execution blocked: `.php`, `.py`, `.cgi`, `.pl`, `.sh` files return 403 — a `~*` regex location `location ~* ^/media/.*\.(?:php|py|cgi|pl|sh)(?:/|$) { deny all; return 403; }` (07-MEDIA-006). The `~*` form is mandatory: a prefix `location /media/` block would replace the proxying block and 403 every genuine photo.
- Only `image/jpeg` served for uploads
- `Content-Disposition: inline` for all media
- `/media/` is rate-limited — see [Rate Limiting](#rate-limiting) above; it reuses the existing `browse_limit` zone (no new `limit_req_zone`, 07-MEDIA-006)
- Storage keys are unguessable `<uuid4>.jpg` with **no `ad_id`** (zone R6: URL anonymity). Three key families exist: `<uuid4>.jpg` for a stored original, `staging/<uuid4>.jpg` in flight, `seed/<filename>.jpg` for generated demo data. Full scheme, the **N ≥ 1 storage-key ownership rule**, the `staging/` byte budget, atomic thumbnail publication and the store/database reconciliation commands: [`media-store-operations.md`](media-store-operations.md)
- The stored original is re-encoded at `STORED_JPEG_QUALITY` (75) to strip EXIF/ICC and thumbnails are derived at `ThumbnailService.QUALITY` (85) — the served photo is **not** the raw Telegram upload. The store is mixed-quality by design and nothing re-derives already-stored bytes

### Client IP Trust Model

Django resolves the rate-limit client IP in `apps/core/utils/client_ip.py`
through a peer gate, not by trusting forwarding headers blindly:

- **Peer gate first.** `REMOTE_ADDR` (the socket peer) is read first. If it is
  loopback, private, or listed in `settings.TRUSTED_PROXY_NETWORKS`, the gate is
  open and forwarded headers may be consulted. Otherwise the peer itself is
  returned and **no header is read** — a public client cannot choose its own
  rate-limit bucket through `X-Real-IP` or `X-Forwarded-For`.
- **Header precedence when trusted.** `X-Real-IP` (set by nginx with
  `proxy_set_header`, which overwrites any client-supplied value) wins; else
  `X-Forwarded-For` is walked **right-to-left** to the first non-private entry;
  else the socket peer. All nginx sites use `$proxy_add_x_forwarded_for`, which
  appends the real client, so the leftmost hop is attacker-controlled and is
  never read.
- **Dev never exercises the untrusted branch.** The default dev stack
  (`docker-compose.dev.override.yml`) publishes Django directly on `:8000`, so
  the peer is loopback — the gate is always open on loopback, and `X-Real-IP`
  supplied directly to Django is trusted in the same way as through nginx.
- **A production public peer is refused by default — unless an operator lists
  it.** When the direct peer is a public address and no listed network contains
  it, the forwarding headers are ignored outright. The guarantee is *no public
  peer is trusted unless an operator explicitly lists a network containing it*:
  adding such a network to `TRUSTED_PROXY_NETWORKS` (e.g. `("0.0.0.0/0",)`)
  deliberately opens the gate for it, which is correct operator-configured
  behaviour, not a bypass.
- **Residual: a private client is trusted as a peer (accepted, not fixed).** A
  client that connects from a private, ULA, or link-local address itself passes
  the peer gate, so a right-to-left `X-Forwarded-For` walk that reaches such an
  entry skips it as a "private proxy hop" and returns the attacker's leftmost
  prefix — e.g. `8.8.8.8, fd00::1234` resolves to `8.8.8.8`. This is
  defence-in-depth only and is left as-is: the primary path is unaffected
  because nginx sets `X-Real-IP` at every location, so a trusted peer with a
  client address never reaches the walk in production. Only an operator who
  fronts Django with a proxy that sends `X-Forwarded-For` but omits `X-Real-IP`
  would expose it.

### Applying a Change to the Nginx Configuration

`docker/nginx/nginx.conf` is a **read-only bind mount** into the nginx
container, taken from the host's own `/app/docker/nginx/nginx.conf`. The
deployment workflow does **not** update it or reload nginx: `deploy.yml`
recreates only the `web` and `bot` services, and its SSH script contains no
`git` command at all, so the pipeline performs **none** of the steps below.
Applying an nginx configuration change is therefore entirely manual:

1. **Pull on the host.** Run `git -C /app pull` on the production host itself.
   `deploy.yml` never runs `git` — `actions/checkout@v4` runs on the ephemeral
   `ubuntu-latest` runner, which never touches the host, so the host's working
   tree is only updated by this manual `git -C /app pull`.
2. **Validate inside the container.** Run `docker compose exec nginx nginx -t`.
   The container is what reads the bind-mounted file, so validation must happen
   there — a host-side `nginx -t` would test a different binary and file.
3. **Reload nginx.** Run `docker compose exec nginx nginx -s reload`.
   `docker compose up -d` alone is **insufficient**: the config is a `:ro` bind
   mount, so the service definition is unchanged and Compose does **not**
   recreate the container — the running nginx keeps serving the old file.
4. **Verify through nginx from outside.** Exercise a real request
   (`https://<host>/…`) and confirm the new behaviour. Do not rely on the
   container-internal `/health/ready/` probe: it talks to `web` directly and
   **passes with nginx stopped**, so it cannot detect a stale or broken nginx
   configuration.
5. **Rollback is manual.** If the change must be undone, revert the file on the
   host (`git -C /app checkout -- docker/nginx/nginx.conf`), re-run steps 2–4.
   There is no automated rollback for nginx: `deploy.yml`'s rollback path
   recreates `web` and `bot` only and never touches the `nginx` service.

## Database Operations

### Backup

```bash
# Using Makefile (project name set automatically)
make backup

# Manual
docker compose --env-file .env.dev \
  -f docker-compose.yml -f docker-compose.dev.override.yml \
  exec -T db pg_dump --no-sync -U $POSTGRES_USER -d $POSTGRES_DB -F c > backups/dump_$(date +%Y%m%d_%H%M%S).dump
```

> **Note:** `pg_dump --no-sync` is used in both the Makefile `backup` target and the production backup
> service (`docker-compose.prod.yml`). The `--no-sync` flag is a `pg_dump`-only optimization that
> skips `fsync` calls during the dump for faster backups; it is **not** valid for `pg_restore`
> (which has no such flag). Backups use custom format (`-F c`), compressed. See
> [Restore Runbook](restore.md) for restore and restore-test procedures.

### Restore

```bash
make restore BACKUP_FILE=./backups/dump_20250719_143022.dump
```

For non-production backup validation and DR drills, use the isolated restore-test target:

```bash
make restore-test BACKUP_FILE=./backups/dump_20250719_143022.dump
```

This restores into a throwaway PostgreSQL container (separate volume, separate DB) and never
touches the live production database. See [Restore Runbook](restore.md) for full details.

### Migration Management

The full development migration workflow — including the consolidation script,
threshold-based reset, advisory-lock behavior, and migration authoring rules — is
documented in [the migration workflow guide](migration-workflow.md).
Summary:

```bash
make migrate         # apply migrations (one-shot, advisory-locked)
make makemigrations  # create new migration files from model changes
make consolidate     # reset apps that exceed 8 files back to one initial migration
```

For production deployment, run migrations as a one-shot service after the database
is healthy (the `migrate` service depends on `db: condition: service_healthy`).

## Admin User Setup

The `create_admin` service creates a pre-configured admin user for Django admin site access.
This is a one-time setup that runs automatically during `make up` when `ADMIN_PASSWORD` is set.

### Pre-configured Admin User

| Attribute | Default Value | Description |
|-----------|---------------|-------------|
| Username | `admin` (or `ADMIN_USERNAME` env var) | Admin login username |
| Password | Set via `ADMIN_PASSWORD` env var | Must be provided for auto-creation |
| Telegram ID | `-1` (or `ADMIN_TELEGRAM_ID` env var) | Placeholder for username/password auth |
| is_staff | `True` | Can access Django admin (resolved to `UserRole.ADMIN` via `User.role` property) |
| is_superuser | `True` | Full admin privileges (resolved to `UserRole.ADMIN` via `User.role` property) |

**Important:** The User model uses `username` as the `USERNAME_FIELD` (not `telegram_id`), so the
Django admin login form displays "Username". Enter the admin username (default: `admin`, or the
`ADMIN_USERNAME` env var) along with the password from the `ADMIN_PASSWORD` env var.

### Automatic Creation

The `create_admin` service runs after migrations complete and creates an admin user if
`ADMIN_PASSWORD` is set in the environment:

```bash
# Set ADMIN_PASSWORD in .env.dev or environment
# Then run:
make up

# Check logs for confirmation
make logs | grep create_admin
```

If `ADMIN_PASSWORD` is empty or not set, the service skips creation with a message:

```
ADMIN_PASSWORD not set, skipping admin user creation
```

### Manual Creation

If `ADMIN_PASSWORD` was not set during initial deployment, use the management command to create the
admin user **for the first time**. This command is for first-time creation only — it is **not** a way
to change the password of an account that already exists (see [Password Change](#password-change)):

```bash
# Create admin user
make create-admin

# Or manually via docker compose
docker compose --env-file .env.dev \
  -f docker-compose.yml -f docker-compose.dev.override.yml \
  run --rm web uv run python src/backend/manage.py create_admin_user \
    --username admin \
    --telegram-id -1 \
    --email admin@example.com
```

`--password` is optional: when it is omitted the command falls back to the `ADMIN_PASSWORD`
environment variable, so the secret does not have to be forced through `argv`:

```bash
docker compose --env-file .env.dev \
  -f docker-compose.yml -f docker-compose.dev.override.yml \
  run --rm web uv run python src/backend/manage.py create_admin_user \
    --username admin \
    --telegram-id -1
```

An explicit `--password` always wins, even when it is empty — the command then fails with
`Password cannot be empty` rather than silently picking up `ADMIN_PASSWORD`. If neither source
supplies a non-empty password the command exits non-zero and creates nothing.

The supplied password is validated against `AUTH_PASSWORD_VALIDATORS` before the user is
created. A real run is refused unless the password:

- contains at least 10 characters;
- is not on Django's common-password list;
- is not entirely numeric;
- is not too similar to the username or email.

`--dry-run` returns *before* this validation, so a successful dry-run is not evidence that the
same password will be accepted by a real run — always pass a policy-compliant password below.

### Dry-Run Mode

Verify what would be created without making changes:

```bash
docker compose --env-file .env.dev \
  -f docker-compose.yml -f docker-compose.dev.override.yml \
  run --rm web uv run python src/backend/manage.py create_admin_user \
    --username admin \
    --password V4lid-Str0ng!Pass \
    --telegram-id -1 \
    --dry-run
```

### Password Change

To change an admin password, use Django's built-in `changepassword` command. It prompts for the
new value on stdin (via `getpass`), so it must be run interactively — **do not** pass `-T`:

```bash
docker compose --env-file .env.prod -f docker-compose.yml -f docker-compose.prod.yml \
  run --rm web /opt/venv/bin/python src/backend/manage.py changepassword <username>
```

Replace `<username>` with the account's `USERNAME_FIELD` value — for this project that is the
`username` column (admin accounts created by `create_admin_user` use the `--username` value).

Use the venv interpreter path `/opt/venv/bin/python` rather than `uv run`: a one-shot `run`
container can fail with a read-only `/opt/venv`, and `uv run` may attempt to re-sync the venv.

`changepassword` enforces `AUTH_PASSWORD_VALIDATORS` against the new value **and**, for the first
time on this path, against the **persisted** user record (the old raw-`set_password` recipe in the
Django shell bypassed every validator). A value that the old recipe would have accepted is now
refused and the command exits non-zero. Note that this only applies to the *next* change: a
credential already stored under the old recipe stays weak until it is changed here.

> `create_admin_user` is **not** an alternative for changing a password. It is idempotent, which
> means it returns early — before any password write — as soon as a user with the same
> `telegram_id` (or `username`) exists, so re-running it with a new `--password` is a no-op.

> **Do not try to change a password from the admin UI.** The user change form at
> `/admin/users/user/<id>/change/` renders a **Reset password** link that does not work: this
> project registers its own `UserAdmin` and declares no `get_urls()`, so the link has no route.
> Following it lands on the admin index with a misleading *"user with ID "1/password" doesn't
> exist. Perhaps it was deleted?"* message, which reads like data loss. The `changepassword`
> command above is the way to change a password. The dead link is a known gap owned by phase 15
> `15-AUTHZ-003`.

### The Admin User Change Form Contract (04-AUT-005)

`UserAdmin` declares an **explicit** field contract instead of letting Django auto-build a form
over every editable `User` field. The auto-built form exposed `password` as a writable text input
whose rendered value was the stored hash, and put `is_superuser` / `is_staff` / `groups` /
`user_permissions` plus every account-state flag in reach of any staff user — and
`has_change_permission` ignores `obj`, so a plain moderator could reach **every** row.

**The change form at `/admin/users/user/<id>/change/` has exactly one writable field.**

| Field | State on the change form |
|-------|--------------------------|
| `preferred_city` | **writable** — the only operator-editable field |
| `password` | present but **inert**: rendered as a masked `hasher.safe_summary()`; a POSTed plaintext value is discarded before validation |
| `is_active`, `is_banned`, `is_deleted`, `is_declined`, `ads_auto_publish`, `telegram_premium`, `telegram_id`, `username`, `first_name`, `last_name`, `email`, `telegram_language`, `source`, `date_joined`, `last_login`, `consent_given_at`, `consent_revoked_at`, `deleted_at` | visible under their fieldset heading but **read-only** |
| `is_superuser`, `is_staff`, `groups`, `user_permissions`, `chat_id` | **not on the form at all** |

The **add** view (`/admin/users/user/add/`) is the one place identity is writable: it uses
`UserCreationForm` and exposes `username`, `telegram_id`, `chat_id`, `password1` and `password2`,
so `AUTH_PASSWORD_VALIDATORS` applies to the new account. It is **superuser-only**
(`has_add_permission` returns `request.user.is_superuser`).

> **Several day-to-day admin operations no longer have a UI path.** Deliberate and knowingly
> accepted — read this table before planning an operational runbook that relies on the user form.

| Operator need | Where it is reachable |
|---|---|
| Ban a user | **Ad** changelist → select ads → *Ban users from selected ads* (`AdAdmin.action_ban_user`); **or** the moderation review page → *Ban* (`moderation/views/review.py::ban_user`, routed at `moderation/urls.py`, `@staff_required`). **Moderators may ban ordinary sellers only** — the target scope lives in `apps.moderation.admin_actions._resolve_ban_targets` (the single home, used by both ban writers) and removes every `is_staff`/`is_superuser` row and the operator's own row from the selection, reporting the skips. A superuser's selection is unrestricted, and "moderator" here means `is_staff`, so a peer moderator is excluded by the same clause. The refusal is **reported**, not silent: the changelist toast counts the dropped rows (error level when the whole selection was refused) and the review page posts a warning naming the refusal. This is a target scope only — approve / reject / soft-delete on a privileged account's ads carry no target guard. It closes none of the rows around it: no un-ban path, no per-request web gate for `is_banned`, no bot-tier gate for `is_banned` / `is_deleted` / `is_declined` (though `is_active` **is** now bot-enforced with a support carve-out, plan 19), no `django_session` janitor, and not the moderator contract (`15-AUTHZ-003`) |
| **Un-ban** a user | **nowhere in the admin** — there is no unban action and no unban service path. `manage.py shell` (`User.objects.filter(…).update(…)`) |
| Disable an account (`is_active = False`) | **Users** changelist → select users → *Deactivate selected users* (`UserAdmin.deactivate_user`, gated by `has_deactivate_permission` → `is_staff or is_superuser`). **Moderators may deactivate ordinary sellers only** — the target scope lives in `apps.users.services.deactivation` and removes every `is_staff`/`is_superuser` row (and the operator's own row) from the selection, reporting the skips (product decision `18-D1` / `18-Q7`). A superuser's selection is unrestricted. Enforced on **both** tiers: the web session is revoked per request, and the bot refuses the account except the **no-argument `/start` / Contact support / support-intake** restoration path (plan 19). See [the system-level record](../99-agent/architecture.md#operator-facing-account-kill-switch-emergent-from-b-01-b-05) |
| Re-enable an account (`is_active = True`) | **Users** changelist → select users → *Reactivate selected users* (`UserAdmin.reactivate_user`). Same target restriction: a moderator may not undo a superuser's disable, and self is always excluded |
| Hard-delete a user | **superuser only** — **Users** changelist → select users → *Delete selected* (`UserAdmin`'s `delete_selected`; `has_delete_permission` → `request.user.is_superuser`). **Irreversible**, and **not** a substitute for `is_active = False` (the row is gone, not disabled) |
| Grant `is_staff` / `is_superuser` / groups | [`create_admin_user`](#manual-creation); the flag flips themselves are not editable |
| Change a password | [`changepassword`](#password-change) — the admin's *Reset password* link has no route |
| Toggle browse-only (`is_declined`) | deliberately unavailable — a form write would skip the `on_commit` search-cache bump, leaving stale listings live |
| Un-soft-delete / undo an erasure (`is_deleted`) | deliberately unavailable — WITHDRAW is terminal and the PII is already nulled |

Disabling an account with `is_active = False` takes effect **immediately on the web tier**:
`login_status` refuses to issue a new session, **and** the already-issued session is treated as
anonymous from the next request on (Django's `AuthenticationMiddleware` resolves the identity per
request, and `ModelBackend` rejects a user whose `is_active` is `False`). The **session cookie
itself survives** until its `expire_date` — the `django_session` row is inert but retained. The
**Telegram bot tier also enforces it**: `AccountStateMiddleware` refuses a deactivated user every
path **except** the no-argument `/start` greeting, the *Contact support* button, and free text in
the support intake — **support is the restoration path** (plan 19, `19-D2`). See
[`architecture.md`](../99-agent/architecture.md#account-state-and-session-revocation-04-aut-002),
where `04-AUT-002` is recorded as **NOT closed** (the residual is now `is_banned` /
`is_deleted` / `is_declined` on both tiers, plus the session janitor).

A ban has a **different** tier profile, and the operator message states both halves. A ban refuses
**login and publishing** and is enforced in the **Telegram bot** (`AccountStateMiddleware` denies
every bot interaction, and ad creation is bot-only), but it does **not** revoke an existing web
session: `MIDDLEWARE` has no per-request account-state gate, and `ModelBackend` consults `is_active`
only — so a banned seller's session keeps working until it expires (14 days). Do not read the ban
row as a total lockout, and do not copy the deactivation wording onto it. The privilege guard above
changes only *which rows* may be banned; neither lever's other tier residuals are closed.

### Changing the Telegram ID Placeholder

If you need to use a different telegram_id for admin login:

```bash
docker compose --env-file .env.dev \
  -f docker-compose.yml -f docker-compose.dev.override.yml \
  run --rm web uv run python src/backend/manage.py create_admin_user \
    --username admin \
    --password your_password \
    --telegram-id -999
```

Then set `ADMIN_TELEGRAM_ID=-999` in your `.env.dev` file and restart the services.

## Seed Data

The project includes a development-only seed command that populates the database with realistic
demo data. This is useful for visual evaluation, pagination testing, and search/filter verification.
Seed also **auto-runs** on `make up` in development (see [Startup Dependency Chain](#startup-dependency-chain)).

For the full seed data generation process — including fixture generation, photo downloads, and LLM
content generation — see [the seed data workflow](seed-workflow.md).

### Running Seed

```bash
# Re-run seed manually (dev: also auto-runs on `make up`)
make seed

# Custom seed parameters via environment variables
SEED_USERS=50 SEED_ADS=200 make seed

# Production (explicit profile, seed does NOT auto-run):
docker compose --env-file .env.prod \
  -f docker-compose.yml -f docker-compose.prod.yml \
  --profile seed run --rm seed
```

**Warning:** The seed command is **destructive** — it deletes all existing seed data before
regenerating. Use `--force` to skip the confirmation prompt.

### What Gets Generated

See [the seed data workflow](seed-workflow.md) for the full list of generated entities, fixture
generation process, and configuration options.

| Entity | Count | Details |
|--------|-------|---------|
| **Categories** | 30 | Real Montenegro classifieds tree (static fixture) |
| **Cities** | 15+ | Real Montenegro cities with regions (static fixture) |
| **Users** | configurable | Fake sellers with unique `telegram_id`, optional username, Russian names |
| **Ads** | configurable | Category-specific ads with multi-language titles/descriptions (ru/en/bs) |
| **Images** | ~90 bundled | CC0 photos (3-16 per category), 1-3 per ad, 3 thumbnail sizes |
| **Analytics events** | auto | `AD_VIEWED` events spread over 90 days |
| **DailyAdMetrics** | auto | Per-ad-per-day view count rollups |

### Seed Service Details

- **Entrypoint:** `docker/entrypoint-seed.sh` — calls `manage.py seed --force` with `SEED_USERS`
  and `SEED_ADS` env var overrides
- **Depends on:** `load_catalog` (condition: `service_completed_successfully`)
- **Volumes:** mounts `media_volume` for photo generation
- **Advisory lock:** uses session-scoped lock ID 110 to prevent concurrent seed operations

## Monitoring & Logging

### Container Health

- **Web:** Exits on crash; `restart: unless-stopped` restarts automatically
- **Bot:** Dual liveness markers: (1) file-based healthcheck via `docker/healthcheck-bot.sh`
  (process alive + `/tmp/mko_bazuna_bot_alive` marker freshness via `BOT_HEALTH_STALE_SECONDS`),
  and (2) Redis-based `bot:liveness` key (epoch timestamp written on startup and every inbound
  update by `LivenessMiddleware` in `telegram_bot/lifecycle.py`, read by the web `/health/ready/`
  readiness probe via `BOT_HEALTH_CHECK_ENABLED`, which defaults off so the probe reports bot as
  `"disabled"` and does not gate readiness by default; the file-based healthcheck remains the
  primary bot alert). Lifecycle hooks in `telegram_bot/lifecycle.py`
  write both markers on startup and clean up the bot session on shutdown.
- **Database:** Healthcheck via `pg_isready`

### Production Logging

The production settings module (`config.settings.prod`) defines a `LOGGING` dict that
configures a console `StreamHandler` on the root logger at `WARNING` level. The
`django`, `django.request` and `django.server` loggers are also `WARNING`, while the
`apps` and `telegram_bot` loggers are explicitly `INFO` (`propagate: False`). Application
loggers for bot update processing, rate-limit hits, dedup suppression, and startup
messages therefore emit at `INFO` and appear in the web/bot container stdout for log
aggregation.

This replaces Django's default logging (`DEFAULT_LOGGING`), which only configured the `django`
logger and silently dropped application-level `INFO` records.

### Log Access

```bash
# Follow all dev logs (project name set automatically)
make logs

# Specific service
docker compose --env-file .env.dev \
  -f docker-compose.yml -f docker-compose.dev.override.yml logs -f bot

# Filter by pattern
make logs | grep "ERROR"
```

### Prometheus Metrics

Production exposes a Prometheus `/metrics` endpoint behind the `web` service (wired via
`django_prometheus` in `INSTALLED_APPS`, middleware, and `path("", include("django_prometheus.urls"))`
in `config/urls.py`). An external Prometheus instance scrapes it on its own schedule.

Because gunicorn runs **3 worker processes** (`workers = 3` in `gunicorn.conf.py`),
each worker owns its own in-process metrics registry. Without multiprocess mode, metrics
gathered by a worker are discarded when that worker is recycled — gunicorn restarts workers
after `max_requests = 1000` (with ±100 jitter) — which causes the scraped `/metrics` output
to jump, drop, or report partial values.

Multiprocess mode fixes this by writing each worker's metric samples to a shared on-disk
directory so the scraper can compute consistent aggregates across all live workers. Three
pieces in production compose must stay in lockstep:

1. **`PROMETHEUS_MULTIPROC_DIR`** environment variable — set to `/tmp/prometheus_multiproc`
   on the `web` service in the **base** [`docker-compose.yml`](../../docker-compose.yml)
   (and in `.env.prod.example`). `prometheus_client` reads this at import time to locate
   the per-worker data files.
2. **`tmpfs` mount** — the base `docker-compose.yml` mounts `/tmp/prometheus_multiproc` as an
   ephemeral tmpfs (`tmpfs: - /tmp/prometheus_multiproc:rw`), so metric files live in memory,
   are writable by the container user, and are discarded on container restart (stale files
   from a crashed worker would otherwise accumulate and skew aggregates).

   **Halves 1 and 2 are a pair, not two independent settings.** `prometheus_client` never
   calls `os.makedirs` on the directory, so the tmpfs mount — created before the container
   starts — is the only thing that makes it exist. The variable alone yields a container that
   boots fine and then raises `FileNotFoundError` on the first metric write (a silently broken
   `/metrics` on a live service); the mount alone is never read. Both halves live in the base
   file so every environment that inherits `gunicorn.conf.py` (dev and prod alike) gets the
   same contract; `docker-compose.prod.yml` overrides only `image:`, `env_file:`, `volumes:`
   and `stop_grace_period` for `web`, and deliberately does not repeat them.
3. **`child_exit` hook** in `gunicorn.conf.py` — when a worker exits (normal recycle or
   crash), Gunicorn calls `child_exit(server, worker)`, which runs
   `prometheus_client.multiprocess.mark_process_dead(worker.pid)`. This flags the exiting
   worker's data files as dead so they are excluded from the next `/metrics` render,
   preventing double-counting or stale-gauge values.

```bash
# Verify the metrics endpoint inside the web container
docker compose --env-file .env.prod \
  -f docker-compose.yml -f docker-compose.prod.yml \
  exec -T web curl -s http://localhost:8000/metrics | head
# Expected: # HELP / # TYPE exposition-format lines
```

> **Note:** The `bot` and `scheduler` services do **not** set
> `PROMETHEUS_MULTIPROC_DIR` — they do not expose a `/metrics` endpoint. Only the
> `web` gunicorn service needs multiprocess mode.

> **Expected flat series:** the `translation_requests_total`, `translation_fallback_total` and
> `translation_circuit_open` series are expected to read **flat (zero/0)** on this endpoint — `web`
> constructs them (it imports `apps.core.services`) but never calls `translate_text`; the real
> increments happen only in `bot` and the `migrate` one-shot, which do not share web's multiprocess
> directory (09-API-017). Do not read these three zeros as an outage.

### Viewing Metrics

```bash
# Show analytics metrics via admin CLI
make shell
# then: python src/backend/manage.py show_metrics
```

## Troubleshooting

### Database Connection Issues

```bash
# Check database health
docker compose --env-file .env.dev \
  -f docker-compose.yml -f docker-compose.dev.override.yml \
  ps db

# Connect directly
make db-shell

# Verify migrations
make migrate
```

### Bot Not Responding

```bash
# Check bot logs
make logs | grep bot

# Verify bot token is set (prints only status, never the token value)
docker compose --env-file .env.dev \
  -f docker-compose.yml -f docker-compose.dev.override.yml \
  exec bot sh -c 'test -n "$BOT_TOKEN" && echo "BOT_TOKEN is set" || echo "BOT_TOKEN is MISSING"'

# Check for Django setup errors
docker compose --env-file .env.dev \
  -f docker-compose.yml -f docker-compose.dev.override.yml \
  exec bot python -c "import django; django.setup(); print('OK')"
```

### Media Files Not Loading

```bash
# Check media volume
docker compose --env-file .env.dev \
  -f docker-compose.yml -f docker-compose.dev.override.yml \
  exec web ls -la /app/media

# Verify file ownership
docker compose --env-file .env.dev \
  -f docker-compose.yml -f docker-compose.dev.override.yml \
  exec web ls -la /app/media/root

# Check nginx logs
make logs | grep nginx
```

A **403 on every image** (not 404) usually means a file-mode problem, not a missing file —
nginx serves `/media/` as a different uid from the app, so a `0600` file is unreadable. See
[`media-store-operations.md`](media-store-operations.md#thumbnail-publication-is-atomic-per-file)
for why published thumbnails are written at `0o666`-and-umask rather than via `mkstemp`, and
check with `ls -l /app/media/*.jpg`.

### Migration Conflicts

```bash
# Check for unapplied migrations
docker compose --env-file .env.dev \
  -f docker-compose.yml -f docker-compose.dev.override.yml \
  run --rm web uv run python src/backend/manage.py showmigrations

# Check for missing migrations
docker compose --env-file .env.dev \
  -f docker-compose.yml -f docker-compose.dev.override.yml \
  run --rm web uv run python src/backend/manage.py makemigrations --check --dry-run
```

### Stale project name containers

See [Recovery from stale project names](#recovery-from-stale-project-names) in the Test
Environment section.

## Related Documentation

- [Local HTTPS with mkcert](local-https-mkcert.md) - Development HTTPS setup for production parity
- [Database Restore Runbook](restore.md)
- [Deployment Rollback Runbook](rollback.md) - Image, config, and schema rollback procedures
- [Migration Workflow](migration-workflow.md) - Dev migration workflow, consolidation, and rules
- [Media Store Operations](media-store-operations.md) - Storage keys, staging budget, thumbnails, store/database reconciliation
- [Seed Data Workflow](seed-workflow.md) - Seed data generation, fixtures, and photo pipeline
- [Architecture Structure](../01-spec/architecture-structure.md)
- [Technical Specification](../01-spec/technical-specification.md)
- [DB Schema](../02-database/db-schema.md)
