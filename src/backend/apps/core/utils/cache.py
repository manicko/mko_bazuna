"""
Django cache utilities for Mko Bazuna.

Holds the project's call-shaped cache helpers: five getter/setter/invalidate
triads (moderation criteria, site config, bot username, support contacts,
anonymous language) plus :func:`cache_get_or_none`, the shared cache-read
primitive, :func:`bump_rate_limit_window`, the shared
:func:`cache_get_or_none` sibling that guards a rate-limit window write, and
:func:`bump_version_key`, the shared durable cache-version counter write.

Cache-failure policy (declared here, once). A request-path cache **read** must
never raise into a request path: a cache outage degrades to "no cached value",
never to a 5xx. Route every request-path read through :func:`cache_get_or_none`,
which swallows ``ConnectionInterrupted`` and ``redis.RedisError``, logs, and
returns ``None``. This is the same exception tuple and the same fail-open intent
as ``telegram_bot.middlewares.update_id_dedup.UpdateIdDedupMiddleware.__call__``.
A request-path **write** that guards traffic — the rate-limit window bump — also
fails open, through :func:`bump_rate_limit_window`, which logs a WARNING naming
the key and reports "allowed". Other cache writes still raise; the caller that
owns the value decides whether to guard them (see
``apps.core.services.site_config``), because the correct recovery differs per
caller.

Cache-version-key policy (declared here, once). A cache-version key is a
**durability** mechanism, not a cache entry: it must outlive every entry that
embeds it, so it is written with ``timeout=None``. Route every version-counter
write through :func:`bump_version_key`, which owns the ``timeout=None``
invariant and returns the new value so a caller cannot accidentally pass a TTL.
See ``docs/architecture/cache-strategy.md``.
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


def bump_rate_limit_window(key: str, limit: int, period: int) -> bool:
    """Return ``True`` when the caller is within its window, fail-open on cache loss.

    The shared body of every request-path rate-limit guard: it bumps ``key`` in
    the shared cache using the atomic ``cache.add`` + ``cache.incr`` idiom and
    reports whether the resulting count is within ``limit``. On a cache outage it
    degrades to "no limit" rather than raising, mirroring
    ``telegram_bot.middlewares.update_id_dedup.UpdateIdDedupMiddleware``: a Redis
    outage must not drop legitimate traffic. Never raises into a request path.

    Args:
        key: The already-derived cache key (the caller owns the key format).
        limit: Maximum number of hits allowed within the window.
        period: Window length in seconds.

    Returns:
        ``True`` if the caller may proceed, ``False`` if it is over the limit.
        A cache outage is reported as ``True`` (fail-open).
    """
    try:
        if cache.add(key, 1, timeout=period):
            return True
        current = cache.incr(key)
    except (ConnectionInterrupted, redis.RedisError):
        logger.warning("Cache write failed for %s; allowing request", key)
        return True
    except ValueError:
        # Key expired between the add/incr calls - treat as a fresh start.
        cache.set(key, 1, timeout=period)
        return True
    return current <= limit


def bump_version_key(key: str) -> int:
    """Increment a durable monotonic cache-version key and return the new value.

    A version key is a correctness mechanism, not a cache entry: every entry
    that embeds it (e.g. ``search:v1:{version}:...``) is retired by changing
    the embedded segment, so the counter must **outlive** those entries. It is
    therefore written with ``timeout=None`` and never expires. A bounded TTL
    makes the counter self-evict, the next bump re-issue ``1``, and an old key
    become byte-identical to a new one — silently resurrecting a stale entry.

    The helper owns the ``timeout=None`` invariant, so no caller can pass a
    TTL. Assumption: the shared Redis backend runs ``noeviction`` (no
    ``maxmemory`` / ``maxmemory-policy`` is configured in any compose file), so
    a TTL-less integer key is retained and not evicted under memory pressure.

    Uses ``cache.incr`` (atomic on Redis, thread-safe on LocMemCache); on a
    missing key (``ValueError`` — a fresh backend, or a legacy evictable key
    that expired) it seeds the counter at ``1`` with ``timeout=None``.

    Args:
        key: The already-derived version key (the caller owns the key format).

    Returns:
        The new counter value.

    Raises:
        ``ConnectionInterrupted`` / ``redis.RedisError`` — a version bump is not
        fail-open: the caller (a signal receiver or an invalidation path)
        decides whether to guard it, because a missed bump is a correctness
        failure, not a degraded read.
    """
    try:
        return int(cache.incr(key))
    except ValueError:
        cache.set(key, 1, timeout=None)
        return 1


def get_cached_criteria(key: str = CRITERIA_CACHE_KEY) -> dict | None:
    """
    Get the cached moderation criteria values.

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
    Set the cached moderation criteria values.

    Args:
        value: Dict of criteria values to cache
        key: Cache key (defaults to moderation_criteria:v1)
        ttl: Time-to-live in seconds (defaults to 300)
    """
    cache.set(key, value, ttl)


def invalidate_criteria_cache(key: str = CRITERIA_CACHE_KEY) -> None:
    """
    Invalidate the cached moderation criteria.

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
