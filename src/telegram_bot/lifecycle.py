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

import logging
import os
from collections.abc import Awaitable, Callable
from pathlib import Path
from time import time as _now
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject
from asgiref.sync import sync_to_async
from django.conf import settings
from django.core.cache import cache
from django.db import close_old_connections, connections

logger = logging.getLogger(__name__)


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


async def _on_startup(*args: Any, **kwargs: Any) -> None:
    """Write liveness markers once the bot reaches the polling loop.

    Fires after ``Bot(token)`` succeeds and the Dispatcher is wired — but
    before ``run_polling`` enters its loop — so a missing marker always means
    the bot has not yet become ready.

    Writes both the file-based marker (read by ``healthcheck-bot.sh``) and the
    Redis ``bot:liveness`` key (read by the web readiness probe).
    """
    path = _marker_path()
    if path:
        Path(path).touch()
        logger.info("Bot liveness marker written: %s", path)
    await _write_redis_marker()


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
