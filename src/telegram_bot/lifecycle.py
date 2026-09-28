"""Bot process lifecycle hooks — startup/shutdown markers and liveness middleware.

Provides two complementary liveness markers:
- File-based: ``BOT_LIVENESS_FILE`` — touched on startup and every inbound update.
  The Docker ``healthcheck-bot.sh`` reads this for readiness + staleness.
- Redis-based: ``bot:liveness`` cache key — written on startup and every update
  and read by the web readiness probe (``/health/ready/``) so the web container
  reports Not Ready when the bot is stuck. (OPS-003)

Both markers are fail-open: a failure to write either is logged but does not
disrupt bot operation.  See ENT-005.
"""

import asyncio
import logging
import os
from collections.abc import Awaitable, Callable
from pathlib import Path
from time import time as _now
from typing import Any, Final

from aiogram import BaseMiddleware, Bot
from aiogram.types import BotCommand, TelegramObject
from asgiref.sync import sync_to_async
from django.conf import settings
from django.core.cache import cache
from django.db import close_old_connections, connections

logger = logging.getLogger(__name__)


# Localized Telegram command menu (EC-3). The ru/bs entries carry their final
# localized descriptions directly as literals. The en entries are English
# literals too (NOT gettext msgids): using eager ``_()`` here would freeze
# them to the import-time locale (``settings.LANGUAGE_CODE``, Russian in
# production), which would leak Russian text into the ``language="en"`` menu.
_COMMANDS: dict[str, list[BotCommand]] = {
    "ru": [
        BotCommand(command="start", description="Начать"),
        BotCommand(command="language", description="Язык"),
        BotCommand(command="post", description="Разместить объявление"),
        BotCommand(command="alerts", description="Уведомления"),
    ],
    "bs": [
        BotCommand(command="start", description="Početak"),
        BotCommand(command="language", description="Jezik"),
        BotCommand(command="post", description="Objavi oglas"),
        BotCommand(command="alerts", description="Obavještenja"),
    ],
    "en": [
        BotCommand(command="start", description="Start"),
        BotCommand(command="language", description="Language"),
        BotCommand(command="post", description="Post ad"),
        BotCommand(command="alerts", description="Alerts"),
    ],
}


# Whole-registration budget (seconds) for the command-menu setup at startup
# (ENT-007). The menu is best-effort, so it must never gate bot readiness:
# the file/Redis liveness markers are written before this runs, and this
# bound caps the worst-case startup stall well under the healthcheck's
# ``start_period: 30s``. A healthy run completes in well under a second, so
# 10s (also the healthcheck ``timeout``) is generous for four sequential
# ``set_my_commands`` round-trips while keeping the unhealthy worst case small.
_BOT_COMMANDS_SETUP_TIMEOUT: Final[float] = 10.0


def _marker_path() -> str | None:
    """Return the configured liveness marker path, or None if disabled.

    A falsy ``BOT_LIVENESS_FILE`` (e.g. ``""`` in test settings) disables all
    marker operations so the hooks and middleware become safe no-ops.
    """
    path = getattr(settings, "BOT_LIVENESS_FILE", "")
    return path or None


async def _write_redis_marker() -> None:
    """Write the Redis-based ``bot:liveness`` marker (epoch timestamp).

    Fail-open: if the cache backend is unreachable the exception is logged at
    debug level and swallowed — the file-based marker remains the fallback.
    """
    try:
        await sync_to_async(cache.set)(
            "bot:liveness",
            int(_now()),
            timeout=settings.BOT_HEALTH_STALE_SECONDS,
        )
    except Exception:
        logger.debug("Could not write bot liveness marker to Redis")


async def _set_bot_commands(bot: Bot) -> None:
    """Register the localized command menu, fail-open on API errors.

    Calls ``set_my_commands`` once per configured language so users see the
    command menu in their preferred locale, plus the default (no-language)
    scope so it never falls back empty. A failure on any scope is logged and
    skipped — the bot still starts polling (EC-3).
    """
    for lang, commands in _COMMANDS.items():
        try:
            await bot.set_my_commands(commands, language=lang)
        except Exception:
            logger.warning(
                "Failed to set bot commands for language %s; continuing", lang
            )
            continue
    try:
        await bot.set_my_commands(_COMMANDS["en"])
    except Exception:
        logger.warning("Failed to set default bot commands; continuing")


async def _on_startup(*args: Any, **kwargs: Any) -> None:
    """Write liveness markers and register the command menu at startup.

    Fires after ``Bot(token)`` succeeds and the Dispatcher is wired — but
    before ``run_polling`` enters its loop — so a missing marker always means
    the bot has not yet become ready.

    Writes both the file-based marker (read by ``healthcheck-bot.sh``) and the
    Redis ``bot:liveness`` key (read by the web readiness probe) before any
    network I/O. The localized command-menu registration (EC-3) runs *after*
    the markers, under a bounded ``asyncio.wait_for`` budget so a slow or
    unresponsive Telegram API can never gate readiness (ENT-007). A failure
    there — including a budget timeout — is logged but does not abort startup.
    """
    path = _marker_path()
    if path:
        Path(path).touch()
        logger.info("Bot liveness marker written: %s", path)
    await _write_redis_marker()
    bot = kwargs.get("bot")
    if bot is not None:
        try:
            await asyncio.wait_for(
                _set_bot_commands(bot), _BOT_COMMANDS_SETUP_TIMEOUT
            )
        except Exception:
            logger.warning("Failed to register bot commands at startup")


async def _on_shutdown(*args: Any, **kwargs: Any) -> None:
    """Remove the liveness marker and close Django DB connections.

    Consolidates the shutdown logic from ``telegram_bot.main`` (ENT-004) into a
    shared module so both production and tests use the same cleanup path.
    """
    path = _marker_path()
    if path:
        try:
            os.remove(path)
        except FileNotFoundError:
            pass
        except OSError as exc:
            logger.warning("Could not remove liveness marker %s: %s", path, exc)
    await sync_to_async(connections.close_all)()
    await sync_to_async(close_old_connections)()


class LivenessMiddleware(BaseMiddleware):
    """Touch liveness markers on every inbound update (freshness signal).

    Updating the marker mtime / Redis timestamp on each processed update lets
    the healthcheck's staleness check detect retry-loops or stuck polling.
    Also writes the Redis ``bot:liveness`` key read by the web readiness probe.
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        path = _marker_path()
        if path:
            try:
                os.utime(path, None)
            except FileNotFoundError:
                pass
            except OSError as exc:
                logger.debug("Could not touch liveness marker %s: %s", path, exc)
        await _write_redis_marker()
        return await handler(event, data)
