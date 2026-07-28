"""Add thumbnail storage key columns to AdImage table."""

from django.db import migrations, models


class Migration(migrations.Migration):
    """Add thumbnail_small, thumbnail_medium, thumbnail_large to AdImage.

    All three fields are nullable CharFields that store storage keys
    for resized image variants generated at upload time.
    """

    dependencies = [
        ("ads", "0006_backfill_translations"),
    ]

    operations = [
        migrations.AddField(
            model_name="adimage",
            name="thumbnail_small",
            field=models.CharField(
                max_length=64,
                blank=True,
                null=True,
                help_text="Storage key for small thumbnail (<uuid>-small.jpg)",
            ),
        ),
        migrations.AddField(
            model_name="adimage",
            name="thumbnail_medium",
            field=models.CharField(
                max_length=64,
                blank=True,
                null=True,
                help_text="Storage key for medium thumbnail (<uuid>-medium.jpg)",
            ),
        ),
        migrations.AddField(
            model_name="adimage",
            name="thumbnail_large",
            field=models.CharField(
                max_length=64,
                blank=True,
                null=True,
                help_text="Storage key for large thumbnail (<uuid>-large.jpg)",
            ),
        ),
    ]