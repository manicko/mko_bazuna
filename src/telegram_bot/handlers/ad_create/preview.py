"""Presentation formatters for the ad-creation preview step.

Extracted from ``telegram_bot/handlers/ad_create.py`` (10-QLT-003 B10) to
reduce module size. Neither function carries router state: ``show_preview`` is
re-exported by ``ad_create/__init__.py`` for its single call site
(``process_photos``), and ``_format_preview_price`` is only referenced by
``show_preview`` here.
"""

from typing import Any

from aiogram import types
from django.utils.translation import get_language, gettext as _

from telegram_bot.services.ad_data import (
    get_category,
    get_city,
    get_feature_names,
    get_lookup_item,
)


async def show_preview(message: types.Message, data: dict[str, Any]) -> None:
    """Show ad preview before submission."""

    category = await get_category(data.get("category_id"))

    city = await get_city(data.get("city_id"))

    purpose = await get_lookup_item(data.get("listing_purpose_id"))

    purpose_name = (
        purpose.get_name(get_language()) if purpose else _("N/A")
    )

    condition = await get_lookup_item(data.get("condition_id"))

    condition_name = (
        condition.get_name(get_language()) if condition else _("N/A")
    )

    feature_ids = data.get("feature_ids", [])

    feature_names = (
        ", ".join(await get_feature_names(feature_ids, locale=get_language()))
        if feature_ids
        else _("None")
    )

    preview_text = (
        _("Ad Preview:\n\n"
          "Title: %(title)s\n"
          "Description: %(description)s...\n"
          "Price: %(price)s\n"
          "Category: %(category)s\n"
          "Purpose: %(purpose)s\n"
          "Condition: %(condition)s\n"
          "Features: %(features)s\n"
          "City: %(city)s\n")
        % {
            "title": data.get("title", _("N/A")),
            "description": data.get("description", _("N/A"))[:100],
            "price": _format_preview_price(data),
            "category": category.get_name(get_language()) if category else _("N/A"),
            "purpose": purpose_name,
            "condition": condition_name,
            "features": feature_names,
            "city": city.get_name(get_language()) if city else _("N/A"),
        }
    )

    await message.answer(
        preview_text
        + _("Send 'confirm' to submit for moderation or 'cancel' to abort.")
    )


def _format_preview_price(data: dict[str, Any]) -> str:
    """Format the selected price (amount + currency) for the preview."""

    amount = data.get("price_amount")

    if amount is None:
        return _("N/A")

    currency = data.get("price_currency")

    label = str(currency) if currency else ""

    return f"{amount} {label}".strip()
