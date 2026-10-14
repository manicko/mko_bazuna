"""Shared mock helpers for telegram_bot tests.

These helpers build lightweight ``MagicMock`` stand-ins for Telegram
``Message`` objects and aiogram ``FSMContext`` so that handler unit tests can
run without a real bot or FSM storage.  Each function covers the union of
parameters used across every call site in the bot test suite.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

# Telegram user_id used across the bot test suite for mock FSM payloads.
# Matches the bot-conftest seller fixture telegram_id (900000100).
TEST_SELLER_ID = 900000100


def build_state(data: dict) -> MagicMock:
    """Build a mock FSMContext backed by the given state *data*.

    The returned ``MagicMock`` exposes the full set of async methods the bot
    handlers may call (``get_data``, ``clear``, ``update``, ``update_data``,
    ``set_state``) so callers can assert on whichever subset they care about.
    """
    state = MagicMock()
    state.get_data = AsyncMock(return_value=data)
    state.clear = AsyncMock()
    state.update = AsyncMock()
    state.update_data = AsyncMock()
    state.set_state = AsyncMock()
    return state


def build_message(
    language_code: str | None = "en-US",
    text: str = "confirm",
) -> MagicMock:
    """Build a mock Telegram ``Message``.

    Args:
        language_code: Set on ``message.from_user.language_code``.  Pass
            ``None`` to simulate a missing locale.
        text: Set on ``message.text``.
    """
    user_mock = MagicMock()
    user_mock.language_code = language_code
    user_mock.id = TEST_SELLER_ID
    user_mock.username = None
    user_mock.first_name = "Test"
    user_mock.last_name = "User"
    message = MagicMock()
    message.text = text
    message.from_user = user_mock
    message.answer = AsyncMock()
    return message


def build_photo_message(file_size: int | None = 1024) -> MagicMock:
    """Build a mock Telegram ``Message`` carrying a single photo upload.

    Args:
        file_size: The ``PhotoSize.file_size`` value.  Defaults to 1024
            (within the 2 MB limit).  Pass ``None`` to simulate Telegram
            omitting the field, or an int above the limit to trigger
            rejection.
    """
    photo_item = MagicMock()
    photo_item.file_id = "test_file_id"
    photo_item.file_size = file_size
    message = MagicMock()
    message.text = None
    message.photo = [photo_item]
    message.answer = AsyncMock()
    message.bot = MagicMock()
    return message


async def mock_translate(text: str, target_locales: list[str]) -> dict[str, str]:
    """Return deterministic translations without hitting the real API."""
    return {loc: f"{text}-{loc}" for loc in target_locales}
