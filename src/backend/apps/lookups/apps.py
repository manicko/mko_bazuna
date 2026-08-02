"""
Lookups app configuration.
"""

from django.apps import AppConfig


class LookupsConfig(AppConfig):
    """Configuration for the lookups app."""

    name = "apps.lookups"
    verbose_name = "Lookups"

    def ready(self) -> None:
        """Connect signal handlers for lookup cache invalidation."""
        import apps.lookups.signals  # noqa: F401