"""
Priority service for moderation queue management.

Provides queue operations: calculate & save priority scores,
query queued ads by priority level, and get priority counts.
"""

import logging

from django.db.models import Count, QuerySet

from apps.ads.models import Ad
from apps.core.enums import AdPriorityLevel, AdStatus, PriorityFilter
from apps.moderation.models import AdModerationPriority
from apps.moderation.services.priority_calculator import PriorityCalculator

logger = logging.getLogger(__name__)


class PriorityService:
    """Manage priority calculations and queue operations."""

    def __init__(self) -> None:
        self.calculator = PriorityCalculator()

    def calculate_and_save(self, ad: Ad) -> AdModerationPriority:
        """Calculate priority and save to database.

        Uses update_or_create to handle both new and existing priority records.
        Returns the saved AdModerationPriority instance.
        """
        data = self.calculator.calculate_priority(ad)

        obj, created = AdModerationPriority.objects.update_or_create(
            ad=ad,
            defaults=data,
        )

        if created:
            logger.info(
                "Created priority record for ad %s (score=%s)",
                ad.id,
                data["base_score"],
            )
        else:
            logger.info(
                "Updated priority record for ad %s (score=%s)",
                ad.id,
                data["base_score"],
            )

        return obj

    def get_queued_ads(
        self, priority_filter: PriorityFilter | None = None
    ) -> QuerySet[Ad]:
        """Get ads in the moderation queue, optionally filtered by priority level.

        Uses select_related and prefetch_related to avoid N+1 queries.
        Orders by base_score descending (highest priority first).
        """
        qs = (
            Ad.objects.filter(
                status__in=[AdStatus.ON_MODERATION, AdStatus.ON_MODERATION_FAILED],
            )
            .select_related(
                "user",
                "category",
                "city",
            )
            .prefetch_related(
                "images",
                "moderation_priority",
            )
        )

        if priority_filter:
            qs = qs.filter(
                moderation_priority__priority_level=priority_filter,
            )

        return qs.order_by("-moderation_priority__base_score", "-created_at")

    def get_priority_counts(self) -> dict[str, int]:
        """Get count of queued ads by priority level in a single query.

        Returns a dict with keys 'high', 'medium', 'low' and counts.
        """
        counts = (
            AdModerationPriority.objects.filter(
                ad__status__in=[AdStatus.ON_MODERATION, AdStatus.ON_MODERATION_FAILED],
            )
            .values("priority_level")
            .annotate(
                count=Count("id"),
            )
            .order_by("priority_level")
        )

        result: dict[str, int] = {level.value: 0 for level in AdPriorityLevel}
        for item in counts:
            result[item["priority_level"]] = item["count"]

        return result
