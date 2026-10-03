"""
Django admin registration for core app.

SiteConfig singleton editing with add/delete disabled.
"""

from django.contrib import admin

from apps.core.models import SiteConfig, SupportContact, SupportTicket
from apps.core.utils.sanitize import mask_telegram_id


@admin.register(SiteConfig)
class SiteConfigAdmin(admin.ModelAdmin):
    """
    SiteConfig singleton admin.

    Exactly one row exists, edited by admin at runtime for centralized
    site name branding.
    """

    list_display = ["name", "bot_username"]
    readonly_fields = []

    def has_add_permission(self, request) -> bool:
        # Singleton - row created automatically if missing
        return False

    def has_delete_permission(self, request, obj=None) -> bool:
        return False


@admin.register(SupportContact)
class SupportContactAdmin(admin.ModelAdmin):
    """
    SupportContact admin (email/Telegram channels configured by staff).

    Add and delete are enabled so staff can manage the full contact list.
    ``is_active`` and ``ordering`` are editable inline from the changelist.
    """

    list_display = ["label", "channel_type", "email", "telegram_id", "is_active", "ordering"]
    list_editable = ["is_active", "ordering"]
    list_filter = ["channel_type", "is_active"]
    search_fields = ["label", "email", "telegram_id"]


@admin.register(SupportTicket)
class SupportTicketAdmin(admin.ModelAdmin):
    """
    SupportTicket admin (view and filter only).

    Tickets are created via the Telegram bot; the admin can only view and
    filter them. Add/delete are disabled because the bot is the only writer and
    tickets are never edited by staff. A ticket is not an audit trail: it is
    personal data deleted with its subject on withdrawal or erasure
    (06-PII-101).
    """

    list_display = ["ticket_ref", "status", "user", "chat_id_display", "telegram_id_display", "created_at"]
    list_filter = ["status", "created_at"]
    search_fields = ["ticket_ref", "telegram_id", "username"]
    readonly_fields = [
        "ticket_ref",
        "chat_id",
        "telegram_id",
        "username",
        "text",
        "user",
        "created_at",
    ]

    def has_add_permission(self, request) -> bool:
        # Tickets created via bot, not admin
        return False

    def has_delete_permission(self, request, obj=None) -> bool:
        # Audit trail preservation
        return False

    @admin.display(description="Chat ID (masked)", ordering="chat_id")
    def chat_id_display(self, obj: SupportTicket) -> str:
        """Render the masked Telegram chat ID of the requester (06-PII-106)."""
        return mask_telegram_id(obj.chat_id)

    @admin.display(description="Telegram ID (masked)", ordering="telegram_id")
    def telegram_id_display(self, obj: SupportTicket) -> str:
        """Render the masked Telegram ID of the requester (06-PII-106)."""
        return mask_telegram_id(obj.telegram_id)
