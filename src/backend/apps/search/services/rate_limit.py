"""
Rate limiting utility for search endpoints (autocomplete and search).

Uses Django's cache framework with atomic increment to enforce
a per-IP request limit within a sliding time window. Each consumer
uses an independent ``namespace`` so their counters do not interfere.
The window bump is delegated to
``apps.core.utils.cache.bump_rate_limit_window``.
"""

import logging

from django.http import HttpRequest

from apps.core.enums import RateLimitBudget
from apps.core.utils.cache import bump_rate_limit_window
from apps.core.utils.client_ip import get_client_ip

logger = logging.getLogger(__name__)

# Maximum number of requests per IP within the time window (08-SRCH-010).
RATE_LIMIT_REQUESTS: int = RateLimitBudget.AUTOCOMPLETE.requests

# Time window in seconds.
RATE_LIMIT_PERIOD: int = RateLimitBudget.AUTOCOMPLETE.period

# Cache key pattern — {namespace} and {ip} are replaced with the rate-limit
# namespace and the client's IP address respectively.
_RATE_LIMIT_KEY_PATTERN: str = "{namespace}_rl:{ip}"


def rate_limit_check(
    request: HttpRequest, *, namespace: str = "autocomplete"
) -> bool:
    """
    Check whether the given request is within the rate limit.

    Delegates the atomic ``cache.add`` + ``cache.incr`` window bump to
    ``apps.core.utils.cache.bump_rate_limit_window``. Returns ``True`` if the
    request is allowed, ``False`` if the caller has exceeded the limit, and
    ``True`` (fail-open) when the cache is unreachable.

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
    return bump_rate_limit_window(key, RATE_LIMIT_REQUESTS, RATE_LIMIT_PERIOD)

