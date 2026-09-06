"""
Add bot_username field to SiteConfig and seed from settings.BOT_USERNAME.

Part of Block A (contact-us): migrates the bot username from the
``settings.BOT_USERNAME`` env var into the ``SiteConfig`` singleton
so it is editable in Django admin.
"""

from django.core.validators import RegexValidator
from django.db import migrations, models


def seed_bot_username(apps, schema_editor):
    SiteConfig = apps.get_model("core", "SiteConfig")

    # Read BOT_USERNAME from settings; fall back to "bazuna_bot" if empty.
    from django.conf import settings as dj_settings

    bot_username = getattr(dj_settings, "BOT_USERNAME", "") or "bazuna_bot"
    # Only seed rows that are still at the factory default — never
    # overwrite an admin-edited value on re-run (migration-workflow.md:285).
    SiteConfig.objects.filter(pk=1, bot_username="bazuna_bot").update(
        bot_username=bot_username
    )


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0002_seed_default"),
    ]

    operations = [
        migrations.AddField(
            model_name="siteconfig",
            name="bot_username",
            field=models.CharField(
                default="bazuna_bot",
                help_text="Telegram bot username without @ prefix",
                max_length=32,
                validators=[
                    RegexValidator(
                        message="Bot username must be 3-32 characters, alphanumeric and underscore only",
                        regex="^[A-Za-z0-9_]{3,32}$",
                    ),
                ],
            ),
        ),
        migrations.RunPython(
            seed_bot_username,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
