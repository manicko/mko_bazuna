"""JS-execution proof gate for contact-link protection (Spec 18, CR-11).

A one-line inline script in the footer sets a ``js=true`` session cookie on
pages that render contact links. Real browsers run the script and send the
cookie back; non-JS scrapers (``requests``/``urllib``) never do. This
middleware reads the cookie and exposes ``request.js_verified``.

A dedicated context processor (``apps.core.context_processors.js_verified``)
bridges that attribute into the top-level template context that the
``{% telegram_deep_link %}`` tag reads.
"""

from __future__ import annotations

from django.http import HttpRequest
from django.utils.deprecation import MiddlewareMixin


class JSExecutionMiddleware(MiddlewareMixin):
    """Read the ``js`` cookie and set ``request.js_verified``.

    ``process_request`` sets ``request.js_verified`` to ``True`` only when the
    ``js`` cookie value is exactly ``"true"``. Any other value (absent,
    ``"false"``, garbage) yields ``False``, so non-JS clients never clear the
    contact-link gate.
    """

    def process_request(self, request: HttpRequest) -> None:
        request.js_verified = request.COOKIES.get("js") == "true"
