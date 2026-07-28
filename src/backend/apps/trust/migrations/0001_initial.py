"""Initial migration for trust app: SellerTrustScore and SellerVerification."""

from django.db import migrations, models


class Migration(migrations.Migration):
    """Create seller_trust_scores and seller_verifications tables."""

    initial = True

    dependencies = [
        ("users", "0002"),
    ]

    operations = [
        migrations.CreateModel(
            name="SellerTrustScore",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("trust_level", models.CharField(choices=[("unverified", "unverified"), ("verified", "verified"), ("trusted", "trusted"), ("pro", "pro")], max_length=20)),
                ("score", models.PositiveSmallIntegerField(default=0)),
                ("ad_count_lifetime", models.PositiveIntegerField(default=0)),
                ("ad_count_active", models.PositiveIntegerField(default=0)),
                ("rejection_rate", models.DecimalField(decimal_places=2, default=0.0, max_digits=5)),
                ("contact_response_rate", models.DecimalField(decimal_places=2, default=0.0, max_digits=5)),
                ("last_calculated", models.DateTimeField(auto_now=True)),
                ("user", models.OneToOneField(on_delete=models.CASCADE, related_name="trust_score", to="users.user")),
            ],
            options={
                "db_table": "seller_trust_scores",
            },
        ),
        migrations.CreateModel(
            name="SellerVerification",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("phone_number", models.CharField(blank=True, max_length=20, null=True)),
                ("verified_by_admin", models.BooleanField(default=False)),
                ("verified_at", models.DateTimeField(blank=True, null=True)),
                ("user", models.OneToOneField(on_delete=models.CASCADE, related_name="verification", to="users.user")),
            ],
            options={
                "db_table": "seller_verifications",
            },
        ),
    ]