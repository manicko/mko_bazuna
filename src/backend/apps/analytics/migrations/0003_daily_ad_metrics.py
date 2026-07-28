"""Create DailyAdMetrics model for daily aggregated ad metrics."""

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    """Create daily_ad_metrics table with constraints and indexes."""

    dependencies = [
        ("ads", "0006_backfill_translations"),
        ("analytics", "0002_analytics_event_ad_fk"),
    ]

    operations = [
        migrations.CreateModel(
            name="DailyAdMetrics",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "ad",
                    models.ForeignKey(
                        help_text="Ad this metric belongs to",
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="daily_metrics",
                        to="ads.ad",
                    ),
                ),
                (
                    "date",
                    models.DateField(
                        help_text="Date of aggregation",
                    ),
                ),
                (
                    "views_count",
                    models.PositiveIntegerField(
                        default=0,
                        help_text="Number of views on this date",
                    ),
                ),
                (
                    "contacts_count",
                    models.PositiveIntegerField(
                        default=0,
                        help_text="Number of contacts on this date",
                    ),
                ),
                (
                    "trust_score",
                    models.FloatField(
                        blank=True,
                        help_text="Auto-computed trust score (0–1)",
                        null=True,
                    ),
                ),
                (
                    "avg_response_time",
                    models.FloatField(
                        blank=True,
                        help_text="Average response time in seconds",
                        null=True,
                    ),
                ),
                (
                    "created_at",
                    models.DateTimeField(
                        auto_now_add=True,
                        help_text="Record creation timestamp",
                    ),
                ),
                (
                    "updated_at",
                    models.DateTimeField(
                        auto_now=True,
                        help_text="Record last update timestamp",
                    ),
                ),
            ],
            options={
                "db_table": "daily_ad_metrics",
                "constraints": [
                    models.UniqueConstraint(
                        fields=["ad", "date"],
                        name="uq_daily_ad_metrics_ad_date",
                    ),
                ],
                "indexes": [
                    models.Index(
                        fields=["date", "-views_count"],
                        name="idx_daily_metrics_date_views",
                    ),
                ],
            },
            bases=(models.Model,),
        ),
    ]