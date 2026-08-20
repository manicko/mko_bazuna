# Implementation Plan: Seed Category Coverage Fix

**Plan ID:** `22_seed-category-coverage_plan`
**Source Spec:** `.ai/problems/22_seed-category-coverage_spec.md`
**Date:** 2026-08-20
**Status:** Ready for implementation

---

## Execution DAG

```
             ┌─────────────────────────────────────────────────────┐
             │  Parallel Group A (no deps)                          │
             │                                                      │
             │  T001: Fix AdGenerator category selection (leaf-only)│
             │  T002: Increase default --ads count to 600           │
             └────────────────────┬───────────────────────────────┘
                                  │
             ┌────────────────────┴───────────────────────────────┐
             │  Serial Group B (depends on A)                     │
             │                                                      │
             │  T003: Update existing tests for leaf-only + 600 ads │
             │  T004: Add new coverage assertion tests             │
             └────────────────────┬───────────────────────────────┘
                                  │
             ┌────────────────────┴───────────────────────────────┐
             │  Final Group C (depends on B)                      │
             │                                                      │
             │  T005: Correct seed-workflow documentation         │
             │  T006: Full test suite run + verification          │
             └─────────────────────────────────────────────────────┘
```

---

## Execution Order

| Order | Task ID | Title | Parallel Group | Risk Level | Blocked By |
|-------|---------|-------|---------------|------------|------------|
| 1 | T001 | Fix `AdGenerator` category selection — filter to leaf-only | A | low | — |
| 1 | T002 | Increase default `--ads` count to 600 | A | low | — |
| 2 | T003 | Update existing tests for leaf-only category filtering | B | low | T001 |
| 2 | T004 | Add new coverage assertion tests | B | low | T001, T002 |
| 3 | T005 | Correct seed-workflow documentation | C | low | T001, T002 |
| 4 | T006 | Full test suite run + verification | C | low | T003, T004 |

---

## Task Specifications

---

### T001: Fix `AdGenerator` category selection — filter to leaf-only

**Priority:** high

**Depends on:** none

**Risk:** low — changes the category loading logic in a single method, well-tested by existing integration tests.

**Goals:**
- `SeedService._load_category_fixtures()` returns only leaf categories
- No ad is ever assigned to a non-leaf (parent/intermediate) category
- The fix uses MPTT's `children` reverse FK relation, not a hardcoded slug list

**Files:**
- `src/backend/apps/seed/services/seed_service.py`

**Target:**
- Method: `SeedService._load_category_fixtures()` (line 222-240)

**Detailed changes:**

Current code (`seed_service.py:238-240`):
```python
load_catalog(CATALOG_PATH)
return list(Category.objects.all())
```

New code:
```python
load_catalog(CATALOG_PATH)
# Only leaf categories (no children) — ads must live at the terminal level.
# Parent categories aggregate ads via MPTT subtree filtering in the listings view,
# so they should never be directly assigned ads.
return list(Category.objects.filter(children__isnull=True))
```

**Acceptance criteria:**
- `Category.objects.filter(children__isnull=True).count()` returns 171 after catalog load
- After running `manage.py seed --ads 600`, no `Ad` row references a non-leaf category
- `load_catalog()` is called before the filter (categories must exist before filtering)
- Deterministic seeding still works (same seed = same output)

**Verification command:**
```bash
docker compose --project-name mko-bazuna-test -f docker-compose.yml -f docker-compose.test.yml run --rm test
```

---

### T002: Increase default `--ads` count to 600

**Priority:** high

**Depends on:** none

**Risk:** low — change default values in configuration, command, entrypoint, and compose file.

**Goals:**
- Default `--ads` changed from 30 to 600
- `SEED_ADS` env var default changed from 30 to 600
- All documentation references updated

**Files:**
- `src/backend/apps/seed/management/commands/seed.py`
- `docker/entrypoint-seed.sh`
- `docker-compose.yml`

**Detailed changes:**

1. **`seed.py:37`** — Change `default=30` to `default=600`:
   ```python
   parser.add_argument(
       "--ads",
       type=int,
       default=600,  # was 30 — calibrated so >=90% of leaf categories get >=1 published ad
       help="Number of ads to generate (default: 600)",
   )
   ```

2. **`entrypoint-seed.sh:9`** — Change `SEED_ADS:-30` to `SEED_ADS:-600`:
   ```bash
   --ads "${SEED_ADS:-600}"
   ```

3. **`docker-compose.yml:127`** — Change `SEED_ADS=${SEED_ADS:-30}` to `SEED_ADS=${SEED_ADS:-600}`

**Acceptance criteria:**
- `manage.py seed --help` shows default=600
- `docker compose --profile seed run --rm seed` generates 600 ads by default
- `SEED_ADS=100` env var overrides to 100
- `--ads 100` CLI flag overrides to 100
- No performance issues with 600 ads (bulk_create with batch_size=5000)

> **Implementation note:** The original decision was 500, but measured
> deterministic coverage (faker_seed=42, 60% published) for the full seed is
> only ~82% at 500 ads — below the 90% Must requirement (V02). Calibrated to
> **600 ads**, which deterministically reaches 90.06% coverage of leaf
> categories (per spec §5.6, the default may be tuned based on measured test
> results).

---

### T003: Update existing tests for leaf-only category filtering

**Priority:** high

**Depends on:** T001

**Risk:** low — test modifications only, no production code changes.

**Goals:**
- Tests that pass ALL categories to `AdGenerator` are updated to pass leaf-only categories
- Tests that explicitly assert non-leaf categories are used are removed or corrected
- Integration tests using the builder-loaded categories filter to leaf-only

**Files:**
- `src/backend/apps/seed/tests/test_seed.py`

**Detailed changes:**

1. **`TestSeedCategoryIntegration.test_ad_generator_with_builder_categories` (line 1015-1056):**
   - Current: `categories = list(Category.objects.exclude(slug__in=["test-seed", ...]))` — passes ALL categories
   - New: `categories = list(Category.objects.filter(children__isnull=True).exclude(slug__in=["test-seed", ...]))`

2. **`TestSeedCommandEnhanced` class (line 854-925):**
   - `setUpTestData` creates `Category.objects.create(name="Тест", slug="test-seed")` — this is already a leaf (no children)
   - No changes needed here — these are leaf categories

3. **`TestAdGenerator.setUpTestData` (line 129-164):**
   - Creates 3 categories (`real-estate`, `cars`, `phones`) — all are leaf (no children set)
   - No changes needed — these are already leaf categories

**Acceptance criteria:**
- All existing tests pass after the change
- `TestSeedCategoryIntegration` uses leaf-only categories
- No test creates or uses non-leaf categories in `AdGenerator` calls

---

### T004: Add new coverage assertion tests

**Priority:** high

**Depends on:** T001, T002

**Risk:** low — new test cases, no production code changes.

**Goals:**
- Test that `SeedService._load_category_fixtures()` returns only leaf categories
- Test that generated ads never reference non-leaf categories
- Test that with 600 ads, ≥90% of leaf categories have ≥1 published ad

**Files:**
- `src/backend/apps/seed/tests/test_seed.py`

**New test classes:**

1. **`TestLeafCategoryFiltering`** — verifies the leaf-only filter:

   ```python
   class TestLeafCategoryFiltering(TestCase):
       """Verify that seed category loading returns only leaf categories."""

       @classmethod
       def setUpTestData(cls):
           from apps.categories.catalog.builder import load_catalog
           CATALOG_PATH = Path(__file__).resolve().parents[2] / "categories" / "catalog" / "categories.yaml"
           load_catalog(CATALOG_PATH)

       def test_load_category_fixtures_returns_leaf_only(self):
           """SeedService._load_category_fixtures() returns only leaf categories."""
           service = SeedService()
           categories = service._load_category_fixtures()
           # Every returned category should have no children
           for cat in categories:
               self.assertFalse(
                   cat.children.exists(),
                   f"Category {cat.slug} is not a leaf (has children)"
               )
           # Should have 171 leaf categories (minus test categories)
           self.assertEqual(len(categories), 171)

       def test_non_leaf_categories_excluded(self):
           """Non-leaf categories are not in the returned list."""
           service = SeedService()
           categories = service._load_category_fixtures()
           slug_set = {c.slug for c in categories}
           # These are known non-leaf (parent) categories
           self.assertNotIn("real-estate", slug_set)
           self.assertNotIn("transport", slug_set)
           self.assertNotIn("goods", slug_set)
           self.assertNotIn("services-jobs", slug_set)
           self.assertNotIn("business", slug_set)
   ```

2. **`TestAdGeneratorLeafOnly`** — verifies AdGenerator never picks non-leaf:

   ```python
   class TestAdGeneratorLeafOnly(TestCase):
       """Verify AdGenerator only assigns leaf categories to ads."""

       @classmethod
       def setUpTestData(cls):
           from apps.categories.catalog.builder import load_catalog
           CATALOG_PATH = Path(__file__).resolve().parents[2] / "categories" / "catalog" / "categories.yaml"
           load_catalog(CATALOG_PATH)
           # Create users and cities
           for i in range(5):
               User.objects.create(username=f"leaf-user{i}", telegram_id=5000+i, chat_id=5000+i, password="!")
           cls.users = list(User.objects.all())
           City.objects.create(name="Будва", slug="budva", region="Coastal", country_code="ME")
           cls.cities = list(City.objects.all())

       def test_no_non_leaf_category_assigned(self):
           """Generated ads never reference non-leaf categories."""
           # Load all categories (including non-leaf)
           all_categories = list(Category.objects.all())
           gen = AdGenerator(
               {"faker_seed": 42, "status_distribution": {"published": 1.0}},
               self.users,
               all_categories,
               self.cities,
           )
           ads = gen.generate(50)
           non_leaf_slugs = {
               cat.slug for cat in all_categories if cat.children.exists()
           }
           for ad in ads:
               self.assertNotIn(
                   ad.category.slug, non_leaf_slugs,
                   f"Ad assigned to non-leaf category: {ad.category.slug}"
               )

       def test_full_seed_coverage(self):
           """Full seed with 600 ads covers >=90% of leaf categories with ads."""
           out = StringIO()
           call_command("seed", "--users=10", "--ads=600", "--force", "--analytics=False", stdout=out)
           leaf_categories = Category.objects.filter(children__isnull=True)
           total_leaf = leaf_categories.count()
           # Count how many leaf categories have at least one published ad
           covered = Ad.objects.filter(
               source=AdSource.SEED,
               status=AdStatus.PUBLISHED,
               category__children__isnull=True,  # parent of ad is a leaf
           )
           covered_slugs = set(covered.values_list('category__slug', flat=True))
           coverage_pct = len(covered_slugs) / total_leaf * 100
           self.assertGreaterEqual(coverage_pct, 90.0,
               f"Coverage {coverage_pct:.1f}% is below 90% threshold")
   ```

**Acceptance criteria:**
- New tests exist, are deterministic, and pass
- `test_load_category_fixtures_returns_leaf_only` asserts exactly 171 categories returned
- `test_full_seed_coverage` verifies ≥90% coverage with 600 ads
- Tests would fail if leaf-only filtering is removed (proving the test is meaningful)

---

### T005: Correct seed-workflow documentation

**Priority:** low

**Depends on:** T001, T002

**Risk:** low — documentation only, no code or data changes.

**Goals:**
- Fix the incorrect statement on `docs/ops/seed-workflow.md:188-189` that JSON fixtures are "not committed (gitignored)"
- Update default ad count references from 30 to 600
- Clarify that `photo_manifest.json` covers all 205 categories (leaf + non-leaf)

**Files:**
- `docs/ops/seed-workflow.md`

**Detailed changes:**

1. **Line 188-189** — Replace:
   > These fixture files are **not** committed (gitignored) and are populated
   > locally or in CI.
   
   With:
   > `photo_manifest.json`, `query_hierarchy.json`, `ads_templates.json`, and
   > `word_lists.json` are committed to git. Only JPEG files (`*.jpg`) and
   > `seed-images-config.json` are gitignored (see `.gitignore` lines 224-228).

2. **Line 34** — Update `python manage.py seed --users=20 --ads=100 --force` example
   to reflect new defaults (keep example values, but add note about default).

3. **Line 35** — Update default count in comment: `# Generate default seed data (10 users, 600 ads)`.

4. **Section 5.2 (Key Architecture Decisions)** — Add note about the photo manifest
   having entries for all 205 categories (not just leaf).

**Acceptance criteria:**
- No incorrect statements about fixture gitignore status remain
- All default ad count references updated
- Documentation in English only (project rule 1)
- All links still valid

---

### T006: Full test suite run + verification

**Priority:** high

**Depends on:** T003, T004, T005

**Risk:** low — verification step, no code changes.

**Goals:**
- All seed module tests pass
- No regressions in related modules (ads, categories, analytics)
- Coverage verification confirmed

**Steps:**
1. Start test DB: `docker compose --project-name mko-bazuna-test -f docker-compose.yml -f docker-compose.test.yml up -d db`
2. Verify DB is running: `docker ps --filter "name=mko-bazuna-test-db-" --filter "status=running"`
3. Run full seed test suite: `docker compose --project-name mko-bazuna-test -f docker-compose.yml -f docker-compose.test.yml run --rm test`
4. Run with verbose filter for seed tests: `... -e PYTEST_OPTS="--reuse-db --create-db --tb=short -v src/backend/apps/seed/tests/" test`

**Acceptance criteria:**
- All tests pass with 0 failures
- No test takes >60s (seed coverage test with 600 ads should complete within timeout)
- `ruff check src/backend/apps/seed/` passes
- `basedpyright src/backend/apps/seed/` passes (or no new type errors)

---

## Risk Assessment Summary

| Task | Risk | Reason | Mitigation |
|------|------|--------|------------|
| T001 | low | Single method change with clear intent | MPTT `children__isnull=True` is well-established pattern |
| T002 | low | Config value changes only | CLI/env override still works for custom counts |
| T003 | low | Test modifications only | Existing tests already use leaf categories in most cases |
| T004 | low | New test cases | Tests designed to fail if fix is reverted |
| T005 | low | Documentation only | Verified against actual `.gitignore`/`.dockerimage` |
| T006 | low | Verification only | Standard test commands per `.ai/context/commands.md` |

## Pre-implementation Checks

Before starting implementation:

1. Verify `Category` model has `children` reverse FK (confirmed: `categories/models.py:42`, `related_name="children"`)
2. Verify test DB is running before tests: `docker ps --filter "name=mko-bazuna-test-db-"`
3. Verify no other code depends on `SeedService._load_category_fixtures()` returning ALL categories
4. Verify the `CATEGORY_GROUP_MAP` in `ads.py` already covers all 171 leaf slugs (confirmed: comment says "All 171 leaf slugs")
