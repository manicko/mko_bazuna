"""
Tests for claim_login_token — atomic token claim against real ORM.

Verifies that ``handle_login_orm`` atomically claims a LoginToken,
rejects expired/already-claimed tokens, and creates-or-retrieves the
User. These tests exercise the INSERT-time triggers and the
UPDATE…RETURNING pattern that protects against TOCTOU races.
"""

import hashlib
from collections.abc import Callable
from typing import Any

import pytest
from asgiref.sync import sync_to_async
from django.utils import timezone

pytestmark = pytest.mark.django_db(transaction=True)


class TestClaimLoginToken:
    """Atomic token claim via handle_login_orm."""

    @pytest.mark.asyncio
    async def test_claim_valid_token(
        self,
        login_token_factory: Callable[..., tuple[str, Any]],
    ) -> None:
        """A valid unclaimed token is claimed and user is created."""
        from telegram_bot.handlers.login import handle_login_orm

        raw_token, _ = login_token_factory()
        token_hash = hashlib.sha256(raw_token.encode()).hexdigest()

        result_token, result_user, created = await handle_login_orm(
            token_hash=token_hash,
            telegram_id=900000200,
            username="new_user",
            first_name="New",
            last_name="User",
        )

        assert result_token is not None
        assert result_token.telegram_id == 900000200
        assert result_token.consumed_at is None  # consumed_at is set by web, not bot
        assert result_user is not None
        assert result_user.telegram_id == 900000200
        assert created is True

    @pytest.mark.asyncio
    async def test_claim_sets_telegram_id_on_token(
        self,
        login_token_factory: Callable[..., tuple[str, Any]],
    ) -> None:
        """Claiming a token sets telegram_id on the LoginToken row."""
        from telegram_bot.handlers.login import handle_login_orm

        raw_token, token = login_token_factory()
        token_hash = hashlib.sha256(raw_token.encode()).hexdigest()

        await handle_login_orm(
            token_hash=token_hash,
            telegram_id=900000201,
            username="user2",
            first_name="User",
            last_name="Two",
        )

        # Refresh from DB to verify the claim
        get_token = sync_to_async(type(token).objects.get)
        refreshed = await get_token(id=token.id)
        assert refreshed.telegram_id == 900000201

    @pytest.mark.asyncio
    async def test_reject_expired_token(
        self,
        login_token_factory: Callable[..., tuple[str, Any]],
    ) -> None:
        """An expired token is rejected (returns None)."""
        from telegram_bot.handlers.login import handle_login_orm
        from apps.users.models import LoginToken

        # Create an expired token directly
        raw_token = "expired_token_string_32chars_abcdefghij"
        token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
        create_token = sync_to_async(LoginToken.objects.create)
        await create_token(
            token_hash=token_hash,
            expires_at=timezone.now() - timezone.timedelta(hours=1),
        )

        result_token, result_user, created = await handle_login_orm(
            token_hash=token_hash,
            telegram_id=900000202,
            username="user3",
            first_name="User",
            last_name="Three",
        )

        assert result_token is None
        assert result_user is None
        assert created is False

    @pytest.mark.asyncio
    async def test_reject_already_claimed_token(
        self,
        login_token_factory: Callable[..., tuple[str, Any]],
    ) -> None:
        """An already-claimed token is rejected (returns None)."""
        from telegram_bot.handlers.login import handle_login_orm
        from apps.users.models import LoginToken

        # Create a token that is already claimed
        raw_token = "claimed_token_32chars_abcdefghijklmn"
        token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
        create_token = sync_to_async(LoginToken.objects.create)
        await create_token(
            token_hash=token_hash,
            telegram_id=999999999,  # Already claimed by another user
            expires_at=timezone.now() + timezone.timedelta(hours=1),
        )

        result_token, result_user, created = await handle_login_orm(
            token_hash=token_hash,
            telegram_id=900000203,
            username="user4",
            first_name="User",
            last_name="Four",
        )

        assert result_token is None
        assert result_user is None
        assert created is False

    @pytest.mark.asyncio
    async def test_creates_user_on_first_claim(
        self,
        login_token_factory: Callable[..., tuple[str, Any]],
    ) -> None:
        """First claim creates a new User record."""
        from telegram_bot.handlers.login import handle_login_orm

        raw_token, _ = login_token_factory()
        token_hash = hashlib.sha256(raw_token.encode()).hexdigest()

        _, result_user, created = await handle_login_orm(
            token_hash=token_hash,
            telegram_id=900000204,
            username="fresh_user",
            first_name="Fresh",
            last_name="User",
        )

        assert result_user is not None
        assert created is True
        assert result_user.telegram_id == 900000204
        assert result_user.username == "fresh_user"

    @pytest.mark.asyncio
    async def test_returns_existing_user_on_second_login(
        self,
        login_token_factory: Callable[..., tuple[str, Any]],
    ) -> None:
        """A second login with the same telegram_id returns the existing user."""
        from telegram_bot.handlers.login import handle_login_orm
        from apps.users.models import User

        telegram_id = 900000205

        # Create user first
        create_user = sync_to_async(User.objects.create)
        existing = await create_user(
            telegram_id=telegram_id,
            chat_id=telegram_id,
            username="existing_user",
        )

        # Create a fresh token for this user
        raw_token, _ = login_token_factory()
        token_hash = hashlib.sha256(raw_token.encode()).hexdigest()

        _, result_user, created = await handle_login_orm(
            token_hash=token_hash,
            telegram_id=telegram_id,
            username="existing_user",
            first_name="Existing",
            last_name="User",
        )

        assert result_user is not None
        assert result_user.id == existing.id
        assert created is False

    @pytest.mark.asyncio
    async def test_invalid_token_hash_returns_none(self) -> None:
        """A non-existent token hash returns None."""
        from telegram_bot.handlers.login import handle_login_orm

        result_token, result_user, created = await handle_login_orm(
            token_hash="a" * 64,  # Valid SHA-256 hex digest but no matching token
            telegram_id=900000206,
            username="ghost",
            first_name="Ghost",
            last_name="User",
        )

        assert result_token is None
        assert result_user is None
        assert created is False