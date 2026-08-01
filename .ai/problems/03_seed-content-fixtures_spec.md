# Specification: Seed Content Fixtures — Realistic Photos & Multi-Language Templates

**File:** `03_seed-content-fixtures_spec.md`
**Status:** Final (ready for implementation planning)
**Date:** 2026-07-31
**Related Spec:** `.ai/problems/02_demo-seed-data_spec.md`
**Related Plan:** `.ai/plans/03_demo-seed-data_plan.md`
**Research:** `.ai/researches/seed_content_sourcing_research.md`

---

## 1. Problem Statement

The seed data module (spec `02_demo-seed-data`) is implemented and functional. However, it uses two types of **placeholder content** that prevent proper visual evaluation of the classifieds site:

1. **Placeholder images:** The `ImageGenerator` generates solid-color JPEGs via Pillow (`_generate_placeholder_jpeg()` — single-color rectangles with no real-world subject). These do not represent real classifieds photos (no products, no interiors, no vehicles).
2. **Flat text templates:** The `ads.json` fixture contains 51 hardcoded Russian templates with a single `{category}` placeholder. Titles and descriptions are fully static — no variable interpolation, no multi-language support (`title_en`, `description_en`, `title_bs`, `description_bs` are not populated).

**What is needed:** Replace the placeholder visual content and flat templates with:
- **Realistic photos** — minimum 3 per category, category-tagged, bundled in the repository from free CC0 sources.
- **Category-patterned text templates** — with variable placeholders (`{condition}`, `{brand}`, `{feature}`, `{city}`, etc.) that the `AdGenerator` fills dynamically, populated in Russian + Bosnian + English.

This is a development-only enhancement — it does not change any production behavior of the classifieds board.

---

## 2. Confirmed Requirements

### 2.1 Photo Sourcing Requirements

| ID | Requirement | Priority |
|----|-------------|----------|
| P01 | Bundle ~90 realistic JPEG photos in `fixtures/images/` directory | Must |
| P02 | Minimum 3 photos per category, with some categories having 12–16 | Must |
| P03 | Each photo tagged with one or more category slugs via `photo_manifest.json` | Must |
| P04 | Photos must be CC0 or equivalent license, allowing bundling in the MIT-licensed repo | Must |
| P05 | Each photo compressed to ≤100KB, dimensions ≤1080px on long side | Must |
| P06 | All EXIF data stripped from bundled photos | Must |
| P07 | Photos bundled in repo with flat directory structure + manifest | Must |
| P08 | A one-time download script (`scripts/download_seed_photos.py`) for reproducibility | Should |
| P09 | Include a small pool of default/fallback photos for uncategorized or missing categories | Must |
| P10 | Montenegro-specific or Mediterranean imagery preferred for real estate and lifestyle categories | Should |

### 2.2 Photo Manifest

| ID | Requirement | Priority |
|----|-------------|----------|
| M01 | `fixtures/images/photo_manifest.json` mapping category slug → photo entries | Must |
| M02 | Each photo entry includes: `filename`, `tags` (list), `width`, `height`, `category_slug` | Must |
| M03 | Manifest includes a `default` section for fallback photos | Must |
| M04 | Manifest includes `version` field for future compatibility | Must |

### 2.3 ImageGenerator Modifications

| ID | Requirement | Priority |
|----|-------------|----------|
| I01 | Replace `_get_seed_image_pool()` solid-color generation with manifest-based photo loading | Must |
| I02 | `ImageGenerator` selects photos by ad's category slug, falling back to `default` pool | Must |
| I03 | Pre-process all manifest photos once (not per-ad) — write to `MEDIA_ROOT/seed/`, generate thumbnails via `ThumbnailService` | Must |
| I04 | `SeedService._clean()` must explicitly clean `MEDIA_ROOT/seed/` before re-seeding | Must |
| I05 | `ThumbnailService` API is unchanged — already compatible | Must (verify) |

### 2.4 Text Template Requirements

| ID | Requirement | Priority |
|----|-------------|----------|
| T01 | Replace flat `ads.json` (51 flat templates) with `ads_templates.json` (hierarchical, category-specific) | Must |
| T02 | Each template includes title + description patterns for all 3 languages (ru, en, bs) | Must |
| T03 | Template variables: `{condition}`, `{brand}`, `{feature}`, `{city}`, `{price}`, `{rooms}`, `{area}`, `{item_age}`, `{year}`, `{mileage}`, `{category}` | Must |
| T04 | At least 50 template entries covering all 30 categories from `categories.json` | Must |
| T05 | Templates organized by `category_slug` with a `default` fallback set | Must |
| T06 | Word lists for variable interpolation stored alongside templates (in `word_lists.json` or inline) | Should |
| T07 | `AdGenerator` fills `title`, `description` (Russian) + `title_en`, `description_en`, `title_bs`, `description_bs` | Must |
| T08 | `AdGenerator` sets `original_language = "ru"` on generated ads | Must |

### 2.5 Data Type Coverage

| Entity | Source | Details |
|--------|--------|---------|
| **Photos** | Bundled CC0 JPEGs | 3–16 per category, ~100KB each, EXIF stripped, category-tagged via manifest |
| **Titles** | Template + Faker variables | Per-category patterns with `{condition}`, `{brand}`, `{feature}`, etc., in ru/bs/en |
| **Descriptions** | Template + Faker variables | Per-category patterns with `{rooms}`, `{area}`, `{price}`, `{item_age}`, etc., in ru/bs/en |
| **Word lists** | Static JSON | Per-language word lists for variable interpolation (conditions, brands, features, cities) |

### 2.6 Non-Functional Requirements

| ID | Requirement |
|----|-------------|
| N01 | Deterministic output: same Faker seed produces same result regardless of photo/template set |
| N02 | No network dependencies at seed time — all photos must be bundled in the repo (spec constraint N05 from spec 02) |
| N03 | No new runtime dependencies — download script may use `requests` as a dev-only tool |
| N04 | Photo + template sourcing is development-only — never run against production |
| N05 | Git repo size impact ≤ ~15MB (under GitHub's 50MB soft limit, no Git LFS needed) |

---

## 3. Conceptual Development Tasks

### Task 1: Create Photo Download Script

**Purpose:** Provide a reproducible, one-time script to download CC0 photos from Unsplash/Pexels and generate the photo manifest.

**Expected outcome:**
- `scripts/download_seed_photos.py` — a standalone Python script
- Uses Unsplash API (primary) and Pexels API (fallback) with free API keys
- Queries per category group (see research section 3.1)
- Downloads at `regular` size (1080px), compresses with Pillow to ≤100KB
- Strips EXIF data
- Outputs to `src/backend/apps/seed/fixtures/images/` with category-tagged naming
- Generates `photo_manifest.json`
- Script is dev-only — not part of the production codebase

**Dependencies:** None (new script)

**Acceptance criteria:**
- Script runs successfully with a valid API key
- Downloads ≥90 photos across all categories
- All photos ≤100KB after compression
- `photo_manifest.json` generated with correct category mappings
- Script is idempotent (can be re-run with force flag)

### Task 2: Bundle and Curate Photos

**Purpose:** Physically obtain high-quality, category-tagged JPEG photos and commit them to the repository.

**Expected outcome:**
- `src/backend/apps/seed/fixtures/images/` directory with ~90 JPEG files
- Each file named `{category_slug}_{NN}.jpg` (e.g., `kvartiry_01.jpg`, `avtomobili_03.jpg`)
- File sizes ≤100KB each (target ~60–100KB)
- All EXIF data stripped
- A human-curated set of default/fallback photos (2–3 images)
- Total directory size ≤12MB

**Dependencies:** Task 1 (download script)

**Acceptance criteria:**
- All 30 categories have ≥3 photos (except Services, Jobs, Sports which may have fewer)
- Photos are visually realistic (not solid colors, not text overlays)
- No copyrighted or attribution-required content
- `photo_manifest.json` maps each photo to its category with tags

### Task 3: Create Photo Manifest

**Purpose:** Define the JSON manifest that maps bundled photos to categories.

**Expected outcome:**
- `src/backend/apps/seed/fixtures/images/photo_manifest.json`
- Schema (see Section 5.2):
  ```json
  {
    "version": 1,
    "categories": {
      "kvartiry": { "photos": [{"filename": "kvartiry_01.jpg", "tags": ["interior"], "width": 1080, "height": 720}] },
      ...
    },
    "default": { "photos": [...] }
  }
  ```
- One entry per bundled photo file
- Tags provide additional metadata (e.g., "interior", "exterior", "front-angle")
- Default section for uncategorized fallbacks

**Dependencies:** Task 2 (photos must exist)

**Acceptance criteria:**
- Every `.jpg` file in `fixtures/images/` has a corresponding entry in the manifest
- Each photo entry maps to exactly one category (or default)
- Manifest is valid JSON, parseable by `json.load()`

### Task 4: Create Category-Patterned Template Fixture

**Purpose:** Replace the flat `ads.json` (51 templates) with a hierarchical `ads_templates.json` supporting category-specific patterns, multi-language content, and variable placeholders.

**Expected outcome:**
- `src/backend/apps/seed/fixtures/ads_templates.json`
- Hierarchical structure: `version`, `templates` (array of template objects)
- Each template: `id`, `category_slug`, `patterns` (ru/en/bs title + description), `variables` config
- At least 50 template entries covering all 30 categories
- Variables: `{condition}`, `{brand}`, `{feature}`, `{city}`, `{price}`, `{rooms}`, `{area}`, `{item_age}`, `{year}`, `{mileage}`, `{category}`
- Template ID format: `{category_slug}_{purpose}_{n}` (e.g., `kvartiry_sell_1`, `avtomobili_sell_1`)

**Dependencies:** None (new fixture file)

**Acceptance criteria:**
- Every template has a valid `category_slug` matching `categories.json`
- Every template has `patterns.ru`, `patterns.en`, `patterns.bs`
- All variable placeholders in templates are documented and supported by the generator
- Default templates exist for categories without specific templates

### Task 5: Create Word Lists for Variable Interpolation

**Purpose:** Provide per-language word lists for the template variable placeholders, enabling realistic, grammatically-correct content generation.

**Expected outcome:**
- `src/backend/apps/seed/fixtures/word_lists.json`
- Per-language word lists:
  - `conditions`: excellent/good/fair (ru/bs/en)
  - `brands`: product brands per category (e.g., Samsung, Apple for electronics; Toyota, BMW for vehicles)
  - `features`: selling points (WiFi, conditioner, etc.)
  - `cities`: Montenegro city names in all 3 languages
  - `item_ages`: "2 years", "недавно куплен" etc.
- Each word list is localized: `{"ru": [...], "en": [...], "bs": [...]}`
- At least 10 entries per word list per language

**Dependencies:** None (new fixture file)

**Acceptance criteria:**
- All variables in `ads_templates.json` have corresponding word lists
- Word lists contain ≥10 entries per language
- Word lists are culturally appropriate for Montenegro classifieds

### Task 6: Modify ImageGenerator to Use Category-Tagged Photos

**Purpose:** Update `ImageGenerator` to load `photo_manifest.json`, select photos by category, and remove the solid-color placeholder generation.

**Expected outcome:**
- `src/backend/apps/seed/generators/images.py` updated:
  - Remove `_generate_placeholder_jpeg()` and `_get_seed_image_pool()`
  - Add `_load_manifest()` to read `photo_manifest.json`
  - Add `_get_photos_for_category(category_slug)` with fallback to default pool
  - `generate()` accepts ads that already have their category set, and selects photos matching each ad's category
  - Pre-process all manifest photos once (write to `MEDIA_ROOT/seed/`, generate thumbnails via `ThumbnailService`)
- `SeedService` updated: `SeedService._clean()` adds `MEDIA_ROOT/seed/` cleanup via `shutil.rmtree()`
- `SeedService.run()` passes category information to `ImageGenerator`

**Dependencies:** Tasks 3, 4

**Acceptance criteria:**
- `ImageGenerator` loads manifest and selects category-appropriate photos
- All manifest photos are pre-processed once (not per-ad)
- `SeedService._clean()` removes all files from `MEDIA_ROOT/seed/`
- Re-running seed produces clean media state
- `ThumbnailService` is called without errors for all photos

### Task 7: Modify AdGenerator for Multi-Language Templates and Variable Interpolation

**Purpose:** Update `AdGenerator` to load `ads_templates.json`, fill variable placeholders with Faker, and generate content in all 3 languages.

**Expected outcome:**
- `src/backend/apps/seed/generators/ads.py` updated:
  - Replace `ads.json` loading with `ads_templates.json` loading
  - Add `_load_word_lists()` to read `word_lists.json`
  - Add `_fill_template(template, locale)` that replaces `{variable}` placeholders with word list values
  - `generate()` assigns category-specific templates (or fallback) per ad
  - `Ad` instances now set: `title` (ru), `description` (ru), `title_en`, `description_en`, `title_bs`, `description_bs`, `original_language = "ru"`
  - Backward compatible with existing `--status-distribution` CLI flag
- Update `AdGenerator._generate_price()` to use category slug from the new template structure

**Dependencies:** Tasks 4, 5

**Acceptance criteria:**
- Generated ads have all 3 language fields populated
- `{variable}` placeholders are replaced with values from word lists
- Category-specific templates are selected (or fallback to default templates)
- Determinism is preserved (same Faker seed = same content)
- Existing seed command tests still pass (updated for new fields)

### Task 8: Update SeedConfig and Existing Fixtures

**Purpose:** Ensure the seed module's configuration and existing fixtures are compatible with the new content structure.

**Expected outcome:**
- `config/seed.default.json` may need new config keys (e.g., `photo_manifest_version`, `template_version`)
- Old `fixtures/ads.json` is deprecated (can be kept for reference or removed)
- Categories fixture unchanged (already 30 categories with slugs)

**Dependencies:** Tasks 4, 5, 6, 7

**Acceptance criteria:**
- Config file updated with any new keys needed by generators
- Old `ads.json` either removed or marked as deprecated
- All fixture files are consistent

### Task 9: Write Tests for New Content Generation

**Purpose:** Ensure the new photo and template systems produce valid, deterministic output.

**Expected outcome:**
- `src/backend/apps/seed/tests/test_seed.py` updated with new tests:
  - `test_photo_manifest_loads`: manifest is valid JSON, covers all photos
  - `test_image_generator_category_selection`: ImageGenerator selects correct photos per category
  - `test_image_generator_fallback`: Falls back to default pool for unknown categories
  - `test_template_variables_filled`: All `{variable}` placeholders are replaced
  - `test_multi_language_templates`: All 3 language fields are populated
  - `test_original_language_set`: `original_language = "ru"` on generated ads
  - `test_word_lists_loaded`: Word lists are loaded and contain expected keys
  - `test_seed_with_realistic_photos`: Full seed run produces AdImage records with non-placeholder image keys
  - `test_media_cleanup`: `MEDIA_ROOT/seed/` is cleaned before re-seed
- Integration test: full seed run with small count, verify both photos and multi-language content

**Dependencies:** Tasks 6, 7

**Acceptance criteria:**
- All new tests pass: `uv run pytest src/backend/apps/seed/tests/`
- Tests are deterministic
- Tests verify observable outcomes (photo selection, language fields, variable filling)

### Task 10: Update Documentation

**Purpose:** Update relevant project documentation to reflect the new content sourcing approach.

**Expected outcome:**
- Update `docs/01-spec/spec-index.md` Phase 2 features if needed
- Update or create seed documentation reference
- Ensure `.ai/researches/seed_content_sourcing_research.md` is linked from the spec

**Dependencies:** All implementation tasks

**Acceptance criteria:**
- Doc maintenance rules followed (English only, frontmatter, cross-links)
- Documentation reflects the final implementation state

### Task 11: Create LLM Prompt Definition Document

**Purpose:** Produce the reusable LLM task document that instructs the LLM agent to autonomously generate all seed fixture content (ads_templates.json, word_lists.json, photo queries) by browsing Avito.ru, analyzing real ad patterns, and generating output files.

**Expected outcome:**
- `.ai/llm-tasks/seed-content-generation.md` containing a single unified LLM workflow prompt:

  1. **Phase 0 — Browse Avito:** Agent visits https://www.avito.ru/ and browses real ad pages per category group, studying title patterns, description structures, selling points, and photo types from live listings. Fallback to olx.ba, njuskalo.hr, barter.rs if Avito blocks access.
   
  2. **Phase 1 — Analyze Patterns:** Agent produces structured pattern definitions for all 24 leaf categories (title_patterns, description_sections, variables, selling_points, photo_types).
   
  3. **Phase 2 — Generate ads_templates.json:** Agent writes the fixture file with 50+ template entries covering all categories in ru/bs/en, using patterns from Phase 1.
   
  4. **Phase 3 — Generate word_lists.json:** Agent writes the word lists fixture file with per-language entries (10+ per list).
   
  5. **Phase 4 — Generate Photo Queries:** Agent produces per-category search queries for Unsplash/Pexels photo download script.

**Dependencies:** None (independent document)

**Acceptance criteria:**
- Document exists at `.ai/llm-tasks/seed-content-generation.md`
- The single prompt is autonomous — the LLM agent can run it from start to finish without human input
- The prompt includes explicit web browsing instructions to fetch Avito pages
- Fallback behavior defined (alternative sites if Avito blocks)
- Expected output file paths and JSON schemas are explicitly defined
- All 30 category slugs from `categories.json` are referenced correctly

---

## 4. Product Owner Decisions

| # | Question | Decision |
|---|----------|----------|
| D1 | Photo sourcing method | **A + D:** Free CC0 stock photo sites (Unsplash primary, Pexels/Pixabay backup) + curated CC0 repositories. One-time download script for reproducibility. |
| D2 | Avito parsing approach | **A + C:** Use existing 30 project categories + LLM agent browses Avito.ru directly (has online access). The agent visits real ad pages per category, extracts patterns from actual listings, then generates category-specific templates. No Python scraping scripts — the agent fetches and analyzes pages autonomously. |
| D3 | Photo quantity per category | **3+ per category**, with high-traffic categories (real estate, vehicles, electronics) having 12–16 photos. Total ~90 photos. |
| D4 | Text template languages | **B:** Russian (base) + Bosnian (bs) + English (en). Populate `title`, `description`, `title_en`, `description_en`, `title_bs`, `description_bs`. Set `original_language = "ru"`. |
| D5 | Text template structure | **A:** Replace all 51 flat templates with ~50 category-patterned templates. Each template has title/description patterns with variable placeholders per language. |
| D6 | Budget | **A:** Zero budget. Only free CC0 sources and LLM-assisted pattern definition (no paid API calls for content). |
| D7 | Photo-to-category mapping | **B:** Category-tagged photos. Each photo mapped to category(s) via `photo_manifest.json`. `ImageGenerator` selects by category with fallback to default pool. |
| D8 | LLM task structure | **A:** Two-phase. Phase 1: analyze categories and define pattern structure. Phase 2: generate actual content (templates + word lists + photo prompts). |
| D9 | LLM input source for Avito patterns | **A:** LLM agent browses Avito.ru directly. The agent fetches real ad pages per category, analyzes listing patterns (titles, descriptions, features, photo types) from actual live data, then generates structured patterns. No human-provided URLs needed — the agent navigates Avito autonomously. |
| D10 | Category coverage for LLM | **A:** Use existing 30 categories from `categories.json`. The LLM generates patterns for all 30 categories from its training knowledge. No human references needed. |
| D11 | LLM output maturity | **A:** Ready-to-commit output. The LLM generates complete `ads_templates.json` and `word_lists.json` files that pass validation. No human editing required. Content is validated by schema checks and automated tests, not manual review. |
| D12 | LLM prompt location | **A:** Prompts stored as a reusable document in `.ai/llm-tasks/seed-content-generation.md`. This document contains all three LLM tasks (category analysis, template generation, photo query generation) with system prompts, user prompts, and expected output format. |

---

## 5. Research Summary

**Research document:** `.ai/researches/seed_content_sourcing_research.md`

### 5.1 Photo Sources Evaluated

| Site | License | API | Rate Limit | Bundlable? | Recommended? |
|------|---------|-----|------------|-----------|-------------|
| **Unsplash** | Unsplash License (free, modify, distribute) | REST API | 1,000 req/hr (demo) | **Yes** | **Primary** |
| **Pexels** | Pexels License (free, no attribution) | REST API | 200 req/hr (default) | **Yes** | Backup |
| **Pixabay** | Pixabay License (free, no attribution) | REST API | 100 req/60s | **Yes** | Fallback |
| **Lorem Picsum** | Unsplash-sourced | No search API | None | Yes | **Rejected** (no search) |

**Key finding:** All three primary sources (Unsplash, Pexels, Pixabay) explicitly allow redistribution and bundling in MIT-licensed repositories. Unsplash offers the highest quality and best API.

### 5.2 Recommended Photo Sourcing Approach

**Hybrid — Script-Assisted Download + Manual Curation** (Research section 7.1):
1. Write `scripts/download_seed_photos.py` using Unsplash API
2. Download 5–10 photos per category query
3. Compress with Pillow to ≤100KB, strip EXIF
4. Human reviewer removes poor-quality images
5. Generate `photo_manifest.json` reflecting curated set

**Rationale:** Meets PO requirement for realistic photos, minimal manual effort, full reproducibility, category-tagged from the start, under 12MB total (no Git LFS needed).

### 5.3 Category-Tagged Photo Structure

| Field | Type | Description |
|-------|------|-------------|
| `version` | int | Manifest version for future compatibility |
| `categories` | object | Maps category slug → photo list |
| `categories.{slug}.photos` | array | List of photo objects |
| `photo.filename` | string | Filename (e.g., `kvartiry_01.jpg`) |
| `photo.tags` | array | Additional tags (e.g., `["interior", "living-room"]`) |
| `photo.width` | int | Image width in pixels |
| `photo.height` | int | Image height in pixels |
| `default` | object | Fallback photos for uncategorized ads |

### 5.4 Template Structure Recommendation

**New file:** `fixtures/ads_templates.json` — hierarchical structure replacing flat `ads.json`:

```json
{
  "version": 2,
  "placeholder_schema": { ... },
  "templates": [
    {
      "id": "real_estate_apartment_sell",
      "category_slug": "kvartiry",
      "patterns": {
        "ru": { "title": "Продам {condition} {rooms}-комнатную квартиру в {city}", "description": "..." },
        "en": { "title": "For sale: {condition} {rooms}-room apartment in {city}", "description": "..." },
        "bs": { "title": "Prodaje se {condition} stan sa {rooms} sobe u {city}", "description": "..." }
      },
      "variables": { "rooms": {"type": "random_int", "min": 1, "max": 4} }
    }
  ]
}
```

### 5.5 Multi-Language Field Mapping

| Ad Model Field | Source | Content |
|----------------|--------|---------|
| `title` | Template pattern `ru` | Russian title (base field) |
| `description` | Template pattern `ru` | Russian description (base field) |
| `title_en` | Template pattern `en` | English title |
| `description_en` | Template pattern `en` | English description |
| `title_bs` | Template pattern `bs` | Bosnian title |
| `description_bs` | Template pattern `bs` | Bosnian description |
| `original_language` | Constant | `"ru"` |

**Fallback chain** (from `Ad.get_title()` / `get_description()`): `title_{locale}` → `title` (Russian). Note: `title_ru` is checked in the getter but is not a model field — it effectively falls through to `title`.

### 5.6 Current ImageGenerator Architecture (to be modified)

**Current flow:**
1. `ImageGenerator.__init__()` receives `config` dict + `list[Ad]`
2. `_get_seed_image_pool()` generates 5 solid-color JPEGs via Pillow (cached module-level)
3. `_preprocess_images()` writes JPEGs to `MEDIA_ROOT/seed/`, generates thumbnails
4. `generate()` selects 1–3 random images per ad (no category awareness)
5. Images shared across all ads

**Required changes:**
- Remove `_generate_placeholder_jpeg()` and `_get_seed_image_pool()`
- Add `_load_manifest()` reading `photo_manifest.json`
- Add `_get_photos_for_category(category_slug)` with fallback to default pool
- Pre-process all manifest photos once (write originals + generate thumbnails)
- `SeedService._clean()` adds `MEDIA_ROOT/seed/` cleanup

### 5.7 ThumbnailService Compatibility

**Finding:** `ThumbnailService` is already compatible with the seed workflow. No changes needed.
- `generate_thumbnails(photo_bytes, key)` accepts raw bytes and a key string
- Uses `O_EXCL` atomic writes — `ImageGenerator._preprocess_images()` already handles `FileExistsError`
- Returns dict mapping `ThumbnailSizeStrEnum` → storage key

### 5.8 Storage and Performance Analysis

| Metric | Value |
|--------|-------|
| Total photos | ~90 |
| File size per photo | 60–100KB (target) |
| Total repo addition | ~9MB |
| Git LFS needed? | No (~12MB with overhead, under 50MB threshold) |
| Thumbnail generation time | ~2s for 90 photos × 3 sizes |
| Image phase total | ~2.2s (vs ~170ms for placeholders) |
| Impact assessment | Acceptable for a dev-only tool |

### 5.9 Implementation Order (from research)

1. Photo sourcing: Run download script, curate, commit to `fixtures/images/`
2. Photo manifest: Create `photo_manifest.json` with category mapping
3. ImageGenerator: Modify to load manifest, select photos by category
4. SeedService: Add media cleanup to `_clean()`
5. Template restructuring: Create `ads_templates.json`
6. AdGenerator: Add multi-language support, variable-filling, category-specific templates
7. Update tests: Cover new photo selection and multi-language template generation

### 5.10 Template Count by Category

| Category Group | Templates (per language) | Total (3 langs) |
|----------------|--------------------------|-----------------|
| Real Estate (kvartiry, doma, kommercheskaya, uchastki) | 10 | 30 |
| Vehicles (avtomobili, mototsikly, vodnyy, zapchasti) | 12 | 36 |
| Electronics (telefony, kompyutery, foto, bytovaya) | 12 | 36 |
| Services (uslugi, stroitelstvo, krasota, obrazovanie, yuridicheskie) | 7 | 21 |
| Jobs (vakansii, rezyume) | 5 | 15 |
| Pets (sobaki, koshki) | 5 | 15 |
| Other (mebel, odezhda, detskie, sport) | 10 | 30 |
| Default (fallback) | 5 | 15 |
| **Total** | **~50** | **~150** |

---

## 6. Assumptions

1. The seed content fixtures enhancement is **development-only** — it does not affect production classifieds behavior.
2. The LLM agent has web browsing capability and can fetch Avito.ru pages. If Avito blocks requests, alternative classifieds sites are used as fallback.
3. The Unsplash/Pexels API keys needed for the one-time download script are available (free tier is sufficient).
4. The `ThumbnailService.generate_thumbnails()` signature remains stable (verified by reading `media/services/thumbnails.py`).
5. The `AdImage.image` field (`CharField`, max_length=64) is sufficient for UUID-based storage keys (verified: current `{uuid}.jpg` = 41 chars; category-tagged keys will be `seed/{category}_{NN}.jpg` ≤ 64 chars).
6. The `categories.json` fixture (30 categories) is the authoritative category list for photo/template mapping.
7. The LLM-generated `ads_templates.json` and `word_lists.json` are validated by automated schema checks before committing — no manual review required.
8. The `Ad.title_ru` / `Ad.description_ru` fields referenced in `get_title()` are not separate model columns — the base `title` / `description` fields serve as Russian (verified via migration `0004_ad_i18n_columns.py`).
9. The existing seed command's `--status-distribution` CLI parameter remains unchanged.
10. The existing seed command's `--users` and `--ads` parameters remain unchanged.

---

## 7. Constraints

1. **No runtime network dependency:** All photos must be bundled in the repo (`fixtures/images/`). No download at seed time (constraint N05 from spec `02_demo-seed-data`).
2. **Zero budget:** Only free CC0 sources allowed. No paid API calls for content generation.
3. **No Python scraping scripts in the repository:** No dedicated scraping scripts or bots should be committed to the repository. The LLM agent may browse Avito.ru pages directly to study ad patterns (using web fetch tool), analyze real listings, and generate patterns from live data. This is ad-hoc research, not an automated pipeline.
4. **Repo size:** Total photo bundle ≤ ~15MB (no Git LFS). Individual photos ≤100KB.
5. **License compliance:** All bundled photos must be CC0 or equivalent (explicitly allowing redistribution in MIT-licensed repos).
6. **Determinism:** Seed output must remain deterministic — same Faker seed produces the same content regardless of which photo or template was selected.
7. **StrEnum for constants:** All new constant sets use `StrEnum` / `IntEnum` (project rule 10).
8. **English-only code:** All comments, logs, docstrings in English (project rule 1).
9. **No `print()` in service layer:** Use `logger = logging.getLogger(__name__)` (project rule 12).

---

## 8. Risks

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Avito blocks LLM agent requests (bot detection, captcha) | Medium | Medium | Fallback to alternative classifieds (olx.ba, njuskalo.hr, barter.rs). If all blocked, agent uses training data as last resort. |
| Category-tagged photos exceed 64-char `AdImage.image` field limit | Low | High | Use naming convention `{category_prefix}_{NN}.jpg` — max ~25 chars, well under 64. |
| Unsplash API rate limit blocks one-time download | Low | Low | Use 1080px `regular` size, batch queries per category. Pexels/Pixabay as fallback. |
| Multi-language template variables are grammatically incorrect in bs/en | Medium | Medium | LLM generates all 3 languages with explicit instructions for natural translation. Automated schema validation catches format errors. |
| Word list for a category lacks appropriate entries | Low | Low | Provide default/fallback words. Minimum 10 entries per word list per language. |
| `MEDIA_ROOT/seed/` cleanup fails on Windows (file locks) | Low | Low | Use `shutil.rmtree(..., ignore_errors=True)` + log warnings. |
| Old `ads.json` fixture not removed, causing confusion | Medium | Low | Deprecate with clear comment or remove. Update `AdGenerator` to only use `ads_templates.json`. |
| Photo manifest becomes out of sync with actual files | Medium | Medium | Test: every `.jpg` file has a manifest entry, every manifest entry has a file. |
| Seeding with many photos makes test runs slower | Low | Low | Image phase adds ~2s — acceptable. Tests use small photo sets or skip image phase. |
| LLM generates malformed JSON output | Medium | Medium | All LLM tasks include explicit schema in the prompt. Run `json.load()` validation before committing. |

---

## 9. Open Questions

1. **None (resolved by PO decisions).** All business decisions have been resolved by the Product Owner. The remaining unknowns are technical and will be resolved during implementation research.

---

## 10. Out of Scope

- **Production photo upload from Telegram:** Only seed/placeholder photos are in scope. Real Telegram photo upload flow is already implemented and unchanged.
- **AI image generation at runtime:** All photos are pre-bundled. No AI image generation during seeding.
- **Content generation infrastructure:** The LLM agent browses Avito once to study patterns and generate fixture files. No automated content pipeline, no cron jobs, no build-time generation. Fixture files are committed to the repo and used statically.
- **Photo editing features:** No photo editing UI, no photo enhancement beyond compression.
- **Photo moderation:** Seed photos are assumed appropriate. No moderation pipeline for seed content.
- **Multi-currency support:** Deferred per architecture docs (decision I). Price is integer BAM only.
- **Video content:** Photos only (JPEG). No video seed content.
- **Photo attribution display:** CC0 photos don't require attribution. No attribution UI needed.

---

## 11. LLM Task Definitions

**File:** `.ai/llm-tasks/seed-content-generation.md`

This section defines the single autonomous LLM workflow that generates all seed fixture content. The agent has web browsing capability and runs all phases in one session — no human intervention required.

**Output files produced:**
1. `src/backend/apps/seed/fixtures/ads_templates.json` — 50+ template entries
2. `src/backend/apps/seed/fixtures/word_lists.json` — per-language word lists
3. `scripts/download_seed_photos.py` — photo download script (using generated search queries)

---

### 11.1 LLM Workflow Prompt

**Purpose:** Browse real Avito.ru classifieds, analyze category patterns, generate fixture content, and produce photo search specifications — all in one autonomous session.

**System prompt:**
```
You are a classifieds content generation agent with full web browsing capability.
You have tools to fetch URLs, read web pages, and write files.
Your mission is to generate realistic seed content for a Montenegro classifieds board
by studying real ads on Avito.ru and similar platforms.

You write natural classifieds text in Russian (native), English (fluent),
and Bosnian/Serbian/Croatian (fluent, Latin script, Montenegro-specific vocabulary).

You have complete autonomy — use your web browsing tool to visit Avito,
study real ad patterns, then generate all fixture files.
```

**User prompt (single workflow):**
```
Generate all seed fixture content for a Montenegro classifieds board by following 
these 4 phases in order. You have web browsing capability — use it to study real ads.

=== PHASE 0: BROWSE AVITO CATEGORIES ===

First, visit https://www.avito.ru/ to understand the category structure.
Then browse each of these category groups and open 3-4 individual ad pages per group:

1. REAL ESTATE → kvartiry, doma, kommercheskaya, uchastki
2. VEHICLES → avtomobili, mototsikly, vodnyy, zapchasti
3. ELECTRONICS → telefony, kompyutery, foto, bytovaya
4. SERVICES → stroitelstvo, krasota, obrazovanie, yuridicheskie
5. JOBS → vakansii, rezyume
6. PETS → sobaki, koshki
7. STANDALONE → mebel, odezhda, detskie, sport

For each ad you read, note:
- Title structure and common patterns
- Description sections and how they're formatted
- Selling points and features mentioned
- Types of photos posted
- What variables are typically included (price, condition, brand, year, etc.)

If Avito blocks your requests, try: olx.ba, njuskalo.hr, or barter.rs.

=== PHASE 1: ANALYZE PATTERNS ===

From your browsing, produce a structured analysis of ALL 24 leaf categories.
Store the analysis as a JSON object with this structure for each category:
{
  "title_patterns": ["3-5 title templates with {variable} placeholders"],
  "description_sections": ["typical sections like condition, features, location"],
  "variables": ["relevant variable names from the list"],
  "selling_points": ["10-15 common selling phrases"],
  "photo_types": ["facade", "living_room", ...]
}

Variables available: condition, brand, feature, city, price, rooms, area, item_age, year, mileage, category

=== PHASE 2: GENERATE ads_templates.json ===

Using the patterns from Phase 1, create ads_templates.json with 50+ entries.
Write the file to: src/backend/apps/seed/fixtures/ads_templates.json

Schema:
{
  "version": 2,
  "placeholder_schema": { ... },
  "templates": [
    {
      "id": "{category_slug}_{purpose}_{NN}",
      "category_slug": "...",
      "patterns": {
        "ru": { "title": "...", "description": "2-4 sentences" },
        "en": { "title": "...", "description": "natural English, not literal translation" },
        "bs": { "title": "...", "description": "Latin script, Montenegro Bosnian" }
      }
    }
  ]
}

Rules:
- Russian is base (most detailed, realistic Avito-style)
- English and Bosnian: natural translations, NOT word-for-word from Russian
- At least 50 templates, all 24 leaf categories covered
- High-traffic: kvartiry(4), avtomobili(4), telefony(3), kompyutery(3), mebel(3), odezhda(3)
- Default fallback: 2-3 templates
- Descriptions are 2-4 realistic sentences, not lists
- Category-appropriate variables (real estate → rooms/area, vehicles → mileage/year)
- No prices, dates, phone numbers in templates (filled at runtime by Faker)

=== PHASE 3: GENERATE word_lists.json ===

Write the file to: src/backend/apps/seed/fixtures/word_lists.json

Schema:
{
  "version": 1,
  "conditions": { "ru": [10+], "en": [10+], "bs": [10+] },
  "brands": {
    "elektronika": { "ru": [...], "en": [...], "bs": [...] },
    "avtomobili": { ... },
    ...per category group
  },
  "features": {
    "kvartiry": { "ru": [10+], "en": [10+], "bs": [10+] },
    ...per category
  },
  "cities": { "ru": [12+ real Montenegro cities], "en": [...], "bs": [...] },
  "item_ages": { "ru": [8+], "en": [8+], "bs": [8+] }
}

Rules:
- Real Montenegro cities only (Podgorica, Budva, Tivat, Bar, Ulcinj, Herceg Novi, Kotor, Cetinje, Nikšić, Danilovgrad, Pljevlja, Bijelo Polje, etc.)
- Brands organized per category group
- Features category-specific
- Bosnian in Latin script

=== PHASE 4: GENERATE PHOTO SEARCH QUERIES ===

Generate search queries for the download_script.py:
- 3-5 Unsplash/Pexels search queries per leaf category
- English queries (best results)
- Landscape orientation preferred (16:9 or 4:3)
- Realistic, well-lit, people-free or unrecognizable people
- For Montenegro-specific categories: add "Montenegro" or "Mediterranean"
- Products on neutral backgrounds
- Vehicles: exterior (front/side/rear) + interior

Output a JSON structure with queries per category, stored in the analysis results from Phase 1.

=== FINAL STEP: REPORT ===

After all phases complete, report:
1. Total templates generated (target: 50+)
2. Categories covered (target: all 24 leaf categories)
3. Word list entry counts per language
4. Photo query counts per category
5. Any categories where Avito was inaccessible and training data was used instead
```

## 12. Definition of Ready

This specification is **ready for implementation planning** when:

- [x] Business problem is clearly stated (placeholder images + flat templates don't represent real classifieds content)
- [x] All requirements are confirmed (10 photo sourcing requirements, 4 manifest requirements, 5 ImageGenerator requirements, 8 template requirements)
- [x] 11 conceptual development tasks are defined with purpose, outcome, and dependencies
- [x] 12 Product Owner decisions are captured (D1-D12)
- [x] Research has been conducted and summarized (7.5 research findings)
- [x] Assumptions, constraints, risks, and out-of-scope items are documented
- [x] LLM task definitions are specified — 3 executable prompts (category analysis, template generation, photo query generation)
- [x] No unresolved business questions remain

**Implementation may begin — no additional business analysis is required.**

---

## Appendix A: Key Files Referenced

| File | Purpose |
|------|---------|
| `src/backend/apps/seed/generators/images.py` | Current ImageGenerator (solid-color JPEGs) |
| `src/backend/apps/seed/generators/ads.py` | Current AdGenerator (flat templates) |
| `src/backend/apps/seed/services/seed_service.py` | SeedService orchestrator with `_clean()` |
| `src/backend/apps/seed/fixtures/ads.json` | 51 flat Russian templates (to be replaced) |
| `src/backend/apps/seed/fixtures/categories.json` | 30 categories with i18n names (source of truth) |
| `src/backend/apps/seed/config/seed.default.json` | Seed configuration |
| `src/backend/apps/media/services/thumbnails.py` | ThumbnailService (unchanged) |
| `src/backend/apps/ads/models.py` | Ad + AdImage models with i18n fields |
| `src/backend/apps/ads/migrations/0004_ad_i18n_columns.py` | Adds title_en, description_en, title_bs, description_bs, original_language |
| `src/backend/apps/core/enums.py` | LanguageLocale, ThumbnailSizeStrEnum |
| `.ai/researches/seed_content_sourcing_research.md` | Full research findings |
| `.ai/problems/02_demo-seed-data_spec.md` | Original seed module specification |
| `.ai/plans/03_demo-seed-data_plan.md` | Original seed module implementation plan |

## Appendix B: Placeholder Variable Reference

| Variable | Type | Source |
|----------|------|--------|
| `{condition}` | adjective | word_lists.json → `conditions.[lang]` |
| `{brand}` | string | word_lists.json → `brands.[lang]` (per category) |
| `{feature}` | string | word_lists.json → `features.[lang]` (per category) |
| `{city}` | string | word_lists.json → `cities.[lang]` |
| `{price}` | integer | Faker `random_int(10, 50000)` |
| `{rooms}` | integer | Faker `random_int(1, 4)` |
| `{area}` | integer | Faker `random_int(30, 150)` (real estate), `random_int(10, 50)` (other) |
| `{item_age}` | string | word_lists.json → `item_ages.[lang]` |
| `{year}` | integer | Faker `random_int(2015, 2024)` |
| `{mileage}` | integer | Faker `random_int(5000, 150000)` (vehicles) |
| `{category}` | string | Category name in appropriate language |
