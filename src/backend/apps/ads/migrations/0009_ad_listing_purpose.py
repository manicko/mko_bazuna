"""Add listing_purpose FK, features M2M, and AdFeature through model to Ad."""

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    """Add listing_purpose and features to the Ad model.

    listing_purpose is nullable initially; the data migration in
    0009_backfill_listing_purpose.py fills in values for existing rows.
    """

    dependencies = [
        ("ads", "0008_adimage_sha256"),
        ("lookups", "0001_initial"),
    ]

    operations = [
        # Create AdFeature through model first (needed by M2M field)
        migrations.CreateModel(
            name="AdFeature",
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
                    "sort_order",
                    models.PositiveIntegerField(
                        default=0,
                        help_text="Display order of this feature on the ad page",
                    ),
                ),
                (
                    "ad",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="ad_features",
                        to="ads.ad",
                    ),
                ),
                (
                    "feature",
                    models.ForeignKey(
                        limit_choices_to={"group__code": "listing_feature"},
                        on_delete=django.db.models.deletion.CASCADE,
                        to="lookups.lookupitem",
                    ),
                ),
            ],
            options={
                "db_table": "ad_features",
                "ordering": ["sort_order"],
                "unique_together": {("ad", "feature")},
            },
        ),
        # Add listing_purpose FK
        migrations.AddField(
            model_name="ad",
            name="listing_purpose",
            field=models.ForeignKey(
                blank=True,
                help_text="What the user wants to do with the object",
                limit_choices_to={"group__code": "listing_purpose"},
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="ads",
                to="lookups.lookupitem",
            ),
        ),
        # Add features M2M
        migrations.AddField(
            model_name="ad",
            name="features",
            field=models.ManyToManyField(
                blank=True,
                related_name="featured_ads",
                through="ads.AdFeature",
                to="lookups.lookupitem",
            ),
        ),
    ]