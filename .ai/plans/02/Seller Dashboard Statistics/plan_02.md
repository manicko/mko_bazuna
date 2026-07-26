# Phase 2 Plan 1: Seller Dashboard Statistics Enhancement
# Generated: 2026-07-26
# Risk Level: MEDIUM (cross-module changes, cache integration)

---
meta:
  phase: 2
  plan: 1
  title: Seller Dashboard Statistics Enhancement
  description: |
    Add seller-facing statistics to dashboard showing ad performance metrics.
    Stats are aggregated from analytics_events table with 5-minute cache TTL.
  risk_level: MEDIUM
  execution_order:
    - T1
    - T3
    - T2
    - T4
    - T5
    - T6
  dependencies:
    task_T1: []
    task_T3: []
    task_T2: [T1, T3]
    task_T4: [T2, T3]
    task_T5: [T1]
    task_T6: [T4]

tasks:
  - id: T1
    symbol: AnalyticsEventType
    action: "Add AD_VIEWED event type to StrEnum"
    file: "src/backend/apps/core/enums.py"
    description: |
      Add AD_VIEWED to AnalyticsEventType enum in core/enums.py.
      This enables tracking of individual ad views for seller statistics.
    rationale: |
      Phase 1 currently lacks view tracking. Adding this enum value allows
      the listings view to record view events that feed into seller stats.
    verification: |
      - uv run basedpyright src/backend/apps/core/enums.py
      - uv run ruff check src/backend/apps/core/enums.py
    after_state: |
      AnalyticsEventType contains five values:
      REGISTRATION_CREATED, AD_PUBLISHED, SEARCH_PERFORMED, CONTACT_INITIATED, AD_VIEWED

  - id: T3
    symbol: TimeRange
    action: "Add TimeRange StrEnum for stats time filtering"
    file: "src/backend/apps/core/enums.py"
    description: |
      Add TimeRange enum with values:
      - ALL_TIME = "all_time"
      - THIRTY_DAYS = "30_days"
      - SEVEN_DAYS = "7_days"
    rationale: |
      Provides semantic time range options for stats filtering.
      Used by SellerStats service and dashboard template selector.
      Follows project rule 10: StrEnum for all fixed values.
    verification: |
      - uv run basedpyright src/backend/apps/core/enums.py
    after_state: |
      TimeRange enum added to core/enums.py with three time range options.

  - id: T2
    symbol: SellerStats
    action: "Create SellerStats service module for stats aggregation"
    file: "src/backend/apps/analytics/services/seller_stats.py"
    description: |
      Create new service module with SellerStats class that:
      - Queries analytics_events table for seller-specific aggregations
      - Caches computed stats for 5 minutes using Django cache
      - Supports time range filtering (all_time, 30_days, 7_days)
      - Provides: total_views, total_contacts, ads_published counts
      - Provides per_ad_stats: dict[int, int] mapping ad_id to view_count
    rationale: |
      Encapsulates all stats logic in a dedicated service module.
      Uses existing cache pattern from apps.core.utils.cache (300s TTL).
      Follows existing service pattern in apps.users.services and apps.moderation.services.
    dependencies:
      - src/backend/apps/analytics/models.py (AnalyticsEvent)
      - src/backend/apps/core/utils/cache.py (cache utilities)
      - src/backend/apps/core/enums.py (AnalyticsEventType, TimeRange)
    verification: |
      - uv run basedpyright src/backend/apps/analytics/services/seller_stats.py
      - uv run ruff check src/backend/apps/analytics/services/seller_stats.py
    after_state: |
      New file exports SellerStats class with:
      - get_stats(user_id, time_range=TimeRange) -> dict
      - _compute_stats_from_events(events_qs) -> dict
      - _get_cache_key(user_id, time_range) -> str

  - id: T4
    symbol: dashboard
    action: "Integrate SellerStats into DashboardView context"
    file: "src/backend/apps/ads/views/dashboard.py"
    description: |
      Modify dashboard() function to:
      - Import SellerStats service and TimeRange enum
      - Read time_range from request.GET with default ALL_TIME
      - Call SellerStats.get_stats() for authenticated user
      - Add stats and selected_time_range to template context
      - Handle cache miss gracefully (returns empty stats)
    rationale: |
      Adds stats data to existing dashboard view.
      Non-breaking change: template handles optional stats.
    dependencies:
      - task_T2 (SellerStats service must exist)
      - task_T3 (TimeRange enum needed)
    verification: |
      - uv run basedpyright src/backend/apps/ads/views/dashboard.py
      - uv run ruff check src/backend/apps/ads/views/dashboard.py
    after_state: |
      dashboard() context includes "seller_stats" dict with view/contact/publish counts.
      Context also includes "selected_time_range" string value.

  - id: T5
    symbol: ad_detail
    action: "Add AD_VIEWED event recording on ad view"
    file: "src/backend/apps/ads/views/listings.py"
    description: |
      Modify ad_detail() function to:
      - Record AnalyticsEvent with type AD_VIEWED on each ad view
      - Use fire-and-forget pattern (sync create, no additional queries)
      - Exclude views from bot-mediated contact (different endpoint)
    rationale: |
      Tracks ad impressions for seller statistics.
      Fire-and-forget avoids impacting page load performance.
    dependencies:
      - task_T1 (AD_VIEWED enum value)
    verification: |
      - uv run basedpyright src/backend/apps/ads/views/listings.py
      - uv run ruff check src/backend/apps/ads/views/listings.py
    after_state: |
      Each successful ad_detail render creates AnalyticsEvent(AD_VIEWED).

  - id: T6
    symbol: dashboard.html
    action: "Add stats card and time range selector to template"
    file: "src/backend/templates/ads/dashboard.html"
    description: |
      Enhance dashboard.html to include:
      - Stats card positioned above grouped ads section
      - Time range selector dropdown (all time, 30 days, 7 days)
      - Display: total views, total contacts, ads published
      - Per-ad view counters in each ad card (for PUBLISHED ads)
      - Uses GET param for time range state management
    rationale: |
      Visual representation of seller statistics.
      Time range selector uses GET param for state management.
      Per-ad counters sourced from SellerStats per_ad_stats breakdown.
    dependencies:
      - task_T4 (stats in context)
    verification: |
      - Manual browser verification
      - Template renders correctly with/without stats data
    after_state: |
      Dashboard displays statistics card with time-selectable metrics.
      Each published ad shows view count badge.

verification_suite:
  - command: "uv run pytest src/backend/apps/analytics/tests/"
    description: "Run analytics service tests (to be created)"
  - command: "uv run pytest src/backend/apps/ads/tests/test_dashboard_stats.py"
    description: "Run dashboard integration tests (to be created)"
  - command: "uv run basedpyright src/backend/apps/analytics/services/"
    description: "Type check analytics services"