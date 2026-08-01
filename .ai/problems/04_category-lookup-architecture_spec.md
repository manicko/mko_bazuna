# Specification: Category + Universal Lookup Architecture

**File:** `04_category-lookup-architecture_spec.md`
**Status:** Final (ready for implementation planning)
**Date:** 2026-08-01
**Source Decision:** `.ai/problems/DECISION_03.md`, `.ai/problems/DECISION_04.md`
**Research:** `docs/07-design-researches/Design_02/04-multi-parent-categories-research.md`

---

## 1. Problem Statement

The Mko Bazuna classifieds board needs a scalable architecture for ad categories and reference data that meets two goals:

1. **Multi-parent category navigation** — a category like "Bicycles" must appear under multiple parent categories simultaneously (Transport, Sports & Hobbies) so buyers can find it through different navigation paths. The current `django-mptt` strict tree (single `parent` FK) does not support this.

2. **Universal reference data system** — variable ad attributes (publication purpose, item condition, features) must be managed through a unified lookup system where:
   - New values are added/changed via admin panel, without code changes
   - Categories define which lookup values are applicable
   - All lookups are cacheable and indexed for search/filtering
   - No EAV pattern is used (standard PostgreSQL FK/M:N only)

3. **Top-level category structure** — the category hierarchy must be organized under 8 fixed top-level sections:
   - **Недвижимость** (Real Estate)
   - **Транспорт** (Auto)
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
| L04 | `LookupItem` has: `code` (machine-readable, immutable), `slug` (URL-friendly), `name_i18n` (JSONB), `sort_order` (per-group), `is_active` (bool), `icon` (optional text/emoji), `color` (optional hex) | Must |
| L05 | `LookupGroup` has `is_system` boolean — system groups cannot be deleted via admin | Must |
| L06 | Two built-in system lookup groups ship with the project: `listing_purpose` and `listing_feature` | Must |
| L07 | Category ↔ LookupItem M:N relationships: `CategoryListingPurpose` and `CategoryListingFeature` through models | Must |
| L08 | All lookup values are managed exclusively through Django admin | Must |
| L09 | No EAV — standard PostgreSQL FK and M:N through tables only | Must |

#### ListingPurpose — What the User Wants to Do With the Object

`listing_purpose` describes the **intent** behind the listing. Every ad must have exactly one purpose. Common purposes shipped with the project:

| Code | Slug (RU) | Description |
|------|-----------|-------------|
| `sell` | `sell` | Selling an item |
| `buy` | `buy` | Buying / looking to purchase |
| `rent` | `rent` | Renting out (lessor) |
| `rent_request` | `rent-request` | Looking to rent (lessee) |
| `service` | `service` | Offering a service |
| `service_request` | `service-request` | Looking for a service |
| `job_offer` | `job-offer` | Offering a job / vacancy |
| `job_seek` | `job-seek` | Looking for a job |
| `giveaway` | `giveaway` | Giving away for free (charity / free stuff) |
| `exchange` | `exchange` | Exchanging items (barter) |

Not all purposes apply to all categories. For example:
- **Real Estate**: `sell`, `rent`, `rent_request`, `buy`, `exchange`
- **Auto**: `sell`, `buy`, `exchange`
- **Jobs**: `job_offer`, `job_seek`
- **Services**: `service`, `service_request`
- **Благотворительность**: `giveaway` only (auto-assigned when price = 0)

Category ↔ ListingPurpose bindings are managed via the `CategoryListingPurpose` through table. The bot FSM filters available purposes to only those linked to the selected category.

#### ListingFeature — Additional Attributes of the Listing

`listing_feature` describes **characteristics or conditions** of the listing. An ad can have 0..N features. Common features shipped with the project:

| Code | Slug (RU) | Description |
|------|-----------|-------------|
| `new` | `new` | Brand new, sealed |
| `used` | `used` | Used item |
| `urgent` | `urgent` | Urgent sale |
| `vip` | `vip` | VIP / promoted listing |
| `with_delivery` | `with-delivery` | Delivery available |
| `with_installment` | `with-installment` | Installment payment available |
| `with_video` | `with-video` | Listing has video |
| `with_document` | `with-document` | Documents available |
| `with_guarantee` | `with-guarantee` | Warranty included |
| `negotiable` | `negotiable` | Price negotiable |
| `business` | `business` | From a business seller |
| `premium` | `premium` | Premium ad |

Features are category-specific. Each category defines which features are available via the `CategoryListingFeature` through table. For example:
- **Electronics**: `new`, `used`, `with_guarantee`, `with_delivery`
- **Real Estate**: `urgent`, `negotiable`, `with_document`, `with_installment`
- **Animals**: `with_document` (pedigree), `with_delivery`

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
  code           — CharField(unique per group? or globally? — see design decision 2.2.1)
  slug           — SlugField(unique globally)
  name_i18n      — JSONField(nullable) — {'ru': str, 'bs': str, 'en': str}
  sort_order     — PositiveIntegerField(default=0)
  is_active      — BooleanField(default=True)
  icon           — CharField(max_length=50, blank=True) — emoji or SVG icon name
  color          — CharField(max_length=7, blank=True) — hex color (#RRGGBB)
```

- `code` uniqueness: **globally unique** (simpler, avoids FK filtering complexity). 
  Rationale: though items belong to a group, a universal code across all groups prevents ambiguity in migrations and scripts. The group context is provided by query filters, not by code scoping.

#### M:N Through Tables

**CategoryListingPurpose:**
```
CategoryListingPurpose:
  id             — AutoField (PK)
  category       — FK -> Category (CASCADE)
  listing_purpose — FK -> LookupItem (CASCADE, group restricted to listing_purpose at app level)
```

**CategoryListingFeature:**
```
CategoryListingFeature:
  id             — AutoField (PK)
  category       — FK -> Category (CASCADE)
  feature        — FK -> LookupItem (CASCADE, group restricted to listing_feature at app level)
```

- Unique constraint: `(category, listing_purpose)` and `(category, feature)` pairs
- These are pure M:N through tables (no additional metadata columns)

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

### 2.8 Bot FSM Integration

| ID | Requirement | Priority |
|----|-------------|----------|
| B01 | After category selection in bot FSM: show available ListingPurpose options for that category | Must |
| B02 | After purpose selection: if category has features, show multi-select feature list | Must |
| B03 | If category has no features defined → skip features step entirely | Must |
| B04 | Purpose is required (single choice) — seller cannot proceed without selecting | Must |
| B05 | Features are optional (0..N) — seller can skip | Must |
| B06 | Flow: category → purpose → features → title/description → price → address → photos → confirmation | Must |

---

## 3. Conceptual Development Tasks

> **Note:** Tasks are listed in dependency order. Tasks within the same dependency group (same number) can be parallelized.

| # | Task | Purpose | Expected Outcome | Dependencies |
|---|------|---------|-----------------|--------------|
| T1 | **Create `lookups` Django app** with `LookupGroup`, `LookupItem` models + migration | Core reference data infrastructure | `apps/lookups/` app with models, migration, admin, `__init__.py`, `apps.py` | None |
| T2 | **Add `CategoryPath` model** to `categories` app + migration | Multi-parent navigation support | `CategoryPath` model in `apps/categories/models.py`, migration | T1 (uses Category which already exists) |
| T3 | **Create through models** `CategoryListingPurpose`, `CategoryListingFeature` in `categories` or new through app + migration | Bind lookups to categories | Through tables with FKs + unique constraints | T1, T2 |
| T4 | **Add `listing_purpose` FK and `features` M:N** to `Ad` model + data migration | Ad can carry purpose and features | New fields on `Ad`, `AdFeature` through model, data migration for existing ads | T3 |
| T5 | **Implement Lookup admin UI** — `LookupGroupAdmin`, `LookupItemAdmin`, through-table inlines | Admin can manage reference data | Complete admin for all lookup models with protection for system groups | T1, T3 |
| T6 | **Implement Category admin extensions** — add `CategoryPath` inline + lookup inlines to `CategoryAdmin` | Admin can manage multi-parent paths and category-lookup bindings | Extended `CategoryAdmin` with TabularInlines | T2, T3, T5 |
| T7 | **Create `FileHashService`** + add `sha256` field to `AdImage` + override `save()` | Photo deduplication | `FileHashService`, migration for sha256 field, backfill script | None |
| T8 | **Create Lookup caching service** + signal-based invalidation | Performance: cached lookups | Cache service, signal handlers, invalidation on admin save | T1 |
| T9 | **Implement Bot FSM integration** — add purpose/feature steps to ad creation dialog | Seller can set purpose and features during posting | Extended bot FSM states and handlers | T4 |
| T10 | **Implement "Copy Ad" bot command** — `/copy` in seller menu | Reuse existing ad as template | Bot command handler, service function for copying | T4 |
| T11 | **Implement Navigation UI updates** — render alternative category paths in web navigation | Multi-parent paths visible to buyers | Updated templates/views for category navigation | T2 |
| T12 | **Seed data fixtures** — initial LookupGroup (listing_purpose, listing_feature) and LookupItem records | Development data for local testing | JSON/YAML fixtures for lookup initial data | T1 |
| T13 | **Ad admin updates** — add listing_purpose/features to `AdAdmin` list/filter/search | Moderators can see purpose and features | Updated `AdAdmin` | T4 |

---

## 4. Product Owner Decisions

| # | Question | Decision |
|---|----------|----------|
| Q1 | LookupItem identity pattern | **Code** = machine-readable immutable identifier (e.g., `sell`, `rent_long`); **Slug** = URL-friendly identifier (e.g., `sell`, `rent-long`). Code globally unique across all groups. |
| Q2 | Translation storage format | **JSONB `name_i18n`** — same pattern as `Category.name_i18n` and `City.name_i18n` |
| Q3 | ListingPurpose multiplicity on Ad | **Required** — every ad must have exactly one listing purpose (non-nullable FK) |
| Q4 | ListingFeature multiplicity on Ad | **Optional 0..N** — seller can add any number of features supported by the category |
| Q5 | Deactivation behavior | **Preserve data** — existing ads keep references; deactivated items hidden from UI and filter options |
| Q6 | "Copy Ad" initial scope | **Telegram bot only** — `/copy` command in seller's ad management menu |
| Q7 | Photo deduplication architecture | **Both A + B** — dedicated `FileHashService.calculate_sha256(file)` method, called automatically by `AdImage.save()` |
| Q8 | System lookup group protection | **Hard protection** — `is_system = True` flag on `LookupGroup`, admin delete blocked, lifecycle controlled by code |
| Q9 | Bot FSM posting flow | **Category → purpose → features → title/description → price → address → photos** |
| Q10 | LookupItem.sort_order scope | **Per-group ordering** — independent sort_order sequences within each `LookupGroup` |

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

---

## 6. Assumptions

1. **Category uniqueness** — a category entity exists once; alternative paths are additional *ways to find it*, not separate entities. Slug is globally unique.
2. **Ad category scope** — an ad always belongs to exactly one canonical category (FK). Alternative paths (including auto-paths to Благотворительность) don't duplicate ads.
3. **Navigation priority** — canonical MPTT tree is primary navigation; alternative paths are supplemental.
4. **Top-level categories are fixed** — the 8 top-level sections (Недвижимость, Авто, Товары, Животные, Работа, Услуги, Бизнес, Благотворительность) are defined upfront and should not change without re-categorization of existing content.
5. **Lookup group extensibility** — `listing_purpose` and `listing_feature` are shipped with the project; new groups can be added by admin at any time.
6. **Bot primary interface** — in Phase 1, sellers post only through Telegram bot. Web posting is deferred.
7. **Single currency** — price is in BAM only (multi-currency deferred per YAGNI).
8. **Price zero means free** — `price = 0` and `price = NULL` are both treated as "free/charity" items. No separate `is_free` boolean field for Phase 1.

---

## 7. Constraints

1. **No EAV** — all variable attributes use standard PostgreSQL FK/M:N through tables with B-Tree indexes.
2. **No GENERATED ALWAYS** — search_vector is maintained by trigger, not generated.
3. **Existing MPTT model preserved** — `Category` model schema unchanged except adding new related models.
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

---

## 9. Open Questions

> All business questions have been resolved. The following are technical/implementation questions for the implementation planning phase:

1. **CategoryPath cycle detection** — should this be validated at the ORM level, service level, or admin level only?
2. **LookupItem.code global uniqueness** — confirmed globally unique. Should validation be at DB level (unique constraint) or app level only?
3. **Feature selection UI in bot** — for categories with many features (10+), should the bot use paginated inline keyboards or a different UX pattern?
4. **Photo dedup edge case** — two different users uploading the same photo → should the system share the file or create separate `AdImage` rows?
5. **Backfill migration for AdImage SHA-256** — should it run as a data migration or a management command for large existing datasets?
6. **Благотворительность auto-path trigger location** — should this be in `Ad.save()`, in `Ad.price` setter, in a `post_save` signal, or in the bot handler that sets the price?

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

---

## 11. Definition of Ready

The specification is **ready for implementation planning** when:

- [x] All business decisions collected from Product Owner (10 questions answered)
- [x] Multi-parent category approach researched and approved
- [x] All conceptual development tasks identified with dependencies
- [x] Assumptions documented
- [x] Constraints documented
- [x] Risks assessed
- [x] Open questions documented (technical only, do not block planning)
- [x] Out of scope explicitly defined