"""
Moderation logging service for Mko Bazuna.

Audit trail for auto-fail and manual reject actions (zone D8, zone R1).
Reason field is TEXT and NEVER shown to seller (US-A11).
"""

import logging

from django.db import transaction

from apps.ads.models import Ad
from apps.core.enums import AdStatus, ModeratorActionType
from apps.core.utils.sanitize import redact_free_text
from apps.moderation.models import ModerationCriteria, ModeratorActionLog
from apps.moderation.services.exceptions import MaxAdsExceeded
from apps.users.models import User

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
    logger.info("Logged auto-moderation failure for ad %s", ad_id)
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
        reason=redact_free_text(reason),
    )
    logger.info("Logged manual rejection for ad %s by moderator %s", ad_id, moderator_id)
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
    logger.info("Logged auto-publish for ad %s", ad_id)
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
    logger.info("Logged manual publish for ad %s by moderator %s", ad_id, moderator_id)
    return log


def log_photo_removed(
    ad_id: int, moderator_id: int, reason: str
) -> ModeratorActionLog:
    """
    Log a moderator's removal of a single ad photo.

    Creates a ModeratorActionLog entry with action_type=OTHER and the supplied
    **canned** reason. The reason is passed through ``redact_free_text`` like
    every other free-text writer — phase 06's write-time redaction landed at
    this ``moderation_log.py`` chokepoint (06-PII-114, ``b3fde27``), so the
    stored value is redacted regardless of the caller. Callers still supply a
    fixed literal rather than request text, which keeps a canned value from
    carrying PII in the first place.

    ``ModeratorActionLog`` has no dedicated actor column; its ``user`` field is
    documented as "User who was moderated **or performed action**", so the
    acting moderator is recorded there (there is no distinct moderated subject
    for a single-photo removal, other than the ad itself, which ``ad_id``
    carries).

    Args:
        ad_id: The ad the photo was removed from.
        moderator_id: The moderator user ID who performed the removal.
        reason: The canned removal reason (INTERNAL ONLY).

    Returns:
        The created ModeratorActionLog instance.
    """
    log = ModeratorActionLog.objects.create(
        ad_id=ad_id,
        user_id=moderator_id,
        action_type=ModeratorActionType.OTHER,
        reason=redact_free_text(reason),
    )
    logger.info(
        "Logged photo removal for ad %s by moderator %s", ad_id, moderator_id
    )
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
        reason=redact_free_text(reason),
    )
    logger.info("Logged ban account for user %s by moderator %s", user_id, moderator_id)
    return log


def log_soft_delete(
    ad_id: int, user_id: int | None, moderator_id: int, reason: str
) -> ModeratorActionLog:
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
        reason=redact_free_text(reason),
    )
    logger.info("Logged soft delete for ad %s by moderator %s", ad_id, moderator_id)
    return log


def set_moderation_failed(ad: Ad, reason: str = "Auto-moderation failed") -> None:
    """Set ad status to ON_MODERATION_FAILED and log the action.

    Wrapped in ``transaction.atomic()`` to ensure the status transition and
    audit log entry are committed or rolled back together.

    Args:
        ad: The Ad instance that failed moderation.
        reason: The reason for failure (default: auto-moderation).
    """
    with transaction.atomic():  # pyright: ignore[reportGeneralTypeIssues] - Django: django-stubs not installed; Atomic.__enter__/__exit__ untyped
        ad.transition_to(AdStatus.ON_MODERATION_FAILED)
        log_auto_fail(ad_id=ad.id, user_id=ad.user_id)


def set_rejected(ad: Ad, moderator_id: int, reason: str) -> None:
    """Set ad status to REJECTED, populate moderated_by, and log the action.

    Wrapped in ``transaction.atomic()`` to ensure the status transition and
    audit log entry are committed or rolled back together.

    Args:
        ad: The Ad instance to reject.
        moderator_id: The moderator user ID performing the rejection.
        reason: The rejection reason (INTERNAL ONLY - never shown to seller).
    """
    with transaction.atomic():  # pyright: ignore[reportGeneralTypeIssues] - Django: django-stubs not installed; Atomic.__enter__/__exit__ untyped
        ad.transition_to(AdStatus.REJECTED, moderator_id=moderator_id)
        log_manual_reject(
            ad_id=ad.id,
            user_id=ad.user_id,
            moderator_id=moderator_id,
            reason=reason,
        )


def set_published(ad: Ad, moderator_id: int | None = None) -> None:
    """Set ad status to PUBLISHED with optional moderator and log the action.

    Wrapped in ``transaction.atomic()`` to ensure the status transition and
    audit log entry are committed or rolled back together.

    The user row is locked with ``select_for_update()`` and the active-ads
    count is re-counted inside the transaction — this is the authoritative,
    race-safe guard for ``max_ads_per_user`` (the advisory check in
    ``auto_moderate`` / ``check`` is best-effort only). The in-flight ad is
    excluded from the count so a user at the limit boundary is not
    over-blocked (AD-002).

    Args:
        ad: The Ad instance to publish.
        moderator_id: The moderator user ID (None for auto-publish).

    Raises:
        MaxAdsExceeded: If the user has already reached their active-ads cap.
    """
    with transaction.atomic():  # pyright: ignore[reportGeneralTypeIssues] - Django: django-stubs not installed; Atomic.__enter__/__exit__ untyped
        # Lock the user row to serialize concurrent publish attempts for the
        # same user, closing the TOCTOU race on max_ads_per_user.
        User.objects.select_for_update().get(pk=ad.user_id)

        max_ads = ModerationCriteria.get_singleton().max_ads_per_user
        active_statuses = [AdStatus.PUBLISHED, AdStatus.ON_MODERATION]
        active_count = (
            Ad.objects.filter(
                user_id=ad.user_id,
                status__in=active_statuses,
            )
            # Exclude the in-flight ad: it is still ON_MODERATION at this
            # point, so counting it would over-block at the limit boundary
            # (AD-002) — a user with max_ads=N could never reach N active ads.
            .exclude(id=ad.id)
            .count()
        )
        if active_count >= max_ads:
            raise MaxAdsExceeded(
                user_id=ad.user_id,
                limit=max_ads,
                current_count=active_count,
            )

        ad.transition_to(AdStatus.PUBLISHED, moderator_id=moderator_id)

        if moderator_id:
            log_manual_publish(ad_id=ad.id, moderator_id=moderator_id)
        else:
            log_auto_publish(ad_id=ad.id, user_id=ad.user_id)
