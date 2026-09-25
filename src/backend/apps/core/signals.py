"""
Signal handlers for core app.

Invalidates cached site name, bot username, and support contacts after admin
edits to SiteConfig and SupportContact.
"""

import logging

from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from apps.core.models import SiteConfig, SupportContact as SupportContactModel
from apps.core.utils.cache import (
    invalidate_bot_username_cache,
    invalidate_site_config,
    invalidate_support_contacts_cache,
)

logger = logging.getLogger(__name__)


@receiver(post_save, sender=SiteConfig)
def invalidate_site_config_cache_on_save(sender, instance, **kwargs):
    """
    Invalidate the cached site name after admin edits.

    Ensures the fresh site name is used on next page render.
    """
    logger.info("Invalidating site config cache after save")
    invalidate_site_config()
    invalidate_bot_username_cache()


@receiver(post_save, sender=SupportContactModel)
def invalidate_support_contacts_cache_on_save(sender, instance, **kwargs):
    """
    Invalidate the cached support contacts after admin creates or updates.

    Ensures the fresh contact list is fetched from the DB on next access.
    """
    logger.info("Invalidating support contacts cache after save")
    invalidate_support_contacts_cache()


@receiver(post_delete, sender=SupportContactModel)
def invalidate_support_contacts_cache_on_delete(sender, instance, **kwargs):
    """
    Invalidate the cached support contacts after admin deletes a contact.

    Ensures the deleted contact is removed from the cache on next access.
    """
    logger.info("Invalidating support contacts cache after delete")
    invalidate_support_contacts_cache()
