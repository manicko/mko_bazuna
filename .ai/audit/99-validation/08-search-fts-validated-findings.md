---
phase: "08"
phase_name: "Search & Full-Text Search (FTS)"
date: "2026-09-12"
auditor: "Executor (subagent)"
validator: "Kilo (validator agent)"
mode: "problems-only"
report_status: "validated"
id_prefix: "SRH"
severity_taxonomy: ".kilo/commands/audit/phases/08-audit-search-fts.md#severity-taxonomy"
---

# Audit Findings — Search & Full-Text Search (FTS) — Validated Report

> **Self-contained validated report.** All decisions are applied inline to the copied findings. Evidence has been re-verified against the current codebase as of 2026-09-12.

## Executive Summary

Seven findings were submitted for validation. **Four are VALIDATED**, **one is REJECTED**, and **two are VALIDATED with reclassification**. The runtime verification claims (R-01 through R-08) were spot-checked: most hold, but **R-06 is partially stale** — the claimed `ruff check` lint failure on `test_audit_runtime.py` no longer reproduces because that file has already been deleted.

**Corrected severity distribution:**

| CRITICAL | 2 (reclassified ↓) |
| MEDIUM | 5 (reclassified ↓) |

| Reclassified to DOC-UPDATE | 3 (SRH-001, SRH-004, SRH-005) |
| Reclassified to BEST-PRACTICE | 2 (SRH-002, SRH-003, SRH-007 — already best-practice, confirmed) |
| Rejected | 1 (SRH-006 — stale, file already deleted) |
| Validated unchanged | 0 |

**Key validation findings:**
- **SRH-002's evidence is stale**: it cites `test_audit_runtime.py:103` as the only test reference, but that file does not exist. The actual references to `translate_cached` are in `test_multi_lang_translation.py:21,53` (import + `.cache_clear()` call in a test fixture). This hidden dependency was **not disclosed** in the original findings.
- **SRH-006 is stale**: the orphaned `test_audit_runtime.py` file has already been deleted. `ruff check src/backend/` passes cleanly.
- **SRH-001, SRH-004, SRH-005** all stem from the same architectural shift (query-time translation → per-language FTS vectors) leaving documentation stale. They address distinct files and are kept separate.

## Scope & Methodology

Same as the original phase. Each finding was re-verified against:
- Source code inspection (actual file contents, not just cited line numbers)
- `grep` for all references to `translate_cached`, `backfill_translations`, `bootstrap_reference_data`
- `ruff check` on the search tests directory and the entire backend
- All Docker entrypoint scripts (`entrypoint.sh`, `entrypoint-test.sh`, `entrypoint-scheduler.sh`, `entrypoint-catalog.sh`, `entrypoint-seed.sh`, `entrypoint-create-admin.sh`)
- CI workflow files (`ci.yml`, `ci-nightly.yml`)
- `docker-compose.yml`
- Spec and documentation cross-references (`spec-index.md`, `technical-specification.md`, `db-indexes.md`, `db-schema.md`, `migration-workflow.md`, `i18n-translation-egress.md`)

## Findings Summary

| ID | Title | Severity | Status | Category | Action |
|----|-------|----------|--------|----------|--------|
| SRH-001 | Stale privacy disclosure in consent.py claims search queries are sent to Google Translate | CRITICAL | Validated | Privacy | Reclassified → DOC-UPDATE |
| SRH-002 | `translate_cached` (bs→ru) is dead code | CRITICAL | Validated | Maintainability | Reclassified → BEST-PRACTICE (evidence corrected) |
| SRH-003 | `backfill_translations` management command is never invoked from any entrypoint or CI | MEDIUM | Validated | Operational gap | Validated → BEST-PRACTICE |
| SRH-004 | `SavedSearch.query` help_text falsely claims "translated to Russian if Bosnian input" | MEDIUM | Validated | Documentation | Reclassified → DOC-UPDATE |
| SRH-005 | `spec-index.md` references only the legacy generic `IX_ads_search_gin`, omitting the 3 per-language GIN indexes | MEDIUM | Validated | Documentation | Reclassified → DOC-UPDATE |
| SRH-006 | Orphaned audit probe file `test_audit_runtime.py` left in the test tree with unused import | MEDIUM | Validated | Test hygiene | Rejected (stale — file already deleted) |
| SRH-007 | Search-vector backfill for pre-existing rows on production upgrade is documented but not automated | MEDIUM | Validated | Operational gap | Validated → BEST-PRACTICE |

## Findings by Severity

### CRITICAL

#### SRH-001: ~~[CRITICAL] Stale privacy disclosure in consent.py claims search queries are sent to Google Translate~~ → [DOC-UPDATE] Reclassified

> **Validation Note:**
> - **Action:** reclassified
> - **Detail:** The code is correct — the search path (`search.py:208-211`) uses per-language FTS vectors with no translation call, as confirmed by `translation.py:9-11` ("Search/alert query translation was removed") and the spec (`spec-index.md` §G:73, `technical-specification.md` §G:119,121). The consent.py docstring (lines 8–13) is the stale artifact: it claims "search queries (on lookup) are sent to Google Translate." Per the type-specific rule ("If code is better than docs → reclassify as DOC-UPDATE"), this is a documentation defect, not a spec deviation. The code already implements the correct behavior (publication-time-only egress for ad title/description).
> - **Evidence corrected:** The original evidence is accurate. `consent.py:8-13` matches exactly.
> - **See also:** SRH-004 and SRH-005 share the same root cause (stale docs from the translation→FTS architecture shift).

| Field | Value |
|---|---|
| **ID** | SRH-001 |
| **Title** | Stale privacy disclosure in consent.py claims search queries are sent to Google Translate |
| **Severity** | CRITICAL → (downgraded with reclassification to DOC-UPDATE, but privacy risk noted) |
| **Category** | Correctness / Privacy |
| **File(s)** | `src/backend/apps/users/views/consent.py:8-13` |
| **Status** | Validated → Reclassified |
| **Problem** | The module docstring of `consent.py` (lines 8–13) states that "search queries (on lookup) are sent to Google Translate via the Google Cloud Translation API (direct httpx call)." The current implementation removed all query-time translation. The search view (`search.py:208-211`, lines 189–211) uses `SearchQuery` + `SearchRank` over per-language FTS vector fields (`locale.fts_vector_field`) with no call to any translation service. `translation.py:9-11` explicitly documents: "Search/alert query translation was removed — the search path now uses language-aware per-language FTS vectors with no external translation." |
| **Impact** | This docstring is part of a consent/privacy disclosure. It overstates data egress to a third-party service (Google) — claiming that buyer search queries are transmitted to Google Translate when they are not. Under GDPR/CCPA-like regimes, misrepresenting the scope of data shared with third parties in a consent-facing document is a compliance risk. |
| **Root Cause** | The docstring was written when the architecture used query-time translation (bs→ru at search time) but was never updated when the translation step was removed in favor of per-language FTS vectors. |
| **Recommendation** | Update the docstring in `consent.py:8-13` to remove the false claim about search-query translation. Replace with an accurate statement: ad title/description are translated at publication time (via the shared translation service), but buyer search queries are NOT sent to any external service. Align the reference to `technical-specification.md` §G. |
| **Effort** | S |
| **Priority** | P0 |

### CRITICAL

#### SRH-002: `translate_cached` (bs→ru) is dead code → [BEST-PRACTICE] Validated (evidence corrected, hidden dependency disclosed)

> **Validation Note:**
> - **Action:** reclassified (speculated type → confirmed BEST-PRACTICE)
> - **Detail:** The core finding is VALID — `grep` for `translate_cached` (word-boundary) confirms zero production callers. The only references are the definition (`translation.py:108`) and two references in `test_multi_lang_translation.py` (import at line 21, `.cache_clear()` call at line 53). However, the original evidence is **STALE**: it cites `test_audit_runtime.py:103` as the only test reference, but that file does not exist (see SRH-006 rejection). The actual test references are in `src/telegram_bot/tests/test_multi_lang_translation.py`. Additionally, a **hidden dependency** was not disclosed: removing `translate_cached` (lines 107–121) would break `test_multi_lang_translation.py:21` (ImportError) and `:53` (AttributeError on `.cache_clear()`), because the test fixture calls `translate_cached.cache_clear()` to reset LRU state between tests. This dependency must be resolved (remove the import + cache_clear call from the test fixture) before or alongside the dead-code removal.
> - **Dead-code policy cross-reference:** Checked spec documents — `translate_cached` is not referenced in `spec-index.md`, `technical-specification.md`, or `db-schema.md` as a required component. It IS mentioned in `docs/96-researches/i18n-translation-egress.md:97` as a cache element, but that research doc describes the lru_cache table, not a required component. The function's own docstring describes it as a "search query" translator, and the module docstring confirms that use was removed. The `@lru_cache(maxsize=128)` decorator on line 107 can be safely removed along with the function.
> - **See also:** SRH-006 (related — the original cross-finding link cited the non-existent `test_audit_runtime.py`; actual dependency is `test_multi_lang_translation.py`).

| Field | Value |
|---|---|
| **ID** | SRH-002 |
| **Title** | `translate_cached` (bs→ru) is dead code — only referenced by its own audit test |
| **Severity** | CRITICAL |
| **Category** | Maintainability |
| **File(s)** | `src/backend/apps/core/services/translation.py:107-121` |
| **Status** | Validated |
| **Problem** | The function `translate_cached(query: str) -> str` at `translation.py:108` is a hardcoded bs→ru wrapper around `_translate_via_api`. It is never called by any production code path. `grep` for `translate_cached` (word boundary) across the entire `src/` tree confirms zero production callers. The only references are: (1) its definition (`translation.py:108`), (2) its `@lru_cache(maxsize=128)` decorator (`translation.py:107`), and (3) `src/telegram_bot/tests/test_multi_lang_translation.py:21` (import) + `:53` (`translate_cached.cache_clear()` call in the `_reset_translation_state` test fixture). The live translation path is `translate_text()` → `translate_cached_generic()` (line 139, called at line 192-193). |
| **Impact** | Dead code with operational risk: `translate_cached` is decorated with `@lru_cache(maxsize=128)` and calls `_translate_via_api` which fires a real HTTP POST to `https://translation.googleapis.com/language/translate/v2` with `settings.GOOGLE_TRANSLATE_API_KEY`. If imported and invoked by accident (e.g., a refactor mistake or debug session), it would incur real Google Cloud Translation API costs and introduce an external egress dependency on the search path that was explicitly designed to avoid it. |
| **Root Cause** | The function was an early implementation of bs→ru query translation that became obsolete when the architecture switched to per-language FTS vectors. The old specific wrapper was left in place alongside the generalized `translate_cached_generic`, but was never wired into the new code paths or removed. |
| **Recommendation** | Remove `translate_cached` (lines 107–121) — the function and its `@lru_cache` decorator. No specification, model, or configuration template references it as a required component. **Critical rollout dependency (NOT in original findings):** the test fixture in `src/telegram_bot/tests/test_multi_lang_translation.py:21,53` imports `translate_cached` and calls `translate_cached.cache_clear()` — this import and cache_clear call must be removed from the test fixture simultaneously to avoid breaking the test suite. |
| **Effort** | S |
| **Priority** | P1 |

### MEDIUM

#### SRH-003: [MEDIUM] `backfill_translations` management command is never invoked from any entrypoint or CI → [BEST-PRACTICE] Validated

| Field | Value |
|---|---|
| **ID** | SRH-003 |
| **Title** | `backfill_translations` management command is never invoked from any entrypoint or CI |
| **Severity** | MEDIUM |
| **Category** | Operational gap |
| **File(s)** | `src/backend/apps/ads/management/commands/backfill_translations.py:56-69` |
| **Status** | Validated |
| **Problem** | The `backfill_translations` management command (translates existing Russian ad titles/descriptions to English and Bosnian) is never called by any Docker entrypoint, CI workflow step, or bootstrap command. The validated verification (entire `src/`, `docker/`, `.github/` tree) confirms: `migrate_locked.py:50-54` (lines 50–54) runs only `migrate --run-syncdb`, `setup_search_triggers`, and `load_exchange_rates` — `backfill_translations` is absent. `bootstrap_reference_data` (at `apps/core/management/commands/bootstrap_reference_data.py`) delegates to `migrate_locked.main()`, so it inherits the same three-step sequence with no backfill step. The `entrypoint-test.sh:25` runs `bootstrap_reference_data || true`. No `.github/workflows/*.yml` references `backfill_translations` — both `ci.yml` (lines 86, 227) and `ci-nightly.yml` (line 65) call only `bootstrap_reference_data`. The `docker-compose.yml:35` calls only `bootstrap_reference_data`. The `entrypoint-scheduler.sh` hourly/daily job list (lines 28–41) does not include it. The command exists and is correctly implemented (idempotent, batched, uses `translate_cached_generic` with error handling), but has no automated invocation path. |
| **Impact** | On a production deployment with pre-existing ads (data migration from a previous version), English and Bosnian translations will never be backfilled. The per-language search vectors (`search_vector_en`, `search_vector_bs`) will remain NULL for those rows because the trigger only populates them from `title_en`/`description_en`/`title_bs` columns, which stay empty without the backfill. This silently degrades cross-language search recall for existing inventory. |
| **Root Cause** | The command was written as a utility but never wired into the startup sequence. The `bootstrap_reference_data` command was built to consolidate the post-migration steps, but `backfill_translations` was not included (likely because it requires the `GOOGLE_TRANSLATE_API_KEY` secret and has external API cost/timeout implications that were deemed unsafe to run unconditionally at container startup). |
| **Recommendation** | Add `backfill_translations` to the bootstrap sequence with a guard: either (a) gate it behind an environment variable flag (e.g., `RUN_TRANSLATION_BACKFILL=true`) so it only runs on explicit operator invocation, or (b) add a `--dry-run` mode and document the manual operator step. At minimum, document in `docs/ops/` that operators must run `python manage.py backfill_translations` after upgrading a populated database. Note: `docs/ops/migration-workflow.md:284,390` already documents this as a manual step — the gap is that it is not in the automated bootstrap chain. |
| **Effort** | S |
| **Priority** | P1 |

### MEDIUM

#### SRH-004: ~~[MEDIUM] SavedSearch.query help_text falsely claims "translated to Russian if Bosnian input"~~ → [DOC-UPDATE] Reclassified

> **Validation Note:**
> - **Action:** reclassified
> - **Detail:** The code is correct — `save_search.py:37` stores the query verbatim (`query = (request.POST.get("query") or "").strip()`, no translation call), and `alert_query.py:48-59` searches the query against the saved search's persisted `language` vector (no translation). The `SavedSearch.query` field's `help_text` at `models.py:76` is the only stale artifact. Per the type-specific rule ("If code is better than docs → reclassify as DOC-UPDATE"), this is a documentation defect. `help_text` is Django's documentation mechanism for model fields, so updating it is a doc-only change with no operational risk.
> - **Evidence corrected:** Original evidence is accurate. `models.py:76` matches exactly.

| Field | Value |
|---|---|
| **ID** | SRH-004 |
| **Title** | `SavedSearch.query` help_text falsely claims "translated to Russian if Bosnian input" |
| **Severity** | MEDIUM |
| **Category** | Documentation / Spec-deviation |
| **File(s)** | `src/backend/apps/search/models.py:76` (help_text); contrast `save_search.py:37,48-57` and `alert_query.py:48-59` |
| **Status** | Validated → Reclassified to DOC-UPDATE |
| **Problem** | The `SavedSearch.query` field declares `help_text="FTS query string (translated to Russian if Bosnian input)"` (models.py:76). This is false: `save_search.py:37` stores the query verbatim (`query = (request.POST.get("query") or "").strip()` — no translation call), and `save_search.py:48-57` creates the `SavedSearch` with that raw query. At match time, `alert_query.py:48-59` searches the query against the saved search's persisted `language` vector — no translation occurs. The web search view (`search.py:189-211`) follows the same pattern: the query is searched in its original language against the matching per-language vector. |
| **Impact** | A developer reading the `help_text` will believe the system translates Bosnian queries to Russian, leading to incorrect assumptions in future feature work or debugging. In the current architecture, a Bosnian-language saved search stores a Bosnian query string and matches it against `search_vector_bs` — the design is correct, but the documentation is wrong and actively misleading. |
| **Root Cause** | The help_text predates the migration from query-time translation to per-language FTS vectors. It was not updated when the architecture changed. |
| **Recommendation** | Update the help_text to: `"FTS query string stored in the user's language; matched against the per-language search vector (no query-time translation)"`. |
| **Effort** | T |
| **Priority** | P2 |

### MEDIUM

#### SRH-005: ~~[MEDIUM] spec-index.md references only the legacy generic IX_ads_search_gin~~ → [DOC-UPDATE] Reclassified

> **Validation Note:**
> - **Action:** reclassified
> - **Detail:** The code is correct — `apps/ads/models.py:259-274` defines FOUR GIN indexes (`IX_ads_search_gin`, `IX_ads_search_gin_ru`, `IX_ads_search_gin_bs`, `IX_ads_search_gin_en`), and `db-indexes.md:46-57` documents all four correctly. The `spec-index.md:91` line "Search index: `GinIndex IX_ads_search_gin`" is the stale artifact — it only references the legacy concatenated vector index. Per the type-specific rule ("If code is better than docs → reclassify as DOC-UPDATE"), this is a documentation defect. Note: `spec-index.md` is internally inconsistent — line 48 states "Search: native PostgreSQL FTS (per-language `search_vector_ru/bs/en` TSVECTOR + GIN)" and line 73 states "buyers search per-language FTS vectors with no query-time translation," but line 91's "Key tables" summary only mentions the legacy index. The fix is to update line 91 to reflect all four indexes.
> - **Evidence corrected:** Original evidence is accurate. `spec-index.md:91` and `ads/models.py:259-274` match exactly.

| Field | Value |
|---|---|
| **ID** | SRH-005 |
| **Title** | `spec-index.md` references only the legacy generic `IX_ads_search_gin`, omitting the 3 per-language GIN indexes |
| **Severity** | MEDIUM |
| **Category** | Documentation |
| **File(s)** | `docs/01-spec/spec-index.md:91` |
| **Status** | Validated → Reclassified to DOC-UPDATE |
| **Problem** | `spec-index.md` line 91 states: *"Search index: `GinIndex IX_ads_search_gin`"*. This references only the legacy concatenated `search_vector` column. The actual production schema (`ads/models.py:259-274`) defines FOUR GIN indexes: `IX_ads_search_gin` (on `search_vector`), `IX_ads_search_gin_ru` (on `search_vector_ru`), `IX_ads_search_gin_bs` (on `search_vector_bs`), and `IX_ads_search_gin_en` (on `search_vector_en`). The three per-language indexes are the ones actually used by the search and alert paths (`search.py:208`, `alert_query.py:63,227`). The legacy `search_vector` index is maintained by the trigger but only read by the generic fallback path (which `search.py` and `alert_query.py` do NOT use). Note: `spec-index.md` line 48 and line 73 already mention the per-language vectors at a conceptual level, but the "Key tables" summary at line 91 is stale. |
| **Impact** | An implementer or maintainer reading `spec-index.md` as the authoritative summary will believe the search index is a single GIN on the generic vector, missing the three per-language indexes that are the actual search backbone. This can lead to incorrect optimization decisions, missing index monitoring, or confusion during schema reviews. |
| **Root Cause** | `spec-index.md` was written before the per-language FTS migration was finalized. The `db-schema.md` and `db-indexes.md` files document the indexes correctly, but the executive summary in `spec-index.md` line 91 was not updated. |
| **Recommendation** | Update `spec-index.md:91` to read: *"Search index: `GinIndex`es on per-language `search_vector_ru/bs/en` TSVECTOR columns (IX_ads_search_gin_ru/bs/en), plus legacy generic `IX_ads_search_gin` retained during transition."* |
| **Effort** | T |
| **Priority** | P2 |

---

#### SRH-006: ~~[MEDIUM] Orphaned audit probe file test_audit_runtime.py left in the test tree with unused import~~ [REJECTED — STALE]

> **Rejection reason:** The file `src/backend/apps/search/tests/test_audit_runtime.py` **does not exist** in the current codebase. Verified by:
> 1. **Glob search** for `**/test_audit_runtime.py` across the entire repo returned no files.
> 2. **`ruff check src/backend/apps/search/tests/test_audit_runtime.py`** returns `E902 Cannot find file` (exit non-zero).
> 3. **`ruff check src/backend/`** (entire backend) returns "All checks passed!" — there is NO lint failure.
> 4. The original finding's own recommendation states: *"Note: this file has already been deleted as part of this audit phase."*
> The finding was valid when written but has since been resolved (the file was deleted). The runtime verification claim R-06 ("ruff check, 1 error in orphaned test, see SRH-006") is **false in the current state**. No action needed.

| Field | Value |
|---|---|
| **ID** | SRH-006 |
| **Title** | ~~Orphaned audit probe file `test_audit_runtime.py` left in the test tree with unused import~~ |
| **Severity** | MEDIUM |
| **Category** | Test hygiene |
| **File(s)** | ~~`src/backend/apps/search/tests/test_audit_runtime.py:11`~~ |
| **Status** | ~~Open~~ → Rejected (stale) |
| **Reason** | File already deleted; ruff passes cleanly. |

> ```text
> $ uv run ruff check src/backend/apps/search/tests/test_audit_runtime.py
> E902 Cannot find file  --> src\backend\apps\search\tests\test_audit_runtime.py:1:1
>
> $ uv run ruff check src/backend/
> All checks passed!
> ```

---

#### SRH-007: [MEDIUM] Search-vector backfill for pre-existing rows on production upgrade is documented but not automated → [BEST-PRACTICE] Validated

| Field | Value |
|---|---|
| **ID** | SRH-007 |
| **Title** | Search-vector backfill for pre-existing rows on production upgrade is documented but not automated |
| **Severity** | MEDIUM |
| **Category** | Operational gap |
| **File(s)** | `docs/02-database/db-indexes.md:165`; `src/backend/apps/ads/management/commands/setup_search_triggers.py:114-125`; `src/backend/apps/ads/migrations/0001_initial.py:705-721` (RunSQL for trigger DDL only) |
| **Status** | Validated |
| **Problem** | The PostgreSQL trigger (`ads_search_vector_fn`, installed at `setup_search_triggers.py:114-125` and `migrations/0001_initial.py:705-721`) is a BEFORE INSERT OR UPDATE trigger that populates `search_vector_ru/bs/en` on every row write. However, it does NOT fire for rows that already exist when the trigger is installed. For a production upgrade on a populated database, all existing ads will have NULL per-language vectors until they are next updated. `db-indexes.md:165-166` documents a one-time manual workaround: `UPDATE ads SET title = title` to trigger a re-evaluation. However, this backfill is NOT included in `setup_search_triggers.py:handle()` (lines 121–125, which only executes DDL via `DDL_STATEMENTS`), nor in migration 0001's RunSQL (lines 705–721, which only creates trigger functions and triggers — no `UPDATE` backfill), nor in `bootstrap_reference_data`. No `backfill_search_vectors` management command exists (confirmed by grep). |
| **Impact** | On a production upgrade with existing ads, the per-language search vectors for all pre-existing rows will be NULL. Buyers will not be able to find existing ads via FTS until each row is individually updated (e.g., by the owner editing their ad). The manual `UPDATE ads SET title = title` workaround is documented but requires operator intervention — if forgotten, search recall degrades silently for the entire existing inventory. |
| **Root Cause** | The backfill is a one-time data operation that was documented as a manual step but never automated into the deployment pipeline. The trigger only handles new/updated rows, and no migration or management command automates the bulk backfill. |
| **Recommendation** | Add a backfill step to `setup_search_triggers.py` (or a separate `backfill_search_vectors` management command) that runs `UPDATE ads SET title = title WHERE search_vector_ru IS NULL OR search_vector_bs IS NULL OR search_vector_en IS NULL` after the trigger is installed, scoped to rows missing vectors. Gate it behind a `--backfill` flag so operators can choose when to run it. |
| **Effort** | S |
| **Priority** | P1 |

---

## Cross-Finding Analysis

### Merge Candidates

**None.** Each finding addresses a distinct file and a distinct root cause:
- SRH-001: consent.py docstring (privacy disclosure)
- SRH-002: translation.py dead function (code maintainability)
- SRH-003: backfill_translations command wiring (translation backfill operational gap)
- SRH-004: SavedSearch.query help_text (model field doc)
- SRH-005: spec-index.md search index line (spec doc)
- SRH-006: (rejected — file already deleted)
- SRH-007: search-vector backfill operational gap (FTS vector backfill)

While SRH-001, SRH-004, and SRH-005 share a common root cause (stale documentation from the query-time-translation → per-language-FTS architectural shift), they address three different files and three different doc surfaces (consent docstring, model help_text, spec summary). Keeping them separate provides clear ownership. They are noted as related but not merged.

### Conflicting Evidence

**None found** across phases. The PII phase (06-pii-consent) findings (PII-001 through PII-003) focus on consent state semantics and do not conflict with the SRH findings. No other audit phase (09–13, 14) has findings files at the time of validation.

### Dependency Chains

**Corrected dependency chain (not in original findings):**

1. **SRH-002 → test_multi_lang_translation.py** (HIDDEN DEPENDENCY — not disclosed in original findings):
   - The original findings incorrectly linked SRH-002 and SRH-006 via `test_audit_runtime.py:103`. Since that file doesn't exist (SRH-006 is stale), the link is broken.
   - The **actual** dependency: removing `translate_cached` from `translation.py` would break `src/telegram_bot/tests/test_multi_lang_translation.py:21` (ImportError on `from apps.core.services.translation import ..., translate_cached, ...`) and `:53` (`translate_cached.cache_clear()` in the `_reset_translation_state` fixture). The test fixture must be updated (remove import + cache_clear call) before or simultaneously with the dead-code removal.
   - **Rollout ordering:** Fix `test_multi_lang_translation.py` first (remove `translate_cached` import and its `.cache_clear()` call from the fixture), then remove `translate_cached` from `translation.py`. Both changes must be atomic in a single commit to avoid a broken test state.

2. **SRH-003 → SRH-007** (NOTED, separate concerns):
   - Both address operational backfill gaps, but for different data: SRH-003 is translation backfill (ru→en/bs columns), SRH-007 is FTS-vector backfill (NULL `search_vector_*` columns). They operate on different commands and different data paths. No implementation dependency exists — keep separate as the original findings correctly noted.

3. **SRH-001, SRH-004, SRH-005** (DOCUMENTATION CONVERGENCE):
   - All three are doc-only fixes from the same architectural shift. They can be applied independently in any order with zero operational risk. No dependency chain.

## Rollout Safety

| ID | Risk | Backward-compatible? | Test gap (must cover) | Corrected dependency |
|----|------|----------------------|-----------------------|---------------------|
| SRH-001 | Low | Yes | Consent view unit test asserting docstring accuracy; PII phase 06 review | None |
| SRH-002 | Low — **but requires coordinated test update** | Yes | Confirm no production caller exists via grep before removal; update `test_multi_lang_translation.py` fixture to remove `translate_cached` import + `cache_clear()` call | **MUST** update `test_multi_lang_translation.py:21,53` atomically |
| SRH-003 | Low | Yes | Integration test: `backfill_translations` command runs without errors on seeded data | None |
| SRH-004 | Low | Yes | None — help_text change only | None |
| SRH-005 | Low | Yes | None — documentation only | None |
| SRH-006 | N/A | N/A | None — file already deleted, no action needed | N/A |
| SRH-007 | Low | Yes | Integration test: `setup_search_triggers --backfill` populates NULL vectors for existing rows | None |

### Rollout Safety Warnings

1. **SRH-002 coordinated removal:** Removing `translate_cached` without updating `test_multi_lang_translation.py` will cause an `ImportError` in the test suite. The original findings' cross-finding analysis mistakenly linked this to `test_audit_runtime.py` (which no longer exists). The actual test dependency is `test_multi_lang_translation.py`, which must be updated in the same commit.

2. **SRH-006 already resolved:** Do not attempt to delete `test_audit_runtime.py` — it is already gone. The original finding's recommendation ("Note: this file has already been deleted as part of this audit phase") indicates resolution.

3. **SRH-001 privacy compliance:** While reclassified as DOC-UPDATE, the finding's CRITICAL severity reflects a real GDPR/CCPA compliance risk. The docstring is a privacy disclosure shown to users; misrepresenting third-party data egress is a material misrepresentation. The fix (docstring update) should be prioritized at P0 alongside any PII-phase remediation.

## Execution Validation

| Finding | Current state | Execution readiness |
|---------|--------------|-------------------|
| SRH-001 | Docstring exists at `consent.py:8-13`, code is correct | Ready — doc-only change |
| SRH-002 | Dead function at `translation.py:107-121`, no production callers | Ready — requires coordinated test update at `test_multi_lang_translation.py:21,53` |
| SRH-003 | `backfill_translations.py` exists, never invoked | Ready — wire into bootstrap with env guard, or document manual step |
| SRH-004 | Stale `help_text` at `models.py:76` | Ready — doc-only change, no migration needed (help_text is not a DB column) |
| SRH-005 | Stale line at `spec-index.md:91` | Ready — doc-only change |
| SRH-006 | File already deleted, ruff passes | No action required |
| SRH-007 | `setup_search_triggers.py` installs DDL only, no backfill | Ready — add backfill step with `--backfill` flag |

All targets still exist in the codebase. All referenced code paths are present and match the described behavior. No targets have drifted.

## Validation Summary

| Action | Count | Details |
|--------|-------|---------|
| Validated (unchanged) | 0 | — |
| Reclassified | 3 | SRH-001 (CRITICAL→DOC-UPDATE), SRH-004 (MEDIUM→DOC-UPDATE), SRH-005 (MEDIUM→DOC-UPDATE) |
| Validated as best-practice (confirmed) | 2 | SRH-002, SRH-003, SRH-007 |
| Rejected | 1 | SRH-006 (stale — file already deleted) |

### Rejected Findings

| ID | Title | Reason |
|----|-------|--------|
| SRH-006 | Orphaned audit probe file `test_audit_runtime.py` | STALE — file does not exist in current codebase; the finding's own recommendation states it was already deleted. `ruff check src/backend/` passes cleanly. Runtime verification R-06 ("1 error in orphaned test") is false in current state. |

### Merged Findings

| Original ID | Merged Into | Rationale |
|-------------|-------------|----------|
| None | — | All findings address distinct files/root causes. SRH-001/SRH-004/SRH-005 share a documentation staleness root cause but are kept separate for clear ownership. |

### Reclassified Findings

| ID | Original Type | New Type | Rationale |
|----|---------------|----------|-----------|
| SRH-001 | SPEC-DEVIATION (CRITICAL) | DOC-UPDATE | Code already implements correct behavior (no query-time translation); only the consent.py docstring is stale. Code > docs. |
| SRH-004 | SPEC-DEVIATION (MEDIUM) | DOC-UPDATE | Code already stores queries verbatim and searches per-language vectors; only the `help_text` is stale. Code > docs. |
| SRH-005 | SPEC-DEVIATION (MEDIUM) | DOC-UPDATE | Code already has 4 GIN indexes; only `spec-index.md:91` summary line is stale. Code > docs. |

### Evidence Corrections

| Finding | Issue | Correction |
|---------|-------|-----------|
| SRH-002 | Cited `test_audit_runtime.py:103` as the only test reference | File doesn't exist (SRH-006). Actual references: `test_multi_lang_translation.py:21` (import) + `:53` (`cache_clear()` in fixture). Hidden dependency not disclosed in original findings. |
| SRH-002 | Missed dependency on `test_multi_lang_translation.py` | Removing `translate_cached` breaks the test fixture's import and `cache_clear()` call. Must be updated atomically. |
| SRH-003 | Cited `bootstrap_reference_data` as a command that should include it | Validated: `bootstrap_reference_data` exists and delegates to `migrate_locked.main()`, which runs only 3 steps (no backfill). The finding's claim is accurate. |
| SRH-006 | Claimed `ruff check` has "1 error in orphaned test" | False — file deleted, ruff passes. |
| SRH-006 | Cross-finding link to SRH-002 via `test_audit_runtime.py:103` | Broken — file doesn't exist; actual link is via `test_multi_lang_translation.py`. |
| SRH-007 | Claimed "nor in migration 0001's RunSQL" | Confirmed — migration 0001 has RunSQL for trigger DDL only (lines 705–721), no backfill UPDATE. |

### Warnings

- **Architectural risk:** The consent.py docstring (SRH-001) is a privacy disclosure in a consent-facing view. While reclassified as DOC-UPDATE, the privacy-compliance risk remains CRITICAL until the docstring is corrected. Regulators may view the discrepancy as a material misrepresentation of data shared with third parties.
- **Maintability risk:** `translate_cached` (SRH-002) retains a live `@lru_cache` decorator and calls `_translate_via_api` with the production Google API key. If accidentally invoked, it would incur real API costs. The function should be removed promptly, coordinated with the test fixture update.
- **Documentation inconsistency:** `spec-index.md` (SRH-005) is internally inconsistent — lines 48 and 73 correctly mention per-language FTS, but line 91's "Key tables" summary only references the legacy index. A future reader relying on line 91 would miss the actual search backbone.
- **Operational gap (production):** Both SRH-003 (translation backfill) and SRH-007 (FTS-vector backfill) represent silent recall degradation on production upgrades with pre-existing data. Neither has an automated invocation path. Operators must be explicitly reminded to run manual backfills post-upgrade until these are wired into the bootstrap sequence.
