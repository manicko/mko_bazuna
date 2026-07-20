# Generated migration for moderation app

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ('users', '0001_initial'),
        ('ads', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='ModerationCriteria',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('title_min_length', models.PositiveIntegerField(default=5, help_text='Minimum title length in characters')),
                ('title_max_length', models.PositiveIntegerField(default=100, help_text='Maximum title length in characters')),
                ('description_min_length', models.PositiveIntegerField(default=10, help_text='Minimum description length in characters')),
                ('description_max_length', models.PositiveIntegerField(default=2000, help_text='Maximum description length in characters')),
                ('price_required', models.BooleanField(default=True, help_text='If True, price field is required for all ads')),
                ('min_images', models.PositiveIntegerField(default=1, help_text='Minimum number of images required')),
                ('max_images', models.PositiveIntegerField(default=5, help_text='Maximum number of images allowed')),
                ('banned_words', models.JSONField(blank=True, default=list, help_text='List of banned words for moderation (case-insensitive)')),
                ('max_ads_per_user', models.PositiveIntegerField(default=10, help_text='Maximum active ads per user')),
                ('duplicate_title_threshold', models.PositiveIntegerField(default=85, help_text='Percentage similarity threshold for duplicate title detection (0-100)')),
                ('updated_at', models.DateTimeField(auto_now=True, help_text='Last update timestamp')),
                ('updated_by', models.ForeignKey(blank=True, help_text='Admin user who last updated criteria', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='criteria_updates', to='users.user')),
            ],
            options={
                'db_table': 'moderation_criteria',
                'verbose_name': 'Moderation Criteria',
                'verbose_name_plural': 'Moderation Criteria',
            },
        ),
        migrations.CreateModel(
            name='ModeratorActionLog',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('action_type', models.CharField(choices=[('reject', 'reject'), ('ban_account', 'ban_account'), ('soft_delete', 'soft_delete'), ('criteria_change', 'criteria_change'), ('other', 'other')], help_text='Type of moderator action', max_length=20)),
                ('reason', models.TextField(help_text='Moderation reason (INTERNAL ONLY - never shown to seller)')),
                ('created_at', models.DateTimeField(auto_now_add=True, help_text='Action timestamp')),
                ('ad', models.ForeignKey(blank=True, help_text='Ad being moderated (SET NULL on deletion)', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='moderation_logs', to='ads.ad')),
                ('user', models.ForeignKey(blank=True, help_text='User who was moderated or performed action (SET NULL on erasure)', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='moderation_actions', to='users.user')),
            ],
            options={
                'db_table': 'moderation_action_logs',
                'ordering': ['-created_at'],
            },
        ),
    ]
