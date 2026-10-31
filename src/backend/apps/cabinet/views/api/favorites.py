"""
JSON favorites-list endpoint — ``GET /api/v1/favorites/``.

The read-only JSON mirror of :func:`apps.cabinet.views.favorites.favorites_list`:
it consumes the **same** shared favorites stack
(:func:`apps.ads.services.favorites.favorites_queryset`, S2.1) with the **same**
page size (:data:`apps.ads.services.favorites.PER_PAGE` = 24) and the **same**
ordering, and answers with the standard pagination envelope instead of a rendered
ad-card grid.

Ownership scoping is by construction: ``favorites_queryset(request.user)`` is
built from the caller's own favorites relation, so another user's favorites are
never visible on this surface. The same predicate that hides a withdrawn / banned
seller's ad from the cabinet HTML list (``account_state_q``) hides it here — the
two surfaces share one queryset, so parity on audience and ordering (including
equal-key ``-favorites__created_at`` ties) is guaranteed rather than re-pinned.

Ordering note (R2). Per the plan the shared ``favorites_queryset`` deliberately
carries **no** ``-id`` tiebreaker — the ``-id`` addition (R2) lives only in
``ListingsQuery._apply_sort`` and is the program's single approved ordering delta.
The extra ``favorites_queryset`` query already restricts to one user's favorites
(PUBLISHED + audience), so any equal-``created_at`` tie stays identical between the
HTML cabinet list and this endpoint because both run the one shared queryset.

Rate limiting mirrors the HTML cabinet favorites view, which has **none** — the
plan assigns no budget namespace to this read and the surface is session-gated, so
no limiter is added here.
"""

import logging
from typing import Any

from django.core.paginator import Paginator
from django.http import HttpRequest, JsonResponse

from apps.ads.services.favorites import PER_PAGE, favorites_queryset
from apps.core.utils.api_auth import login_required_api

logger = logging.getLogger(__name__)


@login_required_api
def favorites_list_view(request: HttpRequest) -> JsonResponse:
    """Return a page of the caller's favorited ads as a JSON envelope.

    Mirrors the HTML cabinet favorites list 1:1: the same shared
    ``favorites_queryset(request.user)`` (PUBLISHED + ``account_state_q`` audience,
    most-recently-favorited first), paginated at the same ``PER_PAGE`` (24). The
    caller's favorites only — ownership scoping is inherent in the queryset.
    """
    ads = favorites_queryset(request.user)

    paginator = Paginator(ads, PER_PAGE)
    page_obj = paginator.get_page(request.GET.get("page", 1))

    return JsonResponse(
        {
            "page": page_obj.number,
            "per_page": PER_PAGE,
            "total_count": paginator.count,
            "results_truncated": False,
            "results": [_serialize_ad(ad) for ad in page_obj.object_list],
            "has_next": page_obj.has_next(),
        }
    )


def _serialize_ad(ad: Any) -> dict[str, Any]:
    """Serialize one ad into the stable, structured JSON shape (D4).

    Keys match ``apps.ads.views.api.listings._serialize_ad`` so every read
    surface exposes the same ad shape. Media is exposed as URLs only (never
    bytes, plan stance #26); ``absolute_url`` uses the model's own
    ``get_absolute_url``.
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
