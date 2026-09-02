"""
Pydantic v2 DTOs for Telegram bot message payloads.

All bot message payloads validated before ORM writes per rule 11.
"""

from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, Field

from apps.currencies.enums import CurrencyCode


class TitlePayload(BaseModel):
    """Validated title input from seller."""

    title: Annotated[
        str,
        Field(
            min_length=5, max_length=200, description="Ad title in original language"
        ),
    ]


class DescriptionPayload(BaseModel):
    """Validated description input from seller."""

    description: Annotated[
        str,
        Field(
            min_length=10,
            max_length=2000,
            description="Ad description in original language",
        ),
    ]


class PricePayload(BaseModel):
    """Validated price input from seller (amount + currency).

    The amount is mandatory: the bot no longer offers a "Skip" option, so
    ``None`` is rejected at schema validation time. A Free/Charity ad enters
    ``Decimal("0")`` explicitly. The currency defaults to EUR.
    """

    price_amount: Decimal = Field(
        ge=0, description="Ad price amount in the chosen currency (>= 0)"
    )
    price_currency: CurrencyCode = CurrencyCode.EUR


class PhotoCountPayload(BaseModel):
    """Validated photo count constraint."""

    photo_count: Annotated[
        int,
        Field(ge=1, le=5, description="Number of photos (1-5)"),
    ]
