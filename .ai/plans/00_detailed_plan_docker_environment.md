# Docker Environment Detailed Plan (Prod/Dev/Test)

> **Naming note:** This is an infrastructure/foundation plan, NOT a feature phase. The `05_`
> file index only orders it after the existing `01`–`04` detailed plans; it is intentionally
> distinct from "Phase 5 (Scraping Service + UI Translation)" in `01_plan_development_phases.md`
> and from `deffered_phase2_05_detailed_plan_scraping_i18n.md`. Refer to this work as the
> **Docker Environment** plan, not "Phase 5".

**Wave:** Foundation (cross-cutting infrastructure)  
**Depends_on:** None to build the environment; the `apps/core/management/commands/*` jobs in Task 9 consume Django apps produced by `01_detailed_plan_publish_discover.md` (Phase 1). The compose/image/settings work (Tasks 0–8, 10–13) is independent and can proceed first.  
**Files_modified:** `pyproject.toml`, `uv.lock`, `docker/Dockerfile`, `docker/entrypoint.sh`, `docker-compose.yml`, `docker-compose.dev.override.yml`, `docker-compose.test.yml`, `docker-compose.prod.yml`, `src/backend/config/settings/base.py`, `src/backend/config/settings/dev.py`, `src/backend/config/settings/prod.py`, `src/backend/config/settings/test.py`, `docker/nginx/nginx.conf`, `.env.example`, `.env.dev`, `Makefile`, `.github/workflows/ci.yml`  
**Autonomous:** Yes  

> **Spec source:** `docker_env_decision_00_prioritized.md` (decisions A1-A16, C1-C7, §4 corrections), `docs/wiki/01_technical_specification.md`, `docs/wiki/02_packages.md`, `docs/wiki/03_structure.md`, `docs/wiki/04_db_structure.md`

---

## Task 0: pyproject.toml Reconciliation + psycopg3/Django-5.2 Verification (Prerequisite)

**Goal:** Fix critical version contradictions in `pyproject.toml` to enable a buildable Docker environment.

**Acceptance Criteria:**
- `pyproject.toml` contains `requires-python = ">=3.14"` (line 9 — owner directive: latest stable Python 3.14)
- `pyproject.toml` contains `django>=5.2.8,<6.0` (Django 5.2.x LTS; line 11 corrected from `django>=6.0.1`. NOTE: Python 3.14 requires Django >=5.2.8 — Django 5.1 is incompatible with 3.14 and is EOL.)
- `pyproject.toml` contains `psycopg[binary]>=3.2.0` (line 12 corrected from `psycopg2-binary>=2.9.11`)
- `pyproject.toml` includes all spec dependencies (versions per canonical `docs/wiki/02_packages.md`): `django-environ>=0.11.0`, `django-mptt>=0.18.0`, `django-filter>=26.1`, `aiogram>=3.15.0`, `deep-translator>=1.11.0`, `django-tailwind>=4.4.0`, `django-htmx>=1.19.0`, `pillow>=10.4.0`, `psycopg[pool]>=3.2.0` (for native pooling if PgBouncer deferred).
  NOTE: `django-storages` + `boto3` are DEFERRED (YAGNI phase 1 — built-in `STORAGES`/FileSystemStorage suffices); add at S3/R2 swap time.
- `pyproject.toml` removes `psycopg2-binary` completely
- `uv.lock` regenerated with `uv lock --refresh` after changes
- Verification: `uv run python -c "import psycopg; print(psycopg.__version__)"` outputs psycopg3 version (>=3.2.0)
- Verification: `uv run python -c "import django; print(django.VERSION)"` outputs Django 5.2.x
- Verification: `uv run basedpyright src/` passes without psycopg2 errors

**Artifacts:** `pyproject.toml`, `uv.lock` (regenerated)  
**Dependencies:** None  
**Risks:** Version drift will cause Docker build failures; psycopg3 wheels must exist for Python 3.14 `python:3.14-slim` base image (add `libpq5` to runtime stage if needed).

---

## Task 1: Multi-Stage Dockerfile with Non-Root User + collectstatic

**Goal:** Create a secure, production-ready multi-stage Dockerfile that supports both web and bot services.

**Acceptance Criteria:**
- `docker/Dockerfile` uses `python:3.14-slim` as base (owner directive: latest stable Python 3.14; Django 5.2.x LTS supports 3.14 since 5.2.8)
- Builder stage installs `gcc libpq-dev` for psycopg3 compilation
- Builder stage runs `uv sync --frozen --no-install-project` to `/opt/venv`
- Builder stage runs `uv run python src/backend/manage.py collectstatic --noinput` (static files baked into image)
- Runtime stage copies venv from builder (no build tools in final image)
- Runtime stage creates non-root user `app` (uid 1000) with write access to `/app/media`
- Runtime stage installs runtime library `libpq5` for psycopg3
- Runtime stage sets `ENV PATH="/opt/venv/bin:$PATH"` and `ENV UV_PROJECT_ENVIRONMENT=/opt/venv`
- Verification: `docker build -t mko-bazuna:dev -f docker/Dockerfile .` succeeds
- Verification: Final image size < 300MB; no gcc/libpq-dev present: `docker run --rm mko-bazuna:dev which gcc` returns nothing

**Artifacts:** `docker/Dockerfile` (completely rewritten), `docker/entrypoint.sh` (created)  
**Dependencies:** Task 0  
**Risks:** psycopg3 requires `libpq5` at runtime; ensure package is included in runtime stage.

---

## Task 2: Base docker-compose.yml + Named Volumes

**Goal:** Create the base compose file with shared services, volumes, and one-shot migrate service.

**Acceptance Criteria:**
- `docker-compose.yml` omits obsolete `version:` key (decision C7)
- Contains services: `db` (postgres:17-alpine, healthcheck via `pg_isready`), `migrate` (one-shot service), `web`, `bot`, `nginx`
- Volume `postgres_data` defined for PostgreSQL persistence
- Volume `media_volume` defined for user-uploaded media
- Volume `static_volume` defined for static files (used by nginx)
- `db` has healthcheck: `pg_isready -U ${POSTGRES_USER} -d ${POSTGRES_DB}`
- `migrate` service uses same image, runs `manage.py migrate --noinput`, exits; has PostgreSQL advisory lock for idempotency
- `web` service: `depends_on: migrate` with `condition: service_completed_successfully` (NOT file-lock per decision C5)
- `bot` service: `depends_on: migrate` with `condition: service_completed_successfully`
- `nginx` service: ports 80/443; mounts `static_volume` and `media_volume` read-only
- `web` port 8000 is NOT published externally (nginx proxies internally)
- Verification: `docker compose config` validates successfully
- Verification: `docker compose up migrate` runs migrations once; second run does nothing (advisory lock)

**Artifacts:** `docker-compose.yml` (rewritten), `docker/entrypoint.sh` (migrate logic), `docker/initdb.d/` directory (optional SQL init scripts)  
**Dependencies:** Task 1  
**Risks:** Migration race between web and bot; use advisory lock to prevent concurrent apply.

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
- Uses `postgres:17` (NOT SQLite — Russian FTS + plpgsql triggers require real PG per decision A6)
- `test` service is one-shot: runs migrate then `pytest --tb=short`
- NO persistent volume for test database (ephemeral)
- Environment variable `DJANGO_SETTINGS_MODULE=config.settings.test` set
- Verification: `docker compose -f docker-compose.yml -f docker-compose.test.yml run --rm test` completes with pytest exit code
- Verification: `uv run pytest` inside test container uses real PostgreSQL connection
- Verification: Test database is destroyed after run (no data leakage)

**Artifacts:** `docker-compose.test.yml`, `config/settings/test.py` (created in Task 6), `docker/entrypoint-test.sh`  
**Dependencies:** Task 1, Task 6  
**Risks:** Test isolation; ensure `pytest-django` creates/destroys test DB correctly.

---

## Task 5: Production Override (docker-compose.prod.yml)

**Goal:** Immutable image deployment with TLS hardening and scheduler.

**Acceptance Criteria:**
- `docker-compose.prod.yml` extends base without bind-mounts
- `web` command uses `gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers 3` (sync WSGI per spec)
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
**Risks:** TLS cert setup deferred to ops runbook; initial deploy can use self-signed certs.

---

## Task 6: Settings Package Split (base/dev/prod/test)

**Goal:** Split single `src/backend/config/settings.py` into environment-aware package selected by `DJANGO_SETTINGS_MODULE`.

**Acceptance Criteria:**
- `src/backend/config/settings/` package created with `base.py`, `dev.py`, `prod.py`, `test.py`
- `src/backend/config/settings/__init__.py` exists (empty or re-exports)
- `base.py` contains common settings: INSTALLED_APPS, MIDDLEWARE, DATABASES (CONN_MAX_AGE=0), TEMPLATES, STORAGES/django-storages abstraction
- `dev.py` inherits from base: `DEBUG=True`, console logging, no SSL redirect
- `prod.py` inherits from base: `DEBUG=False`, `SECURE_SSL_REDIRECT=True`, `SECURE_PROXY_SSL_HEADER=('HTTP_X_FORWARDED_PROTO','https')`, `USE_X_FORWARDED_HOST=True`, secure cookies (`SESSION_COOKIE_SECURE=True`, `CSRF_COOKIE_SECURE=True`)
- `test.py` inherits from base: `DEBUG=True`, test database config, faster password hasher
- All settings use `django-environ` for `.env` parsing (prevents "False"→True string bugs)
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
- `/static/` location serves from `/static_volume/` with 30d cache
- `/media/` location serves from `/media_volume/` with zone R8 hardening:
  - Script execution blocked: `location ~* /media/.*\.(php|py|cgi|pl|sh)$ { deny all; return 403; }`
  - Header: `X-Content-Type-Options: nosniff always`
  - Header: `Content-Disposition: inline`
  - MIME whitelist: **image/jpeg only** (per decision §4.5); default `application/octet-stream`
  - Header: `X-Frame-Options: DENY always`
  - Header: `Content-Security-Policy: default-src 'none'; img-src 'self' data:; object-src 'none'`
- Reverse proxy to `http://web:8000` with forwarded headers
- TLS termination ready: `listen 443 ssl http2;` with cert paths from env
- HTTP to HTTPS redirect: `return 301 https://$host$request_uri;` (commented for dev, enabled in prod)
- Verification: `curl -I http://localhost/media/test.jpg` in prod returns correct headers
- Verification: Script request blocked: `curl -I http://localhost/media/test.php` returns 403

**Artifacts:** `docker/nginx/nginx.conf`  
**Dependencies:** Task 2  
**Risks:** MIME whitelist rationale documented: Telegram delivers JPEG only; png/webp broader than spec (decision §4.5).

---

## Task 8: .env.example + .env.dev Templates

**Goal:** Provide environment variable templates without API_ID/API_HASH per spec.

**Acceptance Criteria:**
- `.env.example` contains all necessary variables without secrets:
  - `DJANGO_SECRET_KEY` (placeholder: `<generate-with-django-secret-key-generator>`)
  - `DEBUG` (True/False)
  - `ALLOWED_HOSTS`
  - `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`
  - `DATABASE_URL` or individual `DATABASE_HOST`, `DATABASE_PORT`, `DATABASE_NAME`, `DATABASE_USER`, `DATABASE_PASSWORD`
  - `BOT_TOKEN` (required for bot operation)
- `.env.dev` created locally with dev values (gitignored)
- **NO `API_ID` or `API_HASH` present** (aiogram Bot API only in phase 1; spec zone R7)
- Verification: `docker compose run --rm web env` in dev shows all required variables loaded
- Verification: Missing `.env` causes container startup failure (fail-fast)

**Artifacts:** `.env.example`, `.env.dev.example` (optional), `.gitignore` entry for `.env.dev`  
**Dependencies:** Task 6  
**Risks:** Secrets management; phase 2 will integrate Docker secrets.

---

## Task 9: Scheduled-Jobs Scheduler Service + Management Commands

**Goal:** Implement idempotent, locked management commands for background jobs.

**Acceptance Criteria:**
- `scheduler` container runs in exec loop (or supercronic) with all jobs
- All jobs wrapped in per-job locks (PostgreSQL advisory lock or lock table)
- Jobs implemented — **names MUST match the feature-phase plans** (`01_detailed_plan_publish_discover.md`, `02_detailed_plan_moderation.md`, `04_detailed_plan_analytics_harden.md`):
  - `archive_sweep` (2 months after `published_at`, zone J) — defined in Phase 4 Task 2
  - `delete_sweep` (4 months after `published_at`, zone J) — defined in Phase 4 Task 2
  - `purge_failed_ads` (7 days after `moderation_failed_at`, zone C4) — defined in Phase 2 Task 4
  - `purge_rejected_ads` (90 days after `rejected_at`, zone D4) — defined in Phase 2 Task 5
  - `consent_hard_delete` (30 days after `consent_revoked_at`, zone R1) — defined in Phase 4 Task 2
  - `sweep_drafts` (30 minutes idle FSM-draft timeout, zone C8/I) — bot idle-timeout logic in Phase 1 Task 9; the sweep *command* is defined in Phase 4 Task 2
  - `cleanup_login_tokens` (expired/consumed tokens, zone C1) — defined in Phase 4 Task 2
- Each job is idempotent (can run multiple times safely) and wrapped in a per-job lock.
- Verification: `docker compose exec scheduler python manage.py archive_sweep --dry-run` shows candidates
- Verification: Job lock prevents concurrent runs: stop+restart doesn't duplicate work

**Artifacts:** `apps/core/management/commands/archive_sweep.py`, `apps/core/management/commands/delete_sweep.py`, `apps/core/management/commands/purge_failed_ads.py`, `apps/core/management/commands/purge_rejected_ads.py`, `apps/core/management/commands/consent_hard_delete.py`, `apps/core/management/commands/sweep_drafts.py`, `apps/core/management/commands/cleanup_login_tokens.py`, `scheduler` service in `docker-compose.prod.yml`  
**Dependencies:** Task 2, Task 6  
**Risks:** Job overlap on restart; use database-level locking.

---

## Task 10: Makefile + PowerShell Dev Shortcuts

**Goal:** Provide ergonomic developer commands for container-based workflow.

**Acceptance Criteria:**
- `Makefile` contains shortcuts: `up`, `down`, `test`, `lint`, `typecheck`, `shell`, `migrate`, `makemigrations`, `logs`, `backup`, `restore`
- PowerShell equivalent (`Makefile.ps1`) for Windows developers
- Commands execute inside containers:
  - `make test` → `docker compose -f docker-compose.yml -f docker-compose.test.yml run --rm test`
  - `make lint` → `docker compose run --rm web uv run ruff check src/`
  - `make typecheck` → `docker compose run --rm web uv run basedpyright src/`
  - `make up` → `docker compose -f docker-compose.yml -f docker-compose.dev.override.yml up -d`
- `backup` target runs `pg_dump` with timestamped filenames
- 7-day rotation implemented via `find` or PowerShell equivalent
- Verification: `make help` lists all targets
- Verification: `make lint` exits 0 on clean code

**Artifacts:** `Makefile`, `Makefile.ps1` (optional)  
**Dependencies:** Task 3  
**Risks:** Windows PowerShell syntax differs; maintain both or single cross-platform script.

---

## Task 11: CI Pipeline (GitHub Actions)

**Goal:** Automated build and test workflow with real PostgreSQL.

**Acceptance Criteria:**
- `.github/workflows/ci.yml` exists with jobs: `build`, `test`, `lint`, `typecheck`
- Build runs on `ubuntu-latest` with `docker build`
- Test job uses `postgres:17` service with healthcheck
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
- Uses `bitnami/pgbouncer:1.5` or `edoburu/pgbouncer` image
- Transaction-mode pooling configured
- Environment variables for `POSTGRES_PASSWORD`, `PGBOUNCER_DATABASE`, etc.
- Healthcheck: `pg_isready -h localhost -p 6432`
- `CONN_MAX_AGE=0` enforced regardless (spec zone C5)
- Verification: `docker compose -f docker-compose.yml -f docker-compose.prod.yml --profile pgbouncer up` starts PgBouncer
- Verification: Documentation in README describes when/why to enable PgBouncer

**Artifacts:** PgBouncer service block in `docker-compose.prod.yml`, README section on PgBouncer  
**Dependencies:** Task 5  
**Risks:** Auth mismatch between PgBouncer and PostgreSQL; test connection before prod deploy.

---

## Task 13: DB Backup Script + Restore Runbook

**Goal:** Daily logical backups with retention for operational safety.

**Acceptance Criteria:**
- `backup` service or cron sidecar runs `pg_dump` daily
- Backups stored to `./backups/` with filename `dump_YYYYMMDD.sql`
- 7-day rotation keeps last 7 dumps (deletes older)
- `Makefile backup` target for manual backup
- Restore procedure documented in `docs/ops/restore.md`:
  - Stop web/bot services
  - Restore: `docker compose exec -T db pg_restore --clean --if-exists -U $POSTGRES_USER -d $POSTGRES_DB < backup.sql`
- Verification: `make backup` creates dump file in `./backups/`
- Verification: Backup script is idempotent (re-running doesn't fail)

**Artifacts:** `backup` service in compose, `docs/ops/restore.md`  
**Dependencies:** Task 2  
**Risks:** Disk space; verify retention works correctly.

---

## Task 14: Verify Wiki Spec Files (02/03/04) Agree with Approved Baseline (PostgreSQL 17 + Python 3.14 + Django 5.2.x LTS)

**Goal:** Confirm the spec source-of-truth (`docs/wiki/02_packages.md`, `03_structure.md`, `04_db_structure.md`) agrees with the approved stack. The owner has already rewritten `02_packages.md` to Django 5.2 LTS + Python 3.14; `03_structure.md` already uses `python:3.14-slim` and `postgres:17`. This task VERIFIES alignment and only patches residual drift.

**Acceptance Criteria:**
- `docs/wiki/02_packages.md`: confirms Django `>=5.2.16,<6.0`, psycopg3 only (no psycopg2-binary), Python 3.14 compatible. If any `5.1.2`/psycopg2 remnant remains, patch it.
- `docs/wiki/03_structure.md`: confirms `python:3.14-slim` base image and `postgres:17-alpine` (canonical version — NOT PG18). If a stale `3.13`/`postgres:18` reference exists, patch it.
- `docs/wiki/04_db_structure.md`: FTS/triggers unchanged; PostgreSQL 17 confirmed (russian FTS config, ICU/locale handled by `postgres:17-alpine` defaults). Add a one-line note that GIN/`pg_trgm` indexes should be reindexed after any major PG collation-provider upgrade.

**Artifacts:** `docs/wiki/02_packages.md`, `docs/wiki/03_structure.md`, `docs/wiki/04_db_structure.md` (verified/edited if needed)  
**Dependencies:** Task 0 (version facts)  
**Risks:** Editing spec source-of-truth must be reviewed; this task closes the loop so the repo spec no longer contradicts `pyproject.toml`/compose.

---

## Dependency Graph

```
Task 0 → Task 1 → Task 2 → Task 6
                            ├──→ Task 3 (dev)
                            ├──→ Task 4 (test)
                            ├──→ Task 5 (prod)
                            └──→ Task 9 (scheduler)   # also needs Task 6 (settings) + apps/core from Phase-1 plan
Task 0 → Task 14 (wiki spec sync)
Task 7 (nginx) ← Task 2
Task 8 (.env)  ← Task 6
Task 10 (Makefile) ← Task 3
Task 11 (CI)   ← Task 4
Task 12 (PgBouncer) ← Task 5
Task 13 (backup) ← Task 2
```

> **Cross-plan note:** Task 9's `apps/core/management/commands/*.py` require the Django apps
> (`apps/core`, `apps/ads`, `apps/users`, `apps/moderation`) created by
> `01_detailed_plan_publish_discover.md`. Sequence Task 9 after those apps exist; Tasks 0–8 and
> 10–13 (pure infra) have no such dependency and can be built independently.

---

## Environment Matrix

| Aspect | **Dev** | **Test** | **Prod** |
|--------|---------|----------|----------|
| Compose files | base + `dev.override` | `test` | base + `prod` |
| Source | bind-mount (`.:/app`) | bind-mount or baked | baked in image (immutable) |
| Server | `runserver` | pytest runner | `gunicorn` sync WSGI |
| DB | `db` (persistent volume) | ephemeral postgres:17 (no volume) | `db` (persistent volume) |
| Migrations | on-demand / `migrate` svc | in test entrypoint | one-shot `migrate` svc (locked) |
| nginx | optional | none | mandatory, TLS + R8 hardening |
| DEBUG | True | True (test settings) | False |
| Secrets | `.env.dev` | CI env vars / generated | `env_file` (Docker secrets later) |
| PgBouncer | off | off | opt-in profile `--profile pgbouncer` |
| Scheduler | manual invoke | off | on (hourly loop) |
| Host ports | web:8000 published | none | 80/443 only |

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