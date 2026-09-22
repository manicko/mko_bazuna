# 08 — Search & Full-Text Search (FTS)

> Audit phase. LLM-auditor instruction. Architecture-agnostic: described via
> ARCHITECTURAL LAYERS, ZONES OF RESPONSIBILITY, KEY RISKS, GOALS. NOT tied to
> specific files, modules, or functions. Must stay valid if the architecture changes.
>
> **Output mode:** `problems-only` — report only findings; do not narrate a clean bill of health.

## 1. Goal

Verify that the unauthenticated search experience is correct, safe, and
performant: only genuinely visible ads are returned, the FTS index is fresh,
input cannot inject SQL, category filtering is correct, and no PII leaks
through queries or logs. Translation is a publication-time concern (Phase 09)
and is not on the search critical path.

## 2. System Under Audit (layers & zones)

| Zone | Concern |
|------|---------|
| **Query Input** | Receives the raw search string from the web form (unauthenticated buyer). Must be validated and bounded. |
| **Per-language FTS** | Buyers search their own language against per-language vector columns (search_vector_ru/bs/en); no query-time translation step. Cross-ref: `apps/core/enums.py` `LanguageLocale` (canonical vector/config mapping). |
| **FTS Execution** | Native PostgreSQL full-text search over a maintained search vector (TSVECTOR + GIN), using a language-specific text-search configuration and weighted fields. |
| **Visibility Filter** | PUBLISHED only; DECLINE (browse-only) does not alter ad status so a seller's PUBLISHED ads remain searchable; WITHDRAW soft-deletes ads (status=DELETED) and bumps the cache version; expiration is status-driven (ARCHIVED/DELETED via background sweeps), not a date predicate. No 'sold' concept exists. |
| **Category Tree** | Hierarchical category navigation; a parent query must expand to all descendants. |
| **Ranking / Pagination** | Relevance ranking + bounded result sets to prevent DoS. |
| **Observability** | Search latency (p95/p99 SLOs via django-prometheus), cache hit-rate SLO (≥85 %), SEARCH_PERFORMED event recording (cache-insensitive), and PII-safe query logging (sanitized + redacted). |

## 3. Prerequisites

- Services runnable via the documented Docker commands (web + bot + DB).
- A throwaway database seeded with synthetic ad text (NO PII) across categories and statuses.
- The external translation service MUST be mockable (no real API calls / cost in tests).
- Linter, type-checker, and search tests available.

## 4. Runtime Verification (mandatory)

Execute, then capture evidence (HTTP responses, DB state, logs, latency):

1. **Visibility gating** — publish an ad → search its text → found. Set ad to any non-PUBLISHED state (moderation/rejected/archived/deleted) → NOT found. Withdraw a seller's consent → their ads become non-PUBLISHED → NOT found. **DECLINE a seller** → their PUBLISHED ads MUST still be found (search must not filter on consent state directly).
2. **Translation (publication-time)** — simulate a translator outage (circuit open / timeout / empty result); assert empty `title_en/bs` columns but non-null `search_vector_ru`, and that Russian search still matches the ad. Cite `apps/core/services/translation.py` (timeout/retry/cache/breaker/fallback).
3. **Injection** — submit SQL/injection-style and unicode/homoglyph queries → assert no injection, safe parameterized execution, no errors.
4. **Category tree** — query a parent category → assert all descendant ads included; wrong-branch ads excluded.
5. **Pagination / limits** — seed volume, search a common term → assert bounded results + pagination; empty query handled.
6. **Performance** — assert within `PerformanceSLO` targets; cite the `test_search_slo.py` regression gate (≤2 s at 60-ad seed volume) rather than a manual latency probe; no unbounded query.
7. **PII in logs** — grep search logs + analytics for identity values in query strings → assert none. Evidence: `sanitize_query_for_log` (truncate + control-char strip) and `RedactingJsonFormatter` (prod LOGGING).
8. **Encoding** — mixed Cyrillic/Latin/Montenegrin query → assert correct tokenization, no mojibake.
9. **Quality gates** — run linter, type-checker, search test suite.

## 5. Audit Dimensions (checks + evidence)

### (a) Visibility gating — CRITICAL
Only PUBLISHED ads returned. Withdrawn (soft-deleted) sellers excluded via status, NOT via a consent filter. DECLINE must NOT hide a seller's PUBLISHED ads.
- Evidence: query predicate == public-listing predicate (single source of truth); no separate consent_revoked filter that would wrongly hide DECLINEd sellers.

### (b) FTS index freshness / maintenance — CRITICAL
Search vector maintained on every relevant save/transition; existing rows backfilled.
- Evidence: publish/archive/delete transitions reflected in index; no permanently stale new ads; category-name change propagates.

### (c) Translation (publication-time) — HIGH
Per-language vector lookup; no query-time translation. Publication-time translator failures (circuit-broken / timeout / empty result) yield degraded cross-language recall (populated-vector-only), never a 500 — Russian search still matches.
- Evidence: `apps/core/services/translation.py` (timeout/retry/cache/breaker/fallback returns original text on failure); empty `title_en/bs` → empty per-language `search_vector_*`, non-null `search_vector_ru`.

### (d) Injection safety — CRITICAL
All input parameterized; no string-built SQL reaching the engine.
- Evidence: injection payloads return safe results or empty; no raw interpolation.

### (e) Category-tree filter correctness — HIGH
Descendant expansion correct; no cross-branch leakage.
- Evidence: parent query returns subtree; unrelated branches absent.

### (f) Ranking / relevance + pagination / limits — HIGH
Relevance ordering present; result sets bounded to prevent DoS.
- Evidence: pagination enforced; max results limited; latency bounded under volume.

### (g) Performance / timeout at scale — MEDIUM
GIN/trigram effectiveness; query completes within target at volume.
- Evidence: latency measured; index usage confirmed; no full scans.

### (h) PII in search logs / queries — CRITICAL
No identity values in logged query strings or analytics.
- Evidence: grep shows none; analytics stores aggregate only.

### (i) Encoding correctness — MEDIUM
Cyrillic/Montenegrin/transliteration round-trips match; no mojibake.
- Evidence: mixed-script queries tokenize correctly.

## 6. Cross-Cutting (owned here, not duplicated)
- **Visibility predicate** must be the single source of truth shared with public listing (phase 05 status + phase 06 consent semantics). Search must not re-implement divergent gating.
- **Index maintenance** must align with the ad state-machine (phase 05): publish/archive/delete must update or exclude the index.
- **Translation step** is an external integration (Phase 09 territory), publication-time only — its failure handling (degraded cross-language recall, never a 500) belongs to Phase 09, not the search path.

## 7. Edge Cases
- Ad published then searched before index updates (race) → acceptable short delay or sync update; verify behavior.
- Seller withdraws consent while ad is on a results page → disappears on refresh (no caching of withdrawn ads).
- Publication-time translator returns empty/garbage → language-specific columns may be unpopulated; degraded cross-language recall (buyer sees only ads whose per-language vector was populated), not a zero-result crash or 500.
- Very long / many-token query → bounded or rejected.
- Deep category nesting → descendant query correct and performant.
- Mixed Cyrillic+Montenegrin+Latin query.
- Ad moved ARCHIVED → PUBLISHED → re-indexed and findable.
- Duplicate / near-duplicate ads → ranking not dominated.
- Search during DB migration / index rebuild → graceful, no 500s.

## 8. Severity Taxonomy

- **CRITICAL**
  - Non-PUBLISHED / withdrawn / soft-deleted ad appears in search.
  - SQL injection via search input.
  - Revoked/withdrawn seller still searchable (when their ads should be non-PUBLISHED).
  - PII leaks in search logs or analytics query strings.
  - FTS index permanently stale (new ads unfindable).
- **HIGH**
  - Translation outage breaks search entirely with no fallback.
  - Category filter misses descendants or includes wrong branch.
  - Search logs leak PII.
  - No pagination/limit enabling DoS.
  - Unbounded query latency.
  - DECLINE incorrectly hides a seller's PUBLISHED ads from search.
- **MEDIUM**
  - Poor ranking/relevance.
  - GIN/trigram perf degradation at scale.
  - Encoding mismatch causing missed matches.
  - Translator rate-limit causing flaky search.
- **LOW**
  - Missing type hints on search helpers.
  - Log verbosity / no latency metrics.
  - No search-latency SLO assertion at seed scale → **RESOLVED** (`test_search_slo.py` asserts ≤2 s at 60-ad seed volume; `PerformanceSLO` constants present).

## 9. Recommended Sequence
1. Discovery — map search entry, query builder, FTS index, translation, category tree, ranking.
2. Runtime verification (§4).
3. Per-dimension checks (§5 a–i).
4. Cross-cutting (§6) and edge cases (§7).
5. Consolidate findings.

## 10. Finding Prefix
Use `SRH-` for all findings in this phase.

## 11. Reporting
- `problems-only: true`.
- Each finding: severity, zone, evidence (path/line/HTTP response/query output), and recommendation with effort/priority.
- Append incrementally (≤100 lines per write) to the phase findings file per `docs/99-agent/rules.md`.
