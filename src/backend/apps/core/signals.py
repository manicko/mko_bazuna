"""
Signal handlers for core app.

Invalidates the cached site name after admin edits to SiteConfig.
"""

import logging

from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.core.models import SiteConfig
from apps.core.utils.cache import invalidate_site_config

logger = logging.getLogger(__name__)


@receiver(post_save, sender=SiteConfig)
def invalidate_site_config_cache_on_save(sender, instance, **kwargs):
    """
    Invalidate the cached site name after admin edits.

    Ensures the fresh site name is used on next page render.
    """
    logger.info("Invalidating site config cache after save")
    invalidate_site_config()
