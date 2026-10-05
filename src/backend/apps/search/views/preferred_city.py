"""
Preferred-city persistence view for Mko Bazuna.

Sets a ``preferred_city`` cookie (city slug, 1-year expiry, HttpOnly) when a
buyer selects a city in the catalog header. For authenticated buyers the city is
also persisted server-side on ``User.preferred_city`` (hybrid persistence per
Decision 018). Guests get the cookie only.
"""

import logging

from django.http import HttpRequest, JsonResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from apps.core.middleware.preferred_city import CONSENT_PREFERENCES_COOKIE
from apps.core.utils.preferred_city_cookie import (
    expire_preferred_city_cookie,
    set_preferred_city_cookie,
)
from apps.locations.models import City

logger = logging.getLogger(__name__)


@require_POST
@never_cache
def set_preferred_city(request: HttpRequest) -> JsonResponse:
    """Persist the buyer's preferred city (cookie + DB for authenticated users).

    Reads the ``slug`` form field, validates the city exists, and sets the
    ``preferred_city`` cookie (1-year expiry, HttpOnly). For authenticated users
    the selected city is also written to ``User.preferred_city``. Returns 400
    for an unknown or missing slug; a GET is rejected with 405.

    Args:
        request: The POST request carrying ``slug``.

    Returns:
        JSON ``{"ok": true}`` on success, or ``{"error": "invalid_city"}`` with
        HTTP 400 when the city slug is unknown.
    """
    # "Clear preferred city" intent (Decision 23 D-2 / D-P1). Accepts either an
    # explicit ``action=clear`` or a present-but-empty ``slug`` (POST slug="").
    # A *missing* slug key or an unknown non-empty slug is invalid input -> 400.
    clear_action = request.POST.get("action") == "clear"
    slug_present_empty = (
        "slug" in request.POST and not (request.POST.get("slug") or "").strip()
    )
    if clear_action or slug_present_empty:
        response = JsonResponse({"ok": True})
        # Mirror the write's attributes on the deletion Set-Cookie. Django's
        # delete_cookie() (5.2) exposes no ``secure`` parameter, so it cannot
        # emit ``Secure`` to match the HTTPS write; the only one-flag route back
        # through it is ``samesite="none"``, which would make this buyer-scoped
        # cookie cross-site capable. Emit an already-expired cookie directly.
        expire_preferred_city_cookie(response, secure=request.is_secure())
        if request.user.is_authenticated:
            request.user.preferred_city = None
            request.user.save(update_fields=["preferred_city"])
        logger.info(
            "Cleared preferred_city for user=%s", getattr(request.user, "id", None)
        )
        return response

    slug = (request.POST.get("slug") or "").strip()
    if not slug or not City.objects.filter(slug=slug).exists():
        return JsonResponse({"error": "invalid_city"}, status=400)

    # Persist server-side for authenticated buyers (R-11), but not for a
    # declined one: their column was cleared on decline (06-PII-110) and a
    # header click must not re-set it. The gate is the plain ``is_declined``
    # attribute — BLOCK 6's account_state_q() would add a cross-app import and
    # a second spelling of the account-state rule for a single boolean.
    if request.user.is_authenticated and not request.user.is_declined:
        try:
            city = City.objects.get(slug=slug)
            request.user.preferred_city = city
            request.user.save(update_fields=["preferred_city"])
        except City.DoesNotExist:
            # Guarded by the validation above; a race is non-fatal.
            logger.warning("Preferred city %s disappeared during save", slug)

    response = JsonResponse({"ok": True})
    # Gate the preference cookie behind preferences consent (T-06c / ePrivacy).
    # The authenticated user's DB preference still applies without the cookie.
    if request.COOKIES.get(CONSENT_PREFERENCES_COOKIE) == "true":
        set_preferred_city_cookie(response, slug, secure=request.is_secure())
    logger.info("Set preferred_city to %s", slug)
    return response
