"""Tests for ``telegram_bot.lifecycle`` shutdown hook.

The shutdown hook (``_on_shutdown``) must close Django DB connections via
``sync_to_async`` rather than calling sync functions directly on the event-loop
thread, where Django 5.2's ``@async_unsafe`` guard raises
``SynchronousOnlyOperation``.
"""

from collections.abc import Callable
from typing import Any

import pytest
from asgiref.sync import sync_to_async
from django.db import (
    close_old_connections as django_close_old_connections,
    connections as django_connections,
)

import telegram_bot.lifecycle as lifecycle_module
from apps.users.models import User

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


class TestOnShutdown:
    """Tests for the ``_on_shutdown`` lifecycle hook."""

    @pytest.mark.asyncio
    async def test_on_shutdown_closes_connections_via_sync_to_async(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Both ``connections.close_all`` and ``close_old_connections`` are
        dispatched through ``sync_to_async``.

        Guards against regression to the broken alternative of calling the sync
        DB methods directly on the event-loop thread, which would raise
        ``SynchronousOnlyOperation`` (since ``BaseDatabaseWrapper.close`` is
        ``@async_unsafe``).
        """
        captured: list[Callable[..., Any]] = []
        real_sync_to_async = lifecycle_module.sync_to_async

        def spy_sync_to_async(
            func: Callable[..., Any], *args: Any, **kwargs: Any
        ) -> Any:
            captured.append(func)
            return real_sync_to_async(func, *args, **kwargs)

        monkeypatch.setattr(lifecycle_module, "sync_to_async", spy_sync_to_async)

        await lifecycle_module._on_shutdown()

        assert len(captured) == 2
        assert django_close_old_connections in captured
        assert django_connections.close_all in captured

    @pytest.mark.asyncio
    async def test_on_shutdown_no_synchronous_only_operation(self) -> None:
        """``_on_shutdown`` must not raise ``SynchronousOnlyOperation`` from
        async context.

        Establishes a live DB connection on the asgiref worker thread (simulating
        real bot ORM work), then invokes the shutdown hook.  Before the fix, the
        direct call to ``close_old_connections()`` on the event-loop thread would
        raise ``SynchronousOnlyOperation`` (Django's ``@async_unsafe`` guard).
        """
        # Establish a live DB connection on the asgiref worker thread.
        await sync_to_async(User.objects.count)()
        # Must not raise SynchronousOnlyOperation or any other exception.
        await lifecycle_module._on_shutdown()
