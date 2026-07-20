# Singleton enforcement migration for ModerationCriteria

from django.db import migrations


def ensure_singleton(apps, schema_editor):
    """Ensure exactly one ModerationCriteria row exists (id=1)."""
    ModerationCriteria = apps.get_model("moderation", "ModerationCriteria")
    ModerationCriteria.objects.get_or_create(pk=1)


class Migration(migrations.Migration):
    dependencies = [
        ("moderation", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(ensure_singleton, migrations.RunPython.noop),
    ]