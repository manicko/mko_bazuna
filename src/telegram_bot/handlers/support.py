"""
Support message intake handler for Telegram bot.

Implements the support-desk flow (EC-9): a user taps the "Contact support"
button on the ``/start`` greeting (``BotCallbackPrefix.SUPPORT_START``) and is
prompted to write their question. The free-text reply is persisted as a
``SupportTicket`` and delivered to the configured support channels (email +
Telegram) so the desk can reply out-of-band.

Access control is governed by ``AccountStateMiddleware`` (anonymous + DECLINE
users may reach support; banned/deleted/consent-revoked users are blocked
before the handler runs). The handler itself only guards against bots, mirroring
``contact.py``.
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


@router.callback_query(F.data == SUPPORT_START_CALLBACK)
async def handle_support_start(
    callback: types.CallbackQuery, state: types.FSMContext
) -> None:
    """Enter the support intake flow from the "Contact support" button.

    Ordering mirrors ``contact.handle_contact_us_start`` (OQ1): bots are
    rejected first (fail fast, never consuming rate budget), then the per-user
    support-message rate limit is applied, then the FSM is moved to
    ``AWAITING_MESSAGE`` and the user is prompted for their question.
    """
    await callback.answer()  # dismiss spinner

    if not callback.from_user or callback.from_user.is_bot:
        return  # OQ1: reject bots, never consume rate budget

    if callback.message is None:
        return  # No originating message to reply to

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

    # Attribute the ticket to the authenticated user when available (the
    # AccountStateMiddleware backfills ``user_id`` into FSM state for
    # registered users); anonymous senders leave ``user`` null.
    user_id: int | None = (await state.get_data()).get("user_id")

    ticket = await handle_support_orm(
        chat_id=message.chat.id,
        telegram_id=message.from_user.id,
        username=message.from_user.username,
        text=text,
        user_id=user_id,
    )

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
    """
    from apps.core.enums import SupportTicketStatus
    from apps.core.models import SupportTicket

    @sync_to_async
    def _create() -> SupportTicket:
        user = None
        if user_id is not None:
            from apps.users.models import User

            try:
                user = User.objects.get(id=user_id)
            except User.DoesNotExist:
                user = None
        return SupportTicket.objects.create(
            user=user,
            chat_id=chat_id,
            telegram_id=telegram_id,
            username=username,
            text=text,
            status=SupportTicketStatus.OPEN,
        )

    return await _create()


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
