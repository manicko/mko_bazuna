"""Tests for the replay-capable 429 backoff error handler (EXT-002).

The production handler ``retry_transient`` is registered on a Dispatcher's
``errors`` observer and invoked directly with a synthetic ``TelegramRetryAfter``.
No ``run_polling`` is called and no real Telegram API requests are made.

A minimal ``Dispatcher`` is built per test instead of the conftest ``dp``
fixture: the conftest fixture wires in module-level singleton routers that
cannot be attached to more than one Dispatcher, and the outbound ``bot`` is a
minimal async-callable stub (the conftest ``bot`` fixture's token does not pass
aiogram validation in the test environment). Only ``dp.errors`` registration and
``await bot(method)`` are exercised, which is all ``retry_transient`` uses.
"""

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any
from unittest.mock import AsyncMock

import pytest
from aiogram import Dispatcher
from aiogram.exceptions import TelegramBadRequest, TelegramRetryAfter
from aiogram.filters import ExceptionTypeFilter
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.methods import SendMessage
from aiogram.types import Chat, Message, Update, User
from aiogram.types.error_event import ErrorEvent

from telegram_bot.retry import _MAX_RETRIES, retry_transient


def _make_dispatcher() -> Dispatcher:
    """Build a Dispatcher with the production error handler registered."""
    dp = Dispatcher(storage=MemoryStorage())
    dp.errors(ExceptionTypeFilter(TelegramRetryAfter))(retry_transient)
    return dp


class _FakeBot:
    """Minimal stand-in for the aiogram Bot outbound-call surface."""

    def __init__(self, call: Callable[[Any], Awaitable[Any]]) -> None:
        self._call = call

    async def __call__(self, method: Any) -> Any:
        return await self._call(method)


def _ok_message() -> Message:
    """Build a valid Message that a successful SendMessage replay would return."""
    return Message(
        message_id=1,
        date=1,
        chat=Chat(id=1, type="private"),
        text="ok",
        from_user=User(id=1, is_bot=False, first_name="x"),
    )


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
async def test_error_handler_marks_handled_after_exhausting_bound(
    monkeypatch,
) -> None:
    """After the retry bound is exhausted the handler still returns True."""
    dp = _make_dispatcher()
    handler = dp.errors.handlers[0].callback

    async def _fake_sleep(seconds: float) -> None:
        pass

    monkeypatch.setattr(asyncio, "sleep", _fake_sleep)

    # Every replay attempt fails with a fresh transient 429.
    async def _failing_call(method: Any) -> Any:
        raise TelegramRetryAfter(
            method=method,
            message="too many",
            retry_after=2,
        )

    bot = _FakeBot(_failing_call)

    exc = TelegramRetryAfter(
        method=SendMessage(chat_id=1, text="hi"),
        message="too many",
        retry_after=2,
    )
    event = ErrorEvent(update=Update(update_id=1), exception=exc)

    result = await handler(event, bot=bot)

    assert result is True


@pytest.mark.asyncio
async def test_error_handler_returns_false_for_unrelated_error() -> None:
    """Non-TelegramRetryAfter errors are not handled by retry_transient."""
    dp = _make_dispatcher()
    handler = dp.errors.handlers[0].callback

    bot = _FakeBot(AsyncMock(return_value=_ok_message()))

    exc = TelegramBadRequest(method=SendMessage(chat_id=1, text="hi"), message="bad")
    event = ErrorEvent(update=Update(update_id=1), exception=exc)

    result = await handler(event, bot=bot)

    assert result is False
