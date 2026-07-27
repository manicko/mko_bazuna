"""
Tests for LanguagePreMiddleware language detection and priority.

Verifies the priority order: ?lang=X > lang_pref cookie > Accept-Language
header > default to Russian. Also verifies cookie persistence when ?lang is
used.

No database interaction required — uses Django's SimpleTestCase.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from django.http import HttpRequest
from django.test import SimpleTestCase

from apps.core.middleware.language import (
    LANGUAGE_COOKIE_MAX_AGE,
    LANGUAGE_COOKIE_NAME,
    LanguagePreMiddleware,
)


def _make_request(
    get: dict | None = None,
    cookies: dict | None = None,
    accept_language: str | None = None,
) -> HttpRequest:
    """Create a minimal HttpRequest with the given attributes."""
    request = HttpRequest()
    request.GET = get or {}
    request.COOKIES = cookies or {}
    if accept_language is not None:
        request.META["HTTP_ACCEPT_LANGUAGE"] = accept_language
    return request


class LanguagePreMiddlewareTests(SimpleTestCase):
    """Tests for LanguagePreMiddleware language detection priority."""

    def setUp(self) -> None:
        """Instantiate middleware once per test."""
        self.middleware = LanguagePreMiddleware(get_response=lambda r: None)

    # --- Priority: ?lang parameter ---

    def test_lang_param_overrides_cookie(self) -> None:
        """?lang=bs overrides lang_pref cookie value."""
        request = _make_request(
            get={"lang": "bs"},
            cookies={LANGUAGE_COOKIE_NAME: "en"},
        )
        self.middleware.process_request(request)
        assert request.LANGUAGE_CODE == "bs"

    def test_lang_param_overrides_accept_language(self) -> None:
        """?lang=ru overrides Accept-Language header."""
        request = _make_request(
            get={"lang": "ru"},
            accept_language="en-US,en;q=0.9",
        )
        self.middleware.process_request(request)
        assert request.LANGUAGE_CODE == "ru"

    def test_lang_param_valid_values(self) -> None:
        """All supported LanguageLocale values work via ?lang."""
        for code in ("ru", "bs", "en"):
            request = _make_request(get={"lang": code})
            self.middleware.process_request(request)
            assert request.LANGUAGE_CODE == code

    def test_invalid_lang_param_defaults_to_russian(self) -> None:
        """Unsupported ?lang value falls back to ru."""
        request = _make_request(get={"lang": "fr"})
        self.middleware.process_request(request)
        assert request.LANGUAGE_CODE == "ru"

    # --- Priority: cookie ---

    def test_cookie_overrides_accept_language(self) -> None:
        """lang_pref cookie overrides Accept-Language header."""
        request = _make_request(
            cookies={LANGUAGE_COOKIE_NAME: "bs"},
            accept_language="en-US,en;q=0.9",
        )
        self.middleware.process_request(request)
        assert request.LANGUAGE_CODE == "bs"

    def test_cookie_valid_values(self) -> None:
        """All supported LanguageLocale values work via cookie."""
        for code in ("ru", "bs", "en"):
            request = _make_request(cookies={LANGUAGE_COOKIE_NAME: code})
            self.middleware.process_request(request)
            assert request.LANGUAGE_CODE == code

    # --- Priority: Accept-Language header ---

    def test_accept_language_parsed(self) -> None:
        """Accept-Language header sets LANGUAGE_CODE to first tag."""
        request = _make_request(accept_language="en-US,en;q=0.9")
        self.middleware.process_request(request)
        assert request.LANGUAGE_CODE == "en"

    def test_accept_language_with_region_tag(self) -> None:
        """Region tag (bs-BA) is stripped to language code."""
        request = _make_request(accept_language="bs-BA,bs;q=0.9")
        self.middleware.process_request(request)
        assert request.LANGUAGE_CODE == "bs"

    def test_accept_language_simple_tag(self) -> None:
        """Simple language tag without region works."""
        request = _make_request(accept_language="ru")
        self.middleware.process_request(request)
        assert request.LANGUAGE_CODE == "ru"

    def test_accept_language_unsupported_falls_back(self) -> None:
        """Unsupported Accept-Language falls back to ru."""
        request = _make_request(accept_language="fr-FR,fr;q=0.9")
        self.middleware.process_request(request)
        assert request.LANGUAGE_CODE == "ru"

    def test_accept_language_empty_string(self) -> None:
        """Empty Accept-Language header falls back to ru."""
        request = _make_request(accept_language="")
        self.middleware.process_request(request)
        assert request.LANGUAGE_CODE == "ru"

    # --- Priority: default ---

    def test_default_to_russian(self) -> None:
        """No lang, cookie, or Accept-Language defaults to ru."""
        request = _make_request()
        self.middleware.process_request(request)
        assert request.LANGUAGE_CODE == "ru"

    # --- Cookie persistence ---

    def test_cookie_set_when_lang_param_used(self) -> None:
        """?lang=bs sets lang_pref cookie on the request."""
        request = _make_request(get={"lang": "bs"})
        request.set_cookie = MagicMock()
        self.middleware.process_request(request)
        request.set_cookie.assert_called_once_with(
            LANGUAGE_COOKIE_NAME,
            "bs",
            max_age=LANGUAGE_COOKIE_MAX_AGE,
        )
        assert request.LANGUAGE_CODE == "bs"

    def test_cookie_not_set_when_no_lang_param(self) -> None:
        """lang_pref cookie is not set when ?lang is absent."""
        request = _make_request(cookies={LANGUAGE_COOKIE_NAME: "en"})
        mock_set_cookie = MagicMock()
        request.set_cookie = mock_set_cookie
        self.middleware.process_request(request)
        assert request.LANGUAGE_CODE == "en"
        mock_set_cookie.assert_not_called()