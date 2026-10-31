"""
JSON search endpoint — ``GET /api/v1/search/``.

The read-only JSON mirror of :func:`apps.search.views.search.search`: it parses
the same GET dimensions, resolves the same request-coupled state (rate limit,
locale, current city, category guess) and delegates the search mechanics to the
**same** service tier (:mod:`apps.search.services.fts` +
:class:`~apps.ads.services.listings_query.ListingsQuery` /
:func:`~apps.ads.services.listings_query.build_listings_context`) the HTML view
uses. The response is a structured envelope instead of a rendered template.

Audience parity is by construction — the shared queryset carries the same
``account_state_q`` predicate the HTML surface does. Ordering parity is by
construction too: both surfaces run the identical FTS pipeline and the identical
cache-hit page-rank restore, so the ``results[].id`` sequence matches the HTML
``page_obj`` ids (proven by ``test_search_api.py``, including the warm-cache
path).

Rate limiting works like the sibling ``/api/v1/ads/`` endpoint: the shared
single enforcement point ``rate_limit_check`` with the dedicated
``API_PUBLIC_READ`` budget under the ``api_search`` namespace; exhaustion is an
RFC 9457 ``rate_limited`` problem with a ``Retry-After`` header, never the legacy
``{"error":"rate_limit"}`` shape the HTML search view still emits.

Analytics/history side effects are recorded inline (the same three calls the HTML
view's private helper makes) so an API search and an HTML search for the same
query produce identical ``SEARCH_PERFORMED`` / popular-search / search-history
rows — including on a warm cache hit.
"""

import logging
from typing import Annotated, Any, Final, cast

from django.core.paginator import Paginator
from django.http import HttpRequest, JsonResponse
from pydantic import Field, ValidationError, field_validator

from apps.ads.services.listings_query import (
    MAX_FEATURE_FILTER_SLUGS,
    ListingsQuery,
    build_listings_context,
)
from apps.categories.models import Category
from apps.core.enums import AdSort, AnalyticsEventType, LanguageLocale, RateLimitBudget
from apps.core.schemas import BaseInputModel
from apps.core.services.analytics import record_event
from apps.core.utils.problem import rate_limited_problem, validation_problem
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
    _is_single_word,
    _rank_cache_hit_page,
    _resolve_search_count,
)
from apps.search.services.popular_search import increment_popular_search
from apps.search.services.rate_limit import rate_limit_check
from apps.search.services.search_history import record_search_history

logger = logging.getLogger(__name__)

# The rate-limit namespace for this route. Distinct per ``/api/v1/`` read route
# so exhausting this counter never throttles another endpoint (plan Q4).
_RATE_LIMIT_NAMESPACE: Final[str] = "api_search"

# Query parameter that suppresses the single-word fuzzy category narrowing for one
# request (the O8 opt-out). Mirrors ``apps.search.views.search.ALL_CATEGORIES_PARAM``.
_ALL_CATEGORIES_PARAM: Final[str] = "all_categories"
# Truthy spellings accepted for the opt-out flag (byte-identical to the HTML view).
_ALL_CATEGORIES_TRUTHY: Final[frozenset[str]] = frozenset({"1", "true", "yes", "on"})


class SearchInputModel(BaseInputModel):
    """Validated GET dimensions for the JSON search endpoint.

    Every scalar mirrors the HTML search view's ``request.GET`` read 1:1 (the
    field names are aliases for the raw query-string keys). The **only** bounded
    field is ``features``: a list over ``MAX_FEATURE_FILTER_SLUGS`` is rejected
    at this DTO boundary (08-SRCH-001), which is the endpoint's single 422
    trigger — every other hostile scalar is coerced later by the shared
    ``ListingsQueryParams`` DTO so the API and HTML surfaces cannot drift.

    ``all_categories`` is the buyer's per-request opt-out of the single-word
    fuzzy category narrowing (O8), read through a truthy-set before-validator.
    """

    q: str = ""
    category: str | None = None
    city: str | None = None
    min_price: str | None = None
    max_price: str | None = None
    listing_purpose: str | None = None
    condition: str | None = None
    sort: str | None = None
    page: str | None = None
    features: Annotated[
        list[str],
        Field(max_length=MAX_FEATURE_FILTER_SLUGS),
    ] = Field(default_factory=list)
    all_categories: bool = False

    @field_validator("features", mode="before")
    @classmethod
    def _clean_features(cls, v: Any) -> list[str]:
        """Strip empty strings and dedupe ``features`` (order-preserving).

        Mirrors ``ListingsQueryParams._clean_feature_slugs`` so a bare
        ``?features=`` or a duplicated slug collapses before the ``max_length``
        cardinality bound — the same cleaning the HTML view gets through the
        shared DTO.
        """
        if v is None:
            return []
        if isinstance(v, str):
            v = [v]
        seen: set[str] = set()
        cleaned: list[str] = []
        for item in v:
            slug = str(item).strip()
            if not slug or slug in seen:
                continue
            seen.add(slug)
            cleaned.append(slug)
        return cleaned

    @field_validator("all_categories", mode="before")
    @classmethod
    def _coerce_all_categories(cls, v: Any) -> bool:
        """Accept the truthy spellings the HTML view accepts (O8)."""
        if isinstance(v, bool):
            return v
        if v is None:
            return False
        return str(v).strip().lower() in _ALL_CATEGORIES_TRUTHY


def search_view(request: HttpRequest) -> JsonResponse:
    """Return a page of FTS search results as a JSON envelope.

    Query dimensions (mirroring the HTML search view 1:1): ``q`` (raw; the view
    applies the control-strip + trim + 200-char slice), ``category`` (slug),
    ``city`` (documented-accepted; the real filter city comes from the
    middleware-resolved ``request.current_city``, exactly as the HTML view),
    ``min_price``, ``max_price``, ``listing_purpose``, ``condition``,
    ``features`` (repeatable), ``sort``, ``page`` and ``all_categories``.
    ``per_page`` is fixed at ``ListingsQuery.PER_PAGE`` (24) like the HTML view.
    Unknown extra query parameters are ignored, exactly as the HTML view ignores
    them.
    """
    if not rate_limit_check(
        request,
        namespace=_RATE_LIMIT_NAMESPACE,
        budget=RateLimitBudget.API_PUBLIC_READ,
    ):
        return rate_limited_problem(RateLimitBudget.API_PUBLIC_READ)

    try:
        dto = SearchInputModel.model_validate({**_known_params(request)})
    except ValidationError as exc:
        # A ?features= list over MAX_FEATURE_FILTER_SLUGS is rejected at the DTO
        # boundary (08-SRCH-001), mirroring the HTML view's 400 — rendered here
        # as the RFC 9457 422 problem the /api/v1/ contract requires.
        return validation_problem(exc)

    # Same normalization as the HTML view: strip control characters (incl. NUL),
    # trim, then slice to the 200-char contract.
    query = strip_control_chars(dto.q).strip()[:MAX_SEARCH_QUERY_LENGTH]

    # City filter (by slug). An explicit URL city (``request.current_city``,
    # resolved by CityResolutionMiddleware from ``/city/<slug>/`` or ``?city=``)
    # always wins; otherwise the persisted preferred city is the *default* filter
    # (R-05). The ``city`` DTO field is documented-accepted for parity with the
    # HTML query dimensions but never drives the filter.
    current_city = getattr(request, "current_city", None) or getattr(
        request, "preferred_city", None
    )
    suggested_city = None
    if current_city:
        try:
            City.objects.get(slug=current_city)
        except City.DoesNotExist:
            suggested_city = suggest_city(current_city)

    # Category filter (by slug) — applies in addition to FTS.
    current_category = dto.category
    suggested_category = None
    breadcrumb_category = None
    if current_category:
        try:
            breadcrumb_category = Category.objects.get(
                slug=current_category, is_active=True
            )
        except Category.DoesNotExist:
            suggested_category = current_category

    # Build the validated params and filter context through the one shared entry
    # point; DTO raw strings are passed through so ``ListingsQueryParams`` stays
    # the single coercion source and the cache key is byte-identical to the HTML
    # view's for the same request.
    try:
        built = build_listings_context(
            category_slug=current_category,
            city_slug=current_city,
            breadcrumb_category=breadcrumb_category,
            sort=dto.sort if dto.sort is not None else AdSort.DATE_NEW,
            min_price=dto.min_price,
            max_price=dto.max_price,
            purpose_slug=dto.listing_purpose,
            condition_slug=dto.condition,
            feature_slugs=dto.features,
            user_id=request.user.id if request.user.is_authenticated else None,
            page=dto.page if dto.page is not None else 1,
        )
    except ValidationError as exc:
        return validation_problem(exc)

    params = built.params
    ads = ListingsQuery.build_queryset(params)

    total_count = 0
    results_truncated = False
    cached_ranked_ids: list[int] | None = None

    all_categories = dto.all_categories
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
                ads, query, params, locale, all_categories=all_categories
            )
            bounded_ids = filtered_qs.values_list("id", flat=True)[
                :SEARCH_CACHE_MAX_HITS
            ]
            return cast("list[int]", list(bounded_ids))

        cached_ids = get_cached_search_ids(cache_key, producer)

        if cached_ids is not None:
            if cached_ids:
                cached_ranked_ids = cached_ids
                ads = _rank_cache_hit_page(ads, cached_ids, params)
            else:
                ads = ads.none()
        else:
            ads = _apply_fts_filtering(
                ads, query, params, locale, all_categories=all_categories
            )

        _record_search_analytics(query, request)

        total_count, results_truncated = _resolve_search_count(cached_ids, ads)

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

    results = [_serialize_ad(ad) for ad in page_obj.object_list]

    if query and not results:
        # Redact PII before the value reaches the production JSONL sink; only the
        # log argument is redacted — search, cache key and analytics keep ``query``
        # unredacted (08-SRCH-002). Observable-behavior parity with the HTML view.
        logger.info(
            "Empty search results for query '%s'",
            redact_search_query(sanitize_query_for_log(query)),
        )

    return JsonResponse(
        {
            "page": page_obj.number,
            "per_page": params.per_page,
            "total_count": total_count,
            "results_truncated": results_truncated,
            "results": results,
            "has_next": page_obj.has_next(),
            "narrowed_category": _named(narrowed_category),
            "suggested_category": suggested_category,
            "suggested_city": suggested_city,
            "search_cache_max_hits": SEARCH_CACHE_MAX_HITS,
        }
    )


def _known_params(request: HttpRequest) -> dict[str, Any]:
    """Build the explicit-dict DTO input from ``request.GET`` known keys.

    An explicit dict — not ``request.GET.dict()`` — so unknown / hostile extra
    parameters are ignored exactly as the HTML view ignores them, and repeated
    ``features`` are collected as a list.
    """
    return {
        "q": request.GET.get("q") or "",
        "category": request.GET.get("category"),
        "city": request.GET.get("city"),
        "min_price": request.GET.get("min_price"),
        "max_price": request.GET.get("max_price"),
        "listing_purpose": request.GET.get("listing_purpose"),
        "condition": request.GET.get("condition"),
        "sort": request.GET.get("sort"),
        "page": request.GET.get("page"),
        "features": request.GET.getlist("features"),
        "all_categories": request.GET.get(_ALL_CATEGORIES_PARAM),
    }


def _record_search_analytics(query: str, request: HttpRequest) -> None:
    """Record search analytics for a query-bearing search.

    Fires ``SEARCH_PERFORMED``, increments the popular-search counter and
    records per-user (or session) search history — the same three calls, in the
    same order, the HTML view's private helper makes, so the two surfaces have
    identical side effects. Called unconditionally inside the ``if query:``
    block so analytics are never suppressed by the cache layer.
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


def _serialize_ad(ad: Any) -> dict[str, Any]:
    """Serialize one ad into the stable, structured JSON shape (D4).

    Local per-app serializer (the mirror does not import the ads API module, so
    neither does this one). Keys match ``apps.ads.views.api.listings._serialize_ad``
    so the two read surfaces expose the same ad shape.
    """
    return {
        "id": ad.id,
        "title": ad.get_title(),
        "price": str(ad.price_amount) if ad.price_amount is not None else None,
        "currency": ad.price_currency,
        "city": _named(ad.city),
        "category": _named(ad.category),
        "listing_purpose": ad.listing_purpose.slug if ad.listing_purpose else None,
        "condition": ad.listing_condition.slug if ad.listing_condition else None,
        "status": ad.status,
        "published_at": ad.published_at.isoformat() if ad.published_at else None,
        "created_at": ad.created_at.isoformat() if ad.created_at else None,
        "image_urls": [image.image_url for image in ad.images.all()],
        "absolute_url": ad.get_absolute_url(),
    }


def _named(obj: Any) -> dict[str, Any] | None:
    """Return ``{"slug", "name"}`` for an optional related object, else ``None``."""
    if obj is None:
        return None
    return {"slug": obj.slug, "name": str(obj.name)}
