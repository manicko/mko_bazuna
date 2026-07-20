# Migration to add partial conditions to indexes

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('ads', '0002_search_vector_triggers'),
    ]

    operations = [
        # Remove old indexes and add them with conditions
        migrations.RemoveIndex(
            model_name='ad',
            name='IX_ads_pub_listing',
        ),
        migrations.RemoveIndex(
            model_name='ad',
            name='IX_ads_archive_sweep',
        ),
        migrations.RemoveIndex(
            model_name='ad',
            name='IX_ads_delete_sweep',
        ),
        migrations.RemoveIndex(
            model_name='ad',
            name='IX_ads_purge_failed',
        ),
        migrations.RemoveIndex(
            model_name='ad',
            name='IX_ads_rejected_sweep',
        ),
        migrations.AddIndex(
            model_name='ad',
            index=models.Index(
                fields=['status', 'category_id', 'city_id', '-published_at'],
                name='IX_ads_pub_listing',
                condition=models.Q(status='published'),
            ),
        ),
        migrations.AddIndex(
            model_name='ad',
            index=models.Index(
                fields=['status', 'published_at'],
                name='IX_ads_archive_sweep',
                condition=models.Q(status='published'),
            ),
        ),
        migrations.AddIndex(
            model_name='ad',
            index=models.Index(
                fields=['status', 'published_at'],
                name='IX_ads_delete_sweep',
                condition=models.Q(status='archived'),
            ),
        ),
        migrations.AddIndex(
            model_name='ad',
            index=models.Index(
                fields=['status', 'moderation_failed_at'],
                name='IX_ads_purge_failed',
                condition=models.Q(status='on_moderation_failed'),
            ),
        ),
        migrations.AddIndex(
            model_name='ad',
            index=models.Index(
                fields=['status', 'rejected_at'],
                name='IX_ads_rejected_sweep',
                condition=models.Q(status='rejected'),
            ),
        ),
    ]
