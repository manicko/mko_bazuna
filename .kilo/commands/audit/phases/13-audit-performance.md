# 13 — Performance & Scalability

> Audit phase. LLM-auditor instruction. Architecture-agnostic: described via
> ARCHITECTURAL LAYERS, ZONES OF RESPONSIBILITY, KEY RISKS, GOALS. NOT tied to
> specific files, modules, or functions. Must stay valid if the architecture changes.
>
> **Output mode:** `problems-only` — report only findings; do not narrate a clean bill of health.

## 1. Goal

Assert that the system's performance and scalability strategy is defined, measured,
and enforced: spec-derived SLOs with error budgets are defined, measured, and
alerted on; the caching strategy is correct under invalidation and cache-stampede
conditions; connection pooling is appropriate for target scale; query performance is
governed by profiling discipline (not FTS-index freshness alone); and load/stress
testing is part of the CI or release process.

Evidence (Phase 13 research — Verdict: all 6 findings RESOLVED against the current
tree): spec-derived SLOs are defined as `PerformanceSLO(IntEnum)`; error budgets are
tracked via burn-rate alerts (`prometheus-slo-alerts.yaml`) over 14.4-min windows; a
live SLO dashboard (`grafana-slo-dashboard.json`) wires django-Prometheus metrics to
SLO constants; and CI gates regressions via the `TestSearchResponseSLORegression`
exit-code gate. Findings PERF-001 (no SLOs)…PERF-006 (cache convention) are all closed
and regression-locked.

## 2. System Under Audit (layers & zones)

| Zone | Concern |
|------|---------|
| **Response Budgets / SLOs** | Spec-defined latency targets (e.g. search <2s, filter <1s) are measured, alerted on, and backed by error budgets with dashboards. |
| **Caching Strategy** | All cache tiers share a single cache and route reads through a single-flight, stale-while-revalidate (SWR) wrapper: version-bump invalidation makes stale keys unreachable via TTL (no global prefix-wipe); cache keys are locale-segmented per the i18n spec; and the bounded SWR stale-TTL window spans every tier (not search-only), so cache-stampede and stale-content-serving risks are governed on all tiers. |
| **Connection Pool** | The database connection-pooling strategy (PgBouncer opt-in vs per-request connection) is appropriate for target concurrency; pooler-prepared-statement compatibility is verified. |
| **Query Performance** | Beyond FTS index freshness, query performance is governed by profiling discipline: `EXPLAIN ANALYZE` review, indexing beyond the GIN FTS vector, and `select_related`/`select_for_update` usage on non-media views. |
| **Load Testing** | A load/stress test exists in CI or release process and is run against seeded volume; regressions are gated. |

## 3. Prerequisites

- Access to the CI workflow definitions and dependency manifest.
- Ability to run the search and filter paths against a seeded database.
- Ability to inspect the cache-key schema and the cache-invalidation call sites.
- Ability to run `EXPLAIN ANALYZE` on representative queries.
- Ability to run a load/stress tool (locust/k6/hey or equivalent) against a seeded stack.
- Linter and type-checker available.

## 4. Runtime Verification (mandatory)

Execute, then capture evidence (timing, query plans, cache hit/miss, load-test output):

1. **SLO measurement** — measure public search and filter latency against spec targets over a seeded catalog → assert an SLO dashboard/alert exists; assert error-budget burn-down is tracked (not a single static threshold).
2. **Caching behavior** — trigger a cacheable path, then mutate the underlying data → assert invalidation; assert cache keys are locale-segmented; assert a cache miss under concurrent first-hit does not stampede (bounded recomputation).
3. **Pooling** — confirm the default production path uses per-request connections (`CONN_MAX_AGE` unset/zero) and PgBouncer is opt-in only → assert the pooler is NOT on the default deploy path.
4. **Query profiling — RESOLVED** — run `EXPLAIN ANALYZE` on representative search/filter/list queries; assert index usage (no `Seq Scan` at seed scale); assert a profiling/review discipline exists (`profile_search.py`, `profile_queries` management command, `docs/ops/profiling.md`, `make profile`).
5. **Load testing — RESOLVED** — enumerate CI/release for a load/stress test; capture evidence (`locustfile.py`, CI `load-test` job, `make load`); assert p95 < `PerformanceSLO.P95_SLO_MS` is gated in CI with a non-zero exit code.

## 5. Audit Dimensions (checks + evidence)

### (a) Response budgets & SLOs — CRITICAL — RESOLVED
Spec-derived latency targets are measured and alerted on; error budgets and dashboards exist.
- Evidence: spec-derived SLOs defined as `PerformanceSLO(IntEnum)`; live SLO dashboard wiring django-Prometheus latency histograms + cache-hit-rate gauge to SLO constants; burn-rate alerts (`search_slo_burn_rate`, `search_p95_latency_slo`, `cache_hit_rate_slo`) with error-budget burn-down over 14.4-min windows; CI `TestSearchResponseSLORegression` gates SLO breaches. Regression-locked by `test_slo_constants.py`, `test_search_slo.py`, `test_observability.py`. Finding 13-PERF-001 closed.

### (b) Caching strategy — correctness & stampede — HIGH — RESOLVED
Cache invalidation is correct, cache keys are locale-segmented, and concurrent first-hit does not stampede.
- Evidence: all cache tiers route reads through a single-flight SWR wrapper with a stale-serve window; invalidation uses version-bump (`cache.incr`) so old keys become unreachable via TTL — no concurrent global prefix-wipe; cache keys include a locale segment. Regression-locked by `test_lookup_cache_swr.py` (single-flight, stale-serve, version-bump, signal invalidation), `test_cache_key_convention.py`, `test_lookup_invalidation.py`. Finding 13-PERF-002 closed.

### (c) Cache-key locale segmentation — HIGH — RESOLVED
The submenu/cache keys include the active locale so a Russian-rendered entry is not served to a Bosnian visitor.
- Evidence: cache keys contain a locale segment per the i18n spec (key format `<namespace>:v<N>:<segments...>`); the documented submenu-key-omits-language bug is closed. Regression-locked by `test_cache_key_convention.py` (asserts key shape) + locale-segment assertions in `test_lookup_cache_swr.py`. Finding 13-PERF-006 closed.

### (d) Connection-pooling strategy at scale — HIGH — RESOLVED (no finding filed)
The production connection strategy sustains target concurrency; the pooler (when enabled) is compatible with prepared statements.
- Evidence: default deploy path uses `CONN_MAX_AGE=0` (fresh connection per request, sync gunicorn workers); PgBouncer is profile-gated opt-in only (NOT on the default deploy path); `prepare_threshold: None` on the pooler path makes the pooler prepared-statement compatible. Verified correct — no finding filed.

### (e) Query performance discipline — HIGH — RESOLVED
Beyond FTS freshness, queries are governed by profiling and indexing discipline.
- Evidence: `EXPLAIN ANALYZE` profiling harness (`profile_search.py` cProfile over the full search stack; `profile_queries` management command asserting no `Seq Scan on ads` at seed scale ≥10k rows on 6 representative querysets); indexes beyond the GIN FTS vector; `select_related`/`select_for_update` discipline on listing views; `docs/ops/profiling.md` documents review cadence (PR ⇒ 10% p95 regression ⇒ CI breach ⇒ on-call incident). Regression-locked. Finding 13-PERF-004 closed.

### (f) Load & stress testing — CRITICAL — RESOLVED
A load/stress test is part of CI and is run against seeded volume with regressions gated.
- Evidence: `locust` declared as a dev dependency; `src/benchmark/locustfile.py` defines the buyer journey (`BuyerJourneyUser`, 8 `@task` methods); CI `load-test` job seeds 120 published ads, runs locust headless (50 users, 60 s), and asserts p95 < `PerformanceSLO.P95_SLO_MS` (500 ms) with `--exit-code` gating; `make load` / `make profile` for local dev. Regression-locked. Finding 13-PERF-005 closed.

### (g) Caching / stale-content risk — MEDIUM — RESOLVED
The cache-serving-stale-content risk is bounded (stale-while-revalidate + TTL discipline).
- Evidence: every cache tier is wrapped in the SWR single-flight wrapper exposing `ttl` + `stale_ttl` — a stale-serve window bounds staleness on all tiers (search, lookups, submenu); a cold miss falls back to a safe `default` rather than blocking. Regression-locked by stale-serve assertions in `test_lookup_cache_swr.py`. Finding 13-PERF-003 closed.

## 6. Cross-Cutting (owned here, not duplicated)

This phase owns the **performance and scalability strategy**: SLOs, the caching strategy, connection pooling at scale, and load testing. It explicitly does NOT audit:

- **Phase 03 (DB concurrency atomicity, async/sync bridge correctness)** — the correctness of the async/sync bridge or transaction atomicity. Phase 03 owns bridge correctness; this phase owns whether pooling is the right strategy for target scale.
- **Phase 08 (FTS search mechanism and FTS-specific latency)** — the FTS index freshness, ranking, and search-recall behavior. Phase 08 owns the search mechanism; this phase audits general query performance, caching, SLOs, and load testing.
- **Phase 10 (code quality / module size / code-level logging)** — code-level quality gates. Phase 10 owns source hygiene; this phase owns the runtime performance/scalability strategy.

## 7. Edge Cases

- SLO defined but no alert → burn-down never triggers.
- Cache invalidated but recomputed synchronously under load → stampede / latency spike.
- Submenu cache key omits locale → Russian content served to Bosnian visitor (documented problem 09).
- PgBouncer enabled but prepares statements not reset → "prepared statement already exists" errors under reuse.
- Per-request connection (`CONN_MAX_AGE=0`) under high concurrency → connection storm beyond DB capacity.
- `delete_pattern` invalidation misses a key prefix → stale content served indefinitely.
- Load test runs only locally, never in CI → regressions slip to release.
- Search within budget in dev (small DB) but unbounded under seeded production volume.

## 8. Severity Taxonomy

- **CRITICAL — RESOLVED** (all closed; evidence: §5(a) & §4.1)
  - No SLO/error-budget/dashboard for spec-derived latency targets → **RESOLVED** — SLO constants with error budgets, live dashboard, burn-rate alerts, CI regression gate (see §5(a) & §4.1).
  - No load/stress test in CI or release process → **RESOLVED** — CI-gated load test asserting p95 vs SLO constant (see §5(f) & §4.5).
- **HIGH — RESOLVED** (all closed; evidence: §5(b), §5(c), §5(d), §5(e))
  - Cache invalidation audited only for existence, not correctness; no stampede guard → **RESOLVED** — version-bump invalidation + single-flight SWR across all cache tiers (see §5(b)).
  - Submenu cache key omits locale (stale-language serve, documented problem 09) → **RESOLVED** — locale-segmented cache keys per convention (see §5(c)).
  - `CONN_MAX_AGE=0` with no pooling rationale at target scale → **RESOLVED (no finding filed)** — per-request default with PgBouncer opt-in (see §5(d)).
  - No `EXPLAIN ANALYZE` / profiling discipline on listing/filter views → **RESOLVED** — profiling harness asserting no seq-scan at seed scale (see §5(e) & §4.4).
  - PgBouncer prepared-statement compatibility unverified → **RESOLVED (no finding filed)** — pooler prepared-statement compatibility verified (see §5(d)).
- **MEDIUM — RESOLVED** (all closed; evidence: §5(g) & §4.1)
  - Cache-serving-stale-content risk unbounded (no stale-while-revalidate / no TTL) → **RESOLVED** — bounded SWR stale-TTL window on every cache tier (see §5(g)).
  - SLOs defined but no burn-down alert (silent budget exhaustion) → **RESOLVED** — burn-rate alerts with error-budget framing (see §5(a) & §4.1).
- **LOW — RESOLVED** (all closed; evidence: §5(c) & §5(f)/§4.5)
  - No cache-key naming convention documented → **RESOLVED** — documented cache-key convention with key-shape tests (see §5(c)).
  - Load test present but not gating (informational only) → **RESOLVED** — p95 assertion gates CI exit code (see §5(f) & §4.5).

## 9. Recommended Sequence

1. Discovery — map SLOs, cache schema + invalidation call sites, pooling path, profiling discipline, load-test coverage.
2. Runtime verification (§4).
3. Per-dimension checks (§5 a–g).
4. Cross-cutting (§6) and edge cases (§7).
5. Consolidate findings.

## 10. Finding Prefix

Use `PERF-` for all findings in this phase.

## 11. Reporting

- `problems-only: true`.
- Each finding: severity, zone, evidence (timing / query plan / cache-key / load-test output / grep hit), and recommendation with effort/priority.
- Append incrementally (≤100 lines per write) to the phase findings file per `docs/99-agent/rules.md`.
