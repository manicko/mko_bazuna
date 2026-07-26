# Mko Bazuna — Implementation Roadmap
# Derived from plan analysis and current implementation status

---

## Phase 1: MVP Launch (Montenegro) — 95% Complete

**Status:** Foundation implemented, pending final integration testing.

### Implemented Features
- Telegram bot ad creation flow (category → city → title → description → price → photos)
- PostgreSQL full-text search with Montenegrin→Russian translation
- Category filtering via django-mptt
- City filtering with typo suggestions
- Price range filtering
- Ad cards with image, title, price, location
- Consent banner (DECLINE/WITHDRAW states)
- Admin moderation interface
- Analytics events (REGISTRATION_CREATED, AD_PUBLISHED, SEARCH_PERFORMED, CONTACT_INITIATED)
- Login token system with atomic claim pattern
- Draft ad persistence via ORM
- Auto-moderation service

### Remaining Tasks
- End-to-end smoke tests verification
- Production deployment configuration (docker-compose finalization)

---

## Phase 2: Post-MVP Enhancements — Not Started

### Block 1: Seller Dashboard Statistics

**What to implement:**
- Add `AD_VIEWED` to `AnalyticsEventType` enum in `apps/core/enums.py`
- Create `TimeRange` StrEnum in `apps/core/enums.py` (all_time, 30_days, 7_days)
- Create `SellerStats` service in `apps/analytics/services/seller_stats.py`
- Integrate stats into `DashboardView` context
- Add `AD_VIEWED` event recording in `ad_detail()` view
- Update `dashboard.html` template with stats card and time range selector

**Dependencies:** None (foundational enhancement)

**Priority:** High (adds immediate seller value)

### Block 2: Photo Thumbnail Generation

**What to implement:**
- Add `ThumbnailSize` StrEnum to `apps/core/enums.py` (SMALL: 240x180, MEDIUM: 640x480, LARGE: 1280x960)
- Create `apps/media/` module structure
- Implement `ThumbnailService.generate_thumbnails()` in `apps/media/services/thumbnails.py`
- Update `AdImage` model with `thumbnail_small`, `thumbnail_medium`, `thumbnail_large` fields
- Integrate thumbnail generation into `save_photo()` workflow
- Create `backfill_thumbnails` management command
- Update templates to use thumbnails with fallback to originals

**Dependencies:** Photo handling already in place (telegram_bot/services/media.py)

**Priority:** High (performance optimization)

### Block 3: Search Autocomplete

**What to implement:**
- Create `PopularSearch` model in `apps/analytics/models.py`
- Create `SearchHistory` model in `apps/analytics/models.py`
- Add `SearchSuggestionSource` StrEnum to `apps/core/enums.py`
- Create `sanitize_autocomplete_query()` function in `apps/core/utils/sanitize.py`
- Create rate limiting utility in `apps/search/services/rate_limit.py`
- Create `get_popular_suggestions()` and `increment_popular_search()` services
- Create `get_user_search_history()` service
- Create `AutocompleteView` in `apps/search/views/autocomplete.py`
- Add URL route `/api/search/autocomplete`
- Update `search()` view to record searches
- Add autocomplete dropdown to search template

**Dependencies:** Existing search infrastructure (query_translator.py, search views)

**Priority:** Medium (UX enhancement)

### Block 4: Saved Search Alerts

**What to implement:**
- Create `SavedSearch` model (user, query, city, category, price range, is_active)
- Create `SavedSearchNotification` model (intermediate table for deduplication)
- Add `SEARCH_ALERT_MATCHED` to `AnalyticsEventType` enum
- Add `ALERT_DELIVERY_TASK` to `AdvisoryLockId` enum
- Create `/alerts` command handler in Telegram bot
- Create `AlertDeliveryTask` management command for daily digest
- Create save search modal template for web UI
- Register `apps.saved_searches` in INSTALLED_APPS

**Dependencies:** Thumbnail generation (for alert message formatting)

**Priority:** Medium (engagement feature)

---

## Phase 3: Growth Features — Not Started

### Block 5: Trust Signals System

**What to implement:**
- Add `TrustLevel` StrEnum (unverified, verified, trusted, pro)
- Create `SellerTrustScore` model (trust metrics, calculated periodically)
- Create `SellerVerification` model (phone verification, Telegram Premium flag)
- Create trust calculation service
- Create badge component templates (verified, trusted, pro badges)
- Integrate trust display into ad cards and detail page

**Dependencies:** Seller Dashboard Statistics (trust analytics build on stats)

**Priority:** Medium

### Block 6: Enhanced Moderation Tooling

**What to implement:**
- Create `AdModerationPriority` model (priority scoring)
- Create priority calculation service
- Create review queue view with keyboard shortcuts
- Create bulk verify/reject services
- Create automated flagging triggers

**Dependencies:** Trust Signals (priority includes trust level factor)

**Priority:** Medium

---

## Phase 4: Advanced Features — Not Started

### Block 7: Multi-Currency & Advanced Features

**What to implement:**
- Multi-currency support with exchange rates
- Tags system for ads
- EAV attributes for category-specific fields
- DRF API for mobile app
- Celery/Redis for background jobs
- S3/R2/MinIO storage integration

**Dependencies:** All Phase 2 features stable

**Priority:** Low (deferred until market expansion)

---

## Critical Path for Next Sprint

1. **Week 1-2:** Seller Dashboard Statistics (T1-T6)
2. **Week 2-3:** Photo Thumbnail Generation (T1.1-T5.3)
3. **Week 3-4:** Search Autocomplete (parallel with thumbnails)
4. **Week 4-5:** Saved Search Alerts (depends on thumbnails)
5. **Week 5-6:** Trust Signals System (Plan 3)

---

## Notes

- All Phase 2 features are additive and backward-compatible
- Feature flags recommended for gradual rollout
- Redis required for caching (defer from Phase 1 as planned)
- Thumbnail fields nullable for safe rollback