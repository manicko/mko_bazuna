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


def get_entity_suggestions(prefix: str, limit: int = 5) -> list[dict]:
    """
    Get matching category and city names for autocomplete.

    Queries Category (with ``is_active=True`` filter) and City
    (no ``is_active`` filter) using case-insensitive prefix matching.
    Results are limited by the ``limit`` parameter per entity type.

    Args:
        prefix: The beginning of a name to match (case-insensitive).
        limit: Maximum number of suggestions per entity type (default 5).

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
            "text": cat.name,
            "source": SearchSuggestionSource.CATEGORY.value,
            "type": "category",
        }
        for cat in categories
    ]

    suggestions.extend(
        {
            "text": city.name,
            "source": SearchSuggestionSource.CITY.value,
            "type": "city",
        }
        for city in cities
    )

    return suggestions