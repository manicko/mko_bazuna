"""
Tests for the ``repair_bot_username`` management command (CFG-005, G5).

The load-bearing test here is
``test_repair_bot_username_invalidates_cached_bot_username``. ``QuerySet.update()``
emits no ``post_save``, so a repair written that way would leave the stale value
cached for ``SITE_CONFIG_CACHE_TTL`` (3600 s). A test that only checks the
database row passes identically whether the command uses ``save()`` or
``update()`` — the cache assertion is the one with teeth, which is why the cache
is primed and asserted before the command runs.
"""

from __future__ import annotations

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import override_settings

from apps.core.models import SiteConfig
from apps.core.services.site_config import get_bot_username
from apps.core.utils.cache import get_cached_bot_username, set_cached_bot_username

pytestmark = [pytest.mark.django_db, pytest.mark.integration]

_INVALID_USERNAME = "<your-bot-username>"
_REPAIRED_USERNAME = "test_bot_for_testing_only"
_ADMIN_USERNAME = "admin_chosen_bot"


def _set_bot_username(value: str) -> SiteConfig:
    """Write ``value`` straight to the singleton, bypassing the validator."""
    config = SiteConfig.get_singleton()
    SiteConfig.objects.filter(pk=config.pk).update(bot_username=value)
    config.refresh_from_db()
    return config


def test_repair_bot_username_corrects_invalid_row() -> None:
    """A row holding the placeholder becomes the BOT_USERNAME setting value."""
    config = _set_bot_username(_INVALID_USERNAME)

    with override_settings(BOT_USERNAME=_REPAIRED_USERNAME):
        call_command("repair_bot_username")

    config.refresh_from_db()
    assert config.bot_username == _REPAIRED_USERNAME


def test_repair_bot_username_invalidates_cached_bot_username() -> None:
    """A repair is visible immediately, not after the 1-hour cache TTL.

    The cache is primed with the invalid value and asserted first, so the test
    cannot pass because nothing was cached. ``save()`` fires ``post_save`` and
    clears the key; ``update()`` would leave the primed value in place.
    """
    config = _set_bot_username(_INVALID_USERNAME)
    set_cached_bot_username(_INVALID_USERNAME)
    assert get_bot_username() == _INVALID_USERNAME
    assert get_cached_bot_username() == _INVALID_USERNAME

    with override_settings(BOT_USERNAME=_REPAIRED_USERNAME):
        call_command("repair_bot_username")

    config.refresh_from_db()
    assert config.bot_username == _REPAIRED_USERNAME
    assert get_cached_bot_username() is None
    assert get_bot_username() == _REPAIRED_USERNAME


def test_repair_bot_username_leaves_valid_row_untouched() -> None:
    """A valid, admin-set row is never overwritten and the command is idempotent."""
    config = _set_bot_username(_ADMIN_USERNAME)

    with override_settings(BOT_USERNAME=_REPAIRED_USERNAME):
        call_command("repair_bot_username")
        call_command("repair_bot_username")

    config.refresh_from_db()
    assert config.bot_username == _ADMIN_USERNAME


@pytest.mark.parametrize("source", ["", "<your-bot-username>", "not a username"])
def test_repair_bot_username_refuses_when_settings_value_is_invalid(
    source: str,
) -> None:
    """An empty or malformed setting raises CommandError and changes nothing.

    Substituting the model default here would manufacture the silent
    ``bazuna_bot`` dead link that G4's required-non-empty decision exists to
    prevent.
    """
    config = _set_bot_username(_INVALID_USERNAME)

    with override_settings(BOT_USERNAME=source):
        with pytest.raises(CommandError):
            call_command("repair_bot_username")

    config.refresh_from_db()
    assert config.bot_username == _INVALID_USERNAME


def test_repair_bot_username_dry_run_changes_nothing() -> None:
    """``--dry-run`` leaves the row and the cache unchanged."""
    config = _set_bot_username(_INVALID_USERNAME)
    set_cached_bot_username(_INVALID_USERNAME)

    with override_settings(BOT_USERNAME=_REPAIRED_USERNAME):
        call_command("repair_bot_username", "--dry-run")

    config.refresh_from_db()
    assert config.bot_username == _INVALID_USERNAME
    assert get_cached_bot_username() == _INVALID_USERNAME
