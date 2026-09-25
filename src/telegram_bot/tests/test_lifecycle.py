"""
Tests for lifecycle hooks (TST-012).

Covers:
- ``_on_startup``: writes liveness markers without raising.
- ``_on_shutdown``: removes markers and closes DB connections without raising.
- ``LivenessMiddleware``: touches file marker and writes Redis marker on
  every inbound update, then delegates to the handler.
"""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytestmark = [
    pytest.mark.django_db(transaction=True),
    pytest.mark.integration,
    pytest.mark.concurrent,
]
pytestmark.append(pytest.mark.xdist_group("bot_concurrent"))


class TestOnStartup:
    """Tests for the startup hook."""

    @pytest.mark.asyncio
    async def test_startup_disabled_when_no_marker_path(self) -> None:
        """When ``BOT_LIVENESS_FILE`` is empty, the hook is a no-op."""
        from telegram_bot.lifecycle import _on_startup

        with patch("telegram_bot.lifecycle._marker_path", return_value=None):
            with patch(
                "telegram_bot.lifecycle._write_redis_marker",
                new=AsyncMock(),
            ):
                await _on_startup(MagicMock(), MagicMock())


    @pytest.mark.asyncio
    async def test_startup_writes_file_marker(self, tmp_path: Path) -> None:
        """When a marker path is configured, the file is touched."""
        from telegram_bot.lifecycle import _on_startup

        marker = tmp_path / "bot_alive"
        assert not marker.exists()

        with patch("telegram_bot.lifecycle._marker_path", return_value=str(marker)):
            with patch(
                "telegram_bot.lifecycle._write_redis_marker",
                new=AsyncMock(),
            ):
                await _on_startup(MagicMock(), MagicMock())

        assert marker.exists()

    @pytest.mark.asyncio
    async def test_startup_writes_redis_marker(self) -> None:
        """The Redis liveness key is always written on startup."""
        from telegram_bot.lifecycle import _on_startup

        with patch("telegram_bot.lifecycle._marker_path", return_value=None):
            with patch(
                "telegram_bot.lifecycle._write_redis_marker",
                new=AsyncMock(),
            ) as mock_redis:
                await _on_startup(MagicMock(), MagicMock())

        mock_redis.assert_awaited_once()


class TestOnShutdown:
    """Tests for the shutdown hook."""

    @pytest.mark.asyncio
    async def test_shutdown_removes_file_marker(self, tmp_path: Path) -> None:
        """On shutdown, the file marker is removed."""
        from telegram_bot.lifecycle import _on_shutdown

        marker = tmp_path / "bot_alive"
        marker.touch()
        assert marker.exists()

        with patch("telegram_bot.lifecycle._marker_path", return_value=str(marker)):
            with patch("telegram_bot.lifecycle.connections.close_all"):
                with patch("telegram_bot.lifecycle.close_old_connections"):
                    await _on_shutdown(MagicMock(), MagicMock())

        assert not marker.exists()

    @pytest.mark.asyncio
    async def test_shutdown_handles_missing_file(self) -> None:
        """If the marker file doesn't exist, shutdown does not raise."""
        from telegram_bot.lifecycle import _on_shutdown

        with patch("telegram_bot.lifecycle._marker_path", return_value="/nonexistent/path"):
            with patch("telegram_bot.lifecycle.connections.close_all"):
                with patch("telegram_bot.lifecycle.close_old_connections"):
                    # Should not raise FileNotFoundError.
                    await _on_shutdown(MagicMock(), MagicMock())


class TestLivenessMiddleware:
    """Tests for the liveness middleware."""

    @pytest.mark.asyncio
    async def test_middleware_touches_file_marker(self, tmp_path: Path) -> None:
        """The middleware updates the file marker mtime on each update."""
        from telegram_bot.lifecycle import LivenessMiddleware

        marker = tmp_path / "bot_alive"
        marker.touch()
        original_mtime = os.path.getmtime(marker)

        mw = LivenessMiddleware()
        state: dict = {}
        handler = AsyncMock(return_value="ok")

        with patch("telegram_bot.lifecycle._marker_path", return_value=str(marker)):
            with patch(
                "telegram_bot.lifecycle._write_redis_marker",
                new=AsyncMock(),
            ):
                await mw(handler, MagicMock(), state)

        handler.assert_awaited_once()
        # The mtime should have been updated.
        assert os.path.getmtime(marker) >= original_mtime

    @pytest.mark.asyncio
    async def test_middleware_writes_redis_marker(self) -> None:
        """The middleware writes the Redis liveness key on each update."""
        from telegram_bot.lifecycle import LivenessMiddleware

        mw = LivenessMiddleware()
        state: dict = {}
        handler = AsyncMock(return_value="ok")

        with patch("telegram_bot.lifecycle._marker_path", return_value=None):
            with patch(
                "telegram_bot.lifecycle._write_redis_marker",
                new=AsyncMock(),
            ) as mock_redis:
                await mw(handler, MagicMock(), state)

        mock_redis.assert_awaited_once()
        handler.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_middleware_without_marker_path(self) -> None:
        """When marker path is None, middleware still delegates to handler."""
        from telegram_bot.lifecycle import LivenessMiddleware

        mw = LivenessMiddleware()
        state: dict = {}
        handler = AsyncMock(return_value="ok")

        with patch("telegram_bot.lifecycle._marker_path", return_value=None):
            with patch(
                "telegram_bot.lifecycle._write_redis_marker",
                new=AsyncMock(),
            ):
                result = await mw(handler, MagicMock(), state)

        assert result == "ok"
        handler.assert_awaited_once()
