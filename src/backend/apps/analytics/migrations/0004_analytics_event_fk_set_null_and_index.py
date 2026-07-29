"""Fix AnalyticsEvent.ad on_delete to SET_NULL and add (event_type, timestamp) index."""

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    """Alter ad FK to SET_NULL for data preservation; add composite index for query perf."""

    dependencies = [
        ("analytics", "0003_daily_ad_metrics"),
    ]

    operations = [
        migrations.AlterField(
            model_name="analyticsevent",
            name="ad",
            field=models.ForeignKey(
                blank=True,
                help_text="Ad associated with this event (null for non-ad events)",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="analytics_events",
                to="ads.ad",
            ),
        ),
        migrations.AddIndex(
            model_name="analyticsevent",
            index=models.Index(
                fields=["event_type", "timestamp"],
                name="idx_analytics_evt_ts",
            ),
        ),
    ]