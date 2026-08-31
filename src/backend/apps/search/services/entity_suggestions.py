"""
Entity suggestions service for Mko Bazuna.

Provides prefix-based autocomplete for category and city entities
used in the search bar dropdown.
"""

import logging

from apps.categories.models import Category
from apps.core.enums import SearchSuggestionSource
from apps.locations.models import City

logger = logging.getLogger(__name__)


def _category_path(category: Category, locale: str = "ru") -> str:
    """Build a root→leaf, human-readable path for a category suggestion.

    Uses ``get_ancestors(include_self=True)`` (root→leaf order) joined by
    ``" > "``, e.g. ``"Товары > Транспорт"``. Names come from ``get_name`` so
    i18n names are honored when available (falling back to Russian ``name``).

    Args:
        category: The category to build a path for.
        locale: Language code for localized names (e.g. "ru", "bs", "en").

    Returns:
        The joined ancestor+self path string.
    """
    return " > ".join(
        item.get_name(locale) for item in category.get_ancestors(include_self=True)
    )


def get_entity_suggestions(
    prefix: str, limit: int = 5, locale: str = "ru"
) -> list[dict]:
    """
    Get matching category and city names for autocomplete.

    Queries Category (with ``is_active=True`` filter) and City
    (no ``is_active`` filter) using case-insensitive prefix matching.
    Results are limited by the ``limit`` parameter per entity type.
    Category and city names are localized via ``get_name(locale)``.

    Args:
        prefix: The beginning of a name to match (case-insensitive).
        limit: Maximum number of suggestions per entity type (default 5).
        locale: Language code for localized names (e.g. "ru", "bs", "en").

    Returns:
        A combined list of dicts, each with keys ``text``, ``source``,
        and ``type``.
    """
    normalized = prefix.strip()
    if not normalized:
        return []

    # Category suggestions with is_active filter — prefix match (istartswith)
    categories = Category.objects.filter(
        name__istartswith=normalized,
        is_active=True,
    ).order_by("name")[:limit]

    # City suggestions without is_active filter (field doesn't exist) — prefix match
    cities = City.objects.filter(
        name__istartswith=normalized,
    ).order_by("name")[:limit]

    suggestions: list[dict] = [
        {
            "text": cat.get_name(locale),
            "source": SearchSuggestionSource.CATEGORY.value,
            "type": SearchSuggestionSource.CATEGORY.value,
            "slug": cat.slug,
            "category_path": _category_path(cat, locale),
        }
        for cat in categories
    ]

    suggestions.extend(
        {
            "text": city.get_name(locale),
            "source": SearchSuggestionSource.CITY.value,
            "type": SearchSuggestionSource.CITY.value,
            "slug": city.slug,
        }
        for city in cities
    )

    return suggestions
