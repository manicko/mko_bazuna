"""Update-level deduplication middleware for the Telegram bot.

Deduplicates re-delivered Telegram updates by ``update_id`` using Django's
``cache.add`` atomic insert-if-absent primitive.  After a bot crash-restart,
Telegram re-delivers any update whose getUpdates offset had not yet been
acknowledged; without dedup this triggers a second ``create_draft_ad`` and its
side-effects (duplicate DRAFT row, re-translation, photo writes) on the same
``Ad``.

``cache.add`` returns ``True`` only on the first insertion of the key — the
exact primitive used by the search/rate-limit services (see
``apps.search.services.rate_limit`` and
``telegram_bot.services.rate_limit``).  On re-delivery it returns ``False`` and
the middleware short-circuits (``return None``) before any handler runs.

Fail-open: if the cache backend is unreachable, the middleware logs a warning
and proceeds — a Redis outage degrades to "no dedup" rather than dropping
legitimate traffic.  This mirrors the pattern in
``apps.lookups.signals.invalidate_lookup_cache``.
"""

import logging
from collections.abc import Awaitable, Callable
from typing import Any, Final

import redis
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject
from asgiref.sync import sync_to_async
from django.core.cache import cache
from django_redis.exceptions import ConnectionInterrupted

logger = logging.getLogger(__name__)

# 24-hour TTL — outlives bot restarts and Telegram's re-delivery window.
DEDUP_TTL_SECONDS: Final[int] = 86400


class UpdateIdDedupMiddleware(BaseMiddleware):
    """Deduplicate re-delivered Telegram updates by ``update_id``.

    Registered as an update-level middleware via ``dp.update.middleware(...)``,
    the event is always an ``aiogram.types.Update`` (verified at runtime) whose
    ``update_id`` is a required ``int``.  The first arrival of an ``update_id``
    inserts the cache key and proceeds; every re-delivery finds the key already
    present, short-circuits, and returns ``None`` so no downstream handler
    (ad creation, translation, photo storage) runs a second time.
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        update_id: int = event.update_id

        try:
            added = await sync_to_async(cache.add)(
                f"bot_update:{update_id}", 1, timeout=DEDUP_TTL_SECONDS
            )
        except (ConnectionInterrupted, redis.RedisError):
            logger.warning(
                "Cache backend unavailable — skipping dedup guard for "
                "update_id=%s (fail-open)",
                update_id,
            )
            return await handler(event, data)

        if not added:
            logger.warning(
                "Re-delivered update_id=%s detected — suppressing handler "
                "to prevent duplicate side-effects",
                update_id,
            )
            return None

        return await handler(event, data)
