"""
Tests for LanguageLocale enum and its fts_config property.

Verifies enum values, PostgreSQL text search config mapping, and
language-code resolution via ``from_code``.
No database interaction required.
"""

import pytest

from apps.core.enums import LanguageLocale

pytestmark = [pytest.mark.unit]


def test_language_locale_values() -> None:
    """Assert each LanguageLocale member has the correct string value."""
    assert LanguageLocale.RUSSIAN.value == "ru"
    assert LanguageLocale.BOSNIAN.value == "bs"
    assert LanguageLocale.ENGLISH.value == "en"


def test_fts_config_property() -> None:
    """Assert fts_config returns the correct PostgreSQL text search config."""
    assert LanguageLocale.RUSSIAN.fts_config == "russian"
    assert LanguageLocale.BOSNIAN.fts_config == "simple"
    assert LanguageLocale.ENGLISH.fts_config == "english"


def test_from_code_russian() -> None:
    """from_code('ru') maps to LanguageLocale.RUSSIAN."""
    assert LanguageLocale.from_code("ru") == LanguageLocale.RUSSIAN


def test_from_code_english_with_region() -> None:
    """from_code('en-US') normalizes the region tag and maps to ENGLISH."""
    assert LanguageLocale.from_code("en-US") == LanguageLocale.ENGLISH


def test_from_code_bosnian() -> None:
    """from_code('bs') maps to LanguageLocale.BOSNIAN."""
    assert LanguageLocale.from_code("bs") == LanguageLocale.BOSNIAN


def test_from_code_none_falls_back() -> None:
    """from_code(None) returns the provided fallback (BOSNIAN by default)."""
    assert (
        LanguageLocale.from_code(None, fallback=LanguageLocale.BOSNIAN)
        == LanguageLocale.BOSNIAN
    )


def test_from_code_unsupported_falls_back() -> None:
    """from_code('fr') returns the fallback when the code is unsupported."""
    assert (
        LanguageLocale.from_code("fr", fallback=LanguageLocale.BOSNIAN)
        == LanguageLocale.BOSNIAN
    )


def test_from_code_defaults_to_bosnian() -> None:
    """from_code(None) with no explicit fallback defaults to BOSNIAN."""
    assert LanguageLocale.from_code(None) == LanguageLocale.BOSNIAN
