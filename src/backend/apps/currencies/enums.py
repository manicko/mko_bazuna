"""
Currency enumeration for Mko Bazuna.

All currency references must use these StrEnum members, never plain strings
(project rule 10).
"""

from enum import StrEnum


class CurrencyCode(StrEnum):
    """Supported ad listing currencies.

    ``EUR`` is the default display currency (project launches in Montenegro).
    Rates are stored relative to EUR in the ``ExchangeRate`` model.
    """

    EUR = "EUR"
    RSD = "RSD"
    BAM = "BAM"

    @property
    def label(self) -> str:
        """Human-readable currency code label (the ISO 4217 code itself)."""
        return self.value
