"""
Smoke tests for TST-006: bot entry point wiring.

Verifies that configure_dispatcher() registers all 6 routers and 5 middleware
in the correct order, and that the dp test fixture includes all routers
(matching production).
"""

from __future__ import annotations

import pytest
from aiogram import Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

pytestmark = [pytest.mark.unit]


# Router singleton names from telegram_bot.handlers — used to reset their
# parent_router between test invocations of configure_dispatcher() (aiogram
# forbids re-attaching an already-attached Router).
_ALL_ROUTERS = [
    "ad_copy_router",
    "ad_create_router",
    "alerts_router",
    "contact_router",
    "language_router",
    "login_router",
]


@pytest.fixture(autouse=True)
def _reset_router_parents() -> None:
    """Clear ``_parent_router`` on every router singleton so
    ``configure_dispatcher()`` can be invoked multiple times in the same
    process (each test gets a fresh Dispatcher)."""
    from telegram_bot import handlers

    for name in _ALL_ROUTERS:
        router = getattr(handlers, name)
        router._parent_router = None  # noqa: SLF001 — test-only reset


def test_configure_dispatcher_registers_all_six_routers() -> None:
    """configure_dispatcher includes all 6 production routers."""
    from telegram_bot.handlers import (
        ad_copy_router,
        ad_create_router,
        alerts_router,
        contact_router,
        language_router,
        login_router,
    )
    from telegram_bot.main import configure_dispatcher

    dp = configure_dispatcher(MemoryStorage())
    registered = set(id(r) for r in dp.sub_routers)
    assert id(login_router) in registered
    assert id(ad_create_router) in registered
    assert id(alerts_router) in registered
    assert id(ad_copy_router) in registered
    assert id(language_router) in registered
    assert id(contact_router) in registered
    assert len(dp.sub_routers) == 6


def test_configure_dispatcher_registers_five_middleware() -> None:
    """configure_dispatcher registers all 5 production middleware.

    Middleware order matters (FQ-001: Language before AccountState), so we
    verify both count and the ordering constraint.
    """
    from telegram_bot.main import configure_dispatcher

    dp = configure_dispatcher(MemoryStorage())

    # Collect middleware class names from the update-level inner stack.
    inner_mw = [type(mw).__name__ for mw in dp.update.middleware._middlewares]

    assert "UpdateIdDedupMiddleware" in inner_mw
    assert "LivenessMiddleware" in inner_mw
    assert "LanguageMiddleware" in inner_mw
    assert "AccountStateMiddleware" in inner_mw

    # DatabaseConnectionMiddleware is registered as an outer middleware.
    outer_mw = [type(mw).__name__ for mw in dp.update.outer_middleware._middlewares]
    assert "DatabaseConnectionMiddleware" in outer_mw


def test_language_middleware_before_account_state() -> None:
    """FQ-001: LanguageMiddleware must be registered before AccountStateMiddleware."""
    from telegram_bot.main import configure_dispatcher

    dp = configure_dispatcher(MemoryStorage())
    inner_mw = [type(mw).__name__ for mw in dp.update.middleware._middlewares]

    lang_idx = inner_mw.index("LanguageMiddleware")
    account_idx = inner_mw.index("AccountStateMiddleware")
    assert lang_idx < account_idx, (
        "LanguageMiddleware must be registered before AccountStateMiddleware "
        "(FQ-001: locale gate must run first so denial messages render in "
        "the user's preferred language)"
    )


def test_dp_fixture_includes_ad_copy_and_language_routers(dp: Dispatcher) -> None:
    """The dp test fixture includes ad_copy_router and language_router
    (both were missing before TST-006)."""
    from telegram_bot.handlers import ad_copy_router, language_router

    registered = set(id(r) for r in dp.sub_routers)
    assert id(ad_copy_router) in registered
    assert id(language_router) in registered


def test_dp_fixture_matches_production_router_count(dp: Dispatcher) -> None:
    """The dp fixture wires the same 6 routers as production."""
    assert len(dp.sub_routers) == 6


def test_configure_dispatcher_accepts_redis_storage() -> None:
    """configure_dispatcher works with RedisStorage (not just MemoryStorage).

    The storage parameter is typed as BaseStorage, so RedisStorage must be
    accepted without error.
    """
    from aiogram.fsm.storage.redis import RedisStorage

    from telegram_bot.main import configure_dispatcher

    storage = RedisStorage.from_url("redis://localhost:6379/0")
    try:
        dp = configure_dispatcher(storage)
        assert isinstance(dp, Dispatcher)
    finally:
        # Close the Redis connection to avoid resource leaks.
        import asyncio

        try:
            asyncio.get_running_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            loop.run_until_complete(storage.close())
            loop.close()


def test_configure_dispatcher_registers_error_handler() -> None:
    """configure_dispatcher registers the TelegramRetryAfter error handler (EXT-002)."""
    from telegram_bot.main import configure_dispatcher

    dp = configure_dispatcher(MemoryStorage())

    # The dp.errors handler for TelegramRetryAfter must be registered.
    assert len(dp.errors.handlers) >= 1
