"""
Tests for LanguageLocale enum and its fts_config property.

Verifies enum values and PostgreSQL text search config mapping.
No database interaction required.
"""

from django.test import SimpleTestCase

from apps.core.enums import LanguageLocale


class LanguageLocaleTests(SimpleTestCase):
    """Tests for LanguageLocale enum values and fts_config property."""

    def test_language_locale_values(self) -> None:
        """Assert each LanguageLocale member has the correct string value."""
        assert LanguageLocale.RUSSIAN.value == "ru"
        assert LanguageLocale.BOSNIAN.value == "bs"
        assert LanguageLocale.ENGLISH.value == "en"

    def test_fts_config_property(self) -> None:
        """Assert fts_config returns the correct PostgreSQL text search config."""
        assert LanguageLocale.RUSSIAN.fts_config == "russian"
        assert LanguageLocale.BOSNIAN.fts_config == "simple"
        assert LanguageLocale.ENGLISH.fts_config == "english"