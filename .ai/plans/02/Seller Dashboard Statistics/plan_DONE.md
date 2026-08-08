# Seller Dashboard Statistics — Implementation Plan

**Phase:** 2  
**Plan ID:** 1  
**Created:** 2026-07-26  
**Risk Level:** MEDIUM (cross-module changes, cache integration, schema migration)  

---

## Overview

Add seller-facing statistics to dashboard showing ad performance metrics. Stats are aggregated from `analytics_events` table with 5-minute cache TTL.

**CRITICAL NOTE:** This plan adds T0 prerequisite (AnalyticsEvent.ad FK) that was missing from the original YAML specification. Per-ad view counters are impossible without this schema change.

---

## Task Execution Order (Corrected)

| Task | Description | Symbol | File | Dependencies |
|------|-------------|--------|------|--------------|
| T0 | Add ad_id FK to AnalyticsEvent | `AnalyticsEvent.ad` | `apps/analytics/models.py` | None |
| T1 | Add AD_VIEWED to AnalyticsEventType | `AnalyticsEventType.AD_VIEWED` | `apps/core/enums.py` | None |
| T2 | Add TimeRange StrEnum | `TimeRange` | `apps/core/enums.py` | None |
| T3 | Add CACHES setting | `CACHES` | `config/settings/base.py` | None |
| T4 | Create SellerStats service | `SellerStats` | `apps/analytics/services/seller_stats.py` | T0, T1, T2 |
| T5 | Integrate into DashboardView | `dashboard` | `apps/ads/views/dashboard.py` | T2, T4 |
| T6 | Record AD_VIEWED in ad_detail | `ad_detail` | `apps/ads/views/listings.py` | T1 |
| T7 | Enhance dashboard template | `dashboard.html` | `templates/ads/dashboard.html` | T5 |

---

## Task Details

### T0: Add ad_id ForeignKey to AnalyticsEvent (BLOCKING PREREQUISITE)

**Symbol:** `AnalyticsEvent.ad`  
**File:** `src/backend/apps/analytics/models.py`  
**Priority:** CRITICAL  

**Description:**
Add nullable ForeignKey field `ad` to `AnalyticsEvent` model to associate events with specific ads. Without this field, per-ad statistics are impossible.

**Changes:**
- Add field to `AnalyticsEvent` class:
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
- Create migration in `apps/analytics/migrations/`

**Risk Mitigation:**
- Field is nullable for events without ad association
- `on_delete=CASCADE` ensures referential integrity

**Verification:**
```bash
uv run django-admin makemigrations analytics --name add_ad_fk
uv run basedpyright src/backend/apps/analytics/models.py
uv run ruff check src/backend/apps/analytics/models.py
```

---

### T1: Add AD_VIEWED to AnalyticsEventType

**Symbol:** `AnalyticsEventType.AD_VIEWED`  
**File:** `src/backend/apps/core/enums.py`  
**Priority:** High  

**Description:**
Add `AD_VIEWED = "ad_viewed"` value to enable tracking of individual ad views.

**Changes:**
- Add `AD_VIEWED = "ad_viewed"` to `AnalyticsEventType` enum
- Add `"TimeRange"` to `__all__` export list

**Verification:**
```bash
uv run basedpyright src/backend/apps/core/enums.py
uv run ruff check src/backend/apps/core/enums.py
```

---

### T2: Add TimeRange StrEnum

**Symbol:** `TimeRange`  
**File:** `src/backend/apps/core/enums.py`  
**Priority:** High  

**Description:**
Add `TimeRange` StrEnum with values for stats time filtering per project rule #10.

**Changes:**
```python
class TimeRange(StrEnum):
    """Time range options for seller statistics filtering."""
    ALL_TIME = "all_time"
    THIRTY_DAYS = "30_days"
    SEVEN_DAYS = "7_days"
```
- Add to `__all__` export list

**Verification:**
```bash
uv run basedpyright src/backend/apps/core/enums.py
uv run ruff check src/backend/apps/core/enums.py
```

---

### T3: Add CACHES setting to base.py

**Symbol:** `CACHES`  
**File:** `src/backend/config/settings/base.py`  
**Priority:** High (production blocking)  

**Description:**
Add explicit `CACHES` Django setting. Currently missing, causing inconsistent stats in multi-worker production.

**Changes:**
```python
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
    }
}
```

**Verification:**
```bash
uv run basedpyright src/backend/config/settings/base.py
uv run ruff check src/backend/config/settings/base.py
```

---

### T4: Create SellerStats service

**Symbol:** `SellerStats`  
**File:** `src/backend/apps/analytics/services/seller_stats.py`  
**Priority:** High  

**Description:**
Create `SellerStats` service class for stats aggregation with caching.

**Changes:**
- Create `apps/analytics/services/` directory
- Create `seller_stats.py` with class-based design (justified for stateful caching)

**Service Interface:**
```python
class SellerStats:
    def __init__(self, user_id: int): ...
    def get_stats(self, time_range: TimeRange = TimeRange.ALL_TIME) -> dict: ...
    def _cache_key(self, time_range: TimeRange) -> str: ...
    def _compute(self, time_range: TimeRange) -> dict: ...
```

**Return Shape:**
```python
{
    "total_views": int,
    "total_contacts": int,
    "total_published": int,
    "per_ad_stats": {ad_id: view_count, ...},
}
```

**Verification:**
```bash
uv run basedpyright src/backend/apps/analytics/services/seller_stats.py
uv run ruff check src/backend/apps/analytics/services/seller_stats.py
```

**Dependencies:** T0, T1, T2

---

### T5: Integrate SellerStats into DashboardView

**Symbol:** `dashboard`  
**File:** `src/backend/apps/ads/views/dashboard.py`  
**Priority:** Medium  

**Description:**
Modify `dashboard()` to import and use `SellerStats`.

**Changes:**
- Import `SellerStats`, `TimeRange`
- Parse `time_range` from `request.GET` with validation
- Call `SellerStats(request.user.id).get_stats(selected_range)`
- Add `seller_stats`, `selected_time_range`, `time_range_options` to context

**Verification:**
```bash
uv run basedpyright src/backend/apps/ads/views/dashboard.py
uv run ruff check src/backend/apps/ads/views/dashboard.py
```

**Dependencies:** T2, T4

---

### T6: Record AD_VIEWED in ad_detail

**Symbol:** `ad_detail`  
**File:** `src/backend/apps/ads/views/listings.py`  
**Priority:** Medium  

**Description:**
Add `AnalyticsEvent` creation on successful ad detail view.

**Changes:**
- Import `AnalyticsEvent`, `AnalyticsEventType`
- After `Ad.objects.get()`, create event with `user_id=ad.user_id` (seller)

**Important:** The `user_id` is the **seller** (ad owner), NOT the viewer. Viewers are anonymous on detail view.

**Verification:**
```bash
uv run basedpyright src/backend/apps/ads/views/listings.py
uv run ruff check src/backend/apps/ads/views/listings.py
```

**Dependencies:** T1

---

### T7: Enhance dashboard template (YAML original T6)

**Symbol:** `dashboard.html`  
**File:** `src/backend/templates/ads/dashboard.html`  
**Priority:** Medium  

**Description:**
Add stats card, time range selector, and per-ad view counters.

**Changes:**
- Stats card after `<h2>Your Ads</h2>` header
- Time range selector `<select>` with GET form submission
- View count badge using `seller_stats.per_ad_stats[ad.id]`

**Verification:**
- Manual browser verification
- Template renders with/without stats data

**Dependencies:** T5

---

## Dependency Graph

```
T0 (ad_id FK) ──┐
                 ├──► T4 (SellerStats) ──► T5 (DashboardView) ──► T7 (Template)
T1 (AD_VIEWED) ─┤
T2 (TimeRange) ──┘
                  │
T3 (CACHES) ─────┘ (configuration prerequisite)

T6 (ad_detail) ──► Can deploy independently after T1
```

---

## Verification Suite

```bash
# Type checking all changed files
uv run basedpyright src/backend/apps/analytics/models.py
uv run basedpyright src/backend/apps/core/enums.py
uv run basedpyright src/backend/config/settings/base.py
uv run basedpyright src/backend/apps/analytics/services/seller_stats.py
uv run basedpyright src/backend/apps/ads/views/dashboard.py
uv run basedpyright src/backend/apps/ads/views/listings.py

# Lint all changed files
uv run ruff check src/backend/apps/analytics/models.py src/backend/apps/core/enums.py src/backend/config/settings/base.py src/backend/apps/analytics/services/seller_stats.py src/backend/apps/ads/views/dashboard.py src/backend/apps/ads/views/listings.py

# Run tests
uv run pytest src/backend/apps/analytics/tests/test_seller_stats.py -v
uv run pytest src/backend/apps/ads/tests/test_dashboard_stats.py -v
```

---

## Test File Locations

| Test File | Description | Pattern |
|-----------|-------------|---------|
| `apps/analytics/tests/__init__.py` | Create test package | Empty |
| `apps/analytics/tests/test_seller_stats.py` | SellerStats unit tests | Class-based, `_make_*` helpers |
| `apps/ads/tests/test_dashboard_stats.py` | Dashboard integration | Reuse existing test patterns |

---

## Risk Mitigation Strategies

| Risk | Mitigation |
|------|------------|
| T0 migration fails in production | Test locally first; field nullable for safe rollout |
| Cache inconsistency in multi-worker prod | T3 adds explicit `CACHES`; Redis swap documented as future |
| View recording impacts page load | Fire-and-forget: sync ORM create only, no extra queries |
| Enum changes break existing code | Additive only; existing code uses unchanged values |
| Template shows stale stats | 5-min TTL is acceptable; handle gracefully |

---

## Notes

1. **Self-views and rate-limiting deferred** per research Section 6: requires viewer identity tracking.

2. **Cache invalidation on events deferred**: With 5-min TTL, eventual consistency is acceptable.

3. **`ad.user_id` semantics**: Events record the **seller**, not viewer. Matches `CONTACT_INITIATED` pattern in `contact.py`.

4. **All additions are backward compatible**: Nullable fields, additive enums, no breaking API changes.