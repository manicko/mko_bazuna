# Seed Data Workflow

> **Purpose:** Generate realistic demo data for development and testing.
> **App:** `apps.seed` — management command `python manage.py seed`

## Overview

The seed module generates realistic demo data for the Mko Bazuna classifieds board. It produces:

- Users (fake Telegram accounts)
- Ads with multi-language content (ru, en, bs)
- Photos from bundled category-tagged images
- Analytics events and daily metrics

## Order of Operations

The seed workflow runs in this order:

```
1. Clean existing seed data
2. Load categories (via catalog builder from categories.yaml)
3. Load cities (from cities.json fixture)
4. Generate users
5. Generate ads (with template interpolation)
6. Generate images (from photo manifest)
7. Generate analytics (optional, enabled by default)
```

## Running the Seed Command

### Basic Usage

```bash
# Generate default seed data (10 users, 30 ads)
python manage.py seed --force

# Custom counts
python manage.py seed --users=20 --ads=100 --force

# Without analytics (faster)
python manage.py seed --users=5 --ads=20 --force --analytics=False

# Custom status distribution
python manage.py seed --users=10 --ads=30 --force --status-distribution='{"published": 0.8, "draft": 0.2}'
```

### Options

| Flag | Default | Description |
|------|---------|-------------|
| `--users` | 10 | Number of users to generate |
| `--ads` | 30 | Number of ads to generate |
| `--force` | False | Skip confirmation prompt |
| `--analytics` | True | Generate analytics events/metrics |
| `--status-distribution` | None | JSON string with status weights override |

### What Gets Seeded

- **Users:** Telegram users with unique `telegram_id`, random names, some with `username=None`
- **Ads:** Multi-language ads (ru, en, bs) with template-filled content, appropriate prices, and random statuses
- **Images:** 1-3 photos per ad from the category-tagged photo manifest
- **Analytics:** `AD_VIEWED` events and `DailyAdMetrics` for published ads

### Cleanup

The seed command automatically:
- Deletes all existing seed data (identified by `Ad.source = 'seed'`)
- Cleans the `MEDIA_ROOT/seed/` directory
- Re-loads categories via the builder (idempotent)

## Category Loading

Categories are loaded from the canonical YAML source:

```
apps/categories/catalog/categories.yaml
```

The `load_catalog()` function from `apps.categories.catalog.builder` creates/updates all Category records.
This is the same mechanism used by the catalog data migration — it is idempotent and safe to run multiple times.

The YAML file defines:
- 7 top-level sections: `real-estate`, `transport`, `goods`, `animals`, `services-jobs`, `business`, `charity`
- 171 leaf category slugs (e.g., `apartments`, `cars`, `phones`, `dogs`)
- Lookup groups for listing purpose and listing feature
- Category paths for multi-parent navigation

## Photo Download

### Prerequisites

1. **Pexels API key** (required) — set in `scripts/seed-images-config.json`
2. **Unsplash API key** (optional fallback) — set in `scripts/seed-images-config.json`
3. **`query_hierarchy.json`** — must be populated with search queries for all 171 leaf categories

### Configuration

Configuration file: `scripts/seed-images-config.json`

| Key | Default | Description |
|-----|---------|-------------|
| `pexels` | true | Enable Pexels photo source |
| `unsplash` | false | Enable Unsplash as fallback |
| `PEXELS_API_KEY` | "" | Pexels API key |
| `UNSPLASH_ACCESS_KEY` | "" | Unsplash API key |
| `photos_per_category` | 3 | Target photos per category |
| `pexels_safe_limit` | 800 | Maximum Pexels API requests per run |
| `max_image_size_bytes` | 100000 | Max file size (100KB per photo) |
| `jpeg_quality` | 75 | JPEG compression quality |
| `max_dimension_px` | 1080 | Max dimension on long side |

### Running the Download Script

```bash
python scripts/download_seed_photos.py          # single pass
python scripts/download_seed_photos.py --all     # loop until limits exhausted
python scripts/download_seed_photos.py --category avtomobili  # single category
```

The script:
1. Reads `query_hierarchy.json` from `apps/seed/fixtures/images/`
2. For each category slug, constructs search queries from objects, contexts, and styles
3. Downloads photos from Pexels (or Unsplash as fallback)
4. Saves JPEGs as `{category_slug}_{NN:02d}.jpg` in `apps/seed/fixtures/images/`
5. Auto-populates `photo_manifest.json` with entries for all downloaded photos

### Rate Limits

- Pexels free tier: ~200 requests/hour
- For 171 categories × 3 photos = 513 photos, expect ~1,539-2,052 search requests
- Estimated time: 15-25 minutes at Pexels free tier
- If rate-limited, the script can be run multiple times with `--all`
- Bump `pexels_safe_limit` if running multiple passes

### Photo Constraints

- Format: JPEG only
- Max size: 100KB per photo
- Max dimension: 1080px on the long side
- EXIF data stripped
- Photos bundled in the repo (no runtime network dependency)

## LLM Content Fixture Generation

### Output Files

| File | Location | Description |
|------|----------|-------------|
| `ads_templates.json` | `apps/seed/fixtures/ads_templates.json` | Ad text templates with multi-language variable interpolation |
| `query_hierarchy.json` | `apps/seed/fixtures/images/query_hierarchy.json` | Photo search query hierarchies per category |
| `word_lists.json` | `apps/seed/fixtures/word_lists.json` | Brand names, features, conditions, cities, item ages |

### Workflow

Use the LLM prompt at `.ai/llm-tasks/seed-content-generation.md` which:

1. Reads `categories.yaml` programmatically to get all 171 leaf slugs
2. Splits generation into 7 sessions (one per top-level section)
3. Each session produces partial output files
4. Partial files are merged into final fixture files
5. A validation script checks: all slugs valid, no duplicate IDs, JSON parseable

### Session Breakdown

| Session | Section | Leaf Count | Output Files |
|---------|---------|------------|--------------|
| 1 | `real-estate` | 11 | `ads_templates.real-estate.json`, `query_hierarchy.real-estate.json`, `word_lists.real-estate.json` |
| 2 | `transport` | 24 | `ads_templates.transport.json`, `query_hierarchy.transport.json`, `word_lists.transport.json` |
| 3 | `goods` | 49 | `ads_templates.goods.json`, `query_hierarchy.goods.json`, `word_lists.goods.json` |
| 4 | `animals` | 10 | `ads_templates.animals.json`, `query_hierarchy.animals.json`, `word_lists.animals.json` |
| 5 | `services-jobs` | 59 | `ads_templates.services-jobs.json`, `query_hierarchy.services-jobs.json`, `word_lists.services-jobs.json` |
| 6 | `business` | 19 | `ads_templates.business.json`, `query_hierarchy.business.json`, `word_lists.business.json` |
| 7 | `charity` | 1 | `ads_templates.charity.json`, `query_hierarchy.charity.json`, `word_lists.charity.json` |

### Template Requirements

- Minimum 2 templates per leaf category (342+ total)
- 4 default/fallback templates preserved (`default_sell_1`, `default_buy_1`, `default_offer_1`, `default_seek_1`)
- All 3 languages (ru, en, bs) populated per template
- Variables: `{condition}`, `{brand}`, `{feature}`, `{city}`, `{price}`, `{rooms}`, `{area}`, `{item_age}`, `{year}`, `{mileage}`, `{category}`

## Key Architecture Decisions

1. **Category source of truth:** `categories.yaml` at `apps/categories/catalog/categories.yaml` is canonical. Never use hardcoded slug lists.
2. **Photo manifest:** Auto-populated by `download_seed_photos.py`. No manual editing.
3. **Templates:** Generated by LLM, not manually written. The prompt references the YAML file, not inline slugs.
4. **No runtime network dependency:** All photos are bundled in the repo.
5. **Idempotent:** The seed command can be run multiple times safely.

## File Reference

| File | Purpose |
|------|---------|
| `apps/seed/management/commands/seed.py` | Django management command |
| `apps/seed/services/seed_service.py` | Seed orchestrator |
| `apps/seed/generators/ads.py` | AdGenerator with CATEGORY_GROUP_MAP |
| `apps/seed/generators/images.py` | ImageGenerator with manifest loading |
| `apps/seed/generators/users.py` | UserGenerator |
| `apps/seed/generators/analytics.py` | AnalyticsGenerator |
| `apps/seed/config/seed.default.json` | Default seed configuration |
| `apps/seed/fixtures/ads_templates.json` | Ad templates (LLM-generated) |
| `apps/seed/fixtures/word_lists.json` | Word lists (LLM-generated) |
| `apps/seed/fixtures/images/query_hierarchy.json` | Photo search queries (LLM-generated) |
| `apps/seed/fixtures/images/photo_manifest.json` | Photo manifest (auto-populated) |
| `apps/categories/catalog/categories.yaml` | Canonical category source |
| `apps/categories/catalog/builder.py` | Catalog builder |
| `scripts/download_seed_photos.py` | Photo download script |
| `scripts/seed-images-config.json` | Photo download configuration |
| `.ai/llm-tasks/seed-content-generation.md` | LLM prompt for content generation |