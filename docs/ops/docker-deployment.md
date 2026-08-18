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
- **Redis cache service (production):** `redis:7-alpine` provides a shared cache backend across web gunicorn workers (3) and the bot process. `LocMemCache` is per-process only and cannot share rate-limit counters or cache invalidations. Dev/test settings override `CACHES` to `LocMemCache`, so no Redis is needed for local development or testing.

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
| Dev | `mko-bazuna-dev` | `docker compose --env-file .env.docker -f docker-compose.yml -f docker-compose.dev.override.yml <cmd>` | `.env.docker` |
| Test | `mko-bazuna-test` | `docker compose -f docker-compose.yml -f docker-compose.test.yml <cmd>` | *(none — test vars are inline in the override)* |

> **Note:** The test recipes do **not** pass `--env-file .env.docker`. Test credentials and settings
> are defined inline in `docker-compose.test.yml` (user: `postgres`, db: `mko_bazuna`, password:
> `postgres`).

> **Warning:** A plain `docker compose up` (without `make` or `--env-file`) silently falls back to
> the directory-name default project `mko_bazuna`. This causes a project-name mismatch with
> Makefile-managed containers and leads to stale, orphaned containers. Always use `make` or
> replicate the exact invocation form above with the correct `COMPOSE_PROJECT_NAME`.

### Environment files

| File | Purpose | Tracked in git |
|------|---------|----------------|
| `.env.docker` | App secrets/creds; passed via `--env-file` and bind-mounted into containers as `src/.env` (also used via `env_file:` in compose) | No (runtime secrets, gitignored) |
| `.env.docker.example` | Template for `.env.docker`; committed to git with placeholder values; copy to `.env.docker` and fill in real values | Yes (template, placeholders only) |
| `.env` | Auto-loaded by Compose for `${VAR}` interpolation in YAML only; sets no `COMPOSE_PROJECT_NAME` | No (gitignored) |

Never set `DATABASE_URL` in `.env.docker` — Compose constructs it from the `POSTGRES_*` variables so
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
  docker compose --project-name mko-bazuna-dev --env-file .env.docker -f docker-compose.yml -f docker-compose.dev.override.yml up -d

  # Stop dev (equiv. to: make down)
  docker compose --project-name mko-bazuna-dev --env-file .env.docker -f docker-compose.yml -f docker-compose.dev.override.yml down

  # Rebuild images without cache (equiv. to: make build)
  docker compose --project-name mko-bazuna-dev --env-file .env.docker -f docker-compose.yml -f docker-compose.dev.override.yml build --no-cache

  # Full environment reset (equiv. to: make clean)
  docker compose --project-name mko-bazuna-dev --env-file .env.docker -f docker-compose.yml -f docker-compose.dev.override.yml down -v --remove-orphans
  docker compose -p mko-bazuna-dev --env-file .env.docker -f docker-compose.yml -f docker-compose.dev.override.yml down --rmi all -v
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
      → create_admin (one-shot, skipped if ADMIN_PASSWORD is empty)
        → seed (one-shot, auto-runs in dev)
  → web (gunicorn, long-lived)
  → bot (aiogram, long-lived)
```

- **`db`** — PostgreSQL 18 with a `pg_isready` healthcheck. `web` and `bot` both block on
  downstream one-shot services completing successfully.
- **`migrate`** — runs `manage.py migrate --noinput` inside a PostgreSQL advisory lock (ID 100) so
  concurrent runs are serialized. Exits 0 on success (including a fresh DB with no pending
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
# Configure environment: copy .env.docker.example to .env.docker and fill in your real values
#   - BOT_TOKEN: your Telegram bot token from @BotFather
#   - DJANGO_SECRET_KEY: python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
#   - POSTGRES_PASSWORD: database password

# Start dev environment (project: mko-bazuna-dev)
make up

# The dependency chain runs automatically:
# db → migrate → load_catalog → create_admin → seed → web, bot
# Web is served at http://localhost:8000 (hot-reload enabled)
```

### Database Configuration

Docker Compose automatically constructs `DATABASE_URL` from the `POSTGRES_*` variables using the
`db` service hostname:

```
postgres://${POSTGRES_USER}:${POSTGRES_PASSWORD}@db:5432/${POSTGRES_DB}
```

**Important:** Do NOT set `DATABASE_URL` in `.env.docker` — the compose files build it from the
individual database variables (`POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`), ensuring the
correct hostname (`db`) is used for inter-container communication.

For local Django development outside Docker (using `uv run` directly), use `.env` (auto-loaded by
Compose) with `DATABASE_URL` pointing to `localhost`:

```bash
# Start Django locally (not in Docker)
uv run python src/backend/manage.py runserver
```

### Development Services

| Service | Port | Description |
|---------|------|-------------|
| `web` | 8000 | Django development server (hot-reload enabled) |
| `bot` | — | Telegram bot (logs to stdout) |
| `db` | — | PostgreSQL 18 (internal, no host port) |
| `nginx` | 80/443 | Optional; use `profiles: ["use-nginx"]` to enable |

### Full environment reset

If you encounter stale containers or build issues:

```bash
# 1. Stop and remove all dev containers and volumes
# Windows: .\Makefile.ps1 down  — or single-line:
#   docker compose --project-name mko-bazuna-dev --env-file .env.docker -f docker-compose.yml -f docker-compose.dev.override.yml down -v

make down    # or: docker compose --env-file .env.docker \
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

### Production-like Development

For full production parity with nginx TLS termination, see
[Local HTTPS with mkcert](local-https-mkcert.md) for certificate setup.

```bash
# Run without nginx (direct web access on port 8000)
make up

# Or run with nginx for production-like HTTPS (requires mkcert setup)
COMPOSE_PROJECT_NAME=mko-bazuna-dev docker compose --env-file .env.docker \
  -f docker-compose.yml -f docker-compose.dev.override.yml --profile use-nginx up -d
```

Windows (PowerShell 5.1+) — single line, no `\` continuation:

```powershell
# Windows equivalents:
.\Makefile.ps1 up

# Or with nginx for production-like HTTPS (requires mkcert setup):
docker compose --project-name mko-bazuna-dev --env-file .env.docker -f docker-compose.yml -f docker-compose.dev.override.yml --profile use-nginx up -d
```

**Note:** Running with `--profile use-nginx` requires TLS certificates. Follow the mkcert setup
guide for local HTTPS development.

## Production Deployment

### Docker Compose Production

```bash
# Copy .env.docker.example to .env.docker and fill in production values
# Then start services:
docker compose --env-file .env.docker -f docker-compose.yml -f docker-compose.prod.yml up -d

# Apply migrations (run once)
docker compose --env-file .env.docker -f docker-compose.yml run --rm migrate
```

### Production Services

| Service | Image/Command | Notes |
|---------|---------------|-------|
| `db` | `postgres:18-alpine` | Persistent volume `postgres_data` |
| `migrate` | Build image, runs migrations | One-shot service with advisory lock |
| `create_admin` | Build image, creates admin user | One-shot service, idempotent |
| `seed` | Build image, `entrypoint-seed.sh` | One-shot service, gated by `profiles: ["seed"]`. Populates database with demo data. See [Seed Data](#seed-data) below. |
| `web` | Build image, gunicorn | Port 8000 not published; nginx proxies |
| `bot` | Build image, `python -m telegram_bot.main` | Restarts on failure |
| `nginx` | `nginx:alpine` | Ports 80/443; TLS termination |

### TLS Configuration

Mount TLS certificates at `/etc/nginx/certs/` in the nginx container:

```bash
# Using Let's Encrypt certificates
docker compose --env-file .env.docker -f docker-compose.yml -f docker-compose.prod.yml up -d
```

The production override file (`docker-compose.prod.yml`) includes:
- HTTPS listener on port 443
- HTTP to HTTPS redirect on port 80
- TLS certificate paths configurable via `TLS_CERT_PATH`

### Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `BOT_TOKEN` | Yes | Telegram bot token from @BotFather |
| `DJANGO_SECRET_KEY` | Yes | Django secret key for signing |
| `POSTGRES_USER` | Yes | Database username |
| `POSTGRES_PASSWORD` | Yes | Database password |
| `POSTGRES_DB` | Yes | Database name |
| `BOT_USERNAME` | Yes | Telegram bot username (without @) |
| `TLS_CERT_PATH` | No | Path to TLS certs (default: `/etc/nginx/certs/`) |
| `PLAUSIBLE_HOST` | No | Analytics host for traffic tracking |
| `ADMIN_USERNAME` | No | Admin username (default: admin) |
| `ADMIN_PASSWORD` | No* | Admin password; required for auto-creation |
| `ADMIN_TELEGRAM_ID` | No | Placeholder telegram_id (default: -1) |
| `SEED_USERS` | No | Number of demo users to generate (default: 10) |
| `SEED_ADS` | No | Number of demo ads to generate (default: 30) |

**Note:** `DATABASE_URL` is automatically constructed from `POSTGRES_*` variables in Docker
containers. Do not set `DATABASE_URL` in `.env.docker` — the compose files build it from the
individual database variables.

*Required for automatic admin creation via `create_admin` service. Can be created manually if not set.

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
| `make build` | Rebuild Docker images without cache |
| `make restart` | Restart the web service |
| `make clean` | Stop containers and remove volumes (`down -v --remove-orphans`) |
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
| `make test-logs` | Follow test environment logs |
| `make test-recreate` | Drop and rebuild test DB schema (`--no-reuse-db --create-db`) |

## Test Environment

The test environment is fully isolated from the running dev environment via a separate Compose
project name (`mko-bazuna-test`). You can run `make up` (dev, port 8000) and `make test`
simultaneously without service-name, network, or named-volume collisions.

### Architecture comparison

| Aspect | Dev (`mko-bazuna-dev`) | Test (`mko-bazuna-test`) |
|--------|------------------------|--------------------------|
| Compose files | `docker-compose.yml` + `docker-compose.dev.override.yml` | `docker-compose.yml` + `docker-compose.test.yml` |
| Env file | `--env-file .env.docker` | *(none — test vars are inline in the override)* |
| DB host port | *(not published)* | **5433** → container 5432 |
| DB credentials | `POSTGRES_*` from `.env.docker` | `postgres` / `postgres` / `mko_bazuna` |
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
| `make test` | Start the test DB if not running, then run the one-shot `test` container (migrate + pytest). |
| `make test-down` | Stop and remove test containers/networks. The DB **volume is preserved** so `--reuse-db` survives between sessions. |
| `make test-recreate` | Drop and rebuild the test DB schema, ignoring the `--reuse-db` cache (`--no-reuse-db --create-db`). |
| `make test-logs` | Follow logs from the test project (db + test run output). |

### `--reuse-db` strategy

The `mko-bazuna-test_postgres_data` volume persists across `make test` / `make test-down` cycles.
The `entrypoint-test.sh` script runs:

```bash
pytest --reuse-db --create-db --tb=short
```

- `--reuse-db` caches the `test_mko_bazuna` schema between runs (skips the ~1.5 s migration replay).
- `--create-db` makes Django rebuild the schema whenever migrations diverge.
- The test DB has its own named volume (`mko-bazuna-test_postgres_data`) because the test override
  does **not** override the base `volumes:` key — Compose prefixes it with the project name,
  yielding the persistent volume above.
- `--reuse-db` is intentionally **Docker-only**; it is not added to `pyproject.toml` `addopts`, so
  host-side and CI runs (which build a fresh DB each time) are unaffected.

To bypass the cache when the schema is stale:

```bash
make test-recreate   # runs: pytest --no-reuse-db --create-db --tb=short
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

### Hourly Sweeps

The platform runs several periodic cleanup tasks:

| Task | Purpose | Schedule |
|------|---------|----------|
| `archive_sweep` | Archive ads older than 2 months | Hourly |
| `delete_sweep` | Hard-delete ads older than 4 months | Hourly |
| `consent_hard_delete` | Erase PII after 30-day withdrawal | Hourly |
| `sweep_drafts` | Delete abandoned DRAFT ads | Hourly |
| `cleanup_login_tokens` | Remove expired login tokens | Hourly |
| `purge_failed_ads` | Delete failed moderation ads (7 days) | Hourly |
| `purge_rejected_ads` | Delete rejected ads (90 days) | Hourly |

### Running Sweeps

```bash
# Run manually (uses the dev project name automatically)
make shell
# then: python src/backend/manage.py archive_sweep

# Or via docker compose directly
docker compose --env-file .env.docker \
  -f docker-compose.yml -f docker-compose.dev.override.yml \
  run --rm web uv run python src/backend/manage.py archive_sweep

# Or via systemd (bare metal)
# /etc/systemd/system/mko-bazuna-scheduler.service
```

## Nginx Configuration

The nginx configuration (`docker/nginx/nginx.conf`) includes:

### Rate Limiting

| Endpoint | Rate Limit | Burst |
|----------|------------|-------|
| `/login/` | 10 req/s | 20 |
| `/search/` | 20 req/s | 40 |

### Security Headers

All responses include:
- `Strict-Transport-Security: max-age=31536000; includeSubDomains`
- `X-Content-Type-Options: nosniff`
- `X-Frame-Options: DENY`
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

- Script execution blocked: `.php`, `.py`, `.cgi`, `.pl`, `.sh` files return 403
- Only `image/jpeg` served for uploads
- `Content-Disposition: inline` for all media
- Storage keys are UUID v4 (unguessable, non-sequential)

## Database Operations

### Backup

```bash
# Using Makefile (project name set automatically)
make backup

# Manual
docker compose --env-file .env.docker \
  -f docker-compose.yml -f docker-compose.dev.override.yml \
  exec -T db pg_dump -U $POSTGRES_USER -d $POSTGRES_DB -F c > backups/dump_$(date +%Y%m%d_%H%M%S).dump
```

### Restore

```bash
make restore BACKUP_FILE=./backups/dump_20250719_143022.dump
```

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
| Email | (empty) | Optional; can be set via `ADMIN_EMAIL` |
| is_staff | `True` | Can access Django admin |
| is_superuser | `True` | Full admin privileges |

**Important:** The User model uses `username` as the `USERNAME_FIELD` (not `telegram_id`), so the
Django admin login form displays "Username". Enter the admin username (default: `admin`, or the
`ADMIN_USERNAME` env var) along with the password from the `ADMIN_PASSWORD` env var.

### Automatic Creation

The `create_admin` service runs after migrations complete and creates an admin user if
`ADMIN_PASSWORD` is set in the environment:

```bash
# Set ADMIN_PASSWORD in .env.docker or environment
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

If `ADMIN_PASSWORD` was not set during initial deployment, or you need to create/change the
password later, use the management command:

```bash
# Create admin user
make create-admin

# Or manually via docker compose
docker compose --env-file .env.docker \
  -f docker-compose.yml -f docker-compose.dev.override.yml \
  run --rm web uv run python src/backend/manage.py create_admin_user \
    --username admin \
    --password your_secure_password \
    --telegram-id -1

# With custom values
docker compose --env-file .env.docker \
  -f docker-compose.yml -f docker-compose.dev.override.yml \
  run --rm web uv run python src/backend/manage.py create_admin_user \
    --username myadmin \
    --password new_password \
    --telegram-id -1 \
    --email admin@example.com
```

### Dry-Run Mode

Verify what would be created without making changes:

```bash
docker compose --env-file .env.docker \
  -f docker-compose.yml -f docker-compose.dev.override.yml \
  run --rm web uv run python src/backend/manage.py create_admin_user \
    --username admin \
    --password test123 \
    --telegram-id -1 \
    --dry-run
```

### Password Change

To change the admin password, use Django's built-in password change command:

```bash
# Open Django shell in web container
make shell

# In the shell:
from django.contrib.auth import get_user_model
User = get_user_model()
user = User.objects.get(telegram_id=-1)  # or username='admin'
user.set_password('new_secure_password')
user.save()
exit()
```

Or use the `create_admin_user` command again with a new password - it's idempotent and will
skip if a user with the same `telegram_id` already exists:

```bash
# This will skip if telegram_id=-1 already exists
make create-admin
```

### Changing the Telegram ID Placeholder

If you need to use a different telegram_id for admin login:

```bash
docker compose --env-file .env.docker \
  -f docker-compose.yml -f docker-compose.dev.override.yml \
  run --rm web uv run python src/backend/manage.py create_admin_user \
    --username admin \
    --password your_password \
    --telegram-id -999
```

Then set `ADMIN_TELEGRAM_ID=-999` in your `.env.docker` file and restart the services.

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
docker compose --env-file .env.docker \
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
- **Bot:** Healthcheck verifies process is running; logs emitted via stdout
- **Database:** Healthcheck via `pg_isready`

### Log Access

```bash
# Follow all dev logs (project name set automatically)
make logs

# Specific service
docker compose --env-file .env.docker \
  -f docker-compose.yml -f docker-compose.dev.override.yml logs -f bot

# Filter by pattern
make logs | grep "ERROR"
```

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
docker compose --env-file .env.docker \
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

# Verify bot token
docker compose --env-file .env.docker \
  -f docker-compose.yml -f docker-compose.dev.override.yml \
  exec bot env | grep BOT_TOKEN

# Check for Django setup errors
docker compose --env-file .env.docker \
  -f docker-compose.yml -f docker-compose.dev.override.yml \
  exec bot python -c "import django; django.setup(); print('OK')"
```

### Media Files Not Loading

```bash
# Check media volume
docker compose --env-file .env.docker \
  -f docker-compose.yml -f docker-compose.dev.override.yml \
  exec web ls -la /app/media

# Verify file ownership
docker compose --env-file .env.docker \
  -f docker-compose.yml -f docker-compose.dev.override.yml \
  exec web ls -la /app/media/root

# Check nginx logs
make logs | grep nginx
```

### Migration Conflicts

```bash
# Check for unapplied migrations
docker compose --env-file .env.docker \
  -f docker-compose.yml -f docker-compose.dev.override.yml \
  run --rm web uv run python src/backend/manage.py showmigrations

# Check for missing migrations
docker compose --env-file .env.docker \
  -f docker-compose.yml -f docker-compose.dev.override.yml \
  run --rm web uv run python src/backend/manage.py makemigrations --check --dry-run
```

### Stale project name containers

See [Recovery from stale project names](#recovery-from-stale-project-names) in the Test
Environment section.

## Related Documentation

- [Local HTTPS with mkcert](local-https-mkcert.md) - Development HTTPS setup for production parity
- [Database Restore Runbook](restore.md)
- [Migration Workflow](migration-workflow.md) - Dev migration workflow, consolidation, and rules
- [Seed Data Workflow](seed-workflow.md) - Seed data generation, fixtures, and photo pipeline
- [Architecture Structure](../01-spec/architecture-structure.md)
- [Technical Specification](../01-spec/technical-specification.md)
- [DB Schema](../02-database/db-schema.md)
