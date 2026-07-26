---
id: roadmap-highlevel
domain: planning
tags:
  - planning
  - roadmap
  - mvp
related:
  - technical-specification
  - user-stories-index
---

# Mko Bazuna — High-Level Roadmap

Phased development plan derived from plan analysis and current implementation status.

---

## Phase 1: MVP Launch — **95% Complete**

Launch core classifieds platform in Montenegro with Telegram-native ad posting and web browsing.

### Implemented Features
- Telegram bot ad creation flow (step-by-step complete)
- PostgreSQL full-text search (Montenegrin→Russian translation active)
- Category filtering via closed admin tree (django-mptt)
- City filtering with typo suggestions ("did you mean")
- Price range filtering
- Ad cards with image, title, price, location in responsive grid
- "Contact seller" deep-link to Telegram bot (anonymity-preserving)
- Hero search with combined keyword + city selector
- Consent banner (DECLINE/WITHDRAW states)
- Admin moderation interface
- Analytics events (REGISTRATION_CREATED, AD_PUBLISHED, SEARCH_PERFORMED, CONTACT_INITIATED)
- Login token system with atomic claim pattern
- Draft ad persistence via ORM
- Auto-moderation service

### Remaining Blockers
| Item | Location | Priority |
|------|----------|----------|
| **Logout view** | apps/users/views/ (new file) | P0 - blocks launch |
| **Search view consent context** | apps/search/views/search.py:83-87 | P0 - banner shows incorrectly |
| **is_declined middleware message** | telegram_bot/middlewares/permissions.py:119-120 | P1 - UX polish |

---

## Phase 2: Post-MVP Enhancements

### Block 1: Seller Dashboard Statistics
Enhanced seller experience with view/contribution metrics.

**What to implement:**
- `AnalyticsEventType.AD_VIEWED` - track ad views per seller
- `TimeRange` StrEnum - filter stats by time period
- `SellerStats` service - aggregate views/contacts/published counts
- Extend `AnalyticsEvent` with nullable `ad_id` FK
- Integrate stats into DashboardView context
- Add view event recording in ad_detail
- Update dashboard.html template with stats card

**Research:** `.ai/plans/seller-dashboard-stats/research.md`

---

### Block 2: Photo Thumbnail Generation
Performance optimization for image loading.

**What to implement:**
- `ThumbnailSize` StrEnum (SMALL: 240x180, MEDIUM: 640x480, LARGE: 1280x960)
- `apps/media/` module with `ThumbnailService`
- Extend `AdImage` model with thumbnail fields
- Integrate thumbnail generation into photo save workflow
- Create backfill management command
- Update templates to use thumbnails with fallback

**Research:** `.ai/plans/photo-thumbnails/research.md`

---

### Block 3: Search Autocomplete
Improved search UX with suggestions.

**What to implement:**
- `PopularSearch` model - aggregated search queries with hit counts
- `SearchHistory` model - per-user search history
- `SearchSuggestionSource` StrEnum
- Rate limiting utility for autocomplete endpoint
- Services: popular_search, search_history, entity_suggestions
- `AutocompleteView` with JSON response
- Update search view to record searches
- Add autocomplete dropdown to search template

**Research:** `.ai/plans/search-autocomplete/research.md`

---

### Block 4: Saved Search Alerts
User engagement via email notifications.

**What to implement:**
- `SavedSearch` model (user, query, filters, is_active)
- `SavedSearchNotification` model (deduplication)
- `SEARCH_ALERT_MATCHED` analytics event type
- `/alerts` command handler in Telegram bot
- `AlertDeliveryTask` management command for daily digest
- Save search modal template for web UI

**Dependencies:** Block 2 (thumbnail generation for alert formatting)

---

## Phase 3: Growth Features

### Block 5: Trust Signals System
Seller reputation and verification indicators.

**What to implement:**
- `TrustLevel` StrEnum (unverified, verified, trusted, pro)
- `SellerTrustScore` model - calculated metrics
- `SellerVerification` model - phone/Telegram Premium flags
- Trust calculation service
- Badge component templates
- Integration into ad cards and detail pages

**Dependencies:** Block 1 (trust analytics build on stats)

---

### Block 6: Enhanced Moderation Tooling
Admin efficiency and automation.

**What to implement:**
- `AdModerationPriority` model - priority scoring
- Priority calculation service
- Review queue view with keyboard shortcuts
- Bulk verify/reject operations
- Automated flagging triggers
- Moderator action logging enhancements

**Dependencies:** Block 5 (priority includes trust level factor)

---

## Phase 4: Advanced Features

### Block 7: Multi-Currency & Infrastructure
Market expansion and scale features.

**What to implement:**
- Multi-currency support with exchange rates
- Tags system for ads
- EAV attributes for category-specific fields
- DRF API for mobile app
- Celery/Redis for background jobs
- S3/R2/MinIO storage integration

**Dependencies:** All Phase 2 features stable

---

## Execution Order

```
Phase 1 Blockers (immediate)
    ↓
Phase 2 Block 1 → Block 2 → Block 3, Block 4 (parallel after Block 2)
    ↓
Phase 3 Block 5 → Block 6
    ↓
Phase 4 Block 7
```

## Estimated Effort

| Phase/Block | Duration |
|-------------|----------|
| Phase 1 completion | 2-3 days |
| Phase 2 total | 3-4 weeks |
| Phase 3 total | 2-3 weeks |
| Phase 4 total | 6-8 weeks (ongoing) |