"""Replay-capable backoff for transient Telegram API failures (EXT-002).

When Telegram responds with HTTP 429 (flood control), or an outbound call fails
with a network or server error, the generic aiogram catch-all merely logs the
error and drops the call, silently losing confirmation/inline-keyboard messages.
This module provides a global ``dp.errors`` handler that replays the exact failed
``TelegramMethod`` within a bounded wall-clock budget (09-API-004).

Import-time side-effect contract: this module must perform no ``ThreadPoolExecutor``
creation, no network I/O and no Django model loading — it is imported lazily
inside ``telegram_bot.main()`` after ``django.setup()``. ONE admitted exception is
the module-level ``prometheus_client.Counter`` below: it registers a metric in the
default Prometheus registry at import time (the established project pattern for
``/metrics``) but is none of the three named prohibitions.
"""

import asyncio
import logging
import time
from typing import Final

from aiogram import Bot
from aiogram.exceptions import (
    AiogramError,
    TelegramNetworkError,
    TelegramRetryAfter,
    TelegramServerError,
)
from aiogram.types.error_event import ErrorEvent
from prometheus_client import Counter

logger = logging.getLogger(__name__)

# Fallback sleep when a transient error carries no ``retry_after``.
_BACKOFF_BASE: Final[float] = 0.5

# Historical attempt-count constant. The replay loop is no longer attempt-bounded
# (attempt-counting is what produced the 900 s pin this module fixes); the
# constant is retained because the success-path test imports it and asserts the
# await count stays at or below it.
_MAX_RETRIES: Final[int] = 3

# Total wall-clock budget for ONE update task's replay loop (09-API-004). No
# single flood response may pin an update task for longer than this. The bound is
# a budget rather than an attempt count so the guarantee is one enforceable
# number, not ``attempts x per-attempt ceiling``.
_MAX_REPLAY_BUDGET_SECONDS: Final[float] = 30.0

# Per-attempt ceiling, so a single retry_after cannot consume the whole budget.
_MAX_BACKOFF_SECONDS: Final[float] = 5.0

# The transient siblings that warrant another replay attempt inside the loop.
_TRANSIENT_EXCEPTIONS: Final[tuple[type[AiogramError], ...]] = (
    TelegramRetryAfter,
    TelegramNetworkError,
    TelegramServerError,
)

# Outbound calls dropped after the replay budget was exhausted. This counter is
# the only line anywhere that says "N messages were dropped": the pre-fix handler
# reported the drop as a success.
_DROPPED_OUTBOUND_CALLS: Final = Counter(
    "telegram_dropped_outbound_calls_total",
    "Outbound Telegram calls dropped after the replay budget was exhausted.",
)


def _retry_delay(exc: BaseException, remaining: float) -> float:
    """Return the clamped sleep for one replay attempt.

    Prefers the Telegram-mandated ``retry_after`` when present, falling back to
    ``_BACKOFF_BASE``, and clamps the result to the remaining budget and the
    per-attempt ceiling so a single ``retry_after`` can consume neither.
    """
    delay = _BACKOFF_BASE
    retry_after = getattr(exc, "retry_after", None)
    if isinstance(exc, TelegramRetryAfter) and retry_after:
        delay = float(retry_after)
    return min(delay, remaining, _MAX_BACKOFF_SECONDS)


async def retry_transient(event: ErrorEvent, bot: Bot) -> bool:
    """Handle a transient outbound-call failure within a bounded replay budget.

    Sleeps a clamped backoff and re-issues the exact failed call via
    ``await bot(exc.method)`` while the wall-clock budget
    (``_MAX_REPLAY_BUDGET_SECONDS``) remains. Returns ``True`` once the call
    succeeds. After the budget is exhausted — or when a permanent ``AiogramError``
    makes a retry pointless — it increments
    ``telegram_dropped_outbound_calls_total`` (only for budget exhaustion) and
    returns ``False`` rather than reporting the drop as a success. In the pinned
    aiogram (3.30.0) ``ErrorsMiddleware`` treats any value other than the
    ``UNHANDLED`` sentinel as the handler's answer, so returning ``False`` does
    **not** re-raise the exception; it stops the drop from being reported as
    handled.
    """
    exc = event.exception
    method_name = type(exc.method).__name__
    start = time.monotonic()

    while True:
        remaining = _MAX_REPLAY_BUDGET_SECONDS - (time.monotonic() - start)
        if remaining <= 0:
            break

        delay = _retry_delay(exc, remaining)
        await asyncio.sleep(delay)
        try:
            await bot(exc.method)
            return True
        except _TRANSIENT_EXCEPTIONS as retry_exc:
            # A fresh 429 refreshes the mandated wait; other transient siblings
            # fall back to the base backoff. Continue while budget remains.
            exc = retry_exc
            logger.warning(
                "Transient outbound-call failure for %s: %s",
                method_name,
                retry_exc,
            )
        except AiogramError as permanent_exc:
            # Permanent failure — do not keep replaying.
            logger.warning(
                "Permanent outbound-call failure for %s: %s",
                method_name,
                permanent_exc,
            )
            return False

    _DROPPED_OUTBOUND_CALLS.inc()
    logger.warning(
        "Dropped outbound call %s after exhausting the %.0fs replay budget",
        method_name,
        _MAX_REPLAY_BUDGET_SECONDS,
    )
    return False
