# Implementation Plan: Demo/Seed Data Module

**Plan ID:** `03_demo-seed-data_plan`
**Source Spec:** `.ai/problems/02_demo-seed-data_spec.md`
**Date:** 2026-07-31
**Status:** Ready for implementation

---

## Execution DAG

```
                   ┌─────────────────────────────────────────────┐
                   │  Parallel Group A (no deps)                  │
                   │                                             │
                   │  T001: Add enum values to core/enums.py     │
                   │  T002: Create apps/seed app skeleton        │
                   └──────────────────┬──────────────────────────┘
                                      │
                   ┌──────────────────┴──────────────────────────┐
                   │  Parallel Group B (depends on Group A)       │
                   │                                             │
                   │  T003: Config file + BaseGenerator          │
                   │  T004: Category and city fixture JSON       │
                   └──────────────────┬──────────────────────────┘
                                      │
                   ┌──────────────────┴──────────────────────────┐
                   │  Serial Group C                             │
                   │                                             │
                   │  T005: Build UserGenerator                  │
                   │         │                                   │
                   │  T006: Build AdGenerator                    │
                   └──────────────────┬──────────────────────────┘
                                      │
                   ┌──────────────────┴──────────────────────────────────┐
                   │  Parallel Group D (depends on T006)                  │
                   │                                                      │
                   │  T007: Research ThumbnailService API (prerequisite)  │
                   │         └── blocks ──► T008: Build ImageGenerator    │
                   │                                                      │
                   │  T009: Build AnalyticsGenerator                      │
                   └──────────────────┬───────────────────────────────────┘
                                      │
                   ┌──────────────────┴──────────────────────────┐
                   │  Serial Group E (depends on T005, T006,     │
                   │                     T008, T009)             │
                   │                                             │
                   │  T010: Build SeedService orchestrator       │
                   │         │                                   │
                   │  T011: Build management command seed.py     │
                   └──────────────────┬──────────────────────────┘
                                      │
                   ┌──────────────────┴──────────────────────────┐
                   │  Parallel Group F (depends on T010, T011)    │
                   │                                             │
                   │  T012: Docker Compose integration           │
                   │  T013: Tests for seed module                 │
                   └─────────────────────────────────────────────┘
```

---

## Execution Order

| Order | Task ID | Title | Parallel Group | Risk Level | Blocked By |
|-------|---------|-------|---------------|------------|------------|
| 1 | T001 | Add `AdSource.SEED` and `AdvisoryLockId.SEED` to enums | A | low | — |
| 1 | T002 | Create `apps/seed` app skeleton and register | A | low | — |
| 2a | T003 | Create `seed.default.yaml` config and `BaseGenerator` | B | low | T002 |
| 2b | T004 | Create fixture JSON files for categories and cities | B | low | T002 |
| 3 | T005 | Build `UserGenerator` | C | low | T003 |
| 4 | T006 | Build `AdGenerator` | C | medium | T004, T005 |
| 5 | T007 | **Research**: ThumbnailService API for seed image flow | D | medium | T006 |
| 5 | T009 | Build `AnalyticsGenerator` | D | low | T006 |
| 6 | T008 | Build `ImageGenerator` | D | high | T006, **T007** |
| 7 | T010 | Build `SeedService` orchestrator | E | medium | T005, T006, T008, T009 |
| 8 | T011 | Build management command `seed.py` | E | low | T010 |
| 9 | T012 | Docker Compose integration | F | medium | T011 |
| 9 | T013 | Tests for seed module | F | low | T011 |

---

## Task Specifications

---

### T001: Add `AdSource.SEED` and `AdvisoryLockId.SEED` to core enums

**Priority:** high

**Depends on:** none

**Risk:** low — purely additive changes to existing StrEnum/IntEnum. No downstream code currently references these values.

**Goals:**
- Add `AdSource.SEED = "seed"` to `apps/core/enums.py`
- Add `AdvisoryLockId.SEED = 110` to `apps/core/enums.py`
- Update `__all__` if needed (automatically exported via import)

**Files:**
- `src/backend/apps/core/enums.py`

**Targets:**
- Class `AdSource` — add member `SEED`
- Class `AdvisoryLockId` — add member `SEED`

**Acceptance criteria:**
- `AdSource.SEED` resolves to `"seed"`
- `AdvisoryLockId.SEED` resolves to `110`
- No import errors in existing code
- All existing tests pass: `uv run pytest src/backend/`

---

### T002: Create `apps/seed` app skeleton and register in INSTALLED_APPS

**Priority:** high

**Depends on:** none

**Risk:** low — zero-model app, no migration impact. Adding to `INSTALLED_APPS` follows existing pattern for all other apps.

**Goals:**
- Create directory tree under `src/backend/apps/seed/`
- Create `SeedConfig` app config with `name = "apps.seed"`
- Add `"apps.seed"` to `INSTALLED_APPS` in `src/backend/config/settings/base.py`

**Files:**
- `src/backend/apps/seed/__init__.py` — empty
- `src/backend/apps/seed/apps.py` — `SeedConfig(AppConfig)` with `name = "apps.seed"`
- `src/backend/apps/seed/management/__init__.py` — empty
- `src/backend/apps/seed/management/commands/__init__.py` — empty
- `src/backend/apps/seed/generators/__init__.py` — empty
- `src/backend/apps/seed/services/__init__.py` — empty
- `src/backend/apps/seed/config/` — empty directory
- `src/backend/apps/seed/fixtures/` — empty directory
- `src/backend/apps/seed/tests/` — empty directory
- `src/backend/apps/seed/tests/__init__.py` — empty
- `src/backend/config/settings/base.py` — add `"apps.seed"` to `INSTALLED_APPS` list

**Targets:**
- New module: `apps.seed`
- Function: `settings/base.py::INSTALLED_APPS` — append `"apps.seed"`

**Semantic anchors:**
- Insert `"apps.seed"` after `"apps.analytics"` in `INSTALLED_APPS` list (last local app entry)

**Acceptance criteria:**
- `uv run python src/backend/manage.py check` passes with no errors
- App is discoverable: `SeedConfig` loads without ImportError
- No migrations exist (zero models)

---

### T003: Create `seed.default.yaml` config and `BaseGenerator`

**Priority:** high

**Depends on:** T002

**Risk:** low — new files, no existing code modified.

**Goals:**
- Create `config/seed.default.yaml` with tunable parameters
- Create `generators/base.py` with `BaseGenerator` providing shared Faker instance, helpers

**Files:**
- `src/backend/apps/seed/config/seed.default.yaml`
- `src/backend/apps/seed/generators/base.py`

**Targets:**
- New class: `BaseGenerator`
- New data file: `seed.default.yaml`

**Detailed requirements:**

`seed.default.yaml`:
```yaml
faker_seed: 42
chunk_size: 10000
status_distribution:
  published: 0.60
  archived: 0.20
  draft: 0.10
  on_moderation: 0.05
  rejected: 0.05
image_count:
  min: 1
  max: 3
analytics:
  days_back: 90
  views_per_ad_per_day:
    min: 0
    max: 15
```

`generators/base.py` design:
- `BaseGenerator` is an abstract base
- `__init__(self, config: dict)` — receives parsed config dict
- `self.faker: Faker` — instance with `ru_RU` locale, seeded with `config["faker_seed"]`
- Helper: `self._random_choice(options, weights)` — weighted random selection
- Helper: `self._random_date(start, end)` — random datetime between two dates
- Helper: `self._chunked(items, size)` — generator yielding chunks of items
- No abstract methods — generators are composed, not inherited

**Acceptance criteria:**
- `BaseGenerator` can be instantiated with a config dict
- Faker produces deterministic output with seed=42
- Helper methods work correctly
- YAML file is parseable by `yaml.safe_load()`

---

### T004: Create fixture JSON files for categories and cities

**Priority:** high

**Depends on:** T002

**Risk:** low — static data files only.

**Goals:**
- Create `fixtures/categories.json` with real Montenegro classifieds category tree
- Create `fixtures/cities.json` with real Montenegro cities

**Files:**
- `src/backend/apps/seed/fixtures/categories.json`
- `src/backend/apps/seed/fixtures/cities.json`

**Targets:**
- New fixture data files

**Detailed requirements:**

`categories.json`:
- django-mptt compatible structure with `pk` as integer PK
- Fields: `pk`, `name` (Russian), `slug`, `is_active`, `parent` (null or parent pk)
- Real Montenegro classifieds categories (real estate, vehicles, electronics, services, jobs, pets, etc.)
- Tree depth of 2-3 levels (parent → child → subcategory)
- At least 20-30 total categories
- No `lft`, `rght`, `tree_id`, `level` — MPTT handles these on `rebuild()`

`cities.json`:
- Fields: `pk`, `name` (Russian), `slug`, `region`, `country_code` (`"ME"`)
- Real Montenegro cities: Podgorica, Nikšić, Bar, Kotor, Budva, Tivat, Herceg Novi, Cetinje, Bijelo Polje, Pljevlja, Rožaje, Berane, Ulcinj, etc.
- At least 15 cities
- Each city has a `region` (e.g., "Central Montenegro", "Coastal Montenegro", "Northern Montenegro")

**Acceptance criteria:**
- Both JSON files load via `django.core.serializers.deserialize('json', ...)` without errors
- Category fixture includes proper `parent` references by integer `pk`
- `Category.objects.rebuild()` succeeds after loading categories
- Cities have correct `country_code = "ME"`

---

### T005: Build `UserGenerator`

**Priority:** high

**Depends on:** T003

**Risk:** low — new generator class, no existing code affected.

**Goals:**
- Generate N fake seller `User` instances using `bulk_create`
- Use `itertools.count()` for unique `telegram_id` and `chat_id`
- 30% probability of non-null `username`

**Files:**
- `src/backend/apps/seed/generators/users.py`

**Targets:**
- New class: `UserGenerator(BaseGenerator)`

**Design:**
```python
class UserGenerator(BaseGenerator):
    def generate(self, count: int) -> list[User]:
        # Uses itertools.count(start=10000) for telegram_id
        # Optional username via Faker (30% chance)
        # All users: is_active=True, is_banned=False, consent_given=True
        # Supports chunked iteration for large counts
```

**Detailed requirements:**
- `generate(self, count)` returns list of unsaved `User` instances (not yet `bulk_create`'d)
- `telegram_id`, `chat_id` from `itertools.count(start=10_000)` — guaranteed unique, no Faker retry limit
- `username`: 30% probability via Faker `user_name()`, otherwise `None`
- `first_name`/`last_name` via Faker `first_name()` / `last_name()` (Russian locale)
- `is_active=True`, `is_banned=False`, `consent_given=True`
- `password` set to unusable (dummy users can't login)
- `yield_chunks(self, count, chunk_size)` for memory-safe iteration at scale
- Does NOT save to DB — caller decides chunking

**Acceptance criteria:**
- Generates exactly `count` users
- All `telegram_id` values are unique
- Deterministic output with same Faker seed
- ~30% of users have non-null `username`

---

### T006: Build `AdGenerator`

**Priority:** high

**Depends on:** T003, T004, T005

**Risk:** medium — references multiple FK entities; must handle status distribution correctly. Bypasses `transition_to()` by setting fields directly.

**Goals:**
- Generate M ad instances referencing existing users, categories, cities
- Apply status distribution from config
- Read title/description templates from fixture file
- Support chunked generation

**Files:**
- `src/backend/apps/seed/generators/ads.py`
- `src/backend/apps/seed/fixtures/ads.json`

**Targets:**
- New class: `AdGenerator(BaseGenerator)`
- New fixture: `ads.json`

**Detailed requirements:**

`fixtures/ads.json`:
- Array of template objects: `{"title": "...", "description": "..."}`
- At least 50 templates with realistic Russian classifieds content
- Mix of categories: real estate, cars, electronics, services, jobs, pets, furniture, clothing
- Titles 30-80 chars, descriptions 100-500 chars
- Use `{category}` placeholder for category name insertion

`AdGenerator`:
- Constructor receives lists of existing `User`, `Category`, `City` objects
- `generate(ad_count, status_weights)` returns `list[Ad]`
- Picks random user/category/city for each ad
- Picks random template from `ads.json`, replaces `{category}` with category name
- Generates price via Faker `random_int(10, 50000)` for most categories (higher for real estate)
- Sets status via weighted random from `status_weights`
- Sets timestamps consistent with status:
  - `PUBLISHED`: `published_at` = random date in past 60 days
  - `ARCHIVED`: `published_at` = 61-90 days ago, `archived_at` = now-30
  - `DRAFT`: no published_at
  - `ON_MODERATION`: `published_at` = now
  - `REJECTED`: as ON_MODERATION
- Sets `source = AdSource.SEED`
- Does NOT call `transition_to()` — sets status field directly
- Does NOT save — `bulk_create` is called by orchestrator

**Acceptance criteria:**
- Generates exactly `ad_count` ads
- Status distribution approximates the weights (±5%)
- All FK references point to existing objects
- Deterministic output
- No `transition_to()` called (verified by code review)
- Price ranges are reasonable per category type

---

### T007: Research ThumbnailService API for seed image flow

**Priority:** medium

**Depends on:** T006

**Risk:** medium — the existing `ThumbnailService.generate_thumbnails()` uses `O_EXCL` atomic writes and writes to a `storage_dir`. The seed flow must understand:
1. How original image files should be stored (key format, directory)
2. Whether ThumbnailService can be called in batch without conflicts
3. How `AdImage` model stores image references

**Blocked By:** none (this is a research task)
**Blocks:** T008 (ImageGenerator)

**Goals:**
- Verify ThumbnailService API compatibility with seed workflow
- Determine image storage key format
- Determine if `O_EXCL` prevents re-running seed images
- Document findings for T008

**Files to study (read-only, no edits):**
- `src/backend/apps/media/services/thumbnails.py`
- `src/backend/apps/ads/models.py` — `AdImage` model fields
- `src/backend/apps/core/enums.py` — `ThumbnailSizeStrEnum`
- `src/backend/apps/analytics/models.py` — if referenced

**Questions to answer:**
1. Can `ThumbnailService.generate_thumbnails()` be called repeatedly for the same file? (O_EXCL issue — must delete before re-seed)
2. What is the expected key format for original images in MEDIA_ROOT?
3. Does `AdImage.image` store a full path or just filename key?
4. What is the storage directory path relative to MEDIA_ROOT?
5. Should seed images use a `seed/` subdirectory for hygiene?

**Expected output:** Research document OR inline findings in the implementation specifications for T008.

**Acceptance criteria:**
- All questions answered
- Clear Go/Go-with-changes recommendation for T008

---

### T008: Build `ImageGenerator`

**Priority:** high

**Depends on:** T006, T007

**Risk:** high — blocked until T007 research confirms ThumbnailService API. Misunderstanding the API would cause runtime failures.

**Goals:**
- Bundle 5-10 royalty-free JPEGs in `fixtures/images/`
- Pre-process images: copy to MEDIA_ROOT, generate thumbnails via ThumbnailService
- Create `AdImage` records referencing generated images, shared across ads

**Files:**
- `src/backend/apps/seed/fixtures/images/` — 5-10 JPEG files (<100KB each)
- `src/backend/apps/seed/generators/images.py`

**Targets:**
- New class: `ImageGenerator(BaseGenerator)`
- New directory: `fixtures/images/` with bundled JPEGs

**Detailed requirements:**

`ImageGenerator`:
- Constructor takes list of `Ad` objects (must exist in DB for FK)
- `generate()` returns `list[AdImage]` ready for `bulk_create`
- **Phase 1 — Pre-process:**
  1. Iterate fixture images in `fixtures/images/`
  2. For each: read bytes, generate UUID key `{uuid}.jpg`
  3. Write original to `MEDIA_ROOT/seed/{uuid}.jpg`
  4. Call `ThumbnailService.generate_thumbnails(photo_bytes, f"{uuid}.jpg")` — writes thumbnails
  5. Build record of available image keys (original + 3 thumbnail keys per image)
- **Phase 2 — Assign to ads:**
  1. For each ad: select 1-3 random images from pool
  2. Create `AdImage` with proper `ad` FK, `position` ordering (1, 2, 3)
  3. Set `image`, `thumbnail_small`, `thumbnail_medium`, `thumbnail_large` fields to generated keys
  4. Images are shared across ads (same pool for all ads — acceptable for demo)
- `MEDIA_ROOT/seed/` subdirectory for hygiene per spec section 5.4

**Acceptance criteria:**
- All fixture images are pre-processed once (not per-ad)
- Each ad gets 1-3 `AdImage` records with correct positions
- Thumbnail files exist on disk after generation
- Re-running seed cleans up media files before re-generation
- Deterministic (same images assigned to same ad positions with same seed)

---

### T009: Build `AnalyticsGenerator`

**Priority:** high

**Depends on:** T006

**Risk:** low — new generator, no complex dependencies beyond existing Ad records and AnalyticsEvent model.

**Goals:**
- Generate fake `AnalyticsEvent` records with `AD_VIEWED` type
- Optionally generate `DailyAdMetrics` rollup records
- Spread events over 90 days with recent-biased distribution
- Respect `--analytics` flag

**Files:**
- `src/backend/apps/seed/generators/analytics.py`

**Targets:**
- New class: `AnalyticsGenerator(BaseGenerator)`

**Detailed requirements:**

```python
class AnalyticsGenerator(BaseGenerator):
    def __init__(self, config, ads: list[Ad]):
        super().__init__(config)
        self.ads = ads

    def generate_events(self) -> list[AnalyticsEvent]:
        # For each ad: 0-15 views per day over 90 days (biasing recent)
        # Returns list ready for bulk_create

    def generate_daily_metrics(self) -> list[DailyAdMetrics]:
        # Rollup per ad per day
        # bulk_create with ignore_conflicts=True
```

- Events spread across `config["analytics"]["days_back"]` days
- Recent days get more weight (exponential decay distribution)
- Each event has: `ad`, `event_type=AD_VIEWED`, `timestamp`, `user=None` (anonymous views)
- `DailyAdMetrics`: one per ad per day with total view count
- `bulk_create` with `ignore_conflicts=True` for metrics
- Skip entirely if analytics=False

**Acceptance criteria:**
- Creates events only for published ads (others should get few/no events)
- Events span the configured number of days
- Recent days have higher event counts than old days
- Deterministic per Faker seed
- Metrics rollup matches event counts

---

### T010: Build `SeedService` orchestrator

**Priority:** high

**Depends on:** T005, T006, T008, T009

**Risk:** medium — orchestrates all generators, handles cleanup order respecting FK constraints, uses advisory lock. Must not deadlock.

**Goals:**
- Orchestrate all generators in correct order
- Clear all seedable tables in FK-safe order before seeding
- Load config from YAML
- Report progress (table names, counts, timing)
- Use advisory lock to prevent concurrent seed operations

**Files:**
- `src/backend/apps/seed/services/seed_service.py`

**Targets:**
- New class: `SeedService`
- New function: `run()`

**Detailed requirements:**

```python
class SeedService:
    def __init__(self):
        self.config = self._load_config()

    def _load_config(self) -> dict:
        # Load seed.default.yaml from config/ directory
        # Merge with CLI overrides

    def run(self, users, ads, force, status_distribution, analytics):
        with advisory_lock(AdvisoryLockId.SEED):
            self._clean()
            users = self._generate_users(users)
            ads = self._generate_ads(ads, users)
            self._generate_images(ads)
            if analytics:
                self._generate_analytics(ads)

    def _clean(self):
        # FK-safe delete order:
        # 1. DailyAdMetrics
        # 2. AnalyticsEvent
        # 3. AdImage
        # 4. Ad
        # 5. User (only seed users — filter by AdSource.SEED)
        # NOTE: Categories and Cities are fixtures — NOT deleted
```

**Design rules:**
- Cleanup must respect FK constraints: delete child tables before parents
- Categories and cities are NOT deleted (they are static fixtures)
- Users are identified and deleted by: user has ads with `source=SEED` OR has no ads
- Advisory lock ID 110 prevents concurrent seeds
- Progress reporting: print `[table] count rows in X.Xs` per table
- Timer per generator phase, total timer at end

**Acceptance criteria:**
- `run()` completes without errors
- All tables are properly cleaned before seeding
- FK constraints are respected during cleanup
- Advisory lock prevents concurrent execution
- Progress output is human-readable
- Re-running produces identical data (deterministic Faker seed)

---

### T011: Build management command `seed.py`

**Priority:** high

**Depends on:** T010

**Risk:** low — standard Django BaseCommand pattern, matches existing commands like `create_admin_user`.

**Goals:**
- Create user-facing CLI `python manage.py seed`
- Parse CLI arguments and delegate to `SeedService`
- Interactive confirmation unless `--force`

**Files:**
- `src/backend/apps/seed/management/commands/seed.py`

**Targets:**
- New class: `Command(BaseCommand)`

**CLI Interface:**
```
python manage.py seed [--users 10] [--ads 30] [--force]
  [--status-distribution '{"published":0.6,"archived":0.2,...}']
  [--analytics True]
```

**Arguments:**
- `--users`: int, default 10
- `--ads`: int, default 30
- `--force`: bool, default False — skip confirmation prompt
- `--status-distribution`: str (JSON), default from config file
- `--analytics`: bool, default True

**Behavior:**
- Show destructive data warning: "This will DELETE all seed data and regenerate. Continue? [y/N]"
- Skip prompt if `--force`
- Parse `--status-distribution` JSON safely (try/except with clear error)
- Call `SeedService().run(...)` with parsed args
- Show success message with timing summary

**Acceptance criteria:**
- `uv run python src/backend/manage.py seed --help` shows all options
- Without `--force`, prompts for confirmation
- With `--force`, skips prompt
- Invalid `--status-distribution` JSON shows clear error
- Default values match spec (10 users, 30 ads)
- Full run populates database with seed data (verified manually)

---

### T012: Docker Compose integration

**Priority:** should

**Depends on:** T011

**Risk:** medium — modifies Docker Compose files and adds entrypoint script. Follows established `create_admin` pattern.

**Goals:**
- Create `entrypoint-seed.sh` for one-shot seed execution
- Add `seed` service to `docker-compose.yml` with `profiles: ["seed"]`
- Add image override to `docker-compose.prod.yml`

**Files:**
- `docker/entrypoint-seed.sh` — new file
- `docker-compose.yml` — add `seed` service
- `docker-compose.prod.yml` — add image override for `seed`

**Targets:**
- New entrypoint script
- New service: `seed` in `docker-compose.yml`

**Detailed requirements:**

`entrypoint-seed.sh`:
```bash
#!/bin/bash
set -e
exec uv run python src/backend/manage.py seed --force \
    --users "${SEED_USERS:-10}" \
    --ads "${SEED_ADS:-30}"
```

`docker-compose.yml` addition (following `create_admin` pattern):
- build context same as other services
- `entrypoint: /app/entrypoint-seed.sh`
- `depends_on: migrate (condition: service_completed_successfully)`
- Environment: `SEED_USERS`, `SEED_ADS` pass-through
- `env_file: .env.docker`
- Volumes: `.env.docker:ro`, `media_volume` (for image generation)
- `profiles: ["seed"]` — opt-in only

`docker-compose.prod.yml` addition:
- Image override: `image: ${REGISTRY...}` same as other services

**Acceptance criteria:**
- `docker compose --profile seed run --rm seed` executes without error
- Environment variables `SEED_USERS`, `SEED_ADS` override defaults
- Service waits for `migrate` to complete before running
- Media volume is accessible for image generation

---

### T013: Tests for seed module

**Priority:** high

**Depends on:** T010, T011

**Risk:** low — tests only, no production code.

**Goals:**
- Unit tests for each generator
- Integration test for full seed run
- Test edge cases: 0 count, max count, invalid status distribution

**Files:**
- `src/backend/apps/seed/tests/test_seed.py`

**Targets:**
- New test class(es) in `tests/test_seed.py`

**Test coverage:**

| Test | Scope | Details |
|------|-------|---------|
| `test_user_generates_correct_count` | Unit | UserGenerator produces N users |
| `test_user_unique_telegram_ids` | Unit | All telegram_id values unique |
| `test_user_deterministic` | Unit | Same seed produces same users |
| `test_ad_generates_correct_count` | Unit | AdGenerator produces M ads |
| `test_ad_status_distribution` | Unit | Status distribution approximates weights |
| `test_ad_fk_references_exist` | Unit | All FKs point to valid objects |
| `test_ad_source_is_seed` | Unit | All ads have source=SEED |
| `test_image_correct_count` | Unit | ImageGenerator creates correct AdImage count |
| `test_analytics_events_created` | Unit | AnalyticsGenerator creates events |
| `test_analytics_skip_when_false` | Unit | Respects analytics=False toggle |
| `test_analytics_daily_metrics` | Unit | DailyAdMetrics rollup correct |
| `test_cleanup_order_respects_fk` | Integration | Cleanup does not violate FK constraints |
| `test_seed_force_skips_prompt` | Integration | `--force` skips confirmation |
| `test_seed_idempotent` | Integration | Re-running produces identical data |
| `test_invalid_status_distribution` | CLI | Invalid JSON raises CommandError |
| `test_seed_with_zero_count` | Integration | N=0 produces no records |

**Acceptance criteria:**
- All tests pass: `uv run pytest src/backend/apps/seed/tests/`
- Tests use Django TestCase with database
- Tests are deterministic (same results every run)
- Integration test verifies complete seed workflow with small counts (2 users, 5 ads)

---

## Risk Assessment Summary

| Task | Risk | Reason | Mitigation |
|------|------|--------|------------|
| T001 | low | Purely additive enum changes | Code review |
| T002 | low | Zero-model app, no migration | `manage.py check` |
| T003 | low | New files only | — |
| T004 | low | Static data files only | Manual review of fixture quality |
| T005 | low | New generator, isolated | Unit tests |
| T006 | medium | FK references, status weighting | Unit tests with assertions |
| T007 | medium | Unknown ThumbnailService API | **Research task — blocks T008** |
| T008 | high | Depends on research, filesystem I/O | Research must confirm Go |
| T009 | low | New generator, isolated | Unit tests |
| T010 | medium | FK cleanup order, advisory lock | Integration test, code review |
| T011 | low | Standard Django pattern | Integration test |
| T012 | medium | Docker Compose changes | Manual Docker run test |
| T013 | low | Tests only | — |

## Pre-implementation Checks

Before starting implementation:

1. Verify `uv add pyyaml` is available (or use built-in `json` — YAML parsing may not be needed if config is JSON; spec says yaml but check existing project deps for YAML support)
2. Verify `Pillow` is available in project deps (already used by ThumbnailService)
3. Verify `MEDIA_ROOT` path exists and is writable during development
4. Verify `AdImage` model fields match ThumbnailService key format expectations