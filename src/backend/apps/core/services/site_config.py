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

    Falls back to 'Bazuna' if the DB is unavailable (R-SN-05). The cache read is
    fail-open (``get_cached_site_config`` swallows a cache outage and reports a
    miss); the cache write is best-effort — a write failure is logged at DEBUG
    and does not mask the value the database returned.
    """
    from apps.core.models import SiteConfig
    from apps.core.utils.cache import (
        get_cached_site_config,
        set_cached_site_config,
    )

    try:
        cached = get_cached_site_config()
        if cached:
            return cached
        obj = SiteConfig.get_singleton()
        name = cast(str, obj.name)
    except Exception:
        logger.warning("SiteConfig unavailable; falling back to 'Bazuna'")
        return "Bazuna"

    try:
        set_cached_site_config(name)
    except Exception:
        logger.debug("Failed to cache site name; serving the database value")
    return name


async def get_site_name_async() -> str:
    """Async wrapper for bot handlers — runs get_site_name in a thread."""
    return await sync_to_async(get_site_name)()


def get_bot_username() -> str:
    """Return the admin-configured Telegram bot username (cached, 1h TTL).

    Falls back to 'bazuna_bot' if the DB is unavailable (Spec 18, Task 1). The
    cache read is fail-open (``get_cached_bot_username`` swallows a cache outage
    and reports a miss); the cache write is best-effort — a write failure is
    logged at DEBUG and does not mask the value the database returned.
    """
    from apps.core.models import SiteConfig
    from apps.core.utils.cache import (
        get_cached_bot_username,
        set_cached_bot_username,
    )

    try:
        cached = get_cached_bot_username()
        if cached:
            return cached
        obj = SiteConfig.get_singleton()
        username = cast(str, obj.bot_username)
    except Exception:
        logger.warning("SiteConfig unavailable; falling back to 'bazuna_bot'")
        return "bazuna_bot"

    try:
        set_cached_bot_username(username)
    except Exception:
        logger.debug("Failed to cache bot username; serving the database value")
    return username


async def get_bot_username_async() -> str:
    """Async wrapper for bot handlers — runs get_bot_username in a thread."""
    return await sync_to_async(get_bot_username)()
