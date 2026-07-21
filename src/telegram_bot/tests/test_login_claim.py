"""
Tests for login-token atomic claim (replay/expiry/used).

Verifies that handle_login_orm enforces single-use, expiry, and replay
protection at the ORM level against the real PostgreSQL database.
"""

import hashlib

import pytest
from apps.users.models import LoginToken
from django.utils import timezone
from telegram_bot.handlers.login import handle_login_orm

pytestmark = [pytest.mark.django_db, pytest.mark.slow, pytest.mark.integration]


@pytest.fixture
def telegram_id() -> int:
    """Unique Telegram user ID for each test."""
    return 900000100


@pytest.fixture
def token_hash() -> str:
    """SHA-256 hash of a raw 32-char token."""
    raw = "a" * 32
    return hashlib.sha256(raw.encode()).hexdigest()


@pytest.fixture
def future_token(token_hash: str) -> LoginToken:
    """Create an unclaimed, unexpired LoginToken."""
    return LoginToken.objects.create(
        token_hash=token_hash,
        telegram_id=None,
        consumed_at=None,
        expires_at=timezone.now() + timezone.timedelta(minutes=5),
    )


@pytest.fixture
def expired_token(token_hash: str) -> LoginToken:
    """Create an unclaimed, expired LoginToken."""
    return LoginToken.objects.create(
        token_hash=token_hash,
        telegram_id=None,
        consumed_at=None,
        expires_at=timezone.now() - timezone.timedelta(minutes=1),
    )


@pytest.fixture
def claimed_token(token_hash: str) -> LoginToken:
    """Create a LoginToken already claimed by the bot (telegram_id set)."""
    return LoginToken.objects.create(
        token_hash=token_hash,
        telegram_id=900000200,
        consumed_at=None,
        expires_at=timezone.now() + timezone.timedelta(minutes=5),
    )


@pytest.fixture
def consumed_token(token_hash: str) -> LoginToken:
    """Create a LoginToken already consumed by the web (consumed_at set)."""
    now = timezone.now()
    return LoginToken.objects.create(
        token_hash=token_hash,
        telegram_id=900000300,
        consumed_at=now,
        expires_at=now + timezone.timedelta(minutes=5),
    )


class TestClaimLoginToken:
    """Tests for login-token atomic claim via handle_login_orm."""

    async def test_fresh_unclaimed_token(self, token_hash: str, telegram_id: int) -> None:
        """Fresh unclaimed+unexpired token is claimed successfully."""
        # Arrange: create token
        LoginToken.objects.create(
            token_hash=token_hash,
            telegram_id=None,
            consumed_at=None,
            expires_at=timezone.now() + timezone.timedelta(minutes=5),
        )

        # Act
        login_token, user, created = await handle_login_orm(
            token_hash=token_hash,
            telegram_id=telegram_id,
            username="test_user",
            first_name="Test",
            last_name="User",
        )

        # Assert
        assert login_token is not None, "Token should be claimed"
        assert login_token.telegram_id == telegram_id, "telegram_id should be set"
        assert login_token.consumed_at is None, "consumed_at should remain None (web phase)"
        assert user is not None, "User should be created or found"
        assert user.chat_id == telegram_id, "User should have correct chat_id"

    async def test_reclaim_blocked(self, token_hash: str, telegram_id: int) -> None:
        """Re-claim of the same token returns None (replay blocked)."""
        # Arrange: create token
        LoginToken.objects.create(
            token_hash=token_hash,
            telegram_id=None,
            consumed_at=None,
            expires_at=timezone.now() + timezone.timedelta(minutes=5),
        )

        # First claim succeeds
        first_claim, _, _ = await handle_login_orm(
            token_hash=token_hash,
            telegram_id=telegram_id,
            username="test_user",
            first_name="Test",
            last_name="User",
        )
        assert first_claim is not None, "First claim should succeed"

        # Act: second claim with same token_hash
        second_claim, _, _ = await handle_login_orm(
            token_hash=token_hash,
            telegram_id=telegram_id + 1,
            username="other_user",
            first_name="Other",
            last_name="User",
        )

        # Assert
        assert second_claim is None, "Re-claim should be blocked"

    async def test_expired_token_rejected(self, token_hash: str, telegram_id: int) -> None:
        """Expired token returns None."""
        # Arrange: create expired token
        LoginToken.objects.create(
            token_hash=token_hash,
            telegram_id=None,
            consumed_at=None,
            expires_at=timezone.now() - timezone.timedelta(minutes=1),
        )

        # Act
        login_token, _, _ = await handle_login_orm(
            token_hash=token_hash,
            telegram_id=telegram_id,
            username="test_user",
            first_name="Test",
            last_name="User",
        )

        # Assert
        assert login_token is None, "Expired token should not be claimable"

    async def test_claimed_token_rejected(self, token_hash: str, telegram_id: int) -> None:
        """Token already claimed by bot (telegram_id set) returns None."""
        # Arrange: create token claimed by another user
        LoginToken.objects.create(
            token_hash=token_hash,
            telegram_id=900000200,
            consumed_at=None,
            expires_at=timezone.now() + timezone.timedelta(minutes=5),
        )

        # Act
        login_token, _, _ = await handle_login_orm(
            token_hash=token_hash,
            telegram_id=telegram_id,
            username="test_user",
            first_name="Test",
            last_name="User",
        )

        # Assert
        assert login_token is None, "Already-claimed token should not be claimable"

    async def test_consumed_token_rejected(self, token_hash: str, telegram_id: int) -> None:
        """Token already consumed by web (consumed_at set) returns None."""
        # Arrange: create consumed token
        now = timezone.now()
        LoginToken.objects.create(
            token_hash=token_hash,
            telegram_id=900000300,
            consumed_at=now,
            expires_at=now + timezone.timedelta(minutes=5),
        )

        # Act
        login_token, _, _ = await handle_login_orm(
            token_hash=token_hash,
            telegram_id=telegram_id,
            username="test_user",
            first_name="Test",
            last_name="User",
        )

        # Assert
        assert login_token is None, "Consumed token should not be claimable"