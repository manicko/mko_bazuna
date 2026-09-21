"""
Pydantic DTOs for the consent subsystem (constraint C-9.2).

Validates consent form submissions at the HTTP boundary (system entry point)
so invalid or malformed data is rejected before it reaches the views/services.
"""

from __future__ import annotations

import logging

from pydantic import BaseModel, Field, field_validator

from apps.core.enums import ConsentChoice, ConsentVersion, CookieCategory

logger = logging.getLogger(__name__)


class ConsentSubmission(BaseModel):
    """
    Pydantic DTO for consent form submission validation (TR-06 / C-9.2).

    Validates the ``choice`` against the ``ConsentChoice`` StrEnum and coerces
    the granular category flags to booleans.
    """

    choice: ConsentChoice
    analytics: bool = False
    preferences: bool = False
    consent_version: str = Field(default=ConsentVersion.V1_0.value, max_length=20)

    @field_validator("consent_version", mode="before")
    @classmethod
    def _normalize_consent_version(cls, value: object) -> str:
        """Leniently normalize the consent version to a valid ConsentVersion value.

        ``None``, empty strings, and unrecognized values are coerced to
        ``ConsentVersion.V1_0.value`` with a warning log so that a malformed
        client submission never triggers a 400 — the default version is
        recorded instead.
        """
        valid_values = {v.value for v in ConsentVersion}
        if value in valid_values:
            return str(value)
        logger.warning(
            "Invalid or missing consent_version (%r); coercing to %r",
            value,
            ConsentVersion.V1_0.value,
        )
        return ConsentVersion.V1_0.value

    def categories(self) -> dict[CookieCategory, bool]:
        """Build the category map keyed by ``CookieCategory`` enum members.

        The stored JSONB keys resolve to the enum's string values
        (``"analytics"``, ``"preferences"``) so existing consumers and tests
        that read the persisted dict are unaffected.
        """
        return {
            CookieCategory.ANALYTICS: self.analytics,
            CookieCategory.PREFERENCES: self.preferences,
        }
