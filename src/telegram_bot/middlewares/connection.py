"""Bot DB-connection lifecycle middleware.

Closes Django's thread-local database connection at the end of each bot
update, mirroring the per-request ``close_old_connections()`` hook that fires
in the HTTP layer (``request_finished`` signal) but never in aiogram's polling
loop.

asgiref's ``sync_to_async(thread_sensitive=True)`` (the default) parks all
ORM calls on a single shared worker thread that holds its own
``BaseDatabaseWrapper`` (thread-local,
``ConnectionHandler.thread_critical=True``).  Calling ``close_old_connections()``
from the async event-loop thread would target the wrong thread or raise
``SynchronousOnlyOperation`` (because ``BaseDatabaseWrapper.close`` is
``@async_unsafe``).  We therefore dispatch the call through ``sync_to_async``
so it lands on the same worker thread.
"""

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject
from asgiref.sync import sync_to_async
from django.db import close_old_connections

logger = logging.getLogger(__name__)


class DatabaseConnectionMiddleware(BaseMiddleware):
    """Close stale DB connections after each bot update.

    Wraps the entire update dispatch in ``try/finally``.  The ``finally`` block
    calls ``close_old_connections()`` via ``sync_to_async`` so it runs on the
    asgiref worker thread that owns the thread-local ORM connection.  With
    ``CONN_MAX_AGE=0`` the connection is closed unconditionally; the next
    update's ORM call reconnects transparently.
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        try:
            return await handler(event, data)
        finally:
            await sync_to_async(close_old_connections)()
