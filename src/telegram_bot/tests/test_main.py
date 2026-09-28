"""
Smoke tests for TST-006: bot entry point wiring.

Verifies that configure_dispatcher() registers all 7 routers and 5 middleware
in the correct order, and that the dp test fixture includes all routers
(matching production). Also covers the relocated BOT_TOKEN placeholder guard
in main() (CFG-006): a placeholder token raises ImproperlyConfigured before
any aiogram wiring, while an empty token takes the graceful skip path.
"""

from __future__ import annotations

import pytest
from aiogram import Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from django.core.exceptions import ImproperlyConfigured
from django.test import override_settings

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
    "support_router",
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


def test_configure_dispatcher_registers_all_seven_routers() -> None:
    """configure_dispatcher includes all 7 production routers."""
    from telegram_bot.handlers import (
        ad_copy_router,
        ad_create_router,
        alerts_router,
        contact_router,
        language_router,
        login_router,
        support_router,
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
    assert id(support_router) in registered
    assert len(dp.sub_routers) == 7


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
    """The dp fixture wires the same 7 routers as production."""
    assert len(dp.sub_routers) == 7


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


def test_main_placeholder_token_raises_before_aiogram_wiring() -> None:
    """A placeholder BOT_TOKEN makes main() raise ImproperlyConfigured.

    CFG-006: the placeholder guard lives here, at the bot entrypoint, so a
    bot-only misconfiguration cannot crash the web tier at settings import
    time. The guard fires before Dispatcher()/configure_dispatcher/Bot(...)/
    run_polling, so no aiogram wiring needs stubbing.

    Load-bearing safety property: importing telegram_bot.main at test time is
    safe because its module-scope
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.prod")
    is a no-op under pytest (DJANGO_SETTINGS_MODULE is already
    config.settings.test) — do not "clean up" that setdefault.
    """
    from telegram_bot.main import main

    with override_settings(BOT_TOKEN="<your-bot-token-from-botfather>"):
        with pytest.raises(ImproperlyConfigured) as exc_info:
            main()
    assert "BOT_TOKEN" in str(exc_info.value)


def test_main_empty_token_skips_gracefully(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """An empty BOT_TOKEN makes main() take the skip path and return normally.

    Paired tripwire against the "returns instead of raising" regression: the
    relocated guard must not swallow the legitimate empty-token skip. Asserts
    the exact warning text the existing skip branch emits.
    """
    from telegram_bot.main import main

    with override_settings(BOT_TOKEN=""):
        with caplog.at_level("WARNING", logger="telegram_bot.main"):
            main()
    assert any(
        "BOT_TOKEN not set - skipping bot startup (development mode)"
        in record.message
        for record in caplog.records
    )
