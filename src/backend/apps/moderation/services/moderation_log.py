"""
Moderation logging service for Mko Bazuna.

Audit trail for auto-fail and manual reject actions (zone D8, zone R1).
Reason field is TEXT and NEVER shown to seller (US-A11).
"""

import logging
from typing import TYPE_CHECKING

from django.db import transaction

from apps.core.enums import AdStatus, ModeratorActionType
from apps.moderation.models import ModeratorActionLog

if TYPE_CHECKING:
    from apps.ads.models import Ad

logger = logging.getLogger(__name__)


def log_auto_fail(ad_id: int, user_id: int) -> ModeratorActionLog:
    """
    Log auto-moderation failure for an ad.

    Creates ModeratorActionLog entry with action_type=OTHER (auto),
    NULL moderated_by (auto action), and auto-generated reason.

    Args:
        ad_id: The ad ID that failed auto-moderation.
        user_id: The user ID who owns the ad.

    Returns:
        The created ModeratorActionLog instance.
    """
    log = ModeratorActionLog.objects.create(
        ad_id=ad_id,
        user_id=user_id,
        action_type=ModeratorActionType.OTHER,
        reason="Auto-moderation failed",
    )
    logger.info(f"Logged auto-moderation failure for ad {ad_id}")
    return log


def log_manual_reject(
    ad_id: int,
    user_id: int,
    moderator_id: int,
    reason: str,
) -> ModeratorActionLog:
    """
    Log manual rejection by moderator.

    Creates ModeratorActionLog entry with action_type=REJECT,
    moderated_by set to the moderator, and the provided reason.

    Args:
        ad_id: The ad ID that was rejected.
        user_id: The user ID who owns the ad.
        moderator_id: The moderator user ID who performed the rejection.
        reason: The rejection reason (INTERNAL ONLY - never shown to seller).

    Returns:
        The created ModeratorActionLog instance.
    """
    log = ModeratorActionLog.objects.create(
        ad_id=ad_id,
        user_id=user_id,
        action_type=ModeratorActionType.REJECT,
        reason=reason,
    )
    logger.info(f"Logged manual rejection for ad {ad_id} by moderator {moderator_id}")
    return log


def log_auto_publish(ad_id: int, user_id: int) -> ModeratorActionLog:
    """
    Log auto-publication by the system.

    Creates ModeratorActionLog entry with action_type=OTHER for audit trail.

    Args:
        ad_id: The ad ID that was published.
        user_id: The user ID who owns the ad.

    Returns:
        The created ModeratorActionLog instance.
    """
    log = ModeratorActionLog.objects.create(
        ad_id=ad_id,
        user_id=user_id,
        action_type=ModeratorActionType.OTHER,
        reason="Auto-published",
    )
    logger.info(f"Logged auto-publish for ad {ad_id}")
    return log


def log_manual_publish(ad_id: int, moderator_id: int) -> ModeratorActionLog:
    """
    Log manual publication by moderator.

    Creates ModeratorActionLog entry for manually publishing an ad.

    Args:
        ad_id: The ad ID that was published.
        moderator_id: The moderator user ID who performed the publication.

    Returns:
        The created ModeratorActionLog instance.
    """
    log = ModeratorActionLog.objects.create(
        ad_id=ad_id,
        action_type=ModeratorActionType.OTHER,
        reason="Manually published by moderator",
    )
    logger.info(f"Logged manual publish for ad {ad_id} by moderator {moderator_id}")
    return log


def log_ban_account(user_id: int, moderator_id: int, reason: str) -> ModeratorActionLog:
    """
    Log account ban action by moderator.

    Creates ModeratorActionLog entry with action_type=BAN_ACCOUNT.

    Args:
        user_id: The user ID who was banned.
        moderator_id: The moderator user ID who performed the ban.
        reason: The ban reason (INTERNAL ONLY).

    Returns:
        The created ModeratorActionLog instance.
    """
    log = ModeratorActionLog.objects.create(
        user_id=user_id,
        action_type=ModeratorActionType.BAN_ACCOUNT,
        reason=reason,
    )
    logger.info(f"Logged ban account for user {user_id} by moderator {moderator_id}")
    return log


def log_soft_delete(ad_id: int, user_id: int | None, moderator_id: int, reason: str) -> ModeratorActionLog:
    """
    Log soft delete action by moderator.

    Creates ModeratorActionLog entry with action_type=SOFT_DELETE.

    Args:
        ad_id: The ad ID that was soft-deleted.
        user_id: The user ID who owns the ad (may be None for admin-initiated).
        moderator_id: The moderator user ID who performed the delete.
        reason: The delete reason (INTERNAL ONLY).

    Returns:
        The created ModeratorActionLog instance.
    """
    log = ModeratorActionLog.objects.create(
        ad_id=ad_id,
        user_id=user_id,
        action_type=ModeratorActionType.SOFT_DELETE,
        reason=reason,
    )
    logger.info(f"Logged soft delete for ad {ad_id} by moderator {moderator_id}")
    return log


def set_moderation_failed(ad: "Ad", reason: str = "Auto-moderation failed") -> None:  # noqa: UP037
    """Set ad status to ON_MODERATION_FAILED and log the action.

    Wrapped in ``transaction.atomic()`` to ensure the status transition and
    audit log entry are committed or rolled back together (DB-002).

    Args:
        ad: The Ad instance that failed moderation.
        reason: The reason for failure (default: auto-moderation).
    """
    with transaction.atomic():  # pyright: ignore[reportGeneralTypeIssues]
        ad.transition_to(AdStatus.ON_MODERATION_FAILED)
        log_auto_fail(ad_id=ad.id, user_id=ad.user_id)


def set_rejected(ad: "Ad", moderator_id: int, reason: str) -> None:  # noqa: UP037
    """Set ad status to REJECTED, populate moderated_by, and log the action.

    Wrapped in ``transaction.atomic()`` to ensure the status transition and
    audit log entry are committed or rolled back together (DB-002).

    Args:
        ad: The Ad instance to reject.
        moderator_id: The moderator user ID performing the rejection.
        reason: The rejection reason (INTERNAL ONLY - never shown to seller).
    """
    with transaction.atomic():  # pyright: ignore[reportGeneralTypeIssues]
        ad.transition_to(AdStatus.REJECTED, moderator_id=moderator_id)
        log_manual_reject(
            ad_id=ad.id,
            user_id=ad.user_id,
            moderator_id=moderator_id,
            reason=reason,
        )


def set_published(ad: "Ad", moderator_id: int | None = None) -> None:  # noqa: UP037
    """Set ad status to PUBLISHED with optional moderator and log the action.

    Wrapped in ``transaction.atomic()`` to ensure the status transition and
    audit log entry are committed or rolled back together (DB-002).

    Args:
        ad: The Ad instance to publish.
        moderator_id: The moderator user ID (None for auto-publish).
    """
    with transaction.atomic():  # pyright: ignore[reportGeneralTypeIssues]
        ad.transition_to(AdStatus.PUBLISHED, moderator_id=moderator_id)

        if moderator_id:
            log_manual_publish(ad_id=ad.id, moderator_id=moderator_id)
        else:
            log_auto_publish(ad_id=ad.id, user_id=ad.user_id)
