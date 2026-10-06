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
from django.conf import settings
from django.contrib.auth.models import AnonymousUser
from django.http import HttpRequest, HttpResponse
from django.test import override_settings
from django.urls import reverse
from django.utils import translation

from apps.core.enums import LanguageLocale
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


def test_lang_param_normalizes_variant(
    middleware: LanguagePreMiddleware,
) -> None:
    """``?lang=en-US`` normalizes to ``en`` via ``LanguageLocale.from_code``.

    Language variants normalize via LanguageLocale.from_code:
    ``en-US`` resolves to ``en`` and the lang_pref cookie IS persisted.
    """
    request = _make_request(get={"lang": "en-US"})
    middleware.process_request(request)
    assert request.LANGUAGE_CODE == "en"
    # Cookie should be persisted for supported (normalized) codes
    assert getattr(request, "_lang_cookie_value", None) == "en"


def test_lang_param_normalizes_bosnian_variant(
    middleware: LanguagePreMiddleware,
) -> None:
    """``?lang=bs-BA`` normalizes to ``bs`` via ``LanguageLocale.from_code``.

    Language variants normalize via LanguageLocale.from_code:
    ``bs-BA`` resolves to ``bs`` and the cookie IS persisted.
    """
    request = _make_request(get={"lang": "bs-BA"})
    middleware.process_request(request)
    assert request.LANGUAGE_CODE == "bs"


def test_invalid_lang_param_defaults_to_language_code(
    middleware: LanguagePreMiddleware,
) -> None:
    """Unsupported ``?lang`` value falls back to BOSNIAN per spec."""
    request = _make_request(get={"lang": "fr"})
    middleware.process_request(request)
    assert request.LANGUAGE_CODE == "bs"


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


# Non-canonical BCP-47 cookie tags (14-I18N-001).
# Each entry is (raw cookie value, expected resolved locale code). A raw value
# whose base language is unsupported resolves to the BOSNIAN fallback per spec.
_NON_CANONICAL_COOKIE_CASES: list[tuple[str, str]] = [
    ("en-US", "en"),
    ("EN", "en"),
    ("en_US", "bs"),  # underscore is not a BCP-47 separator -> unsupported
    ("de-DE", "bs"),  # de is unsupported -> fallback
    ("ru-RU", "ru"),
    ("nonsense", "bs"),
]


def test_cookie_non_canonical_resolves_to_supported_locale(
    middleware: LanguagePreMiddleware,
) -> None:
    """Non-canonical cookie tags resolve to a member of settings.LANGUAGES.

    Before the fix the raw cookie string reached ``translation.activate()``
    unchanged, so ``en-US`` activated ``en-us`` (not a configured locale) and
    every DB-backed string fell through to Russian. Every resolved code must be
    a member of ``settings.LANGUAGES`` (14-I18N-001).
    """
    supported = {code for code, _ in settings.LANGUAGES}
    for raw, expected in _NON_CANONICAL_COOKIE_CASES:
        request = _make_request(cookies={LANGUAGE_COOKIE_NAME: raw})
        middleware.process_request(request)
        assert request.LANGUAGE_CODE in supported, (
            f"cookie {raw!r} resolved to {request.LANGUAGE_CODE!r}, "
            "which is not a member of settings.LANGUAGES"
        )
        assert request.LANGUAGE_CODE in LanguageLocale.values()
        assert request.LANGUAGE_CODE == expected


def test_cookie_membership_holds_for_every_case_in_table(
    middleware: LanguagePreMiddleware,
) -> None:
    """Membership guard spans the canonical AND non-canonical cookie table.

    Iterates ``LanguageLocale.values()`` for the canonical half (never bare
    literals) and the explicit non-canonical half, asserting membership for
    every input including the hostile ones.
    """
    supported = {code for code, _ in settings.LANGUAGES}
    cases = [(code, code) for code in LanguageLocale.values()]
    cases += _NON_CANONICAL_COOKIE_CASES
    for raw, expected in cases:
        request = _make_request(cookies={LANGUAGE_COOKIE_NAME: raw})
        middleware.process_request(request)
        assert request.LANGUAGE_CODE in supported, f"cookie {raw!r} -> {request.LANGUAGE_CODE!r}"
        assert request.LANGUAGE_CODE == expected


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
    """Unsupported Accept-Language falls back to BOSNIAN per spec."""
    request = _make_request(accept_language="fr-FR,fr;q=0.9")
    middleware.process_request(request)
    assert request.LANGUAGE_CODE == "bs"


def test_accept_language_empty_string_falls_back_to_language_code(
    middleware: LanguagePreMiddleware,
) -> None:
    """Empty Accept-Language header falls back to ``settings.LANGUAGE_CODE``."""
    request = _make_request(accept_language="")
    middleware.process_request(request)
    assert request.LANGUAGE_CODE == "en"


def test_accept_language_honours_descending_q_values(
    middleware: LanguagePreMiddleware,
) -> None:
    """The highest-q supported tag wins, not merely the first tag (14-I18N-015).

    ``de-DE`` is unsupported and ranks first; ``ru`` ranks second at q=0.8 and
    must be selected over ``bs`` at q=0.6. Before the fix only the first
    comma-separated tag was inspected, so this resolved to ``bs``.
    """
    request = _make_request(accept_language="de-DE,ru;q=0.8,bs;q=0.6")
    middleware.process_request(request)
    assert request.LANGUAGE_CODE == "ru"


def test_accept_language_q_zero_member_is_not_selected(
    middleware: LanguagePreMiddleware,
) -> None:
    """A supported tag with ``q=0`` is skipped explicitly.

    ``ru;q=0`` means Russian is explicitly unacceptable, so the resolver must
    skip it and fall back to BOSNIAN. Django's parser retains ``q=0`` members,
    so the skip is explicit, not a parser default.
    """
    request = _make_request(accept_language="ru;q=0")
    middleware.process_request(request)
    assert request.LANGUAGE_CODE == "bs"


def test_accept_language_q_zero_higher_rank_does_not_shadow_supported(
    middleware: LanguagePreMiddleware,
) -> None:
    """A q=0 unsupported-first tag does not stop the next supported tag."""
    request = _make_request(accept_language="de-DE;q=0,bs;q=0.7")
    middleware.process_request(request)
    assert request.LANGUAGE_CODE == "bs"


def test_accept_language_underscore_tag_is_unsupported(
    middleware: LanguagePreMiddleware,
) -> None:
    """A malformed member (``en_US``) rejects the whole header -> fallback."""
    request = _make_request(accept_language="en_US")
    middleware.process_request(request)
    assert request.LANGUAGE_CODE == "bs"


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


@override_settings(SESSION_COOKIE_SECURE=True, SESSION_COOKIE_SAMESITE="Strict")
def test_cookie_carries_project_security_attributes(
    middleware: LanguagePreMiddleware,
) -> None:
    """The lang_pref cookie carries the project's secure/samesite/httponly policy.

    ``lang_pref`` was the only project cookie opting out of every
    ``SESSION_COOKIE_*``/``CSRF_COOKIE_*`` attribute the project sets. The
    middleware's ``set_cookie`` is now the authoritative writer (Q5 option (a))
    and reads ``secure``/``samesite`` from settings rather than writing literals,
    so ``prod.py``'s strictness and ``test.py``'s relaxation keep applying.

    ``SESSION_COOKIE_*`` is pinned here (the base settings already do this in
    production) so the assertion is not vacuously true under the test settings'
    ``SESSION_COOKIE_SECURE = False`` relaxation — and so the values are proven
    to be READ from settings, not hard-coded. ``httponly`` is safe because no
    client-side code reads the cookie.
    """
    request = _make_request(get={"lang": "bs"})
    response = HttpResponse()
    middleware.process_request(request)
    middleware.process_response(request, response)

    cookie = response.cookies["lang_pref"]
    # Read from settings, never a literal: Django's Morsel stores Secure as ""
    # when False and True when set, so compare the flag's truthiness.
    assert bool(cookie["secure"]) == settings.SESSION_COOKIE_SECURE
    assert cookie["samesite"] == settings.SESSION_COOKIE_SAMESITE
    assert cookie["httponly"] is True
    # The hardening must not alter the name, max_age or written value.
    assert cookie.value == "bs"
    assert int(cookie["max-age"]) == LANGUAGE_COOKIE_MAX_AGE
    # Vary stays byte-identical to the pre-block contract: this block adds no header.
    assert "Accept-Language" in response.headers.get("Vary", "")
    assert "Cookie" not in response.headers.get("Vary", "")
    assert response.headers.get("Content-Language") == "bs"
    assert request.LANGUAGE_CODE == "bs"


def test_cookie_security_attributes_track_settings(
    middleware: LanguagePreMiddleware,
) -> None:
    """secure/samesite follow SESSION_COOKIE_* rather than a literal.

    Proves the values are read from settings: with the prod values pinned the
    emitted cookie carries ``Secure`` and ``SameSite=Strict``; with the test
    relaxation the ``Secure`` flag is absent. A hard-coded literal could not
    satisfy both.
    """
    request = _make_request(get={"lang": "bs"})
    response = HttpResponse()
    middleware.process_request(request)
    middleware.process_response(request, response)

    cookie = response.cookies["lang_pref"]
    with override_settings(SESSION_COOKIE_SECURE=True, SESSION_COOKIE_SAMESITE="Strict"):
        strict_request = _make_request(get={"lang": "bs"})
        strict_response = HttpResponse()
        middleware.process_request(strict_request)
        middleware.process_response(strict_request, strict_response)
    strict_cookie = strict_response.cookies["lang_pref"]

    assert bool(strict_cookie["secure"]) is True
    assert strict_cookie["samesite"] == "Strict"
    assert bool(cookie["secure"]) is False
    assert cookie["samesite"] == settings.SESSION_COOKIE_SAMESITE


@override_settings(SESSION_COOKIE_SECURE=True, SESSION_COOKIE_SAMESITE="Strict")
def test_lang_param_sets_cookie_without_consent_context(client) -> None:
    """?lang=bs sets lang_pref end-to-end with NO consent context present.

    Under Q5 option (a) the server write is the authoritative writer: the
    language switcher no longer writes the cookie from JavaScript, and it never
    did unless ``consent_preferences`` was set. This drives the real middleware
    stack (no ``consent_preferences`` cookie seeded) against a DB-free route and
    asserts the cookie is still emitted — the case current tests do not cover.
    The cookie must also carry ``httponly`` (safe because no client-side code
    reads it) and the project's security policy; ``SESSION_COOKIE_*`` is pinned
    so the values are proven to be read from settings, not hard-coded.
    """
    response = client.get(reverse("core:csp_report"), {"lang": "bs"})

    assert "consent_preferences" not in client.cookies
    assert "lang_pref" in response.cookies
    cookie = response.cookies["lang_pref"]
    assert cookie.value == "bs"
    assert cookie["httponly"] is True
    assert bool(cookie["secure"]) == settings.SESSION_COOKIE_SECURE
    assert cookie["samesite"] == settings.SESSION_COOKIE_SAMESITE
    assert int(cookie["max-age"]) == LANGUAGE_COOKIE_MAX_AGE


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
        (None, None, "fr-FR,fr;q=0.9", "bs"),  # unsupported -> bs per spec
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
    """An invalid ``?lang`` falls back to BOSNIAN in both thread-local and
    request."""
    request = _make_request(get={"lang": "fr"})
    middleware.process_request(request)
    assert translation.get_language() == "bs"
    assert request.LANGUAGE_CODE == "bs"
