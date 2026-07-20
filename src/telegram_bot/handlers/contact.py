"""
Anonymous contact handler for Telegram bot.

Handles buyer-to-seller contact via deep-link without PII exposure.
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


async def handle_contact(
    message: types.Message, bot: Bot, ad_id: int
) -> bool:
    """
    Handle contact deep-link for anonymous buyer-seller communication.

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

    # Check seller availability and get seller telegram_id
    is_available, seller_telegram_id = await check_seller_available(ad_id)

    # Record contact attempt (analytics)
    await record_contact_event(buyer_telegram_id)

    if not is_available:
        await message.answer("объявление больше недоступно")
        return True

    if seller_telegram_id is None:
        await message.answer("продавец больше недоступен для связи")
        return True

    # Send anonymous message to seller
    buyer_name = _get_buyer_display_name(message.from_user)
    await bot.send_message(
        chat_id=seller_telegram_id,
        text=(
            f"Новый запрос от покупателя!\n\n"
            f"Покупатель: {buyer_name}\n"
            f"Ad ID: {ad_id}\n\n"
            f"Напишите своё сообщение — оно будет переслано анонимно."
        ),
    )

    # Confirm to buyer
    await message.answer(
        "Ваш запрос отправлен продавцу анонимно. "
        "Ожидайте ответа в этом чате."
    )
    return True


async def check_seller_available(ad_id: int) -> tuple[bool, int | None]:
    """
    Check if seller is available for contact.

    Zone R2 conditions:
        - ad.status == PUBLISHED
        - seller.telegram_id IS NOT NULL
        - NOT seller.is_deleted
        - NOT seller.is_banned
        - seller.consent_revoked_at IS NULL

    Args:
        ad_id: The ad ID to check.

    Returns:
        Tuple of (is_available, seller_telegram_id or None).
    """
    from apps.ads.models import Ad
    from apps.core.enums import AdStatus

    @sync_to_async
    def _check() -> tuple[bool, int | None]:
        try:
            ad = Ad.objects.select_related("user").get(id=ad_id)
        except Ad.DoesNotExist:
            logger.info(f"Ad {ad_id} not found for contact")
            return (False, None)

        if ad.status != AdStatus.PUBLISHED:
            logger.info(f"Ad {ad_id} not PUBLISHED (status={ad.status}) for contact")
            return (False, None)

        seller = ad.user
        if seller is None:
            logger.info(f"Ad {ad_id} has no seller")
            return (False, None)

        # Zone R2 conditions
        if seller.telegram_id is None:
            return (False, None)
        if seller.is_deleted:
            return (False, None)
        if seller.is_banned:
            return (False, None)
        if seller.consent_revoked_at is not None:
            return (False, None)

        return (True, seller.telegram_id)

    return await _check()


async def record_contact_event(buyer_telegram_id: int | None) -> None:
    """
    Record CONTACT_INITIATED analytics event.

    User field is nullable since buyer may not be authenticated.
    """
    from apps.analytics.models import AnalyticsEvent
    from apps.core.enums import AnalyticsEventType
    from apps.users.models import User

    @sync_to_async
    def _record() -> None:
        user_id = None
        if buyer_telegram_id is not None:
            try:
                user = User.objects.get(telegram_id=buyer_telegram_id)
                user_id = user.id
            except User.DoesNotExist:
                pass  # Buyer may not exist yet

        AnalyticsEvent.objects.create(
            event_type=AnalyticsEventType.CONTACT_INITIATED,
            user_id=user_id,
        )

    await _record()
    logger.info("Contact initiated event recorded")


def _get_buyer_display_name(user: types.User) -> str:
    """
    Get buyer display name without exposing Telegram username/ID.

    Uses first_name + last_name if available, otherwise "Покупатель".

    Args:
        user: Telegram user object.

    Returns:
        Display name string.
    """
    parts = []
    if user.first_name:
        parts.append(user.first_name)
    if user.last_name:
        parts.append(user.last_name)

    if parts:
        return " ".join(parts)
    return "Покупатель"