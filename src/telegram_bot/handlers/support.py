"""
Support message intake handler for Telegram bot.

Implements the support-desk flow (EC-9): a user taps the "Contact support"
button on the ``/start`` greeting (``BotCallbackPrefix.SUPPORT_START``) and is
prompted to write their question. The free-text reply is persisted as a
``SupportTicket`` and delivered to the configured support channels (email +
Telegram) so the desk can reply out-of-band.

Access control is governed by ``AccountStateMiddleware`` before the handler
runs: a **deactivated** user reaches the intake through the plan 19 support
carve-out. Banned / deleted / consent-revoked users are blocked.
**DECLINE users cannot reach support**: ``SUPPORT_START`` is not a contact
deep-link, so a DECLINE user's ``/start`` greeting is rejected and they never
see the keyboard (pre-existing behaviour, recorded as ``19-D5``/``D-3`` — not
fixed by plan 19). The handler itself only guards against bots, mirroring
``contact.py``.

**Storage-consent gate (06-PII-101).** Support intake requires consent to
personal-data storage. The actor is resolved server-side from the
Telegram-signed ``chat_id`` (never a client-supplied field) and must satisfy
``can_store_personal_data`` — a registered account that has granted consent and
is not blocked. An unregistered ``chat_id`` is refused with
:data:`SUPPORT_CONSENT_REQUIRED_MESSAGE`, which points at sign-in and consent;
no ticket is created. When the FSM holds a ``user_id`` it is cross-checked
against the server-resolved actor, so free text captured before consent cannot
become a ticket afterwards. The FSM is reset to ``IDLE`` on refusal.
"""

import logging
from typing import Final

from aiogram import Bot, F, Router, types
from asgiref.sync import sync_to_async
from django.utils.translation import gettext as _, gettext_lazy

from apps.core.services.support import get_support_contacts_async
from telegram_bot.schemas.callbacks import BotCallbackPrefix
from telegram_bot.services.rate_limit import check_support_message_rate_limit
from telegram_bot.services.support_delivery_email import (
    send_support_notification_email,
)
from telegram_bot.services.support_delivery_telegram import (
    send_support_notification_telegram,
)
from telegram_bot.states import ContactUsState

logger = logging.getLogger(__name__)

router = Router()

# Maximum length of a support message body.
SUPPORT_MESSAGE_MAX_LENGTH: Final[int] = 4000

# Callback data for the "Contact support" button (shared with login.py's
# no-arg /start greeting).
SUPPORT_START_CALLBACK: Final[BotCallbackPrefix] = BotCallbackPrefix.SUPPORT_START

# Prompt shown when the support flow is entered (English source).
# ``gettext_lazy`` keeps the translation deferred until handler-run time so it
# resolves under the per-user locale (see contact.py), not the import-time
# ``settings.LANGUAGE_CODE``.
SUPPORT_PROMPT_MESSAGE: Final = gettext_lazy(
    "Write your question — we will reply as soon as possible."
)

# Shown when a user exceeds the support-message rate limit.
SUPPORT_RATE_LIMITED_MESSAGE: Final = gettext_lazy(
    "Too many requests to support. Please try again later."
)

# Shown when a submitted message is too long.
SUPPORT_MESSAGE_TOO_LONG_MESSAGE: Final = gettext_lazy(
    "Your message is too long. Please write no more than 4000 characters."
)

# Shown when the sender is not allowed to store personal data: an unregistered
# chat_id, or a registered account that has not consented / is blocked. The
# notice names the remedy (sign in and accept consent). No ticket is created.
SUPPORT_CONSENT_REQUIRED_MESSAGE: Final = gettext_lazy(
    "To contact support, please sign in and accept the personal data storage "
    "consent first."
)


@router.callback_query(F.data == SUPPORT_START_CALLBACK)
async def handle_support_start(
    callback: types.CallbackQuery, state: types.FSMContext
) -> None:
    """Enter the support intake flow from the "Contact support" button.

    Ordering mirrors ``contact.handle_contact_us_start`` (OQ1) with the
    storage-consent gate (06-PII-101) ahead of the rate limit: bots are rejected
    first (fail fast), then the gate refuses a sender who may not store personal
    data — before any rate budget is consumed — and only then is the per-user
    support-message rate limit applied, the FSM moved to ``AWAITING_MESSAGE`` and
    the user prompted. A sender who may not store personal data gets the consent
    notice instead of the prompt, so no message is invited that could never be
    persisted, and a refused sender is never told to "try again later".
    """
    await callback.answer()  # dismiss spinner

    if not callback.from_user or callback.from_user.is_bot:
        return  # OQ1: reject bots, never consume rate budget

    if callback.message is None:
        return  # No originating message to reply to

    if not await _actor_may_store(callback.from_user.id):
        await callback.message.answer(SUPPORT_CONSENT_REQUIRED_MESSAGE)
        return

    if not await check_support_message_rate_limit(callback.from_user.id):
        await callback.message.answer(SUPPORT_RATE_LIMITED_MESSAGE)
        return

    await state.set_state(ContactUsState.AWAITING_MESSAGE)
    await callback.message.answer(SUPPORT_PROMPT_MESSAGE)


@router.message(ContactUsState.AWAITING_MESSAGE)
async def handle_support_message(
    message: types.Message, bot: Bot, state: types.FSMContext
) -> None:
    """Persist the user's support message and deliver it to the support desk.

    Validates the input (bots rejected, empty text rejected, max length
    enforced), persists a ``SupportTicket`` via a single ``@sync_to_async`` ORM
    call (mirroring ``contact.handle_contact_orm`` under CONN_MAX_AGE=0), then
    delivers via email + Telegram and confirms with the generated ``ticket_ref``.

    The persistence call also enforces the storage-consent gate (06-PII-101):
    it resolves the actor server-side from the signed ``chat_id`` and refuses
    (returning ``None``) when the sender is unregistered, when the FSM
    ``user_id`` disagrees with the resolved actor, or when the actor may not
    store personal data. On refusal the consent notice is shown and no ticket is
    created.

    The FSM is reset back to ``IDLE`` once the message has been handled.
    """
    if not message.from_user or message.from_user.is_bot:
        return

    text = (message.text or "").strip()
    if not text:
        await message.answer(
            _("Please send your question as a text message.")
        )
        return

    if len(text) > SUPPORT_MESSAGE_MAX_LENGTH:
        await message.answer(SUPPORT_MESSAGE_TOO_LONG_MESSAGE)
        return

    # Attribute the ticket to the account resolved server-side from the signed
    # chat_id (06-PII-101). The FSM ``user_id`` is only a cross-check, never the
    # source of identity: a stale value must not let free text captured before
    # consent become a ticket.
    user_id: int | None = (await state.get_data()).get("user_id")

    ticket = await handle_support_orm(
        chat_id=message.chat.id,
        telegram_id=message.from_user.id,
        username=message.from_user.username,
        text=text,
        user_id=user_id,
    )

    if ticket is None:
        # Refused on the storage-consent gate: no ticket, no delivery.
        await message.answer(SUPPORT_CONSENT_REQUIRED_MESSAGE)
        await state.set_state(ContactUsState.IDLE)
        return

    bot_username = await _get_bot_username(bot)

    await send_support_notification_email(ticket, bot_username)
    active_contacts = await get_support_contacts_async()
    await send_support_notification_telegram(ticket, bot, active_contacts)

    await message.answer(
        _("Your request has been received. Reference: %(ref)s")
        % {"ref": ticket.ticket_ref}
    )

    await state.set_state(ContactUsState.IDLE)


async def handle_support_orm(
    chat_id: int,
    telegram_id: int,
    username: str | None,
    text: str,
    user_id: int | None,
):
    """Persist a ``SupportTicket`` in a single ``sync_to_async`` call.

    Mirrors ``contact.handle_contact_orm``: the whole ORM interaction runs on
    Django's sync worker thread in one call to reduce DB connection churn with
    CONN_MAX_AGE=0. The ``ticket_ref`` is generated in the model's ``save()``
    override; the returned instance carries it for the confirmation reply.

    The actor is resolved server-side from the Telegram-signed ``chat_id`` — the
    same key ``AccountStateMiddleware._resolve_user`` uses — so no
    client-supplied identity can attribute a ticket. Returns ``None`` (refusal)
    when:

    - the ``chat_id`` resolves to no ``User`` (unregistered sender), or
    - the FSM ``user_id`` is present but differs from the resolved actor (a
      stale FSM captured before consent), or
    - ``can_store_personal_data`` is false (no granted consent, or blocked).

    A ``None`` return is the single refusal signal; the caller shows the consent
    notice and creates no ticket.
    """
    from apps.core.enums import SupportTicketStatus
    from apps.core.models import SupportTicket
    from apps.users.models import User
    from apps.users.services.account_state import can_store_personal_data

    @sync_to_async
    def _create() -> SupportTicket | None:
        try:
            user = User.objects.get(chat_id=chat_id)
        except User.DoesNotExist:
            return None  # Unregistered sender: refuse.
        if user_id is not None and user_id != user.id:
            return None  # Stale FSM identity: refuse.
        if not can_store_personal_data(user):
            return None  # No storage consent (or blocked): refuse.
        return SupportTicket.objects.create(
            user=user,
            chat_id=chat_id,
            telegram_id=telegram_id,
            username=username,
            text=text,
            status=SupportTicketStatus.OPEN,
        )

    return await _create()


async def _actor_may_store(chat_id: int) -> bool:
    """Whether the signed ``chat_id`` resolves to a user who may store data.

    Single-resolution gate used by ``handle_support_start`` before inviting a
    message. Resolves server-side (never from client input) and delegates to
    ``can_store_personal_data`` (06-PII-101). An unregistered ``chat_id`` is a
    refusal.
    """
    from apps.users.models import User
    from apps.users.services.account_state import can_store_personal_data

    @sync_to_async
    def _check() -> bool:
        try:
            user = User.objects.get(chat_id=chat_id)
        except User.DoesNotExist:
            return False
        return can_store_personal_data(user)

    return await _check()


async def _get_bot_username(bot: Bot) -> str:
    """Return the bot's Telegram username, or an empty string if unavailable.

    Resolved via ``bot.get_me()``; never raises so support delivery is not
    disrupted by a temporary API failure.
    """
    try:
        me = await bot.get_me()
        return me.username or ""
    except Exception:
        logger.exception("Failed to resolve bot username for support delivery")
        return ""
