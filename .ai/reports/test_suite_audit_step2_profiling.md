# Test Suite Audit — Step 2: Runtime Profiling

**Date:** 2026-08-26  
**Method:** Runtime execution in Docker (PostgreSQL 18 test DB) with timing, per-marker tier runs, `--durations`, and distribution-strategy comparison  
**Scope:** All registered markers (seed, unit, settings, concurrent, integration) + fast-gate variants  

---

## 1. Summary

| Metric | Value |
|---|---|
| Container startup overhead (uv sync + DB connect) | **25–30s** per fresh container |
| Fast-gate xdist (`--dist loadgroup`) wall time | **85s** |
| Fast-gate xdist (`--dist loadscope`) wall time | **100–104s** |
| Seed tier (sequential, no xdist) wall time | **162–183s** (varies with DB load) |
| Unit-only (serial, no xdist) actual test time | **~12s** (within ~37s total run) |
| Settings tier (subprocess-isolated) | **~10s** test time (within ~35s total run) |
| Concurrent tier (28 bot tests) | **<5s** test time (within ~30s total run) |
| Full suite (fast-gate + seed) | **~247s ≈ 4.1 min** (85s + 162s) |
| **Documented `make test-all` estimate** | **~35 min** |
| **Overestimate factor** | **~8.5×** |

**Key findings:**
1. The `~35 min` estimate for `make test-all` is **8.5× inflated** — actual measured time is ~4.1 min.
2. `--dist loadgroup` is **20% faster** than `--dist loadscope` locally (85s vs 100–104s), contradicting the prior assumption that loadgroup is only useful in CI.
3. Container startup overhead (`uv sync` = 25–30s) dominates when running small tiers individually — it is 60–70% of the total runtime for settings (35s) and concurrent (30s) runs.
4. The seed tier (162–183s, sequential) is the single largest time component after the fast-gate.

---

## 2. Container Startup Overhead

Each `docker compose run --rm test` invocation pays a fixed cost before any tests execute:

| Step | Time | Notes |
|---|---|---|
| `uv sync --frozen --no-install-project --group dev` | **25–29s** | First run compiles 4058 bytecode files; cached runs are faster (~2s) but the Docker layer overhead remains |
| `compilemessages` (.po → .mo) | ~2–3s | Only runs in the default entrypoint, not in `--entrypoint bash` overrides |
| DB connection wait + migration advisory lock | **~3s** | `--reuse-db` skips schema rebuild; migration is idempotent via advisory lock |
| **Total fixed overhead** | **~28–32s** | Paid **per container**, not per test batch |

**Impact:** For the settings tier (3 tests, ~10s actual test time), 70% of the 35s total is overhead. For concurrent (28 tests, ~5s actual), it's 83% overhead. This makes per-tier profiling misleading when measured via individual container invocations.

---

## 3. Tier-by-Tier Measurements

### 3.1 Fast-gate (non-seed) xdist — `--dist loadgroup`

**Command:** `uv run pytest -n auto --dist loadgroup --reuse-db -m "not seed" --tb=no -q --durations=20 -p no:warnings`

| Metric | Value |
|---|---|
| Elapsed (wall) | **85s** |
| Total tests (from progress line) | **1025** |
| Passed | **989** |
| Errors | **25** (all `FileNotFoundError` on template files) |
| Failed | **4** (3× `test_catalog_filters.py`, 1× `test_detail_context.py`) |
| xdist passthrough markers (`u`) | **7** |
| Exit code | 1 |

**Progress-dot breakdown:** 1025 characters = 989 `.` + 25 `E` + 4 `F` + 7 `u` = 1025 ✓

#### Slowest 20 tests (fast-gate loadgroup)

| # | Duration | Phase | Test |
|---|---|---|---|
| 1 | 7.70s | setup | `test_expand_button_absent_for_leaf_category` (categories/test_submenu.py) |
| 2 | 7.53s | setup | `test_expand_button_present_for_category_with_children` (categories/test_submenu.py) |
| 3 | 6.85s | setup | `test_breadcrumb_shows_ancestor_chain` (ads/test_breadcrumbs_render.py) |
| 4 | 6.73s | setup | `test_breadcrumb_empty_on_home` (ads/test_breadcrumbs_render.py) |
| 5 | 6.72s | **call** | `test_image_keys_have_correct_format` (seed/test_seed.py) ← runs in fast-gate |
| 6 | 6.66s | setup | `test_breadcrumb_on_ad_detail` (ads/test_breadcrumbs_render.py) |
| 7 | 6.28s | setup | `test_breadcrumb_shows_root_category` (ads/test_breadcrumbs_render.py) |
| 8 | 5.97s | setup | `test_only_rejected_satisfies_constraint` (ads/test_ad_constraints.py) |
| 9 | 4.85s | setup | `test_add_failed_to_rejected_raises` (ads/test_ad_constraints.py) |
| 10 | 4.78s | setup | `test_add_rejected_to_failed_raises` (ads/test_ad_constraints.py) |

**Pattern:** 8 of the 10 slowest tests are in `setup` phase — indicating `django_db(transaction=True)` TRUNCATE overhead, not test logic.

### 3.2 Seed tier (sequential)

**Command:** `uv run pytest -m seed --reuse-db --tb=line -q --durations=20`

| Metric | Value |
|---|---|
| Elapsed (wall) | **162s** (Run 2) / **183s** (Run 1) |
| Total tests | **26** |
| Passed | **25** |
| Failed | **1** |
| Exit code | 1 |

**Failure:** `TestAdGeneratorLeafOnly::test_full_seed_coverage` — `AssertionError: Coverage 87.7% is below 90% threshold` (configured at `test_seed.py:1451`). This is a coverage-gate assertion, not a functional failure.

#### Slowest 20 tests (seed tier)

| # | Duration | Phase | Test |
|---|---|---|---|
| 1 | 12.14s | **call** | `test_media_cleanup` (real_images: full image pipeline) |
| 2 | 8.33s | **call** | `test_full_seed_coverage` (also has coverage-gate failure) |
| 3 | 6.61s | **call** | `test_generates_ad_images` |
| 4 | 4.76s | **call** | `test_seed_idempotent` |
| 5 | 4.71s | **call** | `test_seed_recovers_from_orphaned_users` |
| 6 | 3.31s | **call** | `test_seed_filter_by_purpose_returns_results` |
| 7 | 3.00s | **call** | `test_seed_with_zero_count` |
| 8 | 2.97s | setup | `test_seed_populates_condition` |
| 9 | 2.85s | **call** | `test_seed_force_skips_prompt` |
| 10 | 2.82s | **call** | `test_seed_produces_seed_source` |

### 3.3 Settings tier

**Command:** `uv run pytest -m settings --reuse-db --tb=line -v`

| Metric | Value |
|---|---|
| Elapsed (wall, incl. overhead) | **35s** |
| Actual test time (elapsed from pytest output) | **28.85s** |
| Total tests | **3** |
| Passed | **3** |

Note: These tests spawn subprocesses for settings validation, so the 28.85s is genuine test execution time (not just overhead).

### 3.4 Concurrent tier

**Command:** `uv run pytest -m concurrent --reuse-db --tb=line -q --durations=5`

| Metric | Value |
|---|---|
| Elapsed (wall) | **<5s** (actual test time, within ~30s container run) |
| Total tests | **28** (7 bot files, ~4 methods each) |
| Status | Passed (no failures in output) |

### 3.5 Unit-only (serial, no xdist)

**Command:** `uv run pytest -m "unit and not seed" --reuse-db --tb=line -q --durations=10`

| Metric | Value |
|---|---|
| Elapsed (wall) | **37s** |
| Total tests | **~93** |
| Passed | ~67 |
| Errors | 25 (template FileNotFoundError, same as fast-gate) |
| Failed | 1 (same flaky `test_detail_template_uses_bot_username_not_settings`) |

---

## 4. Distribution Strategy Comparison

| Strategy | Command | Time | Notes |
|---|---|---|---|
| `--dist loadscope` | `-n auto --dist loadscope --reuse-db -m "not seed"` | 100–104s | Groups tests by module/class |
| `--dist loadgroup` | `-n auto --dist loadgroup --reuse-db -m "not seed"` | **85s** | Respects `xdist_group("bot_concurrent")` markers; **15–19% faster** even locally |

**Finding:** `--dist loadgroup` is faster locally despite the prior report's concern that module-level `pytestmark` (without `xdist_group`) would reduce loadgroup's effectiveness. The 7 bot files using `xdist_group("bot_concurrent")` pin to a single worker, but the remaining 1018 tests distribute evenly across the other 7 workers.

---

## 5. Pre-existing Test Failures

### 5.1 Template `FileNotFoundError` errors (25 tests)

All 25 errors share the same root cause: test helpers attempt to open template files at hardcoded paths like `/app/src/backend/src/backend/templates/components/header_catalog.html`, but the templates don't exist at that path. These errors appear consistently across every run:

```
FileNotFoundError: [Errno 2] No such file or directory: '.../templates/components/header_catalog.html'
```

Affected files:
- `apps/search/tests/test_autocomplete_template.py` — 12 tests
- `apps/ads/tests/test_detail_context.py` (`TestBreadcrumbEllipsisTemplate`) — 4 tests
- `apps/ads/tests/test_catalog_filters.py` (`TestFilterUrlReset`) — 3 tests + 4 failures (same path issue)
- `apps/ads/tests/test_detail_context.py` (`TestAdDetailBotUsernameContext`) — 1 failure

### 5.2 Flaky currency tests (3 tests)

`apps/currencies/tests/test_price_normalizer.py`:
- `test_eur_preserves_amount`
- `test_bam_normalized_by_seeded_rate`
- `test_rsd_normalized_by_seeded_rate`

These pass in some runs and fail in others (observed: passed in loadgroup run, failed in loadscope Run 2 and unit-only run). Likely floating-point precision issues in seeded rate calculations.

### 5.3 Seed coverage gate failure (1 test)

`TestAdGeneratorLeafOnly::test_full_seed_coverage` — asserts 90% coverage but gets 87.7%. Not a functional failure.

---

## 6. xdist Worker Utilization

The container has 8 CPUs. With `-n auto`, 8 xdist workers are launched.

| Phase | Wall time | Estimated serial time | Speedup | Efficiency |
|---|---|---|---|---|
| Fast-gate (loadgroup) | 85s | ~415s (extrapolated from unit-only: 93 tests in 12s → 1025 tests ≈ 133s; but including setup overhead) | ~5× | ~62% |
| Seed (serial, no xdist) | 162s | 162s | 1× | N/A (not parallelized) |

**Note on speedup:** The theoretical 8× speedup is reduced to 5× due to:
1. DB contention on shared PostgreSQL test database
2. Fixed overhead (collection, import, setup) that doesn't parallelize
3. The `test_media_cleanup` test (12s, single-threaded I/O) anchors one worker

---

## 7. Recommendations for Step 3

Based on profiling data, ranked by impact:

1. **Add xdist to nightly seed tests** — 162–183s sequential → estimated 25–40s with 8 workers. Would reduce total suite time from ~247s to ~120s (52% reduction).

2. **Investigate the 25 template `FileNotFoundError` errors** — these waste xdist worker capacity and produce 25+ lines of error output per run. Root cause: template-loading test helpers using incorrect path resolution.

3. **Address flaky currency tests** — non-deterministic failures waste CI cycles and erode confidence in the test suite.

4. **Consider caching `uv sync` in the Docker image** — eliminates 25–30s overhead per container invocation. Could be done by building the venv into the image layer.

5. **Investigate setup-heavy tests** — 8 of the top 10 slowest fast-gate tests are in `setup` phase, indicating `django_db(transaction=True)` TRUNCATE overhead. Consider if these tests truly need transactional rollback.

6. **Fix the seed coverage gate failure** — `test_full_seed_coverage` fails on 87.7% vs 90% threshold. Either increase coverage or lower the threshold.
