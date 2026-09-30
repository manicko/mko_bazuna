"""
Near-real-time publish-time alert delivery (AL-001) + per-ad Telegram message
builder (AL-002).

Flow (Approach 1, per alert-delivery-research):
    ``Ad.post_save(PUBLISHED)`` -> ``transaction.on_commit`` ->
    ``deliver_immediate_alerts(ad_id)`` -> ad-centric matcher ->
    idempotent ``SavedSearchNotification`` recording -> background daemon thread
    ``asyncio.run(Bot(...))`` send capped by ``asyncio.Semaphore(10)``.

Delivery state (03-DB-007): a ``SavedSearchNotification`` row is an ATTEMPT
RECORD and ``delivered_at`` is the receipt. ``find_matching_saved_searches``
excludes only pairs whose alert was already DELIVERED, and the receipt is
written AFTER a successful send (``notification_delivery.mark_delivered``), so a
recorded-but-undelivered pair stays eligible and is retried by the daily
``send_alerts`` command rather than lost. Users without a stable ``chat_id`` are
never recorded (A4/C8); their pair stays collectable.
"""

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Final

from aiogram import Bot
from aiogram.exceptions import (
    AiogramError,
    TelegramBadRequest,
    TelegramForbiddenError,
    TelegramNetworkError,
    TelegramRetryAfter,
    TelegramServerError,
)
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from django.conf import settings
from django.utils import timezone
from django.utils.translation import gettext as _, override as translation_override

from apps.ads.models import Ad
from apps.ads.templatetags.price_tags import format_price_value
from apps.core.enums import AdStatus, LanguageLocale
from apps.search.models import SavedSearch
from apps.search.services.alert_query import (
    find_matching_saved_searches,
    record_notifications,
)

logger = logging.getLogger(__name__)

# Telegram fan-out safety cap (R2).
_SEND_CONCURRENCY: Final[int] = 10

# Capped backoff base (seconds) for transient retries (429/network/5xx).
_BACKOFF_BASE: Final[float] = 0.5

# Bounded thread pool: caps concurrent delivery daemon threads globally.
# Replaces unbounded threading.Thread (one per published ad burst).
_MAX_DELIVERY_THREADS: Final[int] = 5
_executor: ThreadPoolExecutor = ThreadPoolExecutor(
    max_workers=_MAX_DELIVERY_THREADS,
    thread_name_prefix="immediate-alert-send",
)

# Inline callback prefix for unsubscribe (callback_data="unsub:<token>").
# Defined as a backend-native string constant to avoid a backend→bot dependency
# reversal (QLT-002 added BotCallbackPrefix.UNSUB to the bot enum; the bot
# layer independently owns its enum, and test_callbacks.py guards against drift).
UNSUB_CALLBACK_PREFIX: Final[str] = "unsub:"


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
    ad = (
        Ad.objects.filter(id=ad_id, status=AdStatus.PUBLISHED)
        .select_related("city", "category")
        .first()
    )
    if ad is None:
        logger.warning(
            "Ad %s not found or not PUBLISHED - skipping immediate alerts", ad_id
        )
        return

    searches = find_matching_saved_searches(ad)
    if not searches:
        return

    # Build payloads FIRST, for users with a stable chat_id (A4), and drop the
    # Nones. Recording happens only for the pairs that actually produced a
    # payload, so a user with no chat_id is never recorded and the pair stays
    # collectable (03-DB-007 D-1).
    payloads = [p for p in (_build_payload(ad, ss) for ss in searches) if p is not None]

    if not payloads:
        return

    # Record attempts idempotently for the pairs that will actually be sent.
    for saved_search in searches:
        if saved_search.pk not in _payload_ss_ids(payloads):
            continue
        record_notifications(saved_search, [ad])
        saved_search.last_notified_at = timezone.now()
        saved_search.save(update_fields=["last_notified_at", "updated_at"])

    # Dispatch to the bounded global thread pool so concurrent publish
    # bursts never exceed _MAX_DELIVERY_THREADS daemon threads.
    _executor.submit(_run_send, payloads)


def _payload_ss_ids(payloads: list[dict]) -> set[int]:
    """Return the set of ``saved_search_id``s represented in the payloads."""
    return {ss_id for ss_id, _ad_id in (p["pair"] for p in payloads)}


async def _mark_delivered(pair: tuple[int, int]) -> None:
    """Record the delivery receipt for ``pair`` from the send thread (03-DB-007).

    ``mark_delivered`` is a synchronous, single-statement ORM call, so it is
    bridged into the event loop with ``sync_to_async``. The mark is written
    AFTER ``send_message`` succeeds and BEFORE the ``except`` clauses, so a
    failed send leaves the pair undelivered and therefore retryable. No
    signature, return-value or exception-handling change.
    """
    from asgiref.sync import sync_to_async

    from apps.search.services.notification_delivery import mark_delivered

    saved_search_id, ad_id = pair
    await sync_to_async(mark_delivered)(
        saved_search_id, ad_id, sent_at=timezone.now()
    )


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
        price_str = format_price_value(ad.price_amount, ad.price_currency) or _(
            "Price not specified"
        )
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
        # Non-serialised side-channel used only for the post-send delivery mark.
        "pair": (saved_search.pk, ad.pk),
    }


def _run_send(payloads: list[dict]) -> None:
    """Run the async send loop for the collected payloads in this thread."""
    try:
        asyncio.run(_send_payloads(settings.BOT_TOKEN, payloads))
    except AiogramError as exc:
        logger.error("Immediate alert send failed: %s", exc)


async def _send_payloads(bot_token: str, payloads: list[dict]) -> None:
    """Send all payloads concurrently, capped by ``asyncio.Semaphore``.

    One Bot is constructed per thread/event-loop and reused across all
    payloads in the batch, then closed once in finally (mirrors
    ``send_alerts.py`` ``_send_user_digests``).
    """
    sem = asyncio.Semaphore(_SEND_CONCURRENCY)
    bot = Bot(token=bot_token)
    try:
        async def _send(payload: dict) -> None:
            async with sem:
                try:
                    await bot.send_message(
                        chat_id=payload["chat_id"],
                        text=payload["text"],
                        parse_mode="HTML",
                        reply_markup=payload["reply_markup"],
                    )
                    await _mark_delivered(payload["pair"])
                except (TelegramBadRequest, TelegramForbiddenError) as exc:
                    # Permanent failures — dead-letter (no retry).
                    logger.warning(
                        "Permanent immediate alert failure to chat %s: %s",
                        payload["chat_id"],
                        exc,
                    )
                except (
                    TelegramRetryAfter,
                    TelegramNetworkError,
                    TelegramServerError,
                ) as exc:
                    # Transient failures — retry once with capped backoff.
                    if isinstance(exc, TelegramRetryAfter) and exc.retry_after:
                        backoff: float = float(exc.retry_after)
                    else:
                        backoff = _BACKOFF_BASE
                    await asyncio.sleep(backoff)
                    try:
                        await bot.send_message(
                            chat_id=payload["chat_id"],
                            text=payload["text"],
                            parse_mode="HTML",
                            reply_markup=payload["reply_markup"],
                        )
                    except AiogramError as retry_exc:
                        logger.warning(
                            "Immediate alert retry failed to chat %s: %s",
                            payload["chat_id"],
                            retry_exc,
                        )

        await asyncio.gather(
            *(_send(p) for p in payloads),
            return_exceptions=True,
        )
    finally:
        await bot.session.close()
