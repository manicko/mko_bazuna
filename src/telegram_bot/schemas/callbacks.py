"""
Callback data constants for Telegram bot inline keyboards.

Centralizes the bot's callback tokens so the ``F.data`` filter lambdas in the
handler modules and the keyboard builders in ``ad_data.py`` can never drift
apart. All fixed values are modeled as a StrEnum per project rule 10.
"""

from enum import StrEnum


class BotCallbackPrefix(StrEnum):
    """Callback-data tokens for inline keyboard buttons (ad creation + contact).

    Members carry the full prefix/sentinel used in ``callback_data``. Builders
    interpolate them with ``f"{BotCallbackPrefix.PURPOSE}{slug}"``; filter
    lambdas match with ``c.data.startswith(BotCallbackPrefix.PURPOSE)``.
    """

    PURPOSE = "purpose:"
    CONDITION = "condition:"
    FEATURE = "feature:"
    PRICE_CURRENCY = "price_currency:"
    PRICE_FREE = "price_free"
    FEATURES_DONE = "features_done"
    CONTACT_US = "contact_us"


__all__ = ["BotCallbackPrefix"]
