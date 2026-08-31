"""
Moderation analytics service for moderator dashboard and metrics.

Provides functions to aggregate moderation statistics, count pending
reviews, calculate moderator performance metrics, and analyze
rejection reasons. All queries are read-only and operate on existing
AnalyticsEvent and ModeratorActionLog data.
"""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import TypedDict

from django.db.models import Avg, Count, F, QuerySet
from django.db.models.functions import Extract
from django.utils import timezone

from apps.ads.models import Ad
from apps.analytics.models import AnalyticsEvent
from apps.core.enums import AdStatus, AnalyticsEventType, ModeratorActionType
from apps.moderation.models import ModeratorActionLog

logger = logging.getLogger(__name__)


class ModerationStats(TypedDict):
    """Aggregated moderation statistics for the staff dashboard."""

    approved: int
    rejected: int
    flagged: int
    avg_time_to_moderate: float | None


class ModeratorPerformance(TypedDict):
    """Per-moderator performance metrics."""

    moderator_id: int
    actions_taken: int
    avg_time_hours: float | None


def get_moderation_stats(days: int = 30) -> ModerationStats:
    """Aggregate moderation statistics over the given time window.

    Counts MODERATION_APPROVED, MODERATION_REJECTED, and MODERATION_FLAGGED
    analytics events, and computes the average time (in hours) from ad
    creation to moderation approval.

    Args:
        days: Number of days to look back (default 30).

    Returns:
        ModerationStats dict with approved/rejected/flagged counts and
        average time to moderate in hours.
    """
    cutoff = timezone.now() - timedelta(days=days)
    events: QuerySet[AnalyticsEvent] = AnalyticsEvent.objects.filter(
        timestamp__gte=cutoff,
        event_type__in=[
            AnalyticsEventType.MODERATION_APPROVED,
            AnalyticsEventType.MODERATION_REJECTED,
            AnalyticsEventType.MODERATION_FLAGGED,
        ],
    )

    approved: int = events.filter(
        event_type=AnalyticsEventType.MODERATION_APPROVED,
    ).count()
    rejected: int = events.filter(
        event_type=AnalyticsEventType.MODERATION_REJECTED,
    ).count()
    flagged: int = events.filter(
        event_type=AnalyticsEventType.MODERATION_FLAGGED,
    ).count()

    # Average time to moderate: difference in seconds between the event
    # timestamp and the ad creation timestamp, then converted to hours.
    approved_with_ad = events.filter(
        event_type=AnalyticsEventType.MODERATION_APPROVED,
        ad__isnull=False,
    )
    avg_seconds: float | None = approved_with_ad.aggregate(
        avg=Avg(
            Extract(F("timestamp"), "epoch") - Extract(F("ad__created_at"), "epoch"),
        ),
    )["avg"]
    avg_time_to_moderate: float | None = (
        round(avg_seconds / 3600, 2) if avg_seconds is not None else None
    )

    return ModerationStats(
        approved=approved,
        rejected=rejected,
        flagged=flagged,
        avg_time_to_moderate=avg_time_to_moderate,
    )


def get_pending_queue_size() -> int:
    """Count ads currently awaiting moderation review.

    Returns:
        Number of ads with status ON_MODERATION.
    """
    return Ad.objects.filter(status=AdStatus.ON_MODERATION).count()


def get_moderator_performance(days: int = 30) -> list[ModeratorPerformance]:
    """Get performance metrics per moderator over the given time window.

    Tracks manual approvals (Ad.published_by) and manual rejections
    (Ad.moderated_by). Results are merged by moderator ID and sorted
    by actions_taken descending.

    Args:
        days: Number of days to look back (default 30).

    Returns:
        List of ModeratorPerformance dicts ordered by actions_taken
        descending.
    """
    cutoff = timezone.now() - timedelta(days=days)

    # Manual approvals via published_by
    approve_data = (
        Ad.objects.filter(
            published_by__isnull=False,
            published_at__gte=cutoff,
        )
        .values("published_by")
        .annotate(
            action_count=Count("id"),
            avg_seconds=Avg(
                Extract(F("published_at"), "epoch") - Extract(F("created_at"), "epoch"),
            ),
        )
    )

    # Manual rejections via moderated_by
    reject_data = (
        Ad.objects.filter(
            moderated_by__isnull=False,
            rejected_at__gte=cutoff,
        )
        .values("moderated_by")
        .annotate(
            action_count=Count("id"),
            avg_seconds=Avg(
                Extract(F("rejected_at"), "epoch") - Extract(F("created_at"), "epoch"),
            ),
        )
    )

    # Merge results by moderator ID
    perf_map: dict[int, dict[str, int | float]] = {}

    for row in approve_data:
        mid: int = row["published_by"]
        perf_map[mid] = {
            "actions": row["action_count"],
            "total_seconds": (row["avg_seconds"] or 0) * row["action_count"],
        }

    for row in reject_data:
        mid = row["moderated_by"]
        if mid in perf_map:
            perf_map[mid]["actions"] += row["action_count"]
            perf_map[mid]["total_seconds"] += (row["avg_seconds"] or 0) * row[
                "action_count"
            ]
        else:
            perf_map[mid] = {
                "actions": row["action_count"],
                "total_seconds": (row["avg_seconds"] or 0) * row["action_count"],
            }

    result: list[ModeratorPerformance] = []
    for mid, data in perf_map.items():
        actions = int(data["actions"])
        total_sec = float(data["total_seconds"])
        avg_hours = round(total_sec / actions / 3600, 2) if actions > 0 else None
        result.append(
            ModeratorPerformance(
                moderator_id=mid,
                actions_taken=actions,
                avg_time_hours=avg_hours,
            ),
        )

    result.sort(key=lambda x: x["actions_taken"], reverse=True)
    return result


def get_rejection_reasons(days: int = 30) -> dict[str, int]:
    """Aggregate rejection reasons from ModeratorActionLog.

    Counts occurrences of each unique reason text for REJECT actions
    within the given time window.

    Args:
        days: Number of days to look back (default 30).

    Returns:
        Dict mapping reason text to occurrence count, ordered by count
        descending.
    """
    cutoff = timezone.now() - timedelta(days=days)
    reasons: QuerySet[ModeratorActionLog] = ModeratorActionLog.objects.filter(
        created_at__gte=cutoff,
        action_type=ModeratorActionType.REJECT,
    )

    reason_counts: dict[str, int] = {}
    for log_entry in reasons:
        reason_counts[log_entry.reason] = reason_counts.get(log_entry.reason, 0) + 1

    # Sort by count descending
    return dict(
        sorted(reason_counts.items(), key=lambda item: item[1], reverse=True),
    )
