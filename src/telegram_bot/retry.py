"""Replay-capable backoff for transient Telegram API failures (EXT-002).

When Telegram responds with HTTP 429 (flood control) to an outbound call, the
generic aiogram catch-all merely logs the error and drops the call, silently
losing confirmation/inline-keyboard messages. This module provides a global
``dp.errors`` handler that sleeps the Telegram-mandated ``retry_after`` and
re-issues the exact failed ``TelegramMethod`` with a bounded retry count.

This module must have NO import-time side effects (no ``ThreadPoolExecutor``,
no network, no Django model loading): it is imported lazily inside
``telegram_bot.main()`` after ``django.setup()``.
"""

import asyncio
import logging
from typing import Final

from aiogram import Bot
from aiogram.exceptions import (
    AiogramError,
    TelegramNetworkError,
    TelegramRetryAfter,
    TelegramServerError,
)
from aiogram.types.error_event import ErrorEvent

logger = logging.getLogger(__name__)

# Backoff tuning constants. ``_BACKOFF_BASE`` is the fallback sleep when a
# transient error carries no ``retry_after``; ``_MAX_RETRIES`` bounds the replay
# loop so a persistently failing call cannot loop forever.
_BACKOFF_BASE: Final[float] = 0.5
_MAX_RETRIES: Final[int] = 3

# The transient siblings that warrant another replay attempt inside the loop.
_TRANSIENT_EXCEPTIONS: Final[tuple[type[AiogramError], ...]] = (
    TelegramRetryAfter,
    TelegramNetworkError,
    TelegramServerError,
)


async def retry_transient(event: ErrorEvent, bot: Bot) -> bool:
    """Handle a transient outbound-call failure with a bounded replay.

    Sleeps the Telegram-mandated ``retry_after`` (or a base fallback) and
    re-issues the exact failed call via ``await bot(exc.method)``. Returns
    ``True`` once handled (success or after exhausting the bound) so the
    generic catch-all does not re-raise and drop the update. Returns ``False``
    for any non-``TelegramRetryAfter`` exception so other handlers or the
    generic catch-all take over.
    """
    exc = event.exception

    if not isinstance(exc, TelegramRetryAfter):
        return False

    # Re-issue the failed outbound call, sleeping retry_after before each try.
    for attempt in range(1, _MAX_RETRIES + 1):
        delay = float(exc.retry_after) if getattr(exc, "retry_after", None) else _BACKOFF_BASE
        await asyncio.sleep(delay)
        try:
            await bot(exc.method)
            return True
        except _TRANSIENT_EXCEPTIONS as retry_exc:
            # A fresh 429 refreshes the mandated wait; other transient siblings
            # fall back to the base backoff. Continue the bounded loop.
            if isinstance(retry_exc, TelegramRetryAfter) and getattr(retry_exc, "retry_after", None):
                exc = retry_exc
            logger.warning(
                "Transient outbound-call failure (attempt %d/%d) for %s: %s",
                attempt,
                _MAX_RETRIES,
                type(exc.method).__name__,
                retry_exc,
            )
        except AiogramError:
            # Permanent failure — do not keep replaying.
            logger.warning(
                "Permanent outbound-call failure for %s: %s",
                type(exc.method).__name__,
                exc,
            )
            break

    logger.warning(
        "Exhausted %d retries for outbound call %s; marking handled",
        _MAX_RETRIES,
        type(exc.method).__name__,
    )
    return True
