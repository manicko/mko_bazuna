"""
Preferred-city persistence view for Mko Bazuna.

Sets a ``preferred_city`` cookie (city slug, 30-day expiry) when a buyer clicks
a city suggestion in the catalog header. This is the **cookie-only** MVP per
Decision 018 — no schema change; registered-user profile persistence is deferred
to a dedicated buyer-profile task.
"""

import logging

from django.http import HttpRequest, JsonResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from apps.locations.models import City

logger = logging.getLogger(__name__)

# 30 days in seconds.
PREFERRED_CITY_COOKIE_MAX_AGE = 30 * 24 * 60 * 60


@require_POST
@never_cache
def set_preferred_city(request: HttpRequest) -> JsonResponse:
    """Persist the buyer's preferred city in a cookie.

    Reads the ``slug`` form field, validates the city exists, and sets the
    ``preferred_city`` cookie (30-day expiry, HttpOnly). Returns 400 for an
    unknown or missing slug.

    Args:
        request: The POST request carrying ``slug``.

    Returns:
        JSON ``{"ok": true}`` on success, or ``{"error": "invalid_city"}`` with
        HTTP 400 when the city slug is unknown.
    """
    slug = (request.POST.get("slug") or "").strip()
    if not slug or not City.objects.filter(slug=slug).exists():
        return JsonResponse({"error": "invalid_city"}, status=400)

    response = JsonResponse({"ok": True})
    response.set_cookie(
        "preferred_city",
        slug,
        max_age=PREFERRED_CITY_COOKIE_MAX_AGE,
        httponly=True,
        samesite="Lax",
        secure=request.is_secure(),
    )
    logger.info("Set preferred_city cookie to %s", slug)
    return response
