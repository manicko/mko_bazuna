"""
Migration 0003: Add is_declined field to User model.

The is_declined boolean field marks users who declined consent (browse-only mode).
When True, blocks seller login/actions while preserving existing ads and PII.
"""

from django.db import migrations, models


class Migration(migrations.Migration):
    """Add is_declined boolean field to User model."""

    dependencies = [
        ("users", "0002_user_chat_id"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="is_declined",
            field=models.BooleanField(
                default=False,
                help_text="User declined consent (browse-only mode)",
            ),
        ),
    ]