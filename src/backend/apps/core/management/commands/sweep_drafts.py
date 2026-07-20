"""
Management command to sweep draft ads after 30-minute retention.

Deletes ads with DRAFT status where created_at is older than 30 minutes.
Uses advisory lock 4 for idempotent, safe concurrent execution.
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
    """Sweep draft ads after 30-minute retention window."""

    help = "Delete ads with DRAFT status older than 30 minutes"

    def add_arguments(self, parser) -> None:
        """Add dry-run argument to the command."""
        parser.add_argument(
            "--dry-run",
            action="store_true",
            dest="dry_run",
            default=False,
            help="Print count of draft ads to be deleted without actually deleting",
        )

    def handle(self, *args, **options) -> None:
        """Execute the draft sweep command with advisory lock."""
        dry_run: bool = options["dry_run"]

        with advisory_lock(AdvisoryLockId.SWEEP_DRAFTS):
            # Query draft ads older than 30 minutes
            cutoff_date = timezone.now() - timedelta(minutes=30)

            queryset = Ad.objects.filter(
                status=AdStatus.DRAFT,
                created_at__lt=cutoff_date,
            )

            count = queryset.count()

            if dry_run:
                logger.info(
                    "DRY RUN: Would delete %d draft ads older than 30 minutes",
                    count,
                )
                return

            # Delete atomically - CASCADE will handle ad_images
            deleted_count, _ = queryset.delete()

            logger.info(
                "Deleted %d draft ads older than 30 minutes",
                deleted_count,
            )