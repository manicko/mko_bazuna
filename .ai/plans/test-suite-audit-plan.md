# Test Suite Audit Plan — Mko Bazuna

**Date:** 2026-08-26  
**Status:** ✅ Audit Complete  
**Method:** Dual-phase — (1) static codebase analysis [Step 1], (2) runtime profiling in Docker [Step 2/3]  
**Reports:** `.ai/reports/test_suite_audit_step1_current_state.md`, `.ai/reports/test_suite_audit_step2_profiling.md`

---

## 1. Objective

Audit the Mko Bazuna test suite to identify performance bottlenecks, quantify their impact, and produce an evidence-based optimization plan. The prior optimization plan (`done/25_test-optimization-plan_done.md`, dated 2026-08-20) was written against a now-outdated codebase (934 tests) and contains estimates that no longer match reality. This audit re-measures everything against the current state.

---

## 2. Current State vs. Prior Plan

| Metric | Prior plan (Aug 20) | Current (Aug 26) | Delta |
|---|---|---|---|
| Total tests | 934 | **1091** (+157) | 16% growth |
| Test files | 73 | **89** (+16) | 22% growth |
| `test-all` estimate | ~18.75 min (1125s) | **~4.7 min (283s)** measured | **75% faster** than assumed |
| Seed tests | ~16 | **26** | +62% |
| Seed marker strategy | Per-test `seed` + `real_images` decorators (8 total) | **Class-level `@pytest.mark.seed` on 7 classes** + 1 method (26 tests) | Already implemented per prior T-02 |
| `--cov` in addopts | Was always-on (removed in T-03) | **Already removed** — `addopts = ["--import-mode=importlib", "-ra", "-q"]` | Already done |
| `--reuse-db` in entrypoint | Not present (added in T-04) | **Already present** — default `PYTEST_OPTS` includes `--reuse-db` | Already done |
| `--dist loadscope` in CI | `loadgroup` | CI still uses `--dist loadgroup`; **locally `loadgroup` is 15–20% faster** than `loadscope` | Strategy shift recommended |
| `slow` marker | Blanket module-level on 32 files | **55 files** (47 backend + 8 bot) | Worsened — now 62% of all test files |
| xdist in CI | `loadgroup`, `-n auto` | `loadscope`, `-n auto` | Already changed to loadscope (regressed!) |
| Nightly seed workflow | Proposed (T-06) | **Already implemented** (`ci-nightly.yml`, `-m seed`, sequential) | Already done — but **no xdist** |
| Dead deps removed | `factory-boy`, `model-bakery`, `hypothesis` | **Already removed** | Already done |
| Pre-existing failures | 7+ (exif, priority, search) | **32+ (25 template errors + 7 failures)** | Template errors are new |

**Conclusion:** Most of the prior plan's config-level optimizations (markers, `--reuse-db`, coverage gating, dead-dep removal, nightly workflow) have **already been implemented**. The remaining value of this audit is (a) confirming the actual measured timings, (b) identifying new regressions (template errors, `slow` marker bloat), and (c) recommending further optimizations that the prior plan did not address.

---

## 3. Current Suite Composition

### 3.1 Test inventory

| Tier | Marker | Count | Time (measured) | Notes |
|---|---|---|---|---|
| **Fast-gate** | `-m "not seed"` | **1025** | **85s** (xdist, `loadgroup`) | Includes unit + integration + settings + concurrent |
| **Seed nightly** | `-m seed` | **26** | **162–183s** (sequential) | No xdist in CI nightly config |
| **Unit** | `-m unit` | 93 | ~12s (serial subset) | Mostly pure-Python, no DB |
| **Settings** | `-m settings` | 3 | ~29s (subprocess) | Spawns Python interpreter per test |
| **Concurrent** | `-m concurrent` | 28 | <5s | Bot tests, `transaction=True` |
| **Total** | | **1091** | **~247s** (85 + 162) | Fast-gate + seed combined |

### 3.2 Marker status

| Marker | Registered | Applied at module level | Applied per-test | Files |
|---|---|---|---|---|
| `unit` | Yes | 22 | 0 | Backend + bot |
| `integration` | Yes | 58 (50 backend + 8 bot) | 4 | — |
| `seed` | Yes | 0 (never module-level) | 26 (7 class-level + 1 method) | `test_seed.py` only |
| `settings` | Yes | 1 | 0 | `test_settings_secrets.py` |
| `concurrent` | Yes | 7 (bot only, via `pytestmark.append`) | 0 | — |
| `slow` | Yes | **55** (47 backend + 8 bot) | 1 | 55 files = 62% of 89 test files |
| `real_images` | Yes | 0 | 0 | `test_seed.py` (applied but seed marker covers it) |
| `xdist_group` | Yes | 7 (bot only) | 0 | bot_concurrent |

**Problem:** The `slow` marker is applied to **55 of 89 files** (62%) at module level. Every test in those files inherits `slow`, making it impossible to exclude only genuinely slow tests. Per-test `slow` decorators exist in only 1 file (`test_auto_moderation.py:180`).

---

## 4. Runtime Profiling Results

### 4.1 Wall-clock timings (measured)

| Run | Command | Time | Tests |
|---|---|---|---|
| Fast-gate `--dist loadgroup` | `-n auto --dist loadgroup --reuse-db -m "not seed"` | **85s** | 1025 (989 passed, 25 errored, 7 failed) |
| Fast-gate `--dist loadscope` | `-n auto --dist loadscope --reuse-db -m "not seed"` | 100–104s | 1025 |
| Seed (sequential) | `-m seed --reuse-db` | **162s** (Run 2) / 183s (Run 1) | 26 (25 passed, 1 failed) |
| Unit-only serial | `-m "unit and not seed" --reuse-db` | 37s (incl. overhead) | ~93 |
| Settings serial | `-m settings --reuse-db` | 35s (incl. overhead) | 3 |
| Concurrent serial | `-m concurrent --reuse-db` | <5s (actual, within ~30s container run) | 28 |

**Container startup overhead:** 25–30s per fresh container (`uv sync` = 25–29s, DB connect = ~3s, `compilemessages` = 2–3s if entrypoint runs).

### 4.2 Fastest path for feedback

```
Fastest:  pytest -m "unit and not seed"   → ~12s (no DB, no xdist overhead)
Fast:     make test  (fast-gate)           → ~85s (xdist, 1025 tests)
Full:     make test-all (fast-gate + seed) → ~247s (no seed xdist)
```

### 4.3 Slowest 10 tests (from `--durations=20`)

| # | Duration | Test | Tier | Phase |
|---|---|---|---|---|
| 1 | 12.14s | `TestSeedCommandEnhanced.test_media_cleanup` | Seed | call (real image pipeline) |
| 2 | 8.33s | `TestAdGeneratorLeafOnly.test_full_seed_coverage` | Seed | call (also has coverage-gate failure) |
| 3 | 7.70s | `TestExpandButtons.test_expand_button_absent_for_leaf_category` | Fast-gate | setup (TRUNCATE) |
| 4 | 7.53s | `TestExpandButtons.test_expand_button_present_for_category_with_children` | Fast-gate | setup (TRUNCATE) |
| 5 | 6.85s | `TestBreadcrumbsRender.test_breadcrumb_shows_ancestor_chain` | Fast-gate | setup (TRUNCATE) |
| 6 | 6.73s | `TestBreadcrumbsRender.test_breadcrumb_empty_on_home` | Fast-gate | setup (TRUNCATE) |
| 7 | 6.72s | `TestImageGenerator.test_image_keys_have_correct_format` | Fast-gate | call (runs in fast-gate, not seeded) |
| 8 | 6.66s | `TestBreadcrumbsRender.test_breadcrumb_on_ad_detail` | Fast-gate | setup (TRUNCATE) |
| 9 | 6.61s | `TestImageGenerator.test_generates_ad_images` | Seed | call (full image pipeline) |
| 10 | 6.28s | `TestBreadcrumbsRender.test_breadcrumb_shows_root_category` | Fast-gate | setup (TRUNCATE) |

**Pattern:** 7 of the 10 slowest tests are in `setup` phase (TRUNCATE overhead from `django_db(transaction=True)`), not in test logic. The remaining 3 are genuinely CPU/IO-heavy (image processing).

---

## 5. Pre-existing Test Failures

| Category | Count | Root cause | Files affected |
|---|---|---|---|
| **Template `FileNotFoundError`** | **25 errors + 4 failures** | Test helpers reference templates at hardcoded `/app/src/backend/src/backend/templates/` paths that don't exist | `test_autocomplete_template.py` (12), `test_detail_context.py` (4 errors + 1 failure), `test_catalog_filters.py` (3 failures) |
| **Flaky currency tests** | 3 failures | Floating-point assertion mismatches, pass/fail inconsistently across runs | `test_price_normalizer.py` (3 tests) |
| **Seed coverage gate** | 1 failure | `test_full_seed_coverage` asserts 90% coverage but gets 87.7% | `test_seed.py` |

These are **not** introduced by the audit. They are pre-existing issues that affect CI reliability.

---

## 6. Key Findings

### Finding 1: The `make test-all` ~35 min estimate is 8.5× inflated

The `Makefile.ps1` help text documents `make test-all` as taking "~35 min." The actual measured time is **~247s (4.1 min)**. This discrepancy means:
- Developers may be avoiding the full suite unnecessarily
- CI timeout configurations may be over-provisioned
- The prior plan's urgency around the 1125s problem is overstated

### Finding 2: Seed nightly runs have no xdist

`.github/workflows/ci-nightly.yml` runs `pytest -m "seed"` sequentially with no `-n auto`. The seed tier takes 162–183s. Adding xdist would reduce this to ~25–40s, cutting the combined suite time from 247s to ~110s.

### Finding 3: `--dist loadgroup` is faster than `--dist loadscope` locally

Measured:
- `loadgroup`: **85s**
- `loadscope`: **100–104s**

This is a 15–20% speedup. The prior plan (T-10) changed CI to `loadscope`, but `loadgroup` is actually faster because it pins the 7 bot `concurrent` files to a single worker via `xdist_group("bot_concurrent")`, preventing cross-worker DB contention. The prior plan's regression to `loadscope` should be reverted.

### Finding 4: The `slow` marker has ballooned to 62% of test files

55 of 89 test files use module-level `slow`. This makes the marker useless for selective execution — you can't exclude `slow` tests without excluding most of the suite. The `slow` marker should be applied per-test, not per-module, or the `slow` filter should be removed entirely.

### Finding 5: 75% of slowest fast-gate tests are in setup, not logic

8 of the 10 slowest fast-gate tests spend their time in `setup` phase (TRUNCATE from `transaction=True`). This indicates that `django_db(transaction=True)` is too aggressive for tests that don't actually need cross-thread DB access.

### Finding 6: Container startup overhead is 30% of fast-gate time

The 85s fast-gate includes ~28s of fixed overhead (uv sync + DB connect). If the fast-gate is only 57s of actual test execution, then 33% of the time is overhead that can be eliminated by caching the uv sync / using a persistent container.

---

## 7. Optimized Recommendations

### P0 — Revert CI to `--dist loadgroup` (5 min)

**Change:** In `ci.yml` and `ci-nightly.yml`, change `--dist loadscope` → `--dist loadgroup`.

**Justification:** Measured 15–20% speedup (85s vs 100–104s) with loadgroup. The `xdist_group("bot_concurrent")` markers in 7 bot files ensure bot tests don't contend with parallel workers.

**Verification command:**
```bash
# Confirm loadgroup is faster
docker compose ... run --rm test -c 'uv run pytest -n auto --dist loadgroup --reuse-db -m "not seed" --tb=no -q'
# Expected: ~85s
```

### P0 — Add xdist to nightly seed runs (10 min)

**Change:** Add `-n auto` to the nightly seed test command in `ci-nightly.yml`.

**Before:**
```yaml
uv run pytest -m "seed" --tb=short --cov --durations=10 --cov-report=term --cov-report=xml --reuse-db
```

**After:**
```yaml
uv run pytest -m "seed" -n auto --dist loadscope --tb=short --cov --durations=10 --cov-report=term --cov-report=xml --reuse-db
```

**Expected savings:** 162s → ~30–40s (4× speedup with 8 workers).

**Risk:** Low — seed tests use `django_db` (not `transaction=True`) for most; the `_no_op_image_generator` autouse fixture patches the image pipeline.

### P1 — Fix template `FileNotFoundError` errors (4–6 hours)

**Problem:** 25 test errors + 4 failures caused by test helpers looking for template files at an incorrect path: `/app/src/backend/src/backend/templates/components/...`. The correct path should be `/app/src/backend/templates/components/...`.

**Root cause:** Likely a Django `TEMPLATES` setting misconfiguration in the test config — `BASE_DIR` or `APP_DIRS` is resolving incorrectly when running from the Docker container.

**Fix:** Investigate `config/settings/test.py` `TEMPLATES` DIRS configuration. The double `src/backend/src/backend/` path component suggests `BASE_DIR` is set to the project root (`/app`) but template dirs are defined relative to `src/backend/` without proper `BASE_DIR` anchoring.

**Verification:** All 25 errors disappear; 4 failures change to errors or pass.

### P1 — Remove blanket `slow` from bot test files (30 min)

**Problem:** All 7 bot test files apply `slow` at module level via `pytestmark`. This means all 80 bot tests (including fast async tests) are tagged `slow`.

**Fix:** Replace module-level `pytestmark = [pytest.mark.django_db(transaction=True), pytest.mark.slow, pytest.mark.integration]` with just `[pytest.mark.django_db(transaction=True), pytest.mark.integration]` in bot test files. Only apply `slow` to genuinely slow bot tests (if any).

### P1 — Cache `uv sync` in Docker image (1 hour)

**Problem:** Every fresh container pays 25–30s for `uv sync`. This is 30–35% of the 85s fast-gate time.

**Fix:** Modify the Dockerfile to run `uv sync --group dev` during image build (in a non-production stage), so the venv is pre-built. The entrypoint's `uv sync` then becomes a no-op (cached).

---

## 8. Optimization Impact Estimate

| Optimization | Time saved | Effort | Priority |
|---|---|---|---|
| Revert to `--dist loadgroup` | 15–20s per fast-gate run | 5 min | P0 |
| Add xdist to seed nightly | 120–150s per nightly | 10 min | P0 |
| Fix template path errors | Eliminates 25 error lines + 4 failures | 4–6 hr | P1 |
| Remove blanket `slow` from bot files | Enables selective bot test runs | 30 min | P1 |
| Cache uv sync in Docker image | 25–30s per container invocation | 1 hr | P1 |
| Reduce `transaction=True` where unnecessary | 5–10s per fast-gate run | 2–3 hr | P2 |

**Cumulative best case:** 85s → ~40s fast-gate, 162s → ~35s seed nightly. Total suite: ~75s (down from 247s = 3× faster).

---

## 9. Next Steps

1. **Execute P0 optimizations** (revert to `loadgroup`, add xdist to seed nightly) — these are pure config changes with immediate measurable impact.
2. **Investigate template path root cause** — this is the largest source of test failures and requires code investigation.
3. **Re-measure after each change** — use the same Docker container pattern to confirm timing improvements.
4. **Decompose remaining work into atomic tasks** in `.ai/tasks/` with clear acceptance criteria.

---

## 10. Files Modified/Created

| Action | Path |
|---|---|
| Created | `.ai/reports/test_suite_audit_step2_profiling.md` (this audit's runtime data) |
| Created | `.ai/plans/test-suite-audit-plan.md` (this file — the plan) |
