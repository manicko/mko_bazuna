"""
Entity suggestions service for Mko Bazuna.

Provides prefix-based autocomplete for category and city entities
used in the search bar dropdown.
"""

import logging

from django.db.models import F, TextField
from django.db.models.fields.json import KeyTextTransform
from django.db.models.functions import Coalesce

from apps.categories.models import Category
from apps.core.enums import LanguageLocale, SearchSuggestionSource
from apps.locations.models import City
from apps.search.schemas import AutocompleteSuggestion

logger = logging.getLogger(__name__)


def _category_path(category: Category, locale: str = LanguageLocale.RUSSIAN) -> str:
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
    prefix: str, limit: int = 5, locale: str = LanguageLocale.RUSSIAN
) -> list[AutocompleteSuggestion]:
    """
    Get matching category and city names for autocomplete.

    Queries Category (with ``is_active=True`` filter) and City
    (no ``is_active`` filter) using case-insensitive prefix matching.
    Results are limited by the ``limit`` parameter per entity type.
    Matching is performed against the locale-aware name
    (``name_i18n[locale] → name_i18n["ru"] → name``) so that prefixes
    in the user's language are honored.  Display names are localized
    via ``get_name(locale)``.

    Args:
        prefix: The beginning of a name to match (case-insensitive).
        limit: Maximum number of suggestions per entity type (default 5).
        locale: Language code for localized names (e.g. "ru", "bs", "en").

    Returns:
        A combined list of ``AutocompleteSuggestion`` objects.
    """
    normalized = prefix.strip()
    if not normalized:
        return []

    match_name = Coalesce(
        KeyTextTransform(locale, F("name_i18n")),
        KeyTextTransform("ru", F("name_i18n")),
        F("name"),
        output_field=TextField(),
    )

    # Category suggestions with is_active filter — prefix match (istartswith)
    # on the locale-aware name (locale → ru → base name fallback chain).
    categories = (
        Category.objects.annotate(_match_name=match_name)
        .filter(_match_name__istartswith=normalized, is_active=True)
        .order_by("name")[:limit]
    )

    # City suggestions without is_active filter (field doesn't exist) — prefix
    # match on the same locale-aware name fallback chain.
    cities = (
        City.objects.annotate(_match_name=match_name)
        .filter(_match_name__istartswith=normalized)
        .order_by("name")[:limit]
    )

    suggestions: list[AutocompleteSuggestion] = [
        AutocompleteSuggestion(
            text=cat.get_name(locale),
            source=SearchSuggestionSource.CATEGORY,
            type=SearchSuggestionSource.CATEGORY,
            slug=cat.slug,
            category_path=_category_path(cat, locale),
        )
        for cat in categories
    ]

    suggestions.extend(
        AutocompleteSuggestion(
            text=city.get_name(locale),
            source=SearchSuggestionSource.CITY,
            type=SearchSuggestionSource.CITY,
            slug=city.slug,
        )
        for city in cities
    )

    return suggestions
