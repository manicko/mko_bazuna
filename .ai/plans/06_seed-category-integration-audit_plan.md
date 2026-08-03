# Seed-Category Integration Audit & Remediation — Implementation Plan

**Plan ID:** `06_seed-category-integration-audit_plan`
**Source Spec:** `.ai/problems/05_seed-category-integration-audit_spec.md`
**Status:** Implementation-ready
**Date:** 2026-08-03

---

## Execution DAG

### Dependency Graph (topological order)

```
                    ┌──────────────────────────────┐
                    │  Group A — Parallel Execution │
                    │  ┌──────┐ ┌──────┐ ┌──────┐  │
                    │  │ T001 │ │ T002 │ │ T003 │  │
                    │  └──┬───┘ └──┬───┘ └────┬─┘  │
                    └─────┼────────┼──────────┼─────┘
                          │        │          │
                    ┌─────┴──┐ ┌──┴──────┐    │
                    │  T004  │ │  T005   │    │
                    └────┬───┘ └─────────┘    │
                         │                    │
                         │            ┌───────┴──────┐
                         │            │    T006       │
                         │            └───────┬───────┘
                         │                    │
                         │            ┌───────┴──────┐
                         │            │    T007       │
                         │            └───────┬───────┘
                         └────────┬───────────┘
                                  │
                          ┌───────┴────────┐
                          │     T008        │
                          └───────┬─────────┘
                                  │
                          ┌───────┴────────┐
                          │     T009        │
                          └─────────────────┘
```

### Parallel Groups

| Group | Tasks | Rationale |
|-------|-------|-----------|
| **Group A** | T001, T002, T003 | Independent: code changes, prompt document, config file — no shared targets |
| **Group B** | T004, T005, T006 | T004 depends on T001 (slug alignment), T005 depends on T001 (reference verification), T006 depends on T002 (prompt needed for generation) |
| **Group C** | T007 | Depends on T003 (pexels config) + T006 (query_hierarchy.json) |
| **Group D** | T008 | Depends on T001 (code), T006 (fixtures), T007 (photos) |
| **Group E** | T009 | Depends on all preceding tasks |

---

## Task Specifications

---

### T001 — Update `AdGenerator` hardcoded slug references

**Priority:** high
**Depends on:** *(none)*
**Risk:** low

**Source reference:** `.ai/problems/05_seed-category-integration-audit_spec.md` — Section 2.6 (A01–A04), Section 5.3

**Description:**
Replace the two hardcoded old-slug references in `AdGenerator` — `CATEGORY_GROUP_MAP` and `_generate_price()` — with mappings keyed to the new English slugs from `categories.yaml`. Remove all old Russian slug references from `ads.py`.

**Affected modules:**
- `apps/seed/generators/ads.py`

**Affected classes:**
- `AdGenerator`

**Affected members:**
- `CATEGORY_GROUP_MAP` (module-level dict, line 25)
- `AdGenerator._generate_price()` (method, line 328)

**Semantic insertion points:**
- Replace `CATEGORY_GROUP_MAP` dict values: old Russian slug keys → new English slug keys from `categories.yaml`
- Replace `_generate_price()` real_estate_slugs and vehicle_slugs sets with new slug values
- Replace `_generate_price()` per-category slug references (`telefony`, `kompyutery`, `foto`) with new equivalents

**Changes:**

1. **`CATEGORY_GROUP_MAP`** — Remap all keys from old Russian slugs to new English slugs from `categories.yaml`. Groups should cover:
   - `real-estate` section → `real_estate` (apartments, houses, rooms, garages, land-plots, commercial-property)
   - `transport` section → `transport` (cars, motorcycles, boats, parts-accessories)
   - `goods` section → `goods` (phones, computers, cameras, home-appliances, furniture, clothing, baby-kids, sports, etc.)
   - `animals` section → `animals` (dogs, cats, birds, fish, other-pets)
   - `services-jobs` section → `services` (construction, beauty, education, legal, vacancies, resumes)
   - `business` section → `business`
   - `charity` section → `charity`
   
   Use sensible defaults for any uncovered leaf slugs (fallback to `default`).

2. **`_generate_price()`** — Update `real_estate_slugs` and `vehicle_slugs` sets to use new English slugs. Update individual slug checks (`telefony` → `phones`, etc.). Maintain the same price range logic structure.

**Acceptance criteria:**
- `CATEGORY_GROUP_MAP` contains entries for all 171 leaf category slugs from `categories.yaml`
- No old Russian slug references remain in `ads.py`
- `_generate_price()` handles all new category groups with appropriate price ranges
- `AdGenerator` creates ads that reference valid Category slugs from the database
- Price ranges match the category group (real estate high, vehicles medium, goods low)

**Verification:**
- `uv run ruff check src/backend/apps/seed/generators/ads.py`
- `uv run basedpyright src/backend/apps/seed/generators/ads.py`
- Visual inspection: grep for old Russian slugs in `ads.py` returns no matches

---

### T002 — Rewrite LLM seed content generation prompt

**Priority:** high
**Depends on:** *(none)*
**Risk:** low

**Source reference:** `.ai/problems/05_seed-category-integration-audit_spec.md` — Section 2.7 (L01–L06), Section 5.2

**Description:**
Rewrite `.ai/llm-tasks/seed-content-generation.md` to reference `categories.yaml` as the canonical category source (not inline slugs), split work into 7 sessions (one per top-level section), include `word_lists.json` as an explicit output, add helper command for extracting leaf slugs, and add a merge + validate phase.

**Affected files:**
- `.ai/llm-tasks/seed-content-generation.md`

**Semantic targets:**
- Entire document rewrite (183 lines → ~300 lines)

**Changes:**

1. Replace the inline 30-slug category list with instructions to read `apps/categories/catalog/categories.yaml` programmatically
2. Add helper command: `python -c "import yaml; data = yaml.load(open('apps/categories/catalog/categories.yaml'), Loader=yaml.SafeLoader); cats = []; [([cats.append(c['slug']) for c in section.get('children', [])]) for section in data['categories']]; print('\n'.join(cats))"`
3. Split generation into 7 sessions (one per top-level section: `real-estate`, `transport`, `goods`, `animals`, `services-jobs`, `business`, `charity`) — each produces partial output files
4. Add `word_lists.json` as explicit Output 3 with full schema specification
5. Add Phase 5 (Merge + Validate) with validation script that checks: all 171 leaf categories covered, all slugs valid, no duplicate template IDs, JSON parseable, all 3 languages populated per template
6. Preserve the 4 default templates as fallback

**Output schema additions:**
- `word_lists.json` schema with `brands` (keyed by top-level section slugs), `features` (keyed by leaf slug), `conditions`, `cities`, `item_ages`

**Acceptance criteria:**
- Prompt is self-contained — LLM agent can execute it without human intervention
- No inline category slugs in the prompt (references `categories.yaml` only)
- Output schemas match the actual code expectations in `AdGenerator`
- Helper command for leaf slug extraction is present

---

### T003 — Bump `pexels_safe_limit` in seed-images-config.json

**Priority:** medium
**Depends on:** *(none)*
**Risk:** low

**Source reference:** `.ai/problems/05_seed-category-integration-audit_spec.md` — Section 5.1, Section 8 (Rate limit mitigation)

**Description:**
Update `pexels_safe_limit` in `scripts/seed-images-config.json` from 150 to a value sufficient for downloading photos for all target categories. The limit must accommodate the chosen photo count strategy (180 photos for ~60 categories or 513+ for 171 categories).

**Affected files:**
- `scripts/seed-images-config.json`

**Semantic targets:**
- Key `pexels_safe_limit` in JSON root

**Changes:**
- Change `pexels_safe_limit` from `150` to `800` (safe for 60 categories × 3 photos × ~3 req/photo) or `2200` (for 171 categories × 3 photos)
- Decision pending from open question Q1 — set to `800` as minimum safe value

**Acceptance criteria:**
- `download_seed_photos.py` runs without hitting the safe limit cap

---

### T004 — Update test data to use new category slugs

**Priority:** high
**Depends on:** `T001` (CATEGORY_GROUP_MAP must use new slugs for tests to pass)
**Risk:** low

**Source reference:** `.ai/problems/05_seed-category-integration-audit_spec.md` — Section 2.8 (S01), Section 5.4

**Description:**
Update all test data in `test_seed.py` that uses old Russian category slugs to use new English slugs from `categories.yaml`. This covers test setup data, manifest test data, and any slug assertions.

**Affected files:**
- `apps/seed/tests/test_seed.py`

**Affected classes:**
- `TestAdGenerator.setUpTestData` — `cat_data` list (lines 143-150)
- `TestImageGeneratorManifest._create_patch` — manifest data (lines 512-552)
- `TestImageGeneratorManifest.test_get_photos_for_category` — photo pool keys (lines 582-593)
- `TestAdGeneratorMultiLang.test_template_variables_filled` — category slug (line 684)
- `TestAdGeneratorMultiLang.test_generated_ads_have_multi_language_fields` — category slug (line 711)

**Changes:**

1. `TestAdGenerator.setUpTestData` — Replace old slugs:
   - `"nedvizhimost"` → real estate section slug (e.g., `"real-estate"` or a leaf slug)
   - `"avtomobili"` → `"cars"`
   - `"elektronika"` → electronics section slug (e.g., `"goods"` or `"phones"`)

2. `TestImageGeneratorManifest._create_patch` — Replace keys:
   - `"kvartiry"` → `"apartments"`
   - `"avtomobili"` → `"cars"`
   - Update corresponding filename references (e.g., `"kvartiry_01.jpg"` → `"apartments_01.jpg"`)

3. `TestImageGeneratorManifest.test_get_photos_for_category` — Replace slug keys to match new manifest structure

4. `TestAdGeneratorMultiLang.test_template_variables_filled` — Replace slug `"telefony"` with new equivalent

5. `TestAdGeneratorMultiLang.test_generated_ads_have_multi_language_fields` — Replace slug `"telefony"` with new equivalent

**Acceptance criteria:**
- All test categories use slugs that exist in `categories.yaml`
- All tests pass: `uv run pytest src/backend/apps/seed/tests/`

---

### T005 — Remove dead code and orphan files

**Priority:** medium
**Depends on:** `T001` (confirm no code references old fixtures)
**Risk:** medium — file deletions, git-tracked files

**Source reference:** `.ai/problems/05_seed-category-integration-audit_spec.md` — Section 2.9 (D01–D04), Section 5.5

**Description:**
Delete orphaned files and dead code artifacts that are no longer referenced after the category system migration. All deletions must be done via `git rm` to track removal history.

**Affected files:**
- `apps/seed/fixtures/categories.json` — delete
- `apps/seed/fixtures/images/*.jpg` — delete (28 orphaned old-slug JPEGs)
- `apps/seed/images/` — verify existence, delete if present

**Pre-deletion verification:**
- `grep -r "categories.json" src/backend/apps/seed/` — must return no references
- `grep -r "kvartiry\|avtomobili\|telefony\|elektronika" src/backend/apps/seed/` — only test data and manifest entries (confirmed by T001 and T004 that these are gone)
- Verify `query_hierarchy.json` key slugs match new system (will be regenerated in T006)

**Changes:**

1. Verify no code references to `categories.json`:
   ```bash
   grep -r "categories.json" src/backend/apps/seed/ --include="*.py"
   ```

2. Delete orphaned fixture:
   ```bash
   git rm src/backend/apps/seed/fixtures/categories.json
   ```

3. Delete old slug-named JPEGs:
   ```bash
   git rm src/backend/apps/seed/fixtures/images/*.jpg
   ```

4. Check and clean `seed/images/` directory if it exists as a separate directory

5. Verify `seed/config/seed.default.json` is kept (confirmed in-use by Section 5.5)

**Acceptance criteria:**
- `categories.json` no longer exists in the seed fixtures directory
- No old-slug JPEGs remain in `fixtures/images/`
- `seed/images/` directory is clean (doesn't exist or is empty)
- `seed/config/seed.default.json` is preserved
- No broken imports after removal

---

### T006 — Regenerate LLM content fixtures (data generation)

**Priority:** high
**Depends on:** `T002` (updated prompt)
**Risk:** low — data-only, git-tracked, re-runnable

**Source reference:** `.ai/problems/05_seed-category-integration-audit_spec.md` — Section 2.4 (T01–T06), Section 2.5 (W01–W04), Section 2.3 (Q01–Q04)

**Description:**
Execute the updated LLM prompt (T002) in 7 sessions (one per top-level section) via the LLM agent. Each session produces partial output files for `ads_templates.json`, `query_hierarchy.json`, and `word_lists.json`. Merge all partial files into the final fixture files.

**This is a data generation task**, not a code change. The implementor executes the LLM generation workflow, not source edits.

**Affected files (generated, not edited):**
- `apps/seed/fixtures/ads_templates.json` — regenerated
- `apps/seed/fixtures/word_lists.json` — regenerated
- `apps/seed/fixtures/images/query_hierarchy.json` — regenerated

**Process:**

1. Read `.ai/llm-tasks/seed-content-generation.md` (as updated by T002)
2. Execute 7 LLM sessions (one per top-level section), producing:
   - `ads_templates.{section}.json` — one per session
   - `query_hierarchy.{section}.json` — one per session
   - `word_lists.{section}.json` — one per session
3. Merge section files into final files:
   - `ads_templates.json` — combine all template arrays + 4 default templates
   - `query_hierarchy.json` — merge all category entries into single root key
   - `word_lists.json` — merge brand groups, features, conditions, cities, item_ages
4. Run validation:
   - All slugs in output files match `categories.yaml` slugs
   - No duplicate template IDs
   - All 171 leaf categories have ≥2 templates
   - All 3 languages (ru, en, bs) populated per template
   - JSON is parseable
   - `query_hierarchy.json` has 171 entries with valid search query arrays
   - `word_lists.json` brand groups match top-level section slugs from `categories.yaml`

**Acceptance criteria:**
- 342+ templates across all 171 leaf categories (2+ per leaf)
- 4 default/fallback templates preserved
- All slugs in all output files are valid `categories.yaml` slugs
- `query_hierarchy.json` has complete entries (objects, contexts, styles) for all leaf slugs
- `word_lists.json` has brands (keyed by section slug), features (keyed by leaf slug), conditions/cities/item_ages (per language)
- JSON files parseable and valid

---

### T007 — Download fresh photos and populate manifest (data generation)

**Priority:** high
**Depends on:** `T003` (pexels config), `T006` (query_hierarchy.json)
**Risk:** low — data-only, re-runnable, network-dependent

**Source reference:** `.ai/problems/05_seed-category-integration-audit_spec.md` — Section 2.2 (P01–P05), Section 5.1

**Description:**
Run `scripts/download_seed_photos.py` with the regenerated `query_hierarchy.json` to download fresh CC0 photos for all new category slugs. The script auto-populates `photo_manifest.json` — no manual editing needed.

**Process:**

1. Ensure `scripts/seed-images-config.json` has updated `pexels_safe_limit` (T003)
2. Verify `scripts/download_seed_photos.py` is slug-agnostic (confirmed per Section 5.1)
3. Run: `python scripts/download_seed_photos.py --all`
4. Monitor output for:
   - Rate limit issues (consider enabling Unsplash as fallback if needed)
   - File size compliance (≤100KB per photo, per constraint 8)
5. Verify `apps/seed/fixtures/images/photo_manifest.json` is populated
6. If API limits prevent full download, run multiple passes

**No code changes to the download script** — only `query_hierarchy.json` input and `pexels_safe_limit` config drive the behavior.

**Acceptance criteria:**
- All old JPEGs deleted (from T005)
- New JPEGs downloaded with new-slug filenames (e.g., `apartments_01.jpg`)
- `photo_manifest.json` has entries for all downloaded photos
- `ImageGenerator.generate()` loads the manifest and produces `AdImage` records
- All photos ≤100KB, EXIF stripped, JPEG format, max 1080px on long side

---

### T008 — Add integration test for full seed pipeline (validation task)

**Priority:** medium
**Depends on:** `T001` (code), `T006` (fixtures), `T007` (photos)
**Risk:** low

**Source reference:** `.ai/problems/05_seed-category-integration-audit_spec.md` — Section 2.8 (S02–S03)

**Description:**
Add an integration test to `test_seed.py` that verifies the end-to-end seed workflow with the new category system: categories load via builder, ads reference valid slugs, photos load from manifest, and the full seed command produces valid data.

**Affected files:**
- `apps/seed/tests/test_seed.py`

**Affected classes:**
- `TestSeedCommand` — add new test method(s)

**Changes:**

Add integration test(s) to `TestSeedCommand` (or create a new `TestSeedCategoryIntegration` class) that verifies:

1. **Category loading via builder:** Call the builder's `load_catalog()` to load categories from `categories.yaml`, verify slugs match expected set
2. **Ad generation with valid slugs:** Run `AdGenerator` with categories loaded via builder, verify all created ads have category slugs present in the database
3. **Photo manifest loading:** Verify `ImageGenerator` loads the manifest and produces `AdImage` records with correct category slug associations
4. **Full seed command:** Run `call_command("seed", ...)` with `--force` and verify end-to-end data integrity

**Acceptance criteria:**
- New test(s) pass deterministically
- Integration test covers: builder → categories → ads → photos → data integrity
- `uv run pytest src/backend/apps/seed/tests/` passes with all tests (existing + new)

---

### T009 — Write seed workflow documentation

**Priority:** medium
**Depends on:** `T001`, `T002`, `T003`, `T004`, `T005`, `T006`, `T007`, `T008` (all tasks complete)
**Risk:** low

**Source reference:** `.ai/problems/05_seed-category-integration-audit_spec.md` — Section 2.10 (M01–M04)

**Description:**
Create/update documentation covering the complete seed data workflow: category loading, user generation, ad generation, photo download, content generation, and analytics seeding. Include instructions for running scripts, API key setup, and LLM content generation.

**Affected files:**
- New: `docs/seed-workflow.md` (or similar)
- Update: `docs/01-spec/spec-index.md`

**Content to cover:**

1. **Full seed workflow** (categories → users → ads → photos → analytics):
   - Order of operations
   - Configuration options
   - Expected output

2. **Photo download instructions:**
   - API keys: Pexels (required), Unsplash (optional fallback)
   - `scripts/seed-images-config.json` configuration guide
   - Rate limits and multi-pass strategy
   - Running: `python scripts/download_seed_photos.py --all`

3. **LLM content fixture regeneration:**
   - Reference to `.ai/llm-tasks/seed-content-generation.md`
   - 7-session workflow explanation
   - Merge + validate procedure
   - File output locations

4. **Update `docs/01-spec/spec-index.md`:**
   - Add reference to this spec (`05_seed-category-integration-audit_spec.md`)

**Acceptance criteria:**
- Developer can reproduce all seed content from scratch using the docs
- All documentation in English (project rule 1)
- API key requirements are documented
- Rate limit expectations are documented (180+ photos, 5-25 minutes)

---

## Order Template

```yaml
tasks:
  - id: task_001
    depends_on: []              # AdGenerator code — CATEGORY_GROUP_MAP + _generate_price

  - id: task_002
    depends_on: []              # LLM prompt rewrite

  - id: task_003
    depends_on: []              # pexels_safe_limit config

  - id: task_004
    depends_on:
      - task_001               # Test data — needs new slug alignment

  - id: task_005
    depends_on:
      - task_001               # Dead code — needs reference verification

  - id: task_006
    depends_on:
      - task_002               # LLM content gen — needs updated prompt

  - id: task_007
    depends_on:
      - task_003               # Photo download — needs pexels config
      - task_006               # Photo download — needs query_hierarchy.json

  - id: task_008
    depends_on:
      - task_001               # Integration test — needs code
      - task_006               # Integration test — needs fixtures
      - task_007               # Integration test — needs photos

  - id: task_009
    depends_on:
      - task_001               # Documentation — all preceding
      - task_002
      - task_003
      - task_004
      - task_005
      - task_006
      - task_007
      - task_008
```

---

## Risk Assessment

| Task | Risk Level | Risk Type | Mitigation |
|------|-----------|-----------|------------|
| T001 | Low | Code change — well-scoped, no public API change | Existing tests verify behavior; grep for old slugs post-change |
| T002 | Low | Document only, no code impact | Reviewable as markdown diff |
| T003 | Low | Single config value change | Verify by running download script |
| T004 | Low | Test data only, no production impact | Run tests to verify |
| T005 | **Medium** | File deletion from git | Pre-deletion grep verification; git tracks history for recovery |
| T006 | Low | Data-only, backed by git | Re-runnable; validation script catches issues |
| T007 | Low | Data-only, re-runnable | Network-dependent but recoverable; multiple passes if rate-limited |
| T008 | Low | Test addition only | No production code changes |
| T009 | Low | Documentation only | No code impact |

### No research gates required

All implementation approaches are determined by the spec:
- `CATEGORY_GROUP_MAP` structure is determined by `categories.yaml` top-level sections
- `_generate_price()` logic structure is preserved (only slugs change)
- Download script is slug-agnostic (confirmed per Section 5.1)
- LLM prompt references YAML with helper command (specified per Section 2.7)
- All fixture formats are already defined by existing code

---

## Verification Summary

| Task | Verification Command |
|------|---------------------|
| T001 | `uv run ruff check src/backend/apps/seed/generators/ads.py` |
| T001 | `uv run basedpyright src/backend/apps/seed/generators/ads.py` |
| T001 | `grep -r "kvartiry\|avtomobili\|telefony\|elektronika\|bytovaya\|foto\|mototsikly\|vodnyy\|zapchasti\|doma\|kommercheskaya\|uchastki" src/backend/apps/seed/generators/ads.py` |
| T004 | `uv run pytest src/backend/apps/seed/tests/ -x` |
| T005 | `grep -r "categories.json" src/` — verify no imports broken |
| T006 | Python validation: all slugs valid, no duplicate IDs, JSON parseable |
| T007 | Verify `photo_manifest.json` has entries; `ls apps/seed/fixtures/images/*.jpg` > 0 |
| T008 | `uv run pytest src/backend/apps/seed/tests/ -x -v` |
| T009 | Manual review of documentation |