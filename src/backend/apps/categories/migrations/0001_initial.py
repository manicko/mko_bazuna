# Generated migration for categories app

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="Category",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(help_text="Russian category name (base storage language)", max_length=200)),
                ("name_i18n", models.JSONField(blank=True, help_text="i18n names: {'ru': <str>, 'bs': <str>}; NULL falls back to name", null=True)),
                ("slug", models.SlugField(help_text="URL-friendly category slug", unique=True)),
                ("is_active", models.BooleanField(default=True, help_text="Inactive categories hide their ads")),
                ("parent", models.ForeignKey(blank=True, help_text="Parent category for tree structure", null=True, on_delete=django.db.models.deletion.CASCADE, related_name="children", to="categories.category")),
                ("lft", models.PositiveIntegerField(editable=False)),
                ("rght", models.PositiveIntegerField(editable=False)),
                ("tree_id", models.PositiveIntegerField(db_index=True, editable=False)),
                ("level", models.PositiveIntegerField(editable=False)),
            ],
            options={
                "db_table": "categories",
            },
        ),
    ]