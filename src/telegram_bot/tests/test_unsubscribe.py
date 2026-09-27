"""
Tests for Telegram saved-search unsubscribe (AL-002, CR10).

Covers:
- ``resolve_unsubscribe``: disables a search owned by the caller (via stable
  ``chat_id``), returns None for unknown tokens / non-owners (no state leak).
- ``resolve_reenable``: re-enables an owned search.
- ``handle_unsubscribe_start`` deep-link branch (``/start unsub_<token>``):
  owned token -> "disabled" message; unknown/foreign -> "invalid".
"""

import inspect
import threading
import time

import pytest
from asgiref.sync import sync_to_async
from django.db import connection, transaction
from django.utils import translation

from apps.search.models import SavedSearch
from apps.users.models import User

pytestmark = [
    pytest.mark.django_db(transaction=True),
    pytest.mark.integration,
    pytest.mark.concurrent,
]
pytestmark.append(pytest.mark.xdist_group("bot_concurrent"))


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
    async def test_owned_search_disabled(self, owner: User) -> None:
        from telegram_bot.handlers.alerts import resolve_unsubscribe

        ss = await sync_to_async(SavedSearch.objects.create)(
            user=owner, query="велосипед", is_active=True
        )

        result = await resolve_unsubscribe(ss.unsubscribe_token, owner.chat_id)

        assert result is not None
        await sync_to_async(result.refresh_from_db)()
        assert result.is_active is False

    @pytest.mark.asyncio
    async def test_non_owner_rejected(self, owner: User, stranger: User) -> None:
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

        result = await resolve_unsubscribe(
            "no_such_token_with_40_chars_xxxxxxxx", stranger.chat_id
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_reenable_owned_search(self, owner: User) -> None:
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
                messages.append(str(text))

        with translation.override("ru"):
            handled = await handle_unsubscribe_start(
                FakeMessage(), None, f"unsub_{ss.unsubscribe_token}"
            )

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
                messages.append(str(text))

        # A well-formed 32-char token that is not in the DB must be rejected.
        with translation.override("ru"):
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


class TestResolveOwnedLocking:
    """Verify _resolve_owned uses row-level locking (03-DB-002).

    These structural assertions guard against accidental removal of the
    ``select_for_update()`` / ``transaction.atomic()`` pattern in
    ``_resolve_owned`` — the fix for the lost-update race on ``is_active``
    between concurrent disable/enable toggles (audit finding 03-DB-002).
    """

    def test_resolve_owned_uses_select_for_update_and_atomic(self) -> None:
        """_resolve_owned source contains select_for_update inside atomic."""
        from telegram_bot.handlers import alerts

        source = inspect.getsource(alerts._resolve_owned)
        assert "transaction.atomic" in source
        assert "select_for_update" in source

    def test_resolve_owned_fetches_inside_atomic(self) -> None:
        """The locked fetch must appear inside the transaction.atomic() block.

        Verifies the ``SELECT … FOR UPDATE`` lookup is performed within the
        atomic block (not before it), so the row lock is held across the
        read-check-write.
        """
        from telegram_bot.handlers import alerts

        source = inspect.getsource(alerts._resolve_owned)
        atomic_idx = source.index("transaction.atomic")
        sfu_idx = source.index("select_for_update")
        assert sfu_idx > atomic_idx, (
            "select_for_update fetch must appear inside the transaction.atomic() "
            "block, not before it"
        )


class TestResolveOwnedConcurrency:
    """Concurrent disable + enable toggles must not lose updates (03-DB-002).

    ``_resolve_owned`` reads a ``SavedSearch`` by token, checks ownership, then
    writes ``is_active``. Without ``select_for_update()``, two concurrent
    toggles (disable + enable) can interleave so one update is lost. With the
    row lock inside ``transaction.atomic()``, the second toggle blocks until the
    first commits and the final ``is_active`` reflects the last writer.
    """

    def test_concurrent_toggle_no_lost_update(self, owner: User) -> None:
        """A toggle blocked on the row lock runs after commit; final value is
        the last writer's (no lost update)."""
        from telegram_bot.handlers.alerts import _resolve_owned

        ss = SavedSearch.objects.create(
            user=owner, query="велосипед", is_active=True
        )
        token = ss.unsubscribe_token
        chat_id = owner.chat_id

        started = threading.Event()
        finished = threading.Event()
        errors: list[BaseException] = []

        def background_enable() -> None:
            """Background thread: re-enables the search (active=True)."""
            started.set()
            try:
                with transaction.atomic():  # pyright: ignore[reportGeneralTypeIssues]
                    _resolve_owned(token, chat_id, active=True)
            except BaseException as exc:  # noqa: BLE001
                errors.append(exc)
            finally:
                finished.set()
                connection.close()

        # --- Main thread: acquire the row lock and disable the search ---
        with transaction.atomic():  # pyright: ignore[reportGeneralTypeIssues]
            _resolve_owned(token, chat_id, active=False)
            # Row is now locked (FOR UPDATE) and is_active=False.

            # --- Start the concurrent re-enable toggle ---
            thread = threading.Thread(target=background_enable)
            thread.start()

            # Wait for the background thread to start.
            assert started.wait(timeout=5), "Background thread did not start"

            # The re-enable should block waiting for the row lock.
            time.sleep(1.0)
            assert not finished.is_set(), (
                "Background toggle completed before the lock was released — "
                "select_for_update did not serialize the concurrent toggles"
            )

        # --- Main transaction commits, releasing the row lock ---
        # The background re-enable can now proceed and must win (last writer).
        assert finished.wait(timeout=10), (
            "Background toggle did not complete after lock was released"
        )
        thread.join(timeout=10)

        assert not errors, f"Background thread raised: {errors}"

        ss.refresh_from_db()
        assert ss.is_active is True, (
            "Final is_active must reflect the last (re-enable) toggle — "
            "a lost update occurred"
        )
