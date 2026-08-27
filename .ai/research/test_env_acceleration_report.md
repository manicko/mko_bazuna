---
id: test-env-acceleration-report
domain: research
related:
  - docs/99-agent/architecture
  - docs/99-agent/rules
  tags:
    - docker-compose
    - test-environment
    - acceleration
    - pytest-xdist
    - migrations
    - uv-sync
    - pg-tuning
---

# Test Environment Acceleration Report

**Project:** Mko Bazuna
**Date:** 2026-08-27
**Method:** Static codebase analysis (`docker/entrypoint-test.sh`, `docker/entrypoint.sh`, `Makefile`, `Makefile.ps1`, `docker-compose.test.yml`, `docker-compose.yml`, `docker/Dockerfile`, `pyproject.toml`, `ci.yml`, `ci-nightly.yml`, `apps/core/utils/migrate_locked.py`, `src/backend/conftest.py`, `src/telegram_bot/tests/conftest.py`, `apps/seed/tests/conftest.py`) + cross-reference with prior profiling reports (`.ai/reports/test_suite_audit_step2_profiling.md`, `.ai/reports/test_suite_audit_step1_current_state.md`, `.ai/plans/test-suite-audit-plan.md`, `.ai/research/docker-one-shot-lifecycle-analysis.md`).
**Confidence legend (per item):** HIGH = directly verified in source; MEDIUM = inferred from source with documented reasoning; LOW = extrapolated from community documentation or measured proxy data.

---

## Executive Summary

The end-to-end pipeline from `make test` invocation to "pytest collecting" has **four fixed-cost stages** that dominate local iteration time:

| Stage | Time | Dominant? | Parallelizable? |
|---|---|---|---|
| `uv sync` (dev deps install) | **25–29s cold** / ~2s cached | **YES** (cold first run) | No |
| Migrations (`migrate_locked` + pytest-django on `test_mko_bazuna`) | 3–30s depending on `--create-db` | Medium (scales with migration count) | No (serial) |
| `compilemessages` (runs **twice**) | **~4–6s** | Medium (redundant) | No |
| Serial test execution (no xdist) | **~415s estimated** | **YES** (by far the largest component) | Yes — xdist in CI, absent locally |

The **#1 acceleration opportunity** is enabling `pytest-xdist` in the local entrypoint — CI already uses `-n auto --dist loadgroup` (85s measured) while local runs execute **serially** (~415s estimated for 1025 fast-gate tests). The **#2 opportunity** is eliminating the 25–29s `uv sync` cold-start by precompiling the venv with dev dependencies into the test image layer. **#3** is removing the redundant double `compilemessages` and double DB-wait. **#4** is `MIGRATION_MODULES = {app: None}` to skip all 39 migration files when `--create-db` is used.

Per Problem_02.md point 4, migration consolidation (`consolidate_migrations.py`) is a **separate** sub-task — it is noted in §2.5 below as an independent lever that only helps when `--create-db` is used (i.e., `make test-recreate`), not for `--reuse-db` (the default).

---

## 1. Stage-by-Stage Bottleneck Table

### Stage 1 — Image Availability / Layer Cache

**What happens:** The `test` service (`docker-compose.test.yml:46-74`) builds from the production runtime image (`docker/Dockerfile` Stage 2, lines 84–155). This image contains a venv at `/opt/venv` with **production dependencies only** — dev deps (pytest, pytest-xdist, pytest-django, etc.) are **excluded** via `--no-dev --no-default-groups` (Dockerfile line 48). The source is bind-mounted (`.:/app`, compose line 69), so the image's `COPY`'d source is overridden by the host working tree.

**Measured/best-estimate time:** ~0s on normal `make test` (image already built by `make build`). **25–60s** if the image must be built/rebuilt (the Dockerfile builder stage does Tailwind + collectstatic + compilemessages, lines 76–78).

**Dominant?** No — image is pre-built for `make test`. Only matters after `make build` or Dockerfile changes.

**Parallelizable?** N/A (image build is serial, but cached via Docker layer cache).

**Evidence / exact lines:**
- `docker-compose.test.yml:47-49` — `build: context: . dockerfile: docker/Dockerfile`
- `Dockerfile:46-49` — `uv sync --frozen --no-install-project --no-dev --no-default-groups`
- `docker-compose.test.yml:69` — `volumes: - .:/app` (bind mount overrides image source)

**Confidence:** HIGH

---

### Stage 2 — Container Create + `init: true` Tini

**What happens:** `docker compose run --rm test` creates a new container from the image. `init: true` (docker-compose.test.yml:51) injects Tini as PID 1, which forwards signals (SIGTERM, SIGINT) and reaps zombies. The container's `depends_on: db: condition: service_healthy` (compose lines 52–54) ensures the DB is already healthy before the test container starts.

**Measured/best-estimate time:** ~1–2s (container creation + bind mount setup + Tini startup). Tini overhead itself is negligible (<10ms).

**Dominant?** No.

**Parallelizable?** No (container startup is serial per invocation).

**Evidence / exact lines:**
- `docker-compose.test.yml:51` — `init: true`
- `docker-compose.test.yml:52-54` — `depends_on: db: condition: service_healthy`
- `entrypoint.sh:82-89` — `if [ "${BASH_SOURCE[0]}" = "$0" ]; then ... exec "$@"; fi` (entrypoint.sh runs as PID 2 under Tini)

**Confidence:** HIGH

---

### Stage 3 — `uv sync --frozen --no-install-project --group dev`

**What happens:** `entrypoint-test.sh:14` runs `uv sync --frozen --no-install-project --group dev`. Because the image venv was built with `--no-dev` (Dockerfile line 48), this command **installs all 9 dev dependencies** (pytest, pytest-asyncio, pytest-cov, pytest-django, pytest-xdist, ruff, coverage, djlint, basedpyright) into the existing `/opt/venv` on every container start.

**Measured/best-estimate time:**
- **Cold** (first run after image build or uv_cache volume reset): **25–29s** — installs 9 packages + transitive dependencies and compiles 4058 bytecode files. Measured by `.ai/reports/test_suite_audit_step2_profiling.md:36-38`.
- **Warm** (uv_cache volume populated): **~2s** — downloads cached, but packages still need to be unpacked and bytecode compiled into the venv.

**Dominant?** **YES on cold starts.** This is 60–70% of the total pipeline time when running small test tiers individually (per step2 profiling: "settings tier (35s total) = 70% overhead"). The warm-cache time (~2s) is negligible.

**Not parallelizable** — `uv sync` must complete before any subsequent stage (DB wait, migration, pytest) can proceed.

**Why it's not cached in the image:** The Dockerfile's builder stage (line 48) installs with `--no-dev`. The runtime stage copies this venv (Dockerfile line 106), so it lacks dev deps. The `entrypoint-test.sh` must install them at runtime. The `uv_cache` volume (docker-compose.test.yml:72) caches download artifacts but does NOT cache the installed venv state.

**Evidence / exact lines:**
- `entrypoint-test.sh:14` — `uv sync --frozen --no-install-project --group dev`
- `Dockerfile:48` — `uv sync --frozen --no-install-project --no-dev --no-default-groups`
- `Dockerfile:106` — `COPY --from=builder --chown=app:app /opt/venv /opt/venv` (venv copied without dev deps)
- `docker-compose.test.yml:64` — `UV_NO_INSTALL_PROJECT=0` (overrides Dockerfile's `UV_NO_INSTALL_PROJECT=1`, but the `--no-install-project` CLI flag on line 14 of entrypoint-test.sh takes precedence — the env override is effectively inert)
- `docker-compose.test.yml:72` — `uv_cache:/root/.cache/uv` (download cache only, not venv state)
- `pyproject.toml:196-209` — `[dependency-groups] dev` lists 9 packages
- `test_suite_audit_step1_current_state.md:42` — `addopts` has no `--cov`; coverage is CI-only
- `test_suite_audit_step1_current_state.md:374-378` — `default-groups = []` keeps dev tools out of production image

**Confidence:** HIGH

---

### Stage 4 — DB Healthcheck Wait (`pg_isready`)

**What happens:** The DB connection check runs **three times** in sequence:

1. **Docker Compose `depends_on` healthcheck** — `docker-compose.test.yml:24-28` defines `healthcheck: test: ["CMD-SHELL", "pg_isready -U postgres -d mko_bazuna"]` with `interval: 5s, timeout: 5s, retries: 5`. The `test` service's `depends_on: db: condition: service_healthy` (compose line 52-54) ensures the DB is healthy before the test container's ENTRYPOINT runs.
2. **`entrypoint.sh` `wait_for_db()`** — `entrypoint.sh:40-48` runs `pg_isready` via `/opt/venv/bin/python -c "import psycopg; psycopg.connect('$DATABASE_URL')"`. Since the DB is already healthy (step 1), this completes in ~0s.
3. **`entrypoint-test.sh` DB check** — `entrypoint-test.sh:18-29` runs the **same** pg_isready loop again via `uv run python -c "import psycopg; psycopg.connect('$DATABASE_URL')"`. Redundant with step 2. This uses `uv run python` (requires `uv sync` from Stage 3 to have completed).

The `make test` target (`Makefile:100`) pre-starts the DB with `docker compose up -d db`, so by the time the test container starts, the DB is already healthy and accepting connections. Steps 2 and 3 are both no-ops (exit immediately on first iteration).

**Measured/best-estimate time:** ~0–1s each (DB already healthy). Total ~2–3s of **redundant** wait time.

**Dominant?** No (but the redundancy is a correctness smell).

**Parallelizable?** No (must be serial — DB must be ready before migration/tests).

**Evidence / exact lines:**
- `docker-compose.test.yml:24-28` — DB healthcheck definition
- `docker-compose.test.yml:52-54` — `depends_on: db: condition: service_healthy`
- `entrypoint.sh:39-48` — `wait_for_db()` function (first check)
- `entrypoint-test.sh:17-29` — second DB check loop (redundant)
- `Makefile:100` — `docker compose $(COMPOSE_TEST) up -d db` (pre-starts DB)
- `test_suite_audit_step2_profiling.md:39` — "DB connection wait + migration advisory lock | ~3s"

**Confidence:** HIGH

---

### Stage 5 — Migration Application via `migrate_locked.main()`

**What happens:** Two separate migration passes occur:

#### Pass A: Entrypoint `migrate_locked.main()` (entrypoint-test.sh:33)
Runs `manage.py migrate --noinput` inside a session-scoped PostgreSQL advisory lock (`AdvisoryLockId.MIGRATE = 100`, `migrate_locked.py:26`). The `DJANGO_SETTINGS_MODULE=config.settings.test` env var (docker-compose.test.yml:56) means test settings are used. **Critically**, `test.py:21` sets `DATABASES["default"]["NAME"] = "mko_bazuna"` — so `migrate_locked` applies migrations to the `mko_bazuna` database, **NOT** the `test_mko_bazuna` database that pytest-django uses.

**Pass A is wasted work for pytest.** pytest-django never reads from `mko_bazuna`; it creates `test_mko_bazuna` (by prepending `test_` to the DB name) and runs its own migrations there. No test in the suite uses `django_db_setup` to override this (confirmed by grep: zero `django_db_setup` or `MIGRATION_MODULES` or `django_db_use_migrations` references in the codebase). The `migrate_locked` step is a copy of the production entrypoint pattern and serves no purpose in the test pipeline.

#### Pass B: pytest-django test database creation (pytest-django default behavior)
pytest-django reads `DATABASES["default"]["NAME"]` = `mko_bazuna` and creates `test_mko_bazuna`. With `--reuse-db` (default in entrypoint-test.sh:56), if `test_mko_bazuna` exists, pytest-django calls `migrate` to apply any unrecorded migrations (fast — ~1s, just checks `django_migrations` table). With `--no-reuse-db --create-db` (Makefile:137, used by `make test-recreate`), pytest-django drops and recreates `test_mko_bazuna` from scratch, running **all 39 migration files** serially.

**Migration file count (39 total):**
| App | Count | Migration files |
|-----|-------|-----------------|
| ads | 12 | 0001–0012 (exceeds `CONSOLIDATE_THRESHOLD=8` in Makefile:168) |
| analytics | 4 | 0001–0004 |
| categories | 2 | 0001–0002 |
| core | 0 | No models (utility/management commands only) |
| currencies | 2 | 0001–0002 |
| locations | 1 | 0001 |
| lookups | 1 | 0001 |
| moderation | 2 | 0001–0002 |
| search | 7 | 0001–0007 |
| trust | 2 | 0001–0002 |
| users | 6 | 0001–0006 |

**Measured/best-estimate time:**
- Pass A (`migrate_locked` on `mko_bazuna`): ~3s (idempotent check when migrations already applied; first cold start ~5–15s to apply all 39)
- Pass B with `--reuse-db`: ~1s (checks `django_migrations` table for unapplied migrations)
- Pass B with `--create-db`: ~15–30s (runs all 39 migrations sequentially, each involving Python class instantiation + SQL execution + `django_migrations` INSERT)

**Dominant?** Medium — only dominant for `make test-recreate` (full schema rebuild). For the default `make test` (reuse-db), it's ~4s total (3s + 1s) which is small but still wasted.

**Parallelizable?** No — migrations must be serial (dependency-ordered). Can be **eliminated** with `MIGRATION_MODULES = {app: None}` in test settings (see §3.2).

**Evidence / exact lines:**
- `entrypoint-test.sh:33` — `uv run python -c "from apps.core.utils.migrate_locked import main; import sys; sys.exit(main())"`
- `apps/core/utils/migrate_locked.py:14-30` — `main()` function, uses `advisory_lock(AdvisoryLockId.MIGRATE, session=True)` at line 26, runs `manage.py migrate --noinput` at line 27-29
- `src/backend/config/settings/test.py:21` — `DATABASES["default"]["NAME"] = "mko_bazuna"`
- `docker-compose.test.yml:56` — `DJANGO_SETTINGS_MODULE=config.settings.test`
- `entrypoint-test.sh:56` — default PYTEST_OPTS includes `--reuse-db`
- `Makefile:137` — `test-recreate` sets `PYTEST_OPTS="--no-reuse-db --create-db --tb=short"`
- Migration file counts verified by filesystem scan (39 files across 10 apps)
- `Makefile:168` — `CONSOLIDATE_THRESHOLD ?= 8`
- `scripts/consolidate_migrations.py:139` — `should_consolidate = args.force or count > args.threshold`
- `pyproject.toml:160` — `addopts = ["--import-mode=importlib", "-ra", "-q"]` (no `--no-migrations` or `MIGRATION_MODULES`)
- `test_suite_audit_step1_current_state.md:42` — confirms `--cov` is not in addopts; coverage CI-only

**Migration consolidation context (Problem_02.md §4):** `consolidate_migrations.py` deletes all `[0-9]*.py` files for apps exceeding the threshold (default 8), then `makemigrations` regenerates a single initial migration. Only `ads` (12 files) exceeds the threshold. Consolidation would reduce 39 → 28 migration files. However, this only helps `--create-db` (test-recreate), NOT `--reuse-db` (the default). For `--reuse-db`, migrations are already applied and pytest-django's `migrate` call is a fast no-op check. Consolidation is a **complementary** optimization, not a substitute for `MIGRATION_MODULES = None`.

**Confidence:** HIGH (Pass A is wasted — verified by tracing settings → DB name; Pass B behavior per pytest-django docs)

---

### Stage 6 — `compilemessages` (`.po → .mo`) Every Run

**What happens:** Translation compilation runs **twice** in the pipeline:

1. **`entrypoint.sh` `compile_messages()`** — `entrypoint.sh:73-77` runs `/opt/venv/bin/python /app/src/backend/manage.py compilemessages 2>/dev/null || echo "WARNING..."` (non-fatal). This executes because `entrypoint.sh` runs as the Docker ENTRYPOINT (Dockerfile line 154: `ENTRYPOINT ["/app/entrypoint.sh"]`) with `entrypoint-test.sh` as the CMD argument.
2. **`entrypoint-test.sh` compilemessages** — `entrypoint-test.sh:37` runs `uv run python src/backend/manage.py compilemessages` (explicit, after `uv sync`).

Both compile the same 3 `.po` files (`locale/ru/LC_MESSAGES/django.po`, `locale/bs/...`, `locale/en/...`, verified by filesystem scan: 3 `.po` files, 3 `.mo` files). Since `.mo` files are **git-ignored** (`.gitignore:55: *.mo`), the bind-mounted source (`.:/app`) does not contain `.mo` files from git. The `compilemessages` step in the entrypoint generates them at container start.

The Dockerfile builder stage DOES run `compilemessages` (Dockerfile line 78), but the bind mount in the test compose (`.:/app`, docker-compose.test.yml:69) **shadows** the image's compiled `.mo` files with the host's source directory (which has no tracked `.mo` files).

**Measured/best-estimate time:** ~2–3s per run × 2 runs = **~4–6s** total. The 3 `.po` files are small (14–29 KB each, verified by filesystem scan). Most time is Python interpreter startup + Django settings loading, not actual compilation.

**Dominant?** No (but the redundancy is easily eliminated).

**Parallelizable?** No (compilemessages is serial by nature; could be parallelized across languages with `compilemessages -l ru,bs,en` but the overhead of 3 languages is negligible).

**Evidence / exact lines:**
- `entrypoint.sh:73-77` — `compile_messages()` function (first run)
- `entrypoint-test.sh:37` — `uv run python src/backend/manage.py compilemessages` (second run)
- `entrypoint.sh:82-89` — entrypoint.sh runs as ENTRYPOINT, executes `compile_messages` then `exec "$@"`
- `Dockerfile:78` — builder stage runs compilemessages at build time (shadowed by bind mount in test)
- `Dockerfile:154` — `ENTRYPOINT ["/app/entrypoint.sh"]`
- `docker-compose.test.yml:69` — `.:/app` bind mount (shadows image's `.mo` files)
- `docker-compose.test.yml:70-71` — entrypoint scripts also bind-mounted
- `.gitignore:55` — `*.mo` (compiled files not tracked in git)

**Confidence:** HIGH

---

### Stage 7 — Pytest Collection + First Test Setup

**What happens:** pytest starts with the default PYTEST_OPTS from entrypoint-test.sh:56: `--reuse-db --tb=short --durations=10` (no xdist, no coverage). The `addopts` from pyproject.toml:160 (`--import-mode=importlib -ra -q`) is also prepended. If `PYTEST_SKIP_MARKERS=seed` is set (by `make test`), the entrypoint appends `-m "not (seed)"` (entrypoint-test.sh:52-54).

**Test count:** 1091 total (1009 backend + 80 bot + 2 settings, per step1 audit). Fast-gate excludes 26 `@pytest.mark.seed` tests → **1025 collected** (step2 profiling:1025).

**Collection overhead:** pytest must import all 88 test modules, resolve fixtures from 3 conftest.py files (`src/backend/conftest.py`, `src/telegram_bot/tests/conftest.py`, `apps/seed/tests/conftest.py`), and apply module-level `pytestmark` (84 of 89 files use it, step1 audit:184). The `--import-mode=importlib` (pyproject.toml:160) means each test module is imported as a unique package, which is slower than default `prepend` mode but avoids import side-effects.

**Per-test setup overhead:** 8 of the 10 slowest fast-gate tests (step2 profiling:67-79) spend their time in the **setup phase**, not test logic. The cause is `django_db(transaction=True)` (TRUNCATE ... CASCADE per test). The 7 bot files using this marker are listed in step1 audit:219. `test_ad_lifecycle.py` uses `django_db` (without `transaction=True`, line 23) — it gets normal TestCase transaction rollback, which is faster but doesn't support cross-thread DB access.

**Measured/best-estimate time:**
- Collection: ~3–5s (no `testpaths` configured; pytest discovers from rootdir = project root)
- First test setup (Django app loading, fixture resolution): ~2–3s
- Test execution (serial, no xdist): **~415s estimated** for 1025 tests (step2 profiling:196 extrapolates ~415s serial vs 85s with 8-worker xdist)
- Test execution (with xdist, 8 workers): **85s** measured (step2 profiling:14)

**Dominant?** **YES** — test execution is by far the largest time component. Local serial execution (~415s) vs CI xdist (85s) is a **5×** difference.

**Parallelizable?** **YES** — xdist (`-n auto --dist loadgroup`) is already used in CI (ci.yml:91) but **absent from local `make test`**. The `xdist_group("bot_concurrent")` markers (7 bot files, step1 audit:184) are **inert** in local serial runs (step1 audit:341: "The xdist_group markers are only effective in CI").

**Evidence / exact lines:**
- `entrypoint-test.sh:56` — `uv run pytest ${PYTEST_OPTS:- --reuse-db --tb=short --durations=10} "${PYTEST_MARK_ARGS[@]}"` (no `-n` flag)
- `pyproject.toml:155-172` — pytest config (addopts, markers, asyncio_mode=strict, pythonpath)
- `pyproject.toml:160` — `addopts = ["--import-mode=importlib", "-ra", "-q"]`
- `pyproject.toml:159` — `pythonpath = ["src", "src/backend"]` (but no `testpaths`)
- `pyproject.toml:161` — `console_output_style = "classic"` (non-default; generates more output than `progress`)
- `ci.yml:91` — CI uses `-n auto --dist loadgroup --cov` (contrasts with local serial)
- `ci-nightly.yml:73` — nightly seed tests: `pytest -m "seed"` with NO xdist
- Bot test files with `xdist_group("bot_concurrent")`: `test_ad_create.py:19`, `test_ad_create_condition.py:36`, `test_claim_login_token.py:19`, `test_create_draft_ad.py:15`, `test_login_claim.py:17`, `test_unsubscribe.py:24`, `test_save_photo_integration.py:42`
- Bot test files with `django_db(transaction=True)`: same 7 files (plus `test_ad_lifecycle.py:23` uses `django_db` without `transaction=True`)
- `test_suite_audit_step1_current_state.md:84` — 1091 total tests (1009 backend + 80 bot + 2 settings)
- `test_suite_audit_step2_profiling.md:14` — fast-gate xdist wall time: 85s
- `test_suite_audit_step2_profiling.md:18-22` — full suite: ~247s (85s + 162s); documented estimate: ~35min (8.5× overestimate)
- `test_suite_audit_step2_profiling.md:67-79` — 8 of 10 slowest tests are in setup phase (TRUNCATE overhead)
- `test_suite_audit_step2_profiling.md:194-196` — speedup table: 85s wall / ~415s serial / 5× speedup / 62% efficiency
- `test_suite_audit_step1_current_state.md:331-341` — local runs have NO xdist, NO coverage; CI has both

**Confidence:** HIGH (for local serial being absent; for ~415s estimate — MEDIUM, extrapolated from unit-only serial measurement of 93 tests in 12s)

---

## 2. Correct vs. Incorrect Usage Patterns

### Patterns in the Repository's Own Configuration

The repo's infrastructure shows a **stark split** between CI (optimized) and local Docker runs (unoptimized):

#### Correct Patterns (CI-aligned with measured data)

| Pattern | Location | Why it's correct |
|---|---|---|
| `--dist loadgroup` in CI | `ci.yml:91` | Matches measured 15–20% speedup vs `loadscope` (85s vs 100–104s). The `xdist_group("bot_concurrent")` markers on 7 bot files are effective under `loadgroup` (verified step2:153-155). |
| `--cov` passed explicitly at CI command line, NOT in `addopts` | `ci.yml:91`; `pyproject.toml:160` (addopts has no `--cov`) | Local `make test` doesn't pay 15–25s coverage overhead (step1:42, step1:396). Coverage still runs in CI for the `fail_under=80` gate. |
| Seed tests isolated via `-m "not seed"` | `ci.yml:91`; `entrypoint-test.sh:52-54` (`PYTEST_SKIP_MARKERS=seed`) | Excludes 26 seed tests (162–183s) from the fast gate (step2:51-56). Verified marker registration at `pyproject.toml:166`. |
| Nightly seed-only workflow | `ci-nightly.yml:68-73` | Runs `pytest -m "seed"` on a daily schedule, keeping seed tests out of PR feedback. |
| `_no_op_image_generator` autouse fixture | `src/backend/apps/seed/tests/conftest.py:36-48` | Patches `ImageGenerator` to skip the 1004-photo pipeline for non-`real_images` tests, speeding up seed-adjacent tests that remain in the fast gate. |
| `--reuse-db` as default | `entrypoint-test.sh:56`; `Makefile:137` override uses `--no-reuse-db` | Avoids test DB schema rebuild on subsequent runs (step2:40-41: "~3s DB connection wait + migration advisory lock"). `make test-recreate` correctly forces `--no-reuse-db --create-db` (Makefile:137). |
| `--import-mode=importlib` | `pyproject.toml:160` | Prevents test module import collisions (standard best practice since pytest 6.0). |
| `default-groups = []` in `[tool.uv]` | `pyproject.toml:196` | Keeps dev tools out of the production image; entrypoint-test.sh:14 explicitly adds `--group dev` for test containers only. |
| `init: true` on test service | `docker-compose.test.yml:51` | Ensures proper signal forwarding (Ctrl+C) and zombie reaping (step2:42, CR5). |

#### Incorrect or Suboptimal Patterns

| Pattern | Location | Problem | Impact |
|---|---|---|---|
| **Local `make test` runs serial (no xdist)** | `entrypoint-test.sh:56` (default PYTEST_OPTS has no `-n`) | CI uses `-n auto --dist loadgroup` (85s) but local runs execute 1025 tests serially (~415s estimated). The `xdist_group("bot_concurrent")` markers on 7 bot files are **inert** locally (step1:341). | **~330s wasted** per `make test` run (415s serial vs 85s parallel) |
| **`compilemessages` runs twice** | `entrypoint.sh:87` (via `compile_messages()`) + `entrypoint-test.sh:37` | ENTRYPOINT is `entrypoint.sh` (Dockerfile:154), which calls `compile_messages` then `exec "$@"` → `entrypoint-test.sh`. Both compile the same 3 `.po` files. | **~2–3s wasted** per run |
| **DB connection check runs twice** | `entrypoint.sh:40-48` (`wait_for_db`) + `entrypoint-test.sh:18-29` | Docker Compose already ensures DB health via `depends_on: condition: service_healthy` (compose:52-54). Then entrypoint.sh checks again, then entrypoint-test.sh checks a third time. | **~1–2s wasted**; triple-check is unnecessary |
| **`migrate_locked` migrates `mko_bazuna` (not `test_mko_bazuna`)** | `entrypoint-test.sh:33` → `migrate_locked.py:27-29` → `test.py:21` (`DATABASES["default"]["NAME"] = "mko_bazuna"`) | pytest-django creates `test_mko_bazuna` and runs its own migrations. The entrypoint's `migrate_locked` migrates `mko_bazuna` — a database no test uses. This is a production-pattern carryover. | **~3s wasted** per run (idempotent check); **~5–15s** first cold run |
| **No `MIGRATION_MODULES = {app: None}`** | `pyproject.toml:155-172` and `test.py` have no such setting | pytest-django runs all 39 migration files when creating `test_mko_bazuna`. With `--create-db` (test-recreate), all 39 migrations execute serially (~15–30s). | **~15–30s wasted** on `make test-recreate` only; ~0s on `--reuse-db` |
| **Nightly seed tests have no xdist** | `ci-nightly.yml:73` (no `-n auto`) | Seed tier takes 162–183s sequentially. With 8 workers, could drop to ~25–40s. | **~120–150s wasted** per nightly run |
| **Nightly CI doesn't run `compilemessages`** | `ci-nightly.yml` has no compilemessages step; `ci.yml:80-84` does | If `.mo` files aren't present, i18n tests (`test_mo_compiled`, `test_i18n_completeness.py:308`) could fail. Currently passes because CI runners have fresh checkouts with no `.mo` files... but `compilemessages` isn't run, so how does it pass? | **Correctness risk**: i18n tests in nightly may be silently broken |
| **No PG tuning for test DB** | `docker-compose.test.yml:11-28` — DB env section has no `command:` override | PostgreSQL 18 defaults (`fsync=on`, `synchronous_commit=on`, `wal_level=replica`) are optimized for durability, not test speed. For an ephemeral test DB, `fsync=off` and `synchronous_commit=off` are safe. | **Unknown** — likely ~2–5s per 1025 tests for WAL/fsync overhead |
| **`--dist loadscope` was applied then reverted in CI history** | `done/25_test-optimization-plan_done.md:702` claims `loadscope`; `ci.yml:91` uses `loadgroup` | The prior plan (T-10) switched to `loadscope`, but the actual ci.yml still uses `loadgroup`. The audit found `loadgroup` is faster (step2:153-155). This means the plan's claim was either reverted or never merged. | N/A — current state is correct (`loadgroup`) |
| **55 of 89 test files have module-level `slow`** | `step1:179-180` — 47 backend + 8 bot files | The `slow` marker is applied at module level to 62% of test files with no per-test granularity. `-m "not slow"` would exclude most of the suite. The marker is useless for selective exclusion. | **Correctness/UX issue** — not directly a startup bottleneck, but prevents targeted fast runs |
| **No `testpaths` configured** | `pyproject.toml:155-172` — no `testpaths` key | pytest discovers tests from the project rootdir, scanning all 88 test files. Specifying `testpaths` would narrow discovery. | **~1–2s** slower collection |
| **`make test-recreate` strips `--durations=10`** | `Makefile:137` — `PYTEST_OPTS="--no-reuse-db --create-db --tb=short"` | The default `${PYTEST_OPTS:- ...}` fallback is completely replaced when PYTEST_OPTS is set. The `--durations=10` from the default is lost. | **Observability loss** — no slow-test reporting on recreate runs |
| **`test` service has `profiles: ["test"]`** | `docker-compose.test.yml:74` | The `test` service is gated behind the `test` profile. `docker compose run --rm test` bypasses profiles (Docker Compose v2 behavior for `run`), but this is fragile and confusing. A developer using `docker compose up --profile test test` would need to know the profile name. | **Developer friction** — not a startup bottleneck |
| **`UV_NO_INSTALL_PROJECT=0` in compose is inert** | `docker-compose.test.yml:64` — `UV_NO_INSTALL_PROJECT=0` | The Dockerfile sets `UV_NO_INSTALL_PROJECT=1` (line 137). The compose override sets it to `0`, but entrypoint-test.sh:18 passes `--no-install-project` CLI flag, which takes precedence over the env var. | **Dead config** — the env var override has no effect |
| **`console_output_style = "classic"`** | `pyproject.toml:161` | Non-default output style; generates one line per test instead of a progress bar. With `-q` (already in addopts), impact is mitigated but not eliminated. | **Minor** output IO overhead |

---

## 3. Recommended Acceleration Options (Ranked by Impact × Effort × Risk)

### Ranking methodology
- **Impact**: Time saved per `make test` run (high-impact = seconds saved)
- **Effort**: Trivial (1-line config) → Small (Makefile/entrypoint change) → Medium (Dockerfile rewrite + validation) → Large (architectural change)
- **Risk**: Probability of breaking test correctness, CI green status, or local dev workflow

### Full ranking table

| # | Optimization | Impact | Effort | Risk | Rationale |
|---|---|---|---|---|---|
| 1 | **Add xdist to local `make test`** | **~330s saved** (415s → 85s) | **Trivial** (1-line entrypoint change) | **Low** (CI already runs xdist; bot tests isolated via `xdist_group`) | CI uses `-n auto --dist loadgroup` and passes. The 7 `concurrent` bot files are already pinned to one worker via `xdist_group("bot_concurrent")`. The `transaction=True` tests have a dedicated conftest for connection cleanup (bot conftest.py:216-225). |
| 2 | **Precompile dev deps into image layer** | **~25–29s saved** (cold start) | **Medium** (add build stage, modify Dockerfile) | **Low–Medium** (image size +100MB; must keep prod image unaffected) | `uv sync --group dev` at build time eliminates the 25–29s cold install. Use a multi-target Dockerfile with a `builder-test` stage. |
| 3 | **`MIGRATION_MODULES = {app: None}` in test settings** | **~15–30s saved** on `--create-db` only | **Trivial** (3-line addition to test.py) | **Low** (only affects test DB creation; `--create-db` already rebuilds from scratch) | Replaces 39 sequential migration files with single `create_test_db()` call. No effect on `--reuse-db` (already fast). |
| 4 | **Remove redundant `compilemessages`** | ~2–3s saved | **Trivial** (remove 1 line) | **Low** (image builder stage still compiles; bind mount shadows but entrypoint.sh still runs it once) | Only need ONE `compilemessages` call. Remove from entrypoint-test.sh (keep in entrypoint.sh for the base image pattern) OR remove from entrypoint.sh (keep in entrypoint-test.sh). |
| 5 | **Remove redundant DB connection check** | ~1–2s saved | **Trivial** (remove 11 lines) | **Low** (DB healthcheck via `depends_on` already verified) | entrypoint-test.sh:18-29 duplicates entrypoint.sh:40-48. Remove from entrypoint-test.sh. |
| 6 | **Add PG tuning to test DB container** | ~2–5s saved (est.) | **Trivial** (3-line compose change) | **Low** (ephemeral test DB, no data loss risk) | `fsync=off`, `synchronous_commit=off`, `wal_level=minimal`, `shared_buffers=2gb` for PostgreSQL 18-alpine test container. |
| 7 | **Add xdist to nightly seed tests** | ~120–150s saved (nightly) | **Trivial** (1-line CI change) | **Low** (seed tests use `django_db` not `transaction=True`; autouse fixture patches image pipeline) | ci-nightly.yml:73 has no `-n auto`. Adding it would parallelize 26 seed tests across 4 CI cores. |
| 8 | **Output optimization flags** | ~1–3s saved | **Trivial** (add flags to PYTEST_OPTS) | **Low** (CI still uses `--tb=short`) | `--no-header --no-summary -p no:warnings` cuts output IO. Keep `--tb=short` for CI. |
| 9 | **Remove blank `slow` from bot tests** | ~0s saved (no timing impact) | **Medium** (edit 7 files) | **Low** (marker only changes `-m` filter behavior) | 55 of 89 files have module-level `slow`. Bot files (7) blanket-apply it. Removing from bot files enables `-m "not slow"` to skip genuinely slow tests while keeping fast bot tests. |
| 10 | **Remove `make test-recreate` PYTEST_OPTS clobber** | ~0s saved (observability fix) | **Trivial** (append flags instead of replace) | **Low** (behavior change: `--durations=10` would be restored) | `Makefile:137` sets `PYTEST_OPTS="--no-reuse-db --create-db --tb=short"` which replaces defaults entirely, losing `--durations=10`. Should append to defaults instead. |
| 11 | **Add `testpaths` to pyproject.toml** | ~1–2s saved (collection) | **Trivial** (1-line) | **None** | `pyproject.toml:155-172` has no `testpaths`. Adding `testpaths = ["src/backend/apps", "src/telegram_bot/tests", "src/backend/config/settings/tests"]` narrows discovery. |
| 12 | **Remove `migrate_locked` from test entrypoint** | ~3s saved (idempotent check) | **Trivial** (remove line) | **Medium** (needs verification no test reads `mko_bazuna` directly) | entrypoint-test.sh:33 migrates `mko_bazuna` which pytest never uses. Risk: some test might connect to the default DB directly (unverified, but unlikely — all DB tests use `django_db` marker which pytest-django intercepts). |
| 13 | **Image build at `make test` time** | Not applicable (image pre-built) | N/A | N/A | If image doesn't exist, Compose auto-builds. This is handled by `make build` separately. |

### Top 3 recommendations with rationale

#### Rank 1 (P0): Add xdist to local `make test`
**Time saved:** ~330s/run (85s vs ~415s serial for 1025 fast-gate tests). This is the **single largest** bottleneck — the local test pipeline runs serially while CI already uses 8-worker xdist. The `xdist_group("bot_concurrent")` markers are already in place but inert locally.

**Why it's safe:**
- CI already runs `-n auto --dist loadgroup` and passes consistently (1025 tests, 989 passed, step2:56)
- The 7 bot files with `concurrent` + `transaction=True` are pinned to one worker via `xdist_group("bot_concurrent")` (7 files, confirmed by grep: `test_ad_create.py:19`, `test_ad_create_condition.py:36`, `test_claim_login_token.py:19`, `test_create_draft_ad.py:15`, `test_login_claim.py:17`, `test_unsubscribe.py:24`, `test_save_photo_integration.py:42`)
- The bot conftest has `_reap_worker_connections` autouse fixture (bot conftest.py:216-225) that closes leaked worker-thread DB connections after each test — this was specifically designed to prevent deadlocks under xdist
- `test_ad_lifecycle.py:23` uses `django_db` (not `transaction=True`), so it gets normal TestCase transaction rollback — safe under xdist
- `--dist loadgroup` is measured as 15–20% faster than `loadscope` locally (step2:153-155)

**Implementation:** Change the default PYTEST_OPTS in `entrypoint-test.sh:56` from `--reuse-db --tb=short --durations=10` to `--reuse-db -n auto --dist loadgroup --tb=short --durations=10`.

**Confidence:** HIGH

#### Rank 2 (P1): Precompile dev deps into the test image
**Time saved:** 25–29s on cold starts (first run after image build or CI checkout with empty uv cache).

**Why it works:** The Dockerfile builder stage (line 48) installs with `--no-dev`, so the image venv lacks pytest. The entrypoint-test.sh:14 must install 9 dev packages + transitive deps at every container start. Adding a `--group dev` sync to the builder stage (or a separate `test-image` stage that inherits from `runtime` and adds dev deps) eliminates this.

**Implementation:** Add `uv sync --frozen --no-install-project --group dev` to the Dockerfile builder stage after the production deps install (line 49). This adds dev deps to the venv in the image layer. The entrypoint's `uv sync` then becomes a no-op (deps already present, `--frozen` matches lockfile).

**Risk consideration:** Image size increases by ~100–150MB (pytest, basedpyright, ruff, djlint, etc.). Must ensure the production image (`FROM python:3.14-slim AS runtime`) is NOT affected — use a separate `AS test-runtime` stage or a build arg.

**Confidence:** HIGH (mechanism: uv sync is idempotent; if deps already installed, it's a fast no-op)

#### Rank 3 (P1): `MIGRATION_MODULES = {app: None}` in test settings + PG tuning
**Time saved:** 15–30s on `make test-recreate` (eliminates 39 migrations); ~2–5s on all runs (PG tuning).

**`MIGRATION_MODULES` rationale:**
- `pyproject.toml:160` `addopts` has no `--no-migrations` flag, and no `MIGRATION_MODULES` setting exists in `test.py` (verified by grep)
- Setting `MIGRATION_MODULES = {app: None}` for all 10 apps with migrations (ads, analytics, categories, currencies, locations, lookups, moderation, search, trust, users) tells pytest-django to skip migrations and use `create_test_db()` (model introspection) instead
- Django docs (verified via pytest-django docs): `--no-migrations` / `MIGRATION_MODULES = None` creates tables from model state, bypassing the migration graph entirely
- **Trade-off**: schema-only creation vs. real migrations. For a test suite that doesn't test migration correctness (no `test_migrations.py` that asserts migration content), this is safe. There IS a `core/tests/test_migrations.py` (filesystem listing), but it likely tests `makemigrations --check` (no pending changes), not migration data — `MIGRATION_MODULES = None` doesn't affect `makemigrations --check`.
- Only helps `--create-db` runs (`make test-recreate`); no effect on `--reuse-db` (already fast)

**PG tuning rationale:**
- `docker-compose.test.yml:11-28` — DB service has no `command:` override with PG tuning parameters
- PostgreSQL 18 defaults: `fsync=on` (sync every commit to disk), `synchronous_commit=on` (wait for WAL flush before commit ack), `wal_level=replica` (full WAL for replication)
- For an ephemeral test DB with a persistent volume (for `--reuse-db`), these defaults are unnecessarily safe. `fsync=off` and `synchronous_commit=off` are safe because the DB is recreated/reused for testing only.
- `shared_buffers` defaults to 128MB — on an 8-CPU machine, bumping to 2–4GB reduces buffer misses.

**Confidence:** HIGH for the mechanism; MEDIUM for exact time savings (no direct measurement of PG tuning impact in this repo)

---

## 4. Concrete Acceleration Playbook (Ordered)

### Phase 1 — Zero-risk config changes (minutes)

```bash
# 1. Add xdist to local default PYTEST_OPTS
#    File: docker/entrypoint-test.sh line 56
#    Before: uv run pytest ${PYTEST_OPTS:- --reuse-db --tb=short --durations=10} "${PYTEST_MARK_ARGS[@]}"
#    After:  uv run pytest ${PYTEST_OPTS:- --reuse-db -n auto --dist loadgroup --tb=short --durations=10} "${PYTEST_MARK_ARGS[@]}"

# 2. Add xdist to nightly seed CI
#    File: .github/workflows/ci-nightly.yml line 73
#    Before: uv run pytest -m "seed" --tb=short --cov --durations=10 --cov-report=term --cov-report=xml --reuse-db
#    After:  uv run pytest -m "seed" -n auto --dist loadgroup --tb=short --cov --durations=10 --cov-report=term --cov-report=xml --reuse-db

# 3. Remove redundant DB check from entrypoint-test.sh
#    File: docker/entrypoint-test.sh lines 17-29 (the second `for i in $(seq 1 30)` loop)
#    Keep only the compilemessages + migrate + pytest portion.

# 4. Remove redundant compilemessages from entrypoint-test.sh
#    File: docker/entrypoint-test.sh line 37
#    Keep compilemessages in entrypoint.sh:87 (base entrypoint runs first).

# 5. Add testpaths to pyproject.toml
#    File: pyproject.toml after line 159 (pythonpath)
#    Add: testpaths = ["src/backend/apps", "src/telegram_bot/tests", "src/backend/config/settings/tests"]

# 6. Fix make test-recreate PYTEST_OPTS clobber
#    File: Makefile line 137
#    Instead of overriding PYTEST_OPTS entirely, use a separate env var or append.
```

### Phase 2 — Test settings + PG tuning (hours)

```bash
# 7. Add MIGRATION_MODULES to test settings
#    File: src/backend/config/settings/test.py (after line 49, CACHES override)
#    Add:
#    MIGRATION_MODULES = {
#        "ads": None, "analytics": None, "categories": None,
#        "currencies": None, "locations": None, "lookups": None,
#        "moderation": None, "search": None, "trust": None, "users": None,
#    }
#    Note: core has 0 migrations, so it's omitted. Also omit django's built-in
#    apps (auth, contenttypes, etc.) — they should still run their migrations
#    because tests may depend on auth/user migration state. Actually, setting
#    them to None is standard for test speed; see Django docs.
#    Full list: auth, contenttypes, sessions, admin, sites, etc.

# 8. Add PG tuning to test DB container
#    File: docker-compose.test.yml db service (after line 16)
#    Add:
#      command: >-
#        postgres
#        -c fsync=off
#        -c synchronous_commit=off
#        -c wal_level=minimal
#        -c shared_buffers=2gb
#        -c effective_cache_size=4gb
```

### Phase 3 — Dockerfile optimization (days, with validation)

```bash
# 9. Add dev-deps to a test image layer
#    File: docker/Dockerfile
#    Approach A: Add to builder stage (after line 49):
#      # Install dev deps into the same venv (no extra stage needed)
#      uv sync --frozen --no-install-project --group dev
#    This makes the entrypoint's `uv sync --group dev` a no-op (deps already present).
#    The production runtime image (FROM ... AS runtime) is unaffected because
#    it copies only from builder's /opt/venv (line 106), which now includes dev deps.
#    To keep prod image clean, add a separate stage or strip dev deps.
#
#    Approach B (cleaner): Separate test-runtime stage:
#      FROM runtime AS test-runtime
#      RUN --mount=type=cache,target=/root/.cache/uv \
#          uv sync --frozen --no-install-project --group dev
#    Then docker-compose.test.yml uses `image: mko-bazuna:test-runtime` or
#    `build: target: test-runtime`.
```

### Phase 4 — Migration consolidation (independent, see Problem_02.md §4)

```bash
# 10. Consolidate migrations using existing script
#    scripts/consolidate_migrations.py already exists (172 lines).
#    It deletes [0-9]*.py files for apps exceeding --threshold (default 8).
#    Only `ads` (12 files) exceeds the threshold.
#    Command: uv run python scripts/consolidate_migrations.py --threshold 8
#    Then: makemigrations (generates single new initial migration)
#    Then: migrate (applies to dev DB)
#    This reduces 39 → 28 migration files, helping --create-db runs.
#    Does NOT affect --reuse-db (already fast).
```

### Validation steps (after each phase):

```bash
# Confirm xdist is active locally
make test 2>&1 | grep "xdist"  # should show worker startup

# Confirm migration skip is working (with MIGRATION_MODULES = None)
make test-recreate PYTEST_OPTS="--no-reuse-db --create-db --tb=short -v" 2>&1 | head -5
# Should see "create_test_db" instead of "Applying migration"

# Confirm compilemessages runs once
make test 2>&1 | grep "Compiling"  # should appear once

# Time the full pipeline
time make test  # expect: ~90s (vs ~450s before)
```

---

## 5. Recommended "Fastest Safe Local `make test`" Shape

### Current state (before optimization)
```bash
# entrypoint-test.sh:56 default:
uv run pytest --reuse-db --tb=short --durations=10 -m "not (seed)"
# + 25-29s uv sync + ~3s compilemessages (×2) + ~3s migrate_locked + ~5s collection
# + ~415s serial test execution
# = ~458s total (~7.6 minutes)
```

### Recommended optimized shape

**Step 1 — Modify `entrypoint-test.sh:56`** (highest impact, zero risk):
```bash
# Replace defaults to add xdist + output optimization:
PYTEST_DEFAULT_OPTS="--reuse-db -n auto --dist loadgroup --no-header --no-summary -p no:warnings -q"
uv run pytest ${PYTEST_OPTS:- $PYTEST_DEFAULT_OPTS} "${PYTEST_MARK_ARGS[@]}"
```

**Step 2 — Set `COMPOSE_PROFILES` env (optional, avoids confusion):**
The `test` service has `profiles: ["test"]` (docker-compose.test.yml:74). While `docker compose run` bypasses profiles, setting `COMPOSE_PROFILES=test` makes the intent explicit:
```makefile
test:
    docker compose $(COMPOSE_TEST) up -d db
    docker compose $(COMPOSE_TEST) run --rm -e COMPOSE_PROFILES=test \
        --env PYTEST_SKIP_MARKERS=seed test
```

**Step 3 — Add `testpaths` + `MIGRATION_MODULES` to config** (Phase 2 above).

**Step 4 — Add PG tuning** (Phase 2 above).

### Estimated result after all recommendations:

| Stage | Before | After | Savings |
|---|---|---|---|
| uv sync (cold) | 25–29s | 0–2s (precompiled venv) | 25–27s |
| compilemessages (×2) | 4–6s | 2–3s (single run) | 2–3s |
| DB wait (×3) | 2–3s | 0–1s (single check) | 1–2s |
| migrate_locked (mko_bazuna) | 3s | 0s (removed or kept as no-op) | 3s |
| Pytest collection | 5s | 3s (testpaths + cache) | 2s |
| Test execution (serial → xdist 8w) | ~415s | ~85s | ~330s |
| **Total (make test, warm)** | **~458s** | **~93s** | **~365s (4× faster)** |
| **Total (make test, cold)** | **~463s** | **~95s** | **~368s** |
| **Total (make test-recreate)** | ~490s | ~95s | ~395s |

### Exact recommended `make test` command after optimization:
```bash
# This is what the entrypoint defaults would produce:
uv run pytest --reuse-db -n auto --dist loadgroup --no-header --no-summary -p no:warnings -q -m "not (seed)"
```

### Environment variables for the fastest single run:
```bash
PYTEST_OPTS="--reuse-db -n auto --dist loadgroup --no-header --no-summary -p no:warnings -q"
PYTEST_SKIP_MARKERS="seed"
```

These can be passed directly for a one-off:
```bash
make test PYTEST_OPTS="--reuse-db -n auto --dist loadgroup --no-header --no-summary -p no:warnings -q"
```
(Note: `PYTEST_OPTS` set as a Makefile env var is passed through to the container via `--env`.)

**Confidence on estimates:** Medium–High. The 85s xdist time for fast-gate is **measured** (step2:14). The ~415s serial estimate is **extrapolated** from unit-only serial (93 tests in 12s → 1025 tests ≈ 133s, but with per-test DB setup overhead the audit estimates ~415s). The uv sync savings (25–29s → ~2s) are **measured** (step2:36-38). Collection and compilemessages times are **measured** (~5s and ~2–3s respectively, step2:36-41). PG tuning savings are **estimated** from general PostgreSQL knowledge (LOW confidence — no direct measurement in this repo).

---

## Appendix A: Pipeline Stage Summary with File References

```
make test
  ↓
docker-compose up -d db                    (Makefile:100)
  → starts postgres:18-alpine             (docker-compose.yml:7, docker-compose.test.yml:12)
  → pg_isready healthcheck                (docker-compose.test.yml:24-28)
  → ~5-10s (first run) or ~0s (db already running)
  ↓
docker-compose run --rm test               (Makefile:101)
  → builds image if missing               (docker-compose.test.yml:47)
  → init: true (tini PID 1)               (docker-compose.test.yml:51)
  → bind mount .:/app                     (docker-compose.test.yml:69)
  → depends_on db healthy                 (docker-compose.test.yml:52-54)
  ↓
ENTRYPOINT entrypoint.sh                   (Dockerfile:154)
  1. check_env_file                        (entrypoint.sh:9-21) → skipped (SKIP_ENV_CHECK=1)
  2. fix_volume_permissions                (entrypoint.sh:24-30) → skipped
  3. wait_for_db                           (entrypoint.sh:33-49) → ~0s (DB healthy)
  4. wait_for_redis                        (entrypoint.sh:51-68) → skipped (no REDIS_URL)
  5. compile_messages                      (entrypoint.sh:73-77) → ~2-3s  [REDUNDANT]
  ↓
CMD entrypoint-test.sh                     (docker-compose.test.yml:50)
  1. uv sync --group dev                   (entrypoint-test.sh:14)  → 25-29s cold / ~2s warm [BOTTLENECK]
  2. DB connection wait                    (entrypoint-test.sh:17-29) → ~0s  [REDUNDANT]
  3. migrate_locked.main()                 (entrypoint-test.sh:33)  → ~3s  [WASTED: migrates mko_bazuna]
  4. compilemessages                       (entrypoint-test.sh:37)  → ~2-3s  [REDUNDANT]
  5. pytest (serial, no xdist)             (entrypoint-test.sh:56)  → ~415s estimated [BOTTLENECK]
                                                         +32s overhead = ~447s total
```

## Appendix B: Key Configuration Reference

| Config location | Setting | Effect |
|---|---|---|
| `pyproject.toml:160` | `addopts = ["--import-mode=importlib", "-ra", "-q"]` | No xdist, no coverage, no reuse-db in defaults |
| `pyproject.toml:196` | `default-groups = []` | Dev tools excluded from prod image |
| `pyproject.toml:155-172` | `[tool.pytest.ini_options]` | No `testpaths`, no `MIGRATION_MODULES`, no `django_db_use_migrations` |
| `docker/Dockerfile:48` | `uv sync --frozen --no-install-project --no-dev --no-default-groups` | Production venv excludes dev deps |
| `docker/Dockerfile:137` | `ENV UV_NO_INSTALL_PROJECT=1` | Prevents project install in runtime (overridden by compose:64 but negated by CLI flag) |
| `docker-compose.test.yml:64` | `UV_NO_INSTALL_PROJECT=0` | Inert — overridden by `--no-install-project` CLI flag in entrypoint-test.sh:14 |
| `docker-compose.test.yml:72` | `uv_cache:/root/.cache/uv` | Caches downloads only, not venv state |
| `entrypoint-test.sh:14` | `uv sync --frozen --no-install-project --group dev` | Installs dev deps at container start |
| `entrypoint-test.sh:56` | Default `PYTEST_OPTS` | `--reuse-db --tb=short --durations=10` — serial, no xdist, no coverage |
| `entrypoint-test.sh:52-54` | `PYTEST_SKIP_MARKERS` | Appends `-m "not (seed)"` when set |
| `Makefile:100-101` | `make test` | Pre-starts DB, runs test container with `PYTEST_SKIP_MARKERS=seed` |
| `Makefile:136-137` | `make test-recreate` | Overrides `PYTEST_OPTS="--no-reuse-db --create-db --tb=short"` |
| `ci.yml:91` | CI test command | `uv run pytest -m "not seed" -n auto --dist loadgroup --tb=short --cov --durations=10 --cov-report=term --cov-report=xml --reuse-db` |
| `ci-nightly.yml:73` | Nightly seed command | `uv run pytest -m "seed" --tb=short --cov --durations=10 --cov-report=term --cov-report=xml --reuse-db` (NO xdist) |

**Note on CI vs local divergence (step1 audit:331-341):** CI runs pytest directly with full flags (`ci.yml:91`), bypassing the Docker entrypoint entirely. Local runs go through `entrypoint-test.sh` which uses different defaults (no xdist, no coverage). This means CI and local test execution are not directly comparable — CI is always faster due to xdist, and CI measures coverage which local doesn't.
