---
id: discrepancies-plan25-26
domain: audit
tags:
  - documentation
  - discrepancies
  - plans-25-26
related:
  - 18_doc-update-discrepancies-plan17-24
---

# Discrepancies: Plans 25–26 vs. Current Documentation

## Context

This report captures deviations between plans/specs
(`25_currency-normalization`, `25_main-menu-navigation`, `26_catalog-filters-sorting`) and the
**current documentation**, identified during the documentation-update task. The code implements all
significant functionality described by these plans (verified via researcher agents); the gaps below
are places where the plans' own documentation-update tasks (e.g. currency plan T-15, filter plan
doc references) were not completed, leaving docs stale or incomplete relative to the implemented
behavior. These directly drive the documentation updates in this pass.

Deviations that do **not** change how the implemented functionality is documented are omitted.
Excluded-by-design: plan 22 seed-coverage (dev/ops tooling, `docs/ops/seed-workflow.md` already
current), plan 22 breadcrumb fix (bug-fix only), plan 25 main-menu navigation redesign (minor UI
refinement — template/JS only, no new capability or user workflow).

---

## 1. `db-indexes.md` is stale vs. multi-currency + catalog-filter indexes

- **Planned:** Currency plan (MR-06) specifies an index on `price_normalized_eur`; filter plan
  (I3, I4) specifies `IX_ad_features_feature_id` and `IX_ads_pub_purpose`. Currency plan T-15 and
  filter plan both expect index docs refreshed.
- **Implemented:** `apps/ads/models.py` `Ad.Meta.indexes` contains
  `IX_ads_price_normalized_eur` (partial B-tree on `price_normalized_eur`);
  `apps/ads/models.py` also has `IX_ads_pub_purpose` (partial, `WHERE status='PUBLISHED'`) in
  `Ad.Meta.indexes`; `apps/ads/models.py` `AdFeature.Meta.indexes` contains
  `IX_ad_features_feature_id`. Migration `0010_ad_currency_price_fields.py` and
  `0011_catalog_filter_indexes.py` create them.
- **Doc state:** `docs/02-database/db-indexes.md` line 42 states "`price` has no index"; the
  `ad_features` section (lines 185–189) states "No additional indexes needed — M2M lookups go
  through Ad.features"; `IX_ads_pub_purpose` and `IX_ad_features_feature_id` and
  `IX_ads_price_normalized_eur` are absent from the file.
- **Assessment:** Concrete doc-vs-code contradiction. The "no price index" claim is now false
  (the column is `price_normalized_eur`, indexed). The two filter indexes are omitted entirely.
- **Documentation impact:** Add the three indexes to `db-indexes.md`; replace the stale
  "`price` has no index" line with correct guidance referencing `price_normalized_eur` and the
  new filter indexes.

## 2. `spec-index.md` does not list multi-currency or catalog filters as implemented

- **Planned:** Currency plan T-15 and filter plan both require `spec-index.md` to reflect
  implemented features in the Phase 2 table.
- **Implemented:** Multi-currency price model (`apps/currencies`, `PriceNormalizer`,
  `recompute_normalized_prices`); catalog filter dimensions `listing_purpose` (F4) and `features`
  (F5) with AND semantics and category-constrained option resolution.
- **Doc state:** `docs/01-spec/spec-index.md` Phase 2 Features table (lines 160–174) contains no
  "Multi-Currency" row and no "Catalog Filters" row. No `currency` or `listing_purpose` keyword.
  The existing "Filter UI" row describes only category/city/price.
- **Assessment:** The agent-reference summary understates the implemented surface.
- **Documentation impact:** Add rows for Multi-Currency Price Model and Catalog Filters
  (listing_purpose + features) to the Phase 2 table with key components and pointer to
  `db-schema.md`/`filter-ui.md`/`search-patterns.md`.

## 3. `filter-ui.md` omits the `listing_purpose` + `features` filter dimensions

- **Planned:** Filter plan T-08/T-09 specify a purpose dropdown, feature checkboxes, purpose/feature
  chips, clear-all, and pagination URL preservation of `listing_purpose`/`features`.
- **Implemented:** `templates/ads/partials/filter_form.html` renders a `listing_purpose` `<select>`
  and `features` checkboxes via HTMX (`hx-get` to `#ad-list`, `hx-push-url="true"`);
  `templates/ads/partials/ad_list.html` renders purpose/feature chips (removable individually), a
  clear-all link, and pagination links carrying `listing_purpose` + repeated `features` params.
  Both `listings()` and `search()` apply the filters and expose `current_listing_purpose` /
  `current_features` / `resolved_purposes` / `resolved_features` in context.
- **Doc state:** `docs/01-spec/filter-ui.md` Filter Groups table (lines 42–47) lists only
  Category, City, Price Range, Condition. No `listing_purpose` or `features` controls, chips, or
  pagination-URL preservation are described.
- **Assessment:** Significant new buyer filter dimensions undocumented.
- **Documentation impact:** Add sections for the listing-purpose dropdown, features checkboxes
  (AND semantics), purpose/feature chips with removal, clear-all, and URL parameter preservation
  in pagination.

## 4. `search-patterns.md` does not name `price_normalized_eur` or the new filters

- **Planned:** Currency plan and filter plan expect sort/filter docs to reference the normalized
  EUR column and the new dimensions.
- **Implemented:** `AdSort` sorts on `F("price_normalized_eur").asc/desc(nulls_last=True)` in
  both `listings()` and `search()`; FTS branch orders by `-rank, -published_at, -id`; both views
  filter on `listing_purpose__slug` and `features__slug`.
- **Doc state:** `docs/01-spec/search-patterns.md` AdSort docs (lines 161–187) describe sort
  generically ("price (low/high)") without naming `price_normalized_eur`, `NULLS LAST`, or the
  relevance tiebreaker; no mention of `listing_purpose`/`features` as additional filters.
- **Assessment:** Sort semantics (NULL placement, tiebreaker, normalized field) and the new filter
  dimensions are not in the buyer-facing search spec.
- **Documentation impact:** Name `price_normalized_eur` in the sort section, document `NULLS LAST`
  for price and the `-published_at, -id` relevance tiebreaker; add a short subsection on the
  additional `listing_purpose` / `features` filters and their AND semantics.

## 5. `architecture.md` omits the currencies subsystem

- **Planned:** Currency plan T-15 expects architecture docs to reflect the `apps/currencies`
  subsystem (`CurrencyCode`, `ExchangeRate`, `PriceNormalizer`, `recompute_normalized_prices`).
- **Implemented:** `apps/currencies/` app (`enums.py` `CurrencyCode`, `models.py` `ExchangeRate`,
  `services/price_normalizer.py`, `management/commands/recompute_normalized_prices.py`);
  `AdvisoryLockId.RECOMPUTE_NORMALIZED_PRICES = 12` in `apps/core/enums.py`; wired into both web
  and bot processes via the shared DB.
- **Doc state:** `docs/99-agent/architecture.md` (Main Concepts, line 20–22) mentions two-process,
  search, and migrations only — there is no mention of a currencies app, price normalization, or
  the recompute command. `db-schema.md` lines 247–265 document the schema, but
  `architecture.md` lacks an architectural reference to the subsystem.
- **Assessment:** A new domain subsystem (currency vocabulary + normalization + batch recompute)
  is implemented but absent from the architecture overview.
- **Documentation impact:** Add a brief currencies/normalization entry to `architecture.md` Main
  Concepts with cross-links to `db-schema.md` and the recompute command, noting the two-process
  shared-DB cache semantics.

## 6. `STRUCT.md` is structurally stale

- **Planned:** N/A (project hygiene).
- **Implemented:** `apps/cabinet/` and `apps/currencies/` apps exist in `src/backend/apps/`;
  `urls.py.bak` is a stale backup artifact, not a live module.
- **Doc state:** `docs/STRUCT.md` line 16 lists `urls.py.bak` and omits `cabinet/` and
  `currencies/` (and does not enumerate `currencies`).
- **Assessment:** Stale source-tree reference; omits two real apps including the new
  `currencies` domain.
- **Documentation impact:** Remove `urls.py.bak`; add `cabinet/` and `currencies/` to the apps
  tree.
