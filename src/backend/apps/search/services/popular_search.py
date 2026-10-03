"""
Popular search service for Mko Bazuna.

Tracks popular search queries atomically and provides prefix-based
autocomplete suggestions filtered by minimum hit count.
"""

import logging
from typing import Final

from django.db.models import F

from apps.core.enums import SearchSuggestionSource
from apps.core.utils.sanitize import redact_search_query, search_query_key
from apps.search.models import PopularSearch
from apps.search.schemas import AutocompleteSuggestion

logger = logging.getLogger(__name__)

# Minimum hit count threshold for a query to appear in popular suggestions.
_MIN_HIT_COUNT: Final[int] = 10


def increment_popular_search(query: str) -> None:
    """
    Atomically increment the hit count for a normalized search query.

    Derives the key from the REDACTED query (redact first, then strip and
    lower), so raw PII never survives in the global cross-user
    ``query_normalized`` column (SRH-004, 06-PII-108).  Uses ``get_or_create``
    for the initial insert and an ``F()`` expression for a race-safe increment
    on subsequent calls.

    Args:
        query: The raw search query string.
    """
    key = search_query_key(query)
    if not key:
        return

    # Redact PII (phones, emails, names) before persisting (SRH-004).
    # ``query_normalized`` is the lookup/dedup key derived from the redaction,
    # so redaction does not affect matching or autocomplete suggestions.
    redacted = redact_search_query(query)

    obj, created = PopularSearch.objects.get_or_create(
        query_normalized=key,
        defaults={"query": redacted, "hit_count": 1},
    )
    if not created:
        PopularSearch.objects.filter(pk=obj.pk).update(
            hit_count=F("hit_count") + 1,
            query=redacted,
        )


def get_popular_suggestions(prefix: str, limit: int = 5) -> list[AutocompleteSuggestion]:
    """
    Return the most popular completed queries matching ``prefix``.

    Queries are matched against the *normalized* form (case-insensitive).
    Only queries whose ``hit_count`` is at least ``MIN_HIT_COUNT`` are
    returned, ordered by popularity descending and capped by ``limit``.

    Args:
        prefix: The beginning of a query string to match.
        limit: Maximum number of suggestions to return (default 5).

    Returns:
        A list of ``AutocompleteSuggestion`` objects.
    """
    normalized_prefix = prefix.strip().lower()
    if not normalized_prefix:
        return []

    qs = PopularSearch.objects.filter(
        query_normalized__startswith=normalized_prefix,
        hit_count__gte=_MIN_HIT_COUNT,
    ).order_by("-hit_count")[:limit]

    return [
        AutocompleteSuggestion(
            text=obj.query,
            source=SearchSuggestionSource.POPULAR_SEARCH,
            type=SearchSuggestionSource.POPULAR_SEARCH,
            hit_count=obj.hit_count,
        )
        for obj in qs
    ]
