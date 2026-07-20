"""
Django admin registration for ads app.

Admin with status/category/city/date filters and reject/ban actions.
"""

from django.contrib import admin

from apps.ads.models import Ad, AdImage


def user_link(obj: Ad) -> str:
    """Display user telegram_id as link."""
    if obj.user:
        return str(obj.user.telegram_id)
    return "-"


user_link.short_description = "User (telegram_id)"  # type: ignore[attr-defined]


def rejected_reason(obj: Ad) -> str:
    """Display rejection reason from moderation log (INTERNAL ONLY)."""
    from apps.core.enums import ModeratorActionType

    log = obj.moderation_logs.filter(action_type=ModeratorActionType.REJECT).last()
    if log:
        return log.reason[:100] if len(log.reason) > 100 else log.reason
    return "-"


rejected_reason.short_description = "Rejection Reason"  # type: ignore[attr-defined]


def action_ad_link(obj: AdImage) -> str:
    """Display parent ad as link."""
    return str(obj.ad_id)


action_ad_link.short_description = "Ad ID"  # type: ignore[attr-defined]


@admin.register(Ad)
class AdAdmin(admin.ModelAdmin):
    """
    Ad admin with listing filters and reject/ban moderation actions.

    Failed-ads list shows rejection reason (INTERNAL ONLY, never to seller).
    """

    list_display = [
        "id",
        "title",
        "status",
        "category",
        "city",
        user_link,
        "published_at",
    ]
    list_filter = ["status", "category", "city", "created_at", "published_at"]
    search_fields = ["title", "description"]
    readonly_fields = [
        "moderation_failed_at",
        "rejected_at",
        "published_by",
        "moderated_by",
    ]
    date_hierarchy = "created_at"
    actions = ["action_reject", "action_ban_user"]

    def get_queryset(self, request):
        """Optimize queryset with related select."""
        qs = super().get_queryset(request)
        return qs.select_related("user", "category", "city")

    @admin.action(description="Reject selected ads")
    def action_reject(self, request, queryset):
        """Bulk reject action for moderation."""
        # This is a placeholder - actual rejection logic would require a reason
        # and would trigger ModeratorActionLog creation
        pass

    @admin.action(description="Ban user from selected ads")
    def action_ban_user(self, request, queryset):
        """Bulk ban users from selected ads."""
        from apps.users.models import User

        user_ids = set(queryset.values_list("user_id", flat=True))

        # Log ban actions for each user
        for user_id in user_ids:
            if user_id:
                from apps.moderation.services.moderation_log import log_ban_account

                log_ban_account(
                    user_id=user_id,
                    moderator_id=request.user.id,
                    reason="Bulk ban via admin action",
                )

        User.objects.filter(telegram_id__in=user_ids).update(is_banned=True)


@admin.register(AdImage)
class AdImageAdmin(admin.ModelAdmin):
    """
    AdImage admin for managing ad images.
    """

    list_display = ["id", action_ad_link, "position"]
    list_filter = ["position"]
    search_fields = ["ad__title"]
    readonly_fields = ["image", "telegram_file_id", "position"]

    def has_add_permission(self, request) -> bool:
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        return False