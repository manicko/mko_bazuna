"""
Signal handlers for moderation app.

Invalidates criteria cache on ModerationCriteria save.
"""

import logging

from apps.moderation.models import ModerationCriteria
from apps.moderation.services.auto_moderation import _invalidate_criteria_cache
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