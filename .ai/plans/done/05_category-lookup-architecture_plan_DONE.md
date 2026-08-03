# Implementation Plan: Category + Universal Lookup Architecture

**Source:** `.ai/problems/04_category-lookup-architecture_spec.md`
**Date:** 2026-08-02
**Status:** Draft

---

## Execution DAG Overview

```
Phase 0 — Foundation (parallel)
  TASK_001  ──┐
  TASK_002  ──┤
  TASK_003  ──┘
               │
Phase 1 — Relationships (serial)
               ├── TASK_004 (needs 001, 002)
               │     └── TASK_005 (needs 004)
               │
Phase 2a — Catalog System (parallel with 2b, 2c)
               └── TASK_006 (needs 001, 004)      ← RESEARCH GATE
                     └── TASK_007 (needs 006)
                           └── TASK_016 (cleanup, needs 007)
               │
Phase 2b — Lookup Services
               ├── TASK_008 (needs 004)
               ├── TASK_009 (needs 001)
               │
Phase 2c — Admin Interfaces (parallel within)
               ├── TASK_010 (needs 001)
               └── TASK_011 (needs 004, 005)
               │
Phase 3 — Bot & Features (parallel)
               ├── TASK_012 (needs 005, 008)
               ├── TASK_013 (needs 005)
               └── TASK_014 (needs 002)
               │
Phase 4 — Verification
               └── TASK_015 (needs all above)
```

---

## Execution Order

```yaml
tasks:
  - id: task_001
    depends_on: []

  - id: task_002
    depends_on: []

  - id: task_003
    depends_on: []

  - id: task_004
    depends_on:
      - task_001
      - task_002

  - id: task_005
    depends_on:
      - task_004

  - id: task_006
    depends_on:
      - task_001
      - task_004
    blocked_by:
      - research_001

  - id: task_007
    depends_on:
      - task_006

  - id: task_008
    depends_on:
      - task_004

  - id: task_009
    depends_on:
      - task_001

  - id: task_010
    depends_on:
      - task_001

  - id: task_011
    depends_on:
      - task_004
      - task_005

  - id: task_012
    depends_on:
      - task_005
      - task_008

  - id: task_013
    depends_on:
      - task_005

  - id: task_014
    depends_on:
      - task_002

  - id: task_015
    depends_on:
      - task_005
      - task_007
      - task_009
      - task_012
      - task_013
      - task_014

  - id: task_016
    depends_on:
      - task_007
```

---

## Research Gates

### research_001: Migration dependency ordering for catalog builder

**Risk:** Modifies shared configuration / changes migrations.

**Problem:** The catalog data migration (`categories/XXXX_load_catalog.py`) calls `builder.load_catalog()` which creates `LookupGroup`, `LookupItem`, `Category`, `CategoryListingPurpose`, `CategoryListingFeature`, and `CategoryPath` records. Django requires explicit `dependencies = [...]` in the migration class to ensure model-creating migrations from the `lookups` app run first.

**Research scope:**
1. Confirm the migration filename pattern: `lookups/0001_initial.py` (from TASK_001) and the through-table migration from TASK_004
2. Determine exact `dependencies` declaration in the catalog migration:
   ```python
   class Migration(migrations.Migration):
       dependencies = [
           ("lookups", "0001_initial"),
           ("categories", "XXXX_add_through_tables"),
       ]
       operations = [
           RunPython(load_catalog, reverse_code=migrations.RunPython.noop),
       ]
   ```
3. Verify that MPTT `insert_at()` works correctly inside a `RunPython` operation (no transaction or MPTT cache issues)
4. Confirm the `SeedService` replacement path: `SeedService._load_category_fixtures()` is replaced with `builder.load_catalog()`, no other callers exist
5. Verify what happens to the old `categories.json` fixture — confirm it's safe to delete (no other module reads it)

**Deliverable:** A short document specifying the exact migration dependency declarations and the SeedService replacement signature.

**Blocks:** TASK_006 (builder module), TASK_007 (data migration)

---

## Task Specifications

---

### TASK_001: Create lookups Django app with LookupGroup + LookupItem models

**Priority:** high

**Depends on:** none

**Source:** Spec sections 2.2 (L01-L07), models defined at lines 160-183

**Description:**
Create a new Django app `apps/lookups/` with two models: `LookupGroup` (reference data group) and `LookupItem` (individual value within a group). The app provides the foundation for the universal reference data system.

**Goals:**
- Create `apps/lookups/` app structure (`__init__.py`, `apps.py`, `models.py`, `admin.py` stub)
- Create `apps/lookups/enums.py` with `LookupGroupCode(StrEnum)` for `listing_purpose`, `listing_feature` codes (spec L13)
- Define `LookupGroup` model with `code`, `name_i18n`, `is_system`, `sort_order`
- Define `LookupItem` model with `group` FK, `slug`, `name_i18n`, `sort_order`, `is_active`, `icon`, `color`
- Generate initial migration `lookups/0001_initial.py`
- Register app in `INSTALLED_APPS` (`config/settings/base.py`)

**Affected modules:**
- `apps/lookups/__init__.py` — new file
- `apps/lookups/enums.py` — new file, `LookupGroupCode(StrEnum)` class
- `apps/lookups/apps.py` — new `LookupsConfig(AppConfig)` class
- `apps/lookups/models.py` — new `LookupGroup` class, new `LookupItem` class
- `apps/lookups/admin.py` — new file (empty or stub)
- `apps/lookups/migrations/0001_initial.py` — new migration
- `apps/core/config/settings/base.py` — add `apps.lookups` to `INSTALLED_APPS`

**Semantic insertion points:**
- `base.py`: array `INSTALLED_APPS`, insert `"apps.lookups"` after `"apps.media"` (follow existing alphabetical-by-app convention)

**StrEnum definition (spec L13 — group codes as StrEnum, not plain strings):**

```python
# apps/lookups/enums.py
from enum import StrEnum

class LookupGroupCode(StrEnum):
    """Machine-readable codes for built-in lookup groups.

    Used in model field limit_choices_to, builder, and resolver —
    never plain strings.
    """
    LISTING_PURPOSE = "listing_purpose"
    LISTING_FEATURE = "listing_feature"
```

Reference this enum (via `from apps.lookups.enums import LookupGroupCode`) in all model field `limit_choices_to` lookups, builder code, and resolver code instead of inline string literals.

**Model definitions (exact from spec):**

```python
from apps.lookups.enums import LookupGroupCode

class LookupGroup(models.Model):
    code = models.CharField(max_length=100, unique=True)  # machine-readable, immutable
    name_i18n = models.JSONField(null=True, blank=True)   # {'ru': str, 'bs': str, 'en': str}
    is_system = models.BooleanField(default=False)         # protected from admin deletion
    sort_order = models.PositiveIntegerField(default=0)
    # Meta: db_table = "lookup_groups", ordering = ["sort_order"]
    # __str__: return self.code

class LookupItem(models.Model):
    group = models.ForeignKey(LookupGroup, CASCADE, related_name="items")
    slug = models.SlugField(max_length=100, unique=True)  # globally unique
    name_i18n = models.JSONField(null=True, blank=True)
    sort_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    icon = models.CharField(max_length=50, blank=True, default="")
    color = models.CharField(max_length=7, blank=True, default="")
    # Meta: db_table = "lookup_items", ordering = ["group", "sort_order"]
    # __str__: return self.slug
```

**Changes:**
1. Create `apps/lookups/` package directory with `__init__.py`
2. Create `apps/lookups/apps.py` with `LookupsConfig(AppConfig)`
3. Create `apps/lookups/models.py` with `LookupGroup` and `LookupItem` as specified above
4. Create `apps/lookups/admin.py` as empty (admin implemented in TASK_010)
5. Create `apps/lookups/__init__.py`
6. Run `python manage.py makemigrations lookups` to generate `0001_initial.py`
7. Add `"apps.lookups"` to `INSTALLED_APPS` in `config/settings/base.py`

**Acceptance criteria:**
- `LookupGroupCode` StrEnum exists with `LISTING_PURPOSE` and `LISTING_FEATURE` members
- `LookupGroup` and `LookupItem` models exist with all specified fields
- `LookupItem.slug` is globally unique
- `LookupItem.group` FK cascades on delete
- Migration applies cleanly (`uv run python manage.py migrate lookups`)
- LookupsConfig is registered correctly

---

### TASK_002: Add CategoryPath model to categories app

**Priority:** high

**Depends on:** none (uses existing Category model only)

**Source:** Spec section 2.1, CategoryPath model at lines 64-78

**Description:**
Add `CategoryPath` model to `apps/categories/models.py` for multi-parent navigation support. Each category can have zero or more alternative parent routes while maintaining a single canonical MPTT parent.

**Goals:**
- Define `CategoryPath` model with `category`, `parent`, `sort_order`, `is_automatic` fields
- Unique constraint on `(category, parent)`
- Generate migration `categories/XXXX_categorypath.py`
- No MPTT integration — CategoryPath is a simple FK model

**Affected modules:**
- `apps/categories/models.py` — add `CategoryPath` class
- `apps/categories/migrations/XXXX_categorypath.py` — new migration

**Semantic insertion points:**
- `models.py`: insert `CategoryPath` class after `Category` class definition

**Model definition (exact from spec):**

```python
class CategoryPath(models.Model):
    category = models.ForeignKey(
        Category, CASCADE, related_name="alternative_parents"
    )
    parent = models.ForeignKey(
        Category, CASCADE, related_name="alternative_children"
    )
    sort_order = models.PositiveIntegerField(default=0)
    is_automatic = models.BooleanField(
        default=False,
        help_text="True if created by system rule (e.g. price=0 -> Благотворительность)"
    )

    class Meta:
        db_table = "category_paths"
        unique_together = [("category", "parent")]
        ordering = ["sort_order"]
        verbose_name_plural = "category paths"

    def __str__(self):
        return f"{self.category.slug} → {self.parent.slug}"

    def clean(self):
        """Validate: category != parent, no cycles."""
        from django.core.exceptions import ValidationError
        if self.category_id == self.parent_id:
            raise ValidationError("A category cannot be an alternative parent of itself")
        # Cycle detection: walk parent chain, ensure no loop back to category
        # (implemented via ancestor check in service/admin layer)
```

**Changes:**
1. Add `CategoryPath` model to `apps/categories/models.py`
2. Run `makemigrations categories` to generate migration
3. Add `clean()` method with self-reference validation (full cycle detection deferred to admin/service layer per spec open question Q1)

**Acceptance criteria:**
- `CategoryPath` model exists with all specified fields and constraints
- Unique constraint on `(category, parent)` works
- Self-reference raises validation error
- Migration applies cleanly

---

### TASK_003: Create FileHashService and add SHA-256 to AdImage

**Priority:** high

**Depends on:** none

**Source:** Spec section 2.6 (PD01-PD06)

**Description:**
Add photo deduplication capability. Create a `FileHashService` with `calculate_sha256()` method, add `sha256` field to `AdImage`, override `save()` to auto-compute hash on creation, and add a backfill data migration for existing rows.

**Goals:**
- Create `FileHashService.calculate_sha256(file_path) -> str` in `apps/media/services/`
- Add `sha256` CharField(64) to `AdImage` model
- Override `AdImage.save()` to compute SHA-256 when creating a new record
- Add index on `sha256` column
- Create backfill migration for existing `AdImage` rows
- Implement skip-duplicate logic: if same user already has same hash → reuse existing record

**Affected modules:**
- `apps/media/services/__init__.py` — no changes needed (already has `ThumbnailService`)
- `apps/media/services/hash_service.py` — new file, `FileHashService` class
- `apps/ads/models.py` — modify `AdImage` class
- `apps/ads/migrations/XXXX_adimage_sha256.py` — new migration (schema + data backfill)

**Semantic insertion points:**
- `apps/media/services/`: new file `hash_service.py` alongside existing `thumbnails.py`
- `apps/ads/models.py`: class `AdImage` — add `sha256` field, add `save()` override

**FileHashService:**

```python
import hashlib

class FileHashService:
    @staticmethod
    def calculate_sha256(file_path: str) -> str:
        """Compute SHA-256 hex digest of a file."""
        sha256 = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                sha256.update(chunk)
        return sha256.hexdigest()
```

**AdImage changes:**
- Add field: `sha256 = models.CharField(max_length=64, db_index=True, blank=True, default="")`
- Override `save()`:
  - If `_state.adding` or not `sha256`: compute SHA-256 from the physical file at `self.image` path
  - If same user's ad already has an `AdImage` with same SHA-256 → skip (return early, do not create duplicate)
- The `user` is accessed via `self.ad.user_id` (Ad FK → User)

**Backfill migration:**
- `RunPython` that iterates all `AdImage` rows where `sha256 = ""`
- For each: compute hash from stored file at `MEDIA_ROOT / image`
- Batch size: 100 to avoid memory issues

**Acceptance criteria:**
- `FileHashService.calculate_sha256()` returns correct hex digest
- New `AdImage` records auto-compute SHA-256
- Duplicate detection works across images in the same user's ads
- Backfill migration processes existing rows without error
- Index on `sha256` exists

---

### TASK_004: Create through models CategoryListingPurpose + CategoryListingFeature

**Priority:** high

**Depends on:** TASK_001 (LookupGroup, LookupItem), TASK_002 (CategoryPath not needed — just needs Category which already exists)

**Source:** Spec section 2.2, through models at lines 187-216

**Description:**
Create two M:N through tables binding `Category` ↔ `LookupItem` for listing purposes and listing features. `CategoryListingPurpose` carries an `is_default` flag. These models enable category-specific lookup value filtering and inheritance.

**Goals:**
- Define `CategoryListingPurpose` with `category`, `listing_purpose` (FK to LookupItem), `is_default`
- Define `CategoryListingFeature` with `category`, `feature` (FK to LookupItem)
- Unique constraints on both through tables
- Composite indexes for resolution performance
- `is_default` unique-per-category enforcement (application level)
- Generate migration

**Affected modules:**
- `apps/categories/models.py` — add `CategoryListingPurpose`, `CategoryListingFeature` classes
- `apps/categories/migrations/XXXX_through_tables.py` — new migration

**Semantic insertion points:**
- `models.py`: insert both through models after `CategoryPath` class

**Model definitions:**

```python
from apps.lookups.enums import LookupGroupCode

class CategoryListingPurpose(models.Model):
    category = models.ForeignKey(Category, CASCADE, related_name="listing_purposes")
    listing_purpose = models.ForeignKey(
        "lookups.LookupItem", CASCADE,
        limit_choices_to={"group__code": LookupGroupCode.LISTING_PURPOSE},
        related_name="category_purposes",
    )
    is_default = models.BooleanField(
        default=False,
        help_text="Default purpose for this category; auto-selected when seller doesn't choose explicitly"
    )

    class Meta:
        db_table = "category_listing_purposes"
        unique_together = [("category", "listing_purpose")]
        indexes = [
            models.Index(fields=["category", "listing_purpose"]),
            models.Index(fields=["listing_purpose"]),
        ]
        verbose_name_plural = "category listing purposes"

    def __str__(self):
        return f"{self.category.slug} → {self.listing_purpose.slug}"


class CategoryListingFeature(models.Model):
    category = models.ForeignKey(Category, CASCADE, related_name="listing_features")
    feature = models.ForeignKey(
        "lookups.LookupItem", CASCADE,
        limit_choices_to={"group__code": LookupGroupCode.LISTING_FEATURE},
        related_name="category_features",
    )

    class Meta:
        db_table = "category_listing_features"
        unique_together = [("category", "feature")]
        indexes = [
            models.Index(fields=["category", "feature"]),
            models.Index(fields=["feature"]),
        ]
        verbose_name_plural = "category listing features"

    def __str__(self):
        return f"{self.category.slug} → {self.feature.slug}"
```

**Changes:**
1. Add `CategoryListingPurpose` class to `apps/categories/models.py`
2. Add `CategoryListingFeature` class to `apps/categories/models.py`
3. Run `makemigrations categories` to generate migration

**Acceptance criteria:**
- Both through models exist with all specified fields and constraints
- Unique constraints work: duplicate `(category, listing_purpose)` or `(category, feature)` raises IntegrityError
- Composite and single-column indexes exist
- Migration applies cleanly

---

### TASK_005: Add listing_purpose and features to Ad model + data migration

**Priority:** high

**Depends on:** TASK_004 (through models + LookupItem exists)

**Source:** Spec section 2.3 (A01-A04), AdFeature through model at lines 291-302

**Description:**
Add `listing_purpose` FK and `features` M:N relationship to the `Ad` model. Create `AdFeature` through model with `sort_order`. Create data migration to assign a default `listing_purpose` (`sell`) to all existing ads.

**Goals:**
- Add `listing_purpose` FK field on `Ad` (required, PROTECT, limit_choices_to)
- Add `features` M2M field on `Ad` through `AdFeature` (optional, blank)
- Create `AdFeature` through model with `ad`, `feature`, `sort_order`
- Generate schema migration
- Create data migration: assign `sell` purpose to all existing ads without one

**Affected modules:**
- `apps/ads/models.py` — modify `Ad` class, add `AdFeature` class
- `apps/ads/migrations/XXXX_ad_listing_purpose.py` — schema migration
- `apps/ads/migrations/XXXX_backfill_listing_purpose.py` — data migration

**Semantic insertion points:**
- `models.py`: add `listing_purpose` field and `features` field to `Ad` class; add `AdFeature` class after `AdImage` class

**Model changes:**

```python
# On Ad class:
listing_purpose = models.ForeignKey(
    "lookups.LookupItem", PROTECT,
    limit_choices_to={"group__code": LookupGroupCode.LISTING_PURPOSE},
    related_name="ads",
    help_text="What the user wants to do with the object",
)
features = models.ManyToManyField(
    "lookups.LookupItem",
    through="ads.AdFeature",
    through_fields=("ad", "feature"),
    blank=True,
    related_name="featured_ads",
)

# New through model:
class AdFeature(models.Model):
    ad = models.ForeignKey(Ad, CASCADE, related_name="ad_features")
    feature = models.ForeignKey(
        "lookups.LookupItem", CASCADE,
        limit_choices_to={"group__code": LookupGroupCode.LISTING_FEATURE},
    )
    sort_order = models.PositiveIntegerField(default=0, help_text="Display order")

    class Meta:
        db_table = "ad_features"
        unique_together = [("ad", "feature")]
        ordering = ["sort_order"]

    def __str__(self):
        return f"Ad {self.ad_id} → {self.feature.slug}"
```

**Data migration:**
- `RunPython`:
  1. Find or create `LookupItem` with slug=`sell` in group `listing_purpose` (seed value — this item must exist before the data migration runs; the catalog migration in TASK_007 will create it, but the data migration must handle the case where it doesn't exist yet by creating it inline)
  2. For all `Ad` rows where `listing_purpose_id IS NULL`: set `listing_purpose_id = sell_item.id`

**Important migration order consideration:**
- This data migration must run AFTER the catalog migration (TASK_007) that creates the `sell` lookup item exists in the database. The data migration should either:
  a. Be a separate migration that depends on the catalog migration, OR
  b. Create the `sell` LookupItem inline (get_or_create) so it's self-contained

  Option (b) is safer — the data migration creates the `sell` item if it doesn't exist, making it independent of the catalog migration order.

**Acceptance criteria:**
- `Ad.listing_purpose` FK exists (non-nullable, PROTECT on delete)
- `Ad.features` M2M exists (blank=True)
- `AdFeature` through model exists with unique_together constraint
- Data migration assigns `sell` to all existing ads
- New ads require `listing_purpose` at creation

---

### RESEARCH GATE: research_001

**(See Research Gates section above)**

---

### TASK_006: Create categories.yaml catalog config and builder module

**Priority:** high

**Depends on:** TASK_001 (models exist), TASK_004 (through models exist)
**Blocked by:** research_001 (migration dependency research)

**Source:** Spec sections 2.9 (CF01-CF15), YAML structure at lines 441-487, rename mechanism at lines 350-399

**Description:**
Create the canonical YAML config file `apps/categories/catalog/categories.yaml` with full category tree, lookup definitions, and bindings. Create `builder.py` module with `load_catalog()` supporting `new_slug` rename, `slug_rename_map`, auto-resolve `category_paths`, and auto-rewrite YAML after rename.

**Goals:**
- Create `apps/categories/catalog/categories.yaml` with `lookups`, `categories`, `category_paths` sections
- Create `apps/categories/catalog/__init__.py`
- Create `apps/categories/catalog/builder.py` with `load_catalog(config_path)` function
- Builder creates in order: LookupGroup → LookupItem → Category tree (L1→L4) → CategoryListingPurpose → CategoryListingFeature → CategoryPath
- Builder uses `update_or_create` by `slug`, MPTT `insert_at()` for tree insertion
- Support `new_slug` transient field for renames with auto-rewrite
- Maintain `slug_rename_map: dict[str, str]` for cross-reference resolution
- Handle `deferred: true` categories (skip, keep in config)
- Atomic YAML rewrite via temp file + `os.replace`

**Affected modules:**
- `apps/categories/catalog/__init__.py` — new package
- `apps/categories/catalog/categories.yaml` — new file (the canonical config)
- `apps/categories/catalog/builder.py` — new module, `load_catalog()` function

**YAML source data:**
The canonical tree structure is defined in `.ai/problems/categories_tree_bazuna.md`. The YAML file must be generated from that document, structured as:

```yaml
lookups:
  listing_purpose:
    - slug: sell
      name_i18n: {ru: "Продажа", bs: "Prodaja", en: "Sell"}
      sort_order: 1
    # ... all 10 purposes from spec

  listing_feature:
    - slug: new
      name_i18n: {ru: "Новый", bs: "Novo", en: "New"}
      sort_order: 1
    # ... all features from spec

categories:
  - slug: real-estate
    name: "Недвижимость"
    name_i18n: {ru: "Недвижимость", bs: "Nekretnine", en: "Real Estate"}
    listing_purpose_override: [sell, rent, rent-request, buy, exchange]
    listing_feature_override: [new, used, urgent, with-document, negotiable, with-installment]
    children:
      - slug: apartments
        name: "Квартиры"
        # inherits purposes/features from parent unless overridden
    # ... full tree from categories_tree_bazuna.md

category_paths:
  - category: bicycles
    parent: transport
  - category: auto-parts
    parent: goods
  # ... all alternative paths
```

**Builder interface:**

```python
def load_catalog(config_path: str | Path) -> dict[str, str]:
    """Load catalog from YAML config. Creates/updates all records.

    Args:
        config_path: Path to categories.yaml file.

    Returns:
        slug_rename_map: {old_slug: new_slug} for any renames that occurred.
    """


def _load_lookups(data: dict) -> dict:
    """Create/update LookupGroup and LookupItem records. Returns group_map."""


def _load_categories(data: dict, group_map: dict) -> dict:
    """Create/update Category tree level by level. Returns category_map."""


def _load_bindings(data: dict, category_map: dict, group_map: dict) -> None:
    """Create/update CategoryListingPurpose and CategoryListingFeature."""


def _load_category_paths(data: dict, category_map: dict) -> None:
    """Create/update CategoryPath records."""
```

**Key builder behaviors:**
1. Match by slug, update fields if exists
2. If `new_slug` present: write `slug=new_slug` to DB, track in `slug_rename_map`
3. Category tree: process level by level (L1→L2→L3→L4), use `insert_at(parent, position='last-child')` for MPTT
4. `category_paths`: resolve old/new slugs via `_resolve_slug()` using `slug_rename_map`
5. After successful run: auto-rewrite YAML (remove new_slug, update slug)
6. `deferred: true` categories: skip entirely

**Acceptance criteria:**
- `categories.yaml` contains all lookup groups, lookup items, category tree, and paths from the canonical tree document
- `builder.load_catalog()` creates all records in correct order
- Builder is idempotent: second run produces no duplicate records
- Rename via `new_slug` works correctly: slug is updated, map tracks old→new
- Auto-rewrite produces valid YAML without `new_slug` fields
- Deferred categories are skipped
- `category_paths` with old slugs resolve correctly after rename

---

### TASK_007: Create catalog data migration + replace SeedService + remove old artifacts

**Priority:** high

**Depends on:** TASK_006 (builder module + YAML config exist)

**Source:** Spec sections CF13-CF15, SeedService replacement at T12, cleanup at T14

**Description:**
Create the data migration that calls `builder.load_catalog()`. Replace `SeedService._load_category_fixtures()` with a call to the same builder. Remove old artifacts: `0002_seed_categories.py` migration, `categories.json` fixture.

**Goals:**
- Create `categories/XXXX_load_catalog.py` data migration calling `builder.load_catalog()`
- Replace `SeedService._load_category_fixtures()` with `builder.load_catalog()`
- Delete `categories/0002_seed_categories.py` migration (replace with squashed equivalent)
- Delete `categories.json` fixture file
- Verify no other code references deleted artifacts

**Affected modules:**
- `apps/categories/migrations/XXXX_load_catalog.py` — new migration
- `apps/seed/services/seed_service.py` — modify `SeedService`, replace `_load_category_fixtures()`
- `apps/categories/migrations/0002_seed_categories.py` — DELETE
- `apps/seed/fixtures/categories.json` — DELETE (or wherever the fixture lives)

**Migration dependency declaration (from research_001):**

```python
from django.db import migrations
from apps.categories.catalog.builder import load_catalog

CONFIG_PATH = "apps/categories/catalog/categories.yaml"


def load_catalog_forward(apps, schema_editor):
    load_catalog(CONFIG_PATH)


class Migration(migrations.Migration):
    dependencies = [
        ("lookups", "0001_initial"),
        ("categories", "XXXX_through_tables"),  # the migration from TASK_004
    ]

    operations = [
        migrations.RunPython(load_catalog_forward, reverse_code=migrations.RunPython.noop),
    ]
```

**SeedService changes:**
```python
# Replace _load_category_fixtures() body:
def _load_category_fixtures(self) -> list[Category]:
    from apps.categories.catalog.builder import load_catalog
    load_catalog(CONFIG_PATH)
    return list(Category.objects.all())
```

**Old migration handling:**
- `0002_seed_categories.py` cannot be simply deleted because migrations form a chain. Options:
  a. If no deployments exist yet: delete the file and recreate from scratch
  b. Create a new migration that replaces 0002 by squashing: `0003_squash_0002.py` with `replaces = [("categories", "0002_seed_categories")]`
  
  Since this is pre-production (spec says "Phase 1"), option (a) is preferred: delete `0002_seed_categories.py` and regenerate migrations from clean state.

**Acceptance criteria:**
- Data migration runs successfully and populates all catalog data
- `SeedService` loads cats -> via builder, JSON fixture no longer needed
- No broken references to deleted artifacts
- `0002_seed_categories.py` is gone (or properly squashed)

---

### TASK_008: Create CategoryLookupResolver service

**Priority:** high

**Depends on:** TASK_004 (through models exist)

**Source:** Spec section 2.2, "CategoryLookupResolver Service" at lines 218-261

**Description:**
Create the `CategoryLookupResolver` service class that resolves inherited purposes and features via MPTT ancestor walk-up. Implements the nearest-explicit-ancestor-wins algorithm with caching. Provides `get_resolved_purposes()`, `get_resolved_features()`, `get_resolved_purpose_codes()`, `get_resolved_feature_codes()`, and `invalidate_*()` methods.

**Goals:**
- Create `apps/categories/services/__init__.py`
- Create `apps/categories/services/lookup_resolution.py` with `CategoryLookupResolver` class
- Implement resolution algorithm (2-query, nearest-ancestor-wins)
- Integrate with cache (cache key pattern: `lookup:resolved_purposes:{category_id}`)
- TTL: 300 seconds
- Support invalidation by category_id and by lookup_item_id

**Affected modules:**
- `apps/categories/services/__init__.py` — new file
- `apps/categories/services/lookup_resolution.py` — new file, `CategoryLookupResolver` class

**Service interface:**

```python
class CategoryLookupResolver:
    def get_resolved_purposes(self, category: Category) -> list[LookupItem]:
        """Get resolved listing purposes for a category (inherited + active only)."""

    def get_resolved_features(self, category: Category) -> list[LookupItem]:
        """Get resolved listing features for a category (inherited + active only)."""

    def get_resolved_purpose_codes(self, category: Category) -> list[str]:
        """Get resolved purpose codes as string slugs."""

    def get_resolved_feature_codes(self, category: Category) -> list[str]:
        """Get resolved feature codes as string slugs."""

    def invalidate_category(self, category_id: int) -> None:
        """Invalidate cache for a category and all its descendants."""

    def invalidate_lookup_item(self, lookup_item_id: int) -> None:
        """Invalidate cache for all categories that reference a given LookupItem."""
```

**Resolution algorithm:**
```python
def _resolve(self, category: Category, through_model, cache_key_prefix: str) -> list[LookupItem]:
    # 1. Check cache
    cache_key = f"{cache_key_prefix}:{category.id}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    # 2. Get ancestors including self (MPTT single query)
    ancestors = category.get_ancestors(include_self=True, ascending=True)

    # 3. Query all through-table bindings for ancestors, joined to LookupItem (active only)
    bindings = through_model.objects.filter(
        category__in=ancestors,
        listing_purpose__is_active=True,  # or feature__is_active=True
    ).select_related("listing_purpose")   # or "feature"

    # 4. Group by category_id, return first group with rows
    grouped = {}
    for b in bindings:
        grouped.setdefault(b.category_id, []).append(b)

    result = []
    for ancestor in ancestors:
        if ancestor.id in grouped:
            result = [b.listing_purpose for b in grouped[ancestor.id]]
            break

    # 5. Cache and return
    cache.set(cache_key, result, 300)
    return result
```

**Changes:**
1. Create `apps/categories/services/` package with `__init__.py`
2. Create `apps/categories/services/lookup_resolution.py` with `CategoryLookupResolver` class
3. Import existing cache utilities from `apps/core/utils/cache.py` (or use `django.core.cache.cache` directly)

**Acceptance criteria:**
- Resolution returns correct inherited values via ancestor walk-up
- Override replaces (not merges) parent values
- Inactive LookupItems are filtered out
- Cache hit returns without DB query
- `invalidate_category()` clears cache for category + descendants
- `invalidate_lookup_item()` clears cache for all referencing categories

---

### TASK_009: Create lookup caching service with signal-based invalidation

**Priority:** high

**Depends on:** TASK_001 (LookupGroup, LookupItem models exist)

**Source:** Spec section 2.7 (CA01-CA06)

**Description:**
Create a caching layer for `LookupGroup` and `LookupItem` records with signal-based invalidation. Implements cache-and-invalidate pattern: all lookup records cached with 1-hour TTL, invalidated on `post_save` / `post_delete` signals. Also handles `CategoryLookupResolver` resolved cache invalidation on through-table changes, LookupItem.is_active toggles, and Category MPTT moves.

**Goals:**
- Create `apps/lookups/services/__init__.py` and `apps/lookups/services/cache_service.py`
- Implement `LookupCacheService` with `get_all_groups()`, `get_group_items()`, `invalidate_all()`
- Connect signal handlers for `LookupGroup`, `LookupItem`, `CategoryListingPurpose`, `CategoryListingFeature`
- Handle `is_active` toggle on LookupItem: reverse-lookup through-table rows, invalidate affected categories + descendants
- Handle Category `move_to()`: invalidate old and new subtrees

**Affected modules:**
- `apps/lookups/services/__init__.py` — new package
- `apps/lookups/services/cache_service.py` — new service
- `apps/lookups/signals.py` — new signal handlers
- `apps/lookups/apps.py` — connect signals in `ready()`
- `apps/categories/signals.py` — new signal handlers for through-table changes
- `apps/categories/apps.py` — connect signals in `ready()`

**Service interface:**

```python
class LookupCacheService:
    @staticmethod
    def get_all_groups() -> list[LookupGroup]:
        """Get all lookup groups (cached)."""

    @staticmethod
    def get_active_items(group_code: str) -> list[LookupItem]:
        """Get active items for a group (cached)."""

    @staticmethod
    def invalidate_all() -> None:
        """Invalidate all lookup caches."""

    @staticmethod
    def invalidate_group(group_code: str) -> None:
        """Invalidate cache for a specific group."""
```

**Signal handlers:**

```python
# In apps/lookups/signals.py:
@receiver(post_save, sender=LookupGroup)
@receiver(post_delete, sender=LookupGroup)
@receiver(post_save, sender=LookupItem)
@receiver(post_delete, sender=LookupItem)
def invalidate_lookup_cache(sender, instance, **kwargs):
    LookupCacheService.invalidate_all()


# In apps/categories/signals.py:
@receiver(post_save, sender=CategoryListingPurpose)
@receiver(post_delete, sender=CategoryListingPurpose)
@receiver(post_save, sender=CategoryListingFeature)
@receiver(post_delete, sender=CategoryListingFeature)
def invalidate_category_lookup_cache(sender, instance, **kwargs):
    resolver = CategoryLookupResolver()
    # Invalidate the affected category + all descendants
    resolver.invalidate_category(instance.category_id)


@receiver(post_save, sender=LookupItem)
def invalidate_on_lookup_item_change(sender, instance, **kwargs):
    if kwargs.get("update_fields") and "is_active" not in kwargs["update_fields"]:
        return
    resolver = CategoryLookupResolver()
    resolver.invalidate_lookup_item(instance.id)
```

**Changes:**
1. Create `apps/lookups/services/` package
2. Create `LookupCacheService` in `cache_service.py`
3. Create `apps/lookups/signals.py` with group/item invalidation handlers
4. Connect signals in `LookupsConfig.ready()`
5. Create `apps/categories/signals.py` (if not existing) with through-table and LookupItem invalidation handlers
6. Connect signals in `CategoriesConfig.ready()`

**Acceptance criteria:**
- `LookupCacheService.get_all_groups()` returns cached groups after first call
- Cache invalidates on any LookupGroup/LookupItem save/delete
- Through-table changes invalidate the affected category's resolved cache
- LookupItem.is_active toggle invalidates all referencing categories
- Category MPTT move invalidates both old and new subtrees

---

### TASK_010: Implement Lookup admin UI

**Priority:** medium

**Depends on:** TASK_001 (models exist)

**Source:** Spec section 2.4 (AD01, AD02, AD06)

**Description:**
Create admin interfaces for `LookupGroup` and `LookupItem`. Group admin with inline items. System groups protected from deletion. Group filter on item list.

**Goals:**
- `LookupGroupAdmin` with `list_display`, inline `LookupItem` (TabularInline)
- `LookupItemAdmin` with `list_display`, `list_filter` by group, search by slug/name
- `LookupGroupAdmin.has_delete_permission()` blocked for `is_system = True`
- `is_system` field read-only in admin for existing records

**Affected modules:**
- `apps/lookups/admin.py` — implement full admin

**Admin configuration:**

```python
class LookupItemInline(TabularInline):
    model = LookupItem
    fields = ["slug", "sort_order", "is_active", "icon", "color"]
    extra = 1
    ordering = ["sort_order"]


@admin.register(LookupGroup)
class LookupGroupAdmin(admin.ModelAdmin):
    list_display = ["code", "sort_order", "is_system", "item_count"]
    list_filter = ["is_system"]
    search_fields = ["code"]
    inlines = [LookupItemInline]
    readonly_fields = ["is_system"]  # prevent toggling in admin

    def item_count(self, obj):
        return obj.items.count()
    item_count.short_description = "Items"

    def has_delete_permission(self, request, obj=None):
        if obj and obj.is_system:
            return False
        return super().has_delete_permission(request, obj)


@admin.register(LookupItem)
class LookupItemAdmin(admin.ModelAdmin):
    list_display = ["slug", "group", "is_active", "sort_order"]
    list_filter = ["group", "is_active"]
    search_fields = ["slug", "name_i18n"]
    ordering = ["group", "sort_order"]
```

**Acceptance criteria:**
- Both admins are registered and functional
- LookupItemInline appears under LookupGroup change page
- System groups cannot be deleted via admin
- `is_system` is read-only in the admin form

---

### TASK_011: Extend CategoryAdmin with inlines + update AdAdmin

**Priority:** medium

**Depends on:** TASK_004 (through models exist), TASK_005 (Ad changes exist)

**Source:** Spec section 2.4 (AD03, AD04, AD05)

**Description:**
Extend `CategoryAdmin` with TabularInline for `CategoryPath`, `CategoryListingPurpose`, and `CategoryListingFeature`. Update `AdAdmin` to include `listing_purpose` and `features` in list display and filters.

**Goals:**
- Add `CategoryPathInline` to `CategoryAdmin` (with drag-and-drop sort_order via grappelli or sortable2)
- Add `CategoryListingPurposeInline` to `CategoryAdmin` (with is_default)
- Add `CategoryListingFeatureInline` to `CategoryAdmin`
- Update `AdAdmin.list_display` to include `listing_purpose`
- Update `AdAdmin.list_filter` to include `listing_purpose`
- Add `features` column to AdAdmin list (or as readonly field in detail)

**Affected modules:**
- `apps/categories/admin.py` — modify `CategoryAdmin` class, add inlines
- `apps/ads/admin.py` — modify `AdAdmin` class

**CategoryAdmin inlines:**

```python
class CategoryPathInline(TabularInline):
    model = CategoryPath
    fk_name = "category"
    fields = ["parent", "sort_order", "is_automatic"]
    readonly_fields = ["is_automatic"]
    extra = 1
    ordering = ["sort_order"]
    autocomplete_fields = ["parent"]
    verbose_name_plural = "Alternative parent paths"


class CategoryListingPurposeInline(TabularInline):
    model = CategoryListingPurpose
    fields = ["listing_purpose", "is_default"]
    extra = 1
    autocomplete_fields = ["listing_purpose"]


class CategoryListingFeatureInline(TabularInline):
    model = CategoryListingFeature
    fields = ["feature"]
    extra = 1
    autocomplete_fields = ["feature"]
```

**AdAdmin updates:**
```python
# In AdAdmin:
list_display = [..., "listing_purpose", "features_list"]
list_filter = [..., "listing_purpose", "features"]
readonly_fields = [..., "listing_purpose", "features"]

def features_list(self, obj):
    return ", ".join(f.slug for f in obj.features.all())
features_list.short_description = "Features"
```

**Acceptance criteria:**
- CategoryAdmin displays all three inlines on the change page
- CategoryPath inline shows parent autocomplete and sort_order
- Purpose inline shows listing_purpose select with is_default checkbox
- Feature inline shows feature select
- AdAdmin shows listing_purpose in list display and filter
- AdAdmin shows features on detail page

---

### TASK_012: Integrate purpose/feature selection into bot FSM

**Priority:** high

**Depends on:** TASK_005 (Ad model changes), TASK_008 (CategoryLookupResolver exists)

**Source:** Spec sections 2.8 (B01-B07), 9 (Q2)

**Description:**
Add listing purpose and feature selection steps to the Telegram bot ad creation FSM. The flow becomes: category → **purpose** → **features** → title → description → price → photos → preview. If only one purpose → auto-select, skip step. If no features → skip features step.

**Goals:**
- Add `PURPOSE` and `FEATURES` states to `AdCreateState` + `AdCreateForm`
- After category selection in `process_category()`: resolve purposes via `CategoryLookupResolver`
- If single purpose: auto-select, skip to next step
- If multiple purposes: show inline keyboard with purpose buttons, default highlighted
- After purpose selection: resolve features, if empty skip to title, else show feature selection
- Feature selection: multi-select with inline keyboard, "Done" button to finish
- Store `listing_purpose_id` and `feature_ids` in FSM state data
- Update `update_ad_and_moderate()` to save `listing_purpose` and `features`
- Handle edge case: 0 resolved purposes → show error, block posting (fallback to `sell`)

**Affected modules:**
- `src/telegram_bot/states.py` — add `AdCreateState.PURPOSE`, `AdCreateState.FEATURES`
- `src/telegram_bot/handlers/ad_create.py` — add `process_purpose()`, `process_features()` handlers; modify `process_category()` to transition to purpose; modify `show_preview()`; modify `update_ad_and_moderate()`

**FSM changes:**

```python
# In states.py:
class AdCreateState(StrEnum):
    CATEGORY = "category"
    PURPOSE = "purpose"        # NEW
    FEATURES = "features"      # NEW
    CITY = "city"
    TITLE = "title"
    DESCRIPTION = "description"
    PRICE = "price"
    PHOTOS = "photos"
    PREVIEW = "preview"

# In ad_create.py AdCreateForm:
class AdCreateForm(StatesGroup):
    category = AdCreateState.CATEGORY
    purpose = AdCreateState.PURPOSE          # NEW
    features = AdCreateState.FEATURES        # NEW
    city = AdCreateState.CITY
    title = AdCreateState.TITLE
    description = AdCreateState.DESCRIPTION
    price = AdCreateState.PRICE
    photos = AdCreateState.PHOTOS
    preview = AdCreateState.PREVIEW
```

**Flow modifications:**
1. `process_category()` — after selecting category, resolve purposes. If 1: auto-select, set state to CITY. If >1: show purpose choice, set state to PURPOSE.

2. `process_purpose()` — receive purpose selection, save `listing_purpose_id`. Resolve features. If empty: set state to CITY. If not empty: show feature choices, set state to FEATURES.

3. `process_features()` — receive feature toggles (add/remove from list). "Done" button finishes, sets state to CITY.

4. `show_preview()` — show selected purpose and features in preview text.

5. `update_ad_and_moderate()` — save `listing_purpose_id` and `features` (via `ad.features.set(...)`) on the Ad.

**Purpose selection keyboard:**
```python
from aiogram.utils.keyboard import InlineKeyboardBuilder

def build_purpose_keyboard(purposes: list, default_slug: str | None = None) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for purpose in purposes:
        text = purpose.name_i18n.get("ru", purpose.slug)
        if purpose.slug == default_slug:
            text = f"✅ {text}"
        builder.button(text=text, callback_data=f"purpose:{purpose.slug}")
    builder.adjust(2)
    return builder.as_markup()
```

**Feature selection keyboard:**
```python
def build_feature_keyboard(features: list, selected_ids: set) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for feature in features:
        text = feature.name_i18n.get("ru", feature.slug)
        if feature.id in selected_ids:
            text = f"✅ {text}"
        builder.button(text=text, callback_data=f"feature:{feature.id}")
    builder.button(text="✔️ Done", callback_data="features_done")
    builder.adjust(2)
    return builder.as_markup()
```

**Changes to preview:**
```python
# In show_preview():
preview_text = (
    f"Ad Preview:\n\n"
    f"Title: {data.get('title', 'N/A')}\n"
    f"Description: {data.get('description', 'N/A')[:100]}...\n"
    f"Price: {data.get('price', 'N/A')} BAM\n"
    f"Category: {category.name if category else 'N/A'}\n"
    f"Purpose: {purpose_name}\n"                # NEW
    f"Features: {feature_names}\n"              # NEW
    f"City: {city.name if city else 'N/A'}\n"
)
```

**Changes to `update_ad_and_moderate()`:**
- Add parameters: `listing_purpose_id: int | None`, `feature_ids: list[int] | None`
- After `ad.save()`, set:
  ```python
  if listing_purpose_id:
      ad.listing_purpose_id = listing_purpose_id
  if feature_ids is not None:
      ad.features.set(feature_ids)
  ```

**Acceptance criteria:**
- Bot FSM flows: category → purpose → features → city → ... (purpose and features inserted)
- Single-purpose category skips purpose step
- Single-purpose or zero-feature category skips features step
- Purpose is saved on the Ad record
- Features are saved via M2M
- Preview shows selected purpose and features
- Edge case: 0 purposes → fallback with error message

---

### TASK_013: Implement "Copy Ad" bot command

**Priority:** medium

**Depends on:** TASK_005 (Ad model changes)

**Source:** Spec section 2.5 (CP01-CP06)

**Description:**
Implement `/copy <ad_id>` bot command in seller's ad management menu. Creates a new `Ad` in `DRAFT` status, copying category, description, address, coordinates, photos (as new `AdImage` rows referencing same files), features, and contacts. Seller can change purpose, price, title, description.

**Goals:**
- Add `/copy` command handler in bot
- Create `copy_ad()` service function (in `apps/ads/services/` or a new service)
- Copy preserves: category, description (all languages), address, coordinates, photos (new rows, same files), features, contacts
- New ad starts in DRAFT status
- Seller must set new: purpose, price, title, description
- Copy reuses existing file storage (no file duplication)

**Affected modules:**
- `apps/ads/services/copy_service.py` — new file, `copy_ad()` function
- `src/telegram_bot/handlers/ad_copy.py` — new file, `/copy` command handler
- `src/telegram_bot/main.py` — register new router

**Service function:**

```python
def copy_ad(source_ad_id: int, seller_user_id: int) -> Ad:
    """Create a new draft ad copied from an existing one.

    Args:
        source_ad_id: ID of the ad to copy.
        seller_user_id: ID of the seller creating the copy.

    Returns:
        The new Ad instance in DRAFT status.

    Raises:
        Ad.DoesNotExist: if source_ad_id not found.
        PermissionError: if seller does not own the source ad.
    """
    source = Ad.objects.select_related(
        "listing_purpose"
    ).prefetch_related(
        "features", "images"
    ).get(id=source_ad_id)

    if source.user_id != seller_user_id:
        raise PermissionError("Cannot copy another user's ad")

    new_ad = Ad(
        user_id=seller_user_id,
        category=source.category,
        city=source.city,
        # Copy all language variants
        title=source.title,
        title_en=source.title_en,
        title_bs=source.title_bs,
        description=source.description,
        description_en=source.description_en,
        description_bs=source.description_bs,
        original_language=source.original_language,
        # Coordinates
        latitude=source.latitude,
        longitude=source.longitude,
        # Start as draft
        status=AdStatus.DRAFT,
    )
    new_ad.save()

    # Copy features
    new_ad.features.set(source.features.all())

    # Copy images (new rows, same storage keys)
    for img in source.images.all():
        AdImage.objects.create(
            ad=new_ad,
            image=img.image,
            telegram_file_id=img.telegram_file_id,
            position=img.position,
            thumbnail_small=img.thumbnail_small,
            thumbnail_medium=img.thumbnail_medium,
            thumbnail_large=img.thumbnail_large,
        )

    return new_ad
```

**Bot command:**

```python
@router.message(Command("copy"))
async def cmd_copy(message: types.Message, state: FSMContext) -> None:
    """Copy an existing ad. Usage: /copy <ad_id>"""
    # Parse ad_id from command
    # Verify seller owns the ad
    # Call copy_ad()
    # Start ad creation flow with pre-filled data
    # Set FSM to purpose selection step
```

**Acceptance criteria:**
- `/copy <ad_id>` creates a new DRAFT ad with copied data
- Copied images reference same storage keys (no file duplication)
- Seller can modify purpose, price, title, description in the copy flow
- Error message if ad_id not found or seller doesn't own it

---

### TASK_014: Implement navigation UI updates for alternative category paths

**Priority:** medium

**Depends on:** TASK_002 (CategoryPath model exists)

**Source:** Spec sections 2.1 (C07, C08, C09)

**Description:**
Update the web site's category navigation to render alternative paths from `CategoryPath`. Categories that have alternative parent routes appear under both the canonical MPTT parent and the alternative parents in navigation menus. Breadcrumb context depends on the path the user followed.

**Goals:**
- Update category navigation templates/views to include `CategoryPath` entries
- Category appears under canonical parent AND alternative parents
- Breadcrumb shows the path the user followed (not just canonical)
- URL structure remains `/category/<slug>/` unchanged

**Affected modules:**
- `apps/categories/views.py` or existing listing views — update category tree queries
- Templates that render category navigation — add alternative path rendering
- Potentially `apps/categories/templatetags/` — new template tags for nav tree

**Changes may include:**
- Modify the category navigation context to include `CategoryPath` entries alongside canonical children
- Add a `get_nav_tree()` helper that merges canonical children with `CategoryPath` alternative_children
- Breadcrumb: store `path_ids` in session/URL parameter to track user's navigation path
- Use the user's path to determine breadcrumb display

**Note:** The actual template changes depend on the existing navigation structure, which is minimal (currently `urlpatterns = []`). The navigation will likely be built as part of the broader site UI effort.

**Acceptance criteria:**
- Categories with `CategoryPath` entries appear under alternative parents in navigation
- Canonical MPTT tree remains primary navigation
- Breadcrumb reflects the user's navigation path when coming via an alternative path
- URL structure unchanged

---

### TASK_015: End-to-end validation

**Priority:** medium

**Depends on:** TASK_005, TASK_007, TASK_009, TASK_012, TASK_013, TASK_014

**Description:**
Validate the complete implementation: catalog loading, lookup resolution, bot FSM operations, and admin functionality.

**Validation test groups:**

**A — Catalog builder:**
1. Run `builder.load_catalog()` on empty DB: all groups, items, categories, bindings, paths created
2. Run again (idempotent): no duplicates, no constraint violations
3. Rename via `new_slug`: slug updated, category_path references resolved, YAML auto-rewritten
4. Deferred categories skipped

**B — Lookup resolution:**
1. Category with explicit purposes returns those purposes
2. Category without explicit purposes inherits from parent
3. Override on subcategory replaces (not merges) parent's set
4. Inactive LookupItem excluded from results
5. `CategoryPath` alternative parents do NOT affect resolution
6. Cache hit returns without DB query
7. Cache invalidation on through-table change

**C — Bot FSM:**
1. Category with single purpose → auto-select, skip purpose step
2. Category with multiple purposes → show purpose selection
3. Purpose with `is_default=True` → highlighted in selection
4. Category with 0 features → skip features step
5. Category with features → show feature selection (multi-select)
6. `update_ad_and_moderate()` saves purpose and features correctly

**D — Copy Ad:**
1. `/copy` creates new DRAFT ad with same category, features, images
2. Copied images share storage keys
3. Seller can modify purpose in the copy

**E — Admin:**
1. LookupGroup admin: CRUD, system group delete blocked
2. LookupItem admin: group filter, search
3. Category admin: CategoryPath inline, purpose inline, feature inline
4. Ad admin: listing_purpose in list display and filter

**F — Migration:**
1. Fresh `migrate` produces populated catalog
2. Data migration assigns `sell` to existing ads

**Test commands:**
```bash
uv run python manage.py migrate
uv run python manage.py seed
uv run pytest apps/categories/tests/ -v
uv run pytest apps/lookups/tests/ -v
uv run pytest src/telegram_bot/tests/ -v
```

**Acceptance criteria:**
- All validation groups pass
- No regressions in existing functionality

---

### TASK_016: Remove old artifacts (cleanup)

**Priority:** low

**Depends on:** TASK_007 (replacement active)

**Source:** Spec section CF15, T14

**Description:**
Remove old hardcoded fixture and migration files that have been replaced by the catalog builder.

**Goals:**
- Delete `0002_seed_categories.py` migration (or squash into replacement)
- Delete `categories.json` fixture file
- Delete `seed.default.json` if unused (verify first)
- Verify no remaining imports or references to deleted files

**Affected modules:**
- `apps/categories/migrations/0002_seed_categories.py` — DELETE
- `apps/seed/fixtures/categories.json` — DELETE (verify path)
- `apps/seed/fixtures/seed.default.json` — DELETE (if unused and confirmed safe)

**Changes:**
1. Git-track deletion of migration file
2. Git-track deletion of fixture file(s)
3. Run `python manage.py migrate --fake categories 0001_initial` (or squash migration chain) to account for removal
4. Run `grep -r "categories.json" src/` to verify no remaining references

**Acceptance criteria:**
- Old migration file removed (or properly squashed)
- Old fixture file removed
- No broken imports or references

---

## Risk Assessment Summary

| Task | Risk | Reason | Mitigation |
|------|------|--------|------------|
| TASK_006 | **HIGH** | Builder involves file I/O (atomic YAML rewrite), MPTT tree insertion in migrations, `new_slug` rename logic | **Research gate required** (research_001) — investigate migration dependency ordering, atomic write patterns |
| TASK_005 | **MEDIUM** | Data migration touches all existing ads; non-nullable FK addition requires careful ordering | Create default LookupItem inline in data migration (get_or_create) to avoid migration ordering issues |
| TASK_007 | **MEDIUM** | Removal of `0002_seed_categories.py` can break migration chain; SeedService replacement may affect seed command | Pre-production: delete and recreate migrations from clean state |
| TASK_012 | **MEDIUM** | Modifies existing bot FSM flow — risk of breaking existing posting flow | Add states between existing ones (don't reorder); verify all state transitions |
| TASK_003 | **LOW** | New field on existing model, backfill migration | Well-defined, no schema conflicts |
| TASK_004 | **LOW** | New through tables only | No existing data migration needed |
| TASK_013 | **LOW** | New bot command, isolated from existing flows | No existing flow modifications |
| TASK_016 | **LOW** | Simple file deletion | Verify no references before deletion |

---

## Architectural Boundaries (Preserved)

1. **Apps separation:** `lookups` app owns LookupGroup/LookupItem. `categories` app owns Category, CategoryPath, through models. `ads` app owns Ad, AdFeature. No circular app dependencies.
2. **Service layer:** `CategoryLookupResolver` lives in `categories/services/`. `LookupCacheService` lives in `lookups/services/`. `FileHashService` lives in `media/services/`.
3. **Cache pattern:** Follows existing `apps/core/utils/cache.py` pattern (key + TTL + get/set/invalidate).
4. **Signal pattern:** Follows existing `apps/moderation/signals.py` pattern (`@receiver` in dedicated module, connected in AppConfig.ready()).
5. **Admin patterns:** Follows existing `CategoryAdmin(MPTTModelAdmin)` and `AdAdmin(ModelAdmin)` patterns.
6. **Bot FSM pattern:** Follows existing `AdCreateForm(StatesGroup)` pattern with `@router.message()` handlers.