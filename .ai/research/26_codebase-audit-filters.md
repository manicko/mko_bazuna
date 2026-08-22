# Codebase Audit: Catalog Filtering & Sorting

**Date:** 2026-08-21
**Scope:** `src/backend/apps/` + `src/telegram_bot/`
**Purpose:** Document the current and possible state of catalog filtering and sorting to inform design decisions for extending the filter set.

---

## 1. Current Ad Model — Filterable Fields

**File:** `src/backend/apps/ads/models.py` (class `Ad`, db table `ads`)

All filterable fields, in declaration order. Django auto-generates the DB column name: for scalar fields it matches the attribute name; for FK fields it is `<field_name>_id`.

| Attribute | DB Column | Type / Field | Semantic Meaning |
|---|---|---|---|
| `user` | `user_id` | FK → `users.User` | Ad owner (seller). FK, on_delete=CASCADE. |
| `title` | `title` | `CharField(max=200)` | Russian title (base storage language; translated from seller input). |
| `title_en` | `title_en` | `CharField(max=200)` | English title. |
| `title_bs` | `title_bs` | `CharField(max=200)` | Bosnian title. |
| `description` | `description` | `TextField` | Russian description (base storage language). |
| `description_en` | `description_en` | `TextField` | English description. |
| `description_bs` | `description_bs` | `TextField` | Bosnian description. |
| `original_language` | `original_language` | `CharField(max=5)` | Original language code (e.g. `ru`, `en`, `bs`). |
| `price` | `price` | `PositiveIntegerField` | **Price in whole BAM units.** `null` allowed ("YAGNI" multi-currency deferred). |
| `category` | `category_id` | FK → `categories.Category` | Ad category. `null` during draft phase. on_delete=PROTECT. |
| `city` | `city_id` | FK → `locations.City` | Ad city location. `null` during draft phase. on_delete=PROTECT. |
| `listing_purpose` | `listing_purpose_id` | FK → `lookups.LookupItem` (group `listing_purpose`) | What the user wants to do with the object (sell/rent/give-away/…). `null` allowed. on_delete=PROTECT. |
| `features` | join table `ad_features` | `ManyToManyField` → `lookups.LookupItem` (through `AdFeature`, group `listing_feature`) | Listing features (new/used/delivery/pickup/…). M2M via through model with `sort_order`. |
| `category_name` | `category_name` | `CharField(max=200)` | Denormalized Russian category name; trigger-synced, `editable=False`. |
| `status` | `status` | `CharField(max=20)` | Lifecycle status (see `apps.core.enums.AdStatus`). |
| `source` | `source` | `CharField(max=20)` | Origin of ad (see `apps.core.enums.AdSource`). |
| `created_at` | `created_at` | `DateTimeField` | Creation timestamp (`auto_now_add=True`). |
| `updated_at` | `updated_at` | `DateTimeField` | Last update timestamp (`auto_now=True`). |
| `published_at` | `published_at` | `DateTimeField` | Drives archive/delete timers; resets on every PUBLISHED transition. |
| `original_published_at` | `original_published_at` | `DateTimeField` | Set once on first publish; immutable. |
| `archived_at` | `archived_at` | `DateTimeField` | Auto-archive (2 months) or manual archive. |
| `deleted_at` | `deleted_at` | `DateTimeField` | Soft delete timestamp. |
| `moderation_failed_at` | `moderation_failed_at` | `DateTimeField` | Failed auto-check; drives 7-day purge (mutually exclusive with `rejected_at`). |
| `rejected_at` | `rejected_at` | `DateTimeField` | Manually rejected; drives 90-day cleanup (mutually exclusive with `moderation_failed_at`). |
| `search_vector` | `search_vector` | `SearchVectorField` | Legacy concatenated TSVECTOR (to be dropped per docs/02-database/db-indexes.md). |
| `search_vector_ru` | `search_vector_ru` | `SearchVectorField` | Russian TSVECTOR for native PostgreSQL FTS. |
| `search_vector_bs` | `search_vector_bs` | `SearchVectorField` | Bosnian TSVECTOR. |
| `search_vector_en` | `search_vector_en` | `SearchVectorField` | English TSVECTOR. |
| `published_by` | `published_by_id` | FK → `users.User` | Moderator who manually published. on_delete=SET_NULL. |
| `moderated_by` | `moderated_by_id` | FK → `users.User` | Moderator who manually rejected. on_delete=SET_NULL. |

**Note on attribute-level fields (area, rooms, etc.):** There are **no** numeric or typed attribute fields on the `Ad` model. The model stores only `price` as a numeric field. There is no `area`, `rooms`, `year`, `mileage`, `brand`, or similar structured attribute column. This is a deliberate Phase-1 constraint — attribute data is not collected at ad-creation time (see §9).

---

## 2. Current URL Structure & Query Parameter Parsing

**File:** `src/backend/apps/search/urls.py` (`search/` route), `src/backend/apps/ads/urls.py` (listings routes), `src/backend/config/urls.py` (root include).

### URL patterns

`config/urls.py` includes `apps.ads.urls`, `apps.search.urls`, `apps.categories.urls`, `apps.locations.urls`, etc. at the root.

**Search (`/search/`):**
```
GET /search/   →  search:search
```

**Listings (`/`):**
```
GET /                                   →  ads:listings          (all published, city-defaulted)
GET /city/<slug:city_slug>/             →  ads:listings_city     (city filter)
GET /category/<slug:category_slug>/     →  ads:listings_category (category subtree filter)
GET /category/<cat>/<city>/<...>        (only if composed — see note below)
GET /<int:ad_id>/                       →  ads:detail
```

**Query parameters parsed in both `listings()` and `search()`:**

| Param | Used in `ads/views/listings.py` | Used in `search/views/search.py` | Parsing logic |
|---|---|---|---|
| `q` | — | yes | Full-text search query (FTS). Empty → browse/sort path. |
| `category` | no (uses path `category_slug`) | yes | Category **slug** (query param). Resolves via `Category.objects.get(slug=...)`; expands to subtree via `get_descendants()`. |
| `city` | yes | yes | City **slug**. Explicit `?city=` wins; otherwise middleware-resolved `request.preferred_city` is the default filter (comment references rules F-5 / R-05 / R-06). |
| `min_price` | yes | yes | `price__gte=int(...)`; `ValueError` silently ignored. |
| `max_price` | yes | yes | `price__lte=int(...)`; `ValueError` silently ignored. |
| `sort` | yes | yes | Defaults to `AdSort.DATE_NEW` (`"date_desc"`). Validated against `AdSort` StrEnum values by `==` comparison. Unsupported → falls to `else` (date_desc). |
| `page` | yes | yes | Pagination page number (Paginator, 24 per page). |

> **Observation:** The two views use the *same query-param names* (`category`, `city`, `min_price`, `max_price`, `sort`, `page`) but differ in how `category`/`city` reach the view: `listings` accepts them via URL path segments (`<slug:category_slug>`, `<slug:city_slug>`) **and** optionally via `?city=`/`?category=`; `search` accepts them only via query params.

### Exact URL format (example browse URL)
```
/category/nedvizhnost/?city=podgorica&min_price=5000&max_price=50000&sort=price_desc&page=2
```
### Exact URL format (example search URL)
```
/search/?q=телефон&category=telefony&city=bar&sort=date_desc
```

---

## 3. Current Sort Implementation

**File:** `src/backend/apps/core/enums.py` (class `AdSort`, a `StrEnum`)

```python
class AdSort(StrEnum):
    """Sort options for ad listings."""
    DATE_NEW = "date_desc"
    DATE_OLD = "date_asc"
    PRICE_LOW = "price_asc"
    PRICE_HIGH = "price_desc"
```

**DB field mapping & direction** (applies identically in both views):

| Enum member | URL `sort` value | DB field | Direction | Code ref |
|---|---|---|---|---|
| `AdSort.DATE_NEW` | `"date_desc"` | `published_at` | DESC (`-`) | listings: `ads = ads.order_by("-published_at")` default `else` branch |
| `AdSort.DATE_OLD` | `"date_asc"` | `published_at` | ASC | listings: `ads.order_by("published_at")` |
| `AdSort.PRICE_LOW` | `"price_asc"` | `price` | ASC | listings: `ads.order_by("price")` |
| `AdSort.PRICE_HIGH` | `"price_desc"` | `price` | DESC (`-`) | listings: `ads.order_by("-price")` |

In `search/views/search.py`, when a text query `q` is present, sort is **overridden** to `order_by("-rank")` (PostgreSQL `SearchRank`) and the `sort` param is parsed only for context/pagination-URL preservation (lines ~120–130). When `q` is empty, the same four-way branch as `listings` is used (lines ~138–148).

**Note:** `sort` is never validated against the enum — any unrecognized value falls through to the `else` → `DATE_NEW`. New sort options would need to be added both to `AdSort` and to the `if/elif/else` chain in both views.

---

## 4. Category Model — MPTT Usage

**File:** `src/backend/apps/categories/models.py` (class `Category`)

`Category` extends `mptt.models.MPTTModel` (django-mptt). Confirmed by import:
```python
from mptt.models import MPTTModel, TreeForeignKey
```
and class declaration `class Category(MPTTModel):`.

### MPTT fields
- `name` — `CharField(max=200)`, Russian base storage language.
- `name_i18n` — `JSONField`, localized names `{'ru', 'bs', 'en'}`.
- `slug` — `SlugField(unique=True)`, URL-friendly identifier.
- `is_active` — `BooleanField(default=True)`. Inactive categories hide their ads.
- `parent` — `TreeForeignKey("self", on_delete=CASCADE, related_name="children")`. `blank=True, null=True` (root nodes have NULL parent).

`MPTTMeta.order_insertion_by = ["name"]`.

### Subtree filtering (`get_descendants`)
Both `listings()` and `search()` use the same idiom to expand a category selection to its subtree:
```python
descendant_ids = category.get_descendants(include_self=True).values_list("id", flat=True)
ads = ads.filter(category_id__in=descendant_ids)
```
This produces an `IN (...)` list of leaf-through-root category IDs, which PostgreSQL matches against the `category_id` column. `get_descendants()` is provided by django-mptt; `include_self=True` ensures the selected category's own ads are included.

### Additional category relationships (filter-relevant)
- `CategoryListingPurpose` (through `CategoryListingPurpose`, db `category_listing_purposes`): M:N binding `Category ↔ LookupItem` (group `listing_purpose`), with `is_default` flag and indexes `IX_cat_listing_purpose_composite` / `IX_cat_listing_purpose_reverse`.
- `CategoryListingFeature` (through `CategoryListingFeature`, db `category_listing_features`): M:N binding `Category ↔ LookupItem` (group `listing_feature`), with indexes `IX_cat_listing_feature_composite` / `IX_cat_listing_feature_reverse`.

These through models define *which* lookup items are available *per category* but are **not** currently wired into the listing/search filter chain — they constrain the bot's ad-creation choice set (see §9) and could constrain the buyer's filter options.

### `CategoryPath` (alternative parent)
`CategoryPath` provides multi-parent navigation shortcuts (db `category_paths`). Each entry binds a `category` to an alternative `parent` with `sort_order` and `is_automatic`. This is **not** MPTT-managed; it is a separate navigation aid and is not used in the current filter chain.

### Fields available for filtering (today & potential)
- **Active today:** `category_id` (subtree via `get_descendants`), `is_active`.
- **Potential:** `listing_purpose` (via the `CategoryListingPurpose` resolver), `listing_feature` (via `CategoryListingFeature` resolver), `CategoryPath` alternative parentage.

---

## 5. City Model — Identifiers

**File:** `src/backend/apps/locations/models.py` (class `City`, db table `cities`)

> Note: the AGENTS.md references "cities" but the actual app is `apps.locations`. The path `src/backend/apps/cities/` does not exist.

### Fields
| Attribute | DB Column | Type | Meaning |
|---|---|---|---|
| `country_code` | `country_code` | `CharField(max=2)` | ISO country code (e.g. `ME`). |
| `name` | `name` | `CharField(max=200)` | Russian city name (base storage language). |
| `name_i18n` | `name_i18n` | `JSONField` | Localized names `{'ru', 'bs', 'en'}`. |
| `region` | `region` | `CharField(max=100)` | Administrative region. |
| `slug` | `slug` | `SlugField(unique=True)` | URL-friendly, **globally unique** city identifier. |

### Identifier usage in filtering
Cities are matched **exactly by `slug`** — both views call `City.objects.get(slope=...)` where `city_slug` is the URL path or `?city=` param value. There is **no** fallback/prefix matching; an unrecognized slug yields a did-you-mean suggestion via `difflib.get_close_matches` (cutoff 0.6) and applies **no filter**, showing all-city results.

There is **no** city hierarchy (no MPTT, no region tree). Cities are a flat lookup table. Region is informational only and is **not** used as a filter dimension in either view.

---

## 6. LookupItem / LookupGroup — Lookup Integration

**Files:**
- `src/backend/apps/lookups/models.py` (classes `LookupGroup`, `LookupItem`)
- `src/backend/apps/lookups/enums.py` (class `LookupGroupCode`, a `StrEnum`)

### LookupGroupCode enum (the only group codes that exist)
```python
class LookupGroupCode(StrEnum):
    LISTING_PURPOSE = "listing_purpose"
    LISTING_FEATURE = "listing_feature"
```
**Only two group codes exist** in the codebase (confirmed by grep across `src/` — no other `LookupGroupCode.*`) references appear). These are the only two values that could serve as filter dimensions on the `Ad` model via lookup FKs.

### LookupItem fields (db table `lookup_items`)
| Attribute | DB Column | Type | Meaning |
|---|---|---|---|
| `group` | `group_id` | FK → `lookup_groups` | Parent lookup group (code: `listing_purpose` or `listing_feature`). |
| `slug` | `slug` | `SlugField(unique=True)` | Globally unique identifier (e.g. `sell`, `new`, `delivery`). |
| `name_i18n` | `name_i18n` | `JSONField` | Localized names `{'ru', 'bs', 'en'}`. |
| `sort_order` | `sort_order` | `PositiveIntegerField` | Display ordering within group. |
| `is_active` | `is_active` | `BooleanField(default=True)` | Inactive items hidden from UI/filter options. |
| `icon` | `icon` | `CharField(max=50)` | Emoji or SVG icon name. |
| `color` | `color` | `CharField(max=7)` | Hex color `#RRGGBB`. |

`LookupGroup` (db `lookup_groups`): `code` (unique), `name_i18n`, `is_system`, `sort_order`.

### Confirmed FK/M2M wiring on Ad
In `ads/models.py`:
- `listing_purpose` is a `ForeignKey("lookups.LookupItem", limit_choices_to={"group__code": LookupGroupCode.LISTING_PURPOSE})`. **Confirmed FK.**
- `features` is a `ManyToManyField("lookups.LookupItem", through="ads.AdFeature", limit_choices_to={"group__code": LookupGroupCode.LISTING_FEATURE})` — but note: the `limit_choices_to` on the M2M's `feature` field is actually enforced on the `AdFeature.feature` through field, not the `Ad.features` M2M directly. The through model `AdFeature` has `feature = ForeignKey("lookups.LookupItem", limit_choices_to={"group__code": LookupGroupCode.LISTING_FEATURE})`.

### Lookup groups available in `categories.yaml`
- **`listing_purpose`** (10 items): `sell`, `give-away`, `rent`, `rent-short`, `lost`, `found`, `offer-service`, `seek-service`, `job-offer`, `job-seek`.
- **`listing_feature`** (19 items): `new`, `used`, `delivery`, `pickup`, `negotiable`, `credit`, `exchange`, `installment`, `urgent`, `luxury`, `eco`, `handmade`, `branded`, `custom`, `warranty`, `packaging`, `import`, `local`, `smart-home`.

These are the two lookup groups that map to Ad-model FKs/M2Ms and could therefore serve as **filter dimensions** (single-select for `listing_purpose`, multi-select for `features`).

---

## 7. Existing Indexes — Filtering Support

**File:** `docs/02-database/db-indexes.md`

### Relevant filter indexes on `ads`
```python
models.Index(name="IX_ads_pub_listing",
    fields=["status", "category_id", "city_id", "-published_at"],
    condition=Q(status=AdStatus.PUBLISHED))   # partial: ~99% of public reads
```
This is the **primary listing index**. It supports the current filter chain exactly:
- `status = PUBLISHED` → the partial condition.
- `category_id IN (...)` → second segment.
- `city_id = <n>` → third segment.
- `-published_at` → the default sort (newest first).

The index is ordered so a browse by category-subtree + city + default date-desc sort is an **index-only scan**.

> **No index on `price`.** The doc explicitly states: *"price has no index (rare filter in phase 1; add only after EXPLAIN ANALYZE at 500k rows, zone C7)."* The `min_price`/`max_price` filters currently do a sequential/BRIN scan over the `IX_ads_pub_listing` partial index (filtering on it post-scan).
>
> **No index on `listing_purpose_id` or `features`.** Adding these as filter dimensions would require new indexes (a B-tree on `listing_purpose_id` within the PUBLISHED partition, and the existing M2M join table `ad_features` already has a unique constraint on `(ad, feature)` plus an implicit index on the reverse lookup).

### Other published/ads indexes
- `IX_ads_search_gin_*` (4 GIN indexes) — support FTS only, not filter dimensions.
- `IX_ads_archive_sweep`, `IX_ads_delete_sweep`, `IX_ads_purge_*`, `IX_ads_rejected_sweep`, `IX_ads_purge_deleted` — background job sweeps, not public reads.
- `IX_ads_user_status` — seller cabinet queries.

### Category/lookup indexes (relevant if those filters are extended)
- `IX_cat_listing_purpose_composite` (`category`, `listing_purpose`) and reverse (`listing_purpose`).
- `IX_cat_listing_feature_composite` (`category`, `feature`) and reverse (`feature`).
- These support *resolving* which purposes/features a category permits, but **not** direct Ad filtering by purpose/feature — those would need Ad-side indexes.

---

## 8. Views & Filters — Exact Filter Chain Construction

**Files:**
- `src/backend/apps/search/views/search.py` (function `search`, ~lines 35–125)
- `src/backend/apps/ads/views/listings.py` (function `listings`, ~lines 47–165)

### `listings()` filter chain (`ads/views/listings.py`)
```
1. ads = Ad.objects.filter(status=AdStatus.PUBLISHED)
            .select_related("category", "city", "user")
            .prefetch_related("user__trust_score")
2. IF category_slug:
     category = Category.objects.get(slug=category_slug, is_active=True)
     descendant_ids = category.get_descendants(include_self=True).values_list("id", flat=True)
     ads = ads.filter(category_id__in=descendant_ids)
3. IF city_slug OR ?city=:
     city = City.objects.get(slug=...)
     ads = ads.filter(city_id=city.id)
   else:
     preferred_city = request.preferred_city
     city = City.objects.get(slug=preferred_city)
     ads = ads.filter(city_id=city.id)
4. IF ?min_price:  ads = ads.filter(price__gte=int(min_price))
5. IF ?max_price:  ads = ads.filter(price__lte=int(max_price))
6. sort branch (AdSort) → ads = ads.order_by(...)
```
`listing_purpose` and `features` are **never filtered** in this chain. The `ads` queryset is built, sorted, then passed to `annotate_favorites` (favorites annotation is additive only) and `Paginator`.

### `search()` filter chain (`search/views/search.py`)
```
1. query = request.GET.get("q", "").strip()
   ads = Ad.objects.filter(status=AdStatus.PUBLISHED)
             .select_related("category", "city")
2. IF ?category:
     category = Category.objects.get(slug=..., is_active=True)
     descendant_ids = category.get_descendants(include_self=True).values_list("id", flat=True)
     ads = ads.filter(category_id__in=descendant_ids)
3. IF ?city (explicit) OR request.preferred_city:
     city = City.objects.get(slug=...)
     ads = ads.filter(city_id=city.id)
4. IF ?min_price:  ads = ads.filter(price__gte=int(min_price))
5. IF ?max_price:  ads = ads.filter(price__lte=int(max_price))
6. IF query:
     - locale-aware per-language TSVECTOR search
     - single-word → fuzzy category detection (expands subtree)
     - annotate rank, filter by vector, order_by("-rank")
     - record analytics, popular search, history
   else:
     sort branch (AdSort) → ads = ads.order_by(...)
```

### Can the filter chain be extended to `listing_purpose` and `features`?
**Yes — straightforwardly, for both views.**

- **`listing_purpose`**: The `Ad` model already has `listing_purpose` FK (column `listing_purpose_id`). It could be filtered as `ads.filter(listing_purpose__slug=<slug>)` or `ads.filter(listing_purpose_id=<id>)`. The lookup item can be resolved the same way category/city are: `LookupItem.objects.get(slug=<param>, group__code=LookupGroupCode.LISTING_PURPOSE)`. For multi-value, `listing_purpose__slug__in=[...]`.
  - The `categories.yaml` already defines per-category `listing_purpose_override` lists, so a buyer filter could be constrained to the *active* category's permitted purposes — but the current `listings` view resolves purpose *only* when no `?listing_purpose=` param is given, and uses the category's `get_resolved_purposes` (via `CategoryLookupResolver`) server-side for the *bot*, not for buyer filtering.

- **`features`**: The `Ad.features` M2M (through `AdFeature`) maps to `LookupItem` group `listing_feature`. Multi-select filtering is `ads.filter(features__slug=<slug>)` (single) or `ads.filter(features__slug__in=[...])` (multi). Because it is a M2M, querying it produces an implicit JOIN/INNER; combining multiple feature filters with `AND` semantics requires care (`&` of `Q` objects or chained `.filter()` — each chained `.filter(features__slug=X)` is an AND across features, which matches "ad has all these features").
  - `categories.yaml` defines per-category `listing_feature_override`, usable to constrain the buyer's feature filter options to the current category subtree's permitted features.

### Extension pattern (concrete, matches existing style)
```python
# listing_purpose filter (single or multi)
purpose_slug = request.GET.get("listing_purpose")
if purpose_slug:
    purpose_ids = LookupItem.objects.filter(
        slug__in=[purpose_slug] if "," not in purpose_slug else purpose_slug.split(","),
        group__code=LookupGroupCode.LISTING_PURPOSE,
    ).values_list("id", flat=True)
    ads = ads.filter(listing_purpose_id__in=purpose_ids)

# features filter (multi)
feature_slugs = request.GET.getlist("features") or (
    request.GET.get("features", "").split(",") if request.GET.get("features") else []
)
if feature_slugs:
    feature_ids = LookupItem.objects.filter(
        slug__in=feature_slugs, group__code=LookupGroupCode.LISTING_FEATURE
    ).values_list("id", flat=True)
    for fid in feature_ids:
        ads = ads.filter(features__id=fid)  # AND semantics: ad has ALL selected features
```

---

## 9. Bot Data Collection — What *Is* Collected During Ad Creation

**Files:**
- `src/telegram_bot/handlers/ad_create.py` (ad-creation FSM handler)
- `src/telegram_bot/states.py` (class `AdCreateState`)

### FSM state sequence (`AdCreateState`, `states.py`)
```python
class AdCreateState(StrEnum):
    CATEGORY       = "category"
    PURPOSE        = "purpose"
    FEATURES       = "features"
    CITY           = "city"
    TITLE          = "title"
    DESCRIPTION    = "description"
    PRICE          = "price"
    PHOTOS         = "photos"
    PREVIEW        = "preview"
```

### Data actually persisted to the Ad row
At the `confirm` step, `process_preview` → `update_ad_and_moderate(...)` writes exactly these fields:
```python
ad.title         = title_ru          # Russian base
ad.description   = desc_ru           # Russian base
ad.title_bs      = title_bs
ad.title_en      = title_en
ad.description_bs = desc_bs
ad.description_en = desc_en
ad.original_language = ...
ad.category_id   = category_id
ad.city_id       = city_id
ad.price         = price              # whole BAM units, or None
ad.listing_purpose_id = listing_purpose_id
ad.features.set(feature_ids)         # M2M via AdFeature
AdImageService.create_or_skip(...)   for each photo
```

### **Confirmed: NO numeric/attribute data is collected**
The bot collection flow collects, per state:
| State | Input | Ad field(s) |
|---|---|---|
| CATEGORY | keyword search → selection | `category_id` |
| PURPOSE | inline keyboard single choice | `listing_purpose_id` |
| FEATURES | inline keyboard multi-toggle | `features` (M2M) |
| CITY | text name → exact/did-you-mean | `city_id` |
| TITLE | 5–200 char text (Pydantic `TitlePayload`) | `title` (+ translations) |
| DESCRIPTION | 10–2000 char text (`DescriptionPayload`) | `description` (+ translations) |
| PRICE | whole-number BAM or `skip` (`PricePayload`) | `price` |
| PHOTOS | 1–5 JPEG, EXIF-stripped (`PhotoCountPayload`) | `AdImage` rows |
| PREVIEW | `confirm`/`cancel` text | — |

There is **no** handler, state, or payload for structured numeric attributes such as `area`, `rooms`, `year`, `mileage`, `brand`, `model`, or `color`. The only numeric field is `price` (BAM whole units). This is consistent with the category tree (§10) not carrying attribute templates — `categories.yaml` only defines `listing_purpose_override` and `listing_feature_override` per category, no per-category attribute schemas.

**Implication:** Any future attribute-based filtering (e.g. "apartments with ≥ 3 rooms" or "cars with mileage < 50000") requires both a bot-creation UX change *and* new columns/relations on the `Ad` model. Filter-by-purpose and filter-by-features, however, need **only view-layer changes** since the data already exists on the Ad row.

---

## 10. Categories Config — 7 Main Groups

**File:** `src/backend/apps/categories/catalog/categories.yaml`

Top-level `categories:` list contains exactly **7 main (root) groups**, each with `slug`, `name`, `name_i18n`, and optional `listing_purpose_override` / `listing_feature_override` and nested `children`.

### The 7 main groups
| # | slug | name (RU) | listing_purpose_override | notes |
|---|---|---|---|---|
| 1 | `real-estate` | Недвижимость | sell, rent, rent-short | children: apartments, houses, rooms, garages, land-plots, other-real-estate, commercial-real-estate (with sub-children: offices, flex-space, retail-spaces, warehouses, commercial-land) |
| 2 | `transport` | Транспорт | sell, rent | children: cars, motorcycles (→4 sub), trucks (→4 sub), water-transport (→4 sub), auto-parts (→11 sub) |
| 3 | `goods` | Товары | sell | children: clothing-shoes-accessories (→6), kids-clothing-shoes (→4), kids-products-toys (→10), beauty-health (→6), watches-jewelry (→3), home-garden (→6), electronics (→8), hobby-leisure (→7) |
| 4 | `animals` | Животные | sell, give-away, lost, found | children: dogs, cats, birds, fish-aquarium, other-animals, pet-supplies (→5 sub) |
| 5 | `services-jobs` | Услуги, работа, вакансии | job-seek, job-offer, seek-service, offer-service | children include repair-service (→6), construction-renovation (→9), it-computers (→3), beauty-health-services (→10), transport-logistics (→4), cleaning (→4), events-entertainment (→4), tutoring-education (→2), finance-legal (→5), security, home-services (→3), no-experience-jobs, food-service-jobs (→2), agriculture, trading, warehousing, other-services |
| 6 | `business` | Бизнес | sell, rent | children: ready-business, business-equipment (→6, with sub-children), business-commercial-real-estate (mirror of real-estate subtrees), business-services (→5) |
| 7 | `charity` | Благотворительность | give-away | no children; `listing_feature_override: []` |

Additional `category_paths:` section defines 6 alternative-parent navigation shortcuts (e.g. `auto-parts → goods`, `bicycles → transport`, `business-commercial-real-estate → real-estate`).

### Key structural facts
- Only root-level groups (the 7 above) lack a parent in the MPTT tree; all leaf categories have a single canonical MPTT parent plus optional `CategoryPath` alternative parents.
- `listing_purpose_override` / `listing_feature_override` constrain which lookup items the **bot** offers for a given category (see `categories/services/lookup_resolution.py` → `CategoryLookupResolver.get_resolved_purposes` / `get_resolved_features`).
- The override lists reference the `categories.yaml` `lookups.listing_purpose` / `lookups.listing_feature` slug sets (§6), so the filter vocabulary for both `listing_purpose` and `features` in a buyer filter could be derived from the *current* category's resolved overrides — but this wiring is **not** currently present in `listings()` or `search()`.

---

## 11. Summary — Current vs. Possible State

### Current filter dimensions (operational)
| Dimension | Source | Multi-value? | Query param / path | Sorted? |
|---|---|---|---|---|
| Category subtree | `Category.MPTT.get_descendants` | single | `category=<slug>` (search) / path `<cat_slug>` (listings) | no |
| City | `City.slug` (exact) | single | `city=<slug>` / path `<city_slug>` | no |
| Price floor | `Ad.price` | single int | `min_price=<int>` | no |
| Price ceiling | `Ad.price` | single int | `max_price=<int>` | no |
| Full-text term | `Ad.search_vector_<locale>` (PostgreSQL TSVECTOR) | single | `q=<text>` (search only) | by rank |

### Current sort options (4)
`date_desc` (default) / `date_asc` / `price_asc` / `price_desc` via `AdSort` StrEnum; maps to `published_at` ± or `price` ±. Overridden to `-rank` when FTS `q` is present.

### Immediately possible extensions (require view-layer work only; data already on Ad row)
| Extension | Column / relation | Effort | Index needed? |
|---|---|---|---|
| `listing_purpose` (single or multi) | `ad.listing_purpose_id` (FK) | add `?listing_purpose=` param + `ads.filter(listing_purpose__slug__in=...)` | recommend B-tree on `listing_purpose_id` (in PUBLISHED scope) |
| `features` (multi-select) | `ad.features` (M2M → `ad_features`) | add `?features=<slug>&features=<slug>` or `?features=a,b` + chained `.filter(features__slug=...)` | existing M2M unique constraint; consider index on `ad_features.feature_id` for performance |
| Combine purpose+features with category/city | same | chain in existing queryset | consider composite / partial indexes |

### Dimensions that need **schema + bot UX** changes (out of scope for a view-only audit)
Any numeric attribute filtering — there are no `area`, `rooms`, `year`, `mileage`, `brand`, `model`, or `color` columns on `Ad`, and the bot collects none of these. Adding such filters requires model migration, bot handler/state expansion, and new per-category attribute configuration.

### Data not yet collected by the bot (confirmed)
`area`, `rooms`, `year`, `mileage`, `brand`, `model`, `color`, `engine_volume`, `condition_grade`, and any other typed attribute — none are present in `AdCreateState` or persisted by `update_ad_and_moderate`.
