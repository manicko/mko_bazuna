"""City-step FSM handler for the Telegram bot ad-creation flow.

Extracted verbatim from ``telegram_bot/handlers/ad_create/__init__.py``
(10-QLT-003 B12). Shares the package-level ``router`` and ``AdCreateForm``.
"""

from aiogram import types
from aiogram.fsm.context import FSMContext
from django.utils.translation import get_language, gettext as _

from apps.locations.services.city_fuzzy import match_city
from telegram_bot.handlers.ad_create import AdCreateForm, router
from telegram_bot.services.ad_data import get_all_cities, get_city_by_name, touch_draft


@router.message(AdCreateForm.city)
async def process_city(message: types.Message, state: FSMContext) -> None:
    """Process city selection."""

    data = await state.get_data()

    if data.get("ad_id") is not None:
        await touch_draft(data["ad_id"])

    if not message.text:
        await message.answer(_("Please send a city name."))

        return

    city_name = message.text.strip()

    # Exact match or did-you-mean

    city = await get_city_by_name(city_name)

    if not city:
        all_cities = await get_all_cities()

        matched = match_city(
            city_name, [c.get_name(get_language()) for c in all_cities], n=1
        )

        if matched:
            match = await get_city_by_name(matched)

            if match:
                city = match

    if not city:
        await message.answer(
            _(
                "City not found. Please send an exact city name.\n"
                "Available cities: Podgorica, Nikšić, Bar, etc."
            )
        )

        return

    await state.update_data(city_id=city.id)

    await state.set_state(AdCreateForm.title)

    await message.answer(
        _("City: %(name)s\nNow enter the ad title (5-200 characters).")
        % {"name": city.get_name(get_language())}
    )
