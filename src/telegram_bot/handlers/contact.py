"""
Anonymous contact handler for Telegram bot.

Handles buyer-to-seller contact via deep-link without PII exposure.
The seller notification uses a fixed anonymous label ("Покупатель")
instead of the buyer's real name. The buyer may disclose their identity
voluntarily in the free-text message.
Implements zone R2 conditions and anonymous forwarding.
"""

import logging
import re
from enum import StrEnum
from typing import Final

from aiogram import Bot, F, Router, types
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from asgiref.sync import sync_to_async
from django.utils.translation import gettext as _

from telegram_bot.services.rate_limit import check_contact_start_rate_limit

logger = logging.getLogger(__name__)

router = Router()

# Deep-link patterns.
# /start contact_<ad_id> — anonymous buyer-to-seller contact.
CONTACT_PATTERN = re.compile(r"^contact_(\d+)$")
# /start contact_us — support desk deep-link for logged-out Telegram-bypass buyers.
CONTACT_US_PATTERN = re.compile(r"^contact_us$")

# Callback data for the inline "Contact us" button (shared with login.py's
# no-arg /start greeting).
CONTACT_US_CALLBACK: Final[str] = "contact_us"


class ContactDeepLinkKind(StrEnum):
    """Deep-link kinds that DECLINE users can access (browse-only contact)."""

    SELLER_CONTACT = "seller_contact"  # /start contact_<ad_id>
    SUPPORT_DESK = "support_desk"  # /start contact_us OR callback contact_us


def classify_contact_deep_link(
    text: str | None,
    callback_data: str | None = None,
) -> ContactDeepLinkKind | None:
    """Classify whether an event is a contact deep-link accessible to DECLINE users.

    Checks both message deep-links (``/start contact_<ad_id>``, ``/start contact_us``)
    and the inline "Contact us" button callback_data.  Returns the deep-link kind if
    it is a contact link, ``None`` otherwise.  Shared between the middleware and the
    handler so the two never drift on what constitutes a contact deep-link.
    """
    # Callback query: inline "Contact us" button
    if callback_data == CONTACT_US_CALLBACK:
        return ContactDeepLinkKind.SUPPORT_DESK
    # Message deep-link: /start <payload>
    if text is None:
        return None
    args = text.split(maxsplit=1)
    if len(args) < 2:
        return None
    deep_link = args[1]
    if CONTACT_US_PATTERN.match(deep_link):
        return ContactDeepLinkKind.SUPPORT_DESK
    if CONTACT_PATTERN.match(deep_link):
        return ContactDeepLinkKind.SELLER_CONTACT
    return None


# Greeting shown to buyers reaching the support desk (Russian, per contact.py
# convention). Shared by the /start contact_us deep-link and the inline button
# so both entry points produce identical output.
_CONTACT_US_GREETING: Final[str] = _(
    "👋 Привет! Вы связались со службой поддержки Bazuna.\n\n"
    "Напишите ваш вопрос — мы ответим как можно скорее.\n\n"
    "Для создания объявления используйте /post."
)

# Shown when a user exceeds the contact-start rate limit (OQ1).
CONTACT_US_RATE_LIMITED_MESSAGE: Final[str] = _(
    "Слишком много запросов в поддержку. Попробуйте позже."
)


async def handle_contact_start(
    message: types.Message, bot: Bot, deep_link: str
) -> bool:
    """
    Check if deep-link is a contact pattern and handle it.

    Patterns:
      - ``/start contact_us`` -> support desk greeting for logged-out buyers
        (Telegram-bypass users), with the inline "Contact us" button re-shower.
      - ``/start contact_<ad_id>`` -> anonymous buyer-to-seller contact.

    Returns True if handled as a contact deep-link, False otherwise.

    Zone R2 conditions enforced (contact_<ad_id> branch only):
        - ad.status == PUBLISHED
        - seller.telegram_id IS NOT NULL
        - NOT seller.is_deleted
        - NOT seller.is_banned
        - seller.consent_revoked_at IS NULL

    Bot messages (contact_<ad_id> branch):
        - ad missing/not PUBLISHED -> "объявление больше недоступно"
        - seller unavailable -> "продавец больше недоступен для связи"
    """
    if CONTACT_US_PATTERN.match(deep_link):
        return await handle_contact_us_start(message, bot)

    match = CONTACT_PATTERN.match(deep_link)
    if not match:
        return False  # Not a contact deep-link

    ad_id = int(match.group(1))
    return await handle_contact(message, bot, ad_id)


def _contact_us_keyboard() -> InlineKeyboardMarkup:
    """Inline 'Contact us' keyboard — shared by the deep-link and the callback.

    Using a single builder (with ``CONTACT_US_CALLBACK``) guarantees the
    keyboard and the ``F.data`` filter can never drift apart.
    """
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=_("Contact us"),
                    callback_data=CONTACT_US_CALLBACK,
                ),
            ],
        ],
    )


async def handle_contact_us_start(message: types.Message, bot: Bot) -> bool:
    """Handle ``/start contact_us`` deep-link for logged-out Telegram-bypass users.

    OQ1 ordering — bots are rejected first (fail fast, never consuming rate
    budget), then the per-user contact-start rate limit is applied, and finally
    the buyer is greeted with the shared support desk message + keyboard.

    Always returns True: the ``contact_us`` deep-link is fully handled here and
    must short-circuit ``login.handle_login_deep_link``.
    """
    if not message.from_user:
        return True
    if message.from_user.is_bot:
        return True  # OQ1: reject bots, never consume rate budget
    if not await check_contact_start_rate_limit(message.from_user.id):
        await message.answer(CONTACT_US_RATE_LIMITED_MESSAGE)
        return True
    await message.answer(_CONTACT_US_GREETING, reply_markup=_contact_us_keyboard())
    return True


@router.callback_query(F.data == CONTACT_US_CALLBACK)
async def handle_contact_us_callback(callback: types.CallbackQuery, bot: Bot) -> None:
    """Inline 'Contact us' button for Telegram-bypass users — same greeting.

    Mirrors ``alerts.handle_unsubscribe_callback`` (alerts.py:103-138):
    answer the callback first to dismiss the spinner, then edit the originating
    message to the shared support desk greeting. ``bot`` is accepted for
    signature parity with the other callback handlers.
    """
    await callback.answer()  # dismiss spinner
    if callback.message is not None:
        await callback.message.edit_text(
            _CONTACT_US_GREETING, reply_markup=_contact_us_keyboard()
        )


async def handle_contact(message: types.Message, bot: Bot, ad_id: int) -> bool:
    """
    Handle contact deep-link for anonymous buyer-seller communication.

    The seller notification uses a fixed anonymous label ("Покупатель")
    instead of the buyer's real name. The buyer may disclose their identity
    voluntarily in the free-text message.

    Zone R2 conditions enforced:
        - ad.status == PUBLISHED
        - seller.telegram_id IS NOT NULL
        - NOT seller.is_deleted
        - NOT seller.is_banned
        - seller.consent_revoked_at IS NULL

    Returns True if contact was handled, False if not available.

    Bot messages:
        - ad missing/not PUBLISHED -> "объявление больше недоступно"
        - seller unavailable -> "продавец больше недоступен для связи"
    """
    if not message.from_user:
        await message.answer(_("Ошибка: не удалось определить отправителя"))
        return True

    buyer_telegram_id = message.from_user.id

    # Combined ORM: check seller availability + record analytics
    is_available, seller_telegram_id = await handle_contact_orm(
        ad_id=ad_id,
        buyer_telegram_id=buyer_telegram_id,
    )

    if not is_available:
        await message.answer(_("объявление больше недоступно"))
        return True

    if seller_telegram_id is None:
        await message.answer(_("продавец больше недоступен для связи"))
        return True

    # Send anonymous message to seller
    await bot.send_message(
        chat_id=seller_telegram_id,
        text=(
            _(
                "Новый запрос от покупателя!\n\n"
                "Покупатель: %(buyer)s\n"
                "Ad ID: %(ad_id)s\n\n"
                "Напишите своё сообщение — оно будет переслано анонимно."
            )
            % {"buyer": ANONYMOUS_BUYER_LABEL, "ad_id": ad_id}
        ),
    )

    # Confirm to buyer
    await message.answer(
        _("Ваш запрос отправлен продавцу анонимно. Ожидайте ответа в этом чате.")
    )
    return True


async def handle_contact_orm(
    ad_id: int,
    buyer_telegram_id: int | None,
) -> tuple[bool, int | None]:
    """
    Check seller availability and record contact analytics event.

    Delegates R2 gating to core.services.contact.get_seller_for_contact()
    and analytics recording to core.services.contact.record_contact_initiated().

    Wraps both in a single sync_to_async call to reduce DB connection churn
    with CONN_MAX_AGE=0.

    Zone R2 conditions:
        - ad.status == PUBLISHED
        - seller.telegram_id IS NOT NULL
        - NOT seller.is_deleted
        - NOT seller.is_banned
        - seller.consent_revoked_at IS NULL

    Args:
        ad_id: The ad ID to check.
        buyer_telegram_id: The buyer's Telegram ID (may be None).

    Returns:
        Tuple of (is_available, seller_telegram_id or None).
    """
    from apps.core.services.contact import (
        get_seller_for_contact,
        record_contact_initiated,
    )

    @sync_to_async
    def _handle() -> tuple[bool, int | None]:
        is_available, seller = get_seller_for_contact(ad_id)
        seller_telegram_id: int | None = seller.telegram_id if seller else None

        record_contact_initiated(buyer_telegram_id)

        return (is_available, seller_telegram_id)

    return await _handle()


ANONYMOUS_BUYER_LABEL = _("Покупатель")
