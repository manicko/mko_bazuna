"""Tests for the declared session lifetime and refresh policy (04-AUT-006).

``base.py`` now declares ``SESSION_COOKIE_AGE`` and
``SESSION_SAVE_EVERY_REQUEST`` explicitly so the session policy is a visible
product decision rather than an implicit framework default. These tests pin the
*declaration* and, more importantly, the *semantics* the declaration claims:

* the lifetime is **write-triggered** for an authenticated user: the session is
  written at ``auth_login()`` at login and again only on a ``?lang=`` language
  switch, so ordinary reads do not re-stamp ``expire_date``;
* the lifetime is **refreshed by each recorded search** for an anonymous user,
  because the recorded search is the write that re-stamps the row.

Tests 3 and 4 together are the point: a test that only exercised an anonymous
session would pass without ever touching an authenticated session, which would be
theatre. Test 5 pins the ``?lang=`` exception so the write-triggered semantics are
executable rather than prose. No test hardcodes the production value ``1209600``
— the value is a product decision owned elsewhere, so these tests are
number-independent and survive a later change to 7 days or 24 hours.

This is a settings-diff subject, so it lives in ``config/settings/tests/`` next
to the other settings tests, not in ``test_settings_defaults.py`` (which is about
transport security) and not in ``apps/users/tests/`` (the production diff is a
settings module change).
"""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import pytest
from django.contrib.auth import SESSION_KEY
from django.contrib.sessions.models import Session
from django.test import Client, override_settings
from django.utils import timezone

from config.settings import base
from conftest import make_user

pytestmark = [pytest.mark.django_db, pytest.mark.integration]

# Resolve the repository root with the same walk-up used across the settings
# tests (test_env_allowlist_reverse.py, test_prod_logging.py). Do not invent a
# second shape.
_ROOT = Path(__file__).resolve().parent
while not (_ROOT / "pyproject.toml").exists():
    _ROOT = _ROOT.parent

_SRC_ROOT = _ROOT / "src"

# The name of a production call that sets a per-session expiry would make the
# declared window meaningless (it would let a view override the module policy).
_PER_SESSION_EXPIRY_CALL = "set_expiry("

# A search query that reaches ``record_search_history``. It must be non-empty:
# the service early-returns on an empty/whitespace query, which would make the
# anonymous-refresh test vacuous.
_SEARCH_QUERY = "session-policy-probe"


def _persisted_expiry(session_key: str) -> object:
    """Return the stored ``expire_date`` of a persisted session row."""
    return Session.objects.get(session_key=session_key).expire_date


def _login(client: Client, telegram_id: int) -> str:
    """Authenticate ``client`` through the real login flow; return the session key.

    Issues a token, performs the bot's phase-1 claim via the service, and
    completes the web login — exactly the two-process handshake the production
    view performs. The client then holds a session cookie backed by a
    ``django_session`` row.
    """
    import hashlib

    from apps.users.services.login_token import claim_token

    issued = client.get("/login/issue/")
    assert issued.status_code == 200
    raw_token = issued.context["raw_token"]
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    assert claim_token(token_hash, telegram_id, timezone.now()) is not None

    response = client.post("/login/status/", {"token": raw_token})
    assert response.status_code == 200
    assert SESSION_KEY in client.session
    session_key = client.session.session_key
    assert session_key is not None
    return session_key


def test_session_lifetime_is_declared_in_base() -> None:
    """Both session-policy names are declared in ``config.settings.base``.

    Asserts the *declaration*, never a literal age: Django's inherited default is
    not an attribute of the ``base`` module, so the mere presence of the names
    **is** the claim that this policy is deliberate rather than implicit.
    """
    for name in ("SESSION_COOKIE_AGE", "SESSION_SAVE_EVERY_REQUEST"):
        assert hasattr(base, name), (
            f"config.settings.base must declare {name} explicitly; a Django "
            "default is not an attribute of that module, so an absent "
            "declaration means the policy is implicit again."
        )

    age = getattr(base, "SESSION_COOKIE_AGE")  # noqa: B009 - name is dynamic
    assert isinstance(age, int)
    assert age > 0

    assert getattr(base, "SESSION_SAVE_EVERY_REQUEST") is False  # noqa: B009 - dynamic


def test_declared_age_bounds_a_real_sessions_expiry() -> None:
    """The declared age is what a real persisted session row expires by.

    Number-independent: ``db.SessionStore.create_model_instance`` stamps
    ``expire_date = get_expiry_date()``, which reads ``settings.SESSION_COOKIE_AGE``
    **at every write**, so a real write performed under the override must land at
    approximately ``now + small``. It reads the setting rather than assuming the
    production value, so a later product change to 7 days or 24 hours does not
    break it.
    """
    from django.core.cache import cache

    small_age = 1234
    cache.clear()
    with override_settings(SESSION_COOKIE_AGE=small_age):
        client = Client()
        response = client.get("/search/", {"q": _SEARCH_QUERY})
        assert response.status_code == 200
        session_key = client.session.session_key
        assert session_key is not None
        stored = Session.objects.get(session_key=session_key)

    # The row was persisted and expires at approximately now + the declared age.
    remaining = stored.expire_date - timezone.now()
    assert timedelta(seconds=small_age - 30) <= remaining <= timedelta(
        seconds=small_age + 30
    )

    # A session past its ``expire_date`` is deleted by the janitor: ``clear_expired()``
    # removes only rows past that bound, so the declared age is what actually
    # bounds the window.
    from django.contrib.sessions.backends.db import SessionStore

    Session.objects.filter(session_key=session_key).update(
        expire_date=timezone.now() - timedelta(seconds=1)
    )
    SessionStore().clear_expired()
    assert not Session.objects.filter(session_key=session_key).exists()


def test_authenticated_session_is_written_once_at_login_and_never_refreshed() -> None:
    """An authenticated session's ``expire_date`` is stamped at login and frozen.

    Read-only requests that trigger no production session write (no ``?lang=``,
    no search, no consent write) must leave the persisted ``expire_date``
    unchanged. This is the authenticated half of the central semantic claim: the
    lifetime is absolute from login, not a sliding idle window.
    """
    telegram_id = 700000600
    make_user(telegram_id, username="session_policy_auth")

    from django.core.cache import cache

    cache.clear()
    client = Client()
    session_key = _login(client, telegram_id)
    expiry_after_login = _persisted_expiry(session_key)

    for _ in range(5):
        response = client.get("/")
        assert response.status_code == 200

    assert _persisted_expiry(session_key) == expiry_after_login


def test_lang_switch_re_stamps_authenticated_session() -> None:
    """A ``?lang=`` request from an authenticated user DOES re-stamp ``expire_date``.

    The authenticated lifetime is write-triggered, not frozen after login: the
    language middleware writes ``request.session["django_language"]`` on a
    supported ``?lang=`` for an authenticated user, and that write makes
    ``SessionMiddleware.process_response`` save the row again, so the window
    moves. Test 3 covers the *no-write* authenticated path (no ``?lang=``); this
    test pins the exception, so the spec's "again only on a ``?lang=`` language
    switch" clause is an executable fact rather than prose that can drift.

    Number-independent: it compares two observed expiries, never ``1209600``.
    """
    telegram_id = 700000601
    make_user(telegram_id, username="session_policy_lang")

    from django.core.cache import cache

    cache.clear()
    client = Client()
    session_key = _login(client, telegram_id)
    expiry_after_login = _persisted_expiry(session_key)

    response = client.get("/", {"lang": "en"})
    assert response.status_code == 200

    assert _persisted_expiry(session_key) > expiry_after_login


def test_anonymous_session_is_refreshed_by_each_recorded_search() -> None:
    """A recorded anonymous search re-stamps ``expire_date`` strictly later.

    The query is non-empty on purpose: ``record_search_history`` early-returns on
    an empty query, which would make this assertion vacuous.
    """
    from django.core.cache import cache

    cache.clear()
    client = Client()

    first = client.get("/search/", {"q": _SEARCH_QUERY})
    assert first.status_code == 200
    session_key = client.session.session_key
    assert session_key is not None
    first_expiry = _persisted_expiry(session_key)

    second = client.get("/search/", {"q": f"{_SEARCH_QUERY}-again"})
    assert second.status_code == 200
    assert client.session.session_key == session_key
    second_expiry = _persisted_expiry(session_key)

    assert second_expiry > first_expiry


def test_no_per_session_expiry_override_exists() -> None:
    """No production code overrides the declared window per session.

    Two independent guards: a source scan for ``set_expiry(`` across non-test
    ``src/**/*.py``, and the absence of a ``_session_expiry`` key in a real
    session after a request cycle (the internal field Django uses when a view
    *does* override the window).
    """
    offenders: list[str] = []
    for path in sorted(_SRC_ROOT.rglob("*.py")):
        if "tests" in path.relative_to(_SRC_ROOT).parts:
            continue
        if _PER_SESSION_EXPIRY_CALL in path.read_text(encoding="utf-8"):
            offenders.append(path.relative_to(_ROOT).as_posix())
    assert not offenders, (
        "production code overrides the session expiry per session, which would "
        f"defeat the declared policy: {offenders}. Remove the call, or fix the "
        "declared policy instead."
    )

    client = Client()
    response = client.get("/")
    assert response.status_code == 200
    assert "_session_expiry" not in client.session
