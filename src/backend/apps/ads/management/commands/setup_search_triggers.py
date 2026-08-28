"""Management command to create PostgreSQL search-vector trigger infrastructure.

After a migration squash that deletes and regenerates migration files via
``makemigrations``, raw SQL DDL such as trigger functions and triggers cannot
be regenerated from model state. This command recreates them idempotently so
that the entrypoint can run it after fresh schema creation.

It installs four idempotent DDL objects:

1. ``ads_search_vector_fn``  — BEFORE INSERT OR UPDATE trigger function on ``ads``
   that populates ``search_vector``, ``search_vector_ru``, ``search_vector_bs``
   and ``search_vector_en`` (i18n-aware, per-language vectors with localized
   category names).
2. ``categories_name_propagate`` — AFTER UPDATE trigger function on ``categories``
   that propagates ``name`` to ``ads.category_name``.
3. ``ads_search_vector_update`` — the BEFORE INSERT OR UPDATE trigger on ``ads``
   wiring ``ads_search_vector_fn``.
4. ``on_category_name_update`` — the AFTER UPDATE trigger on ``categories``
   firing on ``name`` and ``name_i18n`` columns, wiring
   ``categories_name_propagate``.

All objects are idempotent: ``CREATE OR REPLACE FUNCTION`` plus
``DROP TRIGGER IF EXISTS`` followed by ``CREATE TRIGGER``.
"""

import logging

from django.core.management.base import BaseCommand
from django.db import connection

logger = logging.getLogger(__name__)

# ── Trigger function 1 ────────────────────────────────────────────────
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

# ── Trigger function 2 ──────────────────────────────────────────────
CATEGORY_PROPAGATE_FN_SQL = """
CREATE OR REPLACE FUNCTION categories_name_propagate() RETURNS TRIGGER AS $$
BEGIN
  UPDATE ads SET category_name = NEW.name
  WHERE category_id = NEW.id;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;
"""

# ── Trigger 3 ───────────────────────────────────────────────────────
SEARCH_VECTOR_TRIGGER_SQL = """
DROP TRIGGER IF EXISTS ads_search_vector_update ON ads;
CREATE TRIGGER ads_search_vector_update
  BEFORE INSERT OR UPDATE ON ads
  FOR EACH ROW EXECUTE FUNCTION ads_search_vector_fn();
"""

# ── Trigger 4 ───────────────────────────────────────────────────────
CATEGORY_PROPAGATE_TRIGGER_SQL = """
DROP TRIGGER IF EXISTS on_category_name_update ON categories;
CREATE TRIGGER on_category_name_update
  AFTER UPDATE OF name, name_i18n ON categories
  FOR EACH ROW EXECUTE FUNCTION categories_name_propagate();
"""

# Ordered so that functions are created before the triggers that reference them.
DDL_STATEMENTS: tuple[tuple[str, str], ...] = (
    ("function ads_search_vector_fn", SEARCH_VECTOR_FN_SQL),
    ("function categories_name_propagate", CATEGORY_PROPAGATE_FN_SQL),
    ("trigger ads_search_vector_update", SEARCH_VECTOR_TRIGGER_SQL),
    ("trigger on_category_name_update", CATEGORY_PROPAGATE_TRIGGER_SQL),
)


class Command(BaseCommand):
    """Create PostgreSQL search-vector trigger functions and triggers."""

    help = (
        "Create idempotent PostgreSQL trigger functions and triggers for "
        "multi-language ad search vectors"
    )

    def handle(self, *args, **options) -> None:
        """Execute all DDL statements against the database.

        Each statement is wrapped in its own transaction savepoint so that a
        failure aborts only the offending statement while earlier ones remain
        committed (raw DDL via ``connection.cursor``).
        """
        for label, sql in DDL_STATEMENTS:
            with connection.cursor() as cursor:
                cursor.execute(sql)
            logger.info("Installed %s", label)
            self.stdout.write(self.style.SUCCESS(f"Installed {label}"))

        self.stdout.write(
            self.style.SUCCESS(
                "Search-vector trigger infrastructure installed successfully"
            )
        )
