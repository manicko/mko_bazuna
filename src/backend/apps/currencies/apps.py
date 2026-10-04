"""
Currencies app configuration.
"""

from django.apps import AppConfig


class CurrenciesConfig(AppConfig):
    """Configuration for the currencies app."""

    name = "apps.currencies"
    verbose_name = "Currencies"

    def ready(self) -> None:
        """Connect signal handlers for exchange-rate cache invalidation."""
        import apps.currencies.signals  # noqa: F401
