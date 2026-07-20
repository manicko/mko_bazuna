# Guarded migration to verify/create lifecycle-related partial indexes.
# Uses CREATE INDEX IF NOT EXISTS (PostgreSQL 18+) for idempotency.
# No-op if indexes already exist.

from django.db import migrations


class Migration(migrations.Migration):
    """Verify lifecycle indexes exist; create only if absent."""

    dependencies = [
        ("ads", "0003_add_index_conditions"),
        ("users", "0001_initial"),
    ]

    operations = [
        # IX_ads_archive_sweep: Partial index for PUBLISHED ads sweep (2-month archive)
        migrations.RunSQL(
            sql="""
                CREATE INDEX IF NOT EXISTS IX_ads_archive_sweep
                ON ads (status, published_at)
                WHERE status = 'published';
            """,
            reverse_sql="DROP INDEX IF EXISTS IX_ads_archive_sweep;",
        ),
        # IX_ads_delete_sweep: Partial index for ARCHIVED ads sweep (4-month delete)
        migrations.RunSQL(
            sql="""
                CREATE INDEX IF NOT EXISTS IX_ads_delete_sweep
                ON ads (status, published_at)
                WHERE status = 'archived';
            """,
            reverse_sql="DROP INDEX IF EXISTS IX_ads_delete_sweep;",
        ),
        # IX_users_erasure_sweep: Index for consent revocation sweep (30-day hard delete)
        migrations.RunSQL(
            sql="""
                CREATE INDEX IF NOT EXISTS IX_users_erasure_sweep
                ON users (consent_revoked_at);
            """,
            reverse_sql="DROP INDEX IF EXISTS IX_users_erasure_sweep;",
        ),
    ]