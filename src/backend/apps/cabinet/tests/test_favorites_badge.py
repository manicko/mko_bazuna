"""
Tests for the header favorites-badge refresh endpoint (T-07).

Covers the ``/cabinet/favorites/count/`` fragment served to HTMX after a
``favorite:toggled`` event:
- Anonymous requests render the outline heart without a count badge.
- Authenticated requests render the filled heart with the user's favorite count.
- The badge count reflects adds/removes (regression detection).
"""

from __future__ import annotations

import re

import pytest
from django.test import Client

from apps.ads.models import AdFavorite
from apps.categories.models import Category
from apps.core.enums import AdStatus
from apps.locations.models import City
from apps.users.models import User
from conftest import create_test_ad

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


def _badge_html(content: str) -> str:
    """Return the HTML inside the ``data-favorites-badge`` container.

    All count regexes are scoped here so a coincidental ``>N<`` anywhere else
    in the response cannot produce a false positive. The split on ``</span>``
    consumes the closing ``<`` of the span tag, so we append ``" <"`` to
    preserve it — keeping the ``>N<`` pattern intact for callers.
    """
    return content.split("data-favorites-badge", 1)[1].split("</span>", 1)[0] + "<"


class TestFavoritesCountBadge:
    def test_anonymous_returns_outline_heart(self) -> None:
        resp = Client().get("/cabinet/favorites/count/?lang=ru")
        assert resp.status_code == 200
        content = resp.content.decode()
        # Anonymous: outline heart, no count badge.
        assert 'aria-label="Войдите, чтобы сохранять избранное"' in content
        assert "data-favorites-badge" in content

    def test_authenticated_returns_filled_heart_with_count(
        self,
        buyer_client: Client,
        buyer: User,
        seller: User,
        category: Category,
        city: City,
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

        resp = buyer_client.get("/cabinet/favorites/count/?lang=ru")
        assert resp.status_code == 200
        content = resp.content.decode()
        assert 'aria-label="Моё избранное"' in content
        # Count 2 — scoped to the badge container (FIND-10).
        assert re.search(r">\s*2\s*<", _badge_html(content)) is not None

    def test_refreshes_after_toggle(
        self,
        buyer_client: Client,
        buyer: User,
        seller: User,
        category: Category,
        city: City,
    ) -> None:
        ad = create_test_ad(
            seller,
            category,
            city,
            title="Красный велосипед",
            status=AdStatus.PUBLISHED,
        )

        # No favorites yet — no count badge rendered.
        resp = buyer_client.get("/cabinet/favorites/count/")
        assert re.search(r">\s*0\s*<", _badge_html(resp.content.decode())) is None

        # Add a favorite via ORM -> count of 1 (FIND-9).
        AdFavorite.objects.create(user=buyer, ad=ad)
        resp = buyer_client.get("/cabinet/favorites/count/")
        assert resp.status_code == 200
        assert re.search(r">\s*1\s*<", _badge_html(resp.content.decode())) is not None

        # Remove it via ORM -> back to no count badge.
        AdFavorite.objects.filter(user=buyer, ad=ad).delete()
        resp = buyer_client.get("/cabinet/favorites/count/")
        assert resp.status_code == 200
        assert re.search(r">\s*1\s*<", _badge_html(resp.content.decode())) is None
