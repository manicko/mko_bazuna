"""
URL-city resolution middleware for Mko Bazuna.

Exposes ``request.current_city``: the city slug explicitly encoded in the
current request's URL, or ``None``. This is the *explicit* city override that
catalog/search views consult before falling back to the persisted preferred-city
value (cookie/DB).

Resolution priority (path form takes priority over query form):
    1. Path form ``/city/<slug>/`` (with or without trailing slash)
    2. Query form ``?city=<slug>``
    3. ``None``

The middleware does NOT query the ``City`` model -- slugs are passed through
unchanged. Validation (slug existence / did-you-mean) is the views' job (CR-7).
It also does NOT touch cookies: only the URL's explicit signals are read here.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from django.utils.deprecation import MiddlewareMixin

logger = logging.getLogger(__name__)

# Matches the explicit city path form: /city/<slug>/ or /city/<slug>.
# Compiled once at import time (no per-request recompilation).
_CITY_PATH_RE = re.compile(r"^/city/([^/]+)/?$")


class CityResolutionMiddleware(MiddlewareMixin):
    """Resolve the URL-encoded city slug into ``request.current_city``.

    ``process_request`` enriches ``request`` with ``request.current_city``
    (a ``str | None`` city slug, or ``None`` when no city is encoded in the
    URL) following the priority:

        1. Path form ``/city/<slug>/`` (with or without trailing slash) -> slug
        2. Query form ``?city=<slug>`` -> slug
        3. absent -> ``None``

    Slugs are passed through unvalidated: no ``City`` model lookup is performed
    here, and no cookies are read or written. Validation and did-you-mean
    suggestions are deferred to the views (CR-7).
    """

    def process_request(self, request: Any) -> None:
        """Set ``request.current_city`` to the URL-encoded slug or ``None``."""
        # Reset so the attribute is never stale from a prior request/state.
        request.current_city = None

        match = _CITY_PATH_RE.match(request.path)
        if match is not None:
            request.current_city = match.group(1)
            logger.debug("Resolved current_city from path: %r", request.current_city)
            return

        city = request.GET.get("city")
        if city is not None:
            request.current_city = city
            logger.debug("Resolved current_city from query: %r", city)
