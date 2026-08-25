"""
Near-real-time publish-time alert delivery (AL-001) + per-ad Telegram message
builder (AL-002).

Flow (Approach 1, per alert-delivery-research):
    ``Ad.post_save(PUBLISHED)`` -> ``transaction.on_commit`` ->
    ``deliver_immediate_alerts(ad_id)`` -> ad-centric matcher ->
    idempotent ``SavedSearchNotification`` recording -> background daemon thread
    ``asyncio.run(Bot(...))`` send capped by ``asyncio.Semaphore(10)``.

Delivery is idempotent via ``uq_saved_search_ad`` + ``ignore_conflicts``, so
the daily ``send_alerts`` command never double-sends; users without a stable
``chat_id`` are logged and skipped (A4/C8).
"""

import asyncio
import logging
import threading

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from apps.ads.models import Ad
from apps.ads.templatetags.price_tags import format_price_value
from apps.core.enums import AdStatus, LanguageLocale
from apps.search.models import SavedSearch
from apps.search.services.alert_query import (
    find_matching_saved_searches,
    record_notifications,
)
from django.conf import settings
from django.utils import timezone
from django.utils.translation import gettext as _, override as translation_override

logger = logging.getLogger(__name__)

# Telegram fan-out safety cap (R2).
_SEND_CONCURRENCY = 10

# Inline callback prefix for unsubscribe (callback_data="unsub:<token>").
UNSUB_CALLBACK_PREFIX = "unsub:"


def deliver_immediate_alerts(ad_id: int) -> None:
    """
    Deliver near-real-time Telegram alerts for a just-published ad.

    Matches active saved searches for the ad, records notifications
    idempotently, and sends one per-ad message to each matching user with a
    stable ``chat_id`` in a background daemon thread.

    Must be called from within the ad's transaction via
    ``transaction.on_commit`` so delivery only fires after the PUBLISHED
    commit (F6/F8/R3).

    Args:
        ad_id: Primary key of the PUBLISHED ad.
    """
    ad = Ad.objects.filter(
        id=ad_id, status=AdStatus.PUBLISHED
    ).select_related("city", "category").first()
    if ad is None:
        logger.warning("Ad %s not found or not PUBLISHED - skipping immediate alerts", ad_id)
        return

    searches = find_matching_saved_searches(ad)
    if not searches:
        return

    # Record notifications idempotently so the daily command never double-sends.
    for saved_search in searches:
        record_notifications(saved_search, [ad])
        saved_search.last_notified_at = timezone.now()
        saved_search.save(update_fields=["last_notified_at", "updated_at"])

    # Build payloads only for users with a stable chat_id (A4).
    payloads = [_build_payload(ad, ss) for ss in searches]
    payloads = [p for p in payloads if p is not None]

    if not payloads:
        return

    thread = threading.Thread(
        target=_run_send,
        args=(payloads,),
        daemon=True,
        name="immediate-alert-send",
    )
    thread.start()


def build_alert_message(
    ad: Ad, saved_search: SavedSearch, locale: str = LanguageLocale.RUSSIAN.value
) -> tuple[str, InlineKeyboardMarkup]:
    """
    Build the per-ad Telegram alert message (CR9).

    Shows title, city, and price in the recipient's preferred language, plus an
    absolute ``[View ad]`` link (via ``settings.SITE_URL`` +
    ``Ad.get_absolute_url``) and a ``[Disable this search]`` inline callback button
    carrying the search's opaque ``unsubscribe_token``.

    Args:
        ad: The published ad.
        saved_search: The saved search that matched.
        locale: Language code for the recipient's preferred language.

    Returns:
        A tuple of (message_text, reply_markup).
    """
    with translation_override(locale):
        title = ad.get_title(locale) or _("Ad")
        city_name = ad.city.get_name(locale) if ad.city else "—"
        price_str = format_price_value(ad.price_amount, ad.price_currency) or _("Price not specified")
        view_ad_label = _("View ad")
        disable_search_label = _("🔕 Disable this search")

        lines = [
            f"<b>{title}</b>",
            f"📍 {city_name}",
            f"💰 {price_str}",
            "",
            f'<a href="{ad.get_absolute_url()}">{view_ad_label}</a>',
        ]

        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text=disable_search_label,
                        callback_data=f"{UNSUB_CALLBACK_PREFIX}{saved_search.unsubscribe_token}",
                    ),
                ],
            ]
        )
    return "\n".join(lines), keyboard


def _build_payload(ad: Ad, saved_search: SavedSearch) -> dict | None:
    """Build a send payload for one saved search, or None when skipped."""
    user = saved_search.user
    if not user.chat_id:
        logger.warning(
            "User %s has no chat_id - skipping immediate alert for search %s",
            saved_search.user_id,
            saved_search.pk,
        )
        return None
    locale = getattr(user, "telegram_language", None) or LanguageLocale.RUSSIAN.value
    text, reply_markup = build_alert_message(ad, saved_search, locale=locale)
    return {
        "chat_id": user.chat_id,
        "text": text,
        "reply_markup": reply_markup,
    }


def _run_send(payloads: list[dict]) -> None:
    """Run the async send loop for the collected payloads in this thread."""
    try:
        asyncio.run(_send_payloads(settings.BOT_TOKEN, payloads))
    except Exception as exc:  # pragma: no cover - defensive
        logger.error("Immediate alert send failed: %s", exc)


async def _send_payloads(bot_token: str, payloads: list[dict]) -> None:
    """Send all payloads concurrently, capped by ``asyncio.Semaphore``."""
    sem = asyncio.Semaphore(_SEND_CONCURRENCY)

    async def _send(payload: dict) -> None:
        async with sem:
            bot = Bot(token=bot_token)
            try:
                await bot.send_message(
                    chat_id=payload["chat_id"],
                    text=payload["text"],
                    parse_mode="HTML",
                    reply_markup=payload["reply_markup"],
                )
            except (TelegramBadRequest, TelegramForbiddenError) as exc:
                logger.warning(
                    "Failed to send immediate alert to chat %s: %s",
                    payload["chat_id"],
                    exc,
                )
            finally:
                await bot.session.close()

    await asyncio.gather(*(_send(p) for p in payloads))
