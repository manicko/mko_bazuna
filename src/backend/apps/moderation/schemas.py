"""
Pydantic v2 DTOs for the moderation API boundary (rule 11).

Validates the bulk-moderation request body before any DB write.
``extra="forbid"`` rejects unknown keys instead of silently dropping them.
"""

from __future__ import annotations

from apps.core.enums import BulkModerationAction
from apps.core.schemas import BaseInputModel

__all__ = ["BulkModerationRequest"]


class BulkModerationRequest(BaseInputModel):
    """Pydantic v2 DTO for the bulk-moderation JSON API boundary.

    Validates the request body before any DB write. ``extra="forbid"``
    rejects unknown keys instead of silently dropping them.
    """

    action: BulkModerationAction
    selected_items: list[int]
    reason: str = ""
