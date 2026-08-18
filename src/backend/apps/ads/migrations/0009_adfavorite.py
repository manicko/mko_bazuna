# Generated manually (plan impl_016 / FND-002): add the AdFavorite model for
# the cabinet Favorites section, with a unique (user, ad) constraint and a
# user-scoped created_at index.

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("ads", "0008_search_vector_gin"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="AdFavorite",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "created_at",
                    models.DateTimeField(
                        auto_now_add=True,
                        help_text="When the ad was favorited",
                    ),
                ),
                (
                    "ad",
                    models.ForeignKey(
                        help_text="The favorited ad",
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="favorites",
                        to="ads.ad",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        help_text="User who favorited the ad",
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="favorites",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "db_table": "ad_favorites",
            },
        ),
        migrations.AddConstraint(
            model_name="adfavorite",
            constraint=models.UniqueConstraint(
                fields=("user", "ad"),
                name="uq_user_ad_favorite",
            ),
        ),
        migrations.AddIndex(
            model_name="adfavorite",
            index=models.Index(
                fields=["user_id", "-created_at"],
                name="ad_favorites_user_created_idx",
            ),
        ),
    ]
