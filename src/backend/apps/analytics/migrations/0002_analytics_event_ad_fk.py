"""Add ad ForeignKey to AnalyticsEvent model."""

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    """Add ad ForeignKey to AnalyticsEvent."""

    dependencies = [
        ("ads", "0006_backfill_translations"),
        ("analytics", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="analyticsevent",
            name="ad",
            field=models.ForeignKey(
                blank=True,
                help_text="Ad associated with this event (null for non-ad events)",
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="analytics_events",
                to="ads.ad",
            ),
        ),
    ]