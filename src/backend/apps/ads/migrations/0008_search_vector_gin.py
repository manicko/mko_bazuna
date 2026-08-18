# Hand-written (plan impl_004): build the three per-language GIN indexes with
# CREATE INDEX CONCURRENTLY to avoid blocking writes on a populated table.
#
# atomic=False is required because CONCURRENTLY cannot run inside a transaction
# block. SeparateDatabaseAndState keeps the model state in sync (the indexes are
# declared in Ad.Meta) while the database builds them non-blockingly.

from django.contrib.postgres.indexes import GinIndex
from django.db import migrations


class Migration(migrations.Migration):

    atomic = False

    dependencies = [
        ("ads", "0007_search_vector_i18n"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunSQL(
                    sql=(
                        "CREATE INDEX CONCURRENTLY IX_ads_search_gin_ru "
                        "ON ads USING gin(search_vector_ru);"
                    ),
                    reverse_sql=(
                        "DROP INDEX CONCURRENTLY IF EXISTS IX_ads_search_gin_ru;"
                    ),
                ),
                migrations.RunSQL(
                    sql=(
                        "CREATE INDEX CONCURRENTLY IX_ads_search_gin_bs "
                        "ON ads USING gin(search_vector_bs);"
                    ),
                    reverse_sql=(
                        "DROP INDEX CONCURRENTLY IF EXISTS IX_ads_search_gin_bs;"
                    ),
                ),
                migrations.RunSQL(
                    sql=(
                        "CREATE INDEX CONCURRENTLY IX_ads_search_gin_en "
                        "ON ads USING gin(search_vector_en);"
                    ),
                    reverse_sql=(
                        "DROP INDEX CONCURRENTLY IF EXISTS IX_ads_search_gin_en;"
                    ),
                ),
            ],
            state_operations=[
                migrations.AddIndex(
                    model_name="ad",
                    index=GinIndex(
                        fields=["search_vector_ru"],
                        name="IX_ads_search_gin_ru",
                    ),
                ),
                migrations.AddIndex(
                    model_name="ad",
                    index=GinIndex(
                        fields=["search_vector_bs"],
                        name="IX_ads_search_gin_bs",
                    ),
                ),
                migrations.AddIndex(
                    model_name="ad",
                    index=GinIndex(
                        fields=["search_vector_en"],
                        name="IX_ads_search_gin_en",
                    ),
                ),
            ],
        ),
    ]
