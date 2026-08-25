"""
User and LoginToken models for Mko Bazuna.

One user = one Telegram account. Authentication via atomic login tokens.
"""

from django.contrib.auth.models import AbstractUser
from django.db import models

from apps.core.enums import AdSource, ConsentChoice, LanguageLocale


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
    """

    user = models.ForeignKey(
        "users.User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="consent_records",
        help_text="User who acted (null for anonymous cookie-based consent)",
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
        default="1.0",
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
        help_text="Anonymized IP (last IPv4 octet zeroed)",
    )
    user_agent = models.TextField(
        blank=True,
        max_length=500,
        help_text="Truncated User-Agent header from the consent request",
    )

    class Meta:
        db_table = "consent_records"
        ordering = ["-consent_given_at"]

    def __str__(self) -> str:
        return f"ConsentRecord {self.id} ({self.choice})"
