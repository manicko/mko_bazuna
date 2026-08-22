---
id: postgresql-filter-performance
title: "PostgreSQL Filter & Sort Performance at Scale — Mko Bazuna Design Reference"
topic: "PostgreSQL indexing, MPTT, FTS, GIN, keyset pagination, Django ORM for 500k-row catalog"
domain: research
tags:
  - database
  - indexes
  - postgresql
  - performance
  - search
  - pagination
  - orm
status: draft
confidence: HIGH
last_updated: 2026-08-22
related:
  - .ai/research/26_codebase-audit-filters.md
  - docs/02-database/db-indexes.md
  - docs/02-database/db-schema.md
  - docs/01-spec/technical-specification.md
---

# PostgreSQL Filter & Sort Performance at Scale — Design Reference

Research-backed analysis of PostgreSQL 18 + Django 5.2 indexing and query
strategies for the Mko Bazuna catalog, grounded in the project's actual schema
(`ads`, `categories`/MPTT, `ad_features`, `lookup_items`). Scale target:
**up to 500k ads** (see `docs/01-spec/technical-specification.md` §Scale targets).

All recommendations are tied to the **actual indexes and query chains** already
in the codebase (see `26_codebase-audit-filters.md` for the filter chain
walk-through). Each section ends with a **Concrete Recommendation** box.

---

## 0. Project Context — The Schema & Current Query Paths

**Stack:** PostgreSQL 18 (PG18), Django 5.2.16, psycopg 3.2, django-mptt 0.18.0,
aiogram 3.x, HTMX MPA. Web gunicorn (sync WSGI) + bot (aiogram) share one DB.

### Key facts (verified from source)

| Table / Field | Type | Current Index? | Notes |
|---|---|---|---|
| `ads.status` | StrEnum | ✅ in `IX_ads_pub_listing` (partial =PUBLISHED) + sweep partials | ~99 % of public reads are PUBLISHED |
| `ads.category_id` | FK → categories | ✅ 2nd col of `IX_ads_pub_listing` | Subtree filter via MPTT `get_descendants` → Python `IN` list |
| `ads.city_id` | FK → cities | ✅ 3rd col of `IX_ads_pub_listing` | Exact slug match, single value |
| `ads.price` | PositiveInt (BAM) | ❌ **none** | Range filter `price__gte`/`price__lte`; range sort `price_asc`/`_desc` |
| `ads.listing_purpose_id` | FK → lookup_items | ❌ none | Not yet a filter dimension; ready to enable |
| `ads.features` (M2M) | ad_features join | ❌ no idx on `feature_id` alone | Unique `(ad, feature)` covers ad→feature; reverse lookup un-indexed |
| `ads.search_vector_ru/bs/en` | TSVECTOR | ✅ GIN per language | FTS on title + description + category_name |
| `ads.published_at` | DateTime | ✅ 4th col of `IX_ads_pub_listing` (-desc) | Default sort = newest-first |
| `ads.id` | BigAuto | ✅ PK | Natural tiebreaker for keyset pagination |

### Current query chains (`ads/views/listings.py`, `search/views/search.py`)

```
listings():
  1. filter(status=PUBLISHED).select_related(cat,city,user).prefetch_related(user__trust_score)
  2. category subtree → category.get_descendants(include_self=True).values_list("id", flat=True)
     → filter(category_id__in=[...IDs...])      ← IN-list (evaluated in Python)
  3. city (exact)      → filter(city_id=city.id)
  4. price range      → filter(price__gte=...); filter(price__lte=...)
  5. sort (4-way)     → order_by(-published_at | published_at | price | -price)
  6. annotate_favorites → .annotate(is_favorited=Exists(subquery))
  7. Paginator(24)    → LIMIT/OFFSET
```

```
search():
  1–4. same base filters
  5. IF q:  annotate(rank=SearchRank(...)).filter(vector=q).order_by("-rank")
     ELSE:  same 4-way sort as listings
  6. annotate_favorites + Paginator(24)
```

### The IX_ads_pub_listing index (the one that matters)

```python
models.Index(
    name="IX_ads_pub_listing",
    fields=["status", "category_id", "city_id", "-published_at"],
    condition=Q(status=AdStatus.PUBLISHED),
)
```

This supports an **index-only scan** for: published → single-category-subtree
(broad IN list) → single-city → default date-desc sort, **provided no price
filter or price sort is applied** and the SELECT list is covered by the index
columns (which it is, since `select_related` doesn't add columns to the WHERE
but the Paginator count + LIMIT scan still needs heap fetches for the row
itself — see §5 for why this matters).

---

## 1. Composite Index Strategies for Multi-Column Filters

### The equality-before-range rule (PostgreSQL §11.3)

> A single multicolumn B-tree index can be used for query conditions that
> constrain all columns **or** constrain a leftmost prefix of columns.
> Equality constraints on leading columns + an inequality on the first
> non-equality column effectively limit the index scan range. Columns to the
> right of the inequality cannot be used for further range narrowing.

**Implication for the current index** `(status, category_id, city_id, -published_at)`:

| Query condition | Uses index? | Why |
|---|---|---|
| `status=PUBLISHED` (partial) + `category_id IN (…)` + `city_id = X` | ✅ range seek on prefix | Three leading columns are equality/range; index is sorted by `-published_at` so no separate Sort needed for default sort |
| + `price >= Y` | ⚠️ index narrows prefix, but **price is not in index** | Planner must visit heap per entry to check price → loses index-only; sort by price becomes full sort |
| `category_id = X` only (no city) | ⚠️ skips past `city_id` | PG18 **skip scan** (new in 18) can help if `city_id` has few hundred distinct values — see below |

### PostgreSQL 18 skip scans (new in PG18)

PG18 introduced **skip-scan lookups** on multicolumn B-tree indexes: a query
that omits an equality condition on a leading column can still use the index
when the skipped column has low cardinality. `status` has 7 values; `city_id`
at production scale is bounded (a few dozen cities). This weakens the
historical argument that "you must put equality columns before range columns" —
PG18 can sometimes use `(status, city_id, price)` even when `status` is given
only via the partial condition. **But skip scans are not free** — they scan one
"stripe" per distinct skipped value. Verify with `EXPLAIN`.

### Covering indexes with INCLUDE (index-only scan)

```sql
CREATE INDEX idx_ads_cover_browse
  ON ads (status, category_id, city_id, -published_at)
  INCLUDE (title, price, category_name, city_id)  -- payload columns
  WHERE status = 'PUBLISHED';
```

`INCLUDE` columns are not part of the search key — they're stored in the
leaf pages so the planner can return them without touching the heap
(index-only scan). This helps when the browse query SELECT-list needs only
indexed/covered columns (title, price, category_name for rendering the card).
**Trade-off:** every extra `INCLUDE` column bloats the index by ~4–6× the
row width; don't over-cover.

### Avoid the "N partial indexes" anti-pattern

PostgreSQL docs explicitly warn against creating one partial index per category
value (the equivalent anti-pattern). The single `IX_ads_pub_listing` covering
the PUBLISHED prefix is correct; do not split it into per-category partials.

### Column ordering in the existing index

The current order `(status, category_id, city_id, -published_at)` is
*optimal* for the dominant traffic: browsing a category subtree in a city,
sorted newest-first. The partial condition `status='PUBLISHED'` is redundant
as an indexed column (it's already in the `WHERE` predicate of the partial
index) but django-mptt's `fields=[...]` list repeats it — harmless, just
wastes ~4 bytes/row.

**Recommendation if category-subtree (IN list) becomes the hot path:**
move `category_id` to the lead position of the partial index:
`(category_id, city_id, -published_at)` — but only if a *single* category is
the most selective filter. Since `get_descendants` returns a multi-ID IN list,
the index still scans all matching categories as a range; the ordering among
them is not contiguous. This is the fundamental impedance mismatch of the
IN-list approach (see §4).

---

### Concrete Recommendation — Composite Indexes

1. **Keep `IX_ads_pub_listing` as-is** for now — it is correctly ordered for
   the dominant browse query. **Do not reorder** without EXPLAIN evidence.
2. **Add a price index** (§3) as a *separate* index rather than inserting
   `price` into the composite. Reasoning: a range predicate in the middle of
   a B-tree key (`status=city=eq, category_id=IN, price=range, sort=-date`)
   breaks the sort-order guarantee — once you hit an inequality, everything to
   the right of it in the index key is "lost" for ordering. Splitting price
   into its own index lets the planner bitmap-AND it with the listing index.
3. **Add an `INCLUDE` clause** to a *new* covering index for the browse
   SELECT-list columns only if `EXPLAIN (ANALYZE, BUFFERS)` shows high heap
   fetches on the listing index. Candidates: `(title, price, category_name)`
   — but measure first; the table is wide (6 localized text fields).
4. **Use `EXPLAIN (ANALYZE, BUFFERS)`** (Django `qs.explain(analyze=True,
   buffers=True)`) on a 500k-row replica before creating any new index.
   PG18's skip-scan means the planner may surprise you — verify rather than
   assume.

---

## 2. MPTT Subtree Indexing — ltree vs. Closure Table vs. B-tree on category_id

### Current setup: django-mptt 0.18.0

The `Category` model extends `mptt.models.MPTTModel`. The migration
(`categories/migrations/0001_initial.py`) reveals the stored fields:

```python
('lft',       models.PositiveIntegerField(editable=False))         # no db_index
('rght',      models.PositiveIntegerField(editable=False))         # no db_index
('tree_id',   models.PositiveIntegerField(db_index=True, editable=False))
('level',     models.PositiveIntegerField(editable=False))         # no db_index
```

**Auto-added index:** django-mptt 0.18.0 *automatically appends* a composite
B-tree index `(tree_id, lft)` to `cls._meta.indexes` if one is not already
present (verified in `mptt/models.py` lines 376–393, field name
`categories_category_tree_id_lft_idx`).

### How `get_descendants` queries (from mptt source)

```python
# MPTTModel.get_descendants() → _mptt_filter(tree_id=…, left__gte=…, left__lte=…)
# Generates SQL:
SELECT ... FROM categories
WHERE tree_id = <node.tree_id>
  AND lft >= <node.lft>
  AND lft <= <node.rght>
  AND ...   -- (grouped by contiguous siblings for multi-node querysets, but
              for a single node instance it collapses to the simple range)
```

For the project's query `category.get_descendants(include_self=True)`, this
is a **single-node range scan** on the `(tree_id, lft)` index — O(log n + k)
where k = subtree size. The category tree is small (~200 categories across 7
roots), so this sub-query is effectively free.

### The two-step pattern & its cost

```python
descendant_ids = category.get_descendants(include_self=True).values_list("id", flat=True)
# → Query 1: SELECT id FROM categories WHERE tree_id=X AND lft BETWEEN a AND b
# → Result: Python list of ~5–50 IDs
ads = ads.filter(category_id__in=descendant_ids)
# → Query 2: SELECT ... FROM ads WHERE category_id IN (id1, id2, ..., idN)
#             AND city_id = X AND ... ORDER BY ...
```

The IN-list is materialized in Python then sent as an `IN (...)` clause. With
a subtree of ~20 leaf categories, this is `category_id IN (23, 24, 27, …, 45)`.
PostgreSQL evaluates `IN` via the B-tree on `category_id` (the 2nd column of
`IX_ads_pub_listing`). The rows matching different IDs are **not contiguous**
in the index (because `published_at` is interleaved), so the planner may choose
a bitmap scan. This is acceptable at 500k rows but is a latent inefficiency.

### Alternatives considered

#### ltree extension

- **What it is:** PostgreSQL's `ltree` extension stores materialized paths
  as a `text` (e.g. `electronics.cars.used`). Supports `@>` (ancestor),
  `<@` (descendant), `~` (pattern), and a **GiST** index (not B-tree).
- **Read performance:** O(log n + k) via GiST range on the path string.
  Reads are excellent for ad-hoc path queries.
- **Write cost:** Each insert/update rewrites the path. Fine for a static
  catalog.
- **Django ecosystem:** No first-class Django integration; would require
  custom field + manager. django-mptt owns the tree layer here; switching
  is a large rewrite with no measured 500k-benefit.
- **Verdict: NOT recommended for this project.** The category tree is static
  (edited in CI via `categories.yaml`, not user-edited). MPTT's read
  performance is already O(log n + k) via the auto `(tree_id, lft)` index.
  ltree adds dependency + rewrite cost for a read pattern (subtree expand →
  IN list) that is dominated by the *ads* query, not the *category* query.

#### Closure Table

- **What it is:** A separate table storing every (ancestor, descendant, depth)
  pair. Subtree = `WHERE ancestor_id = X`; ancestors = `WHERE descendant_id =
  X`. All O(1) with indexes on both directions.
- **Storage:** O(N × H) rows for a balanced tree (H = height). For 200
  categories and ~8 levels, ~1,600 rows — trivial.
- **Write cost:** Insert/delete must cascade-insert all ancestor pairs
  (a single transaction). Django-mptt already does this via its `lft`/`rght`
  renumbering.
- **FK integrity:** Real foreign keys on both ends (unlike MPTT, which has
  no referential-integrity enforcement on the tree structure itself).
- **Django ecosystem:** The `django-mptt` library is already chosen and
  working; replacing it is a multi-week migration (signals, admin
  integration, tree rebuild).
- **Verdict: Migration candidate only if write-heavy category edits are
  introduced.** For a read-heavy classifieds catalog with a CI-managed
  category tree, MPTT is the pragmatic choice.

#### Materialized Path (single column)

- **What it is:** Store `parent_path` as a string like `1/3/7/23/`.
  Subtree = `WHERE path LIKE '1/3/%'`. Single B-tree index on `path`.
- **Used by:** Ancestry (Ruby), django-simple-history tree variants.
- **Pros:** simplest; no extra table; single B-tree; move = update
  only descendants.
- **Cons:** no built-in referential integrity; string prefix matching
  can be slower than integer range for very deep trees.
- **Verdict:** equivalent to ltree's materialized-path approach; same
  "not worth switching" conclusion.

### Index coverage of MPTT internals

The auto-added `(tree_id, lft)` index is sufficient for `get_descendants`.
**Gap:** there is **no explicit index on `parent_id`** alone. django-mptt's
`get_children()` uses `_mptt_filter(parent=self)` which queries
`parent_id = X AND tree_id = Y` — the `(tree_id, lft)` index can't serve
`parent_id`-leading queries. The root-category listing (rendering the top
level of the menu) does `Category.objects.filter(parent=None)` and is
currently served by... a sequential scan on the categories table (only 200
rows, so fine). At 200 rows this is irrelevant; note it for future growth.

### Recommendation: keep MPTT, optimize the consumer

The category subtree is not the bottleneck at 500k ads — the **ads** query is.
The MPTT range scan completes in <1 ms for 200 categories. Don't replace MPTT.

---

### Concrete Recommendation — MPTT / Category Tree

1. **Do not migrate away from django-mptt.** Read performance is already
   optimal via the auto `(tree_id, lft)` B-tree index. The tree has ~200
   nodes; subtree expansion is sub-millisecond.
2. **Add `db_index=True` to `Category.parent_id`** if/when the category tree
   grows beyond ~2k nodes and `get_children` / `parent=None` lookups become
   hot. Currently not worth it. Document this threshold.
3. **Address the IN-list consumer, not the tree query.** The real
   inefficiency is materializing IDs into a Python list then issuing an
   `IN (…)` against the ads table. See §4 for the alternative that keeps the
   MPTT range query *inside* the SQL planner.
4. **Cache the active-category tree** (it is CI-managed, not user-edited)
   in Redis per the project's existing cache infrastructure
   (`docs/99-agent/architecture.md` §Cache Backend). A 200-row tree with
   `lft`/`rght`/`tree_id` is ~20 KB — cache for the menu + subtree resolution
   and skip the DB hit entirely. Invalidate on deployment (tree is
   seed-time, not runtime).

---

## 3. Price Range B-tree Range Scans

### Current state

`ads.price` is `PositiveIntegerField` (whole BAM units).
**There is no index on price.** The doc explicitly defers: *"price has no
index (rare filter in phase 1; add only after EXPLAIN ANALYZE at 500k rows,
zone C7)."*

### Why a standalone B-tree on price

Range predicates (`price__gte`, `price__lte`) are B-tree's native strength.
A B-tree index supports `>=`, `<=`, `BETWEEN` with a bounded range scan.

```sql
-- Standalone price index scoped to PUBLISHED
CREATE INDEX IX_ads_pub_price ON ads (price)
  WHERE status = 'PUBLISHED';
```

**Selectivity matters.** If 80 % of ads fall within a typical
`min_price=5000, max_price=50000` range, the index won't help (seq scan is
cheaper than 80 % index scan + heap fetches). But if price filtering is
selective (e.g. "cars under 5,000 BAM" matching 5 % of rows), a B-tree range
scan wins. This must be measured — which is exactly why the docs defer to
"EXPLAIN ANALYZE at 500k rows."

### The composite-vs-separate dilemma

Inserting `price` into `IX_ads_pub_listing` as `(status, category_id, city_id,
price, -published_at)` is **counterproductive**:

- `category_id` is already an **IN list** (not equality), so the index can't
  use the `city_id` or `price` columns after it for ordering.
- A **range** predicate (`price >= X`) in the middle of a B-tree key
  *terminates* the usable prefix: everything to the right (`price`,
  `-published_at`) becomes unusable for either filtering or sorting.

**The correct decomposition:** two separate indexes:
1. `IX_ads_pub_listing` `(status, category_id, city_id, -published_at)` —
   handles category + city + default date sort (index-only when covered).
2. `IX_ads_pub_price` `(price)` partial on PUBLISHED — handles range filter.

The PG planner will **bitmap-AND** these two indexes: one provides the
candidate set, the other narrows it, then a Sort node orders by the chosen
sort key. At 500k rows this is ~20k–40k heap tuples — the Sort is in-memory
(top-N heapsort) and fast. **Do not** try to fuse them into one composite.

### Why sort-by-price currently forces a sort

`ORDER BY price ASC` with a filter `category_id IN (…)` + `city_id = X` but
**no price index**: the planner uses `IX_ads_pub_listing` (matching the prefix),
then sorts the ~thousands of matched rows by price — an O(k log k) sort.
With a standalone price index, the planner can't use either index to *both*
filter AND sort by price (the filters aren't on the price index). So a sort
is unavoidable with the two-index approach. The win is only in *filtering*
(narrowing to the price range), not in avoiding the sort.

If price-sort becomes the dominant sort (e.g. "sort by price"), a **dedicated**
index `(price, id)` partial on PUBLISHED lets the planner range-scan by price
and fetch in sorted order — no Sort node. But this index won't also filter on
category/city efficiently (those aren't prefix columns). Trade-off: one index
optimizes filtering, another optimizes price-sorting; keep both if both are
hot paths.

### NULL handling

`price` is nullable. Rows with `price IS NULL` are excluded by `price__gte`
filters (SQL three-valued logic) — correct for a price range. For
`ORDER BY price ASC`, NULLs sort first (NULLS FIRST is default in PostgreSQL
for ASC). If NULL-price ads should sort last, use `ORDER BY price ASC NULLS
LAST` / `NULLS FIRST DESC` — and note this **breaks index ordering** (a
B-tree on `price` cannot satisfy `NULLS LAST` on ASC without a `NULLS LAST`
modifier on the index column).

### Concrete Recommendation — Price Index

1. **Before 500k:** keep no price index (matches the deferred plan). Measure
   with `qs.explain(analyze=True, buffers=True)` on a seeded 500k test DB.
2. **At/above 500k, if price filtering is selective:** add
   ```sql
   CREATE INDEX IX_ads_pub_price ON ads (price) WHERE status = 'PUBLISHED';
   ```
   This is a *separate* index (not merged into `IX_ads_pub_listing`), so the
   planner can bitmap-AND it. Size: ~5% of the table if 5 % of ads have a
   price in the filtered range; ~20-30 MB at 500k rows for an `int4` column.
3. **If `price_asc`/`price_desc` sort is the dominant path** (not just a
   filter), add a sort-optimizing index:
   ```sql
   CREATE INDEX IX_ads_pub_price_sort ON ads (price, id) WHERE status = 'PUBLISHED';
   ```
   The trailing `id` provides a deterministic tiebreaker (two ads can share
   a price) and enables true index-ordered retrieval. Add `NULLS LAST`
   clause if the sort must place NULL-price ads at the end:
   `(price ASC NULLS LAST, id ASC)`.
4. **Use `EXPLAIN (ANALYZE, BUFFERS, SUMMARY)`** on representative price-range
   queries at scale before finalizing. If the planner chooses a seq scan
   despite the index, the filter is non-selective — remove the index.

---

## 4. Full-Text Search Integration with Faceted Filtering

### Current architecture (verified)

- **Per-language TSVECTOR columns:** `search_vector_ru`, `search_vector_bs`,
  `search_vector_en` (plus legacy `search_vector` to be dropped in Phase 3).
- **Trigger-maintained:** `ads_search_vector_fn()` plpgsql trigger — NOT
  `GENERATED ALWAYS` because the vector includes the category name from the
  `categories` table (a join at write-time).
- **Per-language GIN indexes:** `IX_ads_search_gin_ru`, `_bs`, `_en`.
- **Search query:** `SearchQuery(query, search_type="websearch", config=config)`
  → `annotate(rank=SearchRank(F(vector_field), search_query))`
  → `filter(**{vector_field: search_query})` → `order_by("-rank")`.
- **Facets (currently none on the search path):** category subtree + city +
  price filters are applied *before* the FTS annotation (same IN-list +
  exact patterns as browse).

### How the planner combines GIN + B-tree: the bitmap-AND

Per PostgreSQL §11.5 **"Combining Multiple Indexes"**:

> A single index scan can only use query clauses that match the index's columns
> with operators of its operator class **joined by AND**. … PostgreSQL has the
> ability to combine multiple indexes … it scans each needed index and prepares a
> **bitmap** in memory giving the locations of table rows … The bitmaps are then
> ANDed and ORed together. … the table rows are visited in **physical order** …
> a separate sort step will be needed if the query has an ORDER BY.

**Key consequence for this project:** When a search applies `category_id IN
(…)` + `city_id = X` + `search_vector_ru @@ query`, the planner may:
1. Use the GIN on `search_vector_ru` → bitmap A (all ads matching the text).
2. Use `IX_ads_pub_listing` on `(status, category_id, city_id, …)` → bitmap B
   (all published ads in the subtree + city).
3. **AND** the two bitmaps → final candidate set.
4. Visit heap in physical order → apply `rank` → **Sort** by `-rank`.

The GIN bitmap narrows the FTS matches; the B-tree bitmap narrows by
structured filters. This works, but **step 4's Sort loses the GIN index's
natural ordering** — the final sort is unavoidable regardless of index choice.
For top-N (`LIMIT 24`), PostgreSQL uses `top-N heapsort` which is O(n) where n
= bitmap cardinality — acceptable.

### Why FTS + structured filters don't fuse into one index

You **cannot** build a single index that serves both the GIN tsvector match
AND the B-tree category/city equality. They are different index AMs (GIN vs
B-tree). The planner's only recourse is bitmap-AND — confirmed by the
PostgreSQL mailing-list discussion (March 2026) that combining a GIN filter
bitmap with a B-tree ordered scan is a known planner limitation; proposals for
"ordered-bitmap scan" (PG18-era, experimental) exist but are **not** in core.

### Faceted counts (analytics on filter results)

A classic e-commerce facet sidebar needs counts per category/feature/brand
*within* the current result set. Two approaches:

**Approach A — aggregate over the already-filtered candidate set (fastest):**
```sql
WITH filtered AS (
  SELECT id FROM ads
  WHERE status='PUBLISHED'
    AND search_vector_ru @@ websearch_to_tsquery('russian', 'телефон')
    AND category_id IN (…) AND city_id = X
)
SELECT c.id, c.name, count(*) AS n
FROM filtered f JOIN ads a ON a.id = f.id
JOIN categories c ON c.id = a.category_id
GROUP BY c.id, c.name;
```
This re-scans the bitmap; at 500k rows the bitmap is in-memory and the join
is fast.

**Approach B — `ts_stat` / `tsvector_to_array` for term-based facets:**
The Bun tutorial (`bun.uptrace.com`) shows using `ts_stat()` over the filtered
tsvector set to build keyword facets. For category/feature facets, this doesn't
apply — those are structured columns. **Use Approach A.**

### Multi-language FTS correctness

The trigger dual-writes `search_vector_ru/bs/en` using the correct per-language
`to_tsvector` config (`russian`, `simple`, `english`). `simple` config for
Bosnian is correct — PostgreSQL 18 has no native Bosnian config (confirmed in
`docs/02-database/db-indexes.md`). The `websearch_to_tsquery` mode handles
quotes/prefix operators and is the right choice for a buyer-facing search box.

### GIN index tips and tricks

From PostgreSQL §70.5 (GIN Tips):

- **Insertion into a GIN index can be slow** — many posting-list entries per
  row. `fastupdate` (default on) mitigates this by buffering inserts; for bulk
  loads, drop + recreate. This matters during seed (`bulk_create` bypasses the
  trigger, so a one-time `UPDATE ads SET title = title` backfill is already in
  the migration notes).
- **`gin_fuzzy_search_limit`** caps result rows for very frequent words —
  default 0 (unlimited). For a classifieds search, leave unlimited; the
  bitmap-AND with structured filters usually keeps cardinality low.
- **GIN only does bitmap scans** (not index/only scans) — the planner always
  visits the heap for the matching rows. This means even index-only-scan
  benefits (INCLUDE columns) are **unavailable** for the FTS match path. For
  the structured-filter bitmap, the B-tree index CAN do index-only scans.

### pg_trgm alternative for title autocomplete

If future work adds **fuzzy/partial title matching** (e.g. "iph" → "iPhone"),
a GIN index with the `pg_trgm` operator class on the title column beats
PostgreSQL's default LIKE handling:
```sql
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE INDEX IX_ads_title_trgm ON ads USING GIN (title gin_trgm_ops)
  WHERE status = 'PUBLISHED';
```
This is **not** needed for the current FTS-by-tsvector design but is the right
tool if substring/fuzzy title search is added. Do not confuse it with the
existing GIN-on-tsvector indexes (different operator classes, different
queries).

### Concrete Recommendation — FTS + Facets

1. **The current GIN-on-per-language-tsvector + B-tree-on-structured-filters
   combination is correct.** The planner bitmap-ANDs them. No schema change
   needed for correct filtering.
2. **Drop the legacy `IX_ads_search_gin`** (on `search_vector`) in Phase 3 as
   planned — the four per-language vectors supersede it. Each GIN index costs
   ~10-15 % of table size; removing one at 500k rows saves ~50-75 MB.
3. **For facet counts:** use Approach A (CTE over the filtered id set +
   aggregate join). Do NOT call `ts_stat()` — it cannot see structured
   columns (category/feature).
4. **Verify the bitmap-AND is happening** with `EXPLAIN (ANALYZE, BUFFERS)`:
   look for `"Plan": {"Node Type": "Bitmap Heap Scan", "Recheck Cond": "(a AND b)"}`
   where both `a` and `b` reference different indexes. If only one index
   appears, the planner chose the more selective one and seq-scanned the
   other's filter — add the missing index or reconsider filter ordering.
5. **Defer pg_trgm** until fuzzy-title search is on the roadmap. It is a
   separate, opt-in capability.

---

## 5. Array / M2M Filtering with GIN Indexes

### Current M2M setup: `Ad.features` → `ad_features`

```python
class AdFeature(models.Model):
    ad = models.ForeignKey(Ad, on_delete=CASCADE, related_name="ad_features")
    feature = models.ForeignKey("lookups.LookupItem",
        limit_choices_to={"group__code": LookupGroupCode.LISTING_FEATURE},
        on_delete=CASCADE)
    sort_order = models.PositiveIntegerField(default=0)
    class Meta:
        db_table = "ad_features"
        unique_together = [("ad", "feature")]
```

The `unique_together = [("ad", "feature")]` creates a **unique B-tree index**
on `(ad_id, feature_id)`. There is **no separate index on `feature_id` alone.**

### The filter query

The audit draft (§3.7 of `26_codebase-audit-filters.md`) proposes:
```python
for fid in feature_ids:
    ads = ads.filter(features__id=fid)  # AND semantics: ad has ALL selected features
```

This generates a JOIN through `ad_features`. For each `fid`, the query is:
```sql
WHERE EXISTS (
  SELECT 1 FROM ad_features af WHERE af.ad_id = ads.id AND af.feature_id = <fid>
)
```

### Index gap: `feature_id` is the 2nd column of the unique index

With only `(ad_id, feature_id)`:
- Lookup by `ad_id` (ad → its features): **index-only seek** — fast.
- Lookup by `feature_id` (which ads have this feature): **full index scan**
  of the unique index, probing each entry's `feature_id`. For 500k ads ×
  ~3 features each = ~1.5M rows in `ad_features`, a feature that 50 % of ads
  have means scanning ~750k index entries.

**Fix:** add a separate B-tree index on `feature_id`:
```python
# In AdFeature.Meta.indexes
models.Index(fields=["feature"], name="IX_ad_features_feature_id"),
```

This is a B-tree (not GIN) on a scalar FK column — the correct structure.
A GIN index on an array column would be relevant only if features were stored
as a native PostgreSQL array (e.g. `feature_ids INTEGER[]`), which is **not**
the current design.

### Array column vs. M2M join: the trade-off

The TigerData article and the SO comparison both note:
- **M2M join table** (current): FK integrity, per-row `sort_order`, easy to
  add metadata. Requires a join + (with the fix above) a reverse B-tree index.
- **PostgreSQL array column** (`feature_ids INTEGER[]`): eliminates the join;
  a single GIN index on the array supports `@>` (contains) in one step.
  But loses per-feature metadata (sort_order), FK constraints, and the
  per-feature lookup for the facet sidebar.

> **Laurenz Albe (SO, 2021):** *"the second option [join table] will perform
> better, and it has the added benefit that you can have foreign key
> constraints to enforce data integrity. In most cases, it is a good idea to
> avoid composite types like arrays or JSON in the database."*

**Verdict for this project:** The M2M join is the right choice — it carries
`sort_order` (needed for ad-page feature display) and the project already
enforces `LookupGroupCode.LISTING_FEATURE` at the FK level. **Do not** convert
to an array column. **Do** add the reverse `feature_id` index.

### AND vs OR semantics for multi-feature filter

- `ads.filter(features__id=fid1).filter(features__id=fid2)` → AND (ad has
  **both** features). Each `.filter()` adds an `EXISTS` clause.
- `ads.filter(features__id__in=[fid1, fid2])` → OR (ad has **either**
  feature). Single `IN` against the join.

For a "show ads with all selected features" filter UI (standard for
classifieds — e.g. "new + delivery"), AND semantics is correct. For "new OR
delivery", OR. The current code pattern (chained `.filter()`) does AND —
document this in the view; expose a `features_match=all|any` param only if
needed.

### GIN on the array alternative (for reference)

If the project *did* store features as `feature_ids INTEGER[]`:
```sql
CREATE INDEX IX_ads_pub_features_arr ON ads USING GIN (feature_ids)
  WHERE status = 'PUBLISHED';
-- query: WHERE feature_ids @> ARRAY[3, 7]  -- contains both
```
The `@>` operator means "left array contains all elements of right array" —
exact AND semantics. `&&` (overlap) = OR. GIN handles both.
**But** this loses `sort_order` and FK integrity. Not recommended here.

### Concrete Recommendation — M2M / Array

1. **Add `models.Index(fields=["feature"], name="IX_ad_features_feature_id")`**
   to `AdFeature.Meta.indexes`. This is the single highest-impact index for
   enabling multi-feature filtering. Cost: ~15-20 MB at 1.5M ad_features rows.
2. **Keep the M2M join table** — do not flatten to a PostgreSQL array. The
   `sort_order` column and FK-to-`LookupItem` constraint are needed for data
   integrity and display ordering.
3. **Implement multi-feature filter as chained `.filter(features__id=fid)`**
   for AND semantics (current code draft). For OR semantics (multi-checkbox
   "any of"), use `features__id__in=[…]`. Document the choice in the view
   docstring; do not silently default to one.
4. **If 500k ads × many features makes `EXISTS` subqueries expensive**,
   consider a **bitmap join index** substitute: a materialized CTE that
   pre-filters features. Out of scope for Phase 1; defer until measured.
5. **Consider `listing_purpose_id` (FK, scalar) index** in parallel (see §6)
   — it follows the same "reverse lookup on a FK" pattern and is cheaper
   than M2M.

---

## 6. Sorting & Pagination — Keyset vs OFFSET+LIMIT at 500k Rows

### Current implementation

```python
# listings.py & search.py
PER_PAGE = 24
paginator = Paginator(ads, PER_PAGE)       # Django's built-in
page_obj = paginator.get_page(page_number)  # → COUNT(*) + LIMIT/OFFSET
```

Django's `Paginator` issues:
1. `SELECT COUNT(*) FROM (…) ` — a full count of the result set (expensive at
   500k; the COUNT itself must scan or index-scan the full bitmap).
2. `SELECT … LIMIT 24 OFFSET N*24` — skips `N*24` rows.

### Why OFFSET+LIMIT is O(n) at depth

**OFFSET forces the database to materialize and discard all preceding rows.**
From the Stack Overflow + Dev.to benchmarks:

```
Page 1  (OFFSET 0):        ~0.1 ms   (Index Scan, 24 rows)
Page 50 (OFFSET 1200):     ~10 ms    (Index Scan, 1224 rows fetched, 1200 discarded)
Page 5000 (OFFSET 120000):  ~87 ms    (reads + sorts 120,024 rows, discards 120k)
```

At 500k ads with 24/page, page 20,000 = `OFFSET 480,000` — the planner walks
through 480k index entries + heap fetches before returning row 24. The count
query (`COUNT(*)`) is *also* O(n) — it must traverse the full result set.

**The correctness problem:** if an ad is published (or its `published_at`
changes) between page requests, rows *shift* — items appear on two pages or
are skipped entirely. For a classifieds board where ads are published daily,
this is not theoretical.

### Keyset (cursor) pagination — the O(1) alternative

Instead of "skip N rows," seek by the **last seen sort key**:

```sql
-- Default sort: published_at DESC, id DESC (id as tiebreaker)
-- Page 1:
SELECT … FROM ads WHERE status='PUBLISHED'
  AND category_id IN (…) AND city_id = X
  ORDER BY published_at DESC, id DESC LIMIT 24;

-- Page 2 (cursor = last row's published_at + id from page 1):
SELECT … FROM ads WHERE status='PUBLISHED'
  AND category_id IN (…) AND city_id = X
  AND (published_at, id) < ('2026-08-15 10:30:00+02', 45678)
  ORDER BY published_at DESC, id DESC LIMIT 24;
```

The `(published_at, id) < (val, val)` **tuple comparison** uses PostgreSQL's
row-value comparator and can be answered by a single composite index seek
— **O(log n + k)** regardless of depth. Verified benchmarks:
~0.09 ms at any page depth (vs 87 ms for OFFSET at page 50k).

### The tiebreaker requirement (critical)

`published_at` is **not unique** — many ads publish within the same second.
Sorting by `(published_at, id)` with `id` (BigAuto PK) appended as the
second key makes the ordering **deterministic**. Without the tiebreaker,
rows with equal `published_at` can appear in any order across pages →
skips and duplicates.

This is non-optional: **the sort columns must uniquely identify a row.**
PostgreSQL docs on row/value comparison (`functions-comparisons.html` §
Row-Type Comparison) confirm tuple comparison works for multi-column
cursors.

### Matching index for keyset

```sql
CREATE INDEX IX_ads_pub_listing_keyset ON ads
  (status, category_id, city_id, published_at DESC, id DESC)
  WHERE status = 'PUBLISHED';
```

This is a *rearrangement* of the existing `IX_ads_pub_listing`: move
`published_at DESC` as the 4th column and append `id DESC` as tiebreaker.
For the default sort, this enables **pure index-ordered retrieval** — no
Sort node, no heap re-sort. For price-sort, the index can't help (price
isn't a prefix); that path needs the `IX_ads_pub_price_sort` from §3.

For **mixed-direction** sorts (e.g. `price ASC, published_at DESC`), a simple
tuple comparison `(price, id) > (last_price, last_id)` works only when
**all directions match**. Mixed directions require the OR-expanded form:
```sql
WHERE (price > last_price)
   OR (price = last_price AND id > last_id)
```
For keyset implementation, **keep sort keys uniform-direction** (all DESC
or all ASC) to use tuple comparison. Price ascending + published_at
descending is a mixed case → use the OR form or pick a single sort axis.

### Backward navigation (previous page)

Keyset only supports forward traversal. To go to the previous page, reverse
the sort, take the first row's cursor, reverse again. Or: store both the
first and last cursor of each fetched page. Most UIs hide "previous" behind
a "load newer" button. Accept this limitation for the classifieds feed.

### Cursor encoding

Encode the last row's sort-key values as an opaque string (base64 of JSON)
so the client can't tamper with pagination internals:
```python
import base64, json
cursor = base64.urlsafe_b64encode(
    json.dumps({"published_at": iso_str, "id": 45678}).encode()
).decode()
```

### When OFFSET is still acceptable

From the comparative analysis:
- **Numbered page UI** ("Go to page 47"): keyset can't jump to page N.
  OFFSET is the *only* option here, with the caveat of capping max page
  depth (e.g. "results beyond page 1000 are not available").
- **Small result sets**: if filters narrow to <500 rows, OFFSET is fine.
- **Admin/moderation UIs**: deep random access is expected. Keep OFFSET.

### Django-specific considerations

- Django's `Paginator` does `COUNT(*)` + `LIMIT/OFFSET` — **replace it**
  for the public catalog with a custom keyset paginator, or use a library.
- No keyset library is currently in `pyproject.toml` dependencies.
- `django-admin` listings already use OFFSET (acceptable for staff).
- The `Paginator.count` call (`SELECT COUNT(*) …`) is itself O(n) and a
  major cost at depth. Keyset eliminates it (the client doesn't need a total
  count — it needs `has_next_page`, which is `LIMIT+1`).
- `select_related` / `prefetch_related` are independent of pagination strategy
  but must be present to avoid N+1 within the page's 24 rows (see §7).

### Concrete Recommendation — Pagination

1. **Keep Django `Paginator` (OFFSET) for the first 3–5 pages** or for
   filtered result sets that are known small (<500 rows). The complexity cost
   of keyset is only justified by depth.
2. **Switch to keyset pagination for the default browse feed** (`* /`
   root, `/category/<slug>/`), where users scroll infinitely and deep
   pagination is common. Implement with:
   - URL param `?cursor=<base64>` (opaque).
   - Sort key: `(published_at DESC, id DESC)` with the matching composite
     index.
   - Return `has_next: (count of returned rows == page_size)` (fetch LIMIT+1,
     drop the extra row — no COUNT needed).
3. **For FTS search results sorted by `-rank`**, keyset is harder:
   `SearchRank` is a computed float, not a stable column. Two ads can have
   identical rank → tiebreaker on `(rank, id)` but `rank` isn't stored.
   **Recommendation:** keep OFFSET for search-result pagination, but cap
   the max page depth (e.g. only paginate to page 100 = 2,400 results;
   beyond that, "Refine your search"). Most buyers don't go past page 3 of
   search results.
4. **Do not implement keyset for `price_asc`/`price_desc` sort** unless and
   until it becomes the dominant path — the `IX_ads_pub_price` or
   `IX_ads_pub_price_sort` index (§3) is the prerequisite, and mixing
   price-sort with cursor state adds UX complexity (cursor must encode
   price + id).
5. **If numbered-page UX ("go to page N") must be preserved:** a hybrid —
   server-side keyset for the data fetch, but cache page-boundary cursors
   in Redis (encode cursor-per-page up to page 100). This is the
   " illusion of numbered pages" pattern; defer until the HTMX infinite-
   scroll migration lands.

---

## 7. Django ORM select_related / prefetch_related / Exists Patterns

### Current usage (verified in both views)

```python
# listings.py
ads = Ad.objects.filter(status=AdStatus.PUBLISHED)
    .select_related("category", "city", "user")           # FK joins, single SQL
    .prefetch_related("user__trust_score")                 # 2nd SQL (M2O, can't select_related)

# search.py
ads = Ad.objects.filter(status=AdStatus.PUBLISHED)
    .select_related("category", "city")                    # missing "user" — minor gap
```

**`annotate_favorites`** (`.ai/ads/views/favorite.py:27`):
```python
favorite_exists = AdFavorite.objects.filter(
    ad_id=OuterRef("pk"), user_id=user_id)
return queryset.annotate(is_favorited=Exists(favorite_exists))
```

This is the **correct** pattern: a correlated `Exists` subquery instead of
`prefetch_related("favorites")` (which would return a list and require a
Python-side filter per ad). The `Exists` renders as:
```sql
SELECT …, EXISTS (
  SELECT 1 FROM ad_favorites WHERE ad_id = ads.id AND user_id = N
) AS is_favorited FROM ads …
```
One extra subquery, but no extra round-trip — the subquery is evaluated
inline by the database for each row in the result set. This is optimal for a
per-row boolean annotation.

### select_related vs. prefetch_related — the rule

| Relationship | Tool | Why |
|---|---|---|
| FK (single value: category, city, user) | `select_related` | JOIN, single SQL |
| O2O reverse (user → trust_score) | `prefetch_related` | can't JOIN reverse O2M/O2O without duplication |
| M2M (Ad.features, Ad.images) | `prefetch_related` | separate query + dedup |
| Per-row boolean (is_favorited) | `Exists` subquery | no object loading, just a flag |

The views correctly use `select_related("category", "city", "user")` — these
are 3 FK columns needed for the ad card (category name, city name, seller).
The `prefetch_related("user__trust_score")` is necessary because
`TrustScore` is a OneToOne reverse relation (can't `select_related` across it
in a list query without duplication issues).

### Gap: `search()` omits `select_related("user")`

`search.py` does `select_related("category", "city")` — missing `"user"`.
The ad card template likely displays the seller's username/trust badge. At 500k
rows, fetching the user via a per-row lazy load (N+1) on the search page would
add 24 extra queries per page. **Fix: add `"user"` to `select_related`.**

### prefetch_related for M2M: images and features

Neither view currently `prefetch_related("images")` in the listing queryset.
This is **correct** for the listing page — you don't load full image objects
for 24 cards (you only need the first thumbnail key). But in the `ad_detail`
view, it does `prefetch_related("images", "user__trust_score")` — correct
for a single ad. For the listing card, a `values()` projection of just the
first image key per ad would be optimal, but that breaks the ORM object graph
→ template expects `ad.images.first()`. Leave as-is; the N+1 here is bounded
to 1 query per page (not per card) if `prefetch_related("images")` is added,
or zero if the template only uses `images.first()` (Django's `first()` on an
unfetched M2M does one extra query per access).

### The `get_descendants → IN` list pattern (revisited)

```python
descendant_ids = category.get_descendants(include_self=True).values_list("id", flat=True)
ads = ads.filter(category_id__in=descendant_ids)
```

This materializes a Python list and passes it as `IN (…)`. At small subtree
sizes (<50 IDs) this is fine. For a root category like `real-estate` with 13
child categories across 3 levels, the IN list grows to ~20 IDs. PostgreSQL
handles 20-value IN lists efficiently via B-tree index scans + bitmap-AND.

**Alternative that avoids Python materialization:** use `Exists` or a
subquery against the categories table directly:
```python
from django.db.models import Exists, OuterRef
subtree = Category.objects.filter(
    tree_id=category.tree_id,
    lft__gte=category.lft,
    lft__lte=category.rght,
)
ads = ads.filter(category_id__in=subtree.values("id"))
# → generates a subquery, no Python materialization
```
But this still becomes `IN (SELECT id FROM categories WHERE …)` — PostgreSQL
handles it the same way. The *only* benefit is avoiding the Python round-trip.
**Not a priority at 500k**; defer.

### Django `explain()` for verification

```python
qs.explain(analyze=True, format="json", buffers=True)
```
Django 5.2's `QuerySet.explain()` wraps PostgreSQL's `EXPLAIN (ANALYZE, …)`.
Use it in a management command or test to verify index usage before/after
any new index. This is the "EXPLAIN ANALYZE at 500k rows" the docs call for.

### Concrete Recommendation — Django ORM

1. **Add `"user"` to `select_related` in `search.py`** — closes an N+1 gap
   where the seller is fetched per-card via lazy load. Diff: `.select_related("category", "city", "user")`.
2. **Keep the `Exists`-based `annotate_favorites`** — it is the correct
   pattern (correlated subquery, no N+1). Do not replace with
   `prefetch_related`.
3. **Do not `prefetch_related("images")` in the listing queryset.** The
   listing card renders only the primary thumbnail; add a targeted
   `prefetch_related("images")` only if the template accesses more than
   the first image per ad.
4. **Use `qs.explain(analyze=True, buffers=True)`** as a pre-deployment gate
   on a 500k-row test database. Add a CI test that asserts `Index Scan` (not
   `Seq Scan`) appears in the plan for the canonical browse query.
5. **For future keyset pagination (§6):** the cursor-encoding helper and the
   `LIMIT+1` "has next" check must live in a service layer, not inline in
   the view. Keep the view thin.

---

## 8. Consolidated Recommendations — Prioritized for This Project

Priority order reflects the 80/20 impact at the project's actual scale
(500k ads, ~200 categories, ~50 cities, HTMX MPA).

### P0 — Pre-500k (current state, measured before adding)

| # | Change | Rationale | Effort |
|---|---|---|---|
| 1 | Run `EXPLAIN (ANALYZE, BUFFERS)` on browse + search at 500k rows | Data-driven decisions; PG18 may surprise with skip-scan | Low (test infra) |
| 2 | Add `"user"` to `select_related` in `search.py` | Closes a latent N+1 (24 queries/page) | 1-line |
| 3 | Cache the Category MPTT tree in Redis (per `architecture.md` §Cache Backend) | Subtree expansion is sub-ms but avoids a DB hit on a CI-managed static tree | Low (cache service already exists) |

### P1 — At/above 500k rows (when EXPLAIN confirms selectivity)

| # | Change | Migration | Notes |
|---|---|---|---|
| 4 | `CREATE INDEX IX_ads_pub_price ON ads (price) WHERE status='PUBLISHED'` | New: partial B-tree on price | Separate index, not merged into `IX_ads_pub_listing`. Verify selectivity > ~3%. |
| 5 | Add `IX_ad_features_feature_id` index on `AdFeature.feature` | New: B-tree on feature_id FK | Enables multi-feature AND/OR filtering via M2M. |
| 6 | Add `db_index=True` on `Ad.listing_purpose` FK (if purpose filter is enabled) | `models.Index(fields=["listing_purpose_id"])` partial on PUBLISHED | `listing_purpose_id` is a scalar FK — B-tree is correct, not GIN. |
| 7 | Keyset pagination for default browse feed (`/`, `/category/<slug>/`) | Code: new cursor paginator | Sort key `(published_at DESC, id DESC)`, matching index. Opaque base64 cursor. |

### P2 — If price-sort or deep search paging becomes dominant

| # | Change | Migration | Notes |
|---|---|---|---|
| 8 | `CREATE INDEX IX_ads_pub_price_sort ON ads (price, id) WHERE status='PUBLISHED'` | Sort-optimizing index for `price_asc`/`price_desc` | Includes `id` tiebreaker. Add `NULLS LAST` if NULL-prices sort to end. |
| 9 | Keyset for price-sort (cursor encodes `price, id`) | Code | Mixed with rank for FTS (see P2 caveat). |
| 10 | Drop legacy `IX_ads_search_gin` (on `search_vector`) | Phase-3 cleanup | Saves ~50 MB at 500k rows; 4 per-language GIN indexes replace it. |

### P3 — Defer until feature-driven (measured, not speculative)

| # | Change | Trigger |
|---|---|---|
| 11 | `pg_trgm` GIN index on `title` | Fuzzy/partial title search ("iph" → "iPhone") |
| 12 | Array column for features (`feature_ids INTEGER[]`) | Only if `sort_order` is dropped and FK integrity is deemed unnecessary — **not recommended** |
| 13 | ltree extension | Only if category tree becomes write-heavy user-edited — **not recommended** for CI-managed tree |
| 14 | Closure table | Only if concurrent subtree moves and real-time ancestor queries are required — **not recommended** |

---

## 9. Sources (confidence-rated)

- **HIGH** — PostgreSQL 18 §11.3 Multicolumn Indexes (equality-before-range,
  leading-column significance): `postgresql.org/docs/18/indexes-multicolumn.html`
- **HIGH** — PostgreSQL 18 §11.5 Combining Multiple Indexes (bitmap-AND of
  GIN + B-tree): `postgresql.org/docs/18/indexes-bitmap-scans.html`
- **HIGH** — PostgreSQL 18 §12.9 Preferred Index Types for Text Search (GIN
  vs GiST for tsvector): `postgresql.org/docs/18/textsearch-indexes.html`
- **HIGH** — PostgreSQL 18 §70.5 GIN Tips and Tricks (fastupdate,
  gin_fuzzy_search_limit, bulk-load drop/recreate): `postgresql.org/docs/18/gin-tips.html`
- **HIGH** — PostgreSQL 18 Release Notes (skip scans, parallel GIN builds,
  AIO): `postgresql.org/docs/18/release-18.html`
- **HIGH** — django-mptt 0.18.0 source (`mptt/models.py`, `mptt/managers.py`):
  verified `get_descendants` generates `WHERE tree_id=… AND lft BETWEEN…`;
  auto-adds `(tree_id, lft)` index.
- **HIGH** — Django 5.2 docs (select_related/prefetch_related/Exists):
  `docs.djangoproject.com/en/5.2/ref/models/querysets`
- **HIGH** — Keyset pagination with non-unique sort keys + tuple
  comparison `(col, id)`: `monpg.app/blog/postgresql-keyset-pagination`,
  `use-the-index-luke.com/no-offset`, `Stack Overflow #237861`
- **HIGH** — Keyset cursor stability, cursor encoding, mixed-direction
  caveats: `dev.to/scion01/optimizing-pagination` (2024),
  `thelinuxcode.com/pagination-2026`
- **MEDIUM** — Closure table storage analysis (O(N×H) rows, insert
  pattern, anti-patterns): openskillindex.com db-closure-table skill
- **MEDIUM** — ltree vs recursive CTE vs materialized path trade-offs:
  `cybertec-postgresql.com` Hans-Jürgen Schönig series (2020),
  `codegenes.net` (2026)
- **MEDIUM** — GIN array/M2M operator classes (@>, <@, &&): TigerData
  "Optimizing Array Queries With GIN Indexes" (2025),
  `dba.stackexchange.com` on array vs join (Laurenz Albe, 2021)
- **MEDIUM** — Faceted search with PostgreSQL (ts_stat for facets,
  CTE-over-filtered-set approach): `Bun tutorial`, `edb.com` faceted-search
  Django article
- **LOW** — PG18 "ordered-bitmap scan" experimental proposal (not in core):
  `postgresql.org/message-id` mailing list thread, March 2026

---

## Appendix A — Index Decision Matrix for the `ads` Table

| Filter / Sort | Index needed | AM | Why not reuse `IX_ads_pub_listing`? |
|---|---|---|---|
| `status=PUBLISHED` + `category_id IN (…)` + `city_id=X` + `ORDER BY -published_at` | `IX_ads_pub_listing` (exists) | B-tree | Already optimal — index-only range scan |
| `price >= Y` (filter) | `IX_ads_pub_price` (new) | B-tree | Can't insert range predicate mid-key without breaking the sort prefix |
| `ORDER BY price DESC` | `IX_ads_pub_price_sort` (new) | B-tree | Sort on a column not in the listing index → full Sort node without it |
| `features__id = F` (M2M) | `IX_ad_features_feature_id` (new) | B-tree | Reverse FK lookup on `feature_id` — 2nd col of unique index is unseekable |
| `listing_purpose_id = P` | `IX_ads_pub_purpose` (new) | B-tree | Scalar FK, not yet a filter |
| `search_vector_ru @@ q` (FTS) | `IX_ads_search_gin_ru` (exists) | GIN | GIN can't coexist with B-tree in one index — bitmap-AND instead |
| `search_vector_ru @@ q` + `category_id IN (…)` | both (bitmap-AND) | GIN + B-tree | Planner combines two indexes; Sort node needed for `-rank` (unavoidable) |
| Default browse, keyset page 2 | `IX_ads_pub_listing_keyset` (new) | B-tree | Needs `id DESC` tiebreaker after `published_at DESC` for stable cursor |
| `title ILIKE '%iph%'` (if added) | `IX_ads_title_trgm` (new) | GIN (pg_trgm) | B-tree LIKE can't use leading wildcard; `gin_trgm_ops` required |

## Appendix B — Keyset Cursor Encoding Example (Python)

```python
import base64, json
from datetime import datetime

def encode_cursor(published_at: datetime, ad_id: int) -> str:
    """Encode a keyset cursor from the last row's sort keys."""
    raw = json.dumps({"t": published_at.isoformat(), "i": ad_id},
                     separators=(",", ":"))
    return base64.urlsafe_b64encode(raw.encode()).decode()

def decode_cursor(cursor: str) -> tuple[datetime, int]:
    """Decode a keyset cursor. Returns (published_at, id)."""
    raw = base64.urlsafe_b64decode(cursor.encode())
    data = json.loads(raw)
    return datetime.fromisoformat(data["t"]), data["i"]

# Query (default browse, backward-compatible with existing date_desc sort):
#   WHERE (published_at, id) < (%s, %s)
#   ORDER BY published_at DESC, id DESC LIMIT 25
# has_next = len(results) == 25; if so, drop the 25th row client-side
```

## Appendix C — Verify Index Usage at Scale (Django management command sketch)

```python
# Management command: verify_browse_plan.py
from apps.ads.models import Ad
from apps.core.enums import AdStatus

qs = (Ad.objects.filter(status=AdStatus.PUBLISHED)
      .select_related("category", "city", "user")
      .order_by("-published_at"))
print(qs.explain(analyze=True, format="json", buffers=True))
# Assert: "Node Type": "Index Scan" (or "Bitmap Heap Scan") — never "Seq Scan"
```
