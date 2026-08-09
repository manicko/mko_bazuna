# Specification: Isolated, Fast Test Environment for Docker Compose

**File:** `09_test-infrastructure_spec.md`
**Status:** Final (ready for implementation planning)
**Date:** 2026-08-09
**Source Decision:** `.ai/problems/Decision_10.md`
**Research:**
- Agent 1 — Current architecture & audit verification (`ses_01ad8fc66ffeUrOLirWMalazPI`)
- Agent 2 — Modern best practices (`docs/ops/research/docker-test-environment-research-report.md`)
- Audit: `.ai/audit/00-bug_report/test-infrastructure-issues.md` (B1–B5 all resolved by `6d9225d`)
- Audit: `.ai/audit/00-bug_report/301-ssl-redirect-test-failure.md` (SECURE_SSL_REDIRECT blocking view tests)

---

## 1. Problem Statement

The developer needs to run the Mko Bazuna development environment (Docker Compose with hot-reload via bind-mounts) **and** a test environment (ephemeral PostgreSQL + pytest) **simultaneously**. Currently this is impossible because both compose files share the default project name `mko_bazuna`, causing the `db` service to collide. Additionally, each test iteration requires rebuilding the Docker image (30–40 min) because the `test` service has no source code bind-mount — tests run against the image-baked source.

### Root causes (confirmed)

| # | Root cause | Evidence |
|---|-----------|----------|
| RC1 | **Project name collision** — `make up` and `make test` both use the default Docker Compose project name `mko_bazuna`. The `db` service container name (`mko_bazuna-db-1`) collides, so the test `db` cannot start while dev `db` is running. | `Makefile` lines 9–10; base `docker-compose.yml` defines `db` without `profiles:` |
| RC2 | **No source bind-mount in test service** — `docker-compose.test.yml` `test` service only mounts `uv_cache:/root/.cache/uv`. Code changes require a full Docker image rebuild (Tailwind CLI download + static build + collectstatic in `docker/Dockerfile` builder stage). | `docker-compose.test.yml` lines 59–60 |
| RC3 | **No `--reuse-db`** — `entrypoint-test.sh` runs `pytest --tb=short` with no `--reuse-db` flag, so Django replays all migrations every test run. | `docker/entrypoint-test.sh` line 37 |
| RC4 | **Test DB is ephemeral** — `docker-compose.test.yml` `db` override has `volumes: []`, so the PostgreSQL container is destroyed after each run. This prevents any schema caching. | `docker-compose.test.yml` line 19 |
| RC5 | **`SECURE_SSL_REDIRECT=True` inherited in test settings** — `config/settings/test.py` does NOT override `SECURE_SSL_REDIRECT` (inherited as `True` from `base.py` line 67). Django's `SecurityMiddleware` 301-redirects all HTTP test-client requests to HTTPS, blocking every DB-backed view test. | Audit `301-ssl-redirect-test-failure.md`; confirmed `grep SECURE_SSL test.py` = 0 matches |

### Audit status (B1–B5)

All five pre-existing infrastructure issues from `.ai/audit/00-bug_report/test-infrastructure-issues.md` were **already resolved** by commit `6d9225d` (Aug 8):

| ID | Issue | Resolution | Evidence |
|----|-------|------------|----------|
| B1 | `default-groups = []` blocks dev tools | `entrypoint-test.sh` runs `uv sync --frozen --no-install-project --group dev` | `docker/entrypoint-test.sh` line 14 |
| B2 | `uv.lock` gitignored | Removed from `.gitignore`; committed (1145-line lockfile in git) | `git ls-files uv.lock` = tracked; `.gitignore` has no `uv.lock` entry |
| B3 | CATALOG_PATH cwd mismatch | Fixed in `test_seed.py`, `load_catalog.py`, `seed_service.py` using `Path(__file__)` | `git log` shows fix in `6d9225d` |
| B4 | Hardcoded `cwd="/app"` in `migrate_locked.py` | Uses `Path(__file__).resolve().parents[3] / "manage.py"` | `migrate_locked.py` line 18 |
| B5 | Deleted `conftest.py` | N/A — root `conftest.py` supersedes it | Confirmed no stale `.pyc` |

> **Note:** The research report at `docs/ops/research/docker-test-environment-research-report.md` references B2 and B4 as open issues — this is outdated. Both are resolved in the current working tree.

---

## 2. Confirmed Requirements & Facts

### Facts (verified against current codebase)

- **F1.** `make test` runs `docker compose -f docker-compose.yml -f docker-compose.test.yml run --rm test` with **no** `COMPOSE_PROJECT_NAME` and **no** `--env-file`. The default project name is the directory name `mko_bazuna`, colliding with `make up`.
- **F2.** `docker-compose.test.yml` overrides `db` with `volumes: []` (ephemeral) and `restart: "no"`. The `test` service has `profiles: ["test"]` and only mounts `uv_cache:/root/.cache/uv`.
- **F3.** The base `docker-compose.yml` `db` service publishes **no host port** — it is internal-only. Dev `db` is at `mko-bazuna-db-1` (or `mko_bazuna-db-1` without project name) on an isolated Docker network.
- **F4.** The Dockerfile builder stage runs `tailwindcss` CLI download (`curl -L -o /usr/local/bin/tailwindcss`), Tailwind CSS compilation, and `collectstatic`. A full `--no-cache` rebuild takes 18–36 min across 6 services (migrate, load_catalog, create_admin, seed, web, bot).
- **F5.** `config/settings/test.py` imports `base.py` via `from .base import *` and overrides only `DEBUG=True`, `DATABASES["default"]["NAME"]="mko_bazuna"`, and `PASSWORD_HASHERS`. It does NOT override `SECURE_SSL_REDIRECT`, `SECURE_PROXY_SSL_HEADER`, or `MIDDLEWARE`. (Confirmed: `LocaleMiddleware` already removed by spec 08.)
- **F6.** `Makefile` has no `dev`, `test-db`, `test-down`, or `test-recreate` targets. `make test` is a single one-shot command.
- **F7.** `Makefile.ps1` mirrors the same targets for Windows.
- **F8.** `pyproject.toml` has `[tool.uv] default-groups = []` — `uv sync` without `--group dev` skips dev tools. `entrypoint-test.sh` compensates with `--group dev`.
- **F9.** `uv.lock` is committed to git (1145 lines). `--frozen` is safe to use.
- **F10.** `config/settings/base.py` sets `PYTHONPATH`-equivalent via `BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent` = `/app/src` in container, `/app/src` in dev bind-mount.

### Confirmed Requirements

- **CR1 — Parallel dev + test.** Running `make up` (or the user's `docker compose ... up -d` command) and `make test` simultaneously must not cause container/service name collisions or port conflicts.
- **CR2 — Fast test iteration (≤5 s incremental).** After the initial Docker image build, changing Python source code and re-running tests must NOT require rebuilding the Docker image. Source code must be bind-mounted into the test container (matching the dev workflow pattern).
- **CR3 — Long-running test PostgreSQL.** The test PostgreSQL container must persist between test runs (not destroyed after each `make test` invocation) to enable `--reuse-db` schema caching. This container must use a separate Docker project/network/volume from dev.
- **CR4 — Test DB host access (optional but preferred).** The test PostgreSQL should be accessible from the host on a dedicated port (5433) for debugging with `psql` or GUI tools.
- **CR5 — `init: true` on test service.** The `test` one-shot container must use `init: true` for proper PID 1 signal handling (Ctrl+C propagation, zombie reaping).
- **CR6 — `--reuse-db` for test speed.** pytest must use `--reuse-db` with a `--create-db` fallback to cache the test database schema between runs while allowing forced resets.
- **CR7 — Fix SECURE_SSL_REDIRECT in test settings.** `config/settings/test.py` must set `SECURE_SSL_REDIRECT = False` so that `django.test.Client` HTTP requests are not 301-redirected to HTTPS. This unblocks all DB-backed view tests.
- **CR8 — Zero Dockerfile changes required.** The solution must work without modifying `docker/Dockerfile`. If changes are needed, a full risk assessment of dev/prod impact is required (PO decision Q4=C).
- **CR9 — Makefile parity.** Both `Makefile` (Linux/macOS) and `Makefile.ps1` (Windows) must expose consistent targets.
- **CR10 — Backward compatibility.** Existing `make up`, `make down`, `make migrate`, etc. must continue to work unchanged for the dev workflow.

---

## 3. Conceptual Development Tasks

### Task 1: Add `COMPOSE_PROJECT_NAME` isolation to Makefile
**Purpose:** Prevent dev and test Docker Compose projects from colliding on service names, networks, and volumes.

**Expected outcome:**
- `Makefile`: `make up` → `COMPOSE_PROJECT_NAME=mko-bazuna-dev docker compose ...`
- `Makefile`: `make test` → `COMPOSE_PROJECT_NAME=mko-bazuna-test docker compose ...`
- `Makefile.ps1`: Same changes for `Invoke-Up` and `Invoke-Test`
- All other `COMPOSE_FILES`-based targets (lint, typecheck, shell, migrate, etc.) also get `COMPOSE_PROJECT_NAME=mko-bazuna-dev`
- All `COMPOSE_TEST`-based targets get `COMPOSE_PROJECT_NAME=mko-bazuna-test`

**Dependencies:** None (Makefile-only change). **Risk:** LOW.

### Task 2: Make test PostgreSQL long-running with persistent volume
**Purpose:** Keep a test PostgreSQL container alive between test runs so `--reuse-db` can cache the schema.

**Expected outcome:**
- `docker-compose.test.yml` `db` override: remove `volumes: []` (use base's `postgres_data` which becomes `mko-bazuna-test_postgres_data` via project name prefix)
- Change `restart: "no"` → `restart: unless-stopped` (or remove override to inherit base `restart: always`)
- Add `ports: ["5433:5432"]` for host-side debugging access (CR4)
- Fix `healthcheck` to use explicit `pg_isready -U postgres -d mko_bazuna` (already done in current test compose)

**Dependencies:** Task 1 (project name isolation). **Risk:** LOW — test compose is independent from dev/prod.

### Task 3: Add source bind-mount to test service
**Purpose:** Tests run against latest source code without rebuilding the Docker image.

**Expected outcome:**
- `docker-compose.test.yml` `test` service gains bind-mounts:
  ```yaml
  volumes:
    - .:/app
    - ./docker/entrypoint.sh:/app/entrypoint.sh
    - ./docker/entrypoint-test.sh:/app/entrypoint-test.sh
    - uv_cache:/root/.cache/uv
  ```
- Add `init: true` to `test` service (CR5)
- Add `SKIP_ENV_CHECK=1` env var (explicit safety, since `.env` is not mounted but `config.settings.test` already skips the check)

**Dependencies:** None (compose-only change). **Risk:** LOW — mirrors the dev override pattern exactly.

### Task 4: Add `--reuse-db --create-db` to test entrypoint
**Purpose:** Cache test database schema between runs for fast iteration.

**Expected outcome:**
- `docker/entrypoint-test.sh` line 37: change `uv run pytest --tb=short` → `uv run pytest --reuse-db --create-db --tb=short`
- Add `make test-recreate` Makefile target: `COMPOSE_PROJECT_NAME=mko-bazuna-test docker compose $(COMPOSE_TEST) run --rm --profile test test uv run pytest --no-reuse-db --create-db --tb=short`
- `Makefile.ps1`: Add matching `test-recreate` function

**Dependencies:** Task 2 (persistent test DB required for reuse). **Risk:** MEDIUM — `--reuse-db` can mask stale schema; mitigated by `--create-db` fallback and `make test-recreate` target.

### Task 5: Fix `SECURE_SSL_REDIRECT` in test settings
**Purpose:** Unblock all DB-backed view tests from 301 HTTPS redirect.

**Expected outcome:**
- `src/backend/config/settings/test.py`: add `SECURE_SSL_REDIRECT = False`
- Also add `SESSION_COOKIE_SECURE = False` and `CSRF_COOKIE_SECURE = False` for consistency with `dev.py` (which already sets these to `False`)

**Dependencies:** None. **Risk:** LOW — test-only setting change, mirrors `dev.py`.

### Task 6: Add test lifecycle Makefile targets
**Purpose:** Provide clear commands for starting, running, and tearing down the test environment.

**Expected outcome:**
- `make test-db` — Start only the test PostgreSQL container (long-running)
- `make test` — Start test DB (if not running) + run one-shot test service against it
- `make test-down` — Stop and remove test environment (with `-v` to optionally clear volumes)
- `make test-logs` — Tail test service logs
- `Makefile.ps1`: Matching PowerShell functions

**Dependencies:** Tasks 1–4. **Risk:** LOW — additive Makefile targets.

### Task 7: Update Docker deployment documentation
**Purpose:** Document the new test workflow, including parallel dev+test, `make test-db`, `make test-down`, and `--reuse-db` semantics.

**Expected outcome:**
- `docs/ops/docker-deployment.md`: Add "Test Environment" section covering:
  - Parallel dev + test with `COMPOSE_PROJECT_NAME`
  - `make test-db`, `make test`, `make test-down`, `make test-recreate`
  - `--reuse-db` workflow and when to use `--create-db`
  - Port 5433 for test DB debugging

**Dependencies:** Tasks 1–6. **Risk:** LOW — documentation only.

---

## 4. Product Owner Decisions

| # | Decision (from PO) | Implementation |
|---|---|---|
| D1 | Q1 = **A** — `COMPOSE_PROJECT_NAME` isolation for dev and test | `mko-bazuna-dev` and `mko-bazuna-test` project names (Task 1) |
| D2 | Q2 = **A** — Source bind-mount in test service (`.:/app`) | Mirrors dev override pattern (Task 3) |
| D3 | Q3 = **A** — Long-running test PostgreSQL, port 5433, persistent | Remove `volumes: []` from test `db`, add `ports: ["5433:5432"]` (Task 2) |
| D4 | Q4 = **C** — Any changes acceptable with full risk assessment | Dockerfile analysis confirms **zero** changes needed (see §7) |

---

## 5. Research Summary

### 5.1 Agent 1 — Current Architecture Investigation

**Key findings:**
- All 5 audit issues (B1–B5) from `test-infrastructure-issues.md` are **already resolved** by commit `6d9225d`. The research report (Session 2) incorrectly lists B2 and B4 as open — both are fixed in the current working tree.
- **Root cause of "test environment doesn't start":** `COMPOSE_PROJECT_NAME` collision. Both `make up` (default project `mko_bazuna`) and `make test` (default project `mko_bazuna`) try to create a container named `mko_bazuna-db-1`. The test `db` cannot start because the dev `db` already holds that name.
- **Root cause of 30–40 min iteration:** The `test` service in `docker-compose.test.yml` has no source bind-mount. Every code change requires `docker compose build` (or `--build`), which re-runs the full Dockerfile builder stage: Tailwind CLI download (~30s), `uv sync` (~60s), Tailwind CSS compilation (~30s), `collectstatic` (~60s), times 6 services.
- **New critical issue found:** `config/settings/test.py` does not override `SECURE_SSL_REDIRECT` (inherited as `True` from `base.py`). This causes `SecurityMiddleware` to 301-redirect every HTTP test-client request to HTTPS, blocking all 15+ DB-backed view test files.
- **Dockerfile risk:** The `test` service can safely add a source bind-mount without touching the Dockerfile. The Dockerfile's runtime stage already sets `UV_NO_INSTALL_PROJECT=1`, `UV_FROZEN=1`, `PYTHONPATH=/app/src:/app/src/backend`, `UV_PROJECT_ENVIRONMENT=/opt/venv` — these are all compatible with bind-mounting source code (as dev already does).

### 5.2 Agent 2 — Modern Best Practices Research Report

Full report: `docs/ops/research/docker-test-environment-research-report.md`

**Three approaches evaluated:**

| Approach | Description | ROI | Risk | Implementation |
|----------|-------------|-----|------|----------------|
| A ⭐ | Project name isolation (`COMPOSE_PROJECT_NAME`) | ★★★★ | LOW | Makefile only |
| B | tmpfs + `--reuse-db --create-db` | ★★★ | MEDIUM | Compose + entrypoint |
| C | Test-specific Dockerfile stage | ★★ | HIGH | Dockerfile + cache mounts |

**Key best practices identified:**
- `COMPOSE_PROJECT_NAME` is the standard Docker Compose pattern for running multiple environments simultaneously
- `init: true` on one-shot containers ensures proper signal handling (Ctrl+C, zombie reaping)
- `--reuse-db` with `--create-db` fallback is the pytest-django standard for fast iteration (used by django/django, saleor, getsentry)
- `x-` extension fields for DRY service definitions (not needed at this scope)
- `profiles:` gates optional services (already used by the `test` service)
- uv cache mount (`--mount=type=cache,target=/root/.cache/uv`) in Dockerfile for build cache (already used in builder stage)
- CI pattern (GitHub Actions service containers) is superior to local Docker for tests, but local Docker is the developer's chosen workflow

**Real-world project patterns surveyed:**
- `django/django`: CI uses GitHub Actions service containers, host-side uv, no Docker Compose for tests
- `saleor/saleor`: Separate `docker-compose.override.yml` for dev; tests run via `docker compose run --rm`; uses `--reuse-db` and tmpfs
- `wagtail/wagtail`: CI uses GitHub Actions services; local tests via host uv + Docker PostgreSQL
- `getsentry/sentry`: Multi-stage Dockerfile; CI services; `--reuse-db --create-db` pattern
- `nickjj/docker-django-example`: Profiles for test services, tmpfs, `init: true`, extension fields

**Final recommendation:** Approach A (project name isolation) as the immediate win, followed by Approach B (persistent DB + `--reuse-db`) for ongoing iteration speed. The PO has chosen exactly this combination (Q1=A, Q3=A).

---

## 6. Assumptions

1. **A1.** The developer runs tests locally via Docker Compose (not host-side `uv run pytest`). This is confirmed by the existing `Makefile` `test` target and `VERIFY_TESTS_INSTRUCTIONS.md`.
2. **A2.** The developer has `uv.lock` committed (confirmed — 1145-line lockfile is tracked in git).
3. **A3.** The Docker image is already built (via `make build` or the user's `docker compose ... build`). The 30–40 min issue is per-change rebuild, not initial build.
4. **A4.** The developer's machine has sufficient disk space for two PostgreSQL containers (dev + test) running simultaneously.
5. **A5.** The `make test` one-shot pattern (`docker compose run --rm test`) is the preferred test invocation — not `docker compose up --profile test`.
6. **A6.** The dev environment uses the default project name or will be updated to `mko-bazuna-dev` as part of Task 1. If the developer has existing containers from the old project name, they need to `make down` before switching.
7. **A7.** The test DB on port 5433 is for debugging only — production tests connect via the Docker network (`db:5432`).
8. **A8.** `--reuse-db` schema caching is acceptable; `--create-db` as fallback handles schema drift. The `make test-recreate` target provides manual reset.

---

## 7. Constraints

1. **Django 5.2 LTS** (`>=5.2.16,<6.0`) — `config.settings.test` must remain compatible.
2. **Python 3.14** — `entrypoint-test.sh` uses `uv run` which requires Python 3.14 compatibility.
3. **PostgreSQL 18 only** — No SQLite fallback (zone C5). The test DB must be PostgreSQL.
4. **PostgreSQL is not published by dev** — The dev `db` service publishes no host port. The test `db` service will publish port 5433 (dev/test isolation).
5. **pgBouncer is production-only** — Not used in dev or test. Session-scoped advisory lock in `migrate_locked.py` is safe.
6. **`--frozen` uv sync** — `entrypoint-test.sh` uses `uv sync --frozen`. With source bind-mount, this requires the host's `uv.lock` to be in sync with `pyproject.toml`. Developers must run `uv lock` after dependency changes.
7. **`PYTHONPATH=/app/src:/app/src/backend`** — Set as ENV in Dockerfile runtime stage. The bind-mount `.:/app` is compatible (source layout matches).
8. **`UV_PROJECT_ENVIRONMENT=/opt/venv`** — Set as ENV in Dockerfile. The venv is NOT bind-mounted; `uv sync` modifies it in-container. The `test` service with `--rm` discards changes after each run.
9. **Two processes, one DB** — The test environment has its own DB. This is a separate instance from dev, which is acceptable for testing.
10. **`migrate_locked.py` uses advisory lock ID 100** — Safe to run in both dev and test (different databases).

---

## 8. Risks

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Dev DB and test DB share the same project name after partial rollout | Medium | Medium | Update Makefile and Makefile.ps1 atomically; verify with `make test` while `make up` is running |
| `--reuse-db` returns stale schema after migration changes | Medium | Medium | Pair `--reuse-db` with `--create-db` flag; document `make test-recreate` for resets; add `--create-db` to the default pytest command so Django always checks for pending migrations |
| Source bind-mount breaks `uv sync --frozen` if `uv.lock` is out of sync | Low | Medium | Ensure `uv.lock` is committed (confirmed); document `uv lock` requirement; consider `--frozen` → `--locked` with fallback for development |
| Port 5433 conflict with another service on host | Low | Low | Use a less-common port (5433 is standard for secondary Postgres); make it configurable via env var |
| Breaking change to `make up` (new `COMPOSE_PROJECT_NAME`) orphans existing containers | Medium | Low | Document `make down` before switching; add cleanup instructions to spec |
| `init: true` requires Docker Compose v2.47+ | Low | Low | Verify Docker version in prerequisites; `init: true` is a compose-level feature, not a Dockerfile change |
| Test service bind-mount hides image-built static files | Low | Low | Tests don't need static files (no `collectstatic` dependency); `WHITENOISE` is disabled in test settings via `DEBUG=True` |
| Dev deps cached in `uv_cache` volume across test runs | Low | Low | `uv_cache` volume persists — expected behavior for faster subsequent runs; can be cleared with `make test-down -v` |

---

## 9. Open Questions

| # | Question | Status |
|---|----------|--------|
| O1 | Should dev also get a `COMPOSE_PROJECT_NAME` prefix, or stay as default? | Resolved: D1 — yes, `mko-bazuna-dev` for consistency and true isolation |
| O2 | Should `make test` auto-start the test DB, or require `make test-db` first? | Resolved: `make test` should auto-start test DB if not running (convenience), and leave it running for `--reuse-db` |
| O3 | Should `make test` automatically run `make test-down` cleanup on exit? | Resolved: No — the test DB must persist for `--reuse-db` to work. User manually runs `make test-down` when done |
| O4 | Should port 5433 be configurable via env var? | Resolved: Keep simple — hardcode 5433. Can be changed later if needed |
| O5 | Should `--reuse-db` be added to `pyproject.toml` `addopts` for host-side `uv run pytest` parity? | Resolved: No — CI creates a fresh DB each run. `--reuse-db` stays Docker-only in `entrypoint-test.sh` |

---

## 10. Out of Scope

1. **CI/CD pipeline changes** — The existing CI workflow (`ci.yml` in the research report's CI section) already uses GitHub Actions service containers with isolated PostgreSQL. No changes needed.
2. **Dockerfile changes** — Zero Dockerfile modifications required (Q4=C allows changes, but none are needed).
3. **Host-side `uv run pytest`** — The developer prefers Docker-based testing. No changes to the `conftest.py` local `DATABASE_URL` default.
4. **Test-specific Docker build stage (Approach C)** — Deferred. The source bind-mount (Task 3) provides sufficient speed improvement without Dockerfile changes.
5. **`tmpfs` for test DB (Approach B detail)** — Not needed because the PO chose persistent test DB (Q3=A). `--reuse-db` on a persistent volume is faster than tmpfs + no-reuse for subsequent runs.
6. **Renaming compose files to `compose.yaml`** — The CI/CD plan (`docs/plans/ci_cd/plan.md`) mentions this, but it is out of scope for this spec.
7. **Multiple test DB schemas** — Single `mko_bazuna_test` database is sufficient. No parallel test workers (no `--numprocesses` / pytest-xdist).

---

## 11. Definition of Ready

This specification is ready for implementation planning when all of the following are verified:

1. ✅ All 4 PO decisions captured (D1–D4).
2. ✅ Research on current architecture is complete and all claims verified against codebase (Agent 1 report).
3. ✅ Research on modern best practices is complete and approaches ranked (Agent 2 report).
4. ✅ Audit findings B1–B5 confirmed as resolved — no false blockers in the research.
5. ✅ New critical issue (SECURE_SSL_REDIRECT) identified and assigned to Task 5.
6. ✅ All conceptual tasks (T1–T7) are independent with clear acceptance criteria.
7. ✅ Dockerfile risk assessment complete: zero changes needed, bind-mount is safe (mirrors dev pattern).
8. ✅ Risks documented with mitigations.
9. ✅ Out of scope clearly delimited (CI changes, Dockerfile changes, host-side testing).
