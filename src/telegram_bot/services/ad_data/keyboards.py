"""Inline keyboard builders for the Telegram bot ad-creation service.

Builds aiogram ``InlineKeyboardMarkup`` for currency, purpose, condition and
feature selection (bot -> backend direction).
"""

from aiogram import types
from aiogram.utils.keyboard import InlineKeyboardBuilder
from django.utils.translation import gettext as _

from apps.core.enums import LanguageLocale
from apps.currencies.enums import CurrencyCode
from apps.lookups.models import LookupItem
from telegram_bot.schemas.callbacks import BotCallbackPrefix

__all__ = [
    "build_currency_keyboard",
    "build_purpose_keyboard",
    "build_condition_keyboard",
    "build_feature_keyboard",
]


# ---------------------------------------------------------------------------
# Inline keyboard builders
# ---------------------------------------------------------------------------

# Presentation-only emoji lookup keyed by CurrencyCode members; the currency
# codes themselves remain sourced solely from the CurrencyCode StrEnum.
_CURRENCY_FLAGS: dict[CurrencyCode, str] = {
    CurrencyCode.EUR: "🇪🇺",
    CurrencyCode.RSD: "🇷🇸",
    CurrencyCode.BAM: "🇧🇦",
}


def build_currency_keyboard() -> types.InlineKeyboardMarkup:
    """Build the inline keyboard for currency selection (EUR first, PO-01).

    Currency buttons are derived from the ``CurrencyCode`` StrEnum so the
    builder and the price-step parser (``price.py``) share a single source of
    truth — no bare ``"EUR"``/``"RSD"``/``"BAM"`` literals (10-QLT-003). The
    enum's definition order (EUR, RSD, BAM) keeps EUR first.
    """

    builder = InlineKeyboardBuilder()

    for code in CurrencyCode:
        builder.button(
            text=f"{_CURRENCY_FLAGS[code]} {code.value}",
            callback_data=f"{BotCallbackPrefix.PRICE_CURRENCY}{code.value}",
        )

    builder.button(text=_("🆓 Free"), callback_data=BotCallbackPrefix.PRICE_FREE)

    builder.adjust(2)

    return builder.as_markup()


def build_purpose_keyboard(
    purposes: list[LookupItem],
    default_slug: str | None = None,
    locale: str = LanguageLocale.RUSSIAN,
) -> types.InlineKeyboardMarkup:
    """Build inline keyboard for purpose selection."""

    builder = InlineKeyboardBuilder()

    for purpose in purposes:
        text = purpose.get_name(locale)

        if purpose.slug == default_slug:
            text = f"✅ {text}"

        builder.button(
            text=text, callback_data=f"{BotCallbackPrefix.PURPOSE}{purpose.slug}"
        )

    builder.adjust(2)

    return builder.as_markup()


def build_condition_keyboard(
    conditions: list[LookupItem],
    locale: str = LanguageLocale.RUSSIAN,
) -> types.InlineKeyboardMarkup:
    """Build inline keyboard for condition single-selection."""
    builder = InlineKeyboardBuilder()
    for condition in conditions:
        text = condition.get_name(locale)
        builder.button(
            text=text, callback_data=f"{BotCallbackPrefix.CONDITION}{condition.slug}"
        )
    builder.adjust(2)
    return builder.as_markup()


def build_feature_keyboard(
    features: list[LookupItem],
    selected_ids: set[int],
    locale: str = LanguageLocale.RUSSIAN,
) -> types.InlineKeyboardMarkup:
    """Build inline keyboard for feature multi-selection."""

    builder = InlineKeyboardBuilder()

    for feature in features:
        if feature.slug in ("new", "used"):
            continue
        text = feature.get_name(locale)

        if feature.id in selected_ids:
            text = f"✅ {text}"

        builder.button(
            text=text, callback_data=f"{BotCallbackPrefix.FEATURE}{feature.id}"
        )

    builder.button(text=_("✔️ Done"), callback_data=BotCallbackPrefix.FEATURES_DONE)

    builder.adjust(2)

    return builder.as_markup()
