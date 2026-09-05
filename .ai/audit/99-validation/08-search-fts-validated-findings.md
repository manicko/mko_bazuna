---
name: 08-search-fts
phase: search-fts
template: .ai/audit/templates/audit-findings.md
status: complete
validated: yes
validator: validator
validated_date: 2026-09-05
---

# Phase 08 Audit Findings — Search & Full-Text Search (FTS) (Validated)

**Executor:** audit-executor
**Validator:** validator
**Template:** .ai/audit/templates/audit-findings.md
**Status:** complete
**Validated:** yes

**Scope:** apps.search.views.search (FTS/ranking/pagination), apps.search.services.{alert_query,popular_search,search_history}, apps.core.services.translation, apps.ads.models (Ad.search_vector* + GIN/partial indexes + trigger `ads_search_vector_fn`), apps.ads.views.listings (visibility predicate), apps.core.utils.sanitize

This file is the self-contained validated report. The reader does not need to consult the original findings file (`.ai/audit/08-search-fts/findings.md`).

---

## Runtime Verification Evidence

| Check | Result | Notes |
|-------|--------|-------|
| Scope — import / module discovery | PASS | All referenced modules resolve to real paths under `src/backend/apps/{search,ads,core}/`. |
| R3 — Linter (ruff) | NOT RUN | Per-phase scope was static analysis only (audit `Status: complete, Validated: no (static analysis only; Docker runtime not executed this phase)`). No runtime/lint executed by this validator. |
| R4 — Test suite | NOT RUN | Docker runtime not executed (per phase status). Test files inspected statically only. |
| R5 — Migration guard | NOT RUN | `setup_search_triggers` / migration DDL inspected statically; no runtime execution. |
| S1 — FTS config resolution | PASS (static) | `LanguageLocale.fts_config` returns `russian`/`simple`/`english`; `fts_vector_field` returns `search_vector_ru`/`_bs`/`_en` only (no generic column). |
| S2 — GIN indexes | PASS (static) | `GinIndex(name="IX_ads_search_gin", fields=["search_vector"])` + three per-language GINs exist in `ads/models.py:256-271`. |
| S3 — Trigger | PASS (static) | `ads_search_vector_fn` (migration `0001_initial.py:706`; `setup_search_triggers.py:34-67`) populates all four vectors on BEFORE INSERT OR UPDATE. |
| S4 — Ranking logic | PASS (static) | `SearchRank(F(vector_field), search_query)` used in both `search.py:203` and `alert_query.py:63`. |
| S5 — `to_tsquery` construction | N/A (static) | No raw `to_tsquery` in `src/` (grep: 0 matches). Query construction uses `django.contrib.postgres.search.SearchQuery(search_type="websearch", config=config)` — compiled by Django to `websearch_to_tsquery`. Per-language only. |
| S6 — Empty/overflow input | FAIL (static) | `/search/` applies no length bound (see SRH-001); `>200`-char `q` overflows `varchar(200)` → `DataError` → HTTP 500. |

> **Note on scope fidelity:** The audit phase header states "static analysis only; Docker runtime not executed this phase." Accordingly, all verification below is source-level (grep + targeted reads). No runtime, lint, typecheck, or test execution was performed for this phase.

---

## Cross-Finding Analysis

### Dependency Chains

| Finding | Depends on | Depends on by | Notes |
|---------|-----------|---------------|-------|
| SRH-001 | — | SRH-004 (directly) | SRH-001's fix (bound `q`) is the behavior that SRH-004's >200-char regression test pins. SRH-004 is the test-gap that let SRH-001 ship; the regression test is the verification half of SRH-001's recommendation. Complementary, not a hard ordering dependency. |
| SRH-002 | — | — | Documentation-only; independent. |
| SRH-003 | — | — | Schema/trigger concern; independent of the input-bound and doc findings. |
| SRH-004 | — | — | Test-suite gap; dependent on SRH-001's fix for the >200-char case. |

### Conflicts Detected

No cross-phase conflicts. Single phase analyzed. No other validated phase asserts the opposite on these four concerns.

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
| **Validation Status** | **VALIDATED** |

**Description:** The `/search/` view reads `q` with only `.strip()` (search.py:57) and enforces no length bound. The raw, uncapped query is then handed unconditionally to `increment_popular_search(query)` (search.py:237) and `record_search_history(...)` (search.py:238-242), neither wrapped in try/except. Those services persist the query into `PopularSearch.query` / `SearchHistory.query`, both `CharField(max_length=200)` (models.py:16, 49). Any search whose `q` exceeds 200 characters makes `get_or_create(... defaults={"query": query})` (popular_search.py:37-45) issue an `INSERT` of a >200-char value into a `varchar(200)` column -> PostgreSQL `value too long for type character varying(200)` -> `DataError` -> unhandled -> HTTP 500. The crash fires for anonymous buyers too (PopularSearch is hit on every non-empty query), so a single 201-character `?q=` takes the public search endpoint down. This violates phase §4.5 / §7 ("Very long / many-token query -> bounded or rejected") — it is neither bounded nor rejected. (Contrast `/search/autocomplete`, which is hardened by `sanitize_autocomplete_query`: 100-char cap + SQL-char strip + rate limit.)

**Evidence:**
- src/backend/apps/search/views/search.py:57 — `query = (request.GET.get("q") or "").strip()` (no max_length)
- src/backend/apps/search/views/search.py:237 — `increment_popular_search(query)` (raw, uncapped)
- src/backend/apps/search/views/search.py:238-242 — `record_search_history(... query, ...)` (raw, uncapped)
- src/backend/apps/search/models.py:16 — `query = models.CharField(max_length=200, db_index=True)` (PopularSearch)
- src/backend/apps/search/models.py:49 — `query = models.CharField(max_length=200)` (SearchHistory)
- src/backend/apps/search/services/popular_search.py:37-45 — `get_or_create(query_normalized=..., defaults={"query": query, ...})` and `.update(... query=query, ...)` (no truncation)

**Validator's Verification:**
- Read `search.py` (full file, 419 lines): line 57 is exactly `query = (request.GET.get("q") or "").strip()` — no slicing, no `[:N]`, no validator. Confirmed by grep: there is no `truncate`, `[:200]`, or `max_length` call between line 57 and the service calls.
- Confirmed `increment_popular_search(query)` at line 237 sits inside the `if query:` block (line 183) with **no surrounding try/except**; `record_search_history(user_id, query, session=...)` spans lines 238-242, also try/except-free. A `DataError` raised there propagates unhandled → HTTP 500.
- Read `popular_search.py:37-49`: `get_or_create(query_normalized=normalized, defaults={"query": query, ...})` inserts the raw `query` into `varchar(200)`; the `else` branch `.update(query=query)` repeats the same overflow on update. No truncation anywhere (`grep` for `[:200]`/`truncate` in the services dir: 0 matches).
- Read `search_history.py:62-70`: for authenticated users `SearchHistory.objects.create(user_id=user_id, query=query, ...)` inserts raw `query` into `varchar(200)`. Anonymous users are session-scoped (no DB write) — so for anonymous buyers the `PopularSearch` INSERT path (line 237) is the public DoS vector, exactly as described.
- Read `search/models.py:13-50`: confirmed `PopularSearch.query` (line 16) and `SearchHistory.query` (line 49) are both `CharField(max_length=200)`.
- Confirmed the autocomplete contrast: `autocomplete.py:53` calls `sanitize_autocomplete_query(...)`; `core/utils/sanitize.py:39-43` caps to 100 chars (`if not query or len(query) < 2 or len(query) > 100: return ""`) and strips `;'"\` ; `services/rate_limit.py` enforces 30 req/60s (`test_autocomplete.py:269-272` asserts SQL-char stripping). So `/search/` (no cap) vs `/search/autocomplete` (capped) asymmetry is real.
- Note on FTS mechanism: the query is built with `SearchQuery(query, search_type="websearch", config=config)` (search.py:202). Django compiles this to `websearch_to_tsquery`, which accepts a long string fine — so the failure is **not** in FTS parsing but in the downstream `varchar(200)` storage. The finding's root-cause attribution (storage overflow) is correct.

**Evidence Quality:** High — all line references verified exact; the asymmetry with autocomplete confirmed empirically.

**Recommendation:** Bound `q` at the input edge in `search()` before any service call — e.g. `query = query[:200]` (or a named constant) so stored fields never overflow, and/or validate and reject >200 chars with a user-facing message. The cap must precede `increment_popular_search`/`record_search_history`. Add a regression test feeding a >200-char `q` and asserting HTTP 200 (not 500). Effort: trivial. Priority: high.

---

### SRH-002: Docs describe a search-time Montenegrin→Russian translation bridge that the code removed

| Field | Value |
|-------|-------|
| **ID** | SRH-002 |
| **Severity** | MEDIUM |
| **Type** | DOC-UPDATE |
| **Affected Modules** | docs/03-packages/packages-list.md, docs/03-packages/dependency-collisions.md, src/backend/apps/core/services/translation.py, src/backend/apps/search/views/search.py |
| **Classification** | advisory |
| **Validation Status** | **VALIDATED** |

**Description:** The implemented search path no longer performs query-time translation. `apps.core.services.translation` is now used only at ad-publication time (translation.py:8-11: "Search/alert query translation was removed — the search path now uses language-aware per-language FTS vectors with no external translation"), and `search()` resolves the buyer's locale to a per-language vector column (search.py:184-189) with no external translator on the search critical path (config = `russian` / `simple` / `english` via `LanguageLocale.fts_config`, search.py:189). The authoritative spec already reflects this — technical-specification.md:119 and search-patterns.md:22 state "no query-time translation; buyers search per-language FTS vectors." However two package/docs files still describe the old bridge: `packages-list.md:35` ("deep-translator … Montenegrin → Russian at search time") and `dependency-collisions.md:32,60` ("Montenegrin→Russian query translation" … "governing both search-side query translation and bot-side ad-creation translation"). The code choice is better (removes an external, PII-egress-prone dependency from the unauthenticated search path), so per audit guidance the fix is to update the docs rather than revert the code.

**Evidence:**
- src/backend/apps/core/services/translation.py:8-11 — "Used at publication time by the bot's ad-creation translator... Search/alert query translation was removed … no external translation"
- src/backend/apps/search/views/search.py:184-189 — locale-resolved per-language vector; "no external translator runs on the search critical path"
- docs/01-spec/technical-specification.md:119 — "No search queries are sent to any translation service"
- docs/01-spec/search-patterns.md:22 — "no query-time translation"
- docs/03-packages/packages-list.md:35 — "Query translation: deep-translator (Montenegrin → Russian at search time; hard timeout ~500ms + fallback to original query)."
- docs/03-packages/dependency-collisions.md:32 — deep-translator row cross-ref: "spec-index.md line 32 (Montenegrin→Russian query translation)"
- docs/03-packages/dependency-collisions.md:60 — "governing both search-side query translation and bot-side ad-creation translation"

**Validator's Verification:**
- Read `translation.py` (full, 184 lines): module docstring lines 8-11 read verbatim as cited ("Search/alert query translation was removed — the search path now uses language-aware per-language FTS vectors with no external translation"). `deep_translator` / `GoogleTranslator` is imported (line 20) and used **only** by `translate_cached`/`translate_text` — none of which are imported by the search app.
- `grep` for `core.services.translation|translate_text|translate_cached` across `src/backend/apps/search` → **0 matches**. The search view imports `sanitize_query_for_log` from `apps.core.utils.sanitize` (search.py:25), **not** the translation service. Confirmed: no external translator on the `/search/` or alert (async) critical path.
- Read `enums.py:188-238`: `LanguageLocale.fts_config` = `russian`/`simple`/`english`, `fts_vector_field` = `search_vector_ru`/`_bs`/`_en` — locale-resolved per-language vector, no translation. Confirmed at search.py:187-189 and alert_query.py:53-54.
- Spec cross-check: `technical-specification.md:119` and `search-patterns.md:22` both state "no query-time translation" (verified exact). `spec-index.md:47` says "deep-translator (Bosnian→Russian at ad publication only; search is per-language FTS, no query-time translation)" — already correct.
- Stale-doc check: `packages-list.md:35` still says "Montenegrin → Russian at search time" — **stale**. However `packages-list.md:50` in the *same file* already states "deep-translator … NOT used for search queries (search is per-language FTS, no query-time translation)" — so the file is **internally inconsistent** (line 35 stale, line 50 current). Fix = align line 35 with line 50.
- `dependency-collisions.md:60` — "governing both search-side query translation and bot-side ad-creation translation" — **stale** (search-side translation does not exist).
- `dependency-collisions.md:32` — the deep-translator risk row itself does **not** claim search-side translation; its stale element is the cross-reference cell "spec-index.md line 32 (Montenegrin→Russian query translation)". That cross-ref is itself stale: `spec-index.md:32` is now generic prose ("Concise technical summary…"), and the *correct* statement lives at `spec-index.md:47`. So the cross-reference points at an outdated line number (minor).

**Evidence Quality:** High for the code-reality claim (no search-time translation, fully verified). Medium for doc citations: the finding bundles `dependency-collisions.md:32` as a stale "search-side" claim, but line 32's row does not itself make that claim — it is the line-60 row and the stale spec-index:32 cross-ref that carry it. The core DOC-UPDATE verdict (packages-list.md:35 and dependency-collisions.md:60 are stale relative to code+spec) stands.

> **Validation Note:**
> - **Action:** none (reclassified n/a — type already DOC-UPDATE, which is correct: code is right, docs are stale).
> - **Detail:** The authoritative spec (`technical-specification.md:119`, `search-patterns.md:22`, `spec-index.md:47`, `i18n-spec.md:162`) already documents the current behavior, so docs — not code — must change. Additional stale/incorrect doc targets beyond the finding's list: `packages-list.md:35` should be aligned with its own `packages-list.md:50` (internal inconsistency), and `dependency-collisions.md:60` should drop the "search-side" clause. The `dependency-collisions.md:32` cross-ref to "spec-index.md line 32" is stale (current statement is at `spec-index.md:47`).
> - **See also:** SRH-002 recommendation (doc-only fix); no production code change.

**Recommendation:** Update `packages-list.md:35` and `dependency-collisions.md:32,60` to scope deep-translator to publication-time ad translation only (matching technical-specification.md / search-patterns.md). Optionally reconcile the audit phase scope §2/§5(c). Effort: trivial. Priority: recommended.

---

### SRH-003: Generic `search_vector` column + GIN index maintained on every ad write but never queried

| Field | Value |
|-------|-------|
| **ID** | SRH-003 |
| **Severity** | MEDIUM |
| **Type** | BEST-PRACTICE |
| **Affected Modules** | src/backend/apps/ads/models.py, src/backend/apps/ads/migrations/0001_initial.py, src/backend/apps/ads/management/commands/setup_search_triggers.py, src/backend/apps/search/views/search.py, src/backend/apps/search/services/alert_query.py |
| **Classification** | advisory |
| **Validation Status** | **VALIDATED (core concern) — evidence corrected** |

**Description:** The `ads` table carries four `SearchVectorField` columns. The trigger function `ads_search_vector_fn` (migration 0001_initial.py:706, setup_search_triggers.py:45) recomputes **all four** on every INSERT/UPDATE, including the generic `search_vector` — a concatenation of `to_tsvector('russian',title) + to_tsvector('russian',description) + to_tsvector('simple',title_bs) + … + category` (7 `to_tsvector` calls). A dedicated GIN index `IX_ads_search_gin` is maintained on it (models.py:256-259). However, **no production query reads the generic column**: both the web search view and `alert_query.find_matching_ads` select the per-language vector exclusively via `LanguageLocale.fts_vector_field` (`search_vector_ru` / `_bs` / `_en`) — search.py:188-189 and the FTS filter `**{vector_field: search_query}` (search.py:204); alert_query.py:53-54,223. The generic `search_vector` therefore costs ~44% (7 of 16) of the trigger's `to_tsvector` CPU on every ad write (publish/moderate/edit/sweep) plus a continuously-maintained GIN index, yet is never read.

**Evidence:**
- src/backend/apps/ads/models.py:214-218 — `search_vector` field (generic)
- src/backend/apps/ads/models.py:256-259 — `GinIndex(name="IX_ads_search_gin", fields=["search_vector"])`
- src/backend/apps/ads/migrations/0001_initial.py:706-714 — trigger function computes `NEW.search_vector`
- src/backend/apps/search/views/search.py:188-189,204 — `vector_field = locale.fts_vector_field`; FTS filter `**{vector_field: search_query}` (per-language only)
- src/backend/apps/search/services/alert_query.py:53-54,223 — `config = locale.fts_config` / `vector_field = locale.fts_vector_field`

**Validator's Verification:**
- Read `ads/models.py:213-271`: confirmed `search_vector` (line 214, generic) plus `search_vector_ru/bs/_en` (219/224/229). Confirmed `GinIndex(name="IX_ads_search_gin", fields=["search_vector"])` (256-259) and three per-language GINs (260-270). The comment on line 213 reads "# Search vectors (NOT GENERATED ALWAYS - maintained by trigger)".
- Read migration `0001_initial.py:706-714` and `setup_search_triggers.py:34-67` (single SQL template mirrored in both): the trigger sets `NEW.search_vector :=` from 7 `to_tsvector` calls (russian title/desc, simple title_bs/desc_bs, english title_en/desc_en, simple category name) and `search_vector_ru`/`_bs`/`_en` from 3 calls each → **7 of 16** total. Ratio verified exactly.
- Grep for `search_vector` across `src/` (excluding the per-language `_ru/_bs/_en` suffixed names): the **only** production references to the bare `search_vector` column are (a) the field definition (models.py:214), (b) its GIN index (models.py:258, migration 536, db-indexes.md), (c) the trigger DDL writing `NEW.search_vector` (migration 706, setup_search_triggers.py:45), and (d) test docstrings. There is **no** `.filter(search_vector=…)`, **no** `SearchRank(F("search_vector"))`, and **no** `annotate(...=F("search_vector"))` read in any production view or service. The generic column is write-only.
- Read `search.py:187-204`: `vector_field = locale.fts_vector_field` resolves to `search_vector_ru/bs/_en` only (enums.py:232-238 — note the dict has **no** `search_vector` key), `config = locale.fts_config`, and the FTS filter is `**{vector_field: search_query}`. Generic column never referenced on the read path.
- Read `alert_query.py:53-66` and `:220-227`: identical per-language pattern (`vector_field = locale.fts_vector_field`, `config = locale.fts_config`, `SearchRank(F(vector_field), …)`, `**{vector_field: search_query}` / `**{locale.fts_vector_field: search_query}`). Generic column never referenced.
- Grep for raw `to_tsquery` in `src/` → **0 matches**. FTS is constructed via `django.contrib.postgres.search.SearchQuery(search_type="websearch", config=config)` (search.py:202; alert_query.py:56, 220), which Django compiles to `websearch_to_tsquery` against the per-language config. The trigger's SQL uses `to_tsvector('config', col)` for *index populating*, not `to_tsquery` for querying.

**Evidence Quality Issues (material):** The finding's evidence includes the claim: "The spec's db-schema (db-schema.md:367) documents only the per-language vectors; the generic column is not a documented feature." This is **contradicted** by the documentation:
- `docs/02-database/db-schema.md:151` — "search_vector (TSVECTOR) … NOT GENERATED ALWAYS — **legacy concatenated vector (maintained by trigger)**"
- `docs/02-database/db-schema.md:364` — "**Legacy `search_vector` retained during dual-write transition (to be dropped in Phase 3).**"
- `docs/02-database/db-indexes.md:47-48` — `IX_ads_search_gin` on `search_vector` … "# legacy concatenated vector (to be dropped)"
- `docs/02-database/db-indexes.md:95-98` — "The trigger dual-writes the legacy vector and the three per-language vectors…"
- `docs/01-spec/i18n-spec.md:162` — "...(plus a legacy `search_vector` during the dual-write transition, not yet dropped; see db-schema.md > Search)…"

So the generic column **is** a documented, intentional transitional artifact (dual-write → drop in Phase 3), referenced across the DB/schema/index/i18n/ migration-research docs — it is **not** dead code and the "not a documented feature" rationale is inaccurate. The finding did not cite line `:367` correctly (`:367` is the "Search fill per language" prose; the legacy note is at `:364`), but that is a minor citation offset; the substantive contradiction stands.

> **Validation Note:**
> - **Action:** reclassified framing (type unchanged: BEST-PRACTICE).
> - **Detail:** The **core observation is verified true** — the generic `search_vector` + its `IX_ads_search_gin` index are maintained on every ad INSERT/UPDATE (7 of 16 trigger `to_tsvector` calls) and are **never read** by any production query (web search or alerts both use `LanguageLocale.fts_vector_field` → per-language columns only). This is a genuine, quantified write-amplification smell. However, the finding's "not a documented feature / dead code" rationale is **incorrect**: `db-schema.md:151` & `:364`, `db-indexes.md:47-48`, and `i18n-spec.md:162` explicitly document the generic column as a **legacy dual-write transitional column "to be dropped in Phase 3"**. Per the dead-code mandatory spec cross-reference, the column is referenced by spec/DB/migration-research docs → **not dead**, just transitional. Consequently the recommended *out-of-band* removal now conflicts with the documented Phase-3 migration trajectory (`docs/07-design-researches/migration_patterns.md` dual-write design) and should not be executed independently of that plan.
> - **See also:** SRH-003 recommendation stands as "investigate first" — the investigation outcome (documented legacy-transitional column, Phase 3 drop planned) means the write-amp cost should be **tracked against the Phase 3 drop** rather than removed ad hoc. If Phase 3 is deferred indefinitely, revisiting removal becomes justified — but that decision belongs in the migration plan, not this audit.
> - **Evidence quality for the *core* technical claim:** High. **Evidence quality for the "not documented" supporting rationale:** Low (contradicted by 5 doc files).

**Recommendation:** Execute **Approach B — remove** the generic `search_vector` column, its `IX_ads_search_gin` GIN index, and the 7 `to_tsvector` assignments that build `NEW.search_vector` from the trigger function. Investigation definitively rules out Approach A (wire a fallback query path): no match-any-language fallback design exists anywhere — a repo-wide search returns zero hits, `LanguageLocale.fts_vector_field` (`apps/core/enums.py:232-238`) has no generic-column entry (only `search_vector_ru/bs/_en`), and both production read paths use the per-language vector exclusively — `search.py:188-204` (`vector_field = locale.fts_vector_field`; `SearchRank(F(vector_field), search_query)`; `**{vector_field: search_query}`) and `alert_query.py:53-68,220-227` (identical pattern). The generic column is confirmed write-only (7 of 16 = 44% of every ad-write trigger `to_tsvector` CPU; zero reads), and is explicitly documented across five files as a transitional dual-write artifact slated for removal: `db-schema.md:151` (legacy concatenated vector), `db-schema.md:364` (to be dropped in Phase 3), `db-indexes.md:47-48` (legacy concatenated vector — to be dropped), `db-indexes.md:95-98` (trigger dual-writes the legacy vector), `i18n-spec.md:161-162` (legacy `search_vector` during the dual-write transition, not yet dropped). Removing out-of-band now is rejected: Phase 3 (Seller Experience & Analytics; `phase-plan-highlevel.md:215`) is a future, not-yet-started phase, and the Phase 3 milestones M3.1-M3.3 (Seller Dashboard, Account Management, Analytics) do not yet schedule this schema cleanup as a concrete ticket — it is documented-but-untracked. Track the 44% trigger-CPU + unused GIN-index write-amplification cost as a Phase-3 milestone item with the following implementation footprint for atomic execution later. The drop touches three source-of-truth surfaces that must be reconciled in lockstep (see also the fragile-insertion-point note at `08-search-fts-validated-findings.md:296`):

1. **New migration** — `DROP INDEX IF EXISTS IX_ads_search_gin` then `ALTER TABLE ads DROP COLUMN IF EXISTS search_vector` then `CREATE OR REPLACE FUNCTION ads_search_vector_fn()` with the `NEW.search_vector :=` block (7 `to_tsvector` calls, lines 45-52 of `setup_search_triggers.py`) removed. No separate backfill RunSQL is required: the `migration_patterns.md:165` backfill note concerns per-language-vector population for seed rows, not the generic column being dropped.
2. **`setup_search_triggers.py:45-52`** — remove the `NEW.search_vector :=` block from the `SEARCH_VECTOR_FN_SQL` idempotent template; must stay in lockstep with the function-body copy embedded in the squashed `0001_initial.py:706` RunSQL (the two are the live copies of this function body).
3. **`ads/models.py`** — remove the field at line 214 (`search_vector = SearchVectorField(...)`) and the index at lines 256-259 (`GinIndex(name="IX_ads_search_gin", fields=["search_vector"])`).
4. **`test_search_triggers.py`** — `TestSearchVectorTrigger.test_insert_populates_all_search_vectors` (line 57) and `test_title_update_refreshes_all_search_vectors` (line 98) assert only the three per-language vectors (lines 60-62), never the generic one — assertions are functionally safe; only docstrings and method names containing "all_search_vectors" should be renamed to avoid post-removal confusion.

**Effort: medium. Priority: recommended. Gated on Phase 3 — do not execute standalone / out-of-band.**

---

### SRH-004: No input-robustness regression tests on the /search/ FTS path (gap that let SRH-001 ship)

| Field | Value |
|-------|-------|
| **ID** | SRH-004 |
| **Severity** | LOW |
| **Type** | BEST-PRACTICE |
| **Affected Modules** | src/backend/apps/search/tests/test_search_view.py |
| **Classification** | advisory |
| **Validation Status** | **VALIDATED** |

**Description:** `test_search_view.py` covers the happy paths the phase scope cares about — only-PUBLISHED gating (`test_search_with_query_returns_only_published`), category-subtree expansion, and pagination. It does **not** exercise §4 runtime-verification inputs that the view does not explicitly guard: (a) a `q` longer than 200 chars (the exact DataError->500 from SRH-001), (b) SQL/injection-style and homoglyph/unicode payloads (§4.3/§5(d)), or (c) a mixed-script or empty query on the FTS branch (§4.5/§7). The autocomplete endpoint is separately hardened-and-tested (`test_autocomplete.py:272` strips SQL metacharacters + caps length + rate limit), but `/search/` is not. Because the robustness contract (bounded/long-query handling, graceful empty query, no 500 on hostile input) is untested, regressions in the input boundary are invisible to CI — the very reason SRH-001 shipped.

**Evidence:**
- src/backend/apps/search/tests/test_search_view.py:1-12 — docstring lists only visibility/category/pagination coverage
- src/backend/apps/search/views/search.py:57 — `query = (request.GET.get("q") or "").strip()` (no cap; no validation)
- src/backend/apps/search/views/search.py:237-242 — `increment_popular_search(query)` / `record_search_history(query)` (no try/except; no precondition)
- src/backend/apps/search/tests/test_search_view.py:117-144 — only PUBLISHED-gating assertions
- src/backend/apps/search/tests/test_search_view.py:317-418 — only pagination assertions
- src/backend/apps/search/tests/test_autocomplete.py:272 — SQL-injection stripping tested for autocomplete only

**Validator's Verification:**
- Read `test_search_view.py` (full, 418 lines). Docstring (lines 1-13) explicitly scopes coverage to: (i) only-PUBLISHED gating, (ii) descendant-category expansion, (iii) pagination — confirmed verbatim.
- Test inventory (static): `TestSearchViewPublishesFilter` (3 tests, l.75-184), `TestSearchViewDescendantCategories` (2 tests, l.187-281), `TestSearchViewCitySuggestion` (1 test, l.284-314), `TestSearchViewPagination` (4 tests, l.317-418).
- Grep for `200|long|inject|truncat|homoglyph|unicode|DataError` in `test_search_view.py` → only `assert response.status_code == 200` occurrences and the name `test_empty_search_returns_all_published`. **No** >200-char query test, **no** SQL-injection/homoglyph test, **no** mixed-script-on-FTS test.
- Confirmed `test_empty_search_returns_all_published` (line 156) tests the *no-`q`* path → hits the `else` (non-FTS) branch (`if query:` is false at line 183), so it does **not** cover "empty query on the FTS branch" (which is structurally impossible — an empty query never enters the FTS branch). The finding's gap (c) is therefore really "mixed-script / no-FTS-fuzzing-coverage"; empty-input graceful handling is incidentally covered via the else branch.
- Contrast confirmed: `test_autocomplete.py:269-272` `test_autocomplete_malicious_query_sanitized` strips SQL metacharacters; `autocomplete.py:53` applies `sanitize_autocomplete_query` (100-char cap + `re.sub(r"[;'\"\\]", "", …)` — sanitize.py:43) and `rate_limit_check` (30/60s). Autocomplete's robustness contract is tested; `/search/`'s is not.

**Evidence Quality Issues (minor):** Two citation offsets vs. current source: (1) the finding cites `test_search_view.py:117-144` for "only PUBLISHED-gating assertions" — the method `test_search_with_query_returns_only_published` actually spans lines 117-154 (the `:144` cut is slightly early); (2) `test_search_view.py:1-12` for the docstring — the docstring actually spans lines 1-13. Neither affects the finding's substance (the coverage gap is real and verified). The line references for `search.py:57`, `search.py:237-242`, and `test_autocomplete.py:272` are exact.

> **Validation Note:**
> - **Action:** none (reclassified n/a — type already BEST-PRACTICE).
> - **Detail:** The test gap is verified real. The only partial nuance: empty-input graceful handling is incidentally covered by `test_empty_search_returns_all_published` (else/no-FTS branch), so gap (c) reduces to "mixed-script queries and explicit long/injection payloads on the FTS branch are untested" — still a real coverage gap, and the >200-char case directly enables a HIGH-severity production 500 (SRH-001).
> - **See also:** SRH-001 (same input boundary); the SRH-004 >200-char regression test is the verification half of SRH-001's recommendation.

**Recommendation:** Add regression tests on `/search/` for: a >200-char `q` (assert HTTP 200, not 500 — pins SRH-001's fix); SQL/injection-style + homoglyph `q` (assert 200 + no error); and empty `q` (assert graceful, no FTS branch executed). Effort: small. Priority: recommended.

---

## Validation Summary

| Action | Count | Details |
|--------|-------|---------|
| Validated (unchanged) | 3 | SRH-001, SRH-002, SRH-004 |
| Reclassified | 0 | — |
| Merged | 0 | — |
| Rejected | 0 | — |
| Validated + evidence corrected | 1 | SRH-003 |
| Cross-referenced for dead-code accuracy | 1 | SRH-003 (generic `search_vector` is NOT dead — documented legacy-transitional column, Phase 3 drop planned) |

### Findings by Severity

| Severity | Count | IDs |
|----------|-------|-----|
| CRITICAL | 0 | — |
| HIGH | 1 | SRH-001 |
| MEDIUM | 2 | SRH-002, SRH-003 |
| LOW | 1 | SRH-004 |
| **Total** | **4** | |

### Evidence Quality Assessment

| ID | Evidence Quality | Notes |
|----|------------------|-------|
| SRH-001 | **High** | All cited line references (search.py:57, :237, :238-242; models.py:16, :49; popular_search.py:37-45) verified exact; FTS mechanism (SearchQuery websearch, not to_tsquery) confirmed; autocomplete asymmetry empirically confirmed. |
| SRH-002 | **High** (core) / **Medium** (doc citations) | Code reality (no search-time translation) fully verified. Doc claims at `packages-list.md:35` (stale) and `dependency-collisions.md:60` (stale) verified. Nuance: `packages-list.md:50` already states the correct position (internal inconsistency); `dependency-collisions.md:32` does not itself claim search-side translation — its stale element is the spec-index.md:32 cross-ref (now at spec-index.md:47). |
| SRH-003 | **High** (core) / **Low** (supporting rationale) | Write-amplification claim (7/16 trigger to_tsvector calls, write-only column, no read) verified exactly. But the "db-schema documents only per-language vectors / column is not a documented feature" rationale is **contradicted** by db-schema.md:151, :364; db-indexes.md:47-48; i18n-spec.md:162 (column documented as legacy dual-write transitional, to be dropped in Phase 3). Not dead code. |
| SRH-004 | **High** (core) / **Medium** (citations) | Test gap verified exactly (grep for long/inject/truncate/homoglyph returns only status_code asserts + the no-FTS empty test). Minor citation offsets (docstring 1-13 not 1-12; published-gating test 117-154 not 117-144). |

### Rejected Findings

None.

### Merged Findings

None.

### Reclassified Findings

None (SRH-003 retains type BEST-PRACTICE; its *supporting rationale* was corrected, not its type — see Validation Note under SRH-003).

---

## Cross-Finding Analysis — Rollout Safety

### Circular Dependencies

No circular dependencies. The four findings are independent in their fix domains:
- SRH-001 = input-bounding in `search()` + popular_search/search_history services.
- SRH-002 = doc text only (no code).
- SRH-003 = ads schema/trigger (gated on Phase 3 plan; not executed out-of-band per validator addendum).
- SRH-004 = test additions.

### Hidden Dependency Chains

- **SRH-004 → SRH-001 (verification pairing):** SRH-001's recommendation mandates a >200-char regression test; SRH-004 is precisely the coverage gap that let SRH-001 ship. They are complementary — applying SRH-001 without SRH-004's tests leaves the boundary unguarded against regression. The fix should be delivered as a **single atomic change**: cap `q` in `search()` AND add the >200-char assertion test.
- **SRH-003 → migration plan (Phase 3):** Any removal of the generic `search_vector` column/index/trigger-assignments must be coordinated with `docs/07-design-researches/migration_patterns.md` (dual-write design) and the Phase 3 milestone. Removing it now without that plan risks diverging the schema from the documented migration trajectory. Not a hidden cycle — a documented sequencing dependency.

### Unsafe Rollout Ordering

- **SRH-001 cap must precede/with SRH-004's regression test.** Bounding `q` at line 57 (before the `if query:` block and the service calls at 237-242) is a backward-compatible truncation: legitimate ≤200-char queries are unaffected; hostile >200-char queries stop raising `DataError`. No schema change → no migration ordering risk.
- **SRH-002** is doc-only → zero rollout risk; no ordering constraint.
- **SRH-003** removal (if/when Phase 3 authorizes) is the only schema-affecting change: requires a migration dropping the column + GIN index + trigger-function edit + backfill SQL removal, sequenced with the dual-write migration plan. Per the validator addendum, **do not execute SRH-003's removal out-of-band**; track as a Phase-3 item.

### Fragile Insertion Points

- SRH-001's insertion point (line 57, `query = ...strip()`) is stable and unambiguous; capping here is the correct, single-input-edge location (precedes all service calls).
- SRH-004's test additions append to `test_search_view.py` — stable module; no fragile anchors.
- SRH-003's trigger-function edit, if ever pursued, touches migration `0001_initial.py:706` SQL (raw DDL) and `setup_search_triggers.py:45-52` (the shared `SEARCH_VECTOR_FN_SQL` template) — these must be edited in lockstep (migration + setup command) to avoid drift. This is a fragility argument for *not* touching them ad hoc, reinforcing the Phase-3 gating.

---

## Rollout Recommendations (Priority Order)

1. **SRH-001 (HIGH) — Bound `q` at the `/search/` input edge.** Truncate `query = query[:200]` (use a named constant aligned to `PopularSearch`/`SearchHistory` `max_length=200`) at `search.py:57`, before `increment_popular_search`/`record_search_history`. Atomic with SRH-004's >200-char regression test (item 2). Backward compatible; no migration; removes a public anonymous DoS → 500. Effort: trivial.
2. **SRH-004 (LOW) — Add `/search/` input-robustness regression tests.** Pin SRH-001's fix with a >200-char `q` assertion (expect HTTP 200, not 500); add SQL-injection/homoglyph `q` assertions (expect 200, no error); assert empty `q` is graceful. Delivered together with item 1. Effort: small.
3. **SRH-002 (MEDIUM) — Fix stale docs.** Align `packages-list.md:35` with its own `packages-list.md:50` ("NOT used for search queries … per-language FTS, no query-time translation"); strip the "search-side query translation" clause from `dependency-collisions.md:60`; correct the stale `spec-index.md:32` cross-reference to point at `spec-index.md:47`. Doc-only. Effort: trivial.
4. **SRH-003 (MEDIUM) — Track write-amp against Phase 3 (do NOT remove out-of-band).** The generic `search_vector` + `IX_ads_search_gin` are confirmed write-only (7/16 of trigger `to_tsvector` CPU on every ad write), but the column is a **documented legacy-dual-write transitional artifact slated for Phase 3 removal** (db-schema.md:364; db-indexes.md:48; i18n-spec.md:162). Record the 44% trigger-CPU / GIN-index write-amplification cost as a Phase-3 milestone item; removal must be sequenced with `migration_patterns.md` dual-write plan and must update both `0001_initial.py:706` DDL and `setup_search_triggers.py:45-52` in lockstep. Effort: medium, **but gated on Phase 3** — no standalone execution.
