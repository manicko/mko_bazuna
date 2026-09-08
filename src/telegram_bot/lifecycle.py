"""Bot process lifecycle hooks — startup/shutdown markers and liveness middleware.

Provides a file-based liveness marker so the Docker healthcheck can verify
*readiness* (bot reached the polling loop and is processing updates) in addition
to *liveness* (PID is alive).  See ENT-005.
"""

import logging
import os
from pathlib import Path
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject
from django.conf import settings
from django.db import close_old_connections, connections

logger = logging.getLogger(__name__)


def _marker_path() -> str | None:
    """Return the configured liveness marker path, or None if disabled.

    A falsy ``BOT_LIVENESS_FILE`` (e.g. ``""`` in test settings) disables all
    marker operations so the hooks and middleware become safe no-ops.
    """
    path = getattr(settings, "BOT_LIVENESS_FILE", "")
    return path or None


async def _on_startup(*args: Any, **kwargs: Any) -> None:
    """Write the liveness marker once the bot reaches the polling loop.

    Fires after ``Bot(token)`` succeeds and the Dispatcher is wired — but
    before ``run_polling`` enters its loop — so a missing marker always means
    the bot has not yet become ready.
    """
    path = _marker_path()
    if path:
        Path(path).touch()
        logger.info("Bot liveness marker written: %s", path)


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
    connections.close_all()
    close_old_connections()


class LivenessMiddleware(BaseMiddleware):
    """Touch the liveness marker on every inbound update (freshness signal).

    Updating the marker mtime on each processed update lets the healthcheck's
    optional staleness check detect retry-loops or stuck polling.
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
        return await handler(event, data)
