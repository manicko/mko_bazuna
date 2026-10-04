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
from django.db.models import Case, F, IntegerField, QuerySet, When
from django.http import (
    HttpRequest,
    HttpResponse,
    HttpResponseBadRequest,
)
from django.shortcuts import render
from pydantic import ValidationError

from apps.ads.services.listings_query import ListingsQuery, ListingsQueryParams
from apps.categories.models import Category
from apps.core.enums import AdSort, AnalyticsEventType, LanguageLocale
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
from apps.search.services.category_fuzzy import get_active_category_names
from apps.search.services.popular_search import increment_popular_search
from apps.search.services.rate_limit import rate_limit_check
from apps.search.services.search_history import record_search_history

logger = logging.getLogger(__name__)

# Maximum accepted length of a search query string. Truncating at the input edge
# prevents a DataError when the value is persisted into CharField(max_length=200)
# via increment_popular_search / record_search_history (SRH-001).
MAX_SEARCH_QUERY_LENGTH: Final[int] = 200

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
    if not rate_limit_check(request, namespace="search"):
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

    # Build validated params and delegate queryset construction to the shared
    # ListingsQuery service (filter + sort + annotate_favorites).
    min_price = request.GET.get("min_price")
    max_price = request.GET.get("max_price")
    listing_purpose_slug = request.GET.get("listing_purpose")
    condition_slug = request.GET.get("condition")
    feature_slugs = request.GET.getlist("features")
    try:
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
    except ValidationError:
        # The only bounded field is ``feature_slugs`` (08-SRCH-001): a list over
        # MAX_FEATURE_FILTER_SLUGS is rejected at the DTO boundary. A bare 400
        # carries no body, so no new i18n surface is introduced; it is not a
        # coercion or truncation, which would silently change result semantics.
        return HttpResponseBadRequest()
    ads = ListingsQuery.build_queryset(params)

    # Defaults for the no-query path; overridden by the FTS COUNT(*) path when
    # a search query is present (08-SRH-002).
    total_count = 0
    results_truncated = False

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
        locale = LanguageLocale.from_code(request.LANGUAGE_CODE)
        if _is_single_word(query) and not all_categories:
            narrowed_category = _fuzzy_category_match(query, locale)
        cache_key = build_search_cache_key(
            params, query, locale, all_categories=all_categories
        )

        def producer() -> list[int]:
            filtered_qs = _apply_fts_filtering(
                ads, query, params, request, all_categories=all_categories
            )
            return list(
                filtered_qs.values_list("id", flat=True)
            )[:SEARCH_CACHE_MAX_HITS]

        cached_ids = get_cached_search_ids(cache_key, producer)

        if cached_ids is not None:
            if cached_ids:
                # Cache hit (fresh or stale-served): filter base queryset to
                # cached IDs and restore FTS rank order via Case/When.
                ads = ads.filter(pk__in=cached_ids).order_by(
                    Case(
                        *[When(pk=pk, then=pos) for pos, pk in enumerate(cached_ids)],
                        default=len(cached_ids),
                        output_field=IntegerField(),
                    )
                )
            else:
                # Cached empty result — no DB round-trip needed.
                ads = ads.none()
        else:
            # Cold miss loser (lock held by another worker): fall back to a
            # direct FTS query so the response is never blocked.
            ads = _apply_fts_filtering(
                ads, query, params, request, all_categories=all_categories
            )

        _record_search_analytics(query, request)

        # Decouple display count from the 1000-row cache cap (08-SRH-002).
        # The cached ID list is capped at SEARCH_CACHE_MAX_HITS. To avoid
        # re-running the expensive FTS filter just to count, the true match
        # count is derived from the cache outcome: the cached list length when
        # it is below the cap, a dedicated COUNT(*) only at/over the cap, and
        # the already-built FTS queryset on the cold-miss loser fallback.
        total_count, results_truncated = _resolve_search_count(
            cached_ids, ads, query, params, request, all_categories=all_categories
        )

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
        "total_count": total_count,
        "results_truncated": results_truncated,
        "narrowed_category": narrowed_category,
        "all_categories": all_categories,
        "show_filters": True,
    }

    # HTMX partial rendering support
    if request.headers.get("HX-Request"):
        return render(request, "ads/partials/ad_list.html", context)
    return render(request, "ads/list.html", context)


def _apply_fts_filtering(
    queryset: QuerySet,
    query: str,
    params: ListingsQueryParams,
    request: HttpRequest,
    *,
    all_categories: bool = False,
) -> QuerySet:
    """Apply per-language FTS filtering and relevance sort (pure, no side effects).

    Adds ``SearchRank`` annotation + TSVector filter on the locale's vector
    column, and overrides sort to keep ``-rank`` as a tiebreaker.

    ``all_categories=True`` is the buyer's per-request opt-out of the single-word
    fuzzy category narrowing (O8): the narrowing block is skipped for that request
    only, so the same query runs against the whole tree. With the default
    ``all_categories=False`` this function is byte-identical to its pre-O8 form and
    ``_is_single_word`` still gates the narrowing.

    Side effects (analytics recording) are deliberately excluded — the caller
    should invoke :func:`_record_search_analytics` separately so that analytics
    fire unconditionally for every query-bearing search regardless of cache state.
    """
    locale = LanguageLocale.from_code(request.LANGUAGE_CODE)
    vector_field = locale.fts_vector_field
    config = locale.fts_config

    # One-word queries: apply fuzzy category detection (locale-aware), unless the
    # buyer opted out for this request (O8).
    if _is_single_word(query) and not all_categories:
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

    return queryset


def _resolve_search_count(
    cached_ids: list[int] | None,
    ads: QuerySet,
    query: str,
    params: ListingsQueryParams,
    request: HttpRequest,
    *,
    all_categories: bool = False,
) -> tuple[int, bool]:
    """Resolve the true match count and truncation flag for a query search.

    Three outcomes based on the cache outcome of ``cached_ids``:

    - ``cached_ids is not None`` and below ``SEARCH_CACHE_MAX_HITS`` (common
      hot path): the count is simply ``len(cached_ids)`` and results are not
      truncated. No ``COUNT(*)`` and no second FTS evaluation.
    - ``cached_ids is not None`` and at the cap: the display queryset ``ads``
      is ``pk__in``-capped to the slice, so a fresh FTS-filtered queryset is
      built to compute the true count via ``COUNT(*)``.
    - ``cached_ids is None`` (cold-miss loser, lock held): ``ads`` is already
      the FTS-filtered queryset, so its count is reused directly.

    ``all_categories`` is threaded through to the count rebuild so a whole-tree
    search counts the same rows the display path renders (O8).

    Returns:
        A ``(total_count, results_truncated)`` tuple.
    """
    if cached_ids is not None and len(cached_ids) < SEARCH_CACHE_MAX_HITS:
        # Common non-truncated hot path: the cached ID list is authoritative.
        return len(cached_ids), False

    if cached_ids is not None:
        # At/over the cap: recompute the true count from a fresh FTS queryset.
        fts_count_qs = _apply_fts_filtering(
            ListingsQuery.build_queryset(params),
            query,
            params,
            request,
            all_categories=all_categories,
        )
        total_count = fts_count_qs.count()
        return total_count, total_count > SEARCH_CACHE_MAX_HITS

    # Cold-miss loser fallback: ads is already the FTS-filtered queryset.
    total_count = ads.count()
    return total_count, total_count > SEARCH_CACHE_MAX_HITS


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


def _ids_for_exact_name(name: str, locale: LanguageLocale) -> list[int]:
    """Every active category id whose localised display name equals *name*.

    Ambiguity is expected: ``Category.name`` carries no uniqueness constraint
    and ``name_i18n`` is free-form, so two active categories can share a
    localised display name. Returning the first hit would scope the search to
    an arbitrary branch that may hold no matching ads at all (08-VAL-003).

    The lookup is computed from ``get_active_category_names(locale)``, so a
    warm cache performs zero category SELECTs.

    Args:
        name: The display name to match (case-insensitive).
        locale: The active search locale.

    Returns:
        The ids of every active category whose localised name matches.
    """
    target = name.casefold()
    return [
        int(entry["id"])
        for entry in get_active_category_names(locale)
        if str(entry["name"]).casefold() == target
    ]


def _resolve_unique_category(ids: list[int]) -> Category | None:
    """Resolve a matched-name id set, refusing an ambiguous match.

    A single id is unambiguous and resolves to its ``Category``. Zero or more
    than one id means no guess: the caller applies no category narrowing, so a
    search is never silently scoped to an arbitrary branch (08-VAL-003).

    Args:
        ids: The candidate category ids that matched a display name.

    Returns:
        The unique matching ``Category``, or ``None`` when the match is absent
        or ambiguous.
    """
    if len(ids) == 1:
        return Category.objects.get(id=ids[0])
    return None


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
    # Try slug match first (slug is unique so first() is safe and a slug match
    # stays unambiguous regardless of the display-name ambiguity rule).
    by_slug = Category.objects.filter(slug__iexact=query, is_active=True).first()
    if by_slug:
        return by_slug
    # Exact match against the locale-appropriate display name (case-insensitive).
    # Iterates the cached name list rather than loading all active categories.
    # Two or more matching ids means an ambiguous display name: return no guess
    # so the search is not scoped to an arbitrary branch (08-VAL-003).
    exact_ids = _ids_for_exact_name(query, locale)
    if exact_ids:
        return _resolve_unique_category(exact_ids)
    return _fuzzy_match_by_name(query, locale)


def _fuzzy_match_by_name(query: str, locale: LanguageLocale) -> Category | None:
    """Find the closest category name match using difflib fuzzy matching.

    Uses the cached active-category name list (versioned + locale-aware), so
    a warm cache runs the fuzzy match with zero category SELECTs. The
    ``difflib.get_close_matches`` algorithm and cutoff are unchanged.

    An ambiguous display name (two or more matching ids) returns no guess so
    the search is not scoped to an arbitrary branch (08-VAL-003).

    Args:
        query: The single-word search query
        locale: The active search locale

    Returns:
        Matching Category or None
    """
    entries = get_active_category_names(locale)
    all_names = [str(entry["name"]) for entry in entries]
    matches = get_close_matches(query, all_names, n=1, cutoff=0.8)
    if matches:
        return _resolve_unique_category(
            _ids_for_exact_name(matches[0], locale)
        )
    return None
