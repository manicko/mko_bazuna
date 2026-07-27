"""Add multi-language content columns to ads table."""

from django.db import migrations, models


class Migration(migrations.Migration):
    """Add i18n columns: title_en, description_en, title_bs, description_bs, original_language."""

    dependencies = [
        ("ads", "0003_add_index_conditions"),
    ]

    operations = [
        migrations.AddField(
            model_name="ad",
            name="title_en",
            field=models.CharField(
                max_length=200,
                blank=True,
                null=True,
                help_text="Ad title in English",
            ),
        ),
        migrations.AddField(
            model_name="ad",
            name="description_en",
            field=models.TextField(
                blank=True,
                null=True,
                help_text="Ad description in English",
            ),
        ),
        migrations.AddField(
            model_name="ad",
            name="title_bs",
            field=models.CharField(
                max_length=200,
                blank=True,
                null=True,
                help_text="Ad title in Bosnian",
            ),
        ),
        migrations.AddField(
            model_name="ad",
            name="description_bs",
            field=models.TextField(
                blank=True,
                null=True,
                help_text="Ad description in Bosnian",
            ),
        ),
        migrations.AddField(
            model_name="ad",
            name="original_language",
            field=models.CharField(
                max_length=5,
                blank=True,
                null=True,
                help_text="Original language code of the ad (e.g. 'ru', 'en', 'bs')",
            ),
        ),
    ]