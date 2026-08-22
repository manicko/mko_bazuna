"""
End-to-end regression tests for the 3-language (ru / bs / en) ad-text switching.

These tests exercise the REAL middleware chain (``settings.MIDDLEWARE``) through
Django's test ``Client``, then assert the chosen language flows all the way
through to the rendered ad title/description. This is a *composition* test: the
original bug was caused by ``LocaleMiddleware`` clobbering
``request.LANGUAGE_CODE`` after ``LanguagePreMiddleware`` set it, which unit
tests of the middleware in isolation could not catch.

Verified behaviour:
    ``?lang=X`` > ``lang_pref`` cookie > ``Accept-Language`` > ``ru``
and the thread-local active language (``{% get_current_language %}``) must agree
with ``request.LANGUAGE_CODE`` at render time.
"""

from __future__ import annotations

import pytest
from django.test import Client, override_settings
from django.urls import reverse
from django.utils import timezone
from django.utils import translation

from apps.ads.models import Ad
from apps.categories.models import Category
from apps.core.enums import AdSource, AdStatus
from apps.locations.models import City
from apps.users.models import User

# Distinct, unambiguous seed values per locale: the strings do not overlap
# across languages, so an assertion can never pass by coincidence.
TITLE_RU = "Русско заголовок"
TITLE_EN = "English title"
TITLE_BS = "Bosnian naslov"
DESC_RU = "Русское описание"
DESC_EN = "English desc"
DESC_BS = "Bosnian opis"

pytestmark = [pytest.mark.django_db, pytest.mark.slow, pytest.mark.integration]


@pytest.fixture(autouse=True)
def _locale_cleanup():
    """Deactivate thread-local language state after each test."""
    yield
    translation.deactivate()


@pytest.fixture(autouse=True)
def _staticfiles_storage():
    """Use non-cached staticfiles storage for deterministic template rendering."""
    with override_settings(
        STORAGES={
            "staticfiles": {
                "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
            },
        },
    ):
        yield


@pytest.fixture
def e2e_ad():
    """Create a published multilingual ad for end-to-end language tests."""
    seller = User.objects.create(
        telegram_id=910000001,
        chat_id=910000001,
        password="x",
    )
    category = Category.objects.create(
        name="Транспорт",
        slug="transport-e2e",
    )
    city = City.objects.create(
        country_code="ME",
        name="Подграф",
        region="Регион",
        slug="podgraf-e2e",
    )
    ad = Ad.objects.create(
        user=seller,
        title=TITLE_RU,
        title_en=TITLE_EN,
        title_bs=TITLE_BS,
        description=DESC_RU,
        description_en=DESC_EN,
        description_bs=DESC_BS,
        category=category,
        city=city,
        category_name=category.name,
        price=100,
        status=AdStatus.PUBLISHED,
        source=AdSource.SEED,
        published_at=timezone.now(),
    )
    detail_url = reverse("ads:detail", kwargs={"ad_id": ad.id})
    listings_url = reverse("ads:listings")
    return {"ad": ad, "detail_url": detail_url, "listings_url": listings_url}


class TestLanguageEndToEnd:
    """Real middleware + real view + real template + published seed Ad."""

    def test_lang_param_wins_over_accept_language(self, e2e_ad) -> None:
        """``?lang=en`` wins over ``Accept-Language: ru`` on the first click."""
        client = Client()
        response = client.get(
            e2e_ad["detail_url"] + "?lang=en",
            HTTP_ACCEPT_LANGUAGE="ru",
        )
        assert response.status_code == 200
        assert TITLE_EN.encode() in response.content
        assert DESC_EN.encode() in response.content
        assert TITLE_RU.encode() not in response.content
        assert translation.get_language() == "en"

    def test_cookie_persists_language_without_param(self, e2e_ad) -> None:
        """A stored ``lang_pref`` cookie drives rendering when no param is sent."""
        client = Client()
        client.cookies["lang_pref"] = "en"
        response = client.get(e2e_ad["detail_url"])
        assert response.status_code == 200
        assert TITLE_EN.encode() in response.content
        assert TITLE_RU.encode() not in response.content

    def test_lang_param_bs_renders_bosnian(self, e2e_ad) -> None:
        client = Client()
        response = client.get(e2e_ad["detail_url"] + "?lang=bs")
        assert response.status_code == 200
        assert TITLE_BS.encode() in response.content
        assert DESC_BS.encode() in response.content
        assert TITLE_RU.encode() not in response.content
        assert translation.get_language() == "bs"

    def test_default_no_signal_renders_russian(self, e2e_ad) -> None:
        """No lang, no cookie, no Accept-Language -> Russian base."""
        client = Client()
        response = client.get(e2e_ad["detail_url"])
        assert response.status_code == 200
        assert TITLE_RU.encode() in response.content
        assert DESC_RU.encode() in response.content
        assert TITLE_EN.encode() not in response.content
        assert TITLE_BS.encode() not in response.content
        assert translation.get_language() == "ru"

    def test_invalid_lang_falls_back_to_russian_and_does_not_persist(self, e2e_ad) -> None:
        """An unsupported ``?lang=fr`` falls back to ru and sets no cookie."""
        client = Client()
        response = client.get(e2e_ad["detail_url"] + "?lang=fr")
        assert response.status_code == 200
        assert TITLE_RU.encode() in response.content
        assert TITLE_EN.encode() not in response.content
        assert "lang_pref" not in response.cookies
        assert translation.get_language() == "ru"

    def test_listing_card_switches_language(self, e2e_ad) -> None:
        """The listing card renders the localized title too (F5)."""
        client = Client()
        client.cookies["lang_pref"] = "en"
        response = client.get(e2e_ad["listings_url"] + "?lang=en")
        assert response.status_code == 200
        assert TITLE_EN.encode() in response.content
        assert TITLE_RU.encode() not in response.content

    def test_vary_and_content_language_headers(self, e2e_ad) -> None:
        """LocaleMiddleware's header contract is preserved by the custom middleware."""
        client = Client()
        response = client.get(e2e_ad["detail_url"] + "?lang=en")
        assert response.status_code == 200
        assert response.headers.get("Content-Language") == "en"
        assert "Accept-Language" in response.headers.get("Vary", "")

    def test_thread_local_matches_request_language_code(self, e2e_ad) -> None:
        """``translation.get_language()`` == ``request.LANGUAGE_CODE`` == chosen X.

        The ``i18n`` context processor reads the thread-local while the custom
        ``language`` context processor overrides ``LANGUAGE_CODE`` with
        ``request.LANGUAGE_CODE``; they must agree, otherwise the switcher
        highlight (thread-local via ``{% get_current_language %}``) desyncs from
        the rendered ad text (``request.LANGUAGE_CODE``).
        """
        client = Client()
        response = client.get(e2e_ad["detail_url"] + "?lang=bs")
        assert response.status_code == 200
        request_lang = response.context["LANGUAGE_CODE"]
        assert translation.get_language() == "bs"
        assert request_lang == "bs"
        assert translation.get_language() == request_lang
