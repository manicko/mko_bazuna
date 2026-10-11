# Test Suite Optimization — Audit: Current State vs. Plan

**Scope:** `src/backend/`, `src/telegram_bot/`, `.github/workflows/`, `pyproject.toml`, `docker/entrypoint-test.sh`, `Makefile`, `Makefile.ps1`
**Date:** 2026-10-11
**Auditor:** @auditor subagent (ses_ed512a70bffe6bLgMwdGElF7Hp)

---

## 1. What's Already Implemented (pre-existing work)

### 1.1 Marker registration (pyproject.toml:172–181)
The following custom markers are already registered:
- `unit`, `integration`, `seed`, `settings`, `concurrent`, `slow`, `real_images`, `xdist_group`

`no_cover` is **NOT** registered. (Plan C1.)

### 1.2 `seed` marker application
- Applied at **15 places** in `src/backend/apps/seed/tests/test_seed.py` (class-level on 4 classes + method-level).
- `src/backend/apps/seed/tests/conftest.py` already patches `seed_service.ImageGenerator` to a no-op stub (`_NoImageGenerator`), skipping the real SHA-256 image pipeline for marked tests.
- `@pytest.mark.real_images` opts back in for the one test that asserts on image files (`TestSeedCommandEnhanced.test_media_cleanup`).

### 1.3 SLO regression gate (CI already has it)
- `ci.yml` lines 184–190: separate "Run SLO regression test" step running `TestSearchResponseSLORegression` with `--reuse-db` — **already implemented** as a named gate.

### 1.4 Seed suite in separate workflow (ci-seed.yml)
- `ci-seed.yml` runs `-m "seed"` serially on push to `main`/`develop` (not per-PR).
- Uses `seed_load_test_ads` command for load-test scale data (refactored from inline shell).

### 1.5 `PYTEST_SKIP_MARKERS` env-var mechanism (entrypoint-test.sh:51–58)
- `docker/entrypoint-test.sh` supports `PYTEST_SKIP_MARKERS` (appends `-m "not (...)"`).
- Used by `Makefile.ps1 test` target (`PYTEST_SKIP_MARKERS=seed`).

### 1.6 `--maxprocesses=4` cap (Makefile only)
- `Makefile` line 179 and `Makefile.ps1` line 150: `test-recreate` sets `--maxprocesses=4`.
- The default pytest invocation in `entrypoint-test.sh:59` also includes `--maxprocesses=4`.

### 1.7 `xdist_group("migrations")` usage
- Only `test_migrations.py` (line 26) uses `xdist_group`. It is a settings-marked test, not a concurrent TRUNCATE test.

### 1.8 Recent git history (last 30 commits on main)
Recent commits focus on CI infrastructure, not test-suite optimization:
- CI security hardening (Trivy SARIF, pinned actions, Node 24, GHCR namespace fix)
- Rate-limiting improvements (429 returns SVG placeholder, Retry-After header)
- Media caching (max-age=86400 on image responses)
- Load-test fixes (seed_load_test_ads command, rate-limit disabled for load-test)
- Settings guards (BOT_USERNAME validation, deploy-check env parity)
- i18n documentation (safe scratch makemessages recipe)

**No commits touch `pyproject.toml` markers, pytest config, or test marker reclassification.** The plan file `.ai/plans/test-suite-optimization-plan.md` is **untracked** (not yet committed).

---

## 2. Plan vs. Implementation Gap Analysis

### Phase 1 — Immediate (S1, G3, P3, L2, C1, P4, F3)

| Plan Item | Target | Current State | Gap | Evidence |
|-----------|--------|---------------|-----|----------|
| **S1** | PR gate excludes `seed`, `slow`, `real_images` | CI uses `-m "not seed"` only | `slow` and `real_images` tests run in PR gate | `ci.yml:177` |
| **G3** | Merge `PYTEST_OPTS` with defaults (preserve `--reuse-db`) | `PYTEST_OPTS` **replaces** all defaults | Setting `PYTEST_OPTS="-k foo"` loses `--reuse-db`, `--maxprocesses=4`, `--dist loadgroup` | `entrypoint-test.sh:59` |
| **P3** | Pin 6 concurrent classes with `xdist_group` | **None** of the 7 `@pytest.mark.concurrent` sites use `xdist_group` | Deadlock/flaky risk under xdist `loadgroup` | Grep: `xdist_group` only in `test_migrations.py:26` |
| **L2** | Cap `--maxprocesses=4` in CI | CI uses `-n auto` with **no** `--maxprocesses` cap | Potential ENOMEM on CI runners | `ci.yml:177` |
| **C1** | `no_cover` on 8 settings tests | `no_cover` marker **not registered**, **not applied** | Settings subprocess tests still counted in coverage reports | `pyproject.toml:172–181` (no `no_cover`); grep finds 0 usages |
| **P4** | `reruns=1` on concurrent tests | `pytest-rerunfailures` installed (`pyproject.toml:222`) but `@pytest.mark.flaky`/`reruns` used **nowhere** | Flake protection absent | Grep: 0 matches for `flaky\|reruns` in tests |
| **F3** | Reclassify 3 tests + `test_session_policy` | `test_download_seed_photos.py` is marked `unit` (correct — pure mocks, no DB); `test_session_policy.py` in `config/settings/tests/` is marked `[django_db, integration]` (not reclassified) | 3 settings tests still marked `unit` but spawn subprocesses; `test_session_policy` still mis-placed | See §3 below |

### Phase 2 — Structural (F1, F2, G2, G4, SLO gate)

| Plan Item | Target | Current State | Gap | Evidence |
|-----------|--------|---------------|-----|----------|
| **F1** | Class-scoped seed fixture (run `call_command("seed")` once per class) | Each test in `TestSeedCommand` (6 tests), `TestSeedCommandEnhanced` (2 tests), `TestSeedFilterCoverage` (8 tests) calls `seed` individually via `_run_seed()` or inline | ~8–17 redundant seed invocations per class | `test_seed.py:862,1331,1936` etc. |
| **F2** | Shared subprocess-probe fixture | Each of ~10 settings test files defines its own `_run_in_subprocess` helper | 10 duplicated helpers | `test_prod_logging.py:32`, `test_settings_secrets.py:37`, etc. |
| **G2** | `--cov` off in PR fast gate | CI test job runs `--cov` + `--cov-report=term/xml` | Coverage overhead in PR gate | `ci.yml:177` |
| **G4** | Nightly workflow (seed/slow/real_images) | No nightly cron workflow exists | Overnight full-suite runs absent | `.github/workflows/` has no `*nightly*` or `cron` for tests |
| **SLO gate** | Separate SLO gate job | **ALREADY DONE** | — | `ci.yml:184–190` |

### Phase 3 — Hardening (Full CI split, strict coverage)

| Plan Item | Target | Current State | Gap | Evidence |
|-----------|--------|---------------|-----|----------|
| Full CI split | Serial seed + parallel non-seed in one Full CI job | CI has `test` (`-m "not seed"`) + `ci-seed.yml` (`-m "seed"` on push) but no single "Full CI" job combining both | No unified Full CI with parallel non-seed + serial seed | `ci.yml` and `ci-seed.yml` are separate workflows |
| **G1** | Strict branch coverage in Full + Nightly | `coverage.py` has `branch = true`, `fail_under = 80` | `fail_under=80` is lenient; "strict" would raise threshold for Full+Nightly | `pyproject.toml:184–191` |

---

## 3. Detailed Findings

### 3.1 F3 Reclassification targets

**The 3 settings tests to reclassify:** The plan's F3 says "Reclassify 3 + `test_session_policy`". The 9 settings test files in `config/settings/tests/` are all marked `[unit, settings]`:
1. `test_bot_username_validation.py` (L41)
2. `test_csrf_trusted_origins.py` (L17)
3. `test_deploy_check_env_parity.py` (L68)
4. `test_env_allowlist.py` (L21)
5. `test_log_mask_key_validation.py` (L28)
6. `test_oneshot_settings.py` (L26)
7. `test_prod_logging.py` (L22)
8. `test_env_allowlist_reverse.py` (L70)
9. `test_settings_secrets.py` (L33)

These are marked `unit` because they don't use `django_db`, but they each spawn subprocesses (70 total `_run_in_subprocess`/`subprocess.run` calls across the directory). The plan likely identifies the 3 heaviest (most parametrizations / subprocess spawns) as candidates for reclassification to `integration` so they don't run in the `unit`-only fast path. **Recommendation:** identify by subprocess count (e.g., `test_settings_secrets.py`, `test_prod_logging.py`, `test_env_allowlist_reverse.py` have the most).

**`test_session_policy.py`:** Currently `pytestmark = [django_db, integration]` (L41). It lives in `config/settings/tests/` but does **not** use subprocess isolation — it uses `django.test.Client` directly. The plan wants it reclassified as a proper `integration` test (move markers, ensure it's not treated as a settings subprocess test). It IS already marked `integration`, but the plan may want it moved out of the settings directory or have its markers normalized.

### 3.2 Concurrent test classes (P3)

7 sites use `@pytest.mark.concurrent` (all use `transaction=True` = TRUNCATE per test), but **none** are pinned with `xdist_group`:

| File | Line | Scope | Class/Method |
|------|------|-------|--------------|
| `test_transition_concurrency.py` | 34 | class (pytestmark) | `TestAdRowLockConcurrency` |
| `test_edit_views_locking.py` | 139 | class | `TestEditViewsRowLockConcurrency` |
| `test_admin_actions.py` | 660 | class | `TestBulkRejectRowLockConcurrency` |
| `test_sweep_archive.py` | 196 | class | `TestArchiveSweepRowLockConcurrency` |
| `test_recompute_command.py` | 200 | method? | need to verify |
| `test_priority_service.py` | 1189 | method | `TestBulkModerationActionView.test_row_lock_blocks_concurrent_writer` |
| `test_db_lock_timeout.py` | 59 | method | `TestLockWaitIsBounded.test_lock_wait_is_bounded` |

The plan says "6 concurrent classes" — likely counting only the class-level marks (5 classes) plus 1 more, or excluding one. All are unpinned. Under `--dist loadgroup`, unpinned tests can be scheduled on different workers, causing TRUNCATE deadlocks on shared tables.

### 3.3 Seed invocation pattern (F1)

`TestSeedCommand` (test_seed.py:806) has 7 tests, 6 of which call `call_command("seed")` directly. `TestSeedFilterCoverage` (L1912) has 8 tests, all calling `self._run_seed()` (L1934). `TestSeedCommandEnhanced` (L1272) has 2 tests, 1 calling `call_command("seed")` twice. Total: ~17 seed invocations within `@pytest.mark.seed` classes, each running the full seed pipeline (user generation, ad generation, status assignment, popular searches, etc.). Even with the ImageGenerator stub, each invocation takes ~150s cumulatively.

### 3.4 Settings test duplication (F2)

Each settings test file defines its own `_run_in_subprocess` helper:
- `test_prod_logging.py:32` — full `subprocess.run` helper
- `test_settings_secrets.py:37` — full `subprocess.run` helper
- `test_csrf_trusted_origins.py:29` — full `subprocess.run` helper
- `test_bot_username_validation.py:38` — imports `_run_in_subprocess` from elsewhere
- `test_deploy_check_env_parity.py:66` — imports `_run_in_subprocess` from `test_prod_logging`
- Others (7–10 files) have similar or imported helpers

70 total subprocess invocations across the settings test directory. A shared fixture would consolidate the helper and allow caching of the subprocess environment.

### 3.5 CI test job configuration (G2, G3, L2)

Current CI test command (`ci.yml:177`):
```
uv run pytest -m "not seed" -n auto --dist loadgroup --tb=short --cov --durations=10 --cov-report=term --cov-report=xml --reuse-db
```

Missing compared to plan targets:
- Excludes only `seed`, not `slow` or `real_images` (S1)
- No `--maxprocesses=4` cap (L2)
- `--cov` enabled (G2 should remove it from PR gate)

### 3.6 `PYTEST_OPTS` fragility (G3)

`entrypoint-test.sh:59`:
```bash
uv run pytest ${PYTEST_OPTS:- --reuse-db --tb=short --durations=10 -n auto --maxprocesses=4 --dist loadgroup} "${PYTEST_MARK_ARGS[@]}"
```
When `PYTEST_OPTS` is set (e.g., `--create-db --tb=short -n auto`), the `${PYTEST_OPTS:- ...}` expansion **discards all defaults** including `--reuse-db`. This means any `PYTEST_OPTS` override that doesn't include `--reuse-db` will rebuild the test DB schema from scratch, adding ~10–15s per run. Only `PYTEST_SKIP_MARKERS` is safely appended (line 51–54); `PYTEST_OPTS` itself is not merged.

### 3.7 Marker registry completeness

The `no_cover` marker from the plan (C1) is **not registered** in `pyproject.toml:172–181`. If applied to tests without registration, pytest with `strict_config = true` (line 163) would raise an error. This must be registered before any test can use it.

---

## 4. Architecture & Dependencies

### 4.1 Test DB provisioning
- `config/settings/test.py` (referenced in `entrypoint-test.sh:12`) hard-pins `DATABASES["default"]["NAME"] = "mko_bazuna"`.
- pytest-django provisions `test_mko_bazuna` via `django_db_setup`.
- `src/backend/conftest.py:111–165` — session-autouse `_restore_test_schema_post_db_setup` fixture runs `migrate --run-syncdb`, `load_exchange_rates`, `setup_search_triggers` under advisory lock 111 (`AdvisoryLockId.TEST_SCHEMA_SETUP`).
- `DisableMigrations` / `MIGRATION_MODULES = None` in test settings means no migration playback during tests.

### 4.2 Two-process model
- Web (gunicorn WSGI, HTMX MPA) + bot (aiogram, `django.setup()` + shared ORM). Migrations run once before both start. This is unchanged by the plan.

### 4.3 xdist distribution
- Currently uses `--dist loadgroup` (correct for bot FSM tests that share state per worker).
- `--dist worksteal` (xdist 3.7+) would break `xdist_group` semantics. Plan recommends sticking with `loadgroup`.

### 4.4 Key constraints
- `strict_config = true` in `pyproject.toml:163` — any unregistered marker causes a hard error.
- `--import-mode=importlib` set in `addopts` (line 169) — must NOT be stripped (e.g., `--override-ini=addopts=` would break it).
- `pytest-randomly` is installed (`pyproject.toml:221`) — random ordering may interact with concurrent tests and seed state.

---

## 5. Summary Table: Plan Items vs. Implementation Status

| Plan Item | Phase | Risk | Effort | Implemented? |
|-----------|-------|------|--------|-------------|
| S1: PR gate excludes `not (seed or slow or real_images)` | 1 | Low | 1 | **No** (`ci.yml:177` excludes only `seed`) |
| G3: Merge `PYTEST_OPTS` with defaults | 1 | Low | 2 | **No** (`entrypoint-test.sh:59` replaces) |
| P3: Pin 6 concurrent classes with `xdist_group` | 1 | Med | 2 | **No** (none pinned except `test_migrations.py`) |
| L2: Cap `--maxprocesses=4` in CI | 1 | Low | 1 | **No** (CI `ci.yml:177` lacks it; Makefile has it) |
| C1: `no_cover` on 8 settings tests | 1 | Low | 1 | **No** (marker not even registered) |
| P4: `reruns=1` on concurrent tests | 1 | Low | 1 | **No** (pytest-rerunfailures installed but unused) |
| F3: Reclassify 3 tests + `test_session_policy` | 1 | Low | 2 | **No** (classification unchanged) |
| F1: Class-scoped seed fixture | 2 | Med | 3 | **No** (seed called per-test, ~17 invocations/class) |
| F2: Shared subprocess-probe fixture | 2 | Low | 2 | **No** (10 duplicated helpers, 70 subprocess calls) |
| G2: `--cov` off PR gate | 2 | Low | 1 | **No** (`ci.yml:177` uses `--cov`) |
| G4: Nightly workflow | 2 | Low | 3 | **No** (no nightly cron) |
| SLO gate: separate job | 2 | Low | 2 | **Yes** (`ci.yml:184–190`) |
| Full CI: serial seed + parallel non-seed | 3 | Low | 2 | **Partial** (separate `ci.yml` + `ci-seed.yml`, no unified Full CI) |
| G1: Strict branch coverage Full+Nightly | 3 | Low | 1 | **No** (`fail_under=80` is lenient) |
