"""
Management command to backfill thumbnails for existing AdImage records.

Iterates over AdImage records that have an original image but missing
thumbnail keys, generates all three thumbnail variants, and persists
them. Idempotent — skips records that already have every thumbnail.

A row with a missing column whose destination file already exists (a stale
leftover from a dead run, or a concurrent generation not yet persisted) is
repaired with ``WriteMode.REPLACE``; a clean destination uses the default
``WriteMode.CREATE_ONLY``.  The column is the source of truth.

Uses advisory lock 102 for safe concurrent execution.

The workflow is split into three phases:
  1. Lock-acquire + collect — advisory lock held inside a short
     transaction to count and collect target IDs, then released.
  2. Filesystem I/O — performed outside any transaction so slow disk
     reads/writes do not hold the DB lock.
  3. Persist — a single short transaction writes all generated keys;
     the lock is not re-acquired (the I/O step is idempotent).
"""

import logging
import os
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Q

from apps.ads.models import AdImage
from apps.core.enums import AdvisoryLockId, ThumbnailSizeStrEnum, WriteMode
from apps.core.utils.advisory_lock import advisory_lock
from apps.media.services.thumbnails import ThumbnailService

logger = logging.getLogger(__name__)

LOCK_ID = AdvisoryLockId.BACKFILL_THUMBNAILS

# Column name -> generated key for each thumbnail size.  Used to decide, per
# row, whether the destination files for the *missing* columns are already on
# disk (a stale leftover from a dead run) and therefore need REPLACE rather
# than CREATE_ONLY.
_SIZE_COLUMNS: dict[ThumbnailSizeStrEnum, str] = {
    ThumbnailSizeStrEnum.SMALL: "thumbnail_small",
    ThumbnailSizeStrEnum.MEDIUM: "thumbnail_medium",
    ThumbnailSizeStrEnum.LARGE: "thumbnail_large",
}


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
        """Execute the backfill command in three phases.

        Phase 1 acquires the advisory lock inside a short transaction,
        collects the IDs of records needing thumbnails, and releases the
        lock before any filesystem I/O begins.

        Phase 2 performs all filesystem reads and thumbnail generation
        outside any transaction.

        Phase 3 persists every generated key in a single short
        transaction without re-acquiring the advisory lock.
        """
        dry_run: bool = options["dry_run"]
        batch_size: int = options["batch_size"]

        # Phase 1 — Lock-acquire + collect (short transaction.atomic() +
        # advisory lock).  The lock covers the count-to-mutate sequence;
        # I/O happens after the ``with`` block exits so the transaction
        # is not held across slow filesystem reads/writes.
        with transaction.atomic():  # pyright: ignore[reportGeneralTypeIssues] - Django: django-stubs not installed; Atomic.__enter__/__exit__ untyped
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

                ids = list(queryset.values_list("id", flat=True))

        # Phase 2 — I/O (no transaction, no lock).  Filesystem reads and
        # thumbnail generation happen here, accumulating pending updates.
        logger.info("Starting thumbnail backfill for %d records", total)

        service = ThumbnailService(storage_dir=settings.MEDIA_ROOT)
        processed = 0
        errors = 0
        pending_updates: list[tuple[int, dict[str, str]]] = []

        for i in range(0, len(ids), batch_size):
            batch_ids = ids[i : i + batch_size]
            batch = list(AdImage.objects.filter(id__in=batch_ids).iterator())

            for ad_image in batch:
                try:
                    result = self._read_and_generate(service, ad_image)
                    if result is not None:
                        pending_updates.append(result)
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

        # Phase 3 — Persist (single short transaction.atomic(), NO lock
        # re-acquisition).  Relying on _read_and_generate idempotency,
        # concurrent runs are safe without holding the lock.
        with transaction.atomic():  # pyright: ignore[reportGeneralTypeIssues] - Django: django-stubs not installed; Atomic.__enter__/__exit__ untyped
            for ad_image_id, update_kwargs in pending_updates:
                if update_kwargs:
                    AdImage.objects.filter(id=ad_image_id).update(**update_kwargs)

        logger.info(
            "Backfill complete: %d processed, %d errors out of %d total",
            processed,
            errors,
            total,
        )

    def _read_and_generate(
        self, service: ThumbnailService, ad_image: AdImage
    ) -> tuple[int, dict[str, str]] | None:
        """Read the original image and generate thumbnail keys.

        Performs only filesystem I/O and returns the fields that still
        need updating.  Does **not** write to the database — persistence
        is deferred to the caller (Phase 3).

        The write mode is decided from the row's column state, which is the
        single source of truth; the file on disk is derived state:

        - every ``thumbnail_*`` column populated -> the row was filtered out in
          Phase 1 and is not reached here.
        - ``NULL`` columns and none of their target files present -> a fresh
          generation, published ``CREATE_ONLY``.
        - ``NULL`` columns with at least one target file already present -> a
          stale leftover from a dead run (or a concurrent generation not yet
          persisted), published ``REPLACE`` and logged ``stale-leftover``.
          ``REPLACE`` rewrites byte-identical content from the same original,
          so a genuine race converges on the same idempotent action and needs
          no separate branch.

        Args:
            service: ThumbnailService for generating variants.
            ad_image: The AdImage record to process.

        Returns:
            ``(ad_image.id, update_kwargs)`` on success, where
            ``update_kwargs`` contains only the thumbnail fields that
            are still ``None`` on ``ad_image``.  Returns ``None`` when
            the original file is missing.

        Raises:
            ValueError: If the image bytes cannot be decoded (propagates
                to the caller's batch loop so the error counter
                increments).
        """
        original_path = Path(settings.MEDIA_ROOT) / str(ad_image.image)

        if not original_path.is_file():
            logger.warning(
                "Original image file not found for AdImage %d: %s",
                ad_image.id,
                original_path,
            )
            return None

        with open(str(original_path), "rb") as f:
            photo_bytes = f.read()

        mode = self._decide_write_mode(ad_image, original_path.parent)

        thumbnail_keys = service.generate_thumbnails(
            photo_bytes, ad_image.image, mode=mode
        )

        # Only update the fields that are still missing (idempotency
        # check) — preserves any thumbnails already present.
        update_kwargs: dict[str, str] = {}
        if ad_image.thumbnail_small is None:
            update_kwargs["thumbnail_small"] = thumbnail_keys[
                ThumbnailSizeStrEnum.SMALL
            ]
        if ad_image.thumbnail_medium is None:
            update_kwargs["thumbnail_medium"] = thumbnail_keys[
                ThumbnailSizeStrEnum.MEDIUM
            ]
        if ad_image.thumbnail_large is None:
            update_kwargs["thumbnail_large"] = thumbnail_keys[
                ThumbnailSizeStrEnum.LARGE
            ]

        return (ad_image.id, update_kwargs)

    @staticmethod
    def _decide_write_mode(ad_image: AdImage, storage_dir: Path) -> WriteMode:
        """Choose the publication mode for a row with at least one missing column.

        The column is the source of truth and the file is derived state, so
        only the destination file's presence is inspected — never the row's
        populated columns, which by definition are already filled.  A leftover
        file at any missing column's final path means a dead run (or an
        in-flight concurrent run) already wrote bytes there; ``REPLACE`` may
        overwrite them, whereas a clean destination uses ``CREATE_ONLY``.
        """
        stem, _ = os.path.splitext(str(ad_image.image))
        for size_enum in ThumbnailSizeStrEnum:
            if getattr(ad_image, _SIZE_COLUMNS[size_enum]) is not None:
                continue
            if (storage_dir / f"{stem}-{size_enum.value}.jpg").exists():
                logger.info(
                    "AdImage %d: repairing stale-leftover %s thumbnail",
                    ad_image.id,
                    size_enum.value,
                )
                return WriteMode.REPLACE
        return WriteMode.CREATE_ONLY
