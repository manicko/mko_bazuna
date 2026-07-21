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

from aiogram import Bot, types
from asgiref.sync import sync_to_async

logger = logging.getLogger(__name__)

# Deep-link pattern: contact_<ad_id>
CONTACT_PATTERN = re.compile(r"^contact_(\d+)$")


async def handle_contact_start(
    message: types.Message, bot: Bot, deep_link: str
) -> bool:
    """
    Check if deep-link is a contact pattern and handle it.

    Pattern: /start contact_<ad_id>

    Returns True if handled as contact deep-link, False otherwise.

    Zone R2 conditions enforced:
        - ad.status == PUBLISHED
        - seller.telegram_id IS NOT NULL
        - NOT seller.is_deleted
        - NOT seller.is_banned
        - seller.consent_revoked_at IS NULL

    Bot messages:
        - ad missing/not PUBLISHED -> "объявление больше недоступно"
        - seller unavailable -> "продавец больше недоступен для связи"
    """
    match = CONTACT_PATTERN.match(deep_link)
    if not match:
        return False  # Not a contact deep-link

    ad_id = int(match.group(1))
    return await handle_contact(message, bot, ad_id)


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
        await message.answer("Ошибка: не удалось определить отправителя")
        return True

    buyer_telegram_id = message.from_user.id

    # Combined ORM: check seller availability + record analytics
    is_available, seller_telegram_id = await handle_contact_orm(
        ad_id=ad_id,
        buyer_telegram_id=buyer_telegram_id,
    )

    if not is_available:
        await message.answer("объявление больше недоступно")
        return True

    if seller_telegram_id is None:
        await message.answer("продавец больше недоступен для связи")
        return True

    # Send anonymous message to seller
    await bot.send_message(
        chat_id=seller_telegram_id,
        text=(
            f"Новый запрос от покупателя!\n\n"
            f"Покупатель: {ANONYMOUS_BUYER_LABEL}\n"
            f"Ad ID: {ad_id}\n\n"
            f"Напишите своё сообщение — оно будет переслано анонимно."
        ),
    )

    # Confirm to buyer
    await message.answer(
        "Ваш запрос отправлен продавцу анонимно. Ожидайте ответа в этом чате."
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
    from apps.core.services.contact import get_seller_for_contact, record_contact_initiated

    @sync_to_async
    def _handle() -> tuple[bool, int | None]:
        is_available, seller = get_seller_for_contact(ad_id)
        seller_telegram_id: int | None = seller.telegram_id if seller else None

        record_contact_initiated(buyer_telegram_id)

        return (is_available, seller_telegram_id)

    return await _handle()


ANONYMOUS_BUYER_LABEL = "Покупатель"
