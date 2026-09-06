"""
Rate limiting for Telegram deep-link page renders (Contact-Us anti-spam).

Per-IP cap on pages that render Telegram contact deep-links, using the atomic
``cache.add`` + ``cache.incr`` idiom shared with the search autocomplete and
login rate limiters. Mirrors ``apps/search/services/rate_limit.py``.
"""

import logging
from typing import Final

from django.core.cache import cache
from django.http import HttpRequest

logger = logging.getLogger(__name__)

RATE_LIMIT_REQUESTS: Final[int] = 60

RATE_LIMIT_PERIOD: Final[int] = 600  # 10 minutes

_RATE_LIMIT_KEY_PATTERN: Final[str] = "telegram_dl_rl:{ip}"


def _get_client_ip(request: HttpRequest) -> str:
    """Extract the client IP, honoring X-Forwarded-For from nginx."""
    x_forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded:
        return x_forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "unknown")


def check_deep_link_render_rate_limit(request: HttpRequest) -> bool:
    """Return True if the requesting IP is within the deep-link render limit.

    Mirrors ``apps.search.services.rate_limit.rate_limit_check``. Returns True
    if the page may render its Telegram contact links, False if the IP has
    exceeded 60 renders in the last 600 seconds. The calling view is
    responsible for producing the 429 response.
    """
    key = _RATE_LIMIT_KEY_PATTERN.format(ip=_get_client_ip(request))

    try:
        added = cache.add(key, 1, timeout=RATE_LIMIT_PERIOD)
        if added:
            current = 1
        else:
            current = cache.incr(key)

        return current <= RATE_LIMIT_REQUESTS

    except ValueError:
        cache.set(key, 1, timeout=RATE_LIMIT_PERIOD)
        return True
