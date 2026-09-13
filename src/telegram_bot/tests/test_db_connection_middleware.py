"""Tests for ``telegram_bot.middlewares.connection.DatabaseConnectionMiddleware``.

The middleware closes Django's thread-local DB connection after each bot update
— the async-world counterpart of the HTTP ``request_finished`` ->
``close_old_connections()`` hook.  Tests 1-4 exercise the middleware directly
with controlled async handlers; test 5 validates registration against the
conftest ``dp`` fixture.

Why direct invocation instead of ``Dispatcher.feed_update`` (the mandated
fallback): the conftest ``dp`` fixture cannot drive ``feed_update``:

* The ``bot`` fixture builds ``Bot(token=settings.BOT_TOKEN)``, but test
  settings set ``BOT_TOKEN = "test-bot-token-for-testing"``, which fails
  aiogram's token validation (``TokenValidationError``), so there is no valid
  Bot to feed updates into.
* Even with a synthetic valid-token Bot, the fixture includes
  ``ad_create_router``, whose state handlers register bare ``AdCreateState``
  ``StrEnum`` members as filters (``@router.message(AdCreateForm.category)``).
  aiogram does not wrap a bare ``StrEnum`` into a ``StateFilter``, so the
  resulting filter callback is a non-callable enum member and ``feed_update``
  raises ``TypeError: the first argument must be callable`` on the first state
  handler it inspects — for *any* inbound message.

The production handler-filter issue is out of scope for DB-001, so per the task's
fallback ("testing the middleware class directly with mock handlers, plus a
structure test on the dp fixture") the middleware is driven directly here.
"""

from collections.abc import Callable
from typing import Any

import pytest
from aiogram.types import TelegramObject
from asgiref.sync import sync_to_async
from django.db import close_old_connections as django_close_old_connections

import telegram_bot.middlewares.connection as connection_module
from apps.users.models import User
from telegram_bot.middlewares import (
    AccountStateMiddleware,
    DatabaseConnectionMiddleware,
)

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


def _make_event() -> TelegramObject:
    """Return a minimal, disposable event the middleware forwards to its handler."""
    return TelegramObject()


def _track_close(monkeypatch: pytest.MonkeyPatch) -> list[int]:
    """Spy on ``close_old_connections`` in the connection module.

    Replaces the module-global name with a tracker that records calls and then
    delegates to the real implementation, so assertions observe the *real*
    close behaviour rather than a stubbed no-op.
    """
    calls: list[int] = []
    real_close = connection_module.close_old_connections

    def tracking_close(*args: Any, **kwargs: Any) -> Any:
        calls.append(1)
        return real_close(*args, **kwargs)

    monkeypatch.setattr(connection_module, "close_old_connections", tracking_close)
    return calls


class TestDatabaseConnectionMiddleware:
    """Behaviour of ``DatabaseConnectionMiddleware`` around the handler call."""

    @pytest.mark.asyncio
    async def test_connection_closed_after_update(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """``close_old_connections`` runs after an update whose handler does ORM work.

        The handler performs a real ORM query via ``sync_to_async`` (dispatched to
        the asgiref worker thread that owns the thread-local connection); the
        middleware's ``finally`` must then close that connection.
        """
        calls = _track_close(monkeypatch)

        async def orm_handler(event: TelegramObject, data: dict[str, Any]) -> str:
            await sync_to_async(User.objects.count)()
            return "orm-done"

        result = await DatabaseConnectionMiddleware()(orm_handler, _make_event(), {})
        assert result == "orm-done"
        assert calls == [1]

    @pytest.mark.asyncio
    async def test_connection_closed_after_handler_exception(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The ``finally`` block still closes the connection when the handler raises."""
        calls = _track_close(monkeypatch)

        class HandlerError(Exception):
            pass

        async def raising_handler(event: TelegramObject, data: dict[str, Any]) -> Any:
            raise HandlerError("boom")

        with pytest.raises(HandlerError):
            await DatabaseConnectionMiddleware()(raising_handler, _make_event(), {})
        assert calls == [1]

    @pytest.mark.asyncio
    async def test_no_error_on_update_without_orm(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """No crash and close still fires for a handler that performs no ORM work."""
        calls = _track_close(monkeypatch)

        async def plain_handler(event: TelegramObject, data: dict[str, Any]) -> str:
            return "ok"

        result = await DatabaseConnectionMiddleware()(plain_handler, _make_event(), {})
        assert result == "ok"
        assert calls == [1]

    @pytest.mark.asyncio
    async def test_close_dispatched_via_sync_to_async(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """``close_old_connections`` must be wrapped through ``sync_to_async``.

        Guards against regression to the broken alternative of calling
        ``close_old_connections`` directly on the event-loop thread, which would
        target the wrong thread-local connection or raise
        ``SynchronousOnlyOperation`` (since ``BaseDatabaseWrapper.close`` is
        ``@async_unsafe``).
        """
        captured: list[Callable[..., Any]] = []
        real_sync_to_async = connection_module.sync_to_async

        def spy_sync_to_async(
            func: Callable[..., Any], *args: Any, **kwargs: Any
        ) -> Any:
            captured.append(func)
            return real_sync_to_async(func, *args, **kwargs)

        monkeypatch.setattr(connection_module, "sync_to_async", spy_sync_to_async)

        async def plain_handler(event: TelegramObject, data: dict[str, Any]) -> str:
            return "ok"

        await DatabaseConnectionMiddleware()(plain_handler, _make_event(), {})
        assert len(captured) == 1
        assert captured[0] is django_close_old_connections


class TestDatabaseConnectionMiddlewareRegistration:
    """Registration of the middleware on the production ``dp`` fixture."""

    def test_state_middleware_registration(self, dp: Any) -> None:
        """Verify middleware registration on the production ``dp`` fixture.

        After AUT-003: ``AccountStateMiddleware`` moved from ``dp.message`` to
        ``dp.update`` (inner chain).  ``DatabaseConnectionMiddleware`` remains on
        the outer chain.
        """
        outer = dp.update.outer_middleware._middlewares
        inner = dp.update.middleware._middlewares
        # DatabaseConnectionMiddleware wraps all inner middlewares (outer chain).
        assert any(isinstance(m, DatabaseConnectionMiddleware) for m in outer)
        assert not any(isinstance(m, DatabaseConnectionMiddleware) for m in inner)
        # AccountStateMiddleware is on the inner chain (AUT-003 fix).
        assert any(isinstance(m, AccountStateMiddleware) for m in inner)
        assert not any(isinstance(m, AccountStateMiddleware) for m in outer)
