# Generated migration for AdModerationPriority model

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    """Create ad_moderation_priorities table with indexes."""

    dependencies = [
        ("ads", "0007_adimage_thumbnails"),
        ("moderation", "0002_singleton_enforcement"),
    ]

    operations = [
        migrations.CreateModel(
            name="AdModerationPriority",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("base_score", models.PositiveSmallIntegerField(default=0)),
                ("priority_level", models.CharField(
                    max_length=10,
                    choices=[("high", "high"), ("medium", "medium"), ("low", "low")],
                )),
                ("flags", models.JSONField(blank=True, default=list)),
                ("confidence_score", models.FloatField(default=0.0)),
                ("escalation_required", models.BooleanField(default=False)),
                ("ad", models.OneToOneField(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="moderation_priority",
                    to="ads.ad",
                )),
            ],
            options={
                "db_table": "ad_moderation_priorities",
                "indexes": [
                    models.Index(fields=["priority_level"], name="ad_mod_prior_priority_6b3c6b_idx"),
                    models.Index(fields=["base_score"], name="ad_mod_prior_base_sc_2f3f63_idx"),
                    models.Index(fields=["escalation_required"], name="ad_mod_prior_escalat_dd4acc_idx"),
                ],
            },
        ),
    ]