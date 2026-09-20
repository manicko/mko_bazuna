"""
Management command to delete orphaned media files from MEDIA_ROOT.

Walks every file under MEDIA_ROOT (excluding the ``seed/`` and ``staging/``
subdirectories — seed data manages its own lifecycle, and staging files are
protected by a TTL reclamation in ``_reclaim_stale_staging``), collects the
set of keys referenced by live ``AdImage`` rows (``image`` +
``thumbnail_small/medium/large``), and deletes files whose key is not
referenced.

This is a backstop for MED-001/MED-002: any file that escapes every explicit
deletion path (e.g. a bug in a sweep command or a partial write failure) is
eventually reclaimed here. Safe to run as a periodic cron job.

Uses advisory lock 103 for safe concurrent execution.
"""

import logging
import os
import time

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.ads.models import AdImage
from apps.core.enums import AdvisoryLockId
from apps.core.utils.advisory_lock import advisory_lock
from apps.media.services.filesystem import STAGING_SUBDIR, delete_photo

logger = logging.getLogger(__name__)

# Subdirectory excluded from orphan sweeps — seed data manages its own lifecycle.
_SEED_SUBDIR = "seed"

# Abandoned in-flight uploads older than this are reclaimed by the sweep.
# 2 hours — safely beyond the 30-minute DRAFT retention (sweep_drafts.py).
_STAGING_TTL_SECONDS = 2 * 60 * 60


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
    """Walk MEDIA_ROOT and return relative paths, excluding seed/ and staging/.

    The ``staging/`` subdirectory holds in-flight uploads that are not yet
    referenced by any AdImage row.  These are protected from the orphan sweep
    here and instead reclaimed by ``_reclaim_stale_staging`` based on file age
    (TTL).  Seed data is excluded because it manages its own lifecycle.
    """
    files: list[str] = []
    for dirpath, _dirnames, filenames in os.walk(media_root):
        rel_dir = os.path.relpath(dirpath, media_root)
        # Skip seed directory (and any subdir starting with seed/)
        if rel_dir == _SEED_SUBDIR or rel_dir.startswith(f"{_SEED_SUBDIR}/"):
            continue
        # Skip staging directory (and any subdir starting with staging/)
        if rel_dir == STAGING_SUBDIR or rel_dir.startswith(f"{STAGING_SUBDIR}/"):
            continue
        for name in filenames:
            rel_path = os.path.join(rel_dir, name) if rel_dir != "." else name
            files.append(rel_path)
    return files


def _reclaim_stale_staging(media_root: str, ttl_seconds: int) -> int:
    """Delete staging files older than *ttl_seconds* (abandoned uploads).

    In-flight uploads live in ``MEDIA_ROOT/staging/`` between upload and
    submission.  If a seller abandons the flow without sending ``/cancel``,
    these files would persist indefinitely (they are excluded from the orphan
    sweep).  This function reclaims files whose modification time exceeds the
    TTL, mirroring the safety margin of the 30-minute DRAFT retention.

    Args:
        media_root: Absolute path to ``MEDIA_ROOT``.
        ttl_seconds: Files older than this are deleted.

    Returns:
        The number of staging files reclaimed.
    """
    staging_root = os.path.join(media_root, STAGING_SUBDIR)
    if not os.path.isdir(staging_root):
        return 0
    now = time.time()
    reclaimed = 0
    for dirpath, _dirnames, filenames in os.walk(staging_root):
        for name in filenames:
            path = os.path.join(dirpath, name)
            try:
                if now - os.path.getmtime(path) >= ttl_seconds:
                    os.remove(path)
                    logger.info(
                        "Reclaimed stale staging file: %s",
                        os.path.relpath(path, media_root),
                    )
                    reclaimed += 1
            except OSError:
                logger.exception("Failed to reclaim staging file: %s", path)
    return reclaimed


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
        with transaction.atomic():  # pyright: ignore[reportGeneralTypeIssues] - Django: django-stubs not installed; Atomic.__enter__/__exit__ untyped
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
                for key in sorted(orphans):
                    delete_photo(key)
                    deleted += 1
                    if deleted % 100 == 0:
                        logger.info("Deleted %d orphaned files...", deleted)

                logger.info("Orphan sweep complete: deleted %d files.", deleted)
                self.stdout.write(
                    self.style.SUCCESS(f"Deleted {deleted} orphaned media files.")
                )

                # Reclaim abandoned staging files (in-flight uploads older than
                # TTL).  Excluded from the orphan sweep above; cleaned up here
                # by age.  Moved inside the lock to serialize all MEDIA_ROOT
                # mutations (plan 34 MED-001; R1 TX-then-FS safety gate GO).
                if not dry_run:
                    reclaimed = _reclaim_stale_staging(media_root, _STAGING_TTL_SECONDS)
                    if reclaimed:
                        self.stdout.write(
                            self.style.SUCCESS(
                                f"Reclaimed {reclaimed} stale staging files."
                            )
                        )
