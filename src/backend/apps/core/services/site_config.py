"""
Shared site-config service for Mko Bazuna.

Provides the single admin-configurable site name, cached with a 1-hour TTL.
Used by the web context processor (sync) and the Telegram bot (async).
"""

import logging
from typing import cast

from asgiref.sync import sync_to_async

logger = logging.getLogger(__name__)


def get_site_name() -> str:
    """Return the admin-configured site name (cached, 1h TTL).

    Falls back to 'Bazuna' if the DB or cache is unavailable (R-SN-05).
    """
    from apps.core.utils.cache import (
        get_cached_site_config,
        set_cached_site_config,
    )
    from apps.core.models import SiteConfig

    cached = get_cached_site_config()
    if cached:
        return cached
    try:
        obj = SiteConfig.get_singleton()
        name = cast(str, obj.name)
        set_cached_site_config(name)
        return name
    except Exception:
        logger.warning("SiteConfig unavailable; falling back to 'Bazuna'")
        return "Bazuna"


async def get_site_name_async() -> str:
    """Async wrapper for bot handlers — runs get_site_name in a thread."""
    return await sync_to_async(get_site_name)()
