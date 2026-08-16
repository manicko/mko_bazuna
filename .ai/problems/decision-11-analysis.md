---
id: decision-11-analysis
domain: spec
tags:
  - phase-2
  - analysis
  - integration-gap
  - seed-data
related:
  - spec-index
  - technical-specification
created: 2026-08-10
---

# Decision 11 — Phase 2 Audit & Integration Specification

> Analyzes what from the Phase 2 plan was implemented, what does not work under
> seeded data, root-causes the failures (integration gaps vs. seed-data issues),
> and specifies fixes that respect the existing architecture.

## 1. Executive Summary

The Phase 2 plan (docs/97-plans/phase-02-detailed-plan-1.md, -2.md, -3.md)
described five feature areas: Seller Dashboard Statistics, Photo Thumbnails,
Search Autocomplete, Saved Search Alerts, Trust Signals, Moderation Tooling.

**Status:** Backend code for 4 of 5 areas is fully implemented. The gap is
**predominantly integration** (frontend wiring) with a secondary layer of
**seed-data completeness** issues.

| Feature Area | Backend Implemented | Frontend Wired | Seed Data Complete |
|---|---|---|---|
| Seller Dashboard Stats | Yes (SellerStats) | Yes (dashboard.html) | Partial (no contact events) |
| Photo Thumbnails | Yes (ThumbnailService) | Yes (templates) | Partial (no SHA-256 via bulk_create) |
| Search Autocomplete | Yes (endpoint + services) | **No** | Partial (no PopularSearch data) |
| Saved Search Alerts | No (models only) | No | No |
| Trust Signals | Yes (TrustCalculator) | Partial (badge tags) | **No** (no trust scores) |

## 2. Feature-by-Feature Audit

### 2.1 Search Autocomplete (Plan 3.2)

**Implemented:** autocomplete() view at /api/search/autocomplete (JSON, rate-limited),
PopularSearch model + increment_popular_search() (atomic hit_count), SearchHistory
+ record/get functions (50-entry cap), get_entity_suggestions() (istartswith prefix
match, active categories only), query sanitization, deduplication, max 10 suggestions,
SEARCH_PERFORMED analytics event. 16 tests in test_autocomplete.py.

**What does not work:** The frontend template (ads/list.html) has a plain <form>
posting to /search/ with a bare <input type="search" name="q">. NO JavaScript calls
the autocomplete endpoint. NO dropdown UI exists. Endpoint fully tested but
disconnected from UI.

**Root cause:** Integration gap. Plan task #5 ("Enhance Search Template — add
autocomplete dropdown component, HTMX-driven suggestions") never executed.

**Seed data gap:** AnalyticsGenerator creates AD_VIEWED events but never creates
PopularSearch records. increment_popular_search() is called in search() view only
for non-anonymous users. With seed data (anonymous browsing), popular search source
is always empty.

### 2.2 Seller Dashboard Statistics (Plan 1.1)

**Implemented:** SellerStats service (5-min cache TTL, aggregates AnalyticsEvent
via ad__user_id join), dashboard() view, dashboard.html template, TimeRange StrEnum,
DailyAdMetrics model.

**What works:** Stats card renders correctly. total_views populated from seed
AD_VIEWED events linked via ad__user_id.

**What does not work:**
- total_contacts is ALWAYS 0 — AnalyticsGenerator only creates AD_VIEWED events;
  no CONTACT_INITIATED events are seeded.
- per_ad_stats shows 0 contacts for all ads.
- contact_response_rate in TrustCalculator is ALWAYS 0 (no CONTACT_RESPONSE events,
  no CONTACT_INITIATED events).

**Root cause:** Seed data gap. AnalyticsGenerator.generate_events() produces only
AD_VIEWED events. Plan specified "contact clicks" tracking but seed skipped it.

### 2.3 Photo Thumbnails (Plan 2.1-2.3)

**Implemented:** AdImage model with thumbnail_small/medium/large fields + URL
properties, ThumbnailService (240x180/640x480/1280x960 JPEG q=85), ImageGenerator
(pre-processes photos, generates thumbnails, sets thumbnail_* keys), templates use
thumbnail_small_url/thumbnail_large_url with fallback.

**What works:** Thumbnails generated on disk during seed. Thumbnail_* keys set on
AdImage records. Listing grid and detail pages display thumbnails.

**What does not work:**
- AdImage.save() computes sha256 for dedup, but ImageGenerator uses
  AdImage.objects.bulk_create() which bypasses save(). All seed images have
  sha256="".
- Dedup check in save() never evaluated for seed data.

**Root cause:** Seed data gap. bulk_create intentionally bypasses save() for
performance. SHA-256 field blanked but does not break image display (only dedup).

### 2.4 Trust Signals (Plan 3)

**Implemented:** SellerTrustScore model (trust_level StrEnum, score, ad_count,
rejection_rate, contact_response_rate), SellerVerification model (phone_number,
verified_by_admin, verified_at), TrustCalculator service (activity 40pts + quality
30pts + response 30pts = 100 total), render_trust_badge template tag, badge templates
referenced in ad_list.html and detail.html.

**What works:** Badge rendering pipeline correctly wired in templates.

**What does not work:**
1. NO SellerTrustScore rows exist for seed users — TrustCalculator.calculate_and_save()
   is never called during seeding. No signal handler or scheduled job triggers it
   on ad publish.
2. ALL trust badges render as empty string "" in grid and detail page.
3. Even if triggered, contact_response_rate would be 0 (no contact events seeded).
4. N+1 query: render_trust_badge does SellerTrustScore.objects.get(user=user) per
   ad in grid (24 ads = 24 extra queries). No prefetch_related used.

**Root cause:** Architecture gap. TrustCalculator exists but never wired into ad
lifecycle. No signal or scheduled task triggers it. Plus seed data doesn't create
trust scores.

### 2.5 Moderation Priority (Plan 3.3)

**Implemented:** calculate_ad_priority post_save signal on Ad (triggers when
status=ON_MODERATION), PriorityService, ModerationCriteria singleton (5-min cache),
AdModerationPriority model.

**What works:** Signal fires correctly when Ad.save() called with ON_MODERATION.

**What does not work:**
- Seed uses Ad.objects.bulk_create() which does NOT fire post_save signals.
- Seed ads created directly in PUBLISHED/ARCHIVED status, bypassing moderation.
- No AdModerationPriority records for seed ads (by design).
- This is NOT a bug — seed ads skip moderation by design. Only an issue if
  someone seeds ads with ON_MODERATION status for moderation testing.

**Root cause:** Seed data design (not a bug).

### 2.6 Saved Search Alerts (Plan 4)

**Implemented:** SavedSearch model, SavedSearchNotification model (unique constraint),
AnalyticsEventType.SEARCH_ALERT_MATCHED enum, AdvisoryLockId.ALERT_DELIVERY_TASK=9.

**What does not work:**
- NO views — no CRUD UI for creating/saving searches
- NO AlertService — no logic to find matching ads or send notifications
- NO management command (send_alerts.py) — no scheduled task
- NO bot handler — no /alerts command
- NO seed data — no SavedSearch records

**Root cause:** Partial implementation — only data model layer exists. Views,
services, and jobs were never built.

### 2.7 Search View Context Mismatch

Shared template ads/partials/ad_list.html rendered by both listings() (homepage)
and search() (search results).

listings() passes: page_obj, suggested_category, suggested_city, current_category,
  current_city, current_sort, min_price, max_price, has_results, consent_shown

search() passes only: page_obj, query, has_results
  — missing: consent_shown, current_category, current_city, current_sort,
  min_price, max_price

Impact: When search view renders the partial:
- consent_shown = Undefined → consent banner logic breaks
- current_category etc. = Undefined → pagination URLs lose filter context
- search() does not support category/city/price/sort filters that listings() does

Root cause: Integration gap — two views share template but developed independently
without reconciling context.

### 2.8 Homepage Search Gap

listings() view (homepage at /) does NOT accept or process a 'q' parameter for
FTS. Only /search/ route performs FTS. Search form on homepage posts to
{% url 'search:search' %} which works, but homepage URL never shows search results.

Spec (search-patterns.md) mentions "Hero Search with Location: Combined keyword +
city selector on homepage" — only keyword search form delivered, no integrated
city selector.

## 3. Architecture Violations

### 3.1 print() in SeedService

seed_service.py lines 144-151 use print() for summary output. Violates
project rule #12 (No print() Statements).

### 3.2 N+1 Trust Badge Queries

render_trust_badge (trust_tags.py) does SellerTrustScore.objects.get(user=user)
per call. In listing grid (24 ads), generates 24 extra queries. No
select_related/prefetch_related.

### 3.3 CATEGORY_GROUP_MAP as plain dict

AdGenerator.CATEGORY_GROUP_MAP is module-level dict[str, str]. Could use StrEnum
but is data mapping, not constant set. Low priority.

### 3.4 BADGE_TEMPLATES as plain dict

trust_tags.py BADGE_TEMPLATES: dict[TrustLevel, str]. Same — config mapping,
not constant set.

## 4. Specification: Fixes and Integration Tasks

### 4.1 [P0] Wire Autocomplete Frontend to Search Template

Type: Integration gap (frontend)

What:
1. Add HTMX-based autocomplete JS to ads/list.html calling /api/search/autocomplete
2. Debounced input (300ms) on search <input>
3. Dropdown component below input showing suggestions (text + source badge)
4. Keyboard navigation (up/down/Enter)
5. Clicking suggestion navigates to /search/?q=<text>

Files:
- templates/ads/list.html (add hx-get/hx-trigger, dropdown container)
- templates/components/autocomplete_dropdown.html (new partial)

Dependencies: none (endpoint exists and tested)

Acceptance:
- Typing 2+ chars shows dropdown with suggestions
- Suggestions show text + source badge (category/city/popular/history)
- Selecting navigates to search results
- 429 rate limit gracefully degrades (hide dropdown)
- Works on both homepage and search page

### 4.2 [P0] Add Filter Context to Search View

Type: Integration gap (context)

What:
1. Update search() to accept category, city, min_price, max_price, sort params
2. Pass these values into template context (same as listings())
3. Include consent_shown in context

Files:
- apps/search/views/search.py (add filter parsing + context vars)

Dependencies: none

Acceptance:
- Search pagination preserves all filter params
- Consent banner renders correctly on search page
- Search within category/city context works

### 4.3 [P1] Add Contact Analytics to Seed

Type: Seed data completeness

What:
1. Extend AnalyticsGenerator to generate CONTACT_INITIATED events for published ads
2. Generate CONTACT_RESPONSE events for ~60% of sellers
3. Time-distributed (recent bias, matching view event pattern)
4. CONTACT_INITIATED events: ad_id set, user_id=null (anonymous buyers)
5. CONTACT_RESPONSE events: ad_id=null, user_id=seller

Files:
- apps/seed/generators/analytics.py (add generate_contact_events())
- apps/seed/services/seed_service.py (call new method)

Dependencies: AnalyticsEvent supports these event types

Acceptance:
- Seed sellers have non-zero total_contacts in dashboard
- TrustCalculator would compute non-zero response scores
- Per-ad stats show contact counts

### 4.4 [P1] Generate Trust Scores for Seed Users

Type: Seed data completeness + architecture gap

What:
1. Add step in SeedService.run() after ads persisted to compute trust scores
2. Create SellerVerification records for ~20% of seed users (verified_by_admin=True)
3. Call TrustCalculator().calculate_and_save(user) for each seed user

Files:
- apps/seed/services/seed_service.py (add _seed_trust_scores() step)

Dependencies: TrustCalculator exists

Acceptance:
- Trust badges render for seed sellers (verified/trusted/pro visible in grid)
- total_contacts and contact_response_rate non-zero where contact events exist
- At least 20% of seed users have verified_by_admin=True

### 4.5 [P2] Fix SHA-256 for Seed Images

Type: Seed data completeness (minor)

What:
1. After AdImage bulk_create, compute SHA-256 for each via FileHashService
2. Batch update via .update() (single query)

Files:
- apps/seed/services/seed_service.py (post-bulk_create backfill)

Dependencies: FileHashService exists

Acceptance:
- All seed AdImage records have non-empty sha256
- Image dedup would work for bot-uploaded duplicates

### 4.6 [P1] Fix N+1 Trust Badge Queries

Type: Performance

What:
1. prefetch_related("user__trust_score") in listings() and search() views
2. Modify render_trust_badge to accept optional pre-computed dict from context
3. Backward compatible: falls back to DB lookup if not provided

Files:
- apps/ads/views/listings.py (add prefetch)
- apps/search/views/search.py (add prefetch)
- apps/trust/templatetags/trust_tags.py (use context cache)

Dependencies: none

Acceptance:
- Listing page with 24 ads generates <=2 extra queries for trust badges
- Badges render identically

### 4.7 [P2] Replace print() with Logging in SeedService

Type: Architecture violation

What: Replace all print() calls with logger.info()

Files: apps/seed/services/seed_service.py (lines 144-151)

Acceptance:
- ruff check passes
- basedpyright passes

### 4.8 [P2] Seed PopularSearch Records

Type: Seed data completeness

What:
1. After seeding ads, generate top N queries from seed ad titles
2. Create PopularSearch records with hit_count >= 10

Files:
- apps/seed/generators/analytics.py or new seed step

Acceptance:
- Autocomplete shows popular searches for common terms
- hit_count >= 10 for all seeded records

## 5. Implementation Priority

| Priority | Task | Effort | Impact | Type |
|---|---|---|---|---|
| P0 | 4.2 Filter context to search view | Small | High | Integration |
| P0 | 4.1 Wire autocomplete frontend | Medium | High | Integration |
| P1 | 4.4 Generate trust scores for seed | Small | High | Seed data |
| P1 | 4.3 Add contact analytics to seed | Medium | Medium | Seed data |
| P1 | 4.6 Fix N+1 trust badge queries | Small | Medium | Performance |
| P2 | 4.5 Fix SHA-256 for seed images | Small | Low | Seed data |
| P2 | 4.7 Replace print() with logging | Trivial | Low | Architecture |
| P2 | 4.8 Seed popular search records | Small | Medium | Seed data |

## 6. Test Plan

### 6.1 Existing Tests

| Test File | Coverage | Status |
|---|---|---|
| apps/search/tests/test_autocomplete.py | Autocomplete endpoint, popular search, history, entities, rate limit | PASSING |
| apps/core/tests/test_contact.py | can_contact_seller zone R2 conditions | PASSING |
| (missing) test_search.py | FTS search, translation, fuzzy category | MISSING |
| (missing) test_seller_stats.py | Stats aggregation, caching, time range | MISSING |
| (missing) test_trust_calculator.py | Score computation, trust level mapping | MISSING |

### 6.2 New Tests Required

1. Search view tests (apps/search/tests/test_search.py):
   - FTS query returns ranked results
   - Translation called when LANGUAGE_CODE != ru
   - Fuzzy category match for single-word queries
   - SEARCH_PERFORMED event recorded
   - Pagination (24 per page)
   - HTMX partial returns correct template

2. SellerStats tests (apps/analytics/tests/test_seller_stats.py):
   - Stats computed correctly from analytics events
   - Cache returns cached value without DB query
   - Time range filtering (7d/30d/all)
   - Per-ad breakdown correct

3. TrustCalculator tests (apps/trust/tests/test_trust_calculator.py):
   - Activity score: 5 pts per published ad, capped at 40
   - Quality score: ratio of non-rejected to total ads
   - Response score: CONTACT_RESPONSE / CONTACT_INITIATED ratio
   - Trust level: >=86 PRO, >=61 TRUSTED, >=61 VERIFIED, >=31 VERIFIED
   - Admin verification + Telegram Premium guarantees VERIFIED floor

4. Template integration tests (tests/integration/test_autocomplete_ui.py):
   - Homepage renders search form with autocomplete attributes
   - Autocomplete endpoint called on input
   - Dropdown displays suggestions
   - Clicking suggestion navigates to search

5. Seed integrity tests (apps/seed/tests/test_seed_integrity.py):
   - All seed AdImage records have non-empty sha256
   - All published-seed-user ads have SellerTrustScore records
   - Dashboard shows non-zero total_views AND total_contacts
   - PopularSearch records exist with hit_count >= 10
   - At least 20% of seed users have verified_by_admin=True

## 7. Decisions

1. Autocomplete frontend uses HTMX (consistent with MPA pattern) plus a minimal
   inline script for debouncing + dropdown management.

2. Trust score seeding computes scores AFTER all ads persisted (batch step in
   SeedService.run()), not inline per-ad.

3. Contact events in seed: CONTACT_INITIATED for ~15% of ad views, CONTACT_RESPONSE
   for ~60% of initiated (realistic 30-80% response rates).

4. SHA-256 backfill uses post-bulk_create batch update, not per-record save().

5. N+1 fix uses prefetch_related("user__trust_score") + context-level dict cache
   in template tag (backward compatible).

## 8. Assumptions

- BOSNIAN fts_config returns "simple" (no "bosnian" PostgreSQL config). Correct.
- Seed images are pre-existing JPEG fixtures in fixtures/images/.
- translate_query 500ms timeout may fail in Docker dev without internet, but
  degrades gracefully (falls back to original query).
- Cache backend in dev is LocMemCache (single-process); rate limiter works
  but won't be shared across processes.
- search() view calls translate_query(query, LANGUAGE_CODE, "ru") — if language
  is "en" or "bs", calls Google Translate API; if "ru", skips translation.
- Seed users have telegram_id and chat_id set (required fields) but no username
  for 70% of users (null username allowed by PostgreSQL unique constraint).
- consent_shown context var is checked in consent_banner.html include: if True,
  banner is NOT shown. Anonymous users get consent_shown=True (banner hidden).
  Search view omits this var → template renders consent_banner.html → Undefined
  → evaluates as falsy → banner SHOWN for anonymous search users (unexpected but
  not crashing).
