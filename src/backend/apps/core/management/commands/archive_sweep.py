"""
Management command to archive published ads after 2-month retention.

Transitions ads with PUBLISHED status where published_at is older than 2 months to ARCHIVED status.
Uses advisory lock 1 for idempotent, safe concurrent execution.
"""

import logging
from datetime import timedelta

from apps.ads.models import Ad
from apps.core.enums import AdStatus, AdvisoryLockId
from apps.core.utils.advisory_lock import advisory_lock
from django.core.management.base import BaseCommand
from django.utils import timezone

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    """Archive published ads after 2-month retention window."""

    help = "Archive ads with PUBLISHED status older than 2 months"

    def add_arguments(self, parser) -> None:
        """Add dry-run argument to the command."""
        parser.add_argument(
            "--dry-run",
            action="store_true",
            dest="dry_run",
            default=False,
            help="Print count of ads to be archived without actually archiving",
        )

    def handle(self, *args, **options) -> None:
        """Execute the archive sweep command with advisory lock."""
        dry_run: bool = options["dry_run"]

        with advisory_lock(AdvisoryLockId.ARCHIVE_SWEEP):
            # Query using the IX_ads_archive_sweep partial index
            # Status is PUBLISHED, published_at older than 2 months
            cutoff_date = timezone.now() - timedelta(days=60)

            queryset = Ad.objects.filter(
                status=AdStatus.PUBLISHED,
                published_at__lt=cutoff_date,
            )

            count = queryset.count()

            if dry_run:
                logger.info(
                    "DRY RUN: Would archive %d ads with PUBLISHED status older than 2 months",
                    count,
                )
                return

            # Update status to ARCHIVED and set archived_at timestamp
            updated_count = queryset.update(
                status=AdStatus.ARCHIVED,
                archived_at=timezone.now(),
            )

            logger.info(
                "Archived %d ads with PUBLISHED status older than 2 months",
                updated_count,
            )