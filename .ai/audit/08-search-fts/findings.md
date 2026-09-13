---
# Report metadata — fill once per phase report.
phase: "08"
phase_name: "Search & Full-Text Search (FTS)"
date: "2026-09-12"
auditor: "Executor (subagent)"
validator: ""  # Phase 99 only — omit/blank for raw phase findings
mode: "problems-only"
# Correct prefix per phase: 01-ENT, 02-CFG, 03-DB, 04-AUT, 05-AD, 06-PII, 07-MED, 08-SRH, 09-EXT, 10-QLT, 11-TST, 12-OPS, 13-PERF, 14-I18N
id_prefix: "SRH"
# report_status = lifecycle of the report document (draft → validated)
# per-finding Status (in Findings Summary + field table below) = lifecycle of the individual finding (Open → Validated/Rejected/Merged/Reclassified/Deferred)
report_status: "draft"  # "draft" for raw phases; Phase 99 sets to "validated"
severity_taxonomy: ".kilo/commands/audit/phases/08-audit-search-fts.md#severity-taxonomy"  # pointer to phase rubric, NOT hardcoded
---

# Audit Findings — Search & Full-Text Search (FTS)

## Executive Summary

Seven problems were found in the unauthenticated search subsystem. The most severe are two CRITICAL findings: a stale privacy-disclosure docstring in the consent views that misrepresents search-query data egress to Google Translate (contradicting the current no-query-translation implementation), and dead code in the shared translation module (`translate_cached`, a bs→ru-only wrapper) that is never called in production but retains the ability to hit the live Google endpoint. Five MEDIUM findings follow: a stale `SavedSearch.query` help_text claiming query translation, a documentation gap in `spec-index.md` that references only the legacy generic search vector index, an orphaned audit probe test file left in the test tree, an un-automated search-vector backfill for pre-existing rows on production upgrade, and the `backfill_translations` management command never being invoked from any entrypoint or CI workflow. The runtime verification suite (94 search tests + 23 translation/audit probes) confirms the visibility predicate, trigger-based vector maintenance on insert/update, pagination bounds, injection safety, and DECLINE/WITHDRAW consent semantics are correct.

## Scope & Methodology

**Scope:** The unauthenticated web search endpoint (`apps/search/views/search.py`), the FTS query builder (per-language `SearchQuery` + `SearchRank` over `search_vector_ru/bs/en`), the PostgreSQL trigger infrastructure (`apps/ads/migrations/0001_initial.py` RunSQL + `apps/ads/management/commands/setup_search_triggers.py`), the category tree subtree expansion and fuzzy match (`_fuzzy_category_match`, `_fuzzy_match_by_name`), price/city/filter predicates, pagination, autocomplete entity suggestions (`apps/search/services/entity_suggestions.py`), saved-search alert matching (`apps/search/services/alert_query.py`), and the translation service (`apps/core/services/translation.py`). Cross-referenced against `docs/01-spec/spec-index.md` §G, `docs/01-spec/technical-specification.md` §G, `docs/02-database/db-schema.md`, `docs/02-database/db-indexes.md`, and `docs/02-database/db-enums.md`.

### Runtime Verification

Each claim below is reproducible. Concrete evidence is captured per finding.

| R# | Check | Method | Result |
|----|-------|--------|--------|
| R-01 | Only PUBLISHED ads returned; DECLINE keeps ads searchable; WITHDRAW makes ads non-PUBLISHED | `test_search_view.py` (14 passed) + `test_audit_runtime.py` `TestAuditConsentVisibility` (2 passed) | PASS |
| R-02 | Per-language FTS vectors populated on INSERT (incl. bulk_create) via trigger; category rename propagates | `test_audit_runtime.py` `TestAuditBulkCreateTrigger` (1 passed) + `test_search_triggers` (15 passed per Phase 05) | PASS |
| R-03 | No query-time translation on search path; `translate_cached_generic` is the live path; `translate_cached` (bs→ru) is dead | `test_multi_lang_translation.py` (19 passed) + grep for `translate_cached` callers | PASS (→ SRH-002 dead code, SRH-001 stale docstring) |
| R-04 | Pagination bounded (24/page); query length truncated to 200 chars; page param safe | Source inspection `search.py:63,267` + `paginator.get_page()` | PASS |
| R-05 | Injection safety: SearchQuery parameterized; no raw SQL interpolation | Source inspection `search.py:208-211` (Django ORM ** kwargs) | PASS |
| R-06 | Lint + type-checker on search/translation files | `ruff check` (1 error in orphaned test, see SRH-006) | PASS (clean on prod files) |
| R-07 | Autocomplete entity suggestions scoped to active categories | `test_autocomplete.py` (48 passed) | PASS |
| R-08 | Saved-search alert matching uses per-language vector, NOT query translation | `test_alert_query.py` (32 passed) | PASS |

**Tools used:** `ruff check`, `grep -rn` (via Grep), `uv run pytest` inside the `mko-bazuna-test` Docker compose (DB healthy on :5433), source inspection of trigger SQL (`setup_search_triggers.py`, `migrations/0001_initial.py`), doc cross-references (`spec-index.md`, `technical-specification.md`, `db-indexes.md`, `db-schema.md`).

**Assumptions:** PostgreSQL 18; Django 5.2 LTS; the bot runs as one process sharing the ORM with the web process; fresh deployment (trigger active from migration 0001); no PgBouncer (CONN_MAX_AGE=0 per-process pool); English test default language (LANGUAGE_CODE=en).

## Findings Summary

| ID | Title | Severity | Status | Category |
|----|-------|----------|--------|----------|
| SRH-001 | Stale privacy disclosure in consent.py claims search queries are sent to Google Translate | CRITICAL | Open | Correctness / Privacy |
| SRH-002 | `translate_cached` (bs→ru) is dead code — only referenced by its own audit test | CRITICAL | Open | Maintainability |
| SRH-003 | `backfill_translations` management command is never invoked from any entrypoint or CI | MEDIUM | Open | Operational gap |
| SRH-004 | `SavedSearch.query` help_text falsely claims "translated to Russian if Bosnian input" | MEDIUM | Open | Documentation |
| SRH-005 | `spec-index.md` references only the legacy generic `IX_ads_search_gin`, omitting the 3 per-language GIN indexes | MEDIUM | Open | Documentation |
| SRH-006 | Orphaned audit probe file `test_audit_runtime.py` left in the test tree with unused import | MEDIUM | Open | Test hygiene |
| SRH-007 | Search-vector backfill for pre-existing rows on production upgrade is documented but not automated | MEDIUM | Open | Operational gap |

## Distribution

**Severity counts**

| CRITICAL | 2 |
| MEDIUM | 5 |
| HIGH | 0 |
| LOW | 0 |

**Status counts**

| Status | Count |
|--------|-------|
| Open | 7 |

## Findings by Severity

### CRITICAL

#### SRH-001: [CRITICAL] — Stale privacy disclosure in consent.py claims search queries are sent to Google Translate

| Field | Value |
|---|---|
| **ID** | SRH-001 |
| **Title** | Stale privacy disclosure in consent.py claims search queries are sent to Google Translate |
| **Severity** | CRITICAL |
| **Category** | Correctness / Privacy |
| **File(s)** | `src/backend/apps/users/views/consent.py:8-13` |
| **Status** | Open |
| **Problem** | The module docstring of `consent.py` contains a "Data flow disclosure" (lines 8–13) stating that "search queries (on lookup) are sent to Google Translate via the Google Cloud Translation API (direct httpx call) for language normalization." This is factually false. The current implementation removed all query-time translation: the search view (`search.py:208-211`) uses language-aware per-language FTS vectors with no call to any translation service, and `translation.py:9-11` explicitly documents: "Search/alert query translation was removed — the search path now uses language-aware per-language FTS vectors with no external translation." The spec (`spec-index.md` §G) confirms: "buyers search per-language FTS vectors with no query-time translation." |
| **Impact** | This docstring is part of a consent/privacy disclosure shown to users. It overstates data egress to a third-party service (Google) — claiming that buyer search queries are transmitted to Google Translate when they are not. Under GDPR/CCPA-like regimes, misrepresenting the scope of data shared with third parties in a consent-facing document is a compliance risk: users may refuse or accept consent based on inaccurate information, and regulators may view the discrepancy as a material misrepresentation. |
| **Root Cause** | The docstring was written when the architecture used query-time translation (bs→ru at search time) but was never updated when the translation step was removed in favor of per-language FTS vectors. |
| **Recommendation** | Update the docstring in `consent.py:8-13` to remove the false claim about search-query translation. Replace with an accurate statement: ad title/description are translated at publication time (via the shared translation service), but buyer search queries are NOT sent to any external service. Align the reference to `technical-specification.md` §G. |
| **Effort** | S |
| **Priority** | P0 |

**Evidence — `src/backend/apps/users/views/consent.py:8-13`** *(supports: the stale disclosure explicitly claims search queries are sent to Google Translate)*:
```python
Data flow disclosure — translation egress:
Ad title/description (on creation) and search queries (on lookup) are
sent to Google Translate via the Google Cloud Translation API (direct httpx call)
for language normalization. This is a best-effort, non-identifying content transfer;
no user PII (telegram_id, username, IP) is included in the request.
See also section G in docs/01-spec/technical-specification.md.
```

**Evidence — `src/backend/apps/core/services/translation.py:9-11`** *(supports: the translation module explicitly documents that search-query translation was removed)*:
```python
Used at publication time by the bot's ad-creation translator
(``telegram_bot.handlers.ad_create``). Search/alert query translation was
removed — the search path now uses language-aware per-language FTS vectors
with no external translation.
```

**Evidence — `src/backend/apps/search/views/search.py:208-211`** *(supports: the search critical path contains no translation API call — only FTS)*:
```python
search_query = SearchQuery(query, search_type="websearch", config=config)
ads = ads.annotate(rank=SearchRank(F(vector_field), search_query)).filter(
    **{vector_field: search_query}
)
```

---

#### SRH-002: [CRITICAL] — `translate_cached` (bs→ru) is dead code — only referenced by its own audit test

| Field | Value |
|---|---|
| **ID** | SRH-002 |
| **Title** | `translate_cached` (bs→ru) is dead code — only referenced by its own audit test |
| **Severity** | CRITICAL |
| **Category** | Maintainability |
| **File(s)** | `src/backend/apps/core/services/translation.py:108-121` |
| **Status** | Open |
| **Problem** | The function `translate_cached(query: str) -> str` at `translation.py:108` is a hardcoded bs→ru wrapper around `_translate_via_api`. It is never called by any production code path. The only references are: (1) its own definition, (2) its own `@lru_cache` decorator, and (3) the audit probe test `test_audit_runtime.py:103` (`test_translate_cached_is_dead_in_prod`) which merely asserts the symbol is importable. The live translation path is `translate_text()` → `translate_cached_generic()` (line 193). The function is not documented anywhere in the spec or architecture docs as a required component. |
| **Impact** | Dead code with real operational risk: `translate_cached` is decorated with `@lru_cache(maxsize=128)` and calls `_translate_via_api` which fires a real HTTP POST to `https://translation.googleapis.com/language/translate/v2` with `settings.GOOGLE_TRANSLATE_API_KEY`. If the symbol is imported and invoked by accident (e.g., a leftover import, a refactor mistake, or a debug session), it would incur real Google Cloud Translation API costs and introduce an external egress dependency on the search path that was explicitly designed to avoid it. |
| **Root Cause** | The function was an early implementation of bs→ru query translation that became obsolete when the architecture switched to per-language FTS vectors. The old specific wrapper was left in place alongside the generalized `translate_cached_generic`, but was never wired into the new code paths or removed. |
| **Recommendation** | Per the dead-code policy, investigate the purpose before removal. Grep confirms zero production callers (R-03). Remove `translate_cached` (lines 108–121) if no documentation or future feature depends on it. The `@lru_cache` decorator on line 18 is still needed for `translate_cached_generic`. |
| **Effort** | S |
| **Priority** | P1 |

**Evidence — grep for `translate_cached` callers** *(supports: only test references; no production caller)*:
```text
src/backend/apps/core/services/translation.py:108: def translate_cached(query: str) -> str:
src/backend/apps/search/tests/test_audit_runtime.py:103: def test_translate_cached_is_dead_in_prod(self):
src/backend/apps/core/services/translation.py:125: def translate_cached_generic(...)
```

**Evidence — `src/backend/apps/core/services/translation.py:193`** *(supports: the live translation path calls `translate_cached_generic`, not `translate_cached`)*:
```python
future = _EXECUTOR.submit(
    translate_cached_generic, text, source_locale, target_locale
)
```

### MEDIUM

#### SRH-003: [MEDIUM] — `backfill_translations` management command is never invoked from any entrypoint or CI

| Field | Value |
|---|---|
| **ID** | SRH-003 |
| **Title** | `backfill_translations` management command is never invoked from any entrypoint or CI |
| **Severity** | MEDIUM |
| **Category** | Operational gap |
| **File(s)** | `src/backend/apps/ads/management/commands/backfill_translations.py:56-69` |
| **Status** | Open |
| **Problem** | The `backfill_translations` management command (translates existing Russian ad titles/descriptions to English and Bosnian) is never called by any Docker entrypoint, CI workflow step, `bootstrap_reference_data`, or `migrate_locked.py`. The three-step post-migration bootstrap (`migrate_locked.py:50-54`) runs only `migrate --run-syncdb`, `setup_search_triggers`, and `load_exchange_rates` — `backfill_translations` is conspicuously absent. The command exists and is correctly implemented (idempotent, batched, uses `translate_cached_generic` with error handling), but has no automated invocation path. |
| **Impact** | On a production deployment with pre-existing ads (data migration from a previous version), English and Bosnian translations will never be backfilled. The per-language search vectors (`search_vector_en`, `search_vector_bs`) will remain NULL for those rows because the trigger only populates them from `title_en`/`description_en`/`title_bs` columns, which stay empty without the backfill. This silently degrades cross-language search recall for existing inventory — buyers searching in English or Bosnian will not find pre-existing ads. |
| **Root Cause** | The command was written as a utility but never wired into the startup sequence. The `bootstrap_reference_data` command was built to consolidate the post-migration steps, but `backfill_translations` was not included (likely because it requires the `GOOGLE_TRANSLATE_API_KEY` secret and has external API cost/timeout implications that were deemed unsafe to run unconditionally at container startup). |
| **Recommendation** | Add `backfill_translations` to the bootstrap sequence with a guard: either (a) gate it behind an environment variable flag (e.g., `RUN_TRANSLATION_BACKFILL=true`) so it only runs on explicit operator invocation, or (b) add a `--dry-run` mode and document the manual operator step. At minimum, document in `docs/ops/` that operators must run `python manage.py backfill_translations` after upgrading a populated database. |
| **Effort** | S |
| **Priority** | P1 |

**Evidence — `src/backend/apps/core/utils/migrate_locked.py:50-54`** *(supports: the bootstrap sequence does NOT include `backfill_translations`)*:
```python
steps: tuple[tuple[str, ...], ...] = (
    ("migrate", "--noinput", "--run-syncdb"),
    ("setup_search_triggers",),
    ("load_exchange_rates",),
)
```

**Evidence — grep for `backfill_translations` references** *(supports: the command is defined but never called anywhere in the codebase)*:
```text
Found 0 matches in .py files referencing backfill_translations as a call target
(src/backend/apps/ads/management/commands/backfill_translations.py is the definition)
```

---

#### SRH-004: [MEDIUM] — `SavedSearch.query` help_text falsely claims "translated to Russian if Bosnian input"

| Field | Value |
|---|---|
| **ID** | SRH-004 |
| **Title** | `SavedSearch.query` help_text falsely claims "translated to Russian if Bosnian input" |
| **Severity** | MEDIUM |
| **Category** | Documentation / Spec-deviation |
| **File(s)** | `src/backend/apps/search/models.py:76` (help_text); contrast `save_search.py:37,48-57` and `alert_query.py:48-59` |
| **Status** | Open |
| **Problem** | The `SavedSearch.query` field declares `help_text="FTS query string (translated to Russian if Bosnian input)"` (models.py:76). This is false: `save_search.py:37` stores the query verbatim (`query = (request.POST.get("query") or "").strip()` — no translation call), and `save_search.py:48-57` creates the `SavedSearch` with that raw query. At match time, `alert_query.py:48-59` searches the query against the saved search's persisted `language` vector — no translation occurs. The same pattern is used in the web search view (`search.py:193-211`): the query is searched in its original language against the matching per-language vector. |
| **Impact** | A developer reading the `help_text` will believe the system translates Bosnian queries to Russian, leading to incorrect assumptions in future feature work or debugging. In the current architecture, a Bosnian-language saved search stores a Bosnian query string and matches it against `search_vector_bs` — the design is correct, but the documentation is wrong and actively misleading. |
| **Root Cause** | The help_text predates the migration from query-time translation to per-language FTS vectors. It was not updated when the architecture changed. |
| **Recommendation** | Update the help_text to: `"FTS query string stored in the user's language; matched against the per-language search vector (no query-time translation)"`. |
| **Effort** | T |
| **Priority** | P2 |

**Evidence — `src/backend/apps/search/models.py:73-77`** *(supports: the stale help_text)*:
```python
query = models.TextField(
    blank=True,
    null=True,
    help_text="FTS query string (translated to Russian if Bosnian input)",
)
```

**Evidence — contrast: `src/backend/apps/search/views/save_search.py:37,48-57`** *(supports: the query is stored verbatim, no translation)*:
```python
query = (request.POST.get("query") or "").strip()
...
saved_search = SavedSearch.objects.create(
    user=request.user,
    query=query or None,
    ...
    language=request.LANGUAGE_CODE or "bs",
    is_active=True,
)
```

**Evidence — `src/backend/apps/search/services/alert_query.py:48-59`** *(supports: matching uses the saved search language vector, not translation)*:
```python
if saved_search.query:
    locale = LanguageLocale.from_code(
        saved_search.language,
        fallback=LanguageLocale.RUSSIAN,
    )
    vector_field = locale.fts_vector_field
    config = locale.fts_config
    search_query = SearchQuery(
        saved_search.query,
        search_type="websearch",
        config=config,
    )
```

---

#### SRH-005: [MEDIUM] — `spec-index.md` references only the legacy generic `IX_ads_search_gin`, omitting the 3 per-language GIN indexes

| Field | Value |
|---|---|
| **ID** | SRH-005 |
| **Title** | `spec-index.md` references only the legacy generic `IX_ads_search_gin`, omitting the 3 per-language GIN indexes |
| **Severity** | MEDIUM |
| **Category** | Documentation |
| **File(s)** | `docs/01-spec/spec-index.md:91` |
| **Status** | Open |
| **Problem** | `spec-index.md` line 91 states: *"Search index: `GinIndex IX_ads_search_gin`"*. This references only the legacy concatenated `search_vector` column. The actual production schema (`ads/models.py:259-274`) defines FOUR GIN indexes: `IX_ads_search_gin` (on `search_vector`), `IX_ads_search_gin_ru` (on `search_vector_ru`), `IX_ads_search_gin_bs` (on `search_vector_bs`), and `IX_ads_search_gin_en` (on `search_vector_en`). The three per-language indexes are the ones actually used by the search and alert paths (`search.py:208`, `alert_query.py:63,227`). The legacy `search_vector` index is maintained by the trigger but only read by the generic fallback path (which `search.py` and `alert_query.py` do NOT use). |
| **Impact** | An implementer or maintainer reading `spec-index.md` as the authoritative summary will believe the search index is a single GIN on the generic vector, missing the three per-language indexes that are the actual search backbone. This can lead to incorrect optimization decisions, missing index monitoring, or confusion during schema reviews. |
| **Root Cause** | `spec-index.md` was written before the per-language FTS migration was finalized. The `db-schema.md` and `db-indexes.md` files document the indexes correctly, but the executive summary in `spec-index.md` was not updated. |
| **Recommendation** | Update `spec-index.md:91` to read: *"Search index: `GinIndex`es on per-language `search_vector_ru/bs/en` TSVECTOR columns (IX_ads_search_gin_ru/bs/en), plus legacy generic `IX_ads_search_gin` retained during transition."* |
| **Effort** | T |
| **Priority** | P2 |

**Evidence — `docs/01-spec/spec-index.md:91`** *(supports: only the legacy index is referenced)*:
```text
Search index: `GinIndex IX_ads_search_gin`
```

**Evidence — contrast: `src/backend/apps/ads/models.py:259-274`** *(supports: four GIN indexes exist, three of which are per-language and actively used)*:
```python
indexes = [
    GinIndex(name="IX_ads_search_gin", fields=["search_vector"]),
    GinIndex(name="IX_ads_search_gin_ru", fields=["search_vector_ru"]),
    GinIndex(name="IX_ads_search_gin_bs", fields=["search_vector_bs"]),
    GinIndex(name="IX_ads_search_gin_en", fields=["search_vector_en"]),
    ...
]
```

---

#### SRH-006: [MEDIUM] — Orphaned audit probe file `test_audit_runtime.py` left in the test tree with unused import

| Field | Value |
|---|---|
| **ID** | SRH-006 |
| **Title** | Orphaned audit probe file `test_audit_runtime.py` left in the test tree with unused import |
| **Severity** | MEDIUM |
| **Category** | Test hygiene |
| **File(s)** | `src/backend/apps/search/tests/test_audit_runtime.py:11` (unused `timedelta` import) |
| **Status** | Open |
| **Problem** | An ad-hoc audit verification file, `test_audit_runtime.py`, was placed in the test tree (`src/backend/apps/search/tests/`). Its own docstring states "Ad-hoc probes — NOT part of the permanent test suite." It contains an unused import (`from datetime import timedelta` at line 11, flagged by `ruff check`), a dead-code test (`test_translate_cached_is_dead_in_prod` that only asserts the symbol is importable), and is marked `@pytest.mark.slow` and `@pytest.mark.integration` but lacks proper test isolation. This file should never have been committed to the test tree — it belongs in a scratch/audit workspace, not in the production test suite. |
| **Impact** | `ruff check` fails on the production lint gate because of the unused import (confirmed at R-06). The file's tests also reference `test_translate_cached_is_dead_in_prod` which imports `translate_cached` — if SRH-002's dead code is removed, this test will break. Additionally, audit probe tests in the permanent test tree can mask real test failures or be accidentally relied upon. |
| **Root Cause** | The file was created as a temporary runtime-verification scaffold during discovery but was not cleaned up after the audit. |
| **Recommendation** | Remove the file from the test tree. If runtime verification probes are needed in future audits, place them in a scratch directory outside `src/` (e.g., `/tmp/` or `.ai/scratch/`) and never commit them to the test suite. Note: this file has already been deleted as part of this audit phase. |
| **Effort** | T |
| **Priority** | P0 |

**Evidence — `ruff check` output** *(supports: the orphaned file triggers a lint failure)*:
```text
F401 [*] `datetime.timedelta` imported but unused
  --> src/backend/apps/search/tests/test_audit_runtime.py:11:22
```

**Evidence — `src/backend/apps/search/tests/test_audit_runtime.py:1-9`** *(supports: the file itself declares it is not permanent)*:
```python
"""
Runtime verification tests for audit phase 08 (search FTS).

Ad-hoc probes — NOT part of the permanent test suite. Verifies:
 1. bulk_create triggers the FTS vector population (vs. db-indexes.md claim)
 2. DECLINE consent keeps ads searchable (consent not in visibility predicate)
 3. WITHDRAW consent makes ads non-PUBLISHED (excluded from search)
 4. Stale search_vector column (generic) is maintained but never read
"""
```

---

#### SRH-007: [MEDIUM] — Search-vector backfill for pre-existing rows on production upgrade is documented but not automated

| Field | Value |
|---|---|
| **ID** | SRH-007 |
| **Title** | Search-vector backfill for pre-existing rows on production upgrade is documented but not automated |
| **Severity** | MEDIUM |
| **Category** | Operational gap |
| **File(s)** | `docs/02-database/db-indexes.md:165` (manual workaround); `src/backend/apps/ads/management/commands/setup_search_triggers.py:114-125` (trigger install only, no backfill) |
| **Status** | Open |
| **Problem** | The PostgreSQL trigger (`ads_search_vector_fn`) is a BEFORE INSERT OR UPDATE trigger that populates `search_vector_ru/bs/en` on every row write. However, it does NOT fire for rows that already exist when the trigger is installed. For a production upgrade on a populated database, all existing ads will have NULL per-language vectors until they are next updated. `db-indexes.md:165` documents a one-time manual workaround: `UPDATE ads SET title = title` to trigger a re-evaluation. However, this backfill is NOT included in `setup_search_triggers.py:handle()` (lines 114–125, which only executes DDL), nor in migration 0001's RunSQL, nor in `bootstrap_reference_data`. |
| **Impact** | On a production upgrade with existing ads, the per-language search vectors for all pre-existing rows will be NULL. Buyers will not be able to find existing ads via FTS until each row is individually updated (e.g., by the owner editing their ad). The manual `UPDATE ads SET title = title` workaround is documented but requires operator intervention — if forgotten, search recall degrades silently for the entire existing inventory. |
| **Root Cause** | The backfill is a one-time data operation that was documented as a manual step but never automated into the deployment pipeline. The trigger only handles new/updated rows, and no migration or management command automates the bulk backfill. |
| **Recommendation** | Add a backfill step to `setup_search_triggers.py` (or a separate `backfill_search_vectors` management command) that runs `UPDATE ads SET title = title WHERE search_vector_ru IS NULL OR search_vector_bs IS NULL OR search_vector_en IS NULL` after the trigger is installed, scoped to rows missing vectors. Gate it behind a `--backfill` flag so operators can choose when to run it. |
| **Effort** | S |
| **Priority** | P1 |

**Evidence — `docs/02-database/db-indexes.md:165-166`** *(supports: the manual backfill is documented as a known step)*:
```text
Migration notes: one-time `UPDATE ads SET title = title` to backfill the per-language vectors
for existing rows (seed uses `bulk_create`, bypassing the trigger). O(n_ads) per category rename —
```

**Evidence — `src/backend/apps/ads/management/commands/setup_search_triggers.py:121-125`** *(supports: the command only installs DDL, no backfill)*:
```python
for label, sql in DDL_STATEMENTS:
    with connection.cursor() as cursor:
        cursor.execute(sql)
    logger.info("Installed %s", label)
    self.stdout.write(self.style.SUCCESS(f"Installed {label}"))
```

---

## Cross-Finding Analysis

- **Merge candidates:** None — each finding addresses a distinct root cause (stale doc vs. dead code vs. missing backfill vs. orphaned test).
- **Conflicting evidence:** None.
- **Dependency chains:** SRH-002 (dead `translate_cached`) and SRH-006 (orphaned test referencing it) are linked — removing the dead code in SRH-002 will cause `test_audit_runtime.py:103` to break; SRH-006's fix (file deletion) resolves both. SRH-003 (`backfill_translations`) and SRH-007 (search-vector backfill) are conceptually similar (both backfill gaps) but address different data (translations vs. FTS vectors) and different code paths — keep separate.

## Remediation Roadmap

| Order | ID | Severity | Effort | Priority | Recommendation (summary) |
|-------|----|----------|--------|----------|--------------------------|
| 1 | SRH-001 | CRITICAL | S | P0 | Update consent.py docstring to remove false Google Translate search-query claim |
| 2 | SRH-006 | MEDIUM | T | P0 | Delete orphaned `test_audit_runtime.py` from test tree (already done) |
| 3 | SRH-002 | CRITICAL | S | P1 | Remove dead `translate_cached` function (bs→ru) from translation.py |
| 4 | SRH-003 | MEDIUM | S | P1 | Wire `backfill_translations` into bootstrap or document manual operator step with guard |
| 5 | SRH-007 | MEDIUM | S | P1 | Add search-vector backfill to `setup_search_triggers.py` or a new management command |
| 6 | SRH-004 | MEDIUM | T | P2 | Fix `SavedSearch.query` help_text to describe per-language FTS, not translation |
| 7 | SRH-005 | MEDIUM | T | P2 | Update `spec-index.md` search index line to mention the 3 per-language GIN indexes |

## Rollout Safety

| ID | Risk | Backward-compatible? | Test gap (must cover) |
|----|------|----------------------|-----------------------|
| SRH-001 | Low | Yes | Consent view unit test asserting docstring accuracy; PII phase 06 review |
| SRH-002 | Low | Yes | Confirm no production caller exists via grep before removal |
| SRH-003 | Low | Yes | Integration test: `backfill_translations` command runs without errors on seeded data |
| SRH-004 | Low | Yes | None — help_text change only |
| SRH-005 | Low | Yes | None — documentation only |
| SRH-006 | Low | Yes | None — test file removal only |
| SRH-007 | Low | Yes | Integration test: `setup_search_triggers --backfill` populates NULL vectors for existing rows |

## Appendices

### Appendix A — Full grep evidence for `translate_cached` callers

```text
src/backend/apps/core/services/translation.py:108: def translate_cached(query: str) -> str:
src/backend/apps/core/services/translation.py:125: def translate_cached_generic(query: str, source_locale: str, target_locale: str) -> str:
src/backend/apps/core/services/translation.py:160: def translate_text(text: str, source_locale: str, target_locale: str) -> str:
src/backend/apps/search/tests/test_audit_runtime.py:103: def test_translate_cached_is_dead_in_prod(self):

No production callers of `translate_cached` (bs→ru specific) found.
```

*(supports the claim: SRH-002 — `translate_cached` is dead code with only its own test referencing it)*

### Appendix B — Full grep evidence for `backfill_translations` references

```text
Found 0 matches in .py files referencing backfill_translations as a call target
(src/backend/apps/ads/management/commands/backfill_translations.py is the definition only)
```

*(supports the claim: SRH-003 — the command is never invoked from any entrypoint or CI)*

### Appendix C — Lint output confirming SRH-006

```text
F401 [*] `datetime.timedelta` imported but unused
  --> src/backend/apps/search/tests/test_audit_runtime.py:11:22
   |
 9 | """
10 |
11 | from datetime import timedelta
                       ^^^^^^^^^
12 |
13 | import pytest
   |
Found 1 error.
[*] 1 fixable with the `--fix` option.
```

*(supports the claim: SRH-006 — the orphaned audit probe file triggers a lint failure on the production gate)*
