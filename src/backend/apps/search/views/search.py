"""
Search view for Mko Bazuna.

FTS search on search_vector with Bosnian->Russian translation.
One-word queries trigger fuzzy category detection.
"""

import logging
import re

from apps.ads.models import Ad
from apps.analytics.models import AnalyticsEvent
from apps.categories.models import Category
from apps.core.enums import AdStatus, AnalyticsEventType
from apps.search.services.query_translator import translate_query_bs_to_ru
from django.contrib.postgres.search import SearchQuery, SearchRank
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render

logger = logging.getLogger(__name__)


def search(request: HttpRequest) -> HttpResponse:
    """
    Search view using PostgreSQL FTS on search_vector.

    Features:
        - Bosnian query translated to Russian before search
        - One-word queries apply fuzzy category detection
        - GIN index used for search_vector (Task 5)
        - Records SEARCH_PERFORMED analytics event

    Args:
        request: HTTP request with 'q' query parameter

    Returns:
        Rendered search results page
    """
    query = (request.GET.get("q") or "").strip()
    ads = Ad.objects.filter(status=AdStatus.PUBLISHED).select_related("category", "city")

    if query:
        # Record search event (analytics)
        AnalyticsEvent.objects.create(
            event_type=AnalyticsEventType.SEARCH_PERFORMED,
            user_id=request.user.id if request.user.is_authenticated else None,
        )

        # Translate Bosnian query to Russian
        translated_query = translate_query_bs_to_ru(query)

        # One-word queries: apply fuzzy category detection
        if _is_single_word(query):
            category_filter = _fuzzy_category_match(translated_query)
            if category_filter:
                ads = ads.filter(category=category_filter)

        # FTS search on search_vector
        search_query = SearchQuery(translated_query, search_type="websearch", config="russian")
        ads = ads.annotate(
            rank=SearchRank("search_vector", search_query)
        ).filter(search_vector=search_query).order_by("-rank")

    has_results = ads.exists() if query else False
    if query and not has_results:
        logger.info(f"Empty search results for query '{query}'")

    context = {
        "ads": ads,
        "query": query,
        "has_results": has_results,
    }

    # HTMX partial rendering support
    if request.headers.get("HX-Request"):
        return render(request, "ads/list.html", context)

    return render(request, "ads/list.html", context)


def _is_single_word(text: str) -> bool:
    """
    Check if text is a single word.

    Args:
        text: The text to check

    Returns:
        True if text contains only one word
    """
    if not text:
        return False
    # Split on whitespace and check
    words = re.split(r"\s+", text.strip())
    return len(words) == 1


def _fuzzy_category_match(query: str) -> Category | None:
    """
    Find category matching the query using fuzzy string matching.

    Args:
        query: The single-word search query

    Returns:
        Matching Category or None
    """
    # Try exact match first
    try:
        return Category.objects.get(name__iexact=query, is_active=True)
    except Category.DoesNotExist:
        pass

    # Try slug match
    try:
        return Category.objects.get(slug__iexact=query, is_active=True)
    except Category.DoesNotExist:
        pass

    # Fuzzy match on name
    from difflib import get_close_matches

    all_names = list(
        Category.objects.filter(is_active=True).values_list("name", flat=True)
    )
    matches = get_close_matches(query, all_names, n=1, cutoff=0.8)
    if matches:
        try:
            return Category.objects.get(name__iexact=matches[0], is_active=True)
        except Category.DoesNotExist:
            pass

    return None
