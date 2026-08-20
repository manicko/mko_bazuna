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

from apps.core.middleware.preferred_city import (
    PREFERRED_CITY_COOKIE_MAX_AGE,
    PREFERRED_CITY_COOKIE_NAME,
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
    slug = (request.POST.get("slug") or "").strip()
    if not slug or not City.objects.filter(slug=slug).exists():
        return JsonResponse({"error": "invalid_city"}, status=400)

    # Persist server-side for authenticated buyers (R-11).
    if request.user.is_authenticated:
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
    if request.COOKIES.get("consent_preferences") == "true":
        response.set_cookie(
            PREFERRED_CITY_COOKIE_NAME,
            slug,
            max_age=PREFERRED_CITY_COOKIE_MAX_AGE,
            httponly=True,
            samesite="Lax",
            secure=request.is_secure(),
        )
    logger.info("Set preferred_city to %s", slug)
    return response
