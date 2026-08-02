# Specification: Category + Universal Lookup Architecture

**File:** `04_category-lookup-architecture_spec.md`
**Status:** Final (ready for implementation planning)
**Date:** 2026-08-02
**Source Decision:** `.ai/problems/DECISION_03.md`, `.ai/problems/DECISION_04.md`
**Research:** `docs/07-design-researches/Design_02/04-multi-parent-categories-research.md`, `ses_03f05c7b6ffeTBlTDzZTWwO724` (lookup inheritance)
**Category Tree:** `.ai/problems/categories_tree_bazuna.md`
**Builder Pattern:** Config-driven `categories.yaml` + `builder.py` (per PO decision 2026-08-02)

---

## 1. Problem Statement

The Mko Bazuna classifieds board needs a scalable architecture for ad categories and reference data that meets two goals:

1. **Multi-parent category navigation** — a category like "Bicycles" must appear under multiple parent categories simultaneously (Transport, Sports & Hobbies) so buyers can find it through different navigation paths. The current `django-mptt` strict tree (single `parent` FK) does not support this.

2. **Universal reference data system** — variable ad attributes (publication purpose, item condition, features) must be managed through a unified lookup system where:
   - New values are added/changed via admin panel, without code changes
   - Categories define which lookup values are applicable
   - All lookups are cacheable and indexed for search/filtering
   - No EAV pattern is used (standard PostgreSQL FK/M:N only)

3. **Top-level category structure** — the category hierarchy must be organized under 7 fixed top-level sections:
   - **Недвижимость** (Real Estate)
   - **Транспорт** (Transport)
   - **Товары** (Goods)
   - **Животные** (Animals)
   - **Услуги, работа, вакансии** (Services)
   - **Бизнес** (Business)
   - **Благотворительность** (Charity / Free stuff)
   
   "Благотворительность" is a special top-level category that collects all ads with price = 0 (or price = None). It is populated automatically based on ad price, not manually by sellers. An ad's canonical category is its "main" category (e.g. "Телефоны" under "Товары"), and the system auto-creates a secondary path to "Благотворительность" when price is zero.

Additionally, the system must support:
- **Ad copy** — create a new ad based on an existing one, changing only purpose/price
- **Photo deduplication** — SHA-256 hashing to avoid storing duplicate images

---

## 2. Confirmed Requirements

### 2.1 Multi-Parent Category Navigation

| ID | Requirement | Priority |
|----|-------------|----------|
| C01 | Keep existing `Category` MPTT model as the **canonical/primary tree** unchanged | Must |
| C02 | Add `CategoryPath` model for alternative parent routes (additional navigation paths) | Must |
| C03 | Each category has exactly one canonical parent (existing MPTT `parent` FK) | Must |
| C04 | Each category can have zero or more alternative paths via `CategoryPath` | Must |
| C05 | Category slug remains globally unique (one entity, many paths to find it) | Must |
| C06 | Ad-to-category remains a single `ForeignKey` (one canonical category per ad) | Must |
| C07 | Navigation UI renders both the canonical tree AND alternative paths | Must |
| C08 | Breadcrumb context depends on the *path* the user followed, not the canonical parent | Should |
| C09 | URL structure: keep `/category/<slug>/` — canonical parent is MPTT path, alternative paths change breadcrumb context only | Must |
| C10 | Search indexing unchanged — search indexes the ad's canonical category | Must |
| C11 | "Благотворительность" (Charity) is a top-level Category, auto-populated via system rule | Must |
| C12 | When `Ad.price = 0` or `NULL` → system creates `CategoryPath` (is_automatic=True) linking ad's category to "Благотворительность" | Must |
| C13 | When `Ad.price` changes from 0 to positive → automatic `CategoryPath` is removed | Must |
| C14 | "Благотворительность" contains NO direct children in MPTT — all content is via `CategoryPath` auto-links | Must |
| C15 | Ad canonical category never changes — auto-path to Благотворительность is supplemental only | Must |

#### CategoryPath Model

```
CategoryPath:
  id             — AutoField (PK)
  category       — FK -> Category (the leaf/child being navigated to)
  parent         — FK -> Category (the alternative parent in the navigation path)
  sort_order     — PositiveIntegerField (ordering within alternative parent's children)
  is_automatic   — BooleanField(default=False, help_text="True if created by system rule (e.g. price=0 -> Благотворительность)")
```

- Unique constraint: `(category, parent)` — no duplicate alternative paths
- A category cannot have itself as an alternative parent (validation)
- Alternative paths must not create cycles (validation)
- CategoryPath entries are NOT MPTT-managed — they are simple navigation shortcuts

#### Special Case: Благотворительность (Charity)

- "Благотворительность" is a real top-level `Category` in the MPTT tree
- It is the only top-level category that can contain ads from **any** other top-level section
- Rule: **When an ad's price = 0 or price = NULL, the system automatically creates a `CategoryPath`** linking the ad's canonical category → Благотворительность
- When the ad's price changes from 0 to a positive value → the automatic `CategoryPath` is removed
- This path is flagged `is_automatic = True`, distinguishing it from manually created paths
- Sellers cannot manually post an ad directly into "Благотворительность" — it is a system-managed section
- In the navigation UI, "Благотворительность" displays all free ads across all categories
- **Design decision**: Price zero = free. The system treats `price = 0` and `price = NULL` (unspecified) as free items. This can be refined later with a separate "is_free" boolean if needed.

### 2.2 Universal Lookup System

| ID | Requirement | Priority |
|----|-------------|----------|
| L01 | Create `LookupGroup` model — a named group of reference data values | Must |
| L02 | Create `LookupItem` model — an individual value within a LookupGroup | Must |
| L03 | `LookupGroup` has a `code` (unique, immutable) and a `name_i18n` (JSONB) | Must |
| L04 | `LookupItem` has: `slug` (globally unique identifier), `name_i18n` (JSONB), `sort_order` (per-group), `is_active` (bool), `icon` (optional text/emoji), `color` (optional hex) | Must |
| L05 | `LookupGroup` has `is_system` boolean — system groups cannot be deleted via admin | Must |
| L06 | Two built-in system lookup groups ship with the project: `listing_purpose` and `listing_feature` | Must |
| L07 | Category ↔ LookupItem M:N relationships: `CategoryListingPurpose` and `CategoryListingFeature` through models | Must |
| L08 | All lookup values are managed exclusively through Django admin | Must |
| L09 | No EAV — standard PostgreSQL FK and M:N through tables only | Must |
| L10 | **Inheritance**: purposes/features defined on a parent category are inherited by all descendants via MPTT ancestor walk-up | Must |
| L11 | **Override**: a category can explicitly redefine its purpose/feature set — that override replaces (not merges) the inherited set for itself and all descendants | Must |
| L12 | **Canonical-only**: inheritance walks the canonical MPTT `parent` chain only; `CategoryPath` alternative parents do NOT participate | Must |
| L13 | **StrEnum**: group codes (`listing_purpose`, `listing_feature`) are defined as `StrEnum`, not plain strings | Must |

#### ListingPurpose — What the User Wants to Do With the Object

`listing_purpose` describes the **intent** behind the listing. Every ad must have exactly one purpose. Common purposes shipped with the project:

| Slug | Description |
|------|-------------|
| `sell` | Selling an item |
| `buy` | Buying / looking to purchase |
| `rent` | Renting out (lessor) |
| `rent-request` | Looking to rent (lessee) |
| `service` | Offering a service |
| `service-request` | Looking for a service |
| `job-offer` | Offering a job / vacancy |
| `job-seek` | Looking for a job |
| `giveaway` | Giving away for free (charity / free stuff) |
| `exchange` | Exchanging items (barter) |

Not all purposes apply to all categories. For example:
- **Real Estate**: `sell`, `rent`, `rent-request`, `buy`, `exchange`
- **Auto**: `sell`, `buy`, `exchange`
- **Jobs**: `job-offer`, `job-seek`
- **Services**: `service`, `service-request`
- **Благотворительность**: `giveaway` only (auto-assigned when price = 0)

Category ↔ ListingPurpose bindings are managed via the `CategoryListingPurpose` through table. The bot FSM filters available purposes to only those linked to the selected category.

#### ListingFeature — Additional Attributes of the Listing

`listing_feature` describes **characteristics or conditions** of the listing. An ad can have 0..N features. Common features shipped with the project:

| Slug | Description |
|------|-------------|
|------|-----------|-------------|
| `new` | Brand new, sealed |
| `used` | Used item |
| `urgent` | Urgent sale |
| `vip` | VIP / promoted listing |
| `with-delivery` | Delivery available |
| `with-installment` | Installment payment available |
| `with-video` | Listing has video |
| `with-document` | Documents available |
| `with-guarantee` | Warranty included |
| `negotiable` | Price negotiable |
| `business` | From a business seller |
| `premium` | Premium ad |

Features are category-specific. Each category defines which features are available via the `CategoryListingFeature` through table. For example:
- **Electronics**: `new`, `used`, `with-guarantee`, `with-delivery`
- **Real Estate**: `urgent`, `negotiable`, `with-document`, `with-installment`
- **Animals**: `with-document` (pedigree), `with-delivery`

#### LookupGroup Model

```
LookupGroup:
  id             — AutoField (PK)
  code           — CharField(unique, max_length=100) — machine-readable, immutable after creation
  name_i18n      — JSONField(nullable) — {'ru': str, 'bs': str, 'en': str}
  is_system      — BooleanField(default=False) — protected from admin deletion
  sort_order     — PositiveIntegerField(default=0)
```

#### LookupItem Model

```
LookupItem:
  id             — AutoField (PK)
  group          — FK -> LookupGroup (CASCADE on delete — group deletion cascades to items)
  slug           — SlugField(unique globally) — serves as both the identifier and URL component
  name_i18n      — JSONField(nullable) — {'ru': str, 'bs': str, 'en': str}
  sort_order     — PositiveIntegerField(default=0)
  is_active      — BooleanField(default=True)
  icon           — CharField(max_length=50, blank=True) — emoji or SVG icon name
  color          — CharField(max_length=7, blank=True) — hex color (#RRGGBB)
```

#### M:N Through Tables

**CategoryListingPurpose:**
```
CategoryListingPurpose:
  id              — AutoField (PK)
  category        — FK -> Category (CASCADE)
  listing_purpose — FK -> LookupItem (CASCADE, group restricted to listing_purpose at app level)
  is_default      — BooleanField(default=False, help_text="Default purpose for this category; used for auto-select when seller doesn't choose explicitly")
```

- Unique constraint: `(category, listing_purpose)` — no duplicate purpose bindings
- Only one purpose per category can have `is_default = True` (enforced at application level)
- If a category has exactly 1 linked purpose → it is treated as default by application logic, regardless of the `is_default` flag
- If a category has 2+ linked purposes and one has `is_default = True` → pre-select that one in UI

**Recommended indexes** (no column schema changes — only indexes for resolution performance):
- Composite index on `(category_id, listing_purpose_id)` on CategoryListingPurpose
- Index on `listing_purpose_id` on CategoryListingPurpose (for reverse lookup on deactivation)
- Composite index on `(category_id, feature_id)` on CategoryListingFeature
- Index on `feature_id` on CategoryListingFeature (for reverse lookup on deactivation)

**CategoryListingFeature:**
```
CategoryListingFeature:
  id             — AutoField (PK)
  category       — FK -> Category (CASCADE)
  feature        — FK -> LookupItem (CASCADE, group restricted to listing_feature at app level)
```

- Unique constraint: `(category, feature)` pairs
- Pure M:N through table (no additional metadata columns for Phase 1)

#### Lookup Inheritance — CategoryLookupResolver Service

Purposes and features defined on a parent category **inherit to all descendants** via the canonical MPTT `parent` chain. An explicit definition on a subcategory **replaces** (not merges) the inherited set.

**Resolution algorithm (nearest-explicit-ancestor-wins):**
1. Get all ancestor IDs including self: `category.get_ancestors(include_self=True)` — 1 indexed MPTT query
2. Fetch all active through-row bindings for those ancestor IDs (joined to `LookupItem` with `is_active=True`) — 1 indexed query
3. Group by `category_id`; return bindings for the first (nearest to leaf) group that has rows

**Example:**
```
Товары [sell, buy, exchange]            ← explicit definition
├── Электроника                          ← no definition → inherits [sell, buy, exchange]
│   └── Телефоны                         ← no definition → inherits [sell, buy, exchange]
└── Одежда [sell, buy]                   ← override → replaces with [sell, buy]
    └── Женская одежда                   ← no definition → inherits from Одежда [sell, buy]
```

**Key rules:**
- Inheritance walks only the canonical MPTT `parent` chain. `CategoryPath` alternative parents do NOT participate (they are navigation-only).
- Override is replacement, not merge — setting `[sell, buy]` on Одежда removes `exchange` entirely.
- Deactivated `LookupItem` (`is_active=False`) is always filtered out in resolution — the service returns only active items.
- If no ancestor has any explicit bindings → return empty list (the caller handles fallback).
- **`is_default` applies only to `listing_purpose`** (singleton choice — pre-select in UI). It does NOT apply to `listing_feature` (multi-select — no concept of "default feature").

**Caching:**
- Cache key: `lookup:resolved_purposes:{category_id}` and `lookup:resolved_features:{category_id}`
- TTL: 300 seconds (5 minutes) — matches existing moderation criteria cache convention
- Invalidation triggers:
  - `CategoryListingPurpose`/`CategoryListingFeature` save/delete → invalidate affected category + all descendants via `get_descendants(include_self=True)`
  - `LookupItem.is_active` toggle → reverse-lookup all through-table rows referencing that item, invalidate those categories + descendants
  - `Category.move_to()` (MPTT restructure) → invalidate old and new subtrees
- Cross-process consistency: signal-based invalidation is best-effort (per gunicorn worker); TTL backs up cross-process eventual consistency. This follows the same pattern as the existing moderation criteria cache.

**Service interface (placed in `apps/categories/services/lookup_resolution.py`):**
```python
class CategoryLookupResolver:
    def get_resolved_purposes(self, category) -> list[LookupItem]: ...
    def get_resolved_features(self, category) -> list[LookupItem]: ...
    def get_resolved_purpose_codes(self, category) -> list[str]: ...
    def get_resolved_feature_codes(self, category) -> list[str]: ...
    def invalidate_category(self, category_id: int) -> None: ...
    def invalidate_lookup_item(self, lookup_item_id: int) -> None: ...
```

#### Default Purpose Selection Logic (Application Rule)

The bot FSM and any future posting UI follows this rule when selecting listing_purpose:

1. Query `CategoryListingPurpose` for the ad's category
2. If count == 1 → auto-select that purpose, **skip the purpose selection step** entirely in the bot FSM
3. If count > 1 → check `is_default`:
   - If one purpose has `is_default = True` → pre-select it, show choice with default highlighted
   - If no purpose has `is_default = True` → show choice without pre-selection, seller must pick
4. If count == 0 → this should not happen (category setup ensures at least one purpose), but fall back to a system-configured default or block posting

This keeps the posting flow efficient: categories like "Телефоны" with only `sell` as purpose skip the step entirely. Categories like "Квартиры" with `sell`, `rent`, `rent-request` show the choice with one pre-selected if admin configured a default.

### 2.3 Ad Model Changes

| ID | Requirement | Priority |
|----|-------------|----------|
| A01 | Add `listing_purpose` FK field on `Ad` — required, non-nullable, to `LookupItem` (group = listing_purpose) | Must |
| A02 | Add M:N relationship `Ad → LookupItem` (group = listing_feature) — optional, 0..N | Must |
| A03 | Existing ads must get a default `listing_purpose` during migration (data migration) | Must |
| A04 | `Ad.category` FK stays unchanged — one canonical category per ad | Must |

New fields on `Ad`:
```
listing_purpose  — ForeignKey("lookups.LookupItem", on_delete=PROTECT, limit_choices_to={"group__code": "listing_purpose"}, help_text="What the user wants to do with the object")
features         — ManyToManyField("lookups.LookupItem", through="ads.AdFeature", limit_choices_to={"group__code": "listing_feature"}, blank=True)
```

New through model for Ad ↔ Feature:
```
AdFeature:
  id             — AutoField (PK)
  ad             — FK -> Ad (CASCADE)
  feature        — FK -> LookupItem (CASCADE, group = listing_feature)
  sort_order     — PositiveIntegerField(default=0, help_text="Display order of this feature on the ad page")
  
  Meta:
    unique_together = (("ad", "feature"),)
    ordering = ["sort_order"]
```

### 2.4 Admin Interface

| ID | Requirement | Priority |
|----|-------------|----------|
| AD01 | `LookupGroupAdmin` — list/edit with `is_system` protected from delete | Must |
| AD02 | `LookupItemAdmin` — list with group filter, inline in LookupGroup admin | Must |
| AD03 | `CategoryAdmin` — keep MPTT tree, add TabularInline for `CategoryPath`, TabularInline for `CategoryListingPurpose`, TabularInline for `CategoryListingFeature` | Must |
| AD04 | `AdAdmin` — add listing_purpose and features to list display and filters | Must |
| AD05 | `CategoryPath` admin — TabularInline under Category, drag-and-drop sort_order | Should |
| AD06 | System group delete blocked at model level + admin permission check | Must |

### 2.5 "Copy Ad" Feature

| ID | Requirement | Priority |
|----|-------------|----------|
| CP01 | Implement in Telegram bot as `/copy <ad_id>` command in seller's ad management menu | Must |
| CP02 | Copy creates a new `Ad` in `DRAFT` status referencing the same seller | Must |
| CP03 | Copy preserves: category, description, address, coordinates, photos (as new `AdImage` rows referencing same files), features, contacts | Must |
| CP04 | Seller changes: ListingPurpose, price, title/description (if needed) | Must |
| CP05 | Copy is implemented via a service function, not raw ORM | Should |
| CP06 | Copied images reuse existing file storage (deduplication already ensures single physical copy) | Must |

### 2.6 Photo Deduplication

| ID | Requirement | Priority |
|----|-------------|----------|
| PD01 | Add `sha256` field to `AdImage` model (CharField, length=64) | Must |
| PD02 | Create `FileHashService.calculate_sha256(file_path) -> str` | Must |
| PD03 | `AdImage.save()` automatically computes SHA-256 hash on creation | Must |
| PD04 | If file with same hash exists AND the same user already has that hash → skip duplicate (reuse existing `AdImage` + new FK relation) | Should |
| PD05 | Backfill migration for existing `AdImage` rows (compute hash from stored files) | Should |
| PD06 | Index on `sha256` column for dedup lookup | Must |

### 2.7 Caching

| ID | Requirement | Priority |
|----|-------------|----------|
| CA01 | All `LookupGroup` and `LookupItem` records cached with low TTL (e.g., 1 hour) or until admin save signal | Must |
| CA02 | Django's `caches` framework — use `CacheService` or django's `cache.set()` / `cache.get()` | Must |
| CA03 | Invalidation on `post_save` / `post_delete` signals for LookupGroup, LookupItem, CategoryListingPurpose, CategoryListingFeature | Must |
| CA04 | Category MPTT tree cached separately (already cached implicitly via database query) | Should |
| CA05 | `CategoryLookupResolver` resolved caches invalidated on through-table changes AND LookupItem.is_active toggles AND Category MPTT moves | Must |
| CA06 | Resolved cache TTL: 300 seconds (5 minutes) — same as existing moderation criteria cache pattern | Must |

#### Rename Example (new_slug mechanism)

When the user wants to rename "Бизнес" → "Бизнес 360" and change slug from `business` to `business-360`:

**In YAML:**
```yaml
- slug: business          # ← by this the builder finds the existing record
  new_slug: business-360  # ← rename target; present ONLY during the transitional run
  name: "Бизнес 360"      # ← also renamed
```

**Builder behavior on the transitional run:**
1. Reads `slug: business` → finds `Category.objects.get(slug="business")`
2. `update_or_create(slug="business", defaults={"slug": "business-360", "name": "Бизнес 360"})`
3. Records `"business" → "business-360"` in the internal `slug_rename_map`
4. After all operations succeed → **auto-rewrites the YAML file**: removes `new_slug`, sets `slug: business-360`

**Final YAML state (after first run):**
```yaml
- slug: business-360   # ← auto-rewritten by builder
  name: "Бизнес 360"
```

**Data integrity:** All existing ads, FK references, M:N bindings, and CategoryPath entries remain intact because the DB row `id` never changed — only the `slug` column was updated.

#### category_paths auto-resolution

When a category is renamed, the builder maintains a `slug_rename_map: {old_slug → new_slug}` during the run. This map is used to resolve `category_paths` references automatically:

```python
# category_paths can use EITHER old or new slug — builder handles both:
def _resolve_slug(slug: str) -> str:
    return slug_rename_map.get(slug, slug)  # "business" → "business-360"

# builder processes paths AFTER categories, so the renamed category already exists
CategoryPath.objects.create(
    category=Category.objects.get(slug=_resolve_slug(yaml_ref)),
    parent=Category.objects.get(slug=_resolve_slug(yaml_parent)),
)
```

The user does NOT need to update `category_paths` manually — the builder resolves references automatically during the transitional run.

#### Auto-rewrite YAML

After a successful `load_catalog()` run that consumed any `new_slug` values, the builder **automatically rewrites** the YAML config file:

1. Removes the `new_slug` field from each renamed entry
2. Sets `slug` to the value that was in `new_slug`
3. Writes to a temporary file, then atomically replaces the original (`os.replace`)
4. If the file is not writable (e.g., Docker read-only fs) — logs a warning, does not fail
5. After rewrite, the YAML always reflects the actual DB state — no stale `new_slug` artifacts

### 2.8 Bot FSM Integration

| ID | Requirement | Priority |
|----|-------------|----------|
| B01 | After category selection in bot FSM: call `CategoryLookupResolver.get_resolved_purposes()` for the selected category to get inherited + active purposes | Must |
| B02 | If resolved purposes count == 1 → auto-select that purpose, **skip the purpose selection step** entirely | Must |
| B03 | If resolved purposes count > 1 → show inline keyboard with `is_default` highlighted, seller picks one | Must |
| B04 | If count == 0 (edge case) → fall back to system default (`sell`) or block posting with error | Must |
| B05 | If category has resolved features: show multi-select feature list (optional, 0..N), seller can skip | Must |
| B06 | If category has no resolved features → skip features step entirely | Must |
| B07 | Flow: category → purpose → features → title/description → price → address → photos → confirmation | Must |

### 2.9 Catalog Configuration & Builder

All category structure, lookup definitions, and their bindings must be managed through a **single YAML configuration file**, loaded by a builder module at migration time and seed time. No hardcoded category data in Python migration files.

> **Source data**: The canonical category tree, lookup slugs, and override bindings are defined in `.ai/problems/categories_tree_bazuna.md`. The YAML config file (`categories.yaml`) is generated from that document. Both files must be kept in sync — changes to the tree first go into `categories_tree_bazuna.md`, then propagate to `categories.yaml`.

| ID | Requirement | Priority |
|----|-------------|----------|
| CF01 | One canonical YAML config file `apps/categories/catalog/categories.yaml` as the single source of truth | Must |
| CF02 | YAML contains: `lookups` (listing_purpose + listing_feature items), `categories` (full tree with nesting), `category_paths` (alternative parent routes) | Must |
| CF03 | Builder module `apps/categories/catalog/builder.py` reads YAML and creates/updates all records via Django ORM | Must |
| CF04 | Builder uses MPTT `insert_at()` for tree insertion — no hardcoded `lft`/`rght` values | Must |
| CF05 | Builder creates records level by level (L1 → L2 → L3 → L4) so parent exists before child | Must |
| CF06 | **Matching strategy: `update_or_create` by `slug`** — if a category already exists, update its fields. For renames, use `new_slug` field (see below). | Must |
| CF07 | **Rename via `new_slug`** — YAML entry can have `new_slug: <new-value>` alongside `slug: <old-value>`. Builder matches by `slug`, writes `new_slug` to DB. | Must |
| CF08 | **slug_rename_map** — builder tracks all renames in an internal map `{old_slug → new_slug}`. Used to auto-resolve references in `category_paths`. | Must |
| CF09 | **Auto-rewrite YAML** — after successful `load_catalog()`, if any `new_slug` was consumed, builder rewrites YAML: removes `new_slug`, sets `slug` to the new value. Atomic write via temp file + `os.replace`. | Must |
| CF10 | **category_paths auto-resolution** — references in `category_paths` are resolved through `slug_rename_map`. User can use old or new slug — builder finds the category. | Must |
| CF11 | Builder creates in order: LookupGroup → LookupItem → Category tree → CategoryListingPurpose/CategoryListingFeature → CategoryPath | Must |
| CF12 | Deferred categories (marked `deferred: true` in YAML) are skipped by builder; kept in config for documentation | Must |
| CF13 | Data migration `categories/XXXX_load_catalog.py` calls `builder.load_catalog(CONFIG_PATH)` via `RunPython` | Must |
| CF14 | `SeedService._load_category_fixtures()` is replaced with a call to the same `builder.load_catalog()` | Must |
| CF15 | Old artifacts removed: `0002_seed_categories.py` migration deleted, `categories.json` fixture deleted | Must |

#### YAML Structure

> The exact listing of categories, lookup slugs, and override bindings is defined in `.ai/problems/categories_tree_bazuna.md`. The structure below is a format example only.

```
# apps/categories/catalog/categories.yaml

lookups:
  listing_purpose:
    - slug: sell
      name_i18n: {ru: "Продажа", bs: "Prodaja", en: "Sell"}
      sort_order: 1
    - slug: give-away
      name_i18n: {ru: "Отдаю бесплатно", ...}
      sort_order: 2
    # ...

  listing_feature:
    - slug: new
      name_i18n: {ru: "Новый", ...}
      sort_order: 1
    # ...

categories:
  - slug: real-estate             # ← by this the builder matches existing records
    name: "Недвижимость"
    name_i18n: {ru: "Недвижимость", bs: "Nekretnine", en: "Real Estate"}
    listing_purpose_override: [sell, rent, rent-short]
    listing_feature_override: [with-photo, with-video, negotiable, ...]
    children:
      - slug: apartments
        name: "Квартиры"
        name_i18n: {ru: "Квартиры", ...}
      - slug: garages
        name: "Гаражи и машиноместа"
        listing_purpose_override: [sell, rent]   # overrides parent's purposes

  # Rename example — new_slug present only during transitional run:
  - slug: business                 # ← old slug (used for matching)
    new_slug: business-360         # ← target slug (written to DB)
    name: "Бизнес 360"
        name_i18n: {ru: "Гаражи и машиноместа", ...}
        listing_purpose_override: [sell, rent]   # overrides parent's purposes
      # ...

category_paths:
  - category: auto-parts
    parent: goods
  - category: bicycles
    parent: transport
  # ...

| ID | Requirement | Priority |
|----|-------------|----------|
| B01 | After category selection in bot FSM: call `CategoryLookupResolver.get_resolved_purposes()` for the selected category to get inherited + active purposes | Must |
| B02 | If resolved purposes count == 1 → auto-select that purpose, **skip the purpose selection step** entirely | Must |
| B03 | If resolved purposes count > 1 → show inline keyboard with `is_default` highlighted, seller picks one | Must |
| B04 | If count == 0 (edge case) → fall back to system default (`sell`) or block posting with error | Must |
| B05 | If category has resolved features: show multi-select feature list (optional, 0..N), seller can skip | Must |
| B06 | If category has no resolved features → skip features step entirely | Must |
| B07 | Flow: category → purpose → features → title/description → price → address → photos → confirmation | Must |

---

## 3. Conceptual Development Tasks

> **Note:** Tasks are listed in dependency order. Tasks within the same dependency group (same number) can be parallelized.

| # | Task | Purpose | Expected Outcome | Dependencies |
|---|------|---------|-----------------|--------------|
| T0 | **Create catalog YAML + builder module with rename support** — `categories/catalog/categories.yaml` + `categories/catalog/builder.py` | Single source of truth for categories, lookups, and bindings; replace hardcoded migration and fixture | YAML config with full tree + lookups + paths; builder module with `load_catalog()` supporting `new_slug` rename, `slug_rename_map`, auto-rewrite, category_paths auto-resolution; data migration calling it; SeedService integration | None (defines the data that T1 models store) |
| T1 | **Create `lookups` Django app** with `LookupGroup`, `LookupItem` models + migration | Core reference data infrastructure | `apps/lookups/` app with models, migration, admin, `__init__.py`, `apps.py` | None |
| T2 | **Add `CategoryPath` model** to `categories` app + migration | Multi-parent navigation support | `CategoryPath` model in `apps/categories/models.py`, migration | T1 (uses Category which already exists) |
| T3 | **Create through models** `CategoryListingPurpose` (with `is_default`), `CategoryListingFeature` + migrations | Bind lookups to categories | Through tables with FKs, unique constraints, is_default flag | T1, T2 |
| T3a | **Create `CategoryLookupResolver` service** in `apps/categories/services/lookup_resolution.py` | Inherited purpose/feature resolution via MPTT walk-up | `CategoryLookupResolver` class with `get_resolved_purposes()`, `get_resolved_features()`, `invalidate_*()` methods | T3 |
| T4 | **Add `listing_purpose` FK and `features` M:N** to `Ad` model + data migration | Ad can carry purpose and features | New fields on `Ad`, `AdFeature` through model, data migration for existing ads | T3 |
| T5 | **Implement Lookup admin UI** — `LookupGroupAdmin`, `LookupItemAdmin`, through-table inlines | Admin can manage reference data | Complete admin for all lookup models with protection for system groups | T1, T3 |
| T6 | **Implement Category admin extensions** — add `CategoryPath` inline + lookup inlines to `CategoryAdmin` | Admin can manage multi-parent paths and category-lookup bindings | Extended `CategoryAdmin` with TabularInlines | T2, T3, T5 |
| T7 | **Create `FileHashService`** + add `sha256` field to `AdImage` + override `save()` | Photo deduplication | `FileHashService`, migration for sha256 field, backfill script | None |
| T8 | **Create Lookup caching service** + signal-based invalidation | Performance: cached lookups | Cache service, signal handlers, invalidation on admin save | T1 |
| T9 | **Implement Bot FSM integration** — add purpose/feature steps to ad creation dialog | Seller can set purpose and features during posting | Extended bot FSM states and handlers | T4 |
| T10 | **Implement "Copy Ad" bot command** — `/copy` in seller menu | Reuse existing ad as template | Bot command handler, service function for copying | T4 |
| T11 | **Implement Navigation UI updates** — render alternative category paths in web navigation | Multi-parent paths visible to buyers | Updated templates/views for category navigation | T2 |
| T12 | **Replace SeedService category loading** — call `builder.load_catalog()` instead of `_load_category_fixtures()` | Unified data loading for migrate and seed | `SeedService` calls same builder; `categories.json` fixture deleted | T0 |
| T13 | **Ad admin updates** — add listing_purpose/features to `AdAdmin` list/filter/search | Moderators can see purpose and features | Updated `AdAdmin` | T4 |
| T14 | **Remove old artifacts** — delete `0002_seed_categories.py`, `categories.json` fixture, `seed.default.json` if unused | Tech debt cleanup | Old hardcoded files removed | T12 |

---

## 4. Product Owner Decisions

| # | Question | Decision |
|---|----------|----------|
| Q1 | LookupItem identity pattern | **Slug only** — `slug` is both the globally-unique identifier and the URL component. No separate `code` field. `code` kept only on `LookupGroup` (used as StrEnum in Python). |
| Q2 | Translation storage format | **JSONB `name_i18n`** — same pattern as `Category.name_i18n` and `City.name_i18n` |
| Q3 | ListingPurpose multiplicity on Ad | **Required** — every ad must have exactly one listing purpose (non-nullable FK) |
| Q4 | ListingFeature multiplicity on Ad | **Optional 0..N** — seller can add any number of features supported by the category |
| Q5 | Deactivation behavior | **Preserve data** — existing ads keep references; deactivated items hidden from UI and filter options |
| Q6 | "Copy Ad" initial scope | **Telegram bot only** — `/copy` command in seller's ad management menu |
| Q7 | Photo deduplication architecture | **Both A + B** — dedicated `FileHashService.calculate_sha256(file)` method, called automatically by `AdImage.save()` |
| Q8 | System lookup group protection | **Hard protection** — `is_system = True` flag on `LookupGroup`, admin delete blocked, lifecycle controlled by code |
| Q9 | Bot FSM posting flow | **Category → purpose → features → title/description → price → address → photos** |
| Q10 | LookupItem.sort_order scope | **Per-group ordering** — independent sort_order sequences within each `LookupGroup` |
| Q11 | Catalog deferred categories | **Include with `deferred: true`** — builder skips them, config keeps them for documentation and future activation |
| Q12 | Catalog builder idempotency | **`update_or_create` by `slug`** — rename via `new_slug` (transient field, auto-removed by builder after first run). No schema changes, no `key` field. |
| Q13 | Catalog builder architecture | **Config-driven builder** — single YAML `categories.yaml` + `builder.py` module, used by both migration (`RunPython`) and seed (`SeedService`) |
| Q14 | Category rename safety | **`new_slug` + `slug_rename_map` + auto-rewrite** — builder renames category in DB, auto-resolves `category_paths` references via internal map, then auto-updates YAML to remove `new_slug`. All FK/M2M data preserved. |

---

## 5. Research Summary

### 5.1 Multi-Parent Category Research

**Source:** `docs/07-design-researches/Design_02/04-multi-parent-categories-research.md`

**Key finding:** Avito, OLX, Jiji, and Facebook Marketplace all use **strict single-parent category trees**. None implement true polyhierarchy. Cross-discovery is solved through search/FTS and keyword matching, not multi-parent browsing.

**Recommended approach: B — Keep MPTT + CategoryPath model**

| Criteria | Approach B Score |
|----------|-----------------|
| Implementation complexity | Medium |
| Admin UI | Good (MPTT tree + TabularInline) |
| Migration complexity | Low (existing data unchanged) |
| Existing code compatibility | High (all existing MPTT calls unchanged) |
| Polyhierarchy support | Supplemental (via alternative paths) |

**Why B wins:**
- Zero data migration — existing MPTT model, seed data, and all categories stay untouched
- Preserves `MPTTModelAdmin` tree UI
- Existing `get_descendants()`, `get_ancestors()`, `category.parent` all unchanged
- Only 3 call sites need minor modification (listings view, search view, alert query)
- No change to search indexing or triggers
- Ad-to-category stays FK — one category per ad

### 5.2 Lookup Inheritance Research

**Source:** Researcher task `ses_03f05c7b6ffeTBlTDzZTWwO724` (2026-08-02)

**Key findings:**
- MPTT `get_ancestors(ascending=True)` returns ancestors in leaf→root order in a single indexed query
- Resolution is 2 queries on cache miss, 0 on cache hit (trivially fast for 30-category tree with 3-5 levels depth)
- `CategoryPath` alternative parents do NOT participate in inheritance — only canonical MPTT parent chain
- Cache invalidation per worker process (LocMemCache) is the same limitation as existing moderation criteria cache — acceptable with 5-minute TTL as safety net
- Through tables need NO schema changes — only composite FK indexes for resolution performance

**Recommended approach: 2-query single-pass MPTT walk-up with per-category caching (300s TTL) + signal-based invalidation**

---

## 6. Assumptions

1. **Category uniqueness** — a category entity exists once; alternative paths are additional *ways to find it*, not separate entities. Slug is globally unique.
2. **Ad category scope** — an ad always belongs to exactly one canonical category (FK). Alternative paths (including auto-paths to Благотворительность) don't duplicate ads.
3. **Navigation priority** — canonical MPTT tree is primary navigation; alternative paths are supplemental.
4. **Top-level categories are fixed** — the 7 top-level sections (Недвижимость, Транспорт, Товары, Животные, Услуги-работа-вакансии, Бизнес, Благотворительность) are defined upfront and should not change without re-categorization of existing content.
5. **Lookup group extensibility** — `listing_purpose` and `listing_feature` are shipped with the project; new groups can be added by admin at any time.
6. **Bot primary interface** — in Phase 1, sellers post only through Telegram bot. Web posting is deferred.
7. **Single currency** — price is in BAM only (multi-currency deferred per YAGNI).
8. **Price zero means free** — `price = 0` and `price = NULL` are both treated as "free/charity" items. No separate `is_free` boolean field for Phase 1.
9. **Inheritance is ancestor-replacement, not merge** — a subcategory's explicit purpose/feature set replaces the entire inherited set. No `UNION`/merge semantics across the ancestor chain.
10. **Only canonical MPTT chain participates in inheritance** — `CategoryPath` alternative parents are navigation-only and do not affect purpose/feature resolution.
11. **Благотворительность initial state** — starts without MPTT children, auto-populated only via CategoryPath (C14). This is not a permanent constraint — subcategories can be added later if needed, with no architectural change required. MPTT children and CategoryPath auto-links do not conflict.

---

## 7. Constraints

1. **No EAV** — all variable attributes use standard PostgreSQL FK/M:N through tables with B-Tree indexes.
2. **No GENERATED ALWAYS** — search_vector is maintained by trigger, not generated.
3. **Existing MPTT model preserved** — `Category` model schema unchanged. Rename logic handled entirely in builder via `new_slug` + `slug_rename_map`; no new fields needed.
4. **Ad lifecycle unchanged** — `transition_to()` method and status matrix remain as-is.
5. **System lookup groups are permanent** — `listing_purpose` and `listing_feature` cannot be deleted via admin.
6. **PostgreSQL only** — no MySQL/SQLite compatibility required.
7. **Russian is base language** — all seed data and storage use Russian as the canonical form.

---

## 8. Risks

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| CategoryPath creates confusion in navigation UI (two paths to same category with different feature sets) | Medium | Medium | Document that features are bound to category (not path). Same category = same features regardless of path. |
| LookupGroup.is_system flag may be accidentally toggled off in admin | Low | Low | Make is_system read-only in admin for existing system groups; changable only via data migration |
| Data migration for existing ads (adding default listing_purpose) may fail for ads in complex states | Medium | Low | Use a single default purpose value (`sell`), handle in migration with fallback; run migration as separate step |
| Bot FSM complexity increases with purpose/feature steps | Medium | Low | Keep feature selection as optional skip; use inline keyboard pagination for many features |
| **Благотворительность auto-path rule** — changing price from 0 to positive requires removing the CategoryPath AND re-indexing | Low | High | Handle in `Ad.save()` or `transition_to()`; use a service method for price+status changes to keep logic centralized |
| **Overlapping top-level categories** — a user may be confused if the same ad appears in Товары and Животные when browsing | Medium | Medium | UI should show canonical category name + breadcrumb; clearly indicate when an item appears via alternative path |
| **Seed data mismatch** — existing `categories.json` fixture uses different top-level structure (Avito-derived) | Medium | High | Regenerate fixtures from scratch using the new 8 top-level structure; old fixture becomes invalid |
| **Builder/bot schema desync** — `categories.yaml` config structure evolves but the builder module and YAML drift apart | Low | Low | Builder reads YAML schema version field; integration test validates that builder creates expected data |
| **Database migration ordering** — T0 (catalog data migration) must run AFTER T1/T3 model migrations but is defined in a different app | Medium | Medium | T0 migration depends on `lookups/XXXX_add_lookup_models` and `categories/XXXX_add_through_tables`; Django migration dependency graph must be explicit |

---

## 9. Open Questions

> All business questions have been resolved. The following are technical/implementation questions for the implementation planning phase:

1. **CategoryPath cycle detection** — should this be validated at the ORM level, service level, or admin level only?
2. **Feature selection UI in bot** — for categories with many features (10+), should the bot use paginated inline keyboards or a different UX pattern?
3. **Photo dedup edge case** — two different users uploading the same photo → should the system share the file or create separate `AdImage` rows?
4. **Backfill migration for AdImage SHA-256** — should it run as a data migration or a management command for large existing datasets?
5. **Благотворительность auto-path trigger location** — should this be in `Ad.save()`, in `Ad.price` setter, in a `post_save` signal, or in the bot handler that sets the price?
6. **Category move (MPTT restructure) and cache invalidation** — `node_moved` signal handler must invalidate both old and new subtrees; is there existing MPTT `node_moved` signal infrastructure to hook into?

---

## 10. Out of Scope

1. **Web-based ad posting** — sellers post only via Telegram bot in Phase 1
2. **Multi-currency support** — single BAM currency only (YAGNI)
3. **Category-specific pricing fields** (e.g., price per m² for real estate) — may use ListingFeature with future price modifiers
4. **Category-specific validation rules** — all validation is generic in Phase 1
5. **SEO-friendly multi-path URLs** — single `/category/<slug>/` pattern only
6. **Image deduplication across users** — dedup within same user's uploads only (Phase 1)
7. **Dynamic lookup group creation from bot** — only admin can create groups
8. **Category drag-and-drop reordering in admin** — MPTT's default tree UI is sufficient for Phase 1
9. **Direct posting into Благотворительность** — sellers cannot choose "Благотворительность" as a category; it is system-managed
10. **Separate `is_free` boolean** — free detection is based on `price = 0 | NULL`; no dedicated free flag in Phase 1
11. **Dynamic YAML config reloading** — config is read at migration/seed time, not watched for changes at runtime

---

## 11. Definition of Ready

The specification is **ready for implementation planning** when:

- [x] All business decisions collected from Product Owner (14 questions answered)
- [x] Multi-parent category approach researched and approved
- [x] Catalog config-driven builder approach confirmed (YAML + builder.py + `new_slug` rename + auto-rewrite)
- [x] All conceptual development tasks identified with dependencies
- [x] Assumptions documented
- [x] Constraints documented
- [x] Risks assessed
- [x] Open questions documented (technical only, do not block planning)
- [x] Out of scope explicitly defined