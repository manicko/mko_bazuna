"""
Bot deactivation access-control matrix (plan 19, ``B-2``; §3 is normative).

Drives the real ``AccountStateMiddleware`` gate with real aiogram ``Update``
objects for a deactivated (``is_active=False``) account and pins every row of
plan 19's §3 matrix:

- no-argument ``/start`` greeting -> allowed (carries the support button)
- ``/start <anything>`` -> blocked (``19-D6``)
- ``SUPPORT_START`` callback -> allowed (the restoration channel)
- free text inside the support-intake FSM -> allowed, and a ``SupportTicket``
  is created (the canary for risk ``R-1``: an event-type allowlist would break
  this step)
- ``contact_us`` / ``contact_<id>`` deep-links -> blocked (``19-D2``)
- every other command / the whole ad-creation flow -> blocked
- a deactivated-and-banned account is NOT granted the carve-out
- leaving the intake FSM blocks the user again

Also pins the **pre-existing** DECLINE behaviour (§3, ``19-D5``/``D-3``) and
the web ``ModelBackend`` session revocation (``19-D5`` must not touch it).

Message assertions deliberately check **hard-coded English fragments**, never a
constant imported from the module under test: plan 18's validator caught a
tautology of exactly that shape (``assert CONSTANT in text`` cannot fail when
``CONSTANT`` comes from the code under test). See ``test_admin_deactivate_user``
for the precedent.
"""

import itertools
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import Chat, Message, Update, User as TelegramUser
from asgiref.sync import sync_to_async
from django.test import Client
from django.utils import timezone

from apps.users.models import User
from conftest import make_user
from telegram_bot.handlers.support import handle_support_message
from telegram_bot.middlewares import AccountStateMiddleware
from telegram_bot.schemas.callbacks import BotCallbackPrefix
from telegram_bot.states import ContactUsState

pytestmark = [
    pytest.mark.django_db(transaction=True),
    pytest.mark.integration,
    pytest.mark.concurrent,
]
pytestmark.append(pytest.mark.xdist_group("bot_concurrent"))

_BASE_CHAT_ID = 900000900
_next_update_id = itertools.count(9000)


def _make_message_update(chat_id: int, text: str = "") -> Update:
    """Construct a real aiogram ``Update`` wrapping a ``Message``."""
    user = TelegramUser(id=chat_id, first_name="Test", is_bot=False)
    return Update(
        update_id=next(_next_update_id),
        message=Message(
            message_id=1,
            date=timezone.now(),
            chat=Chat(id=chat_id, type="private"),
            from_user=user,
            text=text,
        ),
    )


def _make_callback_update(chat_id: int, callback_data: str) -> Update:
    """Construct a real aiogram ``Update`` wrapping a ``CallbackQuery``."""
    from aiogram.types import CallbackQuery

    user = TelegramUser(id=chat_id, first_name="Test", is_bot=False)
    bot = TelegramUser(id=777000, first_name="MkoBazunaBot", is_bot=True)
    msg = Message(
        message_id=1,
        date=timezone.now(),
        chat=Chat(id=chat_id, type="private"),
        from_user=bot,
    )
    return Update(
        update_id=next(_next_update_id),
        callback_query=CallbackQuery(
            id="cb_test",
            from_user=user,
            message=msg,
            chat_instance="-1",
            data=callback_data,
        ),
    )


def _make_support_fsm(chat_id: int) -> FSMContext:
    """A real ``FSMContext`` over in-memory storage, keyed on ``chat_id``."""
    storage = MemoryStorage()
    key = StorageKey(bot_id=1, chat_id=chat_id, user_id=chat_id, thread_id=0)
    return FSMContext(storage=storage, key=key)


async def _make_deactivated(chat_id: int, **overrides: object) -> User:
    """Create an ``is_active=False`` user (plus any extra flags)."""
    user = await sync_to_async(make_user)(chat_id, is_active=False, **overrides)
    # ``make_user`` writes ``is_active`` via ``overrides``; assert it stuck.
    assert user.is_active is False
    return user


async def _run_gate(
    update: Update,
    data: dict[str, Any],
) -> tuple[Any, AsyncMock, AsyncMock]:
    """Run the real middleware over ``update``; return (result, handler, answer).

    ``Message.answer`` is monkeypatched at the call site by callers that need
    it; here we install an ``AsyncMock`` on the class for the duration.
    """
    handler = AsyncMock(return_value="proceed")
    answer = AsyncMock()
    original = Message.answer
    Message.answer = answer  # type: ignore[method-assign]
    try:
        result = await AccountStateMiddleware()(handler, update, data)
    finally:
        Message.answer = original  # type: ignore[method-assign]
    return result, handler, answer


# ---------------------------------------------------------------------------
# §3 matrix — allowed rows
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_deactivated_user_sees_the_start_greeting() -> None:
    """No-argument ``/start`` is allowed: it carries the support button."""
    chat_id = _BASE_CHAT_ID + 1
    await _make_deactivated(chat_id)

    result, handler, answer = await _run_gate(
        _make_message_update(chat_id, "/start"), {}
    )

    assert result == "proceed"
    handler.assert_awaited_once()
    answer.assert_not_awaited()


@pytest.mark.asyncio
async def test_deactivated_user_with_start_argument_is_blocked() -> None:
    """``19-D6``: ``/start <anything>`` stays blocked for a deactivated user."""
    chat_id = _BASE_CHAT_ID + 2
    await _make_deactivated(chat_id)

    result, handler, answer = await _run_gate(
        _make_message_update(chat_id, "/start login_" + "a" * 32), {}
    )

    assert result is None
    handler.assert_not_awaited()
    answer.assert_awaited_once()


@pytest.mark.asyncio
async def test_deactivated_user_can_tap_contact_support() -> None:
    """``SUPPORT_START`` passes the gate — the restoration channel."""
    chat_id = _BASE_CHAT_ID + 3
    await _make_deactivated(chat_id)

    result, handler, answer = await _run_gate(
        _make_callback_update(chat_id, str(BotCallbackPrefix.SUPPORT_START)), {}
    )

    assert result == "proceed"
    handler.assert_awaited_once()
    answer.assert_not_awaited()


@pytest.mark.asyncio
async def test_deactivated_user_can_complete_the_support_ticket() -> None:
    """The most important test in the plan (§3, ``R-1``).

    Free text while in the support-intake FSM must pass the state-based
    carve-out, and the ticket must actually be persisted. An event-type
    allowlist would let the user tap the button but never complete the ticket.

    Re-pinned for the storage-consent gate (06-PII-101): the deactivated user
    must also have granted consent, which is the carve-out's real purpose —
    "contact support to restore your account" stays reachable for anyone who
    actually consented. ``_make_deactivated`` forwards ``**overrides`` to
    ``make_user``, so ``consent_given_at`` is set explicitly here rather than
    relying on a fixture default.
    """
    chat_id = _BASE_CHAT_ID + 4
    user = await _make_deactivated(chat_id, consent_given_at=timezone.now())

    state = _make_support_fsm(chat_id)
    await state.set_state(ContactUsState.AWAITING_MESSAGE)
    await state.update_data(user_id=user.id)

    update = _make_message_update(chat_id, "Please restore my account")

    # 1. The middleware gate lets the free-text update through.
    result, handler, answer = await _run_gate(update, {"state": state})
    assert result == "proceed"
    handler.assert_awaited_once()
    answer.assert_not_awaited()

    # 2. The same update reaches the real handler and persists a ticket.
    #    aiogram's ``Message`` is a frozen pydantic model, so build the
    #    handler-side double with ``MagicMock`` (mirroring ``test_support.py``).
    handler_message = MagicMock()
    handler_message.from_user = MagicMock()
    handler_message.from_user.id = chat_id
    handler_message.from_user.is_bot = False
    handler_message.from_user.username = "deactivated_user"
    handler_message.chat = MagicMock()
    handler_message.chat.id = chat_id
    handler_message.text = "Please restore my account"
    handler_message.answer = AsyncMock()
    bot = MagicMock()
    bot.get_me = AsyncMock(return_value=MagicMock(username="mybot"))

    from unittest.mock import patch

    with (
        patch(
            "telegram_bot.handlers.support.send_support_notification_email",
            new=AsyncMock(),
        ),
        patch(
            "telegram_bot.handlers.support.send_support_notification_telegram",
            new=AsyncMock(),
        ),
        patch(
            "telegram_bot.handlers.support.get_support_contacts_async",
            new=AsyncMock(return_value=[]),
        ),
    ):
        await handle_support_message(handler_message, bot, state)

    from apps.core.models import SupportTicket

    count = await sync_to_async(SupportTicket.objects.count)()
    assert count == 1
    ticket = await sync_to_async(SupportTicket.objects.latest)("id")
    assert ticket.telegram_id == chat_id
    assert ticket.text == "Please restore my account"
    assert ticket.user_id == user.id


@pytest.mark.asyncio
async def test_deactivated_user_without_consent_is_refused() -> None:
    """A deactivated user without storage consent is refused (06-PII-101).

    Complementary half of ``test_deactivated_user_can_complete_the_support_ticket``:
    the carve-out must not exempt a deactivated account from the storage-consent
    gate. The free-text update still passes the middleware (the carve-out is a
    state rule), but the handler refuses it, so no ticket is created.
    """
    chat_id = _BASE_CHAT_ID + 21
    user = await _make_deactivated(chat_id)  # no consent_given_at

    state = _make_support_fsm(chat_id)
    await state.set_state(ContactUsState.AWAITING_MESSAGE)
    await state.update_data(user_id=user.id)

    update = _make_message_update(chat_id, "Please restore my account")

    result, handler, answer = await _run_gate(update, {"state": state})
    assert result == "proceed"

    handler_message = MagicMock()
    handler_message.from_user = MagicMock()
    handler_message.from_user.id = chat_id
    handler_message.from_user.is_bot = False
    handler_message.from_user.username = "deactivated_no_consent"
    handler_message.chat = MagicMock()
    handler_message.chat.id = chat_id
    handler_message.text = "Please restore my account"
    handler_message.answer = AsyncMock()
    bot = MagicMock()
    bot.get_me = AsyncMock(return_value=MagicMock(username="mybot"))

    from unittest.mock import patch

    with (
        patch(
            "telegram_bot.handlers.support.send_support_notification_email",
            new=AsyncMock(),
        ),
        patch(
            "telegram_bot.handlers.support.send_support_notification_telegram",
            new=AsyncMock(),
        ),
        patch(
            "telegram_bot.handlers.support.get_support_contacts_async",
            new=AsyncMock(return_value=[]),
        ),
    ):
        await handle_support_message(handler_message, bot, state)

    from apps.core.models import SupportTicket

    count = await sync_to_async(SupportTicket.objects.count)()
    assert count == 0
    handler_message.answer.assert_awaited_once()


@pytest.mark.asyncio
async def test_deactivated_user_is_blocked_after_leaving_the_support_fsm() -> None:
    """Once out of the intake state, the deactivated user is blocked again."""
    chat_id = _BASE_CHAT_ID + 5
    await _make_deactivated(chat_id)

    state = _make_support_fsm(chat_id)
    await state.set_state(ContactUsState.IDLE)

    result, handler, answer = await _run_gate(
        _make_message_update(chat_id, "anything at all"), {"state": state}
    )

    assert result is None
    handler.assert_not_awaited()
    answer.assert_awaited_once()


# ---------------------------------------------------------------------------
# §3 matrix — blocked rows
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_deactivated_user_cannot_create_an_ad() -> None:
    """``/post`` and the ad-creation FSM are blocked (``19-D2``)."""
    chat_id = _BASE_CHAT_ID + 6
    await _make_deactivated(chat_id)

    state = _make_support_fsm(chat_id)
    from telegram_bot.states import AdCreateState

    await state.set_state(AdCreateState.TITLE)

    for text in ("/post", "My ad title"):
        result, handler, answer = await _run_gate(
            _make_message_update(chat_id, text), {"state": state}
        )
        assert result is None, f"{text!r} must be blocked"
        handler.assert_not_awaited()
        answer.assert_awaited_once()


@pytest.mark.asyncio
async def test_deactivated_user_cannot_smuggle_a_command_through_the_support_fsm() -> None:
    """A command typed in the support-intake state is still blocked.

    The intake carve-out is free-text-only. Without this, a deactivated user
    could enter the support FSM and send ``/post`` to reach ad creation, since
    ``/post`` would otherwise satisfy the state-based carve-out.
    """
    chat_id = _BASE_CHAT_ID + 20
    await _make_deactivated(chat_id)

    state = _make_support_fsm(chat_id)
    await state.set_state(ContactUsState.AWAITING_MESSAGE)

    for text in ("/post", "/language", "/start"):
        result, handler, answer = await _run_gate(
            _make_message_update(chat_id, text), {"state": state}
        )
        # ``/start`` (no args) is allowed by the greeting clause; commands are not.
        if text == "/start":
            assert result == "proceed", text
            handler.assert_awaited_once()
        else:
            assert result is None, f"{text!r} must be blocked"
            handler.assert_not_awaited()
            answer.assert_awaited_once()

    # A non-support callback in the intake state is likewise blocked (the
    # free-text carve-out is message-only, not callback-only).
    result, handler, answer = await _run_gate(
        _make_callback_update(chat_id, "purpose:sale"), {"state": state}
    )
    assert result is None
    handler.assert_not_awaited()
    answer.assert_awaited_once()


@pytest.mark.asyncio
async def test_deactivated_user_cannot_use_contact_deep_link() -> None:
    """``contact_us`` / ``contact_<id>`` are blocked for a deactivated user."""
    chat_id = _BASE_CHAT_ID + 7
    await _make_deactivated(chat_id)

    for text in ("/start contact_us", "/start contact_42"):
        result, handler, answer = await _run_gate(
            _make_message_update(chat_id, text), {}
        )
        assert result is None, f"{text!r} must be blocked"
        handler.assert_not_awaited()
        answer.assert_awaited_once()


@pytest.mark.asyncio
async def test_deactivated_user_blocked_for_other_commands() -> None:
    """Any other command or callback is blocked."""
    chat_id = _BASE_CHAT_ID + 8
    await _make_deactivated(chat_id)

    result, handler, answer = await _run_gate(
        _make_message_update(chat_id, "/language"), {}
    )
    assert result is None
    handler.assert_not_awaited()
    answer.assert_awaited_once()

    result, handler, answer = await _run_gate(
        _make_callback_update(chat_id, "purpose:sale"), {}
    )
    assert result is None
    handler.assert_not_awaited()
    answer.assert_awaited_once()


@pytest.mark.asyncio
async def test_deactivated_and_banned_user_is_not_granted_the_carve_out() -> None:
    """``is_active`` evaluated first; carve-out unreachable for a banned account.

    Even the ``SUPPORT_START`` callback — the strongest carve-out shape — must
    not open a restoration channel for a banned-and-deactivated account.
    """
    chat_id = _BASE_CHAT_ID + 9
    await _make_deactivated(chat_id, is_banned=True)

    result, handler, answer = await _run_gate(
        _make_callback_update(chat_id, str(BotCallbackPrefix.SUPPORT_START)), {}
    )

    assert result is None
    handler.assert_not_awaited()
    answer.assert_awaited_once()


@pytest.mark.asyncio
async def test_deactivated_and_revoked_user_is_not_granted_the_carve_out() -> None:
    """The carve-out is also unreachable for an erased (consent-revoked) account."""
    chat_id = _BASE_CHAT_ID + 10
    await _make_deactivated(chat_id, consent_revoked=True)

    result, handler, answer = await _run_gate(
        _make_message_update(chat_id, "/start"), {}
    )

    assert result is None
    handler.assert_not_awaited()
    answer.assert_awaited_once()


# ---------------------------------------------------------------------------
# 19-D3 — the rejection message
# ---------------------------------------------------------------------------


async def _deactivated_rejection_message(chat_id: int) -> str:
    """Drive a plain blocked update and return the rejection text."""
    result, handler, answer = await _run_gate(
        _make_message_update(chat_id, "/language"), {}
    )
    assert result is None
    assert answer.await_count == 1
    call = answer.await_args
    assert call is not None
    return str(call.args[0])


@pytest.mark.asyncio
async def test_rejection_message_differs_from_the_banned_message() -> None:
    """``19-D3``: the deactivation message is distinct from the ban message."""
    deactivated_chat = _BASE_CHAT_ID + 11
    await _make_deactivated(deactivated_chat)
    deactivated_text = await _deactivated_rejection_message(deactivated_chat)

    from telegram_bot.middlewares import AccountStateMiddleware as _M

    banned_chat = _BASE_CHAT_ID + 12
    await sync_to_async(make_user)(banned_chat, is_banned=True)
    can, banned_text = await _M()._check_user_state(banned_chat)

    assert can is False
    assert deactivated_text != banned_text


@pytest.mark.asyncio
async def test_rejection_message_points_at_support() -> None:
    """The deactivation message names the restoration channel (support)."""
    chat_id = _BASE_CHAT_ID + 13
    await _make_deactivated(chat_id)
    text = await _deactivated_rejection_message(chat_id)

    # Hard-coded fragments, NOT an imported constant (plan 18's tautology trap).
    assert "deactivated" in text.lower()
    assert "support" in text.lower()


# ---------------------------------------------------------------------------
# Pre-existing DECLINE behaviour and the web revocation regression
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_decline_user_cannot_reach_support() -> None:
    """Pins the pre-existing DECLINE-blocked behaviour (§3, ``19-D5``/``D-3``).

    ``SUPPORT_START`` is not a contact deep-link, so a DECLINE user's ``/start``
    greeting is rejected and they never see the support keyboard. This is
    recorded, not fixed; the owner for any change is product (``D-3``).
    """
    chat_id = _BASE_CHAT_ID + 14
    await sync_to_async(make_user)(chat_id, is_declined=True)

    result, handler, answer = await _run_gate(
        _make_callback_update(chat_id, str(BotCallbackPrefix.SUPPORT_START)), {}
    )
    assert result is None
    handler.assert_not_awaited()
    answer.assert_awaited_once()


@pytest.mark.django_db(transaction=True)
def test_web_session_still_revoked() -> None:
    """``19-D5`` must not touch the web tier: ``ModelBackend`` still revokes.

    A deactivated user's live session is treated as anonymous on the next
    request — the plan-18 guarantee this plan leaves untouched.
    """
    user = make_user(900000999, is_active=True, consent_given_at=timezone.now())
    user.set_password("testpass")
    user.save(update_fields=["password"])

    client = Client()
    client.force_login(user)
    assert client.get("/dashboard/").status_code == 200

    User.objects.filter(pk=user.pk).update(is_active=False)
    # Session identity is re-resolved per request; ModelBackend rejects an
    # inactive user, so the dashboard redirects to login.
    response = client.get("/dashboard/")
    assert response.status_code == 302
