"""Tests for the load_catalog management command (ENT-040, ENT-037).

Covers the post-load guard that asserts Category and City rows exist after
the catalog builder runs, raising CommandError if either dataset is empty.
Also covers the ENT-037 smoke test: load_catalog populates LookupItem rows
via builder Phase 1 (lookups).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.categories.models import Category
from apps.locations.models import City
from apps.lookups.models import LookupItem

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


@pytest.fixture
def loaded_catalog(request, city: City) -> None:
    """Load the full category catalog from categories.yaml once per test.

    The *city* fixture guarantees ``City.objects.exists()`` is True so the
    post-load city guard passes. ``--no-rewrite`` prevents the builder from
    mutating the committed ``categories.yaml`` on disk.

    Indirectly parametrize with ``"no_cities"`` to delete all cities before
    loading — this exercises the post-load city guard (B19 audit finding #4).
    """
    if getattr(request, "param", None) == "no_cities":
        City.objects.all().delete()
        with pytest.raises(CommandError, match="zero cities"):
            call_command("load_catalog", "--no-rewrite")
    else:
        call_command("load_catalog", "--no-rewrite")


class TestLoadCatalogPostLoadGuard:
    """Tests for the post-load guard in load_catalog (ENT-040)."""

    def test_load_catalog_fails_fast_on_empty_categories(self, tmp_path: Path) -> None:
        """An empty YAML config produces zero categories; command raises CommandError."""
        empty_config = tmp_path / "empty.yaml"
        empty_config.write_text("--- {}", encoding="utf-8")

        with pytest.raises(CommandError, match="Catalog loaded zero categories"):
            call_command("load_catalog", "--config", str(empty_config))

    def test_load_catalog_succeeds_with_categories_present(
        self, loaded_catalog: None
    ) -> None:
        """Running load_catalog with a valid config populates categories and passes the guard.

        The *loaded_catalog* fixture invokes ``load_catalog`` with the *city*
        fixture satisfying the command's city guard.
        """
        assert Category.objects.exists()

    @pytest.mark.parametrize("loaded_catalog", ["no_cities"], indirect=True)
    def test_post_load_guard_checks_cities(self, loaded_catalog: None) -> None:
        """When cities table is empty, the guard raises CommandError for cities.

        The *loaded_catalog* fixture (parametrized with ``"no_cities"``) deletes
        all cities before calling ``load_catalog`` and asserts the command
        raises ``CommandError`` with the city-guard message. ``load_catalog``
        itself does not seed cities (ENT-031), so the table stays empty.
        """
        assert not City.objects.exists()

    def test_load_catalog_populates_lookup_items(self, loaded_catalog: None) -> None:
        """The real management command populates LookupItem rows (ENT-037).

        ``load_catalog`` invokes ``builder.load_catalog``, whose Phase 1
        (``_load_lookups``) creates ``LookupItem`` rows via
        ``update_or_create``. The *loaded_catalog* fixture satisfies the
        command's post-load ``City.objects.exists()`` guard.
        """
        assert LookupItem.objects.exists()
        assert LookupItem.objects.count() > 0
