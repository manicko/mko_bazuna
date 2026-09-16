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
    """
    keys = list(instance.storage_keys())
    if not keys:
        return

    def _cleanup() -> None:
        for key in keys:
            try:
                delete_photo(key)
            except Exception:  # noqa: BLE001 — never let FS failure break the cascade
                logger.exception("Failed to delete media file for key: %s", key)

    transaction.on_commit(_cleanup)
