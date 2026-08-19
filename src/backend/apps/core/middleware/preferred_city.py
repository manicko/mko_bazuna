"""
Preferred-city middleware for Mko Bazuna.

Resolves the *effective* preferred city for each request (hybrid persistence):

- Authenticated buyers: the database value wins (``User.preferred_city``).
- Anonymous buyers: the ``preferred_city`` cookie (city slug) is the fallback.

The resolved slug is exposed to views/context as ``request.preferred_city``
(a ``str | None`` city slug) so catalog/search views can use it as a *default*
city filter. Stale cookies (a slug no longer present in ``cities``) are treated
as ``None`` and deleted during ``process_response``.

Writes never happen here — the cookie/DB is written only by the explicit
selection endpoint (``apps.search.views.preferred_city.set_preferred_city``).
"""

from __future__ import annotations

import logging
from typing import Any

from django.utils.deprecation import MiddlewareMixin

from apps.locations.models import City

logger = logging.getLogger(__name__)

PREFERRED_CITY_COOKIE_NAME = "preferred_city"
PREFERRED_CITY_COOKIE_MAX_AGE = 365 * 24 * 60 * 60  # 1 year


class PreferredCityMiddleware(MiddlewareMixin):
    """Resolve the effective preferred city and clean up stale cookies.

    ``process_request`` enriches ``request`` with ``request.preferred_city``
    (a ``str | None`` city slug) following the priority:

        authenticated + ``User.preferred_city`` set -> DB slug (wins)
        otherwise cookie slug (validated against ``City``) -> cookie slug
        stale / absent cookie                       -> ``None``

    ``process_response`` deletes a cookie that referenced a city no longer in
    the catalog (R-10 / stale-cookie tolerance).
    """

    def process_request(self, request: Any) -> None:
        """Set ``request.preferred_city`` to the effective city slug or ``None``."""
        # Reset both attributes so a request is never polluted by prior state.
        request.preferred_city = None
        request._preferred_city_stale_cookie = False

        # Guard on request.user so middleware ordering is robust: if
        # AuthenticationMiddleware has not run yet, fall back to the cookie.
        if (
            hasattr(request, "user")
            and request.user.is_authenticated
            and getattr(request.user, "preferred_city_id", None)
        ):
            # DB wins — do not consult the cookie for authenticated buyers.
            request.preferred_city = request.user.preferred_city.slug
            return

        cookie_slug = request.COOKIES.get(PREFERRED_CITY_COOKIE_NAME)
        if cookie_slug and City.objects.filter(slug=cookie_slug).exists():
            request.preferred_city = cookie_slug
            return

        if cookie_slug:
            # Stale cookie: intent recorded for cleanup in process_response.
            request._preferred_city_stale_cookie = True
            logger.info("Ignoring stale preferred_city cookie value: %r", cookie_slug)
        request.preferred_city = None

    def process_response(self, request: Any, response: Any) -> Any:
        """Delete a stale ``preferred_city`` cookie, if one was detected."""
        if getattr(request, "_preferred_city_stale_cookie", False):
            response.delete_cookie(PREFERRED_CITY_COOKIE_NAME)
        return response
