"""
Django admin registration for moderation app.

Singleton criteria editing and read-only action logs.
"""

from apps.moderation.models import ModerationCriteria, ModeratorActionLog
from django.contrib import admin


def log_ad_link(obj: ModeratorActionLog) -> str:
    """Display ad ID if available."""
    return str(obj.ad_id) if obj.ad_id else "-"


log_ad_link.short_description = "Ad ID"  # type: ignore[attr-defined]


def log_user_link(obj: ModeratorActionLog) -> str:
    """Display user telegram_id if available."""
    if obj.user:
        return str(obj.user.telegram_id)
    return "-"


log_user_link.short_description = "User (telegram_id)"  # type: ignore[attr-defined]


@admin.register(ModerationCriteria)
class ModerationCriteriaAdmin(admin.ModelAdmin):
    """
    ModerationCriteria singleton admin.

    Exactly one row exists, edited by admin at runtime per US-A11.
    """

    list_display = ["id", "title_min_length", "title_max_length", "price_required", "updated_at"]
    readonly_fields = ["updated_at", "updated_by"]

    def has_add_permission(self, request) -> bool:
        # Singleton - row created automatically if missing
        return False

    def has_delete_permission(self, request, obj=None) -> bool:
        return False

    def save_model(self, request, obj, form, change):
        """Track who updates the criteria."""
        if change:
            obj.updated_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(ModeratorActionLog)
class ModeratorActionLogAdmin(admin.ModelAdmin):
    """
    Moderator action audit log - read-only.

    NEVER shown to sellers per US-A11.
    """

    list_display = ["id", "action_type", log_ad_link, log_user_link, "created_at"]
    list_filter = ["action_type", "created_at"]
    readonly_fields = ["ad", "user", "action_type", "reason", "created_at"]

    def has_add_permission(self, request) -> bool:
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        return False

    def has_delete_permission(self, request, obj=None) -> bool:
        return False