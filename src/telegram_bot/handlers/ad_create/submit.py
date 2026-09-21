"""Preview/submission FSM handler for the Telegram bot ad-creation flow.

Extracted verbatim from ``telegram_bot/handlers/ad_create/__init__.py``
(10-QLT-003 B16). ``process_preview`` handles the final preview step: on
``confirm`` it translates the ad text to all supported languages and submits
it for moderation via ``submit_ad``; on ``cancel`` it delegates to
``cmd_cancel`` (imported from :mod:`.entry`).

Shares the package-level ``router`` and ``AdCreateForm`` (imported, not
redefined) so the handler registers against the same Router instance.
"""

import logging
from decimal import Decimal

from aiogram import types
from aiogram.fsm.context import FSMContext
from asgiref.sync import sync_to_async
from django.utils.translation import gettext as _

from apps.ads.services.submission import SubmitAdInput, submit_ad
from apps.core.enums import LanguageLocale
from telegram_bot.handlers.ad_create import AdCreateForm, router
from telegram_bot.services.ad_data import translate_all_languages

from .entry import cmd_cancel

logger = logging.getLogger(__name__)


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
