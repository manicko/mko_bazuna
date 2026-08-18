"""
Cabinet app configuration.

The unified User Cabinet hub hosting Favorites, Saved-Search Alerts, and
Search History sections, plus the seller dashboard (\"Мои объявления\") link.
"""

from django.apps import AppConfig


class CabinetConfig(AppConfig):
    name = "apps.cabinet"
    verbose_name = "Cabinet"
