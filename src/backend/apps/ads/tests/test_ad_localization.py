"""
Unit tests for Ad model localized getters (get_title / get_description).

Verifies the fallback chain: ``title_<locale>`` -> ``title`` (Russian base).
There is no ``title_ru``/``description_ru`` column — the Russian base lives in
``title``/``description`` — so the assertions use those real fields only.

Uses in-memory ``Ad`` instances (no DB).
"""

import pytest

from apps.ads.models import Ad

pytestmark = [pytest.mark.unit]


def _make_ad(**kwargs) -> Ad:
    """Create an in-memory Ad for testing localized getters (no DB).

    Sets default values for every locale-aware field, then overrides with any
    provided keyword arguments. The returned object is a real ``Ad`` instance
    built via ``__new__`` so it carries the actual ``get_title`` /
    ``get_description`` methods without needing a database row.
    """
    fields: dict[str, str | None] = {
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


# ── Locale-specific content ──────────────────────────────────────────────


def test_get_title_returns_bs_when_present() -> None:
    ad = _make_ad(title="Original", title_bs="Bosnian title")
    assert ad.get_title("bs") == "Bosnian title"


def test_get_title_returns_en_when_present() -> None:
    ad = _make_ad(title="Original", title_en="English title")
    assert ad.get_title("en") == "English title"


def test_get_title_returns_ru_with_default_locale() -> None:
    """Default locale (``ru``) returns the Russian base stored in ``title``."""
    ad = _make_ad(title="Russian title")
    assert ad.get_title() == "Russian title"


# ── Fallback: locale empty -> Russian base ───────────────────────────────


def test_get_title_fallback_ru_when_bs_is_none() -> None:
    ad = _make_ad(title="Russian fallback", title_bs=None)
    assert ad.get_title("bs") == "Russian fallback"


def test_get_title_fallback_ru_when_bs_is_empty() -> None:
    ad = _make_ad(title="Russian fallback", title_bs="")
    assert ad.get_title("bs") == "Russian fallback"


# ── Fallback: locale empty -> Russian base (None / empty) ──────────────────


def test_get_title_fallback_base_when_locale_and_ru_are_none() -> None:
    ad = _make_ad(title="Original title", title_bs=None)
    assert ad.get_title("bs") == "Original title"


def test_get_title_fallback_base_when_locale_and_ru_are_empty() -> None:
    ad = _make_ad(title="Original title", title_bs="")
    assert ad.get_title("bs") == "Original title"


def test_get_title_unknown_locale_falls_to_base_when_present() -> None:
    """Unknown locale (e.g. 'fr') falls back to the Russian base (title)."""
    ad = _make_ad(title="Russian")
    assert ad.get_title("fr") == "Russian"


# ── Edge cases ───────────────────────────────────────────────────────────


def test_get_title_returns_empty_when_all_fields_are_none() -> None:
    ad = _make_ad(title=None, title_bs=None)
    assert ad.get_title("bs") == ""


def test_get_title_returns_empty_when_all_fields_are_empty() -> None:
    ad = _make_ad(title="", title_bs="")
    assert ad.get_title("bs") == ""


def test_get_title_whitespace_only_is_truthy_and_returned() -> None:
    """Whitespace-only strings are truthy -> returned without fallback."""
    ad = _make_ad(title_bs="   ", title="Should not appear")
    assert ad.get_title("bs") == "   "


def test_get_title_none_locale_field_skips_gracefully() -> None:
    ad = _make_ad(title="Original", title_bs=None)
    assert ad.get_title("bs") == "Original"


# ── description ──────────────────────────────────────────────────────────


def test_get_description_returns_bs_when_present() -> None:
    ad = _make_ad(description="Original", description_bs="Bosnian desc")
    assert ad.get_description("bs") == "Bosnian desc"


def test_get_description_returns_en_when_present() -> None:
    ad = _make_ad(description="Original", description_en="English desc")
    assert ad.get_description("en") == "English desc"


def test_get_description_returns_ru_with_default_locale() -> None:
    """Default locale (``ru``) returns the Russian base stored in ``description``."""
    ad = _make_ad(description="Russian desc")
    assert ad.get_description() == "Russian desc"


# ── Fallback: locale empty -> Russian base ───────────────────────────────


def test_get_description_fallback_ru_when_bs_is_none() -> None:
    ad = _make_ad(description="Russian fallback", description_bs=None)
    assert ad.get_description("bs") == "Russian fallback"


def test_get_description_fallback_ru_when_bs_is_empty() -> None:
    ad = _make_ad(description="Russian fallback", description_bs="")
    assert ad.get_description("bs") == "Russian fallback"


# ── Fallback: locale empty -> Russian base (None / empty) ──────────────────


def test_get_description_fallback_base_when_locale_and_ru_are_none() -> None:
    ad = _make_ad(description="Original desc", description_bs=None)
    assert ad.get_description("bs") == "Original desc"


def test_get_description_fallback_base_when_locale_and_ru_are_empty() -> None:
    ad = _make_ad(description="Original desc", description_bs="")
    assert ad.get_description("bs") == "Original desc"


def test_get_description_unknown_locale_falls_to_base_when_present() -> None:
    """Unknown locale (e.g. 'fr') falls back to the Russian base (description)."""
    ad = _make_ad(description="Russian")
    assert ad.get_description("fr") == "Russian"


# ── Edge cases ───────────────────────────────────────────────────────────


def test_get_description_returns_empty_when_all_fields_are_none() -> None:
    ad = _make_ad(description=None, description_bs=None)
    assert ad.get_description("bs") == ""


def test_get_description_returns_empty_when_all_fields_are_empty() -> None:
    ad = _make_ad(description="", description_bs="")
    assert ad.get_description("bs") == ""


def test_get_description_whitespace_only_is_truthy_and_returned() -> None:
    ad = _make_ad(description_bs="   ", description="Should not appear")
    assert ad.get_description("bs") == "   "


def test_get_description_none_locale_field_skips_gracefully() -> None:
    ad = _make_ad(description="Original", description_bs=None)
    assert ad.get_description("bs") == "Original"
