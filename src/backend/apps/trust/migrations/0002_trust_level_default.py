"""Add default to trust_level field in SellerTrustScore."""

from django.db import migrations, models


class Migration(migrations.Migration):
    """Add default=TrustLevel.UNVERIFIED to trust_level field."""

    dependencies = [
        ("trust", "0001_initial"),
    ]

    operations = [
        migrations.AlterField(
            model_name="sellertrustscore",
            name="trust_level",
            field=models.CharField(
                choices=[
                    ("unverified", "unverified"),
                    ("verified", "verified"),
                    ("trusted", "trusted"),
                    ("pro", "pro"),
                ],
                default="unverified",
                max_length=20,
            ),
        ),
    ]