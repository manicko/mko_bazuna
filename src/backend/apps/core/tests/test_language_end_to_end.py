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

from django.test import TestCase
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


class LanguageEndToEndTests(TestCase):
    """Real middleware + real view + real template + published seed Ad."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.seller = User.objects.create(
            telegram_id=910000001,
            chat_id=910000001,
            password="x",
        )
        cls.category = Category.objects.create(
            name="Транспорт",
            slug="transport-e2e",
        )
        cls.city = City.objects.create(
            country_code="ME",
            name="Подграф",
            region="Регион",
            slug="podgraf-e2e",
        )
        cls.ad = Ad.objects.create(
            user=cls.seller,
            title=TITLE_RU,
            title_en=TITLE_EN,
            title_bs=TITLE_BS,
            description=DESC_RU,
            description_en=DESC_EN,
            description_bs=DESC_BS,
            category=cls.category,
            city=cls.city,
            category_name=cls.category.name,
            price=100,
            status=AdStatus.PUBLISHED,
            source=AdSource.SEED,
            published_at=timezone.now(),
        )
        cls.detail_url = reverse("ads:detail", kwargs={"ad_id": cls.ad.id})
        cls.listings_url = reverse("ads:listings")

    def setUp(self) -> None:
        # ``process_request`` now calls ``translation.activate()``; clear the
        # thread-local between tests so language state never leaks.
        self.addCleanup(translation.deactivate)

    # --- Resolution priority ---------------------------------------------

    def test_lang_param_wins_over_accept_language(self) -> None:
        """``?lang=en`` wins over ``Accept-Language: ru`` on the first click."""
        response = self.client.get(
            self.detail_url + "?lang=en",
            HTTP_ACCEPT_LANGUAGE="ru",
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, TITLE_EN)
        self.assertContains(response, DESC_EN)
        self.assertNotContains(response, TITLE_RU)
        self.assertEqual(translation.get_language(), "en")

    def test_cookie_persists_language_without_param(self) -> None:
        """A stored ``lang_pref`` cookie drives rendering when no param is sent."""
        self.client.cookies["lang_pref"] = "en"
        response = self.client.get(self.detail_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, TITLE_EN)
        self.assertNotContains(response, TITLE_RU)

    def test_lang_param_bs_renders_bosnian(self) -> None:
        response = self.client.get(self.detail_url + "?lang=bs")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, TITLE_BS)
        self.assertContains(response, DESC_BS)
        self.assertNotContains(response, TITLE_RU)
        self.assertEqual(translation.get_language(), "bs")

    def test_default_no_signal_renders_russian(self) -> None:
        """No lang, no cookie, no Accept-Language -> Russian base."""
        response = self.client.get(self.detail_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, TITLE_RU)
        self.assertContains(response, DESC_RU)
        self.assertNotContains(response, TITLE_EN)
        self.assertNotContains(response, TITLE_BS)
        self.assertEqual(translation.get_language(), "ru")

    # --- Invalid parameter handling --------------------------------------

    def test_invalid_lang_falls_back_to_russian_and_does_not_persist(self) -> None:
        """An unsupported ``?lang=fr`` falls back to ru and sets no cookie."""
        response = self.client.get(self.detail_url + "?lang=fr")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, TITLE_RU)
        self.assertNotContains(response, TITLE_EN)
        self.assertNotIn("lang_pref", response.cookies)
        self.assertEqual(translation.get_language(), "ru")

    # --- Listing surface -------------------------------------------------

    def test_listing_card_switches_language(self) -> None:
        """The listing card renders the localized title too (F5)."""
        self.client.cookies["lang_pref"] = "en"
        response = self.client.get(self.listings_url + "?lang=en")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, TITLE_EN)
        self.assertNotContains(response, TITLE_RU)

    # --- Response headers ------------------------------------------------

    def test_vary_and_content_language_headers(self) -> None:
        """LocaleMiddleware's header contract is preserved by the custom middleware."""
        response = self.client.get(self.detail_url + "?lang=en")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("Content-Language"), "en")
        self.assertIn("Accept-Language", response.headers.get("Vary", ""))

    # --- Thread-local ↔ request-attribute consistency --------------------

    def test_thread_local_matches_request_language_code(self) -> None:
        """``translation.get_language()`` == ``request.LANGUAGE_CODE`` == chosen X.

        The ``i18n`` context processor reads the thread-local while the custom
        ``language`` context processor overrides ``LANGUAGE_CODE`` with
        ``request.LANGUAGE_CODE``; they must agree, otherwise the switcher
        highlight (thread-local via ``{% get_current_language %}``) desyncs from
        the rendered ad text (``request.LANGUAGE_CODE``).
        """
        response = self.client.get(self.detail_url + "?lang=bs")
        self.assertEqual(response.status_code, 200)
        request_lang = response.context["LANGUAGE_CODE"]
        self.assertEqual(translation.get_language(), "bs")
        self.assertEqual(request_lang, "bs")
        self.assertEqual(translation.get_language(), request_lang)
