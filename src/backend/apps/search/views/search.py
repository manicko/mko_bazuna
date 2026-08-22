"""
Search view for Mko Bazuna.

Language-aware FTS search on per-language search vectors.
The query is searched in the buyer's own language against the matching
vector column — no external translation on the search critical path.
One-word queries trigger fuzzy category detection.
"""

import logging
import re

from apps.ads.models import Ad
from apps.analytics.models import AnalyticsEvent
from apps.categories.models import Category
from apps.core.enums import AdStatus, AdSort, AnalyticsEventType, LanguageLocale
from apps.locations.models import City
from django.contrib.postgres.search import SearchQuery, SearchRank
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.core.paginator import Paginator
from django.db.models import F
from apps.core.utils.sanitize import sanitize_query_for_log
from apps.search.services.popular_search import increment_popular_search
from apps.search.services.search_history import record_search_history

logger = logging.getLogger(__name__)


def search(request: HttpRequest) -> HttpResponse:
    """
    Search view using PostgreSQL FTS on per-language search vectors.

    Features:
        - Resolves the locale from request.LANGUAGE_CODE and searches the
          matching per-language vector without query translation
        - One-word queries apply fuzzy category detection (locale-aware)
        - GIN index used for each per-language search vector
        - Records SEARCH_PERFORMED analytics event
        - Paginated results (24 per page) with HTMX partial support

    Args:
        request: HTTP request with 'q' query parameter

    Returns:
        Rendered search results page (full or HTMX partial)
    """
    PER_PAGE = 24

    query = (request.GET.get("q") or "").strip()
    ads = Ad.objects.filter(status=AdStatus.PUBLISHED).select_related("category", "city")

    # Category filter (by slug) — applies in addition to FTS
    current_category = request.GET.get("category")
    suggested_category = None
    breadcrumb_category = None
    if current_category:
        try:
            category = Category.objects.get(slug=current_category, is_active=True)
            breadcrumb_category = category
            descendant_ids = category.get_descendants(include_self=True).values_list(
                "id", flat=True
            )
            ads = ads.filter(category_id__in=descendant_ids)
        except Category.DoesNotExist:
            suggested_category = current_category

    # City filter (by slug). An explicit ?city= always wins; otherwise the
    # middleware-resolved preferred city is the *default* filter (R-05).
    explicit_city = request.GET.get("city")
    current_city = explicit_city or getattr(request, "preferred_city", None)
    suggested_city = None
    if current_city:
        try:
            city = City.objects.get(slug=current_city)
            ads = ads.filter(city_id=city.id)
        except City.DoesNotExist:
            suggested_city = current_city

    # Price range filter (EUR-equivalent values, CR-10)
    min_price = request.GET.get("min_price")
    max_price = request.GET.get("max_price")
    if min_price:
        try:
            ads = ads.filter(price_normalized_eur__gte=int(min_price))
        except ValueError:
            pass
    if max_price:
        try:
            ads = ads.filter(price_normalized_eur__lte=int(max_price))
        except ValueError:
            pass

    # Resolve the current city/category filters to object ids so the
    # save-search modal can prefill its selects (FT-002).
    selected_city_id: int | None = None
    if current_city:
        try:
            selected_city_id = City.objects.get(slug=current_city).id
        except City.DoesNotExist:
            selected_city_id = None

    selected_category_id: int | None = (
        breadcrumb_category.id if breadcrumb_category else None
    )

    # Sort (parsed for context + pagination URL preservation; FTS branch keeps -rank)
    current_sort = request.GET.get("sort", AdSort.DATE_NEW)

    if query:
        # Resolve locale from the request's UI language preference. The query is
        # searched in its original language against the matching vector column;
        # no external translator runs on the search critical path.
        locale = LanguageLocale.from_code(request.LANGUAGE_CODE)
        vector_field = locale.fts_vector_field
        config = locale.fts_config

        # One-word queries: apply fuzzy category detection (locale-aware)
        if _is_single_word(query):
            category_filter = _fuzzy_category_match(query, locale)
            if category_filter:
                # Expand to category subtree (consistent with listings.py)
                descendant_ids = category_filter.get_descendants(include_self=True).values_list(
                    "id", flat=True
                )
                ads = ads.filter(category_id__in=descendant_ids)

        # FTS search on the locale's per-language vector
        search_query = SearchQuery(query, search_type="websearch", config=config)
        ads = ads.annotate(
            rank=SearchRank(F(vector_field), search_query)
        ).filter(**{vector_field: search_query}).order_by("-rank")

        # Record search event (analytics) after successful execution
        AnalyticsEvent.objects.create(
            event_type=AnalyticsEventType.SEARCH_PERFORMED,
            user_id=request.user.id if request.user.is_authenticated else None,
        )

        # Record popular search and user history for autocomplete.
        # Anonymous users get session-scoped, deduped, capped history.
        increment_popular_search(query)
        record_search_history(
            request.user.id if request.user.is_authenticated else None,
            query,
            session=request.session,
        )
    else:
        # No FTS query: apply the requested sort ordering so buyers can
        # browse by date or price even on an unfiltered /search/ page.
        if current_sort == AdSort.DATE_OLD:
            ads = ads.order_by("published_at")
        elif current_sort == AdSort.PRICE_LOW:
            ads = ads.order_by("price_normalized_eur")
        elif current_sort == AdSort.PRICE_HIGH:
            ads = ads.order_by("-price_normalized_eur")
        else:  # DATE_NEW — default, newest first
            ads = ads.order_by("-published_at")

    # Paginate results
    from apps.ads.views.favorite import annotate_favorites

    ads = annotate_favorites(ads, request.user.id if request.user.is_authenticated else None)
    paginator = Paginator(ads, PER_PAGE)
    page_number = request.GET.get("page", 1)
    page_obj = paginator.get_page(page_number)

    total_count = int(paginator.count)
    has_results = total_count > 0
    if query and not has_results:
        logger.info("Empty search results for query '%s'", sanitize_query_for_log(query))

    context = {
        "page_obj": page_obj,
        "query": query,
        "has_results": has_results,
        "current_category": current_category,
        "current_city": current_city,
        "current_sort": current_sort,
        "min_price": min_price,
        "max_price": max_price,
        "suggested_category": suggested_category,
        "suggested_city": suggested_city,
        "breadcrumb_category": breadcrumb_category,
        # Save-search modal context (FT-002)
        "cities": City.objects.order_by("name"),
        "categories": Category.objects.filter(is_active=True).order_by("name"),
        "selected_city": selected_city_id,
        "selected_category": selected_category_id,
    }

    # HTMX partial rendering support
    if request.headers.get("HX-Request"):
        return render(request, "ads/partials/ad_list.html", context)

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


def _fuzzy_category_match(query: str, locale: LanguageLocale) -> Category | None:
    """
    Find category matching the query using the locale-appropriate name.

    Matches against ``Category.get_name(locale)`` so single-word queries find
    the category in the buyer's own language.

    Args:
        query: The single-word search query
        locale: The active search locale

    Returns:
        Matching Category or None
    """
    # Try slug match first (slug is unique so first() is safe)
    by_slug = Category.objects.filter(slug__iexact=query, is_active=True).first()
    if by_slug:
        return by_slug
    # Exact match against the locale-appropriate display name (case-insensitive)
    for category in Category.objects.filter(is_active=True):
        if category.get_name(locale.value).lower() == query.lower():
            return category
    return _fuzzy_match_by_name(query, locale)


def _fuzzy_match_by_name(query: str, locale: LanguageLocale) -> Category | None:
    """Find the closest category name match using difflib fuzzy matching.

    Args:
        query: The single-word search query
        locale: The active search locale

    Returns:
        Matching Category or None
    """
    from difflib import get_close_matches

    active = list(Category.objects.filter(is_active=True))
    all_names = [category.get_name(locale.value) for category in active]
    matches = get_close_matches(query, all_names, n=1, cutoff=0.8)
    if matches:
        matched_name = matches[0]
        for category in active:
            if category.get_name(locale.value) == matched_name:
                return category
    return None
