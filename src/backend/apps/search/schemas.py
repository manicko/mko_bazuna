"""
Pydantic DTOs for the search web boundary.

Defines the ``AutocompleteSuggestion`` model that replaces untyped dicts
in the autocomplete response path.  All three suggestion producers
(user history, entity matching, popular searches) return typed instances
of this DTO, and the view serialises them via ``model_dump(mode="json")``.

Also defines ``SavedSearchInput``, the single input boundary shared by the
saved-search create view (``apps.search.views.save_search``) and the cabinet
edit view (``apps.cabinet.views.saved_searches``).  Both previously coerced
the same four POST fields through byte-identical module-private closures.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator

from apps.core.enums import SearchSuggestionSource
from apps.core.schemas import BaseInputModel


class AutocompleteSuggestion(BaseModel):
    """
    Typed suggestion returned by the autocomplete endpoint.

    ``source`` and ``type`` carry the same ``SearchSuggestionSource`` enum
    value.  ``type`` is a deprecated alias kept for backward compatibility
    with the frontend consumer (``header_catalog.html``) and existing tests.

    ``extra="allow"`` lets producers attach additional keys (e.g. ``slug``,
    ``category_path``, ``hit_count``) without failing validation; those keys
    are also accepted as named fields with ``None`` defaults.
    """

    text: str
    source: SearchSuggestionSource
    type: SearchSuggestionSource
    slug: str | None = None
    category_path: str | None = None
    hit_count: int | None = None

    model_config = {"extra": "allow"}


class SavedSearchInput(BaseInputModel):
    """Validated filters for a saved-search create/edit POST (10-CQ-004).

    One boundary for the four optional filters that the create view
    (``apps.search.views.save_search``) and the cabinet edit view
    (``apps.cabinet.views.saved_searches``) both accept.  Each view previously
    coerced these fields through its own byte-identical ``_int_or_none``
    closure; both closures are replaced by this DTO.

    Coercion semantics are copied exactly from those closures and from the
    sibling ``ListingsQueryParams`` DTO: a blank or non-integer value becomes
    ``None`` (no filter), never an error.  The one new rule is ``ge=0`` on the
    price bounds — a negative price is a boundary violation, not a value to
    persist.  The bound lives here rather than on ``SavedSearch`` because
    ``PositiveIntegerField`` emits no check constraint: a negative price would
    otherwise be silently stored.
    """

    city_id: int | None = None
    category_id: int | None = None
    min_price: int | None = Field(default=None, ge=0)
    max_price: int | None = Field(default=None, ge=0)

    @field_validator("city_id", "category_id", "min_price", "max_price", mode="before")
    @classmethod
    def _coerce_int_or_none(cls, v: Any) -> int | None:
        """Coerce a raw POST value to ``int``, returning ``None`` on failure.

        Blank (``None`` or ``""``) and unparseable values both yield ``None``,
        matching the deleted closures' semantics exactly.  ``int`` accepts
        surrounding whitespace, so no explicit strip is needed.
        """
        if v is None or v == "":
            return None
        try:
            return int(v)
        except (ValueError, TypeError):
            return None
