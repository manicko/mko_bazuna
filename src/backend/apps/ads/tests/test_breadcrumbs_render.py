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
from pathlib import Path

import pytest
from django.test import Client
from django.urls import reverse

from apps.ads.models import Ad
from apps.categories.catalog.builder import load_catalog
from apps.categories.models import Category
from apps.core.enums import AdSource, AdStatus
from apps.locations.models import City
from apps.users.models import User

pytestmark = [pytest.mark.django_db, pytest.mark.slow, pytest.mark.integration]


def _breadcrumb_nav(content: str) -> str:
    """Extract the inner HTML of the rendered ``<nav aria-label="Breadcrumb">``."""
    match = re.search(
        r'<nav aria-label="Breadcrumb"[^>]*>(.*?)</nav>', content, re.S
    )
    return match.group(1).strip() if match else ""


@pytest.fixture(autouse=True)
def _load_catalog():
    """Load the category catalog and create a city for breadcrumb tests."""
    catalog_path = (
        Path(__file__).resolve().parents[2] / "categories" / "catalog" / "categories.yaml"
    )
    load_catalog(catalog_path)
    City.objects.create(
        name="Подгорица", slug="podgorica", region="Central", country_code="ME"
    )
    yield


class TestBreadcrumbsRender:
    """Breadcrumb rendering against the real catalog tree."""

    def test_breadcrumb_shows_root_category(self) -> None:
        """A root category (no ancestors) renders ``Главная > [name]`` with the
        current category as plain text (no self-link)."""
        client = Client()
        response = client.get("/category/business/")
        assert response.status_code == 200
        nav = _breadcrumb_nav(response.content.decode("utf-8"))
        assert "Главная" in nav
        assert "Бизнес" in nav

    def test_breadcrumb_shows_ancestor_chain(self) -> None:
        """A child category renders its ancestor chain."""
        client = Client()
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
        ad = Ad.objects.create(
            user=user,
            title="Test Ad",
            description="Test",
            price=100,
            category=leaf,
            city=city,
            category_name="Офисы",
            status=AdStatus.PUBLISHED,
            source=AdSource.SEED,
            published_at="2024-01-01 00:00:00+00",
        )
        client = Client()
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
        response = client.get("/")
        assert response.status_code == 200
        nav = _breadcrumb_nav(response.content.decode("utf-8"))
        assert nav == ""
