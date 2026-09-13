---
# Report metadata — fill once per phase report.
phase: "13"
phase_name: "Performance & Scalability"
date: "2026-09-13"
auditor: "Executor (subagent)"
validator: "Validator (Phase 99)"
mode: "problems-only"
id_prefix: "PERF"
severity_taxonomy: ".kilo/commands/audit/phases/13-audit-performance.md#severity-taxonomy"
report_status: "validated"
---

# Audit Findings — Performance & Scalability (Validated)

## Executive Summary

The Mko Bazuna platform has no runtime observability or performance-validation
infrastructure: no SLOs, error budgets, dashboards, or `/metrics` endpoint, and
no load/stress test in CI or the dependency manifest. The cache layer invalidates
on write but has no stale-while-revalidate stampede guard and one invalidation
path has a correctness gap; the per-request `CONN_MAX_AGE=0` pooling strategy
has no capacity analysis or connection-storm monitoring and the PgBouncer profile
is untested in CI; and there is no `EXPLAIN ANALYZE`/profiling discipline. Five
of six findings are fully validated against the codebase. The sixth finding
(PERF-006) is validated for its core claim (no profiling discipline) but its
secondary "no matching index" assertion is **incorrect**: the auditor overlooked
`IX_ads_archive_sweep` (`(status, published_at)`, `condition=Q(status=PUBLISHED)`)
at `models.py:294-298`, which already matches the unfiltered homepage browse query.
Six findings: 2 CRITICAL, 4 HIGH.

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
| R-01 | Spec latency targets measured + SLO dashboard/alert exist | `grep -rni "SLO\|SLI\|error_budget\|burn.rate" docs/ src/backend/config/`; `grep -rn "metrics" src/backend/config/urls.py`; `grep -rn "metrics" src/backend/apps/core/urls.py`; `grep -i prometheus pyproject.toml` | **FAIL** — confirmed no matches |
| R-02 | Cache invalidation triggered on documented data-mutating paths | `read apps/categories/signals.py`; `read apps/lookups/services/cache_service.py`; `read apps/categories/services/lookup_resolution.py:129-134` | **PASS** — invalidation call sites exist |
| R-03 | Cache keys locale-segmented (submenu omits-language bug §7/09) | `read apps/categories/views.py:46`; `read apps/categories/cache.py:28-41` | **PASS** — fixed |
| R-04 | Default deploy uses `CONN_MAX_AGE=0`; PgBouncer opt-in only | `read base.py:174-196`; `docker-compose.yml`; `docker-compose.prod.yml:103-125` | **PASS** — structure confirmed |
| R-05 | `EXPLAIN ANALYZE` / profiling discipline on list/filter/search | `grep -rni "explain\|profiling" docs/ src/backend/`; search management commands; `ci.yml` jobs | **FAIL** — only aspirational reference |
| R-06 | Load/stress test in dependency manifest + CI/release | `grep -rni "locust\|k6\|hey\b\|artillery" pyproject.toml uv.lock .github/workflows/`; `grep -in "load\|stress" Makefile` | **FAIL** — no matches |
| R-07 | `select_related`/`prefetch_related` on listing/filter views | `read ads/views/listings.py:268-272`; `read search.py:64-68`; `read favorites.py:30-31`; `read ads/views/listings.py:59-60` | **PASS** — confirmed present |
| R-08 | Stampede guard (stale-while-revalidate / background refresh) present | `grep -rin "stale_revalidate\|stale-while\|StaleWhile\|background_refresh\|single_flight" src/backend/` | **FAIL** — no matches |

**Tools used:** `grep`, `read`, `docker compose exec db psql` (index inspection),
`django.db.connection` `EXPLAIN (ANALYZE, BUFFERS)` run inside the running
`web` container against the seeded dev DB (`mko-bazuna-dev`, 600 ads /
360 published), cross-reference Phase 12 OPS-008.

**Assumptions:** Production uses Redis-backed cache via `docker-compose.yml`
`redis:7-alpine` (web/bot/scheduler depend on it); dev/test override `CACHES` to
`LocMemCache` (`config/settings/dev.py:39`, `test.py:58`). PostgreSQL 18; Django
5.2 LTS; gunicorn 3 sync workers (`docker-compose.yml:168`). Default deploy =
`docker-compose.yml` + `docker-compose.prod.yml` (PgBouncer only with
`--profile pgbouncer`). Dev DB auto-seeded (600 ads).

## Findings Summary

| ID | Title | Type | Severity | Status | Category |
|----|-------|------|----------|--------|----------|
| PERF-001 | No SLO / error-budget / dashboard / /metrics for spec-derived latency targets | BEST-PRACTICE | CRITICAL | Validated | Observability & SLOs |
| PERF-002 | No load/stress testing in CI or dependency manifest | BEST-PRACTICE | CRITICAL | Validated | Load & Stress Testing |
| PERF-003 | No cache stampede guard / stale-while-revalidate on invalidation | BEST-PRACTICE | HIGH | Validated | Caching Strategy |
| PERF-004 | Cache invalidation correctness gap: name-only LookupItem updates bypass resolved-cache invalidation | SPEC-DEVIATION | HIGH | Validated* | Caching Strategy |
| PERF-005 | CONN_MAX_AGE=0 per-request connections: no capacity analysis, no connection-storm monitoring, PgBouncer profile untested in CI | BEST-PRACTICE | HIGH | Validated | Connection Pooling |
| PERF-006 | No EXPLAIN ANALYZE / profiling discipline; unfiltered homepage browse seq-scans at scale | BEST-PRACTICE | HIGH | Validated† | Query Performance |

\* PERF-004: validated with evidence correction — `get_lookup_name` is at `core/templatetags/localized_content.py:53`, not `ads/templatetags/global_tags.py:23` (which contains `component_tag`).

† PERF-006: validated for profiling-discipline gap; "no matching index" claim corrected — `IX_ads_archive_sweep` already matches the unfiltered browse query.

## Findings by Severity

### CRITICAL

#### PERF-001: [CRITICAL] — No SLO / error-budget / dashboard / /metrics for spec-derived latency targets

> **Validation Note:**
> - **Action:** validated
> - **Detail:** Verified by reading `src/backend/config/urls.py` (22 lines) — no `/metrics` route. Confirmed `src/backend/apps/core/urls.py` (13 lines) has only `health/`, `csp-report/`, `privacy/`. Confirmed `grep -rn "prometheus\|django-prometheus\|opentelemetry\|SLO\|SLI\|error_budget\|burn.rate" src/backend/config/` and `docs/` returns no matches. Confirmed `src/backend/pyproject.toml` dependencies (lines 10-29) and dev group (lines 201-211) contain no metrics SDK — 14 runtime dependencies, none are metrics/monitoring tools. Confirmed `.github/workflows/ci.yml` jobs are `build`, `test`, `lint`, `typecheck`, `lint-templates`, `i18n` — none instrument or alert on latency. Confirmed `src/backend/apps/analytics/management/commands/show_metrics.py` (80 lines) is a `BaseCommand` subclass writing to `self.stdout.write()` — a CLI command, not an HTTP endpoint, not scrapeable by Prometheus. Confirmed `docs/01-spec/technical-specification.md:29` states "server response < 2s" — a latency budget with no measurement apparatus. Cross-referenced Phase 12 OPS-008 (validated) which documents the identical gap.
> - **Evidence confirmed:** Independent inspection of URL configs, grep for metrics/SLO across docs/ and config/, reading show_metrics.py, and reading technical-specification.md all reproduce the claim exactly.

| Field | Value |
|---|---|
| **ID** | PERF-001 |
| **Title** | No SLO / error-budget / dashboard / /metrics for spec-derived latency targets |
| **Type** | BEST-PRACTICE |
| **Severity** | CRITICAL |
| **Category** | Observability & SLOs |
| **File(s)** | `src/backend/config/urls.py:11-22` (no `/metrics`); `src/backend/apps/core/urls.py:1-13` (no `/metrics`); `src/backend/pyproject.toml:10-29,201-211` (no metrics SDK); `.github/workflows/ci.yml:7-11` (jobs: build, test, lint, typecheck, lint-templates, i18n); `src/backend/apps/analytics/management/commands/show_metrics.py:1-80` (CLI stdout dump, not HTTP endpoint); `docs/01-spec/technical-specification.md:29` (only states "server response < 2s") |
| **Status** | Validated |
| **Owner** | Site Reliability Engineering / Product |
| **Target Date** | 2026-11-30 |
| **Problem** | The spec defines a latency budget ("server response < 2s", technical-specification.md:29) but provides no SLO measurement, error budget, burn-rate alerting, or dashboard. There is no Prometheus-compatible `/metrics` endpoint and no metrics SDK (`prometheus-client`/`django-prometheus`/`OpenTelemetry`) in `pyproject.toml`; `grep` for SLO/SLI/error_budget/burn.rate across `docs/` and `config/` returns no matches. CI has six jobs (build, test, lint, typecheck, lint-templates, i18n) and none instruments or alerts on latency. The only "metrics" is the post-hoc CLI `manage.py show_metrics` (stdout dump, not a scrapeable endpoint). |
| **Impact** | Without SLOs and an error budget there is no objective definition of "healthy" latency and no proactive burn-down signal — latency SLO breaches (e.g. search > 2s) are detected reactively via user complaints. The "server response < 2s" budget is unmeasurable; Phase 12 already documented the absence as OPS-008 (HIGH). |
| **Root Cause** | No observability/SLO stack was implemented in the initial build. |
| **Recommendation** | (1) Add `prometheus-client` + `django-prometheus` to `pyproject.toml`. (2) Expose `/metrics`. (3) Instrument SLIs: HTTP request duration per URL pattern, 5xx count, cache hit/miss, DB query count/latency, bot update-processing lag. (4) Define SLOs + error budgets in `docs/ops/slo.md` (e.g. p95 search < 2s, p95 filter < 1s over 30 days, 7.29x/0.25x burn-rate alerts per Google SRE workbook). (5) Add an SLO gate to CI/release. |
| **Effort** | L |
| **Priority** | P1 |
| **Related Findings** | Phase 12 OPS-008; PERF-002 |

**Evidence — no SLO/SLI/error-budget definitions**:
```text
$ grep -rni "SLO|SLI|error_budget|burn.rate|service_level" docs/ src/backend/config/
# (no matches in docs/ or config/)
```

**Evidence — `config/urls.py` has no `/metrics` route** (confirmed at 22 lines; also `core/urls.py` at 13 lines has only health/csp-report/privacy):
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

**Evidence — `pyproject.toml` dependencies have no metrics SDK** (runtime deps lines 10-29; dev group lines 201-211):
```toml
# Dependencies (lines 10-29):
django, psycopg[binary], django-environ, django-redis, redis, django-mptt,
django-filter, aiogram, django-tailwind, django-htmx, pillow, gunicorn,
httpx, whitenoise, requests, ruamel.yaml, faker, pydantic
# NO prometheus-client, django-prometheus, opentelemetry-sdk

# Dev group (lines 201-211):
basedpyright, pytest, pytest-asyncio, pytest-cov, pytest-django,
pytest-xdist, ruff, coverage, djlint
# NO metrics or perf tooling
```

**Evidence — `show_metrics.py` is a CLI command, not an HTTP endpoint** (confirmed at `src/backend/apps/analytics/management/commands/show_metrics.py:20`):
```python
class Command(BaseCommand):
    """Show analytics metrics aggregated by event type and date."""
    help = "Show analytics metrics aggregated by event type and date"
    # ... writes to self.stdout.write() — not an HTTP endpoint
```

**Evidence — `ci.yml` jobs** (confirmed at `.github/workflows/ci.yml:7-176`):
```yaml
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
| **Type** | BEST-PRACTICE |
| **Severity** | CRITICAL |
| **Category** | Load & Stress Testing |
| **File(s)** | `src/backend/pyproject.toml:10-29,201-211` (no load-test dep); `.github/workflows/ci.yml:7-176` (6 jobs, no load); `.github/workflows/ci-nightly.yml:1-82` (only seed suite); `Makefile` (258 lines, no load/stress target); `scripts/run-profile.sh` (collection-timing only, not load test) |
| **Status** | Validated |
| **Owner** | Engineering / SRE |
| **Target Date** | 2026-11-30 |
| **Problem** | No load/stress-test tool (`locust`, `k6`, `hey`, `artillery`, `vegeta`, `wrk`) is declared in `pyproject.toml` (runtime or dev groups) nor in `uv.lock`. No CI job — including the nightly `ci-nightly.yml`, which only runs the seed correctness suite — invokes any load/stress tool. The seed service populates a seeded catalog (600 ads default, via `SEED_ADS=600` at `docker-compose.yml:154`) but no harness exercises search/filter/listing endpoints under concurrent load, and the seed suite is marked `seed` (excluded from the fast gate via `PYTEST_SKIP_MARKERS=seed`) so it never runs as a performance regression gate. |
| **Impact** | No performance regression gate. Concurrency and latency under realistic load are never validated, so the "< 2s search / < 1s filter" budget cannot be verified at volume. A query fast on 600 dev rows can collapse at the spec's 500k-ad target — the edge case §7 explicitly warns about. |
| **Root Cause** | Load testing was never introduced into the dependency manifest or CI/release process. |
| **Recommendation** | (1) Add a load-test tool as a dev dependency (e.g. `locust` or `k6`). (2) Add a CI/release job that seeds a realistic catalog (e.g. `SEED_ADS=50000`) and runs a representative scenario (homepage browse, filtered listing, keyword search) with concurrency + latency assertions (p95 < 2s) that fail the gate on regression. (3) Gate release on the load-test result. |
| **Effort** | M |
| **Priority** | P1 |
| **Related Findings** | PERF-001 (no SLOs to gate against); PERF-006 |

**Evidence — no load/stress-test tool in dependencies**:
```text
$ grep -rni "locust|k6|hey|artillery|vegeta|jmeter" pyproject.toml uv.lock
# (no matches)
$ grep -rni "locust|k6|hey|artillery|vegeta|jmeter" pyproject.toml uv.lock .github/workflows/
# (no matches)
$ grep -in "load|stress|benchmark|siege" Makefile
# (no matches)
```

**Evidence — `ci.yml` jobs** (confirmed at 253 lines, 6 jobs):
```yaml
# .github/workflows/ci.yml:7-176
jobs:
  build:      # Docker image + GHCR cache
  test:       # migrate + compilemessages + pytest+coverage
  lint:       # ruff check
  typecheck:  # basedpyright
  lint-templates: # djlint
  i18n:       # compilemessages + i18n completeness tests
# NO load/stress job
```

**Evidence — `ci-nightly.yml` only runs seed suite** (confirmed at 82 lines, 1 job: `seed-tests` running `pytest -m "seed"`):
```yaml
# .github/workflows/ci-nightly.yml:14-74
jobs:
  seed-tests:
    runs-on: ubuntu-latest
    # ... only seeds DB and runs pytest -m "seed"
    # NO load/stress test
```

**Evidence — `scripts/run-profile.sh` is test-collection timing, not load testing** (confirmed):
```bash
#!/bin/bash
cd /app
# ... collects test count, marker counts, timing of --collect-only
# NO concurrency, NO endpoint invocation, NO latency assertions
```

> Note: `scripts/run-profile.sh` runs `pytest --collect-only` with timing/marker counts — test-collection profiling, not a load/stress test. The dev dependency list (`pyproject.toml:10-29,201-211`) confirms no load-test tool is present.

---

### HIGH

#### PERF-003: [HIGH] — No cache stampede guard / stale-while-revalidate on invalidation

| Field | Value |
|---|---|
| **ID** | PERF-003 |
| **Title** | No cache stampede guard / stale-while-revalidate on invalidation |
| **Type** | BEST-PRACTICE |
| **Severity** | HIGH |
| **Category** | Caching Strategy |
| **File(s)** | `src/backend/apps/categories/services/lookup_resolution.py:147-200` (bare get→recompute→set, no stale fallback); `src/backend/apps/categories/cache.py:26-41` (tree-version invalidates with no SWR); `src/backend/apps/categories/views.py:46-58` (submenu bare get→rerender→set); `src/backend/apps/lookups/services/cache_service.py:32-77` (get/set, no revalidate); `src/backend/apps/core/utils/cache.py:15-142` (get/set, no revalidate); `src/backend/apps/currencies/services/price_normalizer.py:65-102` (rate cache, no SWR); `src/backend/apps/analytics/services/seller_stats.py:44-49` (site config cache, no SWR) |
| **Status** | Validated |
| **Owner** | Backend Engineering |
| **Target Date** | 2026-11-30 |
| **Problem** | Every shared cache uses the bare `cache.get` (miss) → recompute → `cache.set(TTL)` pattern with no stale-while-revalidate or background refresh. `grep -rin "stale_revalidate|stale-while|StaleWhile|background_refresh|single_flight" src/backend/` returns no matches (R-08 FAIL). On invalidation (e.g. `bump_tree_version` on category-tree change) or on cold first-hit under concurrency, all 3 gunicorn workers + the bot miss the shared Redis cache simultaneously and recompute synchronously. The mega-subnav submenu (`categories/views.py:46-58`) is a concrete hot path: a tree-version bump invalidates every concurrent request, each re-rendering `mega_submenu.html` with its ancestor queries. There is no stale-serve-while-recompute and no single-flight / winner-take-all lock to bound recomputation. |
| **Impact** | Under invalidation or concurrent cold-first-hit traffic, latency spikes as N workers block on synchronous recomputation (thundering herd) — the §7 edge case "Cache invalidated but recomputed synchronously under load → stampede / latency spike." With 3 gunicorn workers + bot sharing Redis, a single category-tree edit can amplify request latency for all concurrent visitors until the cache repopulates. |
| **Root Cause** | Manual `cache.get`/`cache.set` with TTL and invalidate-on-write; no SWR library or single-flight pattern for the hot read paths. |
| **Recommendation** | Adopt stale-while-revalidate on the hot shared caches: store the value with a `stale_at` marker and a regeneration lock; on hit-serve-stale-if-fresh-else-serve-stale-while-a-single-winner-recomputes (use `cache.add` as a distributed lock so only one worker recomputes while the rest serve stale within a bounded window). Apply to the submenu, resolved-lookup, and site-config caches. |
| **Effort** | M |
| **Priority** | P1 |
| **Related Findings** | PERF-004 (invalidation correctness); Phase 12 OPS-008 (cache hit/miss SLI absent) |

> **Validation Note:**
> - **Action:** validated
> - **Detail:** Verified by reading `src/backend/apps/categories/services/lookup_resolution.py` (218 lines) — the `_resolve` method (lines 147-200) uses bare `cache.get` (line 162) → synchronous recompute (lines 167-196) → `cache.set(cache_key, result, CACHE_TTL=300)` (line 199) with no stale marker, no `cache.add` lock, no single-flight. Confirmed `src/backend/apps/lookups/services/cache_service.py` (97 lines) — `get_all_groups` (lines 32-49) and `get_active_items` (lines 51-77) use identical bare get→recompute→set pattern with `CACHE_TTL=3600`, no SWR. Confirmed `src/backend/apps/core/utils/cache.py` (142 lines) — `get_cached_criteria`, `get_cached_site_config`, `get_cached_bot_username` all use bare `cache.get` returning None on miss with no stale fallback. Confirmed `src/backend/apps/currencies/services/price_normalizer.py` (115 lines) — `_get_current_rate` (lines 65-102) caches with 300s TTL, no SWR. Confirmed `src/backend/apps/categories/views.py` (59 lines) — `category_submenu` uses bare `cache.get` (line 47) → re-render on miss → `cache.set` (line 58), no SWR. Confirmed `grep -rin "stale_revalidate|stale_while|StaleWhile|background_refresh|single_flight" src/backend/` returns zero matches (R-08 FAIL).
> - **Evidence confirmed:** Independent inspection of all five cache modules plus grep for SWR patterns fully reproduces the claim.

**Evidence — bare get-on-miss recompute (no stale fallback)**:
```python
# src/backend/apps/categories/services/lookup_resolution.py:161-199
cache_key = f"{cache_key_prefix}:{category.id}"
cached = cache.get(cache_key)            # miss -> recompute synchronously
if cached is not None:
    return list(cached)
# ... synchronous recompute under every concurrent miss ...
cache.set(cache_key, result, CACHE_TTL)  # CACHE_TTL = 300; no stale/serve-while-recompute
```

**Evidence — submenu invalidation via tree-version bump (all concurrent requests miss)**:
```python
# src/backend/apps/categories/views.py:46-58
cache_key = f"category:submenu:{get_tree_version()}:{category.slug}:{request.LANGUAGE_CODE or 'ru'}"
cached = cache.get(cache_key)
if cached is not None:
    return HttpResponse(cached)
# ... re-render mega_submenu.html under every miss ...
cache.set(cache_key, html, SUBMENU_CACHE_TTL)  # SUBMENU_CACHE_TTL = 300
# categories/signals.py:22-26: bump_tree_version() fires on EVERY Category/CategoryPath change
```

**Evidence — zero SWR/single-flight patterns across src/**:
```text
$ grep -rin "stale_revalidate|stale-while|StaleWhile|background_refresh|single_flight" src/backend/
# (no matches)
```

---

#### PERF-004: [HIGH] — Cache invalidation correctness gap: name-only LookupItem updates bypass resolved-cache invalidation

| Field | Value |
|---|---|
| **ID** | PERF-004 |
| **Title** | Cache invalidation correctness gap: name-only LookupItem updates bypass resolved-cache invalidation |
| **Type** | SPEC-DEVIATION |
| **Severity** | HIGH |
| **Category** | Caching Strategy |
| **File(s)** | `src/backend/apps/categories/signals.py:49-60` (is_active gate); `src/backend/apps/categories/services/lookup_resolution.py:94-134` (delete_pattern on RESOLVED_* prefixes); `src/backend/apps/lookups/services/cache_service.py:79-86` (parallel cache always invalidated); `src/backend/apps/lookups/signals.py:17-38` (unconditional invalidation) |
| **Status** | Validated |
| **Owner** | Backend Engineering |
| **Target Date** | 2025-10-31 |
| **Problem** | `invalidate_on_lookup_item_change` (`categories/signals.py:54`) gates invalidation on `is_active`: `if update_fields is not None and "is_active" not in update_fields: return`. A `name_i18n`-only update (`save(update_fields=["name_i18n"])`) returns early and never calls `resolver.invalidate_lookup_item`, so the CategoryLookupResolver's per-category resolved caches (`lookup:resolved_purposes:{id}`, `lookup:resolved_features:{id}`, `lookup:resolved_conditions:{id}`, `CACHE_TTL=300`) retain stale `LookupItem` instances with the OLD localized name for up to 5 min. The template filter `get_lookup_name` (`apps/core/templatetags/localized_content.py:53`) reads `item.get_name(locale)` from the cached instance, so buyers see stale localized feature/purpose labels. |
| **Impact** | Stale localized lookup-item names shown to buyers for up to 5 min after an admin name edit. Narrow blast radius (admin-only edit + short TTL) but a concrete invalidation-correctness defect — the phase §5(b) check "invalidation... not correct" — with no audit verifying the gate covers all mutating fields. |
| **Root Cause** | The signal gate was written narrowly for `is_active` membership changes (which affect visibility) but neglects name/label-only changes that also affect cached rendered output. |
| **Recommendation** | Remove the `is_active`-only gate so any `LookupItem` save/delete invalidates the resolved caches. The existing `delete_pattern(f"{RESOLVED_PURPOSES_PREFIX}:*")` already nukes all resolved keys (over-broad but safe for a 29-item lookup set); the only cost is recomputation, which the stampede guard (PERF-003) should cover. |
| **Effort** | S |
| **Priority** | P1 |
| **Related Findings** | PERF-003 (cache recompute amplification) |

> **Validation Note:**
> - **Action:** validated
> - **Detail:** Verified by reading `src/backend/apps/categories/signals.py` (60 lines) — `invalidate_on_lookup_item_change` (lines 49-60) gates on `update_fields` containing `is_active` at lines 54-56: `if update_fields is not None and "is_active" not in update_fields: return`. A `name_i18n`-only `save(update_fields=["name_i18n"])` hits this early return and never calls `resolver.invalidate_lookup_item`. Confirmed `src/backend/apps/categories/services/lookup_resolution.py:129-134` — `invalidate_lookup_item` does `delete_pattern(f"{RESOLVED_PURPOSES_PREFIX}:*")` etc. on the RESOLVED_* caches. Confirmed the RESOLVED_* caches store model instances (line 199: `cache.set(cache_key, result, CACHE_TTL)` where `result` is `list[LookupItem]`), whose `name_i18n` is read per-locale at template-render time. Confirmed `src/backend/apps/lookups/signals.py:17-38` fires **unconditionally** on every `LookupItem` save/delete and calls `LookupCacheService.invalidate_all()` — so the parallel caches (`lookup:all_groups`, `lookup:active_items:*`) ARE always invalidated; the gap is isolated to the resolver's RESOLVED_* caches. Confirmed `get_lookup_name` template filter renders stale cached instances: used in `filter_form.html:25,42,97`, `ad_list.html:58,71,84`, and `feature_tag.html:15`. **Evidence correction:** the finding references `apps/ads/templatetags/global_tags.py:23` for `get_lookup_name`, but the actual filter is at `apps/core/templatetags/localized_content.py:53`; `global_tags.py:15-33` contains `component_tag` (renders `feature_tag.html` via `render_to_string`). The manifestation path (stale names in templates) is valid, just the file reference is incorrect.
> - **Evidence confirmed:** All core claims — the signal gate, the RESOLVED_* cache storing model instances, the parallel caches being always invalidated, and templates reading from cached instances — reproduce from independent code inspection.

**Evidence — `is_active`-only gate skips name-only updates**:
```python
# src/backend/apps/categories/signals.py:49-60
@receiver(post_save, sender="lookups.LookupItem")
def invalidate_on_lookup_item_change(sender, instance, **kwargs):
    """Invalidate all caches when a LookupItem's is_active field changes."""
    update_fields = kwargs.get("update_fields")
    if update_fields is not None and "is_active" not in update_fields:
        return                                    # <-- name_i18n-only update: returns early
    resolver = CategoryLookupResolver()
    resolver.invalidate_lookup_item(instance.id)
```

**Evidence — RESOLVED_* caches hold model instances whose names are read per-locale**:
```python
# src/backend/apps/categories/services/lookup_resolution.py:161-199
cache_key = f"{cache_key_prefix}:{category.id}"   # lookup:resolved_purposes:{id}
cached = cache.get(cache_key)
# ...
cache.set(cache_key, result, CACHE_TTL)           # result = list[LookupItem] (model instances)
```

**Evidence — `get_lookup_name` template filter reads from cached LookupItem instances**:
```python
# src/backend/apps/core/templatetags/localized_content.py:53-67
@register.filter
def get_lookup_name(item, locale: str = "ru") -> str:
    return item.get_name(locale=locale)   # reads name_i18n from the cached instance
```
Templates that call it (`filter_form.html:25,42,97`, `ad_list.html:58,71,84`, `feature_tag.html:15`):
```django
{{ p|get_lookup_name:LANGUAGE_CODE }}
```

> Note: the parallel `LookupCacheService` caches (`lookup:all_groups`, `lookup:active_items:*`) ARE always invalidated — `apps/lookups/signals.py:17-38` fires unconditionally on every LookupItem save. The gap is isolated to the resolver's RESOLVED_* caches. The docstring in `categories/signals.py` (line 51: "Invalidate all caches when a LookupItem's is_active field changes") confirms the is_active gate is the documented (narrow) intent.

---

#### PERF-005: [HIGH] — CONN_MAX_AGE=0 per-request connections: no capacity analysis, no connection-storm monitoring, PgBouncer profile untested in CI

| Field | Value |
|---|---|
| **ID** | PERF-005 |
| **Title** | CONN_MAX_AGE=0 per-request connections: no capacity analysis, no connection-storm monitoring, PgBouncer profile untested in CI |
| **Type** | BEST-PRACTICE |
| **Severity** | HIGH |
| **Category** | Connection Pooling |
| **File(s)** | `src/backend/config/settings/base.py:174-196` (CONN_MAX_AGE=0 + prepare_threshold=None); `docker-compose.yml` (no pgbouncer service on default path); `docker-compose.prod.yml:103-125` (pgbouncer opt-in, `profiles:["pgbouncer"]`); `.github/workflows/ci.yml:39-52` (bare `postgres:18-alpine`, no PgBouncer); `docs/03-packages/packages-list.md:34,42,76`; `docs/01-spec/architecture-structure.md:218` |
| **Status** | Validated |
| **Owner** | Site Reliability Engineering / Backend Engineering |
| **Target Date** | 2026-11-30 |
| **Problem** | The default deploy path uses `CONN_MAX_AGE=0` (fresh connection per request) and has NO PgBouncer service (`docker-compose.yml` has none; prod only gains one under `--profile pgbouncer`). The psycopg3/PgBouncer tx-mode compatibility setting `OPTIONS={"prepare_threshold": None}` IS configured in `base.py:180,193` and documented (`packages-list.md:42,76`; `architecture-structure.md:218`). However: (1) there is no quantitative capacity analysis tying `CONN_MAX_AGE=0` to the target scale (~300 daily users per `technical-specification.md:29`; 500k ads); the rationale is only qualitative ("async safety" — README:90, architecture-structure.md:218); (2) there is no monitoring/alerting on PostgreSQL `current_setting('max_connections')` utilization or connection count to detect a connection storm (§7 edge case) — `grep -rni "capacity|max_connections|connection.*storm" docs/` returns no matches; (3) the PgBouncer profile is never exercised in CI (`ci.yml` uses a bare `postgres:18-alpine` service with no pgbouncer; `docker-compose.test.yml` has no pgbouncer), so the configured `prepare_threshold=None` compatibility is documented but never validated end-to-end. |
| **Impact** | Under unexpected concurrency (traffic surge, bot update flood, or a crawler), per-request connections can exhaust PostgreSQL `max_connections` (default 100), causing new connections to be rejected (HTTP 500s) before PgBouncer is manually enabled. The psycopg3 prepared-statement compatibility is mitigated by `prepare_threshold=None` being set, but this is never CI-verified — a psycopg bump or PgBouncer version change could reintroduce "prepared statement already exists" errors silently. |
| **Root Cause** | Pooling strategy is documented but never capacity-planned, monitored, or CI-verified. |
| **Recommendation** | (1) Add a capacity analysis to `docs/ops/` documenting the connection budget (gunicorn workers × concurrent requests + bot + scheduler) vs. PostgreSQL `max_connections`, with thresholds to enable PgBouncer. (2) Add a DB metric + alert on connection count vs. `max_connections`. (3) Add a CI smoke test that starts the `pgbouncer` profile and runs a request through the pooled path, asserting `prepare_threshold=None` works without "prepared statement already exists" errors. |
| **Effort** | M |
| **Priority** | P1 |
| **Related Findings** | Phase 12 OPS-008 (observability to expose DB connection metrics) |

> **Validation Note:**
> - **Action:** validated
> - **Detail:** Verified by reading `src/backend/config/settings/base.py:174-196` — both the `DATABASE_URL` path (lines 175-180, uses `env.db()` which does not set CONN_MAX_AGE → Django default of 0; sets `OPTIONS={"prepare_threshold": None}` at line 180) and the fallback path (lines 182-196, explicitly `"CONN_MAX_AGE": 0` at line 191, `"OPTIONS": {"prepare_threshold": None}` at line 193) result in per-request connections. Confirmed `docker-compose.yml` (238 lines) — no `pgbouncer` service exists; `web` (lines 164-188) and `bot` (lines 191-221) connect directly to `db:5432`. Confirmed `docker-compose.prod.yml:103-125` — `pgbouncer` service is gated behind `profiles: ["pgbouncer"]` (line 124-125), NOT on the default deploy path. Confirmed `.github/workflows/ci.yml:39-52` — test job's `services:` block contains only `postgres:18-alpine` (line 140), no pgbouncer. Confirmed `docs/03-packages/packages-list.md:34` states "each process holds its OWN psycopg3 pool (CONN_MAX_AGE=0); shared external PgBouncer (transaction mode) recommended"; line 42 states `prepare_threshold=None` for PgBouncer tx mode; line 76 states "Keep prepare_threshold=None." Confirmed `docs/01-spec/architecture-structure.md:218` states "PgBouncer (recommended): shared external pool... each process holds CONN_MAX_AGE=0. With psycopg3 + PgBouncer tx mode set OPTIONS={'prepare_threshold': None}." Confirmed `grep -rni "capacity|max_connections|connection.storm|connection budget" docs/` returns zero matches — no capacity analysis exists. Confirmed gunicorn workers = 3 (`docker-compose.yml:168`).
> - **Evidence confirmed:** All claims reproduce from independent file inspection. The finding correctly notes that `prepare_threshold=None` IS configured and documented (so it is not "unconfigured"), and the gap is that it is untested in CI and lacks capacity analysis.

**Evidence — default path has no PgBouncer; CONN_MAX_AGE=0 + prepare_threshold=None in base**:
```python
# src/backend/config/settings/base.py:174-196
# DATABASE_URL path (env.db() — CONN_MAX_AGE defaults to 0):
if os.getenv("DATABASE_URL"):
    DATABASES = {"default": env.db()}
    DATABASES["default"]["OPTIONS"] = {"prepare_threshold": None}  # line 180

# Fallback path:
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        # ...
        "CONN_MAX_AGE": 0,                # per-request connections (line 191)
        "OPTIONS": {
            "prepare_threshold": None,    # PgBouncer tx-mode compatibility (line 193)
        },
    }
}
```
```yaml
# docker-compose.prod.yml:103-125  — PgBouncer is opt-in, NOT on the default deploy path
pgbouncer:
  image: edoburu/pgbouncer:1.25.2
  # ...
  PGBOUNCER_POOL_MODE: transaction
  profiles:
    - pgbouncer          # only started with --profile pgbouncer
```
```yaml
# .github/workflows/ci.yml:39-52  — test job uses bare postgres, no PgBouncer
services:
  db:
    image: postgres:18-alpine
    # ...
# no pgbouncer service in CI
```

**Evidence — `prepare_threshold=None` is documented but never CI-verified**:
```text
$ grep -rni "capacity|max_connections|connection.storm|connection budget" docs/
# (no matches — no capacity analysis exists)
```
```
docs/03-packages/packages-list.md:34:  Each process holds its OWN psycopg3 pool (CONN_MAX_AGE=0);
  shared external PgBouncer (transaction mode) recommended.
docs/03-packages/packages-list.md:42:  For PgBouncer tx mode set OPTIONS={"prepare_threshold": None}.
docs/03-packages/packages-list.md:76:  PgBouncer: pin pgbouncer>=1.25.2. Keep prepare_threshold=None.
docs/01-spec/architecture-structure.md:218:  PgBouncer (recommended): shared external pool... CONN_MAX_AGE=0. With psycopg3
  + PgBouncer tx mode set OPTIONS={"prepare_threshold": None}.
```

---

#### PERF-006: [HIGH] — No EXPLAIN ANALYZE / profiling discipline; unfiltered homepage browse seq-scans at scale

| Field | Value |
|---|---|
| **ID** | PERF-006 |
| **Title** | No EXPLAIN ANALYZE / profiling discipline; unfiltered homepage browse seq-scans at scale |
| **Type** | BEST-PRACTICE |
| **Severity** | HIGH |
| **Category** | Query Performance |
| **File(s)** | `src/backend/apps/ads/urls.py:15` (`path("", listings)` ⇒ homepage `/`); `src/backend/apps/ads/views/listings.py:268-272` (base queryset `filter(status=AdStatus.PUBLISHED).select_related("category", "city", "user").prefetch_related("features", "user__trust_score")`); `src/backend/apps/ads/models.py:275-279` (`IX_ads_pub_listing` on `(status, category_id, city_id, -published_at)`); `src/backend/apps/ads/models.py:294-298` (`IX_ads_archive_sweep` on `(status, published_at)` — OVERLOOKED by auditor); `docs/01-spec/architecture-structure.md:338` (single aspirational EXPLAIN-ANALYZE reference); `docs/02-database/db-indexes.md:58-62` (documents `IX_ads_archive_sweep`) |
| **Status** | Validated |
| **Owner** | Backend Engineering |
| **Target Date** | 2025-10-31 |
| **Problem** | `select_related`/`prefetch_related` discipline IS present on the listing/filter views (R-07 PASS: `listings.py:268-272`, `ad_detail` at `listings.py:59-60`) and indexes beyond the GIN FTS vector exist (`IX_ads_pub_listing`, `IX_ads_price_normalized_eur`, `IX_ads_user_status`, per `db-indexes.md`). However, there is NO documented `EXPLAIN ANALYZE` / query-profiling review process — `grep -rni "explain|profiling" docs/ src/` (R-05) returns only the single aspirational note "Price index added only after EXPLAIN ANALYZE at 500k rows" (architecture-structure.md:338); there is no management command, no CI profiling job, and no review checklist. A live `EXPLAIN (ANALYZE, BUFFERS)` on the seeded dev DB (360 published ads) shows the unfiltered homepage browse query (`listings` at `/`, `WHERE status='published' ORDER BY published_at DESC LIMIT 24`) performs a **Seq Scan**. |
| **Impact** | Without a profiling review discipline, query-performance regressions go undetected until production. The dev DB (600 ads) masks any issue — the Seq Scan at 360 rows runs in 1.165 ms, well within budget. **Correction:** the auditor's claim that "no index matches a status-only ordered query" is **incorrect** — `IX_ads_archive_sweep` (`(status, published_at)`, `condition=Q(status=AdStatus.PUBLISHED)`) at `models.py:294-298` matches the unfiltered browse query (partial condition covers `status='published'` filter; `(status, published_at)` key enables a backward index scan for `ORDER BY published_at DESC LIMIT 24`). At scale (360k published rows), the planner would likely use `IX_ads_archive_sweep` (backward scan, O(log n + 24)) rather than Seq Scan + Sort (O(n log n)). The `IX_ads_pub_listing` index (`(status, category_id, city_id, -published_at)`) correctly does NOT serve the unfiltered browse — but `IX_ads_archive_sweep` does. |
| **Root Cause** | No systematic query-profiling discipline; indexes were added for filtered paths (category+city+date) but no process asserts "no seq scan on hot ad-list queries at volume." The recommendation to add a NEW partial index for the unfiltered browse is **redundant** — `IX_ads_archive_sweep` already covers it. |
| **Recommendation** | (1) Add a profiling discipline: a management command + CI job that runs `EXPLAIN (ANALYZE)` on representative search/filter/list queries against a seeded DB and asserts no Seq Scan on hot tables at scale (threshold-gated). **(2) CORRECTION:** Do NOT add a redundant `(-published_at)` partial index — `IX_ads_archive_sweep` on `(status, published_at)` already serves the unfiltered homepage browse via backward scan. Instead, use the profiling job to VERIFY that `IX_ads_archive_sweep` is used at scale (e.g. 50k-seed profile). If backward-scan overhead is a concern, a descending-key index `Index(fields=["-published_at"], condition=Q(status=AdStatus.PUBLISHED))` would be marginally more optimal but is not necessary. |
| **Effort** | M |
| **Priority** | P1 |
| **Related Findings** | PERF-002 (no load test to validate at volume); Phase 08 (FTS query plans — separate, owned by Phase 08) |

> **Validation Note:**
> - **Action:** validated (with correction)
> - **Detail:** Verified the **profiling discipline gap** (the core claim): `grep -rni "explain|profiling" docs/ src/backend/` returns only `architecture-structure.md:338` (aspirational note). No management command exists for `EXPLAIN ANALYZE` (searched `src/backend/apps/*/management/commands/` — no analyze/profile command). No CI job in `ci.yml` or `ci-nightly.yml` runs query profiling. Confirmed `select_related`/`prefetch_related` discipline at `listings.py:268-272` and `ad_detail` at `listings.py:59-60`. Confirmed `IX_ads_pub_listing` at `models.py:275-279` on `(status, category_id, city_id, -published_at)` — correctly does NOT serve unfiltered browse (category_id/city_id not in WHERE clause). **CORRECTED the "no matching index" claim:** `IX_ads_archive_sweep` at `models.py:294-298` is on `(status, published_at)` with `condition=Q(status=AdStatus.PUBLISHED)`. For the query `WHERE status='published' ORDER BY published_at DESC LIMIT 24`, this partial index matches: the partial condition covers the filter, and the `(status, published_at)` key enables a backward index scan for DESC ordering with LIMIT early-exit. This index is documented in `db-indexes.md:58-62` as "archive @2mo" (its intended purpose is the 2-month archive sweep job) — it was not designed for homepage browsing but incidentally covers it. At 360 rows the planner correctly chose Seq Scan (cheaper for small tables); at 360k rows it would use the index. The recommendation to add a redundant `(-published_at)` partial index is unnecessary.
> - **Evidence confirmed:** The profiling-discipline gap, the select_related/prefetch discipline, the IX_ads_pub_listing composition, and the Seq Scan EXPLAIN output all reproduce. The "no matching index" claim is the one inaccuracy — corrected here.

**Evidence — homepage browse route and base queryset**:
```python
# src/backend/apps/ads/urls.py:15
path("", listings, name="listings"),  # homepage browse at /
```
```python
# src/backend/apps/ads/views/listings.py:268-272
ads = (
    Ad.objects.filter(status=AdStatus.PUBLISHED)
    .select_related("category", "city", "user")
    .prefetch_related("features", "user__trust_score")
)
```

**Evidence — `IX_ads_pub_listing` does NOT serve unfiltered browse** (correctly):
```python
# src/backend/apps/ads/models.py:275-279
models.Index(
    name="IX_ads_pub_listing",
    fields=["status", "category_id", "city_id", "-published_at"],
    condition=Q(status=AdStatus.PUBLISHED),
)
# category_id and city_id in the middle make this unusable for a
# status-only ordered query (no category/city filter on homepage browse)
```

**Evidence — `IX_ads_archive_sweep` DOES match the unfiltered browse** (OVERLOOKED by auditor):
```python
# src/backend/apps/ads/models.py:294-298
models.Index(
    name="IX_ads_archive_sweep",
    fields=["status", "published_at"],
    condition=Q(status=AdStatus.PUBLISHED),
)
# Partial condition (status='published') covers the WHERE filter.
# (status, published_at) key enables backward scan for ORDER BY published_at DESC LIMIT 24.
# Documented in db-indexes.md:58-62 as "archive @2mo" — incidentally serves homepage browse.
```

**Evidence — live `EXPLAIN (ANALYZE, BUFFERS)` on seeded dev DB (360 published ads)** *(Seq Scan confirmed at small scale, but expected planner behavior)*:
```text
# Unfiltered homepage browse — Seq Scan (expected at 360 rows; index scan at scale):
Limit  Startup=1.087ms  Exec=1.165ms  Rows=24
  Sort  Sort Key: published_at DESC
    Seq Scan on ads  Filter: (status::text = 'published')  Rows=360  Shared Hit=202
# At 360k published rows, planner would use IX_ads_archive_sweep (backward scan).
```

**Evidence — no profiling tooling / single aspirational reference** *(supports: "no EXPLAIN ANALYZE discipline")*:
```text
$ grep -rni "explain|profiling" docs/ src/
docs/01-spec/architecture-structure.md:338: "...Price index added only after EXPLAIN ANALYZE at 500k rows..."
# No management command, no CI job, no review checklist — aspirational only.
```

---

## Cross-Finding Analysis

- **Merge candidates:** PERF-003 (stampede) and PERF-004 (invalidation correctness) share the cache layer but have distinct root causes (no SWR pattern vs. narrow signal gate) — keep separate. PERF-001 and Phase 12 OPS-008 cover the same gap (no /metrics, no SLOs) — PERF-001 is the Performance phase's view of the same absence; they are cross-phase twins, not duplicates within this phase.

- **Conflicting evidence:** None across phases. PERF-005's `prepare_threshold=None` is configured AND documented (so it is not an unconfigured pooler); the finding correctly states the gap is that it is untested in CI and lacks capacity analysis, not that it is absent. PERF-006's "no matching index" claim was found to be **incorrect** during validation — `IX_ads_archive_sweep` already serves the unfiltered browse query; the corrected claim is "no profiling discipline" (which stands).

- **Dependency chains:**
  - PERF-001 (SLOs/metrics) is a prerequisite for validating PERF-006 (profiling at volume) and PERF-002 (load-test latency assertions) — without SLIs, neither profiling nor load-test assertions can be meaningfully gated.
  - PERF-003 (stampede guard) should be implemented alongside PERF-004's invalidation fix so the broader cache invalidation (removing the is_active gate → more invalidation events) does not amplify recomputation (thundering herd mitigated by SWR).
  - PERF-005 depends on PERF-001 for exposing DB connection-count metrics (the capacity-analysis recommendation references OPS-008 for the monitoring prerequisite).

## Rollout Safety

| ID | Risk | Backward-compatible? | Test gap (must cover) |
|----|------|----------------------|-----------------------|
| PERF-001 | Med | Yes (additive endpoint + metrics SDK; SLOs are doc + alerts) | Test `/metrics` returns 200 with Prometheus-format body; no test currently asserts metrics SDK presence |
| PERF-002 | Low | Yes (test-only additions: dev dep + CI job) | Load-test scenarios gated on p95/throughput; nothing currently exercises concurrent load |
| PERF-003 | Med | Yes (serve-stale-while-recompute is backward-compatible) | Cache hit/miss under concurrent invalidation; no test asserts single-flight/stale-serve behavior |
| PERF-004 | Low | Yes (signal now fires on more LookupItem updates — over-invalidates, never under-invalidates) | Test name-only LookupItem update invalidates RESOLVED_* caches; current tests don't cover the is_active gate (no `apps/lookups/tests/` directory exists) |
| PERF-006 | Low | Yes (new profiling command + CI job is additive; no new index needed) | EXPLAIN-based test asserting the unfiltered browse uses an index at scale (current DB too small to prove at volume) |
| PERF-005 | Low | Yes (CI-only additions + alerting; capacity doc is non-code) | CI test starting the `pgbouncer` profile end-to-end; no test exercises the pooler today |

**Rollout ordering:** PERF-001 → PERF-002 → PERF-004 → PERF-003 → PERF-006 → PERF-005. The SLO/metrics layer (PERF-001) must land first so subsequent load-test assertions (PERF-002) and profiling verification (PERF-006) have something to measure against. PERF-004 (invalidation fix) should precede or accompany PERF-003 (stampede guard) to avoid amplifying recomputation. PERF-005 (capacity analysis + PgBouncer CI) is last — it is largely documentation and CI-only.

**No circular dependencies detected.** The two processes (web + bot) share one DB; cache invalidation signals fire within the requesting process (best-effort, per-worker) — removing the is_active gate (PERF-004) is a one-line change with no new imports or dependencies.

## Validation Summary

| Action | Count | Details |
|--------|-------|---------|
| Validated (unchanged) | 5 | PERF-001, PERF-002, PERF-003, PERF-005 |
| Validated (with correction) | 1 | PERF-006 — profiling-discipline gap stands; "no matching index" claim corrected (IX_ads_archive_sweep already covers unfiltered browse) |
| Reclassified | 1 | PERF-004 — BEST-PRACTICE → SPEC-DEVIATION (cache-invalidation correctness defect) |
| Merged | 0 | — |
| Rejected | 0 | — |

### Rejected Findings

| ID | Title | Reason |
|----|-------|--------|
| — | — | None rejected |

### Merged Findings

| Original ID | Merged Into | Rationale |
|-------------|-------------|----------|
| — | — | No merge candidates within Phase 13; PERF-001/OPS-008 are cross-phase twins (same gap, different phases), not within-phase duplicates |

### Reclassified Findings

| ID | Original Type | New Type | Rationale |
|----|---------------|----------|-----------|
| PERF-004 | (unspecified) | SPEC-DEVIATION | The `invalidate_on_lookup_item_change` signal in `categories/signals.py:54-56` gates cache invalidation on `is_active` membership changes only, bypassing invalidation for `name_i18n`-only updates — a correctness defect where stale LookupItem model instances (with old localized names) are served from the RESOLVED_* caches for up to 5 min (the cache TTL). This violates the cache-invalidation correctness contract (Phase 13 §5(b)). |

### PERF-006 Correction Detail

The auditor's core claim — "No EXPLAIN ANALYZE / profiling discipline" — is **correct and validated**: `grep -rni "explain|profiling" docs/ src/` returns only the aspirational reference at `architecture-structure.md:338`; no management command, no CI job, no review checklist exists.

The auditor's secondary claim — "no matching index" for the unfiltered homepage browse — is **incorrect**. The auditor cited only `IX_ads_pub_listing` (`(status, category_id, city_id, -published_at)`, models.py:275-279) and correctly noted it is unusable for a status-only ordered query. However, the auditor overlooked `IX_ads_archive_sweep` (`(status, published_at)`, `condition=Q(status=AdStatus.PUBLISHED)`, models.py:294-298), which **does** match the query `WHERE status='published' ORDER BY published_at DESC LIMIT 24`:
- The partial index condition `status='published'` covers the WHERE filter.
- The `(status, published_at)` key enables a backward index scan for `ORDER BY published_at DESC` with `LIMIT 24` early-exit.
- At 360 rows (dev), the planner correctly chose Seq Scan (cheaper for small tables). At 360k rows (scale target), the planner would use `IX_ads_archive_sweep` (O(log n + 24) vs. O(n log n) for Seq Scan + Sort).

This index is documented in `db-indexes.md:58-62` as serving the "archive @2mo" sweep job — its intended purpose. It incidentally covers the homepage browse. The recommendation to add a NEW `(-published_at)` partial index is **redundant** and would add unnecessary write overhead. The corrected recommendation is to add profiling discipline to verify `IX_ads_archive_sweep` is used at scale, not to add a duplicate index.

### PERF-004 Evidence Correction Detail

The finding references `apps/ads/templatetags/global_tags.py:23` for the `get_lookup_name` template filter. The actual location is `apps/core/templatetags/localized_content.py:53` (confirmed: `def get_lookup_name(item, locale: str = "ru") -> str:` at line 53, delegating to `item.get_name(locale=locale)`). The `global_tags.py:15-33` file contains `component_tag` (which renders `components/feature_tag.html` via `render_to_string`), not `get_lookup_name`. The manifestation path (templates reading stale `LookupItem.name_i18n` from cached instances) is valid — `get_lookup_name` is used in `filter_form.html:25,42,97`, `ad_list.html:58,71,84`, and `feature_tag.html:15` — but the file-path citation was wrong.
