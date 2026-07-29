"""
Migration to add related_name and composite index to SearchHistory.

Changes:
- Add ``related_name="search_history"`` to the ``user`` ForeignKey on
  ``SearchHistory`` (the column itself is unchanged, only the Django-side
  relation name is added).
- Add a composite index on ``(user_id, -created_at)`` to optimise the
  "most recent history per user" query.
"""

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    """Add related_name and composite index to SearchHistory."""

    dependencies = [
        ("search", "0001_initial"),
    ]

    operations = [
        migrations.AlterField(
            model_name="searchhistory",
            name="user",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="search_history",
                to="users.user",
            ),
        ),
        migrations.AddIndex(
            model_name="searchhistory",
            index=models.Index(
                fields=["user_id", "-created_at"],
                name="search_hist_user_id_created_at_idx",
            ),
        ),
    ]