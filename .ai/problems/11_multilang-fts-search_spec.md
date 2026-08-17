---
id: multilang-fts-search
domain: spec
source: .ai/problems/Decision_12.md
tags:
  - search
  - fts
  - multilingual
  - postgres
  - phase-2
related:
  - technical-specification
  - decision-11-analysis
  - search-patterns
  - db-schema
  - db-indexes
  - architecture-structure
created: 2026-08-17
status: ready
---

# Specification: Multi-Language FTS Search Architecture

## 1. Problem Statement

The Mko Bazuna classifieds board stores ad content in three languages (Russian base,
Bosnian, English) and supports a three-language UI (Russian, Bosnian, English).
The **search** flow currently translates the buyer's query to Russian via Google
Translate (`deep-translator`) on **every** search request, then runs a single
PostgreSQL `search_vector` using `config="russian"`.

**Two problems:**

1. **External service on the critical path.** Google Translate is called on every
   search. Even with LRU cache, 500 ms timeout, and a circuit breaker, an external
   HTTP dependency sits on the most latency-sensitive user path (search). This
   adds latency, failure modes, and ongoing cost.

2. **Incorrect cross-language matching.** The database trigger
   (`ads_search_vector_fn`, migration `0006`) already builds a **single
   concatenated** `search_vector` containing lexemes from all three language configs
   (`russian` + `simple` for Bosnian + `english`). The search view still queries
   only the Russian portion (`config="russian"`), so the Bosnian/English lexemes
   in the vector are dead data. Worse, because PostgreSQL's `@@` operator is
   config-agnostic (it tests set membership against ALL lexemes in the vector
   regardless of the query's config), a future change to query in Bosnian or
   English against the combined vector would produce **cross-language false
   matches** (shared vocabulary, loanwords, numbers) and **false negatives**
   (stemming mismatches between configs).

**Decision_12** (captured in `.ai/problems/Decision_12.md`) recommends replacing
the single concatenated vector with **separate per-language TSVECTOR columns**
(`search_vector_ru`, `search_vector_bs`, `search_vector_en`), each with its own
GIN index, and selecting the appropriate vector + config based on
`request.LANGUAGE_CODE` — **without** translating the query.

> Core principle: ads are translated once at publication time; search must not
> call an external translator.

## 2. Confirmed Requirements

### R1. Per-language search vectors
- Three new `TSVECTOR` columns on the `ads` table:
  `search_vector_ru`, `search_vector_bs`, `search_vector_en`.
- Each column populated by the existing `ads_search_vector_fn` trigger using the
  correct PostgreSQL text-search config:
  - `ru`: `to_tsvector('russian', ...)`
  - `bs`: `to_tsvector('simple', ...)`
  - `en`: `to_tsvector('english', ...)`
- Each vector includes title (weight A), description (weight B), and
  category name (weight C) in the corresponding language.
- Three separate GIN indexes (`IX_ads_search_gin_ru`, `_bs`, `_en`).
- The old single `search_vector` column and its GIN index are dropped in a
  follow-up migration (after the new code is deployed).

### R2. Language-aware search view (no query translation)
- The `search` view (`apps/search/views/search.py`) resolves the locale from
  `request.LANGUAGE_CODE` via `LanguageLocale.from_code()`.
- The query is searched **in its original language** against the matching vector
  column — no `deep-translator` call in the search path.
- `SearchQuery(query, search_type="websearch", config=<locale.fts_config>)` and
  `SearchRank(F(<vector_field>), search_query)` are used for ranking.
- Single-word queries still trigger fuzzy category detection
  (`_fuzzy_category_match`), which must use the locale-appropriate category name
  for matching.

### R3. Category names indexed per language
- The trigger must index `category.name_i18n->>'bs'` in `search_vector_bs` and
  `category.name_i18n->>'en'` in `search_vector_en` (falling back to the
  Russian `name` if the localized value is missing).
- The `categories_name_propagate` trigger fires on `UPDATE OF name, name_i18n`
  (not just `name`) so category translation changes re-index all affected ads.

### R4. Saved search alerts: persisted language preference
- `SavedSearch` model gains a `language` column (`CharField`, max 5, nullable,
  defaults to `"bs"` — the project's fallback locale).
- The alert path (`find_matching_ads` in `alert_query.py`) reads
  `saved_search.language`, selects the matching vector + config, and searches
  **without** translating the query.
- The `send_alerts` management command has no `request.LANGUAGE_CODE`; the
  language is read from the persisted `SavedSearch.language` field.

### R5. Dead-code cleanup
- Remove from `query_translator.py`: `translate_query`,
  `translate_query_bs_to_ru`, `translate_cached`, `translate_cached_generic`,
  `invalidate_translation_cache`, and the module-level `_EXECUTOR` and
  `_CIRCUIT_BREAKER`. These have **no remaining callers** after R2/R4 remove
  the search and alert translation calls.
- Remove from `ad_create.py`: the obsolete `translate_to_russian` and
  `_do_translate` functions (0 callers; the active path uses
  `translate_all_languages` for publication-time translation).
- Keep `deep-translator` as a dependency — still used at publication time
  (`translate_all_languages` in `ad_create.py`) and in the
  `backfill_translations` management command.

### R6. Migration safety
- Multi-step migration sequence with zero search downtime (see §8).
- Seed data regenerated after migration (seed uses `bulk_create`, bypassing the
  trigger — a backfill `UPDATE` is required to populate vectors).

## 3. Conceptual Development Tasks

| # | Task | Purpose | Expected Outcome | Dependencies |
|---|---|---|---|---|
| T1 | Add per-language TSVECTOR columns & trigger | Model layer | Three new `SearchVectorField` columns on `Ad`; updated `Meta.indexes` with 3 GIN indexes; `LanguageLocale.fts_vector_field` property | None |
| T2 | DB migration: add columns + dual-write trigger + backfill | Migration | New migration adds 3 nullable columns, updates `ads_search_vector_fn` to dual-write (old + new), backfills existing rows via `UPDATE ads SET title = title` | T1 |
| T3 | Update search view to language-aware no-translation flow | Search path | `search.py` uses `LanguageLocale.from_code(request.LANGUAGE_CODE)` → selects vector field + config → no `translate_query` call | T2 |
| T4 | Update alert query to persisted language | Alert path | `alert_query.py` reads `saved_search.language`, selects vector + config, no `translate_query_bs_to_ru` call | T2, T5 |
| T5 | Add `language` column to `SavedSearch` | Model layer | New `saved_searches.language` column; migration | None |
| T6 | Update category name FTS per language | Trigger | `ads_search_vector_fn` indexes `name_i18n->>'bs'` / `name_i18n->>'en'`; `categories_name_propagate` fires on `name, name_i18n` | T2 (can be same migration) |
| T7 | Remove dead translation code | Cleanup | `query_translator.py` and `ad_create.py` stripped of dead functions; tests updated; `deep-translator` retained | T3, T4 |
| T8 | Update tests & docs | Testing | `test_search_triggers.py`, `test_alert_query.py` updated for per-language vectors; `search-patterns.md`, `db-indexes.md`, `db-schema.md` updated | T1–T7 |
| T9 | Drop old single `search_vector` column | Migration cleanup | Follow-up migration removes old `search_vector` + `IX_ads_search_gin` after production validation | T2, T3 (deployed & validated) |

## 4. Product Owner Decisions

All four PO questions were answered with **"Option A — recommended"** (verbatim:
«берем опцию а везде - рекомендовано»):

| Decision | Choice | Rationale |
|---|---|---|
| **D1 — Search vector architecture** | **A:** Separate per-language columns + 3 GIN indexes; drop old single vector | Perfect language isolation; correct per-language stemming; no cross-language false matches |
| **D2 — Saved search alerts language** | **A:** Add `language` column to `SavedSearch`, captured at creation from `request.LANGUAGE_CODE` | Each saved search remembers the user's language; alerts search the correct vector |
| **D3 — Category names in FTS** | **A:** Index `name_i18n->>'bs'` / `name_i18n->>'en'` in respective vectors; fall back to Russian `name` | Category names searchable in the user's language |
| **D4 — Dead code cleanup scope** | **A:** Remove all dead translation functions (`translate_query`, `translate_query_bs_to_ru`, `invalidate_translation_cache`, `translate_cached`, `translate_cached_generic`, `translate_to_russian`, `_do_translate`); keep `deep-translator` for publication + backfill | Project rule: no dead code; `deep-translator` still needed at ad publication |

## 5. Research Summary

Two Researcher agent reports were produced and reviewed:

### Research Report 1 — "Research multi-language FTS approaches"
- **Cross-language matching risk:** VERIFIED via PostgreSQL 18 docs. The `config`
  parameter in `SearchQuery`/`to_tsquery` controls **query parsing only** (lexeme
  normalization), NOT vector filtering. The `@@` operator is a pure
  set-membership test against ALL lexemes in the TSVECTOR. A single concatenated
  vector causes cross-language false matches (shared vocabulary like "radio"
  appearing in all configs) and false negatives (Russian stemming of
  "велосипеды"→`велосипед` won't match a `simple`-config query for
  "велосипеды"). **Confidence: HIGH.**
- **Trade-offs:** Separate vectors provide language isolation (correctness),
  higher index selectivity (per-index ~1/3 size), at the cost of 3× GIN indexes
  and slightly more trigger code. For the 500K-ad / 300-DAU scale, 3 GINs are
  negligible. **Confidence: HIGH.**
- **Migration safety:** `AddField` for nullable `TSVECTOR` is metadata-only on
  PG18 (no table rewrite). `DROP COLUMN` auto-removes associated GIN indexes;
  trigger function must be `CREATE OR REPLACE`'d before column drop.
  `DROP INDEX CONCURRENTLY` is supported but cannot be used inside a
  transaction block (Django RunSQL needs `atomic=False`). **Confidence: HIGH.**
- **Django ORM pattern:** `SearchVectorField` supports
  `.filter(**{f"search_vector_{locale}": search_query})` via kwargs expansion —
  no `extra()` or `raw()` needed. `SearchRank(F(vector_field), query)` for
  dynamic column names. **Confidence: HIGH.**
- **Category name localization:** `categories.name_i18n` is JSONB with
  `ru`/`bs`/`en` keys. The `categories_name_propagate` trigger currently fires
  only on `UPDATE OF name` — must be expanded to `name, name_i18n`. The
  `categories_name_propagate` function updates `ads.category_name`, which fires
  the `ads_search_vector_update` trigger, so the re-index cascade works
  automatically. **Confidence: HIGH.**
- **Alert path:** `find_matching_ads` (`alert_query.py:50`) hardcodes
  `translate_query_bs_to_ru`. `SavedSearch` has no language column. Must add
  `language` to `SavedSearch` and read it in the alert command
  (which runs without `request.LANGUAGE_CODE`). **Confidence: HIGH.**

### Research Report 2 — "Research FTS migration & dead code"
- **`translate_query` call sites:** `search.py:23` (import) + `search.py:95`
  (call). After T3, import removed.
- **`translate_query_bs_to_ru` call sites:** `alert_query.py:22` (import) +
  `alert_query.py:50` (call). After T4, import removed.
- **`invalidate_translation_cache`:** 0 call sites — dead code.
- **`translate_cached`:** 1 internal call (`query_translator.py:113`) + 1 test
  import (`test_query_translator.py:18,32`).
- **`translate_cached_generic`:** 2 internal calls (lines 149, 196) + 0 external
  test references.
- **`translate_to_russian` (`ad_create.py:652`):** 0 callers — dead code.
  Removing breaks NO tests.
- **`_do_translate` (`ad_create.py:645`):** only called from dead
  `translate_to_russian` (line 657). 0 external callers. Removing breaks NO
  tests.
- **`_do_translate_to` (`ad_create.py:792`):** the ACTIVE function used by
  `translate_all_languages` (`ad_create.py:798`). Called at lines 460, 463.
  Mocked in `test_multi_lang_translation.py` (8 methods) and
  `test_ad_create.py` (2 tests). **Cannot be removed.**
- **`translate_all_languages`:** active publication-time translation. **Cannot be
  removed.**
- **Test impact:** `test_query_translator.py` tests are entirely about
  `translate_query_bs_to_ru` — these tests must be deleted when the function is
  removed (T7). **Confidence: HIGH.**

## 6. Assumptions

- A1. The `LanguageLocale` enum (`apps/core/enums.py:160-201`) is the canonical
  language model. Its `fts_config` property (`enums.py:194-201`) maps
  `ru→"russian"`, `bs→"simple"`, `en→"english"`. A new `fts_vector_field`
  property will be added mapping to `search_vector_ru/bs/en`.
- A2. Search vector columns are **trigger-maintained** (BEFORE INSERT OR UPDATE
  on `ads`), NOT `GENERATED ALWAYS`. This is the current architecture
  (`ad/models.py:183-187` with `help_text="NOT GENERATED ALWAYS"`).
- A3. The Bosnian `simple` text-search config is intentional — PostgreSQL has no
  `bosnian` config. The `simple` config (lowercase + tokenize, no stemming) is
  a known limitation documented in the audit
  (`.ai/audit/08-search-fts/findings.md`) and accepted for MVP.
- A4. Seed data uses `bulk_create` which bypasses the trigger — existing seed
  data will have NULL vector columns after adding them. A backfill `UPDATE`
  (`UPDATE ads SET title = title`) is required to populate vectors for seeded
  ads.
- A5. The `backfill_translations` management command
  (`src/backend/apps/ads/management/commands/backfill_translations.py`) runs
  **outside** of migrations (manual command), so it does not need changes. Only
  the trigger and search view need updating.
- A6. The bot's `translate_all_languages` (`ad_create.py:798`) continues to
  translate ad content at publication time using `deep-translator`. This is the
  only allowed use of the external translator — content is translated once, not
  at search time.

## 7. Constraints

- C1. **PostgreSQL 18 only.** PostgreSQL text-search configs (`russian`,
  `english`, `simple`) and `tsvector` are PostgreSQL-specific. SQLite (Django's
  test DB default) does NOT support these. All FTS tests must use real PostgreSQL
  (marked `pytest.mark.integration` / `pytest.mark.slow`).
- C2. **StrEnum for all constants.** The `LanguageLocale` enum must be used for
  language codes and FTS config selection — no inline string literals.
- C3. **No `print()` statements.** All logging via `logging.getLogger(__name__)`.
- C4. **Migrations run exactly once.** The two-process architecture (web + bot)
  means migrations must be idempotent and run before both start.
- C5. **`deep-translator` retained as a dependency.** It is still used at
  publication time and in the backfill command. Only the *query-translation*
  functions are removed.
- C6. **No search results degradation.** The per-language vectors must produce
  results at least as relevant as the current Russian-translated approach. The
  Russian vector is the default; all existing Russian-language ads remain
  searchable in Russian.

## 8. Migration Sequence

### Phase 1 — Deploy new vectors (backwards compatible)
1. **Add columns** (new migration `0007_search_vector_i18n`):
   ```python
   migrations.AddField(model_name='ad', name='search_vector_ru',
       field=models.SearchVectorField(blank=True, null=True))
   migrations.AddField(model_name='ad', name='search_vector_bs', ...)
   migrations.AddField(model_name='ad', name='search_vector_en', ...)
   ```
   Metadata-only on PG18 (no table rewrite for nullable columns).

2. **Update trigger function** (dual-write) via `RunSQL`:
   `CREATE OR REPLACE FUNCTION ads_search_vector_fn()` — assigns to BOTH
   `NEW.search_vector` (old) and `NEW.search_vector_ru/bs/en` (new).

3. **Category i18n trigger update** — expand `categories_name_propagate`
   trigger to fire on `UPDATE OF name, name_i18n`.

4. **Backfill existing rows** via `RunSQL`:
   ```sql
   UPDATE ads SET title = title;
   ```
   Fires the BEFORE UPDATE trigger, populating all vector columns.

5. **Add 3 GIN indexes** (in the same or follow-up migration):
   ```python
   GinIndex(name="IX_ads_search_gin_ru", fields=["search_vector_ru"]),
   GinIndex(name="IX_ads_search_gin_bs", fields=["search_vector_bs"]),
   GinIndex(name="IX_ads_search_gin_en", fields=["search_vector_en"]),
   ```
   NOTE: Building 3 GIN indexes on a populated table causes a full table scan
   per index. On 500K rows this may take several minutes. Should run during a
   low-traffic window or with `CONCURRENTLY`.

### Phase 2 — Deploy code that reads new vectors
6. Update `search.py` (T3) and `alert_query.py` (T4) to use per-language vectors.
7. Add `LanguageLocale.fts_vector_field` property (T1).
8. Add `SavedSearch.language` column (T5).
9. Run seed to regenerate demo data.

### Phase 3 — Remove old column (cleanup)
10. After production validation (new code live, queries using new vectors):
    - Migration: drop old GIN index `IX_ads_search_gin`, drop
      `search_vector` column, update trigger to stop dual-writing.

### Downtime assessment
- **Phase 1 steps 1–4:** Near-zero downtime. `ADD COLUMN` is metadata-only on
  PG18. `CREATE OR REPLACE FUNCTION` is atomic. The `UPDATE` backfill acquires
  ROW EXCLUSIVE locks per row (compatible with reads).
- **Phase 1 step 5 (3 GIN indexes):** Blocking if built normally. Use
  `CREATE INDEX CONCURRENTLY` (requires `atomic=False` on the migration) to
  avoid table locks.
- **Phase 3:** `DROP INDEX CONCURRENTLY` is non-blocking; `DROP COLUMN` is
  metadata-only on PG18.

## 9. Risks

| Risk | Impact | Mitigation |
|---|---|---|
| R1 — Seed data vectors not populated | Search returns no results in dev | Seed `bulk_create` bypasses trigger; run `UPDATE ads SET title = title` after seeding, or use `Ad.save()` in seed (slower but correct) |
| R2 — GIN index build blocks writes for minutes | Production downtime window | Use `CREATE INDEX CONCURRENTLY` with `atomic=False` migration |
| R3 — Old single-vector GIN index still queried by stale code | Search silently uses wrong vector | Deploy code change (T3/T4) BEFORE or in the same window as dropping the old column |
| R4 — Category `name_i18n` updates don't re-index ads | Stale category names in search | Expand `categories_name_propagate` trigger to fire on `name_i18n` (T6) |
| R5 — `test_query_translator.py` deletion loses test coverage | Regression risk for ad-publication translation | Verify `test_multi_lang_translation.py` covers `translate_all_languages` (the retained function). Publication-time translation is tested via bot integration tests |
| R6 — Bosnian `simple` config has no stemming | Less relevant Bosnian search results | Known MVP limitation (A3). Document; revisit if needed |
| R7 — SavedSearch.language defaults to `"bs"` for old rows | Existing saved searches search Bosnian vector | Acceptable — they currently search Russian-translated; switching to Bosnian vector is a behavior change. Consider a data migration defaulting old rows to `"ru"` |

## 10. Open Questions

None. All four PO decisions (D1–D4) were resolved with "Option A — recommended".
The research reports confirmed feasibility with HIGH confidence.

## 11. Out of Scope

- **Elasticsearch / OpenSearch migration** — Decision_12 explicitly recommends
  against this for MVP (PostgreSQL FTS + `pg_trgm` is sufficient).
- **Bosnian text-search stemming** — PostgreSQL has no `bosnian` config; `simple`
  (no stemming) is retained as an accepted MVP limitation.
- **Per-user query language detection** — language is determined from
  `request.LANGUAGE_CODE` (the user's UI language preference), not from
  analyzing the query text's language. This is consistent with the existing
  `LanguagePreMiddleware` design.
- **Frontend search UI changes** — the HTMX autocomplete (`f37e9ab` commit) is
  unaffected. Only the backend FTS query construction changes.

## 12. Definition of Ready

A task in this specification is "ready" when:

1. **T1:** The Django model has `search_vector_ru/bs/en` fields with 3 GIN
   indexes; `LanguageLocale.fts_vector_field` property returns the correct
   column name.
2. **T2:** A reproducible migration applies cleanly on an empty database and
   backfills a populated database without errors; the trigger maintains all
   three vector columns on INSERT/UPDATE.
3. **T3:** `search.py` no longer imports or calls `translate_query`; it selects
   the vector column and config from `LanguageLocale`; FTS search returns correct
   results for Russian, Bosnian, and English queries (verified by tests using
   real PostgreSQL).
4. **T4:** `alert_query.py` no longer imports `translate_query_bs_to_ru`; it reads
   `saved_search.language` and selects the vector/config accordingly.
5. **T5:** `SavedSearch` model has a non-null `language` column defaulting to
   `"bs"`; the `SavedSearch` creation UI stores `request.LANGUAGE_CODE`.
6. **T6:** The `ads_search_vector_fn` trigger indexes localized category names
   (`name_i18n->>'bs'`, `name_i18n->>'en'`); `categories_name_propagate` fires
   on `name, name_i18n` updates.
7. **T7:** `query_translator.py` contains no `translate_query`,
   `translate_query_bs_to_ru`, `translate_cached*`, or
   `invalidate_translation_cache`; `ad_create.py` contains no `translate_to_russian`
   or `_do_translate`; `deep-translator` import remains.
8. **T8:** All existing tests that reference removed functions are updated or
   deleted; `test_search_triggers.py` tests all three language vectors;
   `test_alert_query.py` uses the `language` column; documentation reflects the
   new architecture.
9. **T9:** The old `search_vector` column + `IX_ads_search_gin` index are dropped
   in a separate migration after production validation; no code references the
   old column.

---

*Specification produced from Decision_12 (owner recommendation) and two
Researcher reports. PO decisions: all Option A. Next free spec number: 11.*
