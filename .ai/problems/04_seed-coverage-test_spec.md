# Specification: Seed Coverage Test Reliability

**Status:** Final — incorporating PO decisions (Q1–Q4) and researcher validation findings  
**Version:** 1.0  
**Date:** 2026-09-02  
**Source Problem:** `.ai/problems/Problem_03.md` (RU)  
**Target Files:** `src/backend/apps/seed/tests/test_seed.py` (class `TestAdGeneratorLeafOnly`, method `test_full_seed_coverage`)  

---

## 1. Problem Summary

The nightly seed-coverage test `test_full_seed_coverage` (seed marker, nightly-only)
**fails deterministically** at 87.7% coverage against a ≥90% threshold. This is a
**pre-existing failure — not caused by Plan 18** — confirmed to reproduce on the
original, unmodified code. The task is to study the failure, review modern practices
for building such tests, and develop a high-quality / reliable variant of the test
(not a production seed-flow change).

The test seeds 600 ads with `faker_seed: 42` (default config) and 60% published-status
weight, then asserts that ≥90% of the 171 leaf categories have at least one **published**
seed ad. The deterministic seed-42 outcome is 87.7% (~150 of 171 categories), below the
90% threshold (~154 categories).

---

## 2. Facts (Verified)

### 2.1 The test

From `src/backend/apps/seed/tests/test_seed.py` (lines 1348–1450):

```python
@pytest.mark.seed
class TestAdGeneratorLeafOnly:
    @pytest.fixture(autouse=True)
    def _setup_class(self, db: None) -> None:
        from apps.categories.catalog.builder import load_catalog
        CATALOG_PATH = (
            Path(__file__).resolve().parents[2]
            / "categories" / "catalog" / "categories.yaml"
        )
        load_catalog(CATALOG_PATH)

    def test_full_seed_coverage(self) -> None:
        """Full seed with 600 ads covers >=90% of leaf categories with ads."""
        out = StringIO()
        call_command(
            "seed",
            "--users=10",
            "--ads=600",            # ← 600 total ads
            "--force",
            "--analytics=False",
            stdout=out,
        )
        total_leaf = Category.objects.filter(children__isnull=True).count()
        covered_slugs = set(
            Ad.objects.filter(
                source=AdSource.SEED,
                status=AdStatus.PUBLISHED,
                category__children__isnull=True,
            ).values_list("category__slug", flat=True)
        )
        coverage_pct = len(covered_slugs) / total_leaf * 100
        assert coverage_pct >= 90.0, (
            f"Coverage {coverage_pct:.1f}% is below 90% threshold"
        )
```

### 2.2 Seed configuration

From `apps/seed/config/seed.default.json`:
- `faker_seed: 42` (deterministic)
- `status_distribution`: `published 0.60, archived 0.20, draft 0.10, on_moderation 0.05, rejected 0.05`
- `analytics.days_back: 90, views_per_ad_per_day: {min: 0, max: 15}`

With 600 ads at 60% published → **expected 360 published ads**.

### 2.3 Category assignment mechanism

From `apps/seed/generators/ads.py`:
- **Line 402:** `category = self._rng.choice(self.categories)` — **uniform random**, no
  stratification or per-category floor. `self.categories` is the full 171-element leaf
  list (`__init__` line 241; populated by `SeedService.run` line 108–109).
- **Lines 398–507:** `generate()` draws category → user → city → status → (conditional)
  purpose → price → 3× template-fill (each consuming multiple `self._rng` draws at
  `ads.py:352-359`). Only the **category** draw is uniform over 171; all others are
  independent by construction.
- **BaseGenerator** (`base.py:41`): `self._rng = random.Random(config.get("faker_seed", 42))`
  — a **single shared, sequential RNG stream** feeding all generators.

### 2.4 Leaf category count

- 171 leaf categories (parent categories with `children__isnull=True`).
- Verified by: `test_load_category_fixtures_returns_leaf_only` (`test_seed.py:1374`,
  `assert len(categories) == 171`) and YAML census (`categories.yaml` = 171 leaf slugs).

### 2.5 Status / purpose mechanics (relevant to coverage)

- Status is drawn via `_weighted_status` (`ads.py:536-542`) using the config weights.
- `listing_purpose` resolution (`ads.py:432-441`) only affects price (give-away → price 0,
  `ads.py:560-562`), **not** category assignment.
- The `charity` category resolves to purpose `give-away` exclusively (`categories.yaml:786`);
  its ads are free but still count toward coverage if published.

### 2.6 Test environment / markers

From `pyproject.toml` (lines 171-180) and `docs/99-agent/rules.md` (lines 36-51):
- Module-level `pytestmark = [pytest.mark.django_db, pytest.mark.slow, pytest.mark.integration]`
  (`test_seed.py:35`).
- `test_full_seed_coverage` is additionally within `@pytest.mark.seed` (`test_seed.py:1427`
  class-level mark).
- **`seed` marker = nightly-only.** `make test` (fast gate) runs with
  `PYTEST_SKIP_MARKERS=seed` → entrypoint appends `-m "not (seed)"`, **excluding all seed
  tests**. `make test-all` (~35 min) includes them.
- `TestSeedCommand` (`test_seed.py:455`) and `TestSeedCommandEnhanced` (`test_seed.py:897`)
  are also `@pytest.mark.seed`; `TestLeafCategoryFiltering` and `TestAdGeneratorLeafOnly`
  (`test_seed.py:1348, 1389`) are also `@pytest.mark.seed`.

### 2.7 Seed image stub (affects runtime, not coverage)

From `apps/seed/tests/conftest.py` (lines 36-46): an autouse fixture
`_no_op_image_generator` patches `seed_service.ImageGenerator` to a no-op stub **unless**
the test carries `@pytest.mark.real_images`. `test_full_seed_coverage` has no
`real_images` mark → the expensive photo pipeline (manifest preprocessing + SHA-256
backfill, `seed_service.py:160-174`) is **mocked out**. Runtime is dominated by
ad generation + DB writes, not image processing.

### 2.8 Researcher findings (validated)

Full assessment in `.ai/research/04_seed-coverage_research.md`. Key validated facts:

| Metric | Value | Source |
|---|---|---|
| Expected coverage (600 ads, 360 published, 171 cats) | **87.89%** (~150 cats) | Coupon collector: 171·(1−(170/171)^360) |
| σ of coverage (Monte Carlo, 200k trials) | **≈2.11 pct-points** | Researcher sim |
| P(coverage ≥ 90%) with 360 published | **17.84%** (exact) / 18.71% (MC) | Inclusion-exclusion + MC |
| Seed-42 realized coverage | **87.7%** (≈ mean / MC-median) | Reported in Problem_03.md |
| Gap from mean to 90% threshold | 1.05σ | 90% − 87.89% = 2.11pp; σ ≈ 2.11pp |
| Published ads for ≥90% @ ≥95% prob | **448** | 448→95.02% |
| Published ads for 100% @ ≥95% prob | **1384** | 1384→95.02% |
| Expected coverage at 1200 ads (720 published) | **≈98.5%** | 171·(1−(170/171)^720) |
| Margin above 90% at 1200 ads | **~9σ** | (98.5−90)/0.56 ≈ 9 |
| `pytest-randomly` / `rerunfailures` installed | **No** | `pyproject.toml` deps; none present |
| Reruns would help | **No** (deterministic seed+order) | Same seed reproduces 87.7% failure |

**Root-cause conclusion (HIGH confidence):** the test fails because the ≥90% threshold
exceeds the *expected* coverage (87.89%) under uniform random assignment of 360 published
ads to 171 categories — a coupon-collector budget that is mathematically too small. The
test is **deterministic-but-fragile**: under fixed `faker_seed: 42` and MPTT's deterministic
category ordering, coverage is reproducibly ~87.7%, but inserting a single new
`self._rng.choice()`/`self._choices()` call anywhere in the per-ad loop shifts the shared
RNG stream and can flip the covered set by O(σ) ≈ ±2 categories — i.e. a change elsewhere
could push coverage above or below 90%.

---

## 3. Product Owner Decisions

| Q | Question | Answer | Implication |
|---|----------|--------|-------------|
| Q1 | What coverage target should the test assert? | **(A) Keep ≥90%** as the target, rendered deterministic via sufficient seed volume. Do not lower to 80–85% (weakens the representativeness contract); do not raise to 100% (over-engineering for a nightly smoke test). | The asserted invariant "seed data demonstrates ≥90% of catalog categories with published ads" is preserved. |
| Q2 | Where should the fix live? | **(A) Test-only.** No production seed-flow change. The generator's uniform-random category assignment is intentional and used by dev/CI/prod seed paths; altering it risks distribution distortion (60/20/10/5/5 status weights) and ripples to every seed consumer. | Changes are confined to `test_full_seed_coverage` / its configuration. Production `apps.seed` behavior is untouched. |
| Q3 | If test-only, which mechanism? | **(A) Bump `--ads` 600→1200** at `test_seed.py:1433`. This yields ~720 published ads → E[coverage] ≈ 98.5%, ~9σ above the 90% threshold → deterministic-looking reliability for seed 42 (and all seeds). | One-line change. Keeps the meaningful ≥90% assertion. Eliminates fragility: even a 2-category RNG shift has no realistic chance of breaching threshold. |
| Q4 | How is "covered" defined — published ads only, or all seed ads? | **(A) Published ads only** (current semantics). A category visible only in draft/archived status is not demonstrable to buyers in the demo. | No change to the coverage query at `test_seed.py:1440-1446` (filter on `status=AdStatus.PUBLISHED` and `category__children__isnull=True`). |

**Recommended fallback (Q3-alternative, if 600 ads must be preserved):** Option 1b —
a dynamic, coupon-collector-derived threshold:
`expected_pct = 100 · 171·(1−(170/171)^(ads·0.6)) / 171`;
`assert coverage_pct >= expected_pct − 3·σ_pct` (σ_pct ≈ 2.11 at the 360-published regime →
≈81.6% bound). This is the most statistically *honest* formulation but adds math to the
test and weakens the explicit 90% contract; recommended **only** if the 1200-ad bump is
rejected.

---

## 4. Conceptual Development Tasks

### Task 1 — Make seed-coverage test deterministic (Primary, Q3=A)

**Purpose:** Eliminate the coverage shortfall so `test_full_seed_coverage` passes reliably
and is no longer fragile to upstream RNG-stream shifts.

**Expected outcome:** The test passes deterministically at seed 42 (and with high
probability for any seed), asserting ≥90% published-coverage of 171 leaf categories.

**Dependency:** None (test-only).

**Change:** `test_seed.py:1433`, `--ads=600` → `--ads=1200`.

**Why it works:** 720 published ads (60% of 1200) → E[coverage] ≈ 168.5/171 ≈ 98.55%,
σ ≈ 0.56 pp → threshold 90% sits ~9σ below the mean. The probability of seed 42 (or any
seed) falling below 90% is effectively zero.

### Task 2 — (Contingency) Dynamic statistical threshold (Q3 fallback)

**Purpose:** If the ad-count bump is rejected, replace the hardcoded 90% bound with a
threshold derived from the coupon-collector expectation for the actual ad count.

**Expected outcome:** The assertion adapts to whatever `--ads` value is used and never
fails under normal variance.

**Dependency:** Task 1's approach rejected by PO.

**Change:** Compute `published = ads · published_weight`, `expected_distinct =
171·(1−(170/171)^published)`, `threshold = expected_distinct − 3·σ`. Assert
`len(covered) >= threshold`.

### Task 3 — (Contingency) Generator-level stratification (Q2=B, not recommended)

**Purpose:** If 100% deterministic coverage is required (e.g., downstream tests need every
category represented), introduce a guaranteed minimum published ad per category in the
generator.

**Expected outcome:** Every leaf category has ≥1 published seed ad; coverage = 100%.

**Dependency:** PO overrides Q2 to (B). Requires a new `generate()` parameter + config key
+ remainder-weight rebalancing to preserve the 60% published aggregate.

**Change:** `ads.py` `generate()` — phase 1 guarantees 1 forced-published ad per category;
phase 2 fills the remainder with reweighted uniform random. **NOT RECOMMENDED** per Q2=A.

### Task 4 — Guard against future fragility (latent, optional)

**Purpose:** Address the latent ordering smell (`seed_service.py:283` returns leaf
categories with no explicit `order_by`, relying on MPTT's implicit tree ordering) and
the shared-RNG brittleness.

**Expected outcome:** The test's category-input order is explicitly stable and the test
documents its RNG fragility so future contributors understand the failure mode.

**Dependency:** None (independent of Tasks 1–3).

**Change:** Add an explicit `.order_by("slug")` or `.order_by("id")` in the test's
assertion query (do **not** change `seed_service.py:283` — that's production seed order);
add a comment in the test noting the coupon-collector rationale and the fragility of the
shared `self._rng` stream.

---

## 5. Analysis of Approaches

### Root cause (the math)
With `n = 171` categories and `m = 360` published ads (60% of 600, uniform assignment):
- **E[coverage] = 171 · (1 − (170/171)^360) = 150.30 categories = 87.89%**
- σ ≈ 2.11 percentage-points (Monte Carlo, 200k trials)
- The 90% threshold (≈154 categories) is **1.05σ above the mean** → only ~17.8% of seeds
  reach it; seed 42's 87.7% sits essentially at the mean/median.
- **The failure is arithmetic, not stochastic.** Raising `--ads` to 1200 gives
  `m = 720` → E[coverage] ≈ 98.55%, σ ≈ 0.56 pp → 90% is ~9σ away → effectively
  zero failure probability.

### Why it is "fragile" (the flakiness mechanism)
1. **Threshold too close to the mean** (1.05σ). Any change shifting seed-42's realized
   coverage by ≥4 categories (≈1.2 pp) flips pass↔fail.
2. **Shared sequential RNG** (`base.py:41`). `generate()` draws category first each
   iteration (`ads.py:402`) then ~18 more `self._rng` draws before the next category. A
   single new `self._rng.choice()`/`choices()` call inserted anywhere in the per-ad loop
   re-ranks every subsequent category → covered set changes by O(σ). (Draws via
   `self.faker.random_int()` use Faker's *separate* RNG and do **not** perturb
   `self._rng`. So fragility targets new `self._rng.*` calls, not faker calls.)

### Modern best-practice alignment (researcher validated)

| Strategy | Fits this test? | Verdict |
|---|---|---|
| `pytest-rerunfailures` `@pytest.mark.flaky(reruns=N)` | **No** — reruns reproduce identical 87.7% (deterministic seed + MPTT order) | Ruled out |
| `pytest-randomly` (random per-run seed) | Not installed; would *expose* the 17.8% pass rate | Not a fix |
| `xfail(strict=False)` quarantine | Tactical bandage only; masks rather than fixes | Rejected (per Q2=A) |
| Lower threshold to 80%/85% (static) | Works, but weakens the 90% contract | Rejected (per Q1=A) |
| Dynamic statistical threshold (Option 1b) | Principled; adapts to ad count | Fallback only |
| Raise `--ads` to 1200 (Option 2) | Test-only, preserves ≥90%, ~9σ margin | **Recommended (Q3=A)** |
| Generator stratification (Option 3/4) | Deterministic 100% but production-wide change + distribution distortion | Rejected (per Q2=A) |

**Project convention supports the test-only approach.** Seed tests are already
nightly-only (`@pytest.mark.seed`, excluded by `make test`'s
`PYTEST_SKIP_MARKERS=seed`). They never block PR iteration; they are a nightly smoke
test of seed representativeness. Therefore the acceptable bar is reliability within the
nightly run with minimal maintenance — favoring a one-line test change over a production
generator change.

---

## 6. Confirmed Requirements

| Req ID | Requirement |
|---|---|
| R-COV-01 | `test_full_seed_coverage` must pass deterministically at `faker_seed: 42` (and with high probability for any seed). |
| R-COV-02 | The test must assert ≥90% of 171 leaf categories have ≥1 **published** seed ad (Q1=A, Q4=A). |
| R-COV-03 | The fix must be **test-only** — no change to `AdGenerator`, `SeedService`, `seed.default.json`, or `categories.yaml` (Q2=A). |
| R-COV-04 | The fix must not distort the documented status distribution (60/20/10/5/5) in dev/CI/prod seed runs. |
| R-COV-05 | The test must remain `@pytest.mark.seed` (nightly-only) and excluded from the fast gate (`make test`). |
| R-COV-06 | The test must remain `@pytest.mark.slow` and `@pytest.mark.integration` (module-level `pytestmark` at `test_seed.py:35`). |
| R-COV-07 | The fix must not break or alter the assertions of any other existing test. |

---

## 7. Acceptance Criteria

### Primary (Q3=A → bump `--ads`)

- [ ] `test_full_seed_coverage` is updated: `--ads=600` → `--ads=1200` at `test_seed.py:1433`.
- [ ] At seed 42, coverage ≈ 98.5% (> 90% threshold) — test passes deterministically.
- [ ] The test still asserts `coverage_pct >= 90.0` (threshold unchanged).
- [ ] The test still filters on `status=AdStatus.PUBLISHED` and `category__children__isnull=True`.
- [ ] The test remains `@pytest.mark.seed`, `@pytest.mark.slow`, `@pytest.mark.integration`, `@pytest.mark.django_db`.
- [ ] All existing tests still pass: `make test` (fast gate, excludes seed) and the full
      seed suite (`make test-all`) including `test_full_seed_coverage` itself.

### Contingency (if Q3 rejected → Option 1b dynamic threshold)

- [ ] Replace the hardcoded `90.0` bound with a coupon-collector expectation:
      `published = 600 · 0.60`; `expected = 171·(1−(170/171)^published)`;
      `threshold = expected − 3σ` (σ ≈ 2.11 pp at this regime).
- [ ] Test passes deterministically at seed 42 (~87.7% vs ~81.6% bound).

---

## 8. Technical Requirements

### 8.1 Test change (primary)

**File:** `src/backend/apps/seed/tests/test_seed.py`, `test_full_seed_coverage` (line 1433)

```python
# BEFORE
call_command(
    "seed",
    "--users=10",
    "--ads=600",
    ...
)

# AFTER
call_command(
    "seed",
    "--users=10",
    "--ads=1200",
    ...
)
```

No other line in the method changes. The assertion (`coverage_pct >= 90.0`) and the
coverage query (`test_seed.py:1438-1446`) are unchanged.

### 8.2 Contingency change (Option 1b)

If the ad-count bump is rejected, the assertion block becomes:

```python
total_leaf = Category.objects.filter(children__isnull=True).count()
covered_slugs = set(
    Ad.objects.filter(
        source=AdSource.SEED,
        status=AdStatus.PUBLISHED,
        category__children__isnull=True,
    ).values_list("category__slug", flat=True)
)
coverage_pct = len(covered_slugs) / total_leaf * 100

# Coupon-collector-aware threshold (Option 1b fallback):
# Expected distinct categories for m published draws over n=171:
published_ads = int(1200 * config_status_weights["published"])  # 720
n_leaf = 171
expected_distinct = n_leaf * (1 - ((n_leaf - 1) / n_leaf) ** published_ads)
expected_pct = expected_distinct / n_leaf * 100
sigma_pct = 0.56  # at m=720 (MC); ≈2.11 at m=360
threshold = expected_pct - 3 * sigma_pct
assert coverage_pct >= threshold, ...
```

*(Contingency only — not applied under Q3=A.)*

### 8.3 Optional hardening (Task 4)

Add a comment above the assertion documenting the rationale:

```python
# Coverage invariant: >=90% of 171 leaf categories have a published seed ad.
# 600 ads × 60% published = 360 published → E[coverage] = 87.9% (below
# threshold). Bumped to --ads=1200 (→ ~720 published, E[coverage] ≈ 98.5%,
# ~9σ above 90%) for deterministic reliability. See .ai/research/04_seed-coverage_research.md.
```

---

## 9. Assumptions

1. **The 60% published weight is fixed** by `seed.default.json` and is not overridden by
   the test (the test passes no `--status-distribution`, so `seed_service.py:81` keeps the
   config default). 360 published = 600 × 0.60; 720 published = 1200 × 0.60.
2. **Category assignment stays uniform random.** `AdGenerator.generate()` line 402 draws
   `self._rng.choice(self.categories)`. Under Q3=A (test-only), the generator is not
   modified, so the coupon-collector math holds.
3. **The image pipeline is mocked** for this test (`conftest.py:36-46`, no
   `@pytest.mark.real_images` on `test_full_seed_coverage`), so increasing `--ads`
   600→1200 adds only ad-generation + `bulk_create` cost (negligible at nightly scale;
   analytics skipped via `--analytics=False`).
4. **`seed.default.json` is the config the test uses.** The test invokes `call_command`
   which constructs `SeedService()` → `_load_config()` reads `seed.default.json`
   (`seed_service.py:35,49`). The `faker_seed: 42` and status weights come from this file.
5. **Category ordering is stable.** `_load_category_fixtures` (`seed_service.py:283`)
   returns `Category.objects.filter(children__isnull=True)` with no explicit `order_by`;
   django-mptt's `TreeManager` implicitly orders by `(tree_id, lft)`. This is treated as
   stable (latent smell documented in Task 4, but not the active cause).
6. **`status=AdStatus.PUBLISHED`** is the correct "buyer-visible" semantics for coverage
   (Q4=A). Draft/archived/on-moderation/rejected ads are not visible buyers.

---

## 10. Constraints

1. **Nightly-only scope:** The test is `@pytest.mark.seed` — excluded from `make test`
   (fast gate). Changes are validated only in `make test-all` (~35 min). The fix must not
   regress the fast gate.
2. **No production seed behavior change:** Per Q2=A, `apps.seed` production code
   (`AdGenerator`, `SeedService`, `seed.default.json`, `categories.yaml`) must not be
   altered for this test.
3. **Determinism:** `faker_seed: 42` must continue to produce reproducible seed output
   (`test_deterministic_*` tests at `test_seed.py:42, 92, 853`). The ad-count bump
   changes *how many* ads are generated, not *whether* output is reproducible.
4. **Status distribution preservation:** No change may distort the 60/20/10/5/5 weights.
5. **No new dependencies:** `pyproject.toml` must not gain pytest-rerunfailures,
   pytest-randomly, or other flaky-test plugins (none are currently installed; the
   deterministic seed makes reruns pointless anyway).

---

## 11. Risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| 1200 ads is noticeably slower in nightly suite | Low | Low | Image pipeline already mocked; `--analytics=False`; measured impact expected <2s beyond the 600-ad baseline. If runtime regresses, fall back to Option 1b (dynamic threshold). |
| Ad-count bump changes other assertions | Very Low | Low | No other test uses `--ads=600`; each seed test passes its own `--ads` (5, 10, 40, 500, 600). Verified by grep. |
| 1200 ads still doesn't reach 90% for some seed | Effectively Zero | Critical | At m=720 published, P(coverage<90%) ≈ 0 (9σ margin). Seed 42 is representative, not a tail event. |
| Generator change is needed later (full coverage) | Low | Medium | Documented as Task 3 contingency / Q2=B path. Out of scope per Q2=A. |
| MPTT version change shifts category order | Low | Low | Latent; documented in Task 4. Not the active cause. Adding explicit `order_by` in the test's assertion query hardens against it without changing production. |
| Coverage assertion becomes stale if categories count changes | Low | Low | The test dynamically computes `total_leaf` (`test_seed.py:1438`) from the DB — it auto-scales with category count. The 90% threshold is a ratio, not an absolute. |

---

## 12. Open Questions

1. **Is 1200 ads acceptable in the nightly suite?** (Resolved Q3=A — yes; runtime impact negligible with mocked images + no analytics.)
2. **Should a dynamic threshold (Option 1b) be implemented *in addition* as a permanent guard?** The static 90% + 1200 ads is robust today, but a dynamic threshold self-adjusts if `--ads` or the published-weight ever changes via config. **Deferred to PO** — recommended as a future hardening step, not required for this fix.
3. **Should the latent MPTT-ordering smell (`seed_service.py:283`, no `order_by`) be fixed in production?** It is currently stable but fragile to django-mptt version bumps. **Deferred to PO / separate task** — not in scope for this test fix.

---

## 13. Out of Scope

- **Production seed generator changes** — `AdGenerator.generate()` (`ads.py:375-507`),
  `SeedService.run` (`seed_service.py:57`), `BaseGenerator` (`base.py:26-41`),
  `seed.default.json`, `categories.yaml`, and the `seed` management command
  (`apps/seed/management/commands/seed.py`) are **not** modified under Q2=A.
- **Generator-level stratification** (Option 3/4) — deferred to Q2=B contingency (Task 3).
- **Flaky-test plugins** (`pytest-rerunfailures`, `pytest-randomly`) — not installed; reruns
  cannot fix a deterministic failure; no new deps added.
- **`xfail` quarantine** — rejected per Q2=A (would mask rather than fix).
- **Non-seed tests** — no other test file is in scope; seed-data consumers (search/filter
  tests via `TestSeedFilterCoverage`, `test_seed.py:1456-1583`) assert only existence of
  purpose/feature/condition rows, not coverage, and are unaffected.
- **i18n** — no user-visible strings are added or changed; `test_i18n_completeness.py` is
  unaffected.
- **Plan 18 (price enforcement / filter reset)** — out of scope; this is a pre-existing
  seed-test issue (per Problem_03.md line 2).

---

## 14. Definition of Ready

The implementation task (Task 1) is ready when all of the following hold:

1. ✅ **Problem is root-caused and documented** — coupon-collector math validated,
   expected coverage = 87.89% < 90% threshold at 360 published ads.
2. ✅ **PO decisions confirmed** — Q1=A (keep 90%), Q2=A (test-only), Q3=A (bump to 1200),
   Q4=A (published-only).
3. ✅ **Research validated** — researcher findings reviewed and consistent with codebase.
4. ✅ **No production code change** — only `test_seed.py` is modified.
5. ✅ **No other test affected** — verified: no other test uses `--ads=600`; no test asserts
   exact seed-42 category/price *values* (only repeatability and existence).
6. ✅ **Runtime budget accepted** — seed tests are nightly-only; image pipeline mocked.
7. ✅ **Acceptance criteria are testable** — fast gate (`make test`) unaffected; full suite
   (`make test-all`) includes the fixed test.

---

## 15. Research References

| Artifact | Path / Link |
|---|---|
| Failing test | `src/backend/apps/seed/tests/test_seed.py:1427-1450` (`TestAdGeneratorLeafOnly.test_full_seed_coverage`) |
| Category assignment | `apps/seed/generators/ads.py:402` (`self._rng.choice(self.categories)`) |
| Seeded RNG stream | `apps/seed/generators/base.py:41` (`random.Random(faker_seed)`) |
| Status weights | `apps/seed/config/seed.default.json:4-10` (60/20/10/5/5) |
| Seed command | `apps/seed/management/commands/seed.py:37-41` (`--ads` default 600) |
| SeedService.run | `apps/seed/services/seed_service.py:57-222` (category loading, ad generation, atomicity) |
| Category fixtures | `apps/seed/services/seed_service.py:262-283` (`_load_category_fixtures`) |
| Image stub | `apps/seed/tests/conftest.py:36-46` (autouse no-op `ImageGenerator`) |
| Pytest markers | `pyproject.toml:171-180` (`seed` = nightly-only) |
| Marker semantics | `docs/99-agent/rules.md:36-51` (fast gate excludes `seed`) |
| Seed workflow | `docs/ops/seed-workflow.md` (order of operations, cleanup, dev workflow) |
| Seed module spec | `docs/01-spec/technical-specification.md:198-218` |
| Researcher report | `.ai/research/04_seed-coverage_research.md` (coupon-collector math, stratification feasibility, best-practices matrix) |
| Flaky-test guidance | pytest "Flaky tests" (`docs.pytest.org/en/stable/explanation/flaky.html`); pytest-rerunfailures (Context7: `/pytest-dev/pytest-rerunfailures`) |
| Coupon collector | Wikipedia, "Coupon collector's problem"; mysimulator.uk; LibreTexts |

---

## 16. Implementation Priority

1. **Task 1 (primary):** Bump `--ads=600` → `--ads=1200` in `test_full_seed_coverage`
   (`test_seed.py:1433`). Add a rationale comment (Task 4 hardening). **[1 minute, ~5 lines
   touched]**
2. **Verify** via `make test` (fast gate — seed tests excluded; must stay green) and
   `make test-all` (full suite including `test_full_seed_coverage` — must now pass).
3. **Task 4 (optional hardening):** Add explicit `order_by("slug")` to the test's
   assertion query and a documentation comment. Defer MPTT-ordering fix to production only
   if a future category-ordering change breaks determinism.
4. **Contingency (only if PO rejects the ad-count bump):** Replace the static 90% bound
   with the dynamic coupon-collector threshold (Task 2 / Section 8.2).

---

*End of specification — ready for implementation planning.*
