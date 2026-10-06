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
from django.conf import settings
from django.test import Client
from django.urls import reverse
from django.utils import translation

from apps.categories.models import Category
from apps.core.enums import AdStatus
from apps.locations.models import City
from apps.users.models import User
from conftest import create_test_ad

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


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


class TestNonCanonicalCookieLocale:
    """Non-canonical ``lang_pref`` cookie drives the DB accessors.

    ``14-I18N-001``: before the fix a raw cookie such as ``en-US`` reached
    ``translation.activate()`` unvalidated, so ``request.LANGUAGE_CODE`` was
    ``en-us`` — outside ``settings.LANGUAGES`` — and every DB-backed string fell
    through the ``locale -> ru`` chain to Russian, site-wide.

    These assertions read the accessor results (``Category.get_name``,
    ``City.get_name``, ``Ad.get_title``), never rendered chrome: under test
    ``settings.LANGUAGE_CODE`` is ``en`` and Django adds it as a catalogue
    fallback, so a chrome assertion is false-green (VAL-003).
    """

    def test_non_canonical_cookie_drives_accessors(
        self,
        seller: User,
        localized_category: Category,
        localized_city: City,
    ) -> None:
        """``en-US`` cookie resolves to ``en`` for every DB accessor."""
        ad = create_test_ad(
            seller,
            localized_category,
            localized_city,
            title="Non-canonical cookie ad",
            status=AdStatus.PUBLISHED,
        )
        client = Client()
        client.cookies["lang_pref"] = "en-US"
        response = client.get(reverse("ads:detail", args=[ad.id]))
        assert response.status_code == 200

        # Resolve the active locale through the same source of truth the view
        # uses, then assert the accessors return that locale's value.
        active = translation.get_language()
        assert active in {code for code, _ in settings.LANGUAGES}

        localized_category.refresh_from_db()
        localized_city.refresh_from_db()
        ad.refresh_from_db()
        assert active == "en"
        assert localized_category.get_name(active) == "Transport"
        assert localized_city.get_name(active) == "Testgrad"
        assert ad.get_title(active) == "Non-canonical cookie ad"

    def test_unsupported_cookie_falls_back_for_accessors(
        self,
        seller: User,
        localized_category: Category,
        localized_city: City,
    ) -> None:
        """An unsupported cookie resolves to the BOSNIAN accessor values."""
        ad = create_test_ad(
            seller,
            localized_category,
            localized_city,
            title="Unsupported cookie ad",
            status=AdStatus.PUBLISHED,
        )
        client = Client()
        client.cookies["lang_pref"] = "de-DE"
        response = client.get(reverse("ads:detail", args=[ad.id]))
        assert response.status_code == 200

        active = translation.get_language()
        assert active in {code for code, _ in settings.LANGUAGES}
        assert active == "bs"
        localized_category.refresh_from_db()
        localized_city.refresh_from_db()
        assert localized_category.get_name(active) == "Prevoz"
        assert localized_city.get_name(active) == "Testgrad"
