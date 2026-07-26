# Enhanced Moderation Tooling — Research Document

## Current State Analysis

### Existing Moderation Components

**1. Moderation Criteria Model** (`apps/moderation/models.py`)
- Singleton model for auto-moderation rules
- Fixed length validations (title: 5-100 chars, description: 10-2000 chars)
- Feature flags (price_required, min/max images)
- Banned words list (case-insensitive)
- User limits (max 10 active ads per user)
- Duplicate title detection (85% threshold via difflib)
- Updated timestamp and audit trail

**2. ModeratorActionLog Model**
- Comprehensive audit trail for all moderator actions
- Links to ads and users (nullable for deletion protection)
- TEXT field for internal-only reasons
- 5 action types: REJECT, BAN_ACCOUNT, SOFT_DELETE, CRITERIA_CHANGE, OTHER
- Auto-display for UI: show ad ID and user telegram_id

**3. Auto-modération Service** (`apps/moderation/services/auto_moderation.py`)
- 300-second Redis cache for ModerationCriteria
- Sequential validation: title → description → price → images → banned words → user limits → duplicates
- Auto-sets ON_MODERATION_FAILED on rule violation
- Auto-publishes on success (coordinated with analytics)
- Seller-safe error messages in `check()` function

**4. Manual Moderation Views** (`apps/moderation/views/review.py`)
- Admin-only (staff/superuser) access control decorator
- Dedicated review page with photo grid and metadata
- Approve, reject, and ban endpoints
- Rejection reason construction from category + text

**5. Admin Actions Service** (`apps/moderation/admin_actions.py`)
- Individual ad actions: approve, reject, ban, soft delete
- Bulk operations: bulk_approve, bulk_reject, bulk_ban_users, bulk_delete
- Moderator logging via dedicated moderation_log service
- Transactional operations (PKs follow auto-modération patterns)

**6. Supporting Infrastructure**
- Signals for cache invalidation
- Test coverage for validation functions (19 test cases)
- Standard Django admin integration for singleton criteria

### Technical Architecture

**Stack Compliance**
- Python 3.14, Django 5.2 LTS
- PostgreSQL 18 with native FTS
- aiogram 3 for Telegram bot integration
- Single shared ORM between web and bot processes
- Migrations run once before both services start

**Concurrency Model**
- Signals-based auto-modération (post-save)
- Database advisory locks for long-running jobs (`AdvisoryLockId`)
- Singleton enforcement via 0002 migration

## Gap Analysis

### Missing Features (vs. Implementation Plan)

**1. Priority-Based Moderation Queue**
- **GAP**: No system to prioritize ads for review
- **CURRENT**: FIFO processing, all ads equal priority
- **IMPACT**: Moderators overwhelmed with low-risk content, high-risk content backlog

**2. Multi-Factor Priority Scoring**
- **GAP**: Single-pass validation only (pass/fail)
- **CURRENT**: No content risk assessment, user history scoring
- **IMPACT**: No ability to triage moderate vs. critical violations

**3. Enhanced Admin UX**
- **GAP**: Basic review page only
- **CURRENT**: Limited filtering, no queue statistics
- **IMPACT**: Poor moderator experience, inefficiency

**4. Advanced Bulk Operations**
- **GAP**: Simple bulk operations (approve/reject)
- **CURRENT**: No preview mode, limited action options
- **IMPACT**: Manual processing, higher error rates

## Modern Moderation Patterns (2026)

### Priority Queues

Priority levels based on multiple factors:
- **HIGH**: immediate review (rule violations, repeat offenders)
- **MEDIUM**: standard processing (edge cases)
- **LOW**: batch processing (established users, minor issues)

Database index strategy for priority queries with GIN indexes on relevant fields.

### Bulk Operations Optimization

- Transaction-aware operations with `SELECT FOR UPDATE`
- Batch processing with progress tracking
- Error handling and rollback on partial failures
- Preview mode before execution

### Admin UX Improvements

- Priority-based review queue with visual indicators
- Bulk action panels with preview and reason templates
- Real-time statistics dashboard
- Keyboard shortcuts for efficiency

### Escalation Pathways

Tiered review system:
- Tier 1 (Auto): Basic validation (current)
- Tier 2 (Staff): Moderate risk, standard content
- Tier 3 (Senior): High risk, complex violations

## Implementation Recommendations

### Data Model: AdModerationPriority

```python
class AdModerationPriority(models.Model):
    ad = models.OneToOneField("ads.Ad", on_delete=models.CASCADE, related_name="moderation_priority")
    base_score = models.PositiveSmallIntegerField(default=0)
    priority_level = models.CharField(max_length=10, choices=[("high", "High"), ("medium", "Medium"), ("low", "Low")])
    flags = models.JSONField(default=list, blank=True)
    confidence_score = models.FloatField(default=0.0)
    escalation_required = models.BooleanField(default=False)

    class Meta:
        db_table = "ad_moderation_priority"
        indexes = [
            models.Index(fields=["priority_level"]),
            models.Index(fields=["base_score"]),
            models.Index(fields=["escalation_required"]),
        ]
```

### PriorityCalculator Service

Multi-factor scoring:
- Content-based (duplicate title, banned words): 0-50 points
- User-based (repeat offender, established seller): 0-30 points
- Total score determines priority level

### PriorityService

Queue management with priority filtering and annotation support for admin views.

### Integration Points

- Signal integration on Ad status change to ON_MODERATION
- Admin interface with priority filters
- Bulk actions API with preview mode
- Advisory lock for queue processing (AdvisoryLockId.QUEUE_PROCESSING)

## Risk Assessment

| Risk | Level | Mitigation |
|------|-------|------------|
| Performance impact | Medium | Background calculation via signals, caching |
| Priority gaming | Medium | Multi-factor scoring, anomaly detection |
| Admin complexity | Low | Progressive enhancement, optional features |