"""
Unit tests for the immediate-alert delivery bridge (EXT-002).

Covers:
- One Bot constructed per batch (not per message); session.close once in finally.
- asyncio.gather return_exceptions=True isolates failures (siblings proceed).
- 429 TelegramRetryAfter backoff honored and retry attempted.
- _run_send narrows except to AiogramError (non-Aiogram errors propagate).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiogram.exceptions import (
    AiogramError,
    TelegramForbiddenError,
    TelegramRetryAfter,
    TelegramServerError,
)

pytestmark = [pytest.mark.unit]


def _payload(chat_id: int = 1) -> dict:
    """Minimal payload dict matching the shape _build_payload returns."""
    return {"chat_id": chat_id, "text": "test message", "reply_markup": None}


# ---------------------------------------------------------------------------
# Bot reuse — one Bot per batch, session closed once
# ---------------------------------------------------------------------------


class TestBotReuse:
    """One Bot is constructed per _send_payloads invocation, not per message."""

    @pytest.mark.asyncio
    async def test_one_bot_constructed_once_per_batch(self) -> None:
        """Bot is created once (not per message); session.close called once."""
        payloads = [_payload(1), _payload(2), _payload(3)]

        with patch(
            "apps.search.services.immediate_alerts.Bot"
        ) as mock_bot_cls:
            mock_bot = mock_bot_cls.return_value
            mock_bot.send_message = AsyncMock()
            mock_bot.session.close = AsyncMock()

            from apps.search.services.immediate_alerts import _send_payloads

            await _send_payloads("test-token", payloads)

            # Exactly one Bot constructed per batch (not per message).
            assert mock_bot_cls.call_count == 1
            # One send_message call per payload.
            assert mock_bot.send_message.await_count == 3
            # session.close called exactly once in finally.
            assert mock_bot.session.close.await_count == 1

    @pytest.mark.asyncio
    async def test_session_closed_even_when_send_fails(self) -> None:
        """session.close is always called via finally, even on dead-letter."""
        payloads = [_payload(42)]

        with patch(
            "apps.search.services.immediate_alerts.Bot"
        ) as mock_bot_cls:
            mock_bot = mock_bot_cls.return_value
            mock_bot.send_message = AsyncMock(
                side_effect=TelegramForbiddenError(
                    message="blocked by user",
                    method=MagicMock(),
                )
            )
            mock_bot.session.close = AsyncMock()

            from apps.search.services.immediate_alerts import _send_payloads

            await _send_payloads("test-token", payloads)

            assert mock_bot.session.close.await_count == 1
            assert mock_bot.send_message.await_count == 1


# ---------------------------------------------------------------------------
# return_exceptions isolation
# ---------------------------------------------------------------------------


class TestGatherIsolation:
    """return_exceptions=True prevents sibling cancellation on failure."""

    @pytest.mark.asyncio
    async def test_permanent_failure_does_not_cancel_siblings(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A TelegramForbiddenError on one payload does not block siblings."""
        payloads = [_payload(1), _payload(2), _payload(3)]

        attempted: list[int] = []

        def fake_send_message(**kwargs: object) -> None:
            attempted.append(int(kwargs["chat_id"]))
            if int(kwargs["chat_id"]) == 2:
                raise TelegramForbiddenError(
                    message="chat not found",
                    method=MagicMock(),
                )

        with patch(
            "apps.search.services.immediate_alerts.Bot"
        ) as mock_bot_cls:
            mock_bot = mock_bot_cls.return_value
            mock_bot.send_message = AsyncMock(side_effect=fake_send_message)
            mock_bot.session.close = AsyncMock()

            from apps.search.services.immediate_alerts import _send_payloads

            await _send_payloads("test-token", payloads)

            # All three payloads attempted despite the failure on chat 2.
            assert sorted(attempted) == [1, 2, 3]
            assert mock_bot.session.close.await_count == 1

    @pytest.mark.asyncio
    async def test_unhandled_exception_does_not_cancel_siblings(self) -> None:
        """A non-AiogramError escaping _send is captured by return_exceptions."""
        payloads = [_payload(1), _payload(2), _payload(3)]

        attempted: list[int] = []

        def fake_send_message(**kwargs: object) -> None:
            attempted.append(int(kwargs["chat_id"]))
            if int(kwargs["chat_id"]) == 2:
                raise RuntimeError("unexpected")

        with patch(
            "apps.search.services.immediate_alerts.Bot"
        ) as mock_bot_cls:
            mock_bot = mock_bot_cls.return_value
            mock_bot.send_message = AsyncMock(side_effect=fake_send_message)
            mock_bot.session.close = AsyncMock()

            from apps.search.services.immediate_alerts import _send_payloads

            # return_exceptions=True: gather must not raise the RuntimeError.
            await _send_payloads("test-token", payloads)

            assert sorted(attempted) == [1, 2, 3]
            assert mock_bot.session.close.await_count == 1


# ---------------------------------------------------------------------------
# 429 retry-after backoff
# ---------------------------------------------------------------------------


class TestRetryAfterBackoff:
    """TelegramRetryAfter (429) honors retry_after for backoff and retries."""

    @pytest.mark.asyncio
    async def test_429_retry_after_honored(self) -> None:
        """retry_after is used as backoff; send_message retried after sleep."""
        payloads = [_payload(42)]

        retry_exc = TelegramRetryAfter(
            message="too many requests",
            method=MagicMock(),
            retry_after=2,
        )

        with patch(
            "apps.search.services.immediate_alerts.Bot"
        ) as mock_bot_cls:
            mock_bot = mock_bot_cls.return_value
            mock_bot.send_message = AsyncMock(
                side_effect=[retry_exc, None]
            )
            mock_bot.session.close = AsyncMock()

            from apps.search.services.immediate_alerts import _send_payloads

            with patch(
                "apps.search.services.immediate_alerts.asyncio.sleep",
                new=AsyncMock(),
            ) as mock_sleep:
                await _send_payloads("test-token", payloads)

            # Backoff sleep honored with retry_after value (2.0 seconds).
            mock_sleep.assert_awaited_once_with(2.0)
            # Retry attempted: 2 total send_message calls.
            assert mock_bot.send_message.await_count == 2

    @pytest.mark.asyncio
    async def test_transient_error_uses_capped_backoff(self) -> None:
        """TelegramServerError triggers retry with _BACKOFF_BASE backoff."""
        payloads = [_payload(99)]

        server_exc = TelegramServerError(
            message="internal server error",
            method=MagicMock(),
        )

        with patch(
            "apps.search.services.immediate_alerts.Bot"
        ) as mock_bot_cls:
            mock_bot = mock_bot_cls.return_value
            mock_bot.send_message = AsyncMock(
                side_effect=[server_exc, None]
            )
            mock_bot.session.close = AsyncMock()

            from apps.search.services.immediate_alerts import (
                _BACKOFF_BASE,
                _send_payloads,
            )

            with patch(
                "apps.search.services.immediate_alerts.asyncio.sleep",
                new=AsyncMock(),
            ) as mock_sleep:
                await _send_payloads("test-token", payloads)

            # Retry uses _BACKOFF_BASE (capped backoff, not retry_after).
            mock_sleep.assert_awaited_once_with(_BACKOFF_BASE)
            assert mock_bot.send_message.await_count == 2

    @pytest.mark.asyncio
    async def test_retry_failure_swallowed_and_logged(self) -> None:
        """If the retry also raises, it is logged and does not propagate."""
        payloads = [_payload(7)]

        retry_exc = TelegramRetryAfter(
            message="too many requests",
            method=MagicMock(),
            retry_after=1,
        )
        second_exc = TelegramForbiddenError(
            message="blocked",
            method=MagicMock(),
        )

        with patch(
            "apps.search.services.immediate_alerts.Bot"
        ) as mock_bot_cls:
            mock_bot = mock_bot_cls.return_value
            mock_bot.send_message = AsyncMock(
                side_effect=[retry_exc, second_exc]
            )
            mock_bot.session.close = AsyncMock()

            from apps.search.services.immediate_alerts import _send_payloads

            with patch(
                "apps.search.services.immediate_alerts.asyncio.sleep",
                new=AsyncMock(),
            ):
                # Must not raise — retry failure is caught by the inner
                # except AiogramError handler and logged.
                await _send_payloads("test-token", payloads)

            assert mock_bot.send_message.await_count == 2
            assert mock_bot.session.close.await_count == 1


# ---------------------------------------------------------------------------
# _run_send exception narrowing
# ---------------------------------------------------------------------------


class TestRunSendExceptionNarrowing:
    """_run_send catches AiogramError, not bare Exception."""

    def test_aiogram_error_caught_and_logged(self) -> None:
        """AiogramError from _send_payloads is caught (not propagated)."""
        with patch(
            "apps.search.services.immediate_alerts._send_payloads",
            new=AsyncMock(side_effect=AiogramError("network down")),
        ):
            from apps.search.services.immediate_alerts import _run_send

            # Must not raise — AiogramError is caught and logged.
            _run_send([])

    def test_non_aiogram_error_propagates(self) -> None:
        """Non-AiogramError (e.g. RuntimeError) propagates — not swallowed."""
        with patch(
            "apps.search.services.immediate_alerts._send_payloads",
            new=AsyncMock(side_effect=RuntimeError("unexpected")),
        ):
            from apps.search.services.immediate_alerts import _run_send

            with pytest.raises(RuntimeError, match="unexpected"):
                _run_send([])
