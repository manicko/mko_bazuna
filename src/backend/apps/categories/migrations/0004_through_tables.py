"""Add CategoryListingPurpose and CategoryListingFeature through models."""

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    """Creates through tables binding Category ↔ LookupItem for purposes and features."""

    dependencies = [
        ("categories", "0003_categorypath"),
        ("lookups", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="CategoryListingPurpose",
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
                    "is_default",
                    models.BooleanField(
                        default=False,
                        help_text=(
                            "Default purpose for this category; "
                            "auto-selected when seller doesn't choose explicitly"
                        ),
                    ),
                ),
                (
                    "category",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="listing_purposes",
                        to="categories.category",
                    ),
                ),
                (
                    "listing_purpose",
                    models.ForeignKey(
                        limit_choices_to={"group__code": "listing_purpose"},
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="category_purposes",
                        to="lookups.lookupitem",
                    ),
                ),
            ],
            options={
                "db_table": "category_listing_purposes",
                "verbose_name_plural": "category listing purposes",
                "unique_together": {("category", "listing_purpose")},
            },
        ),
        migrations.CreateModel(
            name="CategoryListingFeature",
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
                    "category",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="listing_features",
                        to="categories.category",
                    ),
                ),
                (
                    "feature",
                    models.ForeignKey(
                        limit_choices_to={"group__code": "listing_feature"},
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="category_features",
                        to="lookups.lookupitem",
                    ),
                ),
            ],
            options={
                "db_table": "category_listing_features",
                "verbose_name_plural": "category listing features",
                "unique_together": {("category", "feature")},
            },
        ),
        migrations.AddIndex(
            model_name="categorylistingpurpose",
            index=models.Index(
                fields=["category", "listing_purpose"],
                name="cat_list_purpose_cat_purpose_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="categorylistingpurpose",
            index=models.Index(
                fields=["listing_purpose"],
                name="cat_list_purpose_purpose_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="categorylistingfeature",
            index=models.Index(
                fields=["category", "feature"],
                name="cat_list_feature_cat_feat_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="categorylistingfeature",
            index=models.Index(
                fields=["feature"],
                name="cat_list_feature_feature_idx",
            ),
        ),
    ]