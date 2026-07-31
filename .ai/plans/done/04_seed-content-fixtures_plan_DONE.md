# Implementation Plan: Seed Content Fixtures

**Plan ID:** `04_seed-content-fixtures_plan`
**Source Spec:** `.ai/problems/03_seed-content-fixtures_spec.md`
**Related Plan:** `.ai/plans/done/03_demo-seed-data_plan_DONE.md`
**Research:** `.ai/researches/seed_content_sourcing_research.md`
**Date:** 2026-07-31
**Status:** Ready for implementation

---

## Execution DAG

```
                     ┌──────────────────────────────────────────────────────────┐
                     │  Parallel Group A — Enablers (no dependencies)           │
                     │                                                          │
                     │  T001: LLM task definition document                       │
                     │  T002: Photo download script                              │
                     └─────────────┬───────────────────────────┬────────────────┘
                                   │                           │
                     (automated)   │          (manual)         │  (code changes)
                                   ▼                           ▼
        ┌──────────────────────────────────┐  ┌──────────────────────────────────┐
        │  Group B — Content Data          │  │  Group C — Python Code Changes  │
        │  (depends on T001, T002)         │  │  (no inter-dependencies)        │
        │                                  │  │                                  │
        │  T003: ads_templates.json +      │  │  T005: ImageGenerator refactor  │
        │        word_lists.json           │  │  T006: AdGenerator refactor     │
        │                                  │  │  T007: SeedService _clean()      │
        │  T004: Bundled photos +          │  │                                  │
        │        photo_manifest.json       │  └───────────┬──────────────────────┘
        └──────────────────────────────────┘              │
                                                          │
                                   ┌──────────────────────┘
                                   ▼
              ┌──────────────────────────────────────────────────┐
              │  Group D — Integration (depends on T005, T006,   │
              │                     T007)                        │
              │                                                  │
              │  T008: Config update + ads.json deprecation     │
              └──────────────────────┬───────────────────────────┘
                                     ▼
              ┌──────────────────────────────────────────────────┐
              │  Group E — Verification (depends on Group D)     │
              │                                                  │
              │  T009: Tests                                     │
              │  T010: Documentation update                      │
              └──────────────────────────────────────────────────┘
```

---

## Execution Order

| Order | Task ID | Title | Parallel Group | Risk Level | Blocked By |
|-------|---------|-------|---------------|------------|------------|
| 1 | T001 | LLM task definition document | A | low | — |
| 1 | T002 | Photo download script | A | low | — |
| 2a | T003 | Generate `ads_templates.json` + `word_lists.json` | B | low | T001 |
| 2b | T004 | Bundle photos + create `photo_manifest.json` | B | medium | T002 |
| 2c | T005 | Refactor `ImageGenerator` for manifest-based photo loading | C | medium | — |
| 2c | T006 | Refactor `AdGenerator` for multi-language template interpolation | C | medium | — |
| 2c | T007 | Update `SeedService._clean()` for seed media directory | C | low | — |
| 3 | T008 | Update config + deprecate old `ads.json` fixture | D | low | T005, T006, T007 |
| 4 | T009 | Write tests for new content generation | E | low | T005, T006, T007 |
| 4 | T010 | Update documentation | E | low | T003, T004, T005, T006 |

---

## Task Specifications

---

### T001: LLM task definition document

**Priority:** high

**Depends on:** none

**Risk:** low — new markdown file only, no production code impact.

**Goals:**
- Create `.ai/llm-tasks/seed-content-generation.md` containing the autonomous LLM workflow prompt
- The document must be a single, runnable prompt that instructs the LLM agent to:
  1. Browse Avito.ru (or fallback sites) to study real ad patterns per category
  2. Analyze patterns and produce structured data for all 24 leaf categories
  3. Generate `ads_templates.json` with 50+ entries covering all categories in ru/bs/en
  4. Generate `word_lists.json` with per-language word lists (10+ entries each)
  5. Generate photo search queries per category for Unsplash/Pexels

**Files:**
- **New:** `.ai/llm-tasks/seed-content-generation.md`

**Affected symbols:**
- None (new document only)

**Acceptance criteria:**
- Document contains a complete autonomous LLM workflow prompt
- All 30 category slugs from `categories.json` are referenced
- Expected output file paths (`src/backend/apps/seed/fixtures/ads_templates.json`, `src/backend/apps/seed/fixtures/word_lists.json`) are explicitly defined
- Output JSON schemas are embedded in the prompt
- Fallback behavior defined (alternative classifieds sites if Avito blocks)
- The prompt includes explicit web browsing instructions

**Implementation notes:**
- Follow the spec Section 11.1 LLM Workflow Prompt structure
- The document must be ready for an LLM to execute autonomously
- Include all phase descriptions (Phase 0-4)
- The document is a static prompt, not executable code

---

### T002: Photo download script

**Priority:** high

**Depends on:** none

**Risk:** low — new standalone script, dev-only tool, no runtime code impact.

**Goals:**
- Create `scripts/download_seed_photos.py` — a standalone Python script
- Script uses Unsplash API (primary) and Pexels API (fallback)
- Queries per category group using photo search queries
- Downloads at `regular` size (1080px)
- Compresses JPEGs with Pillow to ≤100KB
- Strips EXIF data
- Outputs to `src/backend/apps/seed/fixtures/images/` with `{category_slug}_{NN}.jpg` naming
- Generates `photo_manifest.json` with proper schema
- Script supports `--force` re-download flag
- Requires API key via `UNSPLASH_ACCESS_KEY` env var (or `PEXELS_API_KEY` as fallback)

**Files:**
- **New:** `scripts/download_seed_photos.py`

**Affected symbols:**
- None (new top-level script)

**Acceptance criteria:**
- Script runs successfully with a valid API key
- Downloads ≥90 photos across all categories
- All photos ≤100KB after compression
- `photo_manifest.json` generated with correct category mappings
- EXIF data stripped
- Script is idempotent (can be re-run with `--force` flag)
- `requests` is the only external dependency (dev-only)

**Implementation notes:**
- Place in `scripts/` at repository root (outside Django app)
- Use Pillow for JPEG compression: resize to max 800×600, quality=75-80, progressive
- Use `argparse` for CLI args
- Add `scripts/requirements-dev.txt` or mention `pip install requests Pillow`
- Photo search queries per category from spec Section 11.1 Phase 4
- Manifest schema per spec Section 5.2

---

### T003: Generate ads_templates.json + word_lists.json

**Priority:** high

**Depends on:** T001 (LLM prompt must be ready before this manual step)

**Risk:** low — JSON fixture files, no code changes.

**Description:** Run the LLM prompt from T001 to generate two fixture files. This is a manual/automated LLM execution step, not a code commit. The LLM agent browses Avito.ru, analyzes real ad patterns, and produces ready-to-commit JSON files.

**Outcome files:**
- `src/backend/apps/seed/fixtures/ads_templates.json`
  - `version: 2` at root
  - `placeholder_schema` documenting all variables
  - `templates` array with 50+ entries
  - Each template: `id`, `category_slug`, `patterns` (ru/en/bs)
  - Template ID format: `{category_slug}_{purpose}_{NN}`
  - All 30 category slugs from `categories.json` covered
  - 2-3 default fallback templates
  - High-traffic categories: kvartiry(4), avtomobili(4), telefony(3), kompyutery(3), mebel(3), odezhda(3)

- `src/backend/apps/seed/fixtures/word_lists.json`
  - `version: 1` at root
  - `conditions`: per-language (10+ each)
  - `brands`: per category group (elektronika, avtomobili, etc.)
  - `features`: per category (10+ each per language)
  - `cities`: 12+ real Montenegro cities per language
  - `item_ages`: 8+ per language
  - Bosnian in Latin script

**Acceptance criteria:**
- All templates have valid `category_slug` matching `categories.json`
- Every template has `patterns.ru`, `patterns.en`, `patterns.bs`
- Variables in templates are documented in `placeholder_schema`
- Word lists contain ≥10 entries per language per category
- JSON is valid (`json.load()` parses successfully)
- File paths match what `AdGenerator` will read:
  - `src/backend/apps/seed/fixtures/ads_templates.json`
  - `src/backend/apps/seed/fixtures/word_lists.json`

---

### T004: Bundle photos + create photo_manifest.json

**Priority:** high

**Depends on:** T002 (download script + API key + manual curation)

**Risk:** medium — binary files in repo, must manage total size ≤12MB.

**Description:** Run the download script from T002, then manually curate the results. This is a multi-step manual process, not automated code.

**Steps:**
1. Obtain free Unsplash API key (https://unsplash.com/developers)
2. Run `python scripts/download_seed_photos.py` (with `UNSPLASH_ACCESS_KEY` set)
3. Manually review downloaded photos — remove poor-quality or irrelevant ones
4. Verify each category has ≥3 photos (high-traffic categories need 12-16)
5. Run compression if needed: ≤100KB per file, max 1080px long side
6. Strip EXIF data from all photos
7. Generate or update `photo_manifest.json` to match the curated set
8. Verify `photo_manifest.json` entry for every `.jpg` file and vice versa

**Outcome files:**
- `src/backend/apps/seed/fixtures/images/`
  - `photo_manifest.json` — category-to-photo mapping
  - `kvartiry_01.jpg` … `kvartiry_NN.jpg` (apartment photos)
  - `avtomobili_01.jpg` … `avtomobili_NN.jpg` (car photos)
  - Plus all other category photos (~90 files total)
  - `default_01.jpg`, `default_02.jpg` (fallback photos)

**Manifest schema:**
```json
{
  "version": 1,
  "categories": {
    "kvartiry": {
      "photos": [
        {"filename": "kvartiry_01.jpg", "tags": ["interior", "living-room"], "width": 1080, "height": 720},
        ...
      ]
    },
    ...
  },
  "default": {
    "photos": [
      {"filename": "default_01.jpg", "tags": []}
    ]
  }
}
```

**Acceptance criteria:**
- Total directory size ≤12MB
- All 30 categories have ≥3 photos
- Every `.jpg` in directory has a manifest entry
- Every manifest entry points to an existing `.jpg`
- Photos ≤100KB each
- EXIF data stripped from all photos
- Photos are CC0 / equivalent license allowing MIT repo bundling
- Montenegro-specific imagery preferred for real estate/lifestyle categories

---

### T005: Refactor ImageGenerator for manifest-based photo loading

**Priority:** high

**Depends on:** none (code reads well-known file path; manifest format is defined in spec)

**Risk:** medium — modifies existing generator. Removes `_generate_placeholder_jpeg()` and `_get_seed_image_pool()`. `generate()` signature stays unchanged for backward compatibility.

**Module:** `src/backend/apps/seed/generators/images.py`

**Affected classes:**
- `ImageGenerator.__init__` — add `self.photo_pool` and `self.default_pool` attributes
- `ImageGenerator.generate` — load manifest in phase 1, select photos by ad category in phase 2
- `ImageGenerator._ensure_seed_dir` — unchanged (already exists)
- `ImageGenerator._preprocess_images` — update to accept manifest photo pool instead of generated JPEGs

**Affected functions (module-level):**
- `_generate_placeholder_jpeg()` — **remove** (replaced by manifest photos)
- `_get_seed_image_pool()` — **remove** (replaced by manifest loading)

**Semantic insertion points:**

1. **Add new method `_load_manifest()` to `ImageGenerator`:**
   - Insert before `generate()`
   - Read `FIXTURES_DIR / "images" / "photo_manifest.json"`
   - Parse JSON and build `self.photo_pool` (dict: category_slug → photo list) and `self.default_pool`
   - Import `FIXTURES_DIR` from `seed_service.py` (or define locally — prefer local constant to avoid cross-module coupling)

2. **Add new method `_get_photos_for_category(category_slug: str)` to `ImageGenerator`:**
   - Return `self.photo_pool.get(category_slug, self.default_pool) or self.default_pool`
   - Simple dict lookup with fallback

3. **Modify `ImageGenerator.generate()`:**
   - Replace `image_pool = _get_seed_image_pool()` with `_load_manifest()` call
   - Build `image_pool` by iterating over all manifest photos (collect all category pools + default)
   - Pass to `_preprocess_images()` as before
   - In phase 2 (ad image assignment): select photos based on `ad.category.slug` instead of random selection from a single pool
   - For each ad: call `_get_photos_for_category(ad.category.slug)` and pick 1-3 random photos from that pool

4. **Modify `ImageGenerator._preprocess_images()`:**
   - The manifest entries already have `filename` — use it as the storage key instead of `uuid.uuid4()`
   - Storage key format: `seed/{filename}` (e.g., `seed/kvartiry_01.jpg`)
   - Read JPEG bytes from `FIXTURES_DIR / "images" / filename`
   - Generate thumbnails from loaded bytes (ThumbnailService API unchanged per spec 5.7)

5. **Update docstring on `ImageGenerator` class:**
   - Replace "bundled placeholder images" with "bundled category-tagged photos from manifest"

**Dependencies:**
- `photo_manifest.json` must exist at `fixtures/images/photo_manifest.json` (T004)
- Bundled JPEGs must exist at `fixtures/images/` (T004)
- These are data dependencies, not code dependencies — the code can be written and tested once the files exist at the expected paths

**Acceptance criteria:**
- `ImageGenerator` loads manifest and selects category-appropriate photos
- Photos from `photo_manifest.json` are pre-processed once (not per-ad)
- Per-ad photo selection filters by `ad.category.slug` with fallback to default pool
- Thumbnails generated correctly via `ThumbnailService`
- `_generate_placeholder_jpeg()` and `_get_seed_image_pool()` are removed
- `generate()` signature unchanged (backward compatible)
- Deterministic output: same Faker seed + same manifest = same result

---

### T006: Refactor AdGenerator for multi-language template interpolation

**Priority:** high

**Depends on:** none (code reads well-known file paths; data format is defined in spec)

**Risk:** medium — modifies existing generator. Replaces flat template loading with hierarchical, multi-language template interpolation. `generate()` signature stays unchanged.

**Module:** `src/backend/apps/seed/generators/ads.py`

**Affected symbols:**
- `ADS_FIXTURE_PATH` — add new constants: `ADS_TEMPLATES_PATH` and `WORD_LISTS_PATH`
- `AdGenerator.__init__` — add `self.templates` loading from `ads_templates.json` and `self.word_lists` from `word_lists.json`
- `AdGenerator._load_templates` — replace implementation to load `ads_templates.json` hierarchical structure
- `AdGenerator.generate` — update to use category-specific templates, fill all 3 language fields, set `original_language = "ru"`
- `AdGenerator._generate_price` — unchanged (already uses `category.slug`)

**Semantic insertion points:**

1. **Add new constants:**
   ```python
   ADS_TEMPLATES_PATH = Path(__file__).resolve().parent.parent / "fixtures" / "ads_templates.json"
   WORD_LISTS_PATH = Path(__file__).resolve().parent.parent / "fixtures" / "word_lists.json"
   ```

2. **Add new method `_load_word_lists()` to `AdGenerator`:**
   - Read `WORD_LISTS_PATH`
   - Parse JSON and store as `self.word_lists: dict[str, Any]`
   - Provide fallback: empty dicts if file missing

3. **Modify `AdGenerator._load_templates()`:**
   - Read `ADS_TEMPLATES_PATH` instead of `ADS_FIXTURE_PATH`
   - Parse JSON with hierarchical structure: `templates` array with `category_slug`, `patterns.ru/en/bs`
   - Build lookup: `dict[str, list[dict]]` mapping category_slug → list of matching templates
   - Include `"default"` key for fallback templates
   - Return dict instead of flat list (update internal usage accordingly)

4. **Add new method `_fill_template(template: dict, locale: str, category_slug: str) -> str`:**
   - Take a template pattern string and locale
   - Replace `{variable}` placeholders with values from word lists or Faker generators:
     - `{condition}` → `_random_choice(word_lists["conditions"][locale])`
     - `{brand}` → `_random_choice(word_lists["brands"].get(category_group, word_lists["brands"]["default"])[locale])`
     - `{feature}` → `_random_choice(word_lists["features"].get(category_slug, word_lists["features"]["default"])[locale])`
     - `{city}` → `_random_choice(word_lists["cities"][locale])`
     - `{price}` → `_generate_price(category)` (integer, already exists)
     - `{rooms}` → `faker.random_int(1, 4)`
     - `{area}` → `faker.random_int(30, 150)` (real estate) or `faker.random_int(10, 50)` (other)
     - `{item_age}` → `_random_choice(word_lists["item_ages"][locale])`
     - `{year}` → `faker.random_int(2015, 2024)`
     - `{mileage}` → `faker.random_int(5000, 150000)` (vehicles only)
     - `{category}` → `category.get_name(locale)` or fallback to `category.name`

5. **Modify `AdGenerator.generate()`:**
   - In the ad creation loop, select template by `category.slug`:
     ```python
     category_templates = self.templates.get(category.slug, self.templates.get("default", []))
     template = self.faker.random_element(category_templates) if category_templates else fallback
     ```
   - For each ad instance, populate all language fields:
     ```python
     title = self._fill_template(template["patterns"]["ru"]["title"], "ru", category.slug)
     description = self._fill_template(template["patterns"]["ru"]["description"], "ru", category.slug)
     title_en = self._fill_template(template["patterns"]["en"]["title"], "en", category.slug)
     description_en = self._fill_template(template["patterns"]["en"]["description"], "en", category.slug)
     title_bs = self._fill_template(template["patterns"]["bs"]["title"], "bs", category.slug)
     description_bs = self._fill_template(template["patterns"]["bs"]["description"], "bs", category.slug)
     ```
   - Set `original_language = "ru"` on every Ad instance

6. **Update `Ad` instance creation in `generate()`:**
   - Add fields: `title_en`, `description_en`, `title_bs`, `description_bs`, `original_language`

7. **Update `AdGenerator` class docstring:**
   - Replace description to mention multi-language support and variable interpolation

**Acceptance criteria:**
- Generated ads have all 6 language fields populated (`title`, `description`, `title_en`, `description_en`, `title_bs`, `description_bs`)
- `original_language = "ru"` on all generated ads
- `{variable}` placeholders are replaced with word list values or Faker-generated values
- Category-specific templates are selected based on ad category slug
- Fallback to `default` templates for categories without specific templates
- Deterministic: same Faker seed + same templates = same content
- Backward compatible with existing `--status-distribution` CLI flag
- `generate()` signature unchanged

---

### T007: Update SeedService._clean() for seed media directory

**Priority:** high

**Depends on:** none (independent additive change to SeedService)

**Risk:** low — additive method, no existing code removed. No signature changes to `SeedService.run()`.

**Module:** `src/backend/apps/seed/services/seed_service.py`

**Affected symbols:**
- `SeedService._clean()` — add `MEDIA_ROOT/seed/` cleanup
- `SeedService.run()` — no changes required (cleanup already called before generation)

**Semantic insertion points:**

1. **Add import:** `import shutil` at top of module (or inline in method)

2. **Modify `SeedService._clean()`:**
   - After deleting all seed DB records (step 5), add:
     ```python
     # 6. Clean seed media directory
     seed_dir = os.path.join(settings.MEDIA_ROOT, "seed")
     if os.path.exists(seed_dir):
         shutil.rmtree(seed_dir, ignore_errors=True)
         logger.info("Cleaned seed media directory: %s", seed_dir)
     ```
   - Add `import os` if not already present (check current imports)
   - Use `ignore_errors=True` for Windows file lock safety (per spec Section 8 risk mitigation)

3. **Update docstring for `SeedService._clean()`:**
   - Add "and cleans the seed media directory" to the docstring description

**Acceptance criteria:**
- `SeedService._clean()` removes `MEDIA_ROOT/seed/` directory
- Cleanup does not fail on missing directory
- `ignore_errors=True` prevents crash on Windows file locks
- No changes to `SeedService.run()` interface or behavior

---

### T008: Update config + deprecate old ads.json fixture

**Priority:** medium

**Depends on:** T005, T006, T007

**Risk:** low — config file edits and file deprecation/removal.

**Files:**
- `src/backend/apps/seed/config/seed.default.json`
- `src/backend/apps/seed/fixtures/ads.json`
- `src/backend/apps/seed/generators/ads.py`

**Affected symbols:**
- `seed.default.json` — add new config keys for version tracking
- `ads.json` — deprecate or remove
- `AdGenerator._load_templates()` — already updated in T006 to use `ads_templates.json`

**Semantic insertion points:**

1. **Modify `seed.default.json`:**
   - Add optional version tracking keys:
     ```json
     "photo_manifest_version": 1,
     "template_version": 2
     ```
   - These are informational only — generators read files directly, not through config

2. **Deprecate `fixtures/ads.json`:**
   - Option A: Remove the file entirely (preferred — AdGenerator no longer references it after T006)
   - Option B: Rename to `ads.json.deprecated` with a README comment
   - Prefer Option A since AdGenerator path constant is also updated in T006

3. **Verify no remaining references to old `ads.json`:**
   - Search codebase for `"ads.json"` string references
   - Update or remove any remaining references

**Acceptance criteria:**
- Config file has new version keys
- Old `ads.json` is removed or clearly deprecated
- No broken references to old fixture path

---

### T009: Write tests for new content generation

**Priority:** high

**Depends on:** T005, T006, T007 (code changes must be implemented first)

**Risk:** low — additive test code, no production code changes.

**Module:** `src/backend/apps/seed/tests/test_seed.py`

**Affected classes (test):**
- `TestAdGenerator` — add new test methods
- `TestImageGenerator` — add new test methods
- `TestSeedCommand` — add test for media cleanup

**Semantic insertion points:**

1. **Add to `TestImageGenerator`:**
   - `test_photo_manifest_loads` — verify `ImageGenerator._load_manifest()` parses `photo_manifest.json`, covers all photos
   - `test_image_generator_category_selection` — create ads with different categories, verify `ImageGenerator` selects correct photos per category by checking storage keys contain expected prefix
   - `test_image_generator_fallback` — create ad with unknown category slug, verify fallback to default pool
   - `test_image_generator_no_placeholder_generated` — verify `_get_seed_image_pool` is not called (or removed)

2. **Add to `TestAdGenerator`:**
   - `test_template_variables_filled` — generate ads, verify `{condition}`, `{brand}` etc. are replaced (no raw `{` characters in output fields)
   - `test_multi_language_templates` — generate ads, verify `title_en`, `description_en`, `title_bs`, `description_bs` are non-empty strings
   - `test_original_language_set` — verify `original_language = "ru"` on generated ads
   - `test_word_lists_loaded` — verify word lists contain expected keys (conditions, brands, features, cities, item_ages) with entries
   - `test_category_specific_templates` — generate ads with specific categories, verify templates match category slug
   - `test_deterministic_multi_language` — same Faker seed produces same multi-language content
   - `test_fallback_template_for_unknown_category` — unknown category slug uses default templates

3. **Add to `TestSeedCommand`:**
   - `test_media_cleanup` — run seed, verify `MEDIA_ROOT/seed/` is cleaned before re-seed (create a dummy file, re-seed, verify it's gone)
   - `test_seed_with_realistic_photos` — full seed run with 2 users, 3 ads, verify `AdImage` records are created with non-placeholder image keys (keys match `{category_slug}_` format)

**Test dependencies:**
- Tests for `ImageGenerator` require `photo_manifest.json` and bundled JPEGs to exist at fixture paths
- Tests for `AdGenerator` require `ads_templates.json` and `word_lists.json` to exist at fixture paths
- Use `@override_settings(MEDIA_ROOT=...)` for media-related tests

**Acceptance criteria:**
- All new tests pass: `uv run pytest src/backend/apps/seed/tests/`
- Tests are deterministic (same seed = same result)
- Tests verify observable outcomes (field values, photo selection by category, variable filling)
- Existing tests still pass

---

### T010: Update documentation

**Priority:** low

**Depends on:** T003, T004, T005, T006 (content and code must be in place)

**Risk:** low — documentation files only.

**Files:**
- `docs/01-spec/spec-index.md`

**Affected symbols:**
- None (documentation only)

**Semantic insertion points:**

1. **Update `docs/01-spec/spec-index.md`:**
   - Add entry for the new seed content fixtures feature under Phase 2
   - Reference `.ai/problems/03_seed-content-fixtures_spec.md`
   - Note that seed data now includes realistic photos and multi-language templates

**Optional:**
- Ensure `.ai/researches/seed_content_sourcing_research.md` is cross-linked from the spec

**Acceptance criteria:**
- Doc maintenance rules followed (English only, frontmatter, cross-links)
- Documentation reflects the final implementation state

---

## Verification and Testing Strategy

### Per-Task Verification

| Task | Pre-merge verification |
|------|----------------------|
| T001 | Manual review of `.ai/llm-tasks/seed-content-generation.md` |
| T002 | Run script with API key, verify output files and manifest |
| T003 | `python -c "import json; json.load(open('...'))"` for fixture files |
| T004 | Count files (`len(glob('*.jpg'))` == manifest entries), total size |
| T005 | `uv run pytest src/backend/apps/seed/tests/ -k "Image"` |
| T006 | `uv run pytest src/backend/apps/seed/tests/ -k "Ad"` |
| T007 | Manual test: `SeedService()._clean()` removes seed media dir |
| T008 | Verify no broken imports, config loads |
| T009 | `uv run pytest src/backend/apps/seed/tests/` |
| T010 | Visual review of updated doc |

### End-to-End Smoke Test

After all tasks are complete, run:

```bash
uv run python src/backend/manage.py seed --users=5 --ads=20 --force --analytics=False
```

Verify:
- No errors during generation
- Generated ads have populated `title_en`, `description_en`, `title_bs`, `description_bs`
- Generated ads have `original_language = "ru"`
- `AdImage` records reference valid photo keys from manifest
- `title` fields contain no raw `{variable}` placeholders
- Re-running produces the same results (deterministic)

---

## Risk Assessment

| Risk | Task(s) | Impact | Mitigation |
|------|---------|--------|------------|
| Unsplash API rate limit during photo download | T002, T004 | Low | Use smaller batch sizes, Pexels fallback, manual download as backup |
| Git repo size > 15MB from bundled photos | T004 | Medium | Enforce ≤100KB per photo, verify total before committing |
| Manifest out of sync with actual photo files | T004, T005 | Medium | Test: every `.jpg` has manifest entry, vice versa |
| LLM generates malformed JSON for templates | T003 | Medium | Validate JSON with `json.load()` before committing |
| Multi-language content grammatically incorrect | T003, T006 | Medium | LLM prompt instructs natural translation, not word-for-word |
| Template variable not found in word lists | T006 | Low | Log warning and leave placeholder as-is or use empty string |
| Old `ads.json` still referenced elsewhere | T008 | Low | Full codebase search before removal |
| Photo naming convention exceeds 64-char `AdImage.image` field | T005 | High | Use `seed/{category}_{NN}.jpg` format — max ~30 chars |
| `MEDIA_ROOT/seed/` cleanup fails on Windows | T007 | Low | Use `shutil.rmtree(..., ignore_errors=True)` |

---

## Rollback Plan

If any task introduces regressions:

1. **T005 — ImageGenerator:** Revert `images.py` to restore `_generate_placeholder_jpeg()` and `_get_seed_image_pool()`. Keep bundled photos in repo (no-op if not referenced).

2. **T006 — AdGenerator:** Revert `ads.py` to restore old `ads.json` loading. Old `ads.json` fixture (T008) removal means it must be restored from git: `git checkout HEAD -- fixtures/ads.json`.

3. **T007 — SeedService:** Revert `seed_service.py` to restore old `_clean()` without media cleanup.

4. **T008 — Config/fixture removal:** Restore old `ads.json`: `git checkout HEAD -- fixtures/ads.json`.

5. **Data files (T003, T004):** Remove or restore from git — no code impact.