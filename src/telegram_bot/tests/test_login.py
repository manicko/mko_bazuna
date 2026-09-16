"""
Tests for the Telegram bot login flow (deep-link authentication).

Covers the atomic login-token claim implemented in
``telegram_bot/handlers.login.handle_login_orm`` against the real PostgreSQL
ORM. The claim is a single-statement ``UPDATE ... RETURNING`` guarded by
``telegram_id IS NULL AND consumed_at IS NULL AND expires_at > now``; these
tests pin that contract:

- a fresh, unexpired, un-consumed token is claimed and a new user is created;
- claiming writes ``telegram_id`` onto the ``LoginToken`` row (persisted);
- a repeat login for an existing ``chat_id`` retrieves rather than creates;
- the token is single-use: a second claim of the same hash is blocked;
- expired, web-consumed, and unknown token hashes are all rejected.

This file consolidates the previously duplicated ``test_claim_login_token.py``
and ``test_login_claim.py`` into a single coherent suite.
"""

import asyncio
import hashlib
from collections.abc import Awaitable, Callable, Iterator
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from asgiref.sync import sync_to_async
from django.core.cache import cache
from django.utils import timezone

from apps.users.models import LoginToken
from telegram_bot.services.rate_limit import (
    LOGIN_RATE_LIMIT_REQUESTS,
    check_login_rate_limit,
)

pytestmark = [
    pytest.mark.django_db(transaction=True),
    pytest.mark.slow,
    pytest.mark.integration,
    pytest.mark.concurrent,
]
pytestmark.append(pytest.mark.xdist_group("bot_concurrent"))

# 32-char token matching LOGIN_PATTERN, used across login rate-limit tests.
CONSENT_TEST_RAW_TOKEN = "abcdefghijklmnopqrstuvwxyz012345"


def _mock_login_message(raw_token: str, user_id: int = 900000200) -> MagicMock:
    """Build a ``Message`` double for ``handle_login_deep_link`` with a login deep-link."""
    message = MagicMock()
    message.text = f"/start login_{raw_token}"
    message.from_user = MagicMock()
    message.from_user.id = user_id
    message.from_user.username = "test_user"
    message.from_user.first_name = "Test"
    message.from_user.last_name = "User"
    message.answer = AsyncMock()
    return message


def _mock_state() -> AsyncMock:
    """Build an ``FSMContext`` double with an async ``update_data``."""
    state = AsyncMock()
    state.update_data = AsyncMock()
    return state


# ---------------------------------------------------------------------------
# Success path
# ---------------------------------------------------------------------------


class TestClaimLoginToken:
    """Atomic claim + user create/retrieve via ``handle_login_orm``."""

    @pytest.mark.asyncio
    async def test_claim_valid_token(
        self,
        login_token_factory: Callable[..., Awaitable[tuple[str, Any]]],
    ) -> None:
        """A fresh, unexpired, un-consumed token is claimed and a new user is created.

        Verifies the full success path: the returned token has ``telegram_id``
        set and ``consumed_at`` still ``None`` (the web phase consumes it
        later), the claim is persisted to the ``LoginToken`` DB row, and the
        user is created with the supplied profile fields and ``created=True``.
        """
        from telegram_bot.handlers.login import handle_login_orm

        # Arrange: a fresh, unclaimed token
        _raw_token, token = await login_token_factory()
        token_hash = token.token_hash
        telegram_id = 900000200

        # Act
        login_token, user, created = await handle_login_orm(
            token_hash=token_hash,
            telegram_id=telegram_id,
            username="new_user",
            first_name="New",
            last_name="User",
        )

        # Assert: claim result
        assert login_token is not None
        assert login_token.telegram_id == telegram_id
        assert login_token.consumed_at is None  # set by the web phase, not the bot

        # Assert: claim persisted to the DB row
        refreshed = await sync_to_async(LoginToken.objects.get)(id=token.id)
        assert refreshed.telegram_id == telegram_id

        # Assert: user created with the expected fields
        assert user is not None
        assert user.telegram_id == telegram_id
        assert user.chat_id == telegram_id
        assert user.username == "new_user"
        assert user.first_name == "New"
        assert user.last_name == "User"
        assert created is True

    @pytest.mark.asyncio
    async def test_returns_existing_user_on_second_login(
        self,
        login_token_factory: Callable[..., Awaitable[tuple[str, Any]]],
    ) -> None:
        """A repeat login for an existing chat_id retrieves (not creates) the user.

        ``handle_login_orm`` keys user lookup on the stable ``chat_id`` so that
        a user who already exists is returned with ``created=False``.
        """
        from apps.users.models import User
        from telegram_bot.handlers.login import handle_login_orm

        telegram_id = 900000205

        # Arrange: pre-existing user with this chat_id
        existing = await sync_to_async(User.objects.create)(
            telegram_id=telegram_id,
            chat_id=telegram_id,
            username="existing_user",
        )

        _raw_token, token = await login_token_factory()
        token_hash = token.token_hash

        # Act
        login_token, user, created = await handle_login_orm(
            token_hash=token_hash,
            telegram_id=telegram_id,
            username="existing_user",
            first_name="Existing",
            last_name="User",
        )

        # Assert
        assert login_token is not None
        assert user is not None
        assert user.id == existing.id
        assert created is False

    @pytest.mark.asyncio
    async def test_reclaim_blocked(
        self,
        login_token_factory: Callable[..., Awaitable[tuple[str, Any]]],
    ) -> None:
        """A token cannot be claimed twice (single-use / replay protection).

        The first claim succeeds and stamps ``telegram_id``; the same hash can
        no longer match the ``WHERE telegram_id IS NULL`` guard, so a second
        claim (even by a different user) returns ``None``.
        """
        from telegram_bot.handlers.login import handle_login_orm

        # Arrange: one fresh token
        _raw_token, token = await login_token_factory()
        token_hash = token.token_hash
        first_user = 900000300
        second_user = 900000301

        # Act: first claim succeeds
        first_claim, _, _ = await handle_login_orm(
            token_hash=token_hash,
            telegram_id=first_user,
            username="first_user",
            first_name="First",
            last_name="User",
        )
        assert first_claim is not None, "First claim should succeed"

        # Act: second claim of the same hash by a different user
        second_claim, _, _ = await handle_login_orm(
            token_hash=token_hash,
            telegram_id=second_user,
            username="second_user",
            first_name="Second",
            last_name="User",
        )

        # Assert
        assert second_claim is None, "Re-claim of a claimed token must be blocked"

    @pytest.mark.asyncio
    async def test_token_unclaimed_on_get_or_create_failure(
        self,
        login_token_factory: Callable[..., Awaitable[tuple[str, Any]]],
    ) -> None:
        """If get_or_create raises a non-IntegrityError, the token claim rolls back.

        After the DB-004 fix, the token claim and user get/create share a single
        outer ``transaction.atomic()``. A ``RuntimeError`` (not ``IntegrityError``)
        from ``get_or_create`` escapes the inner SAVEPOINT, propagates through the
        outer ``atomic()`` (triggering ``ROLLBACK``), and the token reverts to its
        unclaimed state — preventing a user lockout. Before the fix, the token
        would remain claimed with no user created.
        """
        from apps.users.models import User
        from telegram_bot.handlers.login import handle_login_orm

        # Arrange
        _raw_token, token = await login_token_factory()
        token_hash = token.token_hash
        telegram_id = 900000310

        # Act + Assert: RuntimeError from get_or_create propagates, rolling back
        # the outer transaction (including the token claim).
        with patch.object(
            User.objects, "get_or_create", side_effect=RuntimeError("boom")
        ):
            with pytest.raises(RuntimeError, match="boom"):
                await handle_login_orm(
                    token_hash=token_hash,
                    telegram_id=telegram_id,
                    username="race_user",
                    first_name="Race",
                    last_name="User",
                )

        # Assert: the token was rolled back — telegram_id and consumed_at are None
        refreshed = await sync_to_async(LoginToken.objects.get)(id=token.id)
        assert refreshed.telegram_id is None
        assert refreshed.consumed_at is None


# ---------------------------------------------------------------------------
# Rejection path
# ---------------------------------------------------------------------------


class TestTokenRejection:
    """handle_login_orm rejects tokens that cannot be claimed."""

    @pytest.mark.asyncio
    async def test_reject_expired_token(self) -> None:
        """An expired token (``expires_at`` in the past) is not claimable."""
        from telegram_bot.handlers.login import handle_login_orm

        raw_token = "expired_token_string_32chars_abcdefghij"
        token_hash = hashlib.sha256(raw_token.encode()).hexdigest()

        # Arrange: expired token
        await sync_to_async(LoginToken.objects.create)(
            token_hash=token_hash,
            expires_at=timezone.now() - timezone.timedelta(hours=1),
        )

        # Act
        login_token, user, created = await handle_login_orm(
            token_hash=token_hash,
            telegram_id=900000400,
            username="user3",
            first_name="User",
            last_name="Three",
        )

        # Assert
        assert login_token is None
        assert user is None
        assert created is False

    @pytest.mark.asyncio
    async def test_reject_consumed_token(self) -> None:
        """A token already consumed by the web (``consumed_at`` set) is rejected.

        The web phase marks a token consumed after it has been redeemed; the bot
        must not re-claim it.
        """
        from telegram_bot.handlers.login import handle_login_orm

        raw_token = "consumed_token_string_32chars_abcdefghij"
        token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
        now = timezone.now()

        # Arrange: token claimed + consumed on the web side
        await sync_to_async(LoginToken.objects.create)(
            token_hash=token_hash,
            telegram_id=900000501,
            consumed_at=now,
            expires_at=now + timezone.timedelta(hours=1),
        )

        # Act
        login_token, user, created = await handle_login_orm(
            token_hash=token_hash,
            telegram_id=900000500,
            username="user6",
            first_name="User",
            last_name="Six",
        )

        # Assert
        assert login_token is None
        assert user is None
        assert created is False

    @pytest.mark.asyncio
    async def test_invalid_token_hash_returns_none(self) -> None:
        """A token hash that matches no ``LoginToken`` row is not claimable."""
        from telegram_bot.handlers.login import handle_login_orm

        # Act
        login_token, user, created = await handle_login_orm(
            token_hash="a" * 64,  # valid-looking SHA-256 hex, no matching row
            telegram_id=900000600,
            username="ghost",
            first_name="Ghost",
            last_name="User",
        )

        # Assert
        assert login_token is None
        assert user is None
        assert created is False


# ---------------------------------------------------------------------------
# Concurrent claim race
# ---------------------------------------------------------------------------


class TestConcurrentClaim:
    """Concurrent claim of a single shared ``LoginToken`` via ``asyncio.gather``.

    Reproduces the race condition described in audit finding TST-005: when
    multiple concurrent claims arrive against a single unclaimed token, only
    ONE must succeed (the token transitions to the claimed state) and the
    remaining N-1 must fail gracefully without crashing.

    ``handle_login_orm`` is async, so concurrency is achieved with
    ``asyncio.gather`` â€” not threading â€” scheduling N coroutines that each
    invoke the atomic ``UPDATE â€¦ RETURNING`` claim. The ``WHERE`` guard
    (``telegram_id IS NULL AND consumed_at IS NULL AND expires_at > now``)
    combined with PostgreSQL's row-level lock on the matched row guarantees
    that only the first claimer to win the lock stamps its ``telegram_id``;
    all others match zero rows and return ``None``.
    """

    @pytest.mark.asyncio
    async def test_concurrent_login_token_race(
        self,
        login_token_factory: Callable[..., Awaitable[tuple[str, Any]]],
    ) -> None:
        """N concurrent claims against one shared token â†’ exactly 1 winner.

        Fires ``num_claimers`` simultaneous ``handle_login_orm`` calls via
        ``asyncio.gather``. The atomic ``UPDATE â€¦ RETURNING`` claim ensures
        only the first claimer to acquire the row lock succeeds; the rest
        return ``None`` gracefully.
        """
        from telegram_bot.handlers.login import handle_login_orm

        # Arrange: a single, unclaimed token shared by all claimers
        _raw_token, token = await login_token_factory()
        token_hash = token.token_hash

        num_claimers = 5

        # Act: fire N concurrent claims against the same token hash.
        # Each claimer uses a distinct telegram_id so successful user creation
        # never collides on the unique chat_id column.
        results = await asyncio.gather(
            *[
                handle_login_orm(
                    token_hash=token_hash,
                    telegram_id=900000300 + i,
                    username=f"concurrent_{i}",
                    first_name=f"Concurrent{i}",
                    last_name="User",
                )
                for i in range(num_claimers)
            ]
        )

        # Assert: exactly one claim succeeded; the rest failed gracefully
        successes = [r for r in results if r[0] is not None]
        failures = [r for r in results if r[0] is None]

        assert len(successes) == 1, (
            f"Expected exactly 1 successful claim, got {len(successes)}"
        )
        assert len(failures) == num_claimers - 1, (
            f"Expected {num_claimers - 1} failed claims, got {len(failures)}"
        )

        # Assert: the winner stamped its telegram_id onto the token and
        # created a user
        winner_token, winner_user, winner_created = successes[0]
        assert winner_token is not None
        assert winner_token.telegram_id is not None
        assert winner_user is not None
        assert winner_created is True

        # Assert: the token row is now claimed (persisted to the DB)
        refreshed = await sync_to_async(LoginToken.objects.get)(id=token.id)
        assert refreshed.telegram_id == winner_token.telegram_id

        # Assert: failed claims returned gracefully (no crash, no side effects)
        for login_token, user, created in failures:
            assert login_token is None
            assert user is None
            assert created is False


# ---------------------------------------------------------------------------
# Login rate-limit integration tests (EXT-007)
# ---------------------------------------------------------------------------


class TestLoginRateLimit:
    """Integration tests for the per-user login rate limit in ``handle_login_deep_link``."""

    @pytest.fixture(autouse=True)
    def _clear_cache(self) -> Iterator[None]:
        """Clear the shared LocMemCache so rate-limit counters don't leak across tests."""
        cache.clear()
        yield
        cache.clear()

    @pytest.mark.asyncio
    async def test_login_rate_limit_allows_single_claim(
        self,
        login_token_factory: Callable[..., Awaitable[tuple[str, Any]]],
    ) -> None:
        """A single login claim within the budget is not blocked.

        Verifies the happy path: the rate-limit check passes, the token is
        claimed, the user is created, and the success message (not the cooldown)
        is sent.
        """
        from telegram_bot.handlers.login import handle_login_deep_link

        raw_token, _token = await login_token_factory(
            raw_token=CONSENT_TEST_RAW_TOKEN
        )

        message = _mock_login_message(raw_token, user_id=900000200)
        await handle_login_deep_link(
            message=message, bot=MagicMock(), state=_mock_state()
        )

        # Not rate-limited — received the success message, not the cooldown.
        message.answer.assert_awaited_once()
        sent_text = message.answer.await_args.args[0]
        assert "Too many login attempts" not in sent_text
        assert "Login successful" in sent_text

    @pytest.mark.asyncio
    async def test_login_rate_limit_blocks_after_threshold(
        self,
        login_token_factory: Callable[..., Awaitable[tuple[str, Any]]],
    ) -> None:
        """The 11th login claim within 60s is blocked with a cooldown message, no DB claim.

        The first claim succeeds (token claimed, user created); claims 2--10 pass
        the rate-limit check but fail at the DB claim (token already consumed).
        The 11th claim is rate-limited *before* ``handle_login_orm`` is invoked,
        so no DB claim occurs on that call.
        """
        from telegram_bot.handlers.login import handle_login_deep_link

        raw_token, _token = await login_token_factory(
            raw_token=CONSENT_TEST_RAW_TOKEN
        )

        # Send 10 claims that all pass the rate-limit check.
        for _ in range(LOGIN_RATE_LIMIT_REQUESTS):
            msg = _mock_login_message(raw_token, user_id=900000200)
            await handle_login_deep_link(
                message=msg, bot=MagicMock(), state=_mock_state()
            )

        # 11th claim — rate-limited before reaching the ORM.
        blocked_msg = _mock_login_message(raw_token, user_id=900000200)
        await handle_login_deep_link(
            message=blocked_msg, bot=MagicMock(), state=_mock_state()
        )

        # The 11th call received the cooldown message, not the claim result.
        blocked_msg.answer.assert_awaited_once()
        sent_text = blocked_msg.answer.await_args.args[0]
        assert "Too many login attempts" in sent_text

    @pytest.mark.asyncio
    async def test_login_rate_limit_does_not_block_non_login_start(self) -> None:
        """A ``/start`` without a ``login_`` deep-link does not consume the login budget.

        After exhausting 10 login rate-limit slots, a plain ``/start`` (welcome
        greeting path) is unaffected — it returns before the rate-limit check
        and does not consume a slot.
        """
        from telegram_bot.handlers.login import handle_login_deep_link

        # Exhaust the login rate-limit budget directly.
        for _ in range(LOGIN_RATE_LIMIT_REQUESTS):
            assert await check_login_rate_limit(900000300) is True

        # /start with no args → welcome greeting (returns before rate-limit check).
        message = MagicMock()
        message.text = "/start"
        message.from_user = MagicMock()
        message.from_user.id = 900000300
        message.answer = AsyncMock()

        with patch(
            "telegram_bot.handlers.login.get_site_name_async",
            new=AsyncMock(return_value="TestSite"),
        ):
            await handle_login_deep_link(
                message=message, bot=MagicMock(), state=_mock_state()
            )

        # Not blocked — received the welcome greeting, not the cooldown.
        message.answer.assert_awaited_once()
        sent_text = message.answer.await_args.args[0]
        assert "Too many login attempts" not in sent_text
        assert "Welcome" in sent_text
