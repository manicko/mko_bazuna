"""
Signal handlers for moderation app.

- Invalidates criteria cache on ModerationCriteria save.
- Calculates priority score when an ad enters ON_MODERATION status.
"""

import logging

from apps.ads.models import Ad
from apps.core.enums import AdStatus
from apps.moderation.models import ModerationCriteria
from apps.moderation.services.auto_moderation import _invalidate_criteria_cache
from apps.moderation.services.priority import PriorityService
from django.db.models.signals import post_save
from django.dispatch import receiver

logger = logging.getLogger(__name__)


@receiver(post_save, sender=ModerationCriteria)
def invalidate_criteria_cache_on_save(sender, instance, **kwargs):
    """
    Invalidate the cached ModerationCriteria after admin edits.

    Ensures fresh criteria values are used on next ad submission.
    """
    logger.info("Invalidating moderation criteria cache after save")
    _invalidate_criteria_cache()


@receiver(post_save, sender=Ad)
def calculate_ad_priority(sender, instance, **kwargs):
    """
    Automatically calculate priority when ad enters ON_MODERATION status.

    Triggers after save if status is ON_MODERATION and no priority record
    exists yet. Uses async in production to avoid blocking the request.
    """
    if instance.status != AdStatus.ON_MODERATION:
        return

    # Only calculate if priority record doesn't exist yet
    try:
        priority = getattr(instance, "moderation_priority", None)
        if priority is None:
            PriorityService().calculate_and_save(instance)
            logger.info("Calculated priority for ad %s", instance.id)
    except Exception as e:
        logger.error("Failed to calculate priority for ad %s: %s", instance.id, e)