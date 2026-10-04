"""
Core enum types for Mko Bazuna.

All fixed value sets are modeled as Enum or StrEnum per project rule 10.
No inline string literals for constants anywhere in the codebase.
"""

from enum import IntEnum, StrEnum

from django.utils.functional import Promise
from django.utils.translation import gettext_lazy as _


class AdSort(StrEnum):
    """Sort options for ad listings."""

    DATE_NEW = "date_desc"
    DATE_OLD = "date_asc"
    PRICE_LOW = "price_asc"
    PRICE_HIGH = "price_desc"


class RateLimitBudget(StrEnum):
    """Per-endpoint application rate-limit budgets and their rationale.

    One declaration for every application-level limiter so the numbers cannot
    drift again — the defect was two undocumented ``Final[int]`` pairs on
    adjacent anonymous HTML routes (08-SRCH-010). Each member's value is the
    stable budget name; the request count and window live in the two properties
    below, read by each limiter's module.

    Budgets:

    SEARCH_PAGE: 30 requests / 60 s. Anonymous HTML search rendering — the
        buyer-facing hot path that runs the FTS query, so it is the tightest.
    AUTOCOMPLETE: 30 requests / 60 s. Same budget as SEARCH_PAGE but a distinct
        key namespace, so the two keep independent counters.
    DEEP_LINK_RENDER: 60 requests / 600 s. Anonymous browse pages that render
        Telegram contact deep-links; a side effect, not a query cost.
    LOGIN_ISSUE: 10 requests / 60 s. Issuing a login token is
        security-sensitive, so it is the tightest budget.
    MEDIA_GATE: 60 requests / 60 s. Anonymous DB-backed media serving; protects
        the database from an over-budget client (09-API-005).
    """

    SEARCH_PAGE = "search_page"
    AUTOCOMPLETE = "autocomplete"
    DEEP_LINK_RENDER = "deep_link_render"
    LOGIN_ISSUE = "login_issue"
    MEDIA_GATE = "media_gate"

    @property
    def requests(self) -> int:
        """Maximum requests allowed inside the window for this budget."""
        return {
            RateLimitBudget.SEARCH_PAGE: 30,
            RateLimitBudget.AUTOCOMPLETE: 30,
            RateLimitBudget.DEEP_LINK_RENDER: 60,
            RateLimitBudget.LOGIN_ISSUE: 10,
            RateLimitBudget.MEDIA_GATE: 60,
        }[self]

    @property
    def period(self) -> int:
        """Window length in seconds for this budget."""
        return {
            RateLimitBudget.SEARCH_PAGE: 60,
            RateLimitBudget.AUTOCOMPLETE: 60,
            RateLimitBudget.DEEP_LINK_RENDER: 600,
            RateLimitBudget.LOGIN_ISSUE: 60,
            RateLimitBudget.MEDIA_GATE: 60,
        }[self]


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
    SWEEP_ORPHANED_MEDIA = 103
    CATALOG_LOAD = 104
    PURGE_DELETED_ADS = 11
    RECOMPUTE_NORMALIZED_PRICES = 12
    REPAIR_BOT_USERNAME = 13
    CONSENT_RECORD_SWEEP = 14
    PURGE_MEDIA_DELETION_ERRORS = 15
    SEED = 110
    TEST_SCHEMA_SETUP = 111


class AdStatus(StrEnum):
    """Ad lifecycle status. Buyer-visible only when PUBLISHED."""

    DRAFT = "draft"
    ON_MODERATION = "on_moderation"
    PUBLISHED = "published"
    REJECTED = "rejected"
    ON_MODERATION_FAILED = "on_moderation_failed"
    ARCHIVED = "archived"
    DELETED = "deleted"


SEEDABLE_AD_STATUSES: frozenset[AdStatus] = frozenset(
    s for s in AdStatus if s not in {AdStatus.ON_MODERATION_FAILED, AdStatus.DELETED}
)


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


class WriteMode(StrEnum):
    """Publication semantics for a thumbnail write.

    ``CREATE_ONLY`` (default) publishes a new file without ever overwriting an
    existing one -- a collision raises ``FileExistsError`` exactly as the
    historical ``O_EXCL`` create path did.  ``REPLACE`` publishes by replacing
    whatever is at the destination and is reserved for repair callers that
    intend to overwrite a stale leftover.
    """

    CREATE_ONLY = "create_only"
    REPLACE = "replace"


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
    def choices(cls) -> list[tuple[str, str | Promise]]:
        """Return list of (value, label) tuples for template select options."""
        return [
            (cls.ALL_TIME.value, _("All Time")),
            (cls.THIRTY_DAYS.value, _("30 Days")),
            (cls.SEVEN_DAYS.value, _("7 Days")),
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


class BulkModerationError(StrEnum):
    """Per-id error strings for the bulk-moderation JSON API.

    The endpoint's response shape
    ``{"completed": N, "errors": [{"id": .., "error": ..}]}`` is a public
    contract consumed outside this repository, so each failure class is a
    stable string value rather than a new response field. The values are
    deliberately free of driver/exception text (CWE-209 discipline).
    """

    CRITERIA_REJECTED = "Auto-moderation failed"
    TRANSITION_REFUSED = "Transition refused by ad status"
    AD_NOT_FOUND = "Ad not found"
    MAX_ADS_EXCEEDED = "User has reached the maximum number of active ads"
    INVALID_TRANSITION = "Ad is not in a modifiable state"
    PROCESSING_FAILED = "Processing failed"


class ApproveOutcome(StrEnum):
    """Result of a single ad approval attempt.

    Distinguishes the three honest outcomes of ``approve_ad`` so callers can
    surface the real reason to the moderator instead of a 500:

    - ``PUBLISHED``: auto-moderation passed and the ad was published.
    - ``CRITERIA_REJECTED``: auto-moderation ran and the ad failed the criteria
      (the ad is set to ``ON_MODERATION_FAILED``).
    - ``TRANSITION_REFUSED``: the state machine refused the transition (or the
      ad was not in an approvable status to begin with). No state change.
    """

    PUBLISHED = "published"
    CRITERIA_REJECTED = "criteria_rejected"
    TRANSITION_REFUSED = "transition_refused"


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

    @property
    def fts_vector_field(self) -> str:
        """Ads search vector column name for this language."""
        return {
            "ru": "search_vector_ru",
            "bs": "search_vector_bs",
            "en": "search_vector_en",
        }[self.value]


class PriceStep(StrEnum):
    """HTML ``step`` attribute for price filter inputs (catalog/search).

    Controls the spinner increment on the ``min_price`` / ``max_price`` inputs
    in ``filter_form.html``. The filter operates on ``price_normalized_eur``
    (EUR-equivalent), so a step of 1 means 1 EUR unit per click.

    To change the increment in the future, edit the value below.
    """

    DEFAULT = "1"


class ConsentChoice(StrEnum):
    """User consent decision (decision F/K, zone R3)."""

    ACCEPTED = "accepted"
    DECLINED = "declined"
    WITHDRAWN = "withdrawn"


class ConsentActionSource(StrEnum):
    """Mechanism by which a consent action was initiated (06-NEW-02).

    Answers "by what mechanism", never "who" — that is ``initiated_by``. Read the
    two together: ``action_source`` is authoritative for which case a row is, and
    ``initiated_by`` names the acting account when one exists and is not the
    subject. The vocabulary is closed on purpose so a future writer cannot invent
    a fourth spelling.
    """

    SELF_SERVICE = "self_service"  # the subject acted, from their own session
    ANONYMOUS_WEB = "anonymous_web"  # an unidentified visitor acted; no account
    ADMIN_STAFF = "admin_staff"  # a staff account acted via the Django admin
    SYSTEM = "system"  # no human actor; an automated process acted
    UNKNOWN = "unknown"  # DEFAULT — row predates 06-NEW-02; not recoverable


class CookieCategory(StrEnum):
    """Granular cookie categories (ePrivacy Art. 5(3) prior consent)."""

    ESSENTIAL = "essential"
    ANALYTICS = "analytics"
    PREFERENCES = "preferences"


class ConsentVersion(StrEnum):
    """Consent-banner version (GDPR Art. 7(1) accountability — version shown)."""

    V1_0 = "1.0"


class UserRole(StrEnum):
    """Roles defined by Phase 15 authorization spec.

    Single source of truth consumed by both the web process and the bot
    process. Maps to Django identity flags:

    - ``ADMIN``     → ``is_staff or is_superuser``
    - ``SELLER``    → authenticated (and not staff/superuser)
    - ``ANONYMOUS``  → unauthenticated identity
    """

    ANONYMOUS = "anonymous"
    SELLER = "seller"
    ADMIN = "admin"


class SupportChannelType(StrEnum):
    """Channel types for seller support tickets."""

    EMAIL = "email"
    TELEGRAM = "telegram"


class SupportTicketStatus(StrEnum):
    """Lifecycle status of a seller support ticket."""

    OPEN = "open"
    REPLIED = "replied"
    CLOSED = "closed"


__all__ = [
    "AdSort",
    "RateLimitBudget",
    "AdvisoryLockId",
    "AdStatus",
    "SEEDABLE_AD_STATUSES",
    "AdSource",
    "AnalyticsEventType",
    "TrustLevel",
    "ModeratorActionType",
    "BulkModerationAction",
    "BulkModerationError",
    "ApproveOutcome",
    "CategoryRejectReason",
    "AdPriorityLevel",
    "PriorityFilter",
    "ThumbnailSizeStrEnum",
    "WriteMode",
    "SearchSuggestionSource",
    "LanguageLocale",
    "PriceStep",
    "TimeRange",
    "ConsentChoice",
    "ConsentActionSource",
    "CookieCategory",
    "ConsentVersion",
    "UserRole",
    "SupportChannelType",
    "SupportTicketStatus",
]
