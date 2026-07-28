"""
Autocomplete view for Mko Bazuna.

Combines suggestions from user search history, entity matching (categories
and cities), and popular searches into a single deduplicated JSON response.
"""

import logging
from typing import Any

from django.http import HttpRequest, JsonResponse

from apps.core.enums import SearchSuggestionSource
from apps.core.utils.sanitize import sanitize_autocomplete_query
from apps.search.services.entity_suggestions import get_entity_suggestions
from apps.search.services.popular_search import get_popular_suggestions
from apps.search.services.rate_limit import rate_limit_check
from apps.search.services.search_history import get_user_search_history

logger = logging.getLogger(__name__)

# Maximum number of suggestions in the final merged response.
_MAX_SUGGESTIONS: int = 10


def autocomplete(request: HttpRequest) -> JsonResponse:
    """
    Return JSON suggestions for the autocomplete dropdown.

    Accepts a ``GET`` request with a ``q`` parameter containing the
    user's typed prefix.  Suggestions are merged from three sources:

    1. **User history** — recent queries by the authenticated user.
    2. **Entity suggestions** — matching category and city names.
    3. **Popular searches** — frequently searched queries.

    Results are deduplicated by the ``"text"`` field, limited to
    ``_MAX_SUGGESTIONS`` items, and returned in a ``JsonResponse``.

    If the query fails sanitisation (empty, too short, too long, or
    contains disallowed characters), an empty suggestions list is
    returned with an HTTP 200 status.

    If the client exceeds the rate limit, an HTTP 429 response with
    ``{"error": "rate_limit"}`` is returned.

    Args:
        request: The incoming HTTP request.

    Returns:
        A ``JsonResponse`` containing the merged suggestions.
    """
    query = sanitize_autocomplete_query(request.GET.get("q", ""))
    if not query:
        return JsonResponse({"suggestions": [], "query": ""})

    if not rate_limit_check(request):
        return JsonResponse({"error": "rate_limit"}, status=429)

    suggestions: list[dict[str, Any]] = []

    # 1. User search history (highest priority, shown first).
    user_id = request.user.id if request.user.is_authenticated else None
    user_history = get_user_search_history(user_id)
    for item in user_history:
        suggestions.append({
            "text": item,
            "source": SearchSuggestionSource.USER_HISTORY.value,
        })

    # 2. Entity suggestions (categories + cities).
    entity_suggestions = get_entity_suggestions(query)
    suggestions.extend(entity_suggestions)

    # 3. Popular suggestions.
    popular = get_popular_suggestions(query)
    suggestions.extend(popular)

    # Deduplicate by "text" field, preserving insertion order.
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for item in suggestions:
        text = item.get("text", "")
        if text and text not in seen:
            seen.add(text)
            unique.append(item)

    return JsonResponse({
        "suggestions": unique[:_MAX_SUGGESTIONS],
        "query": query,
    })