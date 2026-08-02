"""Add CategoryPath model for multi-parent navigation support."""

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    """Creates CategoryPath table for alternative parent routes."""

    dependencies = [
        ("categories", "0002_seed_categories"),
    ]

    operations = [
        migrations.CreateModel(
            name="CategoryPath",
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
                ("sort_order", models.PositiveIntegerField(default=0)),
                (
                    "is_automatic",
                    models.BooleanField(
                        default=False,
                        help_text=(
                            "True if created by system rule "
                            "(e.g. price=0 -> Благотворительность)"
                        ),
                    ),
                ),
                (
                    "category",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="alternative_parents",
                        to="categories.category",
                        help_text="The leaf/child being navigated to",
                    ),
                ),
                (
                    "parent",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="alternative_children",
                        to="categories.category",
                        help_text="The alternative parent in the navigation path",
                    ),
                ),
            ],
            options={
                "db_table": "category_paths",
                "ordering": ["sort_order"],
                "verbose_name_plural": "category paths",
                "unique_together": {("category", "parent")},
            },
        ),
    ]