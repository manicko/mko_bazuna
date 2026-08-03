"""Backfill translations for existing ads to English and Bosnian.

This migration previously contained a RunPython operation for translation backfill.
That logic has been extracted to the ``backfill_translations`` management command.
This migration is now a no-op schema-only migration to preserve the dependency chain.
"""

from django.db import migrations


class Migration(migrations.Migration):
    """No-op migration — backfill logic moved to management command.

    Dependencies:
        - ads/0005: Multi-language search vector trigger update (must run
          before this backfill so new inserts/updates have proper vectors).
    """

    dependencies = [
        ("ads", "0005_multi_lang_search_vector"),
    ]

    operations: list[migrations.operations.base.Operation] = []