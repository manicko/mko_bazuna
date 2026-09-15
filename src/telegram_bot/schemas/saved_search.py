"""
Pydantic v2 DTOs for saved search input validation.

Validates search query and price range inputs from the bot and web UI.
"""

from typing import Annotated

from pydantic import BaseModel, Field


class SavedSearchQueryPayload(BaseModel):
    """Validated search query input for saved search alert."""

    query: Annotated[
        str | None,
        Field(max_length=200, description="Search query string"),
    ] = None


class SavedSearchPricePayload(BaseModel):
    """Validated price range input for saved search alert."""

    min_price: Annotated[
        int | None,
        Field(ge=0, le=1000000, description="Minimum price in BAM"),
    ] = None
    max_price: Annotated[
        int | None,
        Field(ge=0, le=1000000, description="Maximum price in BAM"),
    ] = None
