"""
Signal handlers for the media app.

- ``delete_adimage_files_on_delete``: cleans up physical files
  (original + thumbnails) when an ``AdImage`` row is deleted,
  using the project's TX-then-FS pattern (delete after commit).
"""

import logging

from django.db import transaction
from django.db.models.signals import pre_delete
from django.dispatch import receiver

from apps.ads.models import AdImage
from apps.media.services.filesystem import delete_photo

logger = logging.getLogger(__name__)


@receiver(pre_delete, sender=AdImage)
def delete_adimage_files_on_delete(sender, instance, **kwargs):
    """Delete physical AdImage files (original + thumbnails) after the
    DB transaction commits, preserving the project's TX-then-FS pattern.

    Collects storage_keys() at pre_delete time (when instance fields
    are populated) and defers file deletion via transaction.on_commit().

    A storage key is deleted only when no *other* ``AdImage`` row still
    references it. ``copy_ad`` deliberately points a copy at the source ad's
    keys (no file duplication), so the same key is legitimately shared across
    ads; when one sharing row is deleted the file must survive for the others.
    The existence check therefore excludes the instance being deleted -- at
    ``pre_delete`` time the row is still in the table (the cascade has not
    finished), so a naive ``filter(image=key).exists()`` would always match
    the row itself, skip every deletion and silently stop all file cleanup.
    That second failure mode is the more dangerous one: it leaks every
    orphaned file forever with no error. Do not "simplify" the exclusion away.
    """
    keys = list(instance.storage_keys())
    if not keys:
        return

    # At pre_delete time this row still exists, so exclude it explicitly by pk.
    shared = set(
        AdImage.objects.filter(image__in=keys)
        .exclude(pk=instance.pk)
        .values_list("image", flat=True)
    )
    orphaned = [key for key in keys if key not in shared]
    if not orphaned:
        return

    def _cleanup() -> None:
        for key in orphaned:
            try:
                delete_photo(key)
            except Exception:  # noqa: BLE001 — never let FS failure break the cascade
                logger.exception("Failed to delete media file for key: %s", key)

    transaction.on_commit(_cleanup)
