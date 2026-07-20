# Generated migration for locations app

from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="City",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("country_code", models.CharField(help_text="ISO country code (e.g., 'BA' for Bosnia)", max_length=2)),
                ("name", models.CharField(help_text="Russian city name (base storage language)", max_length=200)),
                ("name_i18n", models.JSONField(blank=True, help_text="i18n names: {'ru': <str>, 'bs': <str>}; NULL falls back to name", null=True)),
                ("region", models.CharField(help_text="Administrative region", max_length=100)),
                ("slug", models.SlugField(help_text="URL-friendly city slug", unique=True)),
            ],
            options={
                "db_table": "cities",
            },
        ),
    ]