"""
Moderator single-photo removal service.

A moderator who finds an inappropriate photo (a phone number, a face) in a
published ad previously had only two disproportionate levers: destroy the whole
listing — losing the seller's text, view count and analytics — or ban the
seller.  ``remove_ad_image`` is the third, proportionate lever: it removes one
``AdImage`` row from one ad and lets the existing ``pre_delete`` receiver free
the bytes.

**Byte freeing is not this service's job.**  ``AdImage`` is append-only by
construction and its file lifecycle is owned by
``apps.media.signals.delete_adimage_files_on_delete``, which composes
``apps.media.services.references.unreferenced_keys`` inside a
``transaction.on_commit`` closure.  Deleting the row is the whole mechanism.
Calling ``delete_photo`` directly here would create a **second byte-freeing
route** that bypasses the four-column reference check — a second data-loss
path — so this module deliberately never imports or calls it.

The single-row delete takes a ``select_for_update()`` lock in ``order_by("pk")``
order, the established row-lock shape in ``apps.moderation.admin_actions``.  A
single-row delete needs a row lock, not a process-wide ``AdvisoryLockId``, so no
new lock id is allocated (``CONSENT_RECORD_SWEEP = 14`` was taken by phase 06;
the next free id is 15 and is not this block's to allocate).
"""

from __future__ import annotations

import logging
from enum import StrEnum
from typing import NamedTuple

from django.db import transaction

from apps.ads.models import AdImage
from apps.moderation.services.moderation_log import log_photo_removed

logger = logging.getLogger(__name__)


class PhotoRemovalReason(StrEnum):
    """Canned audit reason for a moderator photo removal (INTERNAL ONLY).

    A fixed literal, never free text from the request.  Phase 06's
    reason-redaction has not landed at the ``apps.moderation.admin_actions``
    boundary, so accepting request text would risk storing unredacted
    moderator prose; a canned value sidesteps that entirely and is the same
    shape the existing auto/other log writers use.
    """

    INAPPROPRIATE_PHOTO = "inappropriate_photo"


class RemoveAdImageResult(NamedTuple):
    """Outcome of a single-photo removal.

    ``removed_key`` is the departing row's primary ``image`` storage key (the
    one a moderator would identify as "the photo"); the thumbnails are freed by
    the same signal path when nothing else references them.  ``audit_log_id``
    is the primary key of the single ``ModeratorActionLog`` row written for the
    removal, so the admin action can report it without re-querying.
    """

    removed_key: str
    audit_log_id: int


def remove_ad_image(ad_image: AdImage, moderator_id: int) -> RemoveAdImageResult:
    """Remove one ``AdImage`` row and record exactly one audit row.

    Reads the target under ``select_for_update()`` (``order_by("pk")``, the
    established shape) so a concurrent cascade cannot race the read-then-delete,
    captures the departing primary key, deletes the row, then writes the audit
    row — all inside one ``transaction.atomic()`` block.  The ``pre_delete``
    receiver registered its ``on_commit`` cleanup when the row was deleted, so
    the bytes are freed after this block commits, through BLOCK 2b's existing
    path.

    A shared key survives: the receiver checks all four key columns, so removing
    this row leaves another ad's files intact.

    Args:
        ad_image: The ``AdImage`` row to remove.  Only its primary key is
            trusted; the fields are re-read under the lock.
        moderator_id: The acting staff user's id, recorded on the audit row.

    Returns:
        The removed primary storage key and the audit-row id.
    """
    with transaction.atomic():  # pyright: ignore[reportGeneralTypeIssues] - Django: django-stubs not installed; Atomic.__enter__/__exit__ untyped
        locked = (
            AdImage.objects.select_for_update().order_by("pk").get(pk=ad_image.pk)
        )
        removed_key = locked.image
        ad_id = locked.ad_id
        locked.delete()
        audit_log = log_photo_removed(
            ad_id=ad_id,
            moderator_id=moderator_id,
            reason=PhotoRemovalReason.INAPPROPRIATE_PHOTO.value,
        )

    logger.info(
        "AdImage %s removed from ad %s by moderator %s (audit log %s)",
        ad_image.pk,
        ad_id,
        moderator_id,
        audit_log.pk,
    )
    return RemoveAdImageResult(
        removed_key=removed_key, audit_log_id=audit_log.pk
    )
