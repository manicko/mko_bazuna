"""
Pydantic base schemas for the core subsystem.

``BaseInputModel`` is the shared base for every client-input DTO in the
project. Enforcing ``extra="forbid"`` rejects unknown/extra fields instead of
silently dropping them, so a misspelled or unexpected input key fails fast at
the HTTP boundary rather than being ignored.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

__all__ = ["BaseInputModel"]


class BaseInputModel(BaseModel):
    """Base for all client-input DTOs; rejects unknown/extra fields."""

    model_config = ConfigDict(extra="forbid")
