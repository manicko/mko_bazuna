"""
Moderation app configuration.
"""

import logging

from django.apps import AppConfig

logger = logging.getLogger(__name__)


class ModerationConfig(AppConfig):
    name = "apps.moderation"
    verbose_name = "Moderation"

    def ready(self):
        # Import signals when app is ready
        import apps.moderation.signals  # noqa: F401 - side-effect: register signals

        logger.debug("Moderation app ready, signals registered")
