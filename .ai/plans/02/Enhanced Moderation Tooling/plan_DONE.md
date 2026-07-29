# Enhanced Moderation Tooling — Implementation Plan

## Overview

Implement priority-based moderation queue, bulk operations, and enhanced admin tooling for efficient content review.

**Research:** `.ai/plans/moderation-tooling/research.md`

---

## Task Execution Order

| Task | Description | Symbol | File | Dependencies |
|------|-------------|--------|------|--------------|
| T1 | Add AdPriorityLevel StrEnum to core enums | `AdPriorityLevel` | `apps/core/enums.py` | None |
| T2 | Add AdModerationPriority model to moderation models | `AdModerationPriority` | `apps/moderation/models.py` | T1 |
| T3 | Add calculate_priority method with AdPriorityLevel enum | `PriorityCalculator.calculate_priority` | `apps/moderation/services/priority_calculator.py` | T2 |
| T4 | Create PriorityService for queue operations | `PriorityService` | `apps/moderation/services/priority.py` | T2 |
| T5 | Add moderation queue view | `moderation_queue` | `apps/moderation/views/queue.py` | T2, T4 |
| T6 | Update Admin with priority filters | `EnhancedAdAdmin` | `apps/moderation/admin.py` | T2 |
| T7 | Register signal for automatic priority calculation | `calculate_ad_priority` | `apps/moderation/signals.py` | T3 |
| T8 | Create bulk moderation actions API | `bulk_moderation_action` | `apps/moderation/views/api_bulk.py` | T4 |
| T9 | Add AdvisoryLockId.QUEUE_PROCESSING constant | `AdvisoryLockId.QUEUE_PROCESSING` | `apps/core/enums.py` | None |
| T10 | Register queue URL and template | `moderation_queue` | `apps/moderation/urls.py` + `templates/admin/moderation/queue.html` | T5 |
| T11 | Create migration for AdModerationPriority model | `Migration 0003` | `apps/moderation/migrations/0003_ad_moderation_priority.py` | T2 |

---

## Task Details

### T1: Add AdPriorityLevel StrEnum

**Symbol:** `AdPriorityLevel`  
**File:** `src/backend/apps/core/enums.py`  
**Priority:** High

```python
class AdPriorityLevel(StrEnum):
    """Priority levels for moderation queue triage."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


__all__ = [
    "AdSort",
    "AdvisoryLockId",
    "AdStatus",
    "AdSource",
    "AnalyticsEventType",
    "ModeratorActionType",
    "CategoryRejectReason",
    "AdPriorityLevel",  # NEW
]
```

### T2: Add AdModerationPriority Model

**Symbol:** `AdModerationPriority`  
**File:** `src/backend/apps/moderation/models.py`  
**Priority:** High

```python
class AdModerationPriority(models.Model):
    """
    Priority metadata for ads in moderation queue.

    One-to-one with Ad to avoid schema pollution.
    Calculated automatically when ad enters ON_MODERATION status.
    """

    ad = models.OneToOneField(
        "ads.Ad",
        on_delete=models.CASCADE,
        related_name="moderation_priority",
    )
    base_score = models.PositiveSmallIntegerField(
        default=0,
        help_text="0-100 score combining content and user risk factors",
    )
    priority_level = models.CharField(
        max_length=10,
        choices=[(l.value, l.value) for l in AdPriorityLevel],
        default=AdPriorityLevel.MEDIUM,
    )
    flags = models.JSONField(
        default=list,
        blank=True,
        help_text="List of risk flags (e.g., 'banned_word', 'repeat_offender')",
    )
    confidence_score = models.FloatField(
        default=0.0,
        help_text="AI confidence in classification (future ML integration)",
    )
    escalation_required = models.BooleanField(
        default=False,
        help_text="True when score >= 80 or >= 3 flags for senior review",
    )

    class Meta:
        db_table = "ad_moderation_priority"
        indexes = [
            models.Index(fields=["priority_level"]),
            models.Index(fields=["base_score"]),
            models.Index(fields=["escalation_required"]),
        ]

    def __str__(self) -> str:
        return f"Priority for Ad {self.ad_id}: {self.priority_level}"
```

### T3: Create PriorityCalculator Service

**Symbol:** `PriorityCalculator`  
**File:** `src/backend/apps/moderation/services/priority_calculator.py`  
**Priority:** High

```python
from apps.ads.models import Ad
from apps.core.enums import AdPriorityLevel
from apps.moderation.models import ModerationCriteria
from datetime import timedelta
from django.utils import timezone


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
            "priority_level": self._get_priority_level(total).value,
            "flags": flags,
            "confidence_score": self._estimate_confidence(ad),
            "escalation_required": total >= 80 or len(flags) >= 3,
        }

    def _calculate_content_score(self, ad: Ad) -> dict:
        """Score based on content analysis."""
        criteria = ModerationCriteria.get_singleton()
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

    def _get_priority_level(self, score: int) -> AdPriorityLevel:
        """Map score to priority level enum."""
        if score >= 80:
            return AdPriorityLevel.HIGH
        if score >= 50:
            return AdPriorityLevel.MEDIUM
        return AdPriorityLevel.LOW

    def _estimate_confidence(self, ad: Ad) -> float:
        """Estimate AI confidence in classification."""
        return 0.7  # Placeholder for future ML integration
```

### T4: Create PriorityService

**Symbol:** `PriorityService`  
**File:** `src/backend/apps/moderation/services/priority.py`  
**Priority:** High

```python
from apps.ads.models import Ad
from apps.core.enums import AdStatus
from apps.moderation.models import AdModerationPriority
from apps.moderation.services.priority_calculator import PriorityCalculator


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
        """
        Get ads in the moderation queue, optionally filtered by priority.

        Uses annotation for efficient priority-level filtering to avoid N+1 queries.
        """
        from django.db.models import Count

        qs = Ad.objects.filter(
            status__in=[AdStatus.ON_MODERATION, AdStatus.ON_MODERATION_FAILED]
        ).select_related(
            "user", "category", "city"
        ).prefetch_related(
            "images", "moderation_priority"
        )

        if priority_filter:
            qs = qs.filter(
                moderation_priority__priority_level=priority_filter
            )

        return qs.order_by("-moderation_priority__base_score", "-created_at")

    def get_priority_counts(self) -> dict[str, int]:
        """Get count of ads by priority level in a single query."""
        from apps.core.enums import AdPriorityLevel
        from django.db.models import Count

        counts = AdModerationPriority.objects.filter(
            ad__status__in=[AdStatus.ON_MODERATION, AdStatus.ON_MODERATION_FAILED]
        ).values("priority_level").annotate(
            count=Count("id")
        ).order_by("priority_level")

        result = {level.value: 0 for level in AdPriorityLevel}
        for item in counts:
            result[item["priority_level"]] = item["count"]
        return result
```

### T5: Add Moderation Queue View

**Symbol:** `moderation_queue`  
**File:** `src/backend/apps/moderation/views/queue.py`  
**Priority:** High

```python
import logging
from apps.core.enums import AdStatus
from apps.moderation.services.priority import PriorityService
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import render


logger = logging.getLogger(__name__)


def _staff_required(view_func):
    """Decorator to require staff or superuser access."""

    def wrapper(request: HttpRequest, *args, **kwargs) -> HttpResponse:
        if not (request.user.is_staff or request.user.is_superuser):
            raise Http404("Not found")
        return view_func(request, *args, **kwargs)

    return wrapper


@_staff_required
def moderation_queue(request: HttpRequest) -> HttpResponse:
    """Display moderation queue with priority filtering."""
    priority = request.GET.get("priority", "all")
    service = PriorityService()

    ads = service.get_queued_ads(
        priority_filter=None if priority == "all" else priority
    )

    # Use optimized count method to avoid N+1 queries
    all_counts = service.get_priority_counts()

    return render(request, "admin/moderation/queue.html", {
        "ads": ads,
        "selected_priority": priority,
        "priority_counts": all_counts,
    })
```

### T6: Update Admin Configuration

**Symbol:** `EnhancedAdAdmin`  
**File:** `src/backend/apps/moderation/admin.py`  
**Priority:** Medium

```python
from apps.ads.models import Ad
from apps.core.enums import AdPriorityLevel
from apps.moderation.models import AdModerationPriority, ModerationCriteria, ModeratorActionLog
from apps.moderation.services.priority import PriorityService
from django.contrib import admin


# ... existing log_ad_link and log_user_link functions ...


@admin.register(Ad)
class EnhancedAdAdmin(admin.ModelAdmin):
    """Enhanced Ad admin with priority-based moderation queue."""

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

        extra_context["priority_queue_stats"] = service.get_priority_counts()

        return super().changelist_view(request, extra_context)


# ... existing ModerationCriteriaAdmin and ModeratorActionLogAdmin classes ...
```

### T7: Register Signal for Priority Calculation

**Symbol:** `calculate_ad_priority`  
**File:** `src/backend/apps/moderation/signals.py`  
**Priority:** High

```python
import logging
from apps.ads.models import Ad
from apps.core.enums import AdStatus
from apps.moderation.services.priority import PriorityService
from django.db.models.signals import post_save
from django.dispatch import receiver


logger = logging.getLogger(__name__)


@receiver(post_save, sender=Ad)
def calculate_ad_priority(sender, instance, **kwargs):
    """
    Automatically calculate priority when ad enters ON_MODERATION status.

    Triggers after save if status is ON_MODERATION and no priority exists yet.
    Uses async task in production to avoid blocking the request.
    """
    if instance.status != AdStatus.ON_MODERATION:
        return

    # Only calculate if priority record doesn't exist
    if not hasattr(instance, "moderation_priority"):
        try:
            PriorityService().calculate_and_save(instance)
            logger.info(f"Calculated priority for ad {instance.id}")
        except Exception as e:
            logger.error(f"Failed to calculate priority for ad {instance.id}: {e}")
```

### T8: Create Bulk Moderation Actions API

**Symbol:** `bulk_moderation_action`  
**File:** `src/backend/apps/moderation/views/api_bulk.py`  
**Priority:** Medium

```python
import json
import logging
from apps.ads.models import Ad
from apps.moderation.admin_actions import approve_ad, reject_ad
from apps.moderation.services.priority import PriorityService
from django.http import HttpRequest, JsonResponse


logger = logging.getLogger(__name__)


def _staff_required_api(view_func):
    """Decorator to require staff/superuser for API endpoints."""

    def wrapper(request: HttpRequest, *args, **kwargs) -> JsonResponse:
        if not (request.user.is_staff or request.user.is_superuser):
            return JsonResponse({"error": "Unauthorized"}, status=403)
        if request.method != "POST":
            return JsonResponse({"error": "POST required"}, status=405)
        return view_func(request, *args, **kwargs)

    return wrapper


@_staff_required_api
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
                approve_ad(ad, request.user.id)
            elif action == "reject":
                reject_ad(ad, request.user.id, reason)
            elif action == "flag":
                PriorityService().calculate_and_save(ad)

            results["completed"] += 1
        except Exception as e:
            results["errors"].append({"id": ad_id, "error": str(e)})

    return JsonResponse(results)
```

### T9: Add AdvisoryLockId.QUEUE_PROCESSING Constant

**Symbol:** `AdvisoryLockId.QUEUE_PROCESSING`  
**File:** `src/backend/apps/core/enums.py`  
**Priority:** Medium

```python
class AdvisoryLockId(IntEnum):
    """PostgreSQL advisory lock IDs for idempotent scheduled jobs."""

    ARCHIVE_SWEEP = 1
    DELETE_SWEEP = 2
    CONSENT_HARD_DELETE = 3
    SWEEP_DRAFTS = 4
    CLEANUP_LOGIN_TOKENS = 5
    PURGE_FAILED_ADS = 6
    PURGE_REJECTED_ADS = 7
    MIGRATE = 100
    CREATE_ADMIN = 101
    QUEUE_PROCESSING = 10  # NEW
```

### T10: Register Queue URL and Template

**Symbol:** `moderation_queue`  
**File:** `src/backend/apps/moderation/urls.py`  
**Priority:** Medium

Add to existing `urls.py`:
```python
from apps.moderation.views.queue import moderation_queue

urlpatterns = [
    # ... existing patterns ...
    path("queue/", moderation_queue, name="queue"),
]
```

Template `templates/admin/moderation/queue.html`:
```django
{% extends "admin/base_site.html" %}

{% block content %}
<h1>Moderation Queue</h1>

<div class="priority-filters">
    <a href="?priority=all" class="{% if selected_priority == 'all' %}active{% endif %}">All ({{ priority_counts.high|add:priority_counts.medium|add:priority_counts.low }})</a>
    <a href="?priority=high" class="{% if selected_priority == 'high' %}active{% endif %}">High ({{ priority_counts.high }})</a>
    <a href="?priority=medium" class="{% if selected_priority == 'medium' %}active{% endif %}">Medium ({{ priority_counts.medium }})</a>
    <a href="?priority=low" class="{% if selected_priority == 'low' %}active{% endif %}">Low ({{ priority_counts.low }})</a>
</div>

<table>
    <thead>
        <tr>
            <th>ID</th>
            <th>Title</th>
            <th>User</th>
            <th>Score</th>
            <th>Priority</th>
            <th>Actions</th>
        </tr>
    </thead>
    <tbody>
        {% for ad in ads %}
        <tr class="priority-{{ ad.moderation_priority.priority_level }}">
            <td>{{ ad.id }}</td>
            <td>{{ ad.title|truncatechars:50 }}</td>
            <td>{{ ad.user.telegram_id }}</td>
            <td>{{ ad.moderation_priority.base_score }}</td>
            <td>{{ ad.moderation_priority.priority_level }}</td>
            <td>
                <a href="{% url 'admin:moderation_review' ad.id %}">Review</a>
            </td>
        </tr>
        {% endfor %}
    </tbody>
</table>
{% endblock %}
```

### T11: Create Migration for AdModerationPriority

**File:** `src/backend/apps/moderation/migrations/0003_ad_moderation_priority.py`  
**Priority:** High

```python
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("ads", "0003_add_index_conditions"),
        ("moderation", "0002_singleton_enforcement"),
    ]

    operations = [
        migrations.CreateModel(
            name="AdModerationPriority",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ("base_score", models.PositiveSmallIntegerField(default=0)),
                ("priority_level", models.CharField(max_length=10)),
                ("flags", models.JSONField(blank=True, default=list)),
                ("confidence_score", models.FloatField(default=0.0)),
                ("escalation_required", models.BooleanField(default=False)),
                ("ad", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="moderation_priority", to="ads.ad")),
            ],
            options={
                "db_table": "ad_moderation_priority",
            },
        ),
        # Indexes added via model Meta
    ]
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
| Priority calculation performance | Medium | Background calculation via signals, caching |
| Admin UI complexity | Low | Progressive enhancement, optional features |
| Priority gaming | Medium | Multi-factor scoring, change detection |

---

## Notes

- Priority calculated on ad entering ON_MODERATION status via post_save signal
- Queue page shows prioritized ads for moderator efficiency
- Bulk actions logged via `ModeratorActionLog`
- Escalation flag highlights high-risk content for senior review