"""
Admin moderation actions service for Mko Bazuna.

Functions for individual ad actions: approve, reject, ban, soft delete.
Used by moderation review views and admin actions.
"""

import logging

from django.db import OperationalError, transaction

from apps.ads.models import Ad
from apps.core.enums import AdStatus, ApproveOutcome
from apps.core.utils.db_lock_timeout import is_lock_timeout
from apps.core.utils.sanitize import mask_telegram_id
from apps.moderation.services.auto_moderation import auto_moderate
from apps.moderation.services.exceptions import MaxAdsExceeded
from apps.moderation.services.moderation_log import (
    log_ban_account,
    log_soft_delete,
    set_rejected,
)
from apps.users.models import User

logger = logging.getLogger(__name__)


def approve_ad(ad: Ad, moderator_id: int) -> ApproveOutcome:
    """
    Approve an ad for publication.

    Delegates to auto_moderate() which validates the ad against
    ModerationCriteria and transitions status to PUBLISHED on success,
    or ON_MODERATION_FAILED on failure.

    The approvable set is ``{ON_MODERATION, ON_MODERATION_FAILED}``: a failed
    ad is reachable for human review, but the state machine (unchanged) still
    refuses ``ON_MODERATION_FAILED -> PUBLISHED``. That refusal is reported as
    ``TRANSITION_REFUSED`` rather than escaping as an exception, so no caller
    surfaces a 500.

    Args:
        ad: Ad instance to approve
        moderator_id: Moderator user ID performing the action

    Returns:
        ``ApproveOutcome.PUBLISHED`` if auto-moderation passed and the ad was
        published, ``ApproveOutcome.CRITERIA_REJECTED`` if auto-moderation ran
        and the ad failed the criteria, ``ApproveOutcome.TRANSITION_REFUSED``
        if the ad was not approvable or the state machine refused the
        transition.
    """
    if ad.status not in (AdStatus.ON_MODERATION, AdStatus.ON_MODERATION_FAILED):
        return ApproveOutcome.TRANSITION_REFUSED

    try:
        result = auto_moderate(ad, moderator_id=moderator_id)
    except ValueError as exc:
        # The state machine refused the transition; auto_moderate's own failure
        # handler may raise a second ValueError from inside its except body, so
        # the message is derived from the outcome, never from the exception text.
        logger.warning(
            "Ad %s (status=%s) approval refused by state machine: %s",
            ad.id,
            ad.status,
            exc,
        )
        return ApproveOutcome.TRANSITION_REFUSED

    if result:
        logger.info("Ad %s approved by moderator %s", ad.id, moderator_id)
        return ApproveOutcome.PUBLISHED

    logger.warning(
        "Ad %s failed auto-moderation during approval by moderator %s",
        ad.id,
        moderator_id,
    )
    return ApproveOutcome.CRITERIA_REJECTED


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
    logger.info("Ad %s rejected by moderator %s", ad.id, moderator_id)


def ban_user_for_ad(ad: Ad, moderator_id: int, reason: str) -> None:
    """
    Ban the user who posted the ad.

    Args:
        ad: Ad instance whose user will be banned
        moderator_id: Moderator user ID performing the action
        reason: Ban reason (INTERNAL ONLY)
    """
    with transaction.atomic():  # pyright: ignore[reportGeneralTypeIssues] - Django: django-stubs not installed; Atomic.__enter__/__exit__ untyped
        try:
            user = User.objects.select_for_update().get(id=ad.user_id)
        except User.DoesNotExist:
            logger.info(
                "ban_user_for_ad: user %s for ad %s already deleted, skipping",
                ad.user_id,
                ad.id,
            )
            return

        if not user.is_banned:
            user.is_banned = True
            user.save(update_fields=["is_banned"])

            log_ban_account(
                user_id=user.id,
                moderator_id=moderator_id,
                reason=reason,
            )
            logger.info(
                "User %s banned by moderator %s",
                mask_telegram_id(user.telegram_id),
                moderator_id,
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

    with transaction.atomic():  # pyright: ignore[reportGeneralTypeIssues] - Django: django-stubs not installed; Atomic.__enter__/__exit__ untyped
        ad.transition_to(AdStatus.DELETED)
        log_soft_delete(
            ad_id=ad.id,
            user_id=ad.user_id,
            moderator_id=moderator_id,
            reason=reason,
        )
    logger.info("Ad %s deleted by moderator %s", ad.id, moderator_id)


def bulk_approve(queryset, moderator_id: int) -> int:
    """
    Bulk approve ads for publication.

    Ads whose user has reached the ``max_ads_per_user`` cap are skipped
    (logged at WARN) rather than aborting the bulk operation.

    Args:
        queryset: Ad queryset to approve
        moderator_id: Moderator user ID performing the action

    Returns:
        Number of ads approved
    """
    count = 0
    try:
        with transaction.atomic():  # pyright: ignore[reportGeneralTypeIssues] - Django: django-stubs not installed; Atomic.__enter__/__exit__ untyped  lock Ad rows through every transition
            # Lock rows in PK order to match sweep lock ordering (no deadlock).
            # transition_to's refresh_from_db() raises Ad.DoesNotExist if a row was
            # hard-deleted mid-bulk (e.g. before the lock was acquired) — skip it
            # per-ad rather than aborting the whole bulk. MaxAdsExceeded
            # is already caught per-ad and preserved here.
            for ad in (
                queryset.filter(
                    status__in=[AdStatus.ON_MODERATION, AdStatus.ON_MODERATION_FAILED]
                )
                .order_by("pk")
                .select_for_update()
            ):
                try:
                    outcome = approve_ad(ad, moderator_id)
                    if outcome is not ApproveOutcome.PUBLISHED:
                        logger.warning(
                            "Skipping ad %s in bulk_approve: %s",
                            ad.id,
                            outcome,
                        )
                        continue
                except MaxAdsExceeded as exc:
                    logger.warning(
                        "Skipping ad %s in bulk_approve: user %s reached "
                        "max %s active ads (current_count=%s)",
                        ad.id,
                        exc.user_id,
                        exc.limit,
                        exc.current_count,
                    )
                    continue
                except Ad.DoesNotExist:
                    logger.warning(
                        "Skipping ad %s in bulk_approve: row hard-deleted mid-bulk",
                        ad.id,
                    )
                    continue
                count += 1
    except OperationalError as exc:
        if not is_lock_timeout(exc):
            raise
        # 03-DB-004: the locking SELECT ... FOR UPDATE precedes every row body, so a
        # lock timeout here fails the bulk with NOTHING committed. Fail loudly;
        # a silently partial bulk is strictly worse, and a per-row continue is
        # not available for the primary path (the lock statement is outside the
        # loop body).
        logger.error("bulk_approve aborted by lock timeout (SQLSTATE 55P03)")
        raise
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
    try:
        with transaction.atomic():  # pyright: ignore[reportGeneralTypeIssues] - Django: django-stubs not installed; Atomic.__enter__/__exit__ untyped  lock Ad rows through every transition
            # Lock rows in PK order. reject_ad()→set_rejected()→transition_to()
            # calls refresh_from_db(); a row hard-deleted mid-bulk raises
            # Ad.DoesNotExist — skip it per-ad rather than aborting the bulk.
            for ad in (
                queryset.filter(
                    status__in=[AdStatus.ON_MODERATION, AdStatus.ON_MODERATION_FAILED]
                )
                .order_by("pk")
                .select_for_update()
            ):
                if ad.status != AdStatus.REJECTED:
                    try:
                        reject_ad(ad, moderator_id, reason)
                    except Ad.DoesNotExist:
                        logger.warning(
                            "Skipping ad %s in bulk_reject: row hard-deleted mid-bulk",
                            ad.id,
                        )
                        continue
                    count += 1
    except OperationalError as exc:
        if not is_lock_timeout(exc):
            raise
        # 03-DB-004: fail the bulk with nothing committed rather than hanging.
        logger.error("bulk_reject aborted by lock timeout (SQLSTATE 55P03)")
        raise
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

    with transaction.atomic():  # pyright: ignore[reportGeneralTypeIssues] - Django: django-stubs not installed; Atomic.__enter__/__exit__ untyped
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
    try:
        with transaction.atomic():  # pyright: ignore[reportGeneralTypeIssues] - Django: django-stubs not installed; Atomic.__enter__/__exit__ untyped  lock Ad rows through every transition
            # Lock rows in PK order. soft_delete_ad()→transition_to(DELETED) calls
            # refresh_from_db(); a row hard-deleted mid-bulk raises
            # Ad.DoesNotExist — skip it per-ad rather than aborting the bulk.
            for ad in (
                queryset.exclude(status=AdStatus.DELETED).order_by("pk").select_for_update()
            ):
                try:
                    soft_delete_ad(ad, moderator_id, reason)
                except Ad.DoesNotExist:
                    logger.warning(
                        "Skipping ad %s in bulk_delete: row hard-deleted mid-bulk",
                        ad.id,
                    )
                    continue
                count += 1
    except OperationalError as exc:
        if not is_lock_timeout(exc):
            raise
        # 03-DB-004: fail the bulk with nothing committed rather than hanging.
        logger.error("bulk_delete aborted by lock timeout (SQLSTATE 55P03)")
        raise
    return count
