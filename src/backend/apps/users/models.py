"""
User and LoginToken models for Mko Bazuna.

One user = one Telegram account. Authentication via atomic login tokens.
"""

from django.contrib.auth.models import AbstractUser
from django.db import models

from apps.core.enums import (
    AdSource,
    ConsentActionSource,
    ConsentChoice,
    ConsentVersion,
    LanguageLocale,
    UserRole,
)


class User(AbstractUser):
    """
    Custom user model for Mko Bazuna.

    One user = one Telegram account. Telegram is the primary auth method.
    Admin-created accounts require a telegram_id placeholder.
    """

    # Override username to be nullable (Telegram login is primary auth).
    # unique=True is required by Django because USERNAME_FIELD = "username".
    # PostgreSQL allows multiple NULLs in a unique constraint, so non-admin
    # users (who have no username) are unaffected.
    username = models.CharField(
        "username",
        max_length=150,
        unique=True,
        blank=True,
        null=True,
        help_text="Optional public @username; NOT used for t.me link or publishing",
    )

    # Telegram identifier (unique, required for active users; nullified on GDPR erasure)
    telegram_id = models.BigIntegerField(
        unique=True,
        blank=True,
        null=True,
        help_text="Telegram user ID; required for authentication (nullified on GDPR withdrawal)",
    )

    # Stable Telegram chat ID (set on first bot contact, never nullified on withdraw)
    chat_id = models.BigIntegerField(
        unique=True,
        db_index=True,
        help_text="Stable Telegram chat ID; set on first bot contact, never nullified",
    )

    # Account state
    is_banned = models.BooleanField(
        default=False,  # pyright: ignore[reportArgumentType]
        help_text="Account is blocked from posting",
    )
    is_deleted = models.BooleanField(
        default=False,  # pyright: ignore[reportArgumentType]
        help_text="Soft delete flag",
    )
    is_declined = models.BooleanField(
        default=False,  # pyright: ignore[reportArgumentType]
        help_text="User declined consent (browse-only mode)",
    )
    ads_auto_publish = models.BooleanField(
        default=True,  # pyright: ignore[reportArgumentType]
        help_text="Publishing ban - when False, ads go to DRAFT instead of ON_MODERATION",
    )
    telegram_premium = models.BooleanField(
        default=False,  # pyright: ignore[reportArgumentType]
        help_text="User has Telegram Premium subscription",
    )

    # Buyer's preferred city for default catalog/search filtering.
    # Nullable; SET_NULL on city removal (a preference must never block a city
    # from being removed from the catalog). Slug cloud: related_name="+".
    preferred_city = models.ForeignKey(
        "locations.City",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        help_text="Buyer's preferred city for default catalog/search filtering (nullable; SET_NULL on city removal)",
    )

    # Timestamps for account lifecycle
    deleted_at = models.DateTimeField(
        blank=True,
        null=True,
        help_text="Soft delete timestamp",
    )
    consent_given_at = models.DateTimeField(
        blank=True,
        null=True,
        help_text="GDPR consent given timestamp (US-A8 / decision F)",
    )
    consent_revoked_at = models.DateTimeField(
        blank=True,
        null=True,
        help_text="GDPR consent revoked timestamp",
    )

    # Telegram-reported language code for localized bot messages.
    # Defaults to Russian; updated when the user runs /language in the bot.
    telegram_language = models.CharField(
        max_length=5,
        default=LanguageLocale.RUSSIAN.value,
        choices=[(loc.value, loc.value) for loc in LanguageLocale],
        help_text="Telegram-reported language code for localized bot messages",
    )

    # Origin of record (null = real user, 'seed' = seed-generated)
    source = models.CharField(
        max_length=20,
        choices=[(s.value, s.value) for s in AdSource],
        default=None,
        null=True,
        blank=True,
        db_index=True,
        help_text="Origin of record (null = real user, 'seed' = seed-generated)",
    )

    # Use username field for Django admin authentication (telegram_id is BigInteger, not suitable as USERNAME_FIELD)
    USERNAME_FIELD = "username"

    # Override groups/user_permissions to avoid clashes with auth.User
    groups = models.ManyToManyField(
        "auth.Group",
        blank=True,
        help_text="The groups this user belongs to.",
        related_name="users",  # Unique related_name to avoid clash
        verbose_name="groups",
    )
    user_permissions = models.ManyToManyField(
        "auth.Permission",
        blank=True,
        help_text="Specific permissions for this user.",
        related_name="users",  # Unique related_name to avoid clash
        verbose_name="user permissions",
    )

    class Meta:
        db_table = "users"
        indexes = [
            models.Index(
                name="IX_users_erasure_sweep",
                fields=["consent_revoked_at"],
            ),
        ]

    def __str__(self) -> str:
        return f"User {self.id}"

    @property
    def role(self) -> UserRole:
        """Resolve this identity's role from Django flags (Phase 15 spec).

        Maps ``is_staff`` / ``is_superuser`` to the ``UserRole`` StrEnum —
        the single source of truth consumed by both processes.

        - ``is_staff or is_superuser`` → ``ADMIN``
        - authenticated (and not staff/superuser) → ``SELLER``
        - unauthenticated identity → ``ANONYMOUS``
        """
        if self.is_staff or self.is_superuser:
            return UserRole.ADMIN
        if self.is_authenticated:
            return UserRole.SELLER
        return UserRole.ANONYMOUS


class LoginToken(models.Model):
    """
    Atomic Telegram login token.

    Token is claimed exactly once under shared lock. Raw token is NEVER stored.
    Two-phase claim:
    1. Bot: sets telegram_id
    2. Web: sets consumed_at
    """

    token_hash = models.CharField(
        max_length=64,
        unique=True,
        db_index=True,
        help_text="SHA-256 of raw 32-char URL-safe token; raw token NEVER stored",
    )
    telegram_id = models.BigIntegerField(
        blank=True,
        null=True,
        help_text="Filled by BOT on /start login_<token>",
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        help_text="Token creation timestamp",
    )
    expires_at = models.DateTimeField(
        help_text="+5 min from creation",
    )
    consumed_at = models.DateTimeField(
        blank=True,
        null=True,
        help_text="Filled by WEB on login completion",
    )
    browser_binding = models.CharField(
        max_length=64,
        blank=True,
        null=True,
        help_text=(
            "SHA-256 hex digest of the issuing browser's __Host-login_browser_id "
            "cookie; the raw id is never stored. NULL means the row predates the "
            "binding (or was written without one) and is never redeemable."
        ),
    )

    class Meta:
        db_table = "login_tokens"

    def __str__(self) -> str:
        return f"LoginToken {self.id}"


class ConsentRecord(models.Model):
    """
    Server-side consent audit record (GDPR Article 7(1) accountability).

    Records every consent action (accept / decline / withdraw) with the banner
    version shown, the choice made, granular categories, and HTTP-layer context
    (anonymized IP + truncated user agent) for demonstrable proof of consent.

    ``user`` is nullable: anonymous visitors record consent via cookies only and
    are identified by ``session_key`` instead of a user account.

    Actor definition (``06-NEW-02``): the actor is the account that performed the
    action, and it is recorded **only when that account is not the subject**.
    ``user`` already names the subject, so a self-action would store the same
    account twice. Write-time invariant: ``initiated_by IS NOT NULL`` at insert
    only when it is a different row from ``user``. Read the pair, never one column
    alone — ``action_source`` is authoritative for *which case* the row is, and
    ``initiated_by`` names the account when one exists. A null ``initiated_by``
    means either "no acting account distinct from the subject" (a self-service
    action, an anonymous visitor or a system action) **or** an ``admin_staff``
    attribution that has since expired at the 12-month actor window
    (``purge_consent_records``) or whose acting account was hard-deleted
    (``SET_NULL``); ``action_source`` tells those apart — ``admin_staff`` is
    written only when a staff account acted.

    Retention is **per field**: ``user`` (the subject) follows the general
    record retention — the 90-day fingerprint bound; ``initiated_by`` (the actor)
    is irreversibly anonymised **12 months after the action**, unless the row is
    under a documented ``legal_hold``; the event and timestamp fields (``choice``,
    ``categories``, ``consent_version``, ``consent_given_at``) are anonymised,
    never deleted. The 12-month actor period is a **chosen minimisation period
    justified by purpose — one full operational/audit cycle — and explicitly NOT
    a statutory term**; it is deliberately shorter than the 5-year decision
    bound, which governs the decision fields only.
    """

    user = models.ForeignKey(
        "users.User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="consent_records",
        help_text=(
            "The subject of the consent action (null for anonymous "
            "cookie-based consent). This is NOT the actor — a third-party "
            "actor is recorded only in initiated_by (06-NEW-02)."
        ),
    )
    session_key = models.CharField(
        max_length=40,
        null=True,
        blank=True,
        help_text="Session key identifying an anonymous consent action",
    )
    consent_given_at = models.DateTimeField(
        auto_now_add=True,
        help_text="Timestamp of the consent action",
    )
    consent_version = models.CharField(
        max_length=20,
        default=ConsentVersion.V1_0.value,
        help_text="Banner text version shown to the user",
    )
    choice = models.CharField(
        max_length=20,
        choices=[(c.value, c.value) for c in ConsentChoice],
        help_text="Consent choice made by the user",
    )
    categories = models.JSONField(
        default=dict,
        help_text="Granular category flags (CookieCategory -> bool)",
    )
    ip_address = models.GenericIPAddressField(
        null=True,
        blank=True,
        help_text="Anonymized IP (IPv4 last octet zeroed; IPv6 /64 prefix retained)",
    )
    user_agent = models.TextField(
        blank=True,
        max_length=500,
        help_text="Truncated User-Agent header from the consent request",
    )
    initiated_by = models.ForeignKey(
        "users.User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        help_text=(
            "Acting account, recorded ONLY when it is not the subject "
            "(06-NEW-02). NULL means either no acting account distinct from the "
            "subject — a self-service action, an anonymous visitor, or a system "
            "action — or an admin_staff attribution cleared after 12 months "
            "(unless held) or emptied by SET_NULL when the acting account was "
            "hard-deleted; action_source tells those apart. Never CASCADE: "
            "consent_hard_delete deletes User rows and a cascade would destroy "
            "the Art. 7(1) ledger. The acting account is irreversibly anonymised "
            "12 months after the action — a chosen minimisation period justified "
            "by purpose, NOT a statutory term, and deliberately shorter than the "
            "5-year decision bound which governs the decision fields only. A "
            "documented legal_hold suspends this actor erasure."
        ),
    )
    action_source = models.CharField(
        max_length=20,
        choices=[(s.value, s.value) for s in ConsentActionSource],
        default=ConsentActionSource.UNKNOWN.value,
        blank=True,
        db_index=True,
        help_text=(
            "Mechanism that initiated the action (06-NEW-02). UNKNOWN is the "
            "default and means the row predates this column: the mechanism was "
            "never captured and is not recoverable. No row written through the "
            "recording service carries UNKNOWN."
        ),
    )
    legal_hold = models.BooleanField(
        default=False,  # pyright: ignore[reportArgumentType]
        help_text=(
            "Documented legal hold (06-NEW-02). Default False leaves every "
            "existing row un-held, so no backfill is needed. A hold suspends the "
            "12-month actor erasure ONLY: it never restores what the 90-day "
            "fingerprint window already cleared, and it never extends the "
            "decision fields, which are anonymised-but-never-deleted at every "
            "age. Superuser-settable (exemption from erasure, not evidence)."
        ),
    )

    class Meta:
        db_table = "consent_records"
        ordering = ["-consent_given_at"]
        indexes = [
            models.Index(
                fields=["consent_given_at"], name="IX_consent_records_sweep"
            ),
        ]

    def __str__(self) -> str:
        return f"ConsentRecord {self.id} ({self.choice})"
