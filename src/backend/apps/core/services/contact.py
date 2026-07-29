"""
Contact bridge service for Mko Bazuna.

Implements zone R2 render conditions and analytics recording for anonymous contact.
Used by web templates to determine if contact button should render.
"""

import logging

from apps.ads.models import Ad
from apps.analytics.models import AnalyticsEvent
from apps.core.enums import AdStatus, AnalyticsEventType
from apps.users.models import User

logger = logging.getLogger(__name__)

# Render conditions (Zone R2)
# Contact button renders ONLY when all conditions are met:
# - ad.status == PUBLISHED
# - seller.telegram_id IS NOT NULL
# - NOT seller.is_deleted
# - NOT seller.is_banned
# - seller.consent_revoked_at IS NULL


def can_contact_seller(ad: Ad) -> bool:
    """
    Check if contact button should render for an ad (zone R2 conditions).

    Render conditions:
        - ad.status == PUBLISHED
        - seller.telegram_id IS NOT NULL
        - NOT seller.is_deleted
        - NOT seller.is_banned
        - seller.consent_revoked_at IS NULL

    Args:
        ad: The ad to check contact eligibility for.

    Returns:
        True if contact button should render, False otherwise.
    """
    if ad.status != AdStatus.PUBLISHED:
        return False

    seller = ad.user
    if seller is None:
        return False

    if seller.telegram_id is None:
        return False

    if seller.is_deleted:
        return False

    if seller.is_banned:
        return False

    if seller.consent_revoked_at is not None:
        return False

    return True


def get_seller_for_contact(ad_id: int) -> tuple[bool, User | None]:
    """
    Get seller info for contact delivery.

    Checks ad status and seller availability. Used by bot handler.

    Args:
        ad_id: The ad ID to look up.

    Returns:
        Tuple of (is_available, seller_user or None).
        If ad not found or not PUBLISHED: (False, None).
        If seller unavailable: (False, None).
        If seller available: (True, User).
    """
    try:
        ad = Ad.objects.select_related("user").get(id=ad_id)
    except Ad.DoesNotExist:
        return (False, None)

    if ad.status != AdStatus.PUBLISHED:
        return (False, None)

    seller = ad.user
    if seller is None:
        return (False, None)

    if seller.telegram_id is None:
        return (False, None)

    if seller.is_deleted:
        return (False, None)

    if seller.is_banned:
        return (False, None)

    if seller.consent_revoked_at is not None:
        return (False, None)

    return (True, seller)


def record_contact_initiated(buyer_telegram_id: int | None = None) -> None:
    """
    Record CONTACT_INITIATED analytics event.

    User field is nullable since buyer may not be authenticated (no login required).

    Args:
        buyer_telegram_id: Optional buyer telegram_id for attribution (may be None).
    """
    user_id = None
    if buyer_telegram_id is not None:
        try:
            user = User.objects.get(telegram_id=buyer_telegram_id)
            user_id = user.id
        except User.DoesNotExist:
            pass  # User may not exist yet, that's fine

    AnalyticsEvent.objects.create(
        event_type=AnalyticsEventType.CONTACT_INITIATED,
        user_id=user_id,
    )
    logger.info("Contact initiated event recorded for buyer %s", user_id)


def record_contact_response(seller_telegram_id: int) -> None:
    """
    Record CONTACT_RESPONSE analytics event.

    Called when seller confirms receiving a contact message from a buyer.
    The response rate is used by TrustCalculator for seller trust scoring.

    Args:
        seller_telegram_id: The seller's Telegram ID.
    """
    try:
        user = User.objects.get(telegram_id=seller_telegram_id)
        AnalyticsEvent.objects.create(
            event_type=AnalyticsEventType.CONTACT_RESPONSE,
            user_id=user.id,
        )
        logger.info("Contact response event recorded for seller %s", user.id)
    except User.DoesNotExist:
        logger.warning("Seller not found for telegram_id %s", seller_telegram_id)