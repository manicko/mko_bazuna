"""
Stale-while-revalidate cache utility for Mko Bazuna.

Wraps Django's ``cache.get``/``cache.set`` with a bounded stale-serve window
and a ``cache.add``-based single-flight lock so that concurrent misses under
invalidation or cold-start do not amplify into a thundering-herd recompute.

Works on both Redis (production — true cross-process single-flight) and
LocMemCache (dev/test — single-flight is intra-process only; stale-serve
path is exercised by tests).

State machine per key:

1. **Fresh hit** (age < ttl):  return cached value immediately.
2. **Stale hit** (ttl <= age < ttl + stale_ttl):
   - Serve the stale value immediately to the caller.
   - Attempt ``cache.add(lock_key)`` — the single "winner" worker
     recomputes via *producer* and overwrites the cache entry; losers
     simply return the stale value they already served.
3. **Cold miss** (no cache entry, or age >= ttl + stale_ttl):
   - First worker to win ``cache.add(lock_key)`` runs *producer*
     synchronously and stores the result.
   - Concurrent losers (lock held by another worker, no stale value)
     receive *default*.
"""

from __future__ import annotations

import logging
import pickle
import time
from collections.abc import Callable
from typing import Any, Final

from django.core.cache import cache

logger = logging.getLogger(__name__)

# Suffix appended to the cache key to form the distributed single-flight lock.
_CACHE_LOCK_SUFFIX: Final[str] = ":lock"


class _CacheEntry:
    """Cache entry carrying the value and its storage timestamp.

    Stored as a plain ``dict`` so it is compatible with every Django cache
    backend (LocMemCache serializes via pickle, RedisCache via pickle — the
    ``stored_at`` float round-trips safely).
    """

    __slots__ = ("value", "stored_at")

    def __init__(self, value: Any, stored_at: float) -> None:
        self.value = value
        self.stored_at = stored_at

    def as_dict(self) -> dict[str, Any]:
        """Return a plain dict suitable for cache serialization."""
        return {"value": self.value, "stored_at": self.stored_at}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> _CacheEntry:
        """Reconstruct from the stored dict."""
        return cls(value=data["value"], stored_at=data["stored_at"])


def get_with_stale_revalidate(
    key: str,
    producer: Callable[[], Any],
    *,
    ttl: int,
    stale_ttl: int,
    lock_ttl: int,
    default: Any = None,
    max_size_bytes: int | None = None,
) -> Any:
    """Return the value for *key*, serving stale-while-revalidating.

    Args:
        key: Cache key for the value.
        producer: Callable that recomputes the value on miss/stale-win.
        ttl: Primary TTL in seconds (fresh lifetime).
        stale_ttl: Additional stale-serve window after TTL expiry.
        lock_ttl: Distributed lock TTL in seconds. Must be < stale_ttl so a
            crashed worker releases the lock before stale data expires.
        default: Value returned on a cold miss when the lock is held by
            another worker (no stale value to serve). Callers should fall
            back to a direct computation in this case.
        max_size_bytes: If set, values whose pickled size exceeds this limit
            are returned but not cached (memory-protection).

    Returns:
        The cached value (fresh or stale), the recomputed value, or *default*
        if the lock is held and no stale value exists.
    """
    lock_key = f"{key}{_CACHE_LOCK_SUFFIX}"
    entry_data = cache.get(key)

    if entry_data is not None:
        entry = _CacheEntry.from_dict(entry_data)
        age = time.time() - entry.stored_at

        if age < ttl:
            # Fresh hit — serve immediately, no revalidation needed.
            return entry.value

        if age < ttl + stale_ttl:
            # Stale but within the stale-serve window.
            # Single winner recomputes; everyone serves the stale value.
            if cache.add(lock_key, "1", lock_ttl):
                _recompute_and_store(key, producer, ttl, stale_ttl, max_size_bytes)
            return entry.value

        # Past the stale window — treat as a cold miss (force recompute).
        # Falls through to _cold_miss_with_lock below.

    # Cold miss: no entry, or entry expired beyond stale window.
    return _cold_miss_with_lock(key, lock_key, producer, lock_ttl, ttl, stale_ttl, default, max_size_bytes)


def _cold_miss_with_lock(
    key: str,
    lock_key: str,
    producer: Callable[[], Any],
    lock_ttl: int,
    ttl: int,
    stale_ttl: int,
    default: Any,
    max_size_bytes: int | None,
) -> Any:
    """Handle a cold cache miss with single-flight coordination.

    The first worker to acquire ``cache.add(lock_key)`` runs *producer*
    synchronously and stores the result. Concurrent losers (lock held)
    receive *default* — they should fall back to their own direct
    computation so a single slow recompute never blocks all readers.
    """
    if cache.add(lock_key, "1", lock_ttl):
        # Winner: recompute synchronously — the caller needs a result.
        value = producer()
        _store(key, value, ttl, stale_ttl, max_size_bytes)
        cache.delete(lock_key)  # release lock early
        return value

    # Lock held by another worker — no stale value, return fallback.
    logger.debug(
        "Cold miss for %s while lock held by another worker; returning default",
        key,
    )
    return default


def _recompute_and_store(
    key: str,
    producer: Callable[[], Any],
    ttl: int,
    stale_ttl: int,
    max_size_bytes: int | None,
) -> None:
    """Winner recomputes the value and stores it (best-effort).

    Called from the stale-hit path: the stale value has already been
    returned to *losing* workers; the winning worker recomputes ``producer()``
    SYNCHRONOUSLY (blocking its own response) and overwrites the cache entry.
    Any exception is caught so the lock is still released.
    """
    lock_key = f"{key}{_CACHE_LOCK_SUFFIX}"
    try:
        value = producer()
        _store(key, value, ttl, stale_ttl, max_size_bytes)
    except Exception:
        logger.warning("SWR recompute failed for %s", key, exc_info=True)
    finally:
        cache.delete(lock_key)


def _store(
    key: str,
    value: Any,
    ttl: int,
    stale_ttl: int,
    max_size_bytes: int | None,
) -> None:
    """Store *value* under *key* with age-tracking for stale-serve.

    If *max_size_bytes* is set and the pickled value exceeds it, the value
    is dropped (returned to the caller but not persisted) to prevent cache
    memory bloat from oversized responses.
    """
    if max_size_bytes is not None:
        try:
            size = len(pickle.dumps(value))
        except Exception:
            size = 0
        if size > max_size_bytes:
            logger.warning(
                "Refusing to cache %s: serialized size %d bytes exceeds limit %d",
                key,
                size,
                max_size_bytes,
            )
            return

    entry = _CacheEntry(value, time.time()).as_dict()
    cache.set(key, entry, timeout=ttl + stale_ttl)


def invalidate_by_prefix(prefix: str) -> None:
    """Invalidate all cache entries whose key starts with *prefix*.

    Uses ``cache.delete_pattern`` (Redis-only) when available; falls back
    to a no-op on LocMemCache. Callers should not rely on this in tests —
    the autouse ``_clear_cache_between_tests`` fixture handles isolation.
    """
    if hasattr(cache, "delete_pattern"):
        cache.delete_pattern(f"{prefix}*")  # type: ignore[attr-defined]
        logger.debug("Invalidated cache entries matching %s*", prefix)
    else:
        logger.debug(
            "delete_pattern not available (LocMemCache); "
            "skipping pattern invalidation for %s*", prefix,
        )
