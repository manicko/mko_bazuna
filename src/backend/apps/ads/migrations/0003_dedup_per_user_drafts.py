"""
Data migration to collapse per-user DRAFT rows (AD-009a).

The bot's ``create_draft_ad`` (``src/telegram_bot/handlers/ad_create.py:862``)
calls ``Ad.objects.create(user_id=user_id, status=AdStatus.DRAFT)`` without
checking for an existing DRAFT, so a user can accumulate multiple DRAFT rows.
This migration keeps only the newest DRAFT per user (greatest ``id``) and
deletes the rest, preparing the data for a future per-user DRAFT unique
constraint.

Non-reversible: older DRAFT rows are hard-deleted (including their AdImage
rows via cascade), and their data cannot be reconstructed, so the reverse
code is a no-op.
"""

from django.db import migrations
from django.db.models import Max

from apps.core.enums import AdStatus


def collapse_per_user_drafts(apps, schema_editor):
    """Keep only the newest DRAFT per user; delete the rest.

    Uses ``apps.get_model`` for the mutable historical ``Ad`` model.  The
    queryset ``delete()`` triggers Django's emulated ``on_delete=CASCADE``
    for ``AdImage`` rows — Django emulates cascade in ``queryset.delete()``
    regardless of DB-level cascade — cleaning up orphaned image records.
    CheckConstraints are satisfied because only DRAFT rows are deleted
    (no terminal-status constraints apply to DRAFT).
    """
    Ad = apps.get_model("ads", "Ad")

    # Newest DRAFT id per user (greatest id).
    newest_ids = list(
        Ad.objects.filter(status=AdStatus.DRAFT)
        .values("user_id")
        .annotate(newest_id=Max("id"))
        .values_list("newest_id", flat=True)
    )

    # Delete all DRAFT rows that are not the newest for their user.
    Ad.objects.filter(status=AdStatus.DRAFT).exclude(
        id__in=newest_ids
    ).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("ads", "0002_alter_adimage_image_alter_adimage_thumbnail_large_and_more"),
    ]

    operations = [
        migrations.RunPython(
            collapse_per_user_drafts,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
