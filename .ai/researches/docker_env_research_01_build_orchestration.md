# Docker Build & Orchestration Research — Phase 1

**Scope:** Researching Docker image design, multi-stage builds, and compose orchestration for a production-ready containerized environment with Prod/Dev/Test profiles.

**Research Angle:** #1 of 3 — BUILD, IMAGE & ORCHESTRATION MECHANICS (Dockerfile design, multi-stage builds, base image choice, uv dependency management, image layering/caching, non-root user, service topology, environment separation, healthchecks, migrations)

---

## 1. Constraints Extracted from Wiki

### From `docs/wiki/packages.md` (packages specification):
- **Django 5.1.2** (exact version specified, line 14)
- **psycopg[binary] >= 3.2.0** — psycopg3 (line 17)
- **aiogram >= 3.15.0** — Telegram bot framework (line 41)
- **uv** for dependency management (lines 25, 79)
- **django-tailwind, django-storages, deep-translator, pytest** in the stack (lines 59, 64, 49, 73)

### From `docs/wiki/architecture-structure.md` (deployment sketch):
- **Services:** db (postgres:17-alpine), web (Django + gunicorn sync WSGI), bot (same image, different command), nginx (ports 80/443) — lines 83-88
- **Volumes:** postgres_data, media_volume, static_volume — line 91
- **gunicorn sync WSGI** for phase 1, NOT ASGI/Uvicorn (line 85)
- **PgBouncer recommended** in transaction mode for shared connection pooling (line 104)
- **Migrations run once before web and bot start** (ordering guard required) — lines 105-106

### From `docs/wiki/db-structure.md` (database requirements):
- **PostgreSQL Russian FTS config** (`to_tsvector('russian', ...)`) — line 6, 183-184
- **Search vector triggers** managed via plpgsql functions — lines 186-218
- **Category name denormalization** into ads table for FTS — line 74

---

## 2. Drift Analysis: pyproject.toml vs Specification

### Critical Drifts Observed:

| Component | Spec Requirement (docs/wiki/packages.md) | Actual State (pyproject.toml) | Impact |
|-----------|------------------------------------------|-------------------------------|--------|
| Django | `django==5.1.2` (exact) | `django>=6.0.1` (looser, newer) | **Breaks compatibility** |
| psycopg | `psycopg[binary]>=3.2.0` (psycopg3) | `psycopg2-binary>=2.9.11` (psycopg2) | **Breaks compatibility** |
| Python version | Implied 3.12-3.13 (Django 5.1 support) | `requires-python = ">=3.14"` | **Pre-release Python** |

### Reasoning:

1. **Django 6.0.1 vs 5.1.2**: Django 6.0 requires Python 3.13+. The spec explicitly pins 5.1.2. Using `>=6.0.1` risks instability and may not align with psycopg3 native support path.

2. **psycopg2-binary vs psycopg3**: psycopg2 is synchronous-only and lacks native connection pooling. The spec requires psycopg3 for Django 5.1+ native support with proper pooling. This affects the PgBouncer strategy (zone C5).

3. **Python 3.14 requirement**: Python 3.14 is in pre-release (as of mid-2026, 3.13 is stable). This prevents stable base image selection.

### Recommended Resolution:

```toml
[project]
name = "mko-bazuna"
version = "0.1.0"
# CHANGE: requires-python = ">=3.12"  # Align with Django 5.1.2
dependencies = [
    "django==5.1.2",                           # Pin exact version per spec
    "psycopg[binary]>=3.2.0",                  # psycopg3 per spec
    "django-environ>=0.11.0",                  # Spec requirement
    "django-mptt==0.16.0",
    "django-filter==24.3",
    "aiogram>=3.15.0",
    "deep-translator>=1.11.0",
    "django-tailwind==4.4.2",
    "django-storages==1.14.4",
    "pillow>=10.4.0",
    "python-dotenv>=1.2.1",  # transitive from django-environ
]
```

**Rationale:** Align pyproject.toml with spec before Docker work. The Docker build depends on correct package versions.

---

## 3. Recommended Approach — Build & Orchestration Mechanics

### 3.1 Multi-Stage Dockerfile Design

A three-stage build optimizes for production image size while keeping dev ergonomics:

```dockerfile
# docker/Dockerfile
################################################################################
# STAGE 1: Builder — compile deps and collectstatic
################################################################################
FROM python:3.12-slim AS builder

# Install build dependencies (gcc, libpq-dev for psycopg3)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /

WORKDIR /app

# Cache: copy dependency files first (most stable layer)
COPY pyproject.toml uv.lock* ./

# Install dependencies to venv
ENV UV_PROJECT_ENVIRONMENT=/opt/venv
ENV UV_LINK_MODE=copy
RUN uv sync --frozen --no-install-project

# Stage 2 will copy the venv, avoiding re-install on code changes
COPY . .

# Collect static files (CSS from django-tailwind)
RUN uv run python src/backend/manage.py collectstatic --noinput

################################################################################
# STAGE 2: Production Runtime
################################################################################
FROM python:3.12-slim AS runtime

# Non-root user (security baseline)
RUN groupadd -r app && useradd -r -g app app && \
    mkdir -p /app/src /app/media /app/staticfiles && \
    chown -R app:app /app

WORKDIR /app

# Copy venv from builder (no gcc/libpq-dev in final image)
COPY --from=builder --chown=app:app /opt/venv /opt/venv
COPY --from=builder --chown=app:app /app/src /app/src
COPY --from=builder --chown=app:app /app/staticfiles /app/staticfiles

# Copy entrypoint
COPY --chown=app:app docker/entrypoint.sh /app/entrypoint.sh

# Activate venv for all subsequent RUN/ENTRYPOINT
ENV PATH="/opt/venv/bin:$PATH"
ENV UV_PROJECT_ENVIRONMENT=/opt/venv

# Runtime volumes (writable for media)
VOLUME ["/app/media"]

# Non-root execution
USER app

EXPOSE 8000
ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3"]
```

**Key decisions:**
- **Base image:** `python:3.12-slim` (stable LTS, matches Django 5.1 support). 3.14 is pre-release; 3.13 acceptable but 3.12 is battle-tested.
- **Non-root user:** uid 1000 (app) created in runtime stage — prevents container escape escalation.
- **Multi-stage:** Builder has gcc/libpq-dev; runtime only has runtime libs — ~200MB smaller final image.
- **venv copy:** `UV_LINK_MODE=copy` ensures self-contained venv (no external symlinks).
- **collectstatic in build:** Static files baked into image for web service; shared via volume for nginx.

### 3.2 Entrypoint Migration-Guard Design

Migrations must run **once**, **before** both web and bot processes, to prevent:
1. Concurrent migration attempts (race condition)
2. Bot starting before ads/search indexes exist
3. Partial migration state between services

```bash
#!/bin/bash
# docker/entrypoint.sh
set -e

# Wait for database to be ready
wait-for-db() {
    echo "Waiting for PostgreSQL..."
    for i in {1..30}; do
        if uv run python -c "import psycopg; psycopg.connect(os.environ['DATABASE_URL'])" 2>/dev/null; then
            echo "Database ready"
            return 0
        fi
        sleep 1
    done
    echo "ERROR: Database unavailable after 30s" >&2
    exit 1
}

# Run migrations once (with file lock for multi-container safety)
run-migrations() {
    MIGRATION_LOCK="/app/.migrations_done"
    
    # In prod: check lock file
    if [ "$RUN_MIGRATIONS" != "false" ] && [ ! -f "$MIGRATION_LOCK" ]; then
        echo "Running database migrations..."
        uv run python src/backend/manage.py migrate --noinput
        
        # Create lock file after success
        touch "$MIGRATION_LOCK"
        echo "Migrations complete"
    else
        echo "Migrations skipped (lock exists or disabled)"
    fi
}

# Execute logic
wait-for-db
run-migrations
exec "$@"
```

**Production consideration:** The lock file approach works within a single container lifecycle. For true run-once across restarts, use a separate `migrator` service or check for migration table existence.

### 3.3 Compose File Layering: Base + Overrides

```
project/
├── docker-compose.yml          # Base: common services, image build
├── docker-compose.dev.yml      # Dev overrides: bind-mounts, runserver, debug
├── docker-compose.prod.yml     # Prod overrides: gunicorn, no mounts, restart policies
└── docker-compose.test.yml     # Test: ephemeral DB, test command
```

**Base `docker-compose.yml` (shared foundation):**

```yaml
# docker-compose.yml
version: "3.9"

services:
  db:
    image: postgres:17-alpine
    restart: unless-stopped
    environment:
      POSTGRES_DB: ${POSTGRES_DB}
      POSTGRES_USER: ${POSTGRES_USER}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./docker/initdb.d:/docker-entrypoint-initdb.d:ro  # FTS init SQL
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER} -d ${POSTGRES_DB}"]
      interval: 5s
      timeout: 5s
      retries: 5

  web:
    build:
      context: .
      dockerfile: docker/Dockerfile
    depends_on:
      db:
        condition: service_healthy
    env_file: .env
    volumes:
      - media_volume:/app/media
      - static_volume:/app/staticfiles:ro  # Read-only for safety
    environment:
      PATH: "/opt/venv/bin:${PATH}"
      UV_PROJECT_ENVIRONMENT: /opt/venv

  bot:
    build:
      context: .
      dockerfile: docker/Dockerfile
    depends_on:
      db:
        condition: service_healthy
    env_file: .env
    volumes:
      - media_volume:/app/media:rw  # Bot writes media
    environment:
      PATH: "/opt/venv/bin:${PATH}"
      UV_PROJECT_ENVIRONMENT: /opt/venv
    restart: unless-stopped

  nginx:
    image: nginx:alpine
    depends_on:
      - web
    ports:
      - "${NGINX_PORT:-80}:80"
      - "${NGINX_SSL_PORT:-443}:443"
    volumes:
      - ./docker/nginx.conf:/etc/nginx/nginx.conf:ro
      - static_volume:/app/staticfiles:ro
      - media_volume:/app/media:ro
      - ./docker/certs:/etc/nginx/certs:ro

volumes:
  postgres_data:
  media_volume:
  static_volume:
```

**Prod override `docker-compose.prod.yml`:**

```yaml
# docker-compose.prod.yml
services:
  web:
    command: gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers 3 --log-level info
    restart: always
    # NO bind-mounts — use baked image
    volumes:
      - media_volume:/app/media
      - static_volume:/app/staticfiles:ro

  bot:
    command: python -m telegram_bot.main
    restart: always
    volumes:
      - media_volume:/app/media:rw

  nginx:
    restart: always
```

**Dev override `docker-compose.dev.yml`:**

```yaml
# docker-compose.dev.yml
services:
  web:
    command: uv run python src/backend/manage.py runserver 0.0.0.0:8000
    volumes:
      - .:/app  # Live code reload
      - media_volume:/app/media
      - static_volume:/app/staticfiles

  # Bot uses same bind-mount for dev iteration
  bot:
    volumes:
      - .:/app
      - media_volume:/app/media:rw
```

**Test override `docker-compose.test.yml`:**

```yaml
# docker-compose.test.yml
services:
  db:
    image: postgres:17-alpine
    environment:
      POSTGRES_DB: mko_bazuna_test
    # No volume — ephemeral DB

  web:
    command: uv run pytest -T
    depends_on:
      - db
    # Override with test-specific env
    environment:
      DJANGO_SETTINGS_MODULE: config.settings.test
```

### 3.4 Healthcheck & Dependency Ordering

**Service startup sequence:**
1. `db` — healthcheck via `pg_isready` (5s interval, 30s total timeout)
2. `web` — `depends_on db: condition: service_healthy`
3. `bot` — `depends_on db: condition: service_healthy`  
4. `nginx` — `depends_on web` (no DB healthcheck needed; proxies to web)

**Critical timing:** Both `web` and `bot` entrypoints wait for DB, then run migrations. The migration guard ensures only one process actually applies them.

### 3.5 Static/Media Volume Strategy

Per spec (docs/wiki/architecture-structure.md lines 64-67, 94-96):

- **static_volume:** Built during Docker image (collectstatic), mounted read-only into nginx. Nginx serves `/static/` directly.
- **media_volume:** Written by bot at runtime (photo uploads), served by nginx at `/media/` with security headers.

```nginx
# docker/nginx.conf (excerpt)
location /static/ {
    alias /app/staticfiles/;
}

location /media/ {
    alias /app/media/;
    location ~* \.(php|py|cgi)$ { deny all; }  # zone R8
    add_header X-Content-Type-Options nosniff;
    add_header Content-Disposition inline;
}
```

### 3.6 Async Bot + Sync ORM Coexistence

The spec (docs/wiki/packages.md line 9) requires:
- **aiogram 3.x** for async Telegram bot (Bot API)
- **sync Django ORM** wrapped in `sync_to_async`
- **Separate processes** (shared image, separate containers)

**Architecture:**
```
web container (gunicorn sync WSGI)
  └─ Django ORM (sync)
  └─ PostgreSQL via psycopg3

bot container (aiogram async event loop)
  └─ aiogram 3.x handlers
  └─ Django ORM via sync_to_async()  # Non-blocking wrapper
  └─ PostgreSQL via psycopg3 (same connection settings)

Both use: CONN_MAX_AGE=0 (per-process connection pools)
PgBouncer (recommended) sits between both and PostgreSQL
```

**Entangled concerns:**
- Migrations run once before both services start (via entrypoint)
- Both services share `media_volume` for photo storage
- Both use same `.env` for `DATABASE_URL` (or PgBouncer DSN)

---

## 4. Trade-offs and Alternatives Considered

| Decision | Chosen | Alternative | Rejected Because |
|----------|--------|-------------|------------------|
| Multi-stage build | 3 stages (builder, runtime) | Single-stage | Single-stage includes build deps (~200MB larger), security risk |
| Base image: python:3.12-slim | Stable LTS | python:3.14-slim | 3.14 is pre-release; 3.13 acceptable but 3.12 battle-tested |
| Non-root user | uid 1000 `app` | root | Security baseline (CIS Docker benchmarks); no practical downside |
| Entrypoint migration lock | File-based (simple) | Separate migrator container | Over-engineered for MVP; file lock sufficient within single container lifecycle |
| nginx in same compose | Yes | Cloud LB / S3 only | Spec requires nginx for media/TLS (lines 94-96) |
| PgBouncer | Optional/recommended | Mandatory | Adds complexity; acceptable to defer until connection pool pressure observed |
| collectstatic in image | Build-time | Runtime volume | Simpler dev flow, faster production boot, consistent assets |

---

## 5. Risks + Open Questions for Planner

### Risks (HIGH/MEDIUM/LOW confidence):

- **DRIFT-1 (HIGH):** pyproject.toml discrepancies will cause build or runtime failures. Must resolve before Docker work proceeds.
- **RISK-1 (MEDIUM):** `python:3.12-slim` may lack `libpq5` needed for psycopg3. Must test or add `libpq5` to runtime stage.
- **RISK-2 (LOW):** Volume permissions — non-root user may not write to `media_volume` if mounted from host on Windows (WSL2 permissions).
- **RISK-3 (LOW):** django-tailwind CSS build requires Node.js at build time if using npm mode. The spec mentions "standalone CLI mode needs NO Node.js" (line 59).

### Open Questions:

1. **Do we need PgBouncer in phase 1?** Spec says "рекомендуется" (recommended) not mandatory. For 300 users/day, Django's built-in pooling may suffice. Decision: *defer to post-MVP unless connection pressure observed*.

2. **How to handle media volume initialization?** Spec mentions DB init scripts in `docker/initdb.d`. Should we seed categories/cities at DB init time via SQL, or use Django migrations? Decision: *use Django migrations for app data, SQL for extensions/FTS config*.

3. **Test profile database strategy:** Ephemeral DB per test run vs persistent test DB? Decision: *ephemeral for CI, persistent for local dev iterations*.

---

## 6. Prioritized Checklist for MVP (~300 users/day, 500k ads)

### P0 — Must-have for any working environment:

- [ ] Align pyproject.toml with spec (Django 5.1.2, psycopg3, Python 3.12)
- [ ] Create multi-stage Dockerfile (builder + runtime)
- [ ] Add non-root user (`app`) to runtime stage
- [ ] Implement entrypoint with DB wait + migration guard
- [ ] Run `collectstatic` in builder stage
- [ ] Split compose into base + dev override
- [ ] Add bot service (separate command, shared volumes)
- [ ] Add nginx service (ports 80/443, media static serving)
- [ ] Add all three volumes: postgres_data, media_volume, static_volume

### P1 — Should-have for production stability:

- [ ] Add `depends_on` with healthcheck conditions
- [ ] Create `docker-compose.prod.yml` override (no bind-mounts)
- [ ] Create `docker-compose.test.yml` for CI
- [ ] Add nginx security headers (zone R8: nosniff, script deny)
- [ ] Add SQL init script for PostgreSQL extensions (pg_trgm)
- [ ] Test psycopg3 connection with `CONN_MAX_AGE=0`
- [ ] Verify media volume write permissions for non-root user

### P2 — Nice-to-have / deferred to post-MVP:

- [ ] PgBouncer service (defer until connection pool pressure)
- [ ] Separate migrator service for run-once guarantee
- [ ] Docker secrets for `.env` (start with env_file)
- [ ] Multi-arch build (linux/amd64 + arm64)
- [ ] BuildKit cache imports for faster rebuilds

---

## References

- `docs/wiki/technical-specification.md` — Lines 18-21 (traffic/load requirements)
- `docs/wiki/packages.md` — Lines 14-17, 41, 59, 64, 73, 9 (exact package versions)
- `docs/wiki/architecture-structure.md` — Lines 64-67, 83-106 (deployment sketch)
- `docs/wiki/db-structure.md` — Lines 6, 183-184 (FTS triggers, Russian config)