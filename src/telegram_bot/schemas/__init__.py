"""Telegram bot schemas package."""

from .message_payloads import (
    DescriptionPayload,
    PhotoCountPayload,
    PricePayload,
    TitlePayload,
)

__all__ = ["TitlePayload", "DescriptionPayload", "PricePayload", "PhotoCountPayload"]
