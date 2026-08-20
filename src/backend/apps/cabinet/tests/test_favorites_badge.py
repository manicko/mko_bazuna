"""
Tests for the header favorites-badge refresh endpoint (T-07).

Covers the ``/cabinet/favorites/count/`` fragment served to HTMX after a
``favorite:toggled`` event:
- Anonymous requests render the outline heart without a count badge.
- Authenticated requests render the filled heart with the user's favorite count.
- The badge count reflects adds/removes (regression detection).
"""

import re

import pytest
from django.test import Client
from django.utils import timezone

from apps.ads.models import Ad, AdFavorite
from apps.categories.models import Category
from apps.core.enums import AdStatus
from apps.locations.models import City
from apps.users.models import User

pytestmark = [pytest.mark.django_db, pytest.mark.slow, pytest.mark.integration]


@pytest.fixture
def seller() -> User:
    return User.objects.create(
        telegram_id=950000200,
        chat_id=950000200,
        password="x",
    )


@pytest.fixture
def buyer() -> User:
    return User.objects.create(
        telegram_id=950000201,
        chat_id=950000201,
        password="y",
    )


@pytest.fixture
def category() -> Category:
    return Category.objects.create(name="Транспорт", slug="transport")


@pytest.fixture
def city() -> City:
    return City.objects.create(
        country_code="ME",
        name="Тестград",
        region="FBiH",
        slug="test-grad",
    )


def _published_ad(seller: User, category: Category, city: City, **kwargs) -> Ad:
    defaults = {
        "user": seller,
        "title": "Красный велосипед",
        "category": category,
        "city": city,
        "category_name": category.name,
        "status": AdStatus.PUBLISHED,
        "published_at": timezone.now(),
    }
    defaults.update(kwargs)
    return Ad.objects.create(**defaults)


class TestFavoritesCountBadge:
    def test_anonymous_returns_outline_heart(self) -> None:
        resp = Client().get("/cabinet/favorites/count/")
        assert resp.status_code == 200
        content = resp.content.decode()
        # Anonymous: outline heart, no count badge.
        assert 'aria-label="Login to save favorites"' in content
        assert "data-favorites-badge" in content
        assert "Login to save favorites" in content

    def test_authenticated_returns_filled_heart_with_count(
        self, buyer: User, seller: User, category: Category, city: City
    ) -> None:
        ad = _published_ad(seller, category, city)
        AdFavorite.objects.create(user=buyer, ad=ad)
        AdFavorite.objects.create(
            user=buyer, ad=_published_ad(seller, category, city, title="Второй")
        )

        client = Client()
        client.force_login(buyer)
        resp = client.get("/cabinet/favorites/count/")
        assert resp.status_code == 200
        content = resp.content.decode()
        assert 'aria-label="My favorites"' in content
        assert re.search(r">\s*2\s*<", content) is not None

    def test_refreshes_after_toggle(
        self, buyer: User, seller: User, category: Category, city: City
    ) -> None:
        ad = _published_ad(seller, category, city)
        client = Client()
        client.force_login(buyer)

        # No favorites yet.
        resp = client.get("/cabinet/favorites/count/")
        assert re.search(r">\s*0\s*<", resp.content.decode()) is None

        # Add a favorite -> count of 1.
        client.post(f"/favorite/{ad.id}/")
        resp = client.get("/cabinet/favorites/count/")
        assert resp.status_code == 200
        assert re.search(r">\s*1\s*<", resp.content.decode()) is not None

        # Remove it -> back to no count.
        client.post(f"/favorite/{ad.id}/")
        resp = client.get("/cabinet/favorites/count/")
        assert resp.status_code == 200
        assert re.search(r">\s*1\s*<", resp.content.decode()) is None
