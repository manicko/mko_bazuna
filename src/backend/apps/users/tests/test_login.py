"""
Tests for web login views (login_issue, login_status) — 04-AUT-001.

Covers:
- login_issue: 200 response, token hash stored as SHA-256, 5-min expiry, raw_token in context, rate limiting
- login_status: 200 (claimed), 204 (pending), 410 (expired/consumed/nonexistent/banned)
- Session establishment on successful login
"""

import hashlib
from datetime import timedelta

import pytest
from django.test import Client
from django.utils import timezone

from apps.locations.models import City
from apps.users.models import LoginToken, User
from apps.users.services.login_token import LOGIN_BROWSER_ID_COOKIE
from conftest import make_user

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


@pytest.fixture(autouse=True)
def _clear_cache():
    """Clear Django cache between tests to prevent rate-limiter state bleed."""
    from django.core.cache import cache

    cache.clear()
    yield
    cache.clear()


# ---------------------------------------------------------------------------
# login_issue tests
# ---------------------------------------------------------------------------


class TestLoginIssue:
    """Tests for login_issue view (token issuance)."""

    def test_login_issue_renders_deep_link(self) -> None:
        """login_issue returns 200 and renders the Telegram deep-link via
        the ``{% telegram_deep_link %}`` tag."""
        client = Client()
        client.cookies["js"] = "true"
        response = client.get("/login/issue/")

        assert response.status_code == 200
        content = response.content.decode()
        assert "js-telegram-link" in content
        assert "data-bot-encoded" in content
        assert 'data-start="login_' in content

    def test_login_issue_stores_token_hash_not_raw(self) -> None:
        """login_issue stores a SHA-256 hash, never the raw token."""
        client = Client()
        response = client.get("/login/issue/")

        assert response.status_code == 200
        raw_token = response.context["raw_token"]
        token_hash = hashlib.sha256(raw_token.encode()).hexdigest()

        token = LoginToken.objects.get(token_hash=token_hash)
        assert token.telegram_id is None
        assert token.consumed_at is None

    def test_login_issue_token_expires_in_5_minutes(self) -> None:
        """Issued token expires approximately 5 minutes from now."""
        client = Client()
        response = client.get("/login/issue/")

        raw_token = response.context["raw_token"]
        token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
        token = LoginToken.objects.get(token_hash=token_hash)

        remaining = token.expires_at - timezone.now()
        assert 240 <= remaining.total_seconds() <= 300

    def test_login_issue_returns_429_on_rate_limit(self) -> None:
        """Exceeding 10 requests/minute from the same IP returns 429."""
        client = Client()
        for _ in range(10):
            response = client.get("/login/issue/")
            assert response.status_code == 200

        response = client.get("/login/issue/")
        assert response.status_code == 429

    def test_login_issue_passes_raw_token_to_template(self) -> None:
        """raw_token is available in template context for client-side polling."""
        client = Client()
        response = client.get("/login/issue/")

        assert response.status_code == 200
        assert "raw_token" in response.context
        assert len(response.context["raw_token"]) == 32


# ---------------------------------------------------------------------------
# login_status tests
# ---------------------------------------------------------------------------


class TestLoginTokenBinding:
    """The login token is bound to the browser that requested it (04-AUT-001).

    Every token here is obtained through the real ``/login/issue/`` path so the
    issuing client holds the ``__Host-login_browser_id`` cookie the view set. The
    phase-1 claim is performed through the service — exactly what the bot's
    ``handle_login_orm`` does — so the two-process handshake is exercised
    without importing the bot package.
    """

    @pytest.fixture(autouse=True)
    def _clear_rate_limit_cache(self):
        """Clear rate-limiter cache between tests."""
        from django.core.cache import cache

        cache.clear()
        yield
        cache.clear()

    def _issue(self, client: Client) -> str:
        """GET the issuing URL and return the raw token (client holds the cookie)."""
        issued = client.get("/login/issue/")
        assert issued.status_code == 200
        return issued.context["raw_token"]

    def _claim(self, raw_token: str, telegram_id: int) -> None:
        from apps.users.services.login_token import claim_token

        token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
        assert claim_token(token_hash, telegram_id, timezone.now()) is not None

    def test_token_from_another_browser_is_rejected(self) -> None:
        """A raw token issued to browser A cannot be redeemed from browser B.

        Three assertions — the three ways a binding can be decorative: the
        attacker is refused, the legitimate token is not burned, and A can
        still redeem it.
        """
        telegram_id = 700000500
        make_user(telegram_id, username="binding_owner")

        browser_a = Client()
        raw_token = self._issue(browser_a)
        token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
        self._claim(raw_token, telegram_id)

        # Browser B (no __Host-login_browser_id cookie, or a different one) is
        # refused.
        browser_b = Client()
        rejected = browser_b.post("/login/status/", {"token": raw_token})
        assert rejected.status_code == 410

        # The attack must not destroy the legitimate session: the token is not
        # burned ...
        assert LoginToken.objects.get(token_hash=token_hash).consumed_at is None

        # ... and A can still redeem it.
        accepted = browser_a.post("/login/status/", {"token": raw_token})
        assert accepted.status_code == 200
        assert "_auth_user_id" in browser_a.session

    def test_same_browser_redeems_end_to_end(self) -> None:
        """Issue → bot claim → redeem in the same browser yields 200 + a session."""
        telegram_id = 700000501
        make_user(telegram_id, username="binding_same")

        client = Client()
        raw_token = self._issue(client)
        self._claim(raw_token, telegram_id)

        response = client.post("/login/status/", {"token": raw_token})
        assert response.status_code == 200
        assert "_auth_user_id" in client.session

    def test_repeat_issue_does_not_invalidate_the_binding(self) -> None:
        """A re-issue keeps one binding yet supersedes the first token.

        What changed and why: ``B-03`` shipped this test to pin that a repeat
        issue does not break the *binding* — a re-mint would have left the first
        token bound to an id the cookie no longer held. ``G-4b`` (``04-AUT-007``)
        now also supersedes the browser's earlier live *unclaimed* token at
        issue time, so the binding guard is kept **and** the supersession is
        asserted: the binding is still reused, not re-minted, but the first
        token is no longer redeemable.
        """
        telegram_id = 700000502
        make_user(telegram_id, username="binding_repeat")

        client = Client()
        first_raw = self._issue(client)
        second_raw = self._issue(client)

        def binding_of(raw: str) -> str | None:
            return LoginToken.objects.get(
                token_hash=hashlib.sha256(raw.encode()).hexdigest()
            ).browser_binding

        # B-03's re-mint guard: the binding is reused across issues.
        first_binding = binding_of(first_raw)
        assert first_binding is not None
        assert first_binding == binding_of(second_raw)

        # The bot claims only the second (the first is already superseded and
        # cannot be claimed) ...
        self._claim(second_raw, telegram_id)
        first_hash = hashlib.sha256(first_raw.encode()).hexdigest()
        from apps.users.services.login_token import claim_token

        assert claim_token(first_hash, telegram_id, timezone.now()) is None

        # ... and only the second redeems. The first is GONE (410), not 200.
        assert client.post("/login/status/", {"token": first_raw}).status_code == 410
        assert client.post("/login/status/", {"token": second_raw}).status_code == 200

    def test_repeat_issue_reuses_the_same_browser_binding(self) -> None:
        """One browser → the same stored binding; two browsers → different ones."""
        browser_a = Client()
        first_raw = self._issue(browser_a)
        second_raw = self._issue(browser_a)

        browser_b = Client()
        third_raw = self._issue(browser_b)

        def binding_of(raw: str) -> str | None:
            return LoginToken.objects.get(
                token_hash=hashlib.sha256(raw.encode()).hexdigest()
            ).browser_binding

        first_binding = binding_of(first_raw)
        assert first_binding is not None
        assert first_binding == binding_of(second_raw)
        assert first_binding != binding_of(third_raw)

    def test_an_unbound_row_is_refused(self) -> None:
        """A NULL binding is refused (G-1a fail-closed) and the token is not burned."""
        telegram_id = 700000503
        make_user(telegram_id, username="binding_unbound")

        client = Client()
        raw_token = self._issue(client)
        token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
        self._claim(raw_token, telegram_id)

        # Force the legacy/unbound state back with an UPDATE.
        LoginToken.objects.filter(token_hash=token_hash).update(browser_binding=None)

        response = client.post("/login/status/", {"token": raw_token})
        assert response.status_code == 410
        assert LoginToken.objects.get(token_hash=token_hash).consumed_at is None

    def test_a_malformed_browser_cookie_is_refused(self) -> None:
        """An attacker-shaped cookie is replaced at issue time, never persisted."""
        client = Client()
        client.cookies[LOGIN_BROWSER_ID_COOKIE] = "x" * 500

        response = client.get("/login/issue/")
        assert response.status_code == 200
        raw_token = response.context["raw_token"]

        stored = LoginToken.objects.get(
            token_hash=hashlib.sha256(raw_token.encode()).hexdigest()
        )
        # The malformed value was never persisted; a fresh 22-char id was minted.
        assert stored.browser_binding is not None
        assert len(stored.browser_binding) == 64
        # And the response replaced the attacker cookie with the minted one.
        assert response.cookies[LOGIN_BROWSER_ID_COOKIE].value != "x" * 500

    def test_cookie_name_satisfies_the_host_prefix_contract(self) -> None:
        """If the emitted name carries ``__Host-`` it must also carry ``Secure``.

        ``__Host-`` is the load-bearing part of the bypass fix: without it any
        sibling subdomain can set the binding for a parent domain (RFC 6265
        §5.3) and choose the value on a victim's first login. The prefix is only
        honoured, however, when the same response also carries ``Secure`` and
        ``Path=/`` and no ``Domain`` — a ``__Host-``-prefixed cookie **without**
        ``Secure`` is rejected by every conformant user agent (Chromium 154,
        Firefox, Safari), the cookie is discarded, and every login degrades to a
        ``410``.

        The invariant asserted is the rule, not a fixed flag: **whenever the
        emitted name starts with ``__Host-``, ``morsel["secure"]`` must be
        ``True``**. This test therefore fails on exactly the defect that shipped
        (``__Host-`` + no ``Secure``) and passes on both the secure and
        non-secure configurations. ``Path`` and the absent ``Domain`` are
        structural and asserted unconditionally.

        The name/flag pairing is derived from one setting in the service and
        pinned per settings module by
        ``config.settings.tests.test_settings_defaults``; this test verifies the
        view emits the pair consistently.
        """
        client = Client()
        response = client.get("/login/issue/")
        assert response.status_code == 200

        morsel = response.cookies[LOGIN_BROWSER_ID_COOKIE]
        # Structural: always Path=/ with no Domain, in both configurations.
        assert morsel["path"] == "/"
        assert morsel["domain"] == ""
        # The invariant: __Host- iff Secure. Under test settings the name is
        # plain (no prefix), so Secure is False; this is legal.
        if LOGIN_BROWSER_ID_COOKIE.startswith("__Host-"):
            assert morsel["secure"]
        else:
            assert not morsel["secure"]


class TestLoginStatus:
    """Tests for login_status view (token polling)."""

    def test_login_status_410_no_token(self) -> None:
        """No token parameter returns 410."""
        client = Client()
        response = client.post("/login/status/", {})
        assert response.status_code == 410

    def test_login_status_410_nonexistent_token(self) -> None:
        """A token hash that doesn't exist returns 410."""
        client = Client()
        response = client.post("/login/status/", {"token": "fake_token_32_chars_aaaaaaaaaaaa"})
        assert response.status_code == 410

    def test_login_status_204_pending(self) -> None:
        """An unclaimed token (telegram_id is None) returns 204."""
        client = Client()
        issued = client.get("/login/issue/")
        assert issued.status_code == 200
        raw_token = issued.context["raw_token"]

        response = client.post("/login/status/", {"token": raw_token})
        assert response.status_code == 204

    def test_login_status_410_expired(self) -> None:
        """An expired token returns 410."""
        client = Client()
        issued = client.get("/login/issue/")
        raw_token = issued.context["raw_token"]
        token_hash = hashlib.sha256(raw_token.encode()).hexdigest()

        # Issue through the real path (so the row is bound), then force the
        # precondition back with an UPDATE — this must still prove expiry.
        LoginToken.objects.filter(token_hash=token_hash).update(
            expires_at=timezone.now() - timedelta(minutes=5)
        )

        response = client.post("/login/status/", {"token": raw_token})
        assert response.status_code == 410

    def test_login_status_410_already_consumed(self) -> None:
        """An already-consumed token returns 410."""
        telegram_id = 700000320
        make_user(telegram_id, username="consumed_user")
        client = Client()
        issued = client.get("/login/issue/")
        raw_token = issued.context["raw_token"]
        token_hash = hashlib.sha256(raw_token.encode()).hexdigest()

        LoginToken.objects.filter(token_hash=token_hash).update(
            telegram_id=telegram_id,
            consumed_at=timezone.now(),
        )

        response = client.post("/login/status/", {"token": raw_token})
        assert response.status_code == 410

    def test_login_status_200_claimed_and_user_exists(self) -> None:
        """A claimed token with a matching user returns 200 and establishes session."""
        telegram_id = 700000300
        make_user(telegram_id, username="weblogin_user")

        client = Client()
        issued = client.get("/login/issue/")
        raw_token = issued.context["raw_token"]
        token_hash = hashlib.sha256(raw_token.encode()).hexdigest()

        # The bot's phase-1 claim, performed through the service.
        from apps.users.services.login_token import claim_token

        assert claim_token(token_hash, telegram_id, timezone.now()) is not None

        response = client.post("/login/status/", {"token": raw_token})
        assert response.status_code == 200

        # Verify session was established
        assert client.session.session_key is not None

    def test_login_status_410_user_banned(self) -> None:
        """A claimed token whose user is banned returns 410."""
        telegram_id = 700000301
        User.objects.create(
            telegram_id=telegram_id,
            chat_id=telegram_id,
            username="banned_user",
            is_banned=True,
        )

        client = Client()
        issued = client.get("/login/issue/")
        raw_token = issued.context["raw_token"]
        token_hash = hashlib.sha256(raw_token.encode()).hexdigest()

        from apps.users.services.login_token import claim_token

        assert claim_token(token_hash, telegram_id, timezone.now()) is not None

        response = client.post("/login/status/", {"token": raw_token})
        assert response.status_code == 410

    def test_login_status_refuses_a_disabled_account(self) -> None:
        """An is_active=False user is refused: 410 and no session cookie.

        The token is valid and already claimed, so this exercises exactly the
        guard between the user lookup and the first session write.
        """
        telegram_id = 700000310
        make_user(telegram_id, username="disabled_user", is_active=False)

        client = Client()
        issued = client.get("/login/issue/")
        raw_token = issued.context["raw_token"]
        token_hash = hashlib.sha256(raw_token.encode()).hexdigest()

        from apps.users.services.login_token import claim_token

        assert claim_token(token_hash, telegram_id, timezone.now()) is not None

        response = client.post("/login/status/", {"token": raw_token})

        assert response.status_code == 410
        assert "_auth_user_id" not in client.session

    def test_login_status_burns_the_token_for_a_disabled_account(self) -> None:
        """The denial still consumes the token, matching the ban/decline paths.

        The burn is the intended consequence: the two-phase handshake must
        restart. A replay of the same raw token is refused with 410.
        """
        telegram_id = 700000311
        make_user(telegram_id, username="disabled_burn", is_active=False)

        client = Client()
        issued = client.get("/login/issue/")
        raw_token = issued.context["raw_token"]
        token_hash = hashlib.sha256(raw_token.encode()).hexdigest()

        from apps.users.services.login_token import claim_token

        assert claim_token(token_hash, telegram_id, timezone.now()) is not None

        first = client.post("/login/status/", {"token": raw_token})
        assert first.status_code == 410

        token = LoginToken.objects.get(token_hash=token_hash)
        assert token.consumed_at is not None

        replay = client.post("/login/status/", {"token": raw_token})
        assert replay.status_code == 410

    def test_login_status_200_and_session_for_an_enabled_account(self) -> None:
        """Control: an is_active=True account still gets 200 and a session.

        Anti-over-reach guard — a blanket refusal would pass the disabled-account
        tests but must fail here.
        """
        telegram_id = 700000312
        make_user(telegram_id, username="enabled_user", is_active=True)

        client = Client()
        issued = client.get("/login/issue/")
        raw_token = issued.context["raw_token"]
        token_hash = hashlib.sha256(raw_token.encode()).hexdigest()

        from apps.users.services.login_token import claim_token

        assert claim_token(token_hash, telegram_id, timezone.now()) is not None

        response = client.post("/login/status/", {"token": raw_token})

        assert response.status_code == 200
        assert "_auth_user_id" in client.session

    def test_login_status_405_on_get(self) -> None:
        """GET requests are rejected with 405 (token must come via POST body)."""
        client = Client()
        response = client.get("/login/status/")
        assert response.status_code == 405


# ---------------------------------------------------------------------------
# LoginToken security edge cases (G-06)
# ---------------------------------------------------------------------------


class TestLoginTokenSecurity:
    """Edge-case tests for LoginToken hashing, mismatch rejection, and atomicity."""

    @pytest.fixture(autouse=True)
    def _clear_cache(self):
        """Clear rate-limiter cache between tests."""
        from django.core.cache import cache

        cache.clear()
        yield
        cache.clear()

    def test_token_hash_mismatch_returns_410(self) -> None:
        """Polling with a *different* raw token (wrong hash) returns 410."""
        # Issue a real token (creates a LoginToken row to prove mismatch detection).
        client = Client()
        assert client.get("/login/issue/").status_code == 200

        # Poll with a tampered token — its SHA-256 hash won't match any row.
        wrong_token = "wrong_token_32chars_abcde_abcdefghij"
        response = client.post("/login/status/", {"token": wrong_token})
        assert response.status_code == 410

    @pytest.mark.parametrize("field", ["token_hash"])
    def test_stored_hash_is_sha256_not_raw(self, field: str) -> None:
        """``token_hash`` is always ``sha256(raw)``, never the raw token string."""
        client = Client()
        response = client.get("/login/issue/")
        raw_token: str = response.context["raw_token"]

        expected_hash = hashlib.sha256(raw_token.encode()).hexdigest()
        token = LoginToken.objects.get(token_hash=expected_hash)

        # The stored value must equal the hash, not the raw token.
        assert getattr(token, field) == expected_hash
        assert getattr(token, field) != raw_token

    @pytest.mark.parametrize("raw", ["a" * 32, "z" * 32, "0123456789abcdef" * 2])
    def test_token_hash_length_is_64_hex(self, raw: str) -> None:
        """SHA-256 hex digest is always 64 characters."""
        token_hash = hashlib.sha256(raw.encode()).hexdigest()
        assert len(token_hash) == 64
        assert all(c in "0123456789abcdef" for c in token_hash)

    def test_consumed_token_cannot_be_reused(self) -> None:
        """A consumed token returns 410 on a second poll (claim atomicity)."""
        telegram_id = 700000350
        User.objects.create(
            telegram_id=telegram_id,
            chat_id=telegram_id,
            username="atomic_user",
        )

        client = Client()
        issued = client.get("/login/issue/")
        raw_token = issued.context["raw_token"]
        token_hash = hashlib.sha256(raw_token.encode()).hexdigest()

        from apps.users.services.login_token import claim_token

        assert claim_token(token_hash, telegram_id, timezone.now()) is not None

        # First poll — should consume and return 200.
        first = client.post("/login/status/", {"token": raw_token})
        assert first.status_code == 200

        # Second poll — token is now consumed → 410.
        second = client.post("/login/status/", {"token": raw_token})
        assert second.status_code == 410

    def test_bot_phase_claim_completes_when_user_exists(self) -> None:
        """Phase 1 (bot set telegram_id + created user) → phase 2 (web poll) claims.

        A token with ``telegram_id`` set (and a matching ``User``) but
        ``consumed_at`` NULL is claimed on the first web poll: the response is
        200 and ``consumed_at`` transitions from NULL to set (single-update
        atomicity). This isolates the "telegram_id set, not yet consumed"
        state before asserting the full session-establishment path elsewhere.

        The bot supplies no binding and ``claim_token``'s ``WHERE`` clause does
        not reference one — this test passing is part of the proof that
        ``src/telegram_bot/`` needs no change.
        """
        telegram_id = 700000360
        User.objects.create(
            telegram_id=telegram_id,
            chat_id=telegram_id,
            username="bot_phase_user",
        )

        client = Client()
        issued = client.get("/login/issue/")
        raw_token = issued.context["raw_token"]
        token_hash = hashlib.sha256(raw_token.encode()).hexdigest()

        from apps.users.services.login_token import claim_token

        assert claim_token(token_hash, telegram_id, timezone.now()) is not None

        # Token has telegram_id set but consumed_at is NULL → first poll claims it.
        response = client.post("/login/status/", {"token": raw_token})
        assert response.status_code == 200

        token = LoginToken.objects.get(token_hash=token_hash)
        assert token.consumed_at is not None


# ---------------------------------------------------------------------------
# preferred-city login reconciliation (AC-6 / R-08)
# ---------------------------------------------------------------------------


@pytest.fixture
def podgorica_city() -> City:
    """A valid Montenegro city used as the preferred city."""
    return City.objects.create(
        country_code="ME",
        name="Подгорица",
        region="Central",
        slug="podgorica",
    )


@pytest.fixture
def budva_city() -> City:
    """A second valid Montenegro city for override tests."""
    return City.objects.create(
        country_code="ME",
        name="Будва",
        region="Coastal",
        slug="budva",
    )


def _claim_login(client: Client, user: User, username: str) -> None:
    """Create a claimed login token for *user* and complete the web login.

    Issues through ``/login/issue/`` so the row is bound to the browser id
    cookie the ``client`` fixture now holds, then performs the bot's phase-1
    claim through the service. The three ``TestLoginPreferredCitySync``
    dependents reach this unchanged.
    """
    issued = client.get("/login/issue/")
    raw_token = issued.context["raw_token"]
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()

    from apps.users.services.login_token import claim_token

    assert claim_token(token_hash, user.telegram_id, timezone.now()) is not None

    response = client.post("/login/status/", {"token": raw_token})
    assert response.status_code == 200


class TestLoginPreferredCitySync:
    """Guest -> account preferred-city migration on login (AC-6 / R-08)."""

    @pytest.fixture(autouse=True)
    def _clear_cache(self):
        """Clear rate-limiter cache between tests."""
        from django.core.cache import cache

        cache.clear()
        yield
        cache.clear()

    def test_login_backfills_db_from_cookie(
        self, client: Client, podgorica_city: City
    ) -> None:
        """Guest cookie `podgorica` + NULL DB -> DB backfilled on login (AC-6)."""
        user = User.objects.create(
            telegram_id=700000400,
            chat_id=700000400,
            username="cookie_user",
        )
        client.cookies["preferred_city"] = "podgorica"

        _claim_login(client, user, "cookie_user")

        user.refresh_from_db()
        assert user.preferred_city_id == podgorica_city.id
        # Cookie is retained as the anonymous fallback (R-09 / D-8).
        assert client.cookies["preferred_city"].value == "podgorica"

    def test_login_does_not_overwrite_existing_db_preference(
        self,
        client: Client,
        podgorica_city: City,
        budva_city: City,
    ) -> None:
        """Existing DB preference wins over a conflicting cookie (D-13)."""
        user = User.objects.create(
            telegram_id=700000401,
            chat_id=700000401,
            username="existing_pref",
            preferred_city=podgorica_city,
        )
        client.cookies["preferred_city"] = "budva"

        _claim_login(client, user, "existing_pref")

        user.refresh_from_db()
        # DB value is Podgorica (not overwritten by the budva cookie).
        assert user.preferred_city_id == podgorica_city.id

    def test_login_without_cookie_does_not_crash(
        self, client: Client, podgorica_city: City
    ) -> None:
        """No preferred_city cookie -> no exception, no DB change."""
        user = User.objects.create(
            telegram_id=700000402,
            chat_id=700000402,
            username="no_cookie_user",
        )

        _claim_login(client, user, "no_cookie_user")

        user.refresh_from_db()
        assert user.preferred_city_id is None

    def test_reconcile_does_not_backfill_for_declined_user(
        self, podgorica_city: City
    ) -> None:
        """The reconcile returns early for a declined user (06-PII-110).

        A declined user's column was cleared on decline and a surviving cookie
        must not re-derive it. ``can_login`` refuses a declined user before the
        reconcile is reached on the HTTP path, so this drives the reconcile
        helper directly — the unit whose early return is the guard.
        """
        from django.test import RequestFactory

        from apps.users.views.consent import _reconcile_preferred_city_on_login

        user = User.objects.create(
            telegram_id=700000410,
            chat_id=700000410,
            username="declined_pref",
            is_declined=True,
        )
        request = RequestFactory().get("/")
        request.COOKIES["preferred_city"] = "podgorica"

        _reconcile_preferred_city_on_login(request, user)

        user.refresh_from_db()
        assert user.preferred_city_id is None

    def test_reconcile_backfills_for_non_declined_user(
        self, podgorica_city: City
    ) -> None:
        """Control: a non-declined user's NULL column is still backfilled."""
        from django.test import RequestFactory

        from apps.users.views.consent import _reconcile_preferred_city_on_login

        user = User.objects.create(
            telegram_id=700000411,
            chat_id=700000411,
            username="active_pref",
        )
        request = RequestFactory().get("/")
        request.COOKIES["preferred_city"] = "podgorica"

        _reconcile_preferred_city_on_login(request, user)

        user.refresh_from_db()
        assert user.preferred_city_id == podgorica_city.id


# ---------------------------------------------------------------------------
# login_rate_limit_check (04-AUT-003 rate-limit contract)
# ---------------------------------------------------------------------------


class TestLoginRateLimitCheck:
    """login_rate_limit_check enforces 10 requests / 60s / IP.

    Uses the atomic ``cache.add`` (first hit) → ``cache.incr`` (subsequent)
    pattern so the counter is initialised at 1 and incremented per request.
    """

    def test_login_rate_limit_check(self) -> None:
        """First 10 calls return True; the 11th is throttled (False).

        Proves the add→incr pattern: the cache key holds the incremented
        counter (1 init + 10 subsequent + the throttled 11th == 11).
        """
        from django.core.cache import cache
        from django.http import HttpRequest

        from apps.users.services.login_rate_limit import (
            RATE_LIMIT_REQUESTS,
            login_rate_limit_check,
        )

        request = HttpRequest()
        request.META = {"REMOTE_ADDR": "127.0.0.1"}

        # Calls 1-10: cache.add creates the key (value=1) on the first hit,
        # then cache.incr advances it to 10 — each <= RATE_LIMIT_REQUESTS.
        for _ in range(RATE_LIMIT_REQUESTS):
            assert login_rate_limit_check(request) is True

        # Call 11: cache.incr advances the counter to 11 > 10 → throttled.
        assert login_rate_limit_check(request) is False

        # Counter reflects 11 increments: 1 (init) + 10 + the throttled attempt.
        assert cache.get("login_rl:127.0.0.1") == RATE_LIMIT_REQUESTS + 1

    def test_login_rate_limit_check_handles_cache_incr_value_error(self) -> None:
        """ValueError from cache.incr (race: key expired between add/incr) →
        counter reset to 1, returns True (graceful degradation)."""
        from unittest.mock import patch

        from django.core.cache import cache
        from django.http import HttpRequest

        from apps.users.services.login_rate_limit import login_rate_limit_check

        cache.clear()
        request = HttpRequest()
        request.META = {"REMOTE_ADDR": "127.0.0.1"}

        # First call: cache.add succeeds (creates key, value=1)
        assert login_rate_limit_check(request) is True

        # Second call: cache.add fails (key exists), cache.incr raises ValueError
        # (simulating the key expiring between add and incr)
        with patch(
            "apps.users.services.login_rate_limit.cache.incr",
            side_effect=ValueError("missing key"),
        ):
            result = login_rate_limit_check(request)

        assert result is True
        # Counter was reset to 1 by the except ValueError branch
        assert cache.get("login_rl:127.0.0.1") == 1
