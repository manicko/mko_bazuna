# Generated migration for search app — PopularSearch, SearchHistory, SavedSearch, SavedSearchNotification

from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("ads", "0001_initial"),
        ("categories", "0001_initial"),
        ("locations", "0001_initial"),
        ("users", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="PopularSearch",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("query", models.CharField(db_index=True, max_length=200)),
                ("query_normalized", models.CharField(db_index=True, max_length=200)),
                ("hit_count", models.PositiveIntegerField(default=1)),
                ("last_seen", models.DateTimeField(auto_now=True)),
            ],
            options={
                "db_table": "popular_searches",
            },
        ),
        migrations.CreateModel(
            name="SearchHistory",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("query", models.CharField(max_length=200)),
                ("query_normalized", models.CharField(db_index=True, max_length=200)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("user", models.ForeignKey(blank=True, null=True, on_delete=models.CASCADE, to="users.user")),
            ],
            options={
                "db_table": "search_history",
            },
        ),
        migrations.CreateModel(
            name="SavedSearch",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("query", models.TextField(blank=True, null=True)),
                ("min_price", models.PositiveIntegerField(blank=True, null=True)),
                ("max_price", models.PositiveIntegerField(blank=True, null=True)),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("category", models.ForeignKey(blank=True, null=True, on_delete=models.SET_NULL, to="categories.category")),
                ("city", models.ForeignKey(blank=True, null=True, on_delete=models.SET_NULL, to="locations.city")),
                ("user", models.ForeignKey(on_delete=models.CASCADE, to="users.user")),
            ],
            options={
                "db_table": "saved_searches",
            },
        ),
        migrations.CreateModel(
            name="SavedSearchNotification",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("sent_at", models.DateTimeField(auto_now_add=True)),
                ("ad", models.ForeignKey(on_delete=models.CASCADE, related_name="saved_search_notifications", to="ads.ad")),
                ("saved_search", models.ForeignKey(on_delete=models.CASCADE, related_name="notifications", to="search.savedsearch")),
            ],
            options={
                "db_table": "saved_search_notifications",
            },
        ),
        migrations.AddConstraint(
            model_name="savedsearchnotification",
            constraint=models.UniqueConstraint(fields=["saved_search", "ad"], name="uq_saved_search_ad"),
        ),
    ]