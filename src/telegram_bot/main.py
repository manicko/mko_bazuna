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

logger = logging.getLogger(__name__)


def main() -> None:
    """Run the Telegram bot."""
    token = os.getenv("BOT_TOKEN")
    if not token:
        logger.warning("BOT_TOKEN not set - bot not running")
        return

    # Storage: MemoryStorage (FSM state in memory, Ad.DRAFT in ORM)
    storage = MemoryStorage()
    dp = Dispatcher(storage=storage)

    # Register account state middleware
    dp.message.middleware(AccountStateMiddleware())

    # Include routers
    from telegram_bot.handlers import login_router, ad_create_router

    dp.include_router(login_router)
    dp.include_router(ad_create_router)

    # Create bot and start polling
    bot = Bot(token=token)

    logger.info("Bot starting with FSM for ad creation...")

    dp.run_polling(bot)


if __name__ == "__main__":
    main()
