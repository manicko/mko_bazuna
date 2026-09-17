---
phase: "08"
phase_name: "Search & Full-Text Search (FTS)"
date: "2026-09-16"
auditor: "Auditor (verification pass)"
mode: "evidence-verification"
status: "final"
---

# Search & FTS — Findings Verification Report (SRH-001–SRH-007)

Verification of each finding against the current codebase as of 2026-09-16.
All file reads, greps, and `ruff` runs performed in this pass.

## SRH-001 — Stale privacy disclosure in `consent.py` (DOC-UPDATE) — VALIDATED

- `src/backend/apps/users/views/consent.py:8-13` — **confirmed present**.
  Lines 8–13 read: "Data flow disclosure — translation egress: Ad title/description (on creation) and
  search queries (on lookup) are sent to Google Translate via the Google Cloud Translation API
  (direct httpx call)…". The "search queries (on lookup)" claim is stale.
- `src/backend/apps/search/views/search.py:190-211` — **confirmed** per-language FTS path with
  **no** translation call. `locale = LanguageLocale.from_code(...)` (194),
  `vector_field = locale.fts_vector_field` (195), `config = locale.fts_config` (196),
  `SearchQuery(query, search_type="websearch", config=config)` (209),
  `SearchRank(F(vector_field), search_query)` (210). No `translate_*` import.
- `src/backend/apps/core/services/translation.py:8-11` — **confirmed** module docstring:
  "Search/alert query translation was removed — the search path now uses language-aware
  per-language FTS vectors with no external translation."
- Spec cross-check: `docs/01-spec/technical-specification.md:118` (§G) and `spec-index.md:47,73`
  confirm "no query-time translation".
- **Verdict:** code matches spec; only the `consent.py:8-13` docstring is stale. DOC-UPDATE reclassification holds.

## SRH-002 — `translate_cached` (bs→ru) is dead code (BEST-PRACTICE) — VALIDATED (evidence corrected)

- `src/backend/apps/core/services/translation.py:107-121` — **confirmed** present:
  `@lru_cache(maxsize=128)` (107), `def translate_cached(query: str) -> str:` (108),
  `return _translate_via_api(query, "bs", "ru")` (121).
- Word-boundary grep `\btranslate_cached\b` across `src/` — **only 3 hits**:
  - def: `translation.py:108`
  - import: `src/telegram_bot/tests/test_multi_lang_translation.py:21`
  - call: `src/telegram_bot/tests/test_multi_lang_translation.py:53` (`translate_cached.cache_clear()` in the autouse `_reset_translation_state` fixture)
  - **Zero production callers.** Confirmed.
- `translate_cached_generic` (line 125) is the **live path** — called by
  `translate_text` at `translation.py:192-194` (`_EXECUTOR.submit(translate_cached_generic, …)`)
  and by `backfill_translations.py:41`.
- No spec/model/config requires `translate_cached` (grep: no required references in
  `spec-index.md`, `technical-specification.md`, `db-schema.md`; only a research-doc mention
  in `docs/96-researches/i18n-translation-egress.md:97`).
- **Evidence correction vs. validated report:** the hidden dependency is
  `test_multi_lang_translation.py:21,53` (not the non-existent `test_audit_runtime.py:103`).
- **Verdict:** dead code confirmed; coordinated test-fixture update required before removal (remove
  the `translate_cached` import + `cache_clear()` call at `test_multi_lang_translation.py:21,53`).

## SRH-003 — `backfill_translations` never invoked (BEST-PRACTICE) — VALIDATED

- `src/backend/apps/ads/management/commands/backfill_translations.py` — **exists** (140 lines,
  idempotent batched ru→en/bs backfill via `translate_cached_generic`). Note: validated report cites
  `:56-69`, which covers only the class header + `add_arguments` + start of `handle` (108-140 is the
  real logic); the file itself is intact.
- `src/backend/apps/core/utils/migrate_locked.py:50-54` — **confirmed**: `steps` tuple contains only
  `("migrate", "--noinput", "--run-syncdb")`, `("setup_search_triggers",)`, `("load_exchange_rates",)`.
  No backfill.
- `src/backend/apps/core/management/commands/bootstrap_reference_data.py:60` — **confirmed** delegates
  to `migrate_locked.main()` (inherits the 3-step sequence).
- Entrypoint scripts — read in full, none invoke `backfill_translations`:
  - `docker/entrypoint-test.sh:25` → `bootstrap_reference_data || true`
  - `docker/entrypoint.sh` → wait_for_db / compile_messages / deploy_check / exec `$@`
  - `docker/entrypoint-scheduler.sh:28-41` → hourly sweeps + daily `send_alerts` (no backfill)
- CI workflows — read in full, none reference backfill:
  - `.github/workflows/ci.yml` → `bootstrap_reference_data` at **line 86** (test job) and **line 236**
    (i18n job). **Evidence correction:** validated report cited "ci.yml (lines 86, 227)"; line 227
    is actually the `echo "ERROR: Database unavailable"` line, not a bootstrap call. The true second
    call is at **ci.yml:236**.
  - `.github/workflows/ci-nightly.yml:65` → `bootstrap_reference_data`
- `docker-compose.yml:35` → `command: bash -c "python src/backend/manage.py bootstrap_reference_data"`
- Grep for `backfill` across `docker/*.sh`, `.github/*.yml`, and all root `entrypoint*.sh` →
  **no matches** (only doc references in `docs/ops/migration-workflow.md`).
- **Verdict:** command exists & is correct, but has **no automated invocation path**. Validated.

## SRH-004 — Stale `SavedSearch.query` help_text (DOC-UPDATE) — VALIDATED

- `src/backend/apps/search/models.py:76` — **confirmed** stale:
  `help_text="FTS query string (translated to Russian if Bosnian input)"`.
- `src/backend/apps/search/views/save_search.py:37` — **confirmed** verbatim storage:
  `query = (request.POST.get("query") or "").strip()`; `SavedSearch.objects.create(..., query=query or None, ...)`
  at 48-50. No translation.
- `src/backend/apps/search/services/alert_query.py:48-68` — **confirmed** per-language vector search
  with no translation: `locale = LanguageLocale.from_code(saved_search.language, …)` (49),
  `vector_field = locale.fts_vector_field` (53), `config = locale.fts_config` (54),
  `SearchQuery(saved_search.query, search_type="websearch", config=config)` (56-60),
  `filter(**{vector_field: search_query})` (66).
  (File lives at `apps/search/services/alert_query.py`, **not** `apps/search/views/` — the validated
  report's "src/backend/apps/search/views/ alert_query.py" path is imprecise.)
- **Verdict:** code correct; only `models.py:76` help_text stale. DOC-UPDATE holds.

## SRH-005 — `spec-index.md` omits per-language GIN indexes (DOC-UPDATE) — VALIDATED

- `docs/01-spec/spec-index.md:91` — **confirmed** stale:
  `- Search index: `GinIndex IX_ads_search_gin`` (only the legacy index).
- `src/backend/apps/ads/models.py:259-274` — **confirmed** all 4 GIN indexes:
  `IX_ads_search_gin` (259-262), `IX_ads_search_gin_ru` (263-266), `IX_ads_search_gin_bs` (267-270),
  `IX_ads_search_gin_en` (271-274).
- `docs/02-database/db-indexes.md:48-59` — **confirmed** all 4 documented (legacy + 3 per-language).
- `spec-index.md` is internally inconsistent: line 48 & 73 already mention per-language vectors
  conceptually, but the §"Key tables" summary at line 91 is stale.
- **Verdict:** code correct; only `spec-index.md:91` stale. DOC-UPDATE holds.

## SRH-006 — Orphaned `test_audit_runtime.py` (REJECTED) — VALIDATED REJECTION, BUT ruff-is-clean claim is STALE

- `test_audit_runtime.py` — **confirmed absent** (glob `**/test_audit_runtime.py` across repo → no files).
  `ruff check` on that path returns `E902 Cannot find file`. Core SRH-006 claim holds → rejection valid.
- `ruff check src/backend/` — **does NOT pass cleanly** as the validated report claims. Current output
  has **6 errors** (run performed 2026-09-16):
  - `src/backend/apps/ads/migrations/0005_remove_ad_ix_ads_delete_sweep_ad_ix_ads_delete_sweep.py:3` — I001 (import unsorted). **Tracked/committed**, generated 2026-09-14 (post-validation date 2026-09-12).
  - `src/backend/apps/ads/migrations/0006_ad_ix_ads_draft_sweep.py:3` — I001 (same). **Tracked/committed**, 2026-09-14.
  - `src/backend/apps/ads/tests/b9_debug_test.py:2` — I001; `:25` — I001; `:26` — F401 (`pathlib.Path` unused). **Untracked**, "Temporary diagnostic test for B9 DEBUG investigation".
  - `src/backend/apps/ads/tests/test_debug_value.py:2` — I001; `:25` — I001. **Untracked**, same diagnostic purpose.
- Ruff config: `[tool.ruff.lint]` selects E/F/I/B/UP (pyproject.toml:117-124); `[tool.ruff]` exclude
  (95-114) does **not** exclude `migrations` (the `migrations` exclude is under `[tool.black]`, line 84).
  So committed migrations 0005/0006 are in scope and **would fail CI lint**.
- Scoped check `ruff check src/backend/apps/search/` → **"All checks passed!"** (search dirs are clean).
- **Evidence correction:** the validated report's claim that "`ruff check src/backend/` returns
  'All checks passed!'" (SRH-006 rejection rationale #3, and runtime-verification R-06) is **false in
  the current working tree**. It was true at validation date (2026-09-12) but is now stale: two
  committed migrations (created 2026-09-14) and two untracked diagnostic test files now fail lint.
- **Verdict:** SRH-006 rejection (test_audit_runtime.py absent) is **correct**, but its supporting
  "ruff is clean" evidence is **stale/REFUTED** — new lint failures have appeared since validation.

## SRH-007 — Search-vector backfill not automated (BEST-PRACTICE) — VALIDATED (with line-number correction)

- `src/backend/apps/ads/management/commands/setup_search_triggers.py` — **confirmed** no `--backfill`
  flag: `Command` defines no `add_arguments`; `handle` (114) executes only `DDL_STATEMENTS` (121-125).
- `DDL_STATEMENTS` (98-103) = 4 entries, all DDL only:
  1. `SEARCH_VECTOR_FN_SQL` — CREATE OR REPLACE FUNCTION (CREATE TRIGGER fn)
  2. `CATEGORY_PROPAGATE_FN_SQL` — CREATE OR REPLACE FUNCTION
  3. `SEARCH_VECTOR_TRIGGER_SQL` — DROP TRIGGER IF EXISTS + CREATE TRIGGER
  4. `CATEGORY_PROPAGATE_TRIGGER_SQL` — DROP TRIGGER IF EXISTS + CREATE TRIGGER
  No `UPDATE` backfill in any DDL statement.
- `src/backend/apps/ads/migrations/0001_initial.py:705-721` — **confirmed** RunSQL for trigger DDL only
  (2 functions + 2 triggers), no backfill UPDATE.
- `db-indexes.md` — the manual `UPDATE ads SET title = title` workaround is at lines **185-187**:
  > "**Migration notes:** one-time `UPDATE ads SET title = title` to backfill the per-language vectors
  > for existing rows (seed uses `bulk_create`, bypassing the trigger)…"
  **Evidence correction:** validated report cited `db-indexes.md:165` (File) and `:165-166` (body),
  but the actual workaround text is at **lines 185-187** (165 is inside the `ad_images` thumbnail block).
- No `backfill_search_vectors` command — **confirmed** (glob `**/backfill_search_vectors*.py` → none;
  grep for `backfill` across docker/CI/shell → none).
- **Verdict:** trigger/backfill gap confirmed; validated report's line citation (165/165-166) is
  incorrect (actual: 185-187). Substance validated.

## Additional context verifications

- **Ad search vectors** (all confirmed present): `search_vector` (`ads/models.py:217`),
  `search_vector_ru` (222), `search_vector_bs` (227), `search_vector_en` (232).
- **Ad translation fields** (all confirmed present): `title_en` (53), `description_en` (70),
  `title_bs` (59), `description_bs` (75), `original_language` (80).
- **CI workflows:** `ci.yml` (262 lines), `ci-nightly.yml` (82 lines) — read in full; only
  `bootstrap_reference_data` invoked, no `backfill_translations`.
- **Prior plans:** `.ai/plans/done/` contains only `17_url-state-preservation_spec_DONE.md` and
  `18_contact-us_spec_DONE.md` — no prior search/FTS plans.
- **Entrypoint layout:** root-level `entrypoint*.sh` are gitignored stale stubs
  (`.gitignore:251` `/entrypoint*.sh`); canonical scripts live in `docker/`.

## Summary

| ID | Status | Substantive claim | Evidence corrections / notes |
|----|--------|-------------------|------------------------------|
| SRH-001 | Validated (DOC-UPDATE) | consent.py:8-13 stale; search.py + translation.py confirm no query-time translation | None |
| SRH-002 | Validated (BEST-PRACTICE) | translate_cached dead; zero production callers | Actual dep is `test_multi_lang_translation.py:21,53` (not `test_audit_runtime.py:103`) |
| SRH-003 | Validated (BEST-PRACTICE) | backfill_translations never invoked from entrypoint/CI | Cited `ci.yml:227` is actually an echo line; real second bootstrap call is `ci.yml:236`. Cited range `:56-69` covers only class header |
| SRH-004 | Validated (DOC-UPDATE) | models.py:76 help_text stale; save_search.py + alert_query.py store/search verbatim | `alert_query.py` is in `apps/search/services/`, not `apps/search/views/` |
| SRH-005 | Validated (DOC-UPDATE) | spec-index.md:91 stale; 4 GIN indexes in code + db-indexes.md | None |
| SRH-006 | Rejected (stale evidence) | test_audit_runtime.py absent ✓ | **`ruff check src/backend/` is NOT clean** (6 errors: 2 committed migrations 0005/0006 dated 2026-09-14, 2 untracked diagnostic test files). Validated report's "ruff passes" claim is stale |
| SRH-007 | Validated (BEST-PRACTIME) | setup_search_triggers has no backfill; migration 0001 DDL-only | `db-indexes.md` workaround is at **185-187**, not 165/165-166 as cited |

## Ancillary observations (out of 7-finding scope)

- `docs/01-spec/technical-specification.md:66` (§D, category-name search) states "Montenegrin query
  is translated to Russian before search, so it matches the Russian category name" — this contradicts
  §G (line 118: "no query-time translation") and the actual code (`search.py:350-353` matches the
  query against the locale-appropriate category name via `Category.get_name(locale.value)`, no
  translation). A spec-internal inconsistency adjacent to SRH-001's root cause; not filed as a
  standalone finding but flagged for triage.
