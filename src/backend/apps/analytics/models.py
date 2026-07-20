"""
Analytics models for Mko Bazuna.

AnalyticsEvent for product metrics.
"""

from django.db import models

from apps.core.enums import AnalyticsEventType


class AnalyticsEvent(models.Model):
    """
    Analytics event for product metrics.

    user_id is nullable and SET NULL on erasure (zone R5) to preserve aggregates.
    """

    event_type = models.CharField(
        max_length=30,
        choices=[(e.value, e.value) for e in AnalyticsEventType],
        help_text="Type of analytics event",
    )
    timestamp = models.DateTimeField(
        auto_now_add=True,
        help_text="Event timestamp",
    )
    user = models.ForeignKey(
        "users.User",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="analytics_events",
        help_text="User who triggered event (SET NULL on erasure)",
    )

    class Meta:
        db_table = "analytics_events"

    def __str__(self) -> str:
        return f"{self.event_type} at {self.timestamp}"