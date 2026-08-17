"""
Admin moderation actions service for Mko Bazuna.

Functions for individual ad actions: approve, reject, ban, soft delete.
Used by moderation review views and admin actions.
"""

import logging

from apps.ads.models import Ad
from apps.core.enums import AdStatus
from apps.core.utils.sanitize import mask_telegram_id
from apps.moderation.services.moderation_log import (
    log_ban_account,
    log_soft_delete,
    set_published,
    set_rejected,
)
from apps.users.models import User
from django.db import transaction

logger = logging.getLogger(__name__)


def approve_ad(ad: Ad, moderator_id: int) -> None:
    """
    Approve an ad for publication.

    Sets original_published_at on first publish (immutable audit field).
    Delegates to set_published() which routes through transition_to(PUBLISHED)
    and logs the action atomically.

    Args:
        ad: Ad instance to approve
        moderator_id: Moderator user ID performing the action
    """
    if ad.status != AdStatus.ON_MODERATION:
        return

    set_published(ad, moderator_id=moderator_id)
    logger.info(f"Ad {ad.id} approved by moderator {moderator_id}")


def reject_ad(ad: Ad, moderator_id: int, reason: str) -> None:
    """
    Reject an ad with reason.

    Delegates to set_rejected() which routes through transition_to(REJECTED)
    and logs the action atomically. The transition matrix enforces valid
    source statuses: ON_MODERATION and ON_MODERATION_FAILED only.

    Args:
        ad: Ad instance to reject
        moderator_id: Moderator user ID performing the action
        reason: Rejection reason (INTERNAL ONLY - Layer-2 checklist + TEXT)
    """
    if ad.status == AdStatus.REJECTED:
        return

    set_rejected(ad, moderator_id=moderator_id, reason=reason)
    logger.info(f"Ad {ad.id} rejected by moderator {moderator_id}")


def ban_user_for_ad(ad: Ad, moderator_id: int, reason: str) -> None:
    """
    Ban the user who posted the ad.

    Args:
        ad: Ad instance whose user will be banned
        moderator_id: Moderator user ID performing the action
        reason: Ban reason (INTERNAL ONLY)
    """
    user = ad.user
    if user and not user.is_banned:
        user.is_banned = True
        user.save(update_fields=["is_banned"])

        log_ban_account(
            user_id=user.id,
            moderator_id=moderator_id,
            reason=reason,
        )
        logger.info(
            f"User {mask_telegram_id(user.telegram_id)} banned by moderator {moderator_id}"
        )


def soft_delete_ad(ad: Ad, moderator_id: int, reason: str) -> None:
    """
    Soft delete an ad.

    Routes through transition_to(DELETED) via the state machine driver.
    The any->DELETED transition is always valid per the transition matrix.

    Args:
        ad: Ad instance to delete
        moderator_id: Moderator user ID performing the action
        reason: Delete reason (INTERNAL ONLY)
    """
    if ad.status == AdStatus.DELETED:
        return

    with transaction.atomic():  # pyright: ignore[reportGeneralTypeIssues]
        ad.transition_to(AdStatus.DELETED)
        log_soft_delete(
            ad_id=ad.id,
            user_id=ad.user_id,
            moderator_id=moderator_id,
            reason=reason,
        )
    logger.info(f"Ad {ad.id} deleted by moderator {moderator_id}")


def bulk_approve(queryset, moderator_id: int) -> int:
    """
    Bulk approve ads for publication.

    Args:
        queryset: Ad queryset to approve
        moderator_id: Moderator user ID performing the action

    Returns:
        Number of ads approved
    """
    count = 0
    for ad in queryset.filter(status=AdStatus.ON_MODERATION):
        approve_ad(ad, moderator_id)
        count += 1
    return count


def bulk_reject(queryset, moderator_id: int, reason: str) -> int:
    """
    Bulk reject ads with reason.

    Args:
        queryset: Ad queryset to reject
        moderator_id: Moderator user ID performing the action
        reason: Rejection reason (INTERNAL ONLY)

    Returns:
        Number of ads rejected
    """
    count = 0
    for ad in queryset.filter(
        status__in=[AdStatus.ON_MODERATION, AdStatus.ON_MODERATION_FAILED]
    ):
        if ad.status != AdStatus.REJECTED:
            reject_ad(ad, moderator_id, reason)
            count += 1
    return count


def bulk_ban_users(queryset, moderator_id: int, reason: str) -> int:
    """
    Bulk ban users who posted the ads.

    Args:
        queryset: Ad queryset to identify users
        moderator_id: Moderator user ID performing the action
        reason: Ban reason (INTERNAL ONLY)

    Returns:
        Number of users banned
    """
    user_ids = set(queryset.values_list("user_id", flat=True))
    count = 0

    for user_id in user_ids:
        if user_id:
            log_ban_account(
                user_id=user_id,
                moderator_id=moderator_id,
                reason=reason,
            )
            count += 1

    User.objects.filter(id__in=user_ids).update(is_banned=True)
    return count


def bulk_delete(queryset, moderator_id: int, reason: str) -> int:
    """
    Bulk soft delete ads.

    Args:
        queryset: Ad queryset to delete
        moderator_id: Moderator user ID performing the action
        reason: Delete reason (INTERNAL ONLY)

    Returns:
        Number of ads deleted
    """
    count = 0
    for ad in queryset.exclude(status=AdStatus.DELETED):
        soft_delete_ad(ad, moderator_id, reason)
        count += 1
    return count
