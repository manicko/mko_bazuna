"""
Tests for LanguagePreMiddleware language detection and priority.

Verifies the priority order: ?lang=X > lang_pref cookie > Accept-Language
header > default to Russian. Also verifies cookie persistence when ?lang is
used.

No database interaction required — uses Django's SimpleTestCase.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from django.contrib.auth.models import AnonymousUser
from django.http import HttpRequest, HttpResponse
from django.test import SimpleTestCase
from django.utils import translation

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
        # ``process_request`` now calls ``translation.activate()``; clear the
        # thread-local afterwards so tests do not leak active languages.
        self.addCleanup(translation.deactivate)

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

    # --- Cookie persistence (via process_response) ---

    def test_cookie_set_when_lang_param_used(self) -> None:
        """?lang=bs sets lang_pref cookie and emits language headers."""
        request = _make_request(get={"lang": "bs"})
        response = HttpResponse()
        self.middleware.process_request(request)
        self.middleware.process_response(request, response)
        # Cookie persistence (CR3: 1-year lang_pref)
        self.assertIn("lang_pref", response.cookies)
        self.assertEqual(response.cookies["lang_pref"].value, "bs")
        self.assertEqual(
            int(response.cookies["lang_pref"]["max-age"]), LANGUAGE_COOKIE_MAX_AGE
        )
        # Header contract (formerly provided by LocaleMiddleware)
        self.assertIn("Accept-Language", response.headers.get("Vary", ""))
        self.assertEqual(response.headers.get("Content-Language"), "bs")
        assert request.LANGUAGE_CODE == "bs"

    def test_cookie_not_set_when_no_lang_param(self) -> None:
        """lang_pref cookie is not (re)set when ?lang is absent."""
        request = _make_request(cookies={LANGUAGE_COOKIE_NAME: "en"})
        response = HttpResponse()
        self.middleware.process_request(request)
        self.middleware.process_response(request, response)
        assert request.LANGUAGE_CODE == "en"
        self.assertNotIn("lang_pref", response.cookies)
        # Headers are still emitted for cookie-driven language
        self.assertIn("Accept-Language", response.headers.get("Vary", ""))
        self.assertEqual(response.headers.get("Content-Language"), "en")

    # --- Session persistence for authenticated users ---

    def test_lang_param_with_session_but_no_user_does_not_crash(self) -> None:
        """?lang must not crash when session is set but user is not.

        Reproduces the production bug: SessionMiddleware runs before
        AuthenticationMiddleware in the middleware chain. The defensive
        ``hasattr(request, "user")`` guard prevents ``AttributeError``.
        """
        request = _make_request(get={"lang": "bs"})
        request.session = MagicMock()
        # Deliberately do NOT set request.user, simulating middleware
        # ordering where AuthenticationMiddleware has not run yet.
        self.middleware.process_request(request)
        assert request.LANGUAGE_CODE == "bs"

    def test_anonymous_user_does_not_persist_session(self) -> None:
        """?lang with an anonymous user does not write to the session."""
        request = _make_request(get={"lang": "en"})
        request.session = MagicMock()
        request.user = AnonymousUser()
        self.middleware.process_request(request)
        assert request.LANGUAGE_CODE == "en"
        request.session.__setitem__.assert_not_called()

    def test_authenticated_user_persists_session(self) -> None:
        """?lang with an authenticated user writes language to session."""
        request = _make_request(get={"lang": "en"})
        request.session = MagicMock()
        request.user = MagicMock(is_authenticated=True)
        self.middleware.process_request(request)
        assert request.LANGUAGE_CODE == "en"
        request.session.__setitem__.assert_called_once_with(
            "django_language", "en"
        )

    # --- Thread-local / request-attr consistency (regression guard) ---

    def test_thread_local_matches_request_language_code(self) -> None:
        """``translation.get_language()`` must agree with ``request.LANGUAGE_CODE``.

        Removing ``LocaleMiddleware`` means this middleware owns the thread-local
        active language (read by ``{% get_current_language %}`` and the ``i18n``
        context processor). If activation and the request attribute ever diverge,
        the switcher highlight desyncs from the rendered ad text.
        """
        cases = [
            ({"lang": "en"}, None, None, "en"),  # ?lang= wins
            (None, {"lang_pref": "bs"}, None, "bs"),  # cookie
            (None, None, "en-US,en;q=0.9", "en"),  # Accept-Language
            (None, None, "fr-FR,fr;q=0.9", "ru"),  # unsupported -> default
            ({}, None, None, "ru"),  # nothing -> default
        ]
        for get, cookies, accept_language, expected in cases:
            request = _make_request(
                get=get or {},
                cookies=cookies or {},
                accept_language=accept_language,
            )
            self.middleware.process_request(request)
            self.assertEqual(
                translation.get_language(),
                request.LANGUAGE_CODE,
                msg=f"thread-local != request.LANGUAGE_CODE for {get=}, {cookies=}",
            )
            self.assertEqual(translation.get_language(), expected)

    def test_invalid_lang_still_syncs_to_russian(self) -> None:
        """An invalid ?lang falls back to ``ru`` in both thread-local and request."""
        request = _make_request(get={"lang": "fr"})
        self.middleware.process_request(request)
        self.assertEqual(translation.get_language(), "ru")
        self.assertEqual(request.LANGUAGE_CODE, "ru")