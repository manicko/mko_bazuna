"""
Tests for web login views (login_issue, login_status) — AUT-009.

Covers:
- login_issue: 200 response, token hash stored as SHA-256, 5-min expiry, raw_token in context, rate limiting
- login_status: 200 (claimed), 204 (pending), 410 (expired/consumed/nonexistent/banned)
- Session establishment on successful login
"""

import hashlib
from datetime import timedelta

import pytest
from apps.locations.models import City
from apps.users.models import LoginToken, User
from django.test import Client
from django.utils import timezone

pytestmark = [pytest.mark.django_db, pytest.mark.slow, pytest.mark.integration]


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
        """login_issue returns 200 and renders the Telegram deep-link."""
        client = Client()
        response = client.get("/login/issue/")

        assert response.status_code == 200
        content = response.content.decode()
        assert "t.me" in content
        assert "start=login_" in content

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


class TestLoginStatus:
    """Tests for login_status view (token polling)."""

    def test_login_status_410_no_token(self) -> None:
        """No token parameter returns 410."""
        client = Client()
        response = client.get("/login/status/")
        assert response.status_code == 410

    def test_login_status_410_nonexistent_token(self) -> None:
        """A token hash that doesn't exist returns 410."""
        client = Client()
        response = client.get("/login/status/?token=fake_token_32_chars_aaaaaaaaaaaa")
        assert response.status_code == 410

    def test_login_status_204_pending(self) -> None:
        """An unclaimed token (telegram_id is None) returns 204."""
        raw_token = "pending_token_32chars_abcde_abcdefghij"
        token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
        LoginToken.objects.create(
            token_hash=token_hash,
            expires_at=timezone.now() + timedelta(hours=1),
        )

        client = Client()
        response = client.get(f"/login/status/?token={raw_token}")
        assert response.status_code == 204

    def test_login_status_410_expired(self) -> None:
        """An expired token returns 410."""
        raw_token = "expired_token_32chars_abcde_abcdefghij"
        token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
        LoginToken.objects.create(
            token_hash=token_hash,
            expires_at=timezone.now() - timedelta(minutes=5),
        )

        client = Client()
        response = client.get(f"/login/status/?token={raw_token}")
        assert response.status_code == 410

    def test_login_status_410_already_consumed(self) -> None:
        """An already-consumed token returns 410."""
        raw_token = "consumed_token_32chars_abcde_abcdefghij"
        token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
        LoginToken.objects.create(
            token_hash=token_hash,
            telegram_id=123456,
            expires_at=timezone.now() + timedelta(hours=1),
            consumed_at=timezone.now(),
        )

        client = Client()
        response = client.get(f"/login/status/?token={raw_token}")
        assert response.status_code == 410

    def test_login_status_200_claimed_and_user_exists(self) -> None:
        """A claimed token with a matching user returns 200 and establishes session."""
        telegram_id = 700000300
        User.objects.create(
            telegram_id=telegram_id,
            chat_id=telegram_id,
            username="weblogin_user",
        )

        raw_token = "claimed_token_32chars_abcde_abcdefghij"
        token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
        LoginToken.objects.create(
            token_hash=token_hash,
            telegram_id=telegram_id,
            expires_at=timezone.now() + timedelta(hours=1),
        )

        client = Client()
        response = client.get(f"/login/status/?token={raw_token}")
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

        raw_token = "banned_token_32chars_abcde_abcdefghij"
        token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
        LoginToken.objects.create(
            token_hash=token_hash,
            telegram_id=telegram_id,
            expires_at=timezone.now() + timedelta(hours=1),
        )

        client = Client()
        response = client.get(f"/login/status/?token={raw_token}")
        assert response.status_code == 410


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
        response = client.get(f"/login/status/?token={wrong_token}")
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

        raw_token = "atomic_token_32chars_abcde_abcdefghij"
        token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
        LoginToken.objects.create(
            token_hash=token_hash,
            telegram_id=telegram_id,
            expires_at=timezone.now() + timedelta(hours=1),
        )

        client = Client()
        # First poll — should consume and return 200.
        first = client.get(f"/login/status/?token={raw_token}")
        assert first.status_code == 200

        # Second poll — token is now consumed → 410.
        second = client.get(f"/login/status/?token={raw_token}")
        assert second.status_code == 410

    def test_bot_phase_claim_completes_when_user_exists(self) -> None:
        """Phase 1 (bot set telegram_id + created user) → phase 2 (web poll) claims.

        A token with ``telegram_id`` set (and a matching ``User``) but
        ``consumed_at`` NULL is claimed on the first web poll: the response is
        200 and ``consumed_at`` transitions from NULL to set (single-update
        atomicity). This isolates the "telegram_id set, not yet consumed"
        state before asserting the full session-establishment path elsewhere.
        """
        telegram_id = 700000360
        User.objects.create(
            telegram_id=telegram_id,
            chat_id=telegram_id,
            username="bot_phase_user",
        )

        raw_token = "bot_phase_32chars_abcde_abcdefghij"
        token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
        LoginToken.objects.create(
            token_hash=token_hash,
            telegram_id=telegram_id,
            expires_at=timezone.now() + timedelta(hours=1),
        )

        # Token has telegram_id set but consumed_at is NULL → first poll claims it.
        client = Client()
        response = client.get(f"/login/status/?token={raw_token}")
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
    """Create a claimed login token for *user* and complete the web login."""
    raw_token = f"{username}_32chars_abcde_abcdefghij"
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    LoginToken.objects.create(
        token_hash=token_hash,
        telegram_id=user.telegram_id,
        expires_at=timezone.now() + timedelta(hours=1),
    )
    response = client.get(f"/login/status/?token={raw_token}")
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
