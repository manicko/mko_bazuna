"""
JSON seller-dashboard endpoint — ``GET /api/v1/dashboard/``.

The read-only JSON mirror of :func:`apps.ads.views.dashboard.dashboard`: it
applies the **same** create-time storage-consent gate, parses ``?time_range=``
with the **same** accepted values and fallback, and answers with a grouped
payload built from the **same** service tier
(:func:`apps.ads.services.dashboard_query.ads_by_status`, extracted in S2.2) and
the **same** :class:`~apps.analytics.services.seller_stats.SellerStats`
aggregation the HTML view renders.

Consent re-assertion (auditor A14). The HTML view gates the surface through its
view-local ``_seller_may_create_ad``, which is a thin wrapper over
:func:`apps.users.services.account_state.can_create_ad`. The API view re-asserts
through that **shared seam directly** — never by importing the HTML view's
private — and the refusal is an RFC 9457 ``consent_required`` problem document
(**R-L1**: absent / withdrawn consent and banned sellers are refused, **never** a
silent empty grouping). The refusal fires **before** any grouping is built, so a
forbidden account can never observe "no rows" in place of "not allowed".

The endpoint carries **no** rate limiter. It mirrors
:func:`apps.ads.views.dashboard.dashboard` exactly, and that HTML view has no
rate-limit check; the plan assigns no private-read budget namespace for the
dashboard route, so adding one would be a drift from the mirror rather than
parity. The session credential is the only access control on both surfaces.
"""

import logging
from http import HTTPStatus
from typing import Any, Final

from django.http import HttpRequest, JsonResponse
from django.utils.functional import Promise
from django.utils.translation import gettext_lazy as _

from apps.ads.services.dashboard_query import ads_by_status
from apps.analytics.services.seller_stats import SellerStats
from apps.core.enums import TimeRange
from apps.core.utils.api_auth import login_required_api
from apps.core.utils.problem import problem
from apps.users.services.account_state import can_create_ad

logger = logging.getLogger(__name__)

# Stable ASCII ``type`` token for the consent refusal (never translated).
_TYPE_CONSENT_REQUIRED: Final[str] = "consent_required"

# English msgid for the consent-refusal detail (cataloged in ``ru``/``bs``/``en``
# in the stage i18n batch; ``gettext_lazy`` defers resolution to render time so
# the string is translated for the active request locale, while the English text
# stays the msgid).
_DETAIL_CONSENT_REQUIRED: Final[str | Promise] = _(
    "Storage consent is required to view the seller dashboard."
)


@login_required_api
def dashboard_view(request: HttpRequest) -> JsonResponse:
    """Return the seller's ads grouped by status plus their stats.

    Mirrors the HTML dashboard 1:1:

    - **Consent gate.** A never-consented / withdrawn / banned account is
      refused with a 403 ``consent_required`` problem *before* any grouping is
      built (R-L1 — never a silent empty list).
    - **``?time_range=``.** The same accepted values as the HTML view
      (``all_time`` / ``30_days`` / ``7_days``); a missing or invalid value falls
      back to ``all_time``, exactly as the HTML view's ``TimeRange`` parse does.
    - **Grouping.** ``ads_by_status(request.user.id)`` (S2.2) grouped by
      ``AdStatus``; each group is serialized with the same ad fields the listings
      serializer exposes (D4).
    - **Stats.** ``SellerStats(request.user.id).get_stats(time_range)`` — the
      same ``total_views`` / ``total_contacts`` / ``ads_published`` /
      ``per_ad_stats`` block the HTML dashboard renders.
    """
    # Consent re-assertion through the shared ``can_create_ad`` seam (A14) —
    # the same underlying predicate ``_seller_may_create_ad`` wraps. Refuse
    # BEFORE building the groups so a forbidden account never receives an empty
    # grouping (R-L1).
    if not can_create_ad(request.user):
        logger.info(
            "Dashboard API refused for user %s: storage consent required",
            request.user.id,
        )
        return problem(
            HTTPStatus.FORBIDDEN,
            _TYPE_CONSENT_REQUIRED,
            _DETAIL_CONSENT_REQUIRED,
        )

    # Same accepted values and fallback as the HTML view: an unknown / missing
    # value resolves to ALL_TIME.
    selected_range_value = request.GET.get("time_range", TimeRange.ALL_TIME.value)
    try:
        time_range = TimeRange(selected_range_value)
    except ValueError:
        time_range = TimeRange.ALL_TIME

    seller_stats = SellerStats(request.user.id).get_stats(time_range)

    # Grouped querysets, keyed by AdStatus in the dashboard's canonical order.
    groups = ads_by_status(request.user.id)

    return JsonResponse(
        {
            "time_range": time_range.value,
            "time_range_options": [value for value, _ in TimeRange.choices()],
            "groups": {
                status.value: {
                    "count": group.count(),
                    "results": [_serialize_ad(ad) for ad in group],
                }
                for status, group in groups.items()
            },
            "stats": seller_stats,
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
