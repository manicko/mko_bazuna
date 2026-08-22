# Test Suite Performance & Strategy Audit Plan

**Project:** Mko Bazuna (Django 5.2 LTS, Python 3.14, PostgreSQL 18, aiogram 3.x, HTMX MPA)
**Status:** Reconciled audit plan — reflects the state of the repo as of commit `b62612` + `3ddc0b2` (test-optimization-plan.md Phase A–D fully implemented) and the current working tree. **⚠️ Working-tree parity edits** (`Makefile`, `Makefile.ps1`, `docker/entrypoint-test.sh`) are present but **uncommitted** at HEAD `510b471` — they are not reproducible from `git checkout HEAD` until committed. `.ai/plans/test-suite-audit-plan.md` itself is **untracked**.
**Scope:** Test-suite performance, marker taxonomy, and CI/fast-gate strategy for `src/`.
**Evidence sources (verified):** Measured run artifacts (§2.1), marker classification via `grep`/glob of `src/`, CI workflow files (`.github/workflows/ci.yml`, `.github/workflows/ci-nightly.yml`), `docker/entrypoint-test.sh`, `Makefile.ps1`, `Makefile`, `pyproject.toml`, `.ai/context/commands.md`, `docs/99-agent/rules.md`, `git log`.

---

## 1. Executive Summary

Two separate plans governed this work. They must not be conflated:

1. **`test-optimization-plan.md`** (the implementation plan) was **fully executed** in commit `b62612` ("Test optimization plan: Phase A–D implementation") + `3ddc0b2` ("fix(test): refine test-optimization implementation and fix regressions"). All of **Phase A** (remove `e2e` marker, canonical root-conftest fixtures, consolidate `_make_ad`/`_create_ad` into `create_test_ad`), **Phase B** (migrate 14 `django.test.TestCase` files to pytest-django, add `test_decorators.py`, refactor `test_priority.py` to the public `calculate_priority` API), **Phase C** (11 coverage gaps C.1–C.10 — constraints, trust-score prefetch N+1, `approve_ad→PUBLISHED` signal chain, search sort, LoginToken edge cases, `save_photo→generate_thumbnails`, contact combinatorics, trust boundaries/floors, priority boundaries), and **Phase D** (update `.ai/context/commands.md` + `docs/99-agent/rules.md`) are **COMPLETE and verified** in the current repo. Nothing from `test-optimization-plan.md` remains open; it is not re-listed below as work.

2. **`test-suite-audit-plan.md`** (this document) is the **strategy/performance** plan. Its scope — marker taxonomy, CI `--reuse-db`, CI job split, dead-dependency removal, coverage-report merging — was **NOT** covered by `test-optimization-plan.md` and is therefore **not** done. Reconciled status:

| Item | Status | Notes |
|---|---|---|
| P2 `NameError: AdStatus` blocker | ✅ Resolved | `test_media_security.py:21` imports `AdStatus` at module scope; git clean. |
| P3 currency-cache xdist race | ✅ Resolved | `_clear_rate_cache` autouse fixture (`test_recompute_command.py:17-23`) + fresh `PriceNormalizer` per `call_command`. |
| P4 `load_catalog` autouse overhead | ✅ Stale / resolved | No `load_catalog` autouse fixture exists in the repo; `load_catalog` is a plain function in `apps/categories/catalog/builder.py`. No action. |
| P1 `slow` marker semantic defect | ⚠️ Re-scoped, **OPEN** | 46 files still apply module-level `pytestmark = [django_db, slow, integration]`. The fast gate **no longer depends on `slow`** (see below), so this no longer blocks dev iteration — but it still corrupts `-m unit` / `-m "not slow"` selection and CI sub-set splitting. |
| Fast gate (dev `make test`) | ✅ Done (PS1) / ✅ Done (bash WT, **uncommitted**) | Seed-exclusion via `PYTEST_SKIP_MARKERS=seed` in `entrypoint-test.sh` + `Makefile.ps1` + bash `Makefile`. The fast-gate mechanism is present in the working tree but **uncommitted** at HEAD `510b471`. |
| CI `--reuse-db` | ❌ Open | `ci.yml:85` + `ci-nightly.yml:73` run `uv run pytest` directly, no `--reuse-db`. |
| CI job split | ❌ Open | Single `test` job; no parallel unit/integration/concurrent/settings split. |
| Dead deps (`radon`, duplicate `requests`) | ❌ Open | Both still in `[dependency-groups].dev`. |
| Seed isolated in nightly | ✅ Done | `ci-nightly.yml:73` runs `-m "seed"`; coverage artifact uploaded. |
| Merge coverage across CI stages | ❌ Open | Separate per-job `.coverage` blobs; `fail_under = 80` measured per-subset. |

**The pivotal reconciliation:** the audit's original central premise — *"the `slow` marker is broken, making fast-feedback CI impossible"* — is **obsolete**. The fast gate pivoted to **seed-exclusion** (`PYTEST_SKIP_MARKERS=seed` appends `-m "not (seed)"`), so `make test` / `.\Makefile.ps1 test` already skips the ~17-minute nightly seed suite and runs the dev gate in ~300s. Consequently P1 is no longer a *blocker*; it is a **marker-hygiene** item that matters for targeted selection (`-m unit`) and the CI split, not for the dev fast gate.

---

## 2. Current State Assessment

### 2.1 Performance Baseline

Measured with the standard test runner
(`docker compose --project-name mko-bazuna-test -f docker-compose.yml -f docker-compose.test.yml run --rm test`)
against a healthy PostgreSQL 18-alpine test DB container (`mko-bazuna-test-db-1`, port 5433). Baseline captured **before** the optimization-plan implementation; counts rose modestly afterward due to added coverage tests (C.1–C.10, B.2).

| Run | Marker/flag | Tests | Wall time | Notes |
|---|---|---|---|---|
| Serial non-seed | default (no marker) | 1,046 | **299s** | 1 failure: `NameError: AdStatus` — **now resolved** |
| Serial seed | `-m seed` | 16 | **1,054s** | ≈85% of total suite wall time |
| xdist non-seed | `-n auto --dist loadscope` | 1,046 | ~290s | only ~3% speedup vs serial; **2 failures** (incl. currency-cache race) — **both now resolved** |
| Unit-only | `-m unit` | 102 | 8.0s setup + ~3s tests | Django setup dominates |
| Concurrent | `-m concurrent` | 28 | 15.38s first-test DB setup + ~3s tests | |
| Settings | `-m settings` | 3 | ~15s (~5s each) | subprocess spawn per test |

**Current fast gate (post-implementation):** `entrypoint-test.sh` exposes `PYTEST_SKIP_MARKERS=seed`, which appends `-m "not (seed)"` to the pytest invocation. `Makefile.ps1` `test` target passes `--env PYTEST_SKIP_MARKERS=seed`; `make test-all` runs everything. Local/Compose reuse the DB via `--reuse-db` (default in entrypoint); `make test-recreate` forces `--no-reuse-db --create-db`.

> Note: the optimization plan's coverage additions (new test files `test_ad_constraints.py`, `test_ad_detail_queries.py`, `test_approve_ad_side_effects.py`, `test_decorators.py`, `test_listings_sort.py`, `test_save_photo_integration.py`) raised the file count; the baseline test count above is the pre-optimization figure. The seed bulk (16 tests, ~1,054s) is unchanged and correctly isolated.

### 2.2 Marker Taxonomy Assessment

Six markers registered in `pyproject.toml` `[tool.pytest.ini_options] markers`: `unit`, `integration`, `seed`, `settings`, `concurrent`, `slow`. The `e2e` marker was **removed** (optimization Phase A.1). Inventory of the 82 test files in `src/`:

| Marker | Meaning (per registration) | Status in repo | Notes |
|---|---|---|---|
| `unit` | No DB, fast SimpleTestCase | ⚠️ ~5 files use it | `test_settings_secrets`, `test_decorators`, `test_download_seed_photos`, `test_media` (bot), `test_multi_lang_translation` (bot). `-m unit` selects only these — far below the ~235 it should. |
| `integration` | DB-backed, functional | applied on 46 files module-level | folded with `slow` (see flaw) |
| `seed` | Seed-command / ImageGenerator | 16 | 1,054s — nightly only; correctly isolated |
| `settings` | Import-time settings validation (subprocess) | 1 file, 3 tests | `test_settings_secrets.py` |
| `concurrent` | `transaction=True` (TRUNCATE per test) | 4 bot files | `test_ad_create`, `test_create_draft_ad`, `test_login_claim`, `test_claim_login_token` |
| `slow` | Genuinely slow (>5s) | ❌ **719+ tagged** | **still blanket-applied** at module level (see flaw) |

#### The flaw (still present)

Module-level `pytestmark = [pytest.mark.django_db, pytest.mark.slow, pytest.mark.integration]` appears on **46 files** (verified by grep: exactly 46 matches of the canonical string). Real profiling shows only **~40** of the tagged tests are genuinely slow (>5s); the other **~679+** are sub-second tests incorrectly tagged `slow`. Any `-m "not slow"` selection wrongly drops fast tests.

**However**, the dev fast gate no longer uses `-m "not slow"` — it uses `PYTEST_SKIP_MARKERS=seed` (`-m "not (seed)"`). So the broken `slow` marker no longer blocks dev iteration. It still matters for: `-m unit`/`-m integration` filterability (P5), the CI job split (Phase 3 Task 3.3), and `-m "not slow"` ad-hoc runs.

#### Related classification defects (still present)

1. **`unit` marker underused:** only ~5 files carry it; the 12+ `SimpleTestCase` files in `apps/core/tests/`, `apps/ads/tests/`, `apps/search/tests/`, `apps/categories/tests/` carry no marker at all → `-m unit` selects ~nothing useful instead of the fastest no-DB tier.
2. **Redundant `slow` on `concurrent` files:** the 4 bot async files (`test_ad_create.py`, `test_create_draft_ad.py`, `test_login_claim.py`, `test_claim_login_token.py`) carry `slow` + `concurrent` + `integration` — `slow` is redundant for the concurrent tier.
3. **Contradictory markers:** `test_ad_image_service.py` and `test_approve_ad_side_effects.py` carry `[django_db, slow, integration]` despite being near-unit integration tests — the `slow` tag is inaccurate.

### 2.3 Infrastructure & CI Assessment

| Artifact | Current state | Assessment |
|---|---|---|
| `docker/entrypoint-test.sh` | `uv run pytest ${PYTEST_OPTS:- --reuse-db --tb=short --durations=10}` + `PYTEST_SKIP_MARKERS` block (lines 47–52) | ✅ Has the seed fast-gate + `--reuse-db` default for local/Compose. ⚠️ No trailing newline (git diff). |
| `Makefile.ps1` | `test` (passes `PYTEST_SKIP_MARKERS=seed`), `test-all` (full suite), help + switch cases updated | ✅ Full parity with entrypoint (in working tree, **uncommitted** at HEAD). |
| `Makefile` (bash) | `test` passes `--env PYTEST_SKIP_MARKERS=seed` (fast gate); `test-all` target exists, in `.PHONY` + project group; default `--reuse-db` via entrypoint | ⚠️ **Fixed in working tree (uncommitted)**; ⚠️ **help text omits `test-all`** (not in `make help` list); ⚠️ `test-purge` comment at L105 references non-existent target |
| `.github/workflows/ci.yml` | line 85: `uv run pytest -m "not seed" -n auto --dist loadscope --tb=short --cov ...` | ❌ Runs pytest **directly** (bypasses entrypoint), no `--reuse-db` → rebuilds schema every run |
| `.github/workflows/ci-nightly.yml` | line 73: `uv run pytest -m "seed" --tb=short --cov ...` | ❌ No `--reuse-db`; single nightly job |
| `pyproject.toml` | 6 markers registered (`e2e` removed); `fail_under = 80` | `fail_under` measured per-subset until coverage is merged |
| `.ai/context/commands.md` | documents `--create-db` caveat + canonical root-conftest fixtures + `create_test_ad`, bot async-`user` exception | ⚠️ **Does NOT document `PYTEST_SKIP_MARKERS`** (gap); `--reuse-db` note is stale (contradicts entrypoint default) |
| `docs/99-agent/rules.md` | line 36: `e2e` removed note; line 38–41: canonical fixtures + `--create-db` required | ⚠️ Line 41 claims `--reuse-db` "is not used" — contradicts entrypoint `--reuse-db` default |

**CI bypass is the real gap.** The entrypoint ships `--reuse-db` + the seed fast-gate, but both CI workflows invoke `uv run pytest` **directly**, bypassing `entrypoint-test.sh` entirely — so CI neither reuses the schema nor goes through the fast-gate env-var logic. CI rebuilds the test schema on every run (the audit's original Task 3.1 gap, unchanged).

**Dead dependencies:** `radon` (pyproject.toml:204) has zero imports in `src/` (dead); `requests` (pyproject.toml:25 project + 207 dev) is duplicated across `[project].dependencies` and `[dependency-groups].dev`. Both inflate install time.

---

## 3. Problem Statement

| ID | Problem | Severity | Status |
|----|---------|----------|--------|
| P1 | `slow` marker semantic defect: 46 files blanket-tag ~719+ tests as `slow`, only ~40 are genuinely slow. | Medium → **Low (fast gate no longer depends on it)** | **OPEN** (re-scoped to marker hygiene) |
| P2 | `NameError: name 'AdStatus' is not defined` in `test_media_security.py` | CRITICAL | ✅ **Resolved** (imports at line 21; git clean) |
| P3 | xdist-only currency-cache race in `test_recompute_corrects_stale_normalized_value` | HIGH | ✅ **Resolved** (`_clear_rate_cache` fixture + fresh `PriceNormalizer` per `call_command`) |
| P4 | Autouse `load_catalog` fixture costs ~4s × 8 tests ≈ 28s per run | LOW | ✅ **Stale — resolved** (no such fixture exists; `load_catalog` is `builder.py:31`, a plain function) |
| P5 | `unit` marker underused (~5 files) + 12+ SimpleTestCase files unmarked + 5 bare `django_db` files misclassified; `-m unit` selects ~nothing | MEDIUM | **OPEN** |
| P6 | CI runs `uv run pytest` directly without `--reuse-db`; schema rebuilt every CI run | MEDIUM | **OPEN** |
| P7 | Dead/duplicate dev deps: `radon` (unused) + `requests` (duplicated) | LOW | **OPEN** |
| P8 (new) | Bash `Makefile`: `make test` ran full suite incl. ~17-min seed; `test-all` undefined | MEDIUM | ⚠️ **Fixed in working tree (uncommitted)** — target + `PYTEST_SKIP_MARKERS=seed` added; ⚠️ help text omits `test-all`; ⚠️ no trailing newline in entrypoint. See Phase E E.1. |

---

## 4. Proposed Solution

### Phase 0 — Completed Foundation (optimization-plan.md, commit `b62612` + `3ddc0b2`)

This phase is **DONE**. Recorded for context; no further work. It established: `e2e` removal, canonical `src/backend/conftest.py` fixtures + `create_test_ad` (referenced from 30+ files; the single remaining `def _make_ad` in `test_ad_localization.py` is an in-memory `SimpleTestCase` variant explicitly out of scope), 14 `TestCase`→pytest migrations (no `class.*TestCase` remains in `src/`), `test_decorators.py` (6 unit cases), `test_priority.py` public-API refactor (no `_get_priority_level`/`_estimate_confidence` refs in tests), 11 coverage additions (C.1–C.10), and docs (`commands.md` + `rules.md`). **This audit plan does not duplicate that work.**

### Phase 1 — Blocking Failures (P0) — VERIFICATION DONE

- **Task 1.1 — `AdStatus` import:** `test_media_security.py:21` imports `from apps.core.enums import AdStatus` at module scope; git clean. ✅ **Closed — not reproducible.**
- **Task 1.2 — Currency cache isolation:** `test_recompute_command.py:17-23` autouse `_clear_rate_cache` (`cache.clear()` before/after); `recompute_normalized_prices.py:75` fresh `PriceNormalizer` per `call_command`; `price_normalizer.py:40` instance-level `_rate_cache`. ✅ **Closed — not reproducible.**

### Phase 2 — Marker Reclassification (P1/P5; hygiene, NOT a fast-gate blocker)

The fast gate is now seed-based, so this phase no longer *unblocks* dev iteration. It *does* restore marker hygiene for `-m unit`/`-m integration` filterability and the CI job split (Phase 3). Apply **only** if/when Phase 3 Task 3.3 (CI split) becomes the goal — otherwise it is low-yield.

- **Task 2.1 — Audit the 46 module-level `slow` files:** keep `slow` **only** on genuinely slow tests (>5s, ~40); remove the blanket module-level `slow` from the ~679+ fast tests so they return to `-m "not slow"` selection.
- **Task 2.2 — Populate the `unit` marker** on the 12+ `SimpleTestCase` (no-DB) files so `-m unit` selects the full fast tier (~235) instead of ~5 files.
- **Task 2.3 — Tag the 5 bare `django_db` files** with `integration` (no `unit`/`slow`) for correct tier assignment.
- **Task 2.4 — Remove redundant `slow` from the 4 bot `concurrent` files** (`test_ad_create.py`, `test_create_draft_ad.py`, `test_login_claim.py`, `test_claim_login_token.py`); they carry `concurrent`+`integration`+`slow` — drop `slow`.
- **Task 2.5 — Correct contradictory `slow` tags** on `test_ad_image_service.py`, `test_approve_ad_side_effects.py`, `test_ad_constraints.py` (near-unit integration tests currently tagged `slow`).

**Validation:** `pytest -m unit --collect-only` grows from ~5 files to the no-DB tier; `pytest -m "not slow"` no longer excludes fast integration tests; pass count unchanged vs. before reclassification.

### Phase 3 — Infrastructure (P6/P7/P8)

- **Task 3.1 — Add `--reuse-db` to CI workflows.** The entrypoint already ships `--reuse-db` (and now `PYTEST_SKIP_MARKERS`); CI bypasses it. In CI the PostgreSQL `services.db` is an ephemeral container (fresh per run), so `--reuse-db` is safe. Add `--reuse-db` to:
  - `ci.yml:85` → `uv run pytest -m "not seed" -n auto --dist loadscope --tb=short --cov --durations=10 --cov-report=term --cov-report=xml --reuse-db`
  - `ci-nightly.yml:73` → `uv run pytest -m "seed" --tb=short --cov --durations=10 --cov-report=term --cov-report=xml --reuse-db`
- **Task 3.2 — `load_catalog` opt-in:** ✅ **Closed — stale.** No `load_catalog` autouse fixture exists (verified: `load_catalog` is `builder.py:31`, a catalog-loader function). No action required.
- **Task 3.3 — Split CI into parallel jobs:** (a) PR gate — `-m unit` + `-m integration`; (b) `-m concurrent`; (c) `-m settings`. **Depends on Phase 2** (correct markers define split boundaries). Keep dependent on 2.1–2.5.
- **Task 3.4 — Remove dead dependencies:** drop `radon` (pyproject.toml:204, zero imports in `src/`); remove the duplicate `requests` from `[dependency-groups].dev` (line 207), keeping the single `[project].dependencies` entry (line 25).
- **Task 3.5 — Bash `Makefile` parity:** ⚠️ **Fixed in working tree, NOT committed (HEAD `510b471`).** `make test` passes `--env PYTEST_SKIP_MARKERS=seed`; `test-all` target + `.PHONY` entry added. ⚠️ **Help text still omits `test-all`** in `make help`; ⚠️ `Makefile.ps1` parity edits are also uncommitted (the claim that "PS1 already had this" is inaccurate vs HEAD). ⚠️ `entrypoint-test.sh` has no trailing newline. See **Phase E E.1** for commit + help-text fixes.

### Phase 4 — Nightly & Coverage Hardening (P2)

- **Task 4.1 — Seed in nightly:** ✅ **Done.** `ci-nightly.yml:73` runs `-m "seed"` nightly with coverage artifact upload (`if: always()`, retention 7d). Nightly `concurrency.cancel-in-progress: false` ensures seed tests always complete.
- **Task 4.2 — Merge coverage reports across CI stages:** aggregate `.coverage`/`coverage.xml` from the PR-gate, concurrent, settings, and nightly jobs so `fail_under = 80` reflects the merged whole. **Open** — currently each job emits a separate blob. Depends on Phase 3 Task 3.3 (CI split) being live. Use `coverage combine` / `pytest-cov` `--cov-append` or a final merge job.

---

## 5. Phase E — Dev Workflow & Test-Infrastructure Hardening

**Rationale:** The optimization plan (Phase A–D) authored the *tests* and their conventions (`create_test_ad`, root-conftest fixtures, pytest-django migration, coverage gaps). **Phase E** owns the *dev-time tooling surface* that makes those tests runnable, fast, and reproducible: the Makefile/entrypoint fast-gate parity (previously claimed "fixed" in §4 Task 3.5 but **uncommitted** at HEAD `510b471`), CI `--reuse-db`, dead-dependency removal, and documentation reconciliation. It is the "E" continuing the optimization plan's A→D letter sequence; it is **not** a product phase (product plan uses Phase 1–4).

### E.1 — Commit parity edits + Makefile help-text fix

| Field | Value |
|-------|-------|
| **Type** | Durability / Commit |
| **Priority** | High |
| **Description** | Stage the working-tree changes to `Makefile`, `Makefile.ps1`, `docker/entrypoint-test.sh` (PYTEST_SKIP_MARKERS fast-gate + `test-all` target). **Fix:** add `test-all` to the bash `Makefile` `help` target (Test Environment block). **Fix:** add trailing newline to `entrypoint-test.sh`. Commit per repo style. |
| **Files** | `Makefile`, `Makefile.ps1`, `docker/entrypoint-test.sh` |
| **Depends on** | Nothing — edits already in working tree |
| **Acceptance criteria** | `make help` lists `test-all`; `git diff` shows only the Phase-E fixes (parity edits committed); `entrypoint-test.sh` ends with a newline. |

### E.2 — CI `--reuse-db`

| Field | Value |
|-------|-------|
| **Type** | Infrastructure |
| **Priority** | Medium |
| **Description** | Append `--reuse-db` to `ci.yml` L85 (`uv run pytest -m "not seed" …`) and `ci-nightly.yml` L73 (`uv run pytest -m "seed" …`). CI uses an ephemeral `services.db` (fresh PostgreSQL per run), so `--reuse-db` is safe — avoids schema rebuild every CI run. |
| **Files** | `.github/workflows/ci.yml`, `.github/workflows/ci-nightly.yml` |
| **Depends on** | audit D5/D6 (already decided) |
| **Acceptance criteria** | Both CI workflows include `--reuse-db` in their pytest invocation. |

### E.3 — Remove dead dependencies

| Field | Value |
|-------|-------|
| **Type** | Cleanup |
| **Priority** | Low |
| **Description** | Remove `radon` from `[dependency-groups].dev` (zero imports in `src/`). Remove duplicate `requests` from `[dependency-groups].dev` (keep single entry in `[project].dependencies` L25). |
| **Files** | `pyproject.toml` |
| **See also** | §4 Task 3.4 |
| **Acceptance criteria** | `grep -n "radon" pyproject.toml` returns nothing; `grep -n "requests" pyproject.toml` returns exactly one hit (in `[project].dependencies`). |

### E.4 — Documentation reconciliation

| Field | Value |
|-------|-------|
| **Type** | Documentation |
| **Priority** | High |
| **Description** | Fix `commands.md` `--create-db`/`--reuse-db` note — current text says "always `--create-db`, never `--reuse-db`" but the entrypoint defaults to `--reuse-db`. Add `PYTEST_SKIP_MARKERS` + `test`/`test-all`/`test-recreate` fast-gate documentation. Fix `rules.md` L41 "`--reuse-db` not used". Update `AGENTS.md` Quick Reference (fast-gate vs full suite vs fresh schema). Fix `architecture.md` Commands table (remove `uv run pytest <path>` which fails locally without Docker PG). |
| **Files** | `.ai/context/commands.md`, `docs/99-agent/rules.md`, `AGENTS.md`, `docs/99-agent/architecture.md` |
| **Acceptance criteria** | `grep PYTEST_SKIP_MARKERS .ai/context/commands.md` returns ≥1 match; `grep "test-all" AGENTS.md` returns ≥1; `grep "uv run pytest" docs/99-agent/architecture.md` returns 0. |

### E.5 — Marker hygiene (gated)

| Field | Value |
|-------|-------|
| **Type** | Marker cleanup |
| **Priority** | Medium |
| **Description** | Tasks 2.1–2.5: de-flagging `slow` from fast tests, populating `unit` on SimpleTestCase files, tagging bare `django_db` files with `integration`, removing redundant `slow` from `concurrent` files, correcting contradictory `slow` tags. **Only if** CI sub-setting (§4 Task 3.3) is adopted. |
| **Files** | ~46 test files + conftest |
| **Depends on** | Decision to adopt §4 Task 3.3 (CI split) |
| **Acceptance criteria** | `pytest -m unit --collect-only` selects the no-DB tier (~235 tests); `pytest -m "not slow"` no longer excludes fast integration tests. |

### E.6 — Coverage merge (Task 4.2)

| Field | Value |
|-------|-------|
| **Type** | CI hardening |
| **Priority** | Low |
| **Description** | Aggregate `.coverage`/`coverage.xml` across CI jobs (PR-gate, concurrent, settings, nightly) so `fail_under = 80` reflects the merged whole, not per-job subsets. |
| **Depends on** | §4 Task 3.3 (CI job split) |
| **Acceptance criteria** | Single merged coverage artifact in CI; `fail_under = 80` measured against the whole suite. |

**Dependency order:** E.1 (commit) → E.2 + E.3 + E.4 (parallel) → (E.5 if 3.3 adopted) → E.6 (after 3.3).

---

## 6. Expected Outcomes

| Metric | Current | After (projected, open tasks done) |
|---|---|---|
| Dev fast gate (`make test`) | ~300s (seed excluded via `PYTEST_SKIP_MARKERS`) | ~300s (unchanged — fast gate already works) |
| `make test` on bash `Makefile` | ~1,350s (full incl. seed — parity gap at HEAD) | ~300s after E.1 (committed WT fix; `make test` passes `PYTEST_SKIP_MARKERS=seed`) |
| CI PR gate (`ci.yml:85`) | >299s (rebuilds schema; no `--reuse-db`) | **~33s serial / ~12s with xdist** (after E.2 `--reuse-db` + Phase 2 markers) |
| Nightly seed | 1,054s (isolated nightly) | 1,054s (unchanged — already isolated) |
| xdist speedup (fast tiers) | ~3% | **2.8–3.9x** once Phase 2 markers correct the split boundaries (E.5) |
| `-m unit` selection | ~5 files | ~235 (after 2.2) |
| `slow` tag accuracy | ~719 falsely `slow` | ~40 genuinely `slow` (after 2.1) |
| `radon` install cost | present, unused | removed (after E.3) |
| Coverage `fail_under` basis | per-subset | merged whole (after E.6) |
| `commands.md` documents `PYTEST_SKIP_MARKERS` | ❌ absent | ✅ documented (after E.4) |
| `AGENTS.md` Quick Ref distinguishes fast-gate vs full | ❌ no | ✅ `make test` / `make test-all` / `test-recreate` (after E.4) |
| Parity edits reproducible from `git clone` | ❌ uncommitted | ✅ committed (after E.1) |
| `make help` lists `test-all` | ❌ omitted | ✅ listed (after E.1) |

---

## 7. Decision Log

| # | Decision | Rationale | Evidence |
|---|---|---|---|
| D1 | `test-optimization-plan.md` (Phase A–D) is COMPLETE & not re-worked here | Commit `b62612` + `3ddc0b2` implemented it; repo verified (e2e removed, `create_test_ad` used from 30+ files, no `TestCase` classes, coverage files present, docs updated) | §4 Phase 0 |
| D2 | Mark P1 (broken `slow`) as re-scoped, not blocked | Fast gate pivoted to `PYTEST_SKIP_MARKERS=seed` (seed-exclusion); `-m "not slow"` no longer gates dev iteration | §2.3, §4 Phase 2 lead |
| D3 | Both audit blockers (P2/P3) already resolved in repo | `AdStatus` imported at `test_media_security.py:21`; currency cache fixture at `test_recompute_command.py:17-23` + fresh `PriceNormalizer` per call | §3 P2/P3 |
| D4 | P4 (`load_catalog` autouse) closed as stale | No `load_catalog` autouse fixture; it is `builder.py:31` (a function) | §3 P4 |
| D5 | Add `--reuse-db` to CI (not the entrypoint — entrypoint already has it) | CI runs `uv run pytest` directly, bypassing the entrypoint; ephemeral `services.db` makes `--reuse-db` safe | §3 P6, §4 Task 3.1 |
| D6 | `--reuse-db` safe in CI, unsafe for local persistent DB | Ephemeral GH Actions PG service = fresh DB per run; local DB reuses stale schema (~527 errors) — already handled by `make test-recreate` / `commands.md` caveat | §2.3, §9, .ai/context/commands.md L58–61, docs/99-agent/rules.md L41 |
| D7 | Populate `unit`/`integration` markers for CI sub-set filtering | Defines the Phase 3 Task 3.3 job split boundaries; restores `-m unit` from ~5 files to the no-DB tier | §3 P5, §4 Phase 2 |
| D8 | Remove `radon` + duplicate `requests` | Zero imports for `radon`; `requests` duplicated across `[project]` and `[dependency-groups].dev` | §3 P7, §4 Task 3.4 |
| D9 | Keep seed in nightly, not PR gate | Seed ≈ 85% of runtime; nightly already runs `-m seed` | §2.1 |
| D10 | Merge coverage post-CI-split | `fail_under = 80` must reflect the whole suite, not per-job subsets | §4 Task 4.2 |
| D11 | Commit working-tree parity edits before declaring 3.5 done | "Fixed but uncommitted" is not durable — `git checkout HEAD` reproduces the gap; `commands.md` and `architecture.md` must reference the committed (post-E.1) state | §5 E.1, §2.3 (Makefile row), §10 L230 |
| D12 | `PYTEST_SKIP_MARKERS` is the fast-gate mechanism; it must be documented in `commands.md` | Researcher grep proved it is **absent** from `commands.md`; audit §2.3 falsely claimed it was documented | §5 E.4, §2.3 (commands.md row) |
| D13 | Phase E = dev workflow, not a product phase | Optim plan = Phase A–D (tests); high-level plan = Phase 1–4 (product); audit = Phase 0–4; Phase E = tooling/workflow layer above tests | §5 (rationale) |

---

## 8. Implementation Sequence (dependency-ordered)

1. **Phase E (dev workflow, open) — E.1–E.6:** Commit the working-tree parity edits (Makefile/entrypoint/Makefile.ps1) + add `test-all` to Makefile help + trailing newline. These must be committed first so the fast-gate is durable and reproducible. E.2 (CI `--reuse-db`), E.3 (dead deps), E.4 (docs) are independent and safe to do now.
2. **Phase 0 (done)** — optimization plan (commit `b62612`); no work remains.
3. **Phase 1 (done)** — blocker verification (P2/P3/P4); closed by repo inspection.
4. **Phase 2 (markers, open)** — Tasks 2.1–2.5 **must precede** Task 3.3 (CI split) and the CI `--reuse-db` gate relies on correct markers for subset selection. Low-urgency now (fast gate is seed-based), but required if CI sub-setting is adopted.
5. **Phase 3 (infra):** Task 3.5 (bash Makefile parity) — ⚠️ Fixed in working tree (**uncommitted**); commit → **E.1**. Task 3.1 (CI `--reuse-db`) is E.2. Task 3.4 (dead deps) is E.3. **Task 3.3 (CI split) depends on Phase 2** (E.5).
6. **Phase 4:** Task 4.1 (seed nightly) is **done**. Task 4.2 (coverage merge) is E.6; depends on Task 3.3.

**Recommended order:** E.1 (commit) → E.2 + E.3 + E.4 (parallel) → (2.1–2.5) → 3.3 → 4.2(E.6). Phases 2 and 3.3/E.5 are only justified if per-subset CI targeting is a goal; otherwise stop after E.1 + E.2 + E.3 + E.4.

---

## 9. Verification Note & Reconciliation

> **Reconciliation with `test-optimization-plan.md`:** `test-optimization-plan.md` (commit `b62612` "Test optimization plan: Phase A–D implementation" + `3ddc0b2` "refine ... and fix regressions") was **executed in full**. Verified in the current working tree:
> - **A.1** `e2e` marker removed — `pyproject.toml` markers hold only `unit, integration, seed, settings, concurrent, slow`. ✅
> - **A.2** Canonical root-conftest fixtures — `create_test_ad` lives at `src/backend/conftest.py:78` and is imported (`from conftest import create_test_ad`) by 30+ test files; `commands.md` §3 and `docs/99-agent/rules.md:38` document it, including the async-`user` exception in `src/telegram_bot/tests/conftest.py`. ✅
> - **A.3** Helper consolidation — `grep "def _make_ad|def _create_ad"` finds only the in-memory `SimpleTestCase` variant in `test_ad_localization.py` (documented out-of-scope); all DB-backed helpers replaced by `create_test_ad`. ✅
> - **B.1** TestCase migration — `grep "class.*\(TestCase\)"` returns 0 in `src/` (only `SimpleTestCase`/`Client`/`RequestFactory` remain). ✅
> - **B.2** `test_decorators.py` exists with `pytestmark = [pytest.mark.unit]`. ✅
> - **B.3** `test_priority.py` no longer references `_get_priority_level`/`_estimate_confidence` (refs now live only in `priority_calculator.py` production code). ✅
> - **C.1–C.10** corresponding test files/functions all present (`test_ad_constraints.py`, `test_ad_detail_queries.py`, `test_detail_context.py`, `test_approve_ad_side_effects.py`, `test_listings_sort.py` [DATE_OLD/NEW], `test_login.py` [hash-mismatch/sha256-stored/64-hex/consumed-cannot-reuse], `test_save_photo_integration.py`, `test_contact.py` cross-product, `test_trust_calculator.py` caps/floors, `test_priority_service.py` boundaries using achievable `{40→LOW, 60→MEDIUM, 80→HIGH, 100→HIGH}`). ✅
> - **D.2** `commands.md` and `docs/99-agent/rules.md` both updated. ✅
>
> **=> Nothing from `test-optimization-plan.md` is carried over — it is fully done.** This audit plan covers only the orthogonal strategy/infra gap (markers, CI `--reuse-db`, CI split, dead deps, coverage merge).

> **Reconciliation with the audit's original premises:**
> - **Fast gate (§2.1 "299s serial, 2 failures"):** the 2 failures (`NameError: AdStatus`, currency-cache race) are **resolved** — not reproducible in the current repo. The 299s serial is the pre-optimization baseline; the dev gate now excludes `seed` via `PYTEST_SKIP_MARKERS`, so local iteration is ~300s without the nightly seed bulk.
> - **CI (§2.3 / §9):** `ci.yml:85` = `uv run pytest -m "not seed" -n auto --dist loadscope --tb=short --cov --durations=10 --cov-report=term --cov-report=xml` and `ci-nightly.yml:73` = `uv run pytest -m "seed" --tb=short --cov --durations=10 --cov-report=term --cov-report=xml`. **Both run pytest directly, bypassing `entrypoint-test.sh`**, so neither inherits `--reuse-db` nor `PYTEST_SKIP_MARKERS`. This is the real gap (Task 3.1) — confirmed unchanged from the original audit; the entrypoint's `--reuse-db` does NOT extend to CI.
> - **`load_catalog` autouse (§3 P4):** the finding is **stale** — no `load_catalog` autouse pytest fixture exists; `load_catalog` is a plain function in `apps/categories/catalog/builder.py:31`. P4 closed, no action.
> - **`slow` marker (§2.2 / §3 P1):** the audit's framing assumed `-m "not slow"` was the fast gate. It is **not** — the fast gate is `-m "not (seed)"` (seed-exclusion). P1 is therefore **re-scoped**: it is no longer a fast-gate blocker, but remains a marker-hygiene item for `-m unit` filterability and the CI split. The 46 module-level `slow` tags are still present and still inaccurate.

> **`--reuse-db` caveat (from `.ai/context/commands.md`): `PYTEST_OPTS="--create-db ..."` is required for local persistent-DB runs; `--reuse-db` is unsafe locally (stale schema, ~527 errors) but safe in CI's ephemeral service DB. The `make test-recreate` escape hatch preserves the local fresh-schema path.**

---

## 10. Out of Scope

- **Rewriting tests** beyond marker edits (optimization plan C.1–C.10 already added the coverage tests).
- **Changing production code logic** (currency-cache behavior, `load_catalog`, moderation signals — only test isolation/markers are in scope here).
- **Removing genuinely slow tests** (seed + genuinely slow tests retained and moved to the correct tier, not deleted).
- **New abstractions or test frameworks** (existing pytest markers/plugins only).
- **The bash `Makefile` parity gap for `test-all`** — ⚠️ Fixed in working tree (**uncommitted**) — target + `PYTEST_SKIP_MARKERS=seed` + `.PHONY` added, but `make help` still omits `test-all` and `entrypoint-test.sh` has no trailing newline. Commit + help-text fix → **Phase E E.1**.
- **Non-test CI concerns** (build, lint, typecheck jobs in `ci.yml` are out of scope except where touched by the `--reuse-db`/split additions).
- **Migrating web/bot DB topology** (shared-DB two-process architecture unchanged).
