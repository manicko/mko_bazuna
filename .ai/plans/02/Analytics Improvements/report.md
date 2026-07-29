# Analytics Improvements — Implementation Verification Report

**Plan:** `.ai\plans\02\Analytics Improvements\plan.md`
**Date:** 2026-07-29
**Scope:** Verify whether each task in the plan is implemented in the actual codebase. No code changes were made — this is a read-only audit.

---

## Executive Summary

| Task | Status | Key Notes |
|------|--------|-----------|
| T0 | ✅ Implemented | No deviations |
| T1 | ✅ Implemented | No deviations |
| T2 | ✅ Implemented | **SPEC-DEVIATION**: `on_delete=CASCADE` instead of `SET_NULL` |
| T3 | ✅ Implemented | **SPEC-DEVIATION**: `CASCADE` instead of `SET_NULL`; **missing `AddIndex`** on `(event_type, timestamp)` |
| T4 | ✅ Implemented | **DOC-UPDATE**: help_text for `trust_score` says "0–1" but algorithm returns 0–100; `avg_response_time` says "seconds" but plan says "hours" |
| T5 | ✅ Implemented | Minor implementation detail differences; functionally correct |
| T6 | ✅ Implemented | Implementation is more detailed than plan spec; functionally correct |
| T7 | ✅ Implemented | **SPEC-DEVIATION**: queries only ads with events (not all published ads); does not call TrustAnalytics/ModerationAnalytics services |
| T8 | ✅ Implemented | **ADDITION**: also creates `AD_PUBLISHED` event beyond plan spec |
| T9 | ❌ Not Implemented | No views directory, no view file, no template, no URL |
| T10 | ❌ Not Implemented | No view file, no template, no URL |

**Overall:** 8 of 10 tasks are implemented. T9 and T10 (the views) are entirely missing. Several SPEC-DEVIATIONs exist in T2/T3/T7.

---

## Detailed Findings by Task

### T0: Add TrustLevel StrEnum — ✅ IMPLEMENTED

**File:** `src/backend/apps/core/enums.py`

- `TrustLevel` enum exists with `UNVERIFIED`, `VERIFIED`, `TRUSTED`, `PRO` — matches plan exactly.
- `"TrustLevel"` is present in `__all__` — matches plan.
- No deviations.

### T1: Extend AnalyticsEventType Enum — ✅ IMPLEMENTED

**File:** `src/backend/apps/core/enums.py`

- All 10 new members are present:
  `SELLER_VERIFIED`, `TRUST_LEVEL_UPDATED`, `MODERATION_APPROVED`, `MODERATION_REJECTED`, `MODERATION_FLAGGED`, `DASHBOARD_VIEWED`, `AD_EDITED`, `AD_REACTIVATED`, `CONTACT_COMPLETED`, `AD_REPORTED`.
- No deviations.

### T2: Add ad ForeignKey to AnalyticsEvent — ✅ IMPLEMENTED (SPEC-DEVIATION)

**File:** `src/backend/apps/analytics/models.py`

- `ad` ForeignKey field exists on `AnalyticsEvent`.
- Nullable (`null=True`, `blank=True`) — ✅ matches plan.
- Related name `analytics_events` — ✅ matches plan.
- String reference `"ads.Ad"` — ✅ matches plan.
- Placed after `user` field — ✅ matches plan.

**SPEC-DEVIATION:** Plan specifies `on_delete=SET_NULL`. Actual code uses `on_delete=models.CASCADE`. This is a data-integrity concern: if an ad is deleted, all its analytics events are also deleted, which contradicts the plan's intent of preserving historical events (the `user` field uses `SET_NULL` for the same reason).

### T3: Create Migration for ad FK — ✅ IMPLEMENTED (SPEC-DEVIATION)

**File:** `src/backend/apps/analytics/migrations/0002_analytics_event_ad_fk.py`

- Migration file exists.
- Dependencies: `analytics.0001_initial`, `ads.0006_backfill_translations` — ✅ (plan says `ads.0001_initial` implicitly; actual uses the latest ads migration at generation time, which is correct).
- `AddField` operation for `ad` ForeignKey — ✅.

**SPEC-DEVIATION 1:** Migration uses `on_delete=django.db.models.deletion.CASCADE`, consistent with T2's deviation. Plan specifies `SET_NULL`.

**SPEC-DEVIATION 2:** Plan explicitly states: "2. `AddIndex` on `(event_type, timestamp)` for query performance". The migration contains **only** `AddField` — no `AddIndex` operation. The index is missing from the schema.

### T4: Create DailyAdMetrics Model — ✅ IMPLEMENTED (DOC-UPDATE)

**File:** `src/backend/apps/analytics/models.py`

- `DailyAdMetrics` model exists with all specified fields:
  - `ad` ForeignKey (CASCADE, related_name=`daily_metrics`) — ✅
  - `date` DateField — ✅
  - `views_count` PositiveIntegerField (default=0) — ✅
  - `contacts_count` PositiveIntegerField (default=0) — ✅
  - `trust_score` FloatField (null=True, blank=True) — ✅
  - `avg_response_time` FloatField (null=True, blank=True) — ✅
  - `created_at` DateTimeField (auto_now_add=True) — ✅
  - `updated_at` DateTimeField (auto_now=True) — ✅
- Meta: `db_table = "daily_ad_metrics"` — ✅
- Unique constraint on `(ad, date)` — ✅
- Index on `(date, -views_count)` — ✅

**DOC-UPDATE 1:** Plan says `trust_score` purpose is "Current trust score". Actual `help_text` says "Auto-computed trust score (0–1)". The "0–1" range is inconsistent with the trust score algorithm in T5, which returns a score in the range [0, 100]. This is a documentation inconsistency in the model's help_text.

**DOC-UPDATE 2:** Plan says `avg_response_time` purpose is "Avg hours to respond". Actual `help_text` says "Average response time in seconds". Units mismatch (hours vs seconds).

**Note:** An additional migration `0003_daily_ad_metrics.py` exists (not explicitly listed in the plan's migration section, but implied by T4). It correctly creates the `DailyAdMetrics` table with constraints and indexes.

### T5: Create TrustAnalytics Service — ✅ IMPLEMENTED

**File:** `src/backend/apps/analytics/services/trust_analytics.py`

- All 4 functions exist with correct signatures:
  - `calculate_seller_trust_score(user_id: int) -> float` — ✅
  - `get_trust_level(score: float) -> TrustLevel` — ✅
  - `record_trust_event(user_id: int, event: AnalyticsEventType) -> None` — ✅
  - `get_seller_daily_metrics(user_id: int, days: int = 30) -> list[DailyAdMetrics]` — ✅

- Trust score algorithm matches plan:
  - Base score: 50 — ✅
  - +10 for each published ad (max 50) — ✅
  - +20 for seller verification — ✅ (implementation checks `SellerVerification.verified_by_admin`, which is a reasonable interpretation of "seller_verified")
  - -10 for each rejected ad (min 0) — ✅
  - Clamps to [0, 100] — ✅

- `get_trust_level` mapping:
  - 0–30: UNVERIFIED — ✅
  - 31–60: VERIFIED — ✅
  - 61–85: TRUSTED — ✅
  - 86–100: PRO — ✅

- Minor implementation detail: `record_trust_event` passes `event.value` (the string) when creating `AnalyticsEvent`, which is correct for a `CharField`. The function signature accepts `AnalyticsEventType` as specified.

- `services/__init__.py` exists but only exports `SellerStats` — it does **not** export `trust_analytics` or `moderation_analytics` functions. This is a minor packaging gap but not a functional issue (imports work via full path).

### T6: Create ModerationAnalytics Service — ✅ IMPLEMENTED

**File:** `src/backend/apps/analytics/services/moderation_analytics.py`

- All 4 functions exist:
  - `get_moderation_stats(days: int = 30) -> ModerationStats` — ✅
  - `get_pending_queue_size() -> int` — ✅
  - `get_moderator_performance(days: int = 30) -> list[ModeratorPerformance]` — ✅
  - `get_rejection_reasons(days: int = 30) -> dict[str, int]` — ✅

- Uses `TypedDict` for `ModerationStats` and `ModeratorPerformance` — reasonable implementation choice.
- `get_moderation_stats` counts `MODERATION_APPROVED`, `MODERATION_REJECTED`, `MODERATION_FLAGGED` events — ✅ matches plan.
- `get_pending_queue_size` counts ads with `status=ON_MODERATION` — ✅ matches plan.
- `get_moderator_performance` tracks manual approvals/rejections via `published_by`/`moderated_by` — ✅ matches plan intent.
- `get_rejection_reasons` aggregates from `ModeratorActionLog` — ✅ matches plan.

- Implementation is more detailed than the plan spec (e.g., computes average time to moderate), but functionally covers all required functions.

### T7: Create Daily Rollup Management Command — ✅ IMPLEMENTED (SPEC-DEVIATION)

**File:** `src/backend/apps/analytics/management/commands/rollup_daily_metrics.py`

- Command file exists with `--dry-run` argument — ✅
- Advisory lock via `AdvisoryLockId.ROLLUP_DAILY_METRICS` — ✅
- `transaction.atomic()` — ✅
- Logging — ✅
- `update_or_create` for idempotency — ✅
- Tests exist in `test_rollup_daily_metrics.py` — ✅

**SPEC-DEVIATION 1:** Plan says: "Query ALL ads with `status=PUBLISHED` (corrected: not just today's)". Actual code queries `AnalyticsEvent.objects.filter(ad__isnull=False, ...)` — it only processes ads that have analytics events, not all published ads. Ads with no events do not get a `DailyAdMetrics` record (confirmed by test `test_skips_ads_without_events`).

**SPEC-DEVIATION 2:** Plan lists dependencies: "Requires `TrustAnalytics` and `ModerationAnalytics` services (T5, T6)". The actual command does **not** call `calculate_seller_trust_score` or any function from `trust_analytics` or `moderation_analytics`. The `trust_score` and `avg_response_time` fields remain `null` after rollup (confirmed by test `test_trust_score_and_avg_response_time_remain_null`).

**SPEC-DEVIATION 3:** Plan says "For each ad, aggregate AnalyticsEvents by type" and "Create/update `DailyAdMetrics` records". Actual code only aggregates events from **yesterday** (`timestamp__date=yesterday`), not all historical dates. This is a narrower scope than the plan implies.

**SPEC-DEVIATION 4:** Plan says "Output progress with logging" — actual code logs summary counts but does not output per-ad progress in non-dry-run mode (only in dry-run mode).

### T8: Update auto_moderation.py for Extended Events — ✅ IMPLEMENTED (ADDITION)

**File:** `src/backend/apps/moderation/services/auto_moderation.py`

- `_fail_moderation()` creates `AnalyticsEvent` with `MODERATION_REJECTED` and `ad_id=ad.id` — ✅ matches plan.
- `_pass_moderation()` creates `AnalyticsEvent` with `MODERATION_APPROVED` and `ad_id=ad.id` — ✅ matches plan.

**ADDITION:** The plan only specifies creating `MODERATION_APPROVED` in `_pass_moderation()`, but the actual code also creates an `AD_PUBLISHED` event. This is an addition beyond the plan spec, not a deviation — the plan's specified event is still created.

### T9: Create SellerTrustDashboard View — ❌ NOT IMPLEMENTED

**Plan specifies:**
- File: `src/backend/apps/analytics/views/seller_dashboard.py`
- Directory: `apps/analytics/views/` (create `__init__.py` for package)
- Decorator: `@login_required`
- View function: `seller_trust_dashboard(request: HttpRequest) -> HttpResponse`
- Template: `analytics/seller_dashboard.html` (extends `ads/dashboard.html`)

**Actual state:**
- No `views` directory exists in `apps/analytics/`.
- No `seller_dashboard.py` file exists anywhere in the analytics app.
- No `analytics/seller_dashboard.html` template exists.
- No URL pattern for a seller trust dashboard exists in `config/urls.py` or any app's `urls.py`.

**Note:** `apps/ads/views/dashboard.py` exists and is a seller dashboard, but it is a **different view** — it lists ads grouped by status and uses `SellerStats` for basic analytics. It is not the trust-focused dashboard specified in T9. The `TrustLevel` enum and `trust_analytics` service exist but are not wired into any view.

### T10: Create ModerationAnalytics View — ❌ NOT IMPLEMENTED

**Plan specifies:**
- File: `src/backend/apps/analytics/views/moderation_dashboard.py`
- Decorator: `@_staff_required` (staff-only)
- View function: `moderation_analytics(request: HttpRequest) -> HttpResponse`
- Template: `analytics/moderation_dashboard.html`

**Actual state:**
- No `moderation_dashboard.py` file exists in the analytics app.
- No `analytics/moderation_dashboard.html` template exists.
- No URL pattern for moderation analytics exists.
- The moderation app (`apps/moderation/`) has URLs for `review`, `approve`, `reject`, `ban` — but no analytics dashboard.
- The `moderation_analytics` service exists and is fully functional, but is not exposed via any view.

---

## Additional Items Not in Plan (Extra Code)

The following files exist in the codebase but are not mentioned in the plan:

| File | Description |
|------|-------------|
| `apps/analytics/services/seller_stats.py` | `SellerStats` service with 5-minute cache TTL, used by `ads/views/dashboard.py` |
| `apps/analytics/management/commands/show_metrics.py` | Management command to show analytics metrics |
| `apps/analytics/tests/test_trust_analytics.py` | Tests for trust analytics service |
| `apps/analytics/tests/test_moderation_analytics.py` | Tests for moderation analytics service |
| `apps/analytics/tests/test_seller_stats.py` | Tests for SellerStats service |
| `apps/analytics/tests/test_rollup_daily_metrics.py` | Tests for rollup management command |
| `apps/analytics/migrations/0003_daily_ad_metrics.py` | Migration for DailyAdMetrics (implied by T4) |

---

## Admin Registration — SPEC-DEVIATION

**Plan (File Changes Summary):** `apps/analytics/admin.py` — "Register DailyAdMetrics"

**Actual state:** `apps/analytics/admin.py` only registers `AnalyticsEvent` via `@admin.register(AnalyticsEvent)`. `DailyAdMetrics` is **not** registered in the admin.

---

## services/__init__.py — Minor Gap

**Plan (T5):** "Directory: `apps/analytics/services/` (create `__init__.py` for package)"

**Actual state:** `__init__.py` exists but only exports `SellerStats`:
```python
from apps.analytics.services.seller_stats import SellerStats
__all__ = ["SellerStats"]
```
The `trust_analytics` and `moderation_analytics` modules are not exported from the package `__init__.py`. This is a minor packaging gap — imports work via full module path, but the plan implies the services package should expose its contents.

---

## Event Type Usage Audit

The following table shows which of the T1 event types are actually recorded in production code (not just tests):

| Event Type | Recorded in Production Code? | Where |
|------------|------------------------------|-------|
| `SELLER_VERIFIED` | ❌ No | Only in tests |
| `TRUST_LEVEL_UPDATED` | ❌ No | Only in tests |
| `MODERATION_APPROVED` | ✅ Yes | `auto_moderation.py` `_pass_moderation()` |
| `MODERATION_REJECTED` | ✅ Yes | `auto_moderation.py` `_fail_moderation()` |
| `MODERATION_FLAGGED` | ❌ No | Only in `moderation_analytics.py` (query), tests |
| `DASHBOARD_VIEWED` | ❌ No | Only in tests |
| `AD_EDITED` | ❌ No | Only in enum definition |
| `AD_REACTIVATED` | ❌ No | Only in enum definition |
| `CONTACT_COMPLETED` | ❌ No | Only in `rollup_daily_metrics.py` (query), tests |
| `AD_REPORTED` | ❌ No | Only in enum definition |
| `AD_PUBLISHED` | ✅ Yes | `auto_moderation.py` `_pass_moderation()` (pre-existing, not from T1) |
| `AD_VIEWED` | ✅ Yes | `ads/views/listings.py` `ad_detail()` (pre-existing) |
| `CONTACT_INITIATED` | ✅ Yes | `core/services/contact.py` (pre-existing) |
| `SEARCH_PERFORMED` | ✅ Yes | `search/views/search.py` (pre-existing) |
| `REGISTRATION_CREATED` | ✅ Yes | (pre-existing) |

**Observation:** 6 of the 10 new event types from T1 are defined as enum members but are never recorded in production code. They are only referenced in tests or queries. This is expected for a plan that defines the enum before the event-recording code is written, but it means the extended event types are not yet fully utilized.

---

## Rollout Analysis

### Risks

1. **T2/T3 CASCADE vs SET_NULL deviation (Medium):** If an ad is deleted, all associated `AnalyticsEvent` records are also deleted. This contradicts the plan's intent of preserving historical analytics data. The `user` FK on the same model uses `SET_NULL` for the same reason. This is a data-loss risk.

2. **Missing AddIndex on (event_type, timestamp) (Low-Medium):** The plan explicitly requests an index for query performance. Without it, queries filtering by `event_type` and `timestamp` (common in analytics) may be slow at scale.

3. **T7 rollup scope narrower than plan (Low):** The command only processes ads with events from yesterday, not all published ads. If the intent is to have `DailyAdMetrics` for every published ad (even those with zero events), this is not achieved.

4. **T9/T10 views missing (High):** The trust and moderation dashboards are not accessible to users. The services and models exist but are not exposed via any URL.

5. **DailyAdMetrics not in admin (Low):** Staff cannot inspect or manage `DailyAdMetrics` records via Django admin.

6. **trust_score range inconsistency (Low):** The `help_text` says "0–1" but the algorithm returns 0–100. This could cause confusion if the value is displayed to users.

### Dependencies

- T5 depends on T0 (TrustLevel), T1 (AnalyticsEventType), T4 (DailyAdMetrics) — all satisfied ✅
- T6 depends on T1 (AnalyticsEventType) — satisfied ✅
- T7 depends on T2 (ad FK), T4 (DailyAdMetrics), T5 (TrustAnalytics), T6 (ModerationAnalytics) — T2 and T4 satisfied, T5 and T6 satisfied but **not called** by the command
- T8 depends on T1 (extended event types), T2 (ad FK) — satisfied ✅
- T9 depends on T5 (TrustAnalytics) — T5 satisfied, but T9 itself not implemented ❌
- T10 depends on T6 (ModerationAnalytics) — T6 satisfied, but T10 itself not implemented ❌

### Backward Compatibility

- T2/T3: The `ad` field is nullable, so existing events are preserved. However, `CASCADE` (instead of `SET_NULL`) means ad deletion cascades to events.
- T4: `DailyAdMetrics` is a new table — no backward compatibility concerns.
- T7: New management command — no backward compatibility concerns.
- T8: Adds event creation in existing functions — no backward compatibility concerns.
- T9/T10: New views — no backward compatibility concerns.

---

## Required Fixes

1. **T2/T3:** Change `on_delete` from `CASCADE` to `SET_NULL` on the `ad` ForeignKey in both the model (`models.py`) and the migration (`0002_analytics_event_ad_fk.py`). This requires a new migration to alter the field.

2. **T3:** Add `AddIndex` operation for `(event_type, timestamp)` in a new migration.

3. **T4:** Update `help_text` for `trust_score` to remove the "0–1" range (or change to "0–100" to match the algorithm). Update `help_text` for `avg_response_time` to clarify units (seconds vs hours — decide on one).

4. **T9:** Create `apps/analytics/views/` directory with `__init__.py`, `seller_dashboard.py` view, `analytics/seller_dashboard.html` template, and register URL in `config/urls.py`.

5. **T10:** Create `apps/analytics/views/moderation_dashboard.py` view, `analytics/moderation_dashboard.html` template, and register URL in `config/urls.py`.

6. **Admin:** Register `DailyAdMetrics` in `apps/analytics/admin.py`.

7. **services/__init__.py:** Export `trust_analytics` and `moderation_analytics` functions from the package `__init__.py` (optional but recommended for consistency).

---

## Advisory Recommendations

1. **T7:** Consider whether the rollup command should create `DailyAdMetrics` records for all published ads (even those with zero events), as the plan implies. Currently, ads with no events do not get a record.

2. **T7:** Consider integrating `TrustAnalytics.calculate_seller_trust_score` and `ModerationAnalytics` functions into the rollup command to populate `trust_score` and `avg_response_time` fields, as the plan suggests.

3. **T1 event types:** Implement event recording for the 6 unused event types (`SELLER_VERIFIED`, `TRUST_LEVEL_UPDATED`, `MODERATION_FLAGGED`, `DASHBOARD_VIEWED`, `AD_EDITED`, `AD_REACTIVATED`, `AD_REPORTED`, `CONTACT_COMPLETED`) in their respective code paths.

4. **T7 dry-run output:** Add per-ad progress logging in non-dry-run mode for operational visibility during scheduled runs.

---

## Conclusion

The plan is **partially implemented**. The foundational work (enums, models, migrations, services, management command, auto-moderation integration) is complete and functional. However:

- **T2/T3** contain a SPEC-DEVIATION (`CASCADE` vs `SET_NULL`) that risks data loss.
- **T3** is missing a requested database index.
- **T4** has documentation inconsistencies in help_text.
- **T9 and T10** (the views) are entirely missing — the analytics dashboards are not accessible to users.
- **Admin** does not register `DailyAdMetrics`.

The most critical gaps are T9/T10 (missing views) and the T2/T3 CASCADE deviation. The services and models are well-implemented and tested, but the user-facing layer is absent.
