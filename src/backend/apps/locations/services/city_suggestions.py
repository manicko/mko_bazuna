"""
City slug suggestion service for Mko Bazuna.

Provides fuzzy-matching of invalid city slugs to the closest valid slug,
used by the "Did you mean:" banner when a ``?city=<invalid_slug>`` parameter
is passed to the search or listings views.
"""

import logging
from difflib import get_close_matches
from typing import Final

from apps.locations.models import City

logger = logging.getLogger(__name__)

# difflib similarity cutoff — values below this are not considered matches.
_CUTOFF: Final[float] = 0.6


def suggest_city(slug: str) -> str | None:
    """Suggest a similar city slug using difflib fuzzy matching.

    When a buyer visits ``/search/?city=budav`` (a typo of ``budva``), this
    function finds the closest valid city slug using ``difflib.get_close_matches``
    and returns it for the "Did you mean:" banner.

    Args:
        slug: The invalid city slug to find a suggestion for.

    Returns:
        The closest matching city slug, or ``None`` if no close match exists.
    """
    all_slugs = list(City.objects.values_list("slug", flat=True))
    matches = get_close_matches(slug, all_slugs, n=1, cutoff=_CUTOFF)
    return matches[0] if matches else None
