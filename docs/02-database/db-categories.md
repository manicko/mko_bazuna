---
id: db-categories
domain: database
tags:
  - categories
  - lookups
  - cache
  - moderation
related:
  - db-schema
  - db-enums
  - db-indexes
  - technical-specification
---

## Purpose

Document the runtime architecture of the **Category & Lookup subsystem** — how listing purposes,
listing features, and category-bound bindings are resolved for a given category; how the catalog
is loaded from a YAML manifest; and how resolution, tree-structure, and lookup caches are kept
consistent via signals.

The authoritative table/column definitions live in [db-schema.md](db-schema.md) and enum values
in [db-enums.md](db-enums.md). This doc covers the **runtime pipeline** (resolver, builder,
caching, signals) that the schema doc does not.

## Main Concepts

- **Config-driven catalog.** Purposes, features, and the category tree are declared in
  `categories/catalog/categories.yaml` and loaded by a transactional builder — not hard-coded.
- **Inherited resolution.** A category's purposes/features inherit from the nearest ancestor
  that defines them (nearest-explicit-ancestor-wins), with 5-minute cached results.
- **Multi-parent navigation.** `CategoryPath` provides alternative navigation routes while the
  canonical tree remains a single-rooted MPTT.
- **Cache invalidation via signals.** Structure, binding, and lookup changes invalidate caches
  automatically; lookup invalidation is best-effort (never fails the write transaction).

## Lookup reference data

`apps.lookups.models` — a universal reference-data system backing all discrete choice sets.

| Model | Role |
|---|---|
| `LookupGroup` | Named group (`code`, `name_i18n`, `is_system`, `sort_order`); system groups are admin-protected |
| `LookupItem` | Individual value (`slug` globally unique, `name_i18n`, `is_active`, `icon`, `color`); `get_name(locale)` falls back `locale → ru → slug` |

The two active groups (see [db-enums.md > LookupGroupCode](db-enums.md)):

| `LookupGroupCode` | Role |
|---|---|
| `LISTING_PURPOSE` | Listing purposes — single-select per ad (e.g. `sell`, `new`) |
| `LISTING_FEATURE` | Listing features — multi-select, AND-semantics (e.g. `urgent`, `premium`) |

`apps.lookups.services.cache_service.LookupCacheService` caches `get_all_groups()`
(`lookup:all_groups`, 1 h TTL, prefetched items) and `get_active_items(group_code)`
(`lookup:active_items:<code>`).

## Categories & bindings

`apps.categories.models`:

- **`Category`** — MPTT tree (`django-mptt>=0.18.0`, no denormalized path/level columns).
  Russian base name + `name_i18n` JSONB; `get_name(locale)` with Russian fallback.
- **`CategoryPath`** — multi-parent navigation (alternative parent routes). `is_automatic`
  marks system-created paths (e.g. price=0 → Charity).
- **`CategoryListingPurpose`** — binds a `LookupItem` (group=`LISTING_PURPOSE`) to a category,
  with `is_default`; unique on `(category, purpose)`.
- **`CategoryListingFeature`** — binds a `LookupItem` (group=`LISTING_FEATURE`) to a category;
  unique on `(category, feature)`.

These through-tables are the data source for the resolver. `Ad` references them via
`listing_purpose` (single FK) and `features` (M2M through `AdFeature` with `sort_order`).
`Ad.category_name` is a trigger-synced denormalization (see [db-schema.md](db-schema.md)).

The catalog manifest (`categories/catalog/categories.yaml`) declares the 9 listing purposes,
19 listing features, the multi-level category tree
(real-estate / transport / goods / animals / services-jobs / business / charity), and the
multi-parent `category_paths`.

## CategoryLookupResolver (inherited resolution)

`apps.categories.services.lookup_resolution.CategoryLookupResolver` resolves a category's
applicable purposes/features using **nearest-explicit-ancestor-wins**: it walks the MPTT
ancestor chain (`get_ancestors(include_self=True, ascending=True)`) and returns the bindings of
the closest ancestor that has them, issuing a single through-table query per resolution.

| Method | Behavior |
|---|---|
| `get_resolved_purposes(category)` / `get_resolved_features(category)` | Resolved bindings |
| `get_resolved_*_codes(...)` | Same, returning codes only |

**Caching:** results are memoized per category in the shared cache
(`lookup:resolved_purposes:<id>` / `lookup:resolved_features:<id>`, 300 s TTL).

**Invalidation:**
- `invalidate_category(category_id)` — clears the resolver cache for the category **and its
  descendants** (inherited resolutions may change).
- `invalidate_lookup_item(item_id)` — clears the resolver cache for any category bound to the
  item.

## Catalog builder (YAML manifest)

`apps.categories.catalog.builder.load_catalog(config_path, apps=None, rewrite_yaml=True) ->
{old_slug: new_slug}` loads the canonical catalog in **one transaction**, four phases:

1. **`_load_lookups`** — upsert `LookupGroup` + `LookupItem` rows.
2. **`_load_categories`** — build the MPTT tree level-by-level; supports `new_slug` renames
   (returned in the slug mapping) and `deferred` entries (skipped).
3. **`_load_bindings`** — populate purpose/feature overrides.
4. **`_load_category_paths`** — populate multi-parent paths, resolving renames.

When renames occur and `rewrite_yaml=True`, the manifest is rewritten in place (via `ruamel.yaml`,
preserving comments/order) so the YAML remains the source of truth.

CLI: `management.commands.load_catalog` (`--config`, `--no-rewrite`).

## Caching strategy

| Cache | Key pattern | TTL | Invalidated by |
|---|---|---|---|
| Tree version | `category:tree_version` (atomic counter) | — | Category / CategoryPath save+delete |
| Submenu fragment | `category:submenu:<version>:<slug>` | 300 s | tree-version bump |
| Resolver result | `lookup:resolved_<purposes\|features>:<id>` | 300 s | category/binding/lookup-item changes |
| Lookup group/item | `lookup:all_groups`, `lookup:active_items:<code>` | 3600 s | LookupGroup/LookupItem save+delete |

The tree version (`apps.categories.cache`) is an atomically-incremented counter
(`cache.incr` with a set-if-missing fallback); submenu HTML fragments are keyed on it, so a
structure change invalidates all cached submenus in one step. Lookup cache invalidation is
best-effort — it catches `redis.ConnectionInterrupted` / `redis.RedisError` and never fails the
write transaction.

## Signals

Signal handlers keep caches and tree state in sync (registered in each app's `apps.py` `ready()`):

- **`categories` app** — `post_save`/`post_delete` on `Category` & `CategoryPath` bump the tree
  version (invalidating all submenu fragments); on `CategoryListingPurpose` &
  `CategoryListingFeature` they call `invalidate_category(category_id)` (self + descendants);
  on `LookupItem` save (when `is_active` is in `update_fields`) they call
  `invalidate_lookup_item(item_id)`.
- **`lookups` app** — `post_save`/`post_delete` on `LookupGroup` & `LookupItem` call
  `LookupCacheService.invalidate_all()` (Redis `delete_pattern` when available, no-fail).

## Ad integration

- `Ad.listing_purpose` — FK to `LookupItem` (group=`LISTING_PURPOSE`); resolved via the resolver
  at publish time and referenced by the filter UI (single-select).
- `Ad.features` — M2M to `LookupItem` (group=`LISTING_FEATURE`) through `AdFeature` (with
  `sort_order`); an ad carries 0..N features, filtered with AND-semantics.
- Buyer filters (see [filter-ui.md](../01-spec/filter-ui.md)) resolve options through the
  resolver, so a category subtree shows only the features/purposes defined by the nearest
  explicit ancestor along the active navigation path.

## Related documents
- [db-schema.md — table definitions](db-schema.md)
- [db-enums.md — LookupGroupCode etc.](db-enums.md)
- [db-indexes.md — composite indexes on binding tables](db-indexes.md)
- [filter-ui.md — buyer filter UX](../01-spec/filter-ui.md)
- [CategoryLookupResolver source](../../src/backend/apps/categories/services/lookup_resolution.py)
