"""
Unit tests for Ad model localized getters (get_title / get_description).

Verifies the fallback chain: ``title_<locale>`` -> ``title`` (Russian base).
There is no ``title_ru``/``description_ru`` column — the Russian base lives in
``title``/``description`` — so the assertions use those real fields only.

Uses SimpleTestCase with in-memory ``Ad`` instances (no DB).
"""

from apps.ads.models import Ad
from django.test import SimpleTestCase


def _make_ad(**kwargs) -> Ad:
    """Create an in-memory Ad for testing localized getters (no DB).

    Sets default values for every locale-aware field, then overrides with any
    provided keyword arguments. The returned object is a real ``Ad`` instance
    built via ``__new__`` so it carries the actual ``get_title`` /
    ``get_description`` methods without needing a database row.
    """
    fields: dict = {
        "title": "",
        "description": "",
        "title_bs": None,
        "description_bs": None,
        "title_en": None,
        "description_en": None,
    }
    fields.update(kwargs)
    ad = Ad.__new__(Ad)
    for field, value in fields.items():
        setattr(ad, field, value)
    return ad


class TestAdGetTitle(SimpleTestCase):
    """Tests for Ad.get_title(locale) fallback behaviour."""

    # ── Locale-specific content ──────────────────────────────────────

    def test_returns_bs_when_present(self) -> None:
        ad = _make_ad(title="Original", title_bs="Bosnian title")
        self.assertEqual(ad.get_title("bs"), "Bosnian title")

    def test_returns_en_when_present(self) -> None:
        ad = _make_ad(title="Original", title_en="English title")
        self.assertEqual(ad.get_title("en"), "English title")

    def test_returns_ru_with_default_locale(self) -> None:
        """Default locale (``ru``) returns the Russian base stored in ``title``."""
        ad = _make_ad(title="Russian title")
        self.assertEqual(ad.get_title(), "Russian title")

    # ── Fallback: locale empty -> Russian base ───────────────────────

    def test_fallback_ru_when_bs_is_none(self) -> None:
        ad = _make_ad(title="Russian fallback", title_bs=None)
        self.assertEqual(ad.get_title("bs"), "Russian fallback")

    def test_fallback_ru_when_bs_is_empty(self) -> None:
        ad = _make_ad(title="Russian fallback", title_bs="")
        self.assertEqual(ad.get_title("bs"), "Russian fallback")

    # ── Fallback: locale empty -> Russian base (None / empty) ──────────

    def test_fallback_base_when_locale_and_ru_are_none(self) -> None:
        ad = _make_ad(title="Original title", title_bs=None)
        self.assertEqual(ad.get_title("bs"), "Original title")

    def test_fallback_base_when_locale_and_ru_are_empty(self) -> None:
        ad = _make_ad(title="Original title", title_bs="")
        self.assertEqual(ad.get_title("bs"), "Original title")

    def test_unknown_locale_falls_to_base_when_present(self) -> None:
        """Unknown locale (e.g. 'fr') falls back to the Russian base (title)."""
        ad = _make_ad(title="Russian")
        self.assertEqual(ad.get_title("fr"), "Russian")

    # ── Edge cases ───────────────────────────────────────────────────

    def test_returns_empty_when_all_fields_are_none(self) -> None:
        ad = _make_ad(title=None, title_bs=None)
        self.assertEqual(ad.get_title("bs"), "")

    def test_returns_empty_when_all_fields_are_empty(self) -> None:
        ad = _make_ad(title="", title_bs="")
        self.assertEqual(ad.get_title("bs"), "")

    def test_whitespace_only_is_truthy_and_returned(self) -> None:
        """Whitespace-only strings are truthy -> returned without fallback."""
        ad = _make_ad(title_bs="   ", title="Should not appear")
        self.assertEqual(ad.get_title("bs"), "   ")

    def test_none_locale_field_skips_gracefully(self) -> None:
        ad = _make_ad(title="Original", title_bs=None)
        self.assertEqual(ad.get_title("bs"), "Original")


class TestAdGetDescription(SimpleTestCase):
    """Tests for Ad.get_description(locale) fallback behaviour."""

    # ── Locale-specific content ──────────────────────────────────────

    def test_returns_bs_when_present(self) -> None:
        ad = _make_ad(description="Original", description_bs="Bosnian desc")
        self.assertEqual(ad.get_description("bs"), "Bosnian desc")

    def test_returns_en_when_present(self) -> None:
        ad = _make_ad(description="Original", description_en="English desc")
        self.assertEqual(ad.get_description("en"), "English desc")

    def test_returns_ru_with_default_locale(self) -> None:
        """Default locale (``ru``) returns the Russian base stored in ``description``."""
        ad = _make_ad(description="Russian desc")
        self.assertEqual(ad.get_description(), "Russian desc")

    # ── Fallback: locale empty -> Russian base ───────────────────────

    def test_fallback_ru_when_bs_is_none(self) -> None:
        ad = _make_ad(description="Russian fallback", description_bs=None)
        self.assertEqual(ad.get_description("bs"), "Russian fallback")

    def test_fallback_ru_when_bs_is_empty(self) -> None:
        ad = _make_ad(description="Russian fallback", description_bs="")
        self.assertEqual(ad.get_description("bs"), "Russian fallback")

    # ── Fallback: locale empty -> Russian base (None / empty) ──────────

    def test_fallback_base_when_locale_and_ru_are_none(self) -> None:
        ad = _make_ad(description="Original desc", description_bs=None)
        self.assertEqual(ad.get_description("bs"), "Original desc")

    def test_fallback_base_when_locale_and_ru_are_empty(self) -> None:
        ad = _make_ad(description="Original desc", description_bs="")
        self.assertEqual(ad.get_description("bs"), "Original desc")

    def test_unknown_locale_falls_to_base_when_present(self) -> None:
        """Unknown locale (e.g. 'fr') falls back to the Russian base (description)."""
        ad = _make_ad(description="Russian")
        self.assertEqual(ad.get_description("fr"), "Russian")

    # ── Edge cases ───────────────────────────────────────────────────

    def test_returns_empty_when_all_fields_are_none(self) -> None:
        ad = _make_ad(description=None, description_bs=None)
        self.assertEqual(ad.get_description("bs"), "")

    def test_returns_empty_when_all_fields_are_empty(self) -> None:
        ad = _make_ad(description="", description_bs="")
        self.assertEqual(ad.get_description("bs"), "")

    def test_whitespace_only_is_truthy_and_returned(self) -> None:
        ad = _make_ad(description_bs="   ", description="Should not appear")
        self.assertEqual(ad.get_description("bs"), "   ")

    def test_none_locale_field_skips_gracefully(self) -> None:
        ad = _make_ad(description="Original", description_bs=None)
        self.assertEqual(ad.get_description("bs"), "Original")
