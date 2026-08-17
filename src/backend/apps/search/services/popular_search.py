"""
Popular search service for Mko Bazuna.

Tracks popular search queries atomically and provides prefix-based
autocomplete suggestions filtered by minimum hit count.
"""

import logging
from typing import Final

from django.db.models import F

from apps.core.enums import SearchSuggestionSource
from apps.search.models import PopularSearch

logger = logging.getLogger(__name__)

# Minimum hit count threshold for a query to appear in popular suggestions.
_MIN_HIT_COUNT: Final[int] = 10


def increment_popular_search(query: str) -> None:
    """
    Atomically increment the hit count for a normalized search query.

    Strips leading/trailing whitespace and lowercases the query for
    normalization.  Uses ``get_or_create`` for the initial insert and
    an ``F()`` expression for a race-safe increment on subsequent calls.

    Args:
        query: The raw search query string.
    """
    normalized = query.strip().lower()
    if not normalized:
        return

    obj, created = PopularSearch.objects.get_or_create(
        query_normalized=normalized,
        defaults={"query": query, "hit_count": 1},
    )
    if not created:
        PopularSearch.objects.filter(pk=obj.pk).update(
            hit_count=F("hit_count") + 1,
            query=query,
        )


def get_popular_suggestions(prefix: str, limit: int = 5) -> list[dict]:
    """
    Return the most popular completed queries matching ``prefix``.

    Queries are matched against the *normalized* form (case-insensitive).
    Only queries whose ``hit_count`` is at least ``MIN_HIT_COUNT`` are
    returned, ordered by popularity descending and capped by ``limit``.

    Args:
        prefix: The beginning of a query string to match.
        limit: Maximum number of suggestions to return (default 5).

    Returns:
        A list of dicts, each with keys ``text``, ``source``, and
        ``hit_count``.
    """
    normalized_prefix = prefix.strip().lower()
    if not normalized_prefix:
        return []

    qs = PopularSearch.objects.filter(
        query_normalized__startswith=normalized_prefix,
        hit_count__gte=_MIN_HIT_COUNT,
    ).order_by("-hit_count")[:limit]

    return [
        {
            "text": obj.query,
            "source": SearchSuggestionSource.POPULAR_SEARCH.value,
            "hit_count": obj.hit_count,
        }
        for obj in qs
    ]
