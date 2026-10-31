"""
JSON favorites toggle endpoint — ``POST /api/v1/favorites/{ad_id}/toggle/``.

The write half of the favorites gap (plan §2.4 row 15; the read half,
``GET /api/v1/favorites/``, shipped at S2.4). It is the JSON sibling of the HTML
heart toggle :func:`apps.ads.views.favorite.toggle_favorite` and consumes the
**same** shared favorites stack (:func:`apps.ads.services.favorites.toggle_favorite`,
S2.1) — one mutator for both surfaces, no API-only business predicate.

Auth is session-only: ``login_required_api`` refuses an anonymous request with a
401 ``unauthenticated`` problem (no ``WWW-Authenticate``, 09-API-010) **before**
the method gate, so an anonymous ``POST`` is 401 rather than 405 (mirrors the
frozen ``staff_required_api`` branch order). A non-POST request from an
authenticated session answers a 405 ``method_not_allowed`` problem with an
``Allow: POST`` header.

The body is a small Pydantic ``BaseInputModel`` DTO (``{"ad_id": <int>}``); a
malformed or missing field answers a 422 ``validation_failed`` problem built by
``validation_problem`` (the S1+ helper, not the frozen ``api_bulk`` 422 shape).
The rate limit is checked **first**, before the body is parsed, mirroring the
``api_bulk`` ordering: the whole ``api_write`` namespace shares one budget
(``RateLimitBudget.API_WRITE``, 30 req / 60 s), so exhausting it answers a 429
``rate_limited`` problem with a ``Retry-After`` header.

A missing or non-PUBLISHED ad makes the service raise ``Ad.DoesNotExist``; this
view maps that to the **uniform** 404 problem (``type="not_found"``), mirroring
the HTML toggle's ``Http404`` refusal.

No CSRF exemption is applied: the endpoint relies on the middleware chain as-is,
exactly like every other ``/api/v1/`` write (writes are POST-only).
"""

import logging
from http import HTTPStatus
from typing import Final

from django.http import HttpRequest, JsonResponse
from django.utils.functional import Promise
from django.utils.translation import gettext_lazy as _
from pydantic import ValidationError

from apps.ads.models import Ad
from apps.ads.services.favorites import toggle_favorite
from apps.core.schemas import BaseInputModel
from apps.core.utils.api_auth import TYPE_METHOD_NOT_ALLOWED, login_required_api
from apps.core.utils.problem import (
    problem,
    rate_limited_problem,
    validation_problem,
)
from apps.search.services.rate_limit import RateLimitBudget, rate_limit_check

logger = logging.getLogger(__name__)

# Stable ASCII ``type`` token for the uniform 404 (never translated). The same
# token the ad-detail endpoint uses for a missing / invisible ad (CWE-209).
TYPE_NOT_FOUND: Final[str] = "not_found"

# English msgids for the detail strings (cataloged in ``ru``/``bs``/``en`` in the
# stage i18n batch; ``gettext_lazy`` defers resolution to render time so the text
# is translated for the active request locale while English stays the msgid).
_DETAIL_NOT_FOUND: Final[str | Promise] = _("Ad not found.")
_DETAIL_METHOD_NOT_ALLOWED: Final[str | Promise] = _("Method not allowed.")

# The rate-limit namespace for every authenticated ``/api/v1/`` write. All
# writes share one key namespace (plan Q4/§2.3), so exhausting the write budget
# throttles writes regardless of which write route spent it.
_RATE_LIMIT_NAMESPACE: Final[str] = "api_write"

# The only allowed method for this write endpoint.
_ALLOWED_METHODS: Final[tuple[str, ...]] = ("POST",)


class FavoriteToggleInput(BaseInputModel):
    """Client-input DTO for the favorites toggle body.

    ``extra="forbid"`` (from :class:`BaseInputModel`) rejects unknown keys, so a
    misspelled field fails fast with a 422 rather than being silently dropped.
    """

    ad_id: int


@login_required_api
def favorite_toggle_view(request: HttpRequest, ad_id: int) -> JsonResponse:
    """Toggle the caller's favorite for the PUBLISHED ad ``ad_id``.

    ``login_required_api`` runs the identity check first (anonymous → 401
    problem, no ``WWW-Authenticate``); this view then applies the method gate,
    the rate limit (before parsing, mirroring ``api_bulk``), the DTO validation,
    and finally the shared toggle service.

    On success returns the post-toggle machine state
    ``{"ad_id", "is_favorited", "favorites_count"}`` carried by
    :class:`apps.ads.services.favorites.FavoriteToggleResult`.
    """
    if request.method not in _ALLOWED_METHODS:
        response = problem(
            HTTPStatus.METHOD_NOT_ALLOWED,
            TYPE_METHOD_NOT_ALLOWED,
            _DETAIL_METHOD_NOT_ALLOWED,
        )
        response["Allow"] = ", ".join(_ALLOWED_METHODS)
        return response

    # Rate limit FIRST, before parsing: the whole write namespace shares one
    # budget, so the cost is charged even for a malformed body (api_bulk order).
    if not rate_limit_check(
        request,
        namespace=_RATE_LIMIT_NAMESPACE,
        budget=RateLimitBudget.API_WRITE,
    ):
        return rate_limited_problem(RateLimitBudget.API_WRITE)

    try:
        # The body is parsed and validated for DTO symmetry with the plan row;
        # the URL id is authoritative (the path names the ad to toggle), so the
        # body's ``ad_id`` is validated but never a second source of truth.
        FavoriteToggleInput.model_validate_json(request.body)
    except ValidationError as exc:
        logger.warning("Invalid favorites toggle request body: %s", exc)
        return validation_problem(exc)

    try:
        result = toggle_favorite(request.user, ad_id)
    except Ad.DoesNotExist:
        # Uniform 404: a missing id and a non-PUBLISHED ad answer identically
        # (CWE-209), mirroring the HTML toggle's Http404 refusal.
        return problem(HTTPStatus.NOT_FOUND, TYPE_NOT_FOUND, _DETAIL_NOT_FOUND)

    return JsonResponse(
        {
            "ad_id": result.ad.id,
            "is_favorited": result.is_favorited,
            "favorites_count": result.favorites_count,
        }
    )


__all__ = [
    "TYPE_NOT_FOUND",
    "FavoriteToggleInput",
    "favorite_toggle_view",
]
