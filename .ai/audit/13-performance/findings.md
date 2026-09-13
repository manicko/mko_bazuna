---
# Report metadata — fill once per phase report.
phase: "13"
phase_name: "Performance & Scalability"
date: "2026-09-13"
auditor: "Executor (subagent)"
validator: ""  # Phase 99 only — omit/blank for raw phase findings
mode: "problems-only"
id_prefix: "PERF"
severity_taxonomy: ".kilo/commands/audit/phases/13-audit-performance.md#severity-taxonomy"
report_status: "draft"
---

# Audit Findings — Performance & Scalability

## Executive Summary

The Mko Bazuna platform has no runtime observability or performance-validation
infrastructure: no SLOs, error budgets, dashboards, or `/metrics` endpoint, and
no load/stress test in CI or the dependency manifest. The cache layer invalidates
on write but has no stale-while-revalidate stampede guard and two invalidation
paths have correctness gaps; the per-request `CONN_MAX_AGE=0` pooling strategy
has no capacity analysis or connection-storm monitoring and the PgBouncer profile
is untested in CI; and there is no `EXPLAIN ANALYZE`/profiling discipline. A live
`EXPLAIN (ANALYZE)` on the seeded dev DB confirmed the homepage browse query
(`listings` at `/`, `WHERE status='published' ORDER BY published_at DESC`)
performs a **Seq Scan** with no matching index — a latent scale bottleneck masked
at 600 rows but material at the spec's 500k-ad target. Six findings: 2 CRITICAL,
4 HIGH.

## Scope & Methodology

**Scope:** Performance and scalability strategy for the two-process stack (web
gunicorn sync WSGI `config.settings.prod`/`base.py`; bot aiogram with
`django.setup()`; shared PostgreSQL 18; Redis-backed `django-redis` cache).
Covers SLO/error-budget/dashboard presence; caching strategy (invalidation call
sites, cache-key locale segmentation, stampede/stale-content guards);
connection-pooling strategy (`CONN_MAX_AGE`, PgBouncer opt-in,
`prepare_threshold`); query-performance discipline (`select_related`/index usage,
`EXPLAIN ANALYZE` review process); load/stress testing in CI and dependencies.
Does NOT re-audit Phase 08 FTS mechanism or Phase 03 async/sync bridge (per
phase §6).

### Runtime Verification

| R# | Check | Method | Result |
|----|-------|--------|--------|
| R-01 | Spec latency targets measured + SLO dashboard/alert exist | `grep -rni "SLO\|SLI\|error_budget\|burn.rate" docs/ src/backend/config/`; `grep -rn "metrics" src/backend/config/urls.py`; `grep -i prometheus pyproject.toml` | FAIL |
| R-02 | Cache invalidation triggered on documented data-mutating paths | `read apps/categories/signals.py`, `apps/lookups/signals.py`, `lookup_resolution.py:131-134`, `cache_service.py:84-85` | PASS |
| R-03 | Cache keys locale-segmented (submenu omits-language bug §7/09) | `read apps/categories/views.py:46`; `test_submenu_cache_isolated_by_locale` | PASS — fixed |
| R-04 | Default deploy uses `CONN_MAX_AGE=0`; PgBouncer opt-in only | `read base.py:188-196`; `docker-compose.yml` (no pgbouncer); `docker-compose.prod.yml:103-125` (`profiles:["pgbouncer"]`) | PASS — structure |
| R-05 | `EXPLAIN ANALYZE` / profiling discipline on list/filter/search | `grep -rni "explain\|profiling" docs/ src/`; search management commands; `ci.yml` jobs | FAIL |
| R-06 | Load/stress test in dependency manifest + CI/release | `grep -rni "locust\|k6\|hey\b\|artillery" pyproject.toml uv.lock .github/workflows/`; `grep -in "load\|stress" Makefile` | FAIL |
| R-07 | `select_related`/`prefetch_related` on listing/filter views | `read listings.py:268-272`, `search.py:64-68`, `favorites.py:30-31`, `listings.py:59-60` | PASS |
| R-08 | Stampede guard (stale-while-revalidate / background refresh) present | `grep -rin "stale_revalidate|stale-while|StaleWhile|background_refresh" src/` | FAIL |

**Tools used:** `grep`, `read`, `docker compose exec db psql` (trigger/index
inspection), `django.db.connection` `EXPLAIN (ANALYZE, BUFFERS)` run inside the
running `web` container against the seeded dev DB (`mko-bazuna-dev`, 600 ads /
360 published), cross-reference Phase 12 findings (OPS-008).

**Assumptions:** Production uses Redis-backed cache via `docker-compose.yml`
`redis:7-alpine` (web/bot/scheduler depend on it); dev/test override `CACHES` to
`LocMemCache` (`config/settings/dev.py:39`, `test.py:58`). PostgreSQL 18; Django
5.2 LTS; gunicorn 3 sync workers (`docker-compose.yml:168`). Default deploy =
`docker-compose.yml` + `docker-compose.prod.yml` (PgBouncer only with
`--profile pgbouncer`). Dev DB auto-seeded (600 ads).

## Findings Summary

| ID | Title | Severity | Status | Category |
|----|-------|----------|--------|----------|
| PERF-001 | No SLO / error-budget / dashboard / /metrics for spec-derived latency targets | CRITICAL | Open | Observability & SLOs |
| PERF-002 | No load/stress testing in CI or dependency manifest | CRITICAL | Open | Load & Stress Testing |
| PERF-003 | No cache stampede guard / stale-while-revalidate on invalidation | HIGH | Open | Caching Strategy |
| PERF-004 | Cache invalidation correctness gap: name-only LookupItem updates bypass resolved-cache invalidation | HIGH | Open | Caching Strategy |
| PERF-005 | CONN_MAX_AGE=0 per-request connections: no capacity analysis, no connection-storm monitoring, PgBouncer profile untested in CI | HIGH | Open | Connection Pooling |
| PERF-006 | No EXPLAIN ANALYZE / profiling discipline; unfiltered homepage browse seq-scans at scale | HIGH | Open | Query Performance |

## Findings by Severity

### CRITICAL

#### PERF-001: [CRITICAL] — No SLO / error-budget / dashboard / /metrics for spec-derived latency targets

| Field | Value |
|---|---|
| **ID** | PERF-001 |
| **Title** | No SLO / error-budget / dashboard / /metrics for spec-derived latency targets |
| **Severity** | CRITICAL |
| **Category** | Observability & SLOs |
| **File(s)** | `src/backend/config/urls.py:11-22` (no `/metrics`); `pyproject.toml:10-29` (no metrics SDK); `.github/workflows/ci.yml:7-11` (jobs: build, test, lint, typecheck, lint-templates, i18n); `docs/01-spec/technical-specification.md:29` (only states "server response < 2s") |
| **Status** | Open |
| **Owner** | Site Reliability Engineering / Product |
| **Target Date** | 2026-11-30 |
| **Problem** | The spec defines a latency budget ("server response < 2s", technical-specification.md:29) but provides no SLO measurement, error budget, burn-rate alerting, or dashboard. There is no Prometheus-compatible `/metrics` endpoint and no metrics SDK (`prometheus-client`/`django-prometheus`/`OpenTelemetry`) in `pyproject.toml`; `grep` for SLO/SLI/error_budget/burn.rate across `docs/` and `config/` returns no matches. CI has six jobs (build, test, lint, typecheck, lint-templates, i18n) and none instruments or alerts on latency. The only "metrics" is the post-hoc CLI `manage.py show_metrics` (stdout dump, not a scrapeable endpoint). |
| **Impact** | Without SLOs and an error budget there is no objective definition of "healthy" latency and no proactive burn-down signal — latency SLO breaches (e.g. search > 2s) are detected reactively via user complaints. The "server response < 2s" budget is unmeasurable; Phase 12 already documented the absence as OPS-008 (HIGH). |
| **Root Cause** | No observability/SLO stack was implemented in the initial build. |
| **Recommendation** | (1) Add `prometheus-client` + `django-prometheus` to `pyproject.toml`. (2) Expose `/metrics`. (3) Instrument SLIs: HTTP request duration per URL pattern, 5xx count, cache hit/miss, DB query count/latency, bot update-processing lag. (4) Define SLOs + error budgets in `docs/ops/slo.md` (e.g. p95 search < 2s, p95 filter < 1s over 30 days, 7.29x/0.25x burn-rate alerts per Google SRE workbook). (5) Add an SLO gate to CI/release. |
| **Effort** | L |
| **Priority** | P1 |
| **Related Findings** | Phase 12 OPS-008; PERF-002 |

**Evidence — no SLO/SLI/error-budget definitions** *(supports: "no SLO/error-budget/dashboard")*:
```text
$ grep -rni "SLO|SLI|error_budget|burn.rate|service_level" docs/ src/backend/config/
# (no matches in docs/ or config/)
```

**Evidence — `config/urls.py:11-22` has no `/metrics` route** *(supports: "no /metrics endpoint")*:
```python
urlpatterns = [
    path("admin/", admin.site.urls),
    path("moderation/", include("apps.moderation.urls")),
    path("analytics/", include("apps.analytics.urls")),
    path("cabinet/", include("apps.cabinet.urls")),
    path("", include("apps.users.urls")),
    path("", include("apps.ads.urls")),
    path("", include("apps.categories.urls")),
    path("", include("apps.locations.urls")),
    path("", include("apps.search.urls")),
    path("", include("apps.core.urls")),
]
# NO /metrics/ route
```

**Evidence — `pyproject.toml` dependencies have no metrics SDK** *(supports: "no metrics SDK")*:
```toml
# src/backend/pyproject.toml:10-29  — no prometheus-client, django-prometheus, opentelemetry-sdk
# dev group (201-211): basedpyright, pytest, ruff, djlint, coverage — no perf tooling
```

**Evidence — `ci.yml` jobs** *(supports: "no monitoring/SLO gate in CI")*:
```yaml
# .github/workflows/ci.yml:7-11
jobs:
  build:      # Docker image + test env
  test:       # migrate + compilemessages + pytest with coverage
  lint:       # ruff check
  typecheck:  # basedpyright
  lint-templates: djlint
  i18n:       # compilemessages + i18n completeness tests
# NO metrics, NO SLO, NO load/stress job
```

> PERF-001 is the Performance phase's view of Phase 12 OPS-008 (no `/metrics`, no SLOs).

---

#### PERF-002: [CRITICAL] — No load/stress testing in CI or dependency manifest

| Field | Value |
|---|---|
| **ID** | PERF-002 |
| **Title** | No load/stress testing in CI or dependency manifest |
| **Severity** | CRITICAL |
| **Category** | Load & Stress Testing |
| **File(s)** | `pyproject.toml:10-29,201-211` (no load-test dep); `.github/workflows/ci.yml:7-11` (no load job); `.github/workflows/ci-nightly.yml:1-82` (only seed suite); `Makefile` (no load/stress target) |
| **Status** | Open |
| **Owner** | Engineering / SRE |
| **Target Date** | 2026-11-30 |
| **Problem** | No load/stress-test tool (`locust`, `k6`, `hey`, `artillery`, `vegeta`, `wrk`) is declared in `pyproject.toml` (runtime or dev groups) nor in `uv.lock`. No CI job — including the nightly `ci-nightly.yml`, which only runs the seed correctness suite — invokes any load/stress tool. The seed service populates a seeded catalog (600 ads default) but no harness exercises search/filter/listing endpoints under concurrent load, and the seed suite is marked `seed` (excluded from the fast gate) so it never runs as a performance regression gate. |
| **Impact** | No performance regression gate. Concurrency and latency under realistic load are never validated, so the "< 2s search / < 1s filter" budget cannot be verified at volume. A query fast on 600 dev rows can collapse at the spec's 500k-ad target — the edge case §7 explicitly warns about. |
| **Root Cause** | Load testing was never introduced into the dependency manifest or CI/release process. |
| **Recommendation** | (1) Add a load-test tool as a dev dependency (e.g. `locust` or `k6`). (2) Add a CI/release job that seeds a realistic catalog (e.g. `SEED_ADS=50000`) and runs a representative scenario (homepage browse, filtered listing, keyword search) with concurrency + latency assertions (p95 < 2s) that fail the gate on regression. (3) Gate release on the load-test result. |
| **Effort** | M |
| **Priority** | P1 |
| **Related Findings** | PERF-001 (no SLOs to gate against); PERF-006 |

**Evidence — no load/stress-test tool in dependencies** *(supports: "no load-test tooling")*:
```text
$ grep -rni "locust|k6|hey|artillery|vegeta|jmeter" pyproject.toml uv.lock
# (no matches)
$ grep -in "load|stress|benchmark|siege" Makefile
# (no matches)
```

> Note: `scripts/run-profile.sh` runs `pytest --profile` (test-timing profiling), not a load/stress test.

---

### HIGH

#### PERF-003: [HIGH] — No cache stampede guard / stale-while-revalidate on invalidation

| Field | Value |
|---|---|
| **ID** | PERF-003 |
| **Title** | No cache stampede guard / stale-while-revalidate on invalidation |
| **Severity** | HIGH |
| **Category** | Caching Strategy |
| **File(s)** | `src/backend/apps/categories/services/lookup_resolution.py:162-199` (cache.get on miss → recompute → cache.set, no stale fallback); `src/backend/apps/categories/cache.py:28-41` (submenu cache.get/set, tree_version invalidates); `src/backend/apps/lookups/services/cache_service.py:41-76` (get/set, no revalidate); `src/backend/apps/core/utils/cache.py:15-98`; `src/backend/apps/currencies/services/price_normalizer.py:87-101`; `src/backend/apps/analytics/services/seller_stats.py:44-49` |
| **Status** | Open |
| **Owner** | Backend Engineering |
| **Target Date** | 2026-11-30 |
| **Problem** | Every shared cache uses the bare `cache.get` (miss) → recompute → `cache.set(TTL)` pattern with no stale-while-revalidate or background refresh. `grep` for `stale_revalidate`/`stale-while`/`StaleWhile`/`background_refresh` across `src/` returns no matches (R-08 FAIL). On invalidation (e.g. `bump_tree_version` on category-tree change) or on cold first-hit under concurrency, all 3 gunicorn workers + the bot miss the shared Redis cache simultaneously and recompute synchronously. The mega-subnav submenu (`categories/views.py:46-58`) is a concrete hot path: a tree-version bump invalidates every concurrent request, each re-rendering `mega_submenu.html` with its ancestor queries. There is no stale-serve-while-recompute and no single-flight / winner-take-all lock to bound recomputation. |
| **Impact** | Under invalidation or concurrent cold-first-hit traffic, latency spikes as N workers block on synchronous recomputation (thundering herd) — the §7 edge case "Cache invalidated but recomputed synchronously under load → stampede / latency spike." With 3 gunicorn workers + bot sharing Redis, a single category-tree edit can amplify request latency for all concurrent visitors until the cache repopulates. |
| **Root Cause** | Manual `cache.get`/`cache.set` with TTL and invalidate-on-write; no SWR library or single-flight pattern for the hot read paths. |
| **Recommendation** | Adopt stale-while-revalidate on the hot shared caches: store the value with a `stale_at` marker and a regeneration lock; on hit-serve-stale-if-fresh-else-serve-stale-while-a-single-winner-recomputes (use `cache.add` as a distributed lock so only one worker recomputes while the rest serve stale within a bounded window). Apply to the submenu, resolved-lookup, and site-config caches. |
| **Effort** | M |
| **Priority** | P1 |
| **Related Findings** | PERF-004 (invalidation correctness), Phase 12 OPS-008 (cache hit/miss SLI absent) |
| **Conditional fields** | Owner / Target Date |

**Evidence — bare get-on-miss recompute (no stale fallback)** *(supports: "no stale-while-revalidate")*:
```python
# src/backend/apps/categories/services/lookup_resolution.py:161-199
cache_key = f"{cache_key_prefix}:{category.id}"
cached = cache.get(cache_key)            # miss -> recompute synchronously
if cached is not None:
    return list(cached)
...
result: list = []                         # <-- recompute under every concurrent miss
for ancestor in ancestors:
    if ancestor.id in grouped:
        result = grouped[ancestor.id]
        break
cache.set(cache_key, result, CACHE_TTL)  # TTL only; no stale/serve-while-recompute
return result
```

**Evidence — submenu invalidation via tree-version bump (all concurrent requests miss)** *(supports: "tree-version invalidation triggers stampede")*:
```python
# src/backend/apps/categories/views.py:46-58
cache_key = f"category:submenu:{get_tree_version()}:{category.slug}:{request.LANGUAGE_CODE or 'ru'}"
cached = cache.get(cache_key)
if cached is not None:
    return cached
...                                        # re-render mega_submenu.html under every miss
cache.set(cache_key, html, SUBMENU_CACHE_TTL)
# categories/signals.py:22-26: bump_tree_version() fires on EVERY Category/CategoryPath change
```

---

#### PERF-004: [HIGH] — Cache invalidation correctness gap: name-only LookupItem updates bypass resolved-cache invalidation

| Field | Value |
|---|---|
| **ID** | PERF-004 |
| **Title** | Cache invalidation correctness gap: name-only LookupItem updates bypass resolved-cache invalidation |
| **Severity** | HIGH |
| **Category** | Caching Strategy |
| **File(s)** | `src/backend/apps/categories/signals.py:49-59` (is_active gate); `src/backend/apps/categories/services/lookup_resolution.py:129-134` (delete_pattern on RESOLVED_* prefixes); `src/backend/apps/lookups/services/cache_service.py:80-86` (parallel cache always invalidated) |
| **Status** | Open |
| **Owner** | Backend Engineering |
| **Target Date** | 2025-10-31 |
| **Problem** | `invalidate_on_lookup_item_change` (categories/signals.py:54) gates invalidation on `is_active`: `if update_fields is not None and "is_active" not in update_fields: return`. A `name_i18n`-only update (`save(update_fields=["name_i18n"])`) returns early and never calls `resolver.invalidate_lookup_item`, so the CategoryLookupResolver's per-category resolved caches (`lookup:resolved_purposes:{id}`, `lookup:resolved_features:{id}`, `lookup:resolved_conditions:{id}`, `CACHE_TTL=300`) retain stale `LookupItem` instances with the OLD localized name for up to 5 min. The template filter `get_lookup_name` (`apps/ads/templatetags/global_tags.py:23`) reads `item.get_name(locale)` from the cached instance, so buyers see stale localized feature/purpose labels. |
| **Impact** | Stale localized lookup-item names shown to buyers for up to 5 min after an admin name edit. Narrow blast radius (admin-only edit + short TTL) but a concrete invalidation-correctness defect — the phase §5(b) check "invalidation... not correct" — with no audit verifying the gate covers all mutating fields. |
| **Root Cause** | The signal gate was written narrowly for `is_active` membership changes (which affect visibility) but neglects name/label-only changes that also affect cached rendered output. |
| **Recommendation** | Remove the `is_active`-only gate so any `LookupItem` save/delete invalidates the resolved caches. The existing `delete_pattern(f"{RESOLVED_PURPOSES_PREFIX}:*")` already nukes all resolved keys (over-broad but safe for a 29-item lookup set); the only cost is recomputation, which the stampede guard (PERF-003) should cover. |
| **Effort** | S |
| **Priority** | P1 |
| **Related Findings** | PERF-003 (cache recompute amplification) |
| **Conditional fields** | Owner / Target Date |

**Evidence — `is_active`-only gate skips name-only updates** *(supports: "name-only LookupItem updates bypass invalidation")*:
```python
# src/backend/apps/categories/signals.py:49-59
@receiver(post_save, sender="lookups.LookupItem")
def invalidate_on_lookup_item_change(sender, instance, **kwargs):
    """Invalidate all caches when a LookupItem's is_active field changes."""
    update_fields = kwargs.get("update_fields")
    if update_fields is not None and "is_active" not in update_fields:
        return                                    # <-- name_i18n-only update: returns early
    resolver = CategoryLookupResolver()
    resolver.invalidate_lookup_item(instance.id)
```

**Evidence — RESOLVED_* caches hold model instances whose names are read per-locale** *(supports: "stale localized names served")*:
```python
# src/backend/apps/categories/services/lookup_resolution.py:161-162,199
cache_key = f"{cache_key_prefix}:{category.id}"   # lookup:resolved_purposes:{id}
cached = cache.get(cache_key)
...
cache.set(cache_key, result, CACHE_TTL)           # result = list[LookupItem] (model instances)
```

> Note: the parallel `LookupCacheService` caches (`lookup:all_groups`, `lookup:active_items:*`) ARE always invalidated — `apps/lookups/signals.py:17-38` fires unconditionally on every LookupItem save. The gap is isolated to the resolver's RESOLVED_* caches.

---

#### PERF-005: [HIGH] — CONN_MAX_AGE=0 per-request connections: no capacity analysis, no connection-storm monitoring, PgBouncer profile untested in CI

| Field | Value |
|---|---|
| **ID** | PERF-005 |
| **Title** | CONN_MAX_AGE=0 per-request connections: no capacity analysis, no connection-storm monitoring, PgBouncer profile untested in CI |
| **Severity** | HIGH |
| **Category** | Connection Pooling |
| **File(s)** | `src/backend/config/settings/base.py:174-196` (CONN_MAX_AGE=0 + prepare_threshold=None); `docker-compose.yml` (no pgbouncer service on default path); `docker-compose.prod.yml:103-125` (pgbouncer opt-in, `profiles:["pgbouncer"]`); `.github/workflows/ci.yml:39-52` (bare `postgres:18-alpine` service, no PgBouncer); `docs/03-packages/packages-list.md:34,76`; `docs/01-spec/architecture-structure.md:218` |
| **Status** | Open |
| **Owner** | Site Reliability Engineering / Backend Engineering |
| **Target Date** | 2026-11-30 |
| **Problem** | The default deploy path uses `CONN_MAX_AGE=0` (fresh connection per request) and has NO PgBouncer service (`docker-compose.yml` has none; prod only gains one under `--profile pgbouncer`, profile-gated at `docker-compose.prod.yml:124`). The psycopg3/PgBouncer tx-mode compatibility setting `OPTIONS={"prepare_threshold": None}` IS configured in `base.py:180,193` and documented (`packages-list.md:42,76`). However: (1) there is no quantitative capacity analysis tying `CONN_MAX_AGE=0` to the target scale (~300 daily users, 500k ads); the rationale is only qualitative ("async safety" — README:90, architecture-structure.md:218); (2) there is no monitoring/alerting on PostgreSQL `current_setting('max_connections')` utilization or connection count to detect a connection storm (§7 edge case) — the spec's own audit-zone C5/c7 notes per-process pooling but states no capacity budget; (3) the PgBouncer profile is never exercised in CI (`ci.yml` uses a bare `postgres:18-alpine` service with no pgbouncer; `docker-compose.test.yml` has no pgbouncer), so the configured `prepare_threshold=None` compatibility is documented but never validated end-to-end. |
| **Impact** | Under unexpected concurrency (traffic surge, bot update flood, or a crawler), per-request connections can exhaust PostgreSQL `max_connections` (default 100), causing new connections to be rejected (HTTP 500s) before PgBouncer is manually enabled. The psycopg3 prepared-statement compatibility is mitigated by `prepare_threshold=None` being set, but this is never CI-verified — a psycopg bump or PgBouncer version change could reintroduce "prepared statement already exists" errors silently. |
| **Root Cause** | Pooling strategy is documented but never capacity-planned, monitored, or CI-verified. |
| **Recommendation** | (1) Add a capacity analysis to `docs/ops/` documenting the connection budget (gunicorn workers × concurrent requests + bot + scheduler) vs. PostgreSQL `max_connections`, with thresholds to enable PgBouncer. (2) Add a DB metric + alert on connection count vs. `max_connections`. (3) Add a CI smoke test that starts the `pgbouncer` profile and runs a request through the pooled path, asserting `prepare_threshold=None` works without "prepared statement already exists" errors. |
| **Effort** | M |
| **Priority** | P1 |
| **Related Findings** | Phase 12 OPS-008 (observability to expose DB connection metrics) |
| **Conditional fields** | Owner / Target Date |

**Evidence — default path has no PgBouncer; CONN_MAX_AGE=0 + prepare_threshold=None in base** *(supports: "pooler not on default deploy; compatibility setting configured but untested")*:
```python
# src/backend/config/settings/base.py:174-196
DATABASES = {
    "default": {
        ...
        "CONN_MAX_AGE": 0,                # per-request connections (default deploy)
        "OPTIONS": {
            "prepare_threshold": None,    # PgBouncer tx-mode compatibility (set but CI-untested)
        },
    }
}
```
```yaml
# docker-compose.prod.yml:103-125  — PgBouncer is opt-in, NOT on the default deploy path
pgbouncer:
  image: edoburu/pgbouncer:1.25.2
  ...
  PGBOUNCER_POOL_MODE: transaction
  profiles:
    - pgbouncer          # only started with --profile pgbouncer
```
```yaml
# .github/workflows/ci.yml:39-52  — test job uses bare postgres, no PgBouncer
services:
  db:
    image: postgres:18-alpine
    ...
# no pgbouncer service in CI
```

---

#### PERF-006: [HIGH] — No EXPLAIN ANALYZE / profiling discipline; unfiltered homepage browse seq-scans at scale

| Field | Value |
|---|---|
| **ID** | PERF-006 |
| **Title** | No EXPLAIN ANALYZE / profiling discipline; unfiltered homepage browse seq-scans at scale |
| **Severity** | HIGH |
| **Category** | Query Performance |
| **File(s)** | `src/backend/apps/ads/urls.py:15` (`path("", listings)` ⇒ homepage `/`); `src/backend/apps/ads/views/listings.py:268-272` (base queryset `filter(status=PUBLISHED).select_related().prefetch_related()`); `src/backend/apps/ads/models.py:275-279` (`IX_ads_pub_listing` on `(status, category_id, city_id, -published_at)`); `docs/01-spec/architecture-structure.md:338` (single aspirational EXPLAIN-ANALYZE reference) |
| **Status** | Open |
| **Owner** | Backend Engineering |
| **Target Date** | 2025-10-31 |
| **Problem** | `select_related`/`prefetch_related` discipline IS present on the listing/filter views (R-07 PASS: `listings.py:268-272`, `search.py:64-68`, `favorites.py:30-31`, `ad_detail` at `listings.py:59-60`) and indexes beyond the GIN FTS vector exist (`IX_ads_pub_listing`, `IX_ads_price_normalized_eur`, `IX_ads_user_status`, per db-indexes.md). However, there is NO documented `EXPLAIN ANALYZE` / query-profiling review process — `grep -rni "explain|profiling" docs/ src/` (R-05) returns only the single aspirational note "Price index added only after EXPLAIN ANALYZE at 500k rows" (architecture-structure.md:338); there is no management command, no CI profiling job, and no review checklist. A live `EXPLAIN (ANALYZE, BUFFERS)` on the seeded dev DB (360 published ads) shows the unfiltered homepage browse query — `listings` at `/` with no category/city filter, `WHERE status='published' ORDER BY -published_at LIMIT 24` — performs a **Seq Scan** (`Index Scan` on no index; the partial `IX_ads_pub_listing` on `(status, category_id, city_id, -published_at)` is unusable for a status-only ordered query). The filtered browse (category+city) and FTS search DO use indexes (Bitmap Index Scan on `IX_ads_search_gin_ru` + `IX_ads_pub_purpose`). The dev DB (600 ads) makes the seq scan 1.165 ms; at the spec's 500k-ad target (≈360k published rows) the seq scan + sort becomes a material latency risk with no profiling gate to flag it. |
| **Impact** | Homepage ("browse all") latency grows with published-ad count; under the 500k-ad target the < 2s budget can be silently exceeded. The dev DB masks the regression (§7 edge case: "Search within budget in dev (small DB) but unbounded under seeded production volume"). |
| **Root Cause** | No systematic query-profiling discipline; indexes were added for filtered paths (category+city+date) but not the unfiltered homepage browse, and nothing asserts "no seq scan on hot ad-list queries at volume." |
| **Recommendation** | (1) Add a profiling discipline: a management command + CI job that runs `EXPLAIN (ANALYZE)` on representative search/filter/list queries against a seeded DB and asserts no Seq Scan on hot tables (threshold-gated). (2) Add a partial index for the unfiltered browse, e.g. `Index(fields=["-published_at"], condition=Q(status=AdStatus.PUBLISHED))` (or reuse `IX_ads_archive_sweep`'s `(status, published_at)` ordering), and validate with `EXPLAIN` at 500k rows via the seed profile (`SEED_ADS=500000`). |
| **Effort** | M |
| **Priority** | P1 |
| **Related Findings** | PERF-002 (no load test to validate at volume); Phase 08 (FTS query plans — separate, owned by Phase 08) |
| **Conditional fields** | Owner / Target Date |

**Evidence — live `EXPLAIN (ANALYZE, BUFFERS)` on seeded dev DB (360 published ads)** *(supports: "homepage browse seq-scans; at scale this degrades")*:

*FTS search (uses indexes — BitmapAnd):*
```text
Limit [Actual Rows=9, Exec Time=2.386ms]
  Sort [Sort Key: rank DESC, published_at DESC]
    Bitmap Heap Scan [Actual Rows=9]
      BitmapAnd
        Bitmap Index Scan [Index=IX_ads_pub_purpose, Actual Rows=360]
        Bitmap Index Scan [Index=IX_ads_search_gin_ru, Actual Rows=12]
```

*Filtered listing (category+city — uses index):*
```text
Limit [Actual Rows=0, Exec Time=37.733ms]
  Sort
    Index Scan [Index=IX_ads_pub_listing, Actual Rows=0]
```

*Unfiltered homepage browse — Seq Scan (NO matching index):*
```text
Limit [Actual Startup=1.087, Actual Rows=24, Exec Time=1.165ms]
  Sort [Sort Key: published_at DESC]
    Seq Scan on ads [Filter: (status='published'), Actual Rows=360, Shared Hit Blocks=202]
```

> The dev DB has only 360 published rows (1.165 ms); at the spec's 500k-ad target this Seq Scan + Sort reads ~360k index/heap tuples with no profiling gate to catch the regression.

**Evidence — no profiling tooling / single aspirational reference** *(supports: "no EXPLAIN ANALYZE discipline")*:
```text
$ grep -rni "explain|profiling" docs/ src/
docs/01-spec/architecture-structure.md:338: "...Price index added only after EXPLAIN ANALYZE at 500k rows..."
# No management command, no CI job, no review checklist — aspirational only.
```

---

## Cross-Finding Analysis

- **Merge candidates:** PERF-003 (stampede) and PERF-004 (invalidation correctness) share the cache layer but have distinct root causes (no SWR pattern vs. narrow signal gate) — keep separate.
- **Conflicting evidence:** None. PERF-005's `prepare_threshold=None` is configured AND documented (so it is not an unconfigured pooler); the finding is that it is untested in CI and lacks capacity analysis, not that it is absent.
- **Dependency chains:** PERF-001 (SLOs/metrics) is a prerequisite for validating PERF-006 (profiling at volume) and PERF-002 (load-test latency assertions); PERF-003 (stampede guard) should be implemented alongside PERF-004's invalidation fix so the broader cache invalidation does not amplify recompuation.

## Remediation Roadmap

| Order | ID | Severity | Effort | Priority | Recommendation (summary) |
|-------|----|----------|--------|----------|--------------------------|
| 1 | PERF-001 | CRITICAL | L | P1 | Add prometheus-client + /metrics; instrument SLIs; define SLOs/error budgets in docs/ops/slo.md; add CI gate |
| 2 | PERF-002 | CRITICAL | M | P1 | Add locust/k6 to dev deps; add CI/load job seeding 50k ads with p95 < 2s assertions |
| 3 | PERF-003 | HIGH | M | P1 | Add stale-while-revalidate / single-flight to hot shared caches (submenu, resolved lookups, site config) |
| 4 | PERF-004 | HIGH | S | P1 | Remove is_active-only gate in categories/signals.py so name-only LookupItem updates invalidate RESOLVED_* caches |
| 5 | PERF-006 | HIGH | M | P1 | Add EXPLAIN-ANALYZE profiling CI job + partial index for unfiltered browse; validate at 500k rows |
| 6 | PERF-005 | HIGH | M | P1 | Add capacity analysis, DB connection-count alert, and CI smoke test for pgbouncer profile |

## Rollout Safety

| ID | Risk | Backward-compatible? | Test gap (must cover) |
|----|------|----------------------|-----------------------|
| PERF-001 | Med | Yes (additive endpoint/metrics; SLOs are doc + alerts) | Test `/metrics` returns 200 with Prometheus-format body; no test currently asserts metrics SDK presence |
| PERF-002 | Low | Yes (test-only additions) | Load-test scenarios gated on p95/throughput; nothing currently exercises concurrent load |
| PERF-003 | Med | Yes | Cache hit/miss under concurrent invalidation; no test asserts single-flight/stale-serve behavior |
| PERF-004 | Low | Yes (signal now fires on more updates) | Test name-only LookupItem update invalidates RESOLVED_* caches; current tests don't cover the gate |
| PERF-006 | Med | Yes (new index is additive) | EXPLAIN-based test asserting the unfiltered browse uses an index (current DB too small to prove at scale) |
| PERF-005 | Low | Yes (CI-only additions + alerting) | CI test starting the pgbouncer profile end-to-end; no test exercises the pooler today |

## Appendices

### Appendix A — `EXPLAIN (ANALYZE, BUFFERS)` output (live, seeded dev DB: 600 ads, 360 published)

Captured by running `django.db.connection.cursor().execute("EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) ...")` inside the running `web` container (`mko-bazuna-dev`), `config.settings.dev`, against PostgreSQL 18.

**A1. FTS search `WHERE status='published' AND search_vector_ru @@ phraseto_tsquery('russian','авто') ORDER BY rank DESC, published_at DESC LIMIT 24`**
```text
Limit  Exec=2.386ms  Rows=9
  Sort  Sort Key: rank DESC, published_at DESC
    Bitmap Heap Scan  Rows=9  Shared Hit=12
      BitmapAnd
        Bitmap Index Scan name=IX_ads_pub_purpose  Rows=360  Shared Hit=1
        Bitmap Index Scan name=IX_ads_search_gin_ru  Rows=12  Shared Hit=3
# Index usage: GOOD (partial status index ∩ GIN search index)
```

**A2. Filtered listing `WHERE status='published' AND category_id IN (1,2,3) AND city_id=1 ORDER BY published_at DESC LIMIT 24`**
```text
Limit  Exec=37.733ms  Rows=0
  Sort
    Index Scan name=IX_ads_pub_listing  Rows=0  Shared Hit=9
# Index usage: GOOD (category+city+date composite)
```

**A3. Unfiltered homepage browse `WHERE status='published' ORDER BY published_at DESC LIMIT 24`**
```text
Limit  Startup=1.087ms  Exec=1.165ms  Rows=24
  Sort  Sort Key: published_at DESC
    Seq Scan on ads  Filter: (status::text = 'published')  Rows=360  Shared Hit=202
# Index usage: NONE — Seq Scan (no index matches a status-only ordered query)
```

*(supports the claim: "at 360 published rows the seq scan is 1.165 ms, but at 360k published rows there is no profiling discipline to catch the regression")*

### Appendix B — Cache key inventory & locale segmentation

| Key pattern | TTL | Shared (Redis)? | Caches rendered content? | Locale-segmented? | Source |
|---|---|---|---|---|---|
| `category:submenu:{tree_version}:{slug}:{LANGUAGE_CODE}` | 300s | yes | **yes (HTML)** | **yes** (per views.py:46; problem 09 FIXED) | `apps/categories/views.py:46`, `cache.py:21-23` |
| `lookup:resolved_purposes:{id}` / `..._features:{id}` / `..._conditions:{id}` | 300s | yes | no (model instances) | n/a (instances; `get_name(locale)` at read time) | `lookup_resolution.py:24-28,161` |
| `lookup:all_groups` | 3600s | yes | no (model instances) | n/a | `cache_service.py:20` |
| `lookup:active_items:{group_code}` | 3600s | yes | no (model instances) | n/a | `cache_service.py:21,63` |
| `moderation_criteria:v1` | 300s | yes | no (dict) | n/a | `core/utils/cache.py:11` |
| `site_config:v1` / `site_config:bot_username:v1` | 3600s | yes | no (string) | n/a | `core/utils/cache.py:56,101` |
| `exchange_rate:v1:{currency}` | 300s | yes | no (string) | n/a | `currencies/price_normalizer.py:26,86` |
| `seller_stats:{user_id}:{time_range}` | 300s | yes | no (numeric dict; title not used for display) | n/a | `analytics/seller_stats.py:54` |
| `autocomplete_rl:{ip}` / `login_rl:{ip}` / `telegram_dl_rl:{ip}` | 600/60s | yes | no (counter) | n/a | rate-limit services |
| `category:tree_version` | persistent | yes | no (int counter) | n/a | `categories/cache.py:21` |

*(supports PERF-003/PERF-004: locale segmentation is correct where rendered content is cached (submenu); all other caches hold locale-agnostic model instances or counters. The stampede gap (no SWR) and the INVALIDATE-on-name-update gap apply regardless of locale segmentation.)*

### Appendix C — Scope exclusions (owned by other phases)

- Phase 08 (FTS search mechanism): the `search_vector_ru/bs/en` GIN indexes and trigger are correct and in use (A1 above) — not re-audited here.
- Phase 03 (DB concurrency / async-sync bridge): `CONN_MAX_AGE=0` async-safety is correct; this phase owns the *scaling* strategy only.
- Phase 12 (Production ops): OPS-008 already documented the no-`/metrics`/no-SLO gap; PERF-001 is the Performance phase's view of the same absence.
