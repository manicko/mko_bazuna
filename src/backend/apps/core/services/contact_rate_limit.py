"""
Rate limiting for Telegram deep-link page renders (Contact-Us anti-spam).

Per-IP cap on pages that render Telegram contact deep-links, delegating the
atomic ``cache.add`` + ``cache.incr`` window bump shared with the search
autocomplete, login and bot rate limiters to
``apps.core.utils.cache.bump_rate_limit_window``.
"""

import logging
from typing import Final

from django.http import HttpRequest

from apps.core.utils.cache import bump_rate_limit_window
from apps.core.utils.client_ip import get_client_ip

logger = logging.getLogger(__name__)

RATE_LIMIT_REQUESTS: Final[int] = 60

RATE_LIMIT_PERIOD: Final[int] = 600  # 10 minutes

_RATE_LIMIT_KEY_PATTERN: Final[str] = "telegram_dl_rl:{ip}"


def check_deep_link_render_rate_limit(request: HttpRequest) -> bool:
    """Return True if the requesting IP is within the deep-link render limit.

    Returns True if the page may render its Telegram contact links, False if the
    IP has exceeded 60 renders in the last 600 seconds, and True (fail-open) when
    the cache is unreachable. The calling view is responsible for producing the
    429 response.
    """
    key = _RATE_LIMIT_KEY_PATTERN.format(ip=get_client_ip(request))
    return bump_rate_limit_window(key, RATE_LIMIT_REQUESTS, RATE_LIMIT_PERIOD)
