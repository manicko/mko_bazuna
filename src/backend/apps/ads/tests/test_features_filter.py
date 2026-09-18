"""Tests for the features multi-select AND filter (F5)."""

from __future__ import annotations

import pytest
from django.test import Client

from apps.ads.models import Ad
from apps.core.enums import AdStatus
from conftest import create_test_ad

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


class TestFeaturesFilter:
    """``?features=...`` multi-select AND semantics (F5)."""

    def _seed_ads(self, seller, category, city, feature_lookup) -> tuple[Ad, Ad, Ad]:
        ad_both = create_test_ad(
            seller,
            category,
            city,
            title="Ad with both features",
            status=AdStatus.PUBLISHED,
        )
        ad_both.features.add(feature_lookup["delivery"], feature_lookup["negotiable"])
        ad_delivery_only = create_test_ad(
            seller,
            category,
            city,
            title="Ad with only delivery",
            status=AdStatus.PUBLISHED,
        )
        ad_delivery_only.features.add(feature_lookup["delivery"])
        ad_none = create_test_ad(
            seller,
            category,
            city,
            title="Ad with no features",
            status=AdStatus.PUBLISHED,
        )
        return ad_both, ad_delivery_only, ad_none

    def test_all_selected_features_required(
        self, seller, category, city, feature_lookup
    ) -> None:
        ad_both, ad_delivery_only, ad_none = self._seed_ads(
            seller, category, city, feature_lookup
        )

        client = Client()
        response = client.get("/search/?features=delivery&features=negotiable")

        assert response.status_code == 200
        ids = {a.id for a in response.context["page_obj"]}
        # AND semantics: an ad matches only if it has ALL selected features,
        # so ad_both (delivery + negotiable) is included while the single-feature
        # and featureless ads are excluded.
        assert ad_both.id in ids
        assert ad_delivery_only.id not in ids
        assert ad_none.id not in ids

    def test_ads_missing_any_selected_feature_excluded(
        self, seller, category, city, feature_lookup
    ) -> None:
        ad_both, ad_delivery_only, ad_none = self._seed_ads(
            seller, category, city, feature_lookup
        )

        client = Client()
        response = client.get("/search/?features=delivery&features=negotiable")

        assert response.status_code == 200
        ids = {a.id for a in response.context["page_obj"]}
        assert ad_delivery_only.id not in ids
        assert ad_none.id not in ids

    def test_single_feature_filter_matches_all_with_that_feature(
        self, seller, category, city, feature_lookup
    ) -> None:
        ad_both, ad_delivery_only, ad_none = self._seed_ads(
            seller, category, city, feature_lookup
        )

        client = Client()
        response = client.get("/search/?features=delivery")

        assert response.status_code == 200
        ids = {a.id for a in response.context["page_obj"]}
        assert ad_both.id in ids
        assert ad_delivery_only.id in ids
        assert ad_none.id not in ids
