"""
Migration to add missing indexes on SavedSearch and SavedSearchNotification.

Adds:
- ``IX_saved_searches_user_active`` on ``saved_searches (user_id, is_active)``
- ``IX_saved_search_notifications_search`` on ``saved_search_notifications (saved_search_id)``
"""

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    """Add performance indexes for saved search alert delivery."""

    dependencies = [
        ("search", "0002_searchhistory_related_name_and_index"),
    ]

    operations = [
        migrations.AddIndex(
            model_name="savedsearch",
            index=models.Index(
                fields=["user_id", "is_active"],
                name="IX_saved_searches_user_active",
            ),
        ),
        migrations.AddIndex(
            model_name="savedsearchnotification",
            index=models.Index(
                fields=["saved_search_id"],
                name="IX_saved_search_notifications_search",
            ),
        ),
    ]