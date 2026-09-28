# Phase 13 — Performance Audit Report

## Audit Context

| | |
|---|---|
| **Phase** | 13 — performance, query plans, caching, load/stress testing |
| **Scope** | Query plans & index availability, N+1 access patterns, over-fetching & serialization, cache effectiveness, connection-pooling strategy, background-job cost, load/stress testing |
| **Mode** | `problems_only = TRUE` — only findings are reported; no PASS/resolved inventory |
| **Stack under test** | Python 3.14 · Django 5.2 LTS · PostgreSQL 18 · gunicorn sync WSGI (3 workers) · aiogram 3.x bot · hourly/daily scheduler · Redis cache · native PG FTS |
| **Date** | 2026-09-28 |
| **Findings** | **15** — 1 CRITICAL, 5 HIGH, 6 MEDIUM, 3 LOW |
| **Architecture-affecting** | PERF-002, PERF-003, PERF-006, PERF-011 |

## Severity bands used in this report

The Phase 13 brief in `.kilo/commands/audit/phases/13-audit-performance.md` (§5) pre-declares every zone "RESOLVED (no finding filed)". That rubric does not survive runtime verification: it is the *previous* cycle's conclusion, and this phase was explicitly asked to grade latency, query plans, row-count amplification and fix cost — none of which the prior cycle measured. The bands below are therefore the standard ones, stated explicitly so severity is auditable.

| Band | Meaning in this phase |
|---|---|
| **CRITICAL** | A deployed guard is inert, so a known production performance risk is unenforced and regressions are silent. |
| **HIGH** | A demonstrated runtime cost that breaches the SLO or monopolises the shared database at a plausible data volume, on a path that is on in production. |
| **MEDIUM** | A demonstrated cost that is real but conditional on data volume, catalogue size, or a default-off flag; or a structural property that will bite as the product grows. |
| **LOW** | Correctness of the performance *discipline* itself — documentation and test guards that no longer describe reality. |

## How this was verified

No production data exists, so a scale-realistic dataset was built in an **isolated** PostgreSQL 18 container (`audit13-pg`, host port 5545, torn down afterwards) rather than on the shared `mko-bazuna-test` instance — which was repeatedly crash-recovered by a parallel agent's SRCH-001 DoS reproduction while this phase ran.

**Dataset** (`audit13_perf`): 60 000 `PUBLISHED` ads · 205 MPTT categories (the shipped catalog) · 5 015 cities · 500 sellers · 120 000 `ad_features` rows (6 features/ad) · 29 listing features · 200 007 `analytics_events` · `ads` = 128 MB. Migrations applied from real migration modules under `config.settings.dev`; `setup_search_triggers` applied and trigger presence **verified via `pg_trigger`** before any FTS result was trusted (the method trap documented in `.ai/audit/08-search-fts/findings.md`).

**Instrumentation:** `EXPLAIN (ANALYZE, BUFFERS, TIMING OFF)` on the exact SQL Django emits; `django.test.Client` through the real URLconf + middleware with `CaptureQueriesContext` for per-request SQL counts; `connection.execute_wrapper` + `traceback` to attribute repeated queries to exact template/view call sites; `ManagementCommand` invocation under `CaptureQueriesContext` for job cost; and a real `locust 2.46.6` run reproducing the CI gate byte-for-byte.

Absolute numbers are single-node, warm-cache, `DEBUG=1`, no nginx/TLS, co-located database — pessimistic. **Ratios, query counts, statement sizes and parameter counts are hardware-independent** and are the load-bearing evidence in every finding.

## What is genuinely well-implemented

Recorded so the findings are read in context, not as a list of complaints:

- The search result cache is **correctly invalidated**. `search.py:152-162` invalidates on ad save/delete, status transitions, moderation publish, image changes and city-default changes. This is the part most projects get wrong, and it is right here. (`SRCH-006`/`SRCH-007` cover the version-counter half; not re-litigated below.)
- `prefetch_related("features", "images")` is present and does collapse to 1 query each on the listing path — measured 4 queries for a 24-row page, vs 27 with the prefetch removed.
- `annotate_favorites` uses a correlated `Exists` on the page query rather than a per-card lookup — the right pattern.
- The FTS trigger keeps `ads` denormalised, so search does not join `ad_features` for text.
- `prepare_threshold: None` in both DB branches (`base.py:245-251`, `base.py:120-129`) is correct for pgbouncer in transaction and statement pooling modes. `CONN_MAX_AGE` is set only in the discrete branch, but Django's default is `0`, so behaviour is identical — **not a finding**.
- Index coverage is genuinely good: `IX_ads_status_published_desc` (`ads(status, published_at DESC)`) serves the default sort via `Parallel Index Scan Backward` + `Gather Merge`; FTS uses the GIN index; `IX_analytics_evt_ts(event_type, timestamp)` exists; every FK the hot path touches is indexed.

## Findings

### PERF-001 — The only CI-gated latency gate reads the wrong CSV column and matches no row, so it always passes

**Severity:** CRITICAL · **Zone:** load/stress testing · **Status:** CONFIRMED by reproduction

**Evidence.** `.github/workflows/ci.yml:466-473`:

```bash
ACTUAL_P95=$(cat /tmp/locust-results_stats.csv | awk -F, 'NR>1 && $1=="Total" {print $6}' | head -1)
if [ -n "$ACTUAL_P95" ] && [ "$(echo "$ACTUAL_P95 > $P95_SLO" | bc)" = "1" ]; then
  echo "::error::p95 ..."
  exit 1
else
  echo "p95 ${ACTUAL_P95}ms within SLO"   # <- unconditional
fi
```

`locust` is declared `>=2.20.0` in `pyproject.toml` and locked at **2.46.6** (`uv.lock`). In that version `StatsCSV.requests_csv_columns` (verified by reading `locust.stats.StatsCSV.__init__`) is:

```
Type, Name, Request Count, Failure Count, Median Response Time, Average Response Time,
Min Response Time, Max Response Time, Average Content Size, Requests/s, Failures/s,
50%, 66%, 75%, 80%, 90%, 95%, 98%, 99%, 99.9%, 99.99%, 100%
```

Two independent defects:

1. **`$1 == "Total"` matches zero rows.** Column 1 is the HTTP `Type` (`GET`); the aggregate row is written by `csv_writer.writerow(chain([stats_entry.method, stats_entry.name, …], …))` and its `name` is the literal **`Aggregated`**, with an *empty* `method`. A real `_stats.csv` produced against the 60 000-ad instance:
   ```
   ,Aggregated,15,3,1800,3655.4254146680855,16.111422039102763,8576.658662990667,...
   ```
   `awk -F, 'NR>1 && $1=="Total"' | wc -l` → `0`.
2. **Even if the row matched, `$6` is `Average Response Time`, not p95.** The true 95th percentile is column 16 (`8600` above; column 6 is `3655`).

Replaying the exact CI shell logic against that real file:

```
ACTUAL_P95=[]
PASS: p95 ms within SLO
```

The `p95 ${ACTUAL_P95}ms` string in the log line is visibly empty. The gate **cannot fail on latency** — it reports "within SLO" while the measured p95 was **8 600 ms against a 500 ms SLO (17×)**. The CI `Step Summary` line `"p95=${ACTUAL_P95}ms (SLO ${P95_SLO}ms)"` is likewise permanently empty, so the SLO burn rate is not even observable in CI.

The `locustfile.py:88-95` `_assert_p95` event hook (`environment.process_exit_code = 1` on a real p95 breach) **is** correct and does set the process exit code, so it is the effective gate. The awk block is dead code that a reviewer would reasonably read as the gate.

**Impact.** The phase brief claims (§4.5) that CI "asserts p95 < `PerformanceSLO.P95_SLO_MS`, so any regression against the SLO fails the build with a non-zero exit code." In practice the build is green at any latency the process can survive. Every performance number this project believes it is protecting is unprotected. This is the highest-leverage finding in the phase: it is the control that would have caught PERF-002 through PERF-006.

**Recommendation.** Do not parse the CSV with positional `awk`. Either delete the awk block and rely on the (correct) event hook, or parse by header name:

```bash
ACTUAL_P95=$(python -c "
import csv
with open('/tmp/locust-results_stats.csv', newline='') as f:
    for row in csv.DictReader(f):
        if row['Name'] == 'Aggregated':
            print(int(float(row['95%'])))
")
```

and add a CI step asserting the value is non-empty, so a future locust format change fails loudly instead of silently disabling the gate.

**Effort:** trivial · **Priority:** recommended (treat as mandatory — a green-but-blind gate is worse than no gate)

---

### PERF-002 — `?features=` amplification is a *memory* blowup that SIGKILLs the PostgreSQL backend and forces full-instance reinitialisation

**Severity:** HIGH · **Zone:** query plans & index availability · **Status:** CONFIRMED — the plan/row-count grading phase 08 deferred

**Cross-reference.** `SRCH-001` (phase 08, CRITICAL) established that `?features=` is unbounded, joins 120+ tables, and measured ~30 s on a 100-ad table. This is **not a re-file**. Phase 08 explicitly left latency, query plan and row-count amplification to this phase. What is new is the *mechanism*, which changes both the severity argument and the fix: the failure is not a slow query, it is an **out-of-memory kill of the database process**.

**Evidence** — 60 000 published ads / 120 000 `ad_features` rows, counting `ListingsQuery.build_queryset(...).count()`, i.e. the exact query `Paginator` issues:

| `features=` | SQL bytes | `JOIN` count | matching ads | `COUNT(*)` ms |
|---:|---:|---:|---:|---:|
| 1 | 2 305 | 5 | 60 000 | 89.0 |
| 2 | 2 441 | 7 | 60 000 | 30.2 |
| 3 | 2 577 | 9 | 60 000 | 67.7 |
| 5 | 2 861 | 13 | 60 000 | 78.4 |
| 8 | 3 287 | 19 | 60 000 | 150.4 |
| 12 | 3 855 | 27 | 60 000 | 386.5 |
| 20 | 4 991 | 43 | 60 000 | 1 404.1 |
| 29 | 6 269 | 61 | 60 000 | 4 803.7 |
| **60** | — | — | — | **backend killed** |

**Growth is superlinear, not linear.** 12→20 features is 1.67× the input and 3.6× the time; 20→29 is 1.45× the input and 3.4× the time. The reason is visible in the plan: the planner emits **nested-loop joins with a `Memoize` node over `ad_features`**, stacked one per feature. The join tree is a *product*, not a sum — this is the row-count amplification the brief asked to confirm. The innermost `ad_features` scan reports a constant `rows=16552`, which is exactly the point: the multiplication happens *above* it, so reading any single plan node understates the cost.

**Failure mode, and why it matters more than "slow".** At 60 features the backend is terminated:

```
server process (PID 87) was terminated by signal 9: Killed
database system was interrupted; last known up at ...
performing immediate shutdown because of crash of another server process
database system is ready to accept connections
```

`signal 9` is a **SIGKILL from the OOM killer** — not `statement_timeout`, not a stack-depth error, not PostgreSQL's own guard. The container has no memory limit (`HostConfig.Memory = 0`) and `work_mem` is the 4 MB default; the nested-loop plan's per-worker state plus the 24 MB temp spill from PERF-006 exhaust the host, and the kernel takes out the backend. The consequence is not one slow request: it is **every in-flight connection dropped and a full crash-recovery cycle of the one database shared by web, bot and scheduler**. Measured recovery in this environment: >200 s. On a host with a real memory budget the SIGKILL may not happen — but the plan then degenerates into unbounded temp-file writes against `pg_default`, an availability risk of the same class.

**Volume dependency.** Times scale with `|ads|` × `|ad_features|`. At the CI load-test scale (120 ads) this query is unremarkable; the growth is only visible past ~10⁴ ads — the same blind spot as PERF-012.

**Fix cost — deliberately minimal, per the project's avoid-overengineering rule.** `apply_filters` (`listings_query.py:136-142`) emits one `.filter(**{f"features__{key}": value})` per selected feature, i.e. N independent joins. The AND-of-features semantics is preserved exactly by a **single** join with a composite `IN`:

```python
if params.feature_slugs:
    queryset = queryset.filter(features__slug__in=params.feature_slugs)
    queryset = queryset.annotate(
        _m=Count("features", filter=Q(features__slug__in=params.feature_slugs))
    ).filter(_m=len(set(params.feature_slugs)))
```

That collapses N nested loops into one index scan plus a grouped count — a **constant-shape** plan regardless of how many `features=` values are sent. The remaining requirement is a **bound on the list length** (the availability half, owned by `SRCH-001`: `max_length` on the query-param list in the DTO layer, per project rule 11). Both are small, local, additive; no architectural change.

**Do not** add a planner hint, a `statement_timeout` (that is `DB-004`'s territory and treats the symptom), or a result cache (it would not survive the version-counter mechanism anyway).

**Effort:** small (DTO bound) + small (single composite join) · **Priority:** recommended

---

### PERF-003 — `rollup_daily_metrics` spends 99.97 % of a 5-minute single transaction on a per-ad `update_or_create` loop

**Severity:** HIGH · **Zone:** background-job cost + N+1 access patterns · **Status:** CONFIRMED

**Evidence.** `apps/analytics/management/commands/rollup_daily_metrics.py:52-73`:

```python
aggregated = AnalyticsEvent.objects.filter(...)
if not aggregated:
    ...
aggregated = aggregated.values("ad_id").annotate(...)
for row in aggregated:                                    # <-- N
    obj, created = DailyAdMetrics.objects.update_or_create(   # <-- 2 queries each
        ad_id=row["ad_id"], date=yesterday,
        defaults={"views": row["views"], ...},
    )
```

`update_or_create` is a `SELECT` followed by an `INSERT` or `UPDATE`. The whole loop runs inside the single `transaction.atomic()` that also holds `pg_advisory_xact_lock(AdvisoryLockId.ROLLUP_DAILY_METRICS)`.

Measured with 200 007 `analytics_events` touching 60 000 distinct ads:

```
DailyAdMetrics rollup complete: 60000 created, 0 updated for 2026-09-27
[rollup] n_sql=8967   (Django query log capped: "Limit for query logging exceeded,
                      only the last 9000 queries will be returned")
[rollup] wall=304835 ms          <-- 5 minutes 5 seconds
[rollup] DailyAdMetrics rows written = 60000
```

The **aggregate query itself is 108 ms**:

```
Group  (actual rows=60000.00)  Buffers: shared hit=2341 read=1075
  ->  Gather Merge  (actual rows=200002.00)  Workers Planned: 2
Execution Time: 108.514 ms
```

So ~304 700 ms of 304 835 ms is the upsert loop: roughly **120 000 sequential round trips** (60 000 `SELECT` + 60 000 `INSERT`) on one connection with `CONN_MAX_AGE=0` — about 2.5 ms of pure per-statement overhead per row.

**Why it matters beyond the runtime.** The job holds a transaction advisory lock for the full 305 s, so a second tick blocks in `apps/core/utils/advisory_lock.py:74`, which per `DB-004` has no `lock_timeout` and logs nothing before acquiring. The bot and web tier share this database and compete for the same buffers and WAL bandwidth meanwhile. Cost is linear in active ads: 600 k ads ⇒ ~50 minutes in a single transaction.

**Fix.** The ORM can express this in one statement. `bulk_create(..., update_conflicts=True, update_fields=[...], unique_fields=["ad", "date"])` (Django ≥ 4.1; project is on 5.2) turns the loop into a single `INSERT … ON CONFLICT DO UPDATE`: 120 000 statements → 1, and 305 s → a few seconds. `DailyAdMetrics` already carries a unique constraint on `(ad, date)`, so this is a drop-in.

Not a re-file of `DB-008` (whole-sweep transactions in `archive_sweep` / `recompute_normalized_prices`); this is a different command with a different defect — an N+1 upsert loop, not a transaction boundary.

**Deliberately not filed:** `rollup_daily_metrics.py:57` uses `timestamp__date=yesterday`, wrapping the column in a function, which is normally non-sargable. At 200 k rows it measured **108.5 ms** (parallel `Gather Merge` + `Group` + `Sort`) versus **117.3 ms** for the sargable `timestamp >= d AND < d + 1` form (sequential `HashAggregate`). The non-sargable form is *faster* here because it parallelises. Rewriting it would be a regression.

**Effort:** small (loop → one `bulk_create`) · **Priority:** recommended

---

### PERF-004 — `render_trust_badge`'s prefetch detection can never fire for a reverse OneToOne, costing one failing `SELECT` per ad card

**Severity:** HIGH · **Zone:** N+1 access patterns · **Status:** CONFIRMED, root-caused

**Evidence.** `src/backend/templates/ads/partials/ad_list.html:122` renders `{% render_trust_badge ad.user %}` once per card. The tag's fast path (`apps/trust/templatetags/trust_tags.py:70-77`):

```python
prefetched_cache = getattr(user, "_prefetched_objects_cache", None)
if isinstance(prefetched_cache, dict) and "trust_score" in prefetched_cache:
    trust_score = user.trust_score
else:
    try:
        trust_score = SellerTrustScore.objects.get(user=user)
```

`SellerTrustScore.user` is `OneToOneField(User, related_name="trust_score")` (`apps/trust/models.py`), so `user.trust_score` is a **reverse** one-to-one. Django's `prefetch_related` batches it correctly — measured, 24-row page: **1** `seller_trust_scores` query, not 24 — but it does **not** populate `user._prefetched_objects_cache["trust_score"]`; the object is attached to the descriptor's own cache instead. Measured directly:

```
[A] n_sql=4
    user._prefetched_objects_cache = {}          <-- always empty
    'trust_score' in user.__dict__ = False
[B] 24 prefetched users  -> seller_trust_scores SQL = 24
[C] 24 non-prefetched    -> seller_trust_scores SQL = 48   (2 per card)
```

So `"trust_score" in prefetched_cache` is **always False** and the tag always takes the `else` branch. The comment at `trust_tags.py:70-71` — *"When the relation has been prefetched (e.g. `prefetch_related('user__trust_score')`), accessing `user.trust_score` does **not** hit the database — so the fallback is skipped entirely"* — is factually wrong for the reverse-OneToOne case.

The extra query only becomes *visible* when the row is **absent**: if a `SellerTrustScore` exists, `getattr` resolves it from the descriptor cache; if not, `ReverseOneToOneDescriptor.__get__` raises `RelatedObjectDoesNotExist` (`related_descriptors.py:534`), the `except` branch fires, and the code issues `SellerTrustScore.objects.get(user=user)` — **a query that is guaranteed to fail** — whose `DoesNotExist` is then swallowed by a second `except`.

Per-request SQL on a warm `/`:

```
GET /        n_sql=46   seller_trust_scores=25   categories=15
GET /search/ n_sql=60   seller_trust_scores=25   categories=15
```

and the call site is unambiguous:

```
x24  trust||SELECT "seller_trust_scores".…  trust_tags.py:77 <- library.py:324 <- base.py:979
x25  (the 25th is the batched prefetch)
```

Sensitivity to the row's presence — created `SellerTrustScore` rows for exactly this page's 24 sellers and re-ran:

```
GET / with 0 persisted score rows                          : 25 seller_trust_scores queries
GET / after creating score rows for this page's sellers     :  1 seller_trust_scores queries
```

**How often is the row absent in production?** `TrustCalculator.calculate_and_save` is called from `auto_moderation.py:282` on every publish, so most sellers *do* have a row. But it is wrapped in a bare `except Exception` that logs a warning and continues (`auto_moderation.py:283-286`), and admin-created ads, `moderation.admin_actions.approve_ad`, and the seed path bypass it. Failure mode: a seller whose trust-score write failed once, or an ad published by any non-auto-moderation path, permanently injects a failing query into **every page of every listing it appears on**.

**Why the existing guards are green.** Both N+1 regression guards seed the row, which is exactly what hides the defect:
- `apps/ads/tests/test_ad_detail_queries.py:47,65` — `SellerTrustScore.objects.create(user=seller, …)` in the test body, then `assert len(trust_queries) <= 1`.
- `apps/search/tests/test_search_query_count.py:22-31` — bound raised to **100** with the rationale *"Bound raised from 35 to 100 in response to 13-PERF-004 recommendation #3"*, i.e. the guard was widened to accommodate the N+1 rather than the N+1 being fixed (see PERF-014).

**Fix.** The prefetch is fine; the *check* is not. Read the value and treat "no row" as the answer:

```python
trust_score = getattr(user, "trust_score", None)   # prefetch cache OR one query, never 2
```

and drop the `.get()` fallback entirely — `related_descriptors` already caches the miss for the request when the relation was prefetched, and issues exactly one query when it was not. This deletes the N+1 **and** the incorrect comment. Then restore `test_search_query_count.py`'s bound to something meaningful.

**Effort:** trivial (tag) + trivial (test bound) · **Priority:** recommended

---

### PERF-005 — The daily `send_alerts` job runs one full FTS query per saved search inside one lock-held transaction

**Severity:** HIGH · **Zone:** background-job cost + N+1 access patterns · **Status:** CONFIRMED

**Evidence.** `apps/search/management/commands/send_alerts.py:93-107` holds a single `transaction.atomic()` around the whole dispatch loop (required — it must publish its advisory-lock marker atomically per `DB-004`'s reasoning), and inside it calls `find_matching_ads(saved_search)` once per saved search. `apps/search/services/alert_query.py:43-99` builds a **fresh** FTS queryset for each call:

```python
queryset = Ad.objects.filter(status=AdStatus.PUBLISHED).select_related("category", "city")
if saved_search.query:
    search_query = SearchQuery(saved_search.query, search_type="websearch", config=config)
    queryset = queryset.annotate(rank=SearchRank(F(vector_field), search_query)) \
                         .filter(**{vector_field: search_query}).order_by("-rank")
```

40 active saved searches on the 60 000-ad dataset:

```
active saved searches: 40
send_alerts --dry-run: n_sql=46 for 40 saved searches (1.15 per search)  wall=7577 ms
DRY RUN: Would process 40 users, 40 saved searches, 120 total matches
```

**190 ms per saved search.** Because the vectors are per-language and each saved search carries its own `query` string, they cannot be collapsed into a single `IN`-style query as written. But the loop is not bounded: cost is `O(|saved_searches| × FTS_cost)`, all inside one transaction holding `pg_advisory_xact_lock(AdvisoryLockId.SEND_ALERTS)`. 1 000 saved searches ⇒ ~190 s of transaction, every day at 08:00 UTC, with no `statement_timeout` to bound it (`DB-004`) and no `lock_timeout` on the wait side.

Secondary cost on the same path: `record_notifications` calls `bulk_create(..., ignore_conflicts=True)` **per saved search** (`immediate_alerts.py:98-101`), each with a single row, immediately followed by `saved_search.save(update_fields=[...])` — 2M extra statements for M matches.

**Related but dormant — stated explicitly, not filed separately.** `find_matching_saved_searches` (`alert_query.py:134-163`) has the same shape inverted: it iterates **every** active saved search and, for each, issues `_ad_matches_vector` → one `Ad.objects.filter(pk=…, vector=…).exists()` query, plus a `Category.objects.get()` + `get_descendants()` per search with a category. It runs from `deliver_immediate_alerts` via a `post_save` signal **on the ad-publish path** — inside the bot's request handler. Severity is limited because `IMMEDIATE_ALERTS_ENABLED` defaults to `False` (`moderation/signals.py:66`), and I did not reproduce it enabled. When the flag is turned on, publish latency becomes `O(active_saved_searches)`.

**Fix — the cheap, obvious one first.** Invert the daily loop the way the publish path already does: instead of "for each saved search, find matching ads", group the distinct non-empty `query` strings by `language`, run **one** FTS query per (language, query) pair, and intersect the result sets in Python against the remaining per-search structural filters. With 40 saved searches typically holding a handful of distinct queries this reduces 40 FTS scans to a handful. If judged premature, the honest interim is a `--limit` / batched loop so the transaction can commit and yield, plus per-search progress logging (the command emits nothing until the end).

Separately, batch the `record_notifications` + `save()` pair across all matches at the end of the loop.

**Effort:** small (batching) / small (per-search transaction yield) · **Priority:** recommended

---

### PERF-006 — For any query with ≥ 1 000 matches the search cache is bypassed for the count, and the cached page itself already exceeds the p95 SLO

**Severity:** HIGH · **Zone:** cache effectiveness · **Status:** CONFIRMED

**Evidence — the count is recomputed on every hit.** `apps/search/views/search.py:126-131` stores at most `SEARCH_CACHE_MAX_HITS = 1000` ids, and `_resolve_search_count` (`search.py:307-317`) branches on exactly that:

```python
if cached_ids is not None and len(cached_ids) < SEARCH_CACHE_MAX_HITS:
    if len(cached_ids) == 0:
        return 0
    base_qs = ListingsQuery.build_queryset(params)
    return base_qs.filter(pk__in=cached_ids).count()   # cheap
# else: fall through and build a FRESH FTS queryset
```

The producer slices in Python — `list(filtered_qs.values_list("id", flat=True))[:1000]` — so `len(cached_ids)` can be *exactly* 1 000 but never more. Therefore **for any query with ≥ 1 000 matches, every cache hit takes the `else` branch and re-runs the full FTS `COUNT(*)`**. Measured on 14 194 matches:

```
[2] SEARCH FTS  COUNT_ms=52.1   n=14194
[3] _resolve_search_count on the 'at the 1000 cap' branch: same 52-64 ms
```

The cache provides **zero** benefit for the count precisely in the broad-query case it exists to serve, and pays 52–64 ms of PostgreSQL time per request for it.

**Evidence — the cached page is still over budget.** Real HTTP requests through the URLconf on the 60 000-ad dataset (`q=велосипед`, 14 194 matches):

```
COLD (cache empty)  /search/?q=велосипед  :  781 ms wall, 54 SQL
WARM (cache hit)    same URL              :  510 ms wall, 54 SQL
slowest single SQL on the WARM path       :  100 ms (the FTS producer / count)
```

`PerformanceSLO.P95_SLO_MS = 500`. A **warm** search — the supposedly fast path — is 510 ms for one request, and 54 SQL statements, on a warm cache with the database co-located. The cache buys 35 %.

**Why the FTS page is expensive — plan evidence.** The 24-row page query has no index that can satisfy `ORDER BY ts_rank DESC, published_at DESC` followed by `LIMIT 24`, so PostgreSQL must evaluate the rank for **every** match and top-N sort:

```
Sort  (actual rows=14194.00)  Sort Key: rank DESC, published_at DESC, id DESC
      Sort Method: top-N heapsort  Memory: 97kB
Buffers: shared hit=9376 read=1682
Execution Time: 282.300 ms
```

Without the `LIMIT` (the cache producer) the same shape spills:

```
Sort Method: external merge  Disk: 7952kB
temp read=2893 written=2896            <-- ~22 MB of temp I/O per cold query
Execution Time: 106.680 ms
```

`work_mem` is the PostgreSQL default (4 MB; not set anywhere in `src/` or `docker/`), so any sort whose projected width exceeds 4 MB goes to disk. At 14 k matches it already does, and it scales with match count: a term matching 100 k ads sorts ~165 MB of temp data per request.

**Fix — three small, independent changes, in priority order:**

1. **Push the `LIMIT` into SQL.** `filtered_qs.values_list("id", flat=True)[:SEARCH_CACHE_MAX_HITS]` instead of slicing the materialised list. Changes the plan from a full sort to `top-N heapsort` and stops the 22 MB temp spill. One line.
2. **Stop recomputing the count at the cap.** Return `SEARCH_CACHE_MAX_HITS` (or `+1` to render the existing "Over 1 000 results" notice at `ad_list.html:92-96` truthfully) instead of rebuilding the FTS queryset. The `results_truncated` flag already exists for exactly this.
3. **Raise `work_mem` for the web/scheduler roles**, or set it per-session in the connection `OPTIONS`. At 4 MB the default is below what this schema's sorts need; 32–64 MB for a 3-worker sync deployment is cheap and bounded. This is *not* a substitute for (1) — it only moves disk writes to memory.

**Not recommended:** an index on `ts_rank` (the expression is query-dependent and would not generalise across `websearch` configs) and a larger `SEARCH_CACHE_MAX_HITS` (that makes PERF-010 worse).

**Cross-reference.** `SRCH-014` (phase 08) already records that `_recompute_and_store` runs **inline in the request** despite the docstring claiming a background recompute. Not re-filed; the cold-miss amplification consequence is PERF-007.

**Volume dependency:** FTS timings depend on match count (14 194 here, chosen by the term). Plan shapes, SQL sizes and query counts are volume-independent; the millisecond figures are not. At the CI load-test's 120 ads the query is trivially fast (PERF-012).

**Effort:** trivial (LIMIT) + small (count branch) + small (`work_mem`) · **Priority:** recommended

---

### PERF-007 — The single-flight lock provides no protection on a cold cache miss; every concurrent loser runs the full FTS query

**Severity:** MEDIUM · **Zone:** cache effectiveness (stampede) · **Status:** CONFIRMED

**Evidence.** `apps/core/utils/swr_cache.py:57-77`:

```python
if not cache.add(lock_key, "1", timeout=LOCK_TTL):
    return default
try:
    value = compute()
    cache.set(cache_key, value, timeout=TTL)
    return value
finally:
    cache.delete(lock_key)
```

The docstring at `:48-49` states: *"If another worker is already computing, this returns `default` immediately. Callers should fall back to a direct computation in this case."* That instruction is the defect. The lock serialises the **writer**; the **losers all execute `compute()` anyway** — it prevents 49 duplicate cache *writes*, not 49 duplicate FTS queries. It is not a stampede guard; it is a duplicate-write guard.

The only caller is the search view (`search.py:108-118`), and on a cold miss the fallback is `build_filtered_fts_ids(query=query)` — a 107 ms FTS query (PERF-006). With `gunicorn workers = 3` and the sync worker class this caps today at 3× rather than 49×, but the exposure scales directly with the worker count if the pool is ever widened, and `get_with_stale_revalidate` is a general-purpose helper that other call sites will adopt with the same misreading.

**Impact.** The realistic trigger is not a cold key but a *new* search term — exactly when a marketplace is most likely to receive concurrent identical requests (a shared link, a trending term, a crawler). The first 3 requests each pay 107 ms of FTS plus the 52 ms count of PERF-006.

**Fix — keep it simple, do not build a queue.** The fallback exists only so the request can be served. Two options, in preference order:

1. **Short retry, then serve stale.** On a lost lock race, sleep a few tens of milliseconds and re-`cache.get` the key (the holder is ~100 ms away). If still absent, fall back. Converts 3 concurrent FTS queries into 1 FTS query + 2 short waits, using only existing primitives.
2. **Correct the docstring and accept it.** If the fallback is genuinely wanted for correctness, say so plainly and drop the lock — it buys nothing for query load.

Option 1 is the better trade and stays within the avoid-overengineering rule; it is ~5 lines. Do **not** introduce a task queue for this: one shared search cache does not justify a broker, and Redis is already present for the cache.

**Effort:** trivial · **Priority:** recommended

---

### PERF-008 — The header context processor materialises the entire `cities` table into every page, and the search view adds a second uncached copy

**Severity:** MEDIUM · **Zone:** over-fetching & serialization · **Status:** CONFIRMED — volume-dependent, see caveat

**Evidence.** `apps/core/context_processors.py:98`:

```python
return {
    ...
    "cities": list(City.objects.order_by("name")),   # every row, every request
```

with the docstring at `:49-50` asserting *"A single indexed MPTT query is acceptable for the MVP (no per-request profiling concern)."* This is the assumption a performance audit is here to overturn, and it is now the single largest contributor to page weight.

`components/header_catalog.html:68-73` renders one `<li><button data-city-option="{{ city.slug }}">` pair per city on every page. Measured on 5 015 cities:

```
GET /            total bytes        : 2,893,850
GET /privacy/    total bytes        :    24,041      (no city dropdown)
<header>…</header> on /             : 2,633,123
<article> cards (24)                :   124,839      (~5 200 B/card — reasonable)
data-city-option attributes in <header> : 5,015
<li>  x5,023   <button> x5,028
<select> blocks: 3   (3,313 B total — not the culprit)
```

`GET /` returns **2.9 MB** for 24 cards; 2.63 MB of it is the city dropdown. Wall-clock: 420 ms warm, of which DB 109 ms and Python/template 311 ms (74 %). `list(City.objects.order_by("name"))` alone was 61 ms for 5 015 rows — the whole table crosses into Python as objects on every request, authenticated or not.

Separately, `apps/search/views/search.py:217-218` adds its **own** uncached copies on top of the context processor's:

```python
"save_search_cities": list(City.objects.order_by("name")),
"save_search_categories": list(Category.objects.filter(is_active=True).order_by("name")),
```

so a search request pays the city table twice.

**Volume caveat — read this before acting.** The shipped fixture `apps/seed/fixtures/cities.json` contains **15** records. At 15 rows this costs ~8 KB and ~0.2 ms; it is **not** a problem today. I injected 5 015 synthetic rows specifically to expose the scaling behaviour, and verified with `EXPLAIN` that the 61 ms is linear in row count. The finding is about the *unbounded, uncached, per-request* design, not a currently-observable cost. The 5 015 figure is my synthetic upper bound, **not** production volume — a real country dataset falls between the two and I could not measure it.

The asymmetry that makes this worth fixing rather than deferring: the **category** submenu is already served from a 24 h SWR cache (`apps/categories/views.py:60-68`, `cache_prefix="categories:submenu:"`) precisely because someone recognised this pattern for the other tree. The city list is the same shape with no cache and no bound.

**Fix — minimal, no schema change.** Cache the two context-processor lists under the same pattern the category submenu uses (they change only via `load_cities` / `load_catalog` management commands, so the existing `invalidate_by_prefix` + `SEARCH_CONTENT_VERSION_KEY` "bump a version integer" mechanism applies unchanged). Drop the duplicate `save_search_cities` in `search.py:217` and reuse the context-processor list. If a full country list is ever loaded, add `region` grouping so the header renders a collapsed list rather than 5 000 buttons — a template change, not a redesign.

**Effort:** small · **Priority:** recommended

---

### PERF-009 — `header_catalog.html` runs one `.exists()` per child category on every page, duplicating a tree that is already cached

**Severity:** MEDIUM · **Zone:** N+1 access patterns · **Status:** CONFIRMED

**Evidence.** `components/header_catalog.html:108` and `:199`:

```django
{% if cat.get_children.exists %}
    <button type="button" data-category-expand="{{ cat.slug }}" aria-controls="menu-{{ cat.id }}" …>
```

A related-manager `.exists()` in a template loop is a query, and it is not covered by `prefetch_related` (which the header does not use). The same pattern is in `components/categories/partials/mega_submenu.html:15`.

Attributed by wrapping the DB cursor in an `execute_wrapper` and capturing the Python stack:

```
GET /   n_sql=70   categories `.exists()` queries = 13
   x12  defaulttags.py:886 <- base.py:723 <- base.py:856 <- base.py:927
```

**12 round trips per page**, one per child category rendered in the header, growing linearly with catalog size. Per-request breakdown on the 60 000-ad dataset:

```
seller_trust_scores 25 | categories 14-15 | lookup_items 3 | cities 2
ad_features 1 | ad_images 1
```

**The redundancy that makes this a finding rather than a tuning note.** The *identical* category tree is already rendered by a view that caches its HTML for 24 h behind a 300 s stale-while-revalidate window:

```python
# apps/categories/views.py:60-68
html = get_with_stale_revalidate(
    build_submenu_html, CATEGORY_SUBMENU_CACHE_TTL,   # 86400
    cache_prefix="categories:submenu:",
    version_key=SEARCH_CONTENT_VERSION_KEY,
)
```

The project has already decided this tree is expensive enough to cache — then pays 12 uncached queries to rebuild a slice of it on every request, on top of a `list(Category.objects.root_nodes()…)` materialisation in the same context processor (`context_processors.py:94-96`).

**Fix.** Two options, both small:

- Add `prefetch_related("children")` to the `root_categories` queryset in the context processor. Django evaluates a prefetched `get_children` from cache without a query, so the `.exists()` becomes free. **One line**, removes 12 queries, fits the existing pattern. Recommended.
- Serve the header's expandable branches from the same cached submenu markup (`aria-controls="menu-{{ cat.id }}"` shows the two views are already designed to share ids). Better long-term shape, larger change.

**Effort:** trivial · **Priority:** recommended

---

### PERF-010 — The cache-hit restore sends a 35 KB statement with 1 000 `CASE…WHEN` arms and 3 003 bind parameters on every page view

**Severity:** MEDIUM · **Zone:** over-fetching & serialization · **Status:** CONFIRMED

**Evidence.** `apps/search/views/search.py:140-142` restores rank order with a positional `CASE`:

```python
ads = ads.filter(pk__in=cached_ids).order_by(
    Case(*[When(pk=pk, then=pos) for pos, pk in enumerate(cached_ids)])
)
```

Measured at the 1 000-id cap:

```
ids=1000  sql_len=35,134  params=3,003  WHEN=1000
```

Three costs, all hardware-independent:

1. **Parse/plan cost scales with the cached set, not the page size.** A 24-row page produces a 35 KB statement with 1 000 conditional branches in the `ORDER BY`, so the `Sort` node evaluates that key per candidate row — versus a ~2 KB class statement on the uncached path.
2. **The id list is sent twice** — once in `IN (…)` and once as 1 000 `WHEN` arms. 5 392 bytes of ids, doubled.
3. **3 003 bind parameters** pushes psycopg onto its prepared-statement path. `prepare_threshold: None` correctly disables server-side prepares for pgbouncer, so this is a parse cost, not a protocol failure — but it is paid on **every page view** of a cached search, so a user paging through results sends 35 KB of SQL per page.

**Interaction with PERF-006.** The `CASE` cost is highest exactly when the cache is most valuable (broad queries) and it partially offsets the win. This is why the warm `/search/` measurement lands at 510 ms.

**Fix — the obvious one.** `IN` does not preserve order in SQL, but the order is *already known*: it is the order of `cached_ids`. So the 1 000 `WHEN` arms only need to cover the 24 ids actually on the page:

```python
page_ids = cached_ids[bottom:top]                       # already ordered by rank
ads = ads.filter(pk__in=page_ids).order_by(
    Case(*[When(pk=pk, then=i) for i, pk in enumerate(page_ids)])
)
```

That cuts the statement from 35 KB to ~800 bytes without touching the cache format. The more thorough alternative is an `in_bulk(order)` map plus a Python sort of the 24 page ids, which makes the statement size independent of the cache cap entirely — 3× more work for the same benefit, so recommend the page-slice option.

**Effort:** trivial (page slice) / small (`in_bulk`) · **Priority:** recommended

---

### PERF-011 — Three sync gunicorn workers cap the whole web tier at 3 in-flight requests, and the SLO alerts cover only `/search/`

**Severity:** MEDIUM · **Zone:** connection pooling & capacity / SLO enforcement · **Status:** CONFIRMED (config), volume-dependent (capacity number)

**Evidence — the constant.** `gunicorn.conf.py`:

```python
bind = "0.0.0.0:8000"
workers = 3
worker_class = "sync"
```

The `sync` worker class handles exactly one request at a time, so **the entire web tier can serve at most 3 concurrent requests**, regardless of how many database connections, nginx workers, or host cores are available. nginx's `worker_processes` / `keepalive` cannot relieve this: they queue, they do not parallelise.

Measured per-request cost at 60 000 ads (warm cache, DB co-located, `DEBUG=1`, no TLS/gzip):

```
GET /            wall 586 ms   (cold template compile)   46 SQL
GET /            wall 420 ms   db 109 ms  python/template 311 ms (74 %)
theoretical max throughput at 3 sync workers  ~=  3 / 0.42 s  =  7.1 req/s
```

The request is **CPU-bound in template rendering, not I/O-bound** (74 % Python/template). That matters for the fix: adding database connections (PgBouncer) would not help, because the bottleneck is a single Python thread per worker. Only more workers, or an async worker class, moves it.

**Evidence — the SLO gap.** `docs/ops/prometheus-slo-alerts.yaml:61,96` scope both latency alerts to `handler="search:search"`:

```promql
django_http_response_duration_seconds_bucket{le="2.000", handler="search:search"}[14.4m]
```

`/` — `ads:listings` — is the highest-traffic page (the target of `view_listings` in the load test's `BuyerJourneyUser`, and `/?q=laptop` carries weight 3 of 9) and has **no latency SLO and no alert**, even though `PerformanceSLO.P95_SLO_MS` / `P99_SLO_MS` are written as generic constants. A 10× regression on the main listing page is invisible to the alert rules.

**Evidence — the connection-pooling premise.** The phase brief's premise table lists PgBouncer as *"profile-gated opt-in only (NOT on the default deploy path)"*. `CONN_MAX_AGE=0` plus 3 sync workers means at most 3 concurrent connections from web, plus 1 from bot and 1 from scheduler — 5 against `max_connections=100` (PG 18 default). **There is no connection-pool problem to solve at this worker count**, and filing one would be speculative. I am explicitly not filing it. The corollary matters: if the worker count is ever raised to fix the throughput ceiling, the pooling decision becomes live and must be revisited in the same change.

**Recommendation, in order of cost/benefit.**

1. **Extend the SLO alerts to `ads:listings`** (ideally a path regex rather than a single handler pin). A YAML change, costs nothing, closes the observability gap regardless of anything else. Do this first.
2. **Size `workers` deliberately.** `workers = 3` is a hard-coded constant unrelated to `WEB_CONCURRENCY` or CPU count. Make it env-driven (`int(os.getenv("WEB_CONCURRENCY", 3))`) so the deploy target can set it, then set it to match the host. Because the load is 74 % CPU, a worker count near the core count is the right shape.
3. **Only then** consider `sync` → `gthread`/`gevent`. This is a real behavioural change for a sync-WSGI project with file I/O in the image path (`ad_serve_image` uses `open()`) and should not be undertaken casually. Listed as a direction, not a prescription.

**Effort:** trivial (alerts) / small (env-driven workers) / large (worker class) · **Priority:** recommended

---

### PERF-012 — The load test's buyer journey targets URLs that are not routes, and `profile_queries` cannot run in any shipped environment

**Severity:** MEDIUM · **Zone:** load/stress testing · **Status:** CONFIRMED

Two independent defects in the load/profiling apparatus, both of which mean the exercise does not measure the product.

**12a — 33 % of the generated traffic 404s.** `src/benchmark/locustfile.py:74-89`:

```python
@task(2) def browse_category(self):     self.client.get("/c/electronics",     name="category-browse")
@task(1) def browse_subcategory(self):  self.client.get("/c/electronics/phones", name="browse-subcategory")
```

The category route is **`/category/<slug:category_slug>/`** (`apps/ads/urls.py:16`) — there is no `/c/` prefix in `config/urls.py` or any included URLconf. Verified against the running application:

```
404 /c/electronics
404 /c/electronics/phones
200 /
200 /?q=laptop
200 /?min_price=100&max_price=500
```

A real locust run against the 60 000-ad instance confirms it is not a rounding artefact:

```
Error report
   4  GET category-browse: HTTPError('404 Client Error: Not Found for url: category-browse')
Aggregated   15 requests, 3 failures (25.00 %)
```

`electronics` and `phones` are real slugs in the shipped catalog (both *child* nodes, not roots), so the fix is a one-line URL change per task, not a data problem. The consequence: category browse — arguably the most index-sensitive query shape in the product — is **not load-tested at all**, while a third of the load is spent on 404s that return in ~1 ms and pull the aggregate p95 *down*.

**12b — `profile_queries` is unrunnable as shipped and is not in CI.** `apps/core/management/commands/profile_queries.py`:

- `SEED_SCALE_MIN_ROWS = 10_000`, and `_scale_dataset()` returns early unless that many published ads exist. The CI load test seeds **120** ads (`ci.yml:414-424`); the dev `seed` command produces far fewer. **No environment in the repository ever creates ≥ 10 000 published rows**, so the command always exits early and the "no `Seq Scan on ads` at ≥10k rows" discipline is never exercised.
- The command is referenced only from `Makefile:165` and `docs/ops/profiling.md:43-63`. It is **not** in `.github/workflows/ci.yml`.
- Even when run, `_build_queries()` does not cover the production shapes it is meant to guard. It omits:
  - `user__is_declined=False`, which `ListingsQuery.build_queryset` adds as a join to `users` on every real request;
  - the `annotate_favorites` correlated `Exists`;
  - the `?features=` multi-select join entirely — i.e. the exact query that OOM-kills the server in PERF-002;
  - the cache-hit restore with its 1 000 `CASE` arms (PERF-010);
  - `_resolve_search_count`'s re-run at the 1 000 cap (PERF-006).

  A reviewer following `docs/ops/profiling.md:52-58` — *"run `profile_queries` after each change to filters, sorting, or pagination … record the seq-scan count in the review description"* — would get a clean report while a new sequential scan shipped on the production path.

**12c — the SLO-gate test.** `apps/search/tests/test_search_slo.py:30-47` (`TestSearchResponseSLORegression`, the one thing CI *does* run) is a single-user, single-request, **60-row** latency assertion in a test process:

```python
elapsed = (time.perf_counter() - start) * 1000
assert elapsed < PerformanceSLO.SEARCH_SLO_MS, f"search response took {elapsed:.0f}ms"
```

At 60 rows the planner uses a sequential scan regardless of which indexes exist, so it is structurally incapable of detecting an indexing or query-plan regression. It is also a *p99* constant (`SEARCH_SLO_MS = 2000`) applied to a *single* sample — it is not a percentile measurement. Worth keeping as a smoke test; it should not be described as the SLO regression gate (phase brief §4.5 does).

**Fix.**

- Correct the two URLs in `locustfile.py` and assert a `0 %` failure rate in the CI step (it currently does not), so a dead route cannot silently consume a third of the load again.
- Lower `SEED_SCALE_MIN_ROWS` to a value the environment can build, or add a documented `make profile-seed` step. Better: add a **nightly** profile job (`ci-nightly.yml` already exists) that seeds ~20 k rows and runs `profile_queries`, so the discipline has a home without slowing every PR.
- Extend `_build_queries()` to include the `user__is_declined` join and the `?features=` shape, and add a `--min-rows` argument so the threshold is a parameter rather than a constant nobody can satisfy.
- Re-baseline after fixing 12a: with the dead task removed, the p95 the load test measures will be materially worse than today's number. That is the point.

**Effort:** trivial (URLs) / small (profile coverage + nightly job) · **Priority:** recommended

---

### PERF-013 — `recompute_normalized_prices` full-table sweep: 125 statements, 3.0 s and 120 `SELECT … FOR UPDATE` batches at 60 000 ads

**Severity:** LOW · **Zone:** background-job cost · **Status:** CONFIRMED

This is **cost quantification for `DB-008`**, not a new finding — `DB-008` (phase 03) already requires the all-or-nothing whole-sweep transaction to become per-batch, and that is not re-filed. What this phase adds is the measured shape of the cost, because `DB-008` needs a magnitude to prioritise against the other sweeps.

`apps/currencies/management/commands/recompute_normalized_prices.py:31-74` wraps the whole sweep in one `transaction.atomic()` and iterates:

```python
with transaction.atomic():
    for batch in ...:                              # .iterator(chunk_size=BATCH_SIZE)
        locked = list(Ad.objects.filter(pk__in=[...]).select_for_update()
                      .only("pk", "price_amount", "price_currency", "price_normalized_eur"))
        ...
        Ad.objects.bulk_update(batch_objs, fields, batch_size=500)
```

Measured with `--dry-run` over 60 000 ads:

```
[5] recompute_normalized_prices --dry-run: n_sql=125  wall=3048 ms  (ads=60000, batch=500)
    SELECT ... FOR UPDATE batches: 120
```

**125 round trips: 120 lock-and-read batches + 5**, and 3.0 s. `select_for_update()` on all 60 000 rows inside one transaction means every row it touches stays locked for the full 3 s, holding the advisory lock the same way. The `.only(...)` projection is already correct and keeps the transfer to 4 columns.

The number of *updated* rows is data-dependent and I could not reproduce production data: my seeded rows had `price_normalized_eur` deliberately inconsistent with `price_amount`, so the dry run reported *"would recompute 59995 of 60000"* — the pathological case where every run is a full-table rewrite. Per phase 09's `API-008`, the shipped `exchange_rates` data is a hard-coded 2026-08-22 manual seed, so in the shipped data path the sweep is likely recomputing a **constant** result set every run and the DML would be a no-op; only the 120 lock-and-read round trips would cost anything. **Stated as a dependency on `API-008`, not as a measurement.**

**Why LOW and not folded into `DB-008`.** 3 s for the full-table pass is well inside `SCHEDULER_COMMAND_TIMEOUT` (1 800 s) and the command is **not** scheduled — `recompute_normalized_prices` is absent from `HOURLY_COMMANDS` in `apps/core/utils/scheduler.py:55-65`, so it runs only when a human invokes it. The transaction-shape fix is `DB-008`'s to make; the only thing worth recording here is that this is the *cheapest* of the sweeps and should be sequenced last.

**Effort:** none (no separate change) · **Priority:** informational

---

### PERF-014 — The N+1 query guard was widened to 100 to accommodate a known N+1, and its stated rationale no longer describes the code

**Severity:** LOW · **Zone:** performance discipline / documentation · **Status:** CONFIRMED

**Evidence.** `apps/search/tests/test_search_query_count.py:14-31`:

```python
# Known non-N+1 sources (each page the HTML partial does a couple of small
# LookupItem lookups for the purpose/condition selects, and each ad card
# does a `filter_form`-style city/category label lookup):
#   ~ 12 LookupItem get_name lookups per page render
#   ~  2 categories by-slug .exists() checks per page
#   ~ 20 per-card localized name / city / category existence checks
# => ~40 baseline queries + search machinery (~15) = ~55, plus headroom.
# Bound raised from 35 to 100 in response to 13-PERF-004 recommendation #3
# (Documented: images is not in prefetch_related; the template's
#  ad.images.first is a prefetched relation so it does not query).
_QUERY_BOUND = 100
```

Three problems:

1. **The guard was raised, not the defect fixed.** A prior 13-PERF cycle recommended fixing the N+1 (recommendation #3); the response was to move the ceiling. This is how N+1s become permanent: a guard at 100 would not notice the listing path going from 46 to 95 queries. The actual measured count is **46** on `/` and **60** on `/search/`.
2. **The stated rationale is now false.** It says *"`images` is not in `prefetch_related`"* — but `ListingsQuery.build_queryset` (`listings_query.py:59`) does specify `prefetch_related("features", "user__trust_score", "images")`. Verified: 24 rows × `features` + `images` = **1 query each**, not 24 each.
3. **The comment misattributes the remaining cost.** It blames "localized-name lookups", but the 12 `categories` `.exists()` calls are the uncached nav N+1 (PERF-009) and the 24-25 `seller_trust_scores` calls are the dead prefetch check (PERF-004) — neither is a "small lookup", and both are fixable. The real query budget after fixing PERF-004 and PERF-009 is closer to **10**, not 46.

**Fix.** Fix PERF-004 and PERF-009 first, then set `_QUERY_BOUND` to a number derived from the actual query inventory — a comment listing each expected statement and why — rather than a round figure plus "headroom". A guard at 46 tolerates a 2× regression; a guard at 100 tolerates none worth catching. Correct the `images` sentence either way.

LOW rather than a test-quality finding because phase 11 owns test quality; it is filed here only because the *performance invariant* the guard encodes is the deliverable, and that invariant was weakened instead of the code being fixed.

**Effort:** trivial (bound + comment) · **Priority:** recommended

---

### PERF-015 — `docs/ops/profiling.md` instructs a review step whose tool cannot run and would not cover the real query shapes

**Severity:** LOW · **Zone:** performance discipline / documentation · **Status:** CONFIRMED

**Evidence.** `docs/ops/profiling.md:43-63` tells the reviewer to run `make profile` and states:

> *This is the single best signal for query regressions at this data volume.*
> *… run `profile_queries` after each change to filters, sorting, or pagination …*
> *… verify no `Seq Scan on ads` appears on the listing query …*
> *… record the seq-scan count in the review description.*

Project rule 14 requires documentation to stay current. Three claims are no longer true:

1. **The tool cannot run.** `_scale_dataset()` returns early unless ≥ 10 000 published ads exist, and no shipped environment creates that (PERF-012b). `make profile` therefore prints the "not enough data" branch and exits 0 — indistinguishable from a clean run.
2. **It is not the best signal for query regressions at this data volume**, because at the volume it *can* produce it does not measure the shapes that regress. The command's own `_build_queries()` omits `user__is_declined=False`, the `annotate_favorites` subquery, the `?features=` join, and the cache-hit restore (PERF-012b). A reviewer following the doc would get a clean report while a new sequential scan shipped on the production path.
3. **The ≥ 10 000-row threshold is the wrong axis anyway.** The FTS timing problem (PERF-006) scales with *match count* for a given term, not with table size, so a 10 000-row dataset with a common term reproduces it while a 10 000-row dataset with a rare term does not. The command has no notion of a match-count target.

**Fix — documentation plus a one-line code change.** Correct the doc to state the real threshold, and add the missing shapes to `_build_queries()` so the "best signal" claim becomes true. Until then, soften the wording to describe what it actually checks (default browse + category + price + FTS shapes at ≥ 10 k rows) and add a pointer that the browse path's N+1 budget is guarded separately by `test_search_query_count.py` (itself corrected in PERF-014). Add the `user__is_declined` join to the command in the same change — one line, and it is the join actually on the production path.

**Effort:** trivial (doc) + small (`_build_queries`) · **Priority:** recommended

---

## Summary

| ID | Title | Severity | Zone |
|---|---|---|---|
| PERF-001 | CI p95 latency gate reads the wrong CSV column and matches no row — always passes | **CRITICAL** | load/stress testing |
| PERF-002 | `?features=` amplification SIGKILLs the PostgreSQL backend; full-instance reinit | **HIGH** | query plans / indexing |
| PERF-003 | `rollup_daily_metrics`: ~120 000 SQL in one 305 s transaction; aggregate is 108 ms | **HIGH** | background jobs / N+1 |
| PERF-004 | `render_trust_badge` prefetch check can never fire → 24 failing SELECTs per page | **HIGH** | N+1 access patterns |
| PERF-005 | `send_alerts` runs one FTS query per saved search in one lock-held transaction | **HIGH** | background jobs / N+1 |
| PERF-006 | For ≥ 1 000 matches the search cache recomputes the count; warm search is 510 ms | **HIGH** | cache effectiveness |
| PERF-007 | Single-flight lock gives no cold-miss protection; all losers run the full FTS | MEDIUM | cache effectiveness |
| PERF-008 | Header materialises the whole `cities` table into every page; search view duplicates it | MEDIUM | over-fetching / serialization |
| PERF-009 | 12 `cat.get_children.exists()` per page, duplicating an already-cached tree | MEDIUM | N+1 access patterns |
| PERF-010 | Cache-hit restore sends 35 KB / 1 000 `CASE` arms / 3 003 binds per page view | MEDIUM | over-fetching / serialization |
| PERF-011 | 3 sync workers cap the tier at 3 in-flight requests; SLO alerts cover only `/search/` | MEDIUM | capacity / SLO enforcement |
| PERF-012 | Load test journeys hit non-routes (33 % 404); `profile_queries` unrunnable and off-CI | MEDIUM | load/stress testing |
| PERF-013 | `recompute_normalized_prices`: 125 SQL / 3.0 s / 120 `FOR UPDATE` batches (cost for `DB-008`) | LOW | background jobs |
| PERF-014 | N+1 guard widened to 100 to accommodate the N+1; rationale no longer true | LOW | performance discipline |
| PERF-015 | `docs/ops/profiling.md` describes a tool that cannot run and misses the real shapes | LOW | performance discipline |

### Sequencing note

**PERF-001 first, and alone.** Every other finding here is a regression that the (currently inert) CI gate would have to catch for the project's performance posture to hold. Fixing PERF-002…PERF-015 without PERF-001 leaves all of them unguarded. The fix is one step of shell.

Then, by cost/benefit: PERF-006 (three small edits, removes the biggest single-request cost), PERF-004 + PERF-009 (two trivial edits, take `GET /` from 46 SQL to ~10), PERF-002's composite-join rewrite plus the DTO bound, PERF-003 (one `bulk_create`), PERF-005 (batching), PERF-011's alert-scope fix. PERF-013, PERF-014 and PERF-015 are documentation/test-guard corrections that should ride along with the changes they describe.

### Conclusions that depend on data volume I could not reproduce

Stated explicitly, per the audit brief:

- **All FTS timings** (PERF-002, PERF-005, PERF-006) scale with *match count*, which I set to 14 194 by choosing the term `велосипед` against my own 60 000-row dataset. A real catalogue's term-frequency distribution is unknown. The **plan shapes, SQL sizes, parameter counts and query counts** are volume-independent; the millisecond figures are not.
- **PERF-008** depends entirely on the `cities` table size. The shipped fixture has **15** rows, where the finding is ~8 KB and immaterial. My 5 015 rows are a synthetic upper bound chosen to expose the scaling, not a measurement of production. The design is the finding.
- **PERF-011's** ~7 req/s figure assumes a co-located database, `DEBUG=1`, and no TLS/gzip; it is a ratio for reasoning, not a capacity plan. The `workers = 3` / `worker_class = "sync"` constant is exact.
- **PERF-013's** updated-row count is data-dependent; I deliberately did not reproduce the shipped `exchange_rates` path (see `API-008`).
- **PERF-001's** reproduction used locust 2.46.6, which is what `uv.lock` pins and what the `mko-bazuna-test-test` image has installed — the version CI uses today. It would *not* have failed on locust ≤ 2.32, where column 1 was `Name`; the repo's `>=2.20.0` specifier makes this a latent regression as well as a present one.
- **Not audited:** real production hardware, real nginx/TLS/gzip behaviour, Redis rather than locmem (the caching measurements used Django's local-memory backend in the probe container, so cache *latency* is unrepresentative — only cache *hit/miss control flow* and statement sizes are), and the bot's own Postgres access patterns beyond the alert fan-out in PERF-005.

### Cross-references to other phases (not re-filed here)

- `SRCH-001` → quantified in **PERF-002** (plan shape, row-count amplification, fix cost).
- `SRCH-006` / `SRCH-007` / `SRCH-014` → the search cache's *correctness* was verified as **sound** and is credited above; only its *effectiveness* under broad queries and on a cold miss is filed (PERF-006, PERF-007).
- `DB-004` (no `lock_timeout` / `statement_timeout`) and `DB-008` (whole-sweep transactions) → both are prerequisites for the fixes in PERF-003, PERF-005 and PERF-013; neither is re-filed.
- `ENT-001` (`PROMETHEUS_MULTIPROC_DIR` unset) → `docs/ops/prometheus-slo-alerts.yaml:13-16` already documents that per-worker metrics break the counter-based alerts. That is phase 12's finding; noted in PERF-011 only because it affects whether the newly-scoped alert would be trustworthy.
- `API-008` (hard-coded 2026-08-22 rate seed) → referenced in PERF-013 as the reason the price recompute's DML volume could not be measured.
- `AD-008` (`ON_MODERATION` never committed) → checked as a possible source of an always-empty metric; no performance impact found, not re-filed.
