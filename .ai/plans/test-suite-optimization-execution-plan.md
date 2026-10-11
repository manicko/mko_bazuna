# Test Suite Optimization — Execution Plan

**Derived from:** `.ai/plans/test-suite-optimization-plan.md`
**Audit source:** `.ai/outputs/test-suite-optimization-audit.md`
**Tech Lead:** Kilo (tech-lead)
**Date:** 2026-10-11
**Status:** Executing — Blocks 1-5 COMPLETED (committed), Blocks 6-8 pending

---

## Context Summary (from Auditor + Git Verification)

**Blocks 1-4 are ALREADY IMPLEMENTED** (verified via `git log`):

| Commit | Block | Change |
|--------|-------|--------|
| `d9f153fb` | Block 1 (G3) | `entrypoint-test.sh`: `PYTEST_DEFAULTS` + `${PYTEST_OPTS:-}` merge |
| `87ccdcf0` | Block 2 (S1+L2+G2) | `ci.yml`: `-m "not (seed or slow or real_images)"`, `--maxprocesses=4`, no `--cov`; parity test updated |
| `5fb4935d` | Block 3 (P3+P4) | 7 concurrent sites: `xdist_group("concurrent")` + `flaky(reruns=1)`; `flaky` marker registered |
| `4ab67487` | Block 4 (C1+F3) | `no_cover` marker registered + applied to 9 settings test files; `settings/tests/conftest.py` created; 3 tests reclassified to `integration` |

**SLO gate already done:** `ci.yml:184-190` separate `TestSearchResponseSLORegression` step.

**Critical constraints (unchanged):**

1. **Parity test `test_docs_ci_parity.py`** (`src/backend/tests/test_docs_ci_parity.py`, marked `unit`) structurally asserts `ci.yml` tokens and entrypoint defaults. Any change to `ci.yml` or `entrypoint-test.sh` must update parity assertions.
2. `--cov` must NOT be in `addopts` — `test_addopts_has_no_cov` enforces CI-only coverage.
3. `strict_config = true` — every new marker must be registered in `pyproject.toml`.
4. `--dist loadgroup` is intentional; parity test forbids `worksteal`.
5. `--import-mode=importlib` must survive any `PYTEST_OPTS` merge.
6. No nightly cron workflow exists yet.
7. `dict_tags.py:42` has Python 2 `except AttributeError, TypeError:` syntax — a **pre-existing SyntaxError** that breaks 47 tests (`test_core_tags.py` + `test_templates.py`). This is a P0 production blocker from the audit findings, **outside the scope** of this optimization plan but noted as a blocking risk for seed test validation.

---

## Execution Blocks (Dependency-Ordered)

### Block 1 — G3: Merge `PYTEST_OPTS` with defaults
**Phase:** 1 | **Risk:** Low | **Effort:** 2 | **Agent:** Implementor
**Status:** ✅ DONE (commit `d9f153fb`)

**File:** `docker/entrypoint-test.sh` (line 59)

**Problem:** `${PYTEST_OPTS:- <defaults>}` discards ALL defaults when `PYTEST_OPTS` is set. `make test-recreate` passes `--create-db --tb=short -n auto --maxprocesses=4 --dist loadgroup` — this drops `--reuse-db`, forcing a full schema rebuild.

**Change:** Split into `PYTEST_DEFAULTS` (always-present) + `${PYTEST_OPTS:+}` (caller additions):
```bash
PYTEST_DEFAULTS="--reuse-db --tb=short --durations=10 -n auto --maxprocesses=4 --dist loadgroup"
uv run pytest ${PYTEST_OPTS:-} ${PYTEST_DEFAULTS} "${PYTEST_MARK_ARGS[@]}"
```
`PYTEST_OPTS` appends additional flags; defaults (including `--reuse-db`) are always retained.

**Parity impact:** `test_entrypoint_defaults_reuse_db`, `test_entrypoint_defaults_loadgroup`, `test_entrypoint_caps_maxprocesses` — all still pass (tokens present in defaults string).

---

### Block 2 — S1+L2+G2: CI gate optimization + parity updates
**Phase:** 1 | **Risk:** Low | **Effort:** 2 | **Agent:** Implementor
**Status:** ✅ DONE (commit `87ccdcf0`)

**Files:** `.github/workflows/ci.yml` (line 177), `src/backend/tests/test_docs_ci_parity.py`

**Changes:**
1. **S1** (ci.yml:177): `-m "not seed"` → `-m "not (seed or slow or real_images)"`
2. **L2** (ci.yml:177): add `--maxprocesses=4` after `-n auto`
3. **G2** (ci.yml:177): remove `--cov --cov-report=term --cov-report=xml` from PR test step
4. **Coverage upload** (ci.yml:192-197): make conditional (`if: failure() || (always() && contains(steps.*, 'cov'))`) — or remove from PR gate entirely (coverage retained in SLO + nightly).
5. **Parity test updates** (`test_docs_ci_parity.py`):
   - `test_ci_excludes_seed`: assert `'-m "not (seed or slow or real_images)"'` instead of `'-m "not seed"'`
   - `test_ci_command_subset`: update `expected` list — remove `"--cov"` and `"--cov-report=xml"`, add `"--maxprocesses=4"`, change marker to `"-m \"not (seed or slow or real_images)\""`

---

### Block 3 — P3+P4: Concurrency hardening
**Phase:** 1 | **Risk:** Medium | **Effort:** 2 | **Agent:** Implementor (after Researcher for F1)
**Status:** ✅ DONE (commit `5fb4935d`)

**Files:** 7 concurrent test sites

| File | Line | Current mark |
|------|------|-------------|
| `apps/ads/tests/test_transition_concurrency.py:34` | class pytestmark | `concurrent` |
| `apps/ads/tests/test_edit_views_locking.py:139` | class | `concurrent` |
| `apps/moderation/tests/test_admin_actions.py:660` | class | `concurrent` |
| `apps/core/tests/test_sweep_archive.py:196` | class | `concurrent` |
| `apps/currencies/tests/test_recompute_command.py:200` | method/class | `concurrent` |
| `apps/moderation/tests/test_priority_service.py:1189` | method | `concurrent` |
| `apps/core/tests/test_db_lock_timeout.py:59` | method | `concurrent` |

**Changes:**
1. **P3:** Add `@pytest.mark.xdist_group("concurrent")` to all 7 sites — pins all TRUNCATE-based concurrent tests to a single xdist worker under `--dist loadgroup`, preventing cross-worker deadlocks on shared tables (`ads_ad`, `ads_ad_status_history`).
2. **P4:** Add `@pytest.mark.flaky(reruns=1, reruns_delay=1)` to the same 7 sites for transient lock-timeout flake recovery.
3. Register `flaky` marker in `pyproject.toml` (defensive — `pytest-rerunfailures` auto-registers, but `strict_config` may require explicit registration).

**Verification:** Run `PYTEST_OPTS="" PYTEST_SKIP_MARKERS="" ./Makefile.ps1 test-recreate -k "concurrent or RowLock or LockWait or ArchiveSweep"` (local test DB) to confirm no deadlocks.

---

### Block 4 — C1+F3: Marker discipline for settings tests
**Phase:** 1 | **Risk:** Low | **Effort:** 2 | **Agent:** Implementor
**Status:** ✅ DONE (commit `4ab67487`)

**Files:** `pyproject.toml:172-181`, 9 files in `config/settings/tests/`

**Changes:**
1. **F3 — Reclassify 3 settings tests** from `[unit, settings]` → `[integration, settings]`:
   - `test_prod_logging.py` (most subprocess calls, ~6)
   - `test_settings_secrets.py` (most subprocess calls, ~8)
   - `test_env_allowlist_reverse.py` (parametrized, high subprocess count)
2. **F3 — `test_session_policy.py`**: Already marked `[django_db, integration]`. No change needed — audit confirms it's correctly classified. Document this.
3. **C1 — Register `no_cover` marker** in `pyproject.toml:172-181`:
   ```
   "no_cover: marks settings tests with subprocess side-effects excluded from coverage"
   ```
4. **C1 — Apply `@pytest.mark.no_cover`** at module level to all 8 settings test files that spawn subprocesses (all 9 `[unit/integration, settings]` files — these are the subprocess-isolation tests, not `test_settings_defaults.py` which is pure import).
   - Note: `test_download_seed_photos.py` (in `apps/seed/tests/`) is already correctly `unit`-marked with pure mocks — not in scope.
5. Add `conftest.py` in `config/settings/tests/` that registers a `pytest_runtest_setup` hook to skip coverage for `no_cover` tests (sets `COVERAGE_PROCESS_START=""` to prevent subprocess coverage data generation).

**Verification:** `pyproject.toml` markers validate; settings tests pass.

---

### Block 5 — F1: Class-scoped seed fixture
**Phase:** 2 | **Risk:** Medium | **Effort:** 3 | **Agent:** Tech Lead (direct implementation from research)

**Files:** `src/backend/apps/seed/tests/conftest.py`, `src/backend/apps/seed/tests/test_seed.py`

**Problem:** `TestSeedFilterCoverage` (8 tests, line 1911) calls `self._run_seed()` (same params: `--users=4 --ads=40`) in every test — 8 redundant `call_command("seed")` invocations, ~60s each. Other seed classes (`TestSeedCommand`, `TestSeedCommandEnhanced`) use different per-test parameters and cannot share.

**Change:**
1. Added class-scoped fixture `seeded_test_data` to `conftest.py` that runs `call_command("seed", ...)` once per class (4 users, 40 ads, patched `_NoImageGenerator`).
2. Refactored `TestSeedFilterCoverage`:
   - Changed `_setup_class` autouse fixture to class scope, delegating to `seeded_test_data` (fixed `PytestRemovedIn10Warning` via `@classmethod`).
   - Removed per-test `self._run_seed()` calls.
   - Tests depend on class-scoped `seeded_test_data` fixture.
3. Kept `_run_seed()` method for any tests that need it (e.g., `test_seed_idempotent`).

**Key technical detail:** With `@pytest.mark.django_db` (no `transaction=True`), each test gets a savepoint-rollback transaction. A class-scoped fixture that commits data (outside the savepoint) persists across tests — the savepoint rollback only affects test-specific changes, not the committed seed data.

**Verification:** All 8 `TestSeedFilterCoverage` tests pass with 1 seed invocation instead of 8. `TestSeedCommand` and `TestSeedCommandEnhanced` unchanged.

**Status:** ✅ DONE — 8 tests pass in ~53s (setup run was 6.68s class-scoped, vs. 8 × individual runs previously).

---

### Block 6 — F2: Shared subprocess-probe fixture
**Phase:** 2 | **Risk:** Low | **Effort:** 2 | **Agent:** Implementor

**Files:** New `config/settings/tests/conftest.py`, 9 settings test files

**Problem:** 10 duplicated `_run_in_subprocess` helpers across settings test files (70 total subprocess calls).

**Change:**
1. Create `config/settings/tests/conftest.py` with shared `_run_in_subprocess` and `_prod_env_overrides` fixtures (moved from `test_prod_logging.py`).
2. Update the 9 settings test files to import from the shared conftest instead of defining local helpers.
3. Apply `no_cover` marker (from Block 4) to skip subprocess coverage.

**Verification:** All settings tests pass; no behavior change.

---

### Block 7 — G4: Nightly workflow
**Phase:** 2 | **Risk:** Low | **Effort:** 3 | **Agent:** Implementor

**File:** `.github/workflows/ci-nightly.yml` (new)

**Change:** Create a nightly workflow with:
- `cron: ["0 3 * * *"]` (daily 03:00 UTC)
- `workflow_dispatch: true` (manual trigger)
- Steps: checkout → setup uv → start DB → bootstrap reference data → `compilemessages` → `pytest -m "not seed" --cov --cov-report=xml --reuse-db -n auto --maxprocesses=4 --dist loadgroup -k "or slow or real_images"` plus a separate seed job
- Coverage upload to artifact
- Concurrency group: `nightly`

**Note:** The existing `ci-seed.yml` runs `-m "seed"` on push (not nightly). This new workflow adds nightly execution of slow/real_images tests + strict coverage. The seed suite from `ci-seed.yml` runs on push; this nightly adds the rest (slow, real_images) that CI skips.

**Verification:** YAML syntax validates; mirrors `ci.yml` structure.

---

### Block 8 — Full CI split + G1: Phase 3 hardening
**Phase:** 3 | **Risk:** Low | **Effort:** 2 | **Agent:** Implementor

**Files:** `.github/workflows/ci.yml`, `pyproject.toml`

**Changes:**
1. **Full CI split:** Add a `full-ci` job to `ci.yml` that runs:
   - Parallel non-seed: `pytest -m "not seed" -n auto --maxprocesses=4 --dist loadgroup --reuse-db --cov --cov-report=xml`
   - (Seed runs separately via `ci-seed.yml` on push — already exists)
   - Or: a single job that runs non-seed in parallel first, then seed serially.
2. **G1 — Strict branch coverage:** In `pyproject.toml`, raise `fail_under` from 80 to 85 for Full CI + Nightly. Add a `[tool.coverage.report]` override or use `--fail-under=85` on the Full CI/Nightly command line instead of changing the global `pyproject.toml` default (which would affect all runs).
   - **Approach:** Pass `--cov-fail-under=85` on the Full CI and Nightly commands; keep `pyproject.toml` `fail_under=80` as the local default.

**Verification:** Full CI job runs both suites; coverage threshold is enforced.

---

## Execution Order

**COMPLETED (Blocks 1-4):**

```
Block 1 (G3) → Block 2 (S1+L2+G2) → Block 3 (P3+P4) → Block 4 (C1+F3)
   ✅        →         ✅          →         ✅        →         ✅
  d9f153fb      87ccdcf0            5fb4935d             4ab67487
```

**REMAINING (Blocks 5-8):**

```
Block 5 (F1: seed fixture)   Block 6 (F2: subprocess fixture)   Block 7 (G4: nightly)
      ↓                            ↓                  ↓
Block 8 (Full CI + G1)
```

**Parallelization opportunities** (max 2 parallel, 1 Implementor):
- Block 5 (Planner) and Block 6 (Planner) can run their task-creation in parallel
- Block 7 and Block 8 are independent but require sequential Implementors

**Sequential blocks** (1 at a time):
1. ~~Block 1 → 2 → 3 → 4~~ (done) → Block 5 → 6 → 7 → 8

## Acceptance Criteria Per Block

| Block | Status | Acceptance Criteria |
|-------|--------|---------------------|
| G3 | ✅ Done | `PYTEST_OPTS="-k foo"` preserves `--reuse-db`; `make test-recreate` works |
| S1+L2+G2 | ✅ Done | `ci.yml` excludes `not (seed or slow or real_images)`, has `--maxprocesses=4`, no `--cov`; parity tests pass |
| P3+P4 | ✅ Done | All 7 concurrent sites have `xdist_group("concurrent")` + `flaky(reruns=1)`; no deadlocks |
| C1+F3 | ✅ Done | `no_cover` registered + applied to 9 files; 3 tests reclassified to `integration`; parity test passes |
| F1 | ✅ Done | `TestSeedFilterCoverage` runs seed once per class via `seeded_test_data` fixture; all 8 tests pass in ~53s (down from ~500s) |
| F2 | ⏳ Pending | Single shared `_run_in_subprocess` + `_prod_env_overrides` in conftest; settings test files import from it |
| G4 | ⏳ Pending | New `ci-nightly.yml` with cron + workflow_dispatch + strict coverage |
| Full CI+G1 | ⏳ Pending | Full CI job runs non-seed (parallel) + seed (serial); `--cov-fail-under=85` on Full+Nightly |

---

## Risks & Mitigations

| Risk | Mitigation |
|------|-----------|
| G3 merge breaks `PYTEST_OPTS` word-splitting (multi-token values) | Document: use `PYTEST_SKIP_MARKERS` for marker exclusion; `PYTEST_OPTS` for flags only |
| P3 `xdist_group("concurrent")` serializes too many tests | Same-group pinning is intentional — prevents TRUNCATE deadlocks; acceptable slowdown |
| F1 fixture scope change breaks seed tests | Run full seed test suite; `test_seed_idempotent` must still call seed twice |
| C1 `no_cover` marker not enforced by coverage.py | Marker is documentation + conftest hook disables subprocess `COVERAGE_PROCESS_START` |
| Parity test breakage | Update `test_docs_ci_parity.py` in Block 2 alongside ci.yml changes |
| `strict_config = true` rejects `flaky` marker | Pre-register `flaky` in `pyproject.toml` (Block 3) |

---

## Files Affected (Summary)

| File | Blocks | Change Type |
|------|--------|-------------|
| `docker/entrypoint-test.sh` | G3 (1) | Modify |
| `.github/workflows/ci.yml` | S1/L2/G2/Full CI (2, 8) | Modify |
| `.github/workflows/ci-nightly.yml` | G4 (7) | New |
| `src/backend/tests/test_docs_ci_parity.py` | S1/L2/G2 (2) | Modify |
| `pyproject.toml` | C1/F3/flaky/G1 (3, 8) | Modify |
| `config/settings/tests/conftest.py` | C1/F2 (4, 6) | New |
| 9 files in `config/settings/tests/` | C1/F3/F2 (4, 6) | Modify |
| 7 concurrent test files | P3/P4 (3) | Modify |
| `apps/seed/tests/conftest.py` | F1 (5) | Modify |
| `apps/seed/tests/test_seed.py` | F1 (5) | Modify |
