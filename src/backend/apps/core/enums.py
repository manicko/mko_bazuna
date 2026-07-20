"""
Core enum types for Mko Bazuna.

All fixed value sets are modeled as Enum or StrEnum per project rule 10.
No inline string literals for constants anywhere in the codebase.
"""

from enum import IntEnum, StrEnum


class AdvisoryLockId(IntEnum):
    """PostgreSQL advisory lock IDs for idempotent scheduled jobs."""

    ARCHIVE_SWEEP = 1
    DELETE_SWEEP = 2
    CONSENT_HARD_DELETE = 3
    SWEEP_DRAFTS = 4
    CLEANUP_LOGIN_TOKENS = 5
    PURGE_FAILED_ADS = 6
    PURGE_REJECTED_ADS = 7
    MIGRATE = 100


class AdStatus(StrEnum):
    """Ad lifecycle status. Buyer-visible only when PUBLISHED."""

    DRAFT = "draft"
    ON_MODERATION = "on_moderation"
    PUBLISHED = "published"
    REJECTED = "rejected"
    ON_MODERATION_FAILED = "on_moderation_failed"
    ARCHIVED = "archived"
    DELETED = "deleted"


class AdSource(StrEnum):
    """Origin of an ad. Phase 1 accepts ads only via Telegram bot."""

    TELEGRAM = "telegram"


class AnalyticsEventType(StrEnum):
    """Analytics event types for product metrics."""

    REGISTRATION_CREATED = "registration_created"
    AD_PUBLISHED = "ad_published"
    SEARCH_PERFORMED = "search_performed"
    CONTACT_INITIATED = "contact_initiated"


class ModeratorActionType(StrEnum):
    """Moderator action types for ModeratorActionLog."""

    REJECT = "reject"
    BAN_ACCOUNT = "ban_account"
    SOFT_DELETE = "soft_delete"
    CRITERIA_CHANGE = "criteria_change"
    OTHER = "other"


class CategoryRejectReason(StrEnum):
    """
    Category reject reasons for UI/admin vocabulary.

    Used as guidance for moderator reject dropdowns. NOT stored as a database column
    (ModeratorActionLog.reason stays TEXT per docs/02-database/db-schema.md).
    """

    ADULT_CONTENT = "adult_content"
    VIOLENCE_GORE = "violence_gore"
    DRUGS_WEAPONS = "drugs_weapons"
    HATE_SPEECH = "hate_speech"
    COUNTERFEIT_GOODS = "counterfeit_goods"
    ILLEGAL_GOODS = "illegal_goods"
    SPAM_SCAM = "spam_scam"
    OFF_TOPIC = "off_topic"


__all__ = ["AdvisoryLockId", "AdStatus", "AdSource", "AnalyticsEventType", "ModeratorActionType", "CategoryRejectReason"]
