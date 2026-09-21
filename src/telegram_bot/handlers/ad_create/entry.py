"""Entry-point FSM handlers for the Telegram bot ad-creation flow.

Extracted verbatim from ``telegram_bot/handlers/ad_create/__init__.py``
(10-QLT-003 B16). ``cmd_post`` starts the ad creation flow when the seller sends
``/post``; ``cmd_cancel`` aborts mid-flow, cleaning up staging photos and the
DRAFT ad only when the ad is still in ``DRAFT`` status.

Shares the package-level ``router`` and ``AdCreateForm`` (imported, not
redefined) so both handlers register against the same Router instance.
"""

import asyncio
import logging

from aiogram import types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from django.utils.translation import gettext as _

from apps.core.enums import AdStatus
from apps.core.services.site_config import get_site_name_async
from apps.media.services.filesystem import delete_photo
from telegram_bot.handlers.ad_create import AdCreateForm, router
from telegram_bot.services.ad_data import (
    _get_ad_status,
    create_draft_ad,
    delete_draft,
)

# Explicit logger name — preserves the "telegram_bot.handlers.ad_create"
# logger that tests assert on via caplog (test_ad_create.py TestCancelAfterSubmit).
logger = logging.getLogger("telegram_bot.handlers.ad_create")


@router.message(Command("post"))
async def cmd_post(message: types.Message, state: FSMContext) -> None:
    """Start the ad creation flow."""

    if not message.from_user:
        return

    data = await state.get_data()

    if "user_id" not in data:
        await message.answer(
            _("Please login first with /start login_<token>")
        )

        return

    # Create draft ad

    ad = await create_draft_ad(user_id=data["user_id"])

    await state.set_state(AdCreateForm.category)

    await state.update_data(ad_id=ad.id)

    await message.answer(
        _(
            "Welcome to %(site)s! Creating new ad. Please select a category.\n"
            "Send a keyword to search, or use /cancel to abort."
        )
        % {"site": await get_site_name_async()}
    )


@router.message(Command("cancel"))
async def cmd_cancel(message: types.Message, state: FSMContext) -> None:
    """Cancel ad creation.

    Only deletes photo files and removes the draft if the ad is still in
    DRAFT status. If the ad has already been submitted (ON_MODERATION or
    later) the FSM ``photos`` list is stale and must not be used to delete
    files belonging to a submitted ad.
    """

    data = await state.get_data()

    if "ad_id" in data:
        ad_status = await _get_ad_status(data["ad_id"])

        if ad_status == AdStatus.DRAFT:
            # Clean up photo files from FSM state before deleting the draft

            photos = data.get("photos", [])

            for photo in photos:
                await asyncio.to_thread(delete_photo, photo["storage_key"])

            await delete_draft(data["ad_id"])

        else:
            logger.info(
                "Cancel skipped photo cleanup: ad %s is %s, not DRAFT",
                data["ad_id"],
                ad_status,
            )

    await state.clear()

    await message.answer(_("Ad creation cancelled."))
