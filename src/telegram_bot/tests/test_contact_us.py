"""
Tests for the ``contact_us`` support-desk entry points (CR-5).

Covers:
- ``/start contact_us`` deep-link handler (``handle_contact_us_start``): the
  is_bot guard (skips answering and never consumes rate budget), the per-user
  rate-limit cooldown, and the shared Russian greeting + inline "Contact us"
  keyboard on success.
- ``handle_contact_us_callback``: the inline button answers the callback
  (spinner dismissed) and edits the originating message to the *same* greeting
  — the identical-output contract between the deep-link and callback paths.
- ``handle_login_deep_link`` (no-arg ``/start``): the welcome greeting now
  carries an inline "Contact us" button whose ``callback_data`` is
  ``"contact_us"``.
- ``CONTACT_US_PATTERN`` routing: ``contact_us`` is handled, ``contact_<id>``
  is not (delegation boundary stays in ``handle_contact_start``).

Deep-link handler tests touch the real LocMemCache rate limiter (no DB rows),
matching the marks/fixture idiom in ``test_rate_limit_service.py``; the
callback and login-button tests are pure mock doubles.
"""

from collections.abc import Iterator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from django.core.cache import cache
from django.utils import translation

from telegram_bot.handlers.contact import (
    _CONTACT_US_GREETING,
    CONTACT_US_PATTERN,
    CONTACT_US_RATE_LIMITED_MESSAGE,
    handle_contact_us_callback,
    handle_contact_us_start,
)
from telegram_bot.services.rate_limit import check_contact_start_rate_limit

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


@pytest.fixture(autouse=True)
def _clear_cache() -> Iterator[None]:
    """Clear the shared LocMemCache so rate-limit counters don't leak across tests."""
    cache.clear()
    yield
    cache.clear()


def _mock_message(user_id: int = 123, is_bot: bool = False) -> MagicMock:
    """Build a ``Message`` double for ``handle_contact_us_start``."""
    message = MagicMock()
    message.from_user = MagicMock()
    message.from_user.id = user_id
    message.from_user.is_bot = is_bot
    message.answer = AsyncMock()
    return message


def _mock_callback(data: str = "contact_us") -> MagicMock:
    """Build a ``CallbackQuery`` double for ``handle_contact_us_callback``.

    Idiom mirrors ``test_price_payload._mock_callback``.
    """
    callback = MagicMock()
    callback.data = data
    callback.message = MagicMock()
    callback.message.edit_text = AsyncMock()
    callback.answer = AsyncMock()
    return callback


# ---------------------------------------------------------------------------
# /start contact_us deep-link handler
# ---------------------------------------------------------------------------


class TestContactUsDeepLink:
    """``handle_contact_us_start``: is_bot -> rate limit -> greeting."""

    @pytest.mark.asyncio
    async def test_greeting_with_keyboard(self) -> None:
        """A normal (non-bot) user within budget gets the Russian greeting + button."""
        message = _mock_message(user_id=201)
        bot = MagicMock()

        with translation.override("ru"):
            result = await handle_contact_us_start(message, bot)

            assert result is True
            message.answer.assert_awaited_once()
            sent_text = message.answer.await_args.args[0]
            # Identical-output contract: the deep-link uses the shared greeting.
            assert str(sent_text) == str(_CONTACT_US_GREETING)
            assert "службой поддержки" in str(sent_text)
            reply_markup = message.answer.await_args.kwargs["reply_markup"]
            button = reply_markup.inline_keyboard[0][0]
            assert button.callback_data == "contact_us"
            assert str(button.text) == "Связаться с нами"

    @pytest.mark.asyncio
    async def test_is_bot_skipped_without_budget(self) -> None:
        """Bots are rejected first (OQ1): no answer, no rate budget consumed."""
        message = _mock_message(user_id=202, is_bot=True)
        bot = MagicMock()

        result = await handle_contact_us_start(message, bot)

        assert result is True
        message.answer.assert_not_awaited()
        # A subsequent real (non-bot) call for the same id must NOT be rate
        # limited — the bot's invocation must not have consumed a slot.
        assert await check_contact_start_rate_limit(202) is True

    @pytest.mark.asyncio
    async def test_rate_limited_sends_cooldown(self) -> None:
        """6th contact-start trigger within the window yields the cooldown message."""
        # Exhaust the per-user budget (default 5) before invoking the handler.
        for _ in range(5):
            assert await check_contact_start_rate_limit(203) is True

        message = _mock_message(user_id=203)
        bot = MagicMock()

        result = await handle_contact_us_start(message, bot)

        assert result is True
        message.answer.assert_awaited_once()
        sent_text = message.answer.await_args.args[0]
        assert sent_text == CONTACT_US_RATE_LIMITED_MESSAGE

    @pytest.mark.asyncio
    async def test_contact_us_pattern_matches(self) -> None:
        """``contact_us`` is recognised as a support-desk deep-link."""
        assert CONTACT_US_PATTERN.match("contact_us") is not None

    @pytest.mark.asyncio
    async def test_contact_us_pattern_does_not_match_contact_ad(self) -> None:
        """``contact_<id>`` must not collide with the support-desk pattern."""
        assert CONTACT_US_PATTERN.match("contact_42") is None


# ---------------------------------------------------------------------------
# Inline "Contact us" callback
# ---------------------------------------------------------------------------


class TestContactUsCallback:
    """``handle_contact_us_callback``: dismiss spinner -> edit to greeting."""

    @pytest.mark.asyncio
    async def test_edits_message_to_shared_greeting(self) -> None:
        """The inline button produces the identical greeting as the deep-link."""
        callback = _mock_callback("contact_us")
        bot = MagicMock()

        with translation.override("ru"):
            await handle_contact_us_callback(callback, bot)

            callback.answer.assert_awaited_once()  # spinner dismissed first
            callback.message.edit_text.assert_awaited_once()
            sent_text = callback.message.edit_text.await_args.args[0]
            assert str(sent_text) == str(_CONTACT_US_GREETING)
            reply_markup = callback.message.edit_text.await_args.kwargs["reply_markup"]
            button = reply_markup.inline_keyboard[0][0]
            assert button.callback_data == "contact_us"
            assert str(button.text) == "Связаться с нами"

    @pytest.mark.asyncio
    async def test_no_message_is_noop(self) -> None:
        """A callback with no originating message only dismisses the spinner."""
        callback = MagicMock()
        callback.message = None
        callback.answer = AsyncMock()

        await handle_contact_us_callback(callback, bot=MagicMock())

        callback.answer.assert_awaited_once()
        # No edit attempted when there is no message to edit.


# ---------------------------------------------------------------------------
# No-arg /start greeting (login.py) — inline "Contact us" button
# ---------------------------------------------------------------------------


class TestLoginStartGreetingButton:
    """The no-arg ``/start`` welcome greeting now carries a Contact us button."""

    @pytest.mark.asyncio
    async def test_welcome_greeting_has_contact_us_button(self) -> None:
        """``/start`` with no args yields the site-name greeting + Contact us button."""
        from telegram_bot.handlers.login import handle_login_deep_link

        message = MagicMock()
        message.text = "/start"
        message.from_user = MagicMock()
        message.answer = AsyncMock()

        with patch(
            "telegram_bot.handlers.login.get_site_name_async",
            new=AsyncMock(return_value="MyBotSite"),
        ):
            await handle_login_deep_link(
                message=message, bot=MagicMock(), state=MagicMock()
            )

        message.answer.assert_awaited_once()
        sent_text = message.answer.await_args.args[0]
        assert "Welcome to MyBotSite!" in sent_text
        reply_markup = message.answer.await_args.kwargs["reply_markup"]
        button = reply_markup.inline_keyboard[0][0]
        assert button.callback_data == "contact_us"
        assert button.text == "Contact us"
