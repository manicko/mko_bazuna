"""
Django admin registration for analytics app.

Provides metrics view aggregating AnalyticsEvent by type and date.
"""

import logging

from apps.analytics.models import AnalyticsEvent, DailyAdMetrics
from django.contrib import admin
from django.db.models import Count
from django.db.models.functions import TruncDate

logger = logging.getLogger(__name__)


@admin.register(AnalyticsEvent)
class AnalyticsEventAdmin(admin.ModelAdmin):
    """
    Analytics event admin with metrics view.

    Aggregates events by type and date for product metrics.
    """

    list_display = ["event_type", "timestamp", "user_link"]
    list_filter = ["event_type", "timestamp"]
    date_hierarchy = "timestamp"
    readonly_fields = ["event_type", "timestamp", "user"]

    def user_link(self, obj):
        """Display user telegram_id if available."""
        if obj.user:
            return str(obj.user.telegram_id)
        return "-"

    user_link.short_description = "User (telegram_id)"  # type: ignore[attr-defined]

    def has_add_permission(self, request):
        """Events are created programmatically, not via admin."""
        return False

    def has_change_permission(self, request, obj=None):
        """Events are read-only."""
        return False

    def has_delete_permission(self, request, obj=None):
        """Events are preserved for metrics."""
        return False

    def changelist_view(self, request, extra_context=None):
        """Add metrics data to the changelist view."""
        extra_context = extra_context or {}

        # Aggregate events by event_type
        type_aggregates = (
            AnalyticsEvent.objects.values("event_type")
            .annotate(count=Count("id"))
            .order_by("-count")
        )

        # Aggregate events by date (last 30 days)
        from datetime import timedelta

        from django.utils import timezone

        thirty_days_ago = timezone.now() - timedelta(days=30)
        date_aggregates = (
            AnalyticsEvent.objects.filter(timestamp__gte=thirty_days_ago)
            .annotate(date=TruncDate("timestamp"))
            .values("date")
            .annotate(count=Count("id"))
            .order_by("date")
        )

        extra_context["type_aggregates"] = type_aggregates
        extra_context["date_aggregates"] = date_aggregates

        return super().changelist_view(request, extra_context=extra_context)


@admin.register(DailyAdMetrics)
class DailyAdMetricsAdmin(admin.ModelAdmin):
    """Admin for daily aggregated ad metrics."""

    list_display = ["ad", "date", "views_count", "contacts_count", "trust_score"]
    list_filter = ["date"]
    date_hierarchy = "date"
    readonly_fields = ["created_at", "updated_at"]

    def has_add_permission(self, request):
        """Metrics are created by management command, not via admin."""
        return False

    def has_change_permission(self, request, obj=None):
        """Metrics are read-only."""
        return False

    def has_delete_permission(self, request, obj=None):
        """Metrics can be deleted for cleanup."""
        return True
