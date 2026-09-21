"""
Ad creation FSM handler for Telegram bot.

Implements step-by-step ad creation with Pydantic validation. Data-access
helpers, media helpers, translation helpers and keyboard builders live in
``telegram_bot.services.ad_data`` (bot -> backend direction).

Step handlers used to be concentrated here; they are now split across submodules
(B10-B15: formatters in ``preview``; B11: category; B12: city; B13: text;
B14: price; B15: photos).
Each submodule imports the shared ``router`` and ``AdCreateForm`` from this
package so every ``@router`` handler registers against the single Router
instance, and this package re-exports them. The orchestrators (``cmd_post``,
``cmd_cancel``) and the preview step (``process_preview``) remain here.
"""

import asyncio
import logging
from decimal import Decimal

from aiogram import Router, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup
from asgiref.sync import sync_to_async
from django.utils.translation import gettext as _

from apps.ads.services.submission import SubmitAdInput, submit_ad
from apps.core.enums import AdStatus, LanguageLocale
from apps.core.services.site_config import get_site_name_async
from apps.media.services.filesystem import delete_photo
from telegram_bot.services.ad_data import (
    _get_ad_status,
    create_draft_ad,
    delete_draft,
    translate_all_languages,
)
from telegram_bot.states import AdCreateState

from .preview import _format_preview_price, show_preview

__all__ = [
    "show_preview",
    "_format_preview_price",
    "process_category",
    "process_category_selected",
    "proceed_to_features_or_city",
    "_show_features_or_city_step",
    "process_purpose",
    "process_condition",
    "process_features",
    "process_city",
    "process_title",
    "process_description",
    "process_price_currency",
    "process_price",
    "_move_from_price_to_photos",
    "process_photos",
]


logger = logging.getLogger(__name__)

# 2 MB — matches the validate_photo limit in filesystem.py (MED-002).
MAX_PHOTO_BYTES = 2 * 1024 * 1024


router = Router()


class AdCreateForm(StatesGroup):
    """FSM states for ad creation."""

    category = AdCreateState.CATEGORY

    purpose = AdCreateState.PURPOSE

    condition = AdCreateState.CONDITION

    features = AdCreateState.FEATURES

    city = AdCreateState.CITY

    title = AdCreateState.TITLE

    description = AdCreateState.DESCRIPTION

    price = AdCreateState.PRICE

    photos = AdCreateState.PHOTOS

    preview = AdCreateState.PREVIEW


# Step handlers are split into submodules (10-QLT-003 B11-B15). Each submodule
# imports the shared ``router`` and ``AdCreateForm`` from this package; importing
# them here runs the ``@router`` decorators (registering every handler on the
# single Router instance) and re-exports the public step handlers.
from .category import (  # noqa: E402
    _show_features_or_city_step,
    proceed_to_features_or_city,
    process_category,
    process_category_selected,
    process_condition,
    process_features,
    process_purpose,
)
from .city import process_city  # noqa: E402
from .photos import process_photos  # noqa: E402
from .price import (  # noqa: E402
    _move_from_price_to_photos,
    process_price,
    process_price_currency,
)
from .text import process_description, process_title  # noqa: E402


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


# --- Preview step ---


@router.message(AdCreateForm.preview)
async def process_preview(message: types.Message, state: FSMContext) -> None:
    """Process preview confirmation."""

    if not message.text:
        return

    if not message.from_user:
        return

    text = message.text.strip().lower()

    if text == "confirm":
        data = await state.get_data()

        original_title = data.get("title", "")

        original_desc = data.get("description", "")

        # Translate to all languages in parallel

        title_translations = await translate_all_languages(
            original_title, LanguageLocale.values()
        )

        desc_translations = await translate_all_languages(
            original_desc, LanguageLocale.values()
        )

        # Update ad with multi-language content and run moderation

        is_valid, errors = await sync_to_async(submit_ad)(
            SubmitAdInput(
                ad_id=data["ad_id"],
                title_ru=title_translations.get("ru", original_title),
                desc_ru=desc_translations.get("ru", original_desc),
                title_bs=title_translations.get("bs", original_title),
                desc_bs=desc_translations.get("bs", original_desc),
                title_en=title_translations.get("en", original_title),
                desc_en=desc_translations.get("en", original_desc),
                original_language=LanguageLocale.from_code(
                    message.from_user.language_code,
                    fallback=LanguageLocale.BOSNIAN,
                ).value,
                category_id=data.get("category_id"),
                city_id=data.get("city_id"),
                price_amount=data.get("price_amount") or Decimal("0"),
                price_currency=data.get("price_currency"),
                photos=data.get("photos", []),
                user_id=data.get("user_id"),
                listing_purpose_id=data.get("listing_purpose_id"),
                feature_ids=data.get("feature_ids"),
                listing_condition_id=data.get("condition_id"),
            )
        )

        if is_valid:
            await message.answer(
                _("Ad submitted for moderation! You'll be notified when it's published.")
            )

            await state.clear()

        else:
            await message.answer(
                _("Ad failed moderation. Please check your content and try again.")
            )

            await state.clear()

            return

    elif text == "cancel":
        await cmd_cancel(message, state)

    else:
        await message.answer(_("Send 'confirm' to submit or 'cancel' to abort."))
