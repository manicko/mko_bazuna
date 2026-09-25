"""
Core models for Mko Bazuna.

Provides shared singleton models used across apps.
"""

from django.conf import settings
from django.core.validators import RegexValidator
from django.db import models
from django.utils import timezone

from apps.core.enums import SupportChannelType, SupportTicketStatus


class SiteConfig(models.Model):
    """
    Site name singleton for centralized branding (Problem 03).

    Exactly one row exists (pk=1). Edited by admin at runtime via Django
    admin. The site name is read through a cache layer on every request
    that renders a page title or `<title>` tag.
    """

    name = models.CharField(
        max_length=255,
        default="Bazuna",
        help_text="Site name displayed in page titles and headers",
    )

    bot_username = models.CharField(
        max_length=32,
        default="bazuna_bot",
        help_text="Telegram bot username without @ prefix",
        validators=[
            RegexValidator(
                regex=r"^[A-Za-z0-9_]{3,32}$",
                message="Bot username must be 3-32 characters, alphanumeric and underscore only",
            ),
        ],
    )

    class Meta:
        db_table = "site_config"
        verbose_name = "Site Config"
        verbose_name_plural = "Site Config"

    def __str__(self) -> str:
        return str(self.name)

    @classmethod
    def get_singleton(cls) -> SiteConfig:
        """Get the singleton instance, creating it if necessary."""
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class SupportContact(models.Model):
    """A support channel (email or Telegram) offered to sellers."""

    channel_type = models.CharField(
        max_length=10,
        choices=[(s.value, s.value) for s in SupportChannelType],
        help_text="Channel type: email or telegram",
    )
    label = models.CharField(
        max_length=255,
        help_text="Human-readable label for this support contact",
    )
    email = models.EmailField(
        null=True,
        blank=True,
        help_text="Email address (required when channel_type is email)",
    )
    telegram_id = models.BigIntegerField(
        null=True,
        blank=True,
        help_text="Telegram user/channel ID (required when channel_type is telegram)",
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Whether this support contact is currently offered",
    )
    ordering = models.PositiveSmallIntegerField(
        default=0,
        help_text="Display order (lower sorts first)",
    )

    class Meta:
        db_table = "support_contacts"
        verbose_name = "Support Contact"
        verbose_name_plural = "Support Contacts"
        ordering = ["ordering", "id"]
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(
                        channel_type=SupportChannelType.EMAIL,
                        email__isnull=False,
                        telegram_id__isnull=True,
                    )
                    | models.Q(
                        channel_type=SupportChannelType.TELEGRAM,
                        telegram_id__isnull=False,
                        email__isnull=True,
                    )
                ),
                name="support_contact_channel_value_required",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.channel_type}: {self.label}"


class SupportTicket(models.Model):
    """A support ticket submitted by a seller (identified via Telegram)."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="support_tickets",
        help_text="Authenticated user who opened the ticket (null if anonymous)",
    )
    chat_id = models.BigIntegerField(
        help_text="Telegram chat_id for anonymous attribution",
    )
    telegram_id = models.BigIntegerField(
        help_text="User's Telegram ID",
    )
    username = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        help_text="Telegram username (if available)",
    )
    text = models.TextField(
        help_text="Ticket body / message text",
    )
    status = models.CharField(
        max_length=10,
        choices=[(s.value, s.value) for s in SupportTicketStatus],
        default=SupportTicketStatus.OPEN,
        help_text="Current lifecycle status of the ticket",
    )
    ticket_ref = models.CharField(
        max_length=32,
        unique=True,
        editable=False,
        help_text="Human-readable reference: SUP-YYYYMM-NNN",
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        help_text="When the ticket was created",
    )

    class Meta:
        db_table = "support_tickets"
        verbose_name = "Support Ticket"
        verbose_name_plural = "Support Tickets"
        ordering = ["-created_at"]

    def save(self, *args, **kwargs) -> None:
        """Auto-generate ``ticket_ref`` (``SUP-YYYYMM-NNN``) on first save."""
        if not self.pk:
            now = timezone.now()
            year_month = now.strftime("%Y%m")
            sequence = (
                SupportTicket.objects.filter(
                    created_at__year=now.year,
                    created_at__month=now.month,
                ).count()
                + 1
            )
            self.ticket_ref = f"SUP-{year_month}-{sequence:03d}"
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"SupportTicket {self.ticket_ref}"
