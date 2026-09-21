"""
Ad creation FSM handler for Telegram bot.

Implements step-by-step ad creation with Pydantic validation. Data-access
helpers, media helpers, translation helpers and keyboard builders live in
``telegram_bot.services.ad_data`` (bot -> backend direction).

Step handlers used to be concentrated here; they are now split across submodules
(B10: formatters in ``preview``; B11: category; B12: city; B13: text;
B14: price; B15: photos; B16: entry orchestrators + submit). Each submodule
imports the shared ``router`` and ``AdCreateForm`` from this package so every
``@router`` handler registers against the single Router instance, and this
package re-exports them.
"""

from aiogram import Router
from aiogram.fsm.state import StatesGroup

from telegram_bot.states import AdCreateState

from .preview import _format_preview_price, show_preview

__all__ = [
    "router",
    "AdCreateForm",
    "MAX_PHOTO_BYTES",
    "show_preview",
    "_format_preview_price",
    "cmd_post",
    "cmd_cancel",
    "process_preview",
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


# Step handlers are split into submodules (10-QLT-003 B11-B16). Each submodule
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
from .entry import cmd_cancel, cmd_post  # noqa: E402
from .photos import process_photos  # noqa: E402
from .price import (  # noqa: E402
    _move_from_price_to_photos,
    process_price,
    process_price_currency,
)
from .submit import process_preview  # noqa: E402
from .text import process_description, process_title  # noqa: E402
