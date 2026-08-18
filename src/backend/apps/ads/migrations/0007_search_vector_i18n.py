# Hand-written (plan impl_003): add per-language search vector columns, update
# the dual-write trigger to populate both the legacy concatenated vector and the
# three per-language vectors (with localized category names), expand the category
# propagate trigger to fire on name_i18n changes, and backfill existing rows.
#
# The 3 GIN indexes are built in migration 0008 (CREATE INDEX CONCURRENTLY).

from django.contrib.postgres.search import SearchVectorField
from django.db import migrations


SEARCH_VECTOR_FN_SQL = """
CREATE OR REPLACE FUNCTION ads_search_vector_fn() RETURNS TRIGGER AS $$
DECLARE
  v_cat TEXT;
  v_name_bs TEXT;
  v_name_en TEXT;
BEGIN
  SELECT name, name_i18n->>'bs', name_i18n->>'en'
    INTO v_cat, v_name_bs, v_name_en
    FROM categories WHERE id = NEW.category_id;
  NEW.category_name := v_cat;
  NEW.search_vector :=
    setweight(to_tsvector('russian', coalesce(NEW.title,'')), 'A') ||
    setweight(to_tsvector('russian', coalesce(NEW.description,'')), 'B') ||
    setweight(to_tsvector('simple', coalesce(NEW.title_bs,'')), 'A') ||
    setweight(to_tsvector('simple', coalesce(NEW.description_bs,'')), 'B') ||
    setweight(to_tsvector('english', coalesce(NEW.title_en,'')), 'A') ||
    setweight(to_tsvector('english', coalesce(NEW.description_en,'')), 'B') ||
    setweight(to_tsvector('simple', coalesce(v_cat,'')), 'C');
  NEW.search_vector_ru :=
    setweight(to_tsvector('russian', coalesce(NEW.title,'')), 'A') ||
    setweight(to_tsvector('russian', coalesce(NEW.description,'')), 'B') ||
    setweight(to_tsvector('russian', coalesce(v_cat,'')), 'C');
  NEW.search_vector_bs :=
    setweight(to_tsvector('simple', coalesce(NEW.title_bs,'')), 'A') ||
    setweight(to_tsvector('simple', coalesce(NEW.description_bs,'')), 'B') ||
    setweight(to_tsvector('simple', coalesce(coalesce(v_name_bs, v_cat),'')), 'C');
  NEW.search_vector_en :=
    setweight(to_tsvector('english', coalesce(NEW.title_en,'')), 'A') ||
    setweight(to_tsvector('english', coalesce(NEW.description_en,'')), 'B') ||
    setweight(to_tsvector('english', coalesce(coalesce(v_name_en, v_cat),'')), 'C');
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;
"""

CATEGORY_PROPAGATE_TRIGGER_SQL = """
DROP TRIGGER IF EXISTS on_category_name_update ON categories;
CREATE TRIGGER on_category_name_update
  AFTER UPDATE OF name, name_i18n ON categories
  FOR EACH ROW EXECUTE FUNCTION categories_name_propagate();
"""


class Migration(migrations.Migration):

    dependencies = [
        ("ads", "0006_ad_ix_ads_purge_deleted_and_more"),
        ("categories", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="ad",
            name="search_vector_ru",
            field=SearchVectorField(
                blank=True,
                null=True,
                help_text="Russian TSVECTOR for native PostgreSQL FTS; NOT GENERATED ALWAYS",
            ),
        ),
        migrations.AddField(
            model_name="ad",
            name="search_vector_bs",
            field=SearchVectorField(
                blank=True,
                null=True,
                help_text="Bosnian TSVECTOR for native PostgreSQL FTS; NOT GENERATED ALWAYS",
            ),
        ),
        migrations.AddField(
            model_name="ad",
            name="search_vector_en",
            field=SearchVectorField(
                blank=True,
                null=True,
                help_text="English TSVECTOR for native PostgreSQL FTS; NOT GENERATED ALWAYS",
            ),
        ),
        migrations.RunSQL(
            sql=SEARCH_VECTOR_FN_SQL,
            reverse_sql=migrations.RunSQL.noop,
        ),
        migrations.RunSQL(
            sql=CATEGORY_PROPAGATE_TRIGGER_SQL,
            reverse_sql=migrations.RunSQL.noop,
        ),
        migrations.RunSQL(
            sql="UPDATE ads SET title = title;",
            reverse_sql=migrations.RunSQL.noop,
        ),
    ]
