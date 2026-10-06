"""
City slug suggestion service for Mko Bazuna.

Provides fuzzy-matching of invalid city slugs to the closest valid slug,
used by the "Did you mean:" banner when a ``?city=<invalid_slug>`` parameter
is passed to the search or listings views.
"""

import logging

from apps.locations.models import City
from apps.locations.services.city_fuzzy import match_city

logger = logging.getLogger(__name__)


def suggest_city(slug: str) -> str | None:
    """Suggest a similar city slug using fuzzy matching.

    When a buyer visits ``/search/?city=budav`` (a typo of ``budva``), this
    function finds the closest valid city slug using the shared city fuzzy
    ladder and returns it for the "Did you mean:" banner.

    Args:
        slug: The invalid city slug to find a suggestion for.

    Returns:
        The closest matching city slug, or ``None`` if no close match exists.
    """
    all_slugs = list(City.objects.values_list("slug", flat=True))
    return match_city(slug, all_slugs, n=1)
