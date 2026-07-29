"""
Saved search alerts handler for Telegram bot.

Allows users to list and manage their saved search queries
via the /alerts command.
"""

import logging

from aiogram import Router, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from asgiref.sync import sync_to_async

from apps.search.models import SavedSearch

logger = logging.getLogger(__name__)

router = Router()


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
        await message.answer(
            "Please login first with /start login_<token>"
        )
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