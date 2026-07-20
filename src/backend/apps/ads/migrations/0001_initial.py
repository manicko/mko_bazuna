# Generated migration for ads app

from django.db import migrations, models
import django.contrib.postgres.search
import django.contrib.postgres.indexes


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("users", "0001_initial"),
        ("categories", "0001_initial"),
        ("locations", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="Ad",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("title", models.CharField(help_text="Ad title in Russian (translated from seller input)", max_length=200)),
                ("description", models.TextField(help_text="Ad description in Russian (translated from seller input)")),
                ("price", models.PositiveIntegerField(blank=True, help_text="Whole BAM units; multi-currency deferred (YAGNI)", null=True)),
                ("category_name", models.CharField(editable=False, help_text="Denormalized Russian category name; trigger-synced", max_length=200)),
                ("status", models.CharField(choices=[("draft", "draft"), ("on_moderation", "on_moderation"), ("published", "published"), ("rejected", "rejected"), ("on_moderation_failed", "on_moderation_failed"), ("archived", "archived"), ("deleted", "deleted")], default="draft", help_text="Ad lifecycle status", max_length=20)),
                ("source", models.CharField(choices=[("telegram", "telegram")], default="telegram", help_text="Origin of ad (phase 1 = bot only)", max_length=20)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("published_at", models.DateTimeField(blank=True, help_text="Drives archive/delete timers; UPDATED on every PUBLISHED transition", null=True)),
                ("original_published_at", models.DateTimeField(blank=True, help_text="Set once on FIRST publish; IMMUTABLE, audit only", null=True)),
                ("archived_at", models.DateTimeField(blank=True, help_text="Auto-archive (2mo) or manual archive", null=True)),
                ("deleted_at", models.DateTimeField(blank=True, help_text="Soft delete timestamp", null=True)),
                ("moderation_failed_at", models.DateTimeField(blank=True, help_text="Failed auto-check; drives 7-day purge (mutually exclusive with rejected_at)", null=True)),
                ("rejected_at", models.DateTimeField(blank=True, help_text="Manually rejected; drives 90-day cleanup (mutually exclusive with moderation_failed_at)", null=True)),
                ("search_vector", django.contrib.postgres.search.SearchVectorField(blank=True, help_text="TSVECTOR for native PostgreSQL FTS; NOT GENERATED ALWAYS", null=True)),
                ("user", models.ForeignKey(help_text="Ad owner", on_delete=models.CASCADE, related_name="ads", to="users.user")),
                ("category", models.ForeignKey(help_text="Ad category", on_delete=models.PROTECT, related_name="ads", to="categories.category")),
                ("city", models.ForeignKey(help_text="Ad city location", on_delete=models.PROTECT, related_name="ads", to="locations.city")),
                ("published_by", models.ForeignKey(blank=True, help_text="Moderator who manually published", null=True, on_delete=models.SET_NULL, related_name="published_ads", to="users.user")),
                ("moderated_by", models.ForeignKey(blank=True, help_text="Moderator who manually rejected", null=True, on_delete=models.SET_NULL, related_name="moderated_ads", to="users.user")),
            ],
            options={
                "db_table": "ads",
            },
        ),
        migrations.CreateModel(
            name="AdImage",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("image", models.CharField(help_text="Storage key (ad_id + UUID v4, no user/telegram PII)", max_length=64)),
                ("telegram_file_id", models.CharField(blank=True, help_text="Telegram file_id; NOT used in <img src>", max_length=255, null=True)),
                ("position", models.PositiveIntegerField(default=0, help_text="Image order in gallery")),
                ("ad", models.ForeignKey(help_text="Parent ad", on_delete=models.CASCADE, related_name="images", to="ads.ad")),
            ],
            options={
                "db_table": "ad_images",
                "ordering": ["position"],
            },
        ),
        migrations.AddIndex(
            model_name="ad",
            index=django.contrib.postgres.indexes.GinIndex(fields=["search_vector"], name="IX_ads_search_gin"),
        ),
        migrations.AddIndex(
            model_name="ad",
            index=models.Index(fields=["status", "category_id", "city_id", "-published_at"], name="IX_ads_pub_listing"),
        ),
        migrations.AddIndex(
            model_name="ad",
            index=models.Index(fields=["user_id", "status"], name="IX_ads_user_status"),
        ),
        migrations.AddIndex(
            model_name="ad",
            index=models.Index(fields=["status", "published_at"], name="IX_ads_archive_sweep"),
        ),
        migrations.AddIndex(
            model_name="ad",
            index=models.Index(fields=["status", "published_at"], name="IX_ads_delete_sweep"),
        ),
        migrations.AddIndex(
            model_name="ad",
            index=models.Index(fields=["status", "moderation_failed_at"], name="IX_ads_purge_failed"),
        ),
        migrations.AddIndex(
            model_name="ad",
            index=models.Index(fields=["status", "rejected_at"], name="IX_ads_rejected_sweep"),
        ),
    ]