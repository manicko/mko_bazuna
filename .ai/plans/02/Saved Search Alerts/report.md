# Saved Search Alerts — Implementation Verification Report

**Plan:** `.ai/plans/02/Saved Search Alerts/plan.md`
**Date:** July 29, 2026
**Scope:** Verify plan tasks T1–T8 + Pydantic schemas against actual codebase.
**Verdict:** **PARTIALLY IMPLEMENTED** — 2 of 10 plan items exist in code; 8 are missing or differ significantly from the plan specification.

---

## Summary

| Task | Plan File | Status | Notes |
|------|-----------|--------|-------|
| T1 | `apps/search/models/saved_search.py` | ⚠️ Partial | Models exist in `models.py` (not `models/` package); fields/indexes differ from plan |
| T2 | `apps/core/enums.py` (AdvisoryLockId) | ❌ Not implemented | `ALERT_DELIVERY_TASK` absent; ID 8 already taken by `ROLLUP_DAILY_METRICS` |
| T3 | `apps/search/services/alert_query.py` | ⚠️ Partial | File exists; implementation differs from plan (no translation, no ranking, no limit, different dedup) |
| T4 | `apps/core/enums.py` (AnalyticsEventType) | ❌ Not implemented | `SEARCH_ALERT_MATCHED` absent from enum |
| T5 | `telegram_bot/states.py` + `handlers/alerts.py` | ❌ Not implemented | `SavedSearchState` absent; `alerts.py` does not exist; `alerts_router` not exported |
| T6 | `apps/search/management/commands/send_alerts.py` | ❌ Not implemented | No `management/` directory in search app |
| T7 | `templates/search/partials/save_search_modal.html` | ❌ Not implemented | No `templates/search/` directory |
| T8 | `telegram_bot/main.py` | ❌ Not implemented | `alerts_router` not imported or registered |
| Schemas | `telegram_bot/schemas/saved_search.py` | ❌ Not implemented | File does not exist |

---

## Detailed Findings

### T1: SavedSearch & SavedSearchNotification Models

**Plan specifies:**
- File at `src/backend/apps/search/models/saved_search.py`
- `src/backend/apps/search/models/__init__.py` exporting both models
- `help_text` on all fields
- Index `IX_saved_searches_user_active` on `[user_id, is_active]`
- `related_name="saved_searches"` on city and category FKs
- Unique constraint named `unique_saved_search_ad`
- Index `IX_saved_search_notifications_search` on `saved_search_id`
- New migration `0002_saved_search_models.py`

**Actual code:**
- Models are in `src/backend/apps/search/models.py` (single file, **not** a `models/` package directory). No `models/__init__.py` exists.
- Both `SavedSearch` and `SavedSearchNotification` are defined with the same core fields.
- **Missing `help_text`** on all fields (plan specifies extensive help_text).
- **No indexes** on `SavedSearch` (plan specifies `IX_saved_searches_user_active`).
- **No `related_name`** on city/category FKs (plan specifies `related_name="saved_searches"`).
- Unique constraint named `uq_saved_search_ad` (plan specifies `unique_saved_search_ad`).
- **No indexes** on `SavedSearchNotification` (plan specifies `IX_saved_search_notifications_search`).
- Models already exist in migration `0001_initial.py` — no `0002` migration is needed or exists.
- `__str__` methods use different format strings than the plan.

**Classification:** `SPEC-DEVIATION` — Models exist but deviate from the plan specification in field metadata, indexes, constraint names, and file structure.

---

### T2: AdvisoryLockId Extension

**Plan specifies:**
- Add `ALERT_DELIVERY_TASK = 8` to `AdvisoryLockId` enum in `apps/core/enums.py`.
- Rationale: "first available ID after existing Phase 4/Phase 2 jobs".

**Actual code:**
- `AdvisoryLockId` enum in `src/backend/apps/core/enums.py` has IDs 1–8 and 100–101.
- **ID 8 is already taken** by `ROLLUP_DAILY_METRICS = 8`.
- `ALERT_DELIVERY_TASK` does **not** exist in the enum.
- The next available ID is **9** (not 8 as the plan assumes).

**Classification:** `SPEC-DEVIATION` — The plan's assumption that ID 8 is available is incorrect. The plan must be corrected to use ID 9 (or another available ID).

---

### T3: AlertQueryService

**Plan specifies:**
- File at `src/backend/apps/search/services/alert_query.py`
- `find_matching_ads()` with:
  - `translate_query_bs_to_ru` for Bosnian→Russian translation
  - `SearchRank` + `order_by("-rank")` for ranking
  - `Exists`/`OuterRef` subquery for deduplication
  - `list(ads[:10])` limit (max 10 per digest)
  - Lazy import of `Ad` inside function
  - `category.get_descendants()` called on FK directly with `except Exception: return []`
- `record_notifications()` handling both `Ad` objects and int IDs

**Actual code:**
- File exists at `src/backend/apps/search/services/alert_query.py`.
- Both `find_matching_ads()` and `record_notifications()` are defined.
- **Does NOT import or use `translate_query_bs_to_ru`** — the query is used directly without translation. This is a behavioral difference: Bosnian queries will not be translated to Russian for FTS matching.
- **Does NOT use `SearchRank` or `order_by("-rank")`** — results are unordered. The plan's ranking is absent.
- **Does NOT use `Exists`/`OuterRef`** — uses `values_list("ad_id", flat=True)` + `exclude(pk__in=notified_ad_ids)` instead. This is a less efficient pattern (materializes all notified ad IDs into a list before filtering) compared to the plan's correlated subquery.
- **No limit of 10** — returns `list(queryset)` without slicing. The plan's `[:10]` digest limit is absent.
- Imports `Ad`, `Category`, `AdStatus`, `SavedSearch`, `SavedSearchNotification` at module level (plan uses lazy import for `Ad`).
- Uses `Category.objects.get(pk=category.pk).get_descendants()` instead of `category.get_descendants()` directly.
- Uses `if category is not None:` guard instead of `try/except Exception: return []`.
- `record_notifications()` uses `SavedSearchNotification(saved_search=saved_search, ad=ad)` directly (no int-ID handling).
- `record_notifications()` returns `len(created)` (actual count from `bulk_create`) instead of `len(ads)` as the plan specifies.
- Imports `from apps.search.models import ...` (not `from apps.search.models.saved_search import ...` as the plan specifies).

**Classification:** `SPEC-DEVIATION` — The service exists but deviates from the plan in translation, ranking, deduplication strategy, result limiting, and import paths.

---

### T4: AnalyticsEventType Extension

**Plan specifies:**
- Add `SEARCH_ALERT_MATCHED = "search_alert_matched"` to `AnalyticsEventType` in `apps/core/enums.py`.

**Actual code:**
- `AnalyticsEventType` enum exists in `src/backend/apps/core/enums.py` with 15 event types.
- `SEARCH_ALERT_MATCHED` is **not present**.
- The enum has: `REGISTRATION_CREATED`, `AD_PUBLISHED`, `SEARCH_PERFORMED`, `CONTACT_INITIATED`, `AD_VIEWED`, `CONTACT_RESPONSE`, `SELLER_VERIFIED`, `TRUST_LEVEL_UPDATED`, `MODERATION_APPROVED`, `MODERATION_REJECTED`, `MODERATION_FLAGGED`, `DASHBOARD_VIEWED`, `AD_EDITED`, `AD_REACTIVATED`, `CONTACT_COMPLETED`, `AD_REPORTED`.

**Classification:** `SPEC-DEVIATION` — The enum value is missing.

---

### T5: Bot Handler for /alerts Command

**Plan specifies:**
- `src/telegram_bot/states.py` — Add `SavedSearchState` StrEnum with 6 states
- `src/telegram_bot/handlers/alerts.py` — New handler with `/alerts` command, `AlertForm` StatesGroup, `get_user_saved_searches()` helper
- `src/telegram_bot/handlers/__init__.py` — Export `alerts_router`

**Actual code:**
- `states.py` exists at `src/telegram_bot/states.py` but contains **only** `AdCreateState` (7 states for ad creation). `SavedSearchState` is **not present**.
- `handlers/alerts.py` **does not exist**.
- `handlers/__init__.py` exists and exports only `login_router` and `ad_create_router`. `alerts_router` is **not exported**.

**Classification:** `SPEC-DEVIATION` — The handler file and state enum are entirely missing.

---

### T6: AlertDeliveryCommand

**Plan specifies:**
- File at `src/backend/apps/search/management/commands/send_alerts.py`
- Management command with `--dry-run` flag, advisory lock, FTS matching, Telegram delivery, analytics recording.

**Actual code:**
- The file **does not exist**.
- The `src/backend/apps/search/` directory has **no `management/` directory** at all.
- No `send_alerts` command is registered anywhere in the codebase.

**Classification:** `SPEC-DEVIATION` — The management command is entirely missing.

---

### T7: Modal Template

**Plan specifies:**
- File at `src/backend/templates/search/partials/save_search_modal.html`
- HTMX-compatible modal with query, city, category, and price fields.

**Actual code:**
- The file **does not exist**.
- There is **no `templates/search/` directory** in the backend.
- The search app's `urls.py` only defines one route: `path("search/", search, name="search")`. There is **no `save-search` URL endpoint** as the plan's template references (`{% url 'search:save-search' %}`).

**Classification:** `SPEC-DEVIATION` — The template and its supporting URL endpoint are entirely missing.

---

### T8: Router Registration

**Plan specifies:**
- In `src/telegram_bot/main.py`, change line 45 to import `alerts_router` and add `dp.include_router(alerts_router)` at line 48.

**Actual code:**
- `main.py` exists at `src/telegram_bot/main.py`.
- Line 45: `from telegram_bot.handlers import login_router, ad_create_router` (no `alerts_router`).
- Lines 47–48: Only `login_router` and `ad_create_router` are included. `alerts_router` is **not** imported or registered.

**Classification:** `SPEC-DEVIATION` — The router is not wired into the bot.

---

### Pydantic Schemas

**Plan specifies:**
- File at `src/telegram_bot/schemas/saved_search.py`
- `SavedSearchQueryPayload` and `SavedSearchPricePayload` Pydantic v2 models.

**Actual code:**
- The file **does not exist**.
- The `src/telegram_bot/schemas/` directory exists with `message_payloads.py` and `__init__.py`, but no `saved_search.py`.
- The existing `message_payloads.py` follows the Pydantic v2 + `Annotated` + `Field` pattern that the plan's schemas would follow, but the saved search DTOs are not present.

**Classification:** `SPEC-DEVIATION` — The Pydantic schemas are entirely missing.

---

## Dependency Chain Verification

All dependencies referenced by the plan exist in the codebase:

| Dependency | Exists? | Location |
|------------|---------|----------|
| `apps.search.services.query_translator.translate_query_bs_to_ru` | ✅ | `src/backend/apps/search/services/query_translator.py:86` |
| `apps.ads.models.Ad` | ✅ | `src/backend/apps/ads/models.py:18` |
| `apps.core.enums.AdStatus` | ✅ | `src/backend/apps/core/enums.py:35` |
| `apps.core.utils.advisory_lock.advisory_lock` | ✅ | `src/backend/apps/core/utils/advisory_lock.py:18` |
| `apps.analytics.models.AnalyticsEvent` | ✅ | `src/backend/apps/analytics/models.py:11` |
| `apps.core.enums.AdvisoryLockId` | ✅ | `src/backend/apps/core/enums.py:20` |
| `apps.core.enums.AnalyticsEventType` | ✅ | `src/backend/apps/core/enums.py:53` |
| `apps.search.models.SavedSearch` | ✅ | `src/backend/apps/search/models.py:37` |
| `apps.search.models.SavedSearchNotification` | ✅ | `src/backend/apps/search/models.py:55` |
| `apps.users.models.User` | ✅ | `src/backend/apps/users/models.py:12` |
| `apps.categories.models.Category` | ✅ | `src/backend/apps/categories/models.py:12` (MPTTModel) |
| `apps.locations.models.City` | ✅ | Referenced via FK in SavedSearch |

**No circular dependencies or missing dependency chains detected.** The plan's dependency DAG is sound; the issue is that most tasks were not executed.

---

## Verification Checklist Status

| Check | Status | Evidence |
|-------|--------|----------|
| `migrate` runs successfully | ⚠️ Cannot verify (no DB) | Migration `0001_initial.py` includes SavedSearch models |
| `select_related`/`prefetch_related` prevent N+1 | ⚠️ Partial | `find_matching_ads` does not use `select_related`; `find_matching_ads` in plan would use it |
| `is_active=False` excluded from delivery | ❌ | `send_alerts.py` does not exist |
| Ads in `SavedSearchNotification` excluded | ✅ | `alert_query.py` uses `exclude(pk__in=notified_ad_ids)` |
| Telegram handler fails gracefully without `chat_id` | ❌ | `alerts.py` does not exist; `User.chat_id` is `NOT NULL` (no null check needed at model level) |
| Management command logs total sent count | ❌ | `send_alerts.py` does not exist |
| Modal template submits via HTMX | ❌ | Template does not exist; no `save-search` URL |
| Advisory lock prevents concurrent runs | ❌ | `ALERT_DELIVERY_TASK` not added; `send_alerts.py` does not exist |
| `SEARCH_ALERT_MATCHED` event recorded | ❌ | Enum value not added; `send_alerts.py` does not exist |

---

## Key Issues

### 1. AdvisoryLockId ID Collision (T2)
The plan specifies `ALERT_DELIVERY_TASK = 8`, but `ROLLUP_DAILY_METRICS = 8` already occupies that ID. This is a **plan error** — the next available ID is 9.

### 2. Translation Not Applied in AlertQueryService (T3)
The plan's `find_matching_ads` calls `translate_query_bs_to_ru(saved_search.query)` before FTS search. The actual implementation uses `saved_search.query` directly without translation. This means Bosnian-language saved search queries will not match Russian-language ad content in the FTS index, producing incorrect results.

### 3. No Result Ranking or Limiting (T3)
The plan uses `SearchRank` + `order_by("-rank")` and limits to 10 results. The actual implementation has no ranking and no limit. This affects both result quality (unranked results) and Telegram message size (no 10-ad cap).

### 4. No Web UI Integration (T7, T8)
The plan specifies a modal template and a `save-search` URL endpoint. Neither exists. Users cannot create saved searches from the web interface.

### 5. No Bot /alerts Handler (T5)
The plan specifies a `/alerts` command handler. It does not exist. Users cannot manage saved searches from Telegram.

### 6. No Delivery Command (T6)
The plan specifies a `send_alerts` management command. It does not exist. No daily alert delivery occurs.

### 7. No Analytics Event (T4)
The `SEARCH_ALERT_MATCHED` analytics event type is not in the enum. Even if the delivery command existed, it could not record the event.

### 8. No Pydantic Schemas (Schemas)
The `SavedSearchQueryPayload` and `SavedSearchPricePayload` DTOs do not exist. Bot input validation for saved search creation is not implemented.

### 9. Model Structural Differences (T1)
The plan specifies a `models/` package directory with `saved_search.py` and `__init__.py`. The actual code uses a single `models.py` file. Additionally, the plan specifies indexes, `help_text`, and `related_name` values that are absent from the actual model definitions.

### 10. Deduplication Strategy Difference (T3)
The plan uses a correlated `Exists`/`OuterRef` subquery for deduplication. The actual implementation uses `values_list` + `exclude(pk__in=...)`, which materializes all notified ad IDs into memory before filtering. For saved searches with many notified ads, this could be a performance concern.

---

## Rollout Analysis

**Risk:** HIGH — The plan describes a complete feature (models, service, bot handler, management command, web UI, schemas, router wiring). Only 2 components (models and service) partially exist. The remaining 8 components are entirely missing.

**Dependencies:** All referenced dependencies exist and are sound. No circular dependencies.

**Rollout ordering:** The plan's DAG is correct. T4 (AnalyticsEventType) and T2 (AdvisoryLockId) should be done first as they have no dependencies. T1 (Models) depends on T4 and T2. T3 (Service) depends on T1. T6 (Command) depends on T1 and T3. T5 (Bot Handler) depends on T1. T8 (Router) depends on T5. T7 (Template) is parallel.

**Migration safety:** The SavedSearch models already exist in `0001_initial.py`. No new migration is needed for T1. If the plan's model changes (indexes, help_text, related_name) are applied, a new migration would be required.

**Backward compatibility:** Adding new enum values, a new management command, a new bot handler, and a new template are all backward-compatible. The `ALERT_DELIVERY_TASK` advisory lock ID must not collide with existing IDs (use 9, not 8).

---

## Required Fixes

1. **T2:** Add `ALERT_DELIVERY_TASK = 9` (not 8) to `AdvisoryLockId` enum.
2. **T4:** Add `SEARCH_ALERT_MATCHED = "search_alert_matched"` to `AnalyticsEventType` enum.
3. **T1:** Reconcile model definitions with the plan (indexes, help_text, related_name, constraint names) or update the plan to match the actual code.
4. **T3:** Reconcile `find_matching_ads` with the plan (add `translate_query_bs_to_ru`, `SearchRank`, `order_by("-rank")`, `[:10]` limit, `Exists`/`OuterRef` subquery) or update the plan to match the actual code.
5. **T5:** Create `handlers/alerts.py`, add `SavedSearchState` to `states.py`, export `alerts_router` from `handlers/__init__.py`.
6. **T6:** Create `management/commands/send_alerts.py`.
7. **T7:** Create `templates/search/partials/save_search_modal.html` and add `save-search` URL endpoint.
8. **T8:** Import and register `alerts_router` in `main.py`.
9. **Schemas:** Create `schemas/saved_search.py` with Pydantic DTOs.

---

## Advisory Recommendations

1. **T3 deduplication:** The plan's `Exists`/`OuterRef` subquery approach is more efficient than the actual `values_list` + `exclude(pk__in=...)` approach. Consider adopting the plan's approach for large datasets.
2. **T3 translation:** The actual code does not translate queries. If the plan's behavior is desired, `translate_query_bs_to_ru` must be integrated. Note that the existing `search/views/search.py` uses the generic `translate_query` function (not `translate_query_bs_to_ru`), so the service should be consistent with the web search layer.
3. **T1 model structure:** The plan specifies a `models/` package directory. The existing code uses a single `models.py`. Converting to a package would require moving `PopularSearch` and `SearchHistory` as well. Consider whether the plan's structure is necessary or whether the plan should be updated to match the existing single-file structure.
4. **T7 URL endpoint:** The plan's template references `{% url 'search:save-search' %}`, but no such URL exists in `search/urls.py`. A view and URL must be created to handle the form submission.
5. **T6 transaction scope:** The plan's `send_alerts.py` uses `advisory_lock` with `session=False` (transaction-scoped). The `advisory_lock` utility documentation states that transaction-scoped locks require the entire operation to be wrapped in `transaction.atomic()`. The plan's implementation does not wrap the matching + notification recording in `transaction.atomic()`, which means the lock may be released prematurely under autocommit mode.
