# Docker Environment Detailed Plan (Prod/Dev/Test)

> **Wave 0 — Foundation Infrastructure, Sequenced FIRST**
> This plan owns ALL infrastructure files. Feature phases (01-04) MUST NOT recreate:
> - `pyproject.toml`, `uv.lock`
> - `docker/Dockerfile`, `docker/entrypoint.sh`
> - `docker-compose*.yml`
> - `src/backend/config/settings/` package
> - `docker/nginx/nginx.conf`
> - `.env.example`, `.env.dev.example`
> - `Makefile`, `.github/workflows/ci.yml`
> - PgBouncer wiring, backup scripts
>
> Violation of the single-owner rule will cause merge conflicts and drift.

**Wave:** Foundation (cross-cutting infrastructure, **sequence first before Phase 1-4**)
**Depends_on:** None (infrastructure is independent of feature phases)
**Files_modified:** `pyproject.toml`, `uv.lock`, `docker/Dockerfile`, `docker/entrypoint.sh`, `docker-compose.yml`, `docker-compose.dev.override.yml`, `docker-compose.test.yml`, `docker-compose.prod.yml`, `src/backend/config/settings/__init__.py`, `src/backend/config/settings/base.py`, `src/backend/config/settings/dev.py`, `src/backend/config/settings/prod.py`, `src/backend/config/settings/test.py`, `docker/nginx/nginx.conf`, `.env.example`, `.env.dev.example`, `Makefile`, `.github/workflows/ci.yml`, `src/backend/apps/core/utils/advisory_lock.py`
**Autonomous:** Yes

> **Spec source:** `docs/wiki/technical-specification.md` (decisions A-L, zones C1-C12, R1-R9), `docs/wiki/packages.md`, `docs/wiki/architecture-structure.md`, `docs/wiki/db-structure.md`
> **Advisory Lock ID allocation:** Phase 4 = 1-5 (`archive_sweep`, `delete_sweep`, `consent_hard_delete`, `sweep_drafts`, `cleanup_login_tokens`); Phase 2 = 6-7 (`purge_failed_ads`, `purge_rejected_ads`); migrate service = 100 (distinct, non-colliding).

---

## Task 0: pyproject.toml Reconciliation + psycopg3/Django 5.2 Verification (Prerequisite)

**Goal:** Fix critical version contradictions in `pyproject.toml` to enable a buildable Docker environment.

**Acceptance Criteria:**
- `pyproject.toml` contains `requires-python = ">=3.14,<3.15"` (aiogram CalVer upper bound: `Python >=3.10,<3.15` per `docs/wiki/packages.md`)
- `pyproject.toml` contains `django>=5.2.16,<6.0` (Django 5.2.x LTS; corrected from `>=5.2.8` per canonical `docs/wiki/packages.md`)
- `pyproject.toml` contains `psycopg[binary]>=3.2.0` (line corrected from `psycopg2-binary>=2.9.11`)
- `pyproject.toml` removes `psycopg[pool]>=3.2.0` — YAGNI (rule 5). PgBouncer is the external pooler; psycopg `[pool]` extra provides native client-side pooling which is not used.
- `pyproject.toml` includes all spec dependencies (versions per canonical `docs/wiki/packages.md`): `django-environ>=0.11.0`, `django-mptt>=0.18.0`, `django-filter>=26.1`, `aiogram>=3.15.0`, `deep-translator>=1.11.0`, `django-tailwind>=4.4.0`, `django-htmx>=1.19.0`, `pillow>=10.4.0`
- `pyproject.toml` removes `psycopg2-binary` completely
- **NO `python-dotenv` declared directly** — it is TRANSITIVE via `django-environ` (per `docs/wiki/packages.md`)
- `pyproject.toml` `[tool.pytest.ini_options]` contains `asyncio_mode="strict"` and `minversion="8.4"` (required for `pytest-asyncio>=1.4.0`)
- `uv.lock` regenerated with `uv lock --refresh` after changes
- Verification: `uv run python -c "import psycopg; print(psycopg.__version__)"` outputs psycopg3 version (>=3.2.0)
- Verification: `uv run python -c "import django; print(django.VERSION)"` outputs Django 5.2.x
- Verification: `uv run basedpyright src/` passes without psycopg2 errors

**Artifacts:** `pyproject.toml`, `uv.lock` (regenerated)
**Dependencies:** None
**Risks:** Version drift will cause Docker build failures; psycopg3 wheels must exist for Python 3.14 `python:3.14-slim` base image (add `libpq5` to runtime stage if needed).

---

## Task 1: Multi-Stage Dockerfile with Non-Root User + Tailwind Build + collectstatic

**Goal:** Create a secure, production-ready multi-stage Dockerfile that supports both web and bot services.

**Acceptance Criteria:**
- `docker/Dockerfile` uses `python:3.14-slim` as base (owner directive: latest stable Python 3.14; Django 5.2.x LTS supports 3.14 since 5.2.8)
- Builder stage installs `gcc libpq-dev` for psycopg3 compilation
- Builder stage runs `uv sync --frozen --no-install-project` to `/opt/venv`
- **Builder stage runs Tailwind build BEFORE collectstatic**: `uv run tailwind build` generates CSS, then `ENV DJANGO_SETTINGS_MODULE=config.settings.prod` and `uv run python src/backend/manage.py collectstatic --noinput` (static files baked into image via whitenoise)
- Runtime stage copies venv from builder (no build tools in final image)
- Runtime stage creates non-root user `app` (uid 1000) with write access to `/app/media`
- Runtime stage installs runtime library `libpq5` for psycopg3
- Runtime stage sets `ENV PATH="/opt/venv/bin:$PATH"` and `ENV UV_PROJECT_ENVIRONMENT=/opt/venv`
- Runtime stage sets `WORKDIR /app` with `src/backend` importable via the venv site-packages / `PYTHONPATH`
- Verification: `docker build -t mko-bazuna:dev -f docker/Dockerfile .` succeeds
- Verification: Final image has **no gcc/libpq-dev present, non-root user only**. (Advisory: image will be ~400-600MB depending on Pillow/Tailwind layers; this is acceptable for MVP.)

**Artifacts:** `docker/Dockerfile` (completely rewritten), `docker/entrypoint.sh` (created)
**Dependencies:** Task 0
**Risks:** psycopg3 requires `libpq5` at runtime; Tailwind CLI must generate output before collectstatic; collectstatic needs `DJANGO_SETTINGS_MODULE` set to prod settings.

---

## Task 2: Base docker-compose.yml + Named Volumes + Migrate Service

**Goal:** Create the base compose file with shared services, volumes, and one-shot migrate service.

**Acceptance Criteria:**
- `docker-compose.yml` omits obsolete `version:` key (decision C7)
- Contains services: `db` (postgres:18-alpine, healthcheck via `pg_isready`), `migrate` (one-shot service), `web`, `bot`, `nginx`
- Volume `postgres_data` defined for PostgreSQL persistence
- Volume `media_volume` defined for user-uploaded media
- `/static/` is served from whitenoise in the image (NO `static_volume`); `/media/` served by nginx from `media_volume` (read-only)
- `db` has healthcheck: `pg_isready -U ${POSTGRES_USER} -d ${POSTGRES_DB}`
- `migrate` service uses same image, runs advisory-locked migrations (lock ID **100**). Uses **session-scoped** `pg_advisory_lock(100)` which is safe here because migrate runs **before** PgBouncer is attached to the database (no connection pooling). Idempotent on re-run.
- `web` service: `depends_on: migrate` with `condition: service_completed_successfully`
- `bot` service: `depends_on: migrate` with `condition: service_completed_successfully`
- `nginx` service: ports 80/443; mounts `media_volume` read-only; does NOT mount a static volume
- `web` port 8000 is NOT published externally (nginx proxies internally)
- Verification: `docker compose config` validates successfully
- Verification: `docker compose up migrate` runs migrations once; second run does nothing (advisory lock ID 100)

**Artifacts:** `docker-compose.yml` (rewritten), `docker/entrypoint.sh` (migrate logic), `docker/initdb.d/` directory (optional SQL init scripts)
**Dependencies:** Task 1
**Risks:** Migration race between web and bot; use advisory lock ID 100 to prevent concurrent apply.

---

## Task 3: Development Override (docker-compose.dev.override.yml)

**Goal:** Enable hot-reloading development workflow with bind-mounts.

**Acceptance Criteria:**
- `docker-compose.dev.override.yml` extends base `docker-compose.yml`
- `web` service uses `runserver` command: `uv run python src/backend/manage.py runserver 0.0.0.0:8000`
- `web` service has `DEBUG=True` environment
- Both `web` and `bot` bind-mount codebase: `.:/app`
- `bot` service binds same volumes for dev iteration
- `nginx` optional in dev (can be disabled via profile)
- Volume permissions handled for Windows/WSL2: `chown -R 1000:1000 /app/media` in entrypoint if needed
- Verification: `docker compose -f docker-compose.yml -f docker-compose.dev.override.yml up` starts web on port 8000 with hot reload
- Verification: File changes in `src/backend/` reflect immediately in running container

**Artifacts:** `docker-compose.dev.override.yml`, `docker/entrypoint.sh` (dev mode handling)
**Dependencies:** Task 2
**Risks:** Windows file mount performance; documented WSL2 requirement (decision C6).

---

## Task 4: Test Environment (docker-compose.test.yml)

**Goal:** Configure ephemeral real PostgreSQL for CI-compatible testing.

**Acceptance Criteria:**
- `docker-compose.test.yml` defines test-specific services
- Uses `postgres:18` (NOT SQLite — Russian FTS + plpgsql triggers require real PG per decision A6)
- `test` service is one-shot: runs migrate then `pytest --tb=short`
- NO persistent volume for test database (ephemeral)
- Environment variable `DJANGO_SETTINGS_MODULE=config.settings.test` set
- `[tool.pytest.ini_options]` includes `asyncio_mode="strict"` and `minversion="8.4"` (set in Task 0)
- Verification: `docker compose -f docker-compose.yml -f docker-compose.test.yml run --rm test` completes with pytest exit code
- Verification: `uv run pytest` inside test container uses real PostgreSQL connection
- Verification: Test database is destroyed after run (no data leakage)

**Artifacts:** `docker-compose.test.yml`, `src/backend/config/settings/test.py` (created in Task 6), `docker/entrypoint-test.sh`
**Dependencies:** Task 1, Task 6
**Risks:** Test isolation; ensure `pytest-django` creates/destroys test DB correctly.

---

## Task 5: Production Override (docker-compose.prod.yml)

**Goal:** Immutable image deployment with TLS hardening and scheduler.

**Acceptance Criteria:**
- `docker-compose.prod.yml` extends base without bind-mounts
- `web` command uses `gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers 3` (sync WSGI per spec). `WORKDIR=/app` ensures `src/backend/config` is importable.
- `web` has `restart: unless-stopped`
- `bot` command uses `python -m telegram_bot.main` with `restart: unless-stopped`
- `nginx` mandatory with TLS config (cert mount path configurable via env)
- `scheduler` service runs Django management commands in loop (hourly), `restart: unless-stopped`
- Optional `pgbouncer` service available via `--profile pgbouncer` (opt-in per decision C3)
- Verification: `docker compose -f docker-compose.yml -f docker-compose.prod.yml config` validates
- Verification: `docker compose -f docker-compose.yml -f docker-compose.prod.yml --profile pgbouncer config` includes PgBouncer
- Verification: `web` and `bot` ports NOT published to host in prod compose

**Artifacts:** `docker-compose.prod.yml`
**Dependencies:** Task 2, Task 6
**Risks:** TLS cert setup deferred to `docs/ops/tls.md`; initial deploy can use self-signed certs.

---

## Task 6: Settings Package Split (base/dev/prod/test)

**Goal:** Split single `src/backend/config/settings.py` into environment-aware package selected by `DJANGO_SETTINGS_MODULE`.

**Acceptance Criteria:**
- `src/backend/config/settings/` package created with `__init__.py`, `base.py`, `dev.py`, `prod.py`, `test.py`
- `base.py` contains common settings: INSTALLED_APPS, MIDDLEWARE, DATABASES, TEMPLATES, STORAGES (FileSystemStorage contract for later S3 swap)
- `base.py` sets `CONN_MAX_AGE=0` and `OPTIONS={"prepare_threshold": None}` for psycopg3 PgBouncer compatibility (zone C5)
- `base.py` uses PostgreSQL engine ONLY — NO SQLite fallback per `docs/wiki/architecture-structure.md` C5
- `dev.py` inherits from base: `DEBUG=True`, console logging, no SSL redirect
- `prod.py` inherits from base: `DEBUG=False`, `SECURE_SSL_REDIRECT=True`, `SECURE_PROXY_SSL_HEADER=('HTTP_X_FORWARDED_PROTO','https')`, `USE_X_FORWARDED_HOST=True`, secure cookies (`SESSION_COOKIE_SECURE=True`, `CSRF_COOKIE_SECURE=True`)
- `test.py` inherits from base: `DEBUG=True`, test database config, faster password hasher, **uses REAL PostgreSQL (NOT SQLite)**
- All settings use `django-environ` for `.env` parsing (prevents "False"→True string bugs)
- `manage.py`/`wsgi.py`/`asgi.py` `DJANGO_SETTINGS_MODULE` updated; old single `settings.py` deleted
- Verification: `DJANGO_SETTINGS_MODULE=config.settings.dev uv run python src/backend/manage.py check` passes
- Verification: `DJANGO_SETTINGS_MODULE=config.settings.prod uv run python src/backend/manage.py check` passes
- Verification: `DJANGO_SETTINGS_MODULE=config.settings.test uv run python src/backend/manage.py check` passes in test container

**Artifacts:** `src/backend/config/settings/__init__.py`, `src/backend/config/settings/base.py`, `src/backend/config/settings/dev.py`, `src/backend/config/settings/prod.py`, `src/backend/config/settings/test.py`, `src/backend/config/settings.py` (migrated/deleted)
**Dependencies:** Task 0
**Risks:** Migration path from single module; ensure `DJANGO_SETTINGS_MODULE` default is updated in `manage.py`/`wsgi.py`/`asgi.py` and no stale `config.settings` import remains.

---

## Task 7: nginx Configuration with Media Hardening (zone R8)

**Goal:** Implement nginx reverse proxy with strict `/media/` security controls.

**Acceptance Criteria:**
- `docker/nginx/nginx.conf` exists with server blocks
- `/static/` location served from whitenoise in the image (NOT from a volume); 30d cache headers
- `/media/` location served from `/media_volume/` with zone R8 hardening:
  - Script execution blocked: `location ~* /media/.*\.(php|py|cgi|pl|sh)$ { deny all; return 403; }`
  - NOTE: this extends the `docs/wiki/architecture-structure.md` regex (`php|py|cgi`) with `pl|sh` as an intentional hardening extension (defense-in-depth against any interpreted script upload). `docs/wiki/architecture-structure.md` will be updated to match.
  - Header: `X-Content-Type-Options: nosniff always`
  - Header: `Content-Disposition: inline`
  - Header: `X-Frame-Options: DENY always`
  - MIME whitelist: **image/jpeg only** (per decision §4.5); default `application/octet-stream`
  - Header: `Content-Security-Policy: default-src 'none'; img-src 'self' data:; object-src 'none'`
- Reverse proxy to `http://web:8000` with forwarded headers
- TLS termination ready: `listen 443 ssl http2;` with cert paths from env
- HTTP to HTTPS redirect: `return 301 https://$host$request_uri;` (commented for dev, enabled in prod)
- Verification: `curl -I http://localhost/media/test.jpg` in prod returns correct headers
- Verification: Script request blocked: `curl -I http://localhost/media/test.php` returns 403
- Verification: `.sh` script request blocked: `curl -I http://localhost/media/test.sh` returns 403

**Artifacts:** `docker/nginx/nginx.conf`
**Dependencies:** Task 2
**Risks:** MIME whitelist rationale documented: Telegram delivers JPEG only; no png/webp support per spec (decision §4.5).

---

## Task 8: .env.example + .env.dev Templates

**Goal:** Provide environment variable templates without API_ID/API_HASH per spec.

**Acceptance Criteria:**
- `.env.example` contains all necessary variables without secrets:
  - `DJANGO_SECRET_KEY` (placeholder: `<generate-with-django-secret-key-generator>`)
  - `DEBUG` (True/False)
  - `ALLOWED_HOSTS`
  - `DATABASE_URL` (single source of truth for DB config — 12-factor; do NOT also set discrete `DATABASE_HOST`/etc.; if both present, `DATABASE_URL` wins)
  - `BOT_TOKEN` (required for bot operation)
- `.env.dev.example` committed as the dev template; local `.env.dev` created from it (gitignored). Standard naming: commit `.env.example` + `.env.dev.example`; gitignore `.env` and `.env.dev` (no `.env.dev.example` in gitignore).
- **NO `API_ID` or `API_HASH` present** (aiogram Bot API only in phase 1; spec zone R7)
- **Missing `.env` causes container startup failure (fail-fast)** — verified via entrypoint check
- Verification: `docker compose run --rm web env` in dev shows all required variables loaded
- Verification: Container fails fast when `.env` missing

**Artifacts:** `.env.example`, `.env.dev.example`, `.gitignore` entries for `.env` and `.env.dev`
**Dependencies:** Task 6
**Risks:** Secrets management; phase 2 will integrate Docker secrets.

---

## Task 9: Scheduled-Jobs Scheduler Service + Advisory Locks (Wiring Only)

**Goal:** Implement idempotent, locked management commands for background jobs. **This task ONLY wires the scheduler service; command implementations live in feature phases.**

**Acceptance Criteria:**
- `scheduler` container runs in exec loop (or supercronic) with all jobs
- All jobs wrapped in per-job PostgreSQL advisory locks (transaction-scoped, PgBouncer-safe)
- Jobs wired (names MUST match the feature-phase plans, lock IDs MUST NOT collide):
  - `archive_sweep` (2 months after `published_at`, zone J) — defined in Phase 4 Task 2; lock `pg_advisory_xact_lock(1)` (transaction-scoped, released on commit/rollback; safe under PgBouncer)
  - `delete_sweep` (4 months after `published_at`, zone J) — defined in Phase 4 Task 2; lock `pg_advisory_xact_lock(2)`
  - `consent_hard_delete` (30 days after `consent_revoked_at`, zone R1) — defined in Phase 4 Task 2; lock `pg_advisory_xact_lock(3)`
  - `sweep_drafts` (30 minutes idle FSM-draft timeout, zone C8/I) — bot idle-timeout logic in Phase 1 Task 9; the sweep *command* is defined in Phase 4 Task 2; lock `pg_advisory_xact_lock(4)`
  - `cleanup_login_tokens` (expired/consumed tokens, zone C1) — defined in Phase 4 Task 2; lock `pg_advisory_xact_lock(5)`
  - `purge_failed_ads` (7 days after `moderation_failed_at`, zone C4) — defined in Phase 2 Task 4; lock `pg_advisory_xact_lock(6)`
  - `purge_rejected_ads` (90 days after `rejected_at`, zone D4) — defined in Phase 2 Task 5; lock `pg_advisory_xact_lock(7)`
- **migrate service uses lock ID 100** for idempotent one-shot execution (runs before PgBouncer attached; session lock safe, see Task 2 cross-note)
- Each job is idempotent (can run multiple times safely) and wrapped in a per-job lock held for the duration of the command's DB transaction
- **Lock ID range allocation documented**: Phase 4 owns 1-5, Phase 2 owns 6-7, migrate uses 100. Document to prevent future collisions.
- Advisory lock wrapper utility `src/backend/apps/core/utils/advisory_lock.py` provides `advisory_lock(lock_id)` context manager using `pg_advisory_xact_lock(lock_id)` (transaction-scoped, PgBouncer-safe). Uses `logger = logging.getLogger(__name__)` (rule 12 — no `print`)
- `scheduler` service in `docker-compose.prod.yml` uses `profiles: ["scheduler"]` so it only starts when explicitly enabled after Phase 4 commands exist (prevents import crash on missing commands)
- Verification: `docker compose -f docker-compose.yml -f docker-compose.prod.yml --profile scheduler up scheduler` starts scheduler only when opted-in
- Verification: Job lock prevents concurrent runs: stop+restart doesn't duplicate work

**Artifacts:** `scheduler` service in `docker-compose.prod.yml` (gated by `profiles: ["scheduler"]`), `src/backend/apps/core/utils/advisory_lock.py`
**Dependencies:** Task 2, Task 6
**Risks:** Job overlap on restart; use database-level locking.

---

## Task 10: Makefile + Dev Shortcuts

**Goal:** Provide ergonomic developer commands for container-based workflow.

**Acceptance Criteria:**
- `Makefile` contains shortcuts: `up`, `down`, `test`, `lint`, `typecheck`, `shell`, `migrate`, `makemigrations`, `logs`, `backup`, `restore`
- Windows dev is the primary path (decision C6 / WSL2); `Makefile.ps1` is REQUIRED (not optional) with parity to the Makefile targets
- Commands execute inside containers:
  - `make test` → `docker compose -f docker-compose.yml -f docker-compose.test.yml run --rm test`
  - `make lint` → `docker compose run --rm web uv run ruff check src/`
  - `make typecheck` → `docker compose run --rm web uv run basedpyright src/`
  - `make up` → `docker compose -f docker-compose.yml -f docker-compose.dev.override.yml up -d`
- `backup` target runs `pg_dump` with timestamped filenames
- 7-day rotation implemented via `find` or PowerShell equivalent
- Verification: `make help` lists all targets
- Verification: `make lint` exits 0 on clean code

**Artifacts:** `Makefile`, `Makefile.ps1` (required, parity targets)
**Dependencies:** Task 3
**Risks:** Windows PowerShell syntax differs; maintain both or single cross-platform script.

---

## Task 11: CI Pipeline (GitHub Actions)

**Goal:** Automated build and test workflow with real PostgreSQL.

**Acceptance Criteria:**
- `.github/workflows/ci.yml` exists with jobs: `build`, `test`, `lint`, `typecheck`
- Build runs on `ubuntu-latest` with `docker build`
- Test job uses `postgres:18` service with healthcheck
- Test runs pytest inside container against real PostgreSQL
- Lint runs `uv run ruff check src/`
- Typecheck runs `uv run basedpyright src/`
- `uv` cache enabled via `astral-sh/setup-uv@v5`
- Verification: GitHub Actions workflow triggers on push to main/develop
- Verification: CI passes with green checkmark on successful run

**Artifacts:** `.github/workflows/ci.yml`
**Dependencies:** Task 4
**Risks:** UV cache key invalidation; ensure lock file hash used for cache key.

---

## Task 12: PgBouncer Opt-In Profile + Documentation

**Goal:** Add optional PgBouncer service for connection pooling.

**Acceptance Criteria:**
- PgBouncer service defined in `docker-compose.prod.yml` under `profiles: ["pgbouncer"]`
- Uses `edoburu/pgbouncer:1.25.2` image (`bitnami/pgbouncer` is deprecated/dead; no tags on Docker Hub)
- Transaction-mode pooling configured
- Environment variables for `POSTGRES_PASSWORD`, `PGBOUNCER_DATABASE`, etc.
- Healthcheck: `pg_isready -h localhost -p 6432`
- **PgBouncer async safety (zone C5):** `CONN_MAX_AGE=0` enforced in `settings/base.py`; `OPTIONS={"prepare_threshold": None}` per psycopg3 documentation
- Verification: `docker compose -f docker-compose.yml -f docker-compose.prod.yml --profile pgbouncer up` starts PgBouncer
- Verification: Documentation in README describes when/why to enable PgBouncer

**Artifacts:** PgBouncer service block in `docker-compose.prod.yml`, README section on PgBouncer
**Dependencies:** Task 5
**Risks:** Auth mismatch between PgBouncer and PostgreSQL; test connection before prod deploy.

---

## Task 13: DB Backup Script + Restore Runbook

**Goal:** Daily logical backups with retention for operational safety.

**Acceptance Criteria:**
- `backup` service or cron sidecar runs `pg_dump -F c` daily (custom format)
- Backups stored to `./backups/` with filename `dump_YYYYMMDD.dump` (custom format)
- 7-day rotation keeps last 7 dumps (deletes older)
- `Makefile backup` target for manual backup
- Restore procedure documented in `docs/ops/restore.md`:
  - Stop web/bot services
  - Restore: `docker compose exec -T db pg_restore --clean --if-exists -U $POSTGRES_USER -d $POSTGRES_DB ./backups/<file>.dump`
- Verification: `make backup` creates dump file in `./backups/`
- Verification: Backup script is idempotent (re-running doesn't fail)

**Artifacts:** `backup` service in compose, `docs/ops/restore.md`
**Dependencies:** Task 2
**Risks:** Disk space; verify retention works correctly.

---

## Task 14: Verify Wiki Spec Files Alignment

**Goal:** Confirm the spec source-of-truth (`docs/wiki/packages.md`, `docs/wiki/architecture-structure.md`, `docs/wiki/db-structure.md`) agrees with the approved stack.

**Acceptance Criteria:**
- `docs/wiki/packages.md`: confirms Django `>=5.2.16,<6.0`, psycopg3 only (no psycopg2-binary), Python 3.14 compatible.
- `docs/wiki/architecture-structure.md`: confirms `python:3.14-slim` base image and `postgres:18-alpine`; removes `static_volume` references (static served by whitenoise from image, nginx serves `media_volume` only); extends R8 script-block regex to `php|py|cgi|pl|sh` to match this plan's zone R8 hardening.
- `docs/wiki/db-structure.md`: FTS/triggers unchanged; PostgreSQL 18 confirmed. Add a one-line note that GIN/`pg_trgm` indexes should be reindexed after any major PG collation-provider upgrade.

**Artifacts:** `docs/wiki/packages.md`, `docs/wiki/architecture-structure.md`, `docs/wiki/db-structure.md` (verified/edited if needed)
**Dependencies:** Task 0 (version facts)
**Risks:** Editing spec source-of-truth must be reviewed; this task closes the loop so the repo spec no longer contradicts `pyproject.toml`/compose.

---

## Dependency Graph

```
Task 0 → Task 1 → Task 2 → Task 6
                             ├──→ Task 3 (dev)
                             ├──→ Task 4 (test)
                             ├──→ Task 5 (prod)
                             └──→ Task 9 (scheduler)   # wires Phase 2+4 commands
Task 0 → Task 14 (wiki spec alignment verification)
Task 7 (nginx) ← Task 2
Task 8 (.env)  ← Task 6
Task 10 (Makefile) ← Task 3
Task 11 (CI)   ← Task 4
Task 12 (PgBouncer) ← Task 5
Task 13 (backup) ← Task 2
```

> **Cross-plan note:** Task 9's scheduler service requires the Django apps (`apps/core`, `apps/ads`, `apps/users`, `apps/moderation`) created by Phase 1. The management command files are defined in Phase 2 (Tasks 4-5) and Phase 4 Task 2. Sequence Task 9 AFTER Phase 1 completes. The `scheduler` service is gated by `profiles: ["scheduler"]` in `docker-compose.prod.yml` so it only starts when explicitly enabled after Phase 4 commands exist (prevents import crash on missing command modules). Pure-infra Tasks 0-8, 10-14 run before any feature phase. Phase 1 (`01_detailed_plan_publish_discover.md`) references this plan as the sole owner of Dockerfile/compose/nginx/settings and does NOT recreate them.

---

## Environment Matrix

| Aspect | **Dev** | **Test** | **Prod** |
|--------|---------|----------|----------|
| Compose files | base + `dev.override` | `test` overlay | base + `prod` |
| Source | bind-mount (`.:/app`) | ephemeral | baked in image (immutable) |
| Server | `runserver` | pytest runner | `gunicorn` sync WSGI |
| DB | `db` (persistent volume) | ephemeral postgres:18 (no volume) | `db` (persistent volume) |
| Migrations | on-demand / `migrate` svc | in test entrypoint | one-shot `migrate` svc (locked, ID 100) |
| nginx | optional | none | mandatory, TLS + R8 hardening |
| DEBUG | True | True (test settings) | False |
| Secrets | `.env.dev` (from `.env.dev.example`) | CI env vars / generated | `env_file` (Docker secrets later) |
| PgBouncer | off | off | opt-in profile `--profile pgbouncer` |
| Scheduler | manual invoke | off | on (hourly loop) |
| Host ports | web:8000 published | none | 80/443 only |
| Static files | whitenoise in image | whitenoise in image | whitenoise in image |
| Media files | nginx via `media_volume` | nginx via `media_volume` | nginx via `media_volume` |

---

## Rule Compliance Checklist

| Rule | Status | Evidence |
|------|--------|----------|
| 1 (English-only) | OK | Entire plan and all referenced artifacts are English |
| 9 (Type hints / Pydantic) | OK | Pydantic v2 boundary validation referenced as Phase 1 deliverable; infra commands typed |
| 10 (StrEnum for constants) | OK | No domain enums invented in infra; zone constants live in feature apps |
| 11 (Pydantic at boundaries) | OK | Cross-referenced for Phase 1 bot input; not a Docker-plan deliverable |
| 12 (logger not print) | OK | Task 9 advisory-lock util uses `logger = logging.getLogger(__name__)` |
| 13 (migrations) | OK | Migrate guard idempotent + ordered before web/bot; plan creates NO schema (schema is Phase 1+) |
| 15 (small modules) | OK | `advisory_lock.py` is a single small utility; tasks split by concern |

---

## Resolved Audit Findings & Advisory Notes

This section preserves the audit trail (the standalone audit file was removed). All CRITICAL/HIGH/MEDIUM mandatory findings were fixed in the plan body; the advisory notes below are captured so the knowledge is not lost.

**Mandatory findings — RESOLVED in this plan:**
- **C-1 (CRITICAL):** advisory locks use `pg_advisory_xact_lock` (transaction-scoped, PgBouncer-safe) via `apps/core/utils/advisory_lock.py`; migrate keeps a session lock documented as pre-PgBouncer (safe).
- **C-2:** `<300MB` image gate removed; kept no-build-tools + non-root checks + `~400-600MB` advisory.
- **H-1:** PgBouncer image is `edoburu/pgbouncer:1.25.2` (bitnami deprecated/dead).
- **H-2:** `requires-python = ">=3.14,<3.15"` (mirrors aiogram ceiling).
- **H-3:** `scheduler` service gated by `profiles: ["scheduler"]`; cross-plan note updated.
- **H-4:** migrate lock documented as pre-PgBouncer session lock (safe).
- **M-6:** `psycopg[pool]` dropped (YAGNI; PgBouncer is the pooler).
- **M-7:** backup uses `pg_dump -F c` + `pg_restore` (custom format consistent).
- **M-4:** `static_volume` removed from this plan; Task 14 mandates removing it from `docs/wiki/architecture-structure.md`.

**Advisory notes (carried forward, apply at implementation):**
- **M-1 (single-host media):** local `media_volume` is single-host only. Document in `docs/wiki/architecture-structure.md`/runbook: S3/R2 swap (already in `STORAGES` contract) is required before horizontal scaling.
- **M-2 (scheduler robustness):** add a per-job `statement_timeout` (or `signal`-based timeout) and stagger job schedules to avoid a lock-ordering stampede / hung-job block.
- **M-3 (DB config precedence):** derive `DATABASES` from `DATABASE_URL` only (12-factor); if both `DATABASE_URL` and discrete vars are present, `DATABASE_URL` wins (Task 8 updated accordingly).
- **M-5 (.env naming):** commit `.env.example` + `.env.dev.example`; gitignore `.env` and `.env.dev`. Standardized in Task 8.
- **L-2 (Windows dev):** `Makefile.ps1` is REQUIRED (not optional) — Windows/WSL2 is the primary dev path (decision C6).
- **L-4 (lock util SSOT):** Phase 2/4 commands MUST `from apps.core.utils.advisory_lock import advisory_lock` and MUST NOT inline a session-scoped snippet (perpetuates C-1). The util is the single source of truth.
- **L-5 (dev nginx):** dev profile disables nginx by default; the HTTP→HTTPS redirect caveat is moot there (already the case).

**Cross-plan contradiction matrix (verified consistent):** base image `python:3.14-slim`, `postgres:18(-alpine)`, whitenoise `/static/` + nginx `/media/`, R8 regex (Docker extends to `php|py|cgi|pl|sh`; `docs/wiki/architecture-structure.md` to be updated via Task 14), advisory-lock IDs (Phase4=1-5, Phase2=6-7, migrate=100), `CONN_MAX_AGE=0` + `prepare_threshold=None`, pyproject versions, scheduler command names, no-SQLite — all consistent across plans.

---

## Deferred (Post-MVP) Items

- **Docker secrets** (Swarm/K8s) — phase 2, decision A12
- **Self-hosted Plausible/Umami** via Docker — phase 2, decision L
- **Log aggregation** (Loki/Promtail) — phase 2
- **Metrics** (Prometheus/Grafana) — phase 2
- **Point-in-time recovery** (WAL archiving) — phase 2
- **Multi-arch build** (linux/arm64) — phase 2
- **Resource limits** in compose — phase 2
- **scraping_service** (Telethon) compose wiring — phase 5
