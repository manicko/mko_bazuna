from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("users", "0002_alter_consentrecord_ip_address"),
    ]

    operations = [
        migrations.AddField(
            model_name="logintoken",
            name="browser_binding",
            field=models.CharField(
                blank=True,
                help_text=(
                    "SHA-256 hex digest of the issuing browser's login_browser_id "
                    "cookie; the raw id is never stored. NULL means the row predates "
                    "the binding (or was written without one) and is never redeemable."
                ),
                max_length=64,
                null=True,
            ),
        ),
    ]
