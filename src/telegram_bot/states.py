"""
FSM states for ad creation and saved search management in Mko Bazuna Telegram bot.

States represent the step-by-step flow for sellers to create ads
and manage their saved search alerts.
"""

from enum import StrEnum


class AdCreateState(StrEnum):
    """States for the ad creation FSM."""

    CATEGORY = "category"
    PURPOSE = "purpose"
    CONDITION = "condition"
    FEATURES = "features"
    CITY = "city"
    TITLE = "title"
    DESCRIPTION = "description"
    PRICE = "price"
    PHOTOS = "photos"
    PREVIEW = "preview"


class ContactUsState(StrEnum):
    """FSM states for the support message intake flow."""

    IDLE = "support_idle"
    AWAITING_MESSAGE = "support_awaiting_message"
