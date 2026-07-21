"""
User and LoginToken models for Mko Bazuna.

One user = one Telegram account. Authentication via atomic login tokens.
"""


from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    """
    Custom user model for Mko Bazuna.

    One user = one Telegram account. Telegram is the primary auth method.
    Admin-created accounts require a telegram_id placeholder.
    """

    # Override username to be nullable (Telegram login is primary auth)
    username = models.CharField(
        "username",
        max_length=150,
        blank=True,
        null=True,
        help_text="Optional public @username; NOT used for t.me link or publishing",
    )

    # Telegram identifier (unique, required for auth - use placeholder for admin accounts)
    telegram_id = models.BigIntegerField(
        unique=True,
        help_text="Telegram user ID; required for authentication",
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
    ads_auto_publish = models.BooleanField(
        default=True,  # pyright: ignore[reportArgumentType]
        help_text="Publishing ban - when False, ads go to DRAFT instead of ON_MODERATION",
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
    hard_delete_at = models.DateTimeField(
        blank=True,
        null=True,
        help_text="Scheduled hard-delete timestamp (telegram_id nulled 30 days after consent withdrawal)",
    )

    # Use telegram_id as the username field for authentication
    USERNAME_FIELD = "telegram_id"

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
        return f"User {self.telegram_id or self.id}"


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