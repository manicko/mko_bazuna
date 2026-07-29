"""
Seller statistics aggregation service with 5-minute cache TTL.

Provides aggregated analytics event data for the seller dashboard,
including total views, total contacts, published ad count, and
per-ad breakdowns. Results are cached for 5 minutes to reduce
database load on repeated requests.
"""

from __future__ import annotations

import logging
from datetime import timedelta

from django.db.models import Count, Q, QuerySet
from django.utils import timezone

from apps.analytics.models import AnalyticsEvent, AnalyticsEventType
from apps.ads.models import Ad
from apps.core.enums import AdStatus, TimeRange

logger = logging.getLogger(__name__)

CACHE_TTL: int = 300  # 5 minutes in seconds


class SellerStats:
    """Aggregates seller analytics events with caching."""

    def __init__(self, user_id: int) -> None:
        self.user_id = user_id

    def get_stats(self, time_range: TimeRange = TimeRange.ALL_TIME) -> dict:
        """Return aggregated stats, using cache if available.

        Args:
            time_range: Filtering window for events.

        Returns:
            Dict with total_views, total_contacts, ads_published, per_ad_stats.
        """
        from django.core.cache import cache

        cache_key = self._cache_key(time_range)
        result = cache.get(cache_key)
        if result is not None:
            return result
        result = self._compute(time_range)
        cache.set(cache_key, result, CACHE_TTL)
        return result

    def _cache_key(self, time_range: TimeRange) -> str:
        """Generate cache key for the given time range."""
        return f"seller_stats:{self.user_id}:{time_range.value}"

    def _compute(self, time_range: TimeRange) -> dict:
        """Compute stats from the database.

        Queries are scoped to the current seller's ads and optionally
        filtered by timestamp for 30-day / 7-day windows.
        """
        user_ads: QuerySet = Ad.objects.filter(user_id=self.user_id)
        ads_published: int = user_ads.filter(status=AdStatus.PUBLISHED).count()

        # Build time-range filter for event queries
        cutoff = timezone.now()  # fallback for ALL_TIME (unused when time_filter is empty)
        time_filter = Q()
        if time_range in (TimeRange.THIRTY_DAYS, TimeRange.SEVEN_DAYS):
            days = 30 if time_range == TimeRange.THIRTY_DAYS else 7
            cutoff = timezone.now() - timedelta(days=days)
            time_filter = Q(timestamp__gte=cutoff)

        events = AnalyticsEvent.objects.filter(
            ad__user_id=self.user_id,
        )
        if time_filter:
            events = events.filter(time_filter)

        total_views: int = events.filter(
            event_type=AnalyticsEventType.AD_VIEWED,
        ).count()

        total_contacts: int = events.filter(
            event_type=AnalyticsEventType.CONTACT_INITIATED,
        ).count()

        # Per-ad aggregated stats via single annotation query
        view_q = Q(analytics_events__event_type=AnalyticsEventType.AD_VIEWED)
        contact_q = Q(
            analytics_events__event_type=AnalyticsEventType.CONTACT_INITIATED,
        )
        if time_filter:
            view_q &= Q(analytics_events__timestamp__gte=cutoff)
            contact_q &= Q(analytics_events__timestamp__gte=cutoff)

        per_ad_qs = user_ads.annotate(
            view_count=Count("analytics_events", filter=view_q),
            contact_count=Count("analytics_events", filter=contact_q),
        ).values("id", "title", "view_count", "contact_count")

        per_ad_stats = [
            {
                "ad_id": row["id"],
                "title": row["title"],
                "views": row["view_count"],
                "contacts": row["contact_count"],
            }
            for row in per_ad_qs
        ]

        return {
            "total_views": total_views,
            "total_contacts": total_contacts,
            "ads_published": ads_published,
            "per_ad_stats": per_ad_stats,
        }