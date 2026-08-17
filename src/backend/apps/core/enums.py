"""
Core enum types for Mko Bazuna.

All fixed value sets are modeled as Enum or StrEnum per project rule 10.
No inline string literals for constants anywhere in the codebase.
"""

from enum import IntEnum, StrEnum


class AdSort(StrEnum):
    """Sort options for ad listings."""

    DATE_NEW = "date_desc"
    DATE_OLD = "date_asc"
    PRICE_LOW = "price_asc"
    PRICE_HIGH = "price_desc"


class AdvisoryLockId(IntEnum):
    """PostgreSQL advisory lock IDs for idempotent scheduled jobs."""

    ARCHIVE_SWEEP = 1
    DELETE_SWEEP = 2
    CONSENT_HARD_DELETE = 3
    SWEEP_DRAFTS = 4
    CLEANUP_LOGIN_TOKENS = 5
    PURGE_FAILED_ADS = 6
    PURGE_REJECTED_ADS = 7
    ROLLUP_DAILY_METRICS = 8
    ALERT_DELIVERY_TASK = 9
    MIGRATE = 100
    CREATE_ADMIN = 101
    BACKFILL_THUMBNAILS = 102
    QUEUE_PROCESSING = 10
    PURGE_DELETED_ADS = 11
    SEED = 110


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
    SEED = "seed"


class AnalyticsEventType(StrEnum):
    """Analytics event types for product metrics."""

    REGISTRATION_CREATED = "registration_created"
    AD_PUBLISHED = "ad_published"
    SEARCH_PERFORMED = "search_performed"
    CONTACT_INITIATED = "contact_initiated"
    SEARCH_ALERT_MATCHED = "search_alert_matched"
    AD_VIEWED = "ad_viewed"
    CONTACT_RESPONSE = "contact_response"
    SELLER_VERIFIED = "seller_verified"
    TRUST_LEVEL_UPDATED = "trust_level_updated"
    MODERATION_APPROVED = "moderation_approved"
    MODERATION_REJECTED = "moderation_rejected"
    MODERATION_FLAGGED = "moderation_flagged"
    DASHBOARD_VIEWED = "dashboard_viewed"
    AD_EDITED = "ad_edited"
    AD_REACTIVATED = "ad_reactivated"
    CONTACT_COMPLETED = "contact_completed"
    AD_REPORTED = "ad_reported"


class ThumbnailSizeStrEnum(StrEnum):
    """Standard thumbnail sizes for Mko Bazuna."""

    SMALL = "small"
    MEDIUM = "medium"
    LARGE = "large"


class AdPriorityLevel(StrEnum):
    """Priority levels for moderation queue triage."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class PriorityFilter(StrEnum):
    """Priority filter for the moderation queue.

    ``ALL`` is a UI/query sentinel (maps to no DB filter) and is NOT a
    value stored in the ``AdModerationPriority.priority_level`` column
    (which uses ``AdPriorityLevel``). HIGH/MEDIUM/LOW mirror
    ``AdPriorityLevel`` so the DB filter is identical.
    """

    ALL = "all"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class TrustLevel(StrEnum):
    """Seller trust level for badge display."""

    UNVERIFIED = "unverified"
    VERIFIED = "verified"
    TRUSTED = "trusted"
    PRO = "pro"


class TimeRange(StrEnum):
    """Time range options for seller statistics filtering."""

    ALL_TIME = "all_time"
    THIRTY_DAYS = "30_days"
    SEVEN_DAYS = "7_days"

    @classmethod
    def choices(cls) -> list[tuple[str, str]]:
        """Return list of (value, label) tuples for template select options."""
        return [
            (cls.ALL_TIME.value, "All Time"),
            (cls.THIRTY_DAYS.value, "30 Days"),
            (cls.SEVEN_DAYS.value, "7 Days"),
        ]


class ModeratorActionType(StrEnum):
    """Moderator action types for ModeratorActionLog."""

    REJECT = "reject"
    BAN_ACCOUNT = "ban_account"
    SOFT_DELETE = "soft_delete"
    CRITERIA_CHANGE = "criteria_change"
    OTHER = "other"


class BulkModerationAction(StrEnum):
    """Bulk moderation action types for the moderation API."""

    APPROVE = "approve"
    REJECT = "reject"
    FLAG = "flag"


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


class SearchSuggestionSource(StrEnum):
    """Source types for search autocomplete suggestions."""

    USER_HISTORY = "user_history"
    POPULAR_SEARCH = "popular_search"
    CATEGORY = "category"
    CITY = "city"


class LanguageLocale(StrEnum):
    """Supported locale codes for UI and ad content."""

    RUSSIAN = "ru"
    BOSNIAN = "bs"
    ENGLISH = "en"

    @classmethod
    def values(cls) -> list[str]:
        """Return a list of all locale string values."""
        return [m.value for m in cls]

    @classmethod
    def from_code(
        cls,
        language_code: str | None,
        *,
        fallback: LanguageLocale | None = None,
    ) -> LanguageLocale:
        """Resolve a Telegram/IETF language_code to a LanguageLocale.

        Normalizes tags like 'en-US' to 'en', maps to the enum, and returns
        fallback when the code is None or unsupported.
        """
        if fallback is None:
            fallback = cls.BOSNIAN
        if not language_code:
            return fallback
        base = language_code.split("-")[0].lower()
        for member in cls:
            if member.value == base:
                return member
        return fallback

    @property
    def fts_config(self) -> str:
        """PostgreSQL text search config for this language."""
        return {
            "ru": "russian",
            "bs": "simple",
            "en": "english",
        }[self.value]


__all__ = [
    "AdSort",
    "AdvisoryLockId",
    "AdStatus",
    "AdSource",
    "AnalyticsEventType",
    "TrustLevel",
    "ModeratorActionType",
    "BulkModerationAction",
    "CategoryRejectReason",
    "AdPriorityLevel",
    "PriorityFilter",
    "ThumbnailSizeStrEnum",
    "SearchSuggestionSource",
    "LanguageLocale",
    "TimeRange",
]
