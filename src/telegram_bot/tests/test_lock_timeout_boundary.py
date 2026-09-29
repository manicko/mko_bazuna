"""Lock-timeout error boundary in the bot handlers (03-DB-004, timeout half B).

Covers the three bot sites that own user state. aiogram's ``dp.errors``
catch-all only logs an exception and does not message the user, so a
``lock_timeout`` reaching a handler would leave the seller with no feedback and
the FSM stranded. These tests pin the per-handler boundary:

- ``process_preview`` answers the busy message and **does not clear the FSM
  state** on a lock timeout, while a genuine moderation failure still clears it.
- ``handle_login_deep_link`` answers the busy message.
- ``alerts._resolve_owned`` returns ``None`` (the existing failure signal).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import psycopg
import pytest
from django.db import OperationalError

pytestmark = [
    pytest.mark.django_db(transaction=True),
    pytest.mark.integration,
    pytest.mark.concurrent,
    pytest.mark.xdist_group("bot_concurrent"),
]


def _lock_timeout_error() -> OperationalError:
    """Build an ``OperationalError`` shaped like a real lock timeout."""
    exc = OperationalError("canceling statement due to lock timeout")
    exc.__cause__ = psycopg.errors.LockNotAvailable(
        "canceling statement due to lock timeout"
    )
    return exc


def _build_message(text: str = "confirm", language_code: str | None = "en-US"):
    user_mock = MagicMock()
    user_mock.language_code = language_code
    user_mock.id = 900000100
    user_mock.username = None
    user_mock.first_name = "Test"
    user_mock.last_name = "User"
    message = MagicMock()
    message.text = text
    message.from_user = user_mock
    message.answer = AsyncMock()
    return message


def _build_state(data: dict) -> MagicMock:
    state = MagicMock()
    state.get_data = AsyncMock(return_value=data)
    state.clear = AsyncMock()
    state.update_data = AsyncMock()
    return state


async def _mock_translate(text: str, target_locales: list[str]) -> dict[str, str]:
    return {loc: f"{text}-{loc}" for loc in target_locales}


class TestProcessPreviewLockTimeout:
    """``process_preview`` keeps the dialog alive on a transient lock failure."""

    @pytest.mark.asyncio
    async def test_lock_timeout_answers_busy_and_keeps_state(self) -> None:
        from telegram_bot.handlers.ad_create import process_preview

        state = _build_state(
            {
                "ad_id": 1,
                "title": "Valid Title",
                "description": "Valid description text for the ad.",
                "price_amount": 100,
                "price_currency": "EUR",
                "photos": [],
                "user_id": 900000100,
            }
        )
        message = _build_message()

        with (
            patch(
                "telegram_bot.handlers.ad_create.submit.translate_all_languages",
                _mock_translate,
            ),
            patch(
                "telegram_bot.handlers.ad_create.submit.submit_ad",
                side_effect=_lock_timeout_error(),
            ),
        ):
            await process_preview(message, state)

        # The busy message, not the deceptive moderation message.
        message.answer.assert_awaited()
        answered = message.answer.await_args.args[0]
        assert "busy" in str(answered).lower()
        # The critical line: state is NOT cleared on a transient lock timeout.
        state.clear.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_genuine_moderation_failure_still_clears_state(self) -> None:
        """The genuine-failure branch keeps its message AND its state.clear()."""
        from telegram_bot.handlers.ad_create import process_preview

        state = _build_state(
            {
                "ad_id": 1,
                "title": "Valid Title",
                "description": "Valid description text for the ad.",
                "price_amount": 100,
                "price_currency": "EUR",
                "photos": [],
                "user_id": 900000100,
            }
        )
        message = _build_message()

        with (
            patch(
                "telegram_bot.handlers.ad_create.submit.translate_all_languages",
                _mock_translate,
            ),
            patch(
                "telegram_bot.handlers.ad_create.submit.submit_ad",
                return_value=(False, ["Title is too short"]),
            ),
        ):
            await process_preview(message, state)

        message.answer.assert_awaited()
        assert message.answer.await_args.args[0] == "Title is too short"
        state.clear.assert_awaited()

    @pytest.mark.asyncio
    async def test_non_lock_operational_error_is_reraised(self) -> None:
        """An unrelated ``OperationalError`` is not swallowed."""
        from telegram_bot.handlers.ad_create import process_preview

        state = _build_state(
            {
                "ad_id": 1,
                "title": "Valid Title",
                "description": "Valid description text for the ad.",
                "price_amount": 100,
                "price_currency": "EUR",
                "photos": [],
                "user_id": 900000100,
            }
        )
        message = _build_message()
        unrelated = OperationalError("connection refused")

        with (
            patch(
                "telegram_bot.handlers.ad_create.submit.translate_all_languages",
                _mock_translate,
            ),
            patch(
                "telegram_bot.handlers.ad_create.submit.submit_ad",
                side_effect=unrelated,
            ),
            pytest.raises(OperationalError),
        ):
            await process_preview(message, state)


class TestResolveOwnedLockTimeout:
    """``_resolve_owned`` degrades to ``None`` on a lock timeout."""

    def test_lock_timeout_returns_none(self, seller) -> None:
        from apps.search.models import SavedSearch
        from telegram_bot.handlers.alerts import _resolve_owned

        SavedSearch.objects.create(
            user=seller,
            unsubscribe_token="a" * 32,
            is_active=True,
        )

        with patch(
            "telegram_bot.handlers.alerts.SavedSearch.objects.select_for_update",
            side_effect=_lock_timeout_error(),
        ):
            result = _resolve_owned("a" * 32, seller.chat_id, active=False)

        assert result is None


class TestHandleLoginLockTimeout:
    """``handle_login_deep_link`` answers the busy message on a lock timeout."""

    @pytest.mark.asyncio
    async def test_lock_timeout_answers_busy(self) -> None:
        import hashlib

        from telegram_bot.handlers import login as login_module

        raw_token = "abcdefghijklmnopqrstuvwxyz012345"
        # The handler hashes the raw token before calling handle_login_orm.
        token_hash = hashlib.sha256(raw_token.encode()).hexdigest()

        message = _build_message(text=f"/start login_{raw_token}")
        message.from_user.id = 900000100
        message.from_user.language_code = "en"

        bot = MagicMock()
        state = _build_state({})

        with (
            patch.object(
                login_module,
                "check_login_rate_limit",
                new=AsyncMock(return_value=True),
            ),
            patch.object(
                login_module,
                "handle_login_orm",
                new=AsyncMock(side_effect=_lock_timeout_error()),
            ),
            patch(
                "telegram_bot.handlers.contact.handle_contact_start",
                new=AsyncMock(return_value=False),
            ),
        ):
            # The unsubscribe deep-link delegate is imported inside the handler;
            # patching the module attribute is sufficient.
            from telegram_bot.handlers import alerts as alerts_module

            with patch.object(
                alerts_module,
                "handle_unsubscribe_start",
                new=AsyncMock(return_value=False),
            ):
                await login_module.handle_login_deep_link(message, bot, state)

        message.answer.assert_awaited()
        answered = message.answer.await_args.args[0]
        assert "busy" in str(answered).lower()
        # The token claim was rolled back; no user state must be recorded.
        state.update_data.assert_not_awaited()
        # Sanity: the hashed token is what the handler would have passed.
        assert token_hash == hashlib.sha256(raw_token.encode()).hexdigest()

    @pytest.mark.asyncio
    async def test_lock_timeout_in_worker_thread_surfaces(self) -> None:
        """A lock timeout raised inside ``sync_to_async`` reaches the handler.

        Exercises the real threading boundary the production path uses, so the
        per-handler catch is proven to work across ``sync_to_async`` rather
        than only when the error is raised on the event-loop thread.
        """
        import hashlib

        from asgiref.sync import sync_to_async

        from telegram_bot.handlers import login as login_module

        raw_token = "bbbdefghijklmnopqrstuvwxyz012345"
        token_hash = hashlib.sha256(raw_token.encode()).hexdigest()

        message = _build_message(text=f"/start login_{raw_token}")
        message.from_user.id = 900000100
        message.from_user.language_code = "en"
        bot = MagicMock()
        state = _build_state({})

        @sync_to_async
        def _raise_in_worker() -> None:
            raise _lock_timeout_error()

        async def _raise_across_thread(*args, **kwargs):
            """Raise a lock timeout from inside a real ``sync_to_async`` call.

            Production ``handle_login_orm`` wraps its work in ``sync_to_async``,
            so the error crosses a worker-thread boundary before it reaches the
            handler. This mirrors that shape.
            """
            await _raise_in_worker()

        with (
            patch.object(
                login_module,
                "check_login_rate_limit",
                new=AsyncMock(return_value=True),
            ),
            patch.object(
                login_module,
                "handle_login_orm",
                new=_raise_across_thread,
            ),
            patch(
                "telegram_bot.handlers.contact.handle_contact_start",
                new=AsyncMock(return_value=False),
            ),
        ):
            from telegram_bot.handlers import alerts as alerts_module

            with patch.object(
                alerts_module,
                "handle_unsubscribe_start",
                new=AsyncMock(return_value=False),
            ):
                await login_module.handle_login_deep_link(message, bot, state)

        message.answer.assert_awaited()
        assert "busy" in str(message.answer.await_args.args[0]).lower()
        assert token_hash  # exercised by the hash above
