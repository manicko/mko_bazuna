# Analytics Improvements - Implementation Plan

**Date:** 2026-07-27  
**Status:** Ready for Execution  
**Source:** Research Document v1

---

## Execution Order (Topologically Sorted)

The following tasks follow strict dependency ordering to minimize coupling and ensure safe incremental rollout.

### Task Graph

```
# Parallel tasks (no dependencies):
# T0, T1, T2, T3, T4, T6, T8 can all start immediately
# 
# Sequential dependencies:
# T0 → T5 → T7 → T9
# T1 ──┬→ T5 → T7 → T9
#     ├→ T6 → T7 → T10
#     └→ T8 → T7
# T2 ──┬→ T3  (migration after model change)
#     └→ T8 → T7
# T4 → T5 → T7

# Legend: Advisory Lock for T7 uses AdvisoryLockId.ROLLUP_DAILY_METRICS
```

| Task | Description | Dependencies | Risk Level |
|------|-------------|--------------|------------|
| T0 | Add TrustLevel StrEnum | None | Low |
| T1 | Extend AnalyticsEventType enum | None | Low |
| T2 | Add ad FK to AnalyticsEvent model | None | Medium |
| T3 | Create migration 0002_analytics_event_ad_fk | T2 | Medium |
| T4 | Create DailyAdMetrics model | None | High |
| T5 | Create TrustAnalytics service | T0, T1, T4 | High |
| T6 | Create ModerationAnalytics service | T1 | High |
| T7 | Create daily rollup management command | T2, T4, T5, T6 | Medium |
| T8 | Update auto_moderation.py for extended events | T1, T2 | Low |
| T9 | Create SellerTrustDashboard view | T5 | Medium |
| T10 | Create ModerationAnalytics view | T6 | Medium |

---

## Task Specifications

### T0: Add TrustLevel StrEnum

**Symbol:** `TrustLevel`  
**File:** `src/backend/apps/core/enums.py`

**Purpose:** Foundation enum for trust system used by TrustAnalytics service (must be created before T5).

**Implementation:**
```python
class TrustLevel(StrEnum):
    UNVERIFIED = "unverified"
    VERIFIED = "verified"
    TRUSTED = "trusted"
    PRO = "pro"
```

**Update `__all__`:** Add `"TrustLevel"` to the `__all__` list in enums.py.

---

### T1: Extend AnalyticsEventType Enum

**Symbol:** `apps.core.enums.AnalyticsEventType`

**Action:** Add trust/moderation event types as new enum members.

**Members to Add:**
- `SELLER_VERIFIED` - Seller account verification
- `TRUST_LEVEL_UPDATED` - Trust score change
- `MODERATION_APPROVED` - Manual or auto approval
- `MODERATION_REJECTED` - Manual or auto rejection
- `MODERATION_FLAGGED` - Content flagged for review
- `DASHBOARD_VIEWED` - Seller dashboard access
- `AD_EDITED` - Ad text/content modified
- `AD_REACTIVATED` - Archived ad republished
- `CONTACT_COMPLETED` - Contact exchange completed
- `AD_REPORTED` - Ad reported by buyer

---

### T2: Add ad ForeignKey to AnalyticsEvent

**Symbol:** `apps.analytics.models.AnalyticsEvent`

**Action:** Add nullable `ad` ForeignKey field to enable per-ad analytics.

**Field Specification:**
- Name: `ad`
- Type: `ForeignKey["ads.Ad"]`
- Nullable: `True` (safe for historical events)
- On Delete: `SET_NULL`
- Related Name: `analytics_events`

**Implementation Notes:**
- Place field after `user` field in class body (fields-before-methods convention)
- Nullable to preserve existing events without ad association
- `to="ads.Ad"` string reference to avoid circular import

---

### T3: Create Migration for ad FK

**File:** `src/backend/apps/analytics/migrations/0002_analytics_event_ad_fk.py`

**Action:** Create schema migration adding the `ad` field.

**Migration Dependencies:**
- `analytics.0001_initial`
- `ads.0001_initial` (implicit via FK reference)

**Migration Operations:**
1. `AddField` for `ad` ForeignKey (nullable)
2. `AddIndex` on `(event_type, timestamp)` for query performance

---

### T4: Create DailyAdMetrics Model

**File:** `src/backend/apps/analytics/models.py` (new class)

**Symbol:** `DailyAdMetrics`

**Purpose:** Pre-aggregated daily metrics for ads to support efficient dashboard queries.

**Fields:**
| Field | Type | Constraints | Purpose |
|-------|------|-------------|---------|
| ad | ForeignKey | CASCADE | Parent ad |
| date | DateField | - | Aggregation date |
| views_count | PositiveIntegerField | default=0 | Daily views |
| contacts_count | PositiveIntegerField | default=0 | Daily contacts |
| trust_score | FloatField | null=True | Current trust score |
| avg_response_time | FloatField | null=True | Avg hours to respond |
| created_at | DateTimeField | auto_now_add=True | Record creation |
| updated_at | DateTimeField | auto_now=True | Last update |

**Meta:**
- `db_table = "daily_ad_metrics"`
- Unique constraint: `(ad, date)`
- Index on `(date, -views_count)` for leaderboard queries

---

### T5: Create TrustAnalytics Service

**File:** `src/backend/apps/analytics/services/trust_analytics.py`

**Directory:** `apps/analytics/services/` (create `__init__.py` for package)

**Purpose:** Calculate and update seller trust scores based on behavioral metrics.

**Dependencies:** T0 (TrustLevel enum), T1 (AnalyticsEventType), T4 (DailyAdMetrics model)

**Functions:**
| Function | Signature | Purpose |
|----------|-----------|---------|
| `calculate_seller_trust_score` | `(user_id: int) -> float` | Compute trust score (0-100) |
| `get_trust_level` | `(score: float) -> TrustLevel` | Map score to TrustLevel enum |
| `record_trust_event` | `(user_id: int, event: AnalyticsEventType) -> None` | Log trust event |
| `get_seller_daily_metrics` | `(user_id: int, days: int = 30) -> list[DailyAdMetrics]` | Get seller metrics |

**Trust Score Algorithm:**
- Base score: 50
- +10 for each published ad (max 50)
- +20 for seller_verified
- -10 for each rejected ad (min 0)
- Score clamps to [0, 100]

---

### T6: Create ModerationAnalytics Service

**File:** `src/backend/apps/analytics/services/moderation_analytics.py`

**Purpose:** Aggregate moderation statistics for staff dashboard.

**Functions:**
| Function | Signature | Purpose |
|----------|-----------|---------|
| `get_moderation_stats` | `(days: int = 30) -> ModerationStats` | Overall stats |
| `get_pending_queue_size` | `() -> int` | Count awaiting review |
| `get_moderator_performance` | `(days: int = 30) -> list[ModeratorPerformance]` | Per-moderator stats |
| `get_rejection_reasons` | `(days: int = 30) -> dict[str, int]` | Top rejection reasons |

---

### T7: Create Daily Rollup Management Command

**File:** `src/backend/apps/analytics/management/commands/rollup_daily_metrics.py`

**Action:** Management command to pre-compute DailyAdMetrics for ALL published ads.

**Command:** `uv run python src/manage.py rollup_daily_metrics`

**Dependencies:**
- Requires `Ad` model with `id`, `user_id`, `status=PUBLISHED`
- Requires `AnalyticsEvent` with `ad` FK (T2)
- Requires `DailyAdMetrics` model (T4)
- Requires `TrustAnalytics` and `ModerationAnalytics` services (T5, T6)

**Logic:**
1. Acquire advisory lock via `AdvisoryLockId.ROLLUP_DAILY_METRICS`
2. Query ALL ads with `status=PUBLISHED` (corrected: not just today's)
3. For each ad, aggregate AnalyticsEvents by type
4. Create/update `DailyAdMetrics` records
5. Output progress with logging
6. Release advisory lock on completion

**Additional Step:** Add to `AdvisoryLockId` in `apps/core/enums.py`:
```python
ROLLUP_DAILY_METRICS = 8  # Analytics daily aggregation
```

---

### T8: Update auto_moderation.py for Extended Events

**File:** `src/backend/apps/moderation/services/auto_moderation.py`

**Dependencies:** T1 (extended event types), T2 (ad FK field)

**Changes:** In `_pass_moderation()`, create AnalyticsEvent with `ad_id`:

```python
AnalyticsEvent.objects.create(
    event_type=AnalyticsEventType.MODERATION_APPROVED,
    user_id=ad.user_id,
    ad_id=ad.id,
)
```

In `_fail_moderation()`, create AnalyticsEvent with `ad_id`:

```python
AnalyticsEvent.objects.create(
    event_type=AnalyticsEventType.MODERATION_REJECTED,
    user_id=ad.user_id,
    ad_id=ad.id,
)
```

---

### T9: Create SellerTrustDashboard View

**File:** `src/backend/apps/analytics/views/seller_dashboard.py`

**Directory:** `apps/analytics/views/` (create `__init__.py` for package)

**Decorator:** `@login_required` (not staff-only - sellers view their own)

**View Function:** `seller_trust_dashboard(request: HttpRequest) -> HttpResponse`

**Purpose:** Trust-focused dashboard for sellers showing metrics and verification status.

**Template:** `analytics/seller_dashboard.html` (extends `ads/dashboard.html`)

---

### T10: Create ModerationAnalytics View

**File:** `src/backend/apps/analytics/views/moderation_dashboard.py`

**Decorator:** `@_staff_required` (staff-only per project security pattern)

**View Function:** `moderation_analytics(request: HttpRequest) -> HttpResponse`

**Template:** `analytics/moderation_dashboard.html`

---

## Directory Structure

Before implementation, create:

```
apps/analytics/
├── models.py
├── admin.py
├── apps.py
├── __init__.py
├── migrations/
│   └── 0001_initial.py
├── management/
│   ├── __init__.py
│   └── commands/__init__.py
├── services/          # NEW: Create this directory
│   └── __init__.py
└── views/             # NEW: Create this directory
    └── __init__.py
```

---

## File Changes Summary

### New Files
| Path | Purpose |
|------|---------|
| `apps/analytics/services/__init__.py` | Service package init |
| `apps/analytics/services/trust_analytics.py` | Trust scoring logic |
| `apps/analytics/services/moderation_analytics.py` | Moderation aggregation |
| `apps/analytics/views/seller_dashboard.py` | Seller-facing view |
| `apps/analytics/views/moderation_dashboard.py` | Staff-facing view |
| `apps/analytics/views/__init__.py` | Views package init |
| `apps/analytics/migrations/0002_analytics_event_ad_fk.py` | Schema migration |
| `apps/analytics/management/commands/rollup_daily_metrics.py` | Daily job |

### Modified Files
| Path | Changes |
|------|---------|
| `apps/core/enums.py` | Add TrustLevel enum, extend AnalyticsEventType, extend `__all__`, add AdvisoryLockId.ROLLUP_DAILY_METRICS |
| `apps/analytics/models.py` | Add ad FK + DailyAdMetrics |
| `apps/analytics/admin.py` | Register DailyAdMetrics |

---

## Testing Strategy

```bash
uv run pytest src/backend/apps/analytics/
uv run ruff check src/backend/apps/analytics/
uv run basedpyright src/backend/apps/analytics/
```

---

## Rollback Plan

1. Revert migration T3 (field is nullable, safe to remove)
2. Service files can be deleted without affecting core
3. Views can be removed from URL patterns without data loss
4. DailyAdMetrics is ephemeral - can be purged if issues arise