"""

Listings view for Mko Bazuna.



Public browsing of PUBLISHED ads with category subtree, city, price range filters.

HTMX-compatible MPA (no login required).

"""



import logging

from difflib import get_close_matches

from apps.analytics.models import AnalyticsEvent


from apps.ads.models import Ad, AdImage

from apps.categories.models import Category

from apps.core.enums import AdStatus, AdSort, AnalyticsEventType

from apps.locations.models import City

from django.http import Http404, HttpRequest, HttpResponse, HttpResponseForbidden

from django.shortcuts import render

from django.core.paginator import Paginator
from django.db.models import Q
from django.conf import settings



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

    # Record the view event for seller statistics
    AnalyticsEvent.objects.create(
        event_type=AnalyticsEventType.AD_VIEWED,
        user_id=ad.user_id,  # Seller, not viewer
        ad_id=ad.id,
    )

    context = {
        "ad": ad,
        "breadcrumb_category": ad.category,
        "bot_username": settings.BOT_USERNAME,
        "is_favorited": (
            ad.favorites.filter(user_id=request.user.id).exists()
            if request.user.is_authenticated
            else False
        ),
    }

    return render(request, "ads/detail.html", context)





def _serve_image(image_key: str) -> HttpResponse:
    """Serve a media file directly (development fallback without nginx).

    Uses ``FileResponse`` to stream the file from ``MEDIA_ROOT``.  In production,
    the ``media_gate`` view returns an ``X-Accel-Redirect`` header that nginx
    intercepts; this helper is only used when ``DEBUG=True``.
    """
    file_path = settings.MEDIA_ROOT / image_key
    if not file_path.exists():
        raise Http404("Image not found")
    with open(file_path, "rb") as f:
        data = f.read()
    return HttpResponse(data, content_type="image/jpeg")


def media_gate(request: HttpRequest, image_key: str) -> HttpResponse:
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
            return _serve_image(image_key)
        response = HttpResponse()
        response["X-Accel-Redirect"] = f"/protected-media/{image_key}"
        return response

    # Non-staff users: only serve images referenced by a PUBLISHED ad. A shared
    # seed key can be attached to several ads, so check existence across all of
    # them rather than the status of a single (arbitrary) row.
    if not AdImage.objects.filter(key_q, ad__status=AdStatus.PUBLISHED).exists():
        return HttpResponseForbidden("Access denied")

    if settings.DEBUG:
        return _serve_image(image_key)

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



    Pagination:

        - 24 ads per page via Django Paginator

        - HTMX partial renders only the ad grid fragment



    Args:

        request: HTTP request with optional query params

        category_slug: Optional category slug for filtering

        city_slug: Optional city slug for filtering



    Returns:

        Rendered listings page (full or HTMX partial)

    """

    PER_PAGE = 24



    # Start with only published ads
    # Prefetch trust scores to avoid N+1 in render_trust_badge template tag.
    ads = (
        Ad.objects.filter(status=AdStatus.PUBLISHED)
        .select_related("category", "city", "user")
        .prefetch_related("user__trust_score")
    )



    # Category filter (subtree)

    suggested_category = None

    breadcrumb_category = None

    if category_slug:

        try:

            category = Category.objects.get(slug=category_slug, is_active=True)

            breadcrumb_category = category

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



    # City filter with did-you-mean. Priority: URL path ``city_slug`` wins, then
    # an explicit ``?city=`` param (did-you-mean only), then the
    # middleware-resolved preferred city as the *default* filter (R-06).
    suggested_city = None
    effective_city = None
    if city_slug:
        effective_city = city_slug
        try:
            city = City.objects.get(slug=city_slug)
            ads = ads.filter(city_id=city.id)
        except City.DoesNotExist:
            # City not found - provide did-you-mean suggestions
            suggested_city = _suggest_city(city_slug)
            # Show all ads but provide city suggestions
    elif request.GET.get("city"):
        suggested_city = _suggest_city(request.GET.get("city", ""))
    else:
        # Default fallback to the preferred city (middleware-validated slug).
        preferred_city = getattr(request, "preferred_city", None)
        if preferred_city:
            effective_city = preferred_city
            try:
                city = City.objects.get(slug=preferred_city)
                ads = ads.filter(city_id=city.id)
            except City.DoesNotExist:
                # Second line of defense for a stale preference: no filter.
                pass



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



    # Annotate favorite state for the card hearts (FT-001)

    from apps.ads.views.favorite import annotate_favorites

    ads = annotate_favorites(ads, request.user.id if request.user.is_authenticated else None)



    # Paginate results

    paginator = Paginator(ads, PER_PAGE)

    page_number = request.GET.get("page", 1)

    page_obj = paginator.get_page(page_number)



    total_count = int(paginator.count)

    has_results = total_count > 0

    if not has_results:

        logger.info("Empty listing results")



    context = {

        "page_obj": page_obj,

        "suggested_category": suggested_category,

        "suggested_city": suggested_city,

        "breadcrumb_category": breadcrumb_category,

        "current_category": category_slug,

        "current_city": effective_city,

        "current_sort": sort,

        "min_price": min_price,

        "max_price": max_price,

        "has_results": has_results,

    }



    # HTMX partial rendering support

    if request.headers.get("HX-Request"):

        return render(request, "ads/partials/ad_list.html", context)



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
