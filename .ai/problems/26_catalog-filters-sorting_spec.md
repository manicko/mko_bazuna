---
id: catalog-filters-sorting-spec
title: "Catalog Filters & Sorting — Specification"
topic: "filter matrix, sort matrix, category groups, MVP scope, technical approach"
domain: spec
tags: [filter, sort, catalog, mvp, mptt, fts, postgresql, htmx]
status: approved
confidence: HIGH
related:
  - .ai/problems/Decision_025.md
  - .ai/plans/25_currency-normalization_plan.md
  - .ai/research/26_filter-sorting-competitor-research.md
  - .ai/research/26_postgresql-filter-performance.md
  - .ai/research/26_codebase-audit-filters.md
  - docs/01-spec/filter-ui.md
  - docs/02-database/db-schema.md
  - docs/02-database/db-indexes.md
  - docs/02-database/db-enums.md
---

# Catalog Filters & Sorting — Specification

## Summary

This specification defines the catalog filtering and sorting system for the
Mko Bazuna classifieds board. Based on competitor research (Avito, OLX,
Craigslist, Facebook Marketplace), a codebase audit, and PostgreSQL 18
performance analysis, this spec extends the existing filter set to include
**`listing_purpose`** (single-select) and **`features`** (multi-select
checkboxes). The multi-currency price model (`price_amount` /
`price_normalized_eur`) is already implemented — price filtering and sorting
already use `price_normalized_eur`. Numeric attribute filters (area, rooms,
year, mileage, brand) are deferred — they require schema migration and bot UX
changes not available in the current data model.

> **Status:** Currency model is IMPLEMENTED. This spec covers the remaining
> work: adding `listing_purpose` and `features` as buyer-facing filters,
> their UI controls, seed data updates, indexes, and tests.

---

## 1. Business Context

### 1.1 Problem

Buyers need to narrow down a catalog of classified ads by structured criteria
(category, location, price, purpose, features) and sort results by relevance
or date. The current UI supports category, city, price, and four sort options.
This spec extends the filter set to include `listing_purpose` and `features`
(both already stored on the `Ad` model but not yet exposed as buyer filters),
while documenting the full filter matrix for future expansion.

### 1.2 Product Decisions (PO-confirmed)

| Decision | Value | Rationale |
|---|---|---|
| Filter scope | Add `listing_purpose` + `features` filters | Data already on Ad model; no schema migration needed |
| Default sort (no filters, no search) | `date_desc` | Newest-first for category browsing |
| Sort with text search or filters | Relevance first (`-rank`), then `date_desc` | Matches Avito/FB pattern; FTS produces a relevance score |
| Price input control | Text inputs (Min / Max) | Consistent with Avito, Craigslist, FB Marketplace |
| Price input currency | EUR-equivalent (per currency plan PO-04) | `price_normalized_eur` is the filter/sort column |
| Category tree depth | Collapsible tree (expand/collapse per group) | Matches existing main-menu pattern |
| Pagination | Django `Paginator` (OFFSET), page cap | Keyset pagination deferred to Phase 2 |
| Active filter chips | Chips + "Clear all" | Per existing `filter-ui.md` |

---

## 2. Data Model — Filterable Fields

**Source:** `src/backend/apps/ads/models.py`, audited in
`.ai/research/26_codebase-audit-filters.md` §1.

### 2.1 Currently Available Filter Dimensions

> **Note on currency model:** The multi-currency price model is **already
> implemented** (see `.ai/plans/25_currency-normalization_plan.md`, T-01..T-10
> all complete). The `Ad` model no longer has a bare `price` field. Instead it
> has `price_amount`, `price_currency`, and `price_normalized_eur`. All price
> filtering and sorting uses `price_normalized_eur` (EUR cross-currency value).
> Seed data defaults to EUR (`price_normalized_eur == price_amount`).

| Dimension | DB Column / Relation | Type | Multi-value? | Notes |
|---|---|---|---|---|
| Category subtree | `category_id` (FK → `categories.Category` MPTT) | FK | Single | Expanded via `get_descendants(include_self=True)` → `IN` list |
| City | `city_id` (FK → `locations.City`) | FK | Single | Exact slug match |
| Price min | `price_normalized_eur` (DecimalField, EUR) | Numeric | Single | `price_normalized_eur__gte=<int>` |
| Price max | `price_normalized_eur` (DecimalField, EUR) | Numeric | Single | `price_normalized_eur__lte=<int>` |
| Listing purpose | `listing_purpose_id` (FK → `lookups.LookupItem`, group `listing_purpose`) | FK | Single | 10 values: `sell`, `give-away`, `rent`, `rent-short`, `lost`, `found`, `offer-service`, `seek-service`, `job-offer`, `job-seek` |
| Features | `ad.features` (M2M → `lookups.LookupItem`, group `listing_feature`, through `AdFeature`) | M2M | Multi | 19 values: `new`, `used`, `delivery`, `pickup`, `negotiable`, `credit`, `exchange`, `installment`, `urgent`, `luxury`, `eco`, `handmade`, `branded`, `custom`, `warranty`, `packaging`, `import`, `local`, `smart-home` |
| Full-text search | `search_vector_ru` / `_bs` / `_en` (TSVECTOR, per-language GIN) | Text | Single | `q=<text>`, overridden to `-rank` sort when active |

### 2.2 Fields NOT Available (Deferred)

There are **no** numeric or typed attribute columns on the `Ad` model. The bot
ad-creation flow (§9 of the codebase audit) collects only:
`category`, `listing_purpose`, `features`, `city`, `title`, `description`,
`price_amount`/`price_currency`, and `photos`. There is no `area`, `rooms`,
`year`, `mileage`, `brand`, `model`, `color`, or similar structured attribute
field.

**Implication:** Any future attribute-based filtering requires both a model
migration (new columns or an EAV/attribute system) and bot handler expansion.
This is explicitly out of scope for the current phase.

---

## 3. Filter Matrix

### 3.1 MVP Filters (Implemented)

| # | Dimension | Control | Source | URL Param | Multi-value? | Filter Logic | Index |
|---|---|---|---|---|---|---|---|
| F1 | Category subtree | Collapsible tree | `Category` MPTT | `category=<slug>` | Single | `category_id IN (get_descendants(include_self))` | `IX_ads_pub_listing` (category_id) |
| F2 | City | Select / chip | `City.slug` | `city=<slug>` | Single | `city_id = <id>` (exact) | `IX_ads_pub_listing` (city_id) |
| F3 | Price range | Dual text inputs (EUR) | `Ad.price_normalized_eur` | `min_price=<int>`, `max_price=<int>` | Single each | `price_normalized_eur__gte`, `price_normalized_eur__lte` | `IX_ads_price_normalized_eur` (exists) |
| F4 | Listing purpose | Single-select dropdown/radio | `Ad.listing_purpose_id` | `listing_purpose=<slug>` | No | `listing_purpose__slug=<slug>` | None yet — see §6.2 |
| F5 | Features | Multi-checkbox | `Ad.features` (M2M) | `features=<slug>&features=<slug>` | Yes | Chained `.filter(features__id=fid)` (AND semantics: ad must have ALL selected features) | `IX_ad_features_feature_id` (to create) |
| F6 | Text search | Text input | `search_vector_<locale>` | `q=<text>` | Single | FTS `@@` query, per-language | `IX_ads_search_gin_ru/bs/en` |

### 3.2 Deferred Filters (Future)

| Dimension | Reason for deferral | Prerequisites |
|---|---|---|
| Area (m²) | Not collected by bot; no model column | Add `area` field to `Ad` + bot handler + `AdCreateState.AREA` |
| Rooms | Not collected by bot; no model column | Add `rooms` field to `Ad` + bot handler |
| Year | Not collected by bot; no model column | Add `year` field to `Ad` + bot handler |
| Mileage | Not collected by bot; no model column | Add `mileage` field to `Ad` + bot handler |
| Brand / Model | Not collected by bot; no model columns | Add `brand`/`model` fields or M2M to brand taxonomy |
| Condition grade | Not collected by bot; could use existing `features` `new`/`used` | Already covered by `features` filter (F5) |
| Color | Not collected by bot; no model column | Add `color` field or FK to color lookup |
| Date posted range | Not requested by PO | Add `created_at` range filter params |

### 3.3 Category-Specific Filter Availability

Per-category overrides for `listing_purpose` and `features` are defined in
`src/backend/apps/categories/catalog/categories.yaml` via `listing_purpose_override`
and `listing_feature_override`. The buyer filter should constrain the
`listing_purpose` dropdown and `features` checkbox list to the **resolved
overrides of the currently selected category**, using the existing
`CategoryListingPurpose` and `CategoryListingFeature` through models.

| Category | Resolved listing_purpose options | Resolved listing_feature options |
|---|---|---|
| Real Estate | `sell`, `rent`, `rent-short` | *(from full set, as constrained by YAML)* |
| Transport | `sell`, `rent` | *(from full set)* |
| Goods | `sell` | *(from full set)* |
| Animals | `sell`, `give-away`, `lost`, `found` | *(from full set)* |
| Services/Jobs | `job-seek`, `job-offer`, `seek-service`, `offer-service` | *(from full set)* |
| Business | `sell`, `rent` | *(from full set)* |
| Charity | `give-away` | none (`listing_feature_override: []`) |

> **Note:** The exact feature/purpose sets per category are configurable in
> `categories.yaml` and resolved at runtime by
> `CategoryListingPurpose` / `CategoryListingFeature` through models
> (see `.ai/research/26_codebase-audit-filters.md` §4). The buyer filter UI
> should query these to determine which checkboxes/dropdown options to render,
> not hardcode the list.

---

## 4. Sorting Matrix

### 4.1 MVP Sort Options

| # | Sort Key | URL Value | DB Field | Direction | Applies When |
|---|---|---|---|---|---|
| S1 | Newest first | `date_desc` | `published_at` | DESC | Default when no search query and no filters |
| S2 | Oldest first | `date_asc` | `published_at` | ASC | Explicit sort selection |
| S3 | Price low → high | `price_asc` | `price_normalized_eur` | ASC | Explicit sort selection (NULLs last) |
| S4 | Price high → low | `price_desc` | `price_normalized_eur` | DESC | Explicit sort selection (NULLs last) |
| S5 | Relevance | *(implicit)* | SearchRank | DESC | When `q` param is present |

### 4.2 Sort Default Logic

```
IF request.GET.q is truthy AND non-empty:
    sort_by = SearchRank(search_vector_<locale>, SearchQuery(q, websearch))  DESC
    secondary_sort = published_at DESC, id DESC  (tiebreaker)
ELSE:
    IF sort param is missing or unrecognized:
        sort_by = published_at DESC  (S1, date_desc)
    ELSE:
        map sort param → S2/S3/S4
```

### 4.3 Sort + Filter Interaction

- When a text search query (`q`) is active, sort is **always overridden** to
  relevance (`-rank`), regardless of the `sort` URL param. The `sort` param
  is preserved in pagination URLs (§7) so the user's selection is not lost
  when they clear the search box.
- When no search query is present, the `sort` param controls the ordering
  directly (date or price).
- Sort is **not** category-dependent — all four options apply to every category.

### 4.4 NULL Handling for Price Sort

`Ad.price_normalized_eur` is nullable (ads with `skip` price during creation
have `price_amount IS NULL` → `price_normalized_eur IS NULL`).
- `price_asc`: NULLs sort **last** (PostgreSQL default is NULLS FIRST for ASC;
  the view must add `NULLS LAST` explicitly).
- `price_desc`: NULLs sort **last** (use `NULLS LAST` on DESC).
- Price range filter (`min_price`/`max_price`): rows with
  `price_normalized_eur IS NULL` are **excluded** (three-valued logic:
  `NULL >= 5000` → NULL → not in result set).

---

## 5. URL Specification

### 5.1 URL Format

```
/search/?q=<text>&category=<cat_slug>&city=<city_slug>&min_price=<int>&max_price=<int>&listing_purpose=<purpose_slug>&features=<slug>&features=<slug>&sort=<sort_value>&page=<n>
```

For category-page routing (non-search):

```
/category/<cat_slug>/?city=<city_slug>&min_price=<int>&max_price=<int>&listing_purpose=<purpose_slug>&features=<slug>&features=<slug>&sort=<sort_value>&page=<n>
```

### 5.2 Query Parameter Reference

| Param | Values | Multi-value? | Default | Required? |
|---|---|---|---|---|
| `q` | Free text | No | (empty) | No |
| `category` | Category slug | No | (none — all categories) | No |
| `city` | City slug | No | `request.preferred_city` (see §5.4) | No |
| `min_price` | Integer (EUR-equivalent) | No | (none) | No |
| `max_price` | Integer (EUR-equivalent) | No | (none) | No |
| `listing_purpose` | Purpose slug | No | (none) | No |
| `features` | Feature slug | Yes (repeatable) | (none) | No |
| `sort` | `date_desc` \| `date_asc` \| `price_asc` \| `price_desc` | No | `date_desc` | No |
| `page` | Integer ≥ 1 | No | 1 | No |

### 5.3 URL Encoding Rules

- All params are URL-encoded (e.g. spaces in `q` → `+` or `%20`).
- Multiple `features` values are encoded as repeated params:
  `?features=new&features=delivery` (not comma-joined, per HTML form convention).
- The URL must be **fully reproducible**: every active filter is reflected in
  the query string so the page can be bookmarked, shared, or reloaded.
- Invalid `sort` values silently fall back to `date_desc` (no error page).
- Invalid `min_price`/`max_price` values are silently ignored (ValueError
  caught, per existing code pattern).
- Invalid `category`/`city`/`listing_purpose`/`features` slugs: unrecognized
  category slug → no category filter applied (show all); unrecognized city →
  did-you-mean suggestion via `difflib.get_close_matches`.

### 5.4 City Default & Precedence

The city filter **defaults to the buyer's preferred city**:
- Authenticated users: `User.preferred_city`.
- Guests: `preferred_city` cookie (consent-gated).
- If neither is available: "All cities" (country-wide, no `city_id` filter).

An explicit `city` value in the URL **always overrides** the default.

### 5.5 HTMX Compatibility

The filter form submits via `hx-get` targeting the results container, updating
the URL via `hx-push-url="true"` so the browser back/forward buttons work.
Pagination links use `hx-get` with the same target. The URL is always
synchronized to reflect the current filter state.

---

## 6. Technical Approach

### 6.1 Filter Pipeline (View Layer)

The filter chain is applied in both `listings()` (`src/backend/apps/ads/views/listings.py`)
and `search()` (`src/backend/apps/search/views/search.py`). The order of
application:

```python
# 1. Base queryset
ads = Ad.objects.filter(status=AdStatus.PUBLISHED)
    .select_related("category", "city", "user")
    .prefetch_related("user__trust_score")

# 2. Category subtree (F1)
descendant_ids = category.get_descendants(include_self=True).values_list("id", flat=True)
ads = ads.filter(category_id__in=descendant_ids)

# 3. City (F2)
ads = ads.filter(city_id=city.id)

# 4. Price range (F3) — on price_normalized_eur (EUR-equivalent)
if min_price: ads = ads.filter(price_normalized_eur__gte=int(min_price))
if max_price: ads = ads.filter(price_normalized_eur__lte=int(max_price))

# 5. Listing purpose (F4) — NEW
if listing_purpose_slug:
    ads = ads.filter(listing_purpose__slug=listing_purpose_slug)

# 6. Features (F5) — NEW — AND semantics chained
for fid in feature_ids:
    ads = ads.filter(features__id=fid)

# 7. Full-text search (F6) — overrides sort
if q:
    ads = ads.annotate(rank=SearchRank(...)).filter(search_vector_<locale>=(...)).order_by("-rank", "-published_at", "-id")
else:
    ads = ads.order_by(<sort_field>)

# 8. Favorites annotation
ads = annotate_favorites(ads, user_id)

# 9. Pagination
paginator = Paginator(ads, 24)
```

**New code needed:** Steps 4, 5, and 6 (F4, F5). Step 4 is a repoint from
`price` → `price_normalized_eur` (already done by the currency plan for the
main filter/sort path, but verify the `AdSort` enum's `order_by` targets).

> **Verified:** Per the researcher audit, T-06 (currency plan) has already
> re-pointed filter/sort to `price_normalized_eur` in both views. The sort
> `order_by("price_normalized_eur")` / `order_by("-price_normalized_eur")`
> is already in place. Only F4 and F5 (listing_purpose, features) remain
> unimplemented.

### 6.2 Database Indexes

Per `.ai/research/26_postgresql-filter-performance.md` §8, the index situation:

| # | Index | Status | Rationale |
|---|---|---|---|
| I1 | `IX_ads_pub_listing` (existing) | ✅ Deployed | Covers category + city + default date sort (index-only scan) |
| I2 | `IX_ads_price_normalized_eur` (existing) | ✅ Deployed | Partial index on `price_normalized_eur WHERE IS NOT NULL` — already created by the currency migration (migration 0010) |
| I3 | `IX_ad_features_feature_id` — `CREATE INDEX ON ad_features (feature_id)` | ❌ To create | Enables efficient reverse M2M lookup for feature filtering (F5) |
| I4 | `IX_ads_pub_purpose` — `CREATE INDEX ON ads (listing_purpose_id) WHERE status='PUBLISHED'` | ❌ To create | Enables efficient `listing_purpose` filtering (F4); scalar FK → B-tree is correct |

**Index I2 (price):** The currency plan's T-02 migration already created
`IX_ads_price_normalized_eur` — a partial B-tree index on `price_normalized_eur`.
No action needed.

**Index I3 (features):** The `ad_features` M2M through table has only a unique
constraint on `(ad_id, feature_id)`. A reverse lookup (which ads have feature X)
scans the full unique index. Add a separate B-tree index on `feature_id`.

**Index I4 (listing_purpose):** `listing_purpose_id` is a scalar FK with no
existing index. Add a partial B-tree index scoped to PUBLISHED ads.

**Verification:** Use Django 5.2's `qs.explain(analyze=True, buffers=True)` on a
500k-row test database to confirm `Index Scan` (not `Seq Scan`) after adding
I3/I4.

### 6.3 Filter Option Resolution

The `listing_purpose` dropdown options and `features` checkbox options should be
constrained to the **currently selected category's** resolved overrides:

```python
# Using the existing CategoryLookupResolver (static methods, cached)
from apps.categories.services.lookup_resolution import CategoryLookupResolver

resolved_purposes = CategoryLookupResolver.get_resolved_purposes(category)
resolved_features = CategoryLookupResolver.get_resolved_features(category)
```

This uses the same resolution path as the bot's ad-creation flow. The resolver
uses MPTT ancestor-walk (nearest-explicit-ancestor-wins) with a 300-second cache.
If no category is selected, show the full set of active lookup items for each
group (query `LookupItem.objects.filter(group__code=..., is_active=True)`).

### 6.4 Pagination

Per the PO decision (Q5 → A), **keep Django `Paginator` (OFFSET)** with a
page cap. Keyset pagination is deferred to Phase 2.

- **Page size:** 24 results per page (current).
- **Max page depth:** Capped at page 500 (12,000 results). Beyond that, show
  a message: "Too many results — try narrowing your filters."
- **Page param:** `page=<n>`, clamped to `[1, max_page]`.

### 6.5 Search + Filter Interaction

Search query (`q`) combines with all other filters via AND logic:
- The text query filters by FTS match on `title`/`description`.
- All other filters (category, city, price, purpose, features) are applied
  before the FTS annotation.
- Sort is overridden to `-rank` (relevance) when `q` is present.
- The `sort` param is **preserved** in pagination URLs even when FTS is active,
  so clearing the search query restores the user's sort preference.

---

## 7. UI Integration

### 7.1 Desktop Layout

- **Sticky sidebar** (25% width) containing all filter controls.
- **Content area** (75% width) showing results + sort selector + active filter
  chips + pagination.
- Category tree is collapsible (expand/collapse per top-level group).

### 7.2 Mobile Layout

- **Slide-up drawer** (full-screen modal) triggered by a "Filters" button.
- Sort selector is a dropdown/button above the results.
- Category tree uses the same collapsible pattern.

### 7.3 Active Filter Chips

Render chips above results for each active filter, matching the existing
`filter-ui.md` patterns:

| Filter | Chip Label | Remove Action |
|---|---|---|
| Category | "Category: <name>" | `?category=` removed |
| City | "City: <name>" | `?city=` removed |
| Price | "Price: <min>–<max> EUR" | `min_price=` + `max_price=` removed |
| Listing purpose | "Purpose: <name>" | `listing_purpose=` removed |
| Features | One chip per feature: "Feature: <name>" | Each removable individually |
| Search | "Search: <q>" | `q=` removed |

**"Clear all" link** resets all filters and returns to page 1.

### 7.4 Sort Selector

Render as a dropdown/button above results:

```html
<select name="sort" class="px-3 py-2 border rounded">
    <option value="date_desc">Newest first</option>
    <option value="date_asc">Oldest first</option>
    <option value="price_asc">Price: low to high</option>
    <option value="price_desc">Price: high to low</option>
</select>
```

When `q` is present, the sort selector is hidden (relevance sort is implied)
but the `sort` param is preserved in subsequent URLs.

---

## 8. Assumptions

1. The multi-currency price model is **already implemented** (see
   `.ai/plans/25_currency-normalization_plan.md`). `Ad.price` no longer exists;
   `price_amount`/`price_currency`/`price_normalized_eur` are in place.
2. Seeds default to EUR (`price_normalized_eur == price_amount`), so price
   filtering/sorting works end-to-end on seed data.
3. The `listing_purpose` and `features` lookup items are already populated in
   the database (seeded via the existing seed workflow — see
   `docs/ops/seed-workflow.md`).
4. Per-category overrides in `categories.yaml` are correctly synced to the
   `CategoryListingPurpose` and `CategoryListingFeature` through models,
   and `CategoryLookupResolver` resolves them correctly.
5. The city default logic (`request.preferred_city`) is already implemented
   (per `filter-ui.md` §Location-Based Filtering).
6. The existing `filter-ui.md` HTML/CSS patterns are the baseline; this spec
   extends them with `listing_purpose` and `features` controls.
7. `select_related("user")` is already present in `search.py` (verified by
   researcher audit — the N+1 gap is closed).
8. At 500k ads, PostgreSQL EXPLAIN verification will be run before adding
   new indexes (per `.ai/research/26_postgresql-filter-performance.md` §8 P0).

---

## 9. Risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Features M2M filter causes N+1 queries | Low | Medium | Chained `.filter(features__id=fid)` generates EXISTS subqueries, not N+1; add `IX_ad_features_feature_id` index |
| `listing_purpose` filter perf at scale | Medium | Low | Add `IX_ads_pub_purpose` partial index; verify with EXPLAIN |
| NULL price sorts incorrectly | Low | Low | Use `NULLS LAST` on `price_normalized_eur` sorts |
| Keyset pagination migration pain later | Medium | Medium | Keep OFFSET for now; keyset is an additive change to the feed view |
| Seed data doesn't populate `listing_purpose`/`features` | High | High | Tasks T10/T11 must update seed generator + service before testing |
| Bot doesn't collect attributes → filter set feels thin | Medium | Low | This is a known Phase-1 constraint; document the path to attribute filters |

---

## 10. Dependencies

| Dependency | Status | Notes |
|---|---|---|
| LookupItem data seeded (listing_purpose, listing_feature) | Existing | `docs/ops/seed-workflow.md` |
| Category overrides in `categories.yaml` | Existing | Already drives bot flow |
| Multi-currency model (`price_amount`/`price_currency`/`price_normalized_eur`) | ✅ Implemented | Currency plan T-01..T-10 complete; migration 0010 |
| `IX_ads_pub_listing` index | ✅ Existing | Already deployed |
| `IX_ads_price_normalized_eur` index | ✅ Existing | Created by currency migration T-02 |
| `select_related("user")` in `search.py` | ✅ Existing | Already fixed by currency plan |
| New DB migrations for index I3 (`ad_features.feature_id`) | ❌ To create | Required for features filter (F5) |
| New DB migration for index I4 (`listing_purpose_id`) | ❌ To create | Required for listing_purpose filter (F4) |
| Seed generator populates `listing_purpose` + `features` | ❌ To create | Tasks T10/T11 — required for test data |
| Category tree cache (Redis) | Existing infra | `docs/99-agent/architecture.md` §Cache Backend |

---

## 11. Implementation Tasks

| # | Task | Component | Effort |
|---|---|---|---|
| T1 | Add `IX_ad_features_feature_id` migration | DB / Django migration | Low |
| T2 | Add `IX_ads_pub_purpose` migration | DB / Django migration | Low |
| T3 | Implement `listing_purpose` filter in `listings()` and `search()` | Views | Medium |
| T4 | Implement `features` filter in `listings()` and `search()` | Views | Medium |
| T5 | Implement category-constrained purpose/feature filter options | Views / Lookup resolution | Medium |
| T6 | Update sort logic: relevance-first when `q` active | Views | Small |
| T7 | Add `listing_purpose` dropdown + `features` checkboxes to filter form | Templates | Medium |
| T8 | Add filter chips for purpose + features (including per-feature chips) | Templates | Small |
| T9 | Preserve `sort` param in pagination URLs when FTS active | Templates / URL building | Small |
| T10 | Update seed generator: populate `listing_purpose` from per-category overrides | Seed generator (`generators/ads.py`) | Medium |
| T11 | Update seed service: populate `features` M2M after `bulk_create` | Seed service (`seed_service.py`) | Medium |
| T12 | Add test assertions for filter behavior on seed data | Test suite | Medium |

> **Already completed by the currency normalization plan:**
> - `Ad.price` → `price_amount`/`price_currency`/`price_normalized_eur` (T-02)
> - `IX_ads_price_normalized_eur` index (T-02)
> - Price filter/sort repointed to `price_normalized_eur` in both views (T-06)
> - `format_price` template filter + Python wrapper (T-11)
> - Seed generator produces EUR prices (T-10)
> - `select_related("user")` fix in `search.py` (researcher audit)

### 11.1 Seed Data Coverage for Test Validation

The current seed generator (`src/backend/apps/seed/generators/ads.py`) sets
`price_amount`, `price_currency` (EUR), `price_normalized_eur`, `category`,
`city`, `status`, and `source` on each `Ad` instance, but **does not** set
`listing_purpose_id` or `features`. This means:

- **Existing filters (category, city, price, sort, search)** are testable on
  current seed data. ✅
- **New MVP filters (listing_purpose F4, features F5)** will return zero
  results against the current seed data until the seed generator is updated.

**Tasks T10 and T11** must populate `listing_purpose` and `features` on each
seeded `Ad` using the per-category overrides from `categories.yaml` (the same
resolution path used by the bot's ad-creation flow via `CategoryLookupResolver`).
Without these, the new filters cannot be validated in a test environment.

**Implementation approach for T10 (listing_purpose):**
```python
# In AdGenerator.generate(), after category selection:
from apps.categories.services.lookup_resolution import CategoryLookupResolver
resolved_purposes = CategoryLookupResolver.get_resolved_purposes(category)
# resolved_purposes returns list[LookupItem]
if resolved_purposes:
    ad.listing_purpose = self._rng.choice(resolved_purposes)
```

**Implementation approach for T11 (features M2M):**
```python
# In SeedService.run(), after Ad.objects.bulk_create() and db_ads fetched:
# (M2M cannot be set via bulk_create — done in post-creation loop)
from apps.categories.services.lookup_resolution import CategoryLookupResolver
for ad in db_ads:
    resolved_features = CategoryLookupResolver.get_resolved_features(ad.category)
    # resolved_features returns list[LookupItem]
    if resolved_features:
        sample = self._rng.sample(
            resolved_features,
            k=self._rng.randint(1, min(3, len(resolved_features)))
        )
        ad.features.set(sample)
```

> **Note:** `Ad.features` is an M2M, so it cannot be set via `bulk_create`.
> The seed service must set M2M relations in a post-`bulk_create` step (similar
> to how `AdImage` is created in Step 5 of `seed_service.py`).
> The `_rng` instance is available on `AdGenerator` (inherited from
> `BaseGenerator`); `SeedService` must share the same RNG instance or create
> its own seeded RNG for deterministic test data.

**Implementation approach for T12 (test assertions):**
```python
# In seed/tests/test_seed.py — add assertions:
# 1. At least one ad has listing_purpose set
# 2. At least one ad has features set (M2M populated)
# 3. Filter by a specific purpose returns >0 results
# 4. Filter by a specific feature returns >0 results
```

### 11.2 Test Validation Matrix

| Filter / Sort | Testable on current seed data? | Requires seed update? |
|---|---|---|
| Category subtree (F1) | ✅ Yes | No |
| City (F2) | ✅ Yes | No |
| Price range (F3) | ✅ Yes (seed sets `price_normalized_eur`) | No |
| Listing purpose (F4) | ❌ No (`listing_purpose_id` not set on seed ads) | **Yes (T10)** |
| Features (F5) | ❌ No (`features` M2M not populated on seed ads) | **Yes (T11)** |
| Text search (F6) | ✅ Yes (title/description are seeded) | No |
| Sort: date_desc / date_asc | ✅ Yes (`published_at` set on PUBLISHED ads) | No |
| Sort: price_asc / price_desc | ✅ Yes (`price_normalized_eur` set, EUR) | No |
| Sort: relevance (with `q`) | ✅ Yes | No |
| Active filter chips | ✅ Partially (chips for F1/F2/F3/F6 work; F4/F5 chips untested until T10/T11) | **Yes (T10, T11)** |

---

## 12. Open Questions

All open questions were resolved by PO decisions during specification. The
following items are deferred to future phases:

1. **Numeric attribute filters** (area, rooms, year, mileage, brand) — requires
   schema migration + bot UX changes. No timeline defined.
2. **Keyset pagination** — deferred to Phase 2 per PO decision.
3. **Faceted counts** (count of ads per category/feature within filtered results)
   — deferred; would require additional queries per the CTE-over-filtered-set
   pattern from the performance research.
4. **Dynamic dependent filters** (e.g., "make depends on category") — no
   cascading filter dependencies exist in the current data model. The only
   category-dependent dimension is the purpose/feature option set (already
   handled via `categories.yaml` overrides).
