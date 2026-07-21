"""
Management command to delete archived ads after 4-month retention.

Deletes ads with ARCHIVED status where published_at is older than 4 months.
Uses advisory lock 2 for idempotent, safe concurrent execution.
Images are CASCADE-deleted via ORM.
"""

import logging
from datetime import timedelta

from apps.ads.models import Ad
from apps.core.enums import AdStatus, AdvisoryLockId
from apps.core.utils.advisory_lock import advisory_lock
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.db import transaction

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    """Delete archived ads after 4-month retention window."""

    help = "Delete ads with ARCHIVED status older than 4 months"

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
            """Execute the delete sweep command with advisory lock."""
            dry_run: bool = options["dry_run"]

            with advisory_lock(AdvisoryLockId.DELETE_SWEEP):
                with transaction.atomic():  # pyright: ignore[reportGeneralTypeIssues]
                    # Query using the IX_ads_delete_sweep partial index
                    # Status is ARCHIVED, published_at older than 4 months
                    cutoff_date = timezone.now() - timedelta(days=120)

                    queryset = Ad.objects.filter(
                        status=AdStatus.ARCHIVED,
                        published_at__lt=cutoff_date,
                    )

                    count = queryset.count()

                    if dry_run:
                        logger.info(
                            "DRY RUN: Would delete %d ads with ARCHIVED status older than 4 months",
                            count,
                        )
                        return

                    # Delete atomically - CASCADE will handle ad_images
                    deleted_count, _ = queryset.delete()

                    logger.info(
                        "Deleted %d ads with ARCHIVED status older than 4 months",
                        deleted_count,
                    )
