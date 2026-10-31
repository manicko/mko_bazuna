"""
JSON listings endpoint — ``GET /api/v1/ads/``.

The read-only JSON mirror of :func:`apps.ads.views.listings.listings`: it parses
the same GET dimensions, builds the queryset through the **same** service tier
(:class:`~apps.ads.services.listings_query.ListingsQuery` /
:func:`~apps.ads.services.listings_query.build_listings_context`) and answers
with a structured pagination envelope instead of a rendered template. Audience
parity is by construction — the shared queryset carries the same
``account_state_q`` predicate the HTML surface does, so a banned / deleted /
declined / consent-withdrawn seller's ads are invisible here exactly as they are
on the website (D5).

Rate limiting uses the shared single enforcement point ``rate_limit_check`` with
the dedicated ``API_PUBLIC_READ`` budget and the per-route ``api_listings``
namespace (R1/Q4); exhaustion is rendered as an RFC 9457 ``rate_limited``
problem with a ``Retry-After`` header, never the legacy bare/JSON 429 shape.
Validation failures are RFC 9457 ``validation_failed`` problems (422). The
legacy HTML listings view keeps its existing 429 shape untouched.
"""

import logging
from typing import Any

from django.core.paginator import Paginator
from django.http import HttpRequest, JsonResponse
from pydantic import ValidationError

from apps.ads.models import Ad
from apps.ads.services.listings_query import (
    ListingsQuery,
    build_listings_context,
)
from apps.core.enums import AdSort, RateLimitBudget
from apps.core.utils.problem import rate_limited_problem, validation_problem
from apps.search.services.rate_limit import rate_limit_check

logger = logging.getLogger(__name__)

# The rate-limit namespace for this route. Distinct per ``/api/v1/`` read route
# so exhausting this counter never throttles another endpoint (plan Q4).
_RATE_LIMIT_NAMESPACE: str = "api_listings"


def listings_view(request: HttpRequest) -> JsonResponse:
    """Return a page of published listings as a JSON envelope.

    Query dimensions (mirroring the HTML listings view 1:1):
    ``category`` (slug), ``city`` (slug), ``listing_purpose``, ``condition``,
    ``features`` (repeatable), ``min_price``, ``max_price``, ``sort``, ``page``.
    Additionally ``per_page`` is accepted (the shared DTO exposes it; the HTML
    view fixes it at ``ListingsQuery.PER_PAGE``). An absent ``per_page`` uses
    the service default, so the default request is byte-identical to the HTML
    page size.

    Unknown / hostile scalar values follow the shared DTO's coercion rules (e.g.
    an unknown ``sort`` falls back to ``date_desc``); unknown extra query
    parameters are ignored, exactly as the HTML view ignores them.
    """
    if not rate_limit_check(
        request,
        namespace=_RATE_LIMIT_NAMESPACE,
        budget=RateLimitBudget.API_PUBLIC_READ,
    ):
        return rate_limited_problem(RateLimitBudget.API_PUBLIC_READ)

    try:
        built = build_listings_context(
            category_slug=request.GET.get("category"),
            city_slug=request.GET.get("city"),
            breadcrumb_category=None,
            sort=request.GET.get("sort", AdSort.DATE_NEW),
            min_price=request.GET.get("min_price"),
            max_price=request.GET.get("max_price"),
            purpose_slug=request.GET.get("listing_purpose"),
            condition_slug=request.GET.get("condition"),
            feature_slugs=request.GET.getlist("features"),
            page=request.GET.get("page", 1),
            user_id=request.user.id if request.user.is_authenticated else None,
            per_page=request.GET.get("per_page") or ListingsQuery.PER_PAGE,
        )
    except ValidationError as exc:
        # A ?features= list over MAX_FEATURE_FILTER_SLUGS is rejected at the DTO
        # boundary (08-SRCH-001), mirroring the HTML view's 400 — rendered here
        # as the RFC 9457 422 problem the /api/v1/ contract requires.
        return validation_problem(exc)

    params = built.params
    queryset = ListingsQuery.build_queryset(params)

    total_count = queryset.count()
    page_obj = _paginate(queryset, params.page, params.per_page)
    results = [_serialize_ad(ad) for ad in page_obj.object_list]

    return JsonResponse(
        {
            "page": page_obj.number,
            "per_page": params.per_page,
            "total_count": total_count,
            "results_truncated": False,
            "results": results,
            "has_next": page_obj.has_next(),
        }
    )


def _paginate(queryset: Any, page: int, per_page: int) -> Any:
    """Return the Django ``Page`` for *queryset* at *page*.

    Uses ``Paginator`` for the same clamping semantics as the HTML view (an
    out-of-range page yields the last page, never an error). ``built.params``
    already guarantees ``page >= 1``.
    """
    paginator = Paginator(queryset, per_page)
    return paginator.get_page(page)


def _serialize_ad(ad: Ad) -> dict[str, Any]:
    """Serialize one ad into the stable, structured JSON shape (D4).

    Keys are stable; media is exposed as URLs only (never bytes, per stance
    #26). ``absolute_url`` uses the model's own ``get_absolute_url`` so the
    ``SITE_URL`` prefix matches the HTML/deep-link surfaces.
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
