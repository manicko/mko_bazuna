"""
JSON ad detail endpoint — ``GET /api/v1/ads/{id}/``.

The read-only JSON mirror of :func:`apps.ads.views.listings.ad_detail`: it applies
the **same** audience predicate (``account_state_q`` on the owner plus
``status=PUBLISHED``), records the **same** ``AD_VIEWED`` analytics side effect,
resolves the **same** per-session favorites state and answers with a structured
detail payload instead of a rendered template.

Audience parity is by construction: the queryset carries the identical
``account_state_q`` filter the HTML surface uses, so a banned / deleted /
declined / consent-withdrawn seller's ad is invisible here exactly as it is on
the website. A **missing** ad and an **audience-blocked** ad (draft,
unpublished, withdrawn or banned seller) both answer the **same** uniform 404
problem document — the distinction is never leaked (plan §2.5 / D5).

Rate limiting uses the shared single enforcement point ``rate_limit_check`` with
the dedicated ``API_PUBLIC_READ`` budget and the per-route ``api_detail``
namespace (R1/Q4); exhaustion is rendered as an RFC 9457 ``rate_limited`` problem
with a ``Retry-After`` header. The legacy HTML detail view keeps its existing
bare-429 shape untouched.
"""

import logging
from http import HTTPStatus
from typing import Any, Final

from django.http import HttpRequest, JsonResponse

from apps.ads.models import Ad
from apps.core.enums import AdStatus, AnalyticsEventType, RateLimitBudget
from apps.core.services.analytics import record_event
from apps.core.services.site_config import get_bot_username
from apps.core.utils.problem import problem, rate_limited_problem
from apps.search.services.rate_limit import rate_limit_check
from apps.users.services.account_state import account_state_q

logger = logging.getLogger(__name__)

# The rate-limit namespace for this route. Distinct per ``/api/v1/`` read route
# so exhausting this counter never throttles another endpoint (plan Q4).
_RATE_LIMIT_NAMESPACE: Final[str] = "api_detail"

# Stable ASCII ``type`` token for the uniform 404 problem document. Both a
# missing ad and an audience-blocked ad answer with this exact document, so the
# client cannot distinguish "does not exist" from "not visible to you"
# (plan §2.5 CWE-209 discipline).
_TYPE_NOT_FOUND: Final[str] = "not_found"

# The stable 404 detail. English msgid (cataloged later); never translated at
# runtime here (``problem`` carries the plain English source).
_DETAIL_NOT_FOUND: Final[str] = "Ad not found."


def detail_view(request: HttpRequest, ad_id: int) -> JsonResponse:
    """Return a single visible ad as a JSON detail payload.

    The ad is loaded with the HTML detail view's exact audience predicate
    (``account_state_q("user__")`` plus ``status=PUBLISHED``). A miss — whether
    the id does not exist or the ad is audience-blocked — yields one uniform 404
    problem document.

    On a hit the ``AD_VIEWED`` event is recorded for the seller (the seller, not
    the viewer, mirrors the HTML view), the caller's favorites state is resolved
    and the contact deep-link is assembled when the seller is contactable.
    """
    if not rate_limit_check(
        request,
        namespace=_RATE_LIMIT_NAMESPACE,
        budget=RateLimitBudget.API_PUBLIC_READ,
    ):
        return rate_limited_problem(RateLimitBudget.API_PUBLIC_READ)

    try:
        ad = (
            Ad.objects.select_related("category", "city", "user")
            .prefetch_related("images")
            .filter(account_state_q("user__"))
            .get(id=ad_id, status=AdStatus.PUBLISHED)
        )
    except Ad.DoesNotExist:
        # Missing id and audience-blocked ad share this exact document
        # (uniform 404 — no existence leak).
        return problem(HTTPStatus.NOT_FOUND, _TYPE_NOT_FOUND, _DETAIL_NOT_FOUND)

    # Record the view event for seller statistics — the same side effect, same
    # conditions (seller attribution) as the HTML detail view (plan Q3).
    record_event(
        AnalyticsEventType.AD_VIEWED,
        user_id=ad.user_id,  # Seller, not viewer
        ad_id=ad.id,
    )

    return JsonResponse(_serialize_ad_detail(ad, request))


def _serialize_ad_detail(ad: Ad, request: HttpRequest) -> dict[str, Any]:
    """Serialize a full ad detail payload.

    Extends the listings ``_serialize_ad`` shape with the detail-only fields the
    HTML detail page exposes: the localized description, a favorites flag for
    the current session and the contact deep-link. Media is exposed as URLs only
    (never bytes, plan stance #26).
    """
    return {
        "id": ad.id,
        "title": ad.get_title(),
        "description": ad.get_description(),
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
        "is_favorited": _is_favorited(ad, request),
        "contact_url": _contact_url(ad) if _seller_contactable(ad) else None,
    }


def _is_favorited(ad: Ad, request: HttpRequest) -> bool:
    """Return the current session's favorites state for *ad*.

    Identical source to the HTML detail view: an authenticated request checks
    ``ad.favorites`` (the ``AdFavorite`` reverse relation); anonymous requests
    always read ``False``.
    """
    if request.user.is_authenticated:
        return ad.favorites.filter(user_id=request.user.id).exists()
    return False


def _seller_contactable(ad: Ad) -> bool:
    """Return True only when the ad is published and the seller is contactable.

    Inlines the Zone R2 render condition the template's ``can_contact`` filter
    applies (``apps.core.services.contact._check_seller_contactable``): the ad is
    PUBLISHED, the seller has a ``telegram_id``, is not deleted, is not banned
    and has not withdrawn consent. Inlined here rather than imported because
    ``apps.core.services.contact`` is not part of the HTML detail mirror's
    imports (import-subset rule, plan §2.3) — only ``ad.user`` fields and
    ``AdStatus`` are consumed.
    """
    if ad.status != AdStatus.PUBLISHED:
        return False
    seller = ad.user
    if seller is None or seller.telegram_id is None:
        return False
    if seller.is_deleted or seller.is_banned:
        return False
    return seller.consent_revoked_at is None


def _contact_url(ad: Ad) -> str:
    """Assemble the Telegram contact deep-link for *ad*.

    Mirrors the ``{% telegram_deep_link "contact" ad.id %}`` tag's click-time
    URL: ``https://t.me/<bot_username>?start=contact_<ad_id>``. The bot username
    is sourced from the same admin-editable ``SiteConfig`` the HTML tag reads.
    """
    return f"https://t.me/{get_bot_username()}?start=contact_{ad.id}"


def _named(obj: Any) -> dict[str, Any] | None:
    """Return ``{"slug", "name"}`` for an optional related object, else ``None``."""
    if obj is None:
        return None
    return {"slug": obj.slug, "name": str(obj.name)}
