"""
Listings view for Mko Bazuna.

Public browsing of PUBLISHED ads with category subtree, city, price range filters.
HTMX-compatible MPA (no login required).
"""

import logging
from difflib import get_close_matches

from django.conf import settings
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import (
    FileResponse,
    Http404,
    HttpRequest,
    HttpResponse,
    HttpResponseBase,
    HttpResponseForbidden,
)
from django.shortcuts import render
from django.utils.translation import gettext as _
from django.views.decorators.vary import vary_on_headers

from apps.ads.models import Ad, AdImage
from apps.ads.services.listings_query import ListingsQuery, ListingsQueryParams
from apps.categories.models import Category
from apps.categories.services.lookup_resolution import CategoryLookupResolver
from apps.core.enums import AdSort, AdStatus, AnalyticsEventType
from apps.core.services.analytics import record_event
from apps.core.services.contact_rate_limit import check_deep_link_render_rate_limit
from apps.core.services.site_config import get_bot_username
from apps.locations.models import City
from apps.locations.services.city_suggestions import suggest_city
from apps.media.services.filesystem import assert_storage_key_contained

logger = logging.getLogger(__name__)


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
        return HttpResponse(status=429)
    try:
        ad = (
            Ad.objects.select_related("category", "city", "user")
            .prefetch_related("images", "features", "user__trust_score")
            .get(id=ad_id, status=AdStatus.PUBLISHED)
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
    # MultipleObjectsReturned -> HTTP 500 for viewers.
    key_q = (
        Q(image=image_key)
        | Q(thumbnail_small=image_key)  # type: ignore[operator]
        | Q(thumbnail_medium=image_key)  # type: ignore[operator]
        | Q(thumbnail_large=image_key)  # type: ignore[operator]
    )

    if not AdImage.objects.filter(key_q).exists():
        raise Http404("Image not found")

    # Staff users (moderators/admins) can view any image regardless of status
    if request.user.is_staff:
        if settings.DEBUG:
            response = _serve_image(image_key)
            response["Cache-Control"] = "no-cache"
            return response
        response = HttpResponse()
        response["X-Accel-Redirect"] = f"/protected-media/{image_key}"
        response["Cache-Control"] = "no-store"
        return response

    # Non-staff users: only serve images referenced by a PUBLISHED ad. A shared
    # seed key can be attached to several ads, so check existence across all of
    # them rather than the status of a single (arbitrary) row.
    if not AdImage.objects.filter(key_q, ad__status=AdStatus.PUBLISHED).exists():
        return HttpResponseForbidden(_("Access denied"))

    if settings.DEBUG:
        response = _serve_image(image_key)
        response["Cache-Control"] = "no-cache"
        return response

    response = HttpResponse()
    response["X-Accel-Redirect"] = f"/protected-media/{image_key}"
    response["Cache-Control"] = "no-store"
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
        return HttpResponse(status=429)
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
    # Params DTO + shared queryset
    params = ListingsQueryParams(
        category_slug=category_slug, city_slug=effective_city,
        min_price=request.GET.get("min_price"), max_price=request.GET.get("max_price"),
        purpose_slug=request.GET.get("listing_purpose"), condition_slug=request.GET.get("condition"),
        feature_slugs=request.GET.getlist("features"), sort=request.GET.get("sort", AdSort.DATE_NEW),
        user_id=request.user.id if request.user.is_authenticated else None,
        page=request.GET.get("page", 1), per_page=ListingsQuery.PER_PAGE,
    )
    ads = ListingsQuery.build_queryset(params)
    # Filter options (F4/F5)
    resolved_purposes, resolved_features, resolved_conditions = ListingsQuery.resolve_filter_options(breadcrumb_category)
    # Pagination
    paginator = Paginator(ads, params.per_page)
    page_obj = paginator.get_page(params.page)
    if not paginator.count:
        logger.info("Empty listing results")
    active_price_lo, active_price_hi = ListingsQuery.active_price_range(params)
    return render(request, "ads/partials/ad_list.html" if request.headers.get("HX-Request") else "ads/list.html", {
        "page_obj": page_obj, "query": None, "suggested_category": suggested_category,
        "suggested_city": suggested_city, "breadcrumb_category": breadcrumb_category,
        "current_category": category_slug, "current_city": effective_city, "current_sort": params.sort,
        "min_price": request.GET.get("min_price"), "max_price": request.GET.get("max_price"),
        "active_price_min": active_price_lo, "active_price_max": active_price_hi,
        "current_listing_purpose": request.GET.get("listing_purpose"),
        "current_features": request.GET.getlist("features"), "current_condition": request.GET.get("condition"),
        "resolved_purposes": resolved_purposes, "resolved_features": resolved_features,
        "resolved_conditions": resolved_conditions, "has_results": paginator.count > 0, "show_filters": True,
    })


def _suggest_category(slug: str) -> str | None:
    """Suggest similar category slug using difflib."""
    all_slugs = list(
        Category.objects.filter(is_active=True).values_list("slug", flat=True)
    )
    matches = get_close_matches(slug, all_slugs, n=1, cutoff=0.6)
    return matches[0] if matches else None
