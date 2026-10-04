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
process-local default registry at import time but is none of the three named
prohibitions.

Observability limit (deliberate, de-scoped follow-on): the ``bot`` service sets no
``PROMETHEUS_MULTIPROC_DIR`` and mounts no tmpfs for it — only ``web`` does
(``docker-compose.yml``), and ``src/backend/tests/test_compose_contract.py`` pins
that arrangement. The counter therefore lives in this process only and is **not
exported** by ``web``'s ``/metrics``, whose ``ExportToDjangoView`` builds a fresh
registry populated solely by ``MultiProcessCollector``. The drop is observable
today **only** through the ``logger.warning`` emitted on exhaustion; the counter is
in-process bookkeeping (and what the unit tests assert the increment against). A
shared multiprocess volume, or a bot-side ``/metrics``, is a deployment-topology
change of the same scale as §6.2's declined "one outbound gateway": it is recorded
here as a named, de-scoped follow-on and is **not** built in this change.
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

# Secondary ceiling on the number of replayed outbound calls for ONE update task
# (09-API-004). The total wall-clock budget (``_MAX_REPLAY_BUDGET_SECONDS``) is the
# primary bound; this attempt cap is a strictly tighter ceiling on the *attempt*
# axis, which the budget alone does not constrain. With only the budget, a
# ``retry_after >= 1`` drive yields up to 30 attempts in 30 s, and the
# ``_BACKOFF_BASE = 0.5`` path (TelegramNetworkError / TelegramServerError) up to 60
# — versus at most 3 pre-fix. The cap restores the pre-fix attempt order of
# magnitude while keeping the budget's stated guarantee: whichever bound is hit
# first stops the loop. 5 is chosen so a legitimate transient blip (a handful of
# consecutive 429s/5xx) is not abandoned early, while a sustained flood cannot
# amplify one update into dozens of replayed calls.
_MAX_REPLAY_ATTEMPTS: Final[int] = 5

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

# Outbound calls dropped after the replay budget or attempt cap was exhausted.
# Process-local (see the module docstring): the increment is real and asserted by
# the unit tests, but it is not exported to ``web``'s ``/metrics``.
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
    (``_MAX_REPLAY_BUDGET_SECONDS``) remains and fewer than
    ``_MAX_REPLAY_ATTEMPTS`` replays have been attempted. The loop stops at
    whichever bound is reached first. Returns ``True`` once the call succeeds.
    After a bound is exhausted — or when a permanent ``AiogramError`` makes a
    retry pointless — it increments the process-local
    ``telegram_dropped_outbound_calls_total`` counter (only for bound exhaustion)
    and returns ``False``.

    Return contract (honest statement): **no aiogram component consumes this
    value.** In the pinned aiogram (3.30.0) ``ErrorsMiddleware`` reads
    ``if response is not UNHANDLED: return response`` else ``raise`` — only the
    ``UNHANDLED`` sentinel propagates. ``Router._propagate_event``,
    ``Dispatcher._process_update`` and ``Dispatcher.feed_update`` all consume the
    result solely through an ``is UNHANDLED`` identity test, so ``True`` and
    ``False`` are indistinguishable to aiogram in every path; ``False`` is a
    runtime no-op. Choosing ``UNHANDLED`` here (so the exception propagates and
    ``_process_update`` logs it) was considered and declined: it would emit an
    ERROR plus traceback per dropped message on exactly the sustained-flood path
    this handler exists to absorb, and double-report alongside the warning below.
    The drop is surfaced by the counter and this one ``logger.warning``, by design.

    Because nothing consumes the return value, a test that calls this handler
    directly cannot distinguish ``True``, ``False`` and ``UNHANDLED``; the
    *contract* is pinned instead by ``test_error_handler_contract_via_feed_update``,
    which drives ``dp.feed_update`` and asserts which branch is reached — which is
    why the direct-callback tests are sufficient *given* the swallow-and-return-
    ``False`` choice above.
    """
    exc = event.exception
    method_name = type(exc.method).__name__
    start = time.monotonic()
    attempts = 0

    while attempts < _MAX_REPLAY_ATTEMPTS:
        remaining = _MAX_REPLAY_BUDGET_SECONDS - (time.monotonic() - start)
        if remaining <= 0:
            break

        delay = _retry_delay(exc, remaining)
        await asyncio.sleep(delay)
        attempts += 1
        try:
            await bot(exc.method)
            return True
        except _TRANSIENT_EXCEPTIONS as retry_exc:
            # A fresh 429 refreshes the mandated wait; other transient siblings
            # fall back to the base backoff. Continue while both bounds remain.
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
        "Dropped outbound call %s after exhausting the replay bound "
        "(%.0fs budget / %d attempts)",
        method_name,
        _MAX_REPLAY_BUDGET_SECONDS,
        _MAX_REPLAY_ATTEMPTS,
    )
    return False
