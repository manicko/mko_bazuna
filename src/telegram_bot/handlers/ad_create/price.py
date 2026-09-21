"""Price-step FSM handlers for the Telegram bot ad-creation flow.

Extracted verbatim from ``telegram_bot/handlers/ad_create/__init__.py``
(10-QLT-003 B14). Shares the package-level ``router`` and ``AdCreateForm``.
"""

from decimal import Decimal

from aiogram import types
from aiogram.fsm.context import FSMContext
from django.utils.translation import gettext as _

from apps.currencies.enums import CurrencyCode
from telegram_bot.handlers.ad_create import AdCreateForm, router
from telegram_bot.schemas.callbacks import BotCallbackPrefix
from telegram_bot.schemas.message_payloads import PricePayload
from telegram_bot.services.ad_data import build_currency_keyboard


@router.callback_query(AdCreateForm.price)
async def process_price_currency(
    callback: types.CallbackQuery, state: FSMContext
) -> None:
    """Process currency selection (or Free) from the price inline keyboard."""

    if not callback.data or not callback.message:
        return

    if callback.data == BotCallbackPrefix.PRICE_FREE:
        await state.update_data(
            price_amount=Decimal("0.00"),
            price_currency=CurrencyCode.EUR,
        )

        await callback.answer()

        await _move_from_price_to_photos(callback.message, state)

        return

    if callback.data.startswith(BotCallbackPrefix.PRICE_CURRENCY):
        currency_value = callback.data.replace(BotCallbackPrefix.PRICE_CURRENCY, "")

        try:
            currency = CurrencyCode(currency_value)

        except ValueError:
            await callback.answer(_("Invalid currency."), show_alert=True)

            return

        await state.update_data(price_currency=currency)

        await callback.answer()

        await callback.message.answer(
            _("Currency: %(currency)s\nNow enter the price amount as a number.")
            % {"currency": currency.value}
        )


@router.message(AdCreateForm.price)
async def process_price(message: types.Message, state: FSMContext) -> None:
    """Process the numeric price amount input with Pydantic validation."""

    data = await state.get_data()

    currency: CurrencyCode | None = data.get("price_currency")

    if currency is None:
        await message.answer(
            _("Please choose a currency first or select 'Free' for a zero-price (Charity) ad."),
            reply_markup=build_currency_keyboard(),
        )

        return

    if not message.text:
        await message.answer(
            _("Please send the price amount as a number, or select 'Free' on the keyboard.")
        )

        return

    text = message.text.strip().lower()

    try:
        price_value = Decimal(text)

        payload = PricePayload(price_amount=price_value, price_currency=currency)

        await state.update_data(price_amount=payload.price_amount)

    except (ValueError, ArithmeticError):
        await message.answer(_("Invalid price. Enter a number."))

        return

    await _move_from_price_to_photos(message, state)


async def _move_from_price_to_photos(message: types.Message, state: FSMContext) -> None:
    """Advance from the price step to the photo upload step."""

    await state.set_state(AdCreateForm.photos)

    await message.answer(
        _("Price saved.\n"
          "Send 1-5 photos (JPEG only). Each photo under ~2MB, max 2560x2560 pixels.\n"
          "Send 'done' when finished.")
    )
