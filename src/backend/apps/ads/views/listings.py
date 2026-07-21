"""
Listings view for Mko Bazuna.

Public browsing of PUBLISHED ads with category subtree, city, price range filters.
HTMX-compatible MPA (no login required).
"""

import logging
from difflib import get_close_matches

from apps.ads.models import Ad, AdImage
from apps.categories.models import Category
from apps.core.enums import AdStatus, AdSort
from apps.locations.models import City
from apps.users.views.consent import is_consent_given
from django.http import Http404, HttpRequest, HttpResponse, HttpResponseForbidden
from django.shortcuts import render

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
    try:
        ad = (
            Ad.objects.select_related("category", "city", "user")
            .prefetch_related("images")
            .get(id=ad_id, status=AdStatus.PUBLISHED)
        )
    except Ad.DoesNotExist:
        raise Http404("Ad not found") from None

    context = {
        "ad": ad,
        "consent_shown": is_consent_given(request),
    }

    return render(request, "ads/detail.html", context)


def media_gate(request: HttpRequest, image_key: str) -> HttpResponse:
    """
    Media access gate for Ad images.

    Looks up AdImage by storage key, verifies parent Ad is PUBLISHED
    (or request is from a staff user), then returns X-Accel-Redirect
    to the internal nginx /protected-media/ location.

    Args:
        request: HTTP request
        image_key: Storage key (UUID v4 + .jpg)

    Returns:
        Empty 200 response with X-Accel-Redirect header, or 403/404
    """
    try:
        ad_image = AdImage.objects.select_related("ad").get(image=image_key)
    except AdImage.DoesNotExist:
        raise Http404("Image not found") from None

    # Allow staff users (moderators/admins) to view any image
    if request.user.is_staff:
        response = HttpResponse()
        response["X-Accel-Redirect"] = f"/protected-media/{image_key}"
        return response

    # Non-staff users: only serve images for PUBLISHED ads
    if ad_image.ad.status != AdStatus.PUBLISHED:
        return HttpResponseForbidden("Access denied")

    response = HttpResponse()
    response["X-Accel-Redirect"] = f"/protected-media/{image_key}"
    return response


def listings(
    request: HttpRequest,
    category_slug: str | None = None,
    city_slug: str | None = None,
) -> HttpResponse:
    """
    Public listings view for PUBLISHED ads.

    Filters:
        - Category: Shows ads in category subtree (get_descendants)
        - City: Exact match with did-you-mean suggestion
        - Price range: min_price and max_price query params

    Sorting:
        - ?sort=date_desc (default): newest first
        - ?sort=date_asc: oldest first
        - ?sort=price_asc: lowest price first
        - ?sort=price_desc: highest price first

    Args:
        request: HTTP request with optional query params
        category_slug: Optional category slug for filtering
        city_slug: Optional city slug for filtering

    Returns:
        Rendered listings page with ads and suggestions
    """
    # Start with only published ads
    ads = Ad.objects.filter(status=AdStatus.PUBLISHED).select_related(
        "category", "city", "user"
    )

    # Category filter (subtree)
    suggested_category = None
    if category_slug:
        try:
            category = Category.objects.get(slug=category_slug, is_active=True)
            # Get all descendants including self
            descendant_ids = category.get_descendants(include_self=True).values_list(
                "id", flat=True
            )
            ads = ads.filter(category_id__in=descendant_ids)
        except Category.DoesNotExist:
            # Category not found - no filter applied
            suggested_category = _suggest_category(category_slug)
    elif request.GET.get("category"):
        # Try to suggest category for invalid slug
        suggested_category = _suggest_category(request.GET.get("category", ""))

    # City filter with did-you-mean
    suggested_city = None
    if city_slug:
        try:
            city = City.objects.get(slug=city_slug)
            ads = ads.filter(city_id=city.id)
        except City.DoesNotExist:
            # City not found - provide did-you-mean suggestions
            suggested_city = _suggest_city(city_slug)
            # Show all ads but provide city suggestions
    elif request.GET.get("city"):
        suggested_city = _suggest_city(request.GET.get("city", ""))

    # Price range filter
    min_price = request.GET.get("min_price")
    max_price = request.GET.get("max_price")

    if min_price:
        try:
            ads = ads.filter(price__gte=int(min_price))
        except ValueError:
            pass  # Invalid price, ignore filter

    if max_price:
        try:
            ads = ads.filter(price__lte=int(max_price))
        except ValueError:
            pass  # Invalid price, ignore filter

    # Sorting
    sort = request.GET.get("sort", AdSort.DATE_NEW)
    if sort == AdSort.DATE_OLD:
        ads = ads.order_by("published_at")
    elif sort == AdSort.PRICE_LOW:
        ads = ads.order_by("price")
    elif sort == AdSort.PRICE_HIGH:
        ads = ads.order_by("-price")
    else:  # date_desc (default)
        ads = ads.order_by("-published_at")

    # Check for empty results
    has_results = ads.exists()
    if not has_results:
        logger.info("Empty listing results")

    context = {
        "ads": ads,
        "suggested_category": suggested_category,
        "suggested_city": suggested_city,
        "current_category": category_slug,
        "current_city": city_slug,
        "current_sort": sort,
        "has_results": has_results,
        "consent_shown": is_consent_given(request),
    }

    # HTMX partial rendering support
    if request.headers.get("HX-Request"):
        return render(request, "ads/list.html", context)

    return render(request, "ads/list.html", context)


def _suggest_category(slug: str) -> str | None:
    """
    Suggest similar category slug using difflib.

    Args:
        slug: The slug to find suggestions for

    Returns:
        Suggested slug or None
    """
    all_slugs = list(
        Category.objects.filter(is_active=True).values_list("slug", flat=True)
    )
    matches = get_close_matches(slug, all_slugs, n=1, cutoff=0.6)
    return matches[0] if matches else None


def _suggest_city(slug: str) -> str | None:
    """
    Suggest similar city slug using difflib.

    Args:
        slug: The slug to find suggestions for

    Returns:
        Suggested slug or None
    """
    all_slugs = list(City.objects.values_list("slug", flat=True))
    matches = get_close_matches(slug, all_slugs, n=1, cutoff=0.6)
    return matches[0] if matches else None
