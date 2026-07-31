# Specification: Demo/Seed Data Module

**File:** `02_demo-seed-data_spec.md`
**Status:** Final (ready for implementation planning)
**Date:** 2026-07-29

---

## 1. Problem Statement

The Mko Bazuna classifieds board cannot be visually evaluated in development mode because the site starts with an empty database. Developers cannot see:

- Ad cards with images, prices, and titles
- Pagination (requires enough ads to span multiple pages)
- Search and filter behavior (requires data to search/filter)
- Long titles, varied photo layouts, and responsive behavior
- Seller dashboards with analytics

What is needed is a repeatable, configurable way to populate the database with realistic demo data on demand, with a single command, and with Docker Compose integration for dev environments.

---

## 2. Confirmed Requirements

### 2.1 Functional Requirements

| ID | Requirement | Priority |
|----|-------------|----------|
| F01 | A Django management command `python manage.py seed` that populates the database with demo data | Must |
| F02 | The command must accept `--users` (default 10) and `--ads` (default 30) CLI parameters | Must |
| F03 | The command must accept `--force` to skip the destructive-data confirmation prompt | Must |
| F04 | The command must accept `--status-distribution` as a JSON string to control ad status mix | Must |
| F05 | The command must accept `--analytics` (boolean, default true) to toggle analytics/views generation | Should |
| F06 | Seed is **destructive**: all data in seedable tables is cleared before reseeding | Must |
| F07 | The command must support load-testing scale: 10,000 users × 20 ads each = 200,000 ads | Should |
| F08 | Generated data must use proper `StrEnum` constants (`AdStatus`, `AdSource`, `AnalyticsEventType`, etc.) | Must |
| F09 | Seed ads must be distinguishable by source: add `AdSource.SEED = "seed"` | Must |
| F10 | Docker Compose integration via `--profile seed` one-shot service, following `create_admin` pattern | Must |
| F11 | Advisory lock ID `SEED = 110` must be added to `AdvisoryLockId` enum | Should |
| F12 | A config file (`seed.default.yaml`) for tunable parameters (status weights, image counts, analytics range) | Should |

### 2.2 Data Types to Generate

| Entity | Source | Details |
|--------|--------|---------|
| **Categories** | Static fixture (`fixtures/categories.json`) | Real Montenegro category tree with MPTT hierarchy, Russian names |
| **Cities** | Static fixture (`fixtures/cities.json`) | Real Montenegro cities with ISO country code `ME`, regions, slugs |
| **Users** | Faker (dynamic) | `User` instances with unique `telegram_id`, `chat_id`, optional `username` |
| **Ads** | Hybrid: Faker text + fixture templates | Published ads with titles, descriptions, prices, reference to user/category/city |
| **Images** | Bundled JPEG files + `ThumbnailService` | 1-3 images per ad, from pool of 5-10 bundled photos |
| **Views** | Faker (dynamic) | `AnalyticsEvent` records with `AD_VIEWED` type, spread over past 90 days |
| **DailyAdMetrics** | Faker (dynamic) | Rollup table with per-ad-per-day view counts, optionally populated |

### 2.3 Non-Functional Requirements

| ID | Requirement |
|----|-------------|
| N01 | Deterministic output: `Faker.seed_instance()` controlled by config for reproducibility |
| N02 | Performance: 200K ads must seed in <5 minutes using `bulk_create` with chunking |
| N03 | All generators must use `bulk_create` (not individual saves) for performance |
| N04 | Seed must be a **development-only** operation — never run in production |
| N05 | No network dependencies: all resources (fixtures, images) must be bundled in the repository |

---

## 3. Conceptual Development Tasks

### Task 1: Create `apps/seed` app skeleton

**Purpose:** Establish the Django app module with proper structure and app config.

**Expected outcome:**
- `src/backend/apps/seed/` directory with:
  - `__init__.py`
  - `apps.py` (`SeedConfig` inheriting `AppConfig`, name `"apps.seed"`)
  - `management/__init__.py`
  - `management/commands/__init__.py`
  - `generators/__init__.py`
  - `services/__init__.py`
  - `config/` directory
  - `fixtures/` directory
  - `tests/__init__.py`
- `apps.seed` added to `INSTALLED_APPS` in `base.py`
- `AdSource.SEED = "seed"` added to `apps/core/enums.py`
- `AdvisoryLockId.SEED = 110` added to `apps/core/enums.py`

**Dependencies:** None

### Task 2: Create reference data fixtures

**Purpose:** Provide static, human-curated JSON files for categories and cities.

**Expected outcome:**
- `fixtures/categories.json`: Real Montenegro classifieds category tree (django-mptt compatible), with `name` (Russian), `slug`, `is_active`, `parent` references, optionally `name_i18n`
- `fixtures/cities.json`: Real Montenegro cities with `country_code="ME"`, `name` (Russian), `region`, `slug`, optionally `name_i18n`

**Dependencies:** Task 1

### Task 3: Build config and base generator infrastructure

**Purpose:** Create the shared infrastructure used by all generators.

**Expected outcome:**
- `config/seed.default.yaml` with:
  - `status_distribution` (map of `AdStatus` → float weights)
  - `image_count` (`min`, `max`)
  - `analytics.days_back`, `analytics.views_per_ad_per_day` (`min`, `max`)
  - `faker_seed` (int, default 42)
  - `chunk_size` (int, default 10000)
- `generators/base.py` with `BaseGenerator` class providing:
  - Shared `Faker` instance with `ru_RU` locale, seeded
  - Helper methods for random choices, datetime generation

**Dependencies:** Task 1

### Task 4: Build `UserGenerator`

**Purpose:** Generate N fake seller users.

**Expected outcome:**
- `generators/users.py` with `UserGenerator(BaseGenerator)`:
  - Generates unique `telegram_id` and `chat_id` using `itertools.count()` (not Faker `.unique`)
  - Optional `username` via Faker (30% probability)
  - All users active, not banned, consent given
  - Returns `list[User]` ready for `bulk_create`
  - Supports chunked generation for large counts

**Dependencies:** Task 3

### Task 5: Build `AdGenerator`

**Purpose:** Generate M ads referencing existing users, categories, and cities.

**Expected outcome:**
- `generators/ads.py` with `AdGenerator(BaseGenerator)`:
  - Reads ad title/description templates from `fixtures/ads.json`
  - Randomly assigns category, city, user from existing records
  - Generates prices via Faker (configurable range)
  - Sets status according to `--status-distribution` (default from config)
  - Sets timestamps (`published_at`, `archived_at`, etc.) consistent with status
  - Returns `list[Ad]` ready for `bulk_create`
  - Does **not** call `transition_to()` — sets fields directly
  - Supports chunked generation for large counts

**Dependencies:** Task 3, Task 4 (for user references), Task 2 (for categories/cities)

### Task 6: Build `ImageGenerator`

**Purpose:** Copy bundled demo photos, generate thumbnails, create `AdImage` records.

**Expected outcome:**
- `fixtures/images/` — 5-10 bundled royalty-free JPEGs (<100KB each)
- `generators/images.py` with `ImageGenerator(BaseGenerator)`:
  - Pre-processes all fixture images at start: copies to `MEDIA_ROOT/<uuid>.jpg`, generates all 3 thumbnail variants via `ThumbnailService`
  - Creates a pool of reusable image keys
  - For each ad: selects 1-3 random images from pool, creates `AdImage` records with proper `position` ordering
  - Images are **shared** across ads (acceptable for demo data)
  - Returns `list[AdImage]` ready for `bulk_create`

**Dependencies:** Task 5 (ads must exist first for FK), existing `ThumbnailService`

### Task 7: Build `AnalyticsGenerator`

**Purpose:** Generate fake view events and aggregated metrics.

**Expected outcome:**
- `generators/analytics.py` with `AnalyticsGenerator(BaseGenerator)`:
  - Creates `AnalyticsEvent` records with `AD_VIEWED` type
  - Spreads events across 90 days with realistic distribution (more recent = more views)
  - Optionally creates `DailyAdMetrics` rollup records (one per ad per day)
  - Uses `bulk_create` with `ignore_conflicts=True` for metrics
  - Respects `--analytics` flag (skip if False)

**Dependencies:** Task 5 (ads)

### Task 8: Build `SeedService` orchestrator

**Purpose:** Orchestrate all generators in correct order with cleanup, progress reporting, and error handling.

**Expected outcome:**
- `services/seed_service.py` with `SeedService`:
  - `run(users, ads, force, status_distribution, analytics)` method
  - Clears all seedable tables in correct order (respecting FK constraints)
  - Loads config from `seed.default.yaml`
  - Instantiates and runs each generator sequentially
  - Reports progress to stdout (table names, counts, timing)
  - Uses advisory lock `SEED = 110` to prevent concurrent seed operations
  - Acquires and releases advisory lock

**Dependencies:** Tasks 4, 5, 6, 7

### Task 9: Build management command `seed.py`

**Purpose:** User-facing CLI entry point.

**Expected outcome:**
- `management/commands/seed.py` inheriting `BaseCommand`:
  - `--users` (int, default 10)
  - `--ads` (int, default 30)
  - `--force` (bool, default False)
  - `--status-distribution` (str, JSON format, e.g. `'{"published":0.6,"archived":0.2,"draft":0.1,"on_moderation":0.05,"rejected":0.05}'`)
  - `--analytics` (bool, default True)
  - Interactive confirmation if not `--force`
  - Delegates to `SeedService`

**Dependencies:** Task 8

### Task 10: Docker Compose integration

**Purpose:** Enable seed as a one-shot Docker service.

**Expected outcome:**
- `docker/entrypoint-seed.sh`: shell script calling `uv run python src/backend/manage.py seed --force` with env var overrides
- `docker-compose.prod.yml` addition: `seed` service with:
  - `build` context
  - `entrypoint` pointing to `entrypoint-seed.sh`
  - `depends_on: migrate (completed)`
  - Environment variables for `SEED_USERS`, `SEED_ADS`
  - `profiles: ["seed"]`
  - Mounts: `.env.docker:ro`, `media_volume`

**Dependencies:** Task 9

### Task 11: Tests for seed module

**Purpose:** Ensure seed generators produce valid data.

**Expected outcome:**
- `tests/test_seed.py`:
  - Test each generator produces correct model instances
  - Test generator handles edge cases (0 count, max count)
  - Test status distribution parsing (valid, invalid, defaults)
  - Test cleanup order respects FK constraints
  - Test `--force` skips confirmation
  - Integration test: full seed run with small count, verify DB state

**Dependencies:** Tasks 4-9

---

## 4. Product Owner Decisions

| # | Question | Decision |
|---|----------|----------|
| Q1 | Favorites model — should seed include it? | **B: Exclude.** No `Favorite` model exists. Generate only what existing models support. |
| Q2 | Photo source and quantity | **A: Bundle 5-10 royalty-free JPEGs** in `fixtures/images/`. Each ad gets 1-3 random images from pool. Owner can add/replace photos later. |
| Q3 | Default seed scale | **A: Small default (10 users, 30 ads).** CLI flags (`--users`, `--ads`) scale up. Must also support **load-testing scale** (10K users × 20 ads). |
| Q4 | Destructive vs additive | **A: Clean-then-seed (idempotent).** `--force` skips confirmation prompt. |
| Q5 | Docker seed timing | **A: Separate one-shot service with `--profile seed`**. Follows existing `migrate` / `create_admin` pattern. |
| Q6 | Categories and cities source | **A: Static fixtures (JSON).** Real data, human-curated. |
| Q7 | Ad status distribution | **Configurable via CLI flag.** All statuses configurable for testing. Default: mostly PUBLISHED with smaller shares of other statuses. |
| Q8 | Views/analytics generation | **C: Both raw events AND rollups.** Configurable toggle (`--analytics`). |

---

## 5. Research Summary

### 5.1 Library Evaluation

| Library | Verdict | Rationale |
|---------|---------|-----------|
| `django-seed` | **REJECTED** | Abandoned (last release 2021, Django 3.2). Cannot control status distribution. Seeds ALL models blindly. |
| `model_bakery` | **APPROVED (internal only)** | Already in dev deps. Use `baker.prepare` + `_bulk_create` internally for high-volume generation. Not exposed as user-facing API. |
| Faker (direct) | **APPROVED** | `Faker('ru_RU')` for Russian content. `Faker.seed_instance(n)` for reproducibility. |
| Custom `SeedService` | **RECOMMENDED** | Industry pattern (Django Cookiecutter, Wagtail, Saleor, Mozilla Kitsune all write custom seed logic). |

### 5.2 Key Architectural Recommendations

| Aspect | Recommendation | Rationale |
|--------|---------------|-----------|
| State machine | **Bypass `transition_to()`** | Direct field setting + `bulk_create` for performance. Seed data needs no state machine validation. |
| Image processing | **Pre-process pool, reuse keys** | Copy all fixture images once, generate thumbnails once, then reference same keys across ads. Avoids I/O per ad at scale. |
| Analytics metrics | **`bulk_create` with `ignore_conflicts=True`** | Handles `UniqueConstraint(ad, date)` gracefully without checking for conflicts first. |
| Faker unique values | **Use `itertools.count()` for IDs** | Faker `.unique` has retry limit. For 200K+ unique values, `itertools.count()` is safer and faster. |
| Chunking | **10K per batch** | Memory safety. `bulk_create` with `batch_size=5000`. |
| Status distribution | **JSON CLI argument** | `--status-distribution '{"published":0.6,...}'` — parseable and flexible. |

### 5.3 Docker Pattern

The `--profile seed` one-shot service follows the established `create_admin` pattern:
- `depends_on: migrate (condition: service_completed_successfully)`
- Environment variables override seed parameters
- `docker compose --profile seed run --rm seed` to execute
- `entrypoint-seed.sh` shell script calls `manage.py seed`

### 5.4 Risks Identified by Research

1. **Image duplication at scale:** 200K ads × 2 images = 400K files in `MEDIA_ROOT`. Acceptable because AdImage stores only keys (not files). Use `images/seed/` subdirectory for hygiene.
2. **django-mptt tree rebuild:** After bulk-creating categories, call `Category.objects.rebuild()`.
3. **Memory at 200K:** ~200MB Python memory for 200K `Ad` objects. Acceptable, chunked at 10K.
4. **search_vector trigger:** Fires on `bulk_create` automatically — desirable (FTS gets populated).

---

## 6. Assumptions

1. The seed module is **development-only** — never executed against production databases.
2. The bundled demo photos use royalty-free licenses compatible with the project's MIT license.
3. The `ThumbnailService.generate_thumbnails()` method accepts raw bytes and a storage key string (to be verified during implementation).
4. The existing `Category.objects.rebuild()` method is sufficient for MPTT tree repair after fixture load.
5. The `apps.seed` app has zero models, therefore zero migrations — adding it to `INSTALLED_APPS` is risk-free.
6. The `media_volume` Docker volume is shared between the `seed` container and `web`/`bot` containers.
7. The `AdImage.image` field is a simple filename key, not an `ImageField` — images are served from `MEDIA_ROOT/<key>.jpg`.

---

## 7. Constraints

1. No new dependencies beyond what `uv add` can provide (but preferably zero new deps).
2. All constants must use `StrEnum` / `IntEnum` (project rule 10).
3. `bulk_create` must be used — no `Model.objects.create()` in loops.
4. Seed must be **idempotent** — repeated runs produce the same result (deterministic Faker seed).
5. The `apps.seed` module must be self-contained under `src/backend/apps/seed/`.
6. The seed command uses advisory lock ID 110 to prevent concurrent execution.
7. No PII in seed data — all user data is synthetic.

---

## 8. Risks

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| `ThumbnailService` API incompatible with seed image flow | Medium | Medium | Research during implementation; adapt if needed |
| Seed at 200K ads exceeds Docker container memory limits | Low | Medium | Chunk at 10K; configurable chunk size |
| Fixture JSON format incompatible with `django-mptt` parent references | Low | Medium | Use `pk` references in fixtures; call `rebuild()` after load |
| `--status-distribution` JSON parsing fragile for CLI | Low | Low | Validate with Pydantic or simple dict parsing |
| Category/city fixtures become stale (new cities/categories needed) | Low | Low | Manual update; rarely changes |

---

## 9. Open Questions

1. **None** — all business decisions have been resolved by the Product Owner. Remaining unknowns are technical and should be resolved during implementation research.

---

## 10. Out of Scope

- **Favorites model** — does not exist in codebase; excluded by PO decision
- **Search history** — no seed for `PopularSearch` or `SearchHistory` (populated naturally by user activity)
- **Saved searches and alerts** — too complex for demo; not needed for visual evaluation
- **Moderation data** — `ModerationCriteria` singleton and `ModeratorActionLog` are admin features, not demo content
- **Trust signals** — `SellerTrustScore` and `SellerVerification` computed by existing services, not seeded
- **Ad moderation priority** — computed by existing services, not seeded
- **Multi-currency** — deferred post-MVP per architecture docs
- **API tests against seed data** — seed is for visual dev, not for CI test fixtures (separate test fixtures exist in `conftest.py`)

---

## 11. Definition of Ready

This specification is **ready for implementation planning** when:

- [x] Business problem is clearly stated
- [x] All requirements are confirmed
- [x] 11 conceptual development tasks are defined with purpose, outcome, and dependencies
- [x] 8 Product Owner decisions are captured
- [x] Research has been conducted and summarized
- [x] Assumptions, constraints, risks, and out-of-scope items are documented
- [x] No unresolved business questions remain

**Implementation may begin — no additional business analysis is required.**