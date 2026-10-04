"""
Rate limiting for the Telegram bot.

Covers both photo uploads (seller, high-frequency) and the ``/start contact_us``
deep-link trigger (buyer, abuse-prone) using Django's cache framework (LocMemCache
in dev / a single bot process; shared Redis cache in production) to cap requests
per actor within a sliding window and blunt burst abuse.

Both limiters mirror ``apps.search.services.rate_limit`` via the atomic
``cache.add`` + ``cache.incr`` idiom.
"""

import logging
from typing import Final

from asgiref.sync import sync_to_async

from apps.core.utils.cache import bump_rate_limit_window

logger = logging.getLogger(__name__)

# Maximum uploads a seller may attempt within the sliding window.
RATE_LIMIT_REQUESTS: Final[int] = 10

# Sliding window length in seconds.
RATE_LIMIT_PERIOD: Final[int] = 60

# Cache key pattern keyed by the seller's user_id.
_RATE_LIMIT_KEY_PATTERN: Final[str] = "bot_upload_rl:{user_id}"


@sync_to_async
def check_upload_rate_limit(
    user_id: int,
    limit: int = RATE_LIMIT_REQUESTS,
    period: int = RATE_LIMIT_PERIOD,
) -> bool:
    """Return True if the seller is within the upload rate limit.

    Delegates the atomic ``cache.add`` + ``cache.incr`` window bump to
    ``apps.core.utils.cache.bump_rate_limit_window`` (shared with the contact,
    support, login and web-tier guards). Returns ``False`` when the limit is
    exceeded, and ``True`` (fail-open) when the cache is unreachable.

    Args:
        user_id: The ad-owner's id (from FSM state).
        limit: Max uploads allowed in the window.
        period: Window length in seconds.

    Returns:
        ``True`` if the upload may proceed, ``False`` if rate-limited.
    """
    key = _RATE_LIMIT_KEY_PATTERN.format(user_id=user_id)
    return bump_rate_limit_window(key, limit, period)


# --- contact-us deep-link limiter -------------------------------------------
# Distinct names from the upload limiter (which uses 10/60) to avoid rebinding
# the shared ``RATE_LIMIT_REQUESTS`` / ``RATE_LIMIT_PERIOD`` constants above.

# Maximum contact_us /start triggers per user within the sliding window.
CONTACT_RATE_LIMIT_REQUESTS: Final[int] = 5

# Sliding window length in seconds (10 minutes — short enough to deter spam,
# long enough to cover a support spike).
CONTACT_RATE_LIMIT_PERIOD: Final[int] = 600

# Cache key pattern keyed by the stable Telegram user_id (cross-chat identity).
_CONTACT_RATE_LIMIT_KEY_PATTERN: Final[str] = "bot_contact_rl:{user_id}"


@sync_to_async
def check_contact_start_rate_limit(
    user_id: int,
    limit: int = CONTACT_RATE_LIMIT_REQUESTS,
    period: int = CONTACT_RATE_LIMIT_PERIOD,
) -> bool:
    """Return ``True`` if the user is within the contact-start rate limit.

    Per-user sliding-window limiter for ``/start contact_us`` triggers, delegating
    the window bump to ``apps.core.utils.cache.bump_rate_limit_window``. Returns
    ``False`` when the limit is exceeded, and ``True`` (fail-open) when the cache
    is unreachable.

    Args:
        user_id: The Telegram user's id (``message.from_user.id``).
        limit: Max contact-start triggers allowed in the window.
        period: Window length in seconds.

    Returns:
        ``True`` if the trigger may proceed, ``False`` if rate-limited.
    """
    key = _CONTACT_RATE_LIMIT_KEY_PATTERN.format(user_id=user_id)
    return bump_rate_limit_window(key, limit, period)


# --- support message limiter ------------------------------------------------

# Maximum support messages a user may send within the sliding window.
SUPPORT_MESSAGE_RATE_LIMIT_REQUESTS: Final[int] = 5

# Sliding window length in seconds (10 minutes — short enough to deter spam,
# long enough to cover a support spike).
SUPPORT_MESSAGE_RATE_LIMIT_PERIOD: Final[int] = 600

# Cache key pattern keyed by the stable Telegram user_id (cross-chat identity).
_SUPPORT_RATE_LIMIT_KEY_PATTERN: Final[str] = "bot_support_rl:{user_id}"


@sync_to_async
def check_support_message_rate_limit(
    user_id: int,
    limit: int = SUPPORT_MESSAGE_RATE_LIMIT_REQUESTS,
    period: int = SUPPORT_MESSAGE_RATE_LIMIT_PERIOD,
) -> bool:
    """Return ``True`` if the user is within the support message rate limit.

    Per-user sliding-window limiter for the support/contact message intake flow,
    delegating the window bump to
    ``apps.core.utils.cache.bump_rate_limit_window``. Returns ``False`` when the
    limit is exceeded, and ``True`` (fail-open) when the cache is unreachable.

    Args:
        user_id: The Telegram user's id (``message.from_user.id``).
        limit: Max support messages allowed in the window.
        period: Window length in seconds.

    Returns:
        ``True`` if the message may proceed, ``False`` if rate-limited.
    """
    key = _SUPPORT_RATE_LIMIT_KEY_PATTERN.format(user_id=user_id)
    return bump_rate_limit_window(key, limit, period)


# --- login deep-link limiter ------------------------------------------------

# Maximum login claim attempts per user within the sliding window.
LOGIN_RATE_LIMIT_REQUESTS: Final[int] = 10

# Sliding window length in seconds.
LOGIN_RATE_LIMIT_PERIOD: Final[int] = 60

# Cache key pattern keyed by the stable Telegram user_id (cross-chat identity).
_LOGIN_RATE_LIMIT_KEY_PATTERN: Final[str] = "bot_login_rl:{user_id}"


@sync_to_async
def check_login_rate_limit(
    user_id: int,
    limit: int = LOGIN_RATE_LIMIT_REQUESTS,
    period: int = LOGIN_RATE_LIMIT_PERIOD,
) -> bool:
    """Return ``True`` if the user is within the login rate limit.

    Per-user sliding-window limiter for ``/start login_<token>`` claims,
    delegating the window bump to
    ``apps.core.utils.cache.bump_rate_limit_window``. Returns ``False`` when the
    limit is exceeded, and ``True`` (fail-open) when the cache is unreachable.

    Args:
        user_id: The Telegram user's id (``message.from_user.id``).
        limit: Max login claims allowed in the window.
        period: Window length in seconds.

    Returns:
        ``True`` if the login claim may proceed, ``False`` if rate-limited.
    """
    key = _LOGIN_RATE_LIMIT_KEY_PATTERN.format(user_id=user_id)
    return bump_rate_limit_window(key, limit, period)
