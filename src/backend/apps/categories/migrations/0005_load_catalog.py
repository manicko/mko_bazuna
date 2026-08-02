"""Data migration to load catalog from YAML config via builder."""

from django.db import migrations

CONFIG_PATH = "apps/categories/catalog/categories.yaml"


def load_catalog_forward(apps, schema_editor):
    """Call builder.load_catalog() to populate all catalog data."""
    from apps.categories.catalog.builder import load_catalog

    load_catalog(CONFIG_PATH)


def reverse_catalog(apps, schema_editor):
    """Reverse: no-op. Catalog data is safe to keep on rollback."""


class Migration(migrations.Migration):
    """Load catalog data from YAML config via builder.

    Depends on:
    - lookups/0001_initial (LookupGroup + LookupItem tables)
    - categories/0004_through_tables (CategoryListingPurpose + CategoryListingFeature)
    """

    dependencies = [
        ("lookups", "0001_initial"),
        ("categories", "0004_through_tables"),
    ]

    operations = [
        migrations.RunPython(load_catalog_forward, reverse_code=reverse_catalog),
    ]