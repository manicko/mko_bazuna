"""
Pydantic v2 DTOs for Telegram bot message payloads.

All bot message payloads validated before ORM writes per rule 11.
"""

from typing import Annotated

from pydantic import BaseModel, Field


class TitlePayload(BaseModel):
    """Validated title input from seller."""

    title: Annotated[
        str,
        Field(min_length=5, max_length=200, description="Ad title in original language"),
    ]


class DescriptionPayload(BaseModel):
    """Validated description input from seller."""

    description: Annotated[
        str,
        Field(
            min_length=10, max_length=2000, description="Ad description in original language"
        ),
    ]


class PricePayload(BaseModel):
    """Validated price input from seller."""

    price: Annotated[
        int | None,
        Field(ge=0, description="Ad price in whole BAM units, nullable"),
    ]


class PhotoCountPayload(BaseModel):
    """Validated photo count constraint."""

    photo_count: Annotated[
        int,
        Field(ge=1, le=5, description="Number of photos (1-5)"),
    ]