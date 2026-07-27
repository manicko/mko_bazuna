"""Update search vector trigger to index all language variants.

Migration 0004 added title_en, description_en, title_bs, description_bs, and
original_language columns. This migration updates the ads_search_vector_fn()
trigger function to include all six language columns in the search vector with
appropriate FTS configurations (russian, simple, english).

The existing columns title and description have NOT been renamed yet, so the
trigger function still references NEW.title and NEW.description (Russian).
"""

from django.db import migrations

# Original function (from migration 0002) — for rollback recovery
OLD_SEARCH_VECTOR_FN = """
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

# New multi-language search vector function
NEW_SEARCH_VECTOR_FN = """
CREATE OR REPLACE FUNCTION ads_search_vector_fn() RETURNS TRIGGER AS $$
DECLARE v_cat TEXT;
BEGIN
  SELECT name INTO v_cat FROM categories WHERE id = NEW.category_id;
  NEW.category_name := v_cat;
  NEW.search_vector :=
    setweight(to_tsvector('russian', coalesce(NEW.title,'')), 'A') ||
    setweight(to_tsvector('russian', coalesce(NEW.description,'')), 'B') ||
    setweight(to_tsvector('simple', coalesce(NEW.title_bs,'')), 'A') ||
    setweight(to_tsvector('simple', coalesce(NEW.description_bs,'')), 'B') ||
    setweight(to_tsvector('english', coalesce(NEW.title_en,'')), 'A') ||
    setweight(to_tsvector('english', coalesce(NEW.description_en,'')), 'B') ||
    setweight(to_tsvector('simple', coalesce(v_cat,'')), 'C');
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;
"""

# Original trigger SQL (from migration 0002) — for rollback recovery
TRIGGER_SQL = """
CREATE TRIGGER ads_search_vector_update
  BEFORE INSERT OR UPDATE ON ads
  FOR EACH ROW EXECUTE FUNCTION ads_search_vector_fn();
"""


class Migration(migrations.Migration):
    """Update the search vector trigger function for multi-language support."""

    dependencies = [
        ("ads", "0004_ad_i18n_columns"),
    ]

    operations = [
        # Step 1: Drop the existing trigger (safe, recreated in step 3)
        migrations.RunSQL(
            sql="DROP TRIGGER IF EXISTS ads_search_vector_update ON ads;",
            reverse_sql=TRIGGER_SQL,
        ),
        # Step 2: Replace the trigger function with multi-language version
        migrations.RunSQL(
            sql=NEW_SEARCH_VECTOR_FN,
            reverse_sql=OLD_SEARCH_VECTOR_FN,
        ),
        # Step 3: Recreate the trigger
        migrations.RunSQL(
            sql=TRIGGER_SQL,
            reverse_sql="DROP TRIGGER IF EXISTS ads_search_vector_update ON ads;",
        ),
    ]