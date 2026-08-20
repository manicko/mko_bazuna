"""
Tests for Telegram saved-search unsubscribe (AL-002, CR10).

Covers:
- ``resolve_unsubscribe``: disables a search owned by the caller (via stable
  ``chat_id``), returns None for unknown tokens / non-owners (no state leak).
- ``resolve_reenable``: re-enables an owned search.
- ``handle_unsubscribe_start`` deep-link branch (``/start unsub_<token>``):
  owned token -> "disabled" message; unknown/foreign -> "invalid".
"""

import pytest
from asgiref.sync import sync_to_async

from apps.search.models import SavedSearch
from apps.users.models import User

pytestmark = [
    pytest.mark.django_db(transaction=True),
    pytest.mark.slow,
    pytest.mark.integration,
    pytest.mark.concurrent,
]


@pytest.fixture
def owner() -> User:
    return User.objects.create(
        telegram_id=950000201,
        chat_id=950000201,
        username="owner",
    )


@pytest.fixture
def stranger() -> User:
    return User.objects.create(
        telegram_id=950000202,
        chat_id=950000202,
        username="stranger",
    )


class TestResolveUnsubscribe:
    """Ownership + is_active flips (CR10)."""

    @pytest.mark.asyncio
    async def test_owned_search_disabled(
        self, owner: User
    ) -> None:
        from telegram_bot.handlers.alerts import resolve_unsubscribe

        ss = await sync_to_async(SavedSearch.objects.create)(
            user=owner, query="велосипед", is_active=True
        )

        result = await resolve_unsubscribe(ss.unsubscribe_token, owner.chat_id)

        assert result is not None
        await sync_to_async(result.refresh_from_db)()
        assert result.is_active is False

    @pytest.mark.asyncio
    async def test_non_owner_rejected(
        self, owner: User, stranger: User
    ) -> None:
        from telegram_bot.handlers.alerts import resolve_unsubscribe

        ss = await sync_to_async(SavedSearch.objects.create)(
            user=owner, query="велосипед", is_active=True
        )

        result = await resolve_unsubscribe(ss.unsubscribe_token, stranger.chat_id)

        assert result is None
        await sync_to_async(ss.refresh_from_db)()
        assert ss.is_active is True  # unchanged — no leak

    @pytest.mark.asyncio
    async def test_unknown_token_rejected(self, stranger: User) -> None:
        from telegram_bot.handlers.alerts import resolve_unsubscribe

        result = await resolve_unsubscribe("no_such_token_with_40_chars_xxxxxxxx", stranger.chat_id)
        assert result is None

    @pytest.mark.asyncio
    async def test_reenable_owned_search(
        self, owner: User
    ) -> None:
        from telegram_bot.handlers.alerts import resolve_reenable

        ss = await sync_to_async(SavedSearch.objects.create)(
            user=owner, query="велосипед", is_active=False
        )

        result = await resolve_reenable(ss.unsubscribe_token, owner.chat_id)

        assert result is not None
        await sync_to_async(result.refresh_from_db)()
        assert result.is_active is True


class TestUnsubscribeDeepLink:
    """/start unsub_<token> deep-link branch (secondary mechanism)."""

    @pytest.mark.asyncio
    async def test_owned_link_disables(self, owner: User) -> None:
        from telegram_bot.handlers.alerts import handle_unsubscribe_start

        ss = await sync_to_async(SavedSearch.objects.create)(
            user=owner, query="велосипед", is_active=True
        )

        messages: list[str] = []

        class FakeFrom:
            id = owner.chat_id

        class FakeMessage:
            text = f"/start unsub_{ss.unsubscribe_token}"
            from_user = FakeFrom()

            async def answer(self, text: str) -> None:
                messages.append(text)

        handled = await handle_unsubscribe_start(FakeMessage(), None, f"unsub_{ss.unsubscribe_token}")

        assert handled is True
        assert any("отключены" in m for m in messages)
        await sync_to_async(ss.refresh_from_db)()
        assert ss.is_active is False

    @pytest.mark.asyncio
    async def test_unknown_link_rejected(self, stranger: User) -> None:
        from telegram_bot.handlers.alerts import handle_unsubscribe_start

        messages: list[str] = []

        class FakeFrom:
            id = stranger.chat_id

        class FakeMessage:
            text = "/start unsub_deadbeef"
            from_user = FakeFrom()

            async def answer(self, text: str) -> None:
                messages.append(text)

        # A well-formed 32-char token that is not in the DB must be rejected.
        handled = await handle_unsubscribe_start(
            FakeMessage(), None, "unsub_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
        )

        assert handled is True
        assert any("недействительна" in m for m in messages)

    @pytest.mark.asyncio
    async def test_non_unsub_link_not_handled(self, owner: User) -> None:
        from telegram_bot.handlers.alerts import handle_unsubscribe_start

        class FakeMessage:
            pass

        handled = await handle_unsubscribe_start(FakeMessage(), None, "login_abc")
        assert handled is False
