"""
Data migration to deduplicate ``MediaDeletionError`` rows (MED-002).

The bot's ``delete_photo`` ``_record_deletion_error`` previously called
``MediaDeletionError.objects.create`` without checking for an existing row, so
repeated deletion failures for the same ``(storage_key, error_type)`` pair could
accumulate multiple rows. This migration keeps only the earliest row
(``MIN(created_at)``, with ``id`` as a deterministic tiebreaker) per
``(storage_key, error_type)`` group and deletes the rest, preparing the data for
the unique constraint added in ``0003_mediadeletionerror_uq_media_deletion_error_key_type``.

Non-reversible: duplicate rows are hard-deleted, and their data cannot be
reconstructed, so the reverse code is a no-op.
"""

from django.db import migrations, transaction
from django.db.models import Min


def dedup_media_deletion_errors(apps: object, schema_editor: object) -> None:
    MediaDeletionError = apps.get_model("media", "MediaDeletionError")  # type: ignore[attr-defined]

    with transaction.atomic():  # pyright: ignore[reportGeneralTypeIssues]
        keep_ids = list(
            MediaDeletionError.objects.values("storage_key", "error_type")
            .annotate(keep_id=Min("id"))
            .values_list("keep_id", flat=True)
        )

        MediaDeletionError.objects.exclude(id__in=keep_ids).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("media", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(
            dedup_media_deletion_errors,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
