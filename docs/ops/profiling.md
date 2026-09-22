# Profiling & Indexing Review

> **Purpose:** Establish a repeatable profiling cadence for the search and listings hot paths, using both Python-level cProfile and PostgreSQL `EXPLAIN (ANALYZE, BUFFERS)`.
> **Tools:** `scripts/profile_search.py` (cProfile), `profile_queries` management command (EXPLAIN), `PerformanceSLO` constants (`src/benchmark/constants.py`)
> **Spec:** `docs/99-agent/rules.md:224-228` (Profiling Rules)

## Overview

Two complementary profiling tools cover the ad search/listing critical path:

| Tool | What it measures | When to use |
|---|---|---|
| `profile_search.py` (cProfile) | Python-level call counts and cumulative time — middleware, ORM, FTS, SWR cache, template rendering | Before optimizing a hot path; diagnosing latency regressions in the application layer |
| `profile_queries` (EXPLAIN ANALYZE) | PostgreSQL query-plan nodes, actual row counts, buffer hits/reads | When a hot path is confirmed via cProfile; verifying index usage before tuning query text |

Both tools reference `PerformanceSLO` thresholds so the SLO budget is visible alongside the profile output:

- **p95 latency SLO:** `PerformanceSLO.P95_SLO_MS` (500 ms)
- **p99 / search latency SLO:** `PerformanceSLO.SEARCH_SLO_MS` / `PerformanceSLO.P99_SLO_MS` (2000 ms)
- **Cache hit-rate SLO:** `PerformanceSLO.CACHE_HIT_RATE_THRESHOLD` (85 %)

See `docs/99-agent/rules.md:224-228` for the full profiling rules.

## Profiling Cadence

> **Rule (rules.md:226):** Profile before optimizing — never optimize a hot path without first confirming it in a cProfile run or `EXPLAIN (ANALYZE, BUFFERS)` output.

| Trigger | Action | Owner |
|---|---|---|
| Every PR touching `apps/search/views/`, `apps/ads/services/listings_query.py`, or `apps/ads/models.py` | Run `profile_queries` against a seed-scale DB; confirm no new Seq Scan on the `ads` table | Author |
| After a cProfile run shows a hot path exceeding **10 % p95 regression** vs. `PerformanceSLO.P95_SLO_MS` | Run `profile_queries` to find the specific query plan; add an index if Seq Scan is present | Author |
| Locst load test shows p95 regression > `PerformanceSLO.LOAD_TEST_P95_REGRESSION_THRESHOLD` % against SLO constants (rules.md:228) | Halt feature work; run both profiling tools; file an index ticket if Seq Scan found | Lead |
| On-call incident: search latency > 2 s in production | Run `profile_queries` against a production-replica read; compare plan to the last known-good baseline | On-call |

## Prerequisites

The dev environment must be running with seed data so the Seq-Scan assertion is meaningful (the planner legitimately uses Seq Scan on tables <10k rows — see `SEED_SCALE_MIN_ROWS` in the command source).

```bash
# Start dev stack (web :8000 + test DB :5433) and seed >10k published ads
make up
```

## Running cProfile — `scripts/profile_search.py`

The cProfile harness exercises the full search view stack (middleware, ORM, native PostgreSQL FTS, SWR search cache, template rendering) via the Django test client — no need to run the HTTP server separately.

```bash
# Inside the dev web container (make profile delegates here)
make profile                              # defaults: 50 iterations, top 30, sort=cumulative

# Override defaults:
make profile ITERATIONS=200               # more iterations for statistical stability
make profile SORT=tottime                 # sort by tottime instead of cumulative
make profile SORT=perf_counter            # use 'time' sort key

# Direct invocation inside the container:
uv run python scripts/profile_search.py --iterations 100 --top 50 --sort time --query "велосипед"
```

The harness writes its report to stdout. Look for:
- `SearchRank` / `tsvector` functions dominating cumulative time (FTS bottleneck)
- SWR cache miss paths (`get_with_stale_revalidate` producer calls)
- ORM query count (unexpected N+1s)

## Running EXPLAIN ANALYZE — `profile_queries`

The management command compiles the same query patterns used by the production search/listings views and runs `EXPLAIN (ANALYZE, BUFFERS)` on each via `django.db.connection`. It asserts that no sequential scan appears on the `ads` table at seed scale.

```bash
# Inside the dev container (requires DJANGO_SETTINGS_MODULE + DB)
python -m manage.py profile_queries

# Override the search term, table, or skip execution:
python -m manage.py profile_queries --query "велосипед"
python -m manage.py profile_queries --table ads
python -m manage.py profile_queries --dry-run       # print SQL only, no EXPLAIN execution

# In Docker (test environment):
docker compose --project-name mko-bazuna-test -f docker-compose.yml -f docker-compose.test.yml \
  run --rm test python -m manage.py profile_queries
```

### Representative queries

The command EXPLAINs these patterns, derived from the search/listings views:

1. **FTS search** — `SearchRank` + `@@ tsvector` filter on `search_vector_ru` (uses `IX_ads_search_gin_ru` GIN index)
2. **Listing** — `status=PUBLISHED` ordered by `-published_at` (uses `IX_ads_pub_listing`)
3. **Filter by city** — `status=PUBLISHED` + `city_id` (uses `IX_ads_pub_listing`)
4. **Filter by category subtree** — `status=PUBLISHED` + `category_id IN (...)` (uses `IX_ads_pub_listing`)
5. **Filter by price range** — `status=PUBLISHED` + `price_normalized_eur` range (uses `IX_ads_price_normalized_eur`)
6. **Sort by price** — `ORDER BY price_normalized_eur ASC NULLS LAST` (uses `IX_ads_price_normalized_eur`)

### Seed-scale guard

The Seq-Scan assertion is **skipped** (with a WARNING) when the published-ad count is below `SEED_SCALE_MIN_ROWS` (10k). This prevents false positives on small datasets where a sequential scan is the optimal plan. To seed the dev DB with enough data:

```bash
make up   # the dev compose stack seeds >10k ads automatically
```

## Index Decision Rule

> **Rule (rules.md:227):** If `profile_queries` reports a `Seq Scan` on the `ads` table at seed scale, add an index **before** tuning the query.

### Diagnosis flow

```
cProfile shows slow search path?
  └─ Yes → profile_queries
            ↓
      EXPLAIN (ANALYZE, BUFFERS) on ads table
            ↓
      Seq Scan on ads detected?
        ├─ Yes  → Add missing index  ──→ re-run profile_queries
        └─ No   → Tune query text / reduce joins
```

### Common index candidates

| EXPLAIN finding | Likely missing index | Pattern |
|---|---|---|
| `Seq Scan on ads` for `search_vector_ru @@` | `GinIndex(fields=["search_vector_ru"])` | `IX_ads_search_gin_ru` (already exists on the model) |
| `Seq Scan on ads` for `category_id IN (...)` | Composite B-tree on `(status, category_id, -published_at)` | `IX_ads_pub_listing` (already exists) |
| `Seq Scan on ads` for `price_normalized_eur >=` | Partial B-tree on `price_normalized_eur` | `IX_ads_price_normalized_eur` (already exists) |
| `Seq Scan on ads` for `city_id =` only | Composite B-tree on `(status, city_id, -published_at)` | **Add** if not present |

Index definitions live in `apps/ads/models.py` (`Ad.Meta.indexes`). Adding a new index requires a migration — run `python manage.py makemigrations ads` after updating the model, then re-run `profile_queries` to confirm the plan switches from Seq Scan to Index/Bitmap Index Scan.
