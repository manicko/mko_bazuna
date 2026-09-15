"""
Tests for site name injection in bot greeting messages.

Verifies that ``get_site_name_async`` is wired into the bot's /start welcome
message and the /post command greeting, so the admin-configured site name
surfaces in user-facing bot messages (R-SN-05).

All tests are pure mocks — no database access required.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytestmark = [pytest.mark.unit]


# ---------------------------------------------------------------------------
# /start welcome greeting
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_login_welcome_greeting_contains_site_name() -> None:
    """The /start welcome message includes the configured site name."""
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


# ---------------------------------------------------------------------------
# /post command greeting
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_post_command_greeting_contains_site_name() -> None:
    """The /post command greeting includes the configured site name."""
    from telegram_bot.handlers.ad_create import cmd_post

    state = MagicMock()
    state.get_data = AsyncMock(return_value={"user_id": 123})
    state.set_state = AsyncMock()
    state.update_data = AsyncMock()

    fresh_ad = MagicMock()
    fresh_ad.id = 42

    message = MagicMock()
    message.from_user = MagicMock()
    message.answer = AsyncMock()

    with (
        patch(
            "telegram_bot.handlers.ad_create.create_draft_ad",
            new=AsyncMock(return_value=fresh_ad),
        ),
        patch(
            "telegram_bot.handlers.ad_create.get_site_name_async",
            new=AsyncMock(return_value="MyBotSite"),
        ),
    ):
        await cmd_post(message=message, state=state)

    message.answer.assert_awaited_once()
    sent_text = message.answer.await_args.args[0]
    assert "Welcome to MyBotSite!" in sent_text
