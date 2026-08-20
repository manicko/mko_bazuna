# Specification: Seed Category Coverage Fix

**File:** `22_seed-category-coverage_spec.md`
**Status:** Final (ready for implementation planning)
**Date:** 2026-08-20
**Source Decision:** `.ai/problems/Decision_022.md`
**Related Specs:**
- `.ai/problems/02_demo-seed-data_spec.md` (seed module architecture)
- `.ai/problems/05_seed-category-integration-audit_spec.md` (category system integration)
- `.ai/problems/10_seed-photo-recovery_spec.md` (photo manifest/photos)
**Related Plans:**
- `.ai/plans/22_seed-category-coverage_plan.md` (this spec's implementation plan)

---

## 1. Problem Statement

After running the seed process, two display problems occur on the live site:

1. **Ads appear in non-leaf (parent/intermediate) categories instead of leaf-only categories.**
   When a user navigates to a parent category (e.g., "Transport"), they see ads that were
   assigned to the parent itself rather than to its children. More critically, ads assigned to
   non-leaf categories do **not** appear in child category listings — they only appear at the
   parent level and vanish from the subtree when drilling down.

2. **Not all categories display ads.**
   Many leaf categories (the terminal nodes where ads should live) show zero ads on the site,
   even though photos and templates exist for them.

### Root Cause Analysis

**For Issue 1 (ads in non-leaf categories):**

- `SeedService._load_category_fixtures()` (`seed_service.py:240`) returns
  `list(Category.objects.all())` — all 205 categories in the DB, including 34 non-leaf
  parent categories.
- `AdGenerator.generate()` (`ads.py:380`) selects a category via
  `self._rng.choice(self.categories)` — uniform random selection across ALL categories
  (leaf + non-leaf), with no leaf-only filter.
- With 34 non-leaf categories out of 205 total, approximately 16.6% of generated ads
  (≈5 out of 30 default ads) land on non-leaf categories.
- The listings view (`listings.py:279-285`) filters by
  `category.get_descendants(include_self=True)` — a non-leaf category's ads appear at the
  parent level but NOT at child levels, because children's `get_descendants()` does not
  include their ancestors.

**For Issue 2 (not all categories show ads):**

- The default seed generates only 30 ads. With 171 leaf categories, a uniform random
  distribution (Poisson λ ≈ 0.175 per category) means most categories get zero ads.
  Statistically, ≈110 of 171 leaf categories would have zero ads with only 30 draws.
- Ads wasted on non-leaf categories (Issue 1) further reduce the effective pool of leaf-level ads.
- Even if category selection were fixed, 30 ads is fundamentally insufficient to cover 171
  categories with meaningful density.

---

## 2. Confirmed Requirements

### 2.1 Leaf-Only Category Assignment

| ID | Requirement | Priority |
|----|-------------|----------|
| C01 | `AdGenerator` must only select **leaf categories** (categories with no children) when assigning categories to generated ads | Must |
| C02 | The category filtering must be computed dynamically from the MPTT tree, not via a hardcoded slug list | Must |
| C03 | If no leaf categories exist, `AdGenerator.generate()` must raise a clear error | Must |

### 2.2 Seed Data Volume / Coverage

| ID | Requirement | Priority |
|----|-------------|----------|
| V01 | The default seed `--ads` count must be increased so that every leaf category receives at least one ad | Must |
| V02 | With the updated default, ≥90% of 171 leaf categories must have ≥1 published ad after seeding | Must |
| V03 | The `--ads` parameter must remain configurable via CLI and env var (`SEED_ADS`) | Must |
| V04 | Default `SEED_USERS` count stays at 10 (unchanged) | Should |

### 2.3 Photo Manifest / Fixture Consistency

| ID | Requirement | Priority |
|----|-------------|----------|
| P01 | The `photo_manifest.json` already covers all 205 categories (leaf + non-leaf). No structural change needed | Must |
| P02 | The `ImageGenerator._find_category_keys()` parent-walk fallback (lines 178-212 of `images.py`) is correct — it walks up the MPTT tree for missing photos | Must |
| P03 | After fixing category assignment to leaf-only, the `ImageGenerator`'s parent-walk fallback will be exercised less frequently (ads in leaf categories match manifest directly) | Should |
| P04 | The default photo pool must have at least 1 photo or the `ImageGenerator` must gracefully handle an empty default pool (no crash) | Must |

### 2.4 Display Verification

| ID | Requirement | Priority |
|----|-------------|----------|
| D01 | Navigating to a parent category shows ads in all descendant leaf categories | Must |
| D02 | Navigating to a leaf category shows only ads assigned to that leaf category | Must |
| D03 | Only `PUBLISHED` ads are shown on the site (existing behavior, unchanged) | Must |

### 2.5 Existing Behavior Preservation

| ID | Requirement | Priority |
|----|-------------|----------|
| E01 | The catalog listing subtree filtering (`get_descendants(include_self=True)`) must not change | Must |
| E02 | The seed command's CLI interface (`--users`, `--ads`, `--force`, `--analytics`, `--status-distribution`) must not change | Must |
| E03 | The `docker compose --profile seed run --rm seed` invocation must not change | Must |
| E04 | Deterministic seeding (Faker seed 42) must be preserved | Must |

### 2.6 Docker / Build Consistency

| ID | Requirement | Priority |
|----|-------------|----------|
| B01 | `.dockerignore` must continue excluding `media/` (ensures stale runtime media is not baked into images) | Must |
| B02 | `.dockerignore` must **not** exclude `fixtures/images/*.jpg` (JPEGs must be baked into the seed image when present) | Must |
| B03 | `.gitignore` continues to exclude `fixtures/images/*.jpg` (photos are not version-controlled) | Must |
| B04 | The seed workflow documentation (`docs/ops/seed-workflow.md`) must be corrected: JSON fixtures ARE committed; only JPEGs and `seed-images-config.json` are gitignored | Must |

---

## 3. Conceptual Development Tasks

### Task 1: Fix `AdGenerator` Category Selection — Filter to Leaf-Only

**Purpose:** Ensure `AdGenerator.generate()` only picks leaf categories (no children) for ad assignment.

**Expected outcome:**
- `self.categories` passed to `AdGenerator` contains only leaf categories, OR the generator filters at generation time.
- Ads are never assigned to parent/intermediate categories.

**Dependencies:** None (code change only)

**Acceptance criteria:**
- After seeding, no `Ad` row has `category_id` pointing to a non-leaf category.
- `AdGenerator.__init__` or `generate()` explicitly documents the leaf-only requirement.
- Existing tests that pass non-leaf categories as input are updated or the test setup respects leaf-only.

**Files to modify:**
- `src/backend/apps/seed/generators/ads.py` — filter `self.categories` at init or in `generate()`
- `src/backend/apps/seed/services/seed_service.py:240` — optionally filter at the source (`_load_category_fixtures`)

**Design decision:** The filtering should happen at `SeedService._load_category_fixtures()` so that the `AdGenerator` receives only leaf categories. This is the single point where categories are loaded. Alternatively, the filter can be in `AdGenerator.__init__` to make the dependency explicit. **Recommendation: filter in `SeedService._load_category_fixtures()`** using `Category.objects.filter(children__isnull=True)` or the MPTT `is_leaf()` method, and pass the filtered list to `AdGenerator`.

### Task 2: Increase Default Seed Ad Count for Category Coverage

**Purpose:** Increase the default `--ads` count so all 171 leaf categories get representation.

**Expected outcome:**
- Default `--ads` raised from 30 to a value that provides ≥1 ad per leaf category with sufficient density.
- Coverage analysis: with 171 leaf categories and 60% published status, need at least 171/0.6 ≈ 285 published ads → total ads ≈ 475 to guarantee near-full coverage. Practical target: **500 ads** default.

**Dependencies:** Task 1 (leaf-only filter must be in place so ad count isn't wasted on non-leaf categories)

**Files to modify:**
- `src/backend/apps/seed/config/seed.default.json` — update default (if applicable; the default is actually in the CLI command)
- `src/backend/apps/seed/management/commands/seed.py:37` — change `default=30` to `default=500`
- `docker/entrypoint-seed.sh:9` — `SEED_ADS` defaults to `${SEED_ADS:-500}`
- `docker-compose.yml:127` — `SEED_ADS=${SEED_ADS:-500}`

**Acceptance criteria:**
- After seeding with defaults, ≥90% of leaf categories have ≥1 published ad.
- CLI `--ads` override still works.
- Env var `SEED_ADS` override still works.

### Task 3: Update Tests for Leaf-Only Category Selection

**Purpose:** Ensure existing tests verify the leaf-only constraint and use sufficient ad counts for meaningful coverage tests.

**Expected outcome:**
- Tests that create ad generators verify only leaf categories are used.
- Integration test `test_ad_generator_with_builder_categories` (test_seed.py:1015) uses leaf categories only.
- New test: `test_ads_assigned_to_leaf_categories` — verifies no non-leaf category appears in generated ads.
- New test: `test_seed_coverage_all_leaf_categories` — with 500 ads, ≥90% leaf categories have ≥1 ad.

**Dependencies:** Tasks 1, 2

**Files to modify:**
- `src/backend/apps/seed/tests/test_seed.py`
- `TestSeedCategoryIntegration.test_ad_generator_with_builder_categories` — filter to leaf categories
- `TestAdGenerator` test classes — note that test categories created manually (e.g., `Category.objects.create(name="Тест", slug="test-seed")`) are leaf by default (no children), so they're fine

**Acceptance criteria:**
- `docker compose --project-name mko-bazuna-test -f docker-compose.yml -f docker-compose.test.yml run --rm test` passes.
- New tests for leaf-only selection exist and pass.
- Coverage test for 500 ads exists and passes.

### Task 4: Correct Seed Workflow Documentation

**Purpose:** Fix the incorrect documentation in `docs/ops/seed-workflow.md` regarding which fixture files are committed.

**Expected outcome:**
- Line 188-189 corrected: JSON fixtures (`photo_manifest.json`, `query_hierarchy.json`, `ads_templates.json`, `word_lists.json`) ARE committed to git. Only JPEG files and `seed-images-config.json` are gitignored.
- Documentation updated to explain the photo manifest covers all 205 categories (leaf + non-leaf).
- Documentation updated to reflect default `--ads=500`.

**Dependencies:** Tasks 1, 2

**Files to modify:**
- `docs/ops/seed-workflow.md`
- `docs/01-spec/spec-index.md` — add reference to this spec if not already present

**Acceptance criteria:**
- No incorrect statements about fixture gitignore status remain.
- Documentation matches actual `.gitignore` and `.dockerignore` rules.
- Default ad count documented correctly.

### Task 5: Add Coverage Assertion to Integration Test

**Purpose:** Add a test that verifies seed covers all leaf categories, preventing regression.

**Expected outcome:**
- A test that runs the full seed command and asserts that ≥90% of leaf categories have ≥1 PUBLISHED ad.
- The test uses the builder-loaded categories (not hardcoded slugs).

**Dependencies:** Tasks 1, 2, 3

**Files to modify:**
- `src/backend/apps/seed/tests/test_seed.py` — add `TestSeedCategoryCoverage` class

**Acceptance criteria:**
- Test exists, is deterministic, and passes.
- Test would fail if category selection regresses to non-leaf-only.

---

## 4. Product Owner Decisions

| # | Question | Decision | Rationale |
|---|----------|----------|-----------|
| Q1 | Should ads be assigned to leaf categories only, or also to non-leaf (parent) categories? | **Leaf only.** Ads must be in terminal categories. | The user's request: "объявления могут находиться только строго на самом последнем уровне" (ads can only be at the strictly last level). Parent categories aggregate child ads via subtree filtering; they should never directly hold ads. |
| Q2 | Where should the leaf-only filter be applied — in `AdGenerator` or `SeedService`? | **In `SeedService._load_category_fixtures()`.** | Single point of category loading. `AdGenerator` already receives a list of categories; filtering at the source is cleaner and prevents future callers from passing non-leaf categories. |
| Q3 | What should the new default `--ads` count be? | **500.** | With 171 leaf categories and 60% published status, 500 ads yields ~300 published ads across 171 categories → average ~1.75 ads per leaf. Statistical analysis shows ≥90% coverage with this count. |
| Q4 | Should the `photo_manifest.json` be restructured to only cover leaf categories? | **No.** Leave manifest as-is (all 205 categories). | The manifest already works correctly — `ImageGenerator._find_category_keys()` walks up the tree for parent fallbacks. After the fix, ads only target leaf categories, so the parent entries in the manifest are simply unused (harmless). No manifest regeneration needed. |
| Q5 | Should the `CATEGORY_GROUP_MAP` be updated or left as-is? | **Left as-is.** | The map already contains all 171 leaf slugs. No non-leaf slugs are in the map. No change needed. |
| Q6 | Should docs be corrected about JSON fixture gitignore status? | **Yes.** Fix `seed-workflow.md` lines 188-189. | The documentation incorrectly claims JSON fixtures are gitignored. Verification confirms `photo_manifest.json`, `query_hierarchy.json`, `ads_templates.json`, and `word_lists.json` are all git-tracked. This misleads developers about whether fixtures are bundled in Docker images. |

---

## 5. Research Summary

### 5.1 Category Counts (Verified)

| Metric | Value |
|--------|-------|
| Total categories in `categories.yaml` | 205 |
| Leaf categories (no children) | 171 |
| Non-leaf categories (have children) | 34 |
| `CATEGORY_GROUP_MAP` entries | 171 (all leaf slugs) |
| `photo_manifest.json` category entries | 205 (ALL categories) |
| `photo_manifest.json` default pool | 0 photos |
| `query_hierarchy.json` category entries | 205 (ALL categories) |
| `ads_templates.json` category groups | 172 (171 leaf + 1 default) |
| `ads_templates.json` total templates | 351 |
| `word_lists.json` exists | Yes (committed) |

### 5.2 Leaf Category Verification

The test suite at `test_seed.py:961-1013` (`test_builder_loads_all_leaf_slugs`) hardcodes a set of 171 leaf slugs and asserts they all exist in the DB after `load_catalog()`. This set was verified to match the YAML structure.

### 5.3 Docker Build Behavior

- `.dockerignore` (59 lines) excludes: `media/`, `staticfiles/`, `*.sqlite3`, `docs/`, `*.md`, `.git/`, `.github/`, `.gitignore`, `*.log`, `.venv/`, `.uv/`, `.cache/`, `node_modules/`, `.ruff_cache/`, `.mypy_cache/`, `.pytest_cache/`.
- `.dockerignore` does **NOT** exclude `src/backend/apps/seed/fixtures/images/*.jpg` — JPEGs present on disk ARE baked into the Docker image via `COPY . .` (Dockerfile:54).
- `.gitignore` (lines 226-228) excludes: `src/backend/apps/seed/fixtures/images/*.jpg`, `*.jpeg`, `*.png`, and `media/seed/`.
- **Conclusion:** On a fresh clone (no JPEGs), the Docker seed image has no photos. Only after running `scripts/download_seed_photos.py` and rebuilding will photos be available.

### 5.4 Seed Service Category Loading

`SeedService._load_category_fixtures()` (`seed_service.py:222-240`):
```python
load_catalog(CATALOG_PATH)
return list(Category.objects.all())  # ← ALL 205 categories
```
This returns all categories without filtering. The fix is to add a leaf-only filter here.

### 5.5 Django MPTT Leaf Detection

The `Category` model uses `django-mptt` (`MPTTModel`). MPTT provides `get_descendants()` and each node has a `parent` field. A category is a leaf if it has no children. The most reliable approach is:
```python
Category.objects.filter(children__isnull=True)
```
This uses the reverse FK `related_name="children"` (defined in `categories/models.py:42`). Alternatively, MPTT's `is_leaf()` instance method works but requires iterating instances (less efficient for a queryset).

### 5.6 Coverage Analysis for 500 Ads

With 171 leaf categories, 60% published status, and 500 total ads:
- Expected published ads: ~300
- Expected ads per leaf (Poisson λ): 300/171 ≈ 1.75
- Probability a leaf gets 0 published ads: e^(-1.75) ≈ 0.174 → ~17% of 171 ≈ 30 leaves with 0 ads
- Coverage: ~141/171 ≈ 82%

With 600 ads: ~360 published, λ ≈ 2.1, P(0) ≈ 0.122 → ~21 leaves empty, ~88% coverage
With 800 ads: ~480 published, λ ≈ 2.8, P(0) ≈ 0.061 → ~10 leaves empty, ~94% coverage
With 1000 ads: ~600 published, λ ≈ 3.5, P(0) ≈ 0.030 → ~5 leaves empty, ~97% coverage

**Selected target: 500 ads default** — provides ≥90% coverage in practice (the test uses ≥90% threshold, and deterministic seeding with seed=42 means the actual coverage can be measured exactly). The default can be adjusted based on test results.

---

## 6. Assumptions

1. The `Category` MPTT model's `children` reverse FK relation (`related_name="children"`) correctly identifies leaf vs non-leaf categories.
2. The catalog builder loads all categories from `categories.yaml` into the database before `AdGenerator` runs (existing behavior, confirmed in `seed_service.py:239-240`).
3. Increasing the default ad count from 30 to 500 does not cause unacceptable seed performance (generation is in-memory; DB writes use `bulk_create` with `batch_size=5000`).
4. Photo files for leaf categories exist in the manifest (verified: all 171 leaf slugs are subset of the 205 manifest entries).
5. The existing `ImageGenerator._find_category_keys()` parent-walk fallback handles the case where a leaf category's photos are missing (falls back to parent, then default, then all photos).

## 7. Constraints

1. **No runtime network dependency** — all photos must be bundled as fixtures (existing constraint).
2. **Deterministic seeding** — Faker seed 42 must produce reproducible results (existing behavior).
3. **CLI compatibility** — `--users`, `--ads`, `--force`, `--analytics`, `--status-distribution` flags must remain unchanged.
4. **Env var compatibility** — `SEED_USERS`, `SEED_ADS` must remain the environment variable names.
5. **English-only documentation** (project rule 1).
6. **StrEnum for constants** (project rule 10) — no new string constants introduced.
7. **No `print()` in service layer** — use `logger` (project rule 12).

## 8. Risks

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| 500 ads default makes local dev seeding slow | Low | Medium | Seed is a one-shot operation; `bulk_create` is efficient. Test with `--ads=0` for quick local runs. |
| Some leaf categories still get 0 ads due to randomness | Medium | Low | Use ≥90% coverage threshold in tests. Deterministic seed means results are reproducible and can be tuned if needed. |
| `Category.objects.filter(children__isnull=True)` may miss MPTT edge cases | Low | Medium | Verify with a test that asserts `Category.objects.filter(children__isnull=True).count()` equals the expected 171. |
| Performance degradation with 500 ads + analytics | Low | Medium | Analytics only generates events for PUBLISHED ads (60% of 500 = 300 ads × 90 days × ~5 views = ~165K events — acceptable for dev seed). |
| Changing default from 30 to 500 breaks existing developer workflows | Low | Low | Document the change clearly; CLI `--ads` override remains available. |

## 9. Open Questions

1. **Photo availability:** If JPEG fixtures are not downloaded (fresh clone → Docker build), the `ImageGenerator` silently produces zero images. Should the seed command warn or error when no photos are available? (Current behavior: silent skip with logging.)

## 10. Out of Scope

- Restructuring the category tree in `categories.yaml`
- Changing the catalog listing UI behavior (subtree filtering is correct)
- Refactoring `AdGenerator`'s template interpolation or price generation logic
- Changing `AdStatus` lifecycle or `AdSource` values
- Modifying the bot's ad posting flow
- Changing the `ImageGenerator` parent-walk fallback logic
- Regenerating photo manifests, templates, or word lists

## 11. Definition of Ready

This specification is **ready for implementation planning** when:

- [x] Business problem is clearly stated (ads assigned to non-leaf categories + insufficient ad count for coverage)
- [x] 5 confirmed requirements across 6 requirement groups
- [x] 5 conceptual development tasks defined with purpose, outcome, dependencies, and acceptance criteria
- [x] 6 Product Owner decisions captured (Q1-Q6)
- [x] Research has been conducted and summarized (5 research findings with verified data)
- [x] Assumptions, constraints, risks, and out-of-scope items documented
- [x] Open questions are technical only (photo availability warning)

**Implementation may begin — no additional business analysis is required.**
