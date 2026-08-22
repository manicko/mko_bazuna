"""
View-layer tests for the catalog filter and sort behavior (Plan 26).

Covers the new buyer-facing filter dimensions and sort improvements:
- ``listing_purpose`` single-select filter (F4) in both ``/`` (listings) and ``/search/``
- ``features`` multi-select AND filter (F5)
- Combining ``q`` + ``listing_purpose`` + ``features`` via AND
- ``NULLS LAST`` for ``price_asc`` / ``price_desc`` on ``price_normalized_eur``
- Relevance tiebreaker (``-rank, -published_at, -id``) for FTS results

These use the real Django test client so the full filter → sort → paginate →
render pipeline is exercised (including the filter-form template).
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.test import Client
from django.utils import timezone

from apps.ads.models import Ad
from apps.core.enums import AdSort, AdStatus
from apps.lookups.models import LookupGroup, LookupItem

from conftest import create_test_ad

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


@pytest.fixture
def purpose_lookup() -> dict[str, LookupItem]:
    """Create the ``listing_purpose`` group with sell/rent items."""
    group = LookupGroup.objects.create(code="listing_purpose", is_system=True)
    sell = LookupItem.objects.create(
        group=group,
        slug="sell",
        name_i18n={"ru": "Продажа", "en": "Sell"},
        is_active=True,
    )
    rent = LookupItem.objects.create(
        group=group,
        slug="rent",
        name_i18n={"ru": "Аренда", "en": "Rent"},
        is_active=True,
    )
    return {"sell": sell, "rent": rent}


@pytest.fixture
def feature_lookup() -> dict[str, LookupItem]:
    """Create the ``listing_feature`` group with new/delivery items."""
    group = LookupGroup.objects.create(code="listing_feature", is_system=True)
    new = LookupItem.objects.create(
        group=group,
        slug="new",
        name_i18n={"ru": "Новый", "en": "New"},
        is_active=True,
    )
    delivery = LookupItem.objects.create(
        group=group,
        slug="delivery",
        name_i18n={"ru": "Доставка", "en": "Delivery"},
        is_active=True,
    )
    return {"new": new, "delivery": delivery}


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


class TestFeaturesFilter:
    """``?features=...`` multi-select AND semantics (F5)."""

    def _seed_ads(self, seller, category, city, feature_lookup) -> tuple[Ad, Ad]:
        ad_both = create_test_ad(
            seller,
            category,
            city,
            title="Ad with both features",
            status=AdStatus.PUBLISHED,
        )
        ad_both.features.add(feature_lookup["new"], feature_lookup["delivery"])
        ad_new_only = create_test_ad(
            seller,
            category,
            city,
            title="Ad with only new",
            status=AdStatus.PUBLISHED,
        )
        ad_new_only.features.add(feature_lookup["new"])
        return ad_both, ad_new_only

    def test_all_selected_features_required(
        self, seller, category, city, feature_lookup
    ) -> None:
        ad_both, ad_new_only = self._seed_ads(seller, category, city, feature_lookup)

        client = Client()
        response = client.get("/search/?features=new&features=delivery")

        assert response.status_code == 200
        ids = {a.id for a in response.context["page_obj"]}
        assert ad_both.id in ids
        assert ad_new_only.id not in ids

    def test_single_feature_returns_all_matches(
        self, seller, category, city, feature_lookup
    ) -> None:
        ad_both, ad_new_only = self._seed_ads(seller, category, city, feature_lookup)

        client = Client()
        response = client.get("/search/?features=new")

        assert response.status_code == 200
        ids = {a.id for a in response.context["page_obj"]}
        assert ad_both.id in ids
        assert ad_new_only.id in ids


class TestFilterAndSearchCombine:
    """``q`` + ``listing_purpose`` + ``features`` combine via AND."""

    def test_q_purpose_and_feature_combine(
        self, seller, category, city, purpose_lookup, feature_lookup
    ) -> None:
        ad_match = create_test_ad(
            seller,
            category,
            city,
            title="Продам красный телефон",
            listing_purpose=purpose_lookup["sell"],
            status=AdStatus.PUBLISHED,
        )
        ad_match.features.add(feature_lookup["new"])
        # Same text + purpose but missing the feature -> must be excluded.
        create_test_ad(
            seller,
            category,
            city,
            title="Продам красный телефон",
            listing_purpose=purpose_lookup["sell"],
            status=AdStatus.PUBLISHED,
        )

        client = Client()
        response = client.get(
            "/search/?q=красный телефон&listing_purpose=sell&features=new"
        )

        assert response.status_code == 200
        ids = {a.id for a in response.context["page_obj"]}
        assert ad_match.id in ids
        assert len(ids) == 1


class TestPriceNullSort:
    """``price_asc``/``price_desc`` place NULL ``price_normalized_eur`` last."""

    def test_price_asc_places_nulls_last(
        self, seller, category, city
    ) -> None:
        priced = create_test_ad(
            seller, category, city, title="Priced", price=100,
            status=AdStatus.PUBLISHED,
        )
        null = create_test_ad(
            seller, category, city, title="No price", price=None,
            status=AdStatus.PUBLISHED,
        )

        client = Client()
        response = client.get(f"/?sort={AdSort.PRICE_LOW}")

        assert response.status_code == 200
        ids = list(a.id for a in response.context["page_obj"])
        assert null.id in ids and priced.id in ids
        assert ids[-1] == null.id

    def test_price_desc_places_nulls_last(
        self, seller, category, city
    ) -> None:
        priced = create_test_ad(
            seller, category, city, title="Priced", price=100,
            status=AdStatus.PUBLISHED,
        )
        null = create_test_ad(
            seller, category, city, title="No price", price=None,
            status=AdStatus.PUBLISHED,
        )

        client = Client()
        response = client.get(f"/?sort={AdSort.PRICE_HIGH}")

        assert response.status_code == 200
        ids = list(a.id for a in response.context["page_obj"])
        assert null.id in ids and priced.id in ids
        assert ids[-1] == null.id


class TestRelevanceTiebreaker:
    """FTS results order by ``-rank, -published_at, -id``."""

    def test_rank_tie_breaks_by_published_at(
        self, seller, category, city
    ) -> None:
        now = timezone.now()
        ad_older = create_test_ad(
            seller,
            category,
            city,
            title="Продам красный телефон",
            status=AdStatus.PUBLISHED,
            published_at=now - timedelta(days=1),
        )
        ad_newer = create_test_ad(
            seller,
            category,
            city,
            title="Продам красный телефон",
            status=AdStatus.PUBLISHED,
            published_at=now,
        )

        client = Client()
        response = client.get("/search/?q=красный телефон")

        assert response.status_code == 200
        ids = list(a.id for a in response.context["page_obj"])
        assert ad_newer.id in ids and ad_older.id in ids
        assert ids.index(ad_newer.id) < ids.index(ad_older.id)
