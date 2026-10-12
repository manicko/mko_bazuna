"""Tests for FTS sort order with relevance-first default."""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.test import Client
from django.utils import timezone

from apps.core.enums import AdSort, AdStatus
from conftest import create_test_ad

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


class TestFtsSortOrder:
    """FTS search results honor ``?sort=`` with relevance-first default (PO-2=A).

    The ``-rank`` annotation is always kept as a secondary tiebreaker so that
    within a chosen sort direction, more relevant ads still float to the top.
    """

    def test_fts_price_asc_orders_by_price(self, seller, category, city) -> None:
        ad_50 = create_test_ad(
            seller,
            category,
            city,
            title="Велосипед",
            price=50,
            status=AdStatus.PUBLISHED,
        )
        ad_200 = create_test_ad(
            seller,
            category,
            city,
            title="Велосипед",
            price=200,
            status=AdStatus.PUBLISHED,
        )
        ad_100 = create_test_ad(
            seller,
            category,
            city,
            title="Велосипед",
            price=100,
            status=AdStatus.PUBLISHED,
        )

        client = Client()
        response = client.get(
            f"/search/?q=велосипед&sort={AdSort.PRICE_LOW}&lang=ru",
            headers={"HX-Request": "true"},
        )

        assert response.status_code == 200
        ids = list(a.id for a in response.context["page_obj"])
        assert ids == [ad_50.id, ad_100.id, ad_200.id]

    def test_fts_price_desc_orders_by_price(self, seller, category, city) -> None:
        ad_50 = create_test_ad(
            seller,
            category,
            city,
            title="Велосипед",
            price=50,
            status=AdStatus.PUBLISHED,
        )
        ad_200 = create_test_ad(
            seller,
            category,
            city,
            title="Велосипед",
            price=200,
            status=AdStatus.PUBLISHED,
        )
        ad_100 = create_test_ad(
            seller,
            category,
            city,
            title="Велосипед",
            price=100,
            status=AdStatus.PUBLISHED,
        )

        client = Client()
        response = client.get(
            f"/search/?q=велосипед&sort={AdSort.PRICE_HIGH}&lang=ru",
            headers={"HX-Request": "true"},
        )

        assert response.status_code == 200
        ids = list(a.id for a in response.context["page_obj"])
        assert ids == [ad_200.id, ad_100.id, ad_50.id]

    def test_fts_price_asc_free_sorts_first(self, seller, category, city) -> None:
        ad_free = create_test_ad(
            seller,
            category,
            city,
            title="Велосипед",
            price=0,
            status=AdStatus.PUBLISHED,
        )
        ad_priced = create_test_ad(
            seller,
            category,
            city,
            title="Велосипед",
            price=100,
            status=AdStatus.PUBLISHED,
        )

        client = Client()
        response = client.get(
            f"/search/?q=велосипед&sort={AdSort.PRICE_LOW}&lang=ru",
            headers={"HX-Request": "true"},
        )

        assert response.status_code == 200
        ids = list(a.id for a in response.context["page_obj"])
        assert ad_free.id in ids
        assert ad_priced.id in ids
        # Price 0 (Free) sorts before positive prices in ascending order.
        assert ids.index(ad_free.id) < ids.index(ad_priced.id)

    def test_default_tiebreaks_by_published_at_desc(
        self, seller, category, city
    ) -> None:
        """Default (no ``?sort=``) sorts by relevance rank, then by ``-published_at``.

        Two ads with the same title (``"Велосипед"``) have equal FTS rank, so
        the secondary ``-published_at`` tiebreaker surfaces the newer ad first.
        """
        now = timezone.now()
        ad_older = create_test_ad(
            seller,
            category,
            city,
            title="Велосипед",
            status=AdStatus.PUBLISHED,
            published_at=now - timedelta(days=1),
        )
        ad_newer = create_test_ad(
            seller,
            category,
            city,
            title="Велосипед",
            status=AdStatus.PUBLISHED,
            published_at=now,
        )

        client = Client()
        response = client.get(
            "/search/?q=велосипед&lang=ru",
            headers={"HX-Request": "true"},
        )

        assert response.status_code == 200
        ids = list(a.id for a in response.context["page_obj"])
        assert ad_newer.id in ids
        assert ad_older.id in ids
        # Equal rank → secondary -published_at tiebreaker: newer first.
        assert ids.index(ad_newer.id) < ids.index(ad_older.id)

    def test_title_match_ranks_above_description_only(
        self, seller, category, city
    ) -> None:
        """A title match outranks a description-only match (true relevance).

        Both ads match the search query, but one has the term in its title
        (highest weight) and the other only in its description (lower weight),
        so the title-match ad must appear first in the default relevance
        ordering.
        """
        ad_title = create_test_ad(
            seller,
            category,
            city,
            title="Велосипед",
            description="Продается товар",
            status=AdStatus.PUBLISHED,
        )
        ad_desc = create_test_ad(
            seller,
            category,
            city,
            title="Самокат",
            description="Продается велосипед в хорошем состоянии",
            status=AdStatus.PUBLISHED,
        )

        client = Client()
        response = client.get(
            "/search/?q=велосипед&lang=ru",
            headers={"HX-Request": "true"},
        )

        assert response.status_code == 200
        ids = list(a.id for a in response.context["page_obj"])
        assert ad_title.id in ids
        assert ad_desc.id in ids
        # Title match (highest weight) ranks above description-only match.
        assert ids.index(ad_title.id) < ids.index(ad_desc.id)
