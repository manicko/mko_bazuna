"""Tests for ``telegram_bot.middlewares.update_id_dedup.UpdateIdDedupMiddleware``.

Verifies the three delivery outcomes with no real cache backend or Telegram
connection — ``cache.add`` is monkeypatched on the middleware module and the
handler event is a lightweight ``MagicMock``.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from django_redis.exceptions import ConnectionInterrupted

import telegram_bot.middlewares.update_id_dedup as dedup_module
from telegram_bot.middlewares import UpdateIdDedupMiddleware

pytestmark = [pytest.mark.unit, pytest.mark.asyncio]


def _make_event(update_id: int = 42) -> MagicMock:
    """Return a minimal mock event carrying the required ``update_id``."""
    event = MagicMock()
    event.update_id = update_id
    return event


class TestUpdateIdDedupMiddleware:
    """Behaviour under the three delivery outcomes."""

    async def test_first_delivery_proceeds(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """cache.add returns True (first arrival) -> handler is invoked."""
        mock_cache = MagicMock()
        mock_cache.add.return_value = True
        monkeypatch.setattr(dedup_module, "cache", mock_cache)

        handler = AsyncMock(return_value="proceeded")
        event = _make_event(update_id=123456)

        result = await UpdateIdDedupMiddleware()(handler, event, {})

        assert result == "proceeded"
        handler.assert_awaited_once_with(event, {})
        mock_cache.add.assert_called_once_with("bot_update:123456", 1, timeout=86400)

    async def test_redelivered_update_skipped(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """cache.add returns False (re-delivery) -> handler NOT invoked, returns None."""
        mock_cache = MagicMock()
        mock_cache.add.return_value = False
        monkeypatch.setattr(dedup_module, "cache", mock_cache)

        handler = AsyncMock(return_value="should-not-run")
        event = _make_event(update_id=789)

        result = await UpdateIdDedupMiddleware()(handler, event, {})

        assert result is None
        handler.assert_not_awaited()
        mock_cache.add.assert_called_once_with("bot_update:789", 1, timeout=86400)

    async def test_redis_unavailable_fail_open(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """cache.add raises ConnectionInterrupted -> fail-open, handler still invoked."""
        mock_cache = MagicMock()
        mock_cache.add.side_effect = ConnectionInterrupted(None)
        monkeypatch.setattr(dedup_module, "cache", mock_cache)

        handler = AsyncMock(return_value="fail-open")
        event = _make_event(update_id=999)

        result = await UpdateIdDedupMiddleware()(handler, event, {})

        assert result == "fail-open"
        handler.assert_awaited_once_with(event, {})
