"""AnalyticsGenerator for seed data — creates fake view events and daily metrics."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from apps.ads.models import Ad
from apps.analytics.models import AnalyticsEvent, DailyAdMetrics
from apps.core.enums import AdStatus, AnalyticsEventType
from apps.seed.generators.base import BaseGenerator

logger = logging.getLogger(__name__)


class AnalyticsGenerator(BaseGenerator):
    """Generates fake AnalyticsEvent and DailyAdMetrics records for seed ads.

    Events are spread across the configured number of days with a recent-day
    bias (exponential decay distribution). Only PUBLISHED ads receive events.
    """

    def __init__(self, config: dict[str, Any], ads: list[Ad]) -> None:
        """Initialize the analytics generator.

        Args:
            config: Parsed seed configuration dict.
            ads: List of Ad instances (must already be saved to DB).
        """
        super().__init__(config)
        self.ads = ads
        analytics_config = config.get("analytics", {})
        self.days_back = analytics_config.get("days_back", 90)
        views_config = analytics_config.get("views_per_ad_per_day", {})
        self.min_views = views_config.get("min", 0)
        self.max_views = views_config.get("max", 15)

    def generate_events(self) -> list[AnalyticsEvent]:
        """Generate AnalyticsEvent records with AD_VIEWED type.

        Returns:
            List of AnalyticsEvent instances ready for bulk_create.
        """
        events: list[AnalyticsEvent] = []
        now = datetime.now(UTC)

        for ad in self.ads:
            # Only published ads get views
            if ad.status != AdStatus.PUBLISHED:
                continue

            # Determine the ad's active period (when it was published)
            if ad.published_at is None:
                continue

            ad_start = ad.published_at
            ad_end = ad.archived_at if ad.archived_at else now

            for day_offset in range(self.days_back):
                day_date = now - timedelta(days=day_offset)

                # Skip if ad wasn't published yet or was already archived
                if day_date < ad_start or (ad_end and day_date > ad_end):
                    continue

                # Recent days get more views (exponential decay)
                # Day 0 (today): full weight, Day 89: ~12% weight
                recency_weight = max(0.1, 1.0 - (day_offset / self.days_back) * 0.9)
                max_for_day = max(0, int(self.max_views * recency_weight))
                if max_for_day < self.min_views:
                    max_for_day = self.min_views

                views_today = self.faker.random_int(self.min_views, max_for_day)
                if views_today == 0:
                    continue

                # Create individual events spread across the day
                for _ in range(views_today):
                    random_hour = self.faker.random_int(0, 23)
                    random_minute = self.faker.random_int(0, 59)
                    event_time = day_date.replace(
                        hour=random_hour,
                        minute=random_minute,
                        second=0,
                        microsecond=0,
                    )
                    event = AnalyticsEvent(
                        event_type=AnalyticsEventType.AD_VIEWED,
                        timestamp=event_time,
                        user=None,
                        ad=ad,
                    )
                    events.append(event)

        return events

    def generate_daily_metrics(self) -> list[DailyAdMetrics]:
        """Generate DailyAdMetrics rollup records.

        Creates one record per ad per day with the total view count.

        Returns:
            List of DailyAdMetrics instances ready for bulk_create
            with ignore_conflicts=True.
        """
        metrics: list[DailyAdMetrics] = []
        now = datetime.now(UTC)

        for ad in self.ads:
            if ad.status != AdStatus.PUBLISHED:
                continue

            if ad.published_at is None:
                continue

            ad_start = ad.published_at
            ad_end = ad.archived_at if ad.archived_at else now

            for day_offset in range(self.days_back):
                day_date = (now - timedelta(days=day_offset)).date()

                # Skip if ad wasn't published yet
                if day_date < ad_start.date():
                    continue
                if ad_end and day_date > ad_end.date():
                    continue

                # Recency-weighted view count
                recency_weight = max(0.1, 1.0 - (day_offset / self.days_back) * 0.9)
                max_for_day = max(0, int(self.max_views * recency_weight))
                if max_for_day < self.min_views:
                    max_for_day = self.min_views

                views_today = self.faker.random_int(self.min_views, max_for_day)
                if views_today == 0:
                    continue

                metric = DailyAdMetrics(
                    ad=ad,
                    date=day_date,
                    views_count=views_today,
                    contacts_count=0,
                )
                metrics.append(metric)

        return metrics