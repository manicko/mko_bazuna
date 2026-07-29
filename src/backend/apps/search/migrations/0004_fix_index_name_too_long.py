"""Fix index name too long (>30 chars) on SavedSearchNotification.

Renames IX_saved_search_notifications_search → idx_saved_search_notif_sid
to satisfy Django's 30-character index name limit.
"""

from django.db import migrations, models


class Migration(migrations.Migration):
    """Fix index name length on SavedSearchNotification."""

    dependencies = [
        ("search", "0003_saved_search_indexes"),
    ]

    operations = [
        migrations.RemoveIndex(
            model_name="savedsearchnotification",
            name="IX_saved_search_notifications_search",
        ),
        migrations.AddIndex(
            model_name="savedsearchnotification",
            index=models.Index(
                fields=["saved_search_id"],
                name="idx_saved_search_notif_sid",
            ),
        ),
    ]