"""
Search view for Mko Bazuna.

Language-aware FTS search on per-language search vectors.
The query is searched in the buyer's own language against the matching
vector column — no external translation on the search critical path.
One-word queries trigger fuzzy category detection.
"""

import logging
import re
from difflib import get_close_matches
from typing import Final

from django.contrib.postgres.search import SearchQuery, SearchRank
from django.core.paginator import Paginator
from django.db.models import F, QuerySet
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render

from apps.ads.services.listings_query import ListingsQuery, ListingsQueryParams
from apps.categories.models import Category
from apps.core.enums import AdSort, AnalyticsEventType, LanguageLocale
from apps.core.services.analytics import record_event
from apps.core.utils.sanitize import sanitize_query_for_log
from apps.locations.models import City
from apps.locations.services.city_suggestions import suggest_city
from apps.search.services.popular_search import increment_popular_search
from apps.search.services.search_history import record_search_history

logger = logging.getLogger(__name__)

# Maximum accepted length of a search query string. Truncating at the input edge
# prevents a DataError when the value is persisted into CharField(max_length=200)
# via increment_popular_search / record_search_history (SRH-001).
MAX_SEARCH_QUERY_LENGTH: Final[int] = 200


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
    query = (request.GET.get("q") or "").strip()[:MAX_SEARCH_QUERY_LENGTH]

    # City filter (by slug). An explicit URL city (``request.current_city``,
    # resolved by CityResolutionMiddleware from ``/city/<slug>/`` or
    # ``?city=``) always wins; otherwise the persisted preferred city is the
    # *default* filter (R-05).
    current_city = getattr(request, "current_city", None) or getattr(
        request, "preferred_city", None
    )
    suggested_city = None
    if current_city:
        try:
            City.objects.get(slug=current_city)
        except City.DoesNotExist:
            suggested_city = suggest_city(current_city)

    # Category filter (by slug) — applies in addition to FTS
    current_category = request.GET.get("category")
    suggested_category = None
    breadcrumb_category = None
    if current_category:
        try:
            breadcrumb_category = Category.objects.get(
                slug=current_category, is_active=True
            )
        except Category.DoesNotExist:
            suggested_category = current_category

    # Build validated params and delegate queryset construction to the shared
    # ListingsQuery service (filter + sort + annotate_favorites).
    min_price = request.GET.get("min_price")
    max_price = request.GET.get("max_price")
    listing_purpose_slug = request.GET.get("listing_purpose")
    condition_slug = request.GET.get("condition")
    feature_slugs = request.GET.getlist("features")
    params = ListingsQueryParams(
        category_slug=current_category,
        city_slug=current_city,
        min_price=min_price,
        max_price=max_price,
        purpose_slug=listing_purpose_slug,
        condition_slug=condition_slug,
        feature_slugs=feature_slugs,
        sort=request.GET.get("sort", AdSort.DATE_NEW),
        user_id=request.user.id if request.user.is_authenticated else None,
        page=request.GET.get("page", 1),
        per_page=ListingsQuery.PER_PAGE,
    )
    ads = ListingsQuery.build_queryset(params)

    if query:
        ads = _apply_fts(ads, query, params, request)

    # Resolve category-constrained filter options (F4/F5).
    resolved_purposes, resolved_features, resolved_conditions = ListingsQuery.resolve_filter_options(breadcrumb_category)

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

    # Active price range for filter summary (§6.6)
    active_price_min, active_price_max = ListingsQuery.active_price_range(params)

    # Paginate results
    paginator = Paginator(ads, params.per_page)
    page_obj = paginator.get_page(params.page)
    total_count = int(paginator.count)
    has_results = total_count > 0
    if query and not has_results:
        logger.info(
            "Empty search results for query '%s'", sanitize_query_for_log(query)
        )

    context = {
        "page_obj": page_obj,
        "query": query,
        "has_results": has_results,
        "current_category": current_category,
        "current_city": current_city,
        "current_sort": params.sort,
        "min_price": min_price,
        "max_price": max_price,
        "active_price_min": active_price_min,
        "active_price_max": active_price_max,
        "current_listing_purpose": listing_purpose_slug,
        "current_features": feature_slugs,
        "current_condition": condition_slug,
        "resolved_purposes": resolved_purposes,
        "resolved_features": resolved_features,
        "resolved_conditions": resolved_conditions,
        "suggested_category": suggested_category,
        "suggested_city": suggested_city,
        "breadcrumb_category": breadcrumb_category,
        # Save-search modal context (FT-002)
        "cities": City.objects.order_by("name"),
        "categories": Category.objects.filter(is_active=True).order_by("name"),
        "selected_city": selected_city_id,
        "selected_category": selected_category_id,
        "show_filters": True,
    }

    # HTMX partial rendering support
    if request.headers.get("HX-Request"):
        return render(request, "ads/partials/ad_list.html", context)
    return render(request, "ads/list.html", context)


def _apply_fts(
    queryset: QuerySet, query: str, params: ListingsQueryParams, request: HttpRequest
) -> QuerySet:
    """Apply per-language FTS filtering, relevance sort, and analytics.

    Adds ``SearchRank`` annotation + TSVector filter on the locale's vector
    column, overrides sort to keep ``-rank`` as a tiebreaker, and records
    the search event + popular search / history entries.
    """
    locale = LanguageLocale.from_code(request.LANGUAGE_CODE)
    vector_field = locale.fts_vector_field
    config = locale.fts_config

    # One-word queries: apply fuzzy category detection (locale-aware)
    if _is_single_word(query):
        category_filter = _fuzzy_category_match(query, locale)
        if category_filter:
            descendant_ids = category_filter.get_descendants(
                include_self=True
            ).values_list("id", flat=True)
            queryset = queryset.filter(category_id__in=descendant_ids)

    # FTS search on the locale's per-language vector
    search_query = SearchQuery(query, search_type="websearch", config=config)
    queryset = queryset.annotate(
        rank=SearchRank(F(vector_field), search_query)
    ).filter(**{vector_field: search_query})

    # Sort FTS results by the requested key, keeping relevance (-rank)
    # as a secondary tiebreaker (PO-2=A). Replaces the service's base
    # sort because order_by() overwrites previous ordering.
    if params.sort == AdSort.PRICE_LOW:
        queryset = queryset.order_by(
            F("price_normalized_eur").asc(nulls_last=True),
            "-rank", "-published_at", "-id",
        )
    elif params.sort == AdSort.PRICE_HIGH:
        queryset = queryset.order_by(
            F("price_normalized_eur").desc(nulls_last=True),
            "-rank", "-published_at", "-id",
        )
    elif params.sort == AdSort.DATE_OLD:
        queryset = queryset.order_by("published_at", "-rank", "-id")
    else:  # DATE_NEW — relevance-first default
        queryset = queryset.order_by("-rank", "-published_at", "-id")

    # Record search event (analytics) after successful execution
    record_event(
        AnalyticsEventType.SEARCH_PERFORMED,
        user_id=request.user.id if request.user.is_authenticated else None,
    )

    # Record popular search and user history for autocomplete.
    increment_popular_search(query)
    record_search_history(
        request.user.id if request.user.is_authenticated else None,
        query,
        session=request.session,
    )

    return queryset


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
    active = list(Category.objects.filter(is_active=True))
    all_names = [category.get_name(locale.value) for category in active]
    matches = get_close_matches(query, all_names, n=1, cutoff=0.8)
    if matches:
        matched_name = matches[0]
        for category in active:
            if category.get_name(locale.value) == matched_name:
                return category
    return None
