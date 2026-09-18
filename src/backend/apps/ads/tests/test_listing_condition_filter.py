"""Tests for the listing_condition single-select filter."""

from __future__ import annotations

import pytest
from django.test import Client

from apps.core.enums import AdStatus
from conftest import create_test_ad

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


class TestListingConditionFilter:
    """``?condition=<slug>`` single-select exact match for the new/used dimension.

    Mirrors ``TestListingPurposeFilter``: condition is a dedicated single-select
    dimension (Spec 12 / PO-4), never part of the ``features`` multi-select.
    """

    def test_listings_filters_by_condition(
        self, seller, category, city, condition_lookup
    ) -> None:
        ad_new = create_test_ad(
            seller,
            category,
            city,
            title="Brand new",
            listing_condition=condition_lookup["new"],
            status=AdStatus.PUBLISHED,
        )
        ad_used = create_test_ad(
            seller,
            category,
            city,
            title="Used good",
            listing_condition=condition_lookup["used"],
            status=AdStatus.PUBLISHED,
        )

        client = Client()
        response = client.get("/?condition=new")

        assert response.status_code == 200
        ids = {a.id for a in response.context["page_obj"]}
        assert ad_new.id in ids
        assert ad_used.id not in ids

    def test_search_filters_by_condition(
        self, seller, category, city, condition_lookup
    ) -> None:
        ad_new = create_test_ad(
            seller,
            category,
            city,
            title="Brand new",
            listing_condition=condition_lookup["new"],
            status=AdStatus.PUBLISHED,
        )
        ad_used = create_test_ad(
            seller,
            category,
            city,
            title="Used good",
            listing_condition=condition_lookup["used"],
            status=AdStatus.PUBLISHED,
        )

        client = Client()
        response = client.get("/search/?condition=used")

        assert response.status_code == 200
        ids = {a.id for a in response.context["page_obj"]}
        assert ad_used.id in ids
        assert ad_new.id not in ids

    def test_condition_filter_excludes_ads_without_condition(
        self, seller, category, city, condition_lookup
    ) -> None:
        ad_new = create_test_ad(
            seller,
            category,
            city,
            title="Brand new",
            listing_condition=condition_lookup["new"],
            status=AdStatus.PUBLISHED,
        )
        ad_unconditioned = create_test_ad(
            seller,
            category,
            city,
            title="No condition set",
            status=AdStatus.PUBLISHED,
        )

        client = Client()
        response = client.get("/?condition=new")

        assert response.status_code == 200
        ids = {a.id for a in response.context["page_obj"]}
        assert ad_new.id in ids
        assert ad_unconditioned.id not in ids

    def test_condition_filter_empty_shows_all(
        self, seller, category, city, condition_lookup
    ) -> None:
        ad_new = create_test_ad(
            seller,
            category,
            city,
            title="Brand new",
            listing_condition=condition_lookup["new"],
            status=AdStatus.PUBLISHED,
        )
        ad_used = create_test_ad(
            seller,
            category,
            city,
            title="Used good",
            listing_condition=condition_lookup["used"],
            status=AdStatus.PUBLISHED,
        )

        client = Client()
        response = client.get("/")

        assert response.status_code == 200
        ids = {a.id for a in response.context["page_obj"]}
        assert ad_new.id in ids
        assert ad_used.id in ids
