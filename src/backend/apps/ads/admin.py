"""
Django admin registration for ads app.

Admin with status/category/city/date filters and reject/ban actions.
Includes listing_purpose and features display for lookup integration.
"""

import logging

from apps.ads.models import Ad, AdImage
from apps.core.enums import AdStatus, ModeratorActionType
from apps.moderation.admin_actions import (
    bulk_approve,
    bulk_ban_users,
    bulk_delete,
    bulk_reject,
)
from apps.moderation.services.priority import PriorityService
from django.contrib import admin

logger = logging.getLogger(__name__)


def user_link(obj: Ad) -> str:
    """Display user telegram_id as link."""
    if obj.user:
        return str(obj.user.telegram_id)
    return "-"


user_link.short_description = "User (telegram_id)"  # type: ignore[attr-defined]


def rejected_reason(obj: Ad) -> str:
    """Display rejection reason from moderation log (INTERNAL ONLY)."""
    log = obj.moderation_logs.filter(action_type=ModeratorActionType.REJECT).last()
    if log:
        return log.reason[:100] if len(log.reason) > 100 else log.reason
    return "-"


rejected_reason.short_description = "Rejection Reason"  # type: ignore[attr-defined]


def action_ad_link(obj: AdImage) -> str:
    """Display parent ad as link."""
    return str(obj.ad_id)


action_ad_link.short_description = "Ad ID"  # type: ignore[attr-defined]


def features_list(obj: Ad) -> str:
    """Display features as comma-separated slugs."""
    return ", ".join(f.slug for f in obj.features.all())


features_list.short_description = "Features"  # type: ignore[attr-defined]


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
        "listing_purpose",
        user_link,
        "published_at",
        rejected_reason,
    ]
    list_filter = [
        "status",
        "category",
        "city",
        "listing_purpose",
        "created_at",
        "published_at",
        "moderation_priority__priority_level",
    ]
    search_fields = ["title", "description"]
    readonly_fields = [
        "moderation_failed_at",
        "rejected_at",
        "published_by",
        "moderated_by",
        "listing_purpose",
    ]
    date_hierarchy = "created_at"
    actions = [
        "action_reject",
        "action_ban_user",
        "action_soft_delete",
        "action_approve",
    ]

    def get_queryset(self, request):
        """Optimize queryset with related select and priority prefetch."""
        qs = super().get_queryset(request)
        return qs.select_related(
            "user", "category", "city", "listing_purpose"
        ).prefetch_related("moderation_priority", "features")

    def has_view_permission(self, request, obj=None) -> bool:
        """Restrict view to staff/superuser only."""
        return request.user.is_staff or request.user.is_superuser

    def has_change_permission(self, request, obj=None) -> bool:
        """Restrict change to staff/superuser only."""
        return request.user.is_staff or request.user.is_superuser

    @admin.action(description="Reject selected ads")
    def action_reject(self, request, queryset):
        """Bulk reject action for moderation."""
        count = bulk_reject(
            queryset, request.user.id, "Bulk rejection via admin action"
        )
        self.message_user(request, f"Rejected {count} ad(s).", level="success")

    @admin.action(description="Approve selected ads")
    def action_approve(self, request, queryset):
        """Bulk approve action for moderation."""
        count = bulk_approve(queryset, request.user.id)
        self.message_user(
            request, f"Approved {count} ad(s) for publication.", level="success"
        )

    @admin.action(description="Ban users from selected ads")
    def action_ban_user(self, request, queryset):
        """Bulk ban users from selected ads."""
        count = bulk_ban_users(queryset, request.user.id, "Bulk ban via admin action")
        self.message_user(request, f"Banned {count} user(s).", level="success")

    @admin.action(description="Soft delete selected ads")
    def action_soft_delete(self, request, queryset):
        """Bulk soft delete action for moderation."""
        count = bulk_delete(queryset, request.user.id, "Bulk deletion via admin action")
        self.message_user(request, f"Deleted {count} ad(s).", level="success")

    def changelist_view(self, request, extra_context=None):
        """Custom changelist with moderation queue presets and priority stats."""
        extra_context = extra_context or {}

        # Add quick filter links for moderation queues
        extra_context["moderation_queues"] = [
            {"name": "On Moderation", "status": AdStatus.ON_MODERATION},
            {"name": "Failed", "status": AdStatus.ON_MODERATION_FAILED},
            {"name": "Rejected", "status": AdStatus.REJECTED},
        ]

        # Add priority queue stats for admin dashboard
        service = PriorityService()
        extra_context["priority_queue_stats"] = service.get_priority_counts()

        return super().changelist_view(request, extra_context=extra_context)


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

    def has_view_permission(self, request, obj=None) -> bool:
        return request.user.is_staff or request.user.is_superuser

    def has_delete_permission(self, request, obj=None) -> bool:
        return False
