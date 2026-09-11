"""
Pydantic DTOs for the search autocomplete web boundary.

Defines the ``AutocompleteSuggestion`` model that replaces untyped dicts
in the autocomplete response path.  All three suggestion producers
(user history, entity matching, popular searches) return typed instances
of this DTO, and the view serialises them via ``model_dump(mode="json")``.
"""

from __future__ import annotations

from pydantic import BaseModel

from apps.core.enums import SearchSuggestionSource


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
