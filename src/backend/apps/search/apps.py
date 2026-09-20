"""
Search app configuration.

Registers signal handlers on app ready.
"""

import logging

from django.apps import AppConfig

logger = logging.getLogger(__name__)


class SearchConfig(AppConfig):
    name = "apps.search"
    verbose_name = "Search"

    def ready(self):
        # Import signals when app is ready
        import apps.search.signals  # noqa: F401 - side-effect: register signals

        logger.debug("Search app ready, signals registered")
