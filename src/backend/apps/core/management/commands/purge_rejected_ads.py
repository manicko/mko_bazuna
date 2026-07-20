"""
Management command to purge manually-rejected ads after 90-day retention.

Deletes ads with REJECTED status where rejected_at is older than 90 days.
Uses advisory lock 7 for idempotent, safe concurrent execution.
ModeratorActionLog entries are preserved with ad_id SET NULL.
"""

import logging
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.ads.models import Ad
from apps.core.enums import AdStatus, AdvisoryLockId
from apps.core.utils.advisory_lock import advisory_lock

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    """Purge manually-rejected ads after 90-day retention window."""

    help = "Purge ads with REJECTED status older than 90 days"

    def add_arguments(self, parser) -> None:
        """Add dry-run argument to the command."""
        parser.add_argument(
            "--dry-run",
            action="store_true",
            dest="dry_run",
            default=False,
            help="Print count of ads to be deleted without actually deleting",
        )

    def handle(self, *args, **options) -> None:
        """Execute the purge command with advisory lock."""
        dry_run: bool = options["dry_run"]

        with advisory_lock(AdvisoryLockId.PURGE_REJECTED_ADS):
            # Query using the IX_ads_rejected_sweep partial index
            # Status is REJECTED, rejected_at older than 90 days
            cutoff_date = timezone.now() - timedelta(days=90)

            queryset = Ad.objects.filter(
                status=AdStatus.REJECTED,
                rejected_at__lt=cutoff_date,
            )

            count = queryset.count()

            if dry_run:
                logger.info(
                    "DRY RUN: Would delete %d ads with REJECTED status older than 90 days",
                    count,
                )
                return

            # Delete atomically - CASCADE will handle ad_images
            # ModeratorActionLog.ad_id will be SET NULL due to on_delete=models.SET_NULL
            deleted_count, _ = queryset.delete()

            logger.info(
                "Deleted %d ads with REJECTED status older than 90 days",
                deleted_count,
            )
