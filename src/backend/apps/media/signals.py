"""
Signal handlers for the media app.

- ``delete_adimage_files_on_delete``: cleans up physical files
  (original + thumbnails) when an ``AdImage`` row is deleted,
  using the project's TX-then-FS pattern (delete after commit).
  A key is freed only when no ``AdImage`` row references it in any of
  its four key columns; that check is delegated to
  ``apps.media.services.references.unreferenced_keys`` and runs inside
  the ``on_commit`` closure.
"""

import logging

from django.db import transaction
from django.db.models.signals import pre_delete
from django.dispatch import receiver

from apps.ads.models import AdImage
from apps.media.services.filesystem import delete_photo
from apps.media.services.references import unreferenced_keys

logger = logging.getLogger(__name__)


@receiver(pre_delete, sender=AdImage)
def delete_adimage_files_on_delete(sender, instance, **kwargs):
    """Delete physical AdImage files (original + thumbnails) after commit.

    Preserves the project's TX-then-FS pattern: the departing row's
    ``storage_keys()`` are captured **by value** at ``pre_delete`` time (when
    the instance fields are still populated) and file deletion is deferred via
    ``transaction.on_commit()``.

    The liveness check runs **inside the closure**, after commit, and is
    unexcluded.  Django's ``Collector.delete()`` sends ``pre_delete`` for
    every collected instance *before* any ``DELETE``, so a check taken here
    would still see sibling rows that are about to disappear; two rows sharing
    a key in one cascade would each skip and the file would leak.  After
    commit those rows are gone, so ``unreferenced_keys()`` answers the correct
    question -- "referenced by any row" -- and the multi-row-cascade leak is
    eliminated.  The closure therefore must not touch ``instance``:
    ``Collector`` sets ``instance.pk = None`` after its ``atomic()`` block, so
    an ``.exclude(pk=instance.pk)`` would raise ``ValueError``.

    A key shared through **any** of the four columns (``image``,
    ``thumbnail_small``, ``thumbnail_medium``, ``thumbnail_large``) survives
    while another ``AdImage`` still references it.  ``copy_ad`` deliberately
    points a copy at the source ad's keys (no file duplication), so keys are
    legitimately shared across ads.

    Residual, accepted characteristic: in a multi-row cascade a shared key is
    passed to ``delete_photo`` **once per departing row**.  The second call
    hits the terminal ``FileNotFoundError`` path and returns before
    ``_record_deletion_error``, so it logs one WARN and writes no
    ``MediaDeletionError`` row.
    """
    keys = tuple(instance.storage_keys())
    if not keys:
        return

    def _cleanup() -> None:
        for key in unreferenced_keys(keys):
            try:
                delete_photo(key)
            except Exception:  # noqa: BLE001 — never let FS failure break the cascade
                logger.exception("Failed to delete media file for key: %s", key)

    transaction.on_commit(_cleanup)
