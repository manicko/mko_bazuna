"""
Management command to sweep draft ads after 30-minute retention.

Deletes ads with DRAFT status where created_at is older than 30 minutes.
Uses advisory lock 4 for idempotent, safe concurrent execution.
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

        with transaction.atomic():  # pyright: ignore[reportGeneralTypeIssues]
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
                    "Deleted %d draft ads older than 30 minutes. "
                    "Removed %d media files.",
                    deleted_count,
                    len(storage_keys),
                )
