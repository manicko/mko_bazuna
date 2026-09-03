"""
Core app configuration.

Registers signal handlers on app ready.
"""

import logging

from django.apps import AppConfig

logger = logging.getLogger(__name__)


class CoreConfig(AppConfig):
    name = "apps.core"
    verbose_name = "Core"

    def ready(self):
        # Import signals when app is ready
        import apps.core.signals  # noqa: F401 - side-effect: register signals

        logger.debug("Core app ready, signals registered")
