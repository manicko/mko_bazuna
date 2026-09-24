"""
Cached, locale-aware category name list for fuzzy matching (SRH-005).

The search view's fuzzy category matcher needs the list of active category
names (localized per buyer locale) to run ``difflib.get_close_matches``.
Previously this list was loaded from the database on every fuzzy request,
issuing up to three full ``Category.objects.filter(is_active=True)`` SELECTs
per request. This module caches the active-category name list behind the
existing versioned category-tree cache key, so a warm cache performs zero
category SELECTs on the fuzzy path.

The cache key embeds ``get_tree_version()`` (from ``apps.categories.cache``)
and the locale, mirroring the ``category:submenu:<tree_version>:<slug>:<locale>``
fragment pattern. ``apps/categories/signals.py`` already bumps the tree version
on every ``Category`` post_save / post_delete, so any name / ``name_i18n`` /
``is_active`` change produces a new key and the stale name list becomes
unreachable — no additional signal or explicit cache-clearing code is needed.
"""

from __future__ import annotations

import logging
from typing import Final

from django.core.cache import cache

from apps.categories.cache import SUBMENU_CACHE_TTL, get_tree_version
from apps.categories.models import Category
from apps.core.enums import LanguageLocale

logger = logging.getLogger(__name__)

# Cache TTL (seconds) for the fuzzy category name list. Matches the categories
# app's submenu fragment cache TTL so the two expire on the same cadence.
FUZZY_NAMES_CACHE_TTL: Final[int] = SUBMENU_CACHE_TTL


def _fuzzy_names_cache_key(locale: LanguageLocale) -> str:
    """Build the versioned, locale-aware cache key for the active name list."""
    return f"category:fuzzy_names:{get_tree_version()}:{locale.value}"


def get_active_category_names(locale: LanguageLocale) -> list[dict[str, object]]:
    """Return cached ``{"name", "id"}`` dicts for active categories in *locale*.

    On a cold miss, populates the cache with a single
    ``Category.objects.filter(is_active=True)`` query. On a warm cache,
    performs zero category SELECTs. The cached value is a plain list of dicts
    (not ORM objects) so it serializes cleanly across cache backends.

    Args:
        locale: The locale whose localized category names are wanted.

    Returns:
        A list of ``{"name": <localized-name>, "id": <category-id>}`` dicts
        for every active category.
    """
    cache_key = _fuzzy_names_cache_key(locale)
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    entries = [
        {"name": category.get_name(locale.value), "id": category.id}
        for category in Category.objects.filter(is_active=True)
    ]
    cache.set(cache_key, entries, timeout=FUZZY_NAMES_CACHE_TTL)
    logger.debug(
        "Populated fuzzy category name list for %s (%d entries)",
        locale.value,
        len(entries),
    )
    return entries
