# Generated manually (plan impl_002): add SavedSearch.language and backfill
# legacy rows to 'ru' so existing Russian-translated alert behaviour is preserved.

from django.db import migrations, models


def backfill_legacy_language(apps, schema_editor):
    """Default existing saved searches to the Russian locale (R7 mitigation).

    Legacy rows were matched against the Russian-translated query vector;
    backfilling to 'ru' keeps that behaviour until the user changes it.
    """
    SavedSearch = apps.get_model("search", "SavedSearch")
    SavedSearch.objects.filter(language__isnull=True).update(language="ru")


class Migration(migrations.Migration):

    dependencies = [
        ("search", "0002_add_fks_indexes_constraints"),
    ]

    operations = [
        migrations.AddField(
            model_name="savedsearch",
            name="language",
            field=models.CharField(
                blank=True,
                default="bs",
                help_text="LanguageLocale code ('ru', 'bs' or 'en') used to search ads",
                max_length=5,
                null=True,
            ),
        ),
        migrations.RunPython(
            backfill_legacy_language,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
