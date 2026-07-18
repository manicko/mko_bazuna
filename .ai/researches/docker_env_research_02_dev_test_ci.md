# Developer Workflow, Test Environment & CI for Dockerized mko_bazuna

**Scope:** Docker-only development with three environment profiles (Prod/Dev/Test) for Django + Telegram bot application.

**Research Angle:** Developer ergonomics on Windows host, real PostgreSQL 17 for FTS/trigger tests, in-container pytest/ruff/basedpyright execution, CI pipeline design.

---

## 1. Constraints Extracted from Wiki

| Source | Section | Constraint |
|--------|---------|------------|
| `01_technical_specification.md` | Traffic | Up to 300 users/day (MVP load) |
| `01_technical_specification.md` | US-S2 | Bot dialog requires `aiogram` with FSM for step-by-step ad creation |
| `02_packages.md` | Core/Web | `pytest==8.3.3`, `pytest-django==4.9.0`, `pytest-factoryboy==2.7.0`, `ruff==0.9.0` |
| `02_packages.md` | Core/Web | Background jobs via `systemd/cron` NOT Celery in phase 1 (decision in spec) |
| `02_packages.md` | Database | `psycopg[binary]>=3.2.0` (PostgreSQL driver) — **spec says psycopg3, pyproject.toml has psycopg2-binary drift** |
| `02_packages.md` | Database | PostgreSQL native FTS with `to_tsvector('russian', ...)` — tests MUST run on real Postgres (not SQLite) |
| `02_packages.md` | Database | plpgsql triggers for `search_vector` denormalization require real Postgres |
| `03_structure.md` | Deployment | `web` service: Django + gunicorn; `bot` service: `python -m telegram_bot.main`; `nginx` for static/media/TLS |
| `03_structure.md` | Deployment | Migrations run once before web and bot start (dedicated step / ordering guard in entrypoint) |
| `04_db_structure.md` | FTS | `search_vector` uses Russian config, GIN index, and plpgsql triggers — requires real PostgreSQL 17 |

---

## 2. pyproject.toml vs Specification Drift

| Item | Specification (02_packages.md) | pyproject.toml (actual) | Impact |
|------|------------------------------|-------------------------|--------|
| Django | `django==5.1.2` | `django>=6.0.1` | **Version mismatch** — spec needs verification against tested versions |
| psycopg | `psycopg[binary]>=3.2.0` | `psycopg2-binary>=2.9.11` | **Critical mismatch** — spec mandates psycopg3 for Django 5.1+ native support; pyproject has psycopg2 |
| pytest | `pytest==8.3.3` | `pytest>=9.1.1` (dev group) | Version bump — test toolchain compatibility should be verified |
| ruff | `ruff==0.9.0` | `ruff>=0.15.20` | Version bump — acceptable for linting |
| OS Support | Linux deploy | `platforms = ["Linux", "Windows"]` | OK — Windows support in pyproject |

**Critical:** The psycopg2 vs psycopg3 drift MUST be resolved. psycopg3 is required for Django 5.1+ native async support and proper connection pooling. Tests may behave differently.

---

## 3. Detailed Findings & Recommended Approach

### 3.1 Developer Container Workflow on Windows

**Day-to-day development happens entirely inside Docker containers.** On Windows (PowerShell), developers use `docker compose up` and all tools run via `docker compose run --rm <service> <command>`.

**Bind Mount Strategy:**
- **Dev profile:** Bind mount codebase into container (`.:/app`) for live code reload
- **Prod profile:** Immutable image with copied code (no mount)
- **Test profile:** Bind mount for speed + ephemeral dedicated Postgres

**Windows-Specific Considerations:**
- WSL2 backend recommended for Docker Desktop (file I/O performance)
- Named volumes (`postgres_data`, `media_volume`) persist outside containers
- `.env` file used locally; Docker secrets for production (not in phase 1)

**Illustrative Dev profile snippet:**
```yaml
# docker-compose.dev.yml (extends base)
services:
  web:
    command: uv run python src/backend/manage.py runserver 0.0.0.0:8000
    volumes:
      - .:/app:cached              # WSL2 performance hint
      - media_volume:/app/media
    environment:
      - DEBUG=True
      - UV_PROJECT_ENVIRONMENT=/opt/venv

  bot:
    command: uv run python -m telegram_bot.main
    volumes:
      - .:/app:cached
      - media_volume:/app/media
    environment:
      - DEBUG=True
      - UV_PROJECT_ENVIRONMENT=/opt/venv
```

### 3.2 Test Service Design (Real Postgres 17)

**Why NOT SQLite in CI:**
- PostgreSQL 17 FTS with `to_tsvector('russian', ...)` fails on SQLite
- plpgsql triggers (`ads_search_vector_fn`, `categories_name_propagate`) are PostgreSQL-specific
- GIN indexes, partial indexes cannot be tested on SQLite
- Tests would pass with SQLite but fail in production

**Test Service Architecture:**
- Dedicated `postgres-test` container with `postgres:17-alpine`
- Database created fresh per test run (ephemeral)
- Migrations run automatically in entrypoint
- Test database destroyed after completion (`--rm` flag)

**Illustrative test service snippet:**
```yaml
# docker-compose.test.yml
services:
  postgres-test:
    image: postgres:17-alpine
    environment:
      POSTGRES_DB: test_bazuna
      POSTGRES_USER: test_user
      POSTGRES_PASSWORD: test_pass
    ports: []                        # No host port exposure

  test:
    build:
      context: .
      dockerfile: docker/Dockerfile
    command: ["./entrypoint-test.sh"]
    volumes:
      - .:/app
    depends_on:
      postgres-test:
        condition: service_healthy
    environment:
      - DATABASE_NAME=test_bazuna
      - DATABASE_USER=test_user
      - DATABASE_PASSWORD=test_pass
      - DATABASE_HOST=postgres-test
      - DJANGO_SETTINGS_MODULE=config.settings.test
```

**Illustrative entrypoint-test.sh:**
```bash
#!/bin/bash
set -e

# Wait for database
until pg_isready -h $DATABASE_HOST -p $DATABASE_PORT -U $DATABASE_USER; do
  echo "Waiting for test database..." sleep 1 done

# Create test database (ephemeral)
psql -h $DATABASE_HOST -U $DATABASE_USER -d postgres -c "DROP DATABASE IF EXISTS test_bazuna;"
psql -h $DATABASE_HOST -U $DATABASE_USER -d postgres -c "CREATE DATABASE test_bazuna;"

# Run migrations
uv run python src/backend/manage.py migrate --noinput

# Seed test data (initial categories/cities)
uv run python src/backend/manage.py loaddata test_fixtures.json

# Run tests
uv run pytest -vv --cov=src --cov-report=term-missing

# Cleanup (when container exits)
# Handled by docker-compose --rm
```

### 3.3 Running pytest/ruff/basedpyright In-Container

All developer commands execute inside the container to ensure environment parity.

**Typical invocation patterns:**
```bash
# From project root on Windows host
docker compose -f docker-compose.dev.yml run --rm web uv run pytest
docker compose -f docker-compose.dev.yml run --rm web uv run ruff check src/
docker compose -f docker-compose.dev.yml run --rm web uv run basedpyright src/
```

**Make/Makefile shortcuts for ergonomics:**
```makefile
.PHONY: test lint typecheck shell

test:
	docker compose -f docker-compose.test.yml run --rm test

lint:
	docker compose -f docker-compose.dev.yml run --rm web uv run ruff check src/

typecheck:
	docker compose -f docker-compose.dev.yml run --rm web uv run basedpyright src/

shell:
	docker compose -f docker-compose.dev.yml run --rm web /bin/bash

migrate:
	docker compose -f docker-compose.dev.yml run --rm web uv run python src/backend/manage.py migrate

makemigrations:
	docker compose -f docker-compose.dev.yml run --rm web uv run python src/backend/manage.py makemigrations
```

### 3.4 CI Pipeline Outline (GitHub Actions)

**Workflow goals:**
- Build Docker image once
- Run tests against real PostgreSQL 17
- Cache dependencies via `uv` lock file
- Fast feedback loop (<5 min typical)

**Illustrative `.github/workflows/ci.yml`:**
```yaml
name: CI

on:
  push:
    branches: [main, develop]
  pull_request:

jobs:
  test:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:17-alpine
        env:
          POSTGRES_DB: test_bazuna
          POSTGRES_USER: test_user
          POSTGRES_PASSWORD: test_pass
        ports: [5432:5432]
        options: >-
          --health-cmd pg_isready
          --health-interval 5s
          --health-timeout 5s
          --health-retries 5

    steps:
      - uses: actions/checkout@v4

      - name: Install uv
        uses: astral-sh/setup-uv@v5
        with:
          enable-cache: true

      - name: Build Docker image
        run: docker build -t mko-bazuna:test -f docker/Dockerfile .

      - name: Run tests in container
        run: |
          docker run --rm \
            -e DATABASE_HOST=host.docker.internal \
            -e DATABASE_NAME=test_bazuna \
            -e DATABASE_USER=test_user \
            -e DATABASE_PASSWORD=test_pass \
            mko-bazuna:test \
            sh -c "uv run python src/backend/manage.py migrate && uv run pytest"

  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
      - run: uv run ruff check src/

  typecheck:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
      - run: uv run basedpyright src/
```

### 3.5 .env Strategy Per Environment

| Profile | .env File | Secrets Handling | Notes |
|---------|-----------|------------------|-------|
| Prod | `.env.prod` (on server, not in repo) | Docker secrets (future); env_file today | `DEBUG=False`, HTTPS enforced |
| Dev | `.env.dev` (local, gitignored) | Plain `.env` | `DEBUG=True`, bind mounts enabled |
| Test | Generated in workflow | CI environment variables | Ephemeral, destroyed after run |

**Recommended .env files:**
```
# .env.dev (local development)
DJANGO_SECRET_KEY=dev-secret-key-change-me
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1,0.0.0.0
POSTGRES_DB=bazuna_dev
POSTGRES_USER=bazuna_dev
POSTGRES_PASSWORD=devpass123
DATABASE_HOST=db
DATABASE_PORT=5432

# .env.prod (deploy-time variables)
DJANGO_SECRET_KEY=<from-secrets>
DEBUG=False
ALLOWED_HOSTS=bazuna.ba
DATABASE_HOST=db
```

### 3.6 Telegram Bot Testing Strategy

**In Dev:** Bot runs with real Telegram API but respects `DEBUG=True`:
- Messages logged to console instead of sent (when `TESTING=true`)
- FSM state transitions observable in container logs

**In Test:** Bot code tested via mocking:
```python
# tests/conftest.py
import pytest
from unittest.mock import AsyncMock, patch

@pytest.fixture
def mock_bot():
    with patch("aiogram.Bot") as mock:
        mock.return_value.send_message = AsyncMock()
        yield mock
```

**Bot test patterns:**
- Unit tests: Mock `aiogram.Bot` and handler dispatch
- Integration tests: Use `aiogram_unittest` framework for FSM testing
- Trigger tests: Real PostgreSQL tests the FTS and trigger logic in models
- No actual Telegram API calls in CI (would require BOT_TOKEN)

---

## 4. Trade-offs & Alternatives

| Alternative | Reject Reason |
|-------------|---------------|
| **SQLite in CI** | Russian FTS (`to_tsvector('russian', ...)`) and plpgsql triggers require real PostgreSQL. Tests are meaningless on SQLite. |
| **Running tools on host (not Docker)** | Breaks environment parity. Different OS (Windows vs Linux), Python versions, and dependency versions lead to "works on my machine" bugs. |
| **Celery in phase 1** | Spec explicitly defers background jobs to `systemd/cron` (decision in `02_packages.md`). Celery adds complexity unnecessary for MVP. |
| **Named pipes for Telegram mocking** | Overengineering. Simple `unittest.mock.patch` covers all bot testing needs. Actual Telegram API calls only happen in manual dev testing. |
| **Separate Dockerfile for test** | Unnecessary. Single `Dockerfile` with multi-stage build or entrypoint variants suffices.

---

## 5. Risks & Open Questions

| Risk | Mitigation/Open Question |
|------|---------------------------|
| **psycopg2 vs psycopg3 drift** | Must align with spec before test environment works correctly. psycopg3 required for async support. |
| **Windows file mount performance** | WSL2 backend is mandatory. `:cached` mount hint helps. Consider Mutagen if performance unacceptable. |
| **Test database cleanup** | Use `--rm` flag + dedicated ephemeral database. Question: Should `pytest-django` handle DB creation via `create_test_db`? |
| **Static files in Dev** | Whitenoise in base image for Dev. Nginx `static_volume` for Prod static/media. Question: How to populate `static_volume` in CI? |
| **Media storage in tests** | Tests need no real media files. Mock storage backend or use temp directory. Question: Test image handling with real Telegram photo flow? |

---

## 6. Prioritized Checklist (MVP: ~300 users/day)

### P0 (Must have for MVP)
- [ ] Fix pyproject.toml psycopg2 → psycopg3 drift
- [ ] Create `docker-compose.dev.yml` with bind mounts and hot reload
- [ ] Create `docker-compose.test.yml` with ephemeral PostgreSQL 17
- [ ] Write `entrypoint-test.sh` for test service (migrate + seed + run pytest)
- [ ] Create `.env.dev` and `.env.example` templates
- [ ] Add Makefile shortcuts (test, lint, typecheck, shell)
- [ ] Configure pytest-django for container execution (`pytest.ini_options`)
- [ ] Add GIN index tests verifying real PostgreSQL FTS behavior

### P1 (Important for Developer Experience)
- [ ] Add nginx service to docker-compose.dev.yml (for media handling)
- [ ] Implement bot testing fixtures with `aiogram_unittest` or custom mocks
- [ ] Create `docker-compose.prod.yml` (immutable images, no mounts)
- [ ] Add CI workflow (`.github/workflows/ci.yml`)
- [ ] Configure container logging for bot (stdout capture in dev)
- [ ] Add test data seeding via `loaddata` or factory-boy
- [ ] Document Windows WSL2 setup in README

### P2 (Post-MVP Enhancements)
- [ ] Add GitHub Actions caching for Docker layers
- [ ] Implement Docker secrets for production (beyond env_file)
- [ ] Add separate scraping service compose file (phase 2)
- [ ] Integrate PgBouncer in compose (per spec recommendation)
- [ ] Add testcontainers pattern for database isolation
- [ ] Add mutation testing (cosmic-ray or similar)

---

*Document written: 2026-07-18*
*Source verification: All wiki files + docker-compose.yml + Dockerfile + pyproject.toml read*
*Drift flags: psycopg2-binary vs psycopg3, Django 6.0.1 vs 5.1.2, pytest 9.x vs 8.3.3*