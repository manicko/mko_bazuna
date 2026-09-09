"""
Tests for AccountStateMiddleware account-state gating (PC-002, PC-003).

Verifies that the middleware delegates to the shared ``get_account_state``
predicate (``apps.users.services.account_state``) and returns state-specific
(i18n-wrapped) denial messages for each blocked account state.

Test environment uses ``LANGUAGE_CODE = "en"`` (see config/settings/test.py),
so ``gettext`` returns the msgid (English source) — the substring assertions
below check English substrings, matching the msgid source text.
"""

from typing import Any

import pytest
from asgiref.sync import sync_to_async
from django.utils import timezone

from apps.users.models import User
from apps.users.services import can_login
from telegram_bot.middlewares import AccountStateMiddleware

pytestmark = [
    pytest.mark.django_db(transaction=True),
    pytest.mark.concurrent,
]
pytestmark.append(pytest.mark.xdist_group("bot_concurrent"))

_BASE_CHAT_ID = 900000200


async def _make_user(
    chat_id: int,
    *,
    is_banned: bool = False,
    is_deleted: bool = False,
    is_declined: bool = False,
    ads_auto_publish: bool = True,
    consent_revoked: bool = False,
) -> User:
    """Create a User with specific account-state flags via sync_to_async."""
    kwargs: dict[str, Any] = {
        "telegram_id": chat_id,
        "chat_id": chat_id,
        "password": "x",
        "is_banned": is_banned,
        "is_deleted": is_deleted,
        "is_declined": is_declined,
        "ads_auto_publish": ads_auto_publish,
    }
    if consent_revoked:
        kwargs["consent_revoked_at"] = timezone.now()
    return await sync_to_async(User.objects.create)(**kwargs)


# ---------------------------------------------------------------------------
# State-specific denial messages
# ---------------------------------------------------------------------------


class TestCheckUserStateMessages:
    """Each blocked state yields a distinct, state-specific denial message."""

    @pytest.mark.asyncio
    async def test_banned_user(self) -> None:
        """Banned user is blocked with a restriction message."""
        chat_id = _BASE_CHAT_ID + 1
        await _make_user(chat_id, is_banned=True)

        middleware = AccountStateMiddleware()
        can_interact, message = await middleware._check_user_state(chat_id)

        assert can_interact is False
        assert "restrict" in message

    @pytest.mark.asyncio
    async def test_deleted_user(self) -> None:
        """Deleted user is blocked with a deletion message."""
        chat_id = _BASE_CHAT_ID + 2
        await _make_user(chat_id, is_deleted=True)

        middleware = AccountStateMiddleware()
        can_interact, message = await middleware._check_user_state(chat_id)

        assert can_interact is False
        assert "deleted" in message

    @pytest.mark.asyncio
    async def test_declined_user(self) -> None:
        """Declined user is blocked with a browse-only message."""
        chat_id = _BASE_CHAT_ID + 3
        await _make_user(chat_id, is_declined=True)

        middleware = AccountStateMiddleware()
        can_interact, message = await middleware._check_user_state(chat_id)

        assert can_interact is False
        assert "browse" in message or "browsing" in message

    @pytest.mark.asyncio
    async def test_consent_revoked_user(self) -> None:
        """Consent-withdrawn user is blocked with an erasure message."""
        chat_id = _BASE_CHAT_ID + 4
        await _make_user(chat_id, consent_revoked=True)

        middleware = AccountStateMiddleware()
        can_interact, message = await middleware._check_user_state(chat_id)

        assert can_interact is False
        assert "erased" in message or "withdrawn" in message

    @pytest.mark.asyncio
    async def test_normal_user(self) -> None:
        """A user with no restriction flags can interact without a message."""
        chat_id = _BASE_CHAT_ID + 5
        await _make_user(chat_id)

        middleware = AccountStateMiddleware()
        can_interact, message = await middleware._check_user_state(chat_id)

        assert can_interact is True
        assert message == ""

    @pytest.mark.asyncio
    async def test_unregistered_user(self) -> None:
        """A chat_id with no matching user returns (True, '')."""
        middleware = AccountStateMiddleware()
        can_interact, message = await middleware._check_user_state(999999999)

        assert can_interact is True
        assert message == ""


# ---------------------------------------------------------------------------
# Cross-predicate agreement
# ---------------------------------------------------------------------------


class TestCrossPredicateAgreement:
    """_check_user_state agrees with the explicit flag formula and can_login."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "row, is_banned, is_deleted, is_declined, consent_revoked, expected_can",
        [
            # Each individual flag blocks interaction.
            (1, True, False, False, False, False),
            (2, False, True, False, False, False),
            (3, False, False, True, False, False),
            (4, False, False, False, True, False),
            # All flags together still blocks.
            (5, True, True, True, True, False),
            # No flags allows interaction.
            (6, False, False, False, False, True),
            # Two flags (deleted + revoked) still blocks.
            (7, False, True, False, True, False),
        ],
    )
    async def test_matches_explicit_formula(
        self,
        row: int,
        is_banned: bool,
        is_deleted: bool,
        is_declined: bool,
        consent_revoked: bool,
        expected_can: bool,
    ) -> None:
        """can_interact matches: not(banned or deleted or declined or revoked).

        This is the single source of truth for interaction gating, matching
        the predicate used in ``get_account_state`` / the AccountState NamedTuple.
        """
        chat_id = _BASE_CHAT_ID + 100 + row
        await _make_user(
            chat_id,
            is_banned=is_banned,
            is_deleted=is_deleted,
            is_declined=is_declined,
            consent_revoked=consent_revoked,
        )

        middleware = AccountStateMiddleware()
        can_interact, _ = await middleware._check_user_state(chat_id)

        expected = not (is_banned or is_deleted or is_declined or consent_revoked)
        assert can_interact == expected
        assert can_interact == expected_can

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "row, is_banned, is_declined",
        [
            (1, True, False),
            (2, False, True),
            (3, True, True),
        ],
    )
    async def test_blocks_when_can_login_blocks(
        self,
        row: int,
        is_banned: bool,
        is_declined: bool,
    ) -> None:
        """When can_login(user) is False, _check_user_state also blocks.

        ``can_login`` gates on is_banned and is_declined only.  The middleware
        extends that gate with is_deleted and consent_revoked, so whenever
        ``can_login`` denies access the middleware must deny too (the middleware
        blocks a superset of the login predicate).
        """
        chat_id = _BASE_CHAT_ID + 200 + row
        user = await _make_user(
            chat_id,
            is_banned=is_banned,
            is_declined=is_declined,
        )

        assert can_login(user) is False

        middleware = AccountStateMiddleware()
        can_interact, message = await middleware._check_user_state(chat_id)

        assert can_interact is False
        assert message != ""

    @pytest.mark.asyncio
    async def test_normal_user_allows_when_can_login_allows(self) -> None:
        """A normal user passes both can_login and _check_user_state."""
        chat_id = _BASE_CHAT_ID + 300
        user = await _make_user(chat_id)

        assert can_login(user) is True

        middleware = AccountStateMiddleware()
        can_interact, message = await middleware._check_user_state(chat_id)

        assert can_interact is True
        assert message == ""
