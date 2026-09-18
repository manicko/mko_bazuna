"""Tests for the listing_purpose single-select filter (F4)."""

from __future__ import annotations

import pytest
from django.test import Client

from apps.core.enums import AdStatus
from conftest import create_test_ad

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


class TestListingPurposeFilter:
    """``?listing_purpose=<slug>`` narrows both listings and search (F4)."""

    def test_listings_filters_by_purpose(
        self, seller, category, city, purpose_lookup
    ) -> None:
        ad_sell = create_test_ad(
            seller,
            category,
            city,
            title="For sale",
            listing_purpose=purpose_lookup["sell"],
            status=AdStatus.PUBLISHED,
        )
        ad_rent = create_test_ad(
            seller,
            category,
            city,
            title="For rent",
            listing_purpose=purpose_lookup["rent"],
            status=AdStatus.PUBLISHED,
        )

        client = Client()
        response = client.get("/?listing_purpose=sell")

        assert response.status_code == 200
        ids = {a.id for a in response.context["page_obj"]}
        assert ad_sell.id in ids
        assert ad_rent.id not in ids

    def test_search_filters_by_purpose(
        self, seller, category, city, purpose_lookup
    ) -> None:
        ad_sell = create_test_ad(
            seller,
            category,
            city,
            title="For sale",
            listing_purpose=purpose_lookup["sell"],
            status=AdStatus.PUBLISHED,
        )
        ad_rent = create_test_ad(
            seller,
            category,
            city,
            title="For rent",
            listing_purpose=purpose_lookup["rent"],
            status=AdStatus.PUBLISHED,
        )

        client = Client()
        response = client.get("/search/?listing_purpose=sell")

        assert response.status_code == 200
        ids = {a.id for a in response.context["page_obj"]}
        assert ad_sell.id in ids
        assert ad_rent.id not in ids
