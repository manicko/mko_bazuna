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
  - spec-index
---

## Purpose

Indexes and the search-vector trigger SQL for phases 1 and 2. Single source of truth for the
named indexes and the two plpgsql trigger functions that keep the per-language
`search_vector_ru/bs/en` and the denormalized `category_name` in sync. Table/column
definitions live in [db-schema.md](db-schema.md); StrEnum types live in [db-enums.md](db-enums.md).

## Indexes — ads
```python
models.Index(name='IX_ads_pub_listing',
    fields=['status', 'category_id', 'city_id', '-published_at'],
    condition=Q(status=AdStatus.PUBLISHED))                 # partial: ~99% of public reads
models.Index(name='IX_ads_user_status', fields=['user_id', 'status'])
GinIndex(name='IX_ads_search_gin', fields=['search_vector'])          # legacy concatenated vector (to be dropped)
GinIndex(name='IX_ads_search_gin_ru', fields=['search_vector_ru'])    # real GIN on Russian TSVECTOR
GinIndex(name='IX_ads_search_gin_bs', fields=['search_vector_bs'])    # real GIN on Bosnian TSVECTOR
GinIndex(name='IX_ads_search_gin_en', fields=['search_vector_en'])    # real GIN on English TSVECTOR
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
Because the search vectors include the category name (another table), the columns cannot be
`GENERATED ALWAYS` — a plpgsql trigger fills them. All computation lives in ONE function so INSERT and
UPDATE paths don't diverge. Code writes `title`/`description`/`category_id`; the trigger fills
`category_name` + the per-language `search_vector_ru/bs/en` (and, during the transition, the legacy
concatenated `search_vector`).

The trigger dual-writes the legacy vector and the three per-language vectors, using the correct
config per language and localized category names:
```sql
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
  UPDATE ads SET category_name = NEW.name  -- trigger #2 recomputes category_name + search vectors
  WHERE category_id = NEW.id;
  RETURN NEW;
END; $$ LANGUAGE plpgsql;

CREATE TRIGGER on_category_name_update
  AFTER UPDATE OF name, name_i18n ON categories
  FOR EACH ROW EXECUTE FUNCTION categories_name_propagate();
```

> Zone D1 (sync-safety): `ads_search_vector_fn` and `categories_name_propagate` keep
> `category_name` + the per-language search vectors consistent across INSERT/UPDATE and
> category renames / `name_i18n` edits. The trigger fires on `name_i18n` updates so localized
> category name changes re-index all affected ads.

**Migration notes:** one-time `UPDATE ads SET title = title` to backfill the per-language vectors
for existing rows (seed uses `bulk_create`, bypassing the trigger). O(n_ads) per category rename —
acceptable for ~30-50 categories.

## Indexes — analytics_events
```python
# FK columns user_id and ad_id have implicit indexes (Django default)
# No explicit additional indexes — queries filter by event_type + timestamp
```

## Indexes — daily_ad_metrics
```python
models.UniqueConstraint(fields=["ad", "date"], name="uq_daily_ad_metrics_ad_date")
models.Index(fields=["date", "-views_count"], name="idx_daily_metrics_date_views")
```

## Indexes — ad_moderation_priorities
```python
models.Index(fields=["priority_level"])
models.Index(fields=["base_score"])
models.Index(fields=["escalation_required"])
```

## Indexes — popular_searches
```python
# Implicit via db_index=True on model fields
models.CharField("query", max_length=200, db_index=True)
models.CharField("query_normalized", max_length=200, db_index=True)
```

## Indexes — search_history
```python
# Implicit via db_index=True on model field
models.CharField("query_normalized", max_length=200, db_index=True)
```

## Indexes — saved_search_notifications
```python
models.UniqueConstraint(fields=["saved_search", "ad"], name="uq_saved_search_ad")
```

## Indexes — seller_trust_scores
```python
# OneToOneField on user_id has implicit unique index (Django default)
# No explicit additional indexes
```

## Indexes — category_listing_purposes
```python
models.Index(name='IX_cat_listing_purpose_composite', fields=['category', 'listing_purpose'])
models.Index(name='IX_cat_listing_purpose_reverse', fields=['listing_purpose'])  # reverse lookup on deactivation
```

## Indexes — category_listing_features
```python
models.Index(name='IX_cat_listing_feature_composite', fields=['category', 'feature'])
models.Index(name='IX_cat_listing_feature_reverse', fields=['feature'])  # reverse lookup on deactivation
```

## Indexes — ad_features
```python
# Unique constraint on (ad, feature) covers lookups by ad
# No additional indexes needed — M2M lookups go through Ad.features
```

## Indexes — ad_images
```python
models.Index(name='IX_adimages_sha256', fields=['sha256'])  # photo deduplication lookup
```
