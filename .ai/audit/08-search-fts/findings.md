# Phase 08 Audit Findings — Search & Full-Text Search (FTS)

**Executor:** audit-executor
**Template:** .ai/audit/templates/audit-findings.md
**Scope (core surface):** apps.search.views.search (FTS/ranking/pagination), apps.search.services.{alert_query,popular_search,search_history}, apps.core.services.translation, apps.ads.models (Ad.search_vector* + GIN/partial indexes + trigger `ads_search_vector_fn`), apps.ads.views.listings (visibility predicate), apps.core.utils.sanitize
**Status:** complete
**Validated:** no (static analysis only; Docker runtime not executed this phase)
**Output:** problems-only (only failing checks; passing checks omitted)

---

## Findings

### SRH-001: Uncapped search query length causes DataError → HTTP 500 (trivial DoS of /search/)

| Field | Value |
|-------|-------|
| **ID** | SRH-001 |
| **Severity** | HIGH |
| **Type** | SPEC-DEVIATION |
| **Affected Modules** | src/backend/apps/search/views/search.py, src/backend/apps/search/services/popular_search.py, src/backend/apps/search/services/search_history.py, src/backend/apps/search/models.py |
| **Classification** | mandatory |

**Description:** The `/search/` view reads `q` with only `.strip()` (search.py:57) and enforces no length bound. The raw, uncapped query is then handed unconditionally to `increment_popular_search(query)` (search.py:237) and `record_search_history(...)` (search.py:238-242), neither wrapped in try/except. Those services persist the query into `PopularSearch.query` / `SearchHistory.query`, both `CharField(max_length=200)` (models.py:16, 49). Any search whose `q` exceeds 200 characters makes `get_or_create(... defaults={"query": query})` (popular_search.py:37-45) issue an `INSERT` of a >200-char value into a `varchar(200)` column -> PostgreSQL `value too long for type character varying(200)` -> `DataError` -> unhandled -> HTTP 500. The crash fires for anonymous buyers too (PopularSearch is hit on every non-empty query), so a single 201-character `?q=` takes the public search endpoint down. This violates phase §4.5 / §7 ("Very long / many-token query -> bounded or rejected") — it is neither bounded nor rejected. (Contrast `/search/autocomplete`, which is hardened by `sanitize_autocomplete_query`: 100-char cap + SQL-char strip + rate limit.)

**Evidence:**
- src/backend/apps/search/views/search.py:57 — `query = (request.GET.get("q") or "").strip()` (no max_length)
- src/backend/apps/search/views/search.py:237 — `increment_popular_search(query)` (raw, uncapped)
- src/backend/apps/search/views/search.py:238-242 — `record_search_history(... query, ...)` (raw, uncapped)
- src/backend/apps/search/models.py:16 — `query = models.CharField(max_length=200, db_index=True)` (PopularSearch)
- src/backend/apps/search/models.py:49 — `query = models.CharField(max_length=200)` (SearchHistory)
- src/backend/apps/search/services/popular_search.py:37-45 — `get_or_create(query_normalized=..., defaults={"query": query, ...})` and `.update(... query=query, ...)` (no truncation)

**Recommendation:** Bound `q` at the input edge in `search()` before any service call — e.g. `query = query[:200]` (or a named constant) so stored fields never overflow, and/or validate and reject >200 chars with a user-facing message. The cap must precede `increment_popular_search`/`record_search_history`. Add a regression test feeding a >200-char `q` and asserting HTTP 200 (not 500). Effort: trivial. Priority: high.

### SRH-002: Docs describe a search-time Montenegrin→Russian translation bridge that the code removed

| Field | Value |
|-------|-------|
| **ID** | SRH-002 |
| **Severity** | MEDIUM |
| **Type** | DOC-UPDATE |
| **Affected Modules** | docs/03-packages/packages-list.md, docs/03-packages/dependency-collisions.md, src/backend/apps/core/services/translation.py, src/backend/apps/search/views/search.py |
| **Classification** | advisory |

**Description:** The implemented search path no longer performs query-time translation. `apps.core.services.translation` is now used only at ad-publication time (translation.py:8-11: "Search/alert query translation was removed — the search path now uses language-aware per-language FTS vectors with no external translation"), and `search()` resolves the buyer's locale to a per-language vector column (search.py:184-189) with no external translator on the search critical path (config = `russian` / `simple` / `english` via `LanguageLocale.fts_config`, search.py:189). The authoritative spec already reflects this — technical-specification.md:119 and search-patterns.md:22 state "no query-time translation; buyers search per-language FTS vectors." However two package/docs files still describe the old bridge: `packages-list.md:35` ("deep-translator … Montenegrin → Russian at search time") and `dependency-collisions.md:32,60` ("Montenegrin→Russian query translation" … "governing both search-side query translation and bot-side ad-creation translation"). The code choice is better (removes an external, PII-egress-prone dependency from the unauthenticated search path), so per audit guidance the fix is to update the docs rather than revert the code. This also makes the phase scope's "Translation Bridge" zone (§2) and §5(c) largely moot — that concern now maps to publication-time translation only.

**Evidence:**
- docs/03-packages/packages-list.md:35 — "Query translation: deep-translator (Montenegrin → Russian at search time; hard timeout ~500ms + fallback to original query)."
- docs/03-packages/dependency-collisions.md:32 — deep-translator row claims "Montenegrin→Russian query translation"
- docs/03-packages/dependency-collisions.md:60 — "governing both search-side query translation and bot-side ad-creation translation"
- src/backend/apps/core/services/translation.py:8-11 — "Search/alert query translation was removed … no external translation"
- src/backend/apps/search/views/search.py:184-189 — locale-resolved per-language vector; "no external translator runs on the search critical path"
- docs/01-spec/technical-specification.md:119 — "No search queries are sent to any translation service"
- docs/01-spec/search-patterns.md:22 — "no query-time translation"

**Recommendation:** Update `packages-list.md:35` and `dependency-collisions.md:32,60` to scope deep-translator to publication-time ad translation only (matching technical-specification.md / search-patterns.md). Optionally reconcile the audit phase scope §2/§5(c) so future auditors don't re-evaluate a bridge that no longer exists. Effort: trivial. Priority: recommended.

### SRH-003: Generic `search_vector` column + GIN index maintained on every ad write but never queried

| Field | Value |
|-------|-------|
| **ID** | SRH-003 |
| **Severity** | MEDIUM |
| **Type** | BEST-PRACTICE |
| **Affected Modules** | src/backend/apps/ads/models.py, src/backend/apps/ads/migrations/0001_initial.py, src/backend/apps/ads/management/commands/setup_search_triggers.py, src/backend/apps/search/views/search.py, src/backend/apps/search/services/alert_query.py |
| **Classification** | advisory |

**Description:** The `ads` table carries four `SearchVectorField` columns. The trigger function `ads_search_vector_fn` (migration 0001_initial.py:706, setup_search_triggers.py:45) recomputes **all four** on every INSERT/UPDATE, including the generic `search_vector` — a concatenation of `to_tsvector('russian',title) + to_tsvector('russian',description) + to_tsvector('simple',title_bs) + … + category` (7 `to_tsvector` calls). A dedicated GIN index `IX_ads_search_gin` is maintained on it (models.py:256-259). However, **no production query reads the generic column**: both the web search view and `alert_query.find_matching_ads` select the per-language vector exclusively via `LanguageLocale.fts_vector_field` (`search_vector_ru` / `_bs` / `_en`) — search.py:188-189 and the FTS filter `**{vector_field: search_query}` (search.py:204); alert_query.py:53-54,223. The generic `search_vector` therefore costs ~44% (7 of 16) of the trigger's `to_tsvector` CPU on every ad write (publish/moderate/edit/sweep) plus a continuously-maintained GIN index, yet is never read. The spec's db-schema (db-schema.md:367) documents only the per-language vectors; the generic column is not a documented feature. Phase §5(b) (index maintenance) and §5(g) (write-path perf) are concerned with exactly this kind of silent write-amplification.

**Evidence:**
- src/backend/apps/ads/models.py:214-218 — `search_vector` field (generic, "TSVECTOR for native PostgreSQL FTS")
- src/backend/apps/ads/models.py:256-259 — `GinIndex(name="IX_ads_search_gin", fields=["search_vector"])`
- src/backend/apps/ads/migrations/0001_initial.py:706-714 — trigger function computes `NEW.search_vector` from all languages
- src/backend/apps/search/views/search.py:188-189,204 — `vector_field = locale.fts_vector_field`; FTS filter `**{vector_field: search_query}` (per-language only)
- src/backend/apps/search/services/alert_query.py:53-54,223 — `config = locale.fts_config` / `vector_field = locale.fts_vector_field`
- grep `search_vector` (non per-language) reads across src -> only the field definition, the index, the trigger DDL, and test names `test_insert_populates_all_search_vectors` / `test_title_update_refreshes_all_search_vectors` (which assert population, not usage)

**Recommendation:** Per the dead-code policy, investigate the column's intended purpose first: (1) if a documented "match-any-language" fallback is wanted, wire `search_vector` + `IX_ads_search_gin` to an explicit fallback query path and document it, or (2) if unused, remove the column, its GIN index, and the 7 `to_tsvector` assignments for `search_vector` from the trigger function (plus the backfill RunSQL) to cut trigger CPU and index write-amplification on the ad-write hot path. Effort: medium. Priority: recommended.

### SRH-004: No input-robustness regression tests on the /search/ FTS path (gap that let SRH-001 ship)

| Field | Value |
|-------|-------|
| **ID** | SRH-004 |
| **Severity** | LOW |
| **Type** | BEST-PRACTICE |
| **Affected Modules** | src/backend/apps/search/tests/test_search_view.py |
| **Classification** | advisory |

**Description:** `test_search_view.py` covers the happy paths the phase scope cares about — only-PUBLISHED gating (`test_search_with_query_returns_only_published`, lines 117-144), category-subtree expansion, and pagination (lines 317-418, incl. out-of-range/invalid page). It does **not** exercise §4 runtime-verification inputs that the view does not explicitly guard: (a) a `q` longer than 200 chars (the exact DataError->500 from SRH-001), (b) SQL/injection-style and homoglyph/unicode payloads (§4.3/§5(d)), or (c) a mixed-script or empty query on the FTS branch (§4.5/§7). The autocomplete endpoint is separately hardened-and-tested (`test_autocomplete.py:272` strips SQL metacharacters + caps length + rate limit), but `/search/` is not. Because the robustness contract (bounded/long-query handling, graceful empty query, no 500 on hostile input) is untested, regressions in the input boundary are invisible to CI — the very reason SRH-001 shipped. Phase §9 quality gates expect the search test suite to verify these.

**Evidence:**
- src/backend/apps/search/tests/test_search_view.py:1-12 — docstring lists only visibility/category/pagination coverage
- src/backend/apps/search/views/search.py:57 — `query = (request.GET.get("q") or "").strip()` (no cap; no validation)
- src/backend/apps/search/views/search.py:237-242 — `increment_popular_search(query)` / `record_search_history(query)` (no try/except; no precondition)
- src/backend/apps/search/tests/test_search_view.py:100-144 — only PUBLISHED-gating assertions
- src/backend/apps/search/tests/test_search_view.py:317-418 — only pagination assertions
- src/backend/apps/search/tests/test_autocomplete.py:272 — SQL-injection stripping tested for autocomplete only

**Recommendation:** Add regression tests on `/search/` for: a >200-char `q` (assert HTTP 200, not 500 — pins SRH-001's fix); SQL/injection-style + homoglyph `q` (assert 200 + no error); and empty `q` (assert graceful, no FTS branch executed). Effort: small. Priority: recommended.

---

## Summary

| Severity | Count | IDs |
|----------|-------|-----|
| CRITICAL | 0 | — |
| HIGH | 1 | SRH-001 |
| MEDIUM | 2 | SRH-002, SRH-003 |
| LOW | 1 | SRH-004 |

## Mandatory Fixes (classification: mandatory)

- **SRH-001** (HIGH): bound `q` to <=200 chars at the `/search/` input edge in `search()` before `increment_popular_search`/`record_search_history` (currently a 201-char query raises `DataError` -> HTTP 500 for anonymous buyers too). Add a >200-char regression test.

## Advisory Recommendations (classification: advisory)

- **SRH-002** (MEDIUM): update `docs/03-packages/packages-list.md:35` and `docs/03-packages/dependency-collisions.md:32,60` to drop the stale "search-side query translation" claim (search uses per-language FTS vectors; deep-translator is publication-time only).
- **SRH-003** (MEDIUM): investigate purpose of the generic `search_vector` column + `IX_ads_search_gin` (maintained on every ad write but never queried); if unused, remove the column, its GIN index, and its 7 `to_tsvector` computations from the trigger function + backfill.
- **SRH-004** (LOW): add `/search/` input-robustness regression tests (long-query/injection/homoglyph/empty) to close the gap that let SRH-001 ship.

## Doc Updates Needed (type: DOC-UPDATE)

- **SRH-002** (MEDIUM): `packages-list.md`, `dependency-collisions.md` — remove the non-existent "search-side query translation" egress; scope `deep-translator` to publication-time ad translation only.
