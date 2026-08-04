"""Data migration to load catalog from YAML config via builder."""
from django.db import migrations

CONFIG_PATH = "apps/categories/catalog/categories.yaml"


def load_catalog_forward(apps, schema_editor):
    """Call builder.load_catalog() to populate all catalog data."""
    from apps.categories.catalog.builder import load_catalog

    load_catalog(CONFIG_PATH, apps=apps, rewrite_yaml=False)


def reverse_catalog(apps, schema_editor):
    """Reverse: no-op. Catalog data is safe to keep on rollback."""


class Migration(migrations.Migration):
    """Load catalog data from YAML config via builder.

    Depends on:
    - categories/0002: seed categories exist (for reference in catalog data)
    - lookups/0001: LookupGroup + LookupItem tables
    """

    dependencies = [
        ("categories", "0002_seed_categories"),
        ("lookups", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(load_catalog_forward, reverse_code=reverse_catalog),
    ]