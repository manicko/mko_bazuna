"""
Management command to pre-compute DailyAdMetrics for all ads with analytics events.

Aggregates AnalyticsEvent data (AD_VIEWED, CONTACT_INITIATED, CONTACT_COMPLETED)
into DailyAdMetrics records for yesterday's date. Uses advisory lock 8
(ROLLUP_DAILY_METRICS) for safe singleton execution.

The write path is a chunked ``bulk_create(update_conflicts=True)`` against the
existing ``uq_daily_ad_metrics_ad_date`` unique constraint, replacing the former
per-ad ``update_or_create`` loop (13-PERF-003). The advisory lock, its placement
inside ``transaction.atomic()``, and its transaction (non-session) scope are
unchanged: whether the whole sweep should be one transaction is 03-DB-008.
"""

import logging
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Count, Q
from django.utils import timezone

from apps.analytics.models import AnalyticsEvent, DailyAdMetrics
from apps.core.enums import AdvisoryLockId, AnalyticsEventType
from apps.core.utils.advisory_lock import advisory_lock

logger = logging.getLogger(__name__)

# One ``bulk_create`` statement per chunk of this many rows. The upsert is
# driven by the existing ``uq_daily_ad_metrics_ad_date`` unique constraint
# (analytics/models.py:109-114), so no per-row SELECT-then-INSERT is needed.
_BULK_CHUNK_SIZE = 1000

# Fields the unique constraint ``uq_daily_ad_metrics_ad_date`` covers; these are
# ``bulk_create(update_conflicts=True)``'s conflict target.
_CONFLICT_FIELDS = ["ad", "date"]

# The metric columns a re-run overwrites. ``created_at`` is deliberately absent
# so an insert keeps its original creation timestamp, matching the previous
# ``update_or_create`` behaviour. ``updated_at`` carries ``auto_now=True``,
# which ``bulk_create`` bypasses, so it is set explicitly on each row.
_UPDATE_FIELDS = ["views_count", "contacts_count", "updated_at"]


class Command(BaseCommand):
    """Pre-compute DailyAdMetrics for all ads with analytics events."""

    help = "Roll up yesterday's analytics events into DailyAdMetrics"

    def _upsert_chunk(self, rows: list[DailyAdMetrics]) -> None:
        """Upsert one chunk against the ad+date unique constraint.

        Uses the existing ``uq_daily_ad_metrics_ad_date`` constraint as the
        conflict target, so a re-run updates the row in place instead of
        creating a duplicate or silently dropping the update.
        """
        DailyAdMetrics.objects.bulk_create(
            rows,
            update_conflicts=True,
            unique_fields=_CONFLICT_FIELDS,
            update_fields=_UPDATE_FIELDS,
        )

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

        with transaction.atomic():  # pyright: ignore[reportGeneralTypeIssues] - Django: django-stubs not installed; Atomic.__enter__/__exit__ untyped
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

                # Rows already present for the target date are the ones this run
                # updates; the rest are inserts. One SELECT replaces the
                # per-row existence probe the old ``update_or_create`` loop
                # issued, so the created/updated split is still reported without
                # reintroducing a per-ad statement.
                existing_ad_ids = set(
                    DailyAdMetrics.objects.filter(date=yesterday).values_list(
                        "ad_id", flat=True
                    )
                )

                now = timezone.now()
                chunk: list[DailyAdMetrics] = []

                for row in aggregated:
                    ad_id = row["ad_id"]
                    if ad_id in existing_ad_ids:
                        updated_count += 1
                    else:
                        created_count += 1

                    chunk.append(
                        DailyAdMetrics(
                            ad_id=ad_id,
                            date=yesterday,
                            views_count=row["views"],
                            contacts_count=row["contacts"],
                            created_at=now,
                            updated_at=now,
                        )
                    )

                    if len(chunk) >= _BULK_CHUNK_SIZE:
                        self._upsert_chunk(chunk)
                        chunk = []

                if chunk:
                    self._upsert_chunk(chunk)

                logger.info(
                    "DailyAdMetrics rollup complete: %d created, %d updated for %s",
                    created_count,
                    updated_count,
                    yesterday,
                )
