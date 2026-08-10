"""
Analytics models for Mko Bazuna.

AnalyticsEvent for product metrics.
"""

from apps.core.enums import AnalyticsEventType
from django.db import models
from django.utils import timezone


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
        default=timezone.now,
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
    ad = models.ForeignKey(
        "ads.Ad",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="analytics_events",
        help_text="Ad associated with this event (null for non-ad events)",
    )

    class Meta:
        db_table = "analytics_events"
        indexes = [
            models.Index(
                fields=["event_type", "timestamp"],
                name="idx_analytics_evt_ts",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.event_type} at {self.timestamp}"

class DailyAdMetrics(models.Model):
    """Daily aggregated metrics per ad for efficient dashboard queries."""

    ad = models.ForeignKey(
        "ads.Ad",
        on_delete=models.CASCADE,
        related_name="daily_metrics",
        help_text="Ad this metric belongs to",
    )
    date = models.DateField(help_text="Date of aggregation")
    views_count = models.PositiveIntegerField(
        default=0,
        help_text="Number of views on this date",
    )
    contacts_count = models.PositiveIntegerField(
        default=0,
        help_text="Number of contacts on this date",
    )
    trust_score = models.FloatField(
        null=True,
        blank=True,
        help_text="Auto-computed trust score (0–100)",
    )
    avg_response_time = models.FloatField(
        null=True,
        blank=True,
        help_text="Average response time in hours",
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        help_text="Record creation timestamp",
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        help_text="Record last update timestamp",
    )

    class Meta:
        db_table = "daily_ad_metrics"
        constraints = [
            models.UniqueConstraint(
                fields=["ad", "date"],
                name="uq_daily_ad_metrics_ad_date",
            )
        ]
        indexes = [
            models.Index(
                fields=["date", "-views_count"],
                name="idx_daily_metrics_date_views",
            )
        ]

    def __str__(self) -> str:
        return f"{self.ad_id} / {self.date} — v:{self.views_count} c:{self.contacts_count}"
