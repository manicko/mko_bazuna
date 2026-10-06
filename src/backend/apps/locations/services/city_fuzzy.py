"""
One shared fuzzy ladder for every city-resolution call site (NF-2).

The web slug suggester (``apps.locations.services.city_suggestions``) and the
Telegram bot city step both resolve a raw query against a list of city strings,
but previously each carried its own copy of the ladder and its own cutoff -- and
the bot site carried a bare ``cutoff=0.6`` literal. This module holds the single
ladder and the single named cutoff so the two sites cannot drift again.

The candidate list is **injected** by the caller: this module imports no other
app (stdlib only) and therefore introduces no new dependency edge. The web
passes city slugs; the bot passes localized city names.
"""

from __future__ import annotations

from difflib import get_close_matches
from typing import Final

# Shared city fuzzy-match cutoff. The Product Owner ruled 0.6 for city
# matching (Q7(b)); both call sites preserve this value.
CITY_FUZZY_CUTOFF: Final[float] = 0.6


def match_city(query: str, candidates: list[str], *, n: int = 1) -> str | None:
    """Return the exact (case-insensitive) or closest candidate for *query*.

    Tier 1: a candidate equal to *query* ignoring case (the web slug exact tier;
    also aligned onto the bot's localized-name list).
    Tier 2: the single closest candidate at :data:`CITY_FUZZY_CUTOFF`.

    Args:
        query: The raw query string (a slug or a localized city name).
        candidates: The caller's candidate list -- city slugs for the web
            suggester, localized names for the bot city step.
        n: How many close matches to compute; only the best is returned. Both
            call sites pass ``n=1``.

    Returns:
        The matching candidate string, or ``None`` when neither tier matches.
    """
    target = query.casefold()
    for candidate in candidates:
        if candidate.casefold() == target:
            return candidate
    matches = get_close_matches(query, candidates, n=n, cutoff=CITY_FUZZY_CUTOFF)
    return matches[0] if matches else None
