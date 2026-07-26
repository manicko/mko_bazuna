# Seller Dashboard Statistics - Research Report

## 1. Current State Analysis

### What Exists

**AnalyticsEvent Model** (`src/backend/apps/analytics/models.py`):
- Basic model with `event_type`, `timestamp`, and nullable `user` ForeignKey
- Already has 4 event types in `AnalyticsEventType` StrEnum:
  - `REGISTRATION_CREATED`
  - `AD_PUBLISHED`
  - `SEARCH_PERFORMED`
  - `CONTACT_INITIATED`
- No `ad_id` field currently exists - events are user-level only
- Uses `db_table = "analytics_events"` and SET_NULL on user erasure

**Cache Utilities** (`src/backend/apps/core/utils/cache.py`):
- Existing pattern with Django cache backend
- `CRITERIA_CACHE_KEY` and `CRITERIA_CACHE_TTL = 300` (5 minutes)
- Functions: `get_cached_criteria()`, `set_cached_criteria()`, `invalidate_criteria_cache()`
- Simple wrapper around `django.core.cache.cache`

**Dashboard View** (`src/backend/apps/ads/views/dashboard.py`):
- Implements `dashboard()` function with `@login_required` decorator
- Returns ads grouped by status (PUBLISHED, ON_MODERATION, etc.)
- Uses `is_consent_given()` for consent banner
- No stats integration currently

**Ad Detail View** (`src/backend/apps/ads/views/listings.py`):
- `ad_detail()` renders single ad for PUBLISHED status
- No view tracking/recording currently
- Uses `can_contact_seller()` from `core/services/contact.py`

**Ad Model** (`src/backend/apps/ads/models.py`):
- Has `status` field with `AdStatus` enum
- Has `published_at` timestamp for each ad
- User relationship via `user` ForeignKey

**Service Pattern Examples**:
- `apps/users/services/account_state.py` - Uses NamedTuple return type
- `apps/core/services/contact.py` - Records `CONTACT_INITIATED` analytics events

**Template** (`src/backend/templates/ads/dashboard.html`):
- Tailwind-styled MPA template
- Uses `ads_by_status` dict and `status_labels`
- HTMX-compatible structure (can accept partial updates)

### What's Needed (per Phase Plan)

1. **AD_VIEWED event type** - Missing from `AnalyticsEventType` enum
2. **TimeRange enum** - Missing for stats filtering (all_time, 30_days, 7_days)
3. **SellerStats service** - Missing aggregation logic for seller statistics
4. **ad_id on AnalyticsEvent** - Currently events only track user, not specific ad
5. **Dashboard context integration** - Stats not passed to template
6. **ad_detail view tracking** - No view event recording
7. **Dashboard template enhancement** - No stats display or time range selector

---

## 2. Gap Analysis

### Critical Missing Pieces

| Component | Status | Issue |
|-----------|--------|-------|
| `AnalyticsEventType.AD_VIEWED` | Missing | Required for view tracking |
| `TimeRange` StrEnum | Missing | Required for time filtering |
| `analytics_events.ad_id` FK | Missing | Cannot track views per ad without this |
| `SellerStats` service | Missing | No aggregation logic exists |
| Dashboard stats context | Missing | No data passed to template |
| `ad_detail` view event | Missing | No recording on page views |
| Dashboard stats UI | Missing | No template for stats display |

### Schema Gap: Missing ad_id on AnalyticsEvent

The current `AnalyticsEvent` model only has `user_id` but **no way to associate events with specific ads**. For seller statistics showing per-ad view counts, we need:

```python
ad = models.ForeignKey(
    "ads.Ad",
    on_delete=models.SET_NULL,
    blank=True,
    null=True,
    related_name="analytics_events",
    help_text="Ad associated with event (SET NULL on ad delete)",
)
```

This is a **critical missing piece** not explicitly mentioned in the phase plan but required for per-ad statistics.

---

## 3. Modern Practices Research (2026)

### PostgreSQL Analytics Optimization

**Django Conditional Aggregation** (HIGH confidence - verified via Context7):

```python
from django.db.models import Count, Q

AnalyticsEvent.objects.filter(
    user_id=seller_id,
    timestamp__gte=cutoff_date
).aggregate(
    views=Count('id', filter=Q(event_type=AnalyticsEventType.AD_VIEWED)),
    contacts=Count('id', filter=Q(event_type=AnalyticsEventType.CONTACT_INITIATED)),
    published=Count('id', filter=Q(event_type=AnalyticsEventType.AD_PUBLISHED)),
)
```

This translates to PostgreSQL `COUNT(...) FILTER (WHERE event_type = ...)` - efficient single-pass aggregation.

**Per-ad Aggregation** (using values() + annotate):

```python
AnalyticsEvent.objects.filter(
    user_id=seller_id,
    event_type=AnalyticsEventType.AD_VIEWED
).values('ad_id').annotate(
    view_count=Count('id')
)
```

### Django Caching Patterns

**Cache Key Design** (following existing pattern):
- Key format: `f"seller_stats:v1:{user_id}:{time_range}"`
- TTL: 300 seconds (5 minutes) - matches `CRITERIA_CACHE_TTL`
- Cache-aside pattern: check cache first, compute if miss, store result

**Default Cache Backend**: The project uses Django's default cache framework. Without explicit Redis/Memcached configuration in `pyproject.toml`, it likely uses `LocMemCache` in dev and will need Redis in production.

**Cache Serialization**: Django cache uses pickle by default. For PostgreSQL JSONB-style efficiency, we store computed aggregates as dicts.

### HTMX-Friendly Updates

**Pattern from existing code**: Templates use full page renders, but HTMX partials are supported via header detection:

```python
if request.headers.get("HX-Request"):
    return render(request, "ads/partials/ad_list.html", context)
```

**Recommended approach**: Stats card can be rendered as a separate partial updated via HTMX GET with time_range parameter, but for simplicity, the phase plan indicates full page reload with GET parameter.

---

## 4. Implementation Approach

### Recommended Approach: Cache-Aside Aggregation

**Rationale**:
1. **Simplicity**: Cache-aside is straightforward, no background jobs needed
2. **Consistency**: Events written immediately, stats computed on-read
3. **Scalability**: 5-minute TTL prevents excessive recomputation
4. **Pattern match**: Follows existing `get_cached_criteria()` pattern

**Alternative considered - Materialized Views**:
- More complex to maintain (refresh on event write)
- PostgreSQL 18 supports `REFRESH MATERIALIZED VIEW CONCURRENTLY`
- **Rejected**: Overengineering for this use case; cache-aside sufficient for MVP

### Data Flow

```
ad_detail() renders ad
    └─> AnalyticsEvent.objects.create(type=AD_VIEWED, user=seller, ad=ad)

dashboard() loads
    └─> SellerStats.get_stats(user_id, time_range)
        └─> Check cache for key "seller_stats:v1:{uid}:{range}"
        └─> MISS: Query analytics_events with time filter
        └─> Aggregate: total_views, total_contacts, ads_published
        └─> Aggregate per-ad: views by ad_id
        └─> Store in cache with 300s TTL
        └─> Return dict with all stats
```

### Key Design Decisions

1. **ad_id nullable on AnalyticsEvent**: Required for events like REGISTRATION_CREATED that have no associated ad
2. **5-minute TTL**: Matches existing pattern, balances freshness vs performance
3. **Cache-aside vs write-through**: Cache-aside chosen for simplicity
4. **GET param for time range**: Simple state management, no JS required

---

## 5. Technical Details

### File Changes Required

#### T1: Add AD_VIEWED to AnalyticsEventType
**File**: `src/backend/apps/core/enums.py`
```python
class AnalyticsEventType(StrEnum):
    REGISTRATION_CREATED = "registration_created"
    AD_PUBLISHED = "ad_published"
    SEARCH_PERFORMED = "search_performed"
    CONTACT_INITIATED = "contact_initiated"
    AD_VIEWED = "ad_viewed"  # NEW
```

#### T3: Add TimeRange StrEnum
**File**: `src/backend/apps/core/enums.py`
```python
class TimeRange(StrEnum):
    ALL_TIME = "all_time"
    THIRTY_DAYS = "30_days"
    SEVEN_DAYS = "7_days"
```

#### Missing: Add ad_id to AnalyticsEvent
**File**: `src/backend/apps/analytics/models.py`
```python
class AnalyticsEvent(models.Model):
    event_type = models.CharField(...)
    timestamp = models.DateTimeField(...)
    user = models.ForeignKey(..., null=True, blank=True)
    ad = models.ForeignKey(  # NEW
        "ads.Ad",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="analytics_events",
    )
```

**Migration needed**: Create new migration for `analytics_events.ad_id` column.

#### T2: Create SellerStats Service
**File**: `src/backend/apps/analytics/services/seller_stats.py` (NEW)
- Methods: `get_stats(user_id, time_range)`, `_compute_stats_from_events()`, `_get_cache_key()`
- Imports: `AnalyticsEvent`, `TimeRange`, `AnalyticsEventType`
- Cache TTL: 300 seconds

**File**: `src/backend/apps/analytics/services/__init__.py` (NEW) - Export SellerStats

#### T4: Integrate SellerStats into DashboardView
**File**: `src/backend/apps/ads/views/dashboard.py`
- Import `SellerStats` and `TimeRange`
- Read `time_range` from `request.GET` (default: `TimeRange.ALL_TIME`)
- Call `SellerStats.get_stats(request.user.id, time_range)`
- Add `seller_stats` and `selected_time_range` to context

#### T5: Add AD_VIEWED Event Recording
**File**: `src/backend/apps/ads/views/listings.py`
- In `ad_detail()`: After successful ad fetch, create `AnalyticsEvent(type=AD_VIEWED)`
- Use fire-and-forget pattern (sync create, no additional queries)

#### T6: Dashboard Template Enhancement
**File**: `src/backend/templates/ads/dashboard.html`
- Add stats card above ads sections
- Add time range selector (dropdown or button group)
- Display: total views, total contacts, ads published
- Per-ad view counters in PUBLISHED ad cards

### Query Patterns (for SellerStats)

```python
# Time filter (PostgreSQL)
from django.utils import timezone

cutoff_map = {
    TimeRange.ALL_TIME: None,
    TimeRange.THIRTY_DAYS: timezone.now() - timedelta(days=30),
    TimeRange.SEVEN_DAYS: timezone.now() - timedelta(days=7),
}

# Total stats query
base_qs = AnalyticsEvent.objects.filter(user_id=user_id)
if cutoff:
    base_qs = base_qs.filter(timestamp__gte=cutoff)

stats = base_qs.aggregate(
    total_views=Count('id', filter=Q(event_type=AnalyticsEventType.AD_VIEWED)),
    total_contacts=Count('id', filter=Q(event_type=AnalyticsEventType.CONTACT_INITIATED)),
    ads_published=Count('id', filter=Q(event_type=AnalyticsEventType.AD_PUBLISHED)),
)

# Per-ad views (for sellers with many published ads)
from apps.ads.models import Ad

published_ad_ids = Ad.objects.filter(
    user_id=user_id, status=AdStatus.PUBLISHED
).values_list('id', flat=True)

per_ad = AnalyticsEvent.objects.filter(
    user_id=user_id,
    event_type=AnalyticsEventType.AD_VIEWED,
    ad_id__in=published_ad_ids,
    timestamp__gte=cutoff,
).values('ad_id').annotate(
    view_count=Count('id')
)
# Returns [{'ad_id': 1, 'view_count': 5}, ...]
```

### Cache Key Strategy

```python
# Key format: seller_stats:v1:{user_id}:{time_range}
def _get_cache_key(user_id: int, time_range: TimeRange) -> str:
    return f"seller_stats:v1:{user_id}:{time_range.value}"
```

### Migration Requirements

1. **Add ad_id column to analytics_events table** - Nullable, with foreign key to ads.id
2. **Add index on (user_id, event_type, timestamp)** - For efficient stats queries
3. **Update choices in migration** to include `ad_viewed`

### Test Strategy

Tests should cover:
- `SellerStats.get_stats()` with different time ranges
- Cache hit/miss behavior
- Empty state when no events exist
- Integration with dashboard view context

---

## Confidence Levels

| Finding | Confidence | Source |
|---------|------------|--------|
| AnalyticsEvent model structure | HIGH | Source code inspection |
| Cache pattern in use | HIGH | Source code inspection |
| Service module pattern | HIGH | Source code inspection |
| Missing ad_id field | HIGH | Schema analysis |
| Django conditional aggregation | HIGH | Context7 verified |
| PostgreSQL FILTER aggregation | HIGH | Context7 verified |