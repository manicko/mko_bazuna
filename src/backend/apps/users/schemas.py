"""
Pydantic DTOs for the consent subsystem (constraint C-9.2).

Validates consent form submissions at the HTTP boundary (system entry point)
so invalid or malformed data is rejected before it reaches the views/services.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from apps.core.enums import ConsentChoice, CookieCategory


class ConsentSubmission(BaseModel):
    """
    Pydantic DTO for consent form submission validation (TR-06 / C-9.2).

    Validates the ``choice`` against the ``ConsentChoice`` StrEnum and coerces
    the granular category flags to booleans.
    """

    choice: ConsentChoice
    analytics: bool = False
    preferences: bool = False
    consent_version: str = Field(default="1.0", max_length=20)

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
