"""
Migration 0004: Remove hard_delete_at field from User model.

The hard_delete_at field was never written by the application code;
the 30-day hard-delete sweep uses consent_revoked_at directly.
This migration removes the dead field to align schema with actual logic.
"""

from django.db import migrations


class Migration(migrations.Migration):
    """Remove unused hard_delete_at field from User model."""

    dependencies = [
        ("users", "0003_user_is_declined"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="user",
            name="hard_delete_at",
        ),
    ]
