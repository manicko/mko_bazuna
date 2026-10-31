"""
Search view for Mko Bazuna.

Language-aware FTS search on per-language search vectors.
The query is searched in the buyer's own language against the matching
vector column — no external translation on the search critical path.
One-word queries trigger fuzzy category detection.

The FTS pipeline itself (filtering + relevance sort, cache-hit rank restore,
count/truncation resolution, and the single-word fuzzy category ladder) lives in
:mod:`apps.search.services.fts`; this view is a thin caller that resolves the
request-coupled state (rate limit, query parsing, locale) and delegates the
search mechanics to the service. The moved helpers are re-exported here for the
existing view-private import sites.
"""

import logging
from typing import Final, cast

from django.core.paginator import Paginator
from django.http import (
    HttpRequest,
    HttpResponse,
    HttpResponseBadRequest,
)
from django.shortcuts import render
from pydantic import ValidationError

from apps.ads.services.listings_query import (
    ListingsQuery,
    build_listings_context,
)
from apps.categories.models import Category
from apps.core.enums import AdSort, AnalyticsEventType, LanguageLocale, RateLimitBudget
from apps.core.services.analytics import record_event
from apps.core.utils.rate_limit_response import rate_limited_response
from apps.core.utils.sanitize import (
    redact_search_query,
    sanitize_query_for_log,
    strip_control_chars,
)
from apps.locations.models import City
from apps.locations.services.city_suggestions import suggest_city
from apps.search.services.cache import (
    SEARCH_CACHE_MAX_HITS,
    build_search_cache_key,
    get_cached_search_ids,
)
from apps.search.services.fts import (
    MAX_SEARCH_QUERY_LENGTH,
    _apply_fts_filtering,
    _fuzzy_category_match,
    _fuzzy_match_by_name as _fuzzy_match_by_name,
    _is_single_word,
    _rank_cache_hit_page,
    _resolve_search_count,
)
from apps.search.services.popular_search import increment_popular_search
from apps.search.services.rate_limit import rate_limit_check
from apps.search.services.search_history import record_search_history

logger = logging.getLogger(__name__)

# Query parameter that suppresses the single-word fuzzy category narrowing for one
# request. The buyer-initiated undo of the Q8 guess: with ``all_categories=1`` the
# same query runs against the whole tree instead of the guessed subtree. It is an
# opt-out, never a default: the parameter is absent from every pre-existing URL, so
# the default predicate is byte-identical and option (a)'s disjunctive branch is
# never adopted as default behaviour (Q8 ruling 2026-10-03; owner decision O8).
ALL_CATEGORIES_PARAM: Final[str] = "all_categories"
# Truthy spellings accepted for the opt-out flag.
_ALL_CATEGORIES_TRUTHY: Final[frozenset[str]] = frozenset({"1", "true", "yes", "on"})


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
    if not rate_limit_check(request, namespace="search", budget=RateLimitBudget.SEARCH_PAGE):
        return rate_limited_response()

    # Strip control characters (incl. NUL) at the input edge, trim surrounding
    # whitespace, then slice. Trimming is restored here: the 08-SRCH-006 rewrite
    # dropped it as collateral; ``?q=+`` decodes to a space, so without it a lone
    # space was a deliberate zero-result instead of the pre-fix browse-all (see
    # the 08-SRCH-006 follow-up commit). The control strip is non-truncating so
    # the 200-char ``q`` contract is preserved and it runs BEFORE the trim, so a
    # padded control character cannot shield a space from the trim; the cleaned
    # value is what is searched, cached, analysed and rendered. The slice is last
    # so ``len(query) <= MAX_SEARCH_QUERY_LENGTH`` holds and ``?q=%20%00%20abc%00``
    # yields ``"abc"`` (08-SRCH-006).
    query = strip_control_chars(request.GET.get("q") or "").strip()[
        :MAX_SEARCH_QUERY_LENGTH
    ]

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

    # Build the validated params and the shared filter context through the one
    # entry point both browse views use (10-CQ-015), then delegate queryset
    # construction to the shared ListingsQuery service (filter + sort +
    # annotate_favorites).
    min_price = request.GET.get("min_price")
    max_price = request.GET.get("max_price")
    listing_purpose_slug = request.GET.get("listing_purpose")
    condition_slug = request.GET.get("condition")
    feature_slugs = request.GET.getlist("features")
    try:
        built = build_listings_context(
            category_slug=current_category,
            city_slug=current_city,
            breadcrumb_category=breadcrumb_category,
            sort=request.GET.get("sort", AdSort.DATE_NEW),
            min_price=min_price,
            max_price=max_price,
            purpose_slug=listing_purpose_slug,
            condition_slug=condition_slug,
            feature_slugs=feature_slugs,
            user_id=request.user.id if request.user.is_authenticated else None,
            page=request.GET.get("page", 1),
        )
    except ValidationError:
        # The only bounded field is ``feature_slugs`` (08-SRCH-001): a list over
        # MAX_FEATURE_FILTER_SLUGS is rejected at the DTO boundary. A bare 400
        # carries no body, so no new i18n surface is introduced; it is not a
        # coercion or truncation, which would silently change result semantics.
        return HttpResponseBadRequest()
    params = built.params
    ads = ListingsQuery.build_queryset(params)

    # Defaults for the no-query path; overridden by the FTS COUNT(*) path when
    # a search query is present (08-SRH-002).
    total_count = 0
    results_truncated = False
    # Full ordered cached id list on a non-empty cache hit: drives pagination
    # metadata while the rendered rows come from the page-scoped rank queryset
    # (13-PERF-010 validated 2026-09).
    cached_ranked_ids: list[int] | None = None

    # The single-word fuzzy category narrowing is a hard filter (Q8 ruling
    # 2026-10-03). The default path signals it and offers an undo; the buyer can
    # opt out of the guess for one request with ``?all_categories=1`` (O8). The
    # flag is read here, before the cache key is built, and threaded into both the
    # narrowing and the cache key so a narrowed and a whole-tree search for the
    # same query can never collide. When the flag is set, ``narrowed_category`` is
    # None (there is nothing to undo) and ``_apply_fts_filtering`` skips the
    # narrowing, so the buyer sees their own query across the whole tree.
    all_categories = _all_categories_requested(request)
    narrowed_category: Category | None = None

    if query:
        # Resolve the active search locale once and thread it into the FTS
        # service; the pipeline is request-free (S1.1 extraction).
        locale = LanguageLocale.from_code(request.LANGUAGE_CODE)
        if _is_single_word(query) and not all_categories:
            narrowed_category = _fuzzy_category_match(query, locale)
        cache_key = build_search_cache_key(
            params, query, locale, all_categories=all_categories
        )

        def producer() -> list[int]:
            filtered_qs = _apply_fts_filtering(
                ads, query, params, locale, all_categories=all_categories
            )
            # Push the cache cap into SQL (13-PERF-006 #1 validated 2026-09):
            # the LIMIT bounds the top-N result set in the database instead of
            # materialising every matching id and slicing the Python list.
            bounded_ids = filtered_qs.values_list("id", flat=True)[
                :SEARCH_CACHE_MAX_HITS
            ]
            return cast("list[int]", list(bounded_ids))

        cached_ids = get_cached_search_ids(cache_key, producer)

        if cached_ids is not None:
            if cached_ids:
                # Cache hit (fresh or stale-served): filter base queryset to
                # the cached IDs and restore FTS rank order via Case/When.
                # The rank arms are scoped to the page window (13-PERF-010
                # validated 2026-09): the full cached list (up to
                # SEARCH_CACHE_MAX_HITS = 1000) is kept to drive pagination
                # metadata, but only this page's ids enter the statement, so
                # statement size and bind count scale with ``per_page``.
                cached_ranked_ids = cached_ids
                ads = _rank_cache_hit_page(ads, cached_ids, params)
            else:
                # Cached empty result — no DB round-trip needed.
                ads = ads.none()
        else:
            # Cold miss loser (lock held by another worker): fall back to a
            # direct FTS query so the response is never blocked.
            ads = _apply_fts_filtering(
                ads, query, params, locale, all_categories=all_categories
            )

        _record_search_analytics(query, request)

        # Decouple display count from the 1000-row cache cap (08-SRH-002).
        # 13-PERF-006 #1 (validated 2026-09): the cached ID list is already
        # bounded by SQL, so the at/over-cap path derives its count from that
        # bounded list and never re-runs the FTS filter to count.
        total_count, results_truncated = _resolve_search_count(cached_ids, ads)

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

    # Paginate results.  On a non-empty cache hit the ordered id list drives
    # the pagination metadata (so page counts and links are unchanged) while the
    # rendered rows come from the page-scoped rank queryset built above
    # (13-PERF-010 validated 2026-09).
    if cached_ranked_ids is not None:
        paginator = Paginator(range(len(cached_ranked_ids)), params.per_page)
        page_obj = paginator.get_page(params.page)
        page_obj.object_list = list(ads)
    else:
        paginator = Paginator(ads, params.per_page)
        page_obj = paginator.get_page(params.page)
    if not query:
        total_count = int(paginator.count)
        results_truncated = False
    # Derive ``has_results`` from the same evaluation as the rendered rows
    # (08-SRCH-015): the empty state must describe the page that is actually
    # rendered, not a count taken from the cache. On a cache hit the rendered
    # page is the cached id list re-filtered against the live predicate, so an
    # ad that stopped matching between the cache write and the read drops out of
    # ``page_obj`` while ``total_count`` still counts it — which, with
    # ``has_results`` derived from ``total_count``, rendered neither cards nor
    # the empty state (a blank results area at HTTP 200).
    #
    # The page contents are the authority, read once here and iterated by the
    # template. A page number past the end is a distinct case that must NOT
    # render the "no results" empty state: ``Paginator.get_page`` clamps it to
    # the last page, so an out-of-range page of a non-empty result set carries
    # rows and stays "has results". Only a genuinely empty result set — no
    # matches, or a warm cache whose every id stopped matching — yields an empty
    # page. This does not touch ``total_count`` or ``results_truncated``: they
    # remain the authoritative count and truncation flag for their consumers.
    has_results = len(page_obj.object_list) > 0
    if query and not has_results:
        # Redact PII (phone, e-mail, multi-word capitalised name) before the value
        # reaches the production JSONL sink. RedactingJsonFormatter cannot rescue
        # this: its pattern only matches key=value, not a bare quoted value. The
        # composition keeps the control-character strip that sanitize_query_for_log
        # already provides on this path; redact_search_query never lengthens and
        # truncates to the same _MAX_QUERY_LENGTH. Only the log argument changes -
        # the search, cache key, analytics and template context keep ``query``
        # unredacted (08-SRCH-002).
        logger.info(
            "Empty search results for query '%s'",
            redact_search_query(sanitize_query_for_log(query)),
        )

    context = {
        **built.filter_context,
        "page_obj": page_obj,
        "query": query,
        "has_results": has_results,
        "suggested_category": suggested_category,
        "suggested_city": suggested_city,
        "breadcrumb_category": breadcrumb_category,
        # Save-search modal context (FT-002). The city list is NOT set here:
        # ``context_processors.header_context`` already publishes ``cities`` on
        # every request, so re-setting it here ran a second identical
        # ``SELECT ... FROM cities ORDER BY name`` and shadowed the processor's
        # value. The header/modal render from the processor's list instead
        # (13-PERF-008 validated 2026-09).
        "categories": Category.objects.filter(is_active=True).order_by("name"),
        "selected_city": selected_city_id,
        "selected_category": selected_category_id,
        "total_count": total_count,
        "results_truncated": results_truncated,
        # The cache cap drives the truncation notice's "showing the first
        # <cap>" wording, so the rendered claim matches the data (13-PERF-006
        # #2, Q9 ruling 2026-10-03).
        "search_cache_max_hits": SEARCH_CACHE_MAX_HITS,
        "narrowed_category": narrowed_category,
        "all_categories": all_categories,
    }

    # HTMX partial rendering support
    if request.headers.get("HX-Request"):
        return render(request, "ads/partials/ad_list.html", context)
    return render(request, "ads/list.html", context)


def _all_categories_requested(request: HttpRequest) -> bool:
    """Whether the request opted out of the category narrowing (O8).

    Reads ``?all_categories=`` and accepts the truthy spellings in
    ``_ALL_CATEGORIES_TRUTHY``. Any other value (absent, empty, ``0``, ``false``)
    leaves the default narrowing in place, so every pre-existing URL keeps the
    exact pre-O8 predicate.
    """
    value = (request.GET.get(ALL_CATEGORIES_PARAM) or "").strip().lower()
    return value in _ALL_CATEGORIES_TRUTHY


def _record_search_analytics(query: str, request: HttpRequest) -> None:
    """Record search analytics for a query-bearing search.

    Fires ``SEARCH_PERFORMED`` event, increments the popular-search counter,
    and records per-user (or session) search history.  Called unconditionally
    inside the view's ``if query:`` block so that analytics are never
    suppressed by the cache layer (cache hit, miss, stale-serve, or fallback).

    Args:
        query: The normalized (stripped, truncated) search query string.
        request: The original HTTP request (for user/session context).
    """
    record_event(
        AnalyticsEventType.SEARCH_PERFORMED,
        user_id=request.user.id if request.user.is_authenticated else None,
    )
    increment_popular_search(query)
    record_search_history(
        request.user.id if request.user.is_authenticated else None,
        query,
        session=request.session,
    )
