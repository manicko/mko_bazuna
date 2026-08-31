"""
Management command to backfill thumbnails for existing AdImage records.

Iterates over AdImage records that have an original image but missing
thumbnail keys, generates all three thumbnail variants, and persists
them. Idempotent — skips records that already have thumbnails.

Uses advisory lock 102 for safe concurrent execution.
"""

import logging
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Q

from apps.ads.models import AdImage
from apps.core.enums import AdvisoryLockId, ThumbnailSizeStrEnum
from apps.core.utils.advisory_lock import advisory_lock
from apps.media.services.thumbnails import ThumbnailService

logger = logging.getLogger(__name__)

LOCK_ID = AdvisoryLockId.BACKFILL_THUMBNAILS


class Command(BaseCommand):
    """Backfill thumbnails for existing AdImage records."""

    help = "Generate thumbnails for AdImage records that lack them"

    def add_arguments(self, parser) -> None:
        """Add command-line arguments."""
        parser.add_argument(
            "--batch-size",
            type=int,
            default=50,
            dest="batch_size",
            help="Number of records to process per batch (default: 50)",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            dest="dry_run",
            default=False,
            help="Count records needing thumbnails without generating them",
        )

    def handle(self, *args, **options) -> None:
        """Execute the backfill command."""
        dry_run: bool = options["dry_run"]
        batch_size: int = options["batch_size"]

        with transaction.atomic():  # pyright: ignore[reportGeneralTypeIssues]
            with advisory_lock(LOCK_ID):
                # Find AdImage records that have an original image but are
                # missing at least one thumbnail variant.
                has_image = Q(image__isnull=False) & ~Q(image="")
                missing_thumbnail = (
                    Q(thumbnail_small__isnull=True)
                    | Q(thumbnail_medium__isnull=True)  # type: ignore[operator]
                    | Q(thumbnail_large__isnull=True)  # type: ignore[operator]
                )
                queryset = AdImage.objects.filter(
                    has_image, missing_thumbnail
                ).order_by("id")

                total = queryset.count()

                if dry_run:
                    logger.info(
                        "DRY RUN: %d AdImage records need thumbnail backfill",
                        total,
                    )
                    return

                if total == 0:
                    logger.info("No AdImage records need thumbnail backfill")
                    return

                logger.info("Starting thumbnail backfill for %d records", total)

                service = ThumbnailService(storage_dir=settings.MEDIA_ROOT)
                processed = 0
                errors = 0

                # Process in batches to avoid long-running transactions
                ids = list(queryset.values_list("id", flat=True))
                for i in range(0, len(ids), batch_size):
                    batch_ids = ids[i : i + batch_size]
                    batch = list(AdImage.objects.filter(id__in=batch_ids).iterator())

                    for ad_image in batch:
                        try:
                            self._process_one(service, ad_image)
                            processed += 1
                        except Exception as exc:
                            errors += 1
                            logger.exception(
                                "Failed to generate thumbnails for AdImage %d: %s",
                                ad_image.id,
                                exc,
                            )

                    logger.info(
                        "Progress: %d/%d processed, %d errors",
                        min(i + batch_size, total),
                        total,
                        errors,
                    )

                logger.info(
                    "Backfill complete: %d processed, %d errors out of %d total",
                    processed,
                    errors,
                    total,
                )

    def _process_one(self, service: ThumbnailService, ad_image: AdImage) -> None:
        """Generate thumbnails for a single AdImage record."""
        original_path = Path(settings.MEDIA_ROOT) / str(ad_image.image)

        if not original_path.is_file():
            logger.warning(
                "Original image file not found for AdImage %d: %s",
                ad_image.id,
                original_path,
            )
            return

        with open(str(original_path), "rb") as f:
            photo_bytes = f.read()

        thumbnail_keys = service.generate_thumbnails(photo_bytes, ad_image.image)

        with transaction.atomic():  # type: ignore[reportGeneralTypeIssues]
            # Only update the fields that are still missing
            update_kwargs = {}
            if ad_image.thumbnail_small is None:
                update_kwargs["thumbnail_small"] = thumbnail_keys.get(
                    ThumbnailSizeStrEnum.SMALL
                )
            if ad_image.thumbnail_medium is None:
                update_kwargs["thumbnail_medium"] = thumbnail_keys.get(
                    ThumbnailSizeStrEnum.MEDIUM
                )
            if ad_image.thumbnail_large is None:
                update_kwargs["thumbnail_large"] = thumbnail_keys.get(
                    ThumbnailSizeStrEnum.LARGE
                )

            if update_kwargs:
                AdImage.objects.filter(id=ad_image.id).update(**update_kwargs)
