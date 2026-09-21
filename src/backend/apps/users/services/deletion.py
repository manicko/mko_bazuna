"""

Consent revocation + soft delete service for Mko Bazuna.



Implements zone R3 two consent states (decision F/K):

- DECLINE (browse-only): blocks only seller actions; no consent_revoked_at, no deletion

- WITHDRAW/DELETE: sets consent_revoked_at + is_deleted, nulls PII, soft-deletes ads



Hard-delete sweep (30 days) is Phase 4 per zone R1.

"""

import logging

from django.db import transaction
from django.utils import timezone

from apps.ads.models import Ad, AdImage
from apps.core.enums import AdStatus
from apps.media.services.filesystem import delete_photo
from apps.users.models import LoginToken, User

logger = logging.getLogger(__name__)


def decline_consent(user: User) -> None:
    """

    Decline consent (browse-only, decision K).



    This blocks only seller actions. No deletion occurs. Contact button continues to work.

    Sets is_declined=True and ads_auto_publish=False to block new ads and login,

    but preserves existing ads and PII.



    Does NOT set consent_revoked_at, is_deleted, or trigger any deletion.



    Args:

        user: The user declining consent.

    """

    user.ads_auto_publish = False

    user.is_declined = True

    user.consent_given_at = None

    user.save(update_fields=["ads_auto_publish", "is_declined", "consent_given_at"])

    logger.info(
        "User %s declined consent - browse-only mode: "
        "ads_auto_publish=False, is_declined=True",
        user.id,
    )


def withdraw_consent(user: User) -> list[str]:
    """
    Withdraw consent and trigger immediate soft-delete (decision F).

    Flow (zone R3):

    - Sets consent_revoked_at = now()

    - Sets is_deleted = True, deleted_at = now()

    - NULLs telegram_id, username immediately (breaks chat linkage)
    - Empties first_name, last_name, email (NOT NULL fields — use "" not None)

    - Invalidates/deletes all active LoginTokens (prevents re-linking after withdrawal)

    - Soft-deletes all user ads (status=DELETED, hidden immediately)

    - DRAFT ads' media files are physically removed from disk

    All DB mutations run inside ``transaction.atomic()`` so that a failure in
    any step rolls back LoginToken deletion, PII nulling, and ad soft-delete.
    Filesystem deletions (``delete_photo``) are performed AFTER the transaction
    commits, following the TX-then-Filesystem pattern. A rollback must never
    remove files for rows that remain in the DB.

    Idempotency: if the user is already soft-deleted (``is_deleted=True``),
    the call is a no-op returning ``[]``.

    Phase 4 will hard-delete (remove rows) 30 days after consent_revoked_at.

    Args:

        user: The user withdrawing consent.

    Returns:

        Storage keys of DRAFT-ad media files deleted from disk (``[]`` when
        the user was already deleted or had no DRAFT ads with images).

    """

    with transaction.atomic():  # pyright: ignore[reportGeneralTypeIssues] - Django: django-stubs not installed; Atomic.__enter__/__exit__ untyped
        if user.is_deleted:
            logger.info("User %s already soft-deleted — skipping withdrawal", user.id)
            return []

        now = timezone.now()

        user_telegram_id = user.telegram_id

        # Invalidate active login tokens BEFORE nulling telegram_id
        # This prevents re-linking via a still-valid token after withdrawal
        LoginToken.objects.filter(telegram_id=user_telegram_id).delete()

        # Set consent revocation timestamp and soft-delete flags
        user.consent_revoked_at = now
        user.is_deleted = True
        user.deleted_at = now

        # NULL PII immediately (breaks chat linkage)
        user.telegram_id = None  # type: ignore[assignment]
        user.username = None
        user.first_name = ""
        user.last_name = ""
        user.email = ""
        user.consent_given_at = None

        user.save(
            update_fields=[
                "consent_revoked_at",
                "is_deleted",
                "deleted_at",
                "consent_given_at",
                "telegram_id",
                "username",
                "first_name",
                "last_name",
                "email",
            ]
        )

        # Soft-delete all user ads (DB-only: returns storage keys for FS cleanup)
        storage_keys = soft_delete_user_ads(user)

    # Delete physical media files after the transaction commits. Filesystem
    # deletions inside transaction.atomic() cannot be rolled back, so a DB
    # rollback would orphan DB rows pointing to already-deleted files.
    for storage_key in storage_keys:
        delete_photo(storage_key)

    logger.info("User %s withdrew consent - soft-delete triggered", user.id)
    return storage_keys


def soft_delete_user_ads(user: User) -> list[str]:
    """
    Soft-delete all ads belonging to a user (DB-only).

    Sets ad status to DELETED and deleted_at to now. For DRAFT ads, collects
    storage keys of their AdImage rows and deletes those rows, since the
    images are orphaned (never published). Physical file removal is the
    caller's responsibility — performed after the transaction commits to
    follow the TX-then-Filesystem pattern. For published ads, images remain
    on disk until the hard-delete sweep (30-day grace period).

    Args:

        user: The user whose ads should be soft-deleted.

    Returns:

        Storage keys of DRAFT-ad media files for filesystem cleanup.
        Empty when the user has no DRAFT ads with images.

    """

    now = timezone.now()

    draft_storage_keys: list[str] = []

    # Collect storage keys for DRAFT ads' images and delete rows (DB-only)
    # DRAFT ads are mid-FSM creations whose images are orphaned on withdrawal
    draft_ad_ids = list(
        Ad.objects.filter(user=user, status=AdStatus.DRAFT).values_list("id", flat=True)
    )

    if draft_ad_ids:
        draft_storage_keys = [
            key
            for img in AdImage.objects.filter(ad_id__in=draft_ad_ids)
            for key in img.storage_keys()
        ]

        # Delete AdImage rows for DRAFT ads (not cascade-deleted since Ad is soft-deleted)
        AdImage.objects.filter(ad_id__in=draft_ad_ids).delete()

        logger.info(
            "Collected %d media files for %d DRAFT ads of user %s for filesystem cleanup",
            len(draft_storage_keys),
            len(draft_ad_ids),
            user.id,
        )

    # Soft-delete all ads: set status=DELETED, deleted_at=now
    ads_deleted = Ad.objects.filter(user=user).update(
        status=AdStatus.DELETED,
        deleted_at=now,
    )

    logger.info("Soft-deleted %s ads for user %s", ads_deleted, user.id)
    return draft_storage_keys


def give_consent(user: User) -> None:
    """

    Give consent (decision F).



    Sets consent_given_at to now() for the user. This covers all processing

    including bot interactions.

    Covers the DECLINE to ACCEPT transition (D6): accepting after a decline

    restores full publishing ability (is_declined=False, ads_auto_publish=True)

    and clears a prior revocation timestamp.

    Does NOT reverse WITHDRAW: if the user is soft-deleted (is_deleted=True),

    the call is a no-op that returns immediately without mutating state or

    PII. WITHDRAW is terminal -- consent_revoked_at is not cleared and no

    ConsentRecord is persisted for a soft-deleted identity.

    Args:

        user: The user giving consent.

    """

    if user.is_deleted:
        logger.info(
            "User %s gave consent but is soft-deleted -- no-op (WITHDRAW is terminal)",
            user.id,
        )
        return

    user.consent_given_at = timezone.now()

    user.is_declined = False

    user.ads_auto_publish = True

    user.consent_revoked_at = None

    user.save(
        update_fields=[
            "consent_given_at",
            "is_declined",
            "ads_auto_publish",
            "consent_revoked_at",
        ]
    )

    logger.info("User %s gave consent - consent_given_at set", user.id)
