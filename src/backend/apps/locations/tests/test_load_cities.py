"""Tests for the load_cities management command.

Verifies city reference data is loaded from cities.json with the correct
CATALOG_LOAD advisory lock (ID 104), session-scoped, and is idempotent.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from unittest.mock import DEFAULT, MagicMock

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.core.enums import AdvisoryLockId
from apps.locations.management.commands.load_cities import CITIES_JSON_PATH
from apps.locations.models import City

pytestmark = [pytest.mark.django_db, pytest.mark.integration]

EXPECTED_SLUGS = {
    "podgorica",
    "niksic",
    "bar",
    "kotor",
    "budva",
    "tivat",
    "herceg-novi",
    "cetinje",
    "bijelo-polje",
    "pljevlja",
    "rozaje",
    "berane",
    "ulcinj",
    "danilovgrad",
    "mojkovac",
}
EXPECTED_CITY_COUNT = len(EXPECTED_SLUGS)


class TestLoadCities:
    """Tests for the load_cities command."""

    def test_loads_all_fifteen_cities(self) -> None:
        """Running load_cities populates the cities table with 15 entries."""
        City.objects.all().delete()
        assert City.objects.count() == 0

        call_command("load_cities")

        assert City.objects.count() == EXPECTED_CITY_COUNT

    def test_all_expected_slugs_present(self) -> None:
        """All 15 fixture slugs appear in the database after loading."""
        City.objects.all().delete()

        call_command("load_cities")

        slugs = set(City.objects.values_list("slug", flat=True))
        assert slugs == EXPECTED_SLUGS

    def test_idempotent_re_run_does_not_duplicate(self) -> None:
        """Re-running load_cities does not duplicate cities (update_conflicts)."""
        City.objects.all().delete()

        call_command("load_cities")
        first_run = City.objects.count()

        call_command("load_cities")
        second_run = City.objects.count()

        assert first_run == EXPECTED_CITY_COUNT
        assert second_run == EXPECTED_CITY_COUNT

    def test_uses_catalog_load_session_lock(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The command acquires AdvisoryLockId.CATALOG_LOAD (104) as session-scoped.

        Follows the spy pattern from test_sweep_lock_structure.py: patch the
        advisory_lock name bound in the command module (imported via
        ``from apps.core.utils.advisory_lock import advisory_lock``) and
        verify the call signature.
        """
        lock_calls: list[tuple[AdvisoryLockId, bool]] = []

        def _spy(lock_id, *, session: bool = False):
            lock_calls.append((lock_id, session))
            # Returning DEFAULT makes the mock substitute its own return
            # value (a no-op context manager), so inner code runs without
            # acquiring a real PostgreSQL lock.
            return DEFAULT

        spy = MagicMock(side_effect=_spy)
        monkeypatch.setattr(
            "apps.locations.management.commands.load_cities.advisory_lock", spy
        )

        City.objects.all().delete()
        call_command("load_cities")

        assert len(lock_calls) == 1
        assert lock_calls[0][0] == AdvisoryLockId.CATALOG_LOAD
        assert lock_calls[0][1] is True

    def test_custom_config_path(self, tmp_path: Path) -> None:
        """The --config flag loads from the specified fixture path."""
        City.objects.all().delete()

        custom = tmp_path / "cities.json"
        shutil.copy(CITIES_JSON_PATH, custom)

        call_command("load_cities", "--config", str(custom))

        assert City.objects.count() == EXPECTED_CITY_COUNT

    def test_missing_fixture_raises_command_error(self, tmp_path: Path) -> None:
        """A nonexistent --config path raises CommandError."""
        missing = tmp_path / "nonexistent.json"
        with pytest.raises(CommandError, match="Cities fixture not found"):
            call_command("load_cities", "--config", str(missing))
