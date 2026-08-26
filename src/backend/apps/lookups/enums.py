"""
StrEnum constants for built-in lookup group codes.

All group code references must use this enum, never plain strings.
"""

from enum import StrEnum


class LookupGroupCode(StrEnum):
    """Machine-readable codes for built-in lookup groups.

    Used in model field limit_choices_to, builder, and resolver —
    never plain strings.
    """

    LISTING_PURPOSE = "listing_purpose"
    LISTING_FEATURE = "listing_feature"
    LISTING_CONDITION = "listing_condition"
