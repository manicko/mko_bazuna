---
id: phase-02-detailed-plan-1
domain: planning
tags:
  - phase-2
  - post-mvp
  - planning
related:
  - spec-index
  - seller-stories
  - buyer-stories
  - search-patterns
  - filter-ui
created: 2026-07-26
---

# Phase 2 Development Plan — Mko Bazuna

> Post-MVP enhancement roadmap for the Telegram-driven classifieds board.

## Overview

Phase 2 builds upon the Phase 1 MVP foundation (Telegram bot ad creation, public browsing, admin moderation) with enhanced seller tools, search improvements, and performance optimizations. This plan addresses:

- Seller dashboard improvements
- Photo thumbnail generation
- Search autocomplete
- Saved search alerts
- Performance optimizations

---

## 1. Seller Dashboard Improvements

### 1.1 Statistics Overview

**Current State:** Dashboard shows grouped ads by status only.

**Enhancement:** Add analytical statistics for sellers.

| Metric | Description | Location |
|--------|-------------|----------|
| Total ads posted | Lifetime count of seller's ads | Dashboard header |
| Active ads | Currently PUBLISHED count | Dashboard header |
| Expired ads | ARCHIVED count pending cleanup | Dashboard header |
| Total views | Aggregated from analytics_events | Per-ad breakdown |

**Implementation Tasks:**

1. **Create SellerStats service** (`apps/analytics/services/seller_stats.py`)
   - Query optimized stats using `analytics_events` table
   - Cache stats for 5-minute intervals per user
   - Return structured data for template consumption

2. **Update DashboardView** (`apps/ads/views/dashboard.py`)
   - Add stats aggregation to context
   - Leverage `select_related`/`prefetch_related` for efficiency
   - Add `select_for_update(skip_locked=True)` for concurrent update safety

3. **Enhance Template** (`templates/ads/dashboard.html`)
   - Add stats card above grouped ads
   - Include per-ad view counters
   - Add time range selector (7d/30d/90d)

**Dependencies:**
- `analytics_events` table (existing)
- `cache` utility layer (existing in `apps/core/utils/cache.py`)

**Database Impact:** None — uses existing analytics infrastructure.

### 1.2 Ad Performance Dashboard

**Enhancement:** Detailed performance metrics per ad.

| Feature | Description |
|---------|-------------|
| View count | Track unique views per ad (daily/weekly/monthly) |
| Contact clicks | Track contact button interactions |
| Archive timing | Show time until auto-archive |
| Engagement score | Combined metric (views + contacts) |

**Implementation Tasks:**

1. **Add AdPerformance model** (`apps/analytics/models/ad_performance.py`)
   - Daily aggregated view/contact counts
   - Partition by ad_id and date
   - Materialized view alternative considered for PG18

2. **Update AdDetailView** (`apps/ads/views/listings.py`)
   - Record view event on ad detail page load
   - Exclude self-views (seller viewing own ad)
   - Rate-limit same-user views (1 per hour max)

3. **Create PerformanceChart component**
   - HTMX-driven chart rendering
   - JSON endpoint for chart data
   - Cache warm-up for frequent sellers

---

## 2. Photo Thumbnail Generation

### 2.1 Current State Analysis

**Photo Handling Flow:**
- Telegram bot downloads JPEG photos
- Photos validated (magic bytes, dimensions, size)
- EXIF metadata stripped via `strip_photo_exif()`
- Stored with UUID v4 keys in `MEDIA_ROOT`
- Served via `media_gate` with `X-Accel-Redirect`

**Gap:** Full-size images served to all clients without optimization.

### 2.2 Thumbnail Pipeline

**Architecture Decision:** Generate thumbnails at upload time, store alongside original.

```
MEDIA_ROOT/
├── originals/                    # Full-size images
│   └── <uuid>.jpg
└── thumbnails/
    ├── small/                    # 240x180 for grid cards
    ├── medium/                   # 640x480 for listings
    └── large/                    # 1280x960 for detail view
```

**Implementation Tasks:**

1. **Create ThumbnailService** (`apps/media/services/thumbnails.py`)

```python
# Key operations:
# - generate_thumbnails(photo_bytes: bytes) -> dict[str, bytes]
# - size variants: small (240x180), medium (640x480), large (1280x960)
# - quality=85, optimize=True
# - maintain aspect ratio with object-fit CSS
```

2. **Update Media Service** (`telegram_bot/services/media.py`)
   - Integrate thumbnail generation into `save_photo()`
   - Store thumbnails with `_small`, `_medium`, `_large` suffixes
   - Maintain atomic write pattern with O_CREAT|O_EXCL

3. **Migrate AdImage model** (`apps/ads/models.py`)
   - Add `thumbnail_small`, `thumbnail_medium`, `thumbnail_large` fields
   - Nullable for backward compatibility
   - Backfill script for existing images

4. **Update Templates**
   - `templates/ads/dashboard.html` — use small thumbnails
   - `templates/ads/partials/ad_list.html` — use small/medium variants
   - `templates/ads/detail.html` — use large thumbnail with srcset

5. **Create ThumbnailCacheMiddleware** (`apps/media/middleware/thumbnail_cache.py`)
   - Set `Cache-Control: 31536000` for thumbnails (immutable)
   - Add `ETag` based on file modification

### 2.3 Thumbnail Variants Specification

| Variant | Dimensions | Use Case | File Size Target |
|---------|------------|----------|------------------|
| Small | 240x180 | Grid cards, dashboard thumbnails | <50KB |
| Medium | 640x480 | List view previews | <150KB |
| Large | 1280x960 | Detail view primary | <400KB |

**Dependencies:**
- Pillow (already in dependencies)
- MEDIA_ROOT configuration
- nginx cache headers (infrastructure)

---

## 3. Search Autocomplete

### 3.1 Current State

Search uses PostgreSQL FTS with:
- Russian translation of Montenegrin queries
- Fuzzy category/city matching via `difflib`
- No autocomplete suggestions

### 3.2 Autocomplete Architecture

**Decision Point:** Client-side cache vs server endpoint.

**Recommended:** Hybrid approach
- Client caches last 100 queries (localStorage)
- Server endpoint for popular terms
- Debounced requests (300ms)

**Implementation Tasks:**

1. **Create PopularSearch model** (`apps/search/models/popular_searches.py`)

| Field | Type | Purpose |
|-------|------|---------|
| id | PK | Django default |
| query | VARCHAR(200) | Sanitized search term |
| query_normalized | VARCHAR(200) | Lowercased, stripped |
| hit_count | INT | Aggregate view count |
| last_seen | TIMESTAMP | For decay sorting |

2. **Create AutocompleteView** (`apps/search/views/autocomplete.py`)

```python
# Endpoint: /api/search/autocomplete?q=<partial>
# Returns: JSON array of suggestions with metadata
# - query: string
# - category_suggestion: optional
# - city_suggestion: optional
# - hit_count: optional (for popular terms)
```

3. **Add SearchHistory model** (`apps/search/models/search_history.py`)

| Field | Type | Purpose |
|-------|------|---------|
| id | PK | Django default |
| user | FK(users) | Nullable (guests) |
| query | TEXT | Original query |
| query_normalized | VARCHAR(200) | Indexed for dedupe |
| created_at | TIMESTAMP | For cleanup |

4. **Create AutocompleteEndpoint** (`apps/search/views/api_autocomplete.py`)
   - Rate limit: 10 requests/minute per IP
   - Sanitize and validate query input
   - Return popular + recent + category suggestions

5. **Enhance Search Template** (`templates/ads/list.html`)
   - Add autocomplete dropdown component
   - Keyboard navigation support
   - HTMX-driven suggestions

### 3.3 Suggestion Sources

| Priority | Source | Weight |
|----------|--------|--------|
| 1 | User's search history | High (personalized) |
| 2 | Popular searches (hit_count > 10) | Medium |
| 3 | Category names matching prefix | Medium |
| 4 | City names matching prefix | Low |

### 3.4 Implementation Considerations

- Privacy: No user query data exposed to other users
- Decay: Last seen timestamp for recency weighting
- Cleanup: Remove history older than 90 days
- Cache: Redis cached popular terms (if available), fallback to DB

---

## 4. Saved Search Alerts

### 4.1 Overview

Buyers can save search queries and receive notifications when matching ads are published.

**Key Decisions:**
- Alert method: Telegram bot notifications only (no email)
- Frequency: Daily digest (not real-time)
- Storage: Dedicated `saved_searches` table with user binding

### 4.2 Data Model

Create `SavedSearch` model (`apps/search/models/saved_searches.py`):

| Field | Type | Purpose |
|-------|------|---------|
| id | PK | Django default |
| user | FK(users) | Alert recipient |
| query | TEXT | Search query |
| city_id | FK(cities, nullable) | Optional filter |
| category_id | FK(categories, nullable) | Optional filter |
| price_min | INT(nullable) | Price range filter |
| price_max | INT(nullable) | Price range filter |
| is_active | BOOL | Toggle for alerts |
| last_notified_at | TIMESTAMP | For deduplication |
| created_at | TIMESTAMP | Record creation |
| notification_count | INT | For pruning inactive |

### 4.3 Alert Delivery Pipeline

1. **SavedSearch model** (`apps/search/models/saved_searches.py`)
   - Pydantic schema for validation
   - Unique constraint on (user, query_normalized)

2. **AlertService** (`apps/search/services/alert_service.py`)
   - Find matching PUBLISHED ads since last check
   - Batch by user for notification
   - Mark ads as "alerted" via intermediate table

3. **AlertDeliveryTask** (`apps/search/management/commands/send_alerts.py`)
   - Run via cron daily (08:00 UTC)
   - Build message with ad previews
   - Send via telegram_bot notification system

4. **Add AlertPreference to User model** (`apps/users/models.py`)
   - `alert_enabled` bool (default True)
   - `alert_daily_hour` int (0-23, local time preference)

### 4.4 User Interface

5. **Add Alert Save UI** (`templates/components/save_search_modal.html`)
   - Modal triggered from search results
   - Confirm query + filters
   - Save button → POST /search/save

6. **Saved Searches Dashboard** (`apps/search/views/saved_searches.py`)
   - List active saved searches
   - Toggle, edit, delete actions
   - Notification statistics

### 4.5 Notification Format

```
New ads matching your saved search:

📦 Товары · Podgorica · 2 hours ago
iPhone 12 в отличном состоянии
Цена: 300 BAM

📦 Товары · Bar · 4 hours ago
Ноутбук MacBook Pro 2020
Цена: 800 BAM

Manage alerts: t.me/<bot>?start=alerts
```

---

## 5. Performance Optimizations

### 5.1 Database-Level Optimizations

#### 5.1.1 Partial Indexes Refinement

Current partial indexes exist for:
- `IX_ads_search_gin` on search_vector
- `IX_ads_pub_listing` for published ad queries
- Various sweep indexes for archive/delete operations

**Phase 2 Additions:**

1. **IX_ads_thumbnail_status** — published ads with images
   ```sql
   CREATE INDEX IX_ads_thumbnail_status ON ads (id)
   WHERE status = 'published' AND id IN (
       SELECT ad_id FROM ad_images
   );
   ```

2. **IX_analytics_daily_rollup** — for stats aggregation
   ```sql
   CREATE INDEX IX_analytics_daily_rollup ON analytics_events
   (event_type, DATE(timestamp))
   WHERE event_type IN ('SEARCH_PERFORMED', 'CONTACT_INITIATED');
   ```

#### 5.1.2 Query Optimization

**Listings Query Enhancement:**
- Add `only()` to select specific fields
- Use `defer()` to exclude large fields (description) in list view
- Implement cursor-based pagination for beyond-page-10 cases

### 5.2 Caching Strategy

#### 5.2.1 Redis Integration

**Deferred:** Phase 1 has no Redis. Phase 2 should add:

1. **Popular Searches Cache**
   - TTL: 1 hour
   - Key: `popular_searches:v1`
   - Fallback to DB query on miss

2. **User Search History Cache**
   - TTL: 24 hours
   - Key: `user_history:{user_id}`
   - Write-through on new searches

3. **Category Tree Cache**
   - TTL: 24 hours
   - Key: `category_tree:v1`
   - Invalidate on admin category changes

#### 5.2.2 Template Fragment Caching

Cache expensive fragments:
- Category navigation tree
- Popular search suggestions
- Empty state components

### 5.3 Image Optimization Pipeline

#### 5.3.1 WebP Support

1. **Add WebP variant** to thumbnail pipeline
   - Auto-detect client `Accept` header
   - 30% smaller than JPEG at equivalent quality
   - Fallback to JPEG for older browsers

2. **Update media_gate** (`apps/ads/views/listings.py`)
   - Check `image_webp` field existence
   - Return appropriate variant

#### 5.3.2 Lazy Loading

1. **Add loading="lazy"** to all `<img>` tags
2. **Add width/height attributes** to prevent layout shift
3. **Add decode="async"** for non-critical images

### 5.4 Search Performance

#### 5.4.1 Query Result Caching

- Cache search results for identical queries (10 minutes)
- Skip cache for authenticated users with different histories
- Cache key: `search:{query_hash}:{city}:{category}`

#### 5.4.2 Trigram Index for Fuzzy Matching

For autocomplete performance:

```sql
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE INDEX IX_categories_name_trgm ON categories USING gin (name gin_trgm_ops);
CREATE INDEX IX_cities_name_trgm ON cities USING gin (name gin_trgm_ops);
```

### 5.5 Template Optimization

#### 5.5.1 Template Fragment Splitting

Split large templates:
- `ads/partials/ad_card.html` — single ad card
- `ads/partials/stats_card.html` — dashboard stats
- `components/search_dropdown.html` — autocomplete UI
- `components/pagination.html` — reusable pagination

#### 5.5.2 HTMX Response Optimization

- Add `hx-swap-oob` for out-of-band updates (stats)
- Minimize HTML payload in partial responses
- Add `Vary: HX-Request` header for CDN

---

## Phase 2 Task Dependencies

```
graph TD
    A[Seller Dashboard Stats] --> B[Dashboard Template]
    C[Thumbnail Generation] --> D[Media Service Update]
    D --> E[AdImage Migration]
    E --> F[Template Updates]
    G[Autocomplete] --> H[Search Models]
    H --> I[Autocomplete View]
    I --> J[Template Integration]
    K[Saved Search Alerts] --> L[SavedSearch Model]
    L --> M[Alert Service]
    M --> N[Alert Delivery Task]
    O[Perf Optimization] --> P[Index Updates]
    O --> Q[Caching Strategy]
    
    style A fill:#e1f5fe
    style C fill:#e1f5fe
    style G fill:#e1f5fe
    style K fill:#e1f5fe
    style O fill:#e1f5fe
```

---

## Implementation Order

### Priority 1 (High-Impact, Low-Risk)

1. **Seller Dashboard Statistics** — adds immediate value, no schema changes
2. **Thumbnail Generation** — improves UX + performance, backward compatible

### Priority 2 (Medium Complexity)

3. **Search Autocomplete** — requires new models + endpoint
4. **Image WebP Support** — thumbnail variant only

### Priority 3 (Higher Complexity)

5. **Saved Search Alerts** — requires notification system
6. **Database Indexes** — requires migration planning
7. **Caching Strategy** — requires Redis infrastructure

---

## Success Metrics

| Feature | Metric | Target |
|---------|--------|--------|
| Dashboard Stats | Seller retention after 7 days | +15% |
| Thumbnails | Page load time reduction | -30% |
| Autocomplete | Search completion rate | +20% |
| Saved Alerts | Alert engagement rate | >25% |
| Overall Performance | 95th percentile response time | ≤2s |

---

## Rollback Considerations

- Thumbnails: New fields nullable, original photos preserved
- Saved Alerts: Opt-in feature, can be disabled via feature flag
- Autocomplete: Purely frontend enhancement, graceful degradation
- Performance: All optimizations are additive

---

## Notes

- All enhancements maintain backward compatibility with Phase 1
- Feature flags recommended for gradual rollout
- Test coverage required for new services
- Documentation updates in `docs/01-spec/` for each feature