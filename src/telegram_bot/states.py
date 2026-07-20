"""
FSM states for ad creation in Mko Bazuna Telegram bot.

States represent the step-by-step flow for sellers to create ads.
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