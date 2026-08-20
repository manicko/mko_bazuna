"""
Tests for core context processors.

Verifies the language() context processor returns correct LANGUAGE_CODE
values. No database interaction required — uses Django's SimpleTestCase.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.http import HttpRequest
from django.test import SimpleTestCase

from apps.core.context_processors import header_context, language


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


class HeaderContextProcessorTests(SimpleTestCase):
    """Tests for header_context() preferred-city + cities exposure."""

    def _call_header_context(self, request: HttpRequest) -> dict:
        """Invoke header_context() with Category/City DB queries mocked."""
        with (
            patch("apps.categories.models.Category") as mock_category,
            patch("apps.locations.models.City") as mock_city,
        ):
            mock_category.objects.root_nodes.return_value.filter.return_value.order_by.return_value = []
            mock_city.objects.order_by.return_value = []
            context = header_context(request)
        return {"context": context, "mock_city": mock_city}

    def test_country_wide_label_when_no_preference(self) -> None:
        """Without a preferred city the badge shows the country-wide label."""
        request = HttpRequest()
        request.LANGUAGE_CODE = "ru"
        result = self._call_header_context(request)
        assert result["context"]["preferred_city_display"] == "Вся страна"
        assert "cities" in result["context"]

    def test_localized_name_for_valid_slug(self) -> None:
        """A valid preferred-city slug maps to its localized name."""
        city = MagicMock()
        city.get_name.return_value = "Подгорица"
        with (
            patch("apps.categories.models.Category") as mock_category,
            patch("apps.locations.models.City") as mock_city,
        ):
            mock_category.objects.root_nodes.return_value.filter.return_value.order_by.return_value = []
            mock_city.objects.order_by.return_value = []
            mock_city.objects.filter.return_value.first.return_value = city

            request = HttpRequest()
            request.preferred_city = "podgorica"
            request.LANGUAGE_CODE = "ru"
            context = header_context(request)

        assert context["preferred_city_display"] == "Подгорица"
        city.get_name.assert_called_once()

    def test_country_wide_label_for_stale_slug(self) -> None:
        """A preferred-city slug not found in the DB falls back to the label."""
        with (
            patch("apps.categories.models.Category") as mock_category,
            patch("apps.locations.models.City") as mock_city,
        ):
            mock_category.objects.root_nodes.return_value.filter.return_value.order_by.return_value = []
            mock_city.objects.order_by.return_value = []
            mock_city.objects.filter.return_value.first.return_value = None

            request = HttpRequest()
            request.preferred_city = "deleted-city"
            request.LANGUAGE_CODE = "ru"
            context = header_context(request)

        assert context["preferred_city_display"] == "Вся страна"

    def test_cities_key_present(self) -> None:
        """Context exposes the ordered ``cities`` list for the dropdown."""
        request = HttpRequest()
        request.LANGUAGE_CODE = "ru"
        result = self._call_header_context(request)
        assert "cities" in result["context"]

    def test_favorites_count_none_for_anonymous(self) -> None:
        """Anonymous (or missing) request user yields ``favorites_count=None``."""
        request = HttpRequest()
        request.LANGUAGE_CODE = "ru"
        result = self._call_header_context(request)
        assert result["context"]["favorites_count"] is None

    def test_favorites_count_for_authenticated(self) -> None:
        """Authenticated user yields an integer favorites count."""
        user = MagicMock()
        user.is_authenticated = True
        user.favorites.count.return_value = 3

        request = HttpRequest()
        request.LANGUAGE_CODE = "ru"
        request.user = user
        result = self._call_header_context(request)

        assert result["context"]["favorites_count"] == 3
        user.favorites.count.assert_called_once()
