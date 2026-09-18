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
        assert cheap.id in ids and expensive.id in ids
        assert ids.index(cheap.id) < ids.index(expensive.id)

    def test_price_desc_orders_by_value(self, seller, category, city) -> None:
        cheap = create_test_ad(
            seller,
            category,
            city,
            title="Cheap",
            price=100,
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
        assert cheap.id in ids and expensive.id in ids
        assert ids.index(expensive.id) < ids.index(cheap.id)
