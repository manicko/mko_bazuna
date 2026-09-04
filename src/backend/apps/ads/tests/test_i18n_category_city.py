"""
Regression tests for category/city i18n rendering on the ad detail page (Spec 09, T-08).

Verifies that ``{{ ad.city|get_city_name:LANGUAGE_CODE }}`` and
``{{ ad.category|get_category_name:LANGUAGE_CODE }}`` in detail.html render
the correct localized name — not the Russian base ``name`` — when the UI
language is switched via ``?lang=bs`` or ``?lang=en``.

The category submenu cache isolation and admin review page localization are
covered by ``test_submenu.py`` and ``test_moderation_views.py`` respectively.
"""

from __future__ import annotations

import pytest
from django.test import Client
from django.urls import reverse

from apps.categories.models import Category
from apps.core.enums import AdStatus
from apps.locations.models import City
from apps.users.models import User

from conftest import create_test_ad

pytestmark = [pytest.mark.django_db, pytest.mark.slow, pytest.mark.integration]


@pytest.fixture
def localized_category() -> Category:
    """Create a category with i18n names in all three locales."""
    return Category.objects.create(
        name="Транспорт",
        slug="transport",
        name_i18n={"ru": "Транспорт", "bs": "Prevoz", "en": "Transport"},
    )


@pytest.fixture
def localized_city() -> City:
    """Create a city with i18n names in all three locales."""
    return City.objects.create(
        country_code="ME",
        name="Тестград",
        slug="test-grad",
        region="Central",
        name_i18n={"ru": "Тестград", "bs": "Testgrad", "en": "Testgrad"},
    )


class TestDetailPageI18n:
    """Ad detail page renders category/city names in the active UI locale."""

    def test_detail_renders_bs_names(
        self,
        seller: User,
        localized_category: Category,
        localized_city: City,
    ) -> None:
        """Detail page with ``?lang=bs`` shows Bosnian category/city names."""
        ad = create_test_ad(
            seller,
            localized_category,
            localized_city,
            title="Test Ad BS",
            status=AdStatus.PUBLISHED,
        )
        client = Client()
        response = client.get(reverse("ads:detail", args=[ad.id]), {"lang": "bs"})
        assert response.status_code == 200
        content = response.content.decode("utf-8")
        assert "Prevoz" in content
        assert "Testgrad" in content
        assert "Транспорт" not in content
        assert "Тестград" not in content

    def test_detail_renders_en_names(
        self,
        seller: User,
        localized_category: Category,
        localized_city: City,
    ) -> None:
        """Detail page with ``?lang=en`` shows English category/city names."""
        ad = create_test_ad(
            seller,
            localized_category,
            localized_city,
            title="Test Ad EN",
            status=AdStatus.PUBLISHED,
        )
        client = Client()
        response = client.get(reverse("ads:detail", args=[ad.id]), {"lang": "en"})
        assert response.status_code == 200
        content = response.content.decode("utf-8")
        assert "Transport" in content
        assert "Testgrad" in content
        # Russian names must not bleed through when UI is English
        assert "Транспорт" not in content
        assert "Тестград" not in content

    def test_detail_defaults_to_en(
        self,
        seller: User,
        localized_category: Category,
        localized_city: City,
    ) -> None:
        """Without an explicit ``lang`` param the detail page defaults to English
        (msging source language)."""
        ad = create_test_ad(
            seller,
            localized_category,
            localized_city,
            title="Test Ad EN",
            status=AdStatus.PUBLISHED,
        )
        client = Client()
        response = client.get(reverse("ads:detail", args=[ad.id]))
        assert response.status_code == 200
        content = response.content.decode("utf-8")
        assert "Transport" in content
        assert "Testgrad" in content

    def test_detail_renders_ru_names(
        self,
        seller: User,
        localized_category: Category,
        localized_city: City,
    ) -> None:
        """``?lang=ru`` renders Russian category/city names."""
        ad = create_test_ad(
            seller,
            localized_category,
            localized_city,
            title="Test Ad RU",
            status=AdStatus.PUBLISHED,
        )
        client = Client()
        response = client.get(reverse("ads:detail", args=[ad.id]) + "?lang=ru")
        assert response.status_code == 200
        content = response.content.decode("utf-8")
        assert "Транспорт" in content
        assert "Тестград" in content

    def test_detail_accepts_accept_language(
        self,
        seller: User,
        localized_category: Category,
        localized_city: City,
    ) -> None:
        """``Accept-Language`` header is honoured for the UI locale."""
        ad = create_test_ad(
            seller,
            localized_category,
            localized_city,
            title="Test Ad AL",
            status=AdStatus.PUBLISHED,
        )
        client = Client()
        response = client.get(
            reverse("ads:detail", args=[ad.id]),
            HTTP_ACCEPT_LANGUAGE="bs",
        )
        assert response.status_code == 200
        content = response.content.decode("utf-8")
        assert "Prevoz" in content
        assert "Транспорт" not in content
