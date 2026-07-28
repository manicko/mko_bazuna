---
id: db-indexes
domain: database
tags:
  - database
  - indexes
  - postgresql
  - search
related:
  - db-schema
  - db-enums
  - technical-specification
---

## Purpose

Indexes and the `search_vector` trigger SQL for phase 1. Single source of truth for the seven
named indexes and the two plpgsql trigger functions that keep `search_vector` and the denormalized
`category_name` in sync. Table/column definitions live in [db-schema.md](db-schema.md); StrEnum
types live in [db-enums.md](db-enums.md).

## Indexes — ads
```python
models.Index(name='IX_ads_pub_listing',
    fields=['status', 'category_id', 'city_id', '-published_at'],
    condition=Q(status=AdStatus.PUBLISHED))                 # partial: ~99% of public reads
models.Index(name='IX_ads_user_status', fields=['user_id', 'status'])
GinIndex(name='IX_ads_search_gin', fields=['search_vector'])  # real GIN on TSVECTOR
models.Index(name='IX_ads_archive_sweep', fields=['status', 'published_at'],
    condition=Q(status=AdStatus.PUBLISHED))                 # archive @2mo
models.Index(name='IX_ads_delete_sweep', fields=['status', 'published_at'],
    condition=Q(status=AdStatus.ARCHIVED))                 # delete @4mo
models.Index(name='IX_ads_purge_failed', fields=['status', 'moderation_failed_at'],
    condition=Q(status=AdStatus.ON_MODERATION_FAILED))      # 7-day purge (zone C4/D12)
models.Index(name='IX_ads_rejected_sweep', fields=['status', 'rejected_at'],
    condition=Q(status=AdStatus.REJECTED))                 # REJECTED @90d (zone D4)
```
Standalone `status`/`category_id`/`city_id` indexes not needed — covered by composites. `price` has no index (rare filter in phase 1; add only after EXPLAIN ANALYZE at 500k rows, zone C7).

## Indexes — users
```python
models.Index(name='IX_users_erasure_sweep', fields=['consent_revoked_at'])  # zone R1: idempotent 30-day hard-delete sweep
```

> Zone R1: `IX_users_erasure_sweep` supports the idempotent 30-day hard-delete sweep after
> consent withdrawal (decision O3).

## search_vector triggers (zone D1, sync-safety, multi-language)
Because `search_vector` includes the category name (another table), the column cannot be
`GENERATED ALWAYS` — a plpgsql trigger fills it. All computation lives in ONE function so INSERT and
UPDATE paths don't diverge. Code writes `title`/`description`/`category_id`; the trigger fills
`category_name` + `search_vector`.

For multi-language support, the search vector includes all language variants with appropriate FTS configurations:
```sql
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
END; $$ LANGUAGE plpgsql;

CREATE TRIGGER ads_search_vector_update
  BEFORE INSERT OR UPDATE ON ads
  FOR EACH ROW EXECUTE FUNCTION ads_search_vector_fn();
```

Bosnian uses `simple` config because PostgreSQL 18 has no native Bosnian text search configuration.
The `ad_images` table also includes thumbnail fields for future phase:
```
thumbnail_small (storage key for 240x180 thumbnail)
thumbnail_medium (storage key for 640x480 thumbnail)
thumbnail_large (storage key for 1280x960 thumbnail)
```

```sql
CREATE OR REPLACE FUNCTION categories_name_propagate() RETURNS TRIGGER AS $$
BEGIN
  UPDATE ads SET category_id = ads.category_id  -- trigger #2 recomputes category_name+search_vector
  WHERE category_id = NEW.id;
  RETURN NEW;
END; $$ LANGUAGE plpgsql;

CREATE TRIGGER on_category_name_update
  AFTER UPDATE OF name ON categories
  FOR EACH ROW EXECUTE FUNCTION categories_name_propagate();
```

> Zone D1 (sync-safety): `ads_search_vector_fn` and `categories_name_propagate` keep
> `category_name` + `search_vector` consistent across INSERT/UPDATE and category renames.

**Migration notes:** one-time `UPDATE ads SET category_id = category_id` (or backfill) to fill
`category_name` + `search_vector` for existing rows. O(n_ads) per category rename — acceptable for
~30-50 categories.
