# Phase 2 Plan 1: Seller Dashboard Statistics - Research & Verification
# Generated: 2026-07-26
# Risk Level: LOW (research gate, no production changes)

---
meta:
  phase: 2
  plan: 1
  title: Research Questions and Decisions Log
  type: research

decisions:
  decision_1:
    topic: "View counting strategy"
    context: |
      Need to track ad views for seller statistics.
      Options: (a) AnalyticsEvent aggregation, (b) Denormalized counter on Ad model.
    decision: "AnalyticsEvent aggregation"
    rationale: |
      - Existing analytics_events table with CONTACT_INITIATED already implemented
      - PostgreSQL can efficiently aggregate using event_type + user_id + ad_id
      - Consistent with existing architecture (no schema changes needed)
      - 5-minute cache tolerates query overhead for dashboard use case
    dependencies:
      - task_T1 (add AD_VIEWED event type)
      - task_T2 (SellerStats service queries events)

  decision_2:
    topic: "Per-ad view counters storage"
    context: |
      How to provide per-ad view counts for display in dashboard?
      Options: (a) Include in SellerStats response, (b) Separate query per ad, (c) Annotate in ORM.
    decision: "Include in SellerStats response"
    rationale: |
      - Single query to fetch all per-ad stats
      - Avoids N+1 in template rendering
      - SellerStats service returns both aggregate and per-ad breakdown
      - Cache includes both aggregate and per-ad data

  decision_3:
    topic: "Time range implementation"
    context: |
      Time range selector needs backend support.
      Options: (a) Query parameter with server-side filtering, (b) Client-side JS filtering, (c) Both.
    decision: "Server-side query parameter with server-side filtering"
    rationale: |
      - Server-side filtering ensures accurate counts
      - Query param in GET maintains browser-back compatibility
      - HTMX can enhance without breaking basic functionality
      - TimeRange enum provides semantic values

research_notes:
  - "AnalyticsEvent already has index on timestamp via auto_now_add"
  - "No need for additional DB indexes for AD_VIEWED - timestamp index sufficient"
  - "Cache key pattern: seller_stats:{user_id}:{time_range}"
  - "Following pattern from apps.core.utils.cache (300s TTL)"
  - "SellerStats service should be in apps/analytics/services/ following existing service location pattern"
  - "Per-ad stats dict keyed by ad_id for O(1) template lookup"