# Seller Dashboard Statistics — Implementation Verification Report

**Plan:** `.ai/plans/02/Seller Dashboard Statistics/plan.md`
**Date:** 2026-07-29
**Scope:** Verify implementation of all 8 tasks (T0–T7) against actual codebase.
**Method:** Static code inspection of source files, migrations, tests, and settings. No code was modified.

---

## Summary

| Task | Status | Notes |
|------|--------|-------|
| T0 — `AnalyticsEvent.ad` FK | ✅ IMPLEMENTED | Model field + migration match plan exactly |
| T1 — `AnalyticsEventType.AD_VIEWED` | ✅ IMPLEMENTED | Enum value present |
| T2 — `TimeRange` StrEnum | ✅ IMPLEMENTED | Enum + `__all__` export present |
| T3 — `CACHES` setting | ✅ IMPLEMENTED | LocMemCache backend matches plan |
| T4 — `SellerStats` service | ✅ IMPLEMENTED | All 4 methods present; return shape deviates (see §4) |
| T5 — `SellerStats` in DashboardView | ⚠️ PARTIALLY IMPLEMENTED | Missing `time_range_options` in context |
| T6 — Record `AD_VIEWED` in `ad_detail` | ✅ IMPLEMENTED | Event creation matches plan semantics |
| T7 — Dashboard template enhancements | ❌ NOT IMPLEMENTED | No stats card, selector, or view badges |

**Overall: 6 of 8 tasks fully implemented. 1 partially implemented. 1 not implemented.**

---

## T0: Add `ad_id` ForeignKey to `AnalyticsEvent` — ✅ IMPLEMENTED

**Plan target:** `src/backend/apps/analytics/models.py` — add nullable `ad` FK to `AnalyticsEvent`.

**Evidence (models.py, lines 35–42):**
```python
ad = models.ForeignKey(
    "ads.Ad",
    on_delete=models.CASCADE,
    null=True,
    blank=True,
    related_name="analytics_events",
    help_text="Ad associated with this event (null for non-ad events)",
)
```

**Migration evidence (`0002_analytics_event_ad_fk.py`):**
- File exists at `src/backend/apps/analytics/migrations/0002_analytics_event_ad_fk.py`.
- `AddField` operation for `model_name="analyticsevent"`, `name="ad"`, with `null=True`, `blank=True`, `on_delete=CASCADE`, `related_name="analytics_events"`.
- Dependencies: `("ads", "0006_backfill_translations")`, `("analytics", "0001_initial")`.

**Conclusion:** Fully matches plan specification. Nullable field for safe rollout, CASCADE on delete for referential integrity.

---

## T1: Add `AD_VIEWED` to `AnalyticsEventType` — ✅ IMPLEMENTED

**Plan target:** `src/backend/apps/core/enums.py` — add `AD_VIEWED = "ad_viewed"`.

**Evidence (enums.py, line 60):**
```python
class AnalyticsEventType(StrEnum):
    ...
    AD_VIEWED = "ad_viewed"
    ...
```

**Conclusion:** Present and matches plan exactly.

---

## T2: Add `TimeRange` StrEnum — ✅ IMPLEMENTED

**Plan target:** `src/backend/apps/core/enums.py` — add `TimeRange` StrEnum with `ALL_TIME`, `THIRTY_DAYS`, `SEVEN_DAYS`.

**Evidence (enums.py, lines 99–104):**
```python
class TimeRange(StrEnum):
    """Time range options for seller statistics filtering."""

    ALL_TIME = "all_time"
    THIRTY_DAYS = "30_days"
    SEVEN_DAYS = "7_days"
```

**Export evidence (enums.py, line 179):** `"TimeRange"` is present in `__all__`.

**Conclusion:** Fully matches plan. Enum values, docstring, and `__all__` export all present.

---

## T3: Add `CACHES` Setting — ✅ IMPLEMENTED

**Plan target:** `src/backend/config/settings/base.py` — add explicit `CACHES` setting.

**Evidence (base.py, lines 213–216):**
```python
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
    }
}
```

**Conclusion:** Matches plan exactly. LocMemCache backend as specified.

---

## T4: Create `SellerStats` Service — ✅ IMPLEMENTED (with return-shape deviation)

**Plan target:** `src/backend/apps/analytics/services/seller_stats.py` — class with `__init__`, `get_stats`, `_cache_key`, `_compute`.

**Evidence (seller_stats.py):**

| Method | Plan Signature | Actual Signature | Match |
|--------|---------------|-----------------|-------|
| `__init__` | `(self, user_id: int)` | `(self, user_id: int) -> None` | ✅ |
| `get_stats` | `(self, time_range: TimeRange = TimeRange.ALL_TIME) -> dict` | `(self, time_range: TimeRange = TimeRange.ALL_TIME) -> dict` | ✅ |
| `_cache_key` | `(self, time_range: TimeRange) -> str` | `(self, time_range: TimeRange) -> str` | ✅ |
| `_compute` | `(self, time_range: TimeRange) -> dict` | `(self, time_range: TimeRange) -> dict` | ✅ |

**Cache TTL:** `CACHE_TTL: int = 300` (5 minutes) — matches plan.

**Export:** `SellerStats` is re-exported from `apps/analytics/services/__init__.py` (line 5: `from apps.analytics.services.seller_stats import SellerStats`).

**Return-shape deviation:**

The plan specifies this return shape:
```python
{
    "total_views": int,
    "total_contacts": int,
    "total_published": int,
    "per_ad_stats": {ad_id: view_count, ...},
}
```

The actual implementation returns:
```python
{
    "total_views": int,
    "total_contacts": int,
    "ads_published": int,       # ← plan says "total_published"
    "per_ad_stats": [           # ← plan says {ad_id: view_count} dict
        {"ad_id": int, "title": str, "views": int, "contacts": int},
        ...
    ],
}
```

Two deviations:
1. **Key name:** `ads_published` instead of `total_published`.
2. **Structure:** `per_ad_stats` is a **list of dicts** (each with `ad_id`, `title`, `views`, `contacts`) instead of a **flat dict** mapping `ad_id → view_count`.

**Impact on T7:** The plan's T7 template directive says to use `seller_stats.per_ad_stats[ad.id]` for view-count badges. With the actual list-of-dicts structure, this template expression would not work as written — it would require iteration or a dict lookup that doesn't exist. This is a forward-compatibility concern for the template task.

**Conclusion:** Service is implemented and functional, but the return shape deviates from the plan specification. The richer structure (list of dicts with title/views/contacts) is arguably more useful for a dashboard, but it diverges from the documented contract.

---

## T5: Integrate `SellerStats` into `DashboardView` — ⚠️ PARTIALLY IMPLEMENTED

**Plan target:** `src/backend/apps/ads/views/dashboard.py` — import `SellerStats`/`TimeRange`, parse `time_range` from GET, call `get_stats`, add `seller_stats`, `selected_time_range`, `time_range_options` to context.

**Evidence (dashboard.py):**

- ✅ **Imports:** `SellerStats` (line 16), `TimeRange` (line 17).
- ✅ **Parse `time_range` from GET with validation:**
  ```python
  selected_range_value = request.GET.get("time_range", TimeRange.ALL_TIME.value)
  try:
      time_range = TimeRange(selected_range_value)
  except ValueError:
      time_range = TimeRange.ALL_TIME
  ```
  (lines 41–45)
- ✅ **Call `SellerStats`:** `seller_stats = SellerStats(request.user.id).get_stats(time_range)` (line 48).
- ✅ **`seller_stats` in context:** (line 79).
- ✅ **`selected_time_range` in context:** (line 80).
- ❌ **`time_range_options` NOT in context:** The plan explicitly requires `time_range_options` to be added to the context dict (for rendering the time-range selector in the template). The actual context dict (lines 69–81) contains `ads_by_status`, `status_labels`, `consent_shown`, `seller_stats`, and `selected_time_range` — but **no `time_range_options`**.

**Conclusion:** Core integration is done, but the `time_range_options` context variable required by the plan is missing. This prevents the template from rendering the time-range selector dropdown as specified in T7.

---

## T6: Record `AD_VIEWED` in `ad_detail` — ✅ IMPLEMENTED

**Plan target:** `src/backend/apps/ads/views/listings.py` — import `AnalyticsEvent`/`AnalyticsEventType`, create event after `Ad.objects.get()` with `user_id=ad.user_id` (seller, not viewer).

**Evidence (listings.py):**

- ✅ **Imports:** `AnalyticsEvent` (line 19), `AnalyticsEventType` (line 26).
- ✅ **Event creation** (lines 69–74):
  ```python
  AnalyticsEvent.objects.create(
      event_type=AnalyticsEventType.AD_VIEWED,
      user_id=ad.user_id,  # Seller, not viewer
      ad_id=ad.id,
  )
  ```
  This is placed after the `Ad.objects.get()` call (lines 60–65) and before the `render()` call (line 81).

**Conclusion:** Fully matches plan. The `user_id` is correctly set to `ad.user_id` (the seller), and `ad_id` is populated — leveraging the T0 FK. The comment "Seller, not viewer" matches the plan's note about anonymous viewers.

---

## T7: Enhance Dashboard Template — ❌ NOT IMPLEMENTED

**Plan target:** `src/backend/templates/ads/dashboard.html` — add:
1. Stats card after `<h2>Your Ads</h2>` header.
2. Time range selector `<select>` with GET form submission.
3. View count badge using `seller_stats.per_ad_stats[ad.id]`.

**Evidence (dashboard.html, 114 lines):**

The template is the **original unmodified version**. None of the three planned changes are present:

- **No stats card:** After `<h2 class="text-xl font-semibold mb-4">Your Ads</h2>` (line 30), the template immediately enters the `{% for status, ads in ads_by_status.items %}` loop. There is no stats summary card showing `total_views`, `total_contacts`, `ads_published`.
- **No time range selector:** There is no `<form>` with a `<select name="time_range">` anywhere in the template. The `selected_time_range` context variable (provided by T5) is never referenced.
- **No view count badges:** Inside the ad card loop (lines 41–98), there is no reference to `seller_stats` or `per_ad_stats`. The `seller_stats` context variable is completely unused in the template.

**Conclusion:** T7 is entirely unimplemented. The template renders the dashboard without any statistics display, time-range filtering UI, or per-ad view counts.

---

## Test Files

**Plan specifies two test files:**

| Test File | Plan Location | Status |
|-----------|--------------|--------|
| `test_seller_stats.py` | `apps/analytics/tests/test_seller_stats.py` | ✅ EXISTS |
| `test_dashboard_stats.py` | `apps/ads/tests/test_dashboard_stats.py` | ❌ MISSING |

**Existing test file (`test_seller_stats.py`):**
- 288 lines, class-based (`TestSellerStats(TestCase)`).
- Uses `_make_*` helper functions (`_make_user`, `_make_category`, `_make_city`, `_make_ad`, `_make_event`).
- Tests: `test_get_stats_all_time`, `test_get_stats_with_time_range_7_days`, `test_get_stats_with_time_range_30_days`, `test_cache_key_format`, `test_empty_data_handling`.
- Uses `@override_settings(CACHES=...)` for test isolation.
- Imports `SellerStats` from `apps.analytics.services` (re-export works).
- ✅ Comprehensive and matches plan's test pattern description.

**Missing test file (`test_dashboard_stats.py`):**
- The plan's "Test File Locations" table specifies `apps/ads/tests/test_dashboard_stats.py` for "Dashboard integration" tests.
- The file does not exist. The `apps/ads/tests/` directory contains only: `test_ad_localization.py`, `test_media_security.py`, `test_search_triggers.py`, `__init__.py`.
- ❌ No dashboard integration tests exist.

---

## Dependency Graph Verification

The plan's dependency graph is:
```
T0 (ad_id FK) ──┐
                 ├──► T4 (SellerStats) ──► T5 (DashboardView) ──► T7 (Template)
T1 (AD_VIEWED) ─┤
T2 (TimeRange) ──┘
                  │
T3 (CACHES) ──────┘ (configuration prerequisite)

T6 (ad_detail) ──► Can deploy independently after T1
```

**Verification of ordering:**
- T0 (model FK) — implemented ✅
- T1 (AD_VIEWED enum) — implemented ✅ (T6 depends on this; T6 is also implemented ✅)
- T2 (TimeRange enum) — implemented ✅ (T4 and T5 depend on this; both implemented ✅)
- T3 (CACHES) — implemented ✅
- T4 (SellerStats) — implemented ✅ (depends on T0, T1, T2 — all present)
- T5 (DashboardView) — implemented ✅ (depends on T2, T4 — both present)
- T6 (ad_detail) — implemented ✅ (depends on T1 — present)
- T7 (Template) — ❌ NOT implemented (depends on T5 — T5 is done, but T7 itself is missing)

**Dependency integrity:** All implemented tasks have their dependencies satisfied. No circular dependencies. The rollout ordering is consistent with the plan.

---

## Deviations and Discrepancies

### Deviation 1: Return shape of `SellerStats._compute()` (T4)

The plan specifies `per_ad_stats` as `{ad_id: view_count, ...}` (a flat dict) and `total_published` as the key for published count. The actual implementation returns a list of dicts (`[{"ad_id", "title", "views", "contacts"}]`) and uses `ads_published` as the key.

**Assessment:** This is a **BEST-PRACTICE** deviation. The actual implementation is richer (includes title and contacts per ad) and more suitable for a dashboard display. However, it diverges from the documented contract and would break the T7 template expression `seller_stats.per_ad_stats[ad.id]` if implemented as specified. The test file `test_seller_stats.py` was written against the actual (list-of-dicts) shape, confirming the implementation is self-consistent.

### Deviation 2: Missing `time_range_options` in DashboardView context (T5)

The plan requires `time_range_options` in the context dict for the template to render the time-range selector. This variable is absent.

**Assessment:** This is a **SPEC-DEVIATION** (minor). The core stats integration works, but the template cannot render the selector without this variable. If T7 is implemented, this must be added.

### Deviation 3: T7 template not implemented

The dashboard template has no stats card, time-range selector, or view-count badges.

**Assessment:** This is a **SPEC-DEVIATION** (high). The user-facing deliverable of the plan is missing. The backend is fully wired (T5 provides `seller_stats` and `selected_time_range` in context), but the template never consumes them.

### Deviation 4: Missing `test_dashboard_stats.py`

The plan specifies a dashboard integration test file that does not exist.

**Assessment:** This is a **BEST-PRACTICE** gap. No integration tests verify the dashboard view's stats integration.

---

## Rollout Analysis

**Risks:**
1. **Template gap (T7):** The dashboard view passes `seller_stats` and `selected_time_range` to the template, but the template ignores them. Users see no statistics. This is a functional gap, not a crash risk — the template degrades gracefully (stats are simply not displayed).
2. **Return-shape mismatch (T4):** If T7 is implemented using the plan's template expression `seller_stats.per_ad_stats[ad.id]`, it will fail because `per_ad_stats` is a list, not a dict. The template must iterate the list or the service must be changed to return a dict.
3. **Missing `time_range_options` (T5):** The time-range selector in T7 cannot be rendered without this context variable.

**Dependencies:**
- All backend dependencies (T0–T6) are satisfied and correctly ordered.
- T7 has no code-level dependencies beyond T5 (which is done), but it requires the `time_range_options` context variable to be added to T5 first.

**Backward compatibility:**
- All changes are additive (nullable FK, additive enum values, new service, new context variables). No breaking changes.
- The `AnalyticsEvent.ad` FK is nullable, so existing events without an ad association are unaffected.
- The `AD_VIEWED` event creation in `ad_detail` adds one extra `INSERT` per page view. The plan notes this is fire-and-forget with no extra queries, which is accurate.

---

## Execution Validation

**Applicability:** All tasks remain applicable. No assumptions were invalidated. The codebase structure matches the plan's file paths (`src/backend/apps/...`).

**Execution readiness:**
- T0–T6: Ready. Code is in place, type-checked (imports resolve), and tested (`test_seller_stats.py` exists).
- T7: Not ready. Requires implementation.
- `test_dashboard_stats.py`: Not ready. Requires creation.

**Verification commands from the plan:**
- `uv run basedpyright src/backend/apps/analytics/models.py` — should pass (field is correctly typed).
- `uv run basedpyright src/backend/apps/core/enums.py` — should pass (enums are standard StrEnum).
- `uv run basedpyright src/backend/config/settings/base.py` — should pass (CACHES is a standard dict).
- `uv run basedpyright src/backend/apps/analytics/services/seller_stats.py` — should pass (type hints are present).
- `uv run basedpyright src/backend/apps/ads/views/dashboard.py` — should pass (imports resolve, types are annotated).
- `uv run basedpyright src/backend/apps/ads/views/listings.py` — should pass (event creation is straightforward).
- `uv run pytest src/backend/apps/analytics/tests/test_seller_stats.py -v` — should pass (tests are comprehensive and match the implementation).
- `uv run pytest src/backend/apps/ads/tests/test_dashboard_stats.py -v` — ❌ WILL FAIL (file does not exist).

---

## Required Fixes

1. **T7: Implement dashboard template enhancements.** Add stats card, time-range selector, and view-count badges to `templates/ads/dashboard.html`. Must account for the actual `per_ad_stats` structure (list of dicts, not flat dict).

2. **T5: Add `time_range_options` to DashboardView context.** The plan requires this variable for the template's time-range selector. Example:
   ```python
   "time_range_options": [
       (TimeRange.ALL_TIME.value, "All Time"),
       (TimeRange.THIRTY_DAYS.value, "30 Days"),
       (TimeRange.SEVEN_DAYS.value, "7 Days"),
   ],
   ```

3. **Create `test_dashboard_stats.py`.** The plan specifies this file for dashboard integration tests. It does not exist.

---

## Advisory Recommendations

1. **Resolve the `per_ad_stats` shape discrepancy.** Either:
   - (a) Update the plan to document the actual list-of-dicts structure, or
   - (b) Change the service to return a dict keyed by `ad_id` if the template expression `per_ad_stats[ad.id]` is preferred.
   The current list-of-dicts is more informative but requires template iteration.

2. **Consider adding a `time_range_options` helper to the `TimeRange` enum** (e.g., a classmethod returning label/value pairs) to avoid hardcoding the options list in the view.

3. **The `test_seller_stats.py` test uses `@override_settings(CACHES=...)`** which is good practice for cache isolation. The same pattern should be applied to `test_dashboard_stats.py` when created.

4. **The `DashboardView` imports `SellerStats` and `TimeRange` on separate lines** (lines 16–17) rather than consolidating. This is a minor style inconsistency but does not affect functionality.

---

## Conclusion

The backend implementation of the Seller Dashboard Statistics plan is **substantially complete** — 6 of 8 tasks are fully implemented, with correct dependency ordering and comprehensive unit tests for the `SellerStats` service. The two gaps are:

1. **T7 (template):** The user-facing dashboard template has not been enhanced with stats display, time-range selector, or view-count badges. This is the primary missing deliverable.
2. **T5 (minor):** The `time_range_options` context variable is missing, which T7 needs.

Additionally, the `per_ad_stats` return shape in `SellerStats._compute()` deviates from the plan's specification (list of dicts vs. flat dict), which must be reconciled before T7 can be implemented as specified.

No code was modified during this verification.
