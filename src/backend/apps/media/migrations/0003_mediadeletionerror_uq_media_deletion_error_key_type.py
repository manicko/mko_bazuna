from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("media", "0002_dedup_media_deletion_errors"),
    ]

    operations = [
        migrations.AddConstraint(
            model_name="mediadeletionerror",
            constraint=models.UniqueConstraint(
                fields=["storage_key", "error_type"],
                name="uq_media_deletion_error_key_type",
            ),
        ),
    ]
