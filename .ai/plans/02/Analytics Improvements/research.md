# Analytics Improvements - Research Document

**Date:** 2026-07-27  
**Scope:** Phase 2 Plan 3 - Analytics Improvements Implementation  
**Status:** Research Complete - Implementation Ready

---

## 1. Current Architecture Analysis

### 1.1 AnalyticsEvent Model (apps/analytics/models.py)

| Field | Type | Purpose | Status |
|-------|------|---------|--------|
| event_type | CharField(30) | Enum: REGISTRATION_CREATED, AD_PUBLISHED, SEARCH_PERFORMED, CONTACT_INITIATED | EXISTS |
| timestamp | DateTimeField | Event timestamp (auto_now_add) | EXISTS |
| user | FK(User, nullable) | User triggered event (SET NULL on erasure) | EXISTS |
| ad | FK(Ad) | MISSING - Cannot associate events with specific ads | MISSING |

**Critical Finding:** The AnalyticsEvent model lacks an ad ForeignKey, preventing per-ad analytics. This is BLOCKING.

### 1.2 AnalyticsEventType Enum

Current values: REGISTRATION_CREATED, AD_PUBLISHED, SEARCH_PERFORMED, CONTACT_INITIATED

### 1.3 Existing Infrastructure

- show_metrics.py provides basic aggregation (no trust/moderation metrics)
- CACHES setting missing from base.py - production blocker

---

## 2. Gap Analysis

| # | Gap | Affected Tasks | Severity |
|---|-----|---------------|----------|
| G1 | AnalyticsEvent lacks ad FK | AN-001, AN-005 | BLOCKING |
| G2 | No extended event types | AN-001 | BLOCKING |
| G3 | No DailyAdMetrics model | AN-002, AN-005 | High |
| G4 | No trust analytics service | AN-003 | High |
| G5 | No moderation analytics service | AN-004 | High |

---

## 3. Extended Event Types

SELLER_VERIFIED, TRUST_LEVEL_UPDATED, MODERATION_APPROVED, MODERATION_REJECTED,
MODERATION_FLAGGED, DASHBOARD_VIEWED, AD_EDITED, AD_REACTIVATED, CONTACT_COMPLETED,
AD_REPORTED

---

## 4. Modern Analytics Patterns (2026)

Pre-aggregation with summary tables for historical metrics.
Materialized views with CONCURRENTLY for near real-time.
Composite indexes on (event_type, timestamp).
BRIN indexes for time-series on large tables.

---

## 5. Dependencies

| Module | Dependency | Nature |
|--------|------------|--------|
| apps.analytics | apps.ads.Ad | FK target |
| apps.analytics | apps.users.User | Existing FK |
| apps.analytics | apps.core.enums | Extended enum |
| apps.trust | apps.core.enums.TrustLevel | Trust display |

---

## 6. Implementation Recommendations

1. Add AnalyticsEvent.ad FK migration
2. Extend AnalyticsEventType enum
3. Create DailyAdMetrics model
4. Create TrustAnalytics service
5. Create ModerationAnalytics service
6. Create daily rollup management command

---

## 7. Risk Assessment

Schema migration: Medium risk, nullable field.
Performance: Medium, background jobs recommended.
Trust accuracy: Medium, multi-factor scoring.
Badge overhead: Low, annotation strategy.

---

## 8. File Manifest

### New Files
src/backend/apps/analytics/services/__init__.py
src/backend/apps/analytics/services/trust_analytics.py
src/backend/apps/analytics/services/moderation_analytics.py
src/backend/apps/analytics/migrations/0002_analytics_event_ad_fk.py

### Modified Files
src/backend/apps/core/enums.py
src/backend/apps/analytics/models.py
src/backend/apps/moderation/services/auto_moderation.py
src/backend/apps/core/services/contact.py
src/backend/apps/analytics/management/commands/show_metrics.py

---

## 9. Success Metrics Alignment

| Metric | Target | Measurement Method |
|--------|--------|-------------------|
| Trust scores updated on publish | 100% | Test coverage |
| Badge display performance | <5% overhead | Query profiling |
| Seller verification uptake | +25% within 30 days | Analytics event count |

---

## 10. Key Decisions Required

1. DailyAdMetrics refresh: daily recommended
2. Historical backfill: No, start fresh
3. Trust score visibility: Badge level only
4. Moderation dashboard: Staff-only
5. Event attribution: Lifetime + 30-day rolling

---

## 11. References

- Phase 2 Plan 3: .ai/plans/phase-02-detailed-plan-3.md
- Trust Research: .ai/plans/02/Trust Signals System/research.md
- Analytics Models: src/backend/apps/analytics/models.py
- Core Enums: src/backend/apps/core/enums.py
- Auto-moderation Service: src/backend/apps/moderation/services/auto_moderation.py
