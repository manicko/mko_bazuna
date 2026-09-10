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


class TestLoadCatalogPostLoadGuard:
    """Tests for the post-load guard in load_catalog (ENT-040)."""

    def test_load_catalog_fails_fast_on_empty_categories(self, tmp_path: Path) -> None:
        """An empty YAML config produces zero categories; command raises CommandError."""
        empty_config = tmp_path / "empty.yaml"
        empty_config.write_text("--- {}", encoding="utf-8")

        with pytest.raises(CommandError, match="zero categories"):
            call_command("load_catalog", "--config", str(empty_config))

    def test_load_catalog_succeeds_with_categories_present(self, city: City) -> None:
        """Running load_catalog with a valid config populates categories and passes the guard.

        The *city* fixture guarantees `City.objects.exists()` is True so the
        city guard does not fire; `--no-rewrite` prevents the builder from
        mutating the committed `categories.yaml` on disk.
        """
        assert Category.objects.count() == 0

        call_command("load_catalog", "--no-rewrite")

        assert Category.objects.exists()

    def test_post_load_guard_checks_cities(self) -> None:
        """When cities table is empty, the guard raises CommandError for cities.

        Categories are loaded normally (real config), but no cities exist, so
        the city guard should fire.
        """
        City.objects.all().delete()
        assert City.objects.count() == 0

        with pytest.raises(CommandError, match="zero cities"):
            call_command("load_catalog", "--no-rewrite")

    def test_load_catalog_populates_lookup_items(self, city: City) -> None:
        """The real management command populates LookupItem rows (ENT-037).

        ``load_catalog`` invokes ``builder.load_catalog``, whose Phase 1
        (``_load_lookups``) creates ``LookupItem`` rows via
        ``update_or_create``. The *city* fixture satisfies the command's
        post-load ``City.objects.exists()`` guard — ``load_catalog`` itself
        does not seed cities (ENT-031).
        """
        assert LookupItem.objects.count() == 0

        call_command("load_catalog", "--no-rewrite")

        assert LookupItem.objects.exists()
        assert LookupItem.objects.count() > 0
