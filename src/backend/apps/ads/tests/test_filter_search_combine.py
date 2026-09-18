"""Tests for combining ``q`` + ``listing_purpose`` + ``features`` via AND."""

from __future__ import annotations

import pytest
from django.test import Client

from apps.core.enums import AdStatus
from conftest import create_test_ad

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


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
        ad_match.features.add(feature_lookup["delivery"])
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
            "/search/?q=красный телефон&listing_purpose=sell&features=delivery&lang=ru"
        )

        assert response.status_code == 200
        ids = {a.id for a in response.context["page_obj"]}
        assert ad_match.id in ids
        assert len(ids) == 1
