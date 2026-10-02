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
from django.db import OperationalError
from django.utils.translation import gettext as _

from apps.ads.services.submission import (
    SubmitAdInput,
    SubmitAdOutcome,
    submit_ad,
)
from apps.core.enums import LanguageLocale
from apps.core.utils.db_lock_timeout import is_lock_timeout
from telegram_bot.handlers.ad_create import AdCreateForm, router
from telegram_bot.services.ad_data import (
    create_draft_ad,
    touch_draft,
    touch_staging_photos,
    translate_all_languages,
)

from .entry import cmd_cancel

logger = logging.getLogger(__name__)


@router.message(AdCreateForm.preview)
async def process_preview(message: types.Message, state: FSMContext) -> None:
    """Process preview confirmation."""

    if not message.text:
        return

    if not message.from_user:
        return

    data = await state.get_data()

    if data.get("ad_id") is not None:
        await touch_draft(data["ad_id"])

    await touch_staging_photos(data.get("photos", []))

    text = message.text.strip().lower()

    if text == "confirm":
        original_title = data.get("title", "")

        original_desc = data.get("description", "")

        # Translate to all languages in parallel

        title_translations = await translate_all_languages(
            original_title, LanguageLocale.values()
        )

        desc_translations = await translate_all_languages(
            original_desc, LanguageLocale.values()
        )

        # Update ad with multi-language content and run moderation.
        #
        # A lock timeout is a TRANSIENT contention failure, not a content
        # failure: it must not be reported as one, and it must not clear the FSM
        # state (that would destroy the seller's typed dialog for a condition
        # that resolves in seconds). Catch it here, answer the busy message and
        # keep the state so the seller can press confirm again.
        try:
            result = await sync_to_async(submit_ad)(
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
        except OperationalError as exc:
            if not is_lock_timeout(exc):
                raise
            logger.warning(
                "Lock timeout submitting ad %s (SQLSTATE 55P03); keeping FSM state",
                data.get("ad_id"),
            )
            await message.answer(
                _("The system is busy. Please try again in a moment.")
            )
            return

        if result.outcome is SubmitAdOutcome.PUBLISHED:
            await message.answer(
                _("Ad submitted for moderation! You'll be notified when it's published.")
            )

            await state.clear()

        elif result.outcome is SubmitAdOutcome.MODERATION_FAILED:
            # A genuine content failure: the seller should start a new ad either
            # way, so the dialog is closed and the moderation reason rendered.
            # Render the real moderation error (mirrors ad_edit), falling back
            # to the generic message when the service returned no reason. The
            # service wraps its strings in gettext_lazy, so ``str`` forces the
            # catalog lookup here, under the request/row locale.
            await message.answer(
                str(result.errors[0])
                if result.errors
                else _("Ad failed moderation. Please check your content and try again.")
            )

            await state.clear()

        else:
            # Non-destructive outcomes (DRAFT_GONE, INVALID_TRANSITION,
            # PHOTO_UNAVAILABLE): the draft row is gone (reaped by sweep_drafts
            # or deleted by a concurrent /post) or unusable, yet the seller's
            # typed dialog is still the only remaining copy. Do NOT clear the
            # state — instead RE-POINT it at a fresh DRAFT so the seller can
            # press confirm again without losing their work.
            #
            # create_draft_ad deletes any pre-existing DRAFT first, so nothing
            # is destroyed: on DRAFT_GONE the draft is already gone, and on
            # INVALID_TRANSITION the row is DELETED, not DRAFT. A replaced
            # ad_id makes the next confirm target a live row.
            #
            # The draft-expired string is the already-shipped, already-
            # translated message; the row-existence probe it used to require is
            # gone because submit_ad now names the outcome.
            new_ad = await create_draft_ad(data["user_id"])

            await state.update({"ad_id": new_ad.id})

            await message.answer(
                _(
                    "Your draft expired and was deleted. "
                    "Please start again with /post."
                )
            )

            return

    elif text == "cancel":
        await cmd_cancel(message, state)

    else:
        await message.answer(_("Send 'confirm' to submit or 'cancel' to abort."))
