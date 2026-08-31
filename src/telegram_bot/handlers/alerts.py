"""
Saved search alerts handler for Telegram bot.

Hosts the /alerts management command and the inline-callback unsubscribe
(AL-002): ``callback_data="unsub:<token>"`` disables a search owned by the
pressing user (via stable ``chat_id``) and swaps the button to re-enable;
``"unsub_on:<token>"`` re-enables it. Deep-link ``/start unsub_<token>`` is
the secondary unsubscribe mechanism (delegated from login.py).
"""

import logging
import re

from aiogram import F, Router, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from asgiref.sync import sync_to_async

from apps.search.models import SavedSearch
from apps.search.services.immediate_alerts import UNSUB_CALLBACK_PREFIX

logger = logging.getLogger(__name__)

router = Router()

# Deep-link pattern: unsub_<32-char-token>
UNSUB_DEEPLINK_PATTERN = re.compile(r"^unsub_([A-Za-z0-9_-]{32})$")

# Re-enable callback prefix (complements the "Отключить" button).
UNSUB_ON_PREFIX = "unsub_on:"


@router.message(Command("alerts"))
async def cmd_alerts(message: types.Message, state: FSMContext) -> None:
    """
    List saved searches for alert management.

    Displays all saved searches for the current user with their
    active status, filters (query, city, category, price), and
    allows toggling individual alerts.
    """
    if not message.from_user:
        return

    data = await state.get_data()
    user_id = data.get("user_id")

    if not user_id:
        await message.answer("Please login first with /start login_<token>")
        return

    saved_searches = await get_user_saved_searches(user_id)

    if not saved_searches:
        await message.answer(
            "You have no saved searches.\n"
            "Saved searches will appear here once created via the web interface."
        )
        return

    lines = ["Your saved searches:"]
    for i, ss in enumerate(saved_searches, 1):
        status = "ON" if ss.is_active else "OFF"
        query_display = ss.query or "any"
        city_display = ss.city.name if ss.city else "any"
        cat_display = ss.category.name if ss.category else "any"

        price_display = "any"
        if ss.min_price or ss.max_price:
            parts = []
            if ss.min_price:
                parts.append(f"≥{ss.min_price}")
            if ss.max_price:
                parts.append(f"≤{ss.max_price}")
            price_display = " ".join(parts)

        lines.append(
            f"{i}. [{status}] {query_display[:30]}\n"
            f"   City: {city_display}, Category: {cat_display}, "
            f"Price: {price_display}"
        )

    lines.append("\nReply with number to toggle, or /cancel to exit.")
    await message.answer("\n".join(lines))


@sync_to_async
def get_user_saved_searches(user_id: int) -> list[SavedSearch]:
    """Get all saved searches for a user, ordered by creation date."""
    return list(
        SavedSearch.objects.filter(user_id=user_id)
        .select_related("city", "category")
        .order_by("-created_at")
    )


# ---------------------------------------------------------------------------
# Inline-callback unsubscribe / re-enable (AL-002, CR10)
# ---------------------------------------------------------------------------


@router.callback_query(F.data.startswith(UNSUB_CALLBACK_PREFIX))
async def handle_unsubscribe_callback(
    callback: types.CallbackQuery, bot: types.Bot
) -> None:
    """Disable a saved search from an inline button, verifying ownership.

    ``callback_data="unsub:<token>"``. The pressing user must own the search
    (matched via the stable ``chat_id``, never ``telegram_id`` — R5/F4/A4).
    """
    if not callback.data:
        return
    token = callback.data[len(UNSUB_CALLBACK_PREFIX) :]
    chat_id = callback.from_user.id if callback.from_user else None

    saved_search = await resolve_unsubscribe(token, chat_id)
    if saved_search is None:
        await callback.answer("Не удалось отключить уведомления")
        return

    if callback.message is not None:
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="Включить уведомления",
                        callback_data=f"{UNSUB_ON_PREFIX}{token}",
                    ),
                ],
            ]
        )
        await bot.edit_message_reply_markup(
            chat_id=callback.message.chat.id,
            message_id=callback.message.message_id,
            reply_markup=keyboard,
        )
    await callback.answer("Уведомления отключены")


@router.callback_query(F.data.startswith(UNSUB_ON_PREFIX))
async def handle_reenable_callback(
    callback: types.CallbackQuery, bot: types.Bot
) -> None:
    """Re-enable a saved search from the swapped inline button."""
    if not callback.data:
        return
    token = callback.data[len(UNSUB_ON_PREFIX) :]
    chat_id = callback.from_user.id if callback.from_user else None

    saved_search = await resolve_reenable(token, chat_id)
    if saved_search is None:
        await callback.answer("Не удалось включить уведомления")
        return

    if callback.message is not None:
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="🔕 Отключить этот поиск",
                        callback_data=f"{UNSUB_CALLBACK_PREFIX}{token}",
                    ),
                ],
            ]
        )
        await bot.edit_message_reply_markup(
            chat_id=callback.message.chat.id,
            message_id=callback.message.message_id,
            reply_markup=keyboard,
        )
    await callback.answer("Уведомления включены")


# ---------------------------------------------------------------------------
# Deep-link unsubscribe (secondary mechanism, CR10 / Q4 minimal scope)
# ---------------------------------------------------------------------------


async def handle_unsubscribe_start(
    message: types.Message, bot: types.Bot, deep_link: str
) -> bool:
    """Handle a ``/start unsub_<token>`` deep link.

    Returns True when the deep link is an unsubscribe link (handled), False
    otherwise. Minimal scope (Q4): show the result + a re-enable hint; no
    "run search now"/list-others UI.
    """
    match = UNSUB_DEEPLINK_PATTERN.match(deep_link)
    if not match:
        return False

    token = match.group(1)
    chat_id = message.from_user.id if message.from_user else None

    saved_search = await resolve_unsubscribe(token, chat_id) if chat_id else None
    if saved_search is None:
        await message.answer(
            "Эта ссылка недействительна или не относится к вашим поискам."
        )
    else:
        await message.answer(
            "Уведомления отключены для этого сохранённого поиска.\n"
            "Чтобы включить их снова, используйте /alerts."
        )
    return True


@sync_to_async
def resolve_unsubscribe(token: str, chat_id: int | None) -> SavedSearch | None:
    """Disable the search owned by ``chat_id`` for ``token``.

    Returns the (now-inactive) SavedSearch when the caller owns it, else None
    (unknown token or not the owner — no state is leaked).
    """
    return _resolve_owned(token, chat_id, active=False)


@sync_to_async
def resolve_reenable(token: str, chat_id: int | None) -> SavedSearch | None:
    """Re-enable the search owned by ``chat_id`` for ``token``."""
    return _resolve_owned(token, chat_id, active=True)


def _resolve_owned(token: str, chat_id: int | None, active: bool) -> SavedSearch | None:
    if not chat_id:
        return None
    try:
        saved_search = SavedSearch.objects.select_related("user").get(
            unsubscribe_token=token
        )
    except SavedSearch.DoesNotExist:
        return None

    # Ownership via the stable, never-nullified chat_id (R5/F4/A4).
    if saved_search.user.chat_id != chat_id:
        return None

    saved_search.is_active = active
    saved_search.save(update_fields=["is_active", "updated_at"])
    logger.info(
        "Saved search %s for user %s set active=%s via Telegram",
        saved_search.pk,
        saved_search.user_id,
        active,
    )
    return saved_search
