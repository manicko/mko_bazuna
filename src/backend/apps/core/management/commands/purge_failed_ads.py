"""
Management command to purge ads that failed auto-moderation after 7-day retention.

Deletes ads with status ON_MODERATION_FAILED where moderation_failed_at is older than 7 days.
Uses advisory lock 6 for idempotent, safe concurrent execution.
"""

import logging
from datetime import timedelta

from apps.ads.models import Ad
from apps.core.enums import AdStatus, AdvisoryLockId
from apps.core.utils.advisory_lock import advisory_lock
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.db import transaction
from apps.ads.models import AdImage
from telegram_bot.services.media import delete_photo

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    """Purge ads that failed auto-moderation after 7-day retention window."""

    help = "Purge ads with ON_MODERATION_FAILED status older than 7 days"

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

        with advisory_lock(AdvisoryLockId.PURGE_FAILED_ADS):
            with transaction.atomic():  # pyright: ignore[reportGeneralTypeIssues]
                # Query using the IX_ads_purge_failed partial index
                # Status is ON_MODERATION_FAILED, moderation_failed_at older than 7 days
                cutoff_date = timezone.now() - timedelta(days=7)

                queryset = Ad.objects.filter(
                    status=AdStatus.ON_MODERATION_FAILED,
                    moderation_failed_at__lt=cutoff_date,
                )

                count = queryset.count()

                if dry_run:
                    logger.info(
                        "DRY RUN: Would delete %d ads with ON_MODERATION_FAILED status older than 7 days",
                        count,
                    )
                    return

                # Collect storage keys for physical media cleanup before ORM cascade
                ad_ids = list(queryset.values_list("id", flat=True))
                storage_keys = list(
                    AdImage.objects.filter(ad_id__in=ad_ids).values_list(
                        "image", flat=True
                    )
                )

                # Delete atomically - CASCADE will handle ad_images
                deleted_count, _ = queryset.delete()

                # Remove physical media files after ORM cascade
                for storage_key in storage_keys:
                    delete_photo(storage_key)

                logger.info(
                    "Deleted %d ads with ON_MODERATION_FAILED status older than 7 days. "
                    "Removed %d media files.",
                    deleted_count,
                    len(storage_keys),
                )
