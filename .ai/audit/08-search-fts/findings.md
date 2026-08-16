# Phase 08 Audit Findings � Search & Full-Text Search (FTS)

**Executor:** audit-executor
**Template:** .kilo/commands/audit/phases/08-audit-search-fts.md
**Status:** complete
**Validated:** yes

---

## Findings

### SRH-001: FTS search_vector trigger missing multi-language i18n fields (spec deviation)

| Field | Value |
|-------|-------|
| **ID** | SRH-001 |
| **Severity** | CRITICAL |
| **Type** | SPEC-DEVIATION |
| **Affected Modules** | src/backend/apps/ads/migrations/0002_initial.py, docs/02-database/db-indexes.md, docs/01-spec/technical-specification.md:101 |
| **Classification** | mandatory |

**Description:**

The search_vector trigger function in migration `0002_initial.py` (`SEARCH_VECTOR_FN_SQL`) builds the `search_vector` using **only** the `russian` text-search configuration over `title`, `description`, and `category_name`. It does not include the Bosnian (`title_bs`, `description_bs`) or English (`title_en`, `description_en`) i18n fields added by migration `0003_ad_i18n_fields`.

The documentation in `docs/02-database/db-indexes.md` (lines 55-76) explicitly specifies a multi-language vector:

```sql
NEW.search_vector :=
  setweight(to_tsvector('russian',   coalesce(NEW.title,'')),     'A') ||
  setweight(to_tsvector('russian',   coalesce(NEW.description,'')), 'B') ||
  setweight(to_tsvector('simple',    coalesce(NEW.title_bs,'')),    'A') ||
  setweight(to_tsvector('simple',    coalesce(NEW.description_bs,'')), 'B') ||
  setweight(to_tsvector('english',   coalesce(NEW.title_en,'')),    'A') ||
  setweight(to_tsvector('english',   coalesce(NEW.description_en,'')), 'B') ||
  setweight(to_tsvector('simple',    coalesce(v_cat,'')),           'C');
```

The actual migration only contains:

```sql
NEW.search_vector :=
  setweight(to_tsvector('russian', coalesce(NEW.title,'')), 'A') ||
  setweight(to_tsvector('russian', coalesce(NEW.description,'')), 'B') ||
  setweight(to_tsvector('simple', coalesce(v_cat,'')), 'C');
```

Spec reference: `docs/01-spec/technical-specification.md` line 101 � "Multi-language search vector includes all language variants using appropriate FTS configurations (russian, simple, english)."

**Evidence:**

- `src/backend/apps/ads/migrations/0002_initial.py` lines 17-20: trigger function only includes `russian` config for `title` and `description`.
- `docs/02-database/db-indexes.md` lines 56-76: documented SQL includes `title_bs`, `description_bs` (simple config) and `title_en`, `description_en` (english config).
- `src/backend/apps/ads/migrations/0003_ad_i18n_fields.py` adds the i18n fields but never updates the trigger function to include them.

**Recommendation:**

Update `SEARCH_VECTOR_FN_SQL` in a new migration (`0004_search_vector_i18n`) to include the i18n fields using `simple` config for Bosnian and `english` config for English, matching the documented SQL in `db-indexes.md`. The `simple` config for Bosnian is justified because PostgreSQL 18 has no native Bosnian text search configuration (as documented in `db-indexes.md` line 78).

Effort: small. Priority: recommended (mandatory � spec deviation affecting cross-language search correctness).

---

### SRH-002: No data backfill migration for existing rows

| Field | Value |
|-------|-------|
| **ID** | SRH-002 |
| **Severity** | MEDIUM |
| **Type** | SPEC-DEVIATION |
| **Affected Modules** | src/backend/apps/ads/migrations/0002_initial.py, docs/02-database/db-indexes.md:102-104 |
| **Classification** | mandatory |

**Description:**

The documentation in `docs/02-database/db-indexes.md` (lines 102-104) states: "Migration notes: one-time `UPDATE ads SET category_id = category_id` (or backfill) to fill `category_name` + `search_vector` for existing rows."

However, migration `0002_initial.py` only creates the trigger function and trigger via `RunSQL` � it does **not** include a `RunSQL` step to backfill `search_vector` and `category_name` for existing rows. The trigger only fires on `INSERT` and `UPDATE` of individual rows. Any ads that existed before the trigger was in place (or in any scenario where the trigger doesn't fire) will have `NULL` `search_vector` and `NULL` `category_name`.

While the test DB is created fresh (so this doesn't affect tests), in production this would mean existing ads added before the migration have stale or NULL search vectors, making them unfindable via FTS.

**Evidence:**

- `docs/02-database/db-indexes.md` lines 102-104: documents the backfill requirement.
- `src/backend/apps/ads/migrations/0002_initial.py` lines 129-144: only `RunSQL` for trigger creation, no backfill `RunSQL`.

**Recommendation:**

Add a `RunSQL` backfill step in a new migration (`0004_search_vector_i18n`) to populate `search_vector` and `category_name` for all existing rows: `UPDATE ads SET category_id = category_id` (which triggers the `BEFORE INSERT OR UPDATE` trigger to fill the vector). Alternatively, call `ads_search_vector_fn()` explicitly via `UPDATE ads SET search_vector = (SELECT ... )`.

Effort: small. Priority: recommended.

---

### SRH-003: send_alerts management command crashes on import (wrong aiogram exception name)

| Field | Value |
|-------|-------|
| **ID** | SRH-003 |
| **Severity** | CRITICAL |
| **Type** | RUNTIME-ERROR |
| **Affected Modules** | src/backend/apps/search/management/commands/send_alerts.py:13,152, .ai/plans/02/Saved Search Alerts/plan.md:485,618,787 |
| **Classification** | mandatory |

**Description:**

`send_alerts.py` line 13 imports `TelegramForbidden` from `aiogram.exceptions`, but aiogram 3.x renamed this exception to `TelegramForbiddenError`. The import fails with `ImportError`, preventing the management command from loading entirely. This breaks the daily saved-search alert delivery cron job.

The project plan (`docs/02-database/db-indexes.md` and `.ai/plans/02/Saved Search Alerts/plan.md`) both reference the old name `TelegramForbidden`, propagating the incorrect name into documentation.

**Evidence:**

- `src/backend/apps/search/management/commands/send_alerts.py` line 13:
  ```python
  from aiogram.exceptions import TelegramBadRequest, TelegramForbidden
  ```
- Test output (`scripts/_tmp_pytest_run.txt` lines 216-217, 243-244, 270-271):
  ```
  ImportError: cannot import name 'TelegramForbidden' from 'aiogram.exceptions'
  ```
- Three `TestSendAlertsCommand` tests fail with this ImportError (lines 1564-1566 in test summary).
- `.ai/plans/02/Saved Search Alerts/plan.md` lines 485, 618, 787: references the incorrect name.

**Recommendation:**

Replace `TelegramForbidden` with `TelegramForbiddenError` in `send_alerts.py`. Update the plan documentation to match. The correct import for aiogram 3.x is:
```python
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
```

Effort: trivial. Priority: recommended (mandatory � production cron job completely broken).

---

### SRH-004: popular_search hit_count reset on every call after first (production logic bug)

| Field | Value |
|-------|-------|
| **ID** | SRH-004 |
| **Severity** | HIGH |
| **Type** | RUNTIME-ERROR |
| **Affected Modules** | src/backend/apps/search/services/popular_search.py:37-45 |
| **Classification** | mandatory |

**Description:**

`increment_popular_search` uses `update_or_create` with `defaults={"query": query, "hit_count": 1}`. On **every** update (when the record already exists), the `hit_count` is **reset to 1** before the subsequent `F("hit_count") + 1` increment runs. This means the hit count can never exceed 2, regardless of how many times the same query is searched.

Test evidence: `test_increment_popular_search_increments_existing` calls `increment_popular_search("????")` three times and expects `hit_count == 3`, but gets `hit_count == 2` (scripts/_tmp_pytest_run.txt line 295-297).

The bug: `update_or_create` applies `defaults` on both INSERT and UPDATE paths. On UPDATE, it sets `hit_count=1` (overwriting), then the `if not created:` block increments to 2. So every call after the first yields hit_count=2, never 3+.

**Evidence:**

- `src/backend/apps/search/services/popular_search.py` lines 37-45:
  ```python
  obj, created = PopularSearch.objects.update_or_create(
      query_normalized=normalized,
      defaults={"query": query, "hit_count": 1},
  )
  if not created:
      PopularSearch.objects.filter(pk=obj.pk).update(
          hit_count=F("hit_count") + 1,
          query=query,
      )
  ```
- Test output line 293-297:
  ```
  FAILED ...test_increment_popular_search_increments_existing
  assert 2 == 3
  ```

**Recommendation:**

Use `get_or_create` instead of `update_or_create`, or move `hit_count` out of `defaults` and only set it on creation. Example fix:
```python
obj, created = PopularSearch.objects.get_or_create(
    query_normalized=normalized,
    defaults={"query": query, "hit_count": 1},
)
if not created:
    PopularSearch.objects.filter(pk=obj.pk).update(
        hit_count=F("hit_count") + 1,
        query=query,
    )
```

Effort: trivial. Priority: recommended (mandatory � incorrect analytics/metrics).

---

### SRH-005: Alert query hardcodes Bosnian?Russian translation for all saved searches

| Field | Value |
|-------|-------|
| **ID** | SRH-005 |
| **Severity** | HIGH |
| **Type** | SPEC-DEVIATION |
| **Affected Modules** | src/backend/apps/search/services/alert_query.py:50, src/backend/apps/search/views/search.py:94-97, src/backend/apps/search/services/query_translator.py:86,170 |
| **Classification** | mandatory |

**Description:**

`find_matching_ads` in `alert_query.py` (line 50) always calls `translate_query_bs_to_ru(saved_search.query)`, which hardcodes `source="bs"` (Bosnian) and `target="ru"` (Russian). This assumes all saved search queries are in Bosnian.

The web search view (`search.py` lines 94-97) is more correct: it uses the generic `translate_query(query, query_language, "ru")` which respects `request.LANGUAGE_CODE` as the source language. But saved searches don't store the user's language preference at creation time, so even the generic function can't be used without additional changes.

If a Russian-speaking user saves a search with a Russian query, `translate_query_bs_to_ru` will try to translate it **from** Bosnian **to** Russian, potentially producing garbage or failing (returning the original, which happens to be correct in this case, but the translation attempt wastes time and may cause circuit-breaker trips).

Test evidence: `test_returns_matching_ads_by_query` and `test_excludes_non_matching_ads` fail with `Warning: Translation failed for query '?????????'` in logs (scripts/_tmp_pytest_run.txt lines 185-190), because the translator attempts to translate an already-Russian query from Bosnian.

**Evidence:**

- `src/backend/apps/search/services/alert_query.py` line 50:
  ```python
  translated_query = translate_query_bs_to_ru(saved_search.query)
  ```
- `src/backend/apps/search/views/search.py` lines 94-97: web search view uses `translate_query(query, query_language, "ru")` (correct).
- Test output lines 179-190: two alert query tests fail; log shows "Translation failed for query '?????????'".

**Recommendation:**

Store the user's language preference on the `SavedSearch` model (or infer it from the user profile) and use `translate_query(saved_search.query, source_locale, "ru")` instead of `translate_query_bs_to_ru`. If no language is stored, use `translate_query` with the user's preferred language or default to Bosnian only for Bosnian-speaking users.

Effort: medium. Priority: recommended.

---

### SRH-006: save_search_modal.html references non-existent URL names

| Field | Value |
|-------|-------|
| **ID** | SRH-006 |
| **Severity** | HIGH |
| **Type** | RUNTIME-ERROR |
| **Affected Modules** | src/backend/templates/search/partials/save_search_modal.html:6,14, src/backend/apps/search/urls.py:9-11 |
| **Classification** | mandatory |

**Description:**

The template `save_search_modal.html` references two URL names that do not exist in the search app's URL configuration:

- Line 6: `{% url 'search:list' %}` � should be `search:search` (the URL name for `/search/`)
- Line 14: `{% url 'search:save-search' %}` � no such URL is defined anywhere

The URL config (`src/backend/apps/search/urls.py`) only defines:
```python
path("search/", search, name="search"),
path("api/search/autocomplete", autocomplete, name="autocomplete"),
```

Rendering this template would raise `django.urls.exceptions.NoReverseMatch` at template-compilation time.

**Evidence:**

- `src/backend/templates/search/partials/save_search_modal.html` lines 6, 14.
- `src/backend/apps/search/urls.py` lines 9-11: only `search` and `autocomplete` URL names defined.

**Recommendation:**

Either implement the missing URL endpoints (`search:list` and `search:save-search`) with corresponding views, or fix the template to reference existing URL names. The plan file `.ai/plans/02/Saved Search Alerts/plan.md` (lines 651, 659) also references these same incorrect URL names, suggesting the endpoints were planned but never implemented.

Effort: medium. Priority: recommended (mandatory � template component broken).

---

### SRH-007: Rate limiter cache not isolated between tests (test isolation issue)

| Field | Value |
|-------|-------|
| **ID** | SRH-007 |
| **Severity** | LOW |
| **Type** | RUNTIME-ERROR |
| **Affected Modules** | src/backend/apps/search/tests/test_autocomplete.py:170-244, src/backend/apps/search/services/rate_limit.py |
| **Classification** | advisory |

**Description:**

The rate limiter uses Django's cache framework (`cache.add`, `cache.incr`) with a per-IP key. The test `test_autocomplete_rate_limit` correctly calls `cache.clear()` before its 31-request loop. However, the subsequent tests `test_autocomplete_deduplication`, `test_autocomplete_anonymous_user_returns_popular_and_entities`, and `test_autocomplete_malicious_query_sanitized` do NOT clear the cache, so they inherit the rate-limit counter from 127.0.0.1 (which has already been exhausted to 31 requests by the prior test).

All three tests fail with HTTP 429 (Too Many Requests) instead of 200.

**Evidence:**

- Test output lines 272-291: three autocomplete tests fail with `assert 429 == 200`.
- `src/backend/apps/search/tests/test_autocomplete.py`: only `test_autocomplete_rate_limit` (line 175) calls `cache.clear()`; the other three tests don't.
- `src/backend/apps/search/services/rate_limit.py` lines 44-58: rate limit uses cache with 60-second window.

**Recommendation:**

Add a `cache.clear()` fixture to the test class or individual tests that use the autocomplete endpoint, or use `pytest-django`'s `cache` fixture to flush cache between tests. In production, the rate limiter works correctly � this is purely a test isolation issue.

Effort: trivial. Priority: recommended.

---

### SRH-008: Translation cache invalidation function defined but never called

| Field | Value |
|-------|-------|
| **ID** | SRH-008 |
| **Severity** | LOW |
| **Type** | BEST-PRACTICE |
| **Affected Modules** | src/backend/apps/search/services/query_translator.py:146-149 |
| **Classification** | advisory |

**Description:**

`invalidate_translation_cache()` is defined at `query_translator.py` line 146 with a docstring stating "Invalidate the translation caches for both legacy and generic translators." It clears both `translate_cached` (LRU maxsize=128) and `translate_cached_generic` (LRU maxsize=256) caches.

However, `invalidate_translation_cache` is **never called** anywhere in the codebase. A grep confirms it only appears in its own definition, its docstring, and the structural index JSON files. This means stale translations persist indefinitely in the LRU cache until the process restarts.

**Evidence:**

- `src/backend/apps/search/services/query_translator.py` lines 146-149: function defined.
- Grep for `invalidate_translation_cache` across the codebase: only matches in `query_translator.py` (definition and docstring) and `.ai/structure/back/py_map.json`, `py_anchors.json` (structural index, not runtime references).

**Recommendation:**

Either wire `invalidate_translation_cache()` into the appropriate lifecycle hooks (e.g., call it when translation settings change, or expose it as a management command for manual cache clearing), or remove the dead code if cache invalidation is not needed. The LRU cache could return stale translations if the translation service improves or changes behavior.

Effort: small. Priority: advisory.

---

### SRH-009: No search latency or translation success observability

| Field | Value |
|-------|-------|
| **ID** | SRH-009 |
| **Severity** | LOW |
| **Type** | BEST-PRACTICE |
| **Affected Modules** | src/backend/apps/search/views/search.py, src/backend/apps/search/services/query_translator.py |
| **Classification** | advisory |

**Description:**

The search view records a `SEARCH_PERFORMED` analytics event (line 116-119) but does not measure or record:

1. **Search execution latency** � the time from query receipt to response rendering (inclusive of translation + FTS execution + pagination).
2. **Translation success/failure ratio** � whether the query was translated or fell back to the original.
3. **FTS match count** � how many ads matched (useful for identifying poor recall).

The translation service has a 500ms timeout (`TRANSLATION_TIMEOUT_SECONDS`) but logs only at `debug`/`info`/`warning` level � there are no metrics (counters/histograms) emitted for monitoring.

The audit phase task (�5g, �5i) and severity taxonomy (�8, LOW: "No observability on translation success ratio") explicitly call for search latency and translation success metrics.

**Evidence:**

- `src/backend/apps/search/views/search.py` lines 116-119: only records `AnalyticsEvent` with `SEARCH_PERFORMED`, no latency or outcome data.
- `src/backend/apps/search/services/query_translator.py`: logs translation success/failure but no metrics emitted (only `logger.debug`/`logger.info`/`logger.warning`).
- Grep for `latency`, `duration`, `metrics`, `histogram`, `timer` in search app: only matches are `timezone` imports and docstring text.

**Recommendation:**

Add structured logging or metrics for: (1) search query execution time (e.g., `logger.info("search_latency_ms=%d", elapsed_ms)`), (2) translation outcome (translated vs. fallback), and (3) result count. Use Django's logging or integrate with a metrics library (e.g., Prometheus `django-prometheus`) if the project adopts one.

Effort: small. Priority: recommended.

---

### SRH-010: No max query length validation on search view entry point

| Field | Value |
|-------|-------|
| **ID** | SRH-010 |
| **Severity** | MEDIUM |
| **Type** | BEST-PRACTICE |
| **Affected Modules** | src/backend/apps/search/views/search.py:48, src/backend/apps/search/services/popular_search.py:37, src/backend/apps/search/services/search_history.py:45, src/backend/apps/search/models.py:13-14,34 |
| **Classification** | advisory |

**Description:**

The search view (`search.py` line 48) accepts the raw `q` GET parameter with only `.strip()` � no length validation or truncation. The query is then:

1. Passed to `SearchQuery()` for FTS � PostgreSQL handles long queries but performance degrades.
2. Passed to `increment_popular_search(query)` � which writes to `PopularSearch.query` (`CharField(max_length=200)`) and `PopularSearch.query_normalized` (`CharField(max_length=200)`). A query longer than 200 characters would raise `psycopg.DataError: value too long for type character varying(200)`.
3. Passed to `record_search_history(request.user.id, query)` � which writes to `SearchHistory.query` (`CharField(max_length=200)`).

The autocomplete endpoint sanitizes queries to 2-100 chars (`sanitize_autocomplete_query`), but the main search view has no equivalent guard. A malicious or buggy client could submit a query >200 chars, causing an unhandled `DataError` ? HTTP 500.

**Evidence:**

- `src/backend/apps/search/views/search.py` line 48: `query = (request.GET.get("q") or "").strip()` � no length check.
- `src/backend/apps/search/services/popular_search.py` line 37: `PopularSearch.objects.update_or_create(query_normalized=normalized, defaults={"query": query, ...})` � writes raw query.
- `src/backend/apps/search/models.py` lines 13-14: `query = models.CharField(max_length=200, db_index=True)`.
- `src/backend/apps/search/services/search_history.py` line 45: `SearchHistory.objects.create(query=query, ...)` � writes raw query.
- `src/backend/apps/search/models.py` line 34: `query = models.CharField(max_length=200)`.

**Recommendation:**

Add a `MAX_QUERY_LENGTH` constant and truncate/validate the query at the search view entry point before passing it to services. The truncated query should be used consistently for FTS, popular search recording, and history recording. A reasonable limit: 200 chars (matching the model field), or 100 chars (matching the autocomplete sanitizer).

Effort: trivial. Priority: recommended.

---

### SRH-011: Alert query test fixtures use default description containing the search term (test bug)

| Field | Value |
|-------|-------|
| **ID** | SRH-011 |
| **Severity** | LOW |
| **Type** | BEST-PRACTICE |
| **Affected Modules** | src/backend/apps/search/tests/test_alert_query.py:116-142 |
| **Classification** | advisory |

**Description:**

The `_create_published_ad` helper in `test_alert_query.py` (line 93-105) uses a default description "????????? ??????? ????????? ? ??????? ?????????" for all ads. This description contains "?????????" � the same term used as the FTS search query in `test_returns_matching_ads_by_query` and `test_excludes_non_matching_ads`.

As a result:
- `test_returns_matching_ads_by_query` creates two ads � "??????? ?????????" and "?????? ??????????" � both with the default description containing "?????????". The FTS query "?????????" matches **both** ads (title + description), returning 2 instead of the expected 1.
- `test_excludes_non_matching_ads` creates one ad "?????? ??????????" with the default description "????????? ??????? ?????????...". The query "?????????" matches the description, returning 1 instead of the expected 0.

The test failures (scripts/_tmp_pytest_run.txt lines 179-190) are caused by the fixture, not by the production code. The FTS search is correctly finding ads whose description contains the search term.

**Evidence:**

- `src/backend/apps/search/tests/test_alert_query.py` lines 93-105: default description contains "?????????".
- Test output lines 179-190: `assert 2 == 1` and `assert 1 == 0`.

**Recommendation:**

Fix the test fixtures to use a generic description that does not contain the search term (e.g., "???????? ??????"), or use per-test custom descriptions. This is a test-only fix; the production FTS logic is correct.

Effort: trivial. Priority: recommended.

---

## Summary

| Severity | Count |
|----------|-------|
| CRITICAL | 2 |
| HIGH | 3 |
| MEDIUM | 2 |
| LOW | 4 |
| **Total** | **11** |

| Classification | Count |
|----------------|-------|
| mandatory | 6 |
| advisory | 5 |
| **Total** | **11** |

Note: SRH-007, SRH-008, SRH-009, SRH-010, SRH-011 are classified as advisory. SRH-001 through SRH-006 are classified as mandatory.

## Mandatory Fixes

1. **SRH-001** � Update `SEARCH_VECTOR_FN_SQL` in a new migration to include i18n fields (`title_bs`, `description_bs` with `simple` config; `title_en`, `description_en` with `english` config), matching `docs/02-database/db-indexes.md`.
2. **SRH-002** � Add backfill `RunSQL` in the same new migration to populate `search_vector` and `category_name` for existing rows.
3. **SRH-003** � Replace `TelegramForbidden` with `TelegramForbiddenError` in `send_alerts.py` and update `.ai/plans/02/Saved Search Alerts/plan.md`.
4. **SRH-004** � Replace `update_or_create` with `get_or_create` in `popular_search.py` to fix hit_count reset bug.
5. **SRH-005** � Store user language preference on `SavedSearch` model and use `translate_query(query, source_locale, "ru")` instead of `translate_query_bs_to_ru` in alert query path.
6. **SRH-006** � Implement `search:list` and `search:save-search` URL endpoints with views, or fix template URL references.

## Advisory Recommendations

1. **SRH-007** � Add `cache.clear()` fixture to autocomplete tests for proper test isolation.
2. **SRH-008** � Wire `invalidate_translation_cache()` into lifecycle hooks or remove the dead code.
3. **SRH-009** � Add latency and translation success/failure metrics to search view and translator service.
4. **SRH-010** � Add max query length validation (truncate/validate) at search view entry point.
5. **SRH-011** � Fix test fixtures in `test_alert_query.py` to use descriptions that don't contain the search term.

## Doc Updates Needed

1. **SRH-001** � `docs/02-database/db-indexes.md` (lines 55-76): The documented multi-language SQL is correct; the code needs to be updated to match. No doc change needed � fix the code.
2. **SRH-003** � `.ai/plans/02/Saved Search Alerts/plan.md` (lines 485, 618, 787): Update `TelegramForbidden` ? `TelegramForbiddenError` in the plan.
3. **SRH-006** � `.ai/plans/02/Saved Search Alerts/plan.md` (lines 651, 659): Either implement the planned `search:list` and `search:save-search` endpoints, or update the plan to reflect the actual URL names (`search:search`).

---

## Notes on Verified-Correct Behavior

The following aspects of search were verified as correct and do **not** generate findings:

- **Visibility gating (�5a):** Search view (`search.py` line 49) filters `Ad.objects.filter(status=AdStatus.PUBLISHED)`, identical to the listings view (`listings.py` line 250). DECLINED sellers' ads remain PUBLISHED (correct per spec). Withdrawn sellers' ads are soft-deleted to `DELETED` status (excluded correctly). No separate consent filter is applied that would wrongly hide DECLINED sellers' ads.
- **Category subtree expansion (�5e):** Both the URL parameter path (line 57-60) and the fuzzy category match path (line 104-107) correctly expand to descendants via `get_descendants(include_self=True)`.
- **Injection safety (�5d):** All FTS queries use Django's parameterized `SearchQuery`/`SearchRank` API. No raw SQL interpolation. `sanitize_autocomplete_query` strips SQL metacharacters.
- **Pagination (�5f):** Both views use `Paginator(ads, 24)`. Search view `tests.py` pagination tests all pass.
- **PII in logs (�5h):** `sanitize_query_for_log` truncates to 100 chars and strips control characters. Log line (line 134) uses sanitized query.
- **Translation fallback (�5c):** `translate_query` and `translate_query_bs_to_ru` both implement timeout (500ms), circuit-breaker, and fallback to original query. Tests in `test_query_translator.py` all pass.
- **Search trigger (�5b):** All 7 tests in `test_search_triggers.py` pass, confirming the trigger fires correctly on INSERT/UPDATE for Russian content.

