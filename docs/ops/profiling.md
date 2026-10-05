# Profiling & Indexing Review

> **Purpose:** Establish a repeatable profiling cadence for the search and listings hot paths, using both Python-level cProfile and PostgreSQL `EXPLAIN (ANALYZE, BUFFERS)`.
> **Tools:** `scripts/profile_search.py` (cProfile), `profile_queries` management command (EXPLAIN), `PerformanceSLO` constants (`src/benchmark/constants.py`)
> **Spec:** `docs/99-agent/rules.md:224-228` (Profiling Rules)
> **Updated:** 13-PERF-015 (validated 2026-09) — the `profile_queries` description now matches the tool BLOCK 3 shipped.

## Overview

Two complementary profiling tools cover the ad search/listing critical path:

| Tool | What it measures | When to use |
|---|---|---|
| `profile_search.py` (cProfile) | Python-level call counts and cumulative time — middleware, ORM, FTS, SWR cache, template rendering | Before optimizing a hot path; diagnosing latency regressions in the application layer |
| `profile_queries` (EXPLAIN ANALYZE) | PostgreSQL query-plan nodes, actual row counts, buffer hits/reads | When a hot path is confirmed via cProfile; verifying index usage before tuning query text |

`make profile` runs **`scripts/profile_search.py`** (the cProfile harness) — it does
**not** run `profile_queries`. The two tools are separate entry points with
separate invocation sections below.

`profile_queries` asserts "no Seq Scan on the `ads` table" **only when the
measurement is meaningful**, and it now fails loudly when it is not:

- It takes a `--min-rows` threshold (default `SEED_SCALE_MIN_ROWS`, `10000`).
  This is a **table-size** axis, not a match-count axis: below the threshold the
  planner may legitimately prefer a sequential scan, so the assertion would be
  vacuous.
- Below the threshold (and without `--dry-run`) the command writes that the
  **measurement did NOT happen** and **exits non-zero** (`CommandError`). It
  never prints a clean-run verdict it did not earn. The previous behaviour — a
  green "Profiling complete" line and exit 0 while the assertion was skipped —
  was removed by 13-PERF-012b/13-PERF-015 (BLOCK 3).
- What it **can** tell you: whether the planner picks a sequential scan on
  `ads` for the representative shapes, at the sampled table size.
- What it **cannot** tell you: it does not measure match count (FTS cost scales
  with how many rows match, not how many rows exist), and it says nothing about
  a run that skipped — check the exit code, not the log line.

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
# Start dev stack (web :8000 + test DB :5433). This seeds SEED_ADS ads — the
# compose default is 600, NOT >10k — so profile_queries will report that the
# measurement did not happen and exit non-zero at that size.
make up
```

To make the assertion meaningful, seed a production-like dataset at or above
the threshold before running `profile_queries` (the nightly `query-profile` job
seeds 10000 published ads and is the model):

```bash
# Inside the dev web container:
python -m manage.py seed --ads 10000 --force
```

The earlier claim that "the dev compose stack seeds >10k ads automatically" was
false: `docker-compose.yml` sets `SEED_ADS=${SEED_ADS:-600}`, so `make up`
seeds 600 ads (13-PERF-015 validated 2026-09).

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

# Override the search term, table, threshold, or skip execution:
python -m manage.py profile_queries --query "велосипед"
python -m manage.py profile_queries --table ads
python -m manage.py profile_queries --min-rows 50000   # lower/raise the table-size threshold
python -m manage.py profile_queries --dry-run          # print SQL only, no EXPLAIN execution

# In Docker (test environment):
docker compose --project-name mko-bazuna-test -f docker-compose.yml -f docker-compose.test.yml \
  run --rm test python -m manage.py profile_queries
```

### Representative queries

The command resolves a **real** `city_id` and `category_id` from the database
(the lowest-id row with a PUBLISHED ad / with an active category) before
compiling the shapes, so each filter is non-empty — the old `city_id=1` /
`category_id__in=[1, 2, 3]` literals named rows that need not exist. If either
cannot be resolved the command stops rather than falling back to a literal.

It EXPLAINs these patterns, derived from the search/listings views:

1. **FTS search** — `SearchRank` + `@@ tsvector` filter on `search_vector_ru` (uses `IX_ads_search_gin_ru` GIN index)
2. **FTS search count** — the FTS-filtered count path the search view runs at/over the cache cap (`_resolve_search_count`)
3. **Listing** — `status=PUBLISHED` ordered by `-published_at` (uses `IX_ads_pub_listing`)
4. **Listing, resolved city + category** — `status=PUBLISHED` + the resolved `city_id` and `category_id`
5. **Filter by city** — `status=PUBLISHED` + `city_id` (uses `IX_ads_pub_listing`)
6. **Filter by category subtree** — `status=PUBLISHED` + `category_id` (uses `IX_ads_pub_listing`)
7. **Filter by price range** — `status=PUBLISHED` + `price_normalized_eur` range (uses `IX_ads_price_normalized_eur`)
8. **Sort by price** — `ORDER BY price_normalized_eur ASC NULLS LAST` (uses `IX_ads_price_normalized_eur`)

### Seed-scale guard

Below `--min-rows` (default `SEED_SCALE_MIN_ROWS`, 10000) the command reports
that the **measurement did NOT happen** and **exits non-zero** — it does not
print a success line. This prevents a false "no Seq Scan" verdict on small
datasets where a sequential scan is the optimal plan. `--dry-run` is exempt
(it prints SQL and never asserts).

Seed a production-like dataset at or above the threshold:

```bash
# Seed 10000 ads explicitly — make up alone seeds only 600 (SEED_ADS default).
python -m manage.py seed --ads 10000 --force
```

## Profiling the on-demand price-recompute sweep

`recompute_normalized_prices` (apps/currencies) re-derives
`price_normalized_eur` for every non-draft ad after an exchange-rate change.
It is **absent from both `HOURLY_COMMANDS` and `DAILY_COMMANDS`**, so the
scheduler never runs it — it executes **only on demand**. Unlike the two tools
above, it is a **write** sweep, so what matters is its statement count, its
`SELECT ... FOR UPDATE` batch count, and its wall time, not a query plan.

Its transaction shape (`03-DB-008`) is **out of scope for performance work
here**: it is one session-scoped advisory lock (`pg_advisory_lock`), a
`select_for_update()` read of `_BATCH_SIZE` (500) rows per batch, and a
per-batch `COMMIT`, so row locks are released as the sweep progresses. This
section **measures and records** that cost; it does not change the command.

**Measured cost** (13-PERF-013 validated 2026-09). Method: a
`CaptureQueriesContext` around a `call_command("recompute_normalized_prices")`
run against a freshly seeded test database, with every row made stale first so
each batch writes and locks. The exact command is `python -m
manage.py recompute_normalized_prices`; the dataset is `seed --ads N --force`.

| Published ads | Statements | `SELECT ... FOR UPDATE` batches | `UPDATE`s | Wall time |
|---|---|---|---|---|
| 2 000 | 22 | 5 (4 × 500 + 1 empty terminator) | 4 | 0.93 s |
| 10 000 | 86 | 21 (20 × 500 + 1 empty terminator) | 20 | 4.5 s |

The sweep is linear in the row count at a fixed batch size: one
`SELECT ... FOR UPDATE` and one `UPDATE` per 500 rows, plus one terminating
empty `SELECT`. At 10 000 rows the per-batch hold averages ~225 ms, consistent
with the worst-batch ≈358 ms recorded for this command in
`docker-deployment.md` (`LOCK_TIMEOUT_SECONDS` is 10 s, so a batch holds well
under the bound).

**A `statement_timeout` is not added here.** A statement and a lock wait are
different bounds; the per-batch shape keeps each batch short, and bounding lock
waits is `03-DB-004` (owner: phase 03), which is why this section records the
cost rather than adding a timeout. Note for whoever implements that: the ~1 s
row-lock holds in `test_recompute_command.py::TestRecomputeRowLockConcurrency`,
`test_sweep_archive.py`, and `test_transition_concurrency.py` break under a
**global** lock timeout below that — phase 03 must choose per-role.

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
