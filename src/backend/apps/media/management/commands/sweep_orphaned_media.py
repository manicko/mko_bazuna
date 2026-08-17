"""
Management command to delete orphaned media files from MEDIA_ROOT.

Walks every file under MEDIA_ROOT (excluding the ``seed/`` subdirectory —
seed data manages its own lifecycle), collects the set of keys referenced by
live ``AdImage`` rows (``image`` + ``thumbnail_small/medium/large``), and
deletes files whose key is not referenced.

This is a backstop for MED-001/MED-002: any file that escapes every explicit
deletion path (e.g. a bug in a sweep command or a partial write failure) is
eventually reclaimed here. Safe to run as a periodic cron job.

Uses advisory lock 103 for safe concurrent execution.
"""

import logging
import os

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.ads.models import AdImage
from apps.core.enums import AdvisoryLockId
from apps.core.utils.advisory_lock import advisory_lock

logger = logging.getLogger(__name__)

# Subdirectory excluded from orphan sweeps — seed data manages its own lifecycle.
_SEED_SUBDIR = "seed"


def _collect_referenced_keys() -> set[str]:
    """Return the set of all storage keys currently referenced by AdImage rows."""
    keys: set[str] = set()
    fields = ("image", "thumbnail_small", "thumbnail_medium", "thumbnail_large")
    for chunk in AdImage.objects.values(*fields).iterator():
        for field in fields:
            val = chunk[field]
            if val:
                keys.add(val)
    return keys


def _walk_media_files(media_root: str) -> list[str]:
    """Walk MEDIA_ROOT and return relative paths, excluding the seed/ subdir."""
    files: list[str] = []
    for dirpath, _dirnames, filenames in os.walk(media_root):
        rel_dir = os.path.relpath(dirpath, media_root)
        if rel_dir == ".":
            if _SEED_SUBDIR in os.listdir(media_root):
                pass  # not in the top-level dir, handled below
        # Skip seed directory (and any subdir starting with seed/)
        if rel_dir == _SEED_SUBDIR or rel_dir.startswith(f"{_SEED_SUBDIR}/"):
            continue
        for name in filenames:
            rel_path = os.path.join(rel_dir, name) if rel_dir != "." else name
            files.append(rel_path)
    return files


class Command(BaseCommand):
    """Delete orphaned media files not referenced by any AdImage row."""

    help = "Delete media files in MEDIA_ROOT that are not referenced by any AdImage"

    def add_arguments(self, parser) -> None:
        """Add dry-run argument."""
        parser.add_argument(
            "--dry-run",
            action="store_true",
            dest="dry_run",
            default=False,
            help="List orphaned files without deleting them",
        )

    def handle(self, *args, **options) -> None:
        """Execute the orphan sweep with advisory lock."""
        dry_run: bool = options["dry_run"]

        media_root = str(settings.MEDIA_ROOT)

        # Snapshot referenced keys before deleting anything (the DB side is
        # read-only here — no writes, so no advisory lock is strictly needed,
        # but we take it to avoid two instances racing on filesystem cleanup).
        with transaction.atomic():  # pyright: ignore[reportGeneralTypeIssues]
            with advisory_lock(AdvisoryLockId.SWEEP_ORPHANED_MEDIA):
                referenced = _collect_referenced_keys()
                on_disk = set(_walk_media_files(media_root))

        orphans = on_disk - referenced

        if dry_run:
            logger.info(
                "DRY RUN: Found %d orphaned media files (not deleting):",
                len(orphans),
            )
            for key in sorted(orphans):
                logger.info("  %s", key)
            self.stdout.write(
                self.style.SUCCESS(
                    f"DRY RUN: {len(orphans)} orphaned files would be deleted."
                )
            )
            return

        deleted = 0
        errors = 0
        for key in sorted(orphans):
            file_path = os.path.join(media_root, key)
            try:
                os.remove(file_path)
                deleted += 1
                if deleted % 100 == 0:
                    logger.info("Deleted %d orphaned files...", deleted)
            except FileNotFoundError:
                # Another process may have removed it concurrently — acceptable.
                pass
            except OSError as exc:
                errors += 1
                logger.error("Failed to delete orphan %s: %s", key, exc)

        logger.info(
            "Orphan sweep complete: deleted %d files (%d errors).",
            deleted,
            errors,
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"Deleted {deleted} orphaned media files ({errors} errors)."
            )
        )
