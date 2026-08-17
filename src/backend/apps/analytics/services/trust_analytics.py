"""
Trust analytics service for seller trust score calculation and metrics.

Provides functions to compute trust scores, map scores to trust levels,
record trust-related analytics events, and query daily metrics.
"""

from __future__ import annotations

import logging
from datetime import timedelta

from django.db.models import QuerySet
from django.utils import timezone

from apps.ads.models import Ad
from apps.analytics.models import AnalyticsEvent, DailyAdMetrics
from apps.core.enums import AdStatus, AnalyticsEventType, TrustLevel
from apps.trust.models import SellerVerification

logger = logging.getLogger(__name__)


def calculate_seller_trust_score(user_id: int) -> float:
    """Calculate trust score (0-100) for a seller based on behavioral metrics.

    Algorithm:
        Base score: 50
        +10 for each published ad (max +50, i.e. up to 5 ads)
        +20 if seller is admin-verified
        -10 for each rejected ad (floor at 0 net effect)
        Final result clamped to [0, 100].

    Args:
        user_id: The seller's user ID.

    Returns:
        Trust score between 0 and 100.
    """
    score: float = 50.0

    # Published ads: +10 each, max 50
    published_count: int = Ad.objects.filter(
        user_id=user_id,
        status=AdStatus.PUBLISHED,
    ).count()
    score += min(published_count, 5) * 10

    # Seller verification: +20 if admin-verified
    try:
        verification = SellerVerification.objects.get(user_id=user_id)
        if verification.verified_by_admin:
            score += 20
    except SellerVerification.DoesNotExist:
        pass

    # Rejected ads: -10 each, minimum 0
    rejected_count: int = Ad.objects.filter(
        user_id=user_id,
        status=AdStatus.REJECTED,
    ).count()
    score = max(score - rejected_count * 10, 0.0)

    # Clamp to [0, 100]
    return min(max(score, 0.0), 100.0)


def get_trust_level(score: float) -> TrustLevel:
    """Map a numeric trust score to a TrustLevel enum.

    Mapping:
        0-30:   UNVERIFIED
        31-60:  VERIFIED
        61-85:  TRUSTED
        86-100: PRO

    Args:
        score: Numeric trust score (0-100).

    Returns:
        The corresponding TrustLevel value.
    """
    if score >= 86:
        return TrustLevel.PRO
    if score >= 61:
        return TrustLevel.TRUSTED
    if score >= 31:
        return TrustLevel.VERIFIED
    return TrustLevel.UNVERIFIED


def record_trust_event(user_id: int, event: AnalyticsEventType) -> None:
    """Record a trust-related analytics event for a seller.

    Args:
        user_id: The seller's user ID.
        event: The type of trust event to record.
    """
    AnalyticsEvent.objects.create(
        event_type=event,
        user_id=user_id,
    )
    logger.info(
        "Trust event recorded: user=%s event=%s",
        user_id,
        event,
    )


def get_seller_daily_metrics(
    user_id: int,
    days: int = 30,
) -> list[DailyAdMetrics]:
    """Retrieve daily aggregated metrics for a seller's ads.

    Args:
        user_id: The seller's user ID.
        days: Number of days to look back (default 30).

    Returns:
        List of DailyAdMetrics records for the seller's ads, ordered
        by date descending.
    """
    cutoff = timezone.now().date() - timedelta(days=days)
    metrics: QuerySet[DailyAdMetrics] = DailyAdMetrics.objects.filter(
        ad__user_id=user_id,
        date__gte=cutoff,
    ).order_by("-date", "ad_id")
    return list(metrics)
