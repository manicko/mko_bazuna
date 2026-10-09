"""
Listings view for Mko Bazuna.

Public browsing of PUBLISHED ads with category subtree, city, price range filters.
HTMX-compatible MPA (no login required).
"""

import logging
from typing import Final

from django.conf import settings
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import (
    FileResponse,
    Http404,
    HttpRequest,
    HttpResponse,
    HttpResponseBadRequest,
    HttpResponseBase,
    HttpResponseForbidden,
)
from django.shortcuts import render
from django.utils.translation import gettext as _
from django.views.decorators.vary import vary_on_headers
from pydantic import ValidationError

from apps.ads.models import Ad, AdImage
from apps.ads.services.listings_query import (
    ListingsQuery,
    build_listings_context,
)
from apps.categories.models import Category
from apps.categories.services.fuzzy import match_category
from apps.categories.services.lookup_resolution import CategoryLookupResolver
from apps.core.enums import AdSort, AdStatus, AnalyticsEventType, RateLimitBudget
from apps.core.services.analytics import record_event
from apps.core.services.contact_rate_limit import check_deep_link_render_rate_limit
from apps.core.services.site_config import get_bot_username
from apps.core.utils.cache import bump_rate_limit_window
from apps.core.utils.client_ip import get_client_ip
from apps.core.utils.rate_limit_response import rate_limited_response
from apps.locations.models import City
from apps.locations.services.city_suggestions import suggest_city
from apps.media.services.filesystem import assert_storage_key_contained
from apps.media.storage_keys import KEY_COLUMNS
from apps.users.services.account_state import account_state_q

logger = logging.getLogger(__name__)

# Application-level limiter for the media gate (09-API-005). The proxy half is
# already shipped — nginx's `location /media/` carries `browse_limit burst=40`
# in both sites — and is deliberately left unchanged: `.ai/plans/21-*` and
# `.ai/plans/22-*` hold that exact directive as a deployed-stack measurement
# basis. This limiter is the half that survives the proxy being bypassed.
#
# The budget (60 requests / 60 s per client IP) now lives in the shared
# ``RateLimitBudget.MEDIA_GATE`` table (08-SRCH-010); the module constants below
# remain so existing callers and tests keep their import surface.
MEDIA_RATE_LIMIT_REQUESTS: int = RateLimitBudget.MEDIA_GATE.requests

MEDIA_RATE_LIMIT_PERIOD: int = RateLimitBudget.MEDIA_GATE.period

_MEDIA_RATE_LIMIT_KEY_PATTERN: Final[str] = "media_gate_rl:{ip}"

# 240×180 gray SVG placeholder returned on 429 so the browser renders the
# thumbnail slot with the same ``bg-gray-200`` (#e5e7eb) fallback the CSS
# uses.  No text content: avoids the i18n completeness gate and keeps the
# body cacheable as a static fallback.
_MEDIA_GATE_429_SVG: Final[str] = (
    '<svg xmlns="http://www.w3.org/2000/svg" '
    'width="240" height="180" viewBox="0 0 240 180">'
    '<rect width="240" height="180" fill="#e5e7eb"/>'
    "</svg>"
)

# 200 responses on media_gate carry a 24h CDN/browser TTL. ``public`` lets nginx
# and shared caches store the response (the view itself is unauthenticated —
# access is gated per-IP by the rate limiter and per-status at the DB lookup).
# ``immutable`` is deliberately omitted: image keys are UUID v4 (uploads) or
# fixed ``seed/<filename>.jpg`` names, NOT content-addressed. Seed files are
# regenerated with WriteMode.REPLACE at the same URL, so a stale cached body
# would be served if ``immutable`` were present.
_MEDIA_CACHE_CONTROL_200: Final[str] = "public, max-age=86400"


def ad_detail(request: HttpRequest, ad_id: int) -> HttpResponse:
    """
    Detail view for a single PUBLISHED ad.

    Shows ad title, description, price, photos, city, category.
    Contact button placeholder for Phase 3.

    Args:
        request: HTTP request
        ad_id: The ad ID to display

    Returns:
        Rendered detail page or 404 if ad not found / not published
    """
    if not check_deep_link_render_rate_limit(request):
        logger.warning("Deep-link render rate limit exceeded (ad_detail)")
        return rate_limited_response(json=False)
    try:
        ad = (
            Ad.objects.select_related("category", "city", "user")
            .prefetch_related("images", "features", "user__trust_score")
            .filter(account_state_q("user__"))
            .get(
                id=ad_id,
                status=AdStatus.PUBLISHED,
            )
        )
    except Ad.DoesNotExist:
        raise Http404("Ad not found") from None

    # Record the view event for seller statistics
    record_event(
        AnalyticsEventType.AD_VIEWED,
        user_id=ad.user_id,  # Seller, not viewer
        ad_id=ad.id,
    )

    # Category-aware feature adequacy validation (Spec_29 §7.2.5 / Q5).
    # Only display features whose slug belongs to the ad's resolved feature set —
    # the nearest-explicit-ancestor-wins MPTM walk via CategoryLookupResolver.
    # This prevents showing a feature from one category (e.g. "credit") on an ad
    # in a different category (e.g. real estate). The resolver is cached (300s).
    resolved_feature_slugs = set(
        CategoryLookupResolver.get_resolved_feature_codes(ad.category)
    )
    display_features = [
        f for f in ad.features.all() if f.slug in resolved_feature_slugs
    ]

    context = {
        "ad": ad,
        "breadcrumb_category": ad.category,
        "bot_username": get_bot_username(),
        "display_features": display_features,
        "is_favorited": (
            ad.favorites.filter(user_id=request.user.id).exists()
            if request.user.is_authenticated
            else False
        ),
    }

    return render(request, "ads/detail.html", context)


def _serve_image(image_key: str) -> HttpResponseBase:
    """Serve a media file directly (development fallback without nginx).

    Uses ``FileResponse`` to stream the file from ``MEDIA_ROOT``.  In production,
    the ``media_gate`` view returns an ``X-Accel-Redirect`` header that nginx
    intercepts; this helper is only used when ``DEBUG=True``.
    """
    try:
        assert_storage_key_contained(image_key)
    except ValueError:
        raise Http404("Image not found") from None

    file_path = settings.MEDIA_ROOT / image_key
    if not file_path.exists():
        raise Http404("Image not found")
    response = FileResponse(open(file_path, "rb"), content_type="image/jpeg")
    response["X-Content-Type-Options"] = "nosniff"
    return response


@vary_on_headers("Cookie")
def media_gate(request: HttpRequest, image_key: str) -> HttpResponseBase:
    """
    Media access gate for Ad images and thumbnails.

    Looks up the AdImage row(s) referencing ``image_key`` (matching the
    ``image`` field first, then the ``thumbnail_*`` fallback) and authorizes
    the request: staff users may view anything; non-staff users only when at
    least one referencing ad is PUBLISHED.

    A storage key is **not** guaranteed to be unique. Seed data deliberately
    reuses ``seed/<filename>`` (and its thumbnail variants) across multiple ads,
    so the lookup uses ``filter`` rather than ``get`` to avoid
    ``MultipleObjectsReturned`` (which previously produced HTTP 500 responses
    and broken images on the listings page).

    Serving:
    - In production (DEBUG=False): returns X-Accel-Redirect to the internal
      nginx /protected-media/ location.
    - In development (DEBUG=True, no nginx): serves the file directly via
      FileResponse.

    Args:
        request: HTTP request
        image_key: Storage key (e.g. ``<uuid>.jpg`` or ``seed/<filename>.jpg``)

    Returns:
        FileResponse (dev) or empty 200 with X-Accel-Redirect header (prod),
        or 403/404
    """
    # Rate limit (09-API-005). Runs before the AdImage lookup so an over-budget
    # client never reaches the database — the same policy `listings` uses
    # (client-IP via `get_client_ip`) and the same shared window bump. A cache
    # outage fails open inside `bump_rate_limit_window`, so an unreachable
    # cache never denies legitimate media.
    media_key = _MEDIA_RATE_LIMIT_KEY_PATTERN.format(ip=get_client_ip(request))
    if not bump_rate_limit_window(
        media_key, MEDIA_RATE_LIMIT_REQUESTS, MEDIA_RATE_LIMIT_PERIOD
    ):
        logger.warning("Media gate rate limit exceeded")
        response = rate_limited_response(
            json=False,
            retry_after=MEDIA_RATE_LIMIT_PERIOD,
            body=_MEDIA_GATE_429_SVG,
        )
        response["Content-Type"] = "image/svg+xml"
        return response

    # Reject malformed storage keys early. A NUL byte (or other control
    # characters) can never occur in a valid key (``<uuid>.jpg`` or
    # ``seed/<filename>.jpg``) and would otherwise be sent verbatim to
    # PostgreSQL, raising DataError (HTTP 500) on path-traversal attempts
    # instead of a clean 404.
    if any(ord(ch) < 0x20 for ch in image_key):
        raise Http404("Image not found")

    # Defence-in-depth: reject path-traversal keys (../, absolute paths, NUL)
    # before they reach the DB or the filesystem. Raises ValueError on
    # violation; translate to 404 so traversal attempts are not leaked.
    try:
        assert_storage_key_contained(image_key)
    except ValueError:
        raise Http404("Image not found") from None

    # Match any AdImage that references this key in its ``image`` field or in
    # one of the ``thumbnail_*`` fields. ``get`` must not be used: seed data
    # shares the same key across several ads, which would raise
    # MultipleObjectsReturned -> HTTP 500 for viewers. The column set is owned
    # by ``apps.media.storage_keys`` so it cannot drift from the model's key
    # columns.
    key_q = Q()
    for column in KEY_COLUMNS:
        key_q |= Q(**{column: image_key})

    if not AdImage.objects.filter(key_q).exists():
        raise Http404("Image not found")

    # Staff users (moderators/admins) can view any image regardless of status
    if request.user.is_staff:
        if settings.DEBUG:
            response = _serve_image(image_key)
            response["Cache-Control"] = _MEDIA_CACHE_CONTROL_200
            return response
        response = HttpResponse()
        response["X-Accel-Redirect"] = f"/protected-media/{image_key}"
        response["Cache-Control"] = _MEDIA_CACHE_CONTROL_200
        return response

    # Non-staff users: only serve images referenced by a PUBLISHED ad owned by
    # an account-state eligible user (the shared ``account_state_q`` declaration,
    # 06-PII-104 / Q7). A shared seed key can be attached to several ads, so
    # check existence across all of them rather than the status of a single
    # (arbitrary) row. This hides a banned seller's images: a ban is a moderation
    # sanction and the media gate is one of the four public surfaces it covers
    # (08-SRCH-008).
    if not AdImage.objects.filter(
        account_state_q("ad__user__"),
        key_q,
        ad__status=AdStatus.PUBLISHED,
    ).exists():
        return HttpResponseForbidden(_("Access denied"))

    if settings.DEBUG:
        response = _serve_image(image_key)
        response["Cache-Control"] = _MEDIA_CACHE_CONTROL_200
        return response

    response = HttpResponse()
    response["X-Accel-Redirect"] = f"/protected-media/{image_key}"
    response["Cache-Control"] = _MEDIA_CACHE_CONTROL_200
    return response


def listings(
    request: HttpRequest,
    category_slug: str | None = None,
    city_slug: str | None = None,
) -> HttpResponse:
    """Public listings view for PUBLISHED ads.

    Filters: category subtree, city (with did-you-mean), price range.
    Sorting: ?sort= (DATE_NEW default).  Pagination: 24/page, HTMX partial.
    """
    # Rate limit (CR-10)
    if not request.headers.get("HX-Request") and not check_deep_link_render_rate_limit(request):
        logger.warning("Deep-link render rate limit exceeded (listings)")
        return rate_limited_response(json=False)
    # City: did-you-mean (F-6); service handles filtering
    effective_city = getattr(request, "current_city", None) or getattr(request, "preferred_city", None)
    suggested_city = suggest_city(effective_city) if effective_city and getattr(
        request, "current_city", None
    ) and not City.objects.filter(slug=effective_city).exists() else None
    # Category: breadcrumb + did-you-mean
    breadcrumb_category = Category.objects.filter(slug=category_slug, is_active=True).first() if category_slug else None
    suggested_category = None
    if category_slug:
        if not breadcrumb_category:
            suggested_category = _suggest_category(category_slug)
    elif request.GET.get("category"):
        suggested_category = _suggest_category(request.GET.get("category", ""))
    # Shared DTO + filter context (10-CQ-015)
    try:
        built = build_listings_context(
            category_slug=category_slug, city_slug=effective_city,
            breadcrumb_category=breadcrumb_category,
            sort=request.GET.get("sort", AdSort.DATE_NEW),
            min_price=request.GET.get("min_price"), max_price=request.GET.get("max_price"),
            purpose_slug=request.GET.get("listing_purpose"), condition_slug=request.GET.get("condition"),
            feature_slugs=request.GET.getlist("features"),
            user_id=request.user.id if request.user.is_authenticated else None,
            page=request.GET.get("page", 1),
        )
    except ValidationError:
        # A ?features= list over MAX_FEATURE_FILTER_SLUGS is rejected at the DTO
        # boundary (08-SRCH-001). A bare 400 has no body, so no i18n surface is
        # added; it is not a coercion or truncation.
        return HttpResponseBadRequest()
    params = built.params
    ads = ListingsQuery.build_queryset(params)
    # Pagination
    paginator = Paginator(ads, params.per_page)
    page_obj = paginator.get_page(params.page)
    if not paginator.count:
        logger.info("Empty listing results")
    context = {
        **built.filter_context,
        "page_obj": page_obj,
        "query": None,
        "suggested_category": suggested_category,
        "suggested_city": suggested_city,
        "breadcrumb_category": breadcrumb_category,
        "has_results": paginator.count > 0,
    }
    return render(
        request,
        "ads/partials/ad_list.html" if request.headers.get("HX-Request") else "ads/list.html",
        context,
    )


def _suggest_category(slug: str) -> str | None:
    """Suggest similar category slug using the shared fuzzy ladder."""
    all_slugs = list(
        Category.objects.filter(is_active=True).values_list("slug", flat=True)
    )
    return match_category(slug, all_slugs)
