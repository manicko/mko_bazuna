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
