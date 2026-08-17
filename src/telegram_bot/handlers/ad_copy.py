"""
Copy Ad command handler for Telegram bot.

Allows sellers to create a new draft ad based on an existing one.
Usage: /copy <ad_id>
"""

import logging

from asgiref.sync import sync_to_async

from aiogram import Router, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext

from apps.ads.services.copy_service import copy_ad
from telegram_bot.states import AdCreateState

logger = logging.getLogger(__name__)

router = Router()


@router.message(Command("copy"))
async def cmd_copy(message: types.Message, state: FSMContext) -> None:
    """Copy an existing ad. Usage: /copy <ad_id>"""
    if not message.from_user:
        return

    # Check if user is logged in
    data = await state.get_data()
    user_id = data.get("user_id")
    if not user_id:
        await message.answer("Please login first with /start login_<token>")
        return

    # Parse ad_id from command
    args = (message.text or "").strip().split(maxsplit=1)
    if len(args) < 2:
        await message.answer("Usage: /copy <ad_id>")
        return

    try:
        ad_id = int(args[1])
    except ValueError:
        await message.answer("Invalid ad ID. Usage: /copy <ad_id>")
        return

    try:
        new_ad = await sync_to_async(copy_ad)(ad_id, user_id)
        logger.info("Ad %d copied to draft %d by user %d", ad_id, new_ad.id, user_id)
    except PermissionError:
        await message.answer("You can only copy your own ads.")
        return
    except Exception as e:
        logger.exception("Failed to copy ad %d for user %d", ad_id, user_id)
        await message.answer(f"Failed to copy ad: {e}")
        return

    # Set FSM state to purpose selection (pre-filled from copy)
    await state.set_state(AdCreateState.PURPOSE)
    await state.update_data(
        ad_id=new_ad.id,
        category_id=new_ad.category_id,
        listing_purpose_id=new_ad.listing_purpose_id,
        title=new_ad.title,
        description=new_ad.description,
        price=new_ad.price,
    )

    await message.answer(
        f"✅ Ad #{ad_id} copied to draft #{new_ad.id}.\n\n"
        f"Title: {new_ad.title}\n"
        f"Category: {new_ad.category.name if new_ad.category_id else 'N/A'}\n\n"
        "You can now change the listing purpose, price, title, and description.\n"
        "Send /cancel to abort.\n\n"
        "Use /post to start fresh or continue editing."
    )
