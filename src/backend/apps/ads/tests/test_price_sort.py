"""Tests for ``price_asc`` / ``price_desc`` sort on ``price_normalized_eur``."""

from __future__ import annotations

import pytest
from django.test import Client

from apps.core.enums import AdSort, AdStatus
from conftest import create_test_ad

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


class TestPriceSort:
    """``price_asc``/``price_desc`` order ads by ``price_normalized_eur`` value."""

    def test_price_asc_orders_by_value(self, seller, category, city) -> None:
        cheap = create_test_ad(
            seller,
            category,
            city,
            title="Cheap",
            price=100,
            status=AdStatus.PUBLISHED,
        )
        mid = create_test_ad(
            seller,
            category,
            city,
            title="Mid",
            price=150,
            status=AdStatus.PUBLISHED,
        )
        expensive = create_test_ad(
            seller,
            category,
            city,
            title="Expensive",
            price=200,
            status=AdStatus.PUBLISHED,
        )

        client = Client()
        response = client.get(f"/?sort={AdSort.PRICE_LOW}")

        assert response.status_code == 200
        ids = list(a.id for a in response.context["page_obj"])
        assert cheap.id in ids and mid.id in ids and expensive.id in ids
        assert ids.index(cheap.id) < ids.index(mid.id) < ids.index(expensive.id)

    def test_price_desc_orders_by_value(self, seller, category, city) -> None:
        cheap = create_test_ad(
            seller,
            category,
            city,
            title="Cheap",
            price=100,
            status=AdStatus.PUBLISHED,
        )
        mid = create_test_ad(
            seller,
            category,
            city,
            title="Mid",
            price=150,
            status=AdStatus.PUBLISHED,
        )
        expensive = create_test_ad(
            seller,
            category,
            city,
            title="Expensive",
            price=200,
            status=AdStatus.PUBLISHED,
        )

        client = Client()
        response = client.get(f"/?sort={AdSort.PRICE_HIGH}")

        assert response.status_code == 200
        ids = list(a.id for a in response.context["page_obj"])
        assert cheap.id in ids and mid.id in ids and expensive.id in ids
        assert ids.index(expensive.id) < ids.index(mid.id) < ids.index(cheap.id)


class TestPriceSortIdTiebreaker:
    """Equal prices are resolved deterministically by the ``-id`` tiebreaker.

    Ads sharing an identical ``price_normalized_eur`` have no fixed relative
    order in PostgreSQL without a unique secondary key. The ``-id`` tiebreaker
    (plan R2, the single approved ordering delta) makes both price directions
    deterministic. Uses the real HTML listings view.
    """

    def test_price_asc_equal_prices_break_by_id_desc(
        self, seller, category, city
    ) -> None:
        """PRICE_LOW with identical prices orders by ``-id`` within the tie."""
        ads = [
            create_test_ad(
                seller,
                category,
                city,
                title=f"Same price {i}",
                price=100,
                status=AdStatus.PUBLISHED,
            )
            for i in range(3)
        ]
        expected = sorted((a.id for a in ads), reverse=True)

        client = Client()
        response = client.get(f"/?sort={AdSort.PRICE_LOW}")

        assert response.status_code == 200
        ids = list(a.id for a in response.context["page_obj"])
        assert ids == expected

    def test_price_desc_equal_prices_break_by_id_desc(
        self, seller, category, city
    ) -> None:
        """PRICE_HIGH with identical prices also breaks by ``-id``."""
        ads = [
            create_test_ad(
                seller,
                category,
                city,
                title=f"Same price {i}",
                price=100,
                status=AdStatus.PUBLISHED,
            )
            for i in range(3)
        ]
        expected = sorted((a.id for a in ads), reverse=True)

        client = Client()
        response = client.get(f"/?sort={AdSort.PRICE_HIGH}")

        assert response.status_code == 200
        ids = list(a.id for a in response.context["page_obj"])
        assert ids == expected
