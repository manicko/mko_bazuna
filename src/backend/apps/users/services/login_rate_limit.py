"""
Rate limiting for login token issuance.

Reuses Django's cache framework with atomic increment to enforce
a per-IP request limit within a sliding time window, delegating the
window bump to ``apps.core.utils.cache.bump_rate_limit_window`` but with
tighter limits for the security-sensitive login endpoint.
"""

import logging
from typing import Final

from django.http import HttpRequest

from apps.core.utils.cache import bump_rate_limit_window
from apps.core.utils.client_ip import get_client_ip

logger = logging.getLogger(__name__)

# Maximum number of login token requests per IP within the time window.
RATE_LIMIT_REQUESTS: Final[int] = 10

# Time window in seconds.
RATE_LIMIT_PERIOD: Final[int] = 60

# Cache key pattern — {ip} is replaced with the client's IP address.
_RATE_LIMIT_KEY_PATTERN: Final[str] = "login_rl:{ip}"


def login_rate_limit_check(request: HttpRequest) -> bool:
    """
    Check whether the given request is within the login rate limit.

    Delegates the atomic ``cache.add`` + ``cache.incr`` window bump to
    ``apps.core.utils.cache.bump_rate_limit_window``.  Returns ``True`` if the
    request is allowed, ``False`` if the caller has exceeded the limit, and
    ``True`` (fail-open) when the cache is unreachable.

    Args:
        request: The incoming HTTP request.

    Returns:
        ``True`` if the request may proceed, ``False`` if rate-limited.
    """
    ip = get_client_ip(request)
    key = _RATE_LIMIT_KEY_PATTERN.format(ip=ip)
    return bump_rate_limit_window(key, RATE_LIMIT_REQUESTS, RATE_LIMIT_PERIOD)

