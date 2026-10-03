from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0003_logintoken_browser_binding"),
    ]

    operations = [
        migrations.AddIndex(
            model_name="consentrecord",
            index=models.Index(
                fields=["consent_given_at"], name="IX_consent_records_sweep"
            ),
        ),
    ]
