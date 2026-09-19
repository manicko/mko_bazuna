"""Telegram bot entrypoint - aiogram 3.x with Django ORM."""

import json
import logging
import os

import django

# Configure Django settings and initialize the app registry BEFORE importing any
# module that pulls Django models (e.g. telegram_bot.middlewares).
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.prod")
django.setup()

from aiogram import Bot, Dispatcher  # noqa: E402
from aiogram.fsm.storage.memory import MemoryStorage  # noqa: E402
from aiogram.fsm.storage.redis import RedisStorage  # noqa: E402
from django.conf import settings  # noqa: E402

from telegram_bot.lifecycle import (  # noqa: E402
    LivenessMiddleware,
    _on_shutdown,
    _on_startup,
)
from telegram_bot.middlewares import (  # noqa: E402
    AccountStateMiddleware,
    DatabaseConnectionMiddleware,
    LanguageMiddleware,
    UpdateIdDedupMiddleware,
)

logger = logging.getLogger(__name__)


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

    # Storage: RedisStorage (persistent FSM across restarts) with MemoryStorage fallback.
    # In production, RedisStorage.from_url(settings.REDIS_URL, ...) persists FSM
    # state in Redis — surviving bot container restarts. json_dumps uses
    # default=str to serialize Decimal values (price_amount).
    # In dev/test (REDIS_URL empty), MemoryStorage is used as an ephemeral
    # fallback — FSM state is cleared on restart but the Ad.DRAFT row in the
    # ORM survives for resumability.
    redis_url = getattr(settings, "REDIS_URL", "") or ""

    if redis_url:
        storage = RedisStorage.from_url(
            redis_url,
            json_dumps=lambda obj: json.dumps(obj, default=str),
        )
    else:
        logger.warning("REDIS_URL not set — using MemoryStorage (ephemeral FSM)")
        storage = MemoryStorage()
    dp = Dispatcher(storage=storage)

    # Register lifecycle hooks: startup writes the liveness marker,
    # shutdown removes it and closes DB connections, LivenessMiddleware
    # touches the marker on every inbound update for freshness.
    dp.startup.register(_on_startup)
    dp.shutdown.register(_on_shutdown)
    dp.update.middleware(UpdateIdDedupMiddleware())
    dp.update.middleware(LivenessMiddleware())
    # Locale middleware must run before AccountStateMiddleware so denial
    # messages render in the user's preferred language (FQ-001).
    dp.update.middleware(LanguageMiddleware())
    # Register account state middleware on update-level so it receives Update
    # events (Message + CallbackQuery), making the isinstance(event, Update)
    # gate and event.message / event.callback_query access functional.
    dp.update.middleware(AccountStateMiddleware())
    dp.update.outer_middleware(DatabaseConnectionMiddleware())

    # Include routers
    from telegram_bot.handlers import (
        ad_copy_router,
        ad_create_router,
        alerts_router,
        contact_router,
        language_router,
        login_router,
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

    dp.run_polling(bot)


if __name__ == "__main__":
    main()
