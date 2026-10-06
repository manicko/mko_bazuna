"""
One shared fuzzy ladder for every category-resolution call site (10-CQ-011).

The listings did-you-mean and the search fuzzy-category matcher both resolve a
raw query against a list of category strings, but previously each carried its
own copy of the ladder and its own cutoff. This module holds the single ladder
and the single named cutoff so the two sites cannot drift again.

The candidate list is **injected** by the caller: this module imports no other
app (stdlib only) and therefore introduces no ``ads -> search`` dependency edge.
The listings view passes category slugs; the search view passes localized
category names from ``apps.search.services.category_fuzzy``.
"""

from __future__ import annotations

from difflib import get_close_matches
from typing import Final

# Unified category fuzzy-match cutoff. The Product Owner ruled 0.8 for
# category matching (Q6, 2026-10-03); the former listings-only 0.6 is retired.
CATEGORY_FUZZY_CUTOFF: Final[float] = 0.8


def match_category(query: str, candidates: list[str]) -> str | None:
    """Return the exact (case-insensitive) or closest candidate for *query*.

    Tier 1: a candidate equal to *query* ignoring case (the search view's
    exact-name tier; also aligned onto the listings slug list).
    Tier 2: the single closest candidate at :data:`CATEGORY_FUZZY_CUTOFF`.

    Args:
        query: The raw query string (a slug or a localized category name).
        candidates: The caller's candidate list -- category slugs for the
            listings did-you-mean, localized names for the search ladder.

    Returns:
        The matching candidate string, or ``None`` when neither tier matches.
    """
    target = query.casefold()
    for candidate in candidates:
        if candidate.casefold() == target:
            return candidate
    matches = get_close_matches(query, candidates, n=1, cutoff=CATEGORY_FUZZY_CUTOFF)
    return matches[0] if matches else None
