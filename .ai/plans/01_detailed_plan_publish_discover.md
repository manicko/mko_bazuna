# Phase 1 Detailed Plan: Minimal Publish-to-Discover Flow

**Wave:** Foundation  
**Depends_on:** None  
**Files_modified:** `src/backend/`, `docs/wiki/*.md`  
**Autonomous:** Yes

---

## Task 1: Django Project Structure + StrEnums
**Goal:** Create constants module per rule 10.
**Acceptance Criteria:**
- `src/backend/apps/core/enums.py` with:
  - `AdStatus`: DRAFT, ON_MODERATION, PUBLISHED, REJECTED, ON_MODERATION_FAILED, ARCHIVED, DELETED
  - `AdSource`: TELEGRAM
  - `AnalyticsEventType`: REGISTRATION_CREATED, AD_PUBLISHED, SEARCH_PERFORMED, CONTACT_INITIATED
  - `ModeratorActionType`: REJECT, BAN_ACCOUNT, SOFT_DELETE, CRITERIA_CHANGE, OTHER
- All models import enums from `apps.core.enums`
**Artifacts:** `apps/core/enums.py`, `__init__.py` files
**Risks:** Import cycles, enum naming must match spec

---

## Task 2: Core Models (User, LoginToken, Ad, AdImage)
**Goal:** Authentication and ad models matching spec schema.
**Acceptance Criteria:**
- `users/models.py`: telegram_id (unique), username (nullable), is_staff, is_banned, is_deleted, ads_auto_publish, consent_given_at, consent_revoked_at, hard_delete_at
- `ads/models.py`: id, user_id, title, description, price, category_id, city_id, status, source, created_at, updated_at, published_at, original_published_at, archived_at, deleted_at, moderation_failed_at, rejected_at, search_vector (indexed), published_by/moderated_by FK nullable, category_name
- `login_tokens/models.py` (**standalone table per spec C1**): token_hash (CHAR(64), UNIQUE), telegram_id (nullable), created_at, expires_at, consumed_at
- `ad_images/models.py`: id, ad_id, telegram_file_id, image_url (UUID v4 key)
**Artifacts:** Model files with migrations
**Dependencies:** Task 1
**Risks:** telegram_id uniqueness, NULL FK semantics (audit trail), token_hash SHA-256 never stores raw

---

## Task 3: Categories + Locations Models (MPTT + JSONB i18n)
**Goal:** Reference data with hierarchy and i18n.
**Acceptance Criteria:**
- `categories/models.py`: name (Russian, required), `name_i18n` (JSONB, `{"ru": str, "bs": str}`), slug, MPTT fields (lft, rght, tree_id, level), is_active
- `locations/models.py`: name (Russian, required), `name_i18n` (JSONB), region, slug
- Seed data: BiH ~50-60 cities, ~15-20 categories
- `get_name(locale)` method with Russian fallback
**Artifacts:** Model files, `fixtures/bih_categories.json`, `fixtures/bih_cities.json`
**Dependencies:** Task 1
**Risks:** Seed data completeness, MPTT tree integrity, JSONB locale fallback

---

## Task 4: Moderation + Analytics Models
**Goal:** ModerationCriteria singleton + action log + analytics.
**Acceptance Criteria:**
- `moderation/models.py`: 
  - `ModerationCriteria` (singleton, editable at runtime per US-A11)
  - `ModeratorActionLog`: ad_id FK nullable, user_id FK nullable, action_type (ModeratorActionType), reason TEXT, created_at
- `analytics/models.py`: event_type (AnalyticsEventType), user_id nullable FK, metadata JSONB, created_at
**Artifacts:** Model files
**Dependencies:** Task 1
**Risks:** Singleton pattern, user erasure (SET NULL on Log)

---

## Task 5: PostgreSQL Triggers + GIN Index
**Goal:** search_vector function with category_name sync.
**Acceptance Criteria:**
- Trigger `sync_category_name()` fires on ads INSERT/UPDATE, writes Russian category name to `ads.category_name`
- Trigger `update_search_vector()` computes TSVECTOR from title + description + category_name
- GIN index `IX_ads_search_gin` on search_vector
- Migration applies triggers on PostgreSQL 17
**Artifacts:** `apps/ads/triggers.sql`, migration file
**Dependencies:** Tasks 2, 3
**Risks:** Trigger syntax, race conditions

---

## Task 6: Publication Indexes
**Goal:** Performance indexes.
**Acceptance Criteria:**
- `IX_ads_pub_listing`: partial B-tree on (status, category_id, city_id, published_at DESC) WHERE status='PUBLISHED'
- `IX_ads_search_gin`: GIN index via `django.contrib.postgres.indexes.GinIndex`
- `IX_users_erasure_sweep`: B-tree on users(consent_revoked_at) for 30-day hard delete
- `IX_ads_purge_failed`: index on ads(moderation_failed_at) for 7-day purge
- `IX_ads_rejected_sweep`: index on ads(rejected_at) for 90-day purge
**Artifacts:** Migration with index SQL
**Dependencies:** Task 2
**Risks:** Partial index syntax correctness

---

## Task 7: Settings Security Configuration
**Goal:** TLS-ready Django settings.
**Acceptance Criteria:**
- `SESSION_COOKIE_SECURE = True`
- `SECURE_SSL_REDIRECT = True`
- `SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')`
- `USE_X_FORWARDED_HOST = True`
- psycopg[binary]>=3.2.0 in pyproject.toml
**Artifacts:** `config/settings.py`, `pyproject.toml`
**Risks:** Local dev vs prod drift

---

## Task 8: nginx Configuration + docker-compose
**Goal:** Media serving with security.
**Acceptance Criteria:**
- nginx.conf: serves `/media/` with `X-Content-Type-Options: nosniff`, script execution blocked
- docker-compose.yml: services db, web, bot, nginx, shared `media_volume`
- TLS configuration (Certbot or self-signed)
- **Migration orchestration guard:** migrations run exactly once before web+bot start (dedicated entrypoint step, not per-container)
- **Async safety:** bot wraps ORM calls + Telegram photo downloads in `sync_to_async` (per spec C5)
- **Connection pooling:** per-process `CONN_MAX_AGE=0`; PgBouncer transaction-mode pool recommended for shared pooling
**Artifacts:** `docker/nginx.conf`, `docker-compose.yml`
**Dependencies:** Task 1
**Risks:** TLS misconfiguration, media path exposure

---

## Task 9: Telegram Bot FSM Layer
**Goal:** Login + ad publishing flow.
**Acceptance Criteria:**
- `telegram_bot/states/AdCreateState`: CATEGORY, CITY, TITLE, DESCRIPTION, PRICE, PHOTOS, PREVIEW
- Login handler: `/start login_<token>` with `hmac.compare_digest` atomic claim (per spec C1)
- Photo validation: reject documents, require JPEG (magic bytes), UUID v4 key generation
- Status: DRAFT → ON_MODERATION → PUBLISHED (auto) or ON_MODERATION_FAILED
- Draft cleanup: 30-min FSM idle timeout (zone C8)
**Artifacts:** `bot/states.py`, `bot/handlers/login.py`, `bot/handlers/ad_create.py`, `services/media.py`
**Dependencies:** Tasks 2, 3, 4
**Risks:** FSM timeout, atomic token claim race, photo validation bypass

---

## Task 10: Auto-Moderation Service
**Goal:** Validation before publish.
**Acceptance Criteria:**
- `services/moderation.py`: check_text_length, check_banned_words (case-insensitive), check_photo_count, check_user_ad_limit
- Reads `ModerationCriteria` singleton (cached)
- Sets `moderation_failed_at` on auto-fail
**Artifacts:** `services/moderation.py`, tests
**Dependencies:** Tasks 2, 4

---

## Task 11: Web Listing + Search Views
**Goal:** Public ad browsing.
**Acceptance Criteria:**
- AdListView: HTMX filter (category subtree, city with difflib did-you-mean, price range)
- Search: PostgreSQL FTS on `search_vector`, deep-translator Bosnian→Russian (Decision G)
- Templates: `ads/list.html`, `ads/detail.html`
**Artifacts:** views, templates
**Dependencies:** Tasks 2, 3, 6
**Risks:** XSS in templates, media security

---

## Task 12: Documentation Updates
**Goal:** Sync wiki with implemented decisions.
**Acceptance Criteria:**
- `docs/wiki/01_technical_specification.md`: Decision H, C, F, G, I, J
- `docs/wiki/02_packages.md`: django 5.1.2, psycopg[binary], aiogram 3.15.0, deep-translator
- `docs/wiki/03_structure.md`: Deployment section, services list
- `docs/wiki/04_db_structure.md`: Schema schema confirmed
**Artifacts:** Updated wiki files