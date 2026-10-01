"""
Rate limiting utility for search endpoints (autocomplete and search).

Uses Django's cache framework with atomic increment to enforce
a per-IP request limit within a sliding time window. Each consumer
uses an independent ``namespace`` so their counters do not interfere.
"""

import logging
from typing import Final

from django.core.cache import cache
from django.http import HttpRequest

from apps.core.utils.client_ip import get_client_ip

logger = logging.getLogger(__name__)

# Maximum number of requests per IP within the time window.
RATE_LIMIT_REQUESTS: Final[int] = 30

# Time window in seconds.
RATE_LIMIT_PERIOD: Final[int] = 60

# Cache key pattern — {namespace} and {ip} are replaced with the rate-limit
# namespace and the client's IP address respectively.
_RATE_LIMIT_KEY_PATTERN: Final[str] = "{namespace}_rl:{ip}"


def rate_limit_check(
    request: HttpRequest, *, namespace: str = "autocomplete"
) -> bool:
    """
    Check whether the given request is within the rate limit.

    Uses an atomic increment pattern via ``cache.add`` followed by
    ``cache.incr`` to initialise the counter at 1 and atomically
    increment on each subsequent request.  Returns ``True`` if the
    request is allowed, ``False`` if the caller has exceeded the limit.

    Each caller passes a distinct ``namespace`` so that autocomplete and
    search keep independent per-IP counters (default ``autocomplete``).

    Args:
        request: The incoming HTTP request.
        namespace: The rate-limit namespace (defaults to ``autocomplete``).

    Returns:
        ``True`` if the request may proceed, ``False`` if rate-limited.
    """
    ip = get_client_ip(request)
    key = _RATE_LIMIT_KEY_PATTERN.format(namespace=namespace, ip=ip)

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

