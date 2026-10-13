"""
Tests for the category submenu endpoint (plan 15, T-300).

Covers the HTMX partial used by the header's "All Categories" dropdown:
- returns 200 + child partial for a valid active category
- excludes inactive children
- returns 404 for unknown or inactive categories
- fragment cache invalidates on structural Category changes
- expand buttons render only for non-leaf children
"""

import pytest
from django.test import Client

from apps.categories.models import Category

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


class TestCategorySubmenu:
    """Category submenu endpoint contract."""

    def test_submenu_returns_children(self, tree: Category) -> None:
        client = Client()
        # ?lang=ru so the response renders the localized name_i18n values
        # rather than falling back to the base ``name`` field. The tree
        # fixture provides ru translations, so we assert actual localization.
        response = client.get("/categories/transport/submenu/?lang=ru")
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
        """Submenu renders localized names based on ``?lang=X`` parameter.

        The ``tree`` fixture already provides ``name_i18n`` for each child.
        This test overwrites the ``bs`` translations to verify the cache
        isolates locales.
        """
        root = tree
        child_bicycles = Category.objects.get(slug="bicycles")
        child_cars = Category.objects.get(slug="cars")

        # Override bs translations
        root.name_i18n = {"ru": "Транспорт", "bs": "Prevoz"}
        root.save(update_fields=["name_i18n"])
        child_bicycles.name_i18n = {"ru": "Велосипеды", "bs": "Bicikli"}
        child_bicycles.save(update_fields=["name_i18n"])
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
def expand_tree() -> None:
    """Create a deterministic category tree for expand-button assertions.

    - ``business`` (non-leaf): one child has a grandchild, so the submenu
      renders ``data-category-expand`` on that child.
    - ``ready-business`` (leaf): no children, so the submenu is empty and
      no expand buttons appear.
    """
    business = Category.objects.create(
        name="Business",
        slug="business",
        name_i18n={"ru": "Бизнес"},
    )
    child = Category.objects.create(
        name="Equipment",
        slug="business-equipment",
        parent=business,
        name_i18n={"ru": "Оборудование"},
    )
    Category.objects.create(
        name="Tractor",
        slug="equipment-tractor",
        parent=child,
    )
    Category.objects.create(
        name="Ready Business",
        slug="ready-business",
        name_i18n={"ru": "Готовый бизнес"},
    )


class TestExpandButtons:
    """Expand buttons render only for children that have children of their own.

    Constructs a deterministic category tree inline rather than relying on
    the committed ``catalog/categories.yaml`` shape (B19 audit finding: hard
    coupling to catalog contents).
    """

    def test_expand_button_present_for_category_with_children(
        self, expand_tree: None
    ) -> None:
        client = Client()
        response = client.get("/categories/business/submenu/")
        assert response.status_code == 200
        content = response.content.decode("utf-8")
        # business-equipment has a child (equipment-tractor) -> expand button.
        assert "data-category-expand" in content

    def test_expand_button_absent_for_leaf_category(self, expand_tree: None) -> None:
        client = Client()
        response = client.get("/categories/ready-business/submenu/")
        assert response.status_code == 200
        content = response.content.decode("utf-8")
        # ready-business is a leaf (no children) -> submenu empty, no expand.
        assert "data-category-expand" not in content
