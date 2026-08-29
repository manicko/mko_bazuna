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
1. Acquire session-scoped advisory lock (ID 110) — prevents concurrent seeds
2. Clean existing seed data (source-field filter, transactional, FK-safe order)
3. Load categories (via catalog builder from categories.yaml)
4. Load cities (from cities.json fixture)
5. Generate users, ads, images, and analytics — ALL inside one transaction.atomic()
   block (crash = full rollback to post-clean state)
   ├─ Generate users (source = AdSource.SEED)
   ├─ Generate ads with template interpolation (source = AdSource.SEED)
   ├─ Generate images (from photo manifest)
   └─ Generate analytics (optional, enabled by default; source = AdSource.SEED)
```

## Running the Seed Command

### Basic Usage

```bash
# Generate default seed data (10 users, 600 ads)
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
| `--ads` | 600 | Number of ads to generate |
| `--force` | False | Skip confirmation prompt |
| `--analytics` | True | Generate analytics events/metrics |
| `--status-distribution` | None | JSON string with status weights override |

### What Gets Seeded

- **Users:** Telegram users with unique `telegram_id`, random names, some with `username=None`, `source=AdSource.SEED`
- **Ads:** Multi-language ads (ru/en/bs) with template-filled content, appropriate prices, and random statuses, `source=AdSource.SEED`
- **Images:** 1-3 photos per ad from the category-tagged photo manifest
- **Analytics:** `AD_VIEWED` events and `DailyAdMetrics` for published ads, `source=AdSource.SEED`
- **PopularSearch:** Seed-generated popular searches, tagged with `source=AdSource.SEED`

### Cleanup

The seed command automatically cleans seed data using **direct `source`-field filtering**
(not reverse-FK traversal), ensuring orphaned seed users (with zero ads) are also removed:

- Cleans seed tables in FK-safe order: `DailyAdMetrics` → `AnalyticsEvent` → `AdImage` → `Ad` → `User` → `PopularSearch`
- All seed rows identified by `source = AdSource.SEED` (`source` field exists on `User`, `Ad`, `AnalyticsEvent`, and `PopularSearch`)
- `MEDIA_ROOT/seed/` directory wiped via `shutil.rmtree`
- Categories re-loaded via the catalog builder (idempotent `update_or_create` by slug)
- Advisory lock (ID 110) prevents concurrent seed runs

All cleanup + generation runs inside a single `transaction.atomic()` block — a mid-generation
crash rolls back to the post-clean state (no half-seeded data).

### Dev Workflow (`make up`)

`make up` forces re-runs of one-shot services (migrate, load_catalog, create_admin, seed)
by running `docker compose rm -sf` before `up`, so every `make up` produces a fresh seed
even if the image hasn't changed.

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
python scripts/download_seed_photos.py --validate  # check manifest vs files
python scripts/download_seed_photos.py --validate --fix=cleanup  # find and clean missing files
```

Both `--category=<slug>` and `--category <slug>` (and likewise `--fix=<mode>` / `--fix <mode>`) are accepted. Unknown flags abort with exit code 1. In `--all` mode, categories with fewer existing photos are processed first on each pass to prioritize under-represented categories.

The script:
1. Reads `query_hierarchy.json` from `apps/seed/fixtures/images/`
2. For each category slug, constructs search queries from objects, contexts, and styles
3. Downloads photos from Pexels (or Unsplash as fallback)
4. Saves JPEGs as `{category_slug}_{NN:02d}.jpg` in `apps/seed/fixtures/images/`
5. Auto-populates `photo_manifest.json` with entries for all downloaded photos

### Manifest Validation (`--validate`)

Before building a Docker image, verify that every entry in `photo_manifest.json`
has a corresponding JPEG file on disk AND that all categories from
`query_hierarchy.json` are represented in the manifest:

```bash
python scripts/download_seed_photos.py --validate
```

This exits with code 0 if all checks pass, or non-zero if any fixture JPEGs are
missing or any categories from `query_hierarchy.json` lack manifest entries.
Use this in CI or as a pre-build check before `docker compose build`.

### Manifest Cleanup (`--fix=cleanup`)

When fixture JPEGs are missing from disk (e.g. after a fresh clone wipes gitignored
images, or after `git clean -fdx`), the manifest still references them. The download
script's `--validate` mode reports the missing files but cannot repair them.

Use `--fix=cleanup` to prune stale manifest entries:

```bash
# Report missing files, clean stale entries, and re-validate
uv run python scripts/download_seed_photos.py --validate --fix=cleanup

# Clean without an initial validation report
uv run python scripts/download_seed_photos.py --fix=cleanup
```

**What it does:**
- Removes every manifest entry (in both `categories` and `default`) whose JPEG file
  does not exist in `apps/seed/fixtures/images/`.
- Saves the manifest atomically (temp file + `os.replace`) to prevent corruption
  on interruption.
- Logs a **WARNING** for any category that loses all its photos.

**What it does NOT do:**
- Does **not** delete any JPEG files from disk (orphans are harmless and safe
  to remove manually if desired).
- Does **not** modify `downloaded_ids.json` — photo IDs are kept so that previously
  accepted photos are not re-fetched.
- Does **not** require API keys or network access — cleanup is purely local.

After cleanup, all manifest-referenced files will exist on disk. Categories that
lost all photos remain in the manifest with an empty `photos` list; re-download
them with `--all` if needed.

### End-to-End Pipeline (3 Stages)

Seed photos flow through three stages — understanding this helps avoid common
pitfalls:

1. **Download** (`scripts/download_seed_photos.py`): A **standalone** script
   (no Django) that fetches JPEGs from Unsplash/Pexels and saves them to
   `apps/seed/fixtures/images/`. Produces `photo_manifest.json`,
   `downloaded_ids.json`, and `query_hierarchy.json` in the same directory.
   `photo_manifest.json` and `query_hierarchy.json` cover **all** 205 categories
   (leaf + non-leaf); the parent-category entries are simply unused at seed time
   because ads are assigned to leaf categories only. These JSON fixture files are
   committed to git; only the JPEG files (`*.jpg`) and `seed-images-config.json`
   are gitignored (see `.gitignore`).

2. **Seed** (`manage.py seed` → `ImageGenerator`): A Django-loaded generator
   that **copies** each fixture JPEG from `fixtures/images/` into
   `MEDIA_ROOT/seed/` (e.g. `media/seed/`). It reads `photo_manifest.json` to
   map category slugs to filenames, generates thumbnails, and creates
   `AdImage` ORM rows with `image = "seed/<filename>.jpg"`. **No network access
   at this stage** — all photos must be bundled as fixtures first.

3. **Read/Serve** (`SeedService._backfill_image_hashes`, `media_gate`):
   Reads JPEGs from `MEDIA_ROOT/seed/` via the path
   `Path(MEDIA_ROOT) / str(img.image)`, computes SHA-256 hashes, and serves
   them at `/media/seed/<filename>.jpg`.

**Key points:**
- The download script writes to **fixtures** (source); seeding copies to
  **media/seed** (runtime). Do not try to make the download script write to
  `MEDIA_ROOT` — it is standalone and cannot resolve Django settings.
- `_clean()` wipes `MEDIA_ROOT/seed/` on every re-seed, but leaves
  `fixtures/images/` intact — re-seeding does not re-download.
- Docker's `COPY . .` bakes fixture JPEGs into the image (`.dockerignore`
  excludes `media/` but NOT `fixtures/images/*.jpg`), giving the seed command
  its "all resources bundled" guarantee.

## Troubleshooting: Missing Photos

After recreating Docker containers (`make clean && make up` or `make reset && make up`), photos may
not appear on the site. This typically happens because:

1. **JPEG fixtures are missing** — fixture JPEGs (`*.jpg`) are gitignored
   (`src/backend/apps/seed/fixtures/images/*.jpg`). Fresh clones or `git clean -fdx` wipe them.
2. **`media_volume` was destroyed** — `make clean` / `make reset` run `docker compose down -v`,
   which removes the named volume containing seeded images.

### Recovery Procedure

1. **Verify JPEGs exist on disk:**
   ```bash
   ls -la src/backend/apps/seed/fixtures/images/*.jpg | head
   ```
   If the directory is empty or missing files, proceed to step 2.

2. **Download fixture photos** (requires API keys in `scripts/seed-images-config.json`):
   ```bash
   uv run python scripts/download_seed_photos.py --all
   ```

3. **Validate the manifest** against files on disk:
   ```bash
   uv run python scripts/download_seed_photos.py --validate
   ```
   If files are missing, clean stale manifest entries:
   ```bash
   uv run python scripts/download_seed_photos.py --validate --fix=cleanup
   ```

4. **Re-run the seed** to copy fixtures into `media_volume`:
   ```bash
   make seed
   ```
   Or, if using compose directly:
   ```bash
   docker compose -f docker-compose.yml -f docker-compose.dev.override.yml run --rm seed
   ```

5. **Verify media volume** inside the running `web` container:
   ```bash
   docker compose exec web ls -la /app/media/seed/ | head
   ```
   The directory should contain JPEG files referenced by `AdImage` rows.

### Notes

- Use `make down` (not `make clean`) to recreate containers **without** destroying `media_volume`.
- In dev mode, `seed` runs automatically on `make up` and `web` waits for it (FR01, FR02).
- The seed entrypoint (`/app/entrypoint-seed.sh`) now checks for fixture JPEGs and will refuse to
  run if none are found.

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
6. **Leaf-only category assignment:** Ads are assigned only to leaf categories
   (categories with no children). Parent/intermediate categories aggregate child
   ads via subtree filtering in the listings view and never directly hold ads.
   The seed loads only leaf categories via the MPTT `children` relation (see
   `SeedService._load_category_fixtures()`). The photo manifest still covers all
   205 categories (leaf + non-leaf); the parent-category entries are unused at
   seed time because `ImageGenerator` walks up the MPTT tree when a leaf
   category has no photos of its own.

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