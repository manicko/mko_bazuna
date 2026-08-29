---
id: pytest-xdist-db-management-report
domain: research
related:
  - docs/99-agent/architecture
  - docs/99-agent/rules
  - .ai/problems/active_findings_compiled.md
  - .ai/reports/fix_load_catalog_fixture_scope_report.md
tags:
  - pytest-xdist
  - pytest-django
  - test-database
  - reuse-db
  - create-db
  - loadgroup
  - loadscope
  - stale-db-cleanup
---

# Research Report: pytest-xdist Worker DB Management, Stale DB Cleanup, and `--dist loadgroup` vs `loadscope`

**Project:** Mko Bazuna  
**Date:** 2026-08-29  
**Stack:** Python 3.14 · Django 5.2 LTS · pytest-django 4.12.0 · pytest-xdist 3.8.0 · PostgreSQL 18  

---

## Executive Summary

1. **`--dist loadgroup` vs `loadscope`**: `loadgroup` groups tests by the `xdist_group` *marker* (explicit, user-defined); `loadscope` groups by *module/class* (automatic, location-based). The project correctly uses `loadgroup` because 6 bot test files pin all FSM-sharing tests to a single worker via `@pytest.mark.xdist_group("bot_concurrent")`.

2. **Per-worker `gw*` databases ARE created**: The project does NOT override `django_db_modify_db_settings`, so pytest-django's **default** per-worker database creation is active. Each xdist worker creates and reuses its own `test_mko_bazuna_gw0`, `test_mko_bazuna_gw1`, etc. The audit finding §8-rec-4's claim that "the current architecture uses a single shared DB" is **incorrect**.

3. **Stale `gw*` databases DO recur**: Under `--reuse-db` (the default), stale worker databases persist across runs, especially when worker count changes or runs are interrupted. The `gw*` suffix originates from pytest-xdist's worker naming convention (`gw0`, `gw1`, …), appended by pytest-django's `django_db_modify_db_settings_xdist_suffix` fixture.

4. **`--no-reuse-db --create-db` is not always sufficient**: While it should drop and recreate each worker's database, it can fail when connections from a crashed worker remain open (`DROP DATABASE` fails with "database is being accessed by other users"). A pre-flight `DROP DATABASE IF EXISTS` loop is recommended as defense-in-depth.

---

## 1. `--dist loadgroup` vs `loadscope` — Detailed Comparison

### Distribution Modes in pytest-xdist (v3.8.0)

| Mode | How tests are grouped | Granularity | When to use |
|---|---|---|---|
| `load` (default) | Sent to any available worker, no grouping | Individual test items | Homogeneous tests, no shared state |
| `loadscope` | By **module** (functions) or **class** (methods) | Module or class | Tests within a module/class share fixtures/resources |
| `loadfile` | By **file** | File | All tests in a file share a worker (stronger than loadscope) |
| `loadgroup` | By `xdist_group` **marker** (or `@pytest.mark.xdist_group`) | User-defined name | Tests with the same group name are pinned to one worker |
| `each` | All workers run all tests | Full suite | When you want every worker to execute the full suite |
| `worksteal` | Load-balancing with work stealing | Dynamic | High CPU contention scenarios |

### `loadgroup` — explicit, marker-driven grouping

```python
@pytest.mark.xdist_group("bot_concurrent")
def test_something(): ...
```

- Groups tests by the **explicit `xdist_group` marker name**.
- Tests with the same group name are **guaranteed** to run on the same worker.
- Tests without any `xdist_group` marker are treated as singletons (their own implicit group) — effectively behaving like `load` for those tests.
- Allows **cross-file** grouping (tests in different files can share a worker if they have the same group name).
- The pytest-xdist scheduler appends the group name(s) to the test nodeid as `@<names>`, and `_split_scope` parses the rightmost `@` to determine group membership.

### `loadscope` — automatic, location-based grouping

- Groups tests by **module** (for standalone functions) or **class** (for methods).
- Class grouping takes priority over module grouping.
- All tests in the same `test_foo.py` file run on the same worker (file-level granularity).
- All methods in the same `TestBar` class run on the same worker.
- Does **not** allow cross-file grouping — tests in different files always go to different workers (unless they happen to land on the same worker by load balancing).

### Why this project chose `loadgroup`

**Evidence from source code:**

The project has 6 bot test files, all marked with `@pytest.mark.xdist_group("bot_concurrent")`:

| File | Line | Marker |
|---|---|---|
| `test_create_draft_ad.py` | 15 | `pytestmark.append(pytest.mark.xdist_group("bot_concurrent"))` |
| `test_create_ad.py` | 18-19 | `pytestmark = [...]; pytestmark.append(pytest.mark.xdist_group("bot_concurrent"))` |
| `test_ad_create_condition.py` | 34-36 | same pattern |
| `test_save_photo_integration.py` | 40-42 | same pattern |
| `test_login.py` | 33-35 | same pattern |
| `test_unsubscribe.py` | 22-24 | same pattern |

These tests use `pytest.mark.django_db(transaction=True)` (registered as `concurrent` marker in `pyproject.toml:168`) and rely on `MemoryStorage` (in-process aiogram FSM storage, `conftest.py:48`). Pinning all bot tests to a single worker via `loadgroup` ensures:

- FSM state from `MemoryStorage` is not shared across workers (each worker has its own in-process storage, which is correct — but the test suite also uses `xdist_group("bot_concurrent")` to ensure tests that modify shared DB state via `TRUNCATE ... CASCADE` don't deadlock with each other across workers).
- The `_reap_worker_connections` autouse fixture in `src/telegram_bot/tests/conftest.py:216-225` (which tracks thread-local connections via `connection_created` signal) doesn't need to coordinate across workers.

`loadscope` **cannot** express this requirement — it would distribute bot tests across workers based on file/module boundaries, breaking the intentional pinning.

### When `loadscope` would be preferred

- When tests within the same module/class share a slow-to-construct fixture and you want to minimize fixture setup overhead by keeping them together.
- When you don't want to annotate tests with markers but still want some grouping.
- When the grouping is naturally aligned with the module/class structure.

---

## 2. Per-Worker `gw*` Database Creation — Verification

### The Default Behavior (Confirmed)

**pytest-django documentation** (`docs/usage.md`):

> "When running tests with `pytest-xdist`, pytest-django automatically creates a separate test database for each process, appending a suffix like 'gw0', 'gw1' to the database name."

**pytest-django documentation** (`docs/database.md`, "Examples > Use the same database for all xdist processes"):

> "By default, each xdist process uses its own database to prevent test interference. If you require all xdist processes to share the same database, you can override the `django_db_modify_db_settings` fixture in `conftest.py` to do nothing, effectively disabling the per-process database modification."

### The `gw*` Suffix Mechanism

The suffix originates from **pytest-xdist's worker naming convention**:
- Workers are named `gw0`, `gw1`, `gw2`, … (confirmed via `worker_id` fixture and `PYTEST_XDIST_WORKER` environment variable in pytest-xdist docs).
- pytest-django's `django_db_modify_db_settings_xdist_suffix` fixture (one of the suffixed variants: `parallel_suffix`, `tox_suffix`, `xdist_suffix`) checks if xdist is active and appends the worker ID to the `DATABASES["default"]["NAME"]` setting.
- The test settings set `DATABASES["default"]["NAME"] = "mko_bazuna"` (`test.py:21`), so pytest-django creates `test_mko_bazuna_gw0`, `test_mko_bazuna_gw1`, etc.

### Project Verification: The Override Is NOT Present

A grep across the entire `src/` tree for `django_db_modify_db_settings` returns **0 matches**. The project's only test DB-related fixtures are:

- `src/backend/conftest.py:40-55` — `_restore_test_schema_post_db_setup(django_db_setup, django_db_blocker)` — runs `load_exchange_rates` and `setup_search_triggers` after DB creation. Does **not** override the DB name or disable per-worker suffixes.
- `src/telegram_bot/tests/conftest.py` — no DB name override; only connection-tracking fixtures.
- `src/backend/apps/currencies/tests/conftest.py` — not checked but unlikely to contain the override.

**Conclusion**: The project uses pytest-django's **default** per-worker database behavior. Each xdist worker creates and reuses its own `test_mko_bazuna_gw*`.

### Audit Finding §8-rec-4 Is Incorrect

The audit finding (`.ai/problems/active_findings_compiled.md:78`) claims:

> "The current architecture uses `--dist loadgroup` against a single shared `test_mko_bazuna` DB — it does not create per-worker `gw*` databases."

This is **false**. The evidence contradicts it:
1. No `django_db_modify_db_settings` override exists (grep: 0 matches).
2. pytest-django docs explicitly state per-worker DBs are created by default.
3. The 16 stale `gw*` databases observed in `fix_load_catalog_fixture_scope_report.md:132` were produced by the **current** configuration (xdist with default per-worker DB), not a "prior (different) parallel-DB configuration."

The finding's justification (b) — "they do not recur under the current setup" — is incorrect. The stale `gw*` databases **do** recur.

---

## 3. `--reuse-db` Lifecycle and Stale DB Accumulation

### How `--reuse-db` Works with xdist

When `--reuse-db` is active (the entrypoint default and CI default):
1. Each worker checks if its own `test_mko_bazuna_gwN` database exists.
2. If it exists, pytest-django skips creation and runs `migrate` to apply any unrecorded migrations (fast — checks `django_migrations` table).
3. If it does not exist, pytest-django creates it from scratch.

This means **stale `gw*` databases persist** across runs when the DB container uses a persistent named volume (`mko-bazuna-test_postgres_data` in `docker-compose.test.yml:7-11`).

### When Stale `gw*` Databases Accumulate

| Scenario | Effect |
|---|---|
| Worker count changes between runs | `-n auto` uses CPU count. Moving from a 4-core to 8-core machine creates `gw4`-`gw7` fresh, but stale `gw0`-`gw3` from the previous run remain. If the next run uses 4 workers again, `gw4`-`gw7` become stale. |
| Run is interrupted (SIGKILL/Ctrl+C) | The crashed worker's `test_mko_bazuna_gwN` database is left in a potentially corrupt or half-migrated state. `--reuse-db` will try to reuse it, potentially hitting errors. |
| Schema drift | If migrations change but `--reuse-db` is used, the DB has an outdated schema. `--create-db` is needed to pick up changes. |

### `--no-reuse-db --create-db` Behavior with xdist

- `--no-reuse-db` tells pytest-django to **drop** the test database before creating it.
- `--create-db` tells pytest-django to **create** the test database from scratch.
- Together, each worker drops and recreates its own `test_mko_bazuna_gwN` database.
- **Problem**: If a previous worker crashed and left connections open, `DROP DATABASE` fails with `ERROR: database "test_mko_bazuna_gw0" is being accessed by other users`. pytest-django does not handle this gracefully — it may fall back to reusing the stale database or raise an error.
- **Solution**: Pre-flight `DROP DATABASE IF EXISTS` from the controller process (before workers spawn) terminates connections and drops databases cleanly via `DROP DATABASE ... WITH (FORCE)` or by terminating backends first.

### CI Environment (Ephemeral)

- CI runs on `ubuntu-latest` with a fresh Postgres service container.
- Each CI run starts with a clean database — no stale databases persist across runs.
- `--reuse-db` in CI speeds up single-run execution (avoids schema rebuild at the start).
- The `--reuse-db` flag is safe in CI because the environment is ephemeral.

### Local Docker (Persistent Volume)

- `docker-compose.test.yml` mounts `postgres_data` volume (inherited from base `docker-compose.yml`).
- The volume persists when `docker compose down` is called (without `-v`).
- Stale `gw*` databases accumulate across `make test` runs.
- `make test-recreate` uses `--no-reuse-db --create-db` which should handle this, but may fail on stuck connections.

---

## 4. The `gw*` Naming Convention: Origin and Mechanism

| Component | Source | Role |
|---|---|---|
| `gwN` worker names | pytest-xdist | Workers are named `gw0`, `gw1`, `gw2`, … |
| `worker_id` fixture | pytest-xdist | Returns `gwN` for workers, `master` for controller |
| `PYTEST_XDIST_WORKER` | pytest-xdist | Environment variable set in each worker process |
| `django_db_modify_db_settings_xdist_suffix` | pytest-django | Checks if xdist is active, appends `worker_id` to DB name |
| `test_mko_bazuna_gwN` | pytest-django | Final test database name per worker |

The `gw*` suffix does **not** come from PostgreSQL, Django's test runner, or the project's configuration — it is entirely a pytest-xdist + pytest-django collaboration.

### Verification: `django_db_modify_db_settings_xdist_suffix`

From pytest-django source (documented in `docs/database.md`):
- `django_db_modify_db_settings_xdist_suffix` is a **session-scoped** fixture provided by pytest-django.
- It calls `get_xdist_worker_id(request)` (from pytest-xdist's plugin API) to get the worker ID.
- If not running under xdist (returns `"master"`), it does nothing.
- If running under xdist (returns `gwN`), it appends `_gwN` to the database NAME setting.
- This fixture is invoked by the umbrella `django_db_modify_db_settings` fixture, which is called during `django_db_setup` (session-scoped).

To share a single DB across workers, you must override `django_db_modify_db_settings` to be a no-op:

```python
@pytest.fixture(scope="session")
def django_db_modify_db_settings():
    pass
```

The project does NOT do this — confirmed by grep (0 matches for `django_db_modify_db_settings` in `src/`).

---

## 5. Stale DB Cleanup Best Practices

### 5.1 Pre-flight `DROP DATABASE IF EXISTS` (Recommended for Local Dev)

A pre-flight cleanup script that runs **before** pytest starts, from the host/controller process, is the most reliable approach:

```bash
# Inside the test container, before pytest runs:
psql -U postgres -d postgres -c "
  DO \$\$
  DECLARE
    r RECORD;
  BEGIN
    FOR r IN
      SELECT datname FROM pg_database
      WHERE datname LIKE 'test_mko_bazuna%'
    LOOP
      EXECUTE 'DROP DATABASE IF EXISTS ' || quote_ident(r.datname) || ' WITH (FORCE)';
    END LOOP;
  END \$\$;
"
```

**Why `WITH (FORCE)`?** PostgreSQL's `DROP DATABASE ... WITH (FORCE)` (PG13+) terminates existing connections before dropping, avoiding the "database is being accessed by other users" error. This is available in the project's PostgreSQL 18.

### 5.2 `--no-reuse-db --create-db` (Sufficient for Most Cases)

pytest-django's `--no-reuse-db --create-db` drops and recreates each worker's database. This works when:
- No connections are stuck from a previous crashed worker.
- The worker count has not changed (each worker drops its own DB).

**Limitation**: When a worker crashes, its connections may persist, causing `DROP DATABASE` to fail. pytest-django may then fall back to reusing the stale database or raise an error.

### 5.3 `docker compose down -v` (Nuclear Option)

Wipes the entire named volume, destroying all databases. Use when:
- The DB volume is thoroughly corrupted.
- A complete environment reset is needed.

The project has `make clean` (Makefile:229-231) which runs `docker compose down -v`, but this is marked "Nuclear: remove containers, volumes, and local DB backups."

### 5.4 CI Strategy

| Environment | Strategy | Rationale |
|---|---|---|
| CI (ephemeral) | `--reuse-db` only | Each run starts fresh; no stale DBs; reuse speeds up single-run execution |
| Nightly CI (seed) | `--reuse-db`, no xdist | Serial execution (seed tests have shared state); ephemeral environment |
| Local dev (persistent) | `--reuse-db` + periodic `DROP DATABASE` | Speed for iteration; pre-flight cleanup before `test-recreate` |
| Local dev (after schema changes) | `--no-reuse-db --create-db` + pre-flight DROP | Ensures clean schema; pre-flight handles stuck connections |

---

## 6. Recommendations for This Project

### 6.1 Add Pre-flight `DROP DATABASE IF EXISTS` to `make test-recreate` and `make clean`

**Confidence: HIGH** — stale `gw*` databases are created by the default pytest-django behavior (no override exists), and `--no-reuse-db --create-db` can fail on stuck connections.

**Implementation** (Makefile `test-recreate` target, Makefile:137-139):

```makefile
test-recreate:
	docker compose $(COMPOSE_TEST) up -d db
	# Drop stale test databases (including xdist gw* shards) before recreating.
	# Done pre-flight so stuck connections from a crashed worker don't block
	# pytest-django's internal DROP DATABASE.
	docker compose $(COMPOSE_TEST) exec db psql -U postgres -d postgres -c \
		"SELECT format('DROP DATABASE IF EXISTS %I WITH (FORCE);', datname) \
		 FROM pg_database WHERE datname LIKE 'test_mko_bazuna%'" \
		| docker compose $(COMPOSE_TEST) exec -T db psql -U postgres -d postgres
	docker compose $(COMPOSE_TEST) run --rm --env PYTEST_OPTS="--no-reuse-db --create-db --tb=short -n auto --dist loadgroup" test
```

**Alternatively**, a more robust approach using a psql loop:

```makefile
test-recreate:
	docker compose $(COMPOSE_TEST) up -d db
	@docker compose $(COMPOSE_TEST) exec -T db psql -U postgres -d mko_bazuna -c \
		"DO \$\$ BEGIN PERFORM pg_terminate_backend(pid) FROM pg_stat_activity \
		 WHERE datname LIKE 'test_mko_bazuna%' AND pid <> pg_backend_pid(); \
		 FOR r IN SELECT datname FROM pg_database WHERE datname LIKE 'test_mko_bazuna%' LOOP \
		 EXECUTE 'DROP DATABASE IF EXISTS ' || quote_ident(r.datname) || ' WITH (FORCE)'; \
		 END LOOP; END \$\$"
	docker compose $(COMPOSE_TEST) run --rm --env PYTEST_OPTS="--no-reuse-db --create-db --tb=short -n auto --dist loadgroup" test
```

**Apply the same to `Makefile.ps1`** (`Invoke-TestRecreate`, line 118-121).

### 6.2 Add a Dedicated `test-clean-db` Target

A standalone target for cleaning stale test databases without running tests:

```makefile
# Drop stale test databases (test_mko_bazuna + test_mko_bazuna_gw*).
test-clean-db:
	docker compose $(COMPOSE_TEST) up -d db
	docker compose $(COMPOSE_TEST) exec -T db psql -U postgres -d postgres -c \
		"DO \$\$ BEGIN \
			PERFORM pg_terminate_backend(pid) FROM pg_stat_activity \
			 WHERE datname LIKE 'test_mko_bazuna%' AND pid <> pg_backend_pid(); \
			FOR r IN SELECT datname FROM pg_database WHERE datname LIKE 'test_mko_bazuna%' LOOP \
				EXECUTE 'DROP DATABASE IF EXISTS ' || quote_ident(r.datname) || ' WITH (FORCE)'; \
			END LOOP; \
		END \$\$"
```

### 6.3 CI Workflow — No Change Needed

The CI workflow (`.github/workflows/ci.yml:91`) uses `--reuse-db` on an ephemeral environment. This is correct:
- Each CI run starts with a fresh Postgres service container.
- `--reuse-db` speeds up the single run (avoids schema rebuild at the start).
- No stale databases accumulate because the environment is destroyed after each run.

The nightly CI (`ci-nightly.yml:73`) runs seed tests serially (`no -n`/xdist) with `--reuse-db`, which is also correct — seed tests likely have shared state that shouldn't be distributed across workers.

### 6.4 Re-evaluate the `prepare_threshold: None` Setting (§8-rec-3)

The audit finding §8-rec-3 (`.ai/problems/active_findings_compiled.md:43-50`) notes that `prepare_threshold: None` in `base.py:160,173` is set for "PgBouncer async safety" but there is **no PgBouncer** in the deployment (grep for `pgbouncer|PgBouncer|pooler` → 0 matches in `docker-compose.yml`). The report's attribution of the `[BAD]` connection issue to `prepare_threshold` is incorrect (the root cause was the class-scoped `transaction.atomic()` firing before `django_db_setup`, fixed by the `django_db_setup: None` dependency in `test_breadcrumbs_render.py`).

**Recommendation**: Remove `"prepare_threshold": None` and the misleading "PgBouncer async safety" comments, since:
- No PgBouncer/transaction pooler is in the deployment topology.
- Without a transaction pooler, server-side prepared statements are safe and provide performance benefits.
- `prepare_threshold: None` disables an optimization with no corresponding benefit.

### 6.5 Consider `MIGRATION_MODULES = DisableMigrations()` Impact on `--create-db` (Already Implemented)

The project's `test.py:70-76` already implements `DisableMigrations`, which makes pytest-django use `create_test_db()` (model introspection) instead of replaying migration files. This is already correct and helps `--create-db` runs. No action needed.

### 6.6 Audit Finding §8-rec-4 Reclassification

The audit finding §8-rec-4 should be reclassified from "LOW — non-recurring under current design" to "RELEVANT-OPEN — actively recurring under current design" because:
- The project does NOT override `django_db_modify_db_settings` (confirmed by grep).
- pytest-django creates per-worker `gw*` databases by default.
- Stale `gw*` databases accumulate under `--reuse-db` with persistent volumes.
- The fix (pre-flight `DROP DATABASE IF EXISTS`) is small and provides defense-in-depth.

---

## 7. Confidence Levels

| Finding | Confidence | Evidence Source |
|---|---|---|
| `loadgroup` groups by `xdist_group` marker | HIGH | pytest-xdist docs (distribution.md), source code analysis |
| `loadscope` groups by module/class | HIGH | pytest-xdist docs (distribution.md) |
| Project uses `loadgroup` for bot FSM tests | HIGH | Source: 6 test files with `xdist_group("bot_concurrent")` |
| pytest-django creates per-worker `gw*` DBs by default | HIGH | pytest-django docs (usage.md, database.md) |
| Project does NOT override `django_db_modify_db_settings` | HIGH | Grep: 0 matches across `src/` |
| `gw*` suffix comes from pytest-xdist worker naming | HIGH | pytest-xdist docs (how-to.md, plugin-api), pytest-django source |
| `--reuse-db` reuses per-worker `gw*` databases | HIGH | pytest-django docs (database.md), inferred from architecture |
| `--no-reuse-db --create-db` can fail on stuck connections | HIGH | PostgreSQL `DROP DATABASE` semantics, well-documented behavior |
| `prepare_threshold: None` is unnecessary without PgBouncer | HIGH | Grep: 0 matches for PgBouncer in docker-compose.yml |
| Audit §8-rec-4 justification (b) is incorrect | HIGH | Source: no `django_db_modify_db_settings` override exists |

---

## 8. Source References

| Source | Relevance |
|---|---|
| pytest-xdist docs (`docs/distribution.md`) | Distribution modes: load, loadscope, loadfile, loadgroup, each, worksteal |
| pytest-xdist docs (`docs/how-to.md`) | `worker_id` fixture, `testrun_uid`, worker naming (`gw0`, `gw1`) |
| pytest-xdist plugin API (`_autodocs/001-plugin-api.md`) | `get_xdist_worker_id()`, `PYTEST_XDIST_WORKER` env var |
| pytest-django docs (`docs/usage.md`) | Per-worker DB creation with xdist ("gw0, gw1") |
| pytest-django docs (`docs/database.md`) | `--reuse-db`, `--create-db`, `django_db_modify_db_settings_xdist_suffix`, "share DB" override pattern |
| `pyproject.toml:163-172` | Registered markers: `unit, integration, seed, settings, concurrent, slow, real_images, xdist_group` |
| `docker/entrypoint-test.sh:41` | Default PYTEST_OPTS: `--reuse-db --tb=short --durations=10 -n auto --dist loadgroup` |
| `Makefile:137-139` | `test-recreate`: `--no-reuse-db --create-db --tb=short -n auto --dist loadgroup` |
| `.github/workflows/ci.yml:91` | CI: `--reuse-db -n auto --dist loadgroup` (ephemeral env, correct) |
| `.github/workflows/ci-nightly.yml:73` | Nightly: `--reuse-db`, no xdist (serial, correct for shared-state seeds) |
| `docker-compose.test.yml:7-11` | Test DB uses persistent `postgres_data` volume (enables stale DB accumulation) |
| `config/settings/test.py:21` | `DATABASES["default"]["NAME"] = "mko_bazuna"` (base name for `test_mko_bazuna_gw*`) |
| `src/backend/conftest.py:40-55` | `_restore_test_schema_post_db_setup` — does NOT override DB name |
| `src/telegram_bot/tests/conftest.py:48` | `MemoryStorage()` — in-process FSM storage per worker |
| `src/telegram_bot/tests/*.py` (6 files) | All use `xdist_group("bot_concurrent")` — justifies `loadgroup` |
| `config/settings/base.py:160,172-173` | `prepare_threshold: None` (§8-rec-3 — unnecessary without PgBouncer) |
| `.ai/problems/active_findings_compiled.md:72-79` | Audit finding §8-rec-4 (incorrect justification) |
| `.ai/reports/fix_load_catalog_fixture_scope_report.md:132` | Document of 16 stale `gw*` databases (not a historical artifact) |
