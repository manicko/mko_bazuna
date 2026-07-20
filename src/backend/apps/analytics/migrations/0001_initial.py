# Generated migration for analytics app

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ('users', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='AnalyticsEvent',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('event_type', models.CharField(choices=[('registration_created', 'registration_created'), ('ad_published', 'ad_published'), ('search_performed', 'search_performed'), ('contact_initiated', 'contact_initiated')], help_text='Type of analytics event', max_length=30)),
                ('timestamp', models.DateTimeField(auto_now_add=True, help_text='Event timestamp')),
                ('user', models.ForeignKey(blank=True, help_text='User who triggered event (SET NULL on erasure)', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='analytics_events', to='users.user')),
            ],
            options={
                'db_table': 'analytics_events',
            },
        ),
    ]
