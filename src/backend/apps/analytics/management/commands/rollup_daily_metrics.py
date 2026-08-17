"""
Management command to pre-compute DailyAdMetrics for all ads with analytics events.

Aggregates AnalyticsEvent data (AD_VIEWED, CONTACT_INITIATED, CONTACT_COMPLETED)
into DailyAdMetrics records for yesterday's date. Uses advisory lock 8
(ROLLUP_DAILY_METRICS) for safe singleton execution.
"""

import logging
from datetime import timedelta

from apps.analytics.models import AnalyticsEvent, DailyAdMetrics
from apps.core.enums import AdvisoryLockId, AnalyticsEventType
from apps.core.utils.advisory_lock import advisory_lock
from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Count, Q
from django.utils import timezone

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    """Pre-compute DailyAdMetrics for all ads with analytics events."""

    help = "Roll up yesterday's analytics events into DailyAdMetrics"

    def add_arguments(self, parser) -> None:
        """Add dry-run argument to the command."""
        parser.add_argument(
            "--dry-run",
            action="store_true",
            dest="dry_run",
            default=False,
            help="Print aggregation results without saving to database",
        )

    def handle(self, *args, **options) -> None:
        """Execute the daily metrics rollup with advisory lock."""
        dry_run: bool = options["dry_run"]

        with transaction.atomic():  # pyright: ignore[reportGeneralTypeIssues]
            with advisory_lock(AdvisoryLockId.ROLLUP_DAILY_METRICS):
                yesterday = timezone.now().date() - timedelta(days=1)

                logger.info("Rolling up analytics events for %s", yesterday)

                event_types = [
                    AnalyticsEventType.AD_VIEWED,
                    AnalyticsEventType.CONTACT_INITIATED,
                    AnalyticsEventType.CONTACT_COMPLETED,
                ]

                aggregated = (
                    AnalyticsEvent.objects.filter(
                        ad__isnull=False,
                        timestamp__date=yesterday,
                        event_type__in=event_types,
                    )
                    .values("ad_id")
                    .annotate(
                        views=Count(
                            "id",
                            filter=Q(event_type=AnalyticsEventType.AD_VIEWED),
                        ),
                        contacts=Count(
                            "id",
                            filter=Q(
                                event_type__in=[
                                    AnalyticsEventType.CONTACT_INITIATED,
                                    AnalyticsEventType.CONTACT_COMPLETED,
                                ]
                            ),
                        ),
                    )
                )

                if not aggregated:
                    logger.info("No analytics events found for %s", yesterday)
                    return

                if dry_run:
                    logger.info(
                        "DRY RUN: Would create/update %d DailyAdMetrics records for %s",
                        len(aggregated),
                        yesterday,
                    )
                    for row in aggregated:
                        logger.info(
                            "  ad_id=%s views=%d contacts=%d",
                            row["ad_id"],
                            row["views"],
                            row["contacts"],
                        )
                    return

                created_count = 0
                updated_count = 0

                for row in aggregated:
                    _, created = DailyAdMetrics.objects.update_or_create(
                        ad_id=row["ad_id"],
                        date=yesterday,
                        defaults={
                            "views_count": row["views"],
                            "contacts_count": row["contacts"],
                        },
                    )
                    if created:
                        created_count += 1
                    else:
                        updated_count += 1

                logger.info(
                    "DailyAdMetrics rollup complete: %d created, %d updated for %s",
                    created_count,
                    updated_count,
                    yesterday,
                )
