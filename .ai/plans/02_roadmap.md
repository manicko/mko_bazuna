# Mko Bazuna — Phase 2 Implementation Roadmap

**Version:** Phase 2 Roadmap  
**Date:** July 2026  
**Status:** NOT STARTED — All features are planned but unimplemented

---

## Executive Summary

Phase 2 focuses on enhancing the post-MVP platform with seller tools, search improvements, trust signals, and analytics. The roadmap is organized into seven implementation blocks following the architectural principles from Phase 1.

---

## Implementation Blocks

### 1. Seller Dashboard Statistics

**What to implement:**
- Add `AD_VIEWED` to `AnalyticsEventType` StrEnum in `apps/core/enums.py`
- Add `TimeRange` StrEnum (all_time, 30_days, 7_days) in `apps/core/enums.py`
- Create `SellerStats` service in `apps/analytics/services/seller_stats.py`
  - Cache-based stats aggregation from `analytics_events` table
  - 5-minute TTL for performance
  - Returns: total_views, total_contacts, ads_published, per_ad_stats
- Integrate stats into `DashboardView` context
- Add stats card and time range selector to `dashboard.html`
- Record `AD_VIEWED` events on ad detail page views

**Source documents:**
- `.ai/plans/phase2_seller_dashboard_stats.yaml`
- `.ai/plans/phase2_plan1_research.md`

---

### 2. Photo Thumbnail Generation

**What to implement:**
- Create `ThumbnailSize` StrEnum (SMALL, MEDIUM, LARGE) in `apps/core/enums.py`
- Create `apps/media/` module structure with `ThumbnailService`
- Implement `ThumbnailService.generate_thumbnails()` using Pillow
  - Generate 240x180 (small), 640x480 (medium), 1280x960 (large) variants
  - LANCZOS resampling, EXIF orientation correction
- Add migration for `AdImage` model: `thumbnail_small`, `thumbnail_medium`, `thumbnail_large` fields
- Integrate thumbnail generation into `telegram_bot/handlers/ad_create.py`
- Create backfill management command for existing images
- Update templates to use thumbnails with fallback to originals

**Source documents:**
- `.ai/plans/photo-thumbnail-generation-plan.yaml`

---

### 3. Search Autocomplete

**What to implement:**
- Create `PopularSearch` model in `apps/search/models/popular_searches.py`
- Create `SearchHistory` model in `apps/search/models/search_history.py`
- Create `AutocompleteView` in `apps/search/views/autocomplete.py`
- Create API endpoint `/api/search/autocomplete`
- Implement hybrid suggestions: user history + popular searches + category/city matching
- Add autocomplete dropdown to search template
- Add trigram indexes on category/city names for fuzzy matching

**Source documents:**
- `.ai/plans/phase-02-detailed-plan-1.md` (Section 3)

---

### 4. Saved Search Alerts

**What to implement:**
- Create `SavedSearch` model in `apps/search/models/saved_searches.py`
- Create `SavedSearchNotification` intermediate model
- Create `AlertService` in `apps/search/services/alert_service.py`
- Create daily alert delivery management command
- Add "Save Search" UI to search results (modal/component)
- Create `/alerts` bot command handler for Telegram
- Implement daily digest messaging format

**Source documents:**
- `.ai/plans/phase-02-detailed-plan-1.md` (Section 4)

---

### 5. Trust Signals System

**What to implement:**
- Add `TrustLevel` StrEnum (unverified, verified, trusted, pro) to `apps/core/enums.py`
- Create `SellerTrustScore` model in `apps/analytics/models/seller_trust.py`
- Create `SellerVerification` model in `apps/users/models/verification.py`
- Implement trust calculation service (periodic background task)
- Create badge HTML components (verified, trusted, pro, premium)
- Integrate trust badges into ad cards and detail page
- Add Trust dashboard UI to seller dashboard

**Source documents:**
- `.ai/plans/phase-02-detailed-plan-3.md` (Section 1)

---

### 6. Enhanced Moderation Tooling

**What to implement:**
- Create `AdModerationPriority` model in `apps/moderation/models/priority.py`
- Implement priority score calculation (risk factors: new seller, banned words, duplicates)
- Create `review_queue` view with priority sorting and keyboard shortcuts
- Create `BulkVerifyService` and `BulkRejectService`
- Implement automated flagging triggers:
  - SuspiciousKeywordTrigger
  - DuplicateDetectionTrigger
  - AnomalyDetectionTrigger
- Create moderation analytics dashboard

**Source documents:**
- `.ai/plans/phase-02-detailed-plan-3.md` (Section 2)

---

### 7. Analytics Improvements

**What to implement:**
- Extend `AnalyticsEventType` StrEnum with trust/moderation events:
  - `SELLER_VERIFIED`, `TRUST_LEVEL_UPDATED`
  - `MODERATION_APPROVED`, `MODERATION_REJECTED`, `MODERATION_FLAGGED`
  - `DASHBOARD_VIEWED`, `AD_EDITED`, `AD_REACTIVATED`
  - `CONTACT_COMPLETED`, `AD_REPORTED`
- Create `DailyAdMetrics` model for daily rollups
- Create `SellerTrustDashboard` view
- Create `ModerationAnalytics` view
- Enhance `show_metrics` CLI command for trust reporting

**Source documents:**
- `.ai/plans/phase-02-detailed-plan-3.md` (Section 3)

---

## Cross-Block Dependencies

```
Seller Dashboard Stats ──► TimeRange, AD_VIEWED enum
Photo Thumbnails ──► ThumbnailSize enum, migration
                                    │
Search Autocomplete ──► PopularSearch, SearchHistory models
Saved Alerts ──► SavedSearch model, AlertService
Trust Signals ──► TrustLevel enum, SellerTrustScore model
Moderation Tooling ──► AdModerationPriority model, analytics events
Analytics ──► Extended AnalyticsEventType, DailyAdMetrics
```

---

## Implementation Order (Recommended)

### Priority 1 (Foundation)
1. **Enums** — ThumbnailSize, TimeRange, TrustLevel (extend existing enums)
2. **Seller Dashboard Statistics** — adds immediate value, uses existing analytics
3. **Photo Thumbnail Generation** — improves UX + performance

### Priority 2 (Core Features)
4. **Search Autocomplete** — requires search infrastructure
5. **Trust Signals** — requires analytics extensions

### Priority 3 (Advanced)
6. **Saved Search Alerts** — requires notification system
7. **Enhanced Moderation Tooling** — requires priority system
8. **Analytics Improvements** — cross-cuts all features

---

## Success Metrics Targets

| Feature | Target |
|---------|--------|
| Dashboard Stats | Seller retention after 7 days: +15% |
| Thumbnails | Page load time reduction: -30% |
| Autocomplete | Search completion rate: +20% |
| Trust Signals | Seller verification rate: +25% within 30 days |
| Moderation Queue | Average review time: <5 minutes |
| Auto-flagging | Accuracy: >85% precision |

---

## Risk Assessment

| Risk | Mitigation |
|------|------------|
| Schema changes for thumbnails | Nullable fields, backward-compatible templates |
| Trust score gaming | Multi-factor scoring, admin override |
| False-positive flagging | Manual review queue, reversible actions |
| Notification system complexity | Start with daily digests, defer real-time |