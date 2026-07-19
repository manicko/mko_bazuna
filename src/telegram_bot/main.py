"""Telegram bot entrypoint - aiogram 3.x with Django ORM."""

import logging
import os

import django

logger = logging.getLogger(__name__)

# Configure Django settings before importing models
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.prod")
django.setup()


def main() -> None:
    """Run the Telegram bot."""
    token = os.getenv("BOT_TOKEN")
    if not token:
        logger.warning("BOT_TOKEN not set - bot not running (stub mode)")
        logger.info("Full implementation in Phase 1 Task 9")
        return

    # Full implementation in Phase 1 Task 9
    # This stub only validates environment
    logger.info("Bot stub validated - full FSM in Phase 1 Task 9")


if __name__ == "__main__":
    main()
