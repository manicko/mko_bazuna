from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0001_initial"),
    ]

    operations = [
        migrations.AlterField(
            model_name="user",
            name="telegram_id",
            field=models.BigIntegerField(
                blank=True,
                help_text="Telegram user ID; required for authentication (nullified on GDPR withdrawal)",
                null=True,
                unique=True,
            ),
        ),
    ]
