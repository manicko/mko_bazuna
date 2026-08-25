"""
Migration to add telegram_language field to User model.

Stores the Telegram-reported language code for localized bot messages.
Defaults to 'ru' (Russian) for existing users, per project convention.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0004_consentrecord"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="telegram_language",
            field=models.CharField(
                choices=[("ru", "ru"), ("bs", "bs"), ("en", "en")],
                default="ru",
                help_text="Telegram-reported language code for localized bot messages",
                max_length=5,
            ),
        ),
    ]
