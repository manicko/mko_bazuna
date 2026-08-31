---
id: docker-test-environment-research-report
domain: ops
tags:
  - research
  - docker
  - test-environment
  - infrastructure
related:
  - docker-deployment
  - doc-maintenance-rules
---

> **Update Notice (2026-08-10):** This research report described the pre-implementation state of the Docker test environment. Both **Approach A** (project-name isolation via `COMPOSE_PROJECT_NAME`) and **Approach B** (`tmpfs` + `--reuse-db --create-db`) have been fully implemented in commit `b67f3dc` ("doc:docker"). All five audit findings (B1âB5) are resolved in commit `6d9225d` ("fix(test-infra): resolve CATALOGPATH and CI dev tooling"). All 10 confirmed requirements (CR1âCR10) from the implementation phase are satisfied. The current, maintained workflow is documented in [Docker Deployment â Test Environment](../docker-deployment.md#test-environment). This report is preserved for historical context.

# Docker Test Environment Architecture Research Report

**Status:** Research Complete  
**Date:** 2026-08-09  
**Scope:** Docker Compose test environment architecture for Mko Bazuna  
**Constraint:** Research only â€” no code changes produced by this report

---

## 1. Executive Summary

Mko Bazuna currently has two divergent test execution paths:

| Context | DB | Python | Isolation |
|---------|----|--------|-----------|
| **Local dev (`make test`)** | Docker Compose PostgreSQL | In-container `uv sync --group dev` | No isolation from dev services |
| **CI (GitHub Actions)** | GitHub Actions service container | Host-side `uv run` | Fully isolated (ephemeral) |

The root problem is that every test run rebuilds the PostgreSQL database schema from scratch â€” there is no `--reuse-db`, no `tmpfs`-ephemeral DB, and no project-name isolation between dev and test containers. For a project with a growing migration set and two processes (web + bot) sharing one database, this wastes 15-30s per test iteration on unnecessary migration replay.

After surveying modern Docker Compose patterns (2024-2026 era), uv + Python Docker optimizations, pytest-django best practices, and real-world Django projects (django/django, saleor, wagtail, getsentry, nickjj), I recommend **Approach A: Parallel dev + test via COMPOSE_PROJECT_NAME** as the highest-ROI next step. It requires zero Dockerfile changes, leverages existing infrastructure, and immediately enables safe concurrent development and testing.

---

## 2. Current State Analysis

### 2.1 Docker Compose Files

**Base file (`docker-compose.yml`):**
- Defines persistent `postgres_data` volume for PostgreSQL
- All services (web, bot, migrate, seed, etc.) share this single database
- No profiles or multi-environment separation
- Healthcheck on db via `pg_isready`

**`docker-compose.test.yml` (override):**
- Removes `postgres_data` volume â†’ ephemeral DB (no persistence)
- Adds `test` service with `profiles: ["test"]`
- Adds `uv_cache` volume for uv package caching
- Does NOT set `COMPOSE_PROJECT_NAME` â†’ collides with dev project name
- Does NOT bind-mount source code â†’ tests run against built image

**`docker-compose.dev.override.yml`:**
- Binds `.:/app` for hot-reload
- Sets `DJANGO_SETTINGS_MODULE=config.settings.dev`

### 2.2 Dockerfile

- **Two-stage build**: builder (with Tailwind CLI + collectstatic) + runtime (gunicorn)
- No test-specific stage â€” dev dependencies installed at runtime via `uv sync --group dev`
- No `init: true` â†’ PID 1 zombie reaping not guaranteed in containers

### 2.3 Test Entrypoint (`docker/entrypoint-test.sh`)

1. `uv sync --frozen --no-install-project --group dev`
2. Wait for PostgreSQL via `pg_isready`
3. `uv run python manage.py migrate`
4. `uv run pytest --tb=short`

**Critical gaps:**
- No `--reuse-db` flag
- No `--create-db` fallback
- No `pytest-django` configuration for parallel DB
- Each invocation re-runs full migration set

### 2.4 CI Workflow (`.github/workflows/ci.yml`)

This is the most revealing data point. CI already implements a different, more efficient pattern than local test:

1. Uses `astral-sh/setup-uv@v5` with `enable-cache: true`
2. Runs `uv sync --frozen --no-install-project` with `UV_DEFAULT_GROUPS: dev`
3. Uses GitHub Actions **service container** for PostgreSQL (`postgres:18-alpine`)
4. Runs migrations, checks for pending migrations, then pytest with coverage
5. Does NOT use Docker Compose for test DB â€” uses ephemeral service container
6. Working directory: `src/backend/` (not `/app/`)
7. Builds a Docker image (for build cache) but does NOT run containers for testing

### 2.5 Audit Findings

| ID | Issue | Impact |
|----|-------|--------|
| B1 | `default-groups = []` in pyproject.toml blocks dev tools | Dev deps not installed by default `uv sync` |
| B2 | `uv.lock` is gitignored | `uv sync --frozen` breaks in CI |
| B3 | `CATALOG_PATH` cwd mismatch | Tests fail if not run from `src/backend/` |
| B4 | `migrate_locked.py` has hardcoded `cwd="/app"` | Path resolution fails outside Docker |
| B5 | Deleted `conftest.py` | Root test configuration missing |

---

## 3. Modern Best Practices (2024-2026 Era)

### 3.1 Docker Compose Architecture Patterns

**File naming:** `compose.yaml` is the preferred name (Docker Compose v2.27+); `docker-compose.yml` retains backward compatibility. Projects typically use:

```
compose.yaml          # base service definitions
compose.dev.yaml      # development overrides
compose.test.yaml     # test-specific service overrides
compose.prod.yaml     # production overrides
```

**Profile-based service gating:** Services like `test`, `redis`, `mailpit` are declared with `profiles: ["test"]` and activated via `docker compose --profile test up`. This prevents accidental activation in production.

**x- extension fields for DRY definitions:** YAML 1.1 extension keys (prefixed with `x-`) allow sharing service configuration without polluting the runtime config:

```yaml
x-test-service: &test-service
  profiles: ["test"]
  build:
    target: "app"

services:
  test:
    <<: *test-service
```

### 3.2 uv + Docker Optimization (2025-2026)

Based on Astral's official Docker guide and community patterns:

**Cache mount (CRITICAL):**
```dockerfile
RUN --mount=type=cache,target=/root/.cache/uv
    uv sync --frozen --no-install-project
```
- Cache survives container rebuilds, reducing dependency install from 15-30s to 1-3s
- Works with BuildKit (default in Docker Compose v2.20+)

**Compile bytecode:**
```dockerfile
ENV UV_COMPILE_BYTECODE=1
```
- Pre-compiles `.pyc` files during install â€” faster startup

**Link mode:**
```dockerfile
ENV UV_LINK_MODE=copy
```
- Avoids issues with hardlinks across container layers/filesystem boundaries

**--no-install-project for non-runtime stages:**
- Skips installing the project itself â€” only resolves dependencies
- Critical for test stages that need deps but use bind-mounted source

### 3.3 PostgreSQL Test Database Strategies

**Strategy 1: Ephemeral tmpfs (in-RAM database)**
```yaml
test-db:
  image: postgres:18-alpine
  tmpfs:
    - /var/lib/postgresql/data
```
- Database is created in RAM only
- Near-instant startup/teardown
- Zero disk I/O cost for test fixtures
- Risk: DB reset between container restarts loses all data (acceptable for tests)

**Strategy 2: Dedicated test database with test_ prefix**
```python
# Django settings automatically prefixes:
# "mko_bazuna" becomes "test_mko_bazuna"
# pytest-django handles this automatically
```
- pytest-django creates `test_<dbname>` by default
- `--reuse-db` caches schema between runs (10-30x faster for repeated runs)
- `--create-db` forces fresh creation (fallback for stale cache)

### 3.4 Process Management (init: true)

```yaml
test:
  init: true
```
- Docker Compose v2.47+ supports `init: true` shorthand
- Spawns `tini` (or `dumb-init`) as PID 1 inside container
- Ensures proper signal handling and zombie reaping for one-shot processes (tests)
- Without it: `KeyboardInterrupt` (Ctrl+C) doesn't propagate to pytest
- Without it: orphaned child processes (e.g., from aiogram) can accumulate

Without `init: true`, pressing Ctrl+C during `docker compose run --rm test` may leave zombie processes because the shell (PID 1) doesn't forward signals properly.

---

## 4. Three Architectural Approaches

### Approach A: Parallel Dev + Test via COMPOSE_PROJECT_NAME

**Concept:** Run separate Docker Compose projects for dev and test using `--project-name` (or `COMPOSE_PROJECT_NAME` env var). Each project gets its own isolated set of containers, networks, and volumes.

**How it works:**
```bash
# Development (persistent DB)
make dev

# Testing (ephemeral DB, separate containers)
COMPOSE_PROJECT_NAME=mko_test docker compose
  -f docker-compose.yml
  -f docker-compose.test.yml
  run --rm test

# Or run them simultaneously:
make dev  # blocks
COMPOSE_PROJECT_NAME=mko_test make test  # runs concurrently
```

**Changes required:**
- None to Dockerfile
- Update Makefile to pass COMPOSE_PROJECT_NAME=mko-bazuna-test to the test target
- Optionally add a compose.test.yml with explicit project name

**Pros:**
- Zero Dockerfile changes â€” uses existing image and entrypoint
- True isolation â€” dev DB and test DB are completely separate containers
- Simultaneous dev + test â€” developer can run tests while app is running
- Leverages existing ephemeral DB in docker-compose.test.yml
- Works today â€” no new infrastructure needed
- CI parity â€” mirrors CI pattern (separate, isolated DB per run)

**Cons:**
- Still re-runs full migrations each run (no `--reuse-db`)
- Still installs dev deps via `uv sync --group dev` at runtime (unless cache mount is added)
- Source not bind-mounted â†’ tests run against built image (but this is actually a feature for CI-like accuracy)

**Build/rebuild time:** 0s incremental (uses existing image)
**Test startup time:** ~5-8s (Postgres ephemeral init + migration + uv sync)
**Risk:** LOW â€” uses existing, tested infrastructure

### Approach B: Ephemeral tmpfs Test DB + pytest-django --reuse-db

**Concept:** Combine Docker Compose's tmpfs for instant PostgreSQL startup with pytest-django's `--reuse-db` to cache migration schema between runs. This is the fastest local test iteration strategy.

**How it works:**
```yaml
# docker-compose.test.yml
services:
  test-db:
    image: postgres:18-alpine
    tmpfs:
      - /var/lib/postgresql/data
    # No volume â†’ resets on every restart

  test:
    command: >
      sh -c "uv sync --frozen --no-install-project --group dev &&
             uv run python manage.py migrate &&
             uv run pytest --reuse-db --create-db --tb=short"
```

**Changes required:**
- Update docker-compose.test.yml to use tmpfs for postgres data
- Add `--reuse-db --create-db` to test entrypoint
- No settings changes needed â€” pytest-django handles test DB naming

**Pros:**
- Instant DB startup â€” tmpfs is in-RAM, eliminates disk I/O for DB init
- Schema caching â€” `--reuse-db` skips re-applying migrations on subsequent runs
- First run: ~5s, subsequent runs: ~2-3s (just uv sync + Python import time)
- No stale data pollution â€” tmpfs resets on container restart
- Standard pytest-django pattern â€” widely documented and used

**Cons:**
- `--reuse-db` can cause issues if migrations change between runs (mitigated by `--create-db` as fallback)
- Requires understanding of pytest-django's database lifecycle
- tmpfs consumes RAM (negligible for test DB sizes in this project)

**Build/rebuild time:** 0s incremental
**Test startup time (first run):** ~5-8s (full migrations)
**Test startup time (subsequent):** ~2-3s (schema cached)
**Risk:** MEDIUM â€” `--reuse-db` semantics need careful testing with Django migrations

### Approach C: Test-Specific Docker Stage with Cache-Optimized Build

**Concept:** Add a `test` target to the existing multi-stage Dockerfile that pre-installs dev dependencies during the image build (using uv cache mounts), so test containers start instantly without runtime `uv sync`.

**How it works:**
```dockerfile
# docker/Dockerfile
FROM python:3.14-slim AS base
# ... existing base layer

FROM base AS runtime
# ... existing runtime layer (production, no dev deps)

FROM base AS test
ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy
# Copy lockfile and pyproject first for cache layer reuse
COPY --from=uv-sync-helper /uv-cache /root/.cache/uv
RUN --mount=type=cache,target=/root/.cache/uv
    uv sync --frozen --no-install-project --group dev
COPY . /app
ENTRYPOINT ["sh", "-c", "uv run python manage.py migrate && uv run pytest --reuse-db --tb=short"]
```

**Changes required:**
- Add `test` stage to Dockerfile
- Update docker-compose.test.yml to use `build: target: test`
- Add cache mount directives for uv
- Ensure `uv.lock` is committed (fixes B2)

**Pros:**
- Fastest container startup â€” dev deps pre-installed in image layer
- Cache-efficient builds â€” uv cache mount persists across builds
- Reproducible â€” exact dependency versions baked into image
- CI-friendly â€” same image used everywhere
- Follows multi-stage best practices â€” Django's own project uses this pattern

**Cons:**
- Larger image â€” includes pytest, ruff, basedpyright in the image
- Rebuild on dependency change â€” requires image rebuild when deps change (but cache makes this fast)
- Complex build config â€” needs BuildKit cache mount setup, uv.lock must be committed
- Requires fixing B2 â€” uv.lock is currently gitignored

**Build/rebuild time (cold):** ~2-3 min (full dependency resolution + install)
**Build/rebuild time (warm):** ~10-30s (cache hits on uv layers)
**Test startup time:** ~3-5s (Postgres init + migration, no uv sync)

**Risk:** HIGH â€” requires Dockerfile changes, uv.lock commitment, BuildKit setup

---

## 5. Detailed Comparison Matrix

| Criteria | Approach A (Project Isolation) | Approach B (tmpfs + reuse-db) | Approach C (Test Docker Stage) |
|---|---|---|---|
| Implementation effort | 1 (Makefile change only) | 3 (compose + entrypoint + settings) | 5 (Dockerfile + compose + lockfile + build config) |
| Build time (incremental) | 0s | 0s | 10-30s (cache warm) |
| Test startup (first run) | ~6s | ~4s | ~3s |
| Test startup (subsequent) | ~6s | ~2-3s | ~3s |
| Requires Dockerfile changes | No | No | Yes |
| Requires uv.lock commit | No | No | Yes (critical) |
| Requires settings changes | No | Yes (--reuse-db) | No |
| Enables concurrent dev+test | Yes | Yes | Yes |
| CI parity | Partial (CI uses service container, not Compose) | High (tests same DB strategy) | High (same image) |
| Risk level | LOW | MEDIUM | HIGH |
| ROI (impact / effort) | 4 stars | 3 stars | 2 stars |

---

## 6. Recommendations (Ranked)

### 6.1 Recommended: Approach A â€” Parallel Dev + Test via COMPOSE_PROJECT_NAME

**Rationale:** This is the highest-ROI change. It requires editing only the Makefile (single line change) and immediately enables safe concurrent development and testing. The approach leverages infrastructure that already exists (docker-compose.test.yml with ephemeral DB, `profiles: ["test"]`). It mirrors the pattern CI already uses (separate, isolated database per run), bringing local dev closer to CI parity.

**Implementation:**
```makefile
# Before:
test:
	docker compose -f docker-compose.yml -f docker-compose.test.yml run --rm test

# After:
test:
	COMPOSE_PROJECT_NAME=mko-bazuna-test docker compose
		-f docker-compose.yml
		-f docker-compose.test.yml
		run --rm --profile test test
```

**Expected impact:** Eliminates a class of bugs where test containers interfere with running dev services. Enables running `make dev` and `make test` simultaneously.

### 6.2 Second Priority: Approach B â€” tmpfs + pytest-django --reuse-db

**Rationale:** After Approach A is in place, the dominant cost in test iteration is PostgreSQL initialization and migration replay. The `tmpfs` strategy eliminates disk I/O for the database, and `--reuse-db` eliminates migration replay on subsequent runs. This is a well-established pytest-django pattern (documented in the pytest-django docs) and is used by projects like Django itself.

**Implementation changes:**
1. In docker-compose.test.yml, add `tmpfs: ["/var/lib/postgresql/data"]` to test DB service
2. In docker/entrypoint-test.sh, add `--reuse-db --create-db` to pytest command
3. No settings changes needed â€” pytest-django handles test DB naming

**Expected impact:** Reduces subsequent test startup from ~6s to ~2-3s. For a developer running 50 test iterations per day, saves ~200 seconds daily.

### 6.3 Third Priority (Deferred): Approach C â€” Test-Specific Docker Stage

**Rationale:** While this provides the most cache-efficient and CI-reproducible setup, it requires the most invasive changes: a new Dockerfile stage, committing `uv.lock` (which is currently gitignored per audit finding B2), and setting up BuildKit cache mounts. This approach should be pursued only after A and B deliver their benefits, and after the `uv.lock` gitignore issue is resolved.

**Prerequisite:** Fix B2 (commit `uv.lock` to version control). Without this, `uv sync --frozen` will fail in CI and any reproducible build process.

**Expected impact:** Reduces container startup to ~3s and build rebuild to ~10-30s with cache hits. Most impactful for CI, where every build starts from a clean cache state.

---

## 7. Modern Docker Compose Configuration Patterns

Based on research from nickjj/docker-django-example, django/django, saleor, and wagtail:

### 7.1 Recommended File Structure
```
docker-compose.yml          # Base: shared service definitions, networks, volumes
docker-compose.dev.yml      # Dev: bind-mounts for hot-reload, DEBUG=True
docker-compose.test.yml     # Test: ephemeral DB, test-specific service, profiles
docker-compose.prod.yml     # Prod: image overrides, production settings
docker-compose.ci.yml       # CI: additional CI-specific overrides (optional)
```

### 7.2 Profile-based Services
```yaml
services:
  test:
    profiles: ["test"]
    # Only starts when: docker compose --profile test up
```

### 7.3 Extension Fields for DRY Config
```yaml
x-db-common: &db-common
  image: postgres:18-alpine
  environment:
    POSTGRES_DB: mko_bazuna
    POSTGRES_USER: postgres
    POSTGRES_PASSWORD: postgres

services:
  db:
    <<: *db-common
    volumes:
      - postgres_data:/var/lib/postgresql/data

  test-db:
    <<: *db-common
    profiles: ["test"]
    tmpfs:
      - /var/lib/postgresql/data
```

### 7.4 init: true for one-shot containers
```yaml
test:
  profiles: ["test"]
  init: true  # Ensures proper signal handling
```

---

## 8. uv Docker Optimization Summary

Based on Astral's official Docker guide and uv Docker best practices:

| Optimization | Directive | Purpose |
|---|---|---|
| Cache mount | `--mount=type=cache,target=/root/.cache/uv` | Persists downloaded wheels across builds |
| Compile bytecode | `ENV UV_COMPILE_BYTECODE=1` | Pre-compiles `.pyc` at install time |
| Link mode | `ENV UV_LINK_MODE=copy` | Avoids hardlink issues across layers |
| No install project | `uv sync --no-install-project` | For stages needing only deps, not the project |
| Default groups | `ENV UV_DEFAULT_GROUPS=""` or `uv sync --no-default-groups --group dev` | Explicitly controls which dependency groups are installed |
| Frozen lockfile | `uv sync --frozen` | Enforces reproducibility; requires committed uv.lock |

### 8.1 Cache Layer Reuse Pattern
```dockerfile
# Copy lockfile FIRST (changes less frequently than source)
COPY uv.lock pyproject.toml ./
RUN --mount=type=cache,target=/root/.cache/uv
    uv sync --frozen --no-install-project --group dev

# Copy source AFTER (changes more frequently)
COPY . .
```
This pattern ensures that the expensive `uv sync` layer is cached unless `pyproject.toml` or `uv.lock` changes.

---

## 9. Django + pytest-django Test Database Best Practices

### 9.1 Standard Test Database Strategy
- Django automatically creates `test_<dbname>` for the default database
- pytest-django manages test database creation/teardown
- `--reuse-db`: skips `DROP DATABASE` + `CREATE DATABASE` + migration replay on subsequent runs
- `--create-db`: forces fresh database creation (use when `--reuse-db` cache is stale)

### 9.2 Settings for Test Speed
```python
# config/settings/test.py
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": "mko_bazuna",
        "TEST": {
            "NAME": "test_mko_bazuna",  # Explicit (optional, auto-derived)
            "SERIALIZE": False,  # Skip test data serialization (faster)
        },
    }
}

# Use MD5 hasher (faster than default PBKDF2 for tests)
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
```

### 9.3 pytest-django Configuration
```ini
# pytest.ini or pyproject.toml [tool.pytest.ini_options]
DJANGO_SETTINGS_MODULE = "config.settings.test"
addopts = "--reuse-db --tb=short"
```

### 9.4 CI vs Local Test Pattern Comparison

| Aspect | CI (GitHub Actions) | Local (Docker Compose) | Recommended Local |
|--------|---------------------|----------------------|-------------------|
| DB provider | Service container | Docker Compose | Docker Compose |
| Python install | Host uv run | In-container uv sync | In-container uv sync |
| DB isolation | Service container (ephemeral) | Project name isolation | Project name + tmpfs |
| Dependency caching | setup-uv@v5 cache | uv_cache volume | uv_cache volume |
| DB reset | Fresh each run | Ephemeral (no volume) | tmpfs |
| Migration strategy | Full migrate each run | Full migrate each run | --reuse-db --create-db |

---

## 10. Risk Assessment

### 10.1 Approach A Risks
| Risk | Likelihood | Mitigation |
|------|-----------|------------|
| Project name collision on shared Docker hosts | LOW | Use a unique prefix like mko-bazuna-test |
| Volume name collision (test uses same named volumes) | LOW | Add volumes key overrides in test compose to use anonymous or prefixed volumes |
| Developer confusion between make dev and make test | LOW | Add Makefile comments and output labels |

### 10.2 Approach B Risks
| Risk | Likelihood | Mitigation |
|------|-----------|------------|
| --reuse-db fails if migration changes | MEDIUM | Always pair with --create-db as fallback; add pytest --reuse-db --create-db |
| tmpfs DB not truly ephemeral if container not restarted | LOW | Use ephemeral DB with no volume mount + tmpfs; Compose run --rm ensures container is removed |
| Schema cache inconsistency after model changes | MEDIUM | Run make test-recreate target that forces --create-db |

### 10.3 Approach C Risks
| Risk | Likelihood | Mitigation |
|------|-----------|------------|
| uv.lock not committed becomes build fails | HIGH (currently broken) | Fix B2 first: remove uv.lock from .gitignore and commit initial lockfile |
| Cache mount not effective in CI | MEDIUM | CI uses GitHub Actions cache, not Docker cache mounts |
| Larger test image | LOW | Acceptable for test-only builds; production uses runtime stage |
| BuildKit not enabled in older Docker versions | LOW | Docker Compose v2.20+ uses BuildKit by default |

---

## 11. Build Time Estimates

Based on research from Astral's uv Docker guide, Django project patterns, and typical CI/CD cache behavior:

| Scenario | Image Build | Dependency Install | DB Init + Migrate | pytest Startup | Total (Cold) | Total (Warm) |
|----------|------------|-------------------|-------------------|---------------|-------------|-------------|
| Current (Approach A only) | 0s (cached) | ~15s (uv sync) | ~3-4s | ~2s | ~20s | ~20s |
| Approach A + B | 0s | ~15s | ~1s (tmpfs) | ~2s | ~18s | ~5s |
| Approach C (cold build) | ~2-3 min | 0s (baked in) | ~3-4s | ~2s | ~2.5 min | N/A |
| Approach C (warm cache) | ~15s | 0s | ~3-4s | ~2s | ~20s | ~20s |

> Note: These estimates assume the project has ~20-30 migrations. For larger projects, the savings from `--reuse-db` are proportionally larger.

---

## 12. Real-World Examples Surveyed

### 12.1 django/django (official)
- Uses GitHub Actions with service containers for PostgreSQL/Redis/MySQL
- Runs `python -m pytest` directly (host-side uv, not Docker)
- Test databases managed by Django's `test_` prefix
- No Docker Compose for tests â€” CI uses Actions services exclusively

### 12.2 saleor/saleor
- Uses Docker Compose for both dev and test
- Separate `docker-compose.override.yml` for dev (bind-mounts)
- Tests run via `docker compose run --rm api pytest`
- Uses `--reuse-db` and `--create-db` pattern
- PostgreSQL with tmpfs for test DB

### 12.3 wagtail/wagtail
- CI uses GitHub Actions with service Postgres
- Local dev: `docker-compose.yml` with bind-mounts
- Tests: `python -m pytest` on host (uv)
- `--reuse-db` in pytest configuration

### 12.4 getsentry/sentry
- Multi-stage Dockerfile with many build targets
- CI uses GitHub Actions services
- Test containers use ephemeral PostgreSQL
- `--reuse-db` with `--create-db` fallback

### 12.5 nickjj/docker-django-example
- Comprehensive multi-environment compose setup
- Uses profiles for test services
- `postgres:18-alpine` with tmpfs for ephemeral test DB
- Multi-stage Dockerfile with `target: "app"` pattern
- `init: true` on all services for proper signal handling
- `x-` extension fields for DRY service definitions

### 12.6 astral-sh/uv-docker-example (official)
- Cache mount pattern for uv: `--mount=type=cache,target=/root/.cache/uv`
- `UV_COMPILE_BYTECODE=1`, `UV_LINK_MODE=copy`
- Multi-stage build: builder + runtime
- `--no-install-project` for dependency-only layers

---

## 13. Prerequisites and Blocking Issues

Before any approach can be fully implemented, two audit findings must be addressed:

### 13.1 B2: uv.lock is gitignored (BLOCKER for Approach C)
- `.gitignore` contains `uv.lock`
- `uv sync --frozen` will fail without committed lockfile
- **Fix:** Remove `uv.lock` from `.gitignore` and commit initial lockfile

### 13.2 B4: migrate_locked.py hardcoded cwd="/app"
- When running from host (CI pattern), cwd is `src/backend/`, not `/app/`
- **Fix:** Use `settings.BASE_DIR` or `os.path.dirname` instead of hardcoded path

### 13.3 B3: CATALOG_PATH cwd mismatch
- Tests fail if not run from `src/backend/`
- **Fix:** Use Django's `BASE_DIR` for path resolution

These are out of scope for this research report but should be flagged as prerequisites for the full optimization path.

---

## 14. Conclusion

The research identifies three viable architectural approaches for improving Mko Bazuna's Docker test environment:

1. **Approach A** (recommended first step): Use `COMPOSE_PROJECT_NAME` isolation for safe concurrent dev + test. Zero code changes, low risk, immediate benefit.
2. **Approach B** (second priority): Add `tmpfs` + `--reuse-db` for faster test iteration. Moderate changes, medium risk, high impact for daily development.
3. **Approach C** (longer-term): Add a test-specific Docker build stage with cache mounts. High effort, high risk, best for CI optimization.

The current CI workflow already implements a superior pattern (host uv + service container DB) compared to local Docker Compose tests. Approaches A and B bring local testing closer to CI parity while preserving the Docker-based workflow for consistency with the project's architecture (two processes, one DB).

**Next step:** Implement Approach A (Makefile change) and measure the improvement. Then evaluate Approach B for daily test iteration speed.
