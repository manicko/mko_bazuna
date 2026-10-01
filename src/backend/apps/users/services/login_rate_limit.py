"""
Rate limiting for login token issuance.

Reuses Django's cache framework with atomic increment to enforce
a per-IP request limit within a sliding time window.
Mirrors the pattern in ``apps/search/services/rate_limit.py`` but with
tighter limits for the security-sensitive login endpoint.
"""

import logging
from typing import Final

from django.core.cache import cache
from django.http import HttpRequest

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

    Uses an atomic increment pattern via ``cache.add`` followed by
    ``cache.incr`` to initialise the counter at 1 and atomically
    increment on each subsequent request.  Returns ``True`` if the
    request is allowed, ``False`` if the caller has exceeded the limit.

    Args:
        request: The incoming HTTP request.

    Returns:
        ``True`` if the request may proceed, ``False`` if rate-limited.
    """
    ip = get_client_ip(request)
    key = _RATE_LIMIT_KEY_PATTERN.format(ip=ip)

    try:
        # cache.add returns True if the key was created (first request).
        added = cache.add(key, 1, timeout=RATE_LIMIT_PERIOD)
        if added:
            current = 1
        else:
            # Atomic increment on existing key.
            current = cache.incr(key)

        return current <= RATE_LIMIT_REQUESTS

    except ValueError:
        # Key expired between the add/incr calls — treat as a fresh start.
        cache.set(key, 1, timeout=RATE_LIMIT_PERIOD)
        return True

