"""Telegram bot entrypoint - aiogram 3.x with Django ORM."""

import logging
import os

import django

# Configure Django settings and initialize the app registry BEFORE importing any
# module that pulls Django models (e.g. telegram_bot.middlewares).
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.prod")
django.setup()

from aiogram import Bot, Dispatcher  # noqa: E402
from aiogram.fsm.storage.memory import MemoryStorage  # noqa: E402
from telegram_bot.middlewares import AccountStateMiddleware  # noqa: E402
from django.conf import settings  # noqa: E402
from django.db import close_old_connections, connections  # noqa: E402

logger = logging.getLogger(__name__)


async def _on_shutdown(*args: object, **kwargs: object) -> None:
    """Close all Django ORM database connections on bot shutdown.

    Registered as an aiogram shutdown callback so that when ``run_polling``
    tears down on SIGTERM/SIGINT, every connection Django opened (including
    worker-thread backends used by ``@sync_to_async`` handlers) is released
    cleanly before the process exits.

    Kept side-effect-free beyond connection close so it can later be extracted
    to a shared ``lifecycle.py`` module (see ENT-005).
    """
    connections.close_all()
    close_old_connections()


def main() -> None:
    """Run the Telegram bot."""
    # BOT_TOKEN comes from Django settings (loaded via django-environ at base.py).
    # In production, an empty token raises ImproperlyConfigured at settings import time (prod.py guard).
    # In development (DEBUG=True), an empty token is permitted; the bot skips startup below.
    token = settings.BOT_TOKEN

    # Skip bot startup if token is empty/missing (development mode)
    if not token:
        logger.warning("BOT_TOKEN not set - skipping bot startup (development mode)")
        return

    # Storage: MemoryStorage (FSM state in memory, Ad.DRAFT in ORM)
    # NOTE: MemoryStorage is ephemeral — FSM state is cleared on bot restart.
    # There is no cross-process broadcast: if the bot is restarted while a user
    # is mid-FSM, the in-progress dialog is lost. The Ad.DRAFT row in the ORM
    # survives, but the FSM state machine state does not.
    # Future: switch to RedisStorage for persistent FSM across restarts.
    storage = MemoryStorage()
    dp = Dispatcher(storage=storage)

    # Register account state middleware
    dp.message.middleware(AccountStateMiddleware())

    # Include routers
    from telegram_bot.handlers import (
        login_router,
        ad_create_router,
        alerts_router,
        ad_copy_router,
        language_router,
        contact_router,
    )

    dp.include_router(login_router)
    dp.include_router(ad_create_router)
    dp.include_router(alerts_router)
    dp.include_router(ad_copy_router)
    dp.include_router(language_router)
    dp.include_router(contact_router)

    # Create bot and start polling
    bot = Bot(token=token)

    logger.info("Bot starting with FSM for ad creation...")

    # Graceful shutdown: fire _on_shutdown on SIGTERM/SIGINT (via aiogram's
    # built-in signal handling in run_polling) to close Django DB connections.
    dp.shutdown.register(_on_shutdown)

    dp.run_polling(bot)


if __name__ == "__main__":
    main()
