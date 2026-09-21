"""Title and description FSM handlers for the Telegram bot ad-creation flow.

Extracted verbatim from ``telegram_bot/handlers/ad_create/__init__.py``
(10-QLT-003 B13). Shares the package-level ``router`` and ``AdCreateForm``.
"""

from aiogram import types
from aiogram.fsm.context import FSMContext
from django.utils.translation import gettext as _

from telegram_bot.handlers.ad_create import AdCreateForm, router
from telegram_bot.schemas.message_payloads import DescriptionPayload, TitlePayload
from telegram_bot.services.ad_data import build_currency_keyboard


@router.message(AdCreateForm.title)
async def process_title(message: types.Message, state: FSMContext) -> None:
    """Process title input with Pydantic validation."""

    if not message.text:
        await message.answer(_("Please send the ad title."))

        return

    try:
        payload = TitlePayload(title=message.text)

    except Exception as e:
        await message.answer(_("Invalid title: {error}").format(error=e))

        return

    await state.update_data(title=payload.title)

    await state.set_state(AdCreateForm.description)

    await message.answer(
        _("Title saved.\nNow enter the ad description (10-2000 characters).")
    )


@router.message(AdCreateForm.description)
async def process_description(message: types.Message, state: FSMContext) -> None:
    """Process description input with Pydantic validation."""

    if not message.text:
        await message.answer(_("Please send the ad description."))

        return

    try:
        payload = DescriptionPayload(description=message.text)

    except Exception as e:
        await message.answer(_("Invalid description: {error}").format(error=e))

        return

    await state.update_data(description=payload.description)

    await state.set_state(AdCreateForm.price)

    await message.answer(
        _("Description saved.\n"
          "Now choose the price currency, or select 'Free' for a zero-price (Charity) ad."),
        reply_markup=build_currency_keyboard(),
    )
