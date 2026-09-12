# 13 — Performance & Scalability

> Audit phase. LLM-auditor instruction. Architecture-agnostic: described via
> ARCHITECTURAL LAYERS, ZONES OF RESPONSIBILITY, KEY RISKS, GOALS. NOT tied to
> specific files, modules, or functions. Must stay valid if the architecture changes.
>
> **Output mode:** `problems-only` — report only findings; do not narrate a clean bill of health.

## 1. Goal

Verify that the system's performance and scalability strategy is defined, measured,
and enforced: spec-derived SLOs with error budgets exist and are alerted on; the
caching strategy is correct under invalidation and cache-stampede conditions;
connection pooling is appropriate for target scale; query performance is governed by
profiling discipline (not FTS-index freshness alone); and load/stress testing is
part of the CI or release process.

## 2. System Under Audit (layers & zones)

| Zone | Concern |
|------|---------|
| **Response Budgets / SLOs** | Spec-defined latency targets (e.g. search <2s, filter <1s) are measured, alerted on, and backed by error budgets with dashboards. |
| **Caching Strategy** | A shared cache is used for site config, rate limits, and submenu data. Cache invalidation correctness, cache-key design (locale segments), cache-stampede prevention (stale-while-revalidate), and stale-content-serving risks are governed. |
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
4. **Query profiling** — run `EXPLAIN ANALYZE` on representative search/filter/list queries → assert index usage; assert a profiling/review discipline exists beyond FTS freshness.
5. **Load testing** — enumerate CI/release for a load or stress test → capture evidence; assert absence if none exists.

## 5. Audit Dimensions (checks + evidence)

### (a) Response budgets & SLOs — CRITICAL
Spec-derived latency targets are measured and alerted on; error budgets and dashboards exist.
- Evidence: SLO dashboard with targets and burn-rate alerts; absence of a dashboard or any response-budget definition is a finding. The CI test gate and code-style rules do not provide SLO measurement/alert infrastructure.

### (b) Caching strategy — correctness & stampede — HIGH
Cache invalidation is correct, cache keys are locale-segmented, and concurrent first-hit does not stampede.
- Evidence: invalidation triggered on the documented data-mutating paths (the Redis `delete_pattern` calls in the category-resolution and lookup-cache services); cache keys include a locale segment; stale-while-revalidate or equivalent stampede guard present. Invalidation calls existing but never audited for correctness, and no stampede guard, is a finding.

### (c) Cache-key locale segmentation — HIGH
The submenu/cache keys include the active locale so a Russian-rendered entry is not served to a Bosnian visitor.
- Evidence: cache keys contain a `<locale>` segment per the i18n spec; the documented bug where the submenu cache key omits language is a finding.

### (d) Connection-pooling strategy at scale — HIGH
The production connection strategy sustains target concurrency; the pooler (when enabled) is compatible with prepared statements.
- Evidence: default deploy path uses `CONN_MAX_AGE=0` (fresh connection per request); PgBouncer is profile-gated. No documented rationale for per-request connections at scale and no prepared-statement compatibility verification with the pooler is a finding.

### (e) Query performance discipline — HIGH
Beyond FTS freshness, queries are governed by profiling and indexing discipline.
- Evidence: `EXPLAIN ANALYZE` review documented; indexes beyond the GIN FTS vector; `select_related`/`select_for_update` discipline on listing views. N+1 auditing is limited to media prefetch only; no general profiling discipline is a finding.

### (f) Load & stress testing — CRITICAL
A load/stress test is part of CI or the release process and is run against seeded volume.
- Evidence: a load/stress tool declared as a dependency and a CI/release job invoking it. Absence of any load-testing tooling (locust/k6/hey) in the dependency manifest and CI is a finding.

### (g) Caching / stale-content risk — MEDIUM
The cache-serving-stale-content risk is bounded (stale-while-revalidate or TTL discipline).
- Evidence: bounded staleness policy. A cache invalidated on write but recomputed on miss with no stale fallback is a finding.

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

- **CRITICAL**
  - No SLO/error-budget/dashboard for spec-derived latency targets.
  - No load/stress test in CI or release process.
- **HIGH**
  - Cache invalidation audited only for existence, not correctness; no stampede guard.
  - Submenu cache key omits locale (stale-language serve, documented problem 09).
  - `CONN_MAX_AGE=0` with no pooling rationale at target scale.
  - No `EXPLAIN ANALYZE` / profiling discipline on listing/filter views.
  - PgBouncer prepared-statement compatibility unverified.
- **MEDIUM**
  - Cache-serving-stale-content risk unbounded (no stale-while-revalidate / no TTL).
  - SLOs defined but no burn-down alert (silent budget exhaustion).
- **LOW**
  - No cache-key naming convention documented.
  - Load test present but not gating (informational only).

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
