# Phase 1 Detailed Plan: Minimal Publish-to-Discover Flow

**Wave:** Foundation
**Depends_on:** None
**Files_modified:** `src/backend/`, `src/telegram_bot/`, `docker/`, `docs/wiki/*.md`
**Autonomous:** Yes

> **Spec source:** `docs/wiki/01_technical_specification.md` (decisions H, C, F, G, I, J),
> `docs/wiki/04_db_structure.md` (schema, triggers, indexes), `docs/wiki/03_structure.md` (deployment),
> `docs/wiki/02_packages.md` (stack). Enums per project rule 10.

---

## Task 1: Django Project Structure + StrEnums

**Goal:** Scaffold the Django project skeleton and centralize all fixed values as `StrEnum` (rule 10).

**Acceptance Criteria:**
- `src/backend/config/settings.py` with TLS-ready defaults (`SESSION_COOKIE_SECURE`, `SECURE_SSL_REDIRECT`, `SECURE_PROXY_SSL_HEADER`, `USE_X_FORWARDED_HOST`), `psycopg[binary]>=3.2.0`, `django-environ` for `.env`.
- `src/backend/apps/core/enums.py` defines:
  - `AdStatus`: `DRAFT`, `ON_MODERATION`, `PUBLISHED`, `REJECTED`, `ON_MODERATION_FAILED`, `ARCHIVED`, `DELETED`
  - `AdSource`: `TELEGRAM`
  - `AnalyticsEventType`: `REGISTRATION_CREATED`, `AD_PUBLISHED`, `SEARCH_PERFORMED`, `CONTACT_INITIATED`
  - `ModeratorActionType`: `REJECT`, `BAN_ACCOUNT`, `SOFT_DELETE`, `CRITERIA_CHANGE`, `OTHER`
  - `CategoryRejectReason` (Layer-2 manual checklist): `ADULT_CONTENT`, `VIOLENCE_GORE`, `DRUGS_WEAPONS`, `HATE_SPEECH`, `COUNTERFEIT_GOODS`, `ILLEGAL_GOODS`, `SPAM_SCAM`, `OFF_TOPIC`
- `uv run manage.py check` passes; `uv run ruff check` passes.
- All models import enums from `apps.core.enums` (no inline string literals for fixed values — rule 10).

**Artifacts:** `config/settings.py`, `config/urls.py`, `apps/core/enums.py`, `__init__.py` files, `pyproject.toml`.
**Dependencies:** None
**Risks:** Enum naming drift vs spec; import cycles between `core` and feature apps.

---

## Task 2: Core Models — User, LoginToken, Ad, AdImage

**Goal:** Implement the authentication and ad data models exactly per `04_db_structure.md`.

**Acceptance Criteria:**
- `apps/users/models.py`: `telegram_id` (BIGINT, UNIQUE, nullable), `username` (nullable), `is_staff`/`is_superuser` (from `AbstractUser`), `is_banned`, `is_deleted`, `ads_auto_publish` (default True), `deleted_at`, `consent_given_at`, `consent_revoked_at`, `hard_delete_at` (all nullable).
- `apps/users/models.py` — **standalone `LoginToken` table** (spec zone C1): `token_hash` (CHAR(64) UNIQUE, indexed — SHA-256 of the raw 32-char URL-safe token; raw token NEVER stored), `telegram_id` (nullable), `created_at`, `expires_at` (+5 min), `consumed_at` (nullable).
- `apps/ads/models.py` — `Ad`: `user_id` FK, `title`, `description`, `price` (INT, nullable), `category_id` FK, `city_id` FK, `category_name` (editable=False, denormalized Russian name), `status` (`AdStatus`), `source` (`AdSource`), `created_at`, `updated_at`, `published_at` (nullable), `original_published_at` (nullable, immutable), `archived_at`, `deleted_at`, `moderation_failed_at` (nullable), `rejected_at` (nullable), `search_vector` (TSVECTOR), `published_by` FK (nullable, SET_NULL), `moderated_by` FK (nullable, SET_NULL).
- `apps/ads/models.py` — `AdImage`: `ad_id` FK, `image` (storage key, UUID v4 — no user/telegram PII in key, zone R6), `telegram_file_id` (nullable), `position` (INT).
- **Lifecycle-timer semantics (decision J / zone C3):** `published_at` is set on first `PUBLISHED`; every subsequent transition INTO `PUBLISHED` (reactivation, price/photo edits) resets the 2-month archive / 4-month delete timers. `original_published_at` is written once and is IMMUTABLE (audit only, never drives sweeps).
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

## Task 4: Moderation + Analytics Models

**Goal:** Moderation singleton, action log, and product analytics model.

**Acceptance Criteria:**
- `apps/moderation/models.py` — `ModerationCriteria` singleton (zone D3/D4): `title_min_length`, `title_max_length`, `description_min_length`, `description_max_length`, `price_required` (BOOL, default True), `min_images` (default 1), `max_images` (default 5), `banned_words` (JSONB `[]`), `max_ads_per_user` (default 10), `duplicate_title_threshold` (default 85), `updated_at`, `updated_by` (FK nullable SET_NULL). Exactly these fields (NO `min_price`/`max_price`).
- `apps/moderation/models.py` — `ModeratorActionLog`: `ad_id` FK (nullable, SET_NULL), `user_id` FK (nullable, SET_NULL), `action_type` (`ModeratorActionType`), `reason` (TEXT — NEVER shown to seller, US-A11), `created_at`.
- `apps/analytics/models.py` — `AnalyticsEvent`: `event_type` (`AnalyticsEventType`), `timestamp` (default now), `user_id` FK (nullable, SET_NULL on erasure, zone R1/R5).
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
- `GinIndex(name='IX_ads_search_gin', fields=['search_vector'])` applied (NOT `models.Index` — that would build a BTREE, zone D12).
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
- `IX_users_erasure_sweep`: `fields=['consent_revoked_at']` (zone R1).
- `IX_ads_archive_sweep`: partial `fields=['status','published_at']`, `condition=Q(status=AdStatus.PUBLISHED)` (zone C4).
- `IX_ads_delete_sweep`: partial `fields=['status','published_at']`, `condition=Q(status=AdStatus.ARCHIVED)` (zone C4).
- `IX_ads_purge_failed`: partial `fields=['status','moderation_failed_at']`, `condition=Q(status=AdStatus.ON_MODERATION_FAILED)` (7-day purge).
- `IX_ads_rejected_sweep`: partial `fields=['status','rejected_at']`, `condition=Q(status=AdStatus.REJECTED)` (90-day purge, zone D4).
- No standalone `price` index (added only after EXPLAIN ANALYZE, zone C7).

**Artifacts:** Index definitions in `Ad.Meta.indexes` + migration.
**Dependencies:** Task 2
**Risks:** Partial-index condition syntax.

---

## Task 7: Settings Security Configuration (TLS-ready)

**Goal:** Production-safe Django settings.

**Acceptance Criteria:**
- `SESSION_COOKIE_SECURE=True`, `CSRF_COOKIE_SECURE=True`, `SECURE_SSL_REDIRECT=True`, `SECURE_PROXY_SSL_HEADER=('HTTP_X_FORWARDED_PROTO','https')`, `USE_X_FORWARDED_HOST=True`.
- `CONN_MAX_AGE=0` (each process owns its pool; PgBouncer transaction-mode recommended, zone C5).
- `DEFAULT_FILE_STORAGE` uses Django's **built-in `FileSystemStorage` via the `STORAGES` setting** (local `MEDIA_ROOT` behind nginx in phase 1). The `STORAGES` contract allows a later swap to `django-storages` + S3/R2/MinIO **without code rewrites** — but `django-storages`/`boto3` are DEFERRED (YAGNI) per canonical `docs/wiki/02_packages.md`. Do NOT add those packages in phase 1.
- `psycopg[binary]>=3.2.0` pinned in `pyproject.toml`.

**Artifacts:** `config/settings.py`, `pyproject.toml`.
**Dependencies:** Task 1
**Risks:** Local dev vs prod settings drift (solve via env flags).

---

## Task 8: nginx + docker-compose Deployment

**Goal:** Media serving with security; migration-orchestration guard; async-safety.

**Acceptance Criteria:**
- `docker-compose.yml`: services `db` (postgres:17-alpine + healthcheck), `web` (gunicorn sync WSGI, mounts `media_volume`, depends_on db healthy, port 8000 NOT published), `bot` (same image, `python -m telegram_bot.main`, `media_volume`), `nginx` (ports 80/443, `media_volume` ro, proxy_pass → web:8000).
- **Migration guard:** migrations run exactly once before `web`+`bot` start (dedicated entrypoint step, not per-container, zone C5/D7).
- **Async safety (zone C5):** bot wraps ORM calls and Telegram photo downloads in `sync_to_async`; each process `CONN_MAX_AGE=0`.
- **nginx `/media/` security (zone R8):** `X-Content-Type-Options: nosniff`; whitelist `image/jpeg`, default `application/octet-stream`; `Content-Disposition: inline`; block script execution `location ~* /media/.*\.(php|py|cgi)$ { deny all; }`.
- `Dockerfile` (python:3.14-slim + uv, non-root USER, `collectstatic --noinput`).

**Artifacts:** `docker-compose.yml`, `docker/Dockerfile`, `docker/nginx.conf`, entrypoint.
**Dependencies:** Task 1
**Risks:** TLS misconfig; media path exposure; migration race.

---

## Task 9: Telegram Bot FSM Layer (aiogram 3.x)

**Goal:** Login via deep-link + step-by-step ad creation (US-S1, US-S2).

**Acceptance Criteria:**
- `telegram_bot/states.py`: `AdCreateState` — CATEGORY, CITY, TITLE, DESCRIPTION, PRICE, PHOTOS, PREVIEW.
- Login handler `/start login_<token>`: bot reads raw token from deep-link, computes SHA-256, atomically claims via `UPDATE login_tokens SET telegram_id=<tg> WHERE token_hash=? AND telegram_id IS NULL AND consumed_at IS NULL AND expires_at > now()`; web then consumes. Constant-time compare via `hmac.compare_digest` (zone C1).
- Category step: bot suggests TOP-3-5 by keyword, seller confirms from suggested tree or full tree; free-text-as-new-category rejected (decision I).
- Photo step: accept ONLY `message.photo` (compressed), reject `message.document`; validate JPEG (magic bytes / PIL), 1..5 photos, ≤2560px, ≤~2MB each; store via the **built-in `FileSystemStorage`** (deferred `django-storages` swap later) with UUID v4 key; keep `telegram_file_id` as metadata.
- On submit: status `DRAFT → ON_MODERATION`; runs auto-moderation (Task 10); preview shown before send with correction of city/category mapping (decision I).
- **Content language invariant (decision G):** before creating the ad, the bot translates seller-provided title/description from Bosnian (or other) to **Russian** using `deep-translator` + request cache, so `to_tsvector('russian', ...)` in `search_vector` is correct. Russian is the stored base language; display layer translates back for BOS UI (Phase 5). This step is mandatory — without it Bosnian tokens would corrupt the Russian FTS config.
- Draft idle timeout 30 min → auto-discard (zone C8); a background cleanup (`sweep_drafts`) removes orphaned FSM drafts (Phase 4 scheduler).
- Login tokens: expired/consumed tokens cleaned by the `cleanup_login_tokens` management command — **created in Phase 4 Task 2** (scheduler), referenced here for completeness (zone C1).
- `published_at` is set on first transition to `PUBLISHED`; every subsequent transition into `PUBLISHED` (reactivation, price/photo edits) **resets the 2/4-month lifecycle timers** (decision J / zone C3). `original_published_at` is set once and is immutable (audit only).
- Bot sets `django.setup()` + shared ORM; ORM/photo ops in `sync_to_async`.

**Artifacts:** `telegram_bot/states.py`, `telegram_bot/handlers/login.py`, `telegram_bot/handlers/ad_create.py`, `telegram_bot/services/media.py`, `telegram_bot/main.py`.
**Dependencies:** Tasks 2, 3, 4, 8
**Risks:** FSM timeout; token-claim race; photo validation bypass; sync/async mixing.

---

## Task 10: Auto-Moderation Service

**Goal:** Single automatic gate before publish (decision A / US-A10).

**Acceptance Criteria:**
- `apps/moderation/services/auto_moderation.py` reads `ModerationCriteria` singleton (cached 5 min).
- Validates: title/description min/max length; `price_required` → price present; photo count 1..`max_images`; case-insensitive `banned_words`; active ad count ≤ `max_ads_per_user`; duplicate-title via `difflib.ratio` ≥ `duplicate_title_threshold`.
- On fail: sets `moderation_failed_at`, status `ON_MODERATION_FAILED`, writes `ModeratorActionLog` (auto reason), returns structured error to bot (seller gets NO specific reason per US-A11).
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
- Templates `ads/list.html`, `ads/detail.html`: show title, description, price, photos, city, category (`get_name(locale)`), date; contact button only when allowed (decision C, refined in Phase 3).
- No login required to browse `PUBLISHED` ads. `uv run ruff check` passes; XSS-safe templates (`{% autoescape %}`/`escape`).

**Artifacts:** views, templates, `apps/search/services.py`.
**Dependencies:** Tasks 2, 3, 6
**Risks:** XSS; media security; translation fallback.

---

## Task 12: Documentation Updates (wiki sync)

**Goal:** Reconcile wiki with implemented decisions.

**Acceptance Criteria:**
- `docs/wiki/01_technical_specification.md`: decisions H, C, F, G, I, J reflected; US-S1/S2, US-B1/B2/B3/B6/B7, US-A1/A2/A3/A7/A10/A11.
- `docs/wiki/02_packages.md`: canonical stack (Django 5.2 LTS, psycopg3, aiogram 3.15, deep-translator, django-mptt 0.18, django-filter 26.1, django-tailwind 4.4, django-htmx, pillow; django-storages/boto3 deferred).
- `docs/wiki/03_structure.md`: deployment section complete (db/web/bot/nginx, migration guard, async safety).
- `docs/wiki/04_db_structure.md`: schema confirmed against implementation.

**Artifacts:** Updated wiki files (English-only per doc-maintenance-rules).
**Dependencies:** Tasks 1-11
**Risks:** Doc drift; non-English content (forbidden).
