---
id: 13-test-env-acceleration-plan
domain: plan
tags:
  - test-infrastructure
  - docker
  - migrations
  - performance
  - ci
related:
  - 13_test-env-acceleration_spec
  - migration_squash_plan
  - test_env_acceleration_report
  - test_suite_audit_step1_current_state
  - test_suite_audit_step2_profiling
  - docker-one-shot-lifecycle-analysis
---

# Implementation Plan 13 — Test-Environment Acceleration & Migration Squashing

> Transforms `13_test-env-acceleration_spec.md` into dependency-aware, independently-executable task specs.
>
> **Spec-vs-reality reconciliation:** The spec was written against an earlier codebase snapshot. On-disk analysis (this writing, 2026-08-27) found several assertions in the spec that no longer hold. These are reconciled in §2 (Findings vs Spec). Where the spec is **correct**, its requirements (R1–R10) are preserved. Where the spec is **stale**, the task list below reflects the actual code state.

---

## 1. Overview

| Dimension | Current state | Target state |
|---|---|---|
| Local `make test` parallelism | **Already has xdist** (`-n auto --dist loadgroup`) in `entrypoint-test.sh:59` | xdist confirmed everywhere; sync `Makefile.ps1` |
| Fresh-DB schema-build cost | 39 migration files replay on `--create-db` (15–30 s) | 10 squashed initials + optional `MIGRATION_MODULES=None` (near-zero) |
| Per-container fixed overhead | ~28–32 s (`uv sync` cold 25–29 s + double `compilemessages` ~4–6 s + redundant DB check ~2 s + wasted `migrate_locked` Pass A ~3 s) | `<2 s` warm cache; `compilemessages` once; DB check once; Pass A removed |
| Migration count (dev/test) | 39 files / 10 apps | 10 files (one `0001_initial` per app) |
| Hand-written DDL preserved | `RunSQL` trigger functions + `RunPython` seed in migrations | Extracted to `setup_search_triggers` + `load_exchange_rates` commands, wired into all entrypoints |
| FileNotFoundError cluster | **Confirmed present** in `_step3_unit.txt` (25 errors — template path resolution) | Tests resolve template paths deterministically |
| Currency test flakiness | **Confirmed present** in `_step3_fg.txt` (`test_rsd_normalized_by_seeded_rate` FAILED) | Seed rates guaranteed in test DB |

---

## 2. Findings vs Spec (reconciliation)

The spec contains several claims that, on 2026-08-27 disk analysis, are **no longer accurate**. Each is annotated with the correct state and the task that addresses the gap.

| Spec § | Spec claim | Actual on-disk state | Action |
|---|---|---|---|
| §4.1 | "entrypoint-test.sh (line 56) do **not** [use xdist]" | `entrypoint-test.sh:59` **already** contains `-n auto --dist loadgroup` in the default `PYTEST_OPTS` | **No action.** Spec §5.2 ranking #2 is stale; local xdist parity is **already achieved**. |
| §4.2 | "local agent runs do not use xdist" | `Makefile test-recreate:139` **already** passes `-n auto --dist loadgroup` | **No action.** But `Makefile.ps1 Invoke-TestRecreate:120` does NOT — see task T2b. |
| §4.2 | "Fast-gate wall time 85 s" / "Full suite ~247 s" | Confirmed. But §4.2 line 176 ("not the ~35 min still printed") is correct; however `Makefile.ps1` help text line 48 still says "~55s vs ~35min" — the overestimate persists in the help text. | Task T6 (docs/fix help text). |
| §5.2 Stage 5 | "wasted `migrate_locked` Pass A" — migrates `mko_bazuna` not `test_mko_bazuna` | Confirmed: `test.py:21` sets `DATABASES["default"]["NAME"] = "mko_bazuna"`; pytest-django creates `test_mko_bazuna`. `migrate_locked.main()` in `entrypoint-test.sh:33` migrates the wrong DB. | Task T1c (remove Pass A from entrypoint-test.sh). |
| §4.3 §5.2 | "25 `FileNotFoundError` errors and flaky currency tests" | **Confirmed present** — `_step3_unit.txt` shows 25+ FileNotFoundError in template-path tests (`Path("src/backend/templates/...").resolve()` resolves to `/app/src/backend/src/backend/...`); `_step3_fg.txt:54` shows `test_rsd_normalized_by_seeded_rate` FAILED. | Task T3. |
| §4.3 table | "users: yes (0002 backfill) chat_id null backfill" | `users/0002_alter_user_telegram_id_null.py` is a **plain `AlterField`** — no `RunPython`, no backfill. Spec's own research study (§5.4) confirms this. | No action needed; spec §4.3 is stale, research §5.4 is correct. |
| §4.3 table | "categories: yes (0002_createcategories seed?)" | `categories/0002_categorylistingcondition.py` is a `CreateModel` — no seed, no `RunPython`. | No action needed. |
| §8 recommendations | "Add PG tuning (`fsync=off`, etc.)" | `docker-compose.test.yml` db service **already** has `fsync=off`, `synchronous_commit=off`, `wal_level=minimal` (lines 24–31). Spec §8 Rank 6 / §9 option #8 are stale. | **No action.** Already done. |
| §9 Rank 1 | "precompile dev venv into image layer" | `entrypoint-test.sh:14` still runs `uv sync --group dev` cold every container start; the image venv is built with `--no-dev` (`Dockerfile:48`). | Task T1a (cached dev venv). |
| §9 Rank 3 | "Adopt `--dist loadgroup` over `loadscope`" | Already `loadgroup` in entrypoint-test.sh:59. | No action. |
| §14.1 step 0a | `scripts/consolidate_migrations.py --inventory` | The script has `--force`/`--threshold`/`--dry-run`/`--apps-dir` only. **No `--inventory` flag exists.** | Task T4a (add `--inventory` to consolidate_migrations.py). |
| §14.1 step 2b | `manage.py squash_rehydrate_runsql` | No such command exists on disk. The Phase-0 rehydration must be done by a command that injects the extracted RunSQL. | Task T4b (create `squash_rehydrate_runsql.py` management command). |
| §5.4 R6 | "management commands that must be extracted" | `backfill_translations.py` **exists** (`ads/management/commands/backfill_translations.py`). `load_exchange_rates.py` and `setup_search_triggers.py` **do not exist** — must be created. | Tasks T4c (create both commands). |
| §13 disposition | "currencies exchange rate seed extracted to `load_exchange_rates`" | Command doesn't exist yet. | Task T4c. |

**Migration file count (authoritative):** 39 numbered files across 10 model apps (verified by glob). `core` has 0; `api`/`cabinet`/`media`/`seed` have no `migrations/` dir.

---

## 3. Task Decomposition

### Task Dependency Graph

```
T1a ──┐
T1b ──┤
T1c ──┼── T5 (verification)
      │
T2a ──┤   (independent)
T2b ──┤
      │
T3 ───┤   (independent — investigation first)
      │
T4a ──┐
T4b ──┤
T4c ──┤
T4d ──┤
T4e ──┤
T4f ──┼── T4g (squash execution)
      │      │
      │      └──── T5 (verification)
      │
T6 ───┘   (docs, independent)
T7 ───┘   (docs, independent)

Key:
T1x = Environment startup cache + cleanup
T2x = Local xdist parity (Makefile.ps1 sync)
T3   = Fast-gate determinism (FileNotFoundError + currency)
T4a–T4g = Migration squash pipeline
T5   = End-to-end verification gate
T6   = Command-pattern standard + stale docs
T7   = Help-text / docs staleness
```

---

### T1 — Environment Startup Cache (R1)

**Priority:** High · **Risk:** Low · **Domain:** Docker build

#### T1a — Precompile dev deps into test image layer
- **File:** `docker/Dockerfile`
- **Action:** Add a `AS test-runtime` stage (after the `runtime` stage) that inherits from `runtime` and runs `uv sync --frozen --no-install-project --group dev` with `UV_COMPILE_BYTECODE=1`. Update `docker-compose.test.yml` test service to build with `target: test-runtime`.
- **Constraint:** Production image (`runtime` stage) must remain `--no-dev`. Dev deps live only in the test-runtime target.
- **Verification:** `entrypoint-test.sh:14` `uv sync` completes in `<2 s` on warm cache (down from 25–29 s cold). `make test-db` + one `make test` succeeds.
- **blocked_by:** none

#### T1b — Remove redundant `compilemessages` (R1)
- **Files:** `docker/entrypoint-test.sh` (line 37), `docker/entrypoint.sh` (lines 73–77)
- **Action:** `entrypoint.sh` runs `compile_messages()` as part of the base ENTRYPOINT. `entrypoint-test.sh` (called as CMD argument) runs it again at line 37. Remove the duplicate at `entrypoint-test.sh:37`. Keep the one in `entrypoint.sh:73` (base image pattern; bind-mount shadows image `.mo` anyway, but one compile is sufficient).
- **Verification:** `make test` log shows `Compiling` appearing **once** (not twice).
- **blocked_by:** none

#### T1c — Remove redundant DB check + wasted `migrate_locked` Pass A (R1, §5.2 Stage 5)
- **Files:** `docker/entrypoint-test.sh` (lines 17–29 DB check; line 33 `migrate_locked`)
- **Action:**
  1. Remove the DB connection check block (lines 17–29) — `docker-compose.test.yml` `depends_on: db: condition: service_healthy` already guarantees DB readiness; `entrypoint.sh:40-48` already checks once.
  2. Remove the `migrate_locked.main()` call (line 33) — it migrates `mko_bazuna` (per `test.py:21`), but pytest-django creates and migrates `test_mko_bazuna` independently. This is pure wasted work in the test path.
- **Risk gate:** Verify no test connects to the `mko_bazuna` database directly (not `test_mko_bazuna`). Grep for `mko_bazuna` in tests excludes `test.py:21` (settings) and `DATABASE_URL` env (compose). All DB tests use the `django_db` marker (pytest-django intercepts).
- **Verification:** `make test` starts without the `migrate_locked` step; pytest-django creates `test_mko_bazuna` from `--reuse-db` cache or `--create-db`. `test_migrations.py` (TST-005) still passes (it runs in-process via `call_command`).
- **blocked_by:** none

---

### T2 — Local xdist Parity (R2)

**Priority:** High · **Risk:** Low · **Domain:** Test runner configuration

#### T2a — Verify xdist is already in entrypoint-test.sh default (CONFIRMED)
- **File:** `docker/entrypoint-test.sh:59`
- **Status:** **Already done.** The default `PYTEST_OPTS` on line 59 includes `-n auto --dist loadgroup`. The spec's claim (§4.1, §5.2) that local runs lack xdist is **stale** — a prior agent already added this.
- **No action required.** This task is a confirmation gate only.

#### T2b — Sync `Makefile.ps1` `Invoke-TestRecreate` to match Makefile parity
- **File:** `Makefile.ps1` (line 120)
- **Action:** `Invoke-TestRecreate` currently passes `PYTEST_OPTS="--no-reuse-db --create-db --tb=short"` (no xdist). Add `-n auto --dist loadgroup` to match `Makefile:139`:
  ```
  Before: --env "PYTEST_OPTS=--no-reuse-db --create-db --tb=short"
  After:  --env "PYTEST_OPTS=--no-reuse-db --create-db --tb=short -n auto --dist loadgroup"
  ```
- **Verification:** `Invoke-TestRecreate` passes xdist flags to pytest; `make test-recreate` (Makefile) and `.\Makefile.ps1 test-recreate` (PowerShell) produce equivalent parallelization.
- **blocked_by:** T2a (confirmation)

---

### T3 — Fast-Gate Determinism (R3)

**Priority:** Medium · **Risk:** Medium · **Domain:** Test harness

#### T3a — Investigate & resolve template `FileNotFoundError` cluster
- **Evidence:** `_step3_unit.txt` shows 25+ `FileNotFoundError` errors from `Path("src/backend/templates/...").resolve()` resolving to `/app/src/backend/src/backend/templates/...` (double `src/backend` prefix).
- **Root-cause hypothesis:** Tests use relative `Path("src/backend/templates/...")` which resolves against CWD. Inside the container (`WORKDIR=/app`), this should resolve to `/app/src/backend/templates/...`. The double-prefix suggests CWD was `/app/src/backend` during the run, OR the `pythonpath = ["src", "src/backend"]` in `pyproject.toml:159` causes `src/backend` to be prepended.
- **Action:**
  1. Identify all test files using `Path("src/backend/templates/...")` (grep results: `test_autocomplete_template.py:30,96`, `test_detail_context.py:164`).
  2. Fix path resolution to use `Path(__file__).resolve().parents[N]` anchored or `django.template.loaders` lookup instead of filesystem path.
- **Verification:** `make test` exits 0 with no `FileNotFoundError` errors in the fast gate.
- **blocked_by:** none (investigation → fix)

#### T3b — Resolve currency seed-rate dependency flakiness
- **Evidence:** `_step3_fg.txt:54` — `FAILED apps/currencies/tests/test_price_normalizer.py::TestPriceNormalizer::test_rsd_normalized_by_seeded_rate`
- **Root cause:** `test_price_normalizer.py` asserts BAM (0.512) and RSD (0.0105) rates with no fixture creating them — they come from `currencies/0001_initial.py` `seed_initial_rates` RunPython. If the migration seed isn't applied (e.g., under `--create-db` without full migrate, or `MIGRATION_MODULES=None`), these tests fail.
- **Action:**
  1. Add an autouse fixture in `src/backend/conftest.py` or `apps/currencies/tests/conftest.py` that ensures `ExchangeRate` rows exist for EUR/BAM/RSD before any currency test runs.
  2. OR: if `MIGRATION_MODULES=None` is adopted (T4e Phase 0), wire `load_exchange_rates` into the test bootstrap.
- **Verification:** `test_price_normalizer.py` passes consistently across `--reuse-db` and `--no-reuse-db --create-db` runs.
- **blocked_by:** T4e (if skip-migration is adopted, this fixture must be wired together)

---

### T4 — Migration Squash Pipeline (R4–R9)

**Priority:** High · **Risk:** Medium · **Domain:** Migrations

#### T4a — Add `--inventory` flag to `consolidate_migrations.py`
- **File:** `scripts/consolidate_migrations.py`
- **Action:** Add an `--inventory` / `-i` flag that scans the pre-squash migration graph and emits a manifest of every non-auto-generated operation: `RunSQL`, `RunPython`, `SeparateDatabaseAndState`, and `AddIndex` with `concurrent=True`. Output to stdout and optionally `--inventory-output <file>`.
- **Purpose:** Phase 0 (§14.1) requires cataloging hand-written ops *before* the wipe. The spec calls `consolidate_migrations.py --inventory` but the flag doesn't exist.
- **Verification:** `uv run python scripts/consolidate_migrations.py --inventory` prints a manifest of all 18 hand-written ops (13 RunSQL + 5 RunPython) across 5 files (ads/0010, ads/0006, ads/0007, currencies/0001, search/0003–0005) with idempotent-classification.
- **blocked_by:** none

#### T4b — Create `squash_rehydrate_runsql` management command
- **File:** `src/backend/apps/core/management/commands/squash_rehydrate_runsql.py` (new)
- **Action:** A management command that, after `makemigrations` regenerates the squashed `0001_initial` files, injects the extracted `RunSQL` trigger/function DDL back into the appropriate app's new `0001_initial`. 
- **Source of truth:** The `ads_search_vector_fn` function (final i18n version from `ads/0007`), `categories_name_propagate` function, and both triggers (`ads_search_vector_update`, `on_category_name_update`) — copied verbatim from the pre-squash migrations with idempotent guards (`CREATE OR REPLACE FUNCTION`, `DROP TRIGGER IF EXISTS`).
- **Verification:** After squash, `manage.py migrate` on a fresh DB creates the trigger functions and triggers; FTS queries on `Ad` return results.
- **blocked_by:** T4a (needs the inventory manifest)

#### T4c — Create `setup_search_triggers` + `load_exchange_rates` management commands
- **Files:**
  - `src/backend/apps/ads/management/commands/setup_search_triggers.py` (new)
  - `src/backend/apps/currencies/management/commands/load_exchange_rates.py` (new)
- **Action:**
  - `setup_search_triggers.py`: Contains the final i18n `ads_search_vector_fn` function DDL (from `ads/0007:12-46`), the `categories_name_propagate` function (from `ads/0002:127`/`0006:77`), and both trigger definitions. Idempotent via `CREATE OR REPLACE FUNCTION` + `DROP TRIGGER IF EXISTS` + `CREATE TRIGGER`.
  - `load_exchange_rates.py`: Replicates `seed_initial_rates` from `currencies/0001:6-28` using live `ExchangeRate` model (not `apps.get_model`), idempotent via `update_or_create`.
- **Verification:** Both commands run without error on a fresh DB; `ExchangeRate` rows exist after `load_exchange_rates`; trigger functions exist after `setup_search_triggers`.
- **blocked_by:** none

#### T4d — Wire extracted commands into entrypoints (R6)
- **Files:** `docker/entrypoint-test.sh`, `docker-compose.yml` (migrate one-shot), `docker/entrypoint.sh`
- **Action:** After `migrate` (or schema creation), run:
  1. `manage.py setup_search_triggers`
  2. `manage.py load_exchange_rates`
  3. `manage.py load_catalog --no-rewrite` (already wired via `load_catalog` one-shot in compose)
  4. `manage.py seed` (already wired via `seed` one-shot in compose)
- **Test entrypoint:** Add steps to `entrypoint-test.sh` after the (now-removed) `migrate_locked` call, before `pytest`.
- **Dev/Prod entrypoint:** Add a `load_catalog` one-shot sibling or extend the `migrate` one-shot to call these commands post-migration.
- **Verification:** `entrypoint-test.sh` runs all three commands before pytest; no currency/FTS test failures.
- **blocked_by:** T4c (commands must exist), T1c (if Pass A removal changes entrypoint ordering)

#### T4e — Add `MIGRATION_MODULES = {app: None}` to test settings (§9 Option B)
- **File:** `src/backend/config/settings/test.py`
- **Action:** Add `MIGRATION_MODULES` setting disabling migrations for all 10 model apps, so pytest-django builds schema via `create_test_db()` (model introspection) instead of replaying migration files. This eliminates the 15–30 s `--create-db` migrate cost.
- **Constraint:** Must be combined with T4d — `setup_search_triggers` + `load_exchange_rates` must run **after** pytest-django creates the test DB (via an autouse fixture or entrypoint step) to restore the 4 trigger/function DDL objects and 3 seed rows that `MIGRATION_MODULES=None` skips.
- **Verification:** V1–V4 gates (§15): `makemigrations --check` clean, `migrate` idempotent, fresh-DB bootstrap works, existing-DB reconcile works.
- **blocked_by:** T4c, T4d (extracted commands must be wired for parity)

#### T4f — Take schema baseline (`pg_dump --schema-only`) for parity verification
- **Action:** Before squashing, run `pg_dump --schema-only` on the current 39-migration schema to capture: table definitions, indexes, constraints, trigger functions, triggers, sequences. Save to `.ai/artifacts/pre-squash-schema.sql`.
- **Purpose:** After squash, compare the squashed schema against this baseline to verify no DDL was lost (V1/V3 parity gates).
- **Verification:** Baseline file exists and is non-empty (≥200 tables/indexes/triggers).
- **blocked_by:** none

#### T4g — Execute the squash (§14.1 Fresh-DB path)
- **Action:** Execute the automated squash procedure:
  1. Run `T4a` inventory (`consolidate_migrations.py --inventory`)
  2. Authored T4b (`squash_rehydrate_runsql`) + T4c commands — already done
  3. Run `consolidate_migrations.py --force` (wipes all `0*.py` files)
  4. Run `makemigrations` (generates 10 `0001_initial.py`)
  5. Run `T4b` rehydration (injects trigger RunSQL into new `ads/0001_initial`)
  6. On fresh DB: `migrate` → `setup_search_triggers` → `load_exchange_rates` → `load_catalog` → `seed`
  7. `makemigrations --check --dry-run` (V1)
  8. `migrate --noinput` twice (V2 idempotency)
- **Note:** This task performs the actual destructive operation. It must be executed **after** T4a–T4f are complete and a git branch is created.
- **Verification:** V1–V7 gates pass (§15). `make test-recreate` builds from 10 files. `test_migrations.py` green.
- **blocked_by:** T4a, T4b, T4c, T4d, T4e, T4f

---

### T5 — End-to-End Verification Gate (R5, §15)

**Priority:** High · **Risk:** Low · **Domain:** Verification

- **Action:** Run the full V1–V7 verification matrix from spec §15:

| Check | Command | Pass criterion |
|---|---|---|
| V1 drift | `manage.py makemigrations --check --dry-run` | exit 0, "No changes detected" |
| V2 idempotency | `manage.py migrate --noinput` (×2) | 2nd run: "No migrations to apply." |
| V3 fresh-DB | `make test-recreate` (fresh volume) | migrate exits 0 from 10 `0001_initial` files |
| V4 existing-DB | dev `migrate --fake` after squash | `django_migrations` lists 10 initials; `migrate` no-op thereafter |
| V5 regression | `make test` (fast gate) + `make test-all` | all previously-green tests stay green |
| V6 CI parity | `ci.yml` test job | `-m "not seed" -n auto --dist loadgroup` exits 0 |
| V7 speed | `make test` (warm cache + xdist) | fast gate ≤ 90 s (Q3 default) |

- **blocked_by:** T1a, T1b, T1c, T3a, T3b, T4a–T4g

---

### T6 — Command-Pattern Standard + Stale Docs (§8, §20)

**Priority:** Low · **Risk:** Low · **Domain:** Documentation

- **Files:** `.ai/commands/` (new), `docs/ops/migration-workflow.md`, `AGENTS.md`
- **Action:**
  1. Create `.ai/commands/test-command-patterns.md` — the §8 table (correct/incorrect command shapes) as a one-page reference.
  2. Add a `make test` wrapper target that prints the canonical command (e.g., `make test` with a comment showing the equivalent direct `pytest` invocation).
  3. Update `docs/ops/migration-workflow.md` §"Reference: App Migration Status" to reflect actual counts (ads=12, search=7, users=6, total=39, not 36/ads=10).
- **Verification:** Reference doc exists at `.ai/commands/test-command-patterns.md`; stale counts corrected in `migration-workflow.md`.
- **blocked_by:** none

#### T6a — Fix `Makefile.ps1` help-text staleness
- **File:** `Makefile.ps1` line 48
- **Action:** Update help text from "~55s vs ~35min" to "~90s vs ~35min" (reflecting actual measured full-suite time ~247 s ≈ 4.1 min per `test_suite_audit_step2_profiling.md`, not 35 min).
- **Verification:** `.\Makefile.ps1 help` shows updated timing.
- **blocked_by:** none

---

## 4. Task Specifications (execution-ready)

### T1a: Precompile dev deps into test image layer

**Source:** Spec §9 Rank 1; env-acceleration report §3.1.

**file:** `docker/Dockerfile`

**semantic_anchor:**
```yaml
anchor_type: "dockerfile_stage"
anchor_name: "runtime"  # FROM python:3.14-slim AS runtime (line 84)
```

**changes:**
```yaml
- action: "add_docker_stage"
  description: |
    Add AS test-runtime stage after the runtime stage that inherits
    the production venv and adds dev dependencies with bytecode precompilation.
  code_hint: |
    FROM runtime AS test-runtime
    ENV UV_NO_INSTALL_PROJECT=1
    RUN --mount=type=cache,target=/root/.cache/uv \
        uv sync --frozen --no-install-project --group dev

# Then update docker-compose.test.yml test service build:
#   build:
#     context: .
#     dockerfile: docker/Dockerfile
#     target: test-runtime
```

**acceptance_criteria:**
- Production `runtime` stage unchanged (`--no-dev --no-default-groups`)
- Test image target `test-runtime` includes dev deps
- `entrypoint-test.sh:14` `uv sync --group dev` completes in `<2 s` warm

**verification:**
```bash
docker compose $(COMPOSE_TEST) build
# entrypoint-test.sh uv sync line should print "Audited..." with 0 installs
```

**blocked_by:** []
**risk:** Low (dev/test image layer only; prod image unchanged)

---

### T1b: Remove redundant compilemessages

**file:** `docker/entrypoint-test.sh`

**semantic_anchor:**
```yaml
anchor_type: "script_block"
anchor_name: "entrypoint-test.sh:37"  # the second compilemessages call
```

**changes:**
```yaml
- action: "delete_line"
  description: Remove the compilemessages invocation from entrypoint-test.sh
  target: "entrypoint-test.sh"
  line_range: "# 37 (echo + command)"
```

**acceptance_criteria:** `compilemessages` appears once in entrypoint-test.sh execution

**verification:**
```bash
make test 2>&1 | grep -c "Compiling"
# should output: 1
```

**blocked_by:** []
**risk:** Low

---

### T1c: Remove redundant DB check + wasted migrate_locked Pass A

**file:** `docker/entrypoint-test.sh`

**semantic_anchor:**
```yaml
anchor_type: "script_block"
anchor_lines: "entrypoint-test.sh:17-29 (DB check); entrypoint-test.sh:33 (migrate_locked)"
```

**changes:**
```yaml
- action: "delete_block"
  description: |
    Remove the DB connection wait loop (lines 17-29) — already guaranteed by
    docker-compose depends_on:condition=service_healthy + entrypoint.sh wait_for_db.
    Remove migrate_locked.main() call (line 33) — migrates mko_bazuna, not test_mko_bazuna.
  target: "entrypoint-test.sh"
```

**acceptance_criteria:**
- entrypoint-test.sh no longer contains `for i in $(seq 1 30)` DB loop
- entrypoint-test.sh no longer calls `migrate_locked.main()`
- pytest-django creates/migrates `test_mko_bazuna` independently
- TST-005 tests still pass (they use `call_command` in-process)

**verification:**
```bash
make test 2>&1 | grep -E "migrate_locked|Waiting for PostgreSQL"
# should return nothing (no output from entrypoint)
# test_migrations.py still runs and passes
```

**blocked_by:** []
**risk:** Medium (must verify no test depends on `mko_bazuna` DB state)

---

### T3a: Resolve template FileNotFoundError cluster

**file:** `src/backend/apps/search/tests/test_autocomplete_template.py`,
          `src/backend/apps/ads/tests/test_detail_context.py`

**semantic_anchor:**
```yaml
anchor_type: "test_file_path_resolver"
anchor_name: "test_autocomplete_template.py:30,96"
```

**changes:**
```yaml
- action: "fix_path_resolution"
  description: |
    Replace Path("src/backend/templates/...").resolve() with
    absolute paths derived from settings.TEMPLATES[0]["DIRS"] or
    Path(__file__).resolve().parents to avoid CWD-dependent resolution.
```

**acceptance_criteria:** No `FileNotFoundError` in `make test` output

**verification:**
```bash
make test PYTEST_SKIP_MARKERS="seed" 2>&1 | grep "FileNotFoundError"
# should return nothing
```

**blocked_by:** []
**risk:** Low (test-only fix)

---

### T3b: Resolve currency seed-rate flakiness

**file:** `src/backend/apps/currencies/tests/test_price_normalizer.py`,
          `src/backend/conftest.py` (or `apps/currencies/tests/conftest.py`)

**semantic_anchor:**
```yaml
anchor_type: "test_fixture"
anchor_name: "conftest.py:canonical_fixtures"
```

**changes:**
```yaml
- action: "add_autouse_fixture"
  description: |
    Add autouse fixture in currencies conftest.py that ensures
    EUR/BAM/RSD ExchangeRate rows exist (using live model, not apps.get_model)
    before any currency test runs. Idempotent.
```

**acceptance_criteria:** `test_price_normalizer.py` passes under both `--reuse-db` and `--no-reuse-db --create-db`

**verification:**
```bash
make test-recreate PYTEST_OPTS="--no-reuse-db --create-db -k test_price_normalizer -v"
# If MIGRATION_MODULES=None adopted: load_exchange_rates runs via fixture or entrypoint
```

**blocked_by:** [T4e]  # if skip-migration is adopted, fixture must be wired
**risk:** Low

---

### T4a: Add `--inventory` flag to consolidate_migrations.py

**file:** `scripts/consolidate_migrations.py`

**semantic_anchor:**
```yaml
anchor_type: "function_argument_parser"
anchor_name: "_parse_args"
```

**changes:**
```yaml
- action: "add_argument"
  description: |
    Add --inventory flag that scans migration files and emits a manifest of
    non-auto-generated operations: RunSQL, RunPython, SeparateDatabaseAndState,
    AddIndex with concurrent=True. Classifies idempotency and external-call risk.
  parameter: "--inventory"
  type: "store_true"
```

**acceptance_criteria:** `python scripts/consolidate_migrations.py --inventory` outputs manifest of 18 hand-written ops

**verification:**
```bash
uv run python scripts/consolidate_migrations.py --inventory
# Expect: 13 RunSQL, 5 RunPython, 1 SeparateDatabaseAndState listed with idempotent classification
```

**blocked_by:** []
**risk:** Low

---

### T4b: Create squash_rehydrate_runsql command

**file:** `src/backend/apps/core/management/commands/squash_rehydrate_runsql.py` (new)

**semantic_anchor:**
```yaml
anchor_type: "new_command"
anchor_name: "squash_rehydrate_runsql"
```

**changes:**
```yaml
- action: "create_command"
  description: |
    Management command that injects the ads FTS trigger function DDL
    (final i18n version from ads/0007) into the new squashed 0001_initial
    as explicit RunSQL with IF NOT EXISTS / CREATE OR REPLACE guards.
```

**acceptance_criteria:** Command reads source DDL from known migration locations and injects idempotent RunSQL

**verification:**
```bash
uv run python src/backend/manage.py squash_rehydrate_runsql --dry-run
# Shows SQL that would be injected
```

**blocked_by:** [T4a]
**risk:** Medium

---

### T4c: Create setup_search_triggers + load_exchange_rates commands

**files:**
- `src/backend/apps/ads/management/commands/setup_search_triggers.py` (new)
- `src/backend/apps/currencies/management/commands/load_exchange_rates.py` (new)

**semantic_anchor:**
```yaml
anchor_type: "management_command"
anchor_name: "setup_search_triggers; load_exchange_rates"
```

**changes:**
```yaml
- action: "create_command"
  description: |
    setup_search_triggers: CREATE OR REPLACE FUNCTION ads_search_vector_fn (final i18n),
    categories_name_propagate; DROP TRIGGER IF EXISTS + CREATE TRIGGER for
    ads_search_vector_update and on_category_name_update.
    load_exchange_rates: upsert 3 ExchangeRate rows (EUR=1.0, BAM=0.512, RSD=0.0105)
    using live model, idempotent via update_or_create.
```

**acceptance_criteria:**
- Both commands run without error on fresh DB
- ExchangeRate rows present after load_exchange_rates
- Trigger functions present after setup_search_triggers

**verification:**
```bash
uv run python src/backend/manage.py load_exchange_rates
psql -c "SELECT currency, rate_to_eur FROM exchange_rates WHERE source='manual_seed'"
uv run python src/backend/manage.py setup_search_triggers
psql -c "SELECT tgname FROM pg_trigger WHERE tgname LIKE '%search_vector%'"
```

**blocked_by:** []
**risk:** Medium

---

### T4d: Wire extracted commands into entrypoints

**files:** `docker/entrypoint-test.sh`, `docker-compose.yml` (migrate one-shot)

**semantic_anchor:**
```yaml
anchor_type: "entrypoint_step"
anchor_name: "entrypoint-test.sh:post-migrate"
```

**changes:**
```yaml
- action: "add_command_calls"
  description: |
    After migrate (or schema creation), run:
    1. manage.py setup_search_triggers
    2. manage.py load_exchange_rates
    3. manage.py load_catalog --no-rewrite (already wired in compose)
    4. manage.py seed (already wired in compose)
```

**acceptance_criteria:**
- entrypoint-test.sh runs all 4 commands before pytest
- compose migrate one-shot runs setup_search_triggers + load_exchange_rates

**verification:**
```bash
make test 2>&1 | grep -E "setup_search_triggers|load_exchange_rates"
# Both should appear in entrypoint output
```

**blocked_by:** [T4c, T1c]
**risk:** Low (idempotent commands)

---

### T4e: Add MIGRATION_MODULES = {app: None} to test settings

**file:** `src/backend/config/settings/test.py`

**semantic_anchor:**
```yaml
anchor_type: "class_attribute"
anchor_name: "test.py:settings_module"
```

**changes:**
```yaml
- action: "add_setting"
  description: |
    Add MIGRATION_MODULES = {None: app_list} for all 10 model apps to
    skip migration replay on --create-db. Requires T4d to restore
    trigger DDL + seed data via management commands.
  code_hint: |
    MIGRATION_MODULES = {
        "ads": None, "analytics": None, "categories": None,
        "currencies": None, "locations": None, "lookups": None,
        "moderation": None, "search": None, "trust": None, "users": None,
    }
```

**acceptance_criteria:**
- `make test-recreate` builds schema in `<5 s` (down from 15–30 s)
- All tests pass (triggers + seed rates restored by T4d commands)

**verification:**
```bash
make test-recreate 2>&1 | grep -E "Applying migration|create_test_db"
# Should show create_test_db, not Applying migration
make test  # full fast gate must pass
```

**blocked_by:** [T4c, T4d]
**risk:** Medium–High (must prove schema parity — see §5 of migration_squash_plan)

---

### T4f: Take schema baseline

**action:** Run `pg_dump --schema-only` on current DB, save to `.ai/artifacts/pre-squash-schema.sql`

**verification:**
```bash
pg_dump -s -U postgres -h localhost -p 5433 mko_bazuna > .ai/artifacts/pre-squash-schema.sql
wc -l .ai/artifacts/pre-squash-schema.sql
# Should be >1000 lines (tables + indexes + triggers + functions)
```

**blocked_by:** []
**risk:** None

---

### T4g: Execute the squash

**action:** Run the Phase 0 — Phase 5 squeeze procedure from spec §14.1:
1. `consolidate_migrations.py --inventory` (T4a output)
2. Verify setup_search_triggers + load_exchange_rates exist (T4c)
3. `consolidate_migrations.py --force` (wipe)
4. `makemigrations` (regenerate 10 initials)
5. `squash_rehydrate_runsql` (inject trigger DDL — T4b)
6. `migrate --fake` (existing DB) or `migrate` (fresh DB) + `setup_search_triggers` + `load_exchange_rates` + `load_catalog` + `seed`
7. `makemigrations --check --dry-run` (V1)
8. `migrate --noinput` ×2 (V2)

**verification:** V1–V7 gates pass; 39 files → 10 files

**blocked_by:** [T4a, T4b, T4c, T4d, T4e, T4f]
**risk:** High (destructive; must run on a git branch with baseline saved)

---

### T2b: Sync Makefile.ps1 test-recreate to xdist parity

**file:** `Makefile.ps1` (line 120)

**semantic_anchor:**
```yaml
anchor_type: "function_parameter"
anchor_name: "Invoke-TestRecreate:120"
```

**changes:**
```yaml
- action: "edit_env_value"
  old_value: "PYTEST_OPTS=--no-reuse-db --create-db --tb=short"
  new_value: "PYTEST_OPTS=--no-reuse-db --create-db --tb=short -n auto --dist loadgroup"
```

**acceptance_criteria:** PowerShell `test-recreate` passes same xdist flags as Makefile

**verification:**
```powershell
.\Makefile.ps1 test-recreate
# pytest output should show "xdist: n" workers active
```

**blocked_by:** [T2a]
**risk:** Low

---

### T6a: Fix Makefile.ps1 help-text staleness

**file:** `Makefile.ps1` (line 48)

**changes:**
```yaml
- old_value: "~55s vs ~35min"
  new_value: "~90s vs ~35min"
```

**blocked_by:** []
**risk:** None

---

### T6b: Command-pattern reference doc + stale docs fix

**files:**
- `.ai/commands/test-command-patterns.md` (new)
- `docs/ops/migration-workflow.md` (§"Reference: App Migration Status")

**changes:**
- Create one-page reference from spec §8
- Correct stale migration counts (ads=12, search=7, users=6, total=39)

**blocked_by:** []
**risk:** None

---

## 5. Verification Strategy

### 5.1 Verification Tasks

| Task | Type | Command | Gates |
|---|---|---|---|
| T1a-verification | inline | `make test` startup log shows `<2 s` for `uv sync` | entrypoint-test.sh:14 |
| T1b-verification | inline | `make test 2>&1 \| grep -c Compiling` → `1` | entrypoint-test.sh |
| T1c-verification | inline | `make test` no `migrate_locked` / `Waiting for PostgreSQL` output; TST-005 passes | entrypoint-test.sh, test_migrations.py |
| T3a-verification | inline | `make test 2>&1 \| grep FileNotFoundError` → empty | test_autocomplete_template.py, test_detail_context.py |
| T3b-verification | inline | `make test-recreate -k test_price_normalizer` passes under both reuse-db and create-db | test_price_normalizer.py |
| T4a-verification | inline | `consolidate_migrations.py --inventory` lists 18 ops | consolidate_migrations.py |
| T4c-verification | inline | `manage.py load_exchange_rates` + `manage.py setup_search_triggers` succeed | psql confirmation |
| T4d-verification | inline | entrypoint-test.sh shows command output before pytest | entrypoint-test.sh |
| T4e-verification | inline | `make test-recreate` shows `create_test_db` not `Applying migration`; tests pass | test.py |
| T4g-verification | gate | V1–V7 matrix from spec §15 | test_migrations.py |
| T5 (full gate) | verification | Full V1–V7 matrix | test_migrations.py, make test, make test-recreate |

### 5.2 Risk Gates

| Risk | Mitigation | Task |
|---|---|---|
| Squash loses trigger DDL | T4a inventory + T4b rehydration + T4f baseline diff | T4a, T4b, T4f, T4g |
| `--fake` masks divergence | V3 fresh-DB gate (no `--fake`) | T4g |
| `MIGRATION_MODULES=None` loses triggers/seed | T4d wiring required; T4e blocked by T4c/T4d | T4c, T4d, T4e |
| xdist exposes ordering bugs | T5 full-suite V5 | T5 |
| Path fix breaks other tests | T3a run full fast gate | T3a |

---

## 6. Execution Order (dependency-respecting)

### Phase 1 — Environment cleanup (parallelizable)
```
T1a ──┐
T1b ──┤── T5
T1c ──┤
      │
T2a ──┤  (confirm already done)
T2b ──┤── T5
      │
T6a ──┘  (docs/help text, independent)
T6b ──┘  (docs, independent)
```

### Phase 2 — Fast-gate determinism (after Phase 1, before squash)
```
T3a ──┐
T3b ──┤── T5
      │
```

### Phase 3 — Migration squash pipeline (sequential, destructive)
```
T4f (baseline) ──┐
                 │
T4a (inventory) ─┼── T4b (rehydration command)
                 │         │
T4c (extract cmd)──────────┼── T4d (wire entrypoints)
                 │         │        │
                 └─────────┴────────┴── T4e (MIGRATION_MODULES)
                                      │
                                      └──── T4g (execute squash)
                                             │
                                             └──── T5 (full gate)
```

**Rationale:** Phase 3 is sequential because each step mutates the migration graph or entrypoint wiring. T4a (inventory) must run before T4b (rehydration) knows what to inject. T4c (commands) must exist before T4d (wiring) can reference them. T4e (skip-migration) depends on T4d (triggers/seed wired) for parity. T4g (actual wipe+regen) is the culminating destructive step.

---

## 7. Appendix A: Authoritative Migration Inventory (39 files)

Verified on disk via glob `src/backend/apps/*/migrations/0*.py`:

| App | Files | RunPython | RunSQL | Notes |
|---|---|---|---|---|
| ads | 12 | 1 (0010: backfill_price_fields, no-op on fresh) | 13 (0002:×4, 0006:×3, 0007:×3, 0008:×3) | FTS trigger functions + GIN indexes; 0008 has 3 `CREATE INDEX CONCURRENTLY` |
| analytics | 4 | 0 | 0 | pure schema |
| categories | 2 | 0 | 0 | pure schema (no seed) |
| currencies | 2 | 1 (0001: seed_initial_rates) | 0 | **load-bearing seed** |
| locations | 1 | 0 | 0 | pure schema |
| lookups | 1 | 0 | 0 | pure schema |
| moderation | 2 | 0 | 0 | pure schema |
| search | 7 | 3 (0003:×1, 0004:×1, 0005:×1, all no-op on fresh) | 0 | pure schema + data backfills |
| trust | 2 | 0 | 0 | pure schema |
| users | 6 | 0 | 0 | pure schema (0002 is plain AlterField, no backfill) |
| **Total** | **39** | **5** | **13** | **4 non-reproducible DDL objects** (2 trigger functions + 2 triggers in ads) |

## Appendix B: Files Referenced

### Production code (to be modified)
- `docker/Dockerfile` — add test-runtime stage
- `docker-compose.test.yml` — build target
- `docker/entrypoint-test.sh` — remove redundant compilemessages + DB check + migrate_locked
- `docker/entrypoint.sh` — keep base compile_messages (no change needed)
- `docker-compose.yml` — wire setup_search_triggers + load_exchange_rates into migrate one-shot
- `Makefile` — already has xdist in test-recreate; no change needed
- `Makefile.ps1` — sync test-recreate + help text
- `src/backend/config/settings/test.py` — add MIGRATION_MODULES
- `pyproject.toml` — no change (addopts already correct)

### New files
- `src/backend/apps/core/management/commands/squash_rehydrate_runsql.py`
- `src/backend/apps/ads/management/commands/setup_search_triggers.py`
- `src/backend/apps/currencies/management/commands/load_exchange_rates.py`
- `.ai/plans/13_test-env-acceleration_plan.md` (this file)

### Management commands (already exist — confirmed)
- `src/backend/apps/ads/management/commands/backfill_translations.py` ✓
- `src/backend/apps/categories/management/commands/load_catalog.py` ✓

### Test files (to be modified)
- `src/backend/apps/search/tests/test_autocomplete_template.py` — fix path resolution
- `src/backend/apps/ads/tests/test_detail_context.py` — fix path resolution
- `src/backend/conftest.py` — add currency seed fixture (or `apps/currencies/tests/conftest.py`)

### Scripts (to be modified)
- `scripts/consolidate_migrations.py` — add `--inventory` flag

### Existing tests (unchanged, gates)
- `src/backend/apps/core/tests/test_migrations.py` (TST-005)

### Artifacts
- `.ai/artifacts/pre-squash-schema.sql` (baseline)

## Appendix C: Verification Command Reference

```bash
# T1 verification
make test 2>&1 | grep -c "Compiling"                    # → 1
make test 2>&1 | grep "migrate_locked\|Waiting for PostgreSQL"  # → empty

# T2 verification
make test-recreate 2>&1 | grep "xdist"                   # → shows worker startup
.\Makefile.ps1 test-recreate 2>&1 | grep "xdist"

# T3 verification
make test 2>&1 | grep "FileNotFoundError"                # → empty
make test-recreate -k "test_price_normalizer" --tb=short  # → passes

# T4 verification
uv run python scripts/consolidate_migrations.py --inventory  # → 18 ops listed
uv run python src/backend/manage.py load_exchange_rates
uv run python src/backend/manage.py setup_search_triggers
make test-recreate 2>&1 | grep "create_test_db"           # → not "Applying migration"
make test-recreate  # → all tests pass

# T4g verification (after squash)
make test-recreate  # → 10 migration files only
uv run python src/backend/manage.py makemigrations --check --dry-run  # → exit 0
```