# Enhanced Moderation Tooling — Implementation Plan

## Overview

Implement priority-based moderation queue, bulk operations, and enhanced admin tooling for efficient content review.

**Research:** `.ai/plans/moderation-tooling/research.md`

---

## Task Execution Order

| Task | Description | Symbol | File | Dependencies |
|------|-------------|--------|------|--------------|
| T1 | Add AdModerationPriority model | `AdModerationPriority` | `apps/moderation/models/priority.py` | None |
| T2 | Create PriorityCalculator service | `PriorityCalculator` | `apps/moderation/services/priority_calculator.py` | T1 |
| T3 | Create PriorityService | `PriorityService` | `apps/moderation/services/priority.py` | T1, T2 |
| T4 | Add moderation queue view | `moderation_queue` | `apps/moderation/views/queue.py` | T1 |
| T5 | Create bulk moderation actions | `bulk_moderation_action` | `apps/moderation/views/api_bulk.py` | T3 |
| T6 | Update Admin with priority filters | `EnhancedAdAdmin` | `apps/moderation/admin.py` | T1 |
| T7 | Create priority middleware | `PriorityMiddleware` | `apps/moderation/middleware/priority.py` | T2 |
| T8 | Add advisory lock constant | `AdvisoryLockId.QUEUE_PROCESSING` | `apps/core/enums.py` | None |

---

## Task Details

### T1: Add AdModerationPriority Model

**Symbol:** `AdModerationPriority`  
**File:** `src/backend/apps/moderation/models/priority.py`  
**Priority:** High

```python
class AdModerationPriority(models.Model):
    ad = models.OneToOneField(
        "ads.Ad",
        on_delete=models.CASCADE,
        related_name="moderation_priority"
    )
    base_score = models.PositiveSmallIntegerField(default=0)
    priority_level = models.CharField(
        max_length=10,
        choices=[
            ("high", "High"),
            ("medium", "Medium"),
            ("low", "Low"),
        ],
        default="medium"
    )
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

### T2: Create PriorityCalculator Service

**Symbol:** `PriorityCalculator`  
**File:** `src/backend/apps/moderation/services/priority_calculator.py`  
**Priority:** High

```python
class PriorityCalculator:
    """Calculate priority scores for ads based on content and user history."""

    def calculate_priority(self, ad: Ad) -> dict:
        """Calculate comprehensive priority score for an ad."""
        scores = []
        flags = []

        # Content-based scoring (duplicate title, banned words)
        content_score = self._calculate_content_score(ad)
        scores.append(content_score["score"])
        flags.extend(content_score["flags"])

        # User history scoring
        user_score = self._calculate_user_score(ad)
        scores.append(user_score["score"])
        flags.extend(user_score["flags"])

        total = int(sum(scores) / len(scores)) if scores else 0

        return {
            "base_score": total,
            "priority_level": self._get_priority_level(total),
            "flags": flags,
            "confidence_score": self._estimate_confidence(ad),
            "escalation_required": total >= 80 or len(flags) >= 3,
        }

    def _calculate_content_score(self, ad: Ad) -> dict:
        """Score based on content analysis."""
        from apps.moderation.models import ModerationCriteria

        criteria = ModerationCriteria.get_solo()
        flags = []
        score = 0

        # Check for banned words overlap
        if criteria.banned_words:
            combined = f"{ad.title} {ad.description}".lower()
            for word in criteria.banned_words:
                if word.lower() in combined:
                    flags.append("banned_word")
                    score += 20

        return {"score": score, "flags": flags}

    def _calculate_user_score(self, ad: Ad) -> dict:
        """Score based on user history."""
        flags = []
        score = 0

        # Check user's ad count
        user_ad_count = Ad.objects.filter(user=ad.user).count()
        if user_ad_count > 50:
            score += 15  # Established user, lower risk

        # Check recent rejections
        recent_failures = Ad.objects.filter(
            user=ad.user,
            status__in=[AdStatus.REJECTED, AdStatus.ON_MODERATION_FAILED],
            created_at__gte=timezone.now() - timedelta(days=7)
        ).count()

        if recent_failures > 3:
            flags.append("repeat_offender")
            score += 25

        return {"score": score, "flags": flags}

    def _get_priority_level(self, score: int) -> str:
        if score >= 80:
            return "high"
        if score >= 50:
            return "medium"
        return "low"

    def _estimate_confidence(self, ad: Ad) -> float:
        """Estimate AI confidence in classification."""
        return 0.7  # Placeholder for future ML integration
```

### T3: Create PriorityService

**Symbol:** `PriorityService`  
**File:** `src/backend/apps/moderation/services/priority.py`  
**Priority:** High

```python
class PriorityService:
    """Manage priority calculations and queue operations."""

    def calculate_and_save(self, ad: Ad) -> AdModerationPriority:
        """Calculate priority and save to database."""
        calculator = PriorityCalculator()
        data = calculator.calculate_priority(ad)

        return AdModerationPriority.objects.update_or_create(
            ad=ad,
            defaults=data
        )[0]

    def get_queued_ads(self, priority_filter: str = None) -> QuerySet:
        """Get ads in the moderation queue, optionally filtered by priority."""
        qs = Ad.objects.filter(
            status__in=[AdStatus.ON_MODERATION, AdStatus.ON_MODERATION_FAILED]
        ).select_related(
            "user", "category", "city"
        ).prefetch_related(
            "images", "moderation_priority"
        )

        if priority_filter:
            qs = qs.filter(moderation_priority__priority_level=priority_filter)

        return qs.order_by("-moderation_priority__base_score", "-created_at")
```

### T4: Add Moderation Queue View

**Symbol:** `moderation_queue`  
**File:** `src/backend/apps/moderation/views/queue.py`  
**Priority:** High

```python
@login_required
def moderation_queue(request: HttpRequest) -> HttpResponse:
    """Display moderation queue with priority filtering."""
    priority = request.GET.get("priority", "all")
    service = PriorityService()

    if priority == "all":
        ads = service.get_queued_ads()
    else:
        ads = service.get_queued_ads(priority_filter=priority)

    return render(request, "admin/moderation/queue.html", {
        "ads": ads,
        "selected_priority": priority,
        "priority_counts": {
            "high": service.get_queued_ads("high").count(),
            "medium": service.get_queued_ads("medium").count(),
            "low": service.get_queued_ads("low").count(),
        }
    })
```

### T5: Create Bulk Moderation Actions API

**Symbol:** `bulk_moderation_action`  
**File:** `src/backend/apps/moderation/views/api_bulk.py`  
**Priority:** Medium

```python
@staff_required
@csrf_exempt
def bulk_moderation_action(request: HttpRequest) -> JsonResponse:
    """Handle bulk moderation actions."""
    data = json.loads(request.body)
    action = data.get("action")
    ad_ids = data.get("selected_items", [])
    reason = data.get("reason", "")

    results = {"completed": 0, "errors": []}

    for ad_id in ad_ids:
        try:
            ad = Ad.objects.get(id=ad_id)
            if action == "approve":
                approve_ad(ad, request.user.id, reason)
            elif action == "reject":
                reject_ad(ad, request.user.id, reason)
            elif action == "flag":
                PriorityService().calculate_and_save(ad)

            results["completed"] += 1
        except Exception as e:
            results["errors"].append({"id": ad_id, "error": str(e)})

    return JsonResponse(results)
```

### T6: Update Admin Configuration

**Symbol:** `EnhancedAdAdmin`  
**File:** `src/backend/apps/moderation/admin.py`  
**Priority:** Medium

```python
from apps.moderation.models.priority import AdModerationPriority
from apps.moderation.services.priority import PriorityService

@admin.register(Ad)
class EnhancedAdAdmin(admin.ModelAdmin):
    list_filter = [
        "status", "category", "city",
        "moderation_priority__priority_level",
    ]

    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            "user", "category", "city"
        ).prefetch_related("moderation_priority")

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        service = PriorityService()

        extra_context["priority_queue_stats"] = {
            "high": service.get_queued_ads("high").count(),
            "medium": service.get_queued_ads("medium").count(),
            "low": service.get_queued_ads("low").count(),
        }

        return super().changelist_view(request, extra_context)
```

### T7: Create Priority Middleware

**Symbol:** `PriorityMiddleware`  
**File:** `src/backend/apps/moderation/middleware/priority.py`  
**Priority:** Low

```python
class PriorityCalculationMiddleware:
    """Automatically calculate priority for ads entering moderation."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        # Trigger priority calculation for ads moving to ON_MODERATION
        # Implementation uses post_save signal instead
        return response
```

### T8: Add Advisory Lock Constant

**Symbol:** `AdvisoryLockId.QUEUE_PROCESSING`  
**File:** `src/backend/apps/core/enums.py`  
**Priority:** Medium

```python
class AdvisoryLockId(IntEnum):
    MIGRATION = 100
    ARCHIVE_SWEEP = 1
    DELETE_SWEEP = 2
    CONSENT_HARD_DELETE = 3
    SWEEP_DRAFTS = 4
    CLEANUP_LOGIN_TOKENS = 5
    PURGE_FAILED_ADS = 6
    PURGE_REJECTED_ADS = 7
    QUEUE_PROCESSING = 10  # NEW
```

---

## Verification Commands

```bash
uv run basedpyright src/backend/apps/moderation/
uv run ruff check src/backend/apps/moderation/
uv run pytest src/backend/apps/moderation/tests/test_priority.py -v
```

---

## Risk Assessment

| Risk | Level | Mitigation |
|------|-------|------------|
| Priority calculation performance | Medium | Cache results, defer to background via signals |
| Admin UI complexity | Low | Progressive enhancement, optional features |
| Priority gaming | Medium | Multi-factor scoring, change detection |

---

## Notes

- Priority calculated on ad creation/update via signal
- Queue page shows prioritized ads for moderator efficiency
- Bulk actions logged via `ModeratorActionLog`
- Escalation flag highlights high-risk content for senior review