"""
Consent revocation + soft delete service for Mko Bazuna.

Implements zone R3 two consent states (decision F/K):
- DECLINE (browse-only): blocks only seller actions; no consent_revoked_at, no deletion
- WITHDRAW/DELETE: sets consent_revoked_at + is_deleted, nulls PII, soft-deletes ads

Hard-delete sweep (30 days) is Phase 4 per zone R1.
"""

import logging
from datetime import datetime

from apps.ads.models import Ad
from apps.core.enums import AdStatus
from apps.users.models import User

logger = logging.getLogger(__name__)


def decline_consent(user: User) -> None:
    """
    Decline consent (browse-only, decision K).

    This blocks only seller actions. No deletion occurs. Contact button continues to work.
    Sets ads_auto_publish=False to block new ads but preserves existing ads and PII.

    Does NOT set consent_revoked_at, is_deleted, or trigger any deletion.

    Args:
        user: The user declining consent.
    """
    user.ads_auto_publish = False
    user.save(update_fields=["ads_auto_publish"])
    logger.info(f"User {user.id} declined consent - ads_auto_publish=False, no deletion")


def withdraw_consent(user: User) -> None:
    """
    Withdraw consent and trigger immediate soft-delete (decision F).

    Flow (zone R3):
    - Sets consent_revoked_at = now()
    - Sets is_deleted = True, deleted_at = now()
    - NULLs telegram_id and username immediately (breaks chat linkage)
    - Soft-deletes all user ads (status=DELETED, hidden immediately)
    - Ads' images are cascade-deleted via AdImage.on_delete=CASCADE

    Phase 4 will hard-delete (remove rows) 30 days after consent_revoked_at.

    Args:
        user: The user withdrawing consent.
    """
    now = datetime.now()

    # Set consent revocation timestamp and soft-delete flags
    user.consent_revoked_at = now
    user.is_deleted = True
    user.deleted_at = now

    # NULL PII immediately (breaks chat linkage)
    user.telegram_id = None  # type: ignore[assignment]
    user.username = None

    user.save(update_fields=[
        "consent_revoked_at",
        "is_deleted",
        "deleted_at",
        "telegram_id",
        "username",
    ])

    # Soft-delete all user ads
    soft_delete_user_ads(user)

    logger.info(f"User {user.id} withdrew consent - soft-delete triggered")


def soft_delete_user_ads(user: User) -> int:
    """
    Soft-delete all ads belonging to a user.

    Sets ad status to DELETED and deleted_at to now. Images are cascade-deleted
    via AdImage.on_delete=CASCADE.

    Args:
        user: The user whose ads should be soft-deleted.

    Returns:
        Number of ads soft-deleted.
    """
    now = datetime.now()

    # Soft-delete all ads: set status=DELETED, deleted_at=now
    # Images cascade via on_delete=CASCADE in AdImage
    ads_deleted = Ad.objects.filter(user=user).update(
        status=AdStatus.DELETED,
        deleted_at=now,
    )

    logger.info(f"Soft-deleted {ads_deleted} ads for user {user.id}")
    return ads_deleted