"""Initial migration for lookups app — LookupGroup and LookupItem models."""

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    """Creates LookupGroup and LookupItem tables."""

    initial = True

    dependencies: list[tuple[str, str]] = []

    operations = [
        migrations.CreateModel(
            name="LookupGroup",
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
                    "code",
                    models.CharField(
                        max_length=100,
                        unique=True,
                        help_text="Machine-readable, immutable group code",
                    ),
                ),
                (
                    "name_i18n",
                    models.JSONField(
                        blank=True,
                        null=True,
                        help_text="Localized names: {'ru': str, 'bs': str, 'en': str}",
                    ),
                ),
                (
                    "is_system",
                    models.BooleanField(
                        default=False,
                        help_text="Protected from admin deletion",
                    ),
                ),
                (
                    "sort_order",
                    models.PositiveIntegerField(default=0),
                ),
            ],
            options={
                "db_table": "lookup_groups",
                "ordering": ["sort_order"],
                "verbose_name": "lookup group",
            },
        ),
        migrations.CreateModel(
            name="LookupItem",
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
                    "slug",
                    models.SlugField(
                        max_length=100,
                        unique=True,
                        help_text="Globally unique identifier",
                    ),
                ),
                (
                    "name_i18n",
                    models.JSONField(
                        blank=True,
                        null=True,
                        help_text="Localized names: {'ru': str, 'bs': str, 'en': str}",
                    ),
                ),
                (
                    "sort_order",
                    models.PositiveIntegerField(default=0),
                ),
                (
                    "is_active",
                    models.BooleanField(
                        default=True,
                        help_text="Inactive items are hidden from UI and filter options",
                    ),
                ),
                (
                    "icon",
                    models.CharField(
                        max_length=50,
                        blank=True,
                        default="",
                        help_text="Emoji or SVG icon name",
                    ),
                ),
                (
                    "color",
                    models.CharField(
                        max_length=7,
                        blank=True,
                        default="",
                        help_text="Hex color code, e.g. #RRGGBB",
                    ),
                ),
                (
                    "group",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="items",
                        to="lookups.LookupGroup",
                        help_text="Parent lookup group",
                    ),
                ),
            ],
            options={
                "db_table": "lookup_items",
                "ordering": ["group", "sort_order"],
                "verbose_name": "lookup item",
            },
        ),
    ]