"""
Fragment-cache helpers for the category submenu endpoint.

A monotonically increasing *tree version* is used so that category submenu
fragments keyed by ``category:submenu:<tree_version>:<slug>:<locale>`` are invalidated
whenever the category tree changes structurally. The ``<locale>`` segment prevents
cross-language cache bleed (a Russian-rendered submenu must not be served to a
Bosnian visitor). This works uniformly on both the LocMemCache (dev/test) and
Redis (production) backends without relying on backend-specific ``delete_pattern``
support.
"""

import logging

from django.core.cache import cache

from apps.core.utils.cache import bump_version_key

logger = logging.getLogger(__name__)

# Cache key tracking the current category tree version (bumped on structural
# Category / CategoryPath changes so cached submenu fragments are invalidated).
TREE_VERSION_KEY = "category:tree_version"
# Submenu fragment cache TTL (seconds).
SUBMENU_CACHE_TTL = 300
# Stale-while-revalidate parameters (seconds). Mirrors the proven
# search/lookup/resolve tiers: lock TTL < stale TTL (SWR invariant).
SUBMENU_CACHE_STALE_TTL = 60
SUBMENU_CACHE_LOCK_TTL = 30


def get_tree_version() -> int:
    """Return the current category tree version (0 when never bumped)."""
    return int(cache.get(TREE_VERSION_KEY, 0) or 0)


def bump_tree_version() -> None:
    """Increment the category tree version to invalidate submenu fragments.

    Delegates to :func:`apps.core.utils.cache.bump_version_key`, which owns the
    durability contract: the version key is written with ``timeout=None`` so it
    outlives the submenu fragments it retires. A bounded TTL would let the
    counter self-evict and re-issue ``1``, making a retired fragment key
    reachable again with stale content.
    """
    bump_version_key(TREE_VERSION_KEY)
    logger.debug("Bumped category tree version")
