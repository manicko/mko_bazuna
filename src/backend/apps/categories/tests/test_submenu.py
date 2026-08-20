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
    Category.objects.create(
        name="Устаревшее", slug="old", parent=root, is_active=False
    )
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

    def test_submenu_invalidated_on_structure_change(self, tree: Category) -> None:
        client = Client()
        # Prime the fragment cache.
        assert client.get("/categories/transport/submenu/").status_code == 200
        assert "NoSuchChild" not in client.get(
            "/categories/transport/submenu/"
        ).content.decode("utf-8")

        # A structural change bumps the tree version -> fragment is invalidated.
        Category.objects.create(name="NewChild", slug="new-child", parent=tree)

        response = client.get("/categories/transport/submenu/")
        assert "NewChild" in response.content.decode("utf-8")


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

    def test_expand_button_present_for_category_with_children(self, catalog: None) -> None:
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
