"""
Tests for Spec 18 Block E — Migration seed function (Outcome 4).

Tests for the ``seed_bot_username`` data migration in
``apps/core/migrations/0003_add_bot_username.py``:
- Seeds from ``settings.BOT_USERNAME`` when the row is at the default value.
- Does NOT overwrite a custom (admin-edited) value.
- Falls back to ``"bazuna_bot"`` when ``settings.BOT_USERNAME`` is empty.

Since test settings disable migration replay (``MIGRATION_MODULES =
DisableMigrations``), the migration function is imported directly via
``importlib`` and invoked against the live app registry (``django.apps.apps``).
"""

from __future__ import annotations

import importlib

import pytest
from django.apps import apps as django_apps
from django.test import override_settings

from apps.core.models import SiteConfig

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


@pytest.fixture
def seed_bot_username():
    """Load the ``seed_bot_username`` function directly from the migration module."""
    migration_module = importlib.import_module(
        "apps.core.migrations.0003_add_bot_username"
    )
    return migration_module.seed_bot_username


# ---------------------------------------------------------------------------
# seed_bot_username(apps, schema_editor)
# ---------------------------------------------------------------------------


@override_settings(BOT_USERNAME="test_bot")
def test_seed_populates_from_settings(seed_bot_username) -> None:
    """Seed populates ``bot_username`` from ``settings.BOT_USERNAME`` at default."""
    config = SiteConfig.get_singleton()
    assert config.bot_username == "bazuna_bot"  # factory default

    seed_bot_username(django_apps, None)

    config.refresh_from_db()
    assert config.bot_username == "test_bot"


@override_settings(BOT_USERNAME="env_bot")
def test_seed_does_not_overwrite_custom(seed_bot_username) -> None:
    """Seed does NOT overwrite a custom (non-default) ``bot_username`` value."""
    config = SiteConfig.get_singleton()
    config.bot_username = "custom_user"
    config.save()

    seed_bot_username(django_apps, None)

    config.refresh_from_db()
    assert config.bot_username == "custom_user"


@override_settings(BOT_USERNAME="")
def test_seed_falls_back_to_default(seed_bot_username) -> None:
    """Seed falls back to ``"bazuna_bot"`` when ``settings.BOT_USERNAME`` is empty."""
    config = SiteConfig.get_singleton()
    assert config.bot_username == "bazuna_bot"

    seed_bot_username(django_apps, None)

    config.refresh_from_db()
    assert config.bot_username == "bazuna_bot"
