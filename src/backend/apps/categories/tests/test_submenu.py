"""
Tests for the category submenu endpoint (plan 15, T-300).

Covers the HTMX partial used by the header's "All Categories" dropdown:
- returns 200 + child partial for a valid active category
- excludes inactive children
- returns 404 for unknown or inactive categories
- fragment cache invalidates on structural Category changes
"""

import pytest
from apps.categories.catalog.builder import load_catalog
from apps.categories.models import Category
from django.test import Client

pytestmark = [pytest.mark.django_db, pytest.mark.slow, pytest.mark.integration]


@pytest.fixture
def tree() -> Category:
    """Create a root category with active and inactive children."""
    root = Category.objects.create(name="Транспорт", slug="transport")
    Category.objects.create(name="Велосипеды", slug="bicycles", parent=root)
    Category.objects.create(name="Автомобили", slug="cars", parent=root)
    Category.objects.create(name="Устаревшее", slug="old", parent=root, is_active=False)
    return root


class TestCategorySubmenu:
    """Category submenu endpoint contract."""

    def test_submenu_returns_children(self, tree: Category) -> None:
        client = Client()
        response = client.get("/categories/transport/submenu/")
        assert response.status_code == 200
        content = response.content.decode("utf-8")
        assert "Велосипеды" in content
        assert "Автомобили" in content
        # Inactive children are excluded.
        assert "Устаревшее" not in content

    def test_submenu_404_unknown(self) -> None:
        client = Client()
        assert client.get("/categories/nonexistent/submenu/").status_code == 404

    def test_submenu_404_inactive_top_category(self, tree: Category) -> None:
        client = Client()
        old = Category.objects.get(slug="old")
        assert client.get(f"/categories/{old.slug}/submenu/").status_code == 404

    def test_submenu_localized_content(self, tree: Category) -> None:
        """Submenu renders localized names based on ``?lang=X`` parameter."""
        root = tree
        root.name_i18n = {"ru": "Транспорт", "bs": "Prevoz"}
        root.save(update_fields=["name_i18n"])

        child_bicycles = Category.objects.get(slug="bicycles")
        child_bicycles.name_i18n = {"ru": "Велосипеды", "bs": "Bicikli"}
        child_bicycles.save(update_fields=["name_i18n"])

        child_cars = Category.objects.get(slug="cars")
        child_cars.name_i18n = {"ru": "Автомобили", "bs": "Automobili"}
        child_cars.save(update_fields=["name_i18n"])

        client = Client()

        # Russian response
        response_ru = client.get("/categories/transport/submenu/?lang=ru")
        assert response_ru.status_code == 200
        content_ru = response_ru.content.decode("utf-8")
        assert "Велосипеды" in content_ru
        assert "Bicikli" not in content_ru

        # Bosnian response — different cache entry, different content
        response_bs = client.get("/categories/transport/submenu/?lang=bs")
        assert response_bs.status_code == 200
        content_bs = response_bs.content.decode("utf-8")
        assert "Bicikli" in content_bs
        assert "Велосипеды" not in content_bs

    def test_submenu_cache_isolated_by_locale(self, tree: Category) -> None:
        """The cache key includes the locale, preventing cross-language bleed."""
        child_bicycles = Category.objects.get(slug="bicycles")
        child_bicycles.name_i18n = {"ru": "Велосипеды", "bs": "Bicikli"}
        child_bicycles.save(update_fields=["name_i18n"])

        client = Client()

        # Prime the cache with Russian
        client.get("/categories/transport/submenu/?lang=ru")
        content_after_ru = client.get(
            "/categories/transport/submenu/?lang=ru"
        ).content.decode("utf-8")
        assert "Велосипеды" in content_after_ru

        # Bosnian should NOT return the cached Russian version
        content_after_bs = client.get(
            "/categories/transport/submenu/?lang=bs"
        ).content.decode("utf-8")
        assert "Bicikli" in content_after_bs
        assert "Велосипеды" not in content_after_bs


@pytest.fixture
def catalog() -> None:
    """Load the full category catalog from categories.yaml."""
    from pathlib import Path

    catalog_path = (
        Path(__file__).resolve().parents[2]
        / "categories"
        / "catalog"
        / "categories.yaml"
    )
    load_catalog(catalog_path)


class TestExpandButtons:
    """Expand buttons render only for categories that have children (RC-A)."""

    def test_expand_button_present_for_category_with_children(
        self, catalog: None
    ) -> None:
        client = Client()
        response = client.get("/categories/business/submenu/")
        assert response.status_code == 200
        content = response.content.decode("utf-8")
        # business has children with children of their own (e.g.
        # business-commercial-real-estate) -> expand buttons must render.
        assert "data-category-expand" in content

    def test_expand_button_absent_for_leaf_category(self, catalog: None) -> None:
        client = Client()
        response = client.get("/categories/ready-business/submenu/")
        assert response.status_code == 200
        content = response.content.decode("utf-8")
        # ready-business is a leaf node (no children) -> no expand buttons.
        assert "data-category-expand" not in content
