"""Add telegram_premium field to User model."""

from django.db import migrations, models


class Migration(migrations.Migration):
    """Add telegram_premium BooleanField to User model."""

    dependencies = [
        ("users", "0002_user_chat_id"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="telegram_premium",
            field=models.BooleanField(
                default=False,
                help_text="User has Telegram Premium subscription",
            ),
        ),
    ]