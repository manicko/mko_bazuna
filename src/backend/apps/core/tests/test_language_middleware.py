"""
Tests for LanguagePreMiddleware language detection and priority.

Verifies the priority order: ?lang=X > lang_pref cookie > Accept-Language
header > default to ``settings.LANGUAGE_CODE``. Also verifies cookie persistence when ?lang is
used.

No database interaction required.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from django.contrib.auth.models import AnonymousUser
from django.http import HttpRequest, HttpResponse
from django.utils import translation

from apps.core.middleware.language import (
    LANGUAGE_COOKIE_MAX_AGE,
    LANGUAGE_COOKIE_NAME,
    LanguagePreMiddleware,
)

pytestmark = [pytest.mark.unit]


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


@pytest.fixture
def middleware():
    """Instantiate middleware once per test.

    Thread-local cleanup is handled by the shared autouse
    ``_reset_translation_state`` fixture in ``src/backend/conftest.py``.
    """
    mw = LanguagePreMiddleware(get_response=lambda r: None)
    yield mw


# --- Priority: ?lang parameter ---


def test_lang_param_overrides_cookie(middleware: LanguagePreMiddleware) -> None:
    """?lang=bs overrides lang_pref cookie value."""
    request = _make_request(
        get={"lang": "bs"},
        cookies={LANGUAGE_COOKIE_NAME: "en"},
    )
    middleware.process_request(request)
    assert request.LANGUAGE_CODE == "bs"


def test_lang_param_overrides_accept_language(
    middleware: LanguagePreMiddleware,
) -> None:
    """?lang=ru overrides Accept-Language header."""
    request = _make_request(
        get={"lang": "ru"},
        accept_language="en-US,en;q=0.9",
    )
    middleware.process_request(request)
    assert request.LANGUAGE_CODE == "ru"


def test_lang_param_valid_values(middleware: LanguagePreMiddleware) -> None:
    """All supported LanguageLocale values work via ?lang."""
    for code in ("ru", "bs", "en"):
        request = _make_request(get={"lang": code})
        middleware.process_request(request)
        assert request.LANGUAGE_CODE == code


def test_invalid_lang_param_defaults_to_language_code(
    middleware: LanguagePreMiddleware,
) -> None:
    """Unsupported ``?lang`` value falls back to ``settings.LANGUAGE_CODE``."""
    request = _make_request(get={"lang": "fr"})
    middleware.process_request(request)
    assert request.LANGUAGE_CODE == "en"


# --- Priority: cookie ---


def test_cookie_overrides_accept_language(middleware: LanguagePreMiddleware) -> None:
    """lang_pref cookie overrides Accept-Language header."""
    request = _make_request(
        cookies={LANGUAGE_COOKIE_NAME: "bs"},
        accept_language="en-US,en;q=0.9",
    )
    middleware.process_request(request)
    assert request.LANGUAGE_CODE == "bs"


def test_cookie_valid_values(middleware: LanguagePreMiddleware) -> None:
    """All supported LanguageLocale values work via cookie."""
    for code in ("ru", "bs", "en"):
        request = _make_request(cookies={LANGUAGE_COOKIE_NAME: code})
        middleware.process_request(request)
        assert request.LANGUAGE_CODE == code


# --- Priority: Accept-Language header ---


def test_accept_language_parsed(middleware: LanguagePreMiddleware) -> None:
    """Accept-Language header sets LANGUAGE_CODE to first tag."""
    request = _make_request(accept_language="en-US,en;q=0.9")
    middleware.process_request(request)
    assert request.LANGUAGE_CODE == "en"


def test_accept_language_with_region_tag(middleware: LanguagePreMiddleware) -> None:
    """Region tag (bs-BA) is stripped to language code."""
    request = _make_request(accept_language="bs-BA,bs;q=0.9")
    middleware.process_request(request)
    assert request.LANGUAGE_CODE == "bs"


def test_accept_language_simple_tag(middleware: LanguagePreMiddleware) -> None:
    """Simple language tag without region works."""
    request = _make_request(accept_language="ru")
    middleware.process_request(request)
    assert request.LANGUAGE_CODE == "ru"


def test_accept_language_unsupported_falls_back_to_language_code(
    middleware: LanguagePreMiddleware,
) -> None:
    """Unsupported Accept-Language falls back to ``settings.LANGUAGE_CODE``."""
    request = _make_request(accept_language="fr-FR,fr;q=0.9")
    middleware.process_request(request)
    assert request.LANGUAGE_CODE == "en"


def test_accept_language_empty_string_falls_back_to_language_code(
    middleware: LanguagePreMiddleware,
) -> None:
    """Empty Accept-Language header falls back to ``settings.LANGUAGE_CODE``."""
    request = _make_request(accept_language="")
    middleware.process_request(request)
    assert request.LANGUAGE_CODE == "en"


# --- Priority: default ---


def test_default_to_language_code(middleware: LanguagePreMiddleware) -> None:
    """No lang, cookie, or Accept-Language defaults to ``settings.LANGUAGE_CODE``."""
    request = _make_request()
    middleware.process_request(request)
    assert request.LANGUAGE_CODE == "en"


# --- Cookie persistence (via process_response) ---


def test_cookie_set_when_lang_param_used(middleware: LanguagePreMiddleware) -> None:
    """?lang=bs sets lang_pref cookie and emits language headers."""
    request = _make_request(get={"lang": "bs"})
    response = HttpResponse()
    middleware.process_request(request)
    middleware.process_response(request, response)
    # Cookie persistence (CR3: 1-year lang_pref)
    assert "lang_pref" in response.cookies
    assert response.cookies["lang_pref"].value == "bs"
    assert int(response.cookies["lang_pref"]["max-age"]) == LANGUAGE_COOKIE_MAX_AGE
    # Header contract (formerly provided by LocaleMiddleware)
    assert "Accept-Language" in response.headers.get("Vary", "")
    assert response.headers.get("Content-Language") == "bs"
    assert request.LANGUAGE_CODE == "bs"


def test_cookie_not_set_when_no_lang_param(middleware: LanguagePreMiddleware) -> None:
    """lang_pref cookie is not (re)set when ?lang is absent."""
    request = _make_request(cookies={LANGUAGE_COOKIE_NAME: "en"})
    response = HttpResponse()
    middleware.process_request(request)
    middleware.process_response(request, response)
    assert request.LANGUAGE_CODE == "en"
    assert "lang_pref" not in response.cookies
    # Headers are still emitted for cookie-driven language
    assert "Accept-Language" in response.headers.get("Vary", "")
    assert response.headers.get("Content-Language") == "en"


# --- Session persistence for authenticated users ---


def test_lang_param_with_session_but_no_user_does_not_crash(
    middleware: LanguagePreMiddleware,
) -> None:
    """?lang must not crash when session is set but user is not.

    Reproduces the production bug: SessionMiddleware runs before
    AuthenticationMiddleware in the middleware chain. The defensive
    ``hasattr(request, "user")`` guard prevents ``AttributeError``.
    """
    request = _make_request(get={"lang": "bs"})
    request.session = MagicMock()
    # Deliberately do NOT set request.user, simulating middleware
    # ordering where AuthenticationMiddleware has not run yet.
    middleware.process_request(request)
    assert request.LANGUAGE_CODE == "bs"


def test_anonymous_user_does_not_persist_session(
    middleware: LanguagePreMiddleware,
) -> None:
    """?lang with an anonymous user does not write to the session."""
    request = _make_request(get={"lang": "en"})
    request.session = MagicMock()
    request.user = AnonymousUser()
    middleware.process_request(request)
    assert request.LANGUAGE_CODE == "en"
    request.session.__setitem__.assert_not_called()


def test_authenticated_user_persists_session(middleware: LanguagePreMiddleware) -> None:
    """?lang with an authenticated user writes language to session."""
    request = _make_request(get={"lang": "en"})
    request.session = MagicMock()
    request.user = MagicMock(is_authenticated=True)
    middleware.process_request(request)
    assert request.LANGUAGE_CODE == "en"
    request.session.__setitem__.assert_called_once_with("django_language", "en")


# --- Thread-local / request-attr consistency (regression guard) ---


def test_thread_local_matches_request_language_code(
    middleware: LanguagePreMiddleware,
) -> None:
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
        (None, None, "fr-FR,fr;q=0.9", "en"),  # unsupported -> default
        ({}, None, None, "en"),  # nothing -> default
    ]
    for get, cookies, accept_language, expected in cases:
        request = _make_request(
            get=get or {},
            cookies=cookies or {},
            accept_language=accept_language,
        )
        middleware.process_request(request)
        assert translation.get_language() == request.LANGUAGE_CODE, (
            f"thread-local != request.LANGUAGE_CODE for {get=}, {cookies=}"
        )
        assert translation.get_language() == expected


def test_invalid_lang_still_syncs_to_language_code(
    middleware: LanguagePreMiddleware,
) -> None:
    """An invalid ``?lang`` falls back to ``settings.LANGUAGE_CODE`` in both
    thread-local and request."""
    request = _make_request(get={"lang": "fr"})
    middleware.process_request(request)
    assert translation.get_language() == "en"
    assert request.LANGUAGE_CODE == "en"
