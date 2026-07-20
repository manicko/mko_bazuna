"""
Auto-moderation service for Mko Bazuna.

Single automatic gate before publish (US-A10). Caches ModerationCriteria for 5 minutes.
Validates ads against criteria and transitions status accordingly.
"""

import logging
from difflib import SequenceMatcher
from typing import Final

from django.utils import timezone

from apps.core.utils.cache import (
    CRITERIA_CACHE_KEY,  # noqa: F401 - re-exported for external use
    invalidate_criteria_cache,  # noqa: F401 - re-exported for external use
    get_cached_criteria,
    set_cached_criteria,
)

from apps.ads.models import Ad
from apps.analytics.models import AnalyticsEvent
from apps.core.enums import AdStatus, AnalyticsEventType, ModeratorActionType
from apps.moderation.models import ModeratorActionLog

logger = logging.getLogger(__name__)

CRITERIA_CACHE_SECONDS: Final[int] = 300  # 5 minutes (TTL)


def _get_cached_criteria() -> tuple:
    """
    Get cached ModerationCriteria as a tuple for cache compatibility.

    Returns criteria values as tuple for caching.
    Uses Django cache with key 'moderation_criteria:v1' and 5-minute TTL.
    Cache invalidated when criteria changes via signal.
    """
    cached = get_cached_criteria()
    if cached is not None:
        return (
            cached["title_min_length"],
            cached["title_max_length"],
            cached["description_min_length"],
            cached["description_max_length"],
            cached["price_required"],
            cached["min_images"],
            cached["max_images"],
            tuple(cached["banned_words"]),
            cached["max_ads_per_user"],
            cached["duplicate_title_threshold"],
        )

    criteria = _get_criteria_uncached()
    cached = {
        "title_min_length": criteria.title_min_length,
        "title_max_length": criteria.title_max_length,
        "description_min_length": criteria.description_min_length,
        "description_max_length": criteria.description_max_length,
        "price_required": criteria.price_required,
        "min_images": criteria.min_images,
        "max_images": criteria.max_images,
        "banned_words": criteria.banned_words,
        "max_ads_per_user": criteria.max_ads_per_user,
        "duplicate_title_threshold": criteria.duplicate_title_threshold,
    }
    set_cached_criteria(cached)
    return (
        criteria.title_min_length,
        criteria.title_max_length,
        criteria.description_min_length,
        criteria.description_max_length,
        criteria.price_required,
        criteria.min_images,
        criteria.max_images,
        tuple(criteria.banned_words),
        criteria.max_ads_per_user,
        criteria.duplicate_title_threshold,
    )


def _get_criteria_uncached():
    """Get ModerationCriteria singleton without caching."""
    from apps.moderation.models import ModerationCriteria as MC
    return MC.get_singleton()


def _invalidate_criteria_cache() -> None:
    """Invalidate the cached criteria to force refresh on next access."""
    invalidate_criteria_cache()


def auto_moderate(ad: Ad) -> bool:
    """
    Auto-moderate an ad before publish.

    Validates ad against cached ModerationCriteria:
    - title_min_length, title_max_length
    - description_min_length, description_max_length
    - price_required
    - min_images, max_images
    - banned_words (case-insensitive)
    - max_ads_per_user
    - duplicate_title (difflib.ratio >= threshold)

    On fail: sets ON_MODERATION_FAILED, moderation_failed_at, logs ModeratorActionLog.
    On pass: sets PUBLISHED, published_at, creates AnalyticsEvent.

    Returns True if passed, False if failed.
    """
    # Refresh cache if stale
    criteria_values = _get_cached_criteria()

    (
        title_min,
        title_max,
        desc_min,
        desc_max,
        price_required,
        min_imgs,
        max_imgs,
        banned_words,
        max_ads,
        dup_threshold,
    ) = criteria_values

    # Validate title length
    if not _validate_title_length(ad.title, title_min, title_max):
        _fail_moderation(ad)
        return False

    # Validate description length
    if not _validate_description_length(ad.description, desc_min, desc_max):
        _fail_moderation(ad)
        return False

    # Validate price required
    if price_required and ad.price is None:
        _fail_moderation(ad)
        return False

    # Validate image count
    if not _validate_image_count(ad, min_imgs, max_imgs):
        _fail_moderation(ad)
        return False

    # Validate banned words
    if _contains_banned_words(ad.title, ad.description, banned_words):
        _fail_moderation(ad)
        return False

    # Validate max ads per user
    if not _validate_max_ads_per_user(ad.user_id, max_ads):
        _fail_moderation(ad)
        return False

    # Validate duplicate title
    if _is_duplicate_title(ad.title, ad.user_id, ad.id, dup_threshold):
        _fail_moderation(ad)
        return False

    # All checks passed - publish
    _pass_moderation(ad)
    return True


def _validate_title_length(title: str, min_len: int, max_len: int) -> bool:
    """Validate title length is within bounds."""
    return min_len <= len(title) <= max_len


def _validate_description_length(description: str, min_len: int, max_len: int) -> bool:
    """Validate description length is within bounds."""
    return min_len <= len(description) <= max_len


def _validate_image_count(ad: Ad, min_count: int, max_count: int) -> bool:
    """Validate image count is within bounds."""
    img_count = ad.images.count()
    return min_count <= img_count <= max_count


def _contains_banned_words(title: str, description: str, banned_words: tuple) -> bool:
    """Check if title or description contains any banned words (case-insensitive)."""
    if not banned_words:
        return False

    combined_text = f"{title} {description}".lower()
    for word in banned_words:
        if word.lower() in combined_text:
            return True
    return False


def _validate_max_ads_per_user(user_id: int, max_ads: int) -> bool:
    """Validate user has not exceeded max active ads limit."""
    # Count only published and on-moderation ads (not drafts, rejected, archived, deleted)
    active_statuses = [AdStatus.PUBLISHED, AdStatus.ON_MODERATION, AdStatus.ON_MODERATION_FAILED]
    count = Ad.objects.filter(
        user_id=user_id,
        status__in=active_statuses,
    ).count()
    return count < max_ads


def _is_duplicate_title(title: str, user_id: int, ad_id: int, threshold: int) -> bool:
    """Check if title is too similar to existing user's titles using difflib.ratio."""
    # Get all titles from user's published and on-moderation ads (exclude current ad)
    existing_ads = Ad.objects.filter(
        user_id=user_id,
        status__in=[AdStatus.PUBLISHED, AdStatus.ON_MODERATION],
    ).exclude(id=ad_id)

    for existing_ad in existing_ads:
        similarity = SequenceMatcher(None, title.lower(), existing_ad.title.lower()).ratio()
        if similarity * 100 >= threshold:
            return True
    return False


def _fail_moderation(ad: Ad) -> None:
    """Set ad to ON_MODERATION_FAILED with timestamp and log action."""
    ad.status = AdStatus.ON_MODERATION_FAILED
    ad.moderation_failed_at = timezone.now()
    ad.save(update_fields=["status", "moderation_failed_at"])

    ModeratorActionLog.objects.create(
        ad_id=ad.id,
        user_id=ad.user_id,
        action_type=ModeratorActionType.OTHER,
        reason="Auto-moderation failed",
    )

    logger.info(f"Auto-moderation failed for ad {ad.id}")


def _pass_moderation(ad: Ad) -> None:
    """Set ad to PUBLISHED with timestamp and create analytics event."""
    now = timezone.now()
    ad.status = AdStatus.PUBLISHED
    ad.published_at = now
    if ad.original_published_at is None:
        ad.original_published_at = now
    ad.save(update_fields=["status", "published_at", "original_published_at"])

    AnalyticsEvent.objects.create(
        event_type=AnalyticsEventType.AD_PUBLISHED,
        user_id=ad.user_id,
    )

    logger.info(f"Auto-moderation passed for ad {ad.id}")