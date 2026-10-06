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
from apps.core.context_processors import language as language_processor
from apps.core.enums import AdStatus, LanguageLocale
from apps.locations.models import City
from apps.lookups.models import LookupGroup, LookupItem
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


@pytest.fixture
def localized_lookup_item() -> LookupItem:
    """Create a LookupItem with i18n names in all three locales."""
    group = LookupGroup.objects.create(code="listing_purpose", name_i18n={})
    return LookupItem.objects.create(
        group=group,
        slug="sell",
        name_i18n={"ru": "Продать", "bs": "Prodati", "en": "Sell"},
    )


# Expected accessor value per locale for the shared fixtures. Parametrised from
# ``LanguageLocale.values()`` so the expectation set and the enum cannot drift.
_EXPECTED_CATEGORY = {
    LanguageLocale.RUSSIAN: "Транспорт",
    LanguageLocale.BOSNIAN: "Prevoz",
    LanguageLocale.ENGLISH: "Transport",
}
_EXPECTED_CITY = {
    LanguageLocale.RUSSIAN: "Тестград",
    LanguageLocale.BOSNIAN: "Testgrad",
    LanguageLocale.ENGLISH: "Testgrad",
}
_EXPECTED_LOOKUP = {
    LanguageLocale.RUSSIAN: "Продать",
    LanguageLocale.BOSNIAN: "Prodati",
    LanguageLocale.ENGLISH: "Sell",
}


class TestAccessorsAcceptLanguageLocale:
    """Every accessor returns the requested locale's value (VAL-003).

    The annotation is ``LanguageLocale`` and the parameter is supplied as a
    ``LanguageLocale`` member rather than a bare ``str``. Assertions read the
    accessor's RETURNED VALUE, never rendered chrome — under test
    ``settings.LANGUAGE_CODE`` is ``en`` and Django adds it as a catalogue
    fallback, so a chrome assertion would be false-green.
    """

    @pytest.mark.parametrize("locale", list(LanguageLocale.values()))
    def test_category_get_name(
        self,
        localized_category: Category,
        locale: str,
    ) -> None:
        """``Category.get_name`` honours each ``LanguageLocale`` member."""
        member = LanguageLocale(locale)
        assert localized_category.get_name(member) == _EXPECTED_CATEGORY[member]

    @pytest.mark.parametrize("locale", list(LanguageLocale.values()))
    def test_city_get_name(
        self,
        localized_city: City,
        locale: str,
    ) -> None:
        """``City.get_name`` honours each ``LanguageLocale`` member."""
        member = LanguageLocale(locale)
        assert localized_city.get_name(member) == _EXPECTED_CITY[member]

    @pytest.mark.parametrize("locale", list(LanguageLocale.values()))
    def test_lookup_item_get_name(
        self,
        localized_lookup_item: LookupItem,
        locale: str,
    ) -> None:
        """``LookupItem.get_name`` honours each ``LanguageLocale`` member."""
        member = LanguageLocale(locale)
        assert localized_lookup_item.get_name(member) == _EXPECTED_LOOKUP[member]

    @pytest.mark.parametrize("locale", list(LanguageLocale.values()))
    def test_ad_get_title(
        self,
        seller: User,
        localized_category: Category,
        localized_city: City,
        locale: str,
    ) -> None:
        """``Ad.get_title`` accepts a ``LanguageLocale`` member without raising."""
        ad = create_test_ad(
            seller,
            localized_category,
            localized_city,
            title="Localized acceptance ad",
            status=AdStatus.PUBLISHED,
        )
        ad.refresh_from_db()
        title = ad.get_title(LanguageLocale(locale))
        assert isinstance(title, str)
        assert title


class TestAccessorFallback:
    """A locale with no rung degrades to the ``ru`` rung — returns, never raises.

    The fallback is deliberate: these accessors accept ``LanguageLocale``, but a
    locale whose key is absent from ``name_i18n`` must still return the Russian
    rung rather than raising or returning the wrong locale's value.
    """

    def test_category_unmapped_locale_degrades_to_ru(
        self, localized_category: Category
    ) -> None:
        """A name map lacking the requested key returns the ``ru`` value."""
        row = Category.objects.create(
            name="Транспорт",
            slug="fallback-cat",
            name_i18n={"ru": "Транспорт", "en": "Transport"},
        )
        # ``bs`` has no rung: the ``ru`` fallback must serve it.
        assert row.get_name(LanguageLocale.BOSNIAN) == "Транспорт"

    def test_lookup_item_unmapped_locale_degrades_to_ru(
        self, localized_lookup_item: LookupItem
    ) -> None:
        """A name map lacking the requested key returns the ``ru`` value."""
        row = LookupItem.objects.create(
            group=localized_lookup_item.group,
            slug="fallback-item",
            name_i18n={"ru": "Продать"},
        )
        assert row.get_name(LanguageLocale.ENGLISH) == "Продать"

    def test_lookup_item_missing_all_names_returns_slug(
        self, localized_lookup_item: LookupItem
    ) -> None:
        """With no usable name the terminal rung is ``slug``, never ``name``.

        ``LookupItem`` is the one accessor whose terminal rung is ``slug``, not
        ``name`` (the model has no ``name`` column); a uniformity edit that
        swapped it for ``name`` would be a regression.
        """
        row = LookupItem.objects.create(
            group=localized_lookup_item.group,
            slug="slug-only-item",
            name_i18n=None,
        )
        assert row.get_name(LanguageLocale.RUSSIAN) == "slug-only-item"


class TestLanguageContextProcessor:
    """``context_processors.language`` emits a ``LanguageLocale`` member.

    The declared emitted type matches the accessor/filter boundary. Because
    ``str(LanguageLocale.RUSSIAN) == "ru"``, the rendered ``{{ LANGUAGE_CODE }}``
    and ``|upper`` outputs are byte-identical to the previous bare-``str`` value.
    """

    def test_emits_language_locale_member(self) -> None:
        """A resolved request locale is returned as a ``LanguageLocale``."""

        class _Request:
            LANGUAGE_CODE = LanguageLocale.BOSNIAN.value

        assert language_processor(_Request())["LANGUAGE_CODE"] is LanguageLocale.BOSNIAN

    def test_falls_back_to_settings_language_code(self) -> None:
        """A request without ``LANGUAGE_CODE`` uses ``settings.LANGUAGE_CODE``.

        The processor reads ``getattr(request, "LANGUAGE_CODE",
        settings.LANGUAGE_CODE)`` and normalises it, so the bare-request path
        yields the settings locale as a ``LanguageLocale`` member.
        """

        class _BareRequest:
            pass

        emitted = language_processor(_BareRequest())["LANGUAGE_CODE"]
        assert emitted is LanguageLocale(settings.LANGUAGE_CODE)

    def test_none_request_locale_normalises_to_russian(self) -> None:
        """A ``None`` request locale hits the explicit Russian fallback."""

        class _Request:
            LANGUAGE_CODE = None

        assert language_processor(_Request())["LANGUAGE_CODE"] is LanguageLocale.RUSSIAN

    def test_unmapped_request_locale_normalises_to_russian(self) -> None:
        """An unmapped request locale normalises to the Russian member."""

        class _Request:
            LANGUAGE_CODE = "de-DE"

        assert language_processor(_Request())["LANGUAGE_CODE"] is LanguageLocale.RUSSIAN

    def test_str_render_is_unchanged(self) -> None:
        """``str()`` of the emitted member equals the bare locale code."""

        class _Request:
            LANGUAGE_CODE = "bs"

        emitted = language_processor(_Request())["LANGUAGE_CODE"]
        assert str(emitted) == "bs"
        assert emitted.upper() == "BS"
