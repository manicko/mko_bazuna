"""
FSM states for ad creation and saved search management in Mko Bazuna Telegram bot.

States represent the step-by-step flow for sellers to create ads
and manage their saved search alerts.
"""

from enum import StrEnum


class AdCreateState(StrEnum):
    """States for the ad creation FSM."""

    CATEGORY = "category"
    CITY = "city"
    TITLE = "title"
    DESCRIPTION = "description"
    PRICE = "price"
    PHOTOS = "photos"
    PREVIEW = "preview"


class SavedSearchState(StrEnum):
    """FSM states for saved search alert management."""

    IDLE = "alerts_idle"
    QUERY = "alerts_query"
    CITY = "alerts_city"
    CATEGORY = "alerts_category"
    PRICE = "alerts_price"
    CONFIRM = "alerts_confirm"