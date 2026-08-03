# Migration for search_vector triggers and category_name propagation

from django.db import migrations

# SQL for the ads search vector trigger function
SEARCH_VECTOR_FN_SQL = """
CREATE OR REPLACE FUNCTION ads_search_vector_fn() RETURNS TRIGGER AS $$
DECLARE v_cat TEXT;
BEGIN
  SELECT name INTO v_cat FROM categories WHERE id = NEW.category_id;
  NEW.category_name := v_cat;
  NEW.search_vector :=
    setweight(to_tsvector('russian', coalesce(NEW.title,'')), 'A') ||
    setweight(to_tsvector('russian', coalesce(NEW.description,'')), 'B') ||
    setweight(to_tsvector('russian', coalesce(v_cat,'')), 'C');
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;
"""

# SQL for the trigger on ads table
SEARCH_VECTOR_TRIGGER_SQL = """
DROP TRIGGER IF EXISTS ads_search_vector_update ON ads;
CREATE TRIGGER ads_search_vector_update
  BEFORE INSERT OR UPDATE ON ads
  FOR EACH ROW EXECUTE FUNCTION ads_search_vector_fn();
"""

# SQL for the categories name propagate function
CATEGORY_PROPAGATE_FN_SQL = """
CREATE OR REPLACE FUNCTION categories_name_propagate() RETURNS TRIGGER AS $$
BEGIN
  UPDATE ads SET category_id = ads.category_id  -- trigger #2 recomputes category_name+search_vector
  WHERE category_id = NEW.id;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;
"""

# SQL for the trigger on categories table
CATEGORY_PROPAGATE_TRIGGER_SQL = """
DROP TRIGGER IF EXISTS on_category_name_update ON categories;
CREATE TRIGGER on_category_name_update
  AFTER UPDATE OF name ON categories
  FOR EACH ROW EXECUTE FUNCTION categories_name_propagate();
"""

# Backfill SQL to populate category_name and search_vector for existing rows
BACKFILL_SQL = """
UPDATE ads SET category_id = category_id;
"""


class Migration(migrations.Migration):
    dependencies = [
        ("ads", "0001_initial"),
        ("categories", "0001_initial"),
    ]

    operations = [
        migrations.RunSQL(
            SEARCH_VECTOR_FN_SQL,
            reverse_sql=migrations.RunSQL.noop,
        ),
        migrations.RunSQL(
            SEARCH_VECTOR_TRIGGER_SQL,
            reverse_sql=migrations.RunSQL.noop,
        ),
        migrations.RunSQL(
            CATEGORY_PROPAGATE_FN_SQL,
            reverse_sql=migrations.RunSQL.noop,
        ),
        migrations.RunSQL(
            CATEGORY_PROPAGATE_TRIGGER_SQL,
            reverse_sql=migrations.RunSQL.noop,
        ),
        migrations.RunSQL(
            BACKFILL_SQL,
            reverse_sql=migrations.RunSQL.noop,
        ),
    ]