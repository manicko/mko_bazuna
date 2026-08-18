# Generated manually (plan impl_016 / FND-001): add SavedSearch audit +
# unsubscribe fields and backfill the opaque unsubscribe_token for legacy
# rows so the unique constraint holds on a populated database.

import secrets

from django.db import migrations, models


def backfill_unsubscribe_tokens(apps, schema_editor):
    """Assign an opaque token to every saved search missing one.

    New rows get their token via the ``SavedSearch.save()`` override; legacy
    rows need one here so ``unsubscribe_token``'s unique constraint is
    satisfied on a populated database. Tokens are independent capability
    handles (not derived from the PK and not a ``Signer`` payload).
    """
    SavedSearch = apps.get_model("search", "SavedSearch")
    for saved_search in SavedSearch.objects.filter(unsubscribe_token__isnull=True).only("pk"):
        saved_search.unsubscribe_token = secrets.token_urlsafe(24)  # 32 URL-safe chars
        saved_search.save(update_fields=["unsubscribe_token"])


class Migration(migrations.Migration):

    dependencies = [
        ("search", "0003_savedsearch_language"),
    ]

    operations = [
        migrations.AddField(
            model_name="savedsearch",
            name="updated_at",
            field=models.DateTimeField(
                auto_now=True,
                help_text="When this saved search was last modified",
            ),
        ),
        migrations.AddField(
            model_name="savedsearch",
            name="last_notified_at",
            field=models.DateTimeField(
                blank=True,
                help_text="Last time this search produced a notification",
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="savedsearch",
            name="unsubscribe_token",
            field=models.CharField(
                blank=True,
                db_index=True,
                help_text=(
                    "Opaque server-generated capability token for Telegram "
                    "unsubscribe deep-links and inline callbacks (never derived "
                    "from the PK)"
                ),
                max_length=40,
                null=True,
                unique=True,
            ),
        ),
        migrations.RunPython(
            backfill_unsubscribe_tokens,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
