"""
Categories app configuration.
"""

from django.apps import AppConfig


class CategoriesConfig(AppConfig):
    name = "apps.categories"
    verbose_name = "Categories"

    def ready(self) -> None:
        """Connect signal handlers for category lookup invalidation."""
        import apps.categories.signals  # noqa: F401
