"""
Tests for core context processors.

Verifies the language() context processor returns correct LANGUAGE_CODE
values. No database interaction required — uses Django's SimpleTestCase.
"""

from __future__ import annotations

from django.http import HttpRequest
from django.test import SimpleTestCase

from apps.core.context_processors import language


class LanguageContextProcessorTests(SimpleTestCase):
    """Tests for the language() context processor function."""

    def test_returns_dict_with_language_code_key(self) -> None:
        """language() returns a dict with LANGUAGE_CODE key."""
        request = HttpRequest()
        request.LANGUAGE_CODE = "en"
        result = language(request)
        assert isinstance(result, dict)
        assert "LANGUAGE_CODE" in result

    def test_extracts_language_code_from_request(self) -> None:
        """language() extracts LANGUAGE_CODE attribute from request."""
        request = HttpRequest()
        request.LANGUAGE_CODE = "bs"
        result = language(request)
        assert result == {"LANGUAGE_CODE": "bs"}

    def test_defaults_to_russian_when_not_set(self) -> None:
        """language() returns 'ru' when LANGUAGE_CODE is not on request."""
        request = HttpRequest()
        result = language(request)
        assert result == {"LANGUAGE_CODE": "ru"}

    def test_handles_explicit_russian(self) -> None:
        """language() returns 'ru' when LANGUAGE_CODE is explicitly 'ru'."""
        request = HttpRequest()
        request.LANGUAGE_CODE = "ru"
        result = language(request)
        assert result == {"LANGUAGE_CODE": "ru"}