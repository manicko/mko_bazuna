# Seed Coverage Test — Research Report

**Task:** Validate root cause, assess generator stratification, and gather modern best
practices for the flaky `test_full_seed_coverage` test.
**Date:** 2026-09-02
**Source problem:** `.ai/problems/Problem_03.md`

---

## TL;DR

`TestAdGeneratorLeafOnly.test_full_seed_coverage` is **deterministically failing** (not
randomly flaky). With 600 ads at 60% published = 360 published ads uniformly assigned to
171 categories, the **expected** coverage is 87.89% but the test asserts ≥90%. Under
uniform assignment, only ~17.8% of seeds reach 90%; seed 42 realizes ~87.7% (≈ the mean).
The test is **fragile** (not stochastic): a single new `self._rng.choice()` in the per-ad
loop re-ranks the RNG stream and can shift coverage by O(σ). No reruns help (deterministic
seed + MPTT order). **Recommended fix: Option 2** — bump `--ads` 600→1200 → ~720 published
→ E[coverage]≈98.5%, ~9σ above 90%. Test-only, one line.

---

## A. Coupon Collector Math (root-cause verification)

### Setup
- Leaf categories `n = 171` (verified: `builder.py` + `categories.yaml` → `test_seed.py:1374`
  asserts `len == 171`; independent YAML count = 171).
- Ads = 600; default `status_distribution` (`seed.default.json:4-10`) → published weight
  0.60 → **expected published `m = 360`** (`SeedService.run` passes config-default weights;
  `AdGenerator.generate` consumes them at `ads.py:392-396, 426`).
- Category assignment **uniform**: `category = self._rng.choice(self.categories)`
  (`ads.py:402`), no weights.
- Category drawn before status (`ads.py:402` then `426`); status independent by
  construction → published subset's categories are i.i.d. uniform over 171 → classic
  coupon-collector model applies.

> **Key distinction:** although `generate()` interleaves ~19–21 `_rng` draws per ad
> (template `413`, user `424`, city `425`, status `426`, conditional purpose `439`, then
> 3×5 word-list choices in `_fill_template` at `ads.py:352-359`), only the **category**
> draw (`402`) is uniform over 171. Status is independent, so conditioning on "published"
> does not bias category. Interleaving changes *which RNG positions* map to categories
> (hence seed-42's realized value differs from a toy consecutive sim) but **not the
> distribution** — expectation/variance/std are as computed.

### 1. Expected coverage and P(≥90%) — m = 360
Exact coupon-collector (distinct-count) formulas:

| Quantity | Value |
|---|---|
| E[covered] = n·(1−((n−1)/n)^m) = 171·(1−(170/171)^360) | **150.30** |
| E[coverage %] | **87.89%** |
| σ(coverage %) (Monte Carlo, 200k trials, uniform) | **2.11%** |
| P(coverage ≥ 90% = ≥154 cats) — exact inclusion-exclusion | **17.84%** |
| P(coverage ≥ 90%) — Monte Carlo 200k | 18.71% (corroborates) |
| P50 / median (MC) | **87.7%** ← matches reported seed-42 realization |

**Conclusion:** E[coverage] (87.89%) is **below** the 90% threshold, and ≥90% is reached
by only ~18% of seeds. Seed 42's ~87.7% ≈ the mean/median — not an outlier, but proof the
threshold exceeds what uniform seeding achieves in expectation. The test is
over-budgeted relative to the probability.

### 2. Published ads needed for reliable coverage (exact inclusion-exclusion)

| Target | Published ads `m` | → Total ads (@60% published) | Probability confirmed |
|---|---|---|---|
| ≥90% coverage at **≥95%** prob | **448** | **≈747 → 750** | 448→95.02%; 447→94.89% |
| 100% coverage (all 171) at **≥95%** prob | **1384** | **≈2307 → 2310** | 1384→95.02%; 1383→94.99% |

Benchmark: classic collect-all expectation `n·ln n ≈ 171·ln(171) ≈ 879`, at which
P(100%)=36.6% — illustrating the heavy right tail.

### 3. Why seed = 42 deterministically yields ~87.7%
- `BaseGenerator.__init__`: `self._rng = random.Random(config.get("faker_seed", 42))`
  (`base.py:41`) — single isolated stream feeding all generators.
- Fixed stream + **deterministic category order** → covered set is fixed (~150 cats)
  every run → 150/171 ≈ 87.7%.
- 87.7% ≈ E[87.89%] and ≈ MC median (87.7%) → a *typical* draw, not pathologically low.
  (Exact 87.7% not reproducible from a toy sim because `generate()` consumes ~19–21 `_rng`
  draws per ad; seed-42's category draws are sampled every ~19th position. Distribution
  unchanged; only the realized point estimate differs by interleaving.)
- **Therefore the failure is arithmetic, not stochastic.**

### 4. Why the test is fragile
1. Threshold sits ~1.0σ above the mean (90%−87.89% = 2.11pp; σ ≈ 2.11pp). Any change
   shifting seed-42 coverage by ≥4 categories (≈1.2 pp) flips pass↔fail.
2. All `self._rng` draws share one `Random(42)` stream (`base.py:41`). `generate()`
   draws category **first** each iteration (`ads.py:402`) then ~18 more `_rng` draws.
   Inserting one new `self._rng.choice()`/`choices()` anywhere in the per-ad loop
   inserts a draw before the next category draw, **re-ranking every subsequent category
   assignment** and changing the covered set by O(σ) ≈ ±2 cats.
   - Draws via `self.faker.random_int(...)` (`_generate_price` `ads.py:596-608`,
     `_fill_template` 357-361) use **Faker's separate RNG** (`faker.seed_instance`,
     `base.py:34`) and do **not** perturb `self._rng`. Fragility targets new `self._rng.*`
     calls, not faker calls.

> **Latent smell:** `_load_category_fixtures` returns `Category.objects.filter(children__isnull=True)`
> with **no `order_by`** (`seed_service.py:283`). Ordering comes from django-mptt's
> `TreeManager` (`.order_by(tree_id, lft)`). Currently stable across runs, but a
> django-mptt version change could shift tree order and flip the test. **Not the active
> cause of flakiness today** (confidence: HIGH on math/causality, MEDIUM on "only active
> instability is the threshold").

---

## B. AdGenerator category-assignment assessment

### B.1 Current mechanism
`category = self._rng.choice(self.categories)` at `ads.py:402`. Uniform, unweighted, no
stratification, no per-category floor.

### B.2 Feasibility of stratified/round-robin assignment
**Yes — small, localized change.** Replace the uniform-per-ad draw in `generate()` with a
two-phase schedule:

```
guaranteed = [c for c in self.categories for _ in range(min_per_category)]
remainder = ad_count - len(guaranteed)
scheduled = guaranteed + [self._rng.choice(self.categories) for _ in range(remainder)]
self._rng.shuffle(scheduled)
# iterate scheduled instead of drawing category inline at line 402
```

**But published-coverage needs status control too.** The test counts *PUBLISHED* ads per
category (`test_seed.py:1440-1446`). Uniform category + random 60% status does not
guarantee any category's ad is published. To guarantee published-coverage you must force
guaranteed ads' status to `PUBLISHED` (overriding the weighted draw at `ads.py:426`).
That guarantees 100% published-coverage but **distorts the published fraction** unless the
remainder's weights are rebalanced.

**Minimum viable variant:** 1 forced-PUBLISHED ad per category + random remainder. With
`ad_count=600`: 171 forced published + (429×0.60≈257) random published = 428/600 =
**71.3% published** vs the 60% target — a **+11pp distortion** of the documented
distribution. To avoid distortion, rebalance remainder weights:
`(0.60·600 − 171)/429 ≈ 44.1%`.

### B.3 Downsides of changing the generator (vs. the test)
- **Distribution distortion:** forcing published ads raises the published fraction unless
  remainder weights are rebalanced (`seed.default.json` / `seed-workflow.md:57` document
  60/20/10/5/5).
- **Scope creep:** stratification changes *every* seed run (dev `make up`, CI, CI), not
  just the one test — `ads.py:402` is on the production seed path
  (`seed_service.py:108-109`).
- **Determinism tests:** `test_deterministic_multi_language` (`test_seed.py:853-872`) and
  `test_deterministic_output` (`test_seed.py:92-101`) require *repeatability* only
  (gen1==gen2), so a seeded shuffle preserves them. Risk only if a future test asserts
  seed-42-specific values — none currently do.
- **`CATEGORY_GROUP_MAP` / template selection unaffected:** `CATEGORY_GROUP_MAP`
  (`ads.py:33-212`) is brand grouping; template lookup is by `category.slug`
  (`ads.py:406-411`). Neither depends on draw order — zero impact.

### B.4 Existing mechanism/flag?
**None.** `seed.default.json` (31 lines) has no category-distribution key. `generate()`
accepts only `ad_count, status_weights` (`ads.py:375-379`). A stratification feature
requires a new `generate()` parameter, a new config key, and remainder-weight rebalancing.

---

## C. Modern best practices (web + pytest docs)

Sources consulted:
- pytest "Flaky tests" (`docs.pytest.org/en/stable/explanation/flaky.html`)
- pytest-rerunfailures (Context7: `/pytest-dev/pytest-rerunfailures`)
- pytest-randomly / random-order / flakefinder (pytest flaky docs)
- Coupon Collector problem (Wikipedia; mysimulator.uk; LibreTexts)
- "Preventing Flaky Tests in Python CI" (johal.in, 2026-03-18)
- "How to avoid and detect flaky tests in Pytest" (Trunk.io, 2026-02)

### 1. Coverage assertions on seeded data
Best practice: assert coverage against a **statistically-justified** bound, not an
arbitrary round number. For uniform sampling over `n` entities with `m` draws, assert
`>= E[K] − k·σ` where `E[K] = n(1−((n−1)/n)^m)`. With seed 42 fixed, a static bound of
80% is robust (mean 87.9%, σ≈2.1% → 80% is ~3.7σ below mean → P(fail)≈0.01%). Better:
make coverage **deterministic** via stratified fixtures (draw each category ≥1) so the
assertion is a hard 100%.

### 2. Coupon collector in seed design
Expected draws for full coverage ≈ `n·ln n` (879 for n=171); the last few coupons dominate
(~n more draws each). Partial-coverage tail is heavy: at m=360, P(≥90%)=17.8%. Seed
budget should target `m ≈ 448 published` for 90%-at-95% or `m ≈ 1384` for 100%-at-95%.
Current 360 is far below the partial-coverage budget comfortably.

### 3. Stratified vs. uniform
- **Stratified:** guarantees representation → deterministic coverage, but adds logic and
  (if status forced) distribution distortion. Preferred when coverage is the *contract*.
- **Uniform random:** simpler, realistic, distribution-preserving, but coverage is a
  random variable with a heavy left tail — unsuitable for a hard lower-bound assertion
  unless `m` is large.

### 4. Flaky-test mitigation (project reality)
- `pytest-rerunfailures` `@pytest.mark.flaky(reruns=N)`: **NOT a fit** — reruns re-execute
  with the same fixed seed 42 and deterministic MPTT order → identical 87.7% failure.
  (Plugin is for *transient* failures.)
- `pytest-randomly` / `pytest-random-order`: would *expose* seed-fragility (17.8% pass
  rate under random seeds). **Not installed** (`pyproject.toml` has none of:
  pytest-randomly, rerunfailures, pytest-random-order, flaky, pytest-replay,
  pytest-repeat — verified). Good: the project avoids accidental per-run randomization.
- `xfail(strict=False)`: valid tactical bandage — mark
  `@pytest.mark.xfail(reason=..., strict=False)` so it fails loudly only on unexpected
  pass. Useful as triage, not a fix.
- **Threshold relaxation / statistical bound:** the principled test-only fix.
- `pytest-repeat` stress (run N× different seeds): would show 17.8% pass rate, proving
  structural unfitness. Not installed; exact math suffices.

### 5. Project convention informs acceptability
- `pyproject.toml:174`: `seed` marker = nightly only.
- Makefile:99-102: `make test` uses `PYTEST_SKIP_MARKERS=seed` → entrypoint appends
  `-m "not (seed)"` → excludes seed tests from the fast gate.
- `make test-all` (~35 min) includes `seed`.
- **Implication:** this test never blocks PR iteration. Acceptable bar: reliability
  within the nightly run + minimal maintenance → favors test-only fix over generator
  change.

---

## D. Recommended approach

| Option | Mechanism | Reliability (≥90%) | Runtime | Code change | Aligns with rules |
|---|---|---|---|---|---|
| 1a. Lower to 85%/80% | Static threshold | Medium (85 = mean−1.4σ → ~92% pass; 80 = never fails) | None | 1 line | Test-only ✓; weakens assertion |
| 1b. Dynamic threshold | E[K]−3σ coupon-collector | High (never fails at m=360) | None | ~6 lines | Test-only ✓; honest stats |
| **2. Bump `--ads` 600→1200** | More draws (≈720 published) | **Very High** (E=98.5%, ~9σ) | Low (nightly, mocked img) | 1 line | **Strongest** — test-only, keeps ≥90% |
| 3. Force 1 published/cat | Generator guarantee | Deterministic 100% | None | Generator + config; shifts seeds | Weak — prod change, distorts 60/20/10/5/5 |
| 4. Hybrid stratified | Floor + reweighted random | Deterministic 100% | None | Generator + config + weight math | Weakest — most code, prod-wide change |

### Recommended: **Option 2 (bump `--ads` to 1200)**
**Rationale:**
- **Test-only** — changes only `call_command("seed", "--ads=600", ...)` at
  `test_seed.py:1433` → `--ads=1200`. No production code, no seed-workflow change,
  no distribution distortion.
- **Statistically bulletproof for seed 42:** 720 published →
  E[coverage] = 171·(1−(170/171)^720) ≈ **168.5/171 = 98.55%**; σ ≈ 0.56 pp.
  Threshold 90% is ~9σ below mean → no seed (including 42) fails. Unlike the current
  360-published setup (P≥90% = 17.8%), this gives deterministic-looking reliability
  without stratification complexity.
- **Preserves the assertion's meaning** (`≥90% covered`).
- **Runtime negligible** in nightly suite (mocked `ImageGenerator` via
  `conftest.py:36-46`; `--analytics=False`; `bulk_create(batch_size=5000)` at
  `seed_service.py:110`).
- **Aligned with rules:** `Production code is king` (no production change) and
  `Avoid overengineering` (one-arg change, no new state/flags/reweighting).

**Secondary recommendation (if 600 must stay):** Option 1b — dynamic
coupon-collector-derived threshold. `expected_pct = 100·171·(1−(170/171)^(600·0.6))/171`
≈ 87.89%; `threshold = 87.89 − 3·2.11 ≈ 81.6%`. Most *honest* formulation but adds math
and weakens the 90% contract.

**Only if a hard 100%-deterministic guarantee is required** (e.g. downstream tests need
every category represented): Option 4, with remainder-weight rebalancing. Heaviest,
touches production seed behavior — recommended only if stratification is genuinely
valuable for dev/demo realism, not for the test alone.

---

## E. Impact assessment

### Tests touching seed path / distribution
| Test | File:lines | Asserts | Option 1 impact | Option 1b | Option 2 | Option 3/4 |
|---|---|---|---|---|---|---|
| `test_full_seed_coverage` | `test_seed.py:1427` | ≥90% published-coverage, ads=600 | changed | changed | changed (ads=1200) | robust (100%) |
| `test_no_non_leaf_category_assigned` | `1405` | ads=10, non-leaf=0 | n/a | n/a | n/a | n/a (stratification assigns leaf only) |
| `test_ad_generator_with_builder_categories` | `1195` | gen.generate(10), pub=1.0, FK valid | n/a | n/a | n/a (direct gen) | if flag off: n/a; if always-on: assertions hold |
| `test_give_away_ads_have_zero_price` | `1256` | gen.generate(500) ≥1 give-away | n/a | n/a | n/a | improved (stratification guarantees charity) |
| `test_full_seed_with_builder_categories` | `1319` | ads=5, count==5 | n/a | n/a | n/a | n/a |
| `TestSeedFilterCoverage._run_seed` | `1479` | ads=40, purpose/features exist | n/a | n/a | n/a | n/a |

### Tests asserting exact counts/totals
- `test_bulk_create_works` (252), `test_seed_with_zero_count` (478-479),
  `test_seed_force_skips_prompt` (493-494: User==2, Ad==3), `test_seed_idempotent` (525:
  count2==count1==5), `test_seed_recovers_from_orphaned_users` (537-550: User==3, Ad==5).
- These use their own small `--ads` values, not 600. **Option 2 does not break them.**

### Tests depending on determinism (faker_seed=42 reproducibility)
- `test_deterministic_faker_seed` (42), `test_random_choice_*` (56-60),
  `test_deterministic_output` (92-101), `test_deterministic_multi_language` (853-872).
- Option 1/2 (test-only): untouched.
- Option 3/4 (generator): `test_deterministic_multi_language` (853) checks gen1==gen2
  (repeatability only) → still passes with seeded shuffle. Risk only if future test
  asserts seed-42-specific values (none do today).

### Cross-module / non-seed tests
- Repo-wide grep for `coverage_pct`, `>= 90`, `>=0.9`, `covered.*category` → **no non-seed
  test** asserts seed category coverage. Seed-data consumers (search/filter tests via
  `TestSeedFilterCoverage`, `test_seed.py:1456-1583`) assert only *existence* of
  purpose/feature/condition rows, not coverage — unaffected.

### Schema / migration
- None of the options require schema changes (no new model fields). No migration needed
  (Rule #13 respected). Seed suite tolerates `--reuse-db`; increasing `--ads` does not
  interact with the test-DB lifecycle (`docs/99-agent/rules.md:56-57`).

---

## Bottom line
The test fails because **90% > E[87.9% coverage]** under uniform random seeding, not
because of stochastic flakiness. The most rule-aligned, lowest-risk fix is **Option 2**:
change `--ads=600` → `--ads=1200` at `test_seed.py:1433`, lifting expected coverage to
~98.5% with a ~9σ safety margin. One-line, test-only change; preserves a meaningful ≥90%
assertion; disturbs no other test and no production behavior.
