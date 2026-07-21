"""
Migration 0002: Add chat_id field to User with backfill from telegram_id.

The chat_id column is a stable Telegram chat ID set on first bot contact that
survives consent withdrawal (unlike telegram_id which is nulled on withdraw).
Existing users are backfilled with their current telegram_id value.
"""

from django.db import migrations, models


class Migration(migrations.Migration):
    """Add chat_id with backfill from telegram_id."""

    dependencies = [
        ("users", "0001_initial"),
    ]

    operations = [
        # Step 1: Add chat_id as nullable first (backfill then alter)
        migrations.AddField(
            model_name="user",
            name="chat_id",
            field=models.BigIntegerField(
                blank=False,
                null=True,
                unique=True,
                db_index=True,
                help_text="Stable Telegram chat ID; set on first bot contact, never nullified",
            ),
            # Preserve the existing index behavior
            preserve_default=False,
        ),
        # Step 2: Backfill chat_id from telegram_id for existing rows
        # telegram_id is NOT NULL for all existing users
        migrations.RunSQL(
            sql='UPDATE "users" SET "chat_id" = "telegram_id" WHERE "chat_id" IS NULL',
            reverse_sql='UPDATE "users" SET "chat_id" = NULL WHERE "chat_id" IS NOT NULL',
        ),
        # Step 3: Alter chat_id to NOT NULL after backfill
        migrations.AlterField(
            model_name="user",
            name="chat_id",
            field=models.BigIntegerField(
                blank=False,
                null=False,
                unique=True,
                db_index=True,
                help_text="Stable Telegram chat ID; set on first bot contact, never nullified",
            ),
            preserve_default=False,
        ),
    ]