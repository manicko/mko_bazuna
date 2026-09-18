"""Tests for the sort dropdown rendering on search results (T4, PO-2)."""

from __future__ import annotations

import pytest
from django.test import Client

from apps.core.enums import AdStatus
from conftest import create_test_ad

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


class TestSortOnSearchResults:
    """The sort dropdown renders on ``/search/?q=`` results (T4, PO-2)."""

    def test_sort_dropdown_visible_on_search_results(
        self, seller, category, city
    ) -> None:
        create_test_ad(
            seller,
            category,
            city,
            title="Транспорт велосипед",
            status=AdStatus.PUBLISHED,
        )
        client = Client()
        response = client.get(
            "/search/?q=транспорт&lang=ru", headers={"HX-Request": "true"}
        )
        assert response.status_code == 200
        assert '<select name="sort"' in response.content.decode("utf-8")
