"""
JSON moderation-review read endpoint — ``GET /api/v1/moderation/review/{id}/``.

The read-only JSON mirror of :func:`apps.moderation.views.review.moderation_review`:
it performs the **same** lookup (``Ad.objects.select_related("user", "category",
"city").prefetch_related("images")`` restricted to the approvable/rejectable
statuses ``{ON_MODERATION, ON_MODERATION_FAILED}``) and answers with the
structured fields the review template renders — the ad detail, the owner's
``telegram_id``, the localized category / city names, the localized description
and the photo URLs — instead of a rendered page.

A missing id and an ad outside the moderation status pair answer the **identical**
uniform 404 problem document (``type="not_found"``), so the distinction between
"absent" and "present but not in moderation" is never leaked (CWE-209) — the same
lookup semantics as the HTML ``get_object_or_404`` guard, rendered as an RFC 9457
problem document rather than an HTML 404 page.

The surface is staff-only: ``staff_required_api_problem`` (the RFC 9457
``/api/v1/`` variant in ``apps/core/utils/api_auth.py``) refuses an anonymous
request with a 401 problem, a non-staff request with a 403 problem, and a wrong
method with a 405 problem — none carries a ``WWW-Authenticate`` challenge
(09-API-010). The frozen legacy ``staff_required_api`` is POST-only and is
intentionally not used here. Rate limiting mirrors the HTML review view, which
has **none**.
"""

import logging
from http import HTTPStatus
from typing import Any, Final

from django.http import HttpRequest, JsonResponse

from apps.ads.models import Ad
from apps.core.enums import AdStatus
from apps.core.utils.api_auth import staff_required_api_problem
from apps.core.utils.problem import problem

logger = logging.getLogger(__name__)

# Stable ASCII ``type`` token for the uniform 404 (never translated).
TYPE_NOT_FOUND: Final[str] = "not_found"

# English msgid for the 404 detail (cataloged in ``ru``/``bs``/``en`` in the
# stage i18n batch; the English text is the msgid).
_DETAIL_NOT_FOUND: Final[str] = "Ad not found."

# The moderation statuses the HTML review lookup is restricted to.
_REVIEWABLE_STATUSES: Final[list[str]] = [
    AdStatus.ON_MODERATION,
    AdStatus.ON_MODERATION_FAILED,
]


@staff_required_api_problem
def review_view(request: HttpRequest, ad_id: int) -> JsonResponse:
    """Return the moderation review payload for *ad_id*.

    The lookup, status restriction and audience semantics are identical to the
    HTML ``moderation_review`` view: the same ``select_related`` /
    ``prefetch_related`` set and the same ``{ON_MODERATION,
    ON_MODERATION_FAILED}`` status filter. A missing id and every out-of-pair
    status answer the uniform 404 problem document.
    """
    ad = (
        Ad.objects.select_related("user", "category", "city")
        .prefetch_related("images")
        .filter(id=ad_id, status__in=_REVIEWABLE_STATUSES)
        .first()
    )
    if ad is None:
        # A missing id and an ad outside the moderation status pair answer the
        # identical uniform 404 problem document (CWE-209) — never an HTML 404.
        return problem(HTTPStatus.NOT_FOUND, TYPE_NOT_FOUND, _DETAIL_NOT_FOUND)

    return JsonResponse(_serialize_review(ad, locale=request.LANGUAGE_CODE))


def _serialize_review(ad: Ad, *, locale: str) -> dict[str, Any]:
    """Serialize an ad into the structured review payload the template renders.

    Field by field this mirrors ``admin/moderation/review.html``: the title and
    description are localized for the request locale (the same
    ``get_title``/``get_description`` chain the template's localized-content
    filters use), the category / city names come from the models' ``get_name``
    methods (the same helpers the template's ``get_category_name`` /
    ``get_city_name`` filters delegate to), the owner is identified by
    ``telegram_id``, the status is the display label, and the photos are exposed
    as URLs only (never bytes, plan stance #26).
    """
    return {
        "id": ad.id,
        "title": ad.get_title(),
        "status": ad.status,
        "status_display": ad.get_status_display(),
        "description": ad.get_description(locale=locale),
        "price": str(ad.price_amount) if ad.price_amount is not None else None,
        "currency": ad.price_currency,
        "category": _localized_named(ad.category, locale),
        "city": _localized_named(ad.city, locale),
        "telegram_id": ad.user.telegram_id,
        "image_urls": [image.image_url for image in ad.images.all()],
        "created_at": ad.created_at.isoformat() if ad.created_at else None,
        "absolute_url": ad.get_absolute_url(),
    }


def _localized_named(obj: Any, locale: str) -> dict[str, Any] | None:
    """Return ``{"slug", "name"}`` with a localized name, else ``None``.

    The localized name comes from the model's own ``get_name(locale)`` (the same
    call the template's ``get_category_name`` / ``get_city_name`` filters make),
    so the JSON name matches the rendered page for the request locale.
    """
    if obj is None:
        return None
    return {"slug": obj.slug, "name": str(obj.get_name(locale=locale))}


__all__ = [
    "TYPE_NOT_FOUND",
    "review_view",
]
