---
phase: 08
phase_name: search-fts
source: .ai/audit/08-search-fts/findings.md
validated: 2026-08-15
validator: validator
---

# Phase 08 Audit Findings — Validation Report (Search & Full-Text Search)

> **Mode:** `problems_only=TRUE` — only findings with confirmed problems are included.
> All 11 findings are **validated** as real problems. No findings were rejected.
> See "Validation Notes" for recommendation and documentation issues discovered during validation.

---

## Findings

### SRH-001: FTS search_vector trigger missing multi-language i18n fields

> **Validation Note:**
> - **Action:** validated
> - **Detail:** Confirmed in `src/backend/apps/ads/migrations/0002_initial.py` lines 17–20 (`SEARCH_VECTOR_FN_SQL`). The trigger function builds `search_vector` using only `to_tsvector('russian', ...)` for `title`, `description`, and `v_cat`. It does NOT include `title_bs`, `description_bs`, `title_en`, or `description_en` added by migration `0003_ad_i18n_fields.py`. Neither `0003` nor the existing `0004_ad_draft_nullable_fields.py` updates the trigger function. `docs/02-database/db-indexes.md` lines 55–76 documents the correct multi-language SQL. `docs/01-spec/technical-specification.md` line 101 confirms the spec requires multi-language vector. Root cause confirmed — no recommendation issues beyond migration numbering (see note below).
> - **Recommendation correction:** The finding recommends creating migration `0004_search_vector_i18n`, but `0004_ad_draft_nullable_fields.py` already exists. The new migration should be `0005_search_vector_i18n` (or later) with dependency on `0004`.
> - **Evidence quality:** Strong — code, docs, spec, and migration lineage all confirmed.
> - **See also:** SRH-002 (same migration context)

**ID:** SRH-001
**Severity:** CRITICAL
**Type:** SPEC-DEVIATION
**Status:** VALIDATED

---

### SRH-002: No data backfill migration for existing rows

> **Validation Note:**
> - **Action:** validated
> - **Detail:** Confirmed in `src/backend/apps/ads/migrations/0002_initial.py` lines 129–144: only `RunSQL` calls create the trigger functions and triggers. No `RunSQL` step backfills `search_vector` or `category_name` for existing rows. `docs/02-database/db-indexes.md` lines 102–104 documents the backfill requirement. The `categories_name_propagate` trigger (migration lines 33–48) only fires on category name updates, not as an initial backfill. In production, existing ads added before the trigger migration would have `NULL` `search_vector` and `category_name`.
> - **Recommendation correction:** Same migration numbering issue as SRH-001 — should be `0005` (not `0004`) since `0004_ad_draft_nullable_fields.py` already exists.
> - **Rollout safety:** The recommended backfill `UPDATE ads SET category_id = ads.category_id` triggers the `BEFORE INSERT OR UPDATE` trigger for each row, causing full table row updates. On large production tables this may cause row-level locks. Recommend running during low-traffic window.
> - **Evidence quality:** Strong — docs and migration code both confirmed.
> - **See also:** SRH-001 (same migration context)

**ID:** SRH-002
**Severity:** MEDIUM
**Type:** SPEC-DEVIATION
**Status:** VALIDATED

---

### SRH-003: send_alerts management command crashes on import

> **Validation Note:**
> - **Action:** validated
> - **Detail:** Confirmed in `src/backend/apps/search/management/commands/send_alerts.py` line 13: `from aiogram.exceptions import TelegramBadRequest, TelegramForbidden`. The installed aiogram package (`aiogram/exceptions.py`) defines `TelegramForbiddenError(TelegramAPIError)` — the name `TelegramForbidden` does not exist. Importing `send_alerts.py` raises `ImportError`, preventing the management command from loading. `scripts/_tmp_pytest_run.txt` lines 216–217, 243–244, 270–271 confirm the `ImportError`. Three `TestSendAlertsCommand` tests fail (lines 219, 246, 270 of pytest output). `.ai/plans/02/Saved Search Alerts/plan.md` lines 485, 618, 787 also use the incorrect name.
> - **Description error:** The finding's description states "The project plan (`docs/02-database/db-indexes.md` and `.ai/plans/02/Saved Search Alerts/plan.md`) both reference the old name." In reality, `docs/02-database/db-indexes.md` does NOT reference `TelegramForbidden` — the grep confirms it only appears in `send_alerts.py`, `.ai/plans/02/Saved Search Alerts/plan.md`, and the findings file itself. This is a minor error in the finding description; the core finding and recommendation are correct.
> - **Dependency:** SRH-003 must be fixed before SRH-005 and SRH-011's `TestSendAlertsCommand` tests can pass (import error blocks command loading).
> - **Evidence quality:** Strong — code, installed package, and test output all confirm.

**ID:** SRH-003
**Severity:** CRITICAL
**Type:** RUNTIME-ERROR
**Status:** VALIDATED

---

### SRH-004: popular_search hit_count reset on every call

> **Validation Note:**
> - **Action:** validated
> - **Detail:** Confirmed in `src/backend/apps/search/services/popular_search.py` lines 37–45. `update_or_create(query_normalized=normalized, defaults={"query": query, "hit_count": 1})` sets `hit_count=1` on BOTH insert and update paths. On update (record exists), `hit_count` is first set to 1 by `defaults`, then incremented by `F("hit_count") + 1` to 2. Every subsequent call resets to 1 then increments to 2. `hit_count` can never exceed 2. `scripts/_tmp_pytest_run.txt` lines 293–297 confirm: `test_increment_popular_search_increments_existing` calls `increment_popular_search("????")` three times, expects `hit_count == 3`, gets `2`.
> - **Recommendation:** The suggested fix (`get_or_create` with `defaults` containing `hit_count=1` only on creation) is correct and minimal. No issues.
> - **Rollout safety:** The `update_or_create` ? `get_or_create` swap introduces a minor race condition (concurrent inserts could raise `IntegrityError`). However, the existing `category_name` trigger pattern and the project's low-traffic scale make this acceptable. If concurrent writes are a concern, a `select_for_update` or `on_conflict` approach could be used, but that is out of scope for this critical bug fix.
> - **Evidence quality:** Strong — code and test output both confirm.

**ID:** SRH-004
**Severity:** HIGH
**Type:** RUNTIME-ERROR
**Status:** VALIDATED

---

### SRH-005: Alert query hardcodes Bosnian?Russian translation

> **Validation Note:**
> - **Action:** validated
> - **Detail:** Confirmed in `src/backend/apps/search/services/alert_query.py` line 50: `translated_query = translate_query_bs_to_ru(saved_search.query)`. This calls `translate_cached(query)` (line 142 of `query_translator.py`) which uses `GoogleTranslator(source="bs", target="ru")`, hardcoding Bosnian as source. In contrast, the web search view (`search.py` lines 93–97) correctly uses `translate_query(query, query_language, "ru")` respecting `request.LANGUAGE_CODE`. The `SavedSearch` model (`models.py` lines 47–106) has no language preference field. `scripts/_tmp_pytest_run.txt` lines 185–186 confirm: `Translation failed for query '?????????'` — a Russian query being incorrectly sent through Bosnian?Russian translation.
> - **Recommendation:** Storing user language preference on `SavedSearch` (or inferring from user profile) and using `translate_query(saved_search.query, source_locale, "ru")` is correct and aligns with the web search view pattern. This is a model change requiring a migration, but is backward compatible (nullable field).
> - **Evidence quality:** Strong — code comparison across alert_query.py and search.py both confirmed.

**ID:** SRH-005
**Severity:** HIGH
**Type:** SPEC-DEVIATION
**Status:** VALIDATED

---

### SRH-006: save_search_modal.html references non-existent URL names

> **Validation Note:**
> - **Action:** validated
> - **Detail:** Confirmed in `src/backend/templates/search/partials/save_search_modal.html` line 6: `{% url 'search:list' %}` and line 14: `{% url 'search:save-search' %}`. The URL config (`src/backend/apps/search/urls.py` lines 9–11) only defines `path("search/", search, name="search")` and `path("api/search/autocomplete", autocomplete, name="autocomplete")`. No `search:list` or `search:save-search` URL names exist anywhere in the codebase (grep confirms zero matches in `src/`). Rendering this template would raise `django.urls.exceptions.NoReverseMatch`. `.ai/plans/02/Saved Search Alerts/plan.md` lines 651, 659 reference the same incorrect URL names, suggesting they were planned but never implemented.
> - **Evidence quality:** Strong — code, URL config, and grep all confirmed.

**ID:** SRH-006
**Severity:** HIGH
**Type:** RUNTIME-ERROR
**Status:** VALIDATED

---

### SRH-007: Rate limiter cache not isolated between tests

> **Validation Note:**
> - **Action:** validated
> - **Detail:** Confirmed in `src/backend/apps/search/tests/test_autocomplete.py`. The `TestAutocompleteEndpoint` class has 5 tests. Only `test_autocomplete_rate_limit` (line 175) calls `cache.clear()`. The subsequent tests — `test_autocomplete_deduplication` (line 154), `test_autocomplete_anonymous_user_returns_popular_and_entities` (line 210), and `test_autocomplete_malicious_query_sanitized` (line 236) — do NOT clear cache. The rate limiter (`rate_limit.py` lines 44–58) uses Django's cache framework with a 60-second window and 30-request threshold, keyed by client IP. All tests use the default test client (IP 127.0.0.1). No `cache.clear()` fixture exists in `conftest.py` or any test-level fixture in the search tests directory. `scripts/_tmp_pytest_run.txt` lines 272–291 confirm three tests fail with `assert 429 == 200`.
> - **Recommendation:** Adding a `cache.clear()` autouse fixture to the `TestAutocompleteEndpoint` class (or a broader conftest) is correct and minimal. The `TestRateLimitService.test_rate_limit_blocks_after_threshold` test (line 426) already calls `cache.clear()` at line 430.
> - **Evidence quality:** Strong — code and test output both confirmed.

**ID:** SRH-007
**Severity:** LOW
**Type:** BEST-PRACTICE
**Status:** VALIDATED

---

### SRH-008: Translation cache invalidation function defined but never called

> **Validation Note:**
> - **Action:** validated
> - **Detail:** Confirmed in `src/backend/apps/search/services/query_translator.py` line 146: `invalidate_translation_cache()` is defined with a docstring. It calls `translate_cached.cache_clear()` (line 148) and `translate_cached_generic.cache_clear()` (line 149). Grep across the entire codebase confirms it is never called at runtime — only appears in its definition (line 146), its docstring (line 157), and structural index JSON files (`.ai/structure/back/py_map.json`, `py_anchors.json`). The test file `test_query_translator.py` has an autouse fixture `_reset_translation_state` (line 27) that manually calls `translate_cached.cache_clear()` (line 32) but does NOT call `invalidate_translation_cache()`.
> - **Practical impact:** LOW. The LRU caches have bounded sizes (128 and 256 entries), so stale translations are eventually evicted. However, within a single process lifetime, stale translations persist until cache eviction. No dynamic translation settings change exists in the current codebase, so the practical impact is limited to development scenarios.
> - **Recommendation:** The suggestion to wire it into lifecycle hooks or remove it is valid. Given no dynamic settings changes exist, removal would be the simpler approach. However, keeping it for future use (when dynamic settings might be supported) is also reasonable. Advisory classification is appropriate.
> - **Evidence quality:** Strong — code and grep both confirmed.

**ID:** SRH-008
**Severity:** LOW
**Type:** BEST-PRACTICE
**Status:** VALIDATED

---

### SRH-009: No search latency or translation success observability

> **Validation Note:**
> - **Action:** validated
> - **Detail:** Confirmed in `src/backend/apps/search/views/search.py` lines 116–119: only `AnalyticsEvent.objects.create(event_type=AnalyticsEventType.SEARCH_PERFORMED, ...)` is recorded. No latency measurement, no translation outcome recording, no FTS match count. `query_translator.py` logs at `debug`/`info`/`warning` levels but emits no metrics (counters/histograms). Grep for `latency`, `duration`, `metrics`, `histogram`, `timer` across the entire `search` app returns only a comment about timeout bounding latency (`query_translator.py` line 21) — no actual metric instrumentation.
> - **Recommendation:** Adding structured logging (e.g., `logger.info("search_latency_ms=%d", elapsed_ms)`) is practical and low-risk. Integrating with Prometheus (`django-prometheus`) would require adding a new dependency — the finding's recommendation correctly suggests this as optional ("if the project adopts one").
> - **Evidence quality:** Strong — code and grep both confirmed.

**ID:** SRH-009
**Severity:** LOW
**Type:** BEST-PRACTICE
**Status:** VALIDATED

---

### SRH-010: No max query length validation on search view entry point

> **Validation Note:**
> - **Action:** validated
> - **Detail:** Confirmed in `src/backend/apps/search/views/search.py` line 48: `query = (request.GET.get("q") or "").strip()` — no length check or truncation. The raw query is passed to:
>   - `increment_popular_search(query)` (`popular_search.py` line 37) which writes to `PopularSearch.query` (`CharField(max_length=200)`, `models.py` line 13) and `query_normalized` (line 14).
>   - `record_search_history(request.user.id, query)` (`search_history.py` line 45) which writes to `SearchHistory.query` (`CharField(max_length=200)`, `models.py` line 34).
>   A query longer than 200 characters would raise `psycopg.DataError: value too long for type character varying(200)` ? HTTP 500. The autocomplete endpoint (`autocomplete.py` line 53) uses `sanitize_autocomplete_query` (`sanitize.py` lines 39–42) which enforces 2–100 chars, but the main search view has no equivalent guard.
> - **Recommendation:** Adding a `MAX_QUERY_LENGTH` constant and truncating/validating at the view entry point is correct and minimal. Truncation to 200 chars (matching the model) is the safe choice.
> - **Evidence quality:** Strong — code across view, services, and models all confirmed.

**ID:** SRH-010
**Severity:** MEDIUM
**Type:** BEST-PRACTICE
**Status:** VALIDATED

---

### SRH-011: Alert query test fixtures use default description containing the search term

> **Validation Note:**
> - **Action:** validated
> - **Detail:** Confirmed in `src/backend/apps/search/tests/test_alert_query.py` lines 93–105. The `_create_published_ad` helper defaults `description` to "????????? ??????? ????????? ? ??????? ?????????" which contains "?????????". Tests `test_returns_matching_ads_by_query` (line 116, query="?????????") creates two ads — "??????? ?????????" (title match) and "?????? ??????????" (desc match only) — both match the FTS query ? returns 2 instead of expected 1. `test_excludes_non_matching_ads` (line 131, query="?????????") creates "?????? ??????????" with default description containing "?????????" ? returns 1 instead of expected 0. `scripts/_tmp_pytest_run.txt` lines 179–190 confirm: `assert 2 == 1` and `assert 1 == 0`. The FTS search is correctly finding ads whose description contains the search term — the bug is in the test fixtures, not production code.
> - **Note on SRH-005 interaction:** Line 185 of pytest output shows "Translation failed for query '?????????'" — this is because `find_matching_ads` calls `translate_query_bs_to_ru` on the Russian query, which fails and falls back to the original. This is a secondary effect of SRH-005 but does not cause the test failures — the failures are purely from the description containing the search term. Fixing SRH-005 alone would NOT fix these test assertions; SRH-011 must also be fixed.
> - **Recommendation:** Using a generic description that doesn't contain the search term is correct and minimal.
> - **Evidence quality:** Strong — code and test output both confirmed.

**ID:** SRH-011
**Severity:** LOW
**Type:** BEST-PRACTICE
**Status:** VALIDATED

---

## Cross-Finding Analysis

### Dependency Chains

| From | Depends On | Detail |
|------|-----------|--------|
| SRH-001 fix | SRH-002 fix | Both should be addressed in a single new migration (`0005_*` in the `ads` app) — the trigger function update (SRH-001) and the backfill RunSQL (SRH-002) belong together. |
| SRH-003 fix | — | Independent. Must be fixed before `TestSendAlertsCommand` tests (SRH-005/SRH-011 downstream tests) can execute. |
| SRH-005 fix | SRH-003 fix | Production code change (alert_query.py). Tests for `send_alerts` cannot run until SRH-003 is fixed (import error). |
| SRH-011 fix | — | Independent test-only fix. Not blocked by SRH-005; fixing SRH-005 alone will not fix SRH-011's assertions. |
| SRH-008 fix | — | Independent. |
| SRH-009 fix | — | Independent. |
| SRH-010 fix | — | Independent. |

### Conflicts

No cross-phase conflicts detected. Findings from phases 01–09 were scanned for overlapping or contradictory claims with the Phase 08 findings. No matches found.

### Merge Candidates

None. While SRH-001 and SRH-002 share the same migration context (search_vector trigger), they have distinct root causes (missing i18n fields vs. missing backfill step) and distinct recommendations. Similarly, SRH-005 and SRH-011 both touch the alert query path but have independent root causes (production translation hardcoding vs. test fixture description).

---

## Rollout Safety Assessment

### SRH-001 + SRH-002 (combined migration)
- **Risk:** MEDIUM. The backfill `UPDATE ads SET category_id = category_id` triggers the updated `BEFORE INSERT OR UPDATE` trigger function for every existing row, causing full row updates. On a production table with many rows, this may cause lock contention.
- **Mitigation:** Run during low-traffic window. The `categories_name_propagate` trigger already uses this same pattern, so no new risk patterns are introduced.
- **Rollback:** The migration uses `RunSQL.noop` for `reverse_sql` (as seen in migration 0002). The new migration should follow the same pattern or provide a proper reverse for the backfill step.

### SRH-003 (import name fix)
- **Risk:** NONE. Trivial rename. Backward compatible.
- **Rollback:** Trivial revert.

### SRH-004 (update_or_create ? get_or_create)
- **Risk:** LOW. `get_or_create` with `defaults` is semantically equivalent for single-threaded usage. Under concurrent requests, two simultaneous first-ever calls for the same query could race, both trying to INSERT, causing one to hit `IntegrityError` (unique constraint on `query_normalized`). Django's `get_or_create` handles this internally by catching `IntegrityError` and retrying the `get`. This is safe.
- **Rollback:** Trivial revert.

### SRH-005 (language preference on SavedSearch)
- **Risk:** LOW. Adding a nullable field to `SavedSearch` is backward compatible. Existing saved searches would have `NULL` language, requiring the service to handle the null case (default to Bosnian or infer from user profile).
- **Rollout ordering:** Must add the model field + migration BEFORE updating `alert_query.py` to use it.

### SRH-006 (URL names or template fix)
- **Risk:** LOW. Two options: (a) implement missing endpoints — requires new views, URL entries, and possibly new migrations; (b) fix template to use existing `search:search` URL name — trivial.
- **Rollout:** Safe either way.

### SRH-007 (test cache isolation)
- **Risk:** NONE. Test-only change.

### SRH-008 (dead code)
- **Risk:** NONE. Either wire in or remove. No production impact currently.

### SRH-009 (observability)
- **Risk:** NONE. Adding logging/metrics is non-breaking.

### SRH-010 (query length validation)
- **Risk:** LOW. Truncation at the view entry point is backward compatible. Users submitting >200 char queries would previously get HTTP 500; after fix they'd get truncated results.
- **Note:** Ensure consistent truncation across FTS, popular search, and history recording (all use the same truncated value).

### SRH-011 (test fixtures)
- **Risk:** NONE. Test-only change.

---

## Validation Summary

| Action | Count | Details |
|--------|-------|---------|
| Validated (unchanged) | 11 | SRH-001, SRH-002, SRH-003, SRH-004, SRH-005, SRH-006, SRH-007, SRH-008, SRH-009, SRH-010, SRH-011 |
| Reclassified | 0 | — |
| Merged | 0 | — |
| Rejected | 0 | — |

### Findings with Recommendation/Documentation Corrections

| ID | Issue |
|----|-------|
| SRH-001 | Recommendation references migration `0004_search_vector_i18n` — collision with existing `0004_ad_draft_nullable_fields.py`. Use `0005` or later. |
| SRH-002 | Same migration numbering issue — should be `0005` (or same as SRH-001), not `0004`. |
| SRH-003 | Description incorrectly claims `docs/02-database/db-indexes.md` references `TelegramForbidden`. Grep confirms it does not — only `.ai/plans/02/Saved Search Alerts/plan.md` and `send_alerts.py` do. Core finding is correct. |

### Document Discrepancy (not a finding)

The "Verified-Correct Behavior" section of the source findings references `test_search_triggers.py` ("All 7 tests in `test_search_triggers.py` pass"). No such file exists in the codebase — the search tests directory contains only `test_autocomplete.py`, `test_autocomplete_template.py`, `test_alert_query.py`, and `test_query_translator.py`. This is a documentation error in the findings but does not affect any finding's validity.

---

## Rollout Sequencing Recommendation

1. **SRH-003** (trivial, unblocks test execution for alert-related tests)
2. **SRH-004** (trivial, fixes popular search metrics)
3. **SRH-010** (trivial, prevents HTTP 500 on long queries)
4. **SRH-006** (template/URL fix — low effort)
5. **SRH-001 + SRH-002** (combined migration — run during low-traffic window)
6. **SRH-005** (model field + service change — requires migration)
7. **SRH-007** (test isolation — independent)
8. **SRH-011** (test fixture fix — independent)
9. **SRH-008** (dead code removal/wiring — optional)
10. **SRH-009** (observability — optional)
