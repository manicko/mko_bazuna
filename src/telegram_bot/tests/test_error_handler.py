"""Tests for the bounded replay-budget error handler (EXT-002 / 09-API-004).

The production handler ``retry_transient`` is registered on a Dispatcher's
``errors`` observer and invoked directly with a synthetic transient exception.
No ``run_polling`` is called and no real Telegram API requests are made, and no
``Bot`` is ever constructed.

A minimal ``Dispatcher`` is built per test instead of the conftest ``dp``
fixture: the conftest fixture wires in module-level singleton routers that
cannot be attached to more than one Dispatcher, and the outbound ``bot`` is a
minimal async-callable stub (the conftest ``bot`` fixture's token does not pass
aiogram validation in the test environment). Only ``dp.errors`` registration and
``await bot(method)`` are exercised, which is all ``retry_transient`` uses.

The dispatcher filter is widened to ``_TRANSIENT_EXCEPTIONS``. While it
hard-coded ``TelegramRetryAfter`` the sibling-replay cases never reached the
handler and passed vacuously — the single most dangerous outcome in the block.
"""

import asyncio
import time
from collections.abc import Awaitable, Callable
from typing import Any
from unittest.mock import AsyncMock

import pytest
from aiogram import Dispatcher
from aiogram.exceptions import (
    TelegramBadRequest,
    TelegramRetryAfter,
    TelegramServerError,
)
from aiogram.filters import ExceptionTypeFilter
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.methods import SendMessage
from aiogram.types import Chat, Message, Update, User
from aiogram.types.error_event import ErrorEvent

from telegram_bot.retry import (
    _DROPPED_OUTBOUND_CALLS,
    _MAX_BACKOFF_SECONDS,
    _MAX_REPLAY_BUDGET_SECONDS,
    _MAX_RETRIES,
    _TRANSIENT_EXCEPTIONS,
    retry_transient,
)


def _make_dispatcher() -> Dispatcher:
    """Build a Dispatcher with the production error handler registered.

    The filter is ``_TRANSIENT_EXCEPTIONS`` (not just ``TelegramRetryAfter``) so
    the sibling-replay cases actually reach the handler.
    """
    dp = Dispatcher(storage=MemoryStorage())
    dp.errors(ExceptionTypeFilter(_TRANSIENT_EXCEPTIONS))(retry_transient)
    return dp


class _FakeBot:
    """Minimal stand-in for the aiogram Bot outbound-call surface."""

    def __init__(self, call: Callable[[Any], Awaitable[Any]]) -> None:
        self._call = call

    async def __call__(self, method: Any) -> Any:
        return await self._call(method)


class _FakeClock:
    """Deterministic monotonic clock advanced by the fake sleep.

    The replay budget is wall-clock, so tests must control ``time.monotonic`` to
    make exhaustion deterministic instead of spending real seconds.
    """

    def __init__(self) -> None:
        self.now = 0.0

    def monotonic(self) -> float:
        return self.now


def _install_fake_clock(monkeypatch: pytest.MonkeyPatch, sleeps: list[float]) -> None:
    """Patch ``asyncio.sleep`` and ``time.monotonic`` with one advancing clock."""
    clock = _FakeClock()

    async def _fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)
        clock.now += seconds

    monkeypatch.setattr(asyncio, "sleep", _fake_sleep)
    monkeypatch.setattr(time, "monotonic", clock.monotonic)


def _dropped_count() -> float:
    """Return the current value of the dropped-outbound-calls counter."""
    return _DROPPED_OUTBOUND_CALLS._value.get()  # noqa: SLF001 — test-only read


def _ok_message() -> Message:
    """Build a valid Message that a successful SendMessage replay would return."""
    return Message(
        message_id=1,
        date=1,
        chat=Chat(id=1, type="private"),
        text="ok",
        from_user=User(id=1, is_bot=False, first_name="x"),
    )


def _error_event(exc: Exception) -> ErrorEvent:
    """Wrap ``exc`` in an ErrorEvent for direct handler invocation."""
    return ErrorEvent(update=Update(update_id=1), exception=exc)


@pytest.mark.asyncio
async def test_error_handler_backs_off_and_replays(monkeypatch) -> None:
    """A TelegramRetryAfter is handled with a sleep and a bounded replay."""
    dp = _make_dispatcher()
    handler = dp.errors.handlers[0].callback

    sleeps: list[float] = []

    async def _fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    monkeypatch.setattr(asyncio, "sleep", _fake_sleep)

    bot_exec = AsyncMock(return_value=_ok_message())
    bot = _FakeBot(bot_exec)

    exc = TelegramRetryAfter(
        method=SendMessage(chat_id=1, text="hi"),
        message="too many",
        retry_after=2,
    )
    event = ErrorEvent(update=Update(update_id=1), exception=exc)

    result = await handler(event, bot=bot)

    assert result is True
    # retry_after honored once (single successful replay).
    assert sleeps == [2.0]
    # The re-issued call executed exactly once, bounded by _MAX_RETRIES.
    assert bot_exec.await_count == 1
    assert bot_exec.await_count <= _MAX_RETRIES


@pytest.mark.asyncio
async def test_error_handler_marks_handled_after_exhausting_bound(monkeypatch) -> None:
    """After the budget is exhausted the handler reports the drop, not success.

    The old assertion (``result is True``) encoded the defect as intended
    behaviour: a dropped outbound call was reported as handled. The handler now
    returns ``False`` and increments the dropped-outbound counter.
    """
    dp = _make_dispatcher()
    handler = dp.errors.handlers[0].callback

    sleeps: list[float] = []
    _install_fake_clock(monkeypatch, sleeps)

    # Every replay attempt fails with a fresh transient 429.
    async def _failing_call(method: Any) -> Any:
        raise TelegramRetryAfter(method=method, message="too many", retry_after=2)

    bot = _FakeBot(_failing_call)

    exc = TelegramRetryAfter(
        method=SendMessage(chat_id=1, text="hi"),
        message="too many",
        retry_after=2,
    )
    event = ErrorEvent(update=Update(update_id=1), exception=exc)

    before = _dropped_count()
    result = await handler(event, bot=bot)
    after = _dropped_count()

    assert result is False
    assert after == before + 1
    # The total sleep is the budget, not an attempt count: the loop stops when
    # the wall-clock budget is spent.
    assert sum(sleeps) <= _MAX_REPLAY_BUDGET_SECONDS


@pytest.mark.asyncio
async def test_error_handler_returns_false_for_unrelated_error() -> None:
    """A persistent permanent error is not retried into the budget and is not counted.

    The old test passed for the wrong reason: it handed the handler a bot whose
    replay *succeeded*, so ``assert result is False`` only held because the
    deleted ``isinstance`` guard short-circuited before any replay. With the
    guard gone the handler must recognise the permanent failure from the replay
    and return ``False`` **without** incrementing the dropped-outbound counter (a
    permanent error is not a budget-exhausted drop).
    """
    dp = _make_dispatcher()
    handler = dp.errors.handlers[0].callback

    async def _permanent_call(method: Any) -> Any:
        raise TelegramBadRequest(method=method, message="bad")

    bot = _FakeBot(_permanent_call)

    exc = TelegramBadRequest(method=SendMessage(chat_id=1, text="hi"), message="bad")
    event = ErrorEvent(update=Update(update_id=1), exception=exc)

    before = _dropped_count()
    result = await handler(event, bot=bot)
    after = _dropped_count()

    assert result is False
    assert after == before


# ---------------------------------------------------------------------------
# RED-1 — the budget bounds the total sleep
# ---------------------------------------------------------------------------


class TestBudgetBoundsTotalSleep:
    """retry_after cannot pin an update task beyond the total budget."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("retry_after", [300, 600])
    async def test_red1_total_sleep_within_budget(
        self, monkeypatch, retry_after: int
    ) -> None:
        """RED-1: retry_after=300/600 yields a bounded TOTAL sleep.

        Before this fix ``sleeps == [300.0, 300.0, 300.0]`` (600 -> 1800 s total)
        with ``handled is True``. The assertion is on the TOTAL, never the
        per-attempt value: an attempt-counting bound also reduces the flood to
        ``3 x ceiling`` and still guarantees no stated budget.
        """
        dp = _make_dispatcher()
        handler = dp.errors.handlers[0].callback

        sleeps: list[float] = []
        _install_fake_clock(monkeypatch, sleeps)

        async def _failing_call(method: Any) -> Any:
            raise TelegramRetryAfter(
                method=method, message="too many", retry_after=retry_after
            )

        bot = _FakeBot(_failing_call)

        exc = TelegramRetryAfter(
            method=SendMessage(chat_id=1, text="hi"),
            message="too many",
            retry_after=retry_after,
        )
        event = ErrorEvent(update=Update(update_id=1), exception=exc)

        before = _dropped_count()
        result = await handler(event, bot=bot)
        after = _dropped_count()

        assert result is False
        assert sum(sleeps) <= _MAX_REPLAY_BUDGET_SECONDS
        assert all(0 < delay <= _MAX_BACKOFF_SECONDS for delay in sleeps)
        assert after == before + 1


# ---------------------------------------------------------------------------
# RED-2 — the reachable transient set
# ---------------------------------------------------------------------------


class TestSiblingTransientReplay:
    """TelegramServerError / TelegramNetworkError enter the handler and replay."""

    @pytest.mark.asyncio
    async def test_red2_server_error_reaches_handler_and_replays(
        self, monkeypatch
    ) -> None:
        """RED-2: a TelegramServerError is replayed.

        Before this fix the filter was ``ExceptionTypeFilter(TelegramRetryAfter)``
        and the body opened with ``if not isinstance(exc, TelegramRetryAfter):
        return False``, so a server error produced ``sleeps == []``,
        ``replays == 0``, ``handled is False``. The handler now replays it.
        """
        dp = _make_dispatcher()
        handler = dp.errors.handlers[0].callback

        sleeps: list[float] = []
        _install_fake_clock(monkeypatch, sleeps)

        bot_exec = AsyncMock(return_value=_ok_message())
        bot = _FakeBot(bot_exec)

        exc = TelegramServerError(
            method=SendMessage(chat_id=1, text="hi"),
            message="server exploded",
        )
        event = ErrorEvent(update=Update(update_id=1), exception=exc)

        result = await handler(event, bot=bot)

        assert result is True
        assert bot_exec.await_count == 1
        assert sleeps == [0.5]
