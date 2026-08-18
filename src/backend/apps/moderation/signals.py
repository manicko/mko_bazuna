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
from django.conf import settings
from django.db import transaction
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


@receiver(post_save, sender=Ad)
def deliver_immediate_alerts_on_publish(sender, instance, **kwargs):
    """
    Schedule near-real-time alert delivery when an ad is PUBLISHED (AL-001).

    Guarded by ``settings.IMMEDIATE_ALERTS_ENABLED`` (default OFF = safe
    rollout, CR15). Delivery runs inside ``transaction.on_commit`` so it only
    fires after the PUBLISHED commit, and the daily ``send_alerts`` command
    remains the catch-all/backfill (A5/C8).
    """
    if not getattr(settings, "IMMEDIATE_ALERTS_ENABLED", False):
        return

    if instance.status != AdStatus.PUBLISHED:
        return

    def _deliver() -> None:
        from apps.search.services.immediate_alerts import deliver_immediate_alerts

        deliver_immediate_alerts(instance.id)

    transaction.on_commit(_deliver)