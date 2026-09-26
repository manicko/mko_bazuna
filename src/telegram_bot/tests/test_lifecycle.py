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


class TestSetBotCommands:
    """Tests for the localized command-menu registration (EC-3)."""

    @pytest.mark.asyncio
    async def test_set_commands_per_language(self) -> None:
        """``_set_bot_commands`` registers the menu for every configured language."""
        from telegram_bot.lifecycle import _COMMANDS, _set_bot_commands

        bot = MagicMock()
        bot.set_my_commands = AsyncMock()

        await _set_bot_commands(bot)

        # One call per language plus the default (no-language) scope.
        expected_calls = len(_COMMANDS) + 1
        assert bot.set_my_commands.await_count == expected_calls

        for lang, commands in _COMMANDS.items():
            bot.set_my_commands.assert_any_await(commands, language=lang)
        # The default scope reuses the English menu without a language.
        bot.set_my_commands.assert_any_await(_COMMANDS["en"])

        # Every language list carries the four canonical commands.
        expected_commands = {"start", "language", "post", "alerts"}
        for commands in _COMMANDS.values():
            assert {c.command for c in commands} == expected_commands

    @pytest.mark.asyncio
    async def test_set_commands_fail_open(self) -> None:
        """A failing ``set_my_commands`` is logged, not raised."""
        from telegram_bot.lifecycle import _set_bot_commands

        bot = MagicMock()
        bot.set_my_commands = AsyncMock(side_effect=RuntimeError("api down"))

        # Must not propagate the error.
        await _set_bot_commands(bot)


class TestOnStartupCommands:
    """Startup registers the command menu and swallows failures."""

    @pytest.mark.asyncio
    async def test_startup_sets_commands(self) -> None:
        """Startup calls ``_set_bot_commands`` with the bot kwarg."""
        from telegram_bot.lifecycle import _on_startup

        bot = MagicMock()

        with patch("telegram_bot.lifecycle._marker_path", return_value=None):
            with patch(
                "telegram_bot.lifecycle._write_redis_marker",
                new=AsyncMock(),
            ):
                with patch(
                    "telegram_bot.lifecycle._set_bot_commands",
                    new=AsyncMock(),
                ) as mock_set_commands:
                    await _on_startup(MagicMock(), bot=bot)

        mock_set_commands.assert_awaited_once_with(bot)

    @pytest.mark.asyncio
    async def test_startup_swallows_command_failure(self) -> None:
        """A ``set_my_commands`` failure on startup does not abort polling."""
        from telegram_bot.lifecycle import _on_startup

        bot = MagicMock()
        bot.set_my_commands = AsyncMock(side_effect=RuntimeError("api down"))

        with patch("telegram_bot.lifecycle._marker_path", return_value=None):
            with patch(
                "telegram_bot.lifecycle._write_redis_marker",
                new=AsyncMock(),
            ):
                # Must not propagate the error from set_my_commands.
                await _on_startup(MagicMock(), bot=bot)

    @pytest.mark.asyncio
    async def test_startup_without_bot(self) -> None:
        """Startup proceeds when no bot kwarg is provided."""
        from telegram_bot.lifecycle import _on_startup

        with patch("telegram_bot.lifecycle._marker_path", return_value=None):
            with patch(
                "telegram_bot.lifecycle._write_redis_marker",
                new=AsyncMock(),
            ):
                await _on_startup(MagicMock(), MagicMock())


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
