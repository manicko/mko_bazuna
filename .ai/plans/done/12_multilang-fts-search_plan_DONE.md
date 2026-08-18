# Plan 12 — Multi-Language FTS Search

**Source spec:** `.ai/problems/11_multilang-fts-search_spec.md`
**Status:** done
**Created:** 2026-08-17
**Completed:** 2026-08-18

---

## 1. Execution DAG Overview

Work is reorganised from the spec's conceptual task list (T1–T9) into
dependency-safe execution groups. The plan is **not** a 1:1 mirror of T1–T9;
it re-sequences around real dependencies (migration ordering, active-vs-dead
code, deploy/validation gates).

```
G1  (parallel model layer, no DB)
    ├─ impl_001  Ad model per-language vectors + fts_vector_field   (spec T1)
    └─ impl_002  SavedSearch.language + search migration 0003       (spec T5)

G2  (DB migration, risky — blocked on impl_001)
    ├─ impl_003  ads migration 0007: add cols + dual-write + i18n category + backfill (spec T2/T6)
    └─ impl_004  ads migration 0008: 3 GIN indexes (CONCURRENTLY, atomic=False) — depends impl_003

G3  (code reading new vectors, parallel — blocked on impl_001 + impl_003/004 + impl_002)
    ├─ impl_005  search view -> per-language, no translation          (spec T3/R2)
    └─ impl_006  alert query -> per-language, persisted language      (spec T4/R4)

G4  (cleanup — blocked on impl_005 + impl_006)
    └─ impl_007  dead translation code cleanup                        (spec T7/R5)

G5  (verification + docs)
    ├─ impl_008  update FTS / alert / translation tests              (spec T8)
    ├─ impl_009  update docs (search-patterns / db-indexes / db-schema) (spec T8)
    └─ verify_001  PostgreSQL FTS integration verification (real PG)

G6  (deployment-gated Phase 3)
    └─ impl_010  drop old single search_vector column + old GIN (deferred) (spec T9/R6)
```

## 2. Confirmed Conflicts & Reinterpretation (MUST READ BEFORE IMPLEMENTATION)

The spec's dead-code requirement (R5 / D4 / DoR-7) and its research report 2
were authored against **obsolete line numbers and an outdated file structure**.
Current code reality differs in three material ways. The plan has been scoped
to reality; implementors must NOT follow R5 verbatim.

### Conflict C1 — R5/R4 cleanup targets the wrong module and wrong functions
`apps/search/services/query_translator.py` is a **re-export shim** only; the
functions listed in R5 (`translate_query`, `translate_query_bs_to_ru`,
`translate_cached`, `translate_cached_generic`, `invalidate_translation_cache`,
`_EXECUTOR`, `_CIRCUIT_BREAKER`) all live in
`apps/core/services/translation.py`.

More importantly, **most of them are still ACTIVE on the publication-time path**:
- `ad_create.py` imports `translate_text` (line 22) and `translate_all_languages`
  (line 771) delegates publication-time translation to
  `translate_text` → which internally uses `_EXECUTOR`, `_CIRCUIT_BREAKER`,
  `translate_cached_generic`, and `translate_cached`.
- `test_multi_lang_translation.py` verifies exactly this path and mocks
  `translate_cached_generic` / `translate_cached` / `_CIRCUIT_BREAKER`.

**Removing these breaks ad-publication translation.** This is a deliberate
redirect from R5. The only genuinely dead items after impl_005/impl_006 are:
- `translate_query_bs_to_ru` (sole caller `alert_query.py` removed in impl_006)
- the `translate_query` **alias name** (sole caller `search.py` removed in
  impl_005); the `translate_text` function itself is retained
- `invalidate_translation_cache` (0 callers, verified)
- the `query_translator.py` shim (sole consumers removed/deleted)
- `apps/core/services/__init__.py` re-export of the removed names.

### Conflict C2 — `ad_create.py` already has no dead functions
R5/D4 names `translate_to_russian` and `_do_translate` in `ad_create.py`
(line ~645–657). These **no longer exist** — they were removed in the earlier
consolidation refactor. `impl_007` makes **no change** to `ad_create.py`; it
retains the `translate_text` import (line 22) used by the active
`translate_all_languages`.

### Conflict C3 — No SavedSearch creation UI exists in the repo
D2/DoR-5 says "the `SavedSearch` creation UI stores `request.LANGUAGE_CODE`".
No web UI or bot handler creates `SavedSearch` except tests. The `language`
field therefore follows R4 exactly (`CharField(max_length=5, nullable=True,
default="bs")`) plus a **data migration** defaulting existing rows to `"ru"`
per R7 mitigation (so existing Russian-translated alert behavior is preserved
for legacy rows). Future creation sites can populate the field, but none exist
today — no speculative UI work is performed.

---

## 3. Risk Assessment

| Task | Risk | Rationale | Gate |
|---|---|---|---|
| impl_003 | **HIGH** | Schema change + trigger rewrite + backfill UPDATE on populated `ads`; migrations run exactly once (C4) | Spec §8/§9 validated approach; must apply cleanly on empty + populated DB |
| impl_004 | **HIGH** | 3 GIN indexes on populated table; `CONCURRENTLY` requires `atomic=False` migration | Build in low-traffic window / `CONCURRENTLY` per spec §8 |
| impl_005 | **MEDIUM** | Cross-module FTS query change; must not regress Russian default (C6) | PostgreSQL integration test |
| impl_006 | **MEDIUM** | Reads new persisted field; behavior change for legacy rows (R7) | Unit test with `language` column |
| impl_007 | **MEDIUM** | Wrong removals break publication-time translation (C1) | Verify `test_multi_lang_translation.py` green |
| impl_010 | **HIGH** | Drops column referenced by any stale code as a working process | Deploy + validate G3 code first; deployment gate |

Research gate: the spec contains two Researcher reports confirming feasibility
(PG18 migration semantics, cross-language matching risk, Django `SearchVectorField`
pattern, alert path) with **HIGH confidence**. These satisfy the required
research gate for impl_003/impl_004 — no additional researcher run needed.

---

# Implementation Tasks

---

## Task impl_001

**id:** impl_001
**title:** Add per-language search vector fields to `Ad` model + `LanguageLocale.fts_vector_field`
**priority:** high
**depends_on:** []
**source_reference:** `.ai/problems/11_multilang-fts-search_spec.md`
**source_section:** T1 — Add per-language TSVECTOR columns & trigger

**description:**
Add three nullable `SearchVectorField` columns (`search_vector_ru`,
`search_vector_bs`, `search_vector_en`) on the `Ad` model and their three GIN
index declarations in `Meta.indexes`. Add a `fts_vector_field` property on
`LanguageLocale` mapping `ru→search_vector_ru`, `bs→search_vector_bs`,
`en→search_vector_en`. Do **not** run/generate any migration in this task —
migration wiring is owned by impl_003/impl_004.

**goals:**
- Model exposes the three per-language vector columns
- `LanguageLocale` resolves the active vector column per language (StrEnum, C2)
- No runtime behaviour change until migrations exist

**files:**
- `src/backend/apps/ads/models.py`
  - targets:
    - class `Ad` → add 3 `SearchVectorField` fields adjacent to existing `search_vector`
    - class `Ad.Meta` → add 3 `GinIndex` entries (`IX_ads_search_gin_ru/_bs/_en` on the new fields)
- `src/backend/apps/core/enums.py`
  - targets:
    - enum `LanguageLocale` → add `fts_vector_field` property (mirroring `fts_config`)

**changes:**
- action: add_field — 3 SearchVectorField columns on `Ad` (`blank=True, null=True`, NOT GENERATED ALWAYS per A2, matching existing `search_vector` help-text convention)
- action: add_field — 3 GinIndex entries in `Ad.Meta.indexes`
- action: add_code — `LanguageLocale.fts_vector_field` property returning the column name via a mapping keyed on the enum value (use StrEnum, no inline literals)

**acceptance_criteria:**
- `Ad._meta` exposes `search_vector_ru/bs/en`
- `LanguageLocale.RUSSIAN.fts_vector_field == "search_vector_ru"` (and `bs`, `en`)
- module imports cleanly (lint + typecheck pass)

---

## Task impl_002

**id:** impl_002
**title:** Add `language` column to `SavedSearch` + data migration (legacy default)
**priority:** high
**depends_on:** []
**source_reference:** `.ai/problems/11_multilang-fts-search_spec.md`
**source_section:** T5 — Add `language` column to SavedSearch; R7 risk mitigation

**description:**
Add `SavedSearch.language` (`CharField`, max 5, nullable, `default="bs"` per R4)
and the search-app migration `0003` that adds the column and backfills existing
rows to `"ru"` (R7 mitigation preserving legacy Russian-translated behavior).

**goals:**
- Persisted per-search language (StrEnum-compatible values `ru`/`bs`/`en`)
- Existing rows default to `"ru"` (legacy behaviour preserved)
- Migration idempotent (C4)

**files:**
- `src/backend/apps/search/models.py` — class `SavedSearch`, add `language` field
- `src/backend/apps/search/migrations/0003_savedsearch_language.py`

**changes:**
- action: add_field — `SavedSearch.language` (`models.CharField(max_length=5, blank=True, null=True, default="bs")`, help_text documenting value is a `LanguageLocale` code)
- action: add_migration — `0003`: `AddField` + a data migration `UPDATE saved_searches SET language = 'ru' WHERE language IS NULL` (or schema default handling) so legacy rows search the Russian vector
- do not add a creation UI (no such site exists in the repo — C3)

**acceptance_criteria:**
- `SavedSearch` model has `language`; `0003` applies cleanly on empty + populated DB
- old rows end with `language = "ru"`
- new rows default to `"bs"`

---

## Task impl_003

**id:** impl_003
**title:** ads migration `0007` — add vector columns, dual-write trigger, i18n category, backfill
**priority:** high
**risk:** HIGH
**depends_on:** [impl_001]
**source_reference:** `.ai/problems/11_multilang-fts-search_spec.md`
**source_section:** T2, T6, §8 Phase 1

**description:**
Hand-write `src/backend/apps/ads/migrations/0007_search_vector_i18n.py` (atomic)
that: (1) `AddField`s the three nullable vector columns (`SeparateDatabaseAndState`
is NOT required here — `AddField` is metadata-only on PG18), (2) `CREATE OR REPLACE
FUNCTION ads_search_vector_fn()` to **dual-write** the legacy `search_vector` AND
the three new per-language columns using `russian`/`simple`/`english` configs,
including localized category names (`name_i18n->>'bs'`, `name_i18n->>'en'`,
falling back to Russian `name`), (3) expands the `categories_name_propagate`
trigger to fire on `UPDATE OF name, name_i18n`, and (4) backfills with
`UPDATE ads SET title = title;` to populate vectors for rows created via
`bulk_create` (seed — A4/R6).

**goals:**
- Backwards-compatible dual-write (old + new columns populated)
- Localized category names indexed per language (T6/R3)
- Category i18n name changes cascade re-index (T6/R4)
- Existing rows backfilled (seed-safe)

**files:**
- `src/backend/apps/ads/migrations/0007_search_vector_i18n.py`

**changes:**
- action: add_migration — `0007`, atomic:
  - 3 × `migrations.AddField` (`search_vector_ru/bs/en`, `SearchVectorField`, nullable)
  - `RunSQL` `CREATE OR REPLACE FUNCTION ads_search_vector_fn()` dual-write (old `search_vector` + new `_ru/_bs/_en`; category weight C uses `coalesce(name_i18n->>'bs', v_cat)` / `->>'en'` for bs/en vectors)
  - `RunSQL` `DROP TRIGGER ... CREATE TRIGGER ... AFTER UPDATE OF name, name_i18n ON categories`
  - `RunSQL` backfill `UPDATE ads SET title = title;`
- do **not** create the 3 GIN indexes here (owned by impl_004, CONCURRENTLY)

**acceptance_criteria:**
- applies cleanly on empty database and on a populated database (with seed)
- after backfill, all three vector columns are non-NULL on existing rows
- INSERT/UPDATE maintains all four vector columns (legacy + 3 new)
- category rename AND category `name_i18n` edit trigger re-index (verified via SQL)

---

## Task impl_004

**id:** impl_004
**title:** ads migration `0008` — 3 GIN indexes built CONCURRENTLY
**priority:** high
**risk:** HIGH
**depends_on:** [impl_003]
**source_reference:** `.ai/problems/11_multilang-fts-search_spec.md`
**source_section:** §8 Phase 1 step 5; R2 risk

**description:**
Separate **non-atomic** migration (`atomic=False`) that builds
`IX_ads_search_gin_ru/_bs/_en` with `CREATE INDEX CONCURRENTLY` to avoid
blocking writes on the populated table (R2). Because `Meta.indexes` (impl_001)
declares these GINs, use `SeparateDatabaseAndState` so the index state is
recognised by Django while the database is built non-blockingly.

**goals:**
- 3 GIN indexes present and usable by FTS
- no write-blocking table lock during build (CONCURRENTLY)
- Django state stays consistent with the model (no phantom `makemigrations`)

**files:**
- `src/backend/apps/ads/migrations/0008_search_vector_gin.py`

**changes:**
- action: add_migration — `0008`, `atomic=False`, via `SeparateDatabaseAndState`:
  - database operations: 3 × `RunSQL CREATE INDEX CONCURRENTLY IX_ads_search_gin_* ON ads USING gin(search_vector_*)`
  - state operations: 3 × `AddIndex` matching the `GinIndex` declarations in `Ad.Meta`
  - reverse: `DROP INDEX CONCURRENTLY` + `RemoveIndex` state
- schedule during low-traffic window / before both processes start (C4)

**acceptance_criteria:**
- migration completes without ERROR; indexes exist via `\di ads_*`
- `makemigrations --check --dry-run` reports no pending changes for these indexes
- reverting `0007`+`0008` works on a dev DB

---

## Task impl_005

**id:** impl_005
**title:** Update search view to language-aware, no-translation FTS
**priority:** high
**depends_on:** [impl_001, impl_003, impl_004]
**source_reference:** `.ai/problems/11_multilang-fts-search_spec.md`
**source_section:** T3 / R2

**description:**
Rewrite the FTS query construction in `apps/search/views/search.py` to resolve
the locale via `LanguageLocale.from_code(request.LANGUAGE_CODE)`, select the
corresponding vector column + FTS config, and search **without** the
`translate_query` call. Make single-word fuzzy category detection locale-aware.

**goals:**
- remove the external translator from the search critical path
- search the buyer's own language vector (no cross-language false matches)
- keep Russian as a fully working default (C6)
- `_fuzzy_category_match` matches the locale-appropriate category name

**files:**
- `src/backend/apps/search/views/search.py`
  - targets:
    - function `search`
    - function `_fuzzy_category_match`
    - function `_fuzzy_match_by_name`

**changes:**
- action: remove_import — `from apps.search.services.query_translator import translate_query`
- action: add_import — `from django.db.models import F`; `from apps.core.enums import LanguageLocale`
- action: replace_code — inside `search`, replace translation block with:
  - `locale = LanguageLocale.from_code(request.LANGUAGE_CODE)`
  - `field = locale.fts_vector_field`; `config = locale.fts_config`
  - `search_query = SearchQuery(query, search_type="websearch", config=config)`
  - `ads = ads.annotate(rank=SearchRank(F(field), search_query)).filter(**{field: search_query}).order_by("-rank")`
- action: replace_code — `_fuzzy_category_match(query, locale)` and `_fuzzy_match_by_name(query, locale)` to match against `Category.get_name(locale)` (i18n-aware), passing `locale` from `search`
- action: replace_docstring — update module/function docstrings (English, C3)

**acceptance_criteria:**
- no import/call of `translate_query` remains
- Russian, Bosnian, English queries hit the correct vector/config
- single-word fuzzy category match works for `ru`/`bs`/`en` category names
- lint + typecheck + FTS integration tests pass

---

## Task impl_006

**id:** impl_006
**title:** Update alert query to persisted-language FTS
**priority:** high
**depends_on:** [impl_001, impl_002, impl_003, impl_004]
**source_reference:** `.ai/problems/11_multilang-fts-search_spec.md`
**source_section:** T4 / R4

**description:**
Update `apps/search/services/alert_query.py` `find_matching_ads` to read
`saved_search.language`, resolve the locale to a vector column + FTS config, and
search **without** `translate_query_bs_to_ru`. The command `send_alerts` runs
without `request.LANGUAGE_CODE`, so the persisted field is the sole source.

**goals:**
- alerts search the user's persisted language vector
- remove the external translator from the alert path
- legacy rows (impl_002 sets `"ru"`) keep existing behaviour

**files:**
- `src/backend/apps/search/services/alert_query.py`
  - targets:
    - function `find_matching_ads`

**changes:**
- action: remove_import — `from apps.search.services.query_translator import translate_query_bs_to_ru`
- action: add_import — `from apps.core.enums import LanguageLocale`; `from django.db.models import F`
- action: replace_code — inside `find_matching_ads`, replace translation + fixed-`russian` block with:
  - `locale = LanguageLocale.from_code(saved_search.language, fallback=LanguageLocale.RUSSIAN)`
  - `field = locale.fts_vector_field`; `config = locale.fts_config`
  - `search_query = SearchQuery(saved_search.query, search_type="websearch", config=config)`
  - `queryset = queryset.annotate(rank=SearchRank(F(field), search_query)).filter(**{field: search_query}).order_by("-rank")`

**acceptance_criteria:**
- no import/call of `translate_query_bs_to_ru` remains
- `find_matching_ads` uses `saved_search.language` to pick vector/config
- alert unit tests (updated in impl_008) pass

---

## Task impl_007

**id:** impl_007
**title:** Remove genuinely dead translation code (scoped per Conflict C1/C2)
**priority:** medium
**risk:** MEDIUM
**depends_on:** [impl_005, impl_006]
**source_reference:** `.ai/problems/11_multilang-fts-search_spec.md`
**source_section:** T7 / R5 / D4 (SCALED to code reality — see §2 Conflicts)

**description:**
Remove only the genuinely dead query-translation code, **preserving** the active
publication-time path (`translate_text` + `_EXECUTOR` + `_CIRCUIT_BREAKER` +
`translate_cached` + `translate_cached_generic`, all still used by
`ad_create.py`). Make **no** change to `ad_create.py`. Delete the obsolete
`test_query_translator.py`. Retain `deep-translator` (C5).

**goals:**
- no dead query-translation code remains
- publication-time translation (bot `translate_all_languages`) is NOT broken
- `deep-translator` dependency retained

**files:**
- `src/backend/apps/core/services/translation.py`
  - targets:
    - function `translate_query_bs_to_ru` → delete
    - assignment/alias `translate_query = translate_text` → delete (keep `translate_text`)
    - function `invalidate_translation_cache` → delete (0 callers)
    - KEEP: `translate_text`, `translate_cached`, `translate_cached_generic`, `_EXECUTOR`, `_CIRCUIT_BREAKER`, `TranslationCircuitBreaker`
- `src/backend/apps/search/services/query_translator.py` → delete shim (all consumers removed)
- `src/backend/apps/core/services/__init__.py` → remove re-exports of deleted names (`translate_query_bs_to_ru`, `translate_query`, `invalidate_translation_cache`); keep `translate_text`
- `src/backend/apps/search/tests/test_query_translator.py` → delete

**changes:**
- action: delete_symbol `translate_query_bs_to_ru`
- action: delete_symbol `invalidate_translation_cache`
- action: delete_code — `translate_query = translate_text` alias
- action: add/remove — trim `query_translator.py` (delete file) and `core/services/__init__.py` re-exports
- action: verify — `translate_text` remains importable and unused-by-search (publication-time only)

**acceptance_criteria:**
- `translate_query_bs_to_ru`, `translate_query`, `invalidate_translation_cache` absent from `core/services/translation.py` and `__init__.py`
- `query_translator.py` file removed; no imports of it remain anywhere
- `ad_create.py` still imports `translate_text` and `translate_all_languages` works (bot tests pass)
- `test_query_translator.py` removed.

---

## Task impl_008

**id:** impl_008
**title:** Update FTS, alert, and translation tests for per-language vectors
**priority:** medium
**depends_on:** [impl_001, impl_002, impl_003, impl_004, impl_005, impl_006, impl_007]
**source_reference:** `.ai/problems/11_multilang-fts-search_spec.md`
**source_section:** T8

**description:**
Update existing integration/unit tests to the new per-language architecture.
All FTS tests use real PostgreSQL `pytest.mark.integration`/`slow` (C1).

**goals:**
- `test_search_triggers.py` verifies all three language vectors are maintained
  and queryable per language (ru/bs/en), including localized category names
- `test_alert_query.py` uses the `language` column and verifies per-language
  vector selection
- removed-function coverage is backfilled by verifying
  `test_multi_lang_translation.py` (publication-time path) passes
- `test_query_translator.py` deleted

**files:**
- `src/backend/apps/ads/tests/test_search_triggers.py`
- `src/backend/apps/search/tests/test_alert_query.py`
- `src/telegram_bot/tests/test_multi_lang_translation.py` (verify; do not weaken)

**changes:**
- action: update_tests — `test_search_triggers.py`: assert `search_vector_ru/bs/en` populated on INSERT; `_fts_match` parametrised over locale/vector/config; category `name_i18n->>'bs'`/`->>'en'` searchable; category `name_i18n` edit cascades re-index
- action: update_tests — `test_alert_query.py`: create `SavedSearch` with explicit `language`; assert Bosnian/English/legacy-Russian searches hit the right vector
- action: verify — run `test_multi_lang_translation.py` mars is still green (C1 gate)

**acceptance_criteria:**
- updated FTS/alert tests pass on real PostgreSQL
- `test_multi_lang_translation.py` green (publication-time translation intact)

---

## Task impl_009

**id:** impl_009
**title:** Update documentation for per-language FTS search
**priority:** low
**depends_on:** [impl_001, impl_003, impl_005, impl_006, impl_007]
**source_reference:** `.ai/problems/11_multilang-fts-search_spec.md`
**source_section:** T8

**description:**
Update architecture/data docs to reflect separate per-language vectors, the
language-aware search/alert flow, the removal of query-time translation, and
the retained publication-time translator.

**goals:**
- docs match the new architecture (project rule 14)
- no stale references to query-time Google Translate

**files:**
- `docs/01-spec/search-patterns.md`
- `docs/02-database/db-indexes.md`
- `docs/02-database/db-schema.md`

**changes:**
- action: update_docs — per-language vector columns + 3 GIN indexes; search/alert flow no longer translates the query; `SavedSearch.language` persisted field; `deep-translator` used only at publication time

**acceptance_criteria:**
- docs accurately describe per-language vectors + no-query-translation flow

---

## Task verify_001

**id:** verify_001
**title:** Verify — per-language FTS integration (real PostgreSQL)
**type:** verification
**status:** pending
**depends_on:** [impl_005, impl_006, impl_007, impl_008]
**verifies:** [impl_003, impl_004, impl_005, impl_006, impl_007, impl_008]

**verification_steps:**
- test: `uv run pytest src/backend/apps/ads/tests/test_search_triggers.py -m integration -v`
- test: `uv run pytest src/backend/apps/search/tests/test_alert_query.py -m integration -v`
- test: `uv run pytest src/telegram_bot/tests/test_multi_lang_translation.py -v`
- test: `uv run pytest src/backend/apps/search/tests -k "not query_translator" -v`
- migration: `uv run python src/backend/manage.py makemigrations --check --dry-run` (no drift)
- seed: run seed, then verify `UPDATE ads SET title = title;` backfilled vectors in dev

**pass_criteria:**
- all FTS/alert/translation tests pass
- no pending migrations
- seed data yields populated per-language vectors after backfill
- publication-time translation path green

**failure_action:** return affected implementation task (impl_003/004/005/006/007/008) to rework
**rollback_task:** none (feature-flagged via dual-write; old column retained until impl_010)

---

## Task impl_010

**id:** impl_010
**title:** Drop legacy single `search_vector` column + old GIN (Phase 3, deployment-gated)
**priority:** low
**risk:** HIGH
**depends_on:** [impl_003, impl_005, impl_006, verify_001]
**blocked_by:** production validation that new code is live and querying new vectors (spec §8 Phase 3, R3)
**source_reference:** `.ai/problems/11_multilang-fts-search_spec.md`
**source_section:** T9 / §8 Phase 3

**description:**
After the new code is deployed and validated, add a follow-up ads migration
(`0009`, `atomic=False`) that: drops `IX_ads_search_gin` (`DROP INDEX
CONCURRENTLY`), `RemoveField`s `search_vector`, and updates
`ads_search_vector_fn` to stop dual-writing. No code may reference the old
column at deploy time.

**goals:**
- remove the now-dead single concatenated vector + index
- zero-downtime drop (CONCURRENTLY + metadata-only DROP COLUMN on PG18)

**files:**
- `src/backend/apps/ads/migrations/0009_drop_legacy_search_vector.py`
- `src/backend/apps/ads/models.py` (remove `search_vector` field + `IX_ads_search_gin` from `Meta.indexes`)

**changes:**
- action: add_migration — `0009` (`atomic=False`): `SeparateDatabaseAndState` with `DROP INDEX CONCURRENTLY IX_ads_search_gin`, `DROP COLUMN search_vector`, `CREATE OR REPLACE FUNCTION ads_search_vector_fn()` writing only the 3 new vectors
- action: remove_field — `Ad.search_vector`; remove `IX_ads_search_gin` from `Ad.Meta.indexes`
- deploy ONLY after verify_001 and production soak

**acceptance_criteria:**
- no references to `search_vector` or `IX_ads_search_gin` anywhere (grep clean)
- migration applies with zero downtime on PG18
- search behaves identically to pre-cleanup state

---

# Task Dependency / Order Summary

```
GROUP 1  (parallel, no deps)
  impl_001 ──┬──► impl_003 ──► impl_004
  impl_002 ──┴──────┴───────────┴──► impl_005  (parallel with impl_006)
                                   ├──► impl_006
                                   └──────────► impl_007 ──► impl_008 / impl_009 / verify_001
                                                                         └──► impl_010 (deployment gate)
```

**Parallel-safe groups:** Group 1 (impl_001 ∥ impl_002); Group 3 (impl_005 ∥
impl_006); docs (impl_009) may run once its inputs land, independent of tests.

**Deployment note:** impl_003/impl_004 (Phase 1) + impl_005/impl_006/impl_007
(Phase 2) are compatible and shipped together with dual-write; impl_010 (Phase 3)
is a separately-scheduled follow-up after soak.
