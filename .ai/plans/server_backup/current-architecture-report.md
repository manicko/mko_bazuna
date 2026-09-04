# Research Report: Current Architecture of Mko Bazuna

> **Date:** 2026-09-01
> **Source of truth:** Project source code (`C:\py_dev\mko_bazuna`)
> **Confidence levels:** `FACT` = directly read from source code; `INFERENCE` = derived from source.

---

## 1. Deployment Architecture

### 1.1 Docker Compose Files

Four compose files are in the repository root:

| File | Purpose | Tracked in git |
|------|---------|----------------|
| `docker-compose.yml` | Base services: `db`, `redis`, `migrate`, `load_catalog`, `create_admin`, `seed`, `web`, `bot`, `nginx` | Yes |
| `docker-compose.prod.yml` | Production overrides: GHCR image pulls for `web`/`bot`/`migrate`/`create_admin`/`seed`; `scheduler` and `backup` services; nginx TLS cert mount | Yes |
| `docker-compose.dev.override.yml` | Dev overrides: bind-mounts (`.:/app`), runserver hot-reload, seed auto-start via `profiles: !reset []` | Yes |
| `docker-compose.test.yml` | Test overrides: ephemeral DB creds, one-shot `test` service using `test-runtime` Dockerfile target | Yes |

### 1.2 Services in Each Compose File

**Base (`docker-compose.yml`) — 9 services:**

| Service | Image/Build | Command | Profile | Depends On |
|---------|-------------|---------|---------|------------|
| `db` | `postgres:18-alpine` | *(default)* | — | — |
| `redis` | `redis:7-alpine` | `redis-server --save "" --appendonly no` | — | — |
| `migrate` | `build: .` (Dockerfile) | `bash -c "python -c 'from apps.core.utils.migrate_locked import main; sys.exit(main())' && python manage.py setup_search_triggers && python manage.py load_exchange_rates"` | — | `db` (healthy) |
| `load_catalog` | `build: .` | entrypoint `entrypoint-catalog.sh` → `manage.py load_catalog --no-rewrite` | — | `migrate` (completed), `redis` (healthy) |
| `create_admin` | `build: .` | entrypoint `entrypoint-create-admin.sh` | — | `load_catalog` (completed) |
| `seed` | `build: .` | entrypoint `entrypoint-seed.sh` | `["seed"]` | `load_catalog` (completed) |
| `web` | `build: .` | `gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers 3` | — | `load_catalog` (completed), `redis` (healthy) |
| `bot` | `build: .` | `python -m telegram_bot.main` | — | `load_catalog` (completed), `redis` (healthy) |
| `nginx` | `nginx:alpine` | *(default)* | — | `web` |

**Top-level volumes:** `postgres_data`, `media_volume` (lines 208–209).

**Production overrides (`docker-compose.prod.yml`) — 6 additional services:**

| Service | Image/Build | Profile | Notes |
|---------|-------------|---------|-------|
| `web` | GHCR image `${REGISTRY}/${REPOSITORY}:${IMAGE_TAG}` | — | Replaces `build` directive — forces `pull` |
| `bot` | GHCR image | — | Replaces `build` directive |
| `migrate` | GHCR image | — | Replaces `build` directive |
| `create_admin` | GHCR image | — | Replaces `build` directive |
| `seed` | GHCR image | — | Replaces `build` directive |
| `nginx` | volumes override only | — | Adds `${TLS_CERT_PATH:-/etc/nginx/certs}:/etc/nginx/certs:ro` |
| `scheduler` | `build: .` | `["scheduler"]` | Runs `entrypoint-scheduler.sh` |
| `backup` | `postgres:18-alpine` | `["backup"]` | Lines 65–97; inline `/bin/sh -c` script |
| `pgbouncer` | `edoburu/pgbouncer:1.25.2` | `["pgbouncer"]` | Port 6432 |

**Dev overrides (`docker-compose.dev.override.yml`)** replace `web` command with tailwindcss + runserver, set `DEBUG=True`, `DJANGO_SETTINGS_MODULE=config.settings.dev`, bind-mount `.:/app`, publish port `8000:8000`, and clear `seed` profile (`profiles: !reset []`) so seed auto-starts.

**Test overrides (`docker-compose.test.yml`)** define a single additional service `test` (lines 46–76) using `target: test-runtime`, bind-mount source, cache uv downloads via `uv_cache` volume, and set `init: true`.

### 1.3 Compose Project Isolation Model

The `Makefile` (lines 17–22) uses **GNU Make target-specific variable exports** to assign `COMPOSE_PROJECT_NAME`:

```makefile
# Lines 17-19 — all main/dev targets
up down build restart lint typecheck ... backup restore prune-backups ...:
    export COMPOSE_PROJECT_NAME = mko-bazuna-dev

# Lines 21-22 — all test targets
test test-all test-db test-down test-logs test-recreate test-clean-db:
    export COMPOSE_PROJECT_NAME = mko-bazuna-test
```

`Makefile.ps1` (lines 15–16) uses equivalent variables: `$DevProject = "mko-bazuna-dev"`, `$TestProject = "mko-bazuna-test"`.

Each project gets distinct named volumes: `mko-bazuna-dev_postgres_data` vs `mko-bazuna-test_postgres_data`, and `mko-bazuna-test_uv_cache`.

### 1.4 Startup Dependency Chain

```
db (healthy, pg_isready)
  → migrate (one-shot, advisory lock ID 100, exits 0)
    → load_catalog (one-shot: categories.yaml → DB)
      → create_admin (one-shot: skipped if ADMIN_PASSWORD empty; `entrypoint-create-admin.sh`)
        → seed (one-shot, dev auto-starts via profiles:!reset [])
→ redis (healthy)
→ web (gunicorn, 3 workers, long-lived)
→ bot (aiogram, long-lived)
```

Source: `docker-compose.yml` `depends_on` chains (lines 36–38, 60–63, 87–89, 115–117, 142–146, 169–173) and `docs/ops/docker-deployment.md` lines 126–154.

Production deployment: `docker compose --env-file .env.docker -f docker-compose.yml -f docker-compose.prod.yml up -d` then `docker compose run --rm migrate` (lines 271–275 of docker-deployment.md).

### 1.5 Multi-Stage Dockerfile

**File:** `docker/Dockerfile` — 3 stages:

**STAGE 1 — `builder`** (`FROM python:3.14-slim AS builder`, line 8):
- Installs: `curl`, `ca-certificates`, `coreutils`, `gettext` (for compilemessages)
- Installs `uv` from `ghcr.io/astral-sh/uv:latest` (line 24)
- Copies `pyproject.toml` + `uv.lock`, runs `uv sync --frozen --no-install-project --no-dev` into `/opt/venv` (lines 47–49)
- Downloads Tailwind CSS CLI standalone binary to `/usr/local/bin/tailwindcss` (lines 52–54)
- Copies source code (line 57)
- Sets `PYTHONPATH=/app/src:/app/src/backend` (line 62)
- Builds Tailwind CSS: `tailwindcss -i .../input.css -o .../output.css --minify` (line 76)
- Runs `collectstatic --noinput` (line 77)
- Runs `compilemessages --locale ru --locale bs --locale en` (lines 78–83)

**STAGE 2 — `runtime`** (`FROM python:3.14-slim AS runtime`, line 89):
- Installs: `libpq5`, `curl`, `ca-certificates`, `coreutils`, `gettext`
- Creates non-root user: `groupadd -r -g 1000 app`, `useradd -r -u 1000 -g app -d /app app` (lines 103–104)
- Creates directories: `/app/src`, `/app/media`, `/app/staticfiles` (line 105)
- Copies venv from builder (`COPY --from=builder --chown=app:app /opt/venv /opt/venv`)
- Copies tailwindcss binary, source code, `pyproject.toml`/`uv.lock`, `/app/staticfiles`
- Copies entrypoint scripts: `docker/entrypoint*.sh` → `/app/` (lines 127–128)
- Sets `PATH="/opt/venv/bin:${PATH}"`, `UV_PROJECT_ENVIRONMENT=/opt/venv`, `UV_NO_INSTALL_PROJECT=1`, `UV_FROZEN=1`, `PYTHONPATH=/app/src:/app/src/backend`
- `VOLUME ["/app/media"]` (line 146)
- `USER app` (line 149)
- `EXPOSE 8000` (line 151)
- `HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 CMD curl -f http://localhost:8000/health/ || exit 1` (lines 154–155)
- `ENTRYPOINT ["/app/entrypoint.sh"]` (line 157)
- `CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3"]` (line 158)

**STAGE 3 — `test-runtime`** (`FROM runtime AS test-runtime`, line 168):
- Copies `uv` and `uvx` binaries from builder (lines 169–170)
- Runs `uv sync --frozen --no-install-project --group dev` to install test dependencies (pytest, ruff, basedpyright) into the inherited venv (lines 172–173)

### 1.6 Non-root User

The runtime stage runs as uid 1000 / user `app` (lines 102–106, 149). The builder stage runs as root for compilation; only the runtime stage drops privileges.

### 1.7 Healthcheck

**Dockerfile runtime:** `curl -f http://localhost:8000/health/` (line 155).
**Bot healthcheck (compose):** `kill -0 1 2>/dev/null || exit 1` (compose line 190).
**DB healthcheck (compose):** `pg_isready -U ${POSTGRES_USER} -d ${POSTGRES_DB}` (compose line 16).
**Redis healthcheck:** `redis-cli ping` (compose line 26).

---

## 2. Volumes and Data Storage

### 2.1 Named Volumes and Mounts

Defined in `docker-compose.yml` lines 208–209:

```yaml
volumes:
  postgres_data:
  media_volume:
```

| Volume | Mounted By | Mount Path | Mode |
|--------|-----------|------------|------|
| `postgres_data` | `db` | `postgres_data:/var/lib/postgresql` (line 14) | read-write |
| `media_volume` | `web` | `media_volume:/app/media` (line 160) | read-write |
| `media_volume` | `bot` | `media_volume:/app/media` (line 187) | read-write |
| `media_volume` | `seed` | `media_volume:/app/media` (line 133) | read-write |
| `media_volume` | `nginx` | `media_volume:/media_volume:ro` (line 202) | read-only |

**Dev override bind-mounts:** `web` and `bot` additionally bind-mount `.:/app` (dev override lines 22, 41). The seed service in dev also bind-mounts `.:/app` (dev override line 77).

### 2.2 PostgreSQL Data Volume

- Volume: `postgres_data`
- Mount path inside postgres container: `postgres_data:/var/lib/postgresql` (compose line 14)
- In test: prefixed as `mko-bazuna-test_postgres_data` (compose test override lines 6–9 note this; documented in docker-deployment.md lines 404, 444–447)
- **No host port published** in base compose (only in test override: `"5433:5432"` at line 23 of test.yml)

### 2.3 Redis

- Image: `redis:7-alpine` (base compose line 22)
- Command: `redis-server --save "" --appendonly no` (base compose line 24) — **ephemeral, no persistence**
- No persistence volumes defined
- Shared across `web`, `bot`, `scheduler` via `REDIS_URL=redis://redis:6379/0`
- Used for: shared cache (django-redis), rate-limit counters across gunicorn workers + bot
- Dev/test override: `REDIS_URL=` (empty) → falls back to `LocMemCache` (base.py line 257)

### 2.4 Media Storage

**Source files:**
- `src/backend/config/settings/base.py` lines 199–203:
  ```python
  MEDIA_URL = "/media/"
  MEDIA_ROOT = BASE_DIR.parent / "media"
  ```
  `BASE_DIR` resolves to `src/backend/config/settings/base.py` → `src/backend` → `src`. So `MEDIA_ROOT = /app/media`.
- Storage backend: `django.core.files.storage.FileSystemStorage` (base.py lines 215–222, `STORAGES` default)

**File naming:** UUID v4 + `.jpg`
- `src/telegram_bot/services/media.py` line 78: `return f"{uuid.uuid4()}.jpg"` (`generate_storage_key`)
- `AdImage.image` field: `CharField(max_length=64)`, help text: `"Storage key (UUID v4 + .jpg, no ad_id/user/telegram PII)"` (models.py line 523)
- No `user_id`, `telegram_id`, or `username` in the storage key (zone R6 anonymity)

**Image validation — JPEG only, magic bytes:**
- `src/telegram_bot/services/media.py` lines 19–27:
  ```python
  JPEG_MAGIC_BYTES = [b"\xff\xd8\xff"]
  def validate_jpeg_bytes(data: bytes) -> bool:
      if len(data) < 3:
          return False
      return any(data.startswith(magic) for magic in JPEG_MAGIC_BYTES)
  ```
- `validate_photo()` (lines 30–73): checks magic bytes, max 2MB (`len(photo_bytes) > 2 * 1024 * 1024`), max dimensions 2560×2560px
- Bot handler (`ad_create.py` line 695): `is_valid, error = validate_photo(photo_bytes)` → returns 415 if invalid

**EXIF stripping:**
- `save_photo()` (`ad_create.py` lines 961–1006): calls `strip_photo_exif()` via `_write()`
- `strip_photo_exif()` (`media.py` lines 126–144): opens with PIL, applies `ImageOps.exif_transpose()`, pops `exif` from `img.info`, re-saves with `format="JPEG", optimize=True`

**Thumbnail sizes:**
- `src/backend/apps/media/services/thumbnails.py` lines 25–29:
  ```python
  SIZES: dict[ThumbnailSizeStrEnum, tuple[int, int]] = {
      ThumbnailSizeStrEnum.SMALL: (240, 180),
      ThumbnailSizeStrEnum.MEDIUM: (640, 480),
      ThumbnailSizeStrEnum.LARGE: (1280, 960),
  }
  ```
- Quality: 85, Format: JPEG, Resampling: LANCZOS, Progressive: True
- Thumbnail keys: `<uuid>-small.jpg`, `<uuid>-medium.jpg`, `<uuid>-large.jpg` (models.py lines 540, 546, 552)
- `AdImage` model fields: `thumbnail_small`, `thumbnail_medium`, `thumbnail_large` (CharField)

**Image security (nginx):**
- `docker/nginx/nginx.conf` lines 82–97: `/protected-media/` is `internal`, aliased to `/media_volume/`, MIME whitelist `image/jpeg jpg jpeg`, `default_type application/octet-stream`, `Content-Disposition: inline`
- `docker/nginx/nginx.conf` lines 73–79: `/media/` proxies to `web:8000` (Django handles per-request access control)

### 2.5 Static Files

- `STATIC_ROOT`: `STATIC_ROOT = BASE_DIR.parent / "staticfiles"` → `/app/staticfiles` (base.py line 194)
- `STATIC_URL = "/static/"` (base.py line 191)
- Collected at **build time** in Dockerfile STAGE 1 (line 77: `manage.py collectstatic --noinput`)
- Copied into runtime STAGE 2 (line 124: `COPY --from=builder --chown=app:app /app/staticfiles /app/staticfiles`)
- Served by WhiteNoise in the web container (WHITENOISE middleware at base.py line 127)
- nginx proxies `/static/` → `http://web:8000/static/` (nginx.conf lines 55–70), with 30d cache headers + `Cache-Control: public, immutable`
- `ThemeStaticFilesStorage` extends `CompressedManifestStaticFilesStorage`, excludes `input.css` from post-processing (static.py lines 1–55)
- **Static files are reconstructible** from source — not critical for backup (research.md lines 129–137)

---

## 3. Services and Processes

### 3.1 web

- **Server:** gunicorn sync WSGI
- **Workers:** 3 (`--workers 3`, Dockerfile CMD line 158; compose line 141)
- **App:** `config.wsgi:application`
- **Port:** 8000 (NOT published in production; compose comment line 162: "Port 8000 NOT published - nginx proxies internally")
- **Entrypoint:** `entrypoint.sh` (sourced, runs `check_env_file` → `fix_volume_permissions` → `wait_for_db` → `wait_for_redis` → `compile_messages` → `exec "$@"`)
- **Dev override:** replaces command with `tailwindcss ... && python manage.py runserver 0.0.0.0:8000`, publishes port `8000:8000`

### 3.2 bot

- **Framework:** aiogram 3.x (`aiogram>=3.15.0`, pyproject.toml line 18)
- **Command:** `python -m telegram_bot.main` (compose line 168)
- **Entrypoint:** `entrypoint.sh`
- **Healthcheck:** `kill -0 1 2>/dev/null || exit 1` (compose lines 190–194)
  - interval: 30s, timeout: 10s, retries: 3, start_period: 30s
- **Shared ORM:** imports Django via `django.setup()` + shared ORM (per project guidelines)
- Mounts `media_volume:/app/media` for ad photo uploads

### 3.3 scheduler

- **File:** `docker/entrypoint-scheduler.sh` lines 21–65 — uses inline Python script
- **Profile:** `["scheduler"]` (prod compose line 63)
- **Depends on:** `db` (healthy), `redis` (healthy) (prod compose lines 56–60)
- **Loop:** `while True: ... time.sleep(3600)` — hourly cycle
- **Hourly commands** (scheduler lines 28–37):
  - `archive_sweep`
  - `delete_sweep`
  - `consent_hard_delete`
  - `sweep_drafts`
  - `cleanup_login_tokens`
  - `purge_failed_ads`
  - `purge_rejected_ads`
  - `purge_deleted_ads`
- **Daily command at 08:00 UTC** (line 41): `daily_commands = ['send_alerts']`
- Each command uses **PostgreSQL advisory locks** (scheduler comment line 46: "jobs are gated by advisory locks in their implementations")
- AdvisoryLockId values (`src/backend/apps/core/enums.py` lines 23–41):
  - `ARCHIVE_SWEEP = 1`, `DELETE_SWEEP = 2`, `CONSENT_HARD_DELETE = 3`, `SWEEP_DRAFTS = 4`, `CLEANUP_LOGIN_TOKENS = 5`, `PURGE_FAILED_ADS = 6`, `PURGE_REJECTED_ADS = 7`, `ROLLUP_DAILY_METRICS = 8`, `ALERT_DELIVERY_TASK = 9`, `QUEUE_PROCESSING = 10`, `PURGE_DELETED_ADS = 11`, `RECOMPUTE_NORMALIZED_PRICES = 12`, `MIGRATE = 100`, `CREATE_ADMIN = 101`, `BACKFILL_THUMBNAILS = 102`, `SEED = 110`

### 3.4 nginx

- **Image:** `nginx:alpine` (base compose line 197)
- **Ports:** `"80:80"`, `"443:443"` (base compose lines 199–200)
- **Config:** bind-mounted `./docker/nginx/nginx.conf` (base compose line 203)
- **TLS:** certificates mounted via `${TLS_CERT_PATH:-/etc/nginx/certs}` (prod override line 34)
- **Functions:** TLS termination, HTTP→HTTPS redirect, rate limiting, static/media proxying, per-request media access control via `X-Accel-Redirect`

### 3.5 One-shot Services

| Service | Entrypoint | Command | Depends On |
|---------|-----------|---------|------------|
| `migrate` | *(inherited from Dockerfile)* | `bash -c "python -c 'from apps.core.utils.migrate_locked import main...' && manage.py setup_search_triggers && manage.py load_exchange_rates"` | `db` (healthy) |
| `load_catalog` | `entrypoint-catalog.sh` | `manage.py load_catalog --no-rewrite` | `migrate` (completed), `redis` (healthy) |
| `create_admin` | `entrypoint-create-admin.sh` | `manage.py create_admin_user --username ... --password ... --telegram-id ...` | `load_catalog` (completed); skipped if `ADMIN_PASSWORD` empty |
| `seed` | `entrypoint-seed.sh` | `manage.py seed --force --users ${SEED_USERS:-10} --ads ${SEED_ADS:-600}` | `load_catalog` (completed); profile `["seed"]`, reset to `[]` in dev |

### 3.6 migrate_locked

- `src/backend/apps/core/utils/migrate_locked.py` lines 22–33:
  - Imports `advisory_lock` from `apps.core.utils.advisory_lock`
  - Acquires `AdvisoryLockId.MIGRATE = 100` (session-scoped)
  - Then runs Django migrations + sets up search triggers + loads exchange rates
- `advisory_lock.py` lines 18–61: context manager using `pg_advisory_lock` (session) or `pg_advisory_xact_lock` (transaction), with proper cleanup

---

## 4. Environment / Configuration

### 4.1 `.env.docker.example` (root, committed template)

**File:** `C:\py_dev\mko_bazuna\.env.docker.example` (73 lines). Full contents (section by section):

| Section | Variables | Line |
|---------|-----------|------|
| Django | `DJANGO_SECRET_KEY`, `DEBUG=False`, `ALLOWED_HOSTS` | 9–11 |
| PostgreSQL | `POSTGRES_USER=bazuna_user`, `POSTGRES_DB=bazuna_db`, `POSTGRES_PASSWORD=your-password` | 15–17 |
| Redis | `REDIS_URL=redis://redis:6379/0` | 22 |
| Telegram | `BOT_USERNAME=bazuna_bot`, `BOT_TOKEN=` (empty, required in prod) | 25–28 |
| Public site | `SITE_URL=https://mko-bazuna.example.com`, `IMMEDIATE_ALERTS_ENABLED=false` | 34–39 |
| TLS | `TLS_CERT_PATH=/etc/nginx/certs` | 43 |
| Analytics | `PLAUSIBLE_HOST=` (empty to disable) | 47 |
| Admin | `ADMIN_USERNAME=admin`, `ADMIN_PASSWORD=` (empty = skip), `ADMIN_TELEGRAM_ID=-1` | 51–54 |
| Seed | `SEED_USERS=10`, `SEED_ADS=600` | 57–59 |
| Registry | `REGISTRY=ghcr.io`, `REPOSITORY=manicko/mko_bazuna`, `IMAGE_TAG=latest` | 64–66 |
| Runtime | `FIX_PERMISSIONS=0`, `SKIP_ENV_CHECK=` | 69–72 |

Note: `DATABASE_URL` is NOT in `.env.docker` — compose constructs it from `POSTGRES_*` (comment at line 4).

### 4.2 `.env.example` (root, committed template)

**File:** `C:\py_dev\mko_bazuna\.env.example` (82 lines). Similar structure but for local (non-Docker) development. Key differences:
- `REDIS_URL=redis://localhost:6379/0` (localhost, not compose service name)
- `BOT_TOKEN=<your-bot-token-from-botfather>` (placeholder, not empty)
- `SEED_ADS=30` (vs 600 in docker example)
- Documents `DATABASE_URL` as optional for local non-Docker dev (lines 14–21)

### 4.3 `.env.docker` (runtime, NOT committed)

The actual runtime file at `C:\py_dev\mko_bazuna\.env.docker` (43 lines) currently has:
- `DJANGO_SECRET_KEY=<generate-with-django-secret-key-generator>` (placeholder)
- `DEBUG=False`
- `POSTGRES_USER=bazuna_user`, `POSTGRES_DB=bazuna_db`, `POSTGRES_PASSWORD=your-password`
- `BOT_USERNAME=<your-bot-username>`, `BOT_TOKEN=<your-bot-token-from-botfather>`
- `SITE_URL=http://localhost:8000`
- `ADMIN_PASSWORD=` (empty — create_admin skipped)
- `ADMIN_TELEGRAM_ID=-1`
- `SEED_ADS=600`
- No `B2_KEY_ID`, `RESTIC_PASSWORD`, or `HEALTHCHECK_UUID` (the old plan's env vars are NOT in the current file)

### 4.4 Env Var Flow

1. `Makefile` passes `--env-file .env.docker` to compose for dev targets (Makefile line 10: `ENV_FILE := --env-file .env.docker`)
2. Each service binds `.env.docker` as `src/.env:ro` via:
   - `volumes: - ./.env.docker:/app/src/.env:ro` (compose line 51, 78, 104, 159, 186)
3. Django reads via `django-environ` — `env.read_env(BASE_DIR / ".env")` where `BASE_DIR` = `src/backend` (base.py line 28)
4. Compose interpolates `${POSTGRES_DB}` etc. from `.env.docker` via the `--env-file` flag + `env_file:` directive

### 4.5 Production Image Override

`docker-compose.prod.yml` lines 7–26: all services (`web`, `bot`, `migrate`, `create_admin`, `seed`) use:
```yaml
image: ${REGISTRY:-ghcr.io}/${REPOSITORY:-manicko/mko_bazuna}:${IMAGE_TAG:-latest}
```
This replaces the `build:` directive, forcing a pull of the pre-built image from GHCR. Defaults: `ghcr.io/manicko/mko_bazuna:latest`.

### 4.6 Entrypoint Scripts

**File:** `docker/` directory — 6 entrypoint scripts:

| Script | Purpose | Lines |
|--------|---------|-------|
| `entrypoint.sh` | Shared setup functions | 95 |
| `entrypoint-test.sh` | Test runner (pytest) | 44 |
| `entrypoint-seed.sh` | Seed entrypoint | 34 |
| `entrypoint-catalog.sh` | Load catalog entrypoint | 17 |
| `entrypoint-create-admin.sh` | Admin creation entrypoint | 28 |
| `entrypoint-scheduler.sh` | Scheduler loop entrypoint | 66 |

#### Sourced-function pattern (`entrypoint.sh`)

`entrypoint.sh` defines shared functions (`check_env_file`, `fix_volume_permissions`, `wait_for_db`, `wait_for_redis`, `compile_messages`) but only **executes** them when run directly — not when sourced:

```bash
# entrypoint.sh lines 87–95
if [ "${BASH_SOURCE[0]}" = "$0" ]; then
    check_env_file
    fix_volume_permissions
    wait_for_db
    wait_for_redis
    compile_messages
    exec "$@"
fi
```

The `BASH_SOURCE[0] = $0` check ensures that when `entrypoint-seed.sh`, `entrypoint-catalog.sh`, or `entrypoint-create-admin.sh` **source** `entrypoint.sh` (lines 10 of each), only the function definitions are loaded — the caller invokes the functions explicitly:

```bash
# entrypoint-seed.sh line 10
source "${SCRIPT_DIR}/entrypoint.sh"
# entrypoint-seed.sh line 12
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# entrypoint-seed.sh lines 12–15
check_env_file
fix_volume_permissions
wait_for_db
wait_for_redis
```

**`entrypoint-scheduler.sh`** (lines 1–5) does NOT source `entrypoint.sh` — it redefines `check_env_file()` inline with a hardcoded path `/app/src/.env` (line 8). It then jumps directly to the inline Python scheduler loop (lines 21–65).

**`entrypoint-test.sh`** (lines 1–44):
- `unset UV_NO_INSTALL_PROJECT` (line 15) — allows dev deps install
- `uv sync --frozen --no-install-project --group dev` (line 16)
- `uv run python src/backend/manage.py migrate --run-syncdb` (line 21)
- `uv run python src/backend/manage.py load_exchange_rates` (line 22)
- `uv run python src/backend/manage.py setup_search_triggers` (line 23)
- Handles `PYTEST_SKIP_MARKERS` → `-m "not (seed)"` and `PYTEST_OPTS` env vars (lines 36–44)
- Default pytest: `--reuse-db --tb=short --durations=10 -n auto --dist loadgroup`

### 4.7 `.env.docker.example` in Old Plan Directory

**File:** `C:\py_dev\mko_bazuna\.ai\plans\server_backup\.env.docker.example` (25 lines) — this is the STALE template from the old backup plan. It includes variables that do NOT exist in the current implementation:

```env
B2_KEY_ID=
B2_APP_KEY=
RESTIC_PASSWORD=
HEALTHCHECK_UUID=
BACKUP_RETENTION_DAYS=7
BACKUP_RETENTION_WEEKS=4
```

These 6 backup-related variables are **not present** in the current `.env.docker.example` (root, 73 lines) or the actual `.env.docker` (runtime, 43 lines). The old plan proposed Restic + Backblaze B2 with Docker secrets; none of this was implemented.

---

## 5. Existing Backup Implementation (What Actually Exists NOW)

### 5.1 The `backup` Service in `docker-compose.prod.yml` (lines 65–97)

```yaml
# docker-compose.prod.yml lines 65-97
backup:
  image: postgres:18-alpine
  environment:
    POSTGRES_HOST: db
    POSTGRES_PORT: 5432
    POSTGRES_DB: ${POSTGRES_DB:?POSTGRES_DB must be set}
    POSTGRES_USER: ${POSTGRES_USER:?POSTGRES_USER must be set}
    PGPASSWORD: ${POSTGRES_PASSWORD:?POSTGRES_PASSWORD must be set}
  volumes:
    - ./backups:/backups
  command:
    - /bin/sh
    - -c
    - |
      set -e;
      until pg_isready -h $$POSTGRES_HOST -p $$POSTGRES_PORT; do sleep 5; done;
      while true; do
        date=$$(date +%Y%m%d);
        pg_dump -h $$POSTGRES_HOST -p $$POSTGRES_PORT
          -U $$POSTGRES_USER -d $$POSTGRES_DB -F c
          -f /backups/dump_$$date.dump;
        echo "Backup completed: dump_$$date.dump";
        find /backups -name 'dump_*.dump' -mtime +7 -delete 2>/dev/null || true;
        sleep 86400;
      done
  depends_on:
    db:
      condition: service_healthy
  restart: unless-stopped
  profiles:
    - backup
```

**Characteristics (FACT):**
- Image: `postgres:18-alpine` (line 68) — standalone PostgreSQL client image, NOT the app image
- **NO restic** — no AWS credentials, no S3/B2 backend, no deduplication
- **NO offsite storage** — backups stored only on the local `./backups/` volume mount
- **NO media backup** — only `backup:` volume is `./backups:/backups`; `media_volume` is NOT mounted
- **NO encryption** — plain `pg_dump` output
- **NO verification** — no `pg_restore --list` check after dump
- **NO secrets management** — no Docker `secrets:` block, no vault
- **Profile-gated:** `profiles: ["backup"]` (line 96) — only starts with `--profile backup`
- **Schedule:** container runs `while true; ...; sleep 86400` loop — daily at container start time
- **Output filename:** `dump_YYYYMMDD.dump` (date-stamped, no timestamp)
- **Retention:** `find /backups -name 'dump_*.dump' -mtime +7 -delete` — 7-day retention via `find -mtime +7`
- **Format:** `pg_dump -F c` (custom format, compressed)

**Old plan vs. reality gap:** The old `.ai/plans/server_backup/plan.md` (lines 64–102) proposed:
- `build: .` with `dockerfile: docker/Dockerfile.backup` — **does not exist** (confirmed: no `docker/Dockerfile.backup` file)
- Restic + Backblaze B2 with `B2_KEY_ID`, `B2_APP_KEY`, `RESTIC_PASSWORD` — **not implemented**
- Docker secrets (`secrets: restic_pass: file: ./secrets/restic_pass.txt`) — **no `secrets/` directory exists**
- Media backup (`media_volume:/media:ro`) — **not mounted in current backup service**

The current backup service is a **minimal, bare-bones implementation** that does daily `pg_dump` with 7-day local retention only. The old plan was never executed.

### 5.2 Makefile Backup Targets (lines 216–245)

```makefile
# Makefile lines 216-245
BACKUPS_DIR := ./backups

backup:
    @mkdir -p $(BACKUPS_DIR)
    @TIMESTAMP=$$(date +%Y%m%d_%H%M%S) && \
        docker compose $(ENV_FILE) -f docker-compose.yml exec -T db \
            pg_dump -U $${POSTGRES_USER} -d $${POSTGRES_DB} -F c \
            > $(BACKUPS_DIR)/dump_$${TIMESTAMP}.dump && \
        echo "✓ Backup created: $(BACKUPS_DIR)/dump_$${TIMESTAMP}.dump"
    @$(MAKE) prune-backups

restore:
    @if [ -z "$(BACKUP_FILE)" ]; then \
        echo "Error: BACKUP_FILE not specified"; \
        echo "Example: make restore BACKUP_FILE=./backups/dump_20250719_143022.dump"; \
        exit 1; \
    fi
    @if [ ! -f "$(BACKUP_FILE)" ]; then \
        echo "Error: file $(BACKUP_FILE) not found"; \
        exit 1; \
    fi
    docker compose $(ENV_FILE) -f docker-compose.yml exec -T db \
        pg_restore -U $${POSTGRES_USER} -d $${POSTGRES_DB} --clean --if-exists $(BACKUP_FILE)
    @echo "✓ Restore completed from $(BACKUP_FILE)"

prune-backups:
    @find $(BACKUPS_DIR) -name "dump_*.dump" -mtime +7 -delete -print
    @echo "✓ Old backups (older than 7 days) pruned"
```

**Key details:**
- `backup` (line 220): runs `pg_dump` via `docker compose exec -T db`, stores to `./backups/dump_YYYYMMDD_HHMMSS.dump` (timestamped), then calls `prune-backups`
- `restore` (line 229): requires `BACKUP_FILE=...` arg, validates existence, runs `pg_restore --clean --if-exists`
- `prune-backups` (line 243): `find ./backups -name "dump_*.dump" -mtime +7 -delete -print`
- Uses `COMPOSE_FILES` (which includes `--env-file .env.docker`) for project-name isolation (Makefile line 10)
- `.PHONY` declaration includes `backup restore prune-backups clean` (Makefile line 5)

### 5.3 Makefile.ps1 Backup Functions (lines 222–289)

PowerShell equivalents with notable differences:

| Function | Lines | Key Differences vs Makefile |
|----------|-------|----------------------------|
| `Invoke-Backup` | 222–249 | Uses `Get-Date -Format "yyyyMMdd_HHmmss"` (line 229). Uses `Get-ChildItem -Filter "dump_*.dump" \| Where-Object { $_.CreationTime -lt (Get-Date).AddDays(-7) }` for pruning (line 244) — uses `CreationTime` instead of `find -mtime`. Uses `-Force` flag on `Remove-Item` (line 246). Does NOT call `Invoke-PruneBackups` automatically. |
| `Invoke-Restore` | 252–273 | Takes `[Parameter(Mandatory=$true)] [string]$BackupFile`. Uses `Test-Path` for file existence (line 258). Same `pg_restore --clean --if-exists` command but via `docker compose exec -T db`. |
| `Invoke-PruneBackups` | 276–289 | Uses `get-childitem` + `Where-Object { $_.CreationTime }` + `Remove-Item -Force`. Does NOT use `-print` equivalent (no output of pruned files, though it does `Write-Host` the filename). |

**PowerShell differences:** The `-Force` on `Remove-Item` and `CreationTime` (vs `LastWriteTime`/`mtime`) are platform-specific. The Makefile backs up via `docker compose exec -T db pg_dump` (streaming stdout redirect); the PowerShell version does `docker compose exec -T db pg_dump ... > $backupFile` (line 240) — same mechanism.

### 5.4 `.gitignore` — backups directory (line 239)

```
# PostgreSQL backup dumps — may contain PII from `make backup`
backups/
```
Confirmed at `.gitignore` line 239. The entire `backups/` directory is gitignored — backup dumps are NEVER committed.

### 5.5 `docs/ops/restore.md` (complete runbook, 176 lines)

The actual current restore runbook has 3 sections:

1. **Automated Backup Service** (lines 27–40): describes the `postgres:18-alpine` container, `pg_dump -F c`, `dump_YYYYMMDD.dump` naming, 7-day prune, daily `while true` loop
2. **Manual Backup** (lines 42–50): `make backup` → `dump_YYYYMMDD_HHMMSS.dump`
3. **Restore Procedure** (lines 52–127):
   - Identify backup file: `ls -la ./backups/` (line 57)
   - Prerequisites check (lines 63–78): stop `web` and `bot` services
   - **Option A: Manual Restore** (lines 82–107): `docker compose exec -T db pg_restore --clean --if-exists -U $POSTGRES_USER -d $POSTGRES_DB ./backups/<file>`
   - **Option B: Makefile Target** (lines 109–113): `make restore BACKUP_FILE=./backups/...`
   - **Post-Restore Steps** (lines 115–133): `docker compose start web bot`, verify DB connectivity, run migrations

Notable: restore.md example uses `POSTGRES_USER=postgres` and `POSTGRES_DB=postgres` in the manual example (line 104–105), but the actual `.env.docker` uses `POSTGRES_USER=bazuna_user` / `POSTGRES_DB=bazuna_db`. This mismatch is a bug in the docs.

**No media restore section** — restore.md only covers database restore, not media volume recovery.

---

## 6. Database Schema (for Backup Scope)

**Source:** `docs/02-database/db-schema.md` (573 lines), cross-referenced with `docs/02-database/db-indexes.md` and `docs/02-database/db-enums.md`.

### 6.1 Table Catalog (31 tables)

| Table | Description | Key Columns |
|-------|-------------|-------------|
| **users** | User accounts (Telegram-bound) | `id`, `telegram_id` (BIGINT UNIQUE nullable), `chat_id` (BIGINT UNIQUE), `username`, `is_staff`, `is_superuser`, `is_banned`, `is_deleted`, `deleted_at`, `consent_given_at`, `consent_revoked_at`, `source` |
| **login_tokens** | Telegram login tokens | `id`, `token_hash` (CHAR(64) UNIQUE), `telegram_id`, `created_at`, `expires_at` (+5min), `consumed_at` |
| **consent_records** | GDPR consent audit log | `id`, `user_id` (FK nullable SET_NULL), `choice` (StrEnum), `categories` (JSONB), `ip_address` (INET nullable), `user_agent` (TEXT nullable), `consented_at`, `revoked_at` |
| **ads** | Ad listings (single table) | `id`, `user_id`, `title`, `title_ru/en/bs`, `description`, `description_ru/en/bs`, `price_amount`, `price_currency`, `price_normalized_eur`, `category_id`, `city_id`, `category_name` (denormalized), `status` (StrEnum), `source`, `published_at`, `original_published_at`, `archived_at`, `deleted_at`, `moderation_failed_at`, `rejected_at`, `search_vector_*`, `published_by`, `moderated_by` |
| **categories** | MPTT category tree | `id`, `name`, `name_i18n` (JSONB), `slug`, `parent_id`, `is_active` |
| **category_paths** | Multi-parent navigation | `id`, `category_id`, `parent_id`, `sort_order`, `is_automatic` |
| **category_listing_purposes** | Purpose-to-category bindings | `id`, `category_id`, `listing_purpose_id`, `is_default` |
| **category_listing_features** | Feature-to-category bindings | `id`, `category_id`, `feature_id` |
| **category_listing_conditions** | Condition-to-category bindings | `id`, `category_id`, `condition_id`, `is_default` |
| **cities** | City reference data | `id`, `country_code`, `name`, `name_i18n` (JSONB), `region`, `slug` |
| **exchange_rates** | Currency rates to EUR | `id`, `currency` (CurrencyCode), `rate_to_eur`, `effective_date`, `source`, `is_current` |
| **lookup_groups** | Reference data groups | `id`, `code`, `name_i18n` (JSONB), `is_system`, `sort_order` |
| **lookup_items** | Reference values | `id`, `group_id`, `slug`, `name_i18n` (JSONB), `sort_order`, `is_active`, `icon`, `color` |
| **ad_images** | Ad photos | `id`, `ad_id`, `image` (UUID v4 key), `telegram_file_id`, `sha256`, `position`, `thumbnail_small/medium/large` |
| **ad_features** | M2M: Ad ↔ LookupItem (features) | `id`, `ad_id`, `feature_id`, `sort_order` |
| **analytics_events** | Product analytics | `id`, `event_type` (StrEnum), `timestamp`, `user_id` (FK nullable SET_NULL), `ad_id` (FK nullable CASCADE), `source` (StrEnum nullable) |
| **moderation_criteria** | Singleton moderation rules | `id`, `title_min/max_length`, `description_min/max_length`, `price_required`, `min/max_images`, `banned_words` (JSONB), `max_ads_per_user`, `duplicate_title_threshold`, `updated_at`, `updated_by` |
| **moderatoractionlog** | Audit log | `id`, `ad_id` (FK nullable SET_NULL), `user_id` (FK nullable SET_NULL), `action_type` (StrEnum), `reason` (TEXT), `created_at` |
| **daily_ad_metrics** | Daily ad metrics rollup | `id`, `ad_id` (FK CASCADE), `date`, `views_count`, `contacts_count`, `trust_score`, `avg_response_time` |
| **saved_searches** | Buyer saved search queries | `id`, `user_id` (FK CASCADE), `query`, `city_id`, `category_id`, `min_price`, `max_price`, `is_active`, `language`, `last_notified_at`, `unsubscribe_token` (VARCHAR(40), unique) |
| **ad_favorites** | User bookmarked ads | `id`, `user_id`, `ad_id`, `created_at` |
| **saved_search_notifications** | Notification tracking | `id`, `saved_search_id`, `ad_id`, `sent_at` |
| **popular_searches** | Popular search queries | `id`, `query`, `query_normalized`, `hit_count`, `last_seen`, `source` (StrEnum nullable) |
| **search_history** | Per-user search history | `id`, `user_id` (FK nullable CASCADE), `query`, `query_normalized`, `created_at` |
| **seller_trust_scores** | Seller trust scores | `id`, `user_id` (OneToOne CASCADE), `trust_level`, `score`, `ad_count_lifetime`, `ad_count_active`, `rejection_rate`, `contact_response_rate`, `last_calculated` |
| **seller_verifications** | Seller verification | `id`, `user_id` (OneToOne CASCADE), `phone_number`, `verified_by_admin`, `verified_at` |
| **ad_moderation_priorities** | Moderation priority scores | `id`, `ad_id` (OneToOne CASCADE, `related_name="moderation_priority"`), `base_score`, `priority_level`, `flags` (JSONB), `confidence_score`, `escalation_required` |

### 6.2 PII-Sensitive Fields

| Field | Table | PII Type | GDPR/Erasurе Notes |
|-------|-------|----------|-------------------|
| `saved_searches.unsubscribe_token` | `saved_searches` | 32-char opaque capability token | Not user PII; enables anonymous unsubscribe |
| `users.telegram_id` | `users` | Telegram user identifier | NULLified on consent withdrawal (zone F, line 91) |
| `users.chat_id` | `users` | Telegram chat identifier | NULLified on consent withdrawal |
| `users.username` | `users` | Public @username | NULLified on consent withdrawal |
| `users.is_deleted` + `deleted_at` | `users` | Soft-delete flag | Phase 3: PII null; Phase 4: hard-delete after 30 days |
| `login_tokens.token_hash` | `login_tokens` | SHA-256 hash (raw token never stored) | Hashed, not plaintext |
| `consent_records.ip_address` | `consent_records` | IP address | Anonymous-only (nullable) |
| `consent_records.user_agent` | `consent_records` | User agent string | Anonymous-only (nullable) |
| `seller_verifications.phone_number` | `seller_verifications` | Phone number | CASCADE-deleted with user |
| `ad_images.telegram_file_id` | `ad_images` | Telegram file metadata | Not PII (no user linkage in key) |

### 6.3 GDPR / Erasure

- **Soft-delete:** All ad deletions are soft (`status=DELETED`, `deleted_at` populated) — schema line 121–157, db-retention.md line 34
- **30-day consent revocation:** `consent_hard_delete` sweep (advisory lock ID 3, `AdvisoryLockId.CONSENT_HARD_DELETE`) hard-deletes user rows where `consent_revoked_at < now() - ERASURE_RETENTION_DAYS` (default 30). Cascades to Ad→AdImage→SellerVerification. `analytics_events.user_id` and `moderatoractionlog.user_id` are SET NULL (preserve aggregates/audit without PII). (db-schema.md lines 78–79, 105–116; db-retention.md lines 85–106)
- **120-day ad retention:** `purge_deleted_ads` sweep (advisory lock ID 11, `AdvisoryLockId.PURGE_DELETED_ADS`) hard-deletes `DELETED`-status ads older than 120 days. Cascades to `ad_images` via `on_delete=CASCADE`. (db-retention.md lines 47–72)
- **90-day rejected retention:** `purge_rejected_ads` (advisory lock ID 7, `AdvisoryLockId.PURGE_REJECTED_ADS`)
- **7-day failed moderation:** `purge_failed_ads` (advisory lock ID 6)
- **Consent audit trail preserved:** `consent_records` inserts a new row per decision epoch — withdrawal writes a NEW row; history is never overwritten (db-schema.md lines 97–103)

### 6.4 Multi-Currency

- `ads.price_currency`: `CurrencyCode` StrEnum (EUR/RSD/BAM, EUR default) — db-enums.md lines 46–56
- `ads.price_amount`: seller's original amount (source of truth)
- `ads.price_normalized_eur`: derived EUR-normalized value (DECIMAL(12,4), indexed via `IX_ads_price_normalized_eur`)
- `exchange_rates` table: `currency`, `rate_to_eur` (DECIMAL(14,8), EUR=1.0), `effective_date`, `source`, `is_current`, constraint `uq_exchange_rate_current_per_currency`
- `PriceNormalizer` reads current rate (cached 5 min); `recompute_normalized_prices` command (advisory lock ID 12, `RECOMPUTE_NORMALIZED_PRICES`) re-derives after rate changes

### 6.5 Search Vectors (FTS)

- `ads.search_vector` (legacy concatenated TSVECTOR, trigger-maintained)
- `ads.search_vector_ru` (russian config, GinIndex `IX_ads_search_gin_ru`)
- `ads.search_vector_bs` (simple config — no native Bosnian FTS, db-schema.md line 365)
- `ads.search_vector_en` (english config, GinIndex `IX_ads_search_gin_en`)
- Trigger function `ads_search_vector_fn()` (db-indexes.md lines 100–137) — BEFORE INSERT OR UPDATE, fills vectors + `category_name`
- Category name change trigger `categories_name_propagate()` (db-indexes.md lines 147–158)
- PG18 note: reindex GIN indexes after any major PostgreSQL collation-provider upgrade (db-schema.md line 365)

---

## 7. CI/CD

### 7.1 `.github/workflows/ci.yml`

**Jobs:**

| Job | Runner | Env | Purpose |
|-----|--------|-----|---------|
| `build` | ubuntu-latest | — | Dockerfile build with cache-from/to GHCR (`ghcr.io/manicko/mko-bazuna:buildcache`), `push: false` |
| `test` | ubuntu-latest | `PYTHONPATH=src:src/backend` | Full test suite with coverage: `uv run pytest -m "not seed" -n auto --dist loadgroup --tb=short --cov --durations=10 --cov-report=term --cov-report=xml --reuse-db` |
| `lint` | ubuntu-latest | — | `uv run ruff check .` |
| `typecheck` | ubuntu-latest | — | `uv run basedpyright .` |
| `lint-templates` | ubuntu-latest | `PYTHONPATH=.` | `uv run djlint templates/` |
| `i18n` | ubuntu-latest | `PYTHONPATH=src:src/backend` | Compiles translations, runs `test_i18n_completeness.py` + `test_i18n_pipeline.py` |

**CI test setup (lines 39–63):**
- Service container: `postgres:18-alpine`, env: `POSTGRES_DB=mko_bazuna`, `POSTGRES_USER=postgres`, `POSTGRES_PASSWORD=postgres`, port `5432:5432`
- Health check: `--health-cmd pg_isready`, interval 5s, timeout 5s, retries 5
- Installs deps: `uv sync --frozen --no-install-project --group dev` (working-dir: `src/backend`)
- Wait for DB, run `migrate_locked.main()`, compile translations, then pytest

**CI coverage upload (lines 114–119):** `actions/upload-artifact@v4`, `retention-days: 30`, path: `src/backend/coverage.xml`

### 7.2 `.github/workflows/ci-nightly.yml`

- **Schedule:** `cron: "0 3 * * *"` — 03:00 UTC daily
- **Manual trigger:** `workflow_dispatch` (line 6)
- **Concurrency:** `group: nightly-seed-tests`, `cancel-in-progress: false` (lines 8–11)
- **Job:** `seed-tests` — same setup as CI test job, but runs `uv run pytest -m "seed" --tb=short --cov --durations=10 --cov-report=term --cov-report=xml --reuse-db`
- **Artifact retention:** 7 days (shorter than CI's 30 days)

### 7.3 Backup in CI

**No backup testing in CI.** CI uses an ephemeral `postgres:18-alpine` service container (destroyed on workflow completion). The `secrets/` directory, `.env.docker`, and any backup logic are absent from CI workflows. The test environment uses `config.settings.test` with no backup-related env vars. (Confirmed: no `B2_KEY_ID`, `RESTIC_PASSWORD`, or backup-related variables in either CI workflow.)

---

## 8. nginx Configuration

### 8.1 `docker/nginx/nginx.conf` (production, 137 lines)

**Upstreams:**
- Single upstream: `web` at `http://web:8000` (compose service name) — used by `proxy_pass` in all locations (lines 56, 74, 102, 112, 121, 130)

**Rate limiting zones (lines 24–25):**
- `limit_req_zone $binary_remote_addr zone=login_limit:10m rate=10r/s;` (lines 24)
- `limit_req_zone $binary_remote_addr zone=search_limit:10m rate=20r/s;` (line 25)

**Server blocks:**
1. **Port 80** (lines 27–31): HTTP→HTTPS redirect (`return 301 https://$host$request_uri`)
2. **Port 443** (lines 33–136): TLS (HTTP/2 enabled), server_name `_`

**Security headers (server-level, lines 37–47):**
- `Strict-Transport-Security "max-age=31536000; includeSubDomains" always` (line 38)
- `X-Content-Type-Options nosniff always` (line 39)
- `X-Frame-Options DENY always` (line 40)
- `Content-Security-Policy-Report-Only` (line 47) — Report-Only mode, allows `unsafe-inline` for scripts/styles, `img-src 'self' data:`, whitelists `unpkg.com` and `*.plausible.io`

**TLS (lines 48–50):**
- `ssl_certificate /etc/nginx/certs/fullchain.pem;`
- `ssl_certificate_key /etc/nginx/certs/privkey.pem;`

**Location blocks:**

| Location | Proxy | Special Config |
|----------|-------|---------------|
| `/static/` (lines 55–70) | `http://web:8000/static/` | `expires 30d`, `Cache-Control "public, immutable"`, re-declares all security headers |
| `/media/` (lines 73–79) | `http://web:8000` | Proxies to Django for per-request access control |
| `/protected-media/` (lines 82–97) | `alias /media_volume/` | `internal;` (only via X-Accel-Redirect), MIME whitelist `image/jpeg`, `Content-Disposition: inline`, security headers re-declared |
| `/login/` (lines 100–107) | `http://web:8000` | `limit_req zone=login_limit burst=20 nodelay` |
| `/search/` (lines 110–117) | `http://web:8000` | `limit_req zone=search_limit burst=40 nodelay` |
| `/health/` (lines 119–126) | `http://web:8000` | No rate limiting, no auth |
| `/` (lines 129–135) | `http://web:8000` | Default catch-all proxy |

All proxy locations set `Host`, `X-Real-IP`, `X-Forwarded-For`, `X-Forwarded-Proto` headers.

### 8.2 `docker/nginx/nginx.dev.conf` (dev, 129 lines)

**Differences from production `nginx.conf`:**
- HSTS header (`Strict-Transport-Security`) is **omitted** (lines 40–41) — "disabled to prevent browser caching"
- No `/health/` location block (dev config line 120 vs prod line 119–126)
- Same rate limiting zones, TLS config, media access control, and security headers
- Same `/protected-media/` `internal;` + `/media_volume:ro` alias pattern

### 8.3 nginx → media_volume mapping

Production nginx (`docker-compose.yml` line 202): `media_volume:/media_volume:ro`
Dev nginx (`docker-compose.dev.override.yml` line 90): `media_volume:/media_volume:ro`

nginx serves protected media from `/media_volume/` (aliased in nginx.conf line 84), which maps to the Docker named volume `media_volume`, which is concurrently mounted at `/app/media` in `web` and `bot` containers.

---

## 9. Gaps Summary (Stale Plan vs. Current Reality)

| Old Plan Item | Status | Current Reality |
|---------------|--------|-----------------|
| `docker/Dockerfile.backup` (Alpine + Restic) | **Not created** | `docker/Dockerfile.backup` does not exist on filesystem |
| Restic backup to Backblaze B2 | **Not implemented** | Current `backup` service uses bare `postgres:18-alpine` + `pg_dump -F c` only |
| `B2_KEY_ID`, `B2_APP_KEY` env vars | **Absent** | Not in `.env.docker.example` (73 lines) or `.env.docker` (43 lines) |
| `RESTIC_PASSWORD` | **Absent** | Not in any env file |
| `HEALTHCHECK_UUID` | **Absent** | Not in any env file |
| Docker secrets (`secrets/restic_pass.txt`) | **Not created** | No `secrets/` directory exists; no `secrets:` block in any compose file |
| Media volume backup | **Not implemented** | `backup` service in prod.yml mounts only `./backups:/backups`; `media_volume` NOT mounted |
| Backup verification (`pg_restore --list`) | **Absent in service** | No verification step in the `backup` service loop; not in entrypoint scripts |
| Offsite/off-server storage | **Absent** | All backups stored locally on `./backups/` volume mount only |
| Backup restore.sh script | **Not created** | Only Makefile `restore` target (docker exec pg_restore) and `docs/ops/restore.md` runbook |

**Bottom line:** The current backup implementation is a minimal daily `pg_dump` with 7-day local retention (lines 65–97 of `docker-compose.prod.yml`) plus ad-hoc Makefile targets (lines 216–245 of `Makefile`). The old plan proposed Restic + B2 + Docker secrets + media backup + verification + offsite sync — **none of which was implemented**. The `secrets/` directory, `Dockerfile.backup`, and `scripts/backup.sh`/`scripts/restore.sh` referenced in the old plan do not exist on the filesystem.

---

