"""
Unit tests for the send_alerts management command (EXT-002).

Covers:
- Transient error handling (429/network/5xx) with retry-once backoff.
- Permanent error dead-lettering (Forbidden).
- bot.session.close called exactly once even when transient errors occur.
- handle() swallows AiogramError from asyncio.run().
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiogram.exceptions import (
    AiogramError,
    TelegramForbiddenError,
    TelegramNetworkError,
    TelegramRetryAfter,
    TelegramServerError,
)

from apps.users.models import User

pytestmark = [pytest.mark.unit]

_MODULE = "apps.search.management.commands.send_alerts"


def _make_mock_user(chat_id: int = 12345) -> MagicMock:
    """Return a MagicMock user with a truthy chat_id and a language."""
    user = MagicMock()
    user.chat_id = chat_id
    user.telegram_language = "ru"
    return user


# ---------------------------------------------------------------------------
# Transient error handling (429 / network / 5xx)
# ---------------------------------------------------------------------------


class TestTransientErrorHandling:
    """Transient errors (429/network/5xx) trigger retry-once with backoff."""

    @pytest.mark.asyncio
    async def test_429_retry_after_honored(self) -> None:
        """TelegramRetryAfter with retry_after -> sleep honors it -> retry attempted."""
        from apps.search.management.commands.send_alerts import Command

        retry_exc = TelegramRetryAfter(
            message="too many requests",
            method=MagicMock(),
            retry_after=2,
        )
        mock_user_obj = _make_mock_user()

        with patch(f"{_MODULE}.Bot") as mock_bot_cls:
            mock_bot = mock_bot_cls.return_value
            mock_bot.send_message = AsyncMock(side_effect=[retry_exc, None])
            mock_bot.session.close = AsyncMock()

            cmd = Command()
            cmd._format_digest = MagicMock(return_value="test message")

            user_ads = {123: [MagicMock(id=1)]}

            with patch.object(
                User.objects, "aget", new=AsyncMock(return_value=mock_user_obj)
            ):

                with patch(
                    f"{_MODULE}.asyncio.sleep", new=AsyncMock()
                ) as mock_sleep:
                    await cmd._send_user_digests("test-token", user_ads)

            # Backoff sleep honored with retry_after value (2.0 seconds).
            mock_sleep.assert_awaited_once_with(2.0)
            # Retry attempted: 2 total send_message calls.
            assert mock_bot.send_message.await_count == 2
            assert mock_bot.session.close.await_count == 1

    @pytest.mark.asyncio
    async def test_server_error_uses_capped_backoff(self) -> None:
        """TelegramServerError -> backoff = _BACKOFF_BASE -> retry attempted."""
        from apps.search.management.commands.send_alerts import (
            _BACKOFF_BASE,
            Command,
        )

        server_exc = TelegramServerError(
            message="internal server error",
            method=MagicMock(),
        )
        mock_user_obj = _make_mock_user()

        with patch(f"{_MODULE}.Bot") as mock_bot_cls:
            mock_bot = mock_bot_cls.return_value
            mock_bot.send_message = AsyncMock(side_effect=[server_exc, None])
            mock_bot.session.close = AsyncMock()

            cmd = Command()
            cmd._format_digest = MagicMock(return_value="test message")

            user_ads = {456: [MagicMock(id=1)]}

            with patch.object(
                User.objects, "aget", new=AsyncMock(return_value=mock_user_obj)
            ):

                with patch(
                    f"{_MODULE}.asyncio.sleep", new=AsyncMock()
                ) as mock_sleep:
                    await cmd._send_user_digests("test-token", user_ads)

            # Retry uses _BACKOFF_BASE (capped backoff, not retry_after).
            mock_sleep.assert_awaited_once_with(_BACKOFF_BASE)
            assert mock_bot.send_message.await_count == 2
            assert mock_bot.session.close.await_count == 1

    @pytest.mark.asyncio
    async def test_network_error_retries_and_deadletters(self) -> None:
        """TelegramNetworkError -> retry attempted; if retry fails, logged/swallowed."""
        from apps.search.management.commands.send_alerts import Command

        network_exc = TelegramNetworkError(
            message="connection reset",
            method=MagicMock(),
        )
        retry_exc = TelegramForbiddenError(
            message="blocked by user",
            method=MagicMock(),
        )
        mock_user_obj = _make_mock_user()

        with patch(f"{_MODULE}.Bot") as mock_bot_cls:
            mock_bot = mock_bot_cls.return_value
            mock_bot.send_message = AsyncMock(
                side_effect=[network_exc, retry_exc]
            )
            mock_bot.session.close = AsyncMock()

            cmd = Command()
            cmd._format_digest = MagicMock(return_value="test message")

            user_ads = {789: [MagicMock(id=1)]}

            with patch.object(
                User.objects, "aget", new=AsyncMock(return_value=mock_user_obj)
            ):

                with patch(
                    f"{_MODULE}.asyncio.sleep", new=AsyncMock()
                ) as mock_sleep:
                    # Must not raise — retry failure is caught by the inner
                    # except AiogramError handler and logged.
                    await cmd._send_user_digests("test-token", user_ads)

            # Retry attempted with sleep.
            mock_sleep.assert_awaited_once()
            # Two send_message calls: original + retry.
            assert mock_bot.send_message.await_count == 2
            assert mock_bot.session.close.await_count == 1

    @pytest.mark.asyncio
    async def test_permanent_failure_deadletters(self) -> None:
        """TelegramForbiddenError -> no retry, logged once."""
        from apps.search.management.commands.send_alerts import Command

        forbidden_exc = TelegramForbiddenError(
            message="blocked by user",
            method=MagicMock(),
        )
        mock_user_obj = _make_mock_user()

        with patch(f"{_MODULE}.Bot") as mock_bot_cls:
            mock_bot = mock_bot_cls.return_value
            mock_bot.send_message = AsyncMock(side_effect=forbidden_exc)
            mock_bot.session.close = AsyncMock()

            cmd = Command()
            cmd._format_digest = MagicMock(return_value="test message")

            user_ads = {111: [MagicMock(id=1)]}

            with patch.object(
                User.objects, "aget", new=AsyncMock(return_value=mock_user_obj)
            ):

                with patch(
                    f"{_MODULE}.asyncio.sleep", new=AsyncMock()
                ) as mock_sleep:
                    await cmd._send_user_digests("test-token", user_ads)

            # No sleep — permanent failure is dead-lettered without retry.
            mock_sleep.assert_not_awaited()
            assert mock_bot.send_message.await_count == 1
            assert mock_bot.session.close.await_count == 1

    @pytest.mark.asyncio
    async def test_429_retry_after_is_capped(self) -> None:
        """A huge Telegram retry_after is clamped to RETRY_AFTER_CEILING (Q8)."""
        from apps.search.management.commands.send_alerts import (
            RETRY_AFTER_CEILING,
            Command,
        )

        retry_exc = TelegramRetryAfter(
            message="too many requests",
            method=MagicMock(),
            retry_after=300,
        )
        mock_user_obj = _make_mock_user()

        with patch(f"{_MODULE}.Bot") as mock_bot_cls:
            mock_bot = mock_bot_cls.return_value
            mock_bot.send_message = AsyncMock(side_effect=[retry_exc, None])
            mock_bot.session.close = AsyncMock()

            cmd = Command()
            cmd._format_digest = MagicMock(return_value="test message")

            user_ads = {123: [MagicMock(id=1)]}

            with patch.object(
                User.objects, "aget", new=AsyncMock(return_value=mock_user_obj)
            ):

                with patch(
                    f"{_MODULE}.asyncio.sleep", new=AsyncMock()
                ) as mock_sleep:
                    await cmd._send_user_digests("test-token", user_ads)

            # The mandated 300 s is clamped to the 30 s ceiling.
            mock_sleep.assert_awaited_once_with(30.0)
            assert RETRY_AFTER_CEILING == 30.0
            # Retry still attempted: two send_message calls.
            assert mock_bot.send_message.await_count == 2
            assert mock_bot.session.close.await_count == 1


# ---------------------------------------------------------------------------
# Hostile seller markup in the digest (09-API-006)
# ---------------------------------------------------------------------------


class TestHostileMarkupEscaped:
    """The digest escapes seller text on the truncated prefix (09-API-006).

    The RED evidence against the unfixed tree was:
    ``'New ads matching your saved searches (1 found):\\n\\n• Selling <b>bold</b> &
    <a href="http://evil.example\\n   - Free\\n'`` — the seller's ``<b>`` was live
    inside the 50-character prefix. The assertion is on ``_format_digest``'s output
    line (not ``send_message``'s text) so it survives the ``[:50]`` truncation: a
    full-substring check returns ``False`` against the defective code for a reason
    unrelated to escaping.
    """

    def test_digest_escapes_seller_markup_in_prefix(self) -> None:
        """The truncated title in the digest carries no live seller markup."""
        from apps.search.management.commands.send_alerts import Command

        ad = MagicMock()
        ad.get_title.return_value = (
            'Selling <b>bold</b> & <a href="http://evil.example">x</a>'
        )
        ad.price_amount = 0
        ad.price_currency = "EUR"

        cmd = Command()
        message = cmd._format_digest([ad], locale="en")

        # The seller's markup is escaped, not live, inside the 50-char prefix.
        assert "<b>bold</b>" not in message
        assert '<a href="http://evil.example">' not in message
        assert "&lt;b&gt;bold&lt;/b&gt;" in message
        assert "&amp;" in message

    def test_digest_ordinary_title_unchanged(self) -> None:
        """Escaping is a no-op on an ordinary title (the control)."""
        from apps.search.management.commands.send_alerts import Command

        ad = MagicMock()
        ad.get_title.return_value = "Selling bicycle"
        ad.price_amount = None
        ad.price_currency = "EUR"

        cmd = Command()
        message = cmd._format_digest([ad], locale="en")

        assert "• Selling bicycle" in message


# ---------------------------------------------------------------------------
# Bot session safety — session.close always called once
# ---------------------------------------------------------------------------


class TestBotSafety:
    """session.close called exactly once even when transient errors occur."""

    @pytest.mark.asyncio
    async def test_session_closed_on_transient_error(self) -> None:
        """bot.session.close called exactly once even when transient errors occur."""
        from apps.search.management.commands.send_alerts import Command

        server_exc = TelegramServerError(
            message="internal server error",
            method=MagicMock(),
        )
        mock_user_obj = _make_mock_user()

        with patch(f"{_MODULE}.Bot") as mock_bot_cls:
            mock_bot = mock_bot_cls.return_value
            mock_bot.send_message = AsyncMock(
                side_effect=[server_exc, server_exc]
            )
            mock_bot.session.close = AsyncMock()

            cmd = Command()
            cmd._format_digest = MagicMock(return_value="test message")

            user_ads = {222: [MagicMock(id=1)]}

            with patch.object(
                User.objects, "aget", new=AsyncMock(return_value=mock_user_obj)
            ):

                with patch(f"{_MODULE}.asyncio.sleep", new=AsyncMock()):
                    await cmd._send_user_digests("test-token", user_ads)

            # session.close called exactly once even though transient errors
            # fired and retries also failed.
            assert mock_bot.session.close.await_count == 1


# ---------------------------------------------------------------------------
# handle() safety — swallows AiogramError
# ---------------------------------------------------------------------------


class TestHandleSafety:
    """handle() wraps asyncio.run() in try/except AiogramError."""

    def test_handle_swallows_aiogram_error(self) -> None:
        """handle() — _send_user_digests raising AiogramError -> handle() does not raise.

        ``_collect_alerts`` is patched to ``({}, [], [])``, so ``users_attempted
        == 0`` and the all-failed ``CommandError`` branch is not entered: the
        blanket ``AiogramError`` swallow exits 0.
        """
        from apps.search.management.commands.send_alerts import Command

        cmd = Command()

        with (
            patch.object(cmd, "_collect_alerts", return_value=({}, [], [])) as mock_collect,
            patch.object(cmd, "_persist_alerts") as mock_persist,
            patch(f"{_MODULE}.transaction.atomic"),
            patch(f"{_MODULE}.advisory_lock"),
            patch.object(
                cmd,
                "_send_user_digests",
                new=AsyncMock(side_effect=AiogramError("network down")),
            ),
        ):
            # Must not raise — AiogramError is caught and logged in handle().
            cmd.handle(dry_run=False)

        mock_collect.assert_called_once()
        mock_persist.assert_called_once()
