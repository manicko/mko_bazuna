# Phase 1 Detailed Plan: Minimal Publish-to-Discover Flow

**Wave:** Foundation
**Depends_on:** `00_detailed_plan_docker_environment.md` (Docker Environment plan — owns Dockerfile, compose files, nginx.conf, settings package, pyproject stack). Phase 1 does NOT recreate infra; it only consumes it and adds feature-specific wiring.
**Files_modified:** `src/backend/`, `src/telegram_bot/`, `docs/wiki/*.md`
**Autonomous:** Yes

> **Spec source:** `docs/wiki/01_technical_specification.md` (decisions H, C, F, G, I, J),
> `docs/wiki/04_db_structure.md` (schema, triggers, indexes), `docs/wiki/03_structure.md` (deployment),
> `docs/wiki/02_packages.md` (stack). Enums per project rule 10.
> **Pydantic boundary validation:** All bot message payloads validated via Pydantic v2 DTOs (rule 11).

> **Planner note:** Produced via 3 iterative Planner runs. Coverage audit, version exactness,
> rule-compliance, DB-structure consistency, and async-safety (zone C5) verified in run 3.

---

## Task 1: Django Project Structure + StrEnums

**Goal:** Scaffold the Django project skeleton and centralize all fixed values as `StrEnum` (rule 10).

**Acceptance Criteria:**
- Settings package is **owned by the Docker Environment plan** (`00_detailed_plan_docker_environment.md` Task 6: `src/backend/config/settings/{base,dev,prod,test}.py`). Phase 1 does NOT create `settings.py`; it only **supplies feature app INSTALLED_APPS / MIDDLEWARE / urls entries** to the Docker plan's `base.py` and adds `config/urls.py` routing. Phase 1 relies on Docker plan Task 0 for the `psycopg[binary]>=3.2.0` + `django-environ` pins.
- `src/backend/apps/core/enums.py` defines:
  - `AdStatus`: `DRAFT`, `ON_MODERATION`, `PUBLISHED`, `REJECTED`, `ON_MODERATION_FAILED`, `ARCHIVED`, `DELETED`
  - `AdSource`: `TELEGRAM`
  - `AnalyticsEventType`: `REGISTRATION_CREATED`, `AD_PUBLISHED`, `SEARCH_PERFORMED`, `CONTACT_INITIATED`
  - `ModeratorActionType`: `REJECT`, `BAN_ACCOUNT`, `SOFT_DELETE`, `CRITERIA_CHANGE`, `OTHER`
  - `CategoryRejectReason` (Layer-2 manual checklist vocabulary, decision A/zone D8): `ADULT_CONTENT`, `VIOLENCE_GORE`, `DRUGS_WEAPONS`, `HATE_SPEECH`, `COUNTERFEIT_GOODS`, `ILLEGAL_GOODS`, `SPAM_SCAM`, `OFF_TOPIC`. NOTE: this enum is a UI/admin *vocabulary* only — `ModeratorActionLog.reason` remains TEXT per `04_db_structure.md` (free TEXT + one of the checklist categories as guidance). The enum is NOT stored as a column; it constrains the admin reject dropdown. Validator WARN resolved: model schema stays TEXT, enum is reference-only.
- `uv run manage.py check` passes; `uv run ruff check` passes.
- All models import enums from `apps.core.enums` (no inline string literals for fixed values — rule 10).

**Artifacts:** `config/urls.py`, `apps/core/enums.py`, `__init__.py` files (feature additions to Docker plan's `settings/base.py`).
**Dependencies:** Docker Environment plan (Tasks 0, 6)
**Risks:** Enum naming drift vs spec; import cycles between `core` and feature apps.

---

## Task 2: Core Models — User, LoginToken, Ad, AdImage

**Goal:** Implement the authentication and ad data models exactly per `04_db_structure.md`.

**Acceptance Criteria:**
- `apps/users/models.py`: `telegram_id` (BIGINT, UNIQUE, nullable), `username` (nullable), `is_staff`/`is_superuser` (from `AbstractUser`), `is_banned`, `is_deleted`, `ads_auto_publish` (default True), `deleted_at`, `consent_given_at`, `consent_revoked_at`, `hard_delete_at` (all nullable).
- `apps/users/models.py` — **standalone `LoginToken` table** (spec zone C1): `token_hash` (CHAR(64) UNIQUE, indexed — SHA-256 of the raw 32-char URL-safe token; raw token NEVER stored), `telegram_id` (nullable), `created_at`, `expires_at` (+5 min), `consumed_at` (nullable).
- `apps/ads/models.py` — `Ad`: `user_id` FK, `title`, `description`, `price` (INT, nullable), `category_id` FK, `city_id` FK, `category_name` (editable=False, denormalized Russian name), `status` (`AdStatus`), `source` (`AdSource`), `created_at`, `updated_at`, `published_at` (nullable), `original_published_at` (nullable, immutable), `archived_at`, `deleted_at`, `moderation_failed_at` (nullable), `rejected_at` (nullable), `search_vector` (TSVECTOR), `published_by` FK (nullable, SET_NULL), `moderated_by` FK (nullable, SET_NULL).
- `apps/ads/models.py` — `AdImage`: `ad_id` FK, `image` (storage key, UUID v4 — no user/telegram PII in key, zone R6), `telegram_file_id` (nullable), `position` (INT).
- **Lifecycle-timer semantics (decision J / zone C3):** `published_at` resets on EVERY `PUBLISHED` transition (archive/reactivation/text edits); `original_published_at` is IMMUTABLE (audit only, never drives sweeps).
- `moderation_failed_at` and `rejected_at` are mutually exclusive terminal states.
- `uv run basedpyright` and `uv run ruff check` pass.

**Artifacts:** `apps/users/models.py`, `apps/ads/models.py`, migrations.
**Dependencies:** Task 1
**Risks:** `telegram_id` uniqueness vs NULL semantics; `search_vector` cannot be `GENERATED ALWAYS` (needs trigger); token_hash SHA-256; NULL FK semantics for audit trail.

---

## Task 3: Categories + Locations Models (MPTT + JSONB i18n)

**Goal:** Reference data with hierarchy and i18n name support.

**Acceptance Criteria:**
- `apps/categories/models.py`: `name` (Russian, required), `name_i18n` (JSONB `{"ru": str, "bs": str}`, nullable), `slug`, MPTT fields (`lft`, `rght`, `tree_id`, `level`), `is_active`. django-mptt is the single source of truth (no denormalized `path`/`level` columns).
- `apps/locations/models.py`: `name` (Russian, required), `name_i18n` (JSONB), `country_code`, `region`, `slug`.
- `get_name(locale)` method on both models: returns `name_i18n[locale]` when present, else falls back to Russian `name` (decision D2).
- Seed data: ~50-60 Bosnia/Herzegovina cities, ~15-20 categories per the recommended tree (Товары / Услуги / Недвижимость with subcategories).
- `uv run manage.py migrate` applies; seed loads via `loaddata`/`RunPython` migration.

**Artifacts:** `apps/categories/models.py`, `apps/locations/models.py`, seed migration/fixtures.
**Dependencies:** Task 1
**Risks:** MPTT tree integrity after seed; JSONB locale fallback correctness.

---

## Task 3.5: Django Admin Registration (US-A1, US-A2, US-A3, US-A7, US-A11)

**Goal:** Register all models in Django admin for administrative access and moderation.

**Acceptance Criteria:**
- `apps/users/admin.py`: User listing with `telegram_id`, `is_banned`, `is_deleted`, `ads_auto_publish`, `consent_given_at`/`consent_revoked_at`.
- `apps/ads/admin.py`: Ad listing (US-A2) with filters for status/category/city/date; quick action to reject (US-A3) or ban account (US-A3).
- `apps/categories/admin.py`: Category management (US-A7) — add/edit/deactivate, tree drag-drop via mptt admin.
- `apps/locations/admin.py`: City management (US-A7) — add/edit/deactivate.
- `apps/moderation/admin.py`: `ModerationCriteria` singleton edit form (US-A11); `ModeratorActionLog` read-only history.
- Admin access restricted to `is_staff`/`is_superuser` (US-A1). Failed ads list view (US-A11) with `reason` display (never shown to sellers).

**Artifacts:** `apps/users/admin.py`, `apps/ads/admin.py`, `apps/categories/admin.py`, `apps/locations/admin.py`, `apps/moderation/admin.py`.
**Dependencies:** Tasks 1, 2, 3, 4
**Risks:** Admin RBAC configuration; display of failed queue vs regular listings.

---

## Task 4: Moderation + Analytics Models

**Goal:** Moderation singleton, action log, and product analytics model.

**Acceptance Criteria:**
- `apps/moderation/models.py` — `ModerationCriteria` singleton (zone D3/D4): `title_min_length`, `title_max_length`, `description_min_length`, `description_max_length`, `price_required` (BOOL, default True), `min_images` (default 1), `max_images` (default 5), `banned_words` (JSONB `[]`), `max_ads_per_user` (default 10), `duplicate_title_threshold` (default 85), `updated_at`, `updated_by` (FK nullable SET_NULL). Exactly these fields (NO `min_price`/`max_price`).
- `apps/moderation/models.py` — `ModeratorActionLog`: `ad_id` FK (nullable, SET_NULL), `user_id` FK (nullable, SET_NULL), `action_type` (`ModeratorActionType`), `reason` (TEXT — NEVER shown to seller, US-A11), `created_at`.
- `apps/analytics/models.py` — `AnalyticsEvent`: `event_type` (`AnalyticsEventType`), `timestamp` (default now), `user_id` FK (nullable, SET NULL on erasure, zone R1/R5).
- `uv run basedpyright` passes.

**Artifacts:** `apps/moderation/models.py`, `apps/analytics/models.py`, migrations.
**Dependencies:** Task 1
**Risks:** Singleton pattern correctness; `user_id` SET NULL on erasure must preserve `reason` for audit.

---

## Task 5: PostgreSQL Triggers + GIN Index (search_vector)

**Goal:** Maintain `search_vector` (title A + description B + category_name C, russian config) and denormalized `category_name` via plpgsql triggers (zone D1).

**Acceptance Criteria:**
- Migration creates function `ads_search_vector_fn()` (computes `category_name` from `categories.name` via FK, then `search_vector = setweight(to_tsvector('russian', title),'A') || setweight(... description,'B') || setweight(... category_name,'C')`).
- Trigger `ads_search_vector_update` BEFORE INSERT OR UPDATE on `ads`.
- Function `categories_name_propagate()` + trigger `on_category_name_update` AFTER UPDATE OF name ON categories (re-touches dependent ads; spec zone D1).
- **`GinIndex(name='IX_ads_search_gin', fields=['search_vector'])`** applied (NOT `models.Index` — that would build a BTREE, zone D12).
- Runs on PostgreSQL 17; one-time backfill for existing rows.
- `uv run manage.py migrate` succeeds against PostgreSQL 17.

**Artifacts:** `apps/ads/migrations/000X_search_vector_triggers.py`, trigger SQL.
**Dependencies:** Tasks 2, 3
**Risks:** Trigger syntax; concurrency; backfill cost on 500k rows.

---

## Task 6: Publication + Lifecycle Indexes

**Goal:** Performance indexes per `04_db_structure.md`.

**Acceptance Criteria:**
- `IX_ads_pub_listing`: partial B-tree `fields=['status','category_id','city_id','-published_at']`, `condition=Q(status=AdStatus.PUBLISHED)`.
- `IX_ads_search_gin`: GIN (Task 5).
- `IX_ads_user_status`: `fields=['user_id','status']`.
- `IX_users_erasure_sweep`: `fields=['consent_revoked_at']` (zone R1, 30-day hard delete).
- `IX_ads_archive_sweep`: partial `fields=['status','published_at']`, `condition=Q(status=AdStatus.PUBLISHED)` (2-month archive trigger).
- `IX_ads_delete_sweep`: partial `fields=['status','published_at']`, `condition=Q(status=AdStatus.ARCHIVED)` (4-month purge).
- `IX_ads_purge_failed`: partial `fields=['status','moderation_failed_at']`, `condition=Q(status=AdStatus.ON_MODERATION_FAILED)` (7-day purge).
- `IX_ads_rejected_sweep`: partial `fields=['status','rejected_at']`, `condition=Q(status=AdStatus.REJECTED)` (90-day purge, zone D4).
- No standalone `price` index (added only after EXPLAIN ANALYZE, zone C7).

**Artifacts:** Index definitions in `Ad.Meta.indexes` + migration.
**Dependencies:** Task 2
**Risks:** Partial-index condition syntax.

---

## Task 7: Settings Security Configuration (TLS-ready)

**Goal:** Production-safe Django settings (contributed to the Docker Environment plan's settings package — NOT a standalone `settings.py`).

**Acceptance Criteria:**
- These values are supplied to the Docker plan's `settings/base.py` (Task 6): `SESSION_COOKIE_SECURE=True`, `CSRF_COOKIE_SECURE=True`, `SECURE_SSL_REDIRECT=True`, `SECURE_PROXY_SSL_HEADER=('HTTP_X_FORWARDED_PROTO','https')`, `USE_X_FORWARDED_HOST=True`.
- `CONN_MAX_AGE=0` (each process owns its pool; PgBouncer transaction-mode recommended, zone C5).
- **PgBouncer async safety:** `OPTIONS={"prepare_threshold": None}` for psycopg3 compatibility (spec zone C5).
- `DEFAULT_FILE_STORAGE` uses Django's **built-in `FileSystemStorage` via the `STORAGES` setting** (local `MEDIA_ROOT` behind nginx in phase 1). The `STORAGES` contract allows later swap to `django-storages` + S3/R2/MinIO **without code rewrites** — but `django-storages`/`boto3` are DEFERRED (YAGNI) per canonical `docs/wiki/02_packages.md`.
- `psycopg[binary]>=3.2.0` pin is owned by Docker plan Task 0 (Phase 1 only adds feature deps on top).

**Artifacts:** Feature contribution to Docker plan's `settings/base.py` (no new settings module created).
**Dependencies:** Task 1, Docker Environment plan (Tasks 0, 6)
**Risks:** Local dev vs prod settings drift (solved by Docker plan's env-flag settings split).

---

## Task 8: Deployment Wiring (consume Docker Environment plan)

**Goal:** Wire Phase 1 feature code into the infrastructure owned solely by `00_detailed_plan_docker_environment.md`. This task does **NOT** create Dockerfile/compose/nginx/settings — those are owned by the Docker Environment plan (single-owner rule, Auditor F-01). Phase 1 only specifies the feature-specific contract those files must satisfy.

**Acceptance Criteria:**
- **Migration guard (zone C5/D7):** confirm the Docker Environment plan's one-shot `migrate` service (advisory-locked) runs before `web`+`bot` (declared in Docker plan Task 2). Phase 1 supplies no migration file of its own for this; it relies on the Docker plan's entrypoint.
- **Async safety (zone C5):** bot wraps ORM calls and Telegram photo downloads in `sync_to_async`; each process `CONN_MAX_AGE=0` (settings owned by Docker plan Task 6; Phase 1 sets `OPTIONS={"prepare_threshold": None}` in its settings contribution if not already covered).
- **nginx `/media/` security contract (zone R8):** Phase 1 requires the Docker plan's `docker/nginx/nginx.conf` (Task 7) to enforce: `X-Content-Type-Options: nosniff`; whitelist `image/jpeg`, default `application/octet-stream`; `Content-Disposition: inline`; block script execution `location ~* /media/.*\.(php|py|cgi)$ { deny all; }`.
- **Dockerfile contract:** Phase 1 requires the Docker plan's `docker/Dockerfile` (Task 1) to use `python:3.14-slim` + uv, non-root USER, `collectstatic --noinput`, and mount `media_volume` read-write for the `app` user.
- **pyproject contract:** Phase 1 requires `pyproject.toml` (Docker plan Task 0) to pin `psycopg[binary]>=3.2.0` and `django-environ>=0.11.0` — Phase 1 adds only its feature dependencies (`aiogram>=3.15.0`, `deep-translator>=1.11.0`, `django-mptt>=0.18.0`, `django-filter>=26.1`, `django-tailwind>=4.4.0`, `django-htmx>=1.19.0`, `pillow>=10.4.0`) on top of the Docker plan's reconciled base.

**Artifacts:** None new infra files. Only feature settings additions + verification that Docker plan contracts hold (feature-app wiring, not infra creation).
**Dependencies:** Task 1, Docker Environment plan (Tasks 0, 1, 2, 6, 7)
**Risks:** Contract drift if Docker plan changes base image/compose topology — keep cross-references in sync.

---

## Task 9: Telegram Bot FSM Layer (aiogram 3.x)

**Goal:** Login via deep-link + step-by-step ad creation (US-S1, US-S2).

**Acceptance Criteria:**
- `telegram_bot/states.py`: `AdCreateState` — CATEGORY, CITY, TITLE, DESCRIPTION, PRICE, PHOTOS, PREVIEW.
- **Pydantic v2 DTO validation (rule 11):** All bot message payloads wrapped via Pydantic models in `telegram_bot/schemas/message_payloads.py` — `PhotoPayload`, `TitlePayload`, `DescriptionPayload`, etc., validating before ORM writes.
- Login handler `/start login_<token>`: bot reads raw token from deep-link, computes SHA-256, atomically claims via `UPDATE login_tokens SET telegram_id=<tg> WHERE token_hash=? AND telegram_id IS NULL AND consumed_at IS NULL AND expires_at > now()`; web then consumes. Constant-time compare via `hmac.compare_digest` (zone C1).
- Category step: bot suggests TOP-3-5 by keyword, seller confirms from suggested tree or full tree; free-text-as-new-category rejected (decision I).
- Photo step: accept ONLY `message.photo` (compressed), reject `message.document`; validate JPEG (magic bytes / PIL), 1..5 photos, ≤2560px, ≤~2MB each; store via built-in `FileSystemStorage` with UUID v4 key; keep `telegram_file_id` as metadata.
- On submit: status `DRAFT → ON_MODERATION`; runs auto-moderation (Task 10); preview shown before send with correction of city/category mapping (decision I).
- **Content language invariant (decision G):** before creating the ad, the bot translates title/description to Russian using `deep-translator` + request cache, so `to_tsvector('russian', ...)` in `search_vector` is correct.
- Draft idle timeout 30 min → auto-discard; cleanup deferred to Phase 4 Task 2 (`sweep_drafts`).
- Login tokens: expired/consumed tokens cleaned by Phase 4 Task 2 (`cleanup_login_tokens`).
- `published_at` resets on EACH `PUBLISHED` transition; `original_published_at` immutable.
- Bot sets `django.setup()` + shared ORM; ORM/photo ops in `sync_to_async`.

**Artifacts:** `telegram_bot/states.py`, `telegram_bot/schemas/message_payloads.py`, `telegram_bot/handlers/login.py`, `telegram_bot/handlers/ad_create.py`, `telegram_bot/services/media.py`, `telegram_bot/main.py`.
**Dependencies:** Tasks 2, 3, 4, Docker Environment plan (Tasks 1, 2, 7)
**Risks:** FSM timeout; token-claim race; photo validation bypass; sync/async mixing.

---

## Task 10: Auto-Moderation Service

**Goal:** Single automatic gate before publish (decision A / US-A10).

**Acceptance Criteria:**
- `apps/moderation/services/auto_moderation.py` reads `ModerationCriteria` singleton (cached 5 min).
- Validates: title/description min/max length; `price_required` → price present; photo count 1..`max_images`; case-insensitive `banned_words`; active ad count ≤ `max_ads_per_user`; duplicate-title via `difflib.ratio` ≥ `duplicate_title_threshold` (0..100 scale).
- On fail: sets `moderation_failed_at`, status `ON_MODERATION_FAILED`, writes `ModeratorActionLog` (auto reason), returns generic error to bot (seller gets NO specific reason per US-A11).
- On pass: status → `PUBLISHED`, `published_at` set, `AnalyticsEvent(AD_PUBLISHED)` recorded.
- `uv run pytest` covers each rule.

**Artifacts:** `apps/moderation/services/auto_moderation.py`, tests.
**Dependencies:** Tasks 2, 4
**Risks:** Cache invalidation after admin edit; difflib cost.

---

## Task 11: Web Listing + FTS Search Views

**Goal:** Public browsing + search (US-B1/B2/B3/B6/B7).

**Acceptance Criteria:**
- `apps/ads/views/listings.py`: HTMX list filtered by category subtree (`get_descendants`), city (exact, with `difflib.get_close_matches` did-you-mean), price range; sort by date/price; empty-state message.
- `apps/search/views/search.py`: FTS on `search_vector` (GIN); Bosnian query translated to Russian via `deep-translator` (timeout ~500ms, fallback to original, 5-min cache, decision G); one-word queries run app-level fuzzy category detect (difflib) → `category_id` filter (zone D1).
- Templates `ads/list.html`, `ads/detail.html`: show title, description, price, photos, city, category (`get_name(locale)`), date; contact button only when allowed (decision C, Phase 3 for contact deep-link logic).
- No login required to browse `PUBLISHED` ads. XSS-safe templates (`{% autoescape %}`).

**Artifacts:** views, templates, `apps/search/services/query_translator.py`.
**Dependencies:** Tasks 2, 3, 6
**Risks:** XSS; media security; translation fallback; did-you-mean for cities.

---

## Task 12: Documentation Updates (wiki sync)

**Goal:** Reconcile wiki with implemented decisions.

**Acceptance Criteria:**
- `docs/wiki/01_technical_specification.md`: decisions H, C, F, G, I, J reflected; US-S1/S2, US-B1/B2/B3/B6/B7, US-A1/A2/A3/A7/A10/A11.
- `docs/wiki/02_packages.md`: canonical stack confirmed (Django 5.2 LTS, psycopg3, aiogram 3.15, deep-translator, django-mptt 0.18, django-filter 26.1, django-tailwind 4.4, django-htmx, pillow; django-storages/boto3/redis/celery DEFERRED).
- `docs/wiki/03_structure.md`: deployment section complete (db/web/bot/nginx, migration guard, async safety).
- `docs/wiki/04_db_structure.md`: schema confirmed against implementation.

**Artifacts:** Updated wiki files (English-only per doc-maintenance-rules).
**Dependencies:** Tasks 1-11
**Risks:** Doc drift; non-English content (forbidden).

---

## Coverage Audit Summary

| User Story | Covered By Task(s) | Notes |
|------------|-------------------|-------|
| US-S1 (Telegram login) | T1, T2, T9 | LoginToken model + bot deep-link handler |
| US-S2 (create ad via bot) | T2, T3, T9, T10 | FSM + auto-moderation |
| US-B1 (browse w/o registration) | T11 | No login required for PUBLISHED ads |
| US-B2 (search) | T11 | FTS on search_vector + query translation |
| US-B3 (filter) | T11 | Category/city/price range filters |
| US-B6 (browse by category) | T3, T11 | MPTT tree + category filter |
| US-B7 (browse by city) | T3, T11 | City lookup + did-you-mean |
| US-A1 (admin auth) | T1, T3.5 | is_staff/is_superuser + admin site |
| US-A2 (admin listing) | T2, T3.5 | Ad listing with filters |
| US-A3 (moderation actions) | T4, T3.5 | Reject/ban actions + ModeratorActionLog |
| US-A7 (cat/city mgmt) | T3, T3.5 | Django admin management |
| US-A10 (auto-moderation) | T10 | Layer-1 synchronous validation |
| US-A11 (failed queue + criteria) | T4, T10, T3.5 | Criteria singleton + failed ad list |

## Version Exactness (Canonical: docs/wiki/02_packages.md)

**Phase 1 Core Stack (CONFIRMED):**
- `django>=5.2.16,<6.0` — LTS 5.2, upper bound blocks 6.0 drift
- `psycopg[binary]>=3.2.0` — psycopg3 for Python 3.14
- `django-environ>=0.11.0` — Typed .env casting
- `django-mptt>=0.18.0` — Django 5.2 compatible
- `django-filter>=26.1` — Django>=5.2 requirement
- `aiogram>=3.15.0` — Bot API bot
- `deep-translator>=1.11.0` — Query translation (Bosnian→Russian)
- `django-tailwind>=4.4.0` — Tailwind standalone (no daisyUI)
- `django-htmx>=1.19.0` — HTMX MPA
- `pillow>=10.4.0` — Image validation (JPEG)

**Deferred (NOT in Phase 1 per 02_packages.md):**
- `django-storages>=1.14.6` — YAGNI until S3/R2 swap
- `boto3>=1.35.0` — YAGNI until S3/R2 swap
- `celery>=5.4.0` — Deferred to post-MVP
- `redis>=5.1.1` — Deferred to post-MVP
- `djangorestframework>=3.15.2` — Deferred (HTMX MPA in phase 1)

## Rule Compliance Checklist

| Rule | Status | Evidence |
|------|--------|----------|
| 10 (StrEnum for ALL constants) | OK | Task 1 centralizes all enums; no inline string literals in models |
| 15 (Small modules/functions) | OK | Tasks split by concern; `apps/ads/`, `apps/moderation/services/`, `telegram_bot/handlers/` structure |
| 13 (Migrations for schema) | OK | Tasks 2, 5, 6 explicit about migrations |
| 1 (English-only in code+docs) | OK | All task artifacts specified as English; doc-maintenance-rules applied |
| 11 (Pydantic v2 at boundaries) | OK | Task 9 adds Pydantic DTOs for bot message payloads (rule 11 explicit) |

## DB Structure Consistency (vs 04_db_structure.md)

| Decision | Status | Evidence |
|----------|--------|----------|
| `published_at` resets on every PUBLISHED | OK | Task 2, Task 9 specify this behavior |
| `original_published_at` immutable | OK | Task 2 specifies: "written once, immutable, audit only" |
| `moderation_failed_at` vs `rejected_at` mutually exclusive | OK | Task 2: "mutually exclusive terminal states" |
| GIN not BTREE for search_vector | OK | Task 5: "GinIndex NOT models.Index" |
| Trigger maintains search_vector + category_name | OK | Task 5: trigger function computes both |

## Async Safety (Zone C5)

| Requirement | Status | Evidence |
|-------------|--------|----------|
| bot wraps ORM in sync_to_async | OK | Task 9, Task 8 |
| CONN_MAX_AGE=0 | OK | Task 7 |
| PgBouncer prepare_threshold=None | OK | Task 7 |
| No DB-backed FSM (Ad.DRAFT in ORM) | OK | Task 9: FSM only tracks steps; `Ad(status=DRAFT)` persisted |
