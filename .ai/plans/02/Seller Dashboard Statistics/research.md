# Seller Dashboard Statistics — Implementation Research Report

**Date:** 2026-07-26
**Scope:** Phase 2 Plan 1 (T1–T6)
**Risk Level:** MEDIUM — cross-module changes, cache integration, missing DB field

---

## 1. Current State Analysis

### 1.1 AnalyticsEvent Model (`apps/analytics/models.py`)

| Aspect | Current State |
|--------|--------------|
| Fields | `event_type` (CharField, max 30), `timestamp` (auto_now_add), `user` (FK User, nullable, SET_NULL) |
| Indexes | Only the default PK index + `auto_now_add` yields a BTREE on `timestamp` implicitly |
| **Missing** | **No `ad_id` ForeignKey** — cannot associate events with specific ads for per-ad view counting |

### 1.2 AnalyticsEventType Enum (`apps/core/enums.py:52-58`)

```python
class AnalyticsEventType(StrEnum):
    REGISTRATION_CREATED = "registration_created"
    AD_PUBLISHED = "ad_published"
    SEARCH_PERFORMED = "search_performed"
    CONTACT_INITIATED = "contact_initiated"
```

**Missing:** `AD_VIEWED = "ad_viewed"`

### 1.3 TimeRange Enum

**Does not exist.** No time range abstraction anywhere in the codebase.

### 1.4 Cache Utilities (`apps/core/utils/cache.py`)

- Three module-level functions: `get_cached_criteria`, `set_cached_criteria`, `invalidate_criteria_cache`
- Hardcoded constants: `CRITERIA_CACHE_KEY`, `CRITERIA_CACHE_TTL` (300s)
- **No generic cache helper** — each consumer must write its own key/TTL/pattern
- Uses `django.core.cache.cache` directly

### 1.5 Cache Configuration (`config/settings/base.py`)

**No `CACHES` setting defined.** Django defaults to `LocMemCache` (local memory, per-process, no shared state). This means:
- In dev, cache works fine (single process)
- In production, with multiple gunicorn workers, each worker has its own cache — stats will be inconsistent
- **Blocking issue for production:** A `CACHES` config (even `LocMem` for single-worker or Redis for multi-worker) must be added before SellerStats caching works correctly

### 1.6 Dashboard View (`apps/ads/views/dashboard.py`)

- Fetches ads grouped by 5 statuses
- Context: `ads_by_status`, `status_labels`, `consent_shown`
- **No stats context** — completely absent

### 1.7 Dashboard Template (`templates/ads/dashboard.html`)

- Renders a grid of ad cards grouped by status
- Each card shows: image, title, price, edit/archive/reactivate buttons
- **No stats card, no time range selector, no per-ad view counters**

### 1.8 Ad Detail View (`apps/ads/views/listings.py:ad_detail`)

- Fetches single PUBLISHED ad, renders detail template
- **No AnalyticsEvent recording** — ad views not tracked at all

### 1.9 Existing Services Directory (`apps/analytics/services/`)

**Does not exist.** Must be created. For patterns, see:
- `apps/users/services/account_state.py` — plain functions, no class, `NamedTuple` for return values
- `apps/core/services/contact.py` — plain functions, `AnalyticsEvent.objects.create()` calls

### 1.10 Analytics Tests (`apps/analytics/tests/`)

**Does not exist.** No test directory for analytics.

---

## 2. Gap Analysis

| # | Gap | Affected Tasks | Severity |
|---|-----|---------------|----------|
| G1 | **AnalyticsEvent lacks `ad_id` FK** — cannot associate events with specific ads. Per-ad view counters (T2 output, T6 display) are impossible without this. | T2, T4, T5, T6 | **BLOCKING** |
| G2 | **No `AD_VIEWED` event type** in `AnalyticsEventType` | T1, T5 | **BLOCKING** |
| G3 | **No `TimeRange` enum** | T2, T3, T4 | **BLOCKING** |
| G4 | **No `apps/analytics/services/` directory** | T2 | Structural |
| G5 | **No generic cache utility** — `SellerStats` must implement its own caching; cannot reuse existing helpers | T2 | Minor |
| G6 | **No `CACHES` Django setting** — production multi-worker stats will be inconsistent | T2 | **Production BLOCKING** |
| G7 | **No analytics tests directory** — new service needs tests; no existing test pattern in analytics app | Verification | Structural |
| G8 | **No per-ad view counts** in `AnalyticsEvent` — `CONTACT_INITIATED` events also lack ad association, but that's out of scope for this plan | T2, T6 | **BLOCKING** |

### 2.1 Critical Schema Gap (G1 + G8)

The `AnalyticsEvent` model stores only `event_type`, `timestamp`, and `user`. To produce per-ad stats (the key deliverable), the service needs:

```sql
SELECT ad_id, COUNT(*) as view_count
FROM analytics_events
WHERE event_type = 'ad_viewed'
  AND user_id = <seller_id>
  AND timestamp BETWEEN <start> AND <end>
GROUP BY ad_id;
```

**Without an `ad_id` column, per-ad breakdown is impossible.** A migration must add:

```python
ad = models.ForeignKey(
    "ads.Ad",
    on_delete=models.CASCADE,
    null=True,       # nullable for events not tied to an ad (e.g., REGISTRATION_CREATED)
    blank=True,
    related_name="analytics_events",
    help_text="Ad associated with this event (null for non-ad events)",
)
```

The original YAML plan (T2) describes `per_ad_stats: dict[int, int]` as output but **never mentions the schema change** needed to support it.

---

## 3. Implementation Recommendations

### 3.1 Task Execution Order

The YAML specifies: T1 → T3 → T2 → T4 → T5 → T6. This is correct **IF** a new task `T0: Add analytics_events.ad_id FK migration` is inserted before T2.

**Recommended order:**

1. **T0** — Add `AnalyticsEvent.ad` FK + migration
2. **T1** — Add `AD_VIEWED` to `AnalyticsEventType`
3. **T3** — Add `TimeRange` enum
4. **T2** — Create `SellerStats` service
5. **T5** — Record `AD_VIEWED` in `ad_detail`
6. **T4** — Integrate `SellerStats` into `DashboardView`
7. **T6** — Enhance dashboard template

### 3.2 `TimeRange` Enum Definition

```python
class TimeRange(StrEnum):
    ALL_TIME = "all_time"
    THIRTY_DAYS = "30_days"
    SEVEN_DAYS = "7_days"
```

**Minor deviation from the YAML:** The YAML says 3 values (`ALL_TIME`, `THIRTY_DAYS`, `SEVEN_DAYS`). The detailed plan mentions `7d/30d/90d` (Section 1.1 in phase-02-detailed-plan-1.md). The YAML's 3 values should take precedence as the more specific plan.

### 3.3 `SellerStats` Service Design

**Location:** `apps/analytics/services/seller_stats.py`

**Architecture:** Class-based (deviating from existing function-based service pattern) because caching adds state. The class wraps cache key generation and stats computation together.

```python
from django.core.cache import cache
from django.db.models import Count, Q
from apps.analytics.models import AnalyticsEvent
from apps.core.enums import AnalyticsEventType, TimeRange

STATS_CACHE_TTL = 300  # 5 minutes

class SellerStats:
    def __init__(self, user_id: int):
        self._user_id = user_id

    def get_stats(self, time_range: TimeRange = TimeRange.ALL_TIME) -> dict:
        cache_key = self._cache_key(time_range)
        result = cache.get(cache_key)
        if result is not None:
            return result
        stats = self._compute(time_range)
        cache.set(cache_key, stats, STATS_CACHE_TTL)
        return stats

    def _cache_key(self, time_range: TimeRange) -> str:
        return f"seller_stats:{self._user_id}:{time_range.value}"

    def _compute(self, time_range: TimeRange) -> dict:
        qs = AnalyticsEvent.objects.filter(user_id=self._user_id)
        if time_range != TimeRange.ALL_TIME:
            days = int(time_range.value.split("_")[0])
            from django.utils import timezone
            from datetime import timedelta
            cutoff = timezone.now() - timedelta(days=days)
            qs = qs.filter(timestamp__gte=cutoff)

        aggregates = qs.aggregate(
            total_views=Count("pk", filter=Q(event_type=AnalyticsEventType.AD_VIEWED)),
            total_contacts=Count("pk", filter=Q(event_type=AnalyticsEventType.CONTACT_INITIATED)),
            total_published=Count("pk", filter=Q(event_type=AnalyticsEventType.AD_PUBLISHED)),
        )

        per_ad = (
            qs.filter(event_type=AnalyticsEventType.AD_VIEWED)
            .exclude(ad_id__isnull=True)
            .values("ad_id")
            .annotate(count=Count("id"))
        )
        per_ad_stats = {item["ad_id"]: item["count"] for item in per_ad}

        return {**aggregates, "per_ad_stats": per_ad_stats}
```

**Return shape:**
```python
{
    "total_views": int,
    "total_contacts": int,
    "total_published": int,
    "per_ad_stats": {ad_id: view_count, ...},
}
```

### 3.4 Cache Strategy Decision

| Concern | Recommendation | Rationale |
|---------|---------------|-----------|
| Cache backend | Add `CACHES` to `base.py` defaulting to `LocMemCache` | Works in dev, single-worker prod. Redis can be swapped later (out of scope). |
| TTL | 300s (5 min) | Matches existing `CRITERIA_CACHE_TTL` in `cache.py`. Tolerable staleness for dashboard. |
| Key format | `seller_stats:{user_id}:{time_range}` | Follows research_notes from `phase2_plan1_research.md` |
| Invalidation | Cache-bust on new event creation | **Not needed** for 5-min TTL. If requested later, use `cache.delete_pattern()` or store user cache keys in a set. |

### 3.5 `CACHES` Setting Addition

Add to `config/settings/base.py`:

```python
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
    }
}
```

This makes caching explicit (no silent default) and provides a single place to swap to Redis in production.

### 3.6 Ad View Recording (T5)

In `ad_detail()`, add after the `Ad.objects.get()` succeeds:

```python
AnalyticsEvent.objects.create(
    event_type=AnalyticsEventType.AD_VIEWED,
    user_id=ad.user_id,   # seller whose ad was viewed
    ad_id=ad.id,
)
```

Note: `user_id` here is the **seller** (ad owner), not the viewer. The viewer is anonymous (no login required). This is the correct semantics for "the seller received a view." This matches how `CONTACT_INITIATED` works in `contact.py` — the event records the seller user for attribution.

### 3.7 DashboardView Integration (T4)

```python
from apps.analytics.services.seller_stats import SellerStats
from apps.core.enums import TimeRange

def dashboard(request):
    time_range_str = request.GET.get("time_range", TimeRange.ALL_TIME)
    try:
        selected_range = TimeRange(time_range_str)
    except ValueError:
        selected_range = TimeRange.ALL_TIME

    stats_service = SellerStats(request.user.id)
    seller_stats = stats_service.get_stats(selected_range)

    context = {
        "ads_by_status": ads_by_status,
        "status_labels": status_labels,
        "seller_stats": seller_stats,
        "selected_time_range": selected_range,
        "time_range_options": list(TimeRange),
        "consent_shown": is_consent_given(request),
    }
```

### 3.8 Template Enhancement (T6)

The existing template (`templates/ads/dashboard.html`) uses Jinja/Django template syntax with `{{ }}` and `{% %}`. The stats card should:

1. **Stats card** — positioned between the `<h2>Your Ads</h2>` header and the first status section
2. **Time range selector** — a `<select>` that submits via GET (pure HTML, no JS needed)
3. **Per-ad counters** — in each `{% for ad in ads %}` card, show a small views badge

---

## 4. Code Patterns to Follow

### 4.1 Service Pattern (from `apps/users/services/account_state.py`)

- Module-level functions preferred (but `SellerStats` class is justified for stateful caching)
- `NamedTuple` or plain `dict` for return values
- Docstrings with Args/Returns sections
- `logger = logging.getLogger(__name__)` at module level

### 4.2 Cache Pattern (from `apps/core/utils/cache.py`)

- Module-level constants for TTL and key prefixes
- `django.core.cache.cache.get()` / `.set()` / `.delete()`
- Follow existing naming: `STATS_CACHE_TTL = 300`

### 4.3 Event Recording Pattern (from `apps/core/services/contact.py:record_contact_initiated`)

- `AnalyticsEvent.objects.create(event_type=..., user_id=...)` — synchronous create
- Informational log after creation

### 4.4 Test Pattern (from `apps/users/tests/test_account_state.py`)

- `pytestmark = [pytest.mark.django_db, pytest.mark.slow, pytest.mark.integration]`
- Module-level `_make_*` helper functions
- Class-based test organization (`TestGetAccountState`, `TestCanPublishAd`)
- Fixtures for default objects
- Test file location: `apps/analytics/tests/test_seller_stats.py`

---

## 5. Dependencies on Other Modules

| Dependency | Direction | Nature |
|-----------|-----------|--------|
| `apps.analytics.models.AnalyticsEvent` | T2 imports | Query source for stats |
| `apps.core.enums.AnalyticsEventType` | T1, T2, T5 import | Enum values for event types |
| `apps.core.enums.TimeRange` | T2, T3, T4 import | Time range filtering |
| `apps.core.utils.cache` | T2 uses | Django cache (add `CACHES` setting) |
| `apps.ads.models.Ad` | T2 query, T5 write | Per-ad stats grouping; FK target for T0 migration |
| `apps.users.models.User` | T4 uses | `request.user.id` for seller context |
| `apps.ads.views.dashboard` | T4 modifies | Stats context injection |
| `apps.ads.views.listings` | T5 modifies | AD_VIEWED event recording |
| `templates/ads/dashboard.html` | T6 modifies | Stats display |

---

## 6. Open Questions / Unresolved Items

1. **Exclude self-views?** Phase-02-detailed-plan (1.2) mentions "Exclude self-views (seller viewing own ad)." The YAML plan does not include this. Recommend deferring to a future iteration — tracking viewer identity requires login on the detail view, which is a significant change.

2. **Rate-limit same-user views?** Phase-02-detailed-plan (1.2) says "Rate-limit same-user views (1 per hour max)." Same as above — requires viewer identity tracking. Defer.

3. **Cache invalidation on new events?** With 5-min TTL, cache is eventually consistent. If dashboard users expect immediate updates after publishing, an invalidation hook in `Ad.save()` or `AnalyticsEvent.save()` could be added. **Recommend deferring** — 5-min staleness is acceptable.

4. **Database index for time-range filtering.** The `auto_now_add` on `timestamp` creates a default BTREE index. For range queries on `(event_type, timestamp)`, a composite index would help. The phase-02-detailed-plan proposes `IX_analytics_daily_rollup`. **Recommend deferring** until query performance measurements warrant it.

5. **`ad.user_id` vs `request.user.id` in ad_detail recording.** The `user_id` on `AD_VIEWED` events should be the ad owner (seller), not the viewer. This must be made explicit in documentation and code to avoid confusion.

---

## 7. Summary of Findings

| Aspect | Verdict |
|--------|---------|
| Plan completeness | Good for UI/service layer; **misses critical schema change** (AnalyticsEvent.ad FK) |
| Risk level | Correct (MEDIUM) — but rises to HIGH without the schema change task |
| Estimated effort | **6 tasks + 1 unplanned** (T0 schema migration) = ~1-2 days dev + testing |
| Production readiness | Blocked by missing `CACHES` Django setting in `base.py` |
| Pattern consistency | Good — follows existing service/cache/test patterns |
| Backward compatibility | All additions are additive; no breaking changes to existing API |