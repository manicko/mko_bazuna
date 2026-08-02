"""Add SHA-256 hash field to AdImage for photo deduplication."""

from django.db import migrations, models


class Migration(migrations.Migration):
    """Add sha256 CharField with db_index to AdImage.

    The sha256 field stores the hex digest of the image file for
    deduplication purposes. An index on this column enables fast
    duplicate lookups.
    """

    dependencies = [
        ("ads", "0007_adimage_thumbnails"),
    ]

    operations = [
        migrations.AddField(
            model_name="adimage",
            name="sha256",
            field=models.CharField(
                max_length=64,
                db_index=True,
                blank=True,
                default="",
                help_text="SHA-256 hex digest for deduplication",
            ),
        ),
    ]