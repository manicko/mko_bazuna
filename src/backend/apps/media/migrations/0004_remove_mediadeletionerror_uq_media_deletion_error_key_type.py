"""
Remove the ``uq_media_deletion_error_key_type`` unique constraint.

``0003`` added ``UniqueConstraint(fields=["storage_key", "error_type"])`` on
``MediaDeletionError`` after the dedup data migration.  The constraint proved
too strict for production usage: transient retry storms for the same key/type
pair can still create concurrent rows before the dedup query lands, and the
``delete_photo`` retry loop does not de-duplicate against in-flight attempts.
Rather than keep the constraint and introduce application-level ``SELECT
FOR UPDATE`` contention, the constraint was dropped from the model and is
removed here so the migration state matches ``apps.media.models``.
"""

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("media", "0003_mediadeletionerror_uq_media_deletion_error_key_type"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="mediadeletionerror",
            name="uq_media_deletion_error_key_type",
        ),
    ]
