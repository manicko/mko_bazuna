"""
Search result caching with stale-while-revalidate (SWR) and single-flight.

Caches PostgreSQL FTS search result ad IDs to prevent cache stampedes
(thundering-herd) when popular queries are requested concurrently by
multiple gunicorn workers + the bot process.  Uses ``cache.add`` as a
distributed lock for single-flight coordination, reusing the pattern from
``apps.users.services.login_rate_limit``.

Cache key encodes: search query (hashed), filters (category, city, price
range, purpose, condition, features, sort, per_page), and locale — ensuring
different search combinations never collide.

TTL: 300 s fresh + 60 s stale window + 30 s lock.

Works on both Redis (production — true cross-process single-flight) and
LocMemCache (dev/test — stale-serve path is exercised by the unit tests).
"""

from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import Callable
from enum import StrEnum
from typing import Final

from django.core.cache import cache

from apps.ads.services.listings_query import ListingsQueryParams
from apps.core.enums import LanguageLocale
from apps.core.utils.swr_cache import get_with_stale_revalidate

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# TTL configuration (seconds).
# Stale-while-revalidate: 5 min fresh + 1 min stale + 30 s lock.
# The lock TTL (30 s) is deliberately shorter than the stale window (60 s)
# so that a crashed / slow worker releases the lock before stale data
# expires, preventing permanent lock starvation.
# ---------------------------------------------------------------------------
SEARCH_CACHE_TTL: Final[int] = 300
SEARCH_CACHE_STALE_TTL: Final[int] = 60
SEARCH_CACHE_LOCK_TTL: Final[int] = 30

# Maximum ad IDs cached per search result (prevents memory bloat for
# queries that match thousands of published ads).
SEARCH_CACHE_MAX_HITS: Final[int] = 1000

# Maximum serialized size of a cached entry (bytes).  Values whose pickled
# representation exceeds this limit are returned to the caller but not
# persisted — a safety net against unexpected response bloat.
SEARCH_CACHE_MAX_ENTRY_BYTES: Final[int] = 512 * 1024


class SearchCacheKey(StrEnum):
    """Versioned namespace prefix for search result cache keys.

    Bump the version (e.g. to ``search:v2``) when the cache entry format
    changes to avoid stale-entry deserialization errors.
    """

    V1 = "search:v1"


# Separately tracked content-freshness token.  Bumped whenever a buyer-visible
# ad changes (status transition, content edit, feature M2M change) so that every
# cache key built by ``build_search_cache_key`` embeds a new version segment.
# Old entries become unreachable on the next read and expire via TTL — no global
# prefix wipe (thundering-herd risk) is needed.
SEARCH_CONTENT_VERSION_KEY = "search:content_version"


def get_search_version() -> int:
    """Return the current search content version (0 when never bumped).

    Mirrors the ``get_tree_version`` pattern from ``apps.categories.cache``.
    """
    return int(cache.get(SEARCH_CONTENT_VERSION_KEY, 0) or 0)


def bump_search_version() -> None:
    """Increment the search content version to invalidate cached search results.

    Uses ``cache.incr`` (atomic on Redis, thread-safe on LocMemCache); falls
    back to a plain ``cache.set`` when the key does not exist yet.

    Mirrors the ``bump_tree_version`` pattern from ``apps.categories.cache``.
    """
    try:
        cache.incr(SEARCH_CONTENT_VERSION_KEY)
    except ValueError:
        cache.set(SEARCH_CONTENT_VERSION_KEY, 1)
        logger.debug("Initialized search content version to 1")


def build_search_cache_key(
    params: ListingsQueryParams,
    query: str,
    locale: LanguageLocale,
) -> str:
    """Build a cache key encoding all search-varying parameters.

    Key structure: ``search:v1:{content_version}:{locale}:{query_hash}:{filters_hash}``

    The content version (a monotonically incremented counter from
    :func:`get_search_version`) ensures that any ad change that could affect
    the buyer-visible result set produces a new key, making old entries
    unreachable without a global prefix wipe.

    The query string is SHA-256 hashed (16 hex chars) to avoid excessively
    long keys for lengthy queries.  Filters (category, city, price, purpose,
    condition, features, sort, per_page) are JSON-serialized with sorted
    keys for deterministic hashing.  The locale ensures per-language vector
    queries never collide.

    Note: ``page`` is intentionally excluded — the cache stores the complete
    ordered result set (up to ``SEARCH_CACHE_MAX_HITS``).  Pagination is
    handled by Django's ``Paginator`` on the re-fetched queryset, so the same
    cache entry serves all pages of a given search.
    """
    query_hash = hashlib.sha256(query.strip().lower().encode("utf-8")).hexdigest()[:16]

    filters = {
        "cat": params.category_slug,
        "city": params.city_slug,
        "min": params.min_price,
        "max": params.max_price,
        "pur": params.purpose_slug,
        "cond": params.condition_slug,
        "feat": ",".join(sorted(params.feature_slugs)),
        "sort": params.sort.value,
        "per_page": params.per_page,
    }
    filters_hash = hashlib.sha256(
        json.dumps(filters, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()[:16]

    return f"{SearchCacheKey.V1}:{get_search_version()}:{locale.value}:{query_hash}:{filters_hash}"


def get_cached_search_ids(
    cache_key: str,
    producer: Callable[[], list[int]],
) -> list[int] | None:
    """Return cached search result IDs, running *producer* on miss/stale.

    States and return values:

    - **Fresh/stale cache hit**: return cached IDs (stale value is refreshed
      in the background by the single-flight winner).
    - **Cold miss (winner)**: run *producer*, cache the result, return IDs.
    - **Cold miss (loser, lock held by another worker)**: return ``None``
      so the caller can fall back to a direct FTS query.

    Args:
        cache_key: The cache key (from :func:`build_search_cache_key`).
        producer: Callable that executes the FTS search and returns
            an ordered list of ad IDs.  Called only on cache miss or
            when the current worker wins the single-flight lock.

    Returns:
        Ordered list of ad IDs, or ``None`` if cold miss and the lock is
        held by another worker (caller should fall back to direct execution).
    """
    result = get_with_stale_revalidate(
        cache_key,
        producer,
        ttl=SEARCH_CACHE_TTL,
        stale_ttl=SEARCH_CACHE_STALE_TTL,
        lock_ttl=SEARCH_CACHE_LOCK_TTL,
        default=None,
        max_size_bytes=SEARCH_CACHE_MAX_ENTRY_BYTES,
    )
    if result is None:
        logger.debug("Cold miss / lock held for search cache key %s", cache_key)
    return result


def bump_search_cache_version() -> None:
    """Bump the content-freshness version to invalidate all search cache entries.

    Called when an ad transitions to/from PUBLISHED / ARCHIVED / DELETED or when
    any search-relevant content field changes.  Instead of a global prefix wipe
    (which causes a thundering-herd), this increments a version counter embedded
    in every cache key — old entries become unreachable and expire via TTL.
    """
    bump_search_version()


def invalidate_search_cache() -> None:
    """Deprecated alias for :func:`bump_search_cache_version`.

    Kept for backward compatibility with any external callers still importing
    the old name.  Delegates to the version-bump mechanism.
    """
    bump_search_cache_version()
