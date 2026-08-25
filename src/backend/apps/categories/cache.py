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

logger = logging.getLogger(__name__)

# Cache key tracking the current category tree version (bumped on structural
# Category / CategoryPath changes so cached submenu fragments are invalidated).
TREE_VERSION_KEY = "category:tree_version"
# Submenu fragment cache TTL (seconds).
SUBMENU_CACHE_TTL = 300


def get_tree_version() -> int:
    """Return the current category tree version (0 when never bumped)."""
    return int(cache.get(TREE_VERSION_KEY, 0) or 0)


def bump_tree_version() -> None:
    """Increment the category tree version to invalidate submenu fragments.

    Uses ``cache.incr`` (atomic on Redis); falls back to a plain set when the
    key does not exist yet (e.g. first change in a fresh backend).
    """
    try:
        cache.incr(TREE_VERSION_KEY)
    except ValueError:
        cache.set(TREE_VERSION_KEY, 1)
        logger.debug("Initialized category tree version to 1")
