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

from apps.ads.models import AdFavorite
from apps.categories.models import Category
from apps.core.enums import AdStatus
from apps.locations.models import City
from apps.users.models import User

from conftest import create_test_ad

pytestmark = [pytest.mark.django_db, pytest.mark.slow, pytest.mark.integration]


@pytest.fixture
def buyer() -> User:
    return User.objects.create(
        telegram_id=950000201,
        chat_id=950000201,
        password="y",
    )


class TestFavoritesCountBadge:
    def test_anonymous_returns_outline_heart(self) -> None:
        resp = Client().get("/cabinet/favorites/count/")
        assert resp.status_code == 200
        content = resp.content.decode()
        # Anonymous: outline heart, no count badge.
        assert 'aria-label="Войдите, чтобы сохранять избранное"' in content
        assert "data-favorites-badge" in content
        assert "Войдите, чтобы сохранять избранное" in content

    def test_authenticated_returns_filled_heart_with_count(
        self, buyer: User, seller: User, category: Category, city: City
    ) -> None:
        ad = create_test_ad(
            seller,
            category,
            city,
            title="Красный велосипед",
            status=AdStatus.PUBLISHED,
        )
        AdFavorite.objects.create(user=buyer, ad=ad)
        AdFavorite.objects.create(
            user=buyer,
            ad=create_test_ad(
                seller,
                category,
                city,
                title="Второй",
                status=AdStatus.PUBLISHED,
            ),
        )

        client = Client()
        client.force_login(buyer)
        resp = client.get("/cabinet/favorites/count/")
        assert resp.status_code == 200
        content = resp.content.decode()
        assert 'aria-label="Моё избранное"' in content
        assert re.search(r">\s*2\s*<", content) is not None

    def test_refreshes_after_toggle(
        self, buyer: User, seller: User, category: Category, city: City
    ) -> None:
        ad = create_test_ad(
            seller,
            category,
            city,
            title="Красный велосипед",
            status=AdStatus.PUBLISHED,
        )
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
