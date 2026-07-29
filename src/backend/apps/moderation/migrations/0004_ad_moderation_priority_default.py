"""Add default=AdPriorityLevel.MEDIUM to priority_level field."""

from django.db import migrations, models


class Migration(migrations.Migration):
    """Add default=AdPriorityLevel.MEDIUM to priority_level on AdModerationPriority."""

    dependencies = [
        ("moderation", "0003_ad_moderation_priority"),
    ]

    operations = [
        migrations.AlterField(
            model_name="admoderationpriority",
            name="priority_level",
            field=models.CharField(
                choices=[("high", "high"), ("medium", "medium"), ("low", "low")],
                default="medium",
                max_length=10,
            ),
        ),
    ]