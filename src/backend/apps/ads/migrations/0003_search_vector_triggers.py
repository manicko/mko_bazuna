"""Add search vector trigger and category_name propagation.

Creates the trigger function ads_search_vector_fn() that auto-populates:
  - category_name (denormalized Russian category name from FK)
  - search_vector (Russian FTS vector from title + description + category_name)

Also creates categories_name_propagate() trigger that re-populates
search_vector when a category name is renamed.
"""

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
  UPDATE ads SET category_id = ads.category_id
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


class Migration(migrations.Migration):
    """Create search vector trigger and category_name propagation triggers.

    Dependencies:
    - ads/0002: FK fields and indexes exist
    - categories/0001: Category table exists
    """

    dependencies = [
        ("ads", "0002_initial"),
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
    ]