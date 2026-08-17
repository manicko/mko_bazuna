"""
Rate limiting for Telegram bot photo uploads.

Mirrors ``apps.search.services.rate_limit`` using Django's cache framework
(LocMemCache in dev / a single bot process; shared Redis cache in production)
to cap photo uploads per seller within a sliding window and blunt burst abuse.
"""

import logging
from typing import Final

from django.core.cache import cache

logger = logging.getLogger(__name__)

# Maximum uploads a seller may attempt within the sliding window.
RATE_LIMIT_REQUESTS: Final[int] = 10

# Sliding window length in seconds.
RATE_LIMIT_PERIOD: Final[int] = 60

# Cache key pattern keyed by the seller's user_id.
_RATE_LIMIT_KEY_PATTERN: Final[str] = "bot_upload_rl:{user_id}"


def check_upload_rate_limit(
    user_id: int,
    limit: int = RATE_LIMIT_REQUESTS,
    period: int = RATE_LIMIT_PERIOD,
) -> bool:
    """Return True if the seller is within the upload rate limit.

    Uses the atomic ``cache.add`` + ``cache.incr`` pattern (identical to the
    search autocomplete rate limiter) so concurrent increments are serialized
    by the cache backend. Returns ``False`` when the limit is exceeded.

    Args:
        user_id: The ad-owner's id (from FSM state).
        limit: Max uploads allowed in the window.
        period: Window length in seconds.

    Returns:
        ``True`` if the upload may proceed, ``False`` if rate-limited.
    """
    key = _RATE_LIMIT_KEY_PATTERN.format(user_id=user_id)

    try:
        # cache.add returns True if the key was created (first request).
        added = cache.add(key, 1, timeout=period)
        if added:
            current = 1
        else:
            # Atomic increment on the existing key.
            current = cache.incr(key)

        return current <= limit

    except ValueError:
        # Key expired between the add/incr calls — treat as a fresh start.
        cache.set(key, 1, timeout=period)
        return True
