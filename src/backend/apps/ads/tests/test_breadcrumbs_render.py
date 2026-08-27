"""
Runtime rendering tests for the catalog breadcrumbs (Spec_022 / plan 22).

Verifies the breadcrumb nav renders correctly on:
- root category pages (no ancestors)
- child category pages (full ancestor chain)
- ad detail pages (category path)
- the home page (empty nav, no crash)

These are integration tests: they render the real templates against a real
PostgreSQL database (the test DB on port 5433), so they need the category
catalog loaded.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path

import pytest
from django.db import transaction
from django.test import Client
from django.urls import reverse
from django.utils import translation
from pytest_django import DjangoDbBlocker

from apps.categories.catalog.builder import load_catalog
from apps.categories.models import Category
from apps.core.enums import AdSource, AdStatus
from apps.locations.models import City
from apps.users.models import User

from conftest import create_test_ad

pytestmark = [pytest.mark.django_db, pytest.mark.slow, pytest.mark.integration]


def _breadcrumb_nav(content: str) -> str:
    """Extract the inner HTML of the rendered ``<nav aria-label="Breadcrumb">``."""
    match = re.search(
        r'<nav aria-label="(?:Хлебные крошки|Breadcrumb)"[^>]*>(.*?)</nav>',
        content,
        re.S,
    )
    return match.group(1).strip() if match else ""


@pytest.fixture(autouse=True, scope="class")
def _load_catalog(
    django_db_setup: None, django_db_blocker: DjangoDbBlocker
) -> Iterator[None]:
    """Load the category catalog and a test city once per class.

    ``load_catalog`` is idempotent (``update_or_create`` throughout) but
    re-parses ``categories.yaml`` and walks the full category tree (~3.6s of
    setup) on every call. Class scope runs it once instead of once per test.

    The setup is wrapped in an ``atomic`` block that is rolled back at class
    teardown via ``set_rollback``, so the catalog rows and the test city never
    leak into sibling classes or sibling xdist workers. This matters because the
    catalog contains ``slug: transport``, which collides with
    ``test_submenu.py``'s ``tree`` fixture (``Category.objects.create``) if left
    committed on the shared test database.

    ``django_db_setup`` is declared as a fixture dependency to ensure the test
    database is created and the connection settings are switched to the test DB
    *before* this class-scoped fixture opens ``transaction.atomic()``. Without
    it, pytest would set up this class-scoped fixture before the session-scoped
    ``django_db_setup``, causing ``atomic()`` to connect to the production DB.
    When ``create_test_db`` later calls ``connection.close()``, the connection
    is in an atomic block so ``close()`` preserves a ``[BAD]`` psycopg object
    instead of setting ``self.connection = None``, and subsequent
    ``ensure_connection()`` calls become no-ops.
    """
    catalog_path = (
        Path(__file__).resolve().parents[2]
        / "categories"
        / "catalog"
        / "categories.yaml"
    )
    with django_db_blocker.unblock():
        with transaction.atomic():
            load_catalog(catalog_path)
            City.objects.create(
                name="Подгорица",
                slug="podgorica",
                region="Central",
                country_code="ME",
            )
            yield
            transaction.set_rollback(True)


class TestBreadcrumbsRender:
    """Breadcrumb rendering against the real catalog tree."""

    def test_breadcrumb_shows_root_category(self) -> None:
        """A root category (no ancestors) renders ``Главная > [name]`` with the
        current category as plain text (no self-link)."""
        client = Client()
        translation.activate("ru")
        response = client.get("/category/business/")
        assert response.status_code == 200
        nav = _breadcrumb_nav(response.content.decode("utf-8"))
        assert "Главная" in nav
        assert "Бизнес" in nav

    def test_breadcrumb_shows_ancestor_chain(self) -> None:
        """A child category renders its ancestor chain."""
        client = Client()
        translation.activate("ru")
        response = client.get("/category/business-commercial-real-estate/")
        assert response.status_code == 200
        nav = _breadcrumb_nav(response.content.decode("utf-8"))
        assert "Бизнес" in nav
        assert "Коммерческая недвижимость" in nav

    def test_breadcrumb_on_ad_detail(self, seller) -> None:
        """An ad in a deep leaf category renders the full category path."""
        user = User.objects.create(
            username="bc-user", telegram_id=7777, chat_id=7777, password="!"
        )
        city = City.objects.get(slug="podgorica")
        leaf = Category.objects.get(slug="business-offices")
        ad = create_test_ad(
            user,
            leaf,
            city,
            title="Test Ad",
            description="Test",
            status=AdStatus.PUBLISHED,
            source=AdSource.SEED,
            price=100,
            published_at="2024-01-01 00:00:00+00",
            category_name="Офисы",
        )
        client = Client()
        translation.activate("ru")
        response = client.get(reverse("ads:detail", args=[ad.id]))
        assert response.status_code == 200
        nav = _breadcrumb_nav(response.content.decode("utf-8"))
        # business -> business-commercial-real-estate -> business-offices
        assert "Бизнес" in nav
        assert "Коммерческая недвижимость" in nav
        assert "Офисы" in nav

    def test_breadcrumb_empty_on_home(self) -> None:
        """The home page (no category) renders an empty/absent breadcrumb nav
        without crashing."""
        client = Client()
        translation.activate("ru")
        response = client.get("/")
        assert response.status_code == 200
        nav = _breadcrumb_nav(response.content.decode("utf-8"))
        assert nav == ""
