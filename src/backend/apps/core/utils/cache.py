"""
Django cache utilities for Mko Bazuna.

Holds the project's call-shaped cache helpers: five getter/setter/invalidate
triads (moderation criteria, site config, bot username, support contacts,
anonymous language) plus :func:`cache_get_or_none`, the shared cache-read
primitive.

Cache-failure policy (declared here, once). A cache **read** must never raise
into a request path: a cache outage degrades to "no cached value", never to a
5xx. Route every request-path read through :func:`cache_get_or_none`, which
swallows ``ConnectionInterrupted`` and ``redis.RedisError``, logs, and returns
``None``. This is the same exception tuple and the same fail-open intent as
``telegram_bot.middlewares.update_id_dedup.UpdateIdDedupMiddleware.__call__``.
A cache **write** may still raise; the caller that owns the value decides
whether to guard it (see ``apps.core.services.site_config``), because the
correct recovery differs per caller.
"""

import logging
from typing import Final, cast

import redis
from django.core.cache import cache
from django_redis.exceptions import ConnectionInterrupted

logger = logging.getLogger(__name__)

CRITERIA_CACHE_KEY: Final[str] = "moderation_criteria:v1"
CRITERIA_CACHE_TTL: Final[int] = 300  # 5 minutes


def cache_get_or_none(key: str) -> object | None:
    """Read ``key`` from the shared cache, returning ``None`` when unreachable.

    The project-wide policy (see the module docstring): a cache read never
    raises into a request path. A cache outage degrades to "no cached value",
    never to a 5xx. Same exception tuple and fail-open intent as
    ``telegram_bot.middlewares.update_id_dedup.UpdateIdDedupMiddleware.__call__``.
    """
    try:
        return cache.get(key)
    except (ConnectionInterrupted, redis.RedisError):
        logger.warning("Cache read failed for %s; treating as a cache miss", key)
        return None


def get_cached_criteria(key: str = CRITERIA_CACHE_KEY) -> dict | None:
    """
    Get cached ModerationCriteria values.

    Args:
        key: Cache key (defaults to moderation_criteria:v1)

    Returns:
        Dict with criteria values or None if not cached
    """
    return cache.get(key)


def set_cached_criteria(
    value: dict,
    key: str = CRITERIA_CACHE_KEY,
    ttl: int = CRITERIA_CACHE_TTL,
) -> None:
    """
    Set cached ModerationCriteria values.

    Args:
        value: Dict of criteria values to cache
        key: Cache key (defaults to moderation_criteria:v1)
        ttl: Time-to-live in seconds (defaults to 300)
    """
    cache.set(key, value, ttl)


def invalidate_criteria_cache(key: str = CRITERIA_CACHE_KEY) -> None:
    """
    Invalidate the cached ModerationCriteria.

    Called when admin updates criteria to ensure fresh values on next access.

    Args:
        key: Cache key to invalidate (defaults to moderation_criteria:v1)
    """
    cache.delete(key)


SITE_CONFIG_CACHE_KEY: Final[str] = "site_config:v1"
SITE_CONFIG_CACHE_TTL: Final[int] = 3600  # 1 hour


def get_cached_site_config(key: str = SITE_CONFIG_CACHE_KEY) -> str | None:
    """
    Get cached site name.

    Fail-open: a cache outage degrades to a miss (``None``), never a 5xx.

    Args:
        key: Cache key (defaults to site_config:v1)

    Returns:
        Site name string or None if not cached or the cache is unreachable
    """
    return cast("str | None", cache_get_or_none(key))


def set_cached_site_config(
    value: str,
    key: str = SITE_CONFIG_CACHE_KEY,
    ttl: int = SITE_CONFIG_CACHE_TTL,
) -> None:
    """
    Set cached site name.

    Args:
        value: Site name to cache
        key: Cache key (defaults to site_config:v1)
        ttl: Time-to-live in seconds (defaults to 3600)
    """
    cache.set(key, value, ttl)


def invalidate_site_config(key: str = SITE_CONFIG_CACHE_KEY) -> None:
    """
    Invalidate the cached site name.

    Called when admin updates site config to ensure fresh value on next access.

    Args:
        key: Cache key to invalidate (defaults to site_config:v1)
    """
    cache.delete(key)


BOT_USERNAME_CACHE_KEY: Final[str] = "site_config:bot_username:v1"


def get_cached_bot_username(key: str = BOT_USERNAME_CACHE_KEY) -> str | None:
    """
    Get cached bot username.

    Fail-open: a cache outage degrades to a miss (``None``), never a 5xx.

    Args:
        key: Cache key (defaults to site_config:bot_username:v1)

    Returns:
        Bot username string or None if not cached or the cache is unreachable
    """
    return cast("str | None", cache_get_or_none(key))


def set_cached_bot_username(
    value: str,
    key: str = BOT_USERNAME_CACHE_KEY,
    ttl: int = SITE_CONFIG_CACHE_TTL,
) -> None:
    """
    Set cached bot username.

    Args:
        value: Bot username to cache
        key: Cache key (defaults to site_config:bot_username:v1)
        ttl: Time-to-live in seconds (defaults to 3600)
    """
    cache.set(key, value, ttl)


def invalidate_bot_username_cache(key: str = BOT_USERNAME_CACHE_KEY) -> None:
    """
    Invalidate the cached bot username.

    Called when admin updates site config to ensure fresh value on next access.

    Args:
        key: Cache key to invalidate (defaults to site_config:bot_username:v1)
    """
    cache.delete(key)


SUPPORT_CONTACTS_CACHE_KEY: Final[str] = "support_contacts:v1"
SUPPORT_CONTACTS_CACHE_TTL: Final[int] = 3600  # 1 hour


def get_cached_support_contacts(
    key: str = SUPPORT_CONTACTS_CACHE_KEY,
) -> list | None:
    """
    Get cached support contacts.

    Args:
        key: Cache key (defaults to support_contacts:v1)

    Returns:
        List of cached SupportContact model instances or None if not cached
    """
    return cache.get(key)


def set_cached_support_contacts(
    value: list,
    key: str = SUPPORT_CONTACTS_CACHE_KEY,
    ttl: int = SUPPORT_CONTACTS_CACHE_TTL,
) -> None:
    """
    Set cached support contacts.

    Args:
        value: List of SupportContact model instances to cache
        key: Cache key (defaults to support_contacts:v1)
        ttl: Time-to-live in seconds (defaults to 3600)
    """
    cache.set(key, value, ttl)


def invalidate_support_contacts_cache(
    key: str = SUPPORT_CONTACTS_CACHE_KEY,
) -> None:
    """
    Invalidate the cached support contacts.

    Called when admin creates, updates, or deletes a SupportContact to ensure
    fresh data is fetched from the DB on the next access.

    Args:
        key: Cache key to invalidate (defaults to support_contacts:v1)
    """
    cache.delete(key)


ANON_LANG_CACHE_KEY_PATTERN: Final[str] = "bot_anon_lang:{telegram_id}"
ANON_LANG_CACHE_TTL: Final[int] = 3600  # 1 hour


def get_cached_anon_language(
    telegram_id: int,
    key: str = ANON_LANG_CACHE_KEY_PATTERN,
) -> str | None:
    """
    Get the cached language for an anonymous Telegram user.

    Args:
        telegram_id: Telegram user ID for which the language was cached
        key: Cache key pattern (defaults to bot_anon_lang:{telegram_id})

    Returns:
        Cached language code string or None if not cached
    """
    return cache.get(key.format(telegram_id=telegram_id))


def set_cached_anon_language(
    telegram_id: int,
    lang: str,
    key: str = ANON_LANG_CACHE_KEY_PATTERN,
    ttl: int = ANON_LANG_CACHE_TTL,
) -> None:
    """
    Cache the language for an anonymous Telegram user.

    Args:
        telegram_id: Telegram user ID for which to cache the language
        lang: Language code to cache
        key: Cache key pattern (defaults to bot_anon_lang:{telegram_id})
        ttl: Time-to-live in seconds (defaults to 3600)
    """
    cache.set(key.format(telegram_id=telegram_id), lang, ttl)


def invalidate_anon_language_cache(
    telegram_id: int,
    key: str = ANON_LANG_CACHE_KEY_PATTERN,
) -> None:
    """
    Invalidate the cached language for an anonymous Telegram user.

    Args:
        telegram_id: Telegram user ID whose cached language to invalidate
        key: Cache key pattern (defaults to bot_anon_lang:{telegram_id})
    """
    cache.delete(key.format(telegram_id=telegram_id))
