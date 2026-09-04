# Mko Bazuna Backup Architecture Research (Updated 2026)

## Executive Summary

Mko Bazuna is a Telegram-driven classifieds board (Avito-like) built on Django 5.2 LTS with PostgreSQL 18 as the sole shared database for two long-lived processes: a gunicorn WSGI web server and an aiogram bot. The platform operates from a single-VPS Docker Compose deployment with compose project isolation (`mko-bazuna-dev` / `mko-bazuna-test`), GHCR pre-built image deployment in production, and a three-service startup gate (migrate → load_catalog → create_admin).

This document describes the current architecture with a focus on **what to back up and why**, the **current backup implementation gap**, and the **2026 best-practices recommendation** for closing it.

> **Recommendation:** The `pg_dump + Restic + Backblaze B2` stack remains the correct 2026 approach for this deployment. The old `research.md` (784 lines) described an implementation that was **never built**. The current backup service is a bare `postgres:18-alpine` container running daily `pg_dump -F c` with 7-day local-only retention — no Restic, no B2, no media backup, no encryption, no offsite storage. The updated plan treats the upgrade as **new work** against this actual baseline.

Key 2026 findings:

| Area | 2026 Verdict | Required Action |
|------|-------------|-----------------|
| PostgreSQL backup tooling | pg_dump still correct for sub-1 GB single-DB | Keep pg_dump; adopt `--format=custom --jobs=4 --no-owner --no-privileges --if-exists --clean` |
| Restic | v0.19.1 stable; native B2 backend deprecated | Upgrade to v0.19.1; use `s3:` S3-gateway at `s3.us-west-002.backblazeb2.com` |
| B2 backend | SSE-S3 + AES-256 client-side | Enable SSE-S3 on bucket; Restic already encrypts client-side |
| Cloud storage | B2 cheapest ($6.95/TB/mo) | Keep B2; switch to S3-compatible gateway |
| Media backup | 50–200 GB, dominates storage | Restic filesystem mode on `media_volume` mounted at `/app/media` |
| MinIO | **Dead** — archived 2026-04-25 | Remove all references; successors: SeaweedFS S3, Garage, RustFS, Ceph RGW |
| Secret management | File-mounted `RESTIC_PASSWORD_FILE` + `env_file` | Not Docker Swarm secrets (single-node compose) |
| Monitoring | Healthchecks.io alive | Add `hc-ping.com` UUID pings for backup job lifecycle |
| DB schema | 31 tables (27 app + 4 Django built-in) | Full GDPR/retention sweep picture must be captured |

---

## 1. Technology Stack

### Core Components

| Component | Technology | Version | Source |
|-----------|------------|---------|--------|
| **Backend** | Django | `>=5.2.16,<6.0` (5.2 LTS) | `pyproject.toml` line 5 |
| **Python** | Python | 3.14 | `pyproject.toml` line 1, `docker/Dockerfile` line 8 |
| **Database** | PostgreSQL | 18-alpine | `docker-compose.yml` line 7, `docker-compose.prod.yml` line 68 |
| **Telegram Bot** | aiogram | `>=3.15.0` | `pyproject.toml` line 18, `docker-compose.yml` line 168 |
| **WSGI Server** | gunicorn | `>=26.0` | `docker-compose.yml` line 141, Dockerfile CMD line 158 |
| **Static Files** | WhiteNoise | `>=6.12.0` | `pyproject.toml`, `config/settings/base.py` line 127 |
| **Containerization** | Docker + Compose | v2 syntax | `docker-compose.yml`, `Makefile` line 10 |
| **Image Registry** | GHCR | `ghcr.io/manicko/mko_bazuna` | `docker-compose.prod.yml` lines 7–26 |
| **Cache** | Redis | 7-alpine | `docker-compose.yml` line 22 |
| **Reverse Proxy** | nginx | alpine | `docker-compose.yml` line 197 |

### Supporting Technologies

| Technology | Purpose | Source |
|------------|---------|--------|
| django-mptt | Hierarchical category tree (MPTT) | `config/settings/base.py` line 105 |
| django-filter | Ad filtering on site | `pyproject.toml` |
| django-environ | Environment variable management | `config/settings/base.py` line 28 |
| psycopg[binary] | PostgreSQL driver (pre-compiled) | `pyproject.toml` (no gcc/libpq-dev needed) |
| deep-translator | Montenegrin → Russian translation for FTS | `pyproject.toml` |
| Pillow | Image processing (thumbnails, EXIF stripping) | `pyproject.toml` |
| pydantic | Validation layer at system boundaries | Project rule #11 |

### Infrastructure Services (Production profiles)

| Service | Profile | Image | Purpose |
|---------|---------|-------|---------|
| `scheduler` | `["scheduler"]` | `build: .` (Dockerfile) | Hourly GDPR sweeps + daily alerts via `entrypoint-scheduler.sh` |
| `backup` | `["backup"]` | Currently `postgres:18-alpine`; plan targets `Dockerfile.backup` | Daily DB dump + Restic → B2 |
| `pgbouncer` | `["pgbouncer"]` | `edoburu/pgbouncer:1.25.2` | Connection pooling (port 6432) |

**Source:** `docker-compose.yml` (9 base services — [CA §1.2]); `docker-compose.prod.yml` (6 prod additions — [CA §1.2]).

---

## 2. Data Storage

### 2.1 Database (PostgreSQL) — 31 Tables

The database is the **single source of truth** for all business logic. PostgreSQL 18 runs in `postgres:18-alpine` with named volume `postgres_data` mounted at `/var/lib/postgresql` ([CA §2.2], `docker-compose.yml` line 14). The full schema is documented in `docs/02-database/db-schema.md` (573 lines) with indexes in `db-indexes.md` and retention policies in `db-retention.md`.

**Table catalog — all 31 tables** (27 application tables from `apps/*/models.py` + 4 Django built-in tables):

#### User / Authentication (3 tables + 1 Django)

| Table | Key Columns | PII | Source |
|-------|-------------|-----|--------|
| `users` | `id`, `telegram_id` (BIGINT UNIQUE nullable), `chat_id` (BIGINT UNIQUE), `username`, `is_staff`, `is_superuser`, `is_banned`, `is_deleted`, `deleted_at`, `consent_given_at`, `consent_revoked_at`, `source`, `telegram_language`, `preferred_city_id` | Telegram ID, chat ID, username | `users/models.py` line 140 |
| `login_tokens` | `id`, `token_hash` (CHAR(64) UNIQUE), `telegram_id`, `created_at`, `expires_at` (+5min), `consumed_at` | SHA-256 hash only (raw token never stored) | `users/models.py` line 152 |
| `consent_records` | `id`, `user_id` (FK nullable SET_NULL), `choice` (StrEnum), `categories` (JSONB), `ip_address` (INET nullable), `user_agent` (TEXT nullable), `consented_at`, `revoked_at` | IP address, user agent (anonymous-only) | `users/models.py` line 194 |
| `django_sessions` | `session_key`, `session_data`, `expire_date` | Session data (transient) | Django built-in |

#### Core Content (4 tables)

| Table | Key Columns | PII | Source |
|-------|-------------|-----|--------|
| `ads` | `id`, `user_id`, `title`, `title_ru/en/bs`, `description`, `description_ru/en/bs`, `price_amount`, `price_currency` (EUR/RSD/BAM), `price_normalized_eur`, `category_id`, `city_id`, `category_name` (denormalized), `listing_purpose_id`, `listing_condition_id`, `status` (StrEnum), `source`, `published_at`, `original_published_at`, `archived_at`, `deleted_at`, `moderation_failed_at`, `rejected_at`, `search_vector`/`_ru/_en/_bs`, `published_by`, `moderated_by` | No direct PII; stores `user_id` FK | `ads/models.py` line 22 |
| `ad_images` | `id`, `ad_id`, `image` (UUID v4 key), `telegram_file_id`, `sha256`, `position`, `thumbnail_small/medium/large` | None (UUID v4 only, no user linkage) | `ads/models.py` line 510 |
| `ad_features` | `id`, `ad_id`, `feature_id`, `sort_order` | None | `ads/models.py` line 614 |
| `ad_favorites` | `id`, `user_id`, `ad_id`, `created_at` | None (FK only) | `ads/models.py` line 650 |

#### Category Reference (5 tables)

| Table | Key Columns | PII | Source |
|-------|-------------|-----|--------|
| `categories` | `id`, `name`, `name_i18n` (JSONB: ru/bs/en), `slug`, `parent_id`, `is_active` | None | `categories/models.py` line 12 |
| `category_paths` | `id`, `category_id`, `parent_id`, `sort_order`, `is_automatic` | None | `categories/models.py` line 67 |
| `category_listing_purposes` | `id`, `category_id`, `listing_purpose_id`, `is_default` | None | `categories/models.py` line 116 |
| `category_listing_features` | `id`, `category_id`, `feature_id` | None | `categories/models.py` line 155 |
| `category_listing_conditions` | `id`, `category_id`, `condition_id`, `is_default` | None | `categories/models.py` line 186 |

#### Locations (1 table)

| Table | Key Columns | PII | Source |
|-------|-------------|-----|--------|
| `cities` | `id`, `country_code`, `name`, `name_i18n` (JSONB), `region`, `slug` | None | `locations/models.py` line 10 |

#### Currency (1 table)

| Table | Key Columns | PII | Source |
|-------|-------------|-----|--------|
| `exchange_rates` | `id`, `currency` (CurrencyCode: EUR/RSD/BAM), `rate_to_eur` (DECIMAL(14,8)), `effective_date`, `source`, `is_current` | None | `currencies/models.py` line 15 |

#### Lookup / Reference Data (2 tables)

| Table | Key Columns | PII | Source |
|-------|-------------|-----|--------|
| `lookup_groups` | `id`, `code`, `name_i18n` (JSONB), `is_system`, `sort_order` | None | `lookups/models.py` line 11 |
| `lookup_items` | `id`, `group_id`, `slug`, `name_i18n` (JSONB), `sort_order`, `is_active`, `icon`, `color` | None | `lookups/models.py` line 43 |

#### Analytics (3 tables)

| Table | Key Columns | PII | Source |
|-------|-------------|-----|--------|
| `analytics_events` | `id`, `event_type` (StrEnum), `timestamp`, `user_id` (FK nullable SET_NULL), `ad_id` (FK nullable CASCADE), `source` (StrEnum nullable) | user_id FK (SET NULL on erasure) | `analytics/models.py` line 12 |
| `daily_ad_metrics` | `id`, `ad_id` (FK CASCADE), `date`, `views_count`, `contacts_count`, `trust_score`, `avg_response_time` | None (ad_id only) | `analytics/models.py` line 69 |
| `popular_searches` | `id`, `query`, `query_normalized`, `hit_count`, `last_seen`, `source` (StrEnum nullable) | Search query text (behavioral) | `search/models.py` line 13 |

#### Buyer Engagement (4 tables)

| Table | Key Columns | PII | Source |
|-------|-------------|-----|--------|
| `search_history` | `id`, `user_id` (FK CASCADE nullable), `query`, `query_normalized`, `created_at` | Search queries | `search/models.py` line 39 |
| `saved_searches` | `id`, `user_id` (FK CASCADE), `query`, `city_id`, `category_id`, `min_price`, `max_price`, `is_active`, `language`, `last_notified_at`, `unsubscribe_token` (VARCHAR(40), unique) | `unsubscribe_token` (opaque capability) | `search/models.py` line 63 |
| `ad_favorites` | *(see Core)* | | |
| `saved_search_notifications` | `id`, `saved_search_id`, `ad_id`, `sent_at` | None | `search/models.py` line 158 |

#### Seller Reputation (2 tables)

| Table | Key Columns | PII | Source |
|-------|-------------|-----|--------|
| `seller_trust_scores` | `id`, `user_id` (OneToOne CASCADE), `trust_level`, `score`, `ad_count_lifetime`, `ad_count_active`, `rejection_rate`, `contact_response_rate`, `last_calculated` | None | `trust/models.py` line 11 |
| `seller_verifications` | `id`, `user_id` (OneToOne CASCADE), `phone_number`, `verified_by_admin`, `verified_at` | **Phone number** (high-sensitivity PII) | `trust/models.py` line 37 |

#### Moderation (3 tables)

| Table | Key Columns | PII | Source |
|-------|-------------|-----|--------|
| `moderation_criteria` | `id`, `title_min/max_length`, `description_min/max_length`, `price_required`, `min/max_images`, `banned_words` (JSONB), `max_ads_per_user`, `duplicate_title_threshold`, `updated_at`, `updated_by` | None | `moderation/models.py` line 11 |
| `moderation_action_logs` | `id`, `ad_id` (FK nullable SET_NULL), `user_id` (FK nullable SET_NULL), `action_type` (StrEnum), `reason` (TEXT), `created_at` | user_id FK (SET NULL on erasure); reason text retained | `moderation/models.py` line 88 |
| `ad_moderation_priorities` | `id`, `ad_id` (OneToOne CASCADE), `base_score`, `priority_level`, `flags` (JSONB), `confidence_score`, `escalation_required` | None | `moderation/models.py` line 134 |

#### Django Built-in (4 tables)

| Table | Purpose | PII |
|-------|---------|-----|
| `django_migrations` | Schema version tracking | None |
| `django_admin_log` | Admin action log | User ID, object repr |
| `django_content_type` | Model type registry | None |
| `django_sessions` | Session storage | Session data (transient) |

**Total: 31 tables.** Source: `apps/*/models.py` `db_table` declarations (28 application models across 10 apps) + 3 Django standard tables (sessions, admin log, content types) + `django_migrations`. The old `research.md` §2.1 listed only 9 tables — missing all 22 tables ([AC §3.3] C1–C7).

**Note on moderation_action_logs table name:** The model class is `ModeratorActionLog` (`moderation/models.py` line 88) with explicit `db_table = "moderation_action_logs"` (line 127). The table name in the database is `moderation_action_logs`, not the Django default `moderatoractionlog`. The `current-architecture-report.md` §6.1 uses `moderatoractionlog` — the actual DB table follows the `db_table` declaration.

### 2.2 PII-Sensitive Fields

| Field | Table | PII Type | GDPR/Erasure Notes | Source |
|-------|-------|----------|-------------------|--------|
| `telegram_id` | `users` | Telegram user identifier | NULLified on consent withdrawal (zone F) | `db-schema.md` line 57 |
| `chat_id` | `users` | Telegram chat identifier | NULLified on consent withdrawal | `db-schema.md` line 58 |
| `username` | `users` | Public @username | NULLified on consent withdrawal | `db-schema.md` line 59 |
| `is_deleted` + `deleted_at` | `users` | Soft-delete flag | Phase 3: PII null; Phase 4: hard-delete after 30 days | `db-schema.md` line 62 |
| `token_hash` | `login_tokens` | SHA-256 hash | Raw token never stored; hash-only | `db-schema.md` line 84 |
| `ip_address` | `consent_records` | IP address | Anonymous-only (nullable); audit traceability | `db-schema.md` line 109 |
| `user_agent` | `consent_records` | User agent string | Anonymous-only (nullable) | `db-schema.md` line 110 |
| `phone_number` | `seller_verifications` | Phone number | CASCADE-deleted with user; high-sensitivity | `db-schema.md` line 550 |
| `unsubscribe_token` | `saved_searches` | 32-char opaque capability token | Not user PII; enables anonymous unsubscribe | `db-schema.md` line 456 |
| `query` | `search_history` | Search query text | Behavioral data; CASCADE with user | `db-schema.md` line 516 |
| `session_data` | `django_sessions` | Session contents | Transient; cleared on expiry | Django built-in |

**Full pg_dump contains all of the above.** Restic's AES-256 client-side encryption protects at-rest data; B2 SSE-S3 adds a second layer ([BP §8.1][BP §8.2]).

### 2.3 Media Files (Volume)

**Location:** `media_volume` Docker named volume → mounted at `/app/media` inside `web`, `bot`, and `seed` containers ([CA §2.1] lines 155–157, `docker-compose.yml` lines 160, 187, 133); mounted at `/media_volume:ro` in `nginx` for protected media serving ([CA §2.1] line 158, `docker-compose.yml` line 202).

**File naming:** UUID v4 + `.jpg` for originals; `<uuid>-small.jpg`, `<uuid>-medium.jpg`, `<uuid>-large.jpg` for thumbnails ([CA §2.4] lines 189–220, `media/services/thumbnails.py` lines 25–29).

**Security properties** ([CA §2.4]):
- UUID v4 keys — non-sequential, unpredictable, no `user_id`/`telegram_id`/`username` in filename (zone R6)
- JPEG-only — strict magic-byte validation (`\xff\xd8\xff`), max 2 MB, max 2560×2560 px (`telegram_bot/services/media.py` lines 19–27, 30–73)
- EXIF stripped on save via `ImageOps.exif_transpose()` + info dict cleanup (`media.py` lines 126–144)
- nginx serves `/protected-media/` as `internal` only, MIME whitelist `image/jpeg`, `default_type application/octet-stream`, `Content-Disposition: inline` (`docker/nginx/nginx.conf` lines 82–97)

**Thumbnail sizes:**
| Size | Dimensions | File key | Quality |
|------|-----------|----------|---------|
| SMALL | 240×180 | `<uuid>-small.jpg` | 85, JPEG, LANCZOS, progressive |
| MEDIUM | 640×480 | `<uuid>-medium.jpg` | 85, JPEG, LANCZOS, progressive |
| LARGE | 1280×960 | `<uuid>-large.jpg` | 85, JPEG, LANCZOS, progressive |

Source: `apps/media/services/thumbnails.py` lines 25–29; `ads/models.py` lines 540, 546, 552.

**Estimated volume:** ~50–200 GB originals + 3× thumbnails ≈ 150 GB additional ([CA §2.4] line 218, `[BP §4.3]` research). Media files dominate storage; Restic's per-file deduplication is the correct backup approach ([BP §4.3]).

### 2.4 Static Files

- **Location:** `/app/staticfiles` inside the container ([CA §2.5], `config/settings/base.py` line 194)
- **Content:** Compiled Tailwind CSS output, Django `collectstatic` output
- **Generated at build time:** `manage.py collectstatic --noinput` in Dockerfile STAGE 1 (line 77) ([CA §1.5])
- **Served by:** WhiteNoise middleware (`base.py` line 127) + nginx with 30d cache + `Cache-Control: public, immutable` (`nginx.conf` lines 55–70)
- **Backup classification:** 🔴 Reconstructible from source — NOT critical for backup ([CA §2.5] line 236)

### 2.5 Configuration

**`.env.docker` (runtime, gitignored)** — 43 lines ([CA §4.3]). Contains: `DJANGO_SECRET_KEY`, `DEBUG`, `ALLOWED_HOSTS`, `POSTGRES_USER=bazuna_user`, `POSTGRES_DB=bazuna_db`, `POSTGRES_PASSWORD`, `REDIS_URL`, `BOT_USERNAME`, `BOT_TOKEN`, `SITE_URL`, `IMMEDIATE_ALERTS_ENABLED`, `PLAUSIBLE_HOST`, `TLS_CERT_PATH`, `ADMIN_*`, `SEED_USERS`, `SEED_ADS`, `FIX_PERMISSIONS`, `SKIP_ENV_CHECK`. Does **not** contain `DATABASE_URL` (compose constructs it from `POSTGRES_*` — [CA §4.3] line 328) or any backup/Restic/B2 variables ([CA §4.3] line 349: "No `B2_KEY_ID`, `RESTIC_PASSWORD`, or `HEALTHCHECK_UUID`").

**`.env.docker.example` (committed template)** — 73 lines, 23 variables ([CA §4.1] line 312). The stale 25-line template at `.ai/plans/server_backup/.env.docker.example` with 6 obsolete backup variables was never merged ([CA §4.7] line 421–434, [AC §3.2] B1).

**Env flow:**
1. `Makefile` passes `--env-file .env.docker` to compose for dev targets ([CA §4.4] line 353, `Makefile` line 10)
2. Each service binds `.env.docker` as `src/.env:ro` via `volumes: - ./.env.docker:/app/src/.env:ro` (`docker-compose.yml` lines 51, 78, 104, 159, 186)
3. Django reads via `django-environ`: `env.read_env(BASE_DIR / ".env")` where `BASE_DIR` = `src/backend` (`base.py` line 28)
4. Compose interpolates `${POSTGRES_DB}` etc. from `.env.docker` via `--env-file` + `env_file:` ([CA §4.4] lines 357–358)

---

## 3. Deployment Architecture

### 3.1 Services and Startup Chain

The platform has **9 base services** in `docker-compose.yml` plus **7 production additions** in `docker-compose.prod.yml` ([CA §1.2]).

**Base services (`docker-compose.yml`):**

| Service | Image/Build | Command | Profile | Depends On |
|---------|-------------|---------|---------|------------|
| `db` | `postgres:18-alpine` | *(default)* | — | — |
| `redis` | `redis:7-alpine` | `redis-server --save "" --appendonly no` | — | — |
| `migrate` | `build: .` (Dockerfile) | `migrate_locked.main()` + `setup_search_triggers` + `load_exchange_rates` | — | `db` (healthy) |
| `load_catalog` | `build: .` | `entrypoint-catalog.sh` → `load_catalog --no-rewrite` | — | `migrate` (completed), `redis` (healthy) |
| `create_admin` | `build: .` | `entrypoint-create-admin.sh` | — | `load_catalog` (completed) |
| `seed` | `build: .` | `entrypoint-seed.sh` | `["seed"]` | `load_catalog` (completed) |
| `web` | `build: .` | `gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers 3` | — | `load_catalog` (completed), `redis` (healthy) |
| `bot` | `build: .` | `python -m telegram_bot.main` | — | `load_catalog` (completed), `redis` (healthy) |
| `nginx` | `nginx:alpine` | *(default)* | — | `web` |

**Production overrides (`docker-compose.prod.yml`):**

| Service | Image | Profile | Notes |
|---------|-------|---------|-------|
| `web` | GHCR `${REGISTRY}/${REPOSITORY}:${IMAGE_TAG}` | — | Replaces `build:` → forces `pull` |
| `bot` | GHCR | — | Same pattern |
| `migrate` | GHCR | — | Same pattern |
| `create_admin` | GHCR | — | Same pattern |
| `seed` | GHCR | `["seed"]` | Same pattern |
| `nginx` | volumes override | — | Adds `${TLS_CERT_PATH:-/etc/nginx/certs}:/etc/nginx/certs:ro` |
| `scheduler` | `build: .` | `["scheduler"]` | `entrypoint-scheduler.sh`, hourly sweeps |
| `backup` | Currently `postgres:18-alpine` | `["backup"]` | **Target:** upgrade to `Dockerfile.backup` |
| `pgbouncer` | `edoburu/pgbouncer:1.25.2` | `["pgbouncer"]` | Port 6432 |

**Startup dependency chain** ([CA §1.4]):

```
db (healthy, pg_isready)
  → migrate (one-shot, advisory lock ID 100, exits 0)
    → load_catalog (one-shot: categories.yaml → DB)
      → create_admin (one-shot: skipped if ADMIN_PASSWORD empty)
        → seed (one-shot, dev auto-starts via profiles:!reset [])
→ redis (healthy)
→ web (gunicorn, 3 workers, long-lived)
→ bot (aiogram, long-lived)
```

Production deploy: `docker compose --env-file .env.docker -f docker-compose.yml -f docker-compose.prod.yml up -d` then `docker compose run --rm migrate` ([CA §1.4] line 91, `docs/ops/docker-deployment.md` lines 271–275).

### 3.2 Volumes

| Volume | Mounted By | Mount Path | Mode | Source |
|--------|-----------|------------|------|--------|
| `postgres_data` | `db` | `postgres_data:/var/lib/postgresql` | read-write | `docker-compose.yml` line 14 |
| `media_volume` | `web` | `media_volume:/app/media` | read-write | `docker-compose.yml` line 160 |
| `media_volume` | `bot` | `media_volume:/app/media` | read-write | `docker-compose.yml` line 187 |
| `media_volume` | `seed` | `media_volume:/app/media` | read-write | `docker-compose.yml` line 133 |
| `media_volume` | `nginx` | `media_volume:/media_volume:ro` | read-only | `docker-compose.yml` line 202 |
| `./backups` | `backup` | `./backups:/backups` | read-write | `docker-compose.prod.yml` line 76 |

**Dev override bind-mounts:** `web` and `bot` additionally bind-mount `.:/app` ([CA §2.1] line 160; `docker-compose.dev.override.yml`).

**Compose project isolation:** Named volumes are project-prefixed at runtime — `mko-bazuna-dev_postgres_data` vs `mko-bazuna-test_postgres_data` ([CA §1.3] line 74). The Makefile sets `COMPOSE_PROJECT_NAME` via target-specific exports (`Makefile` lines 17–22); `Makefile.ps1` uses equivalent variables (`$DevProject = "mko-bazuna-dev"`, line 15) ([CA §1.3]).

### 3.3 Redis (Shared Cache)

- **Image:** `redis:7-alpine` (`docker-compose.yml` line 22, [CA §2.3])
- **Command:** `redis-server --save "" --appendonly no` — **ephemeral, no persistence** ([CA §2.3] line 172, `docker-compose.yml` line 24)
- **No persistence volumes** defined ([CA §2.3])
- **Shared across:** `web` (3 gunicorn workers), `bot`, `scheduler` via `REDIS_URL=redis://redis:6379/0` ([CA §2.3] line 174)
- **Used for:** django-redis shared cache, rate-limit counters across gunicorn workers + bot
- **Dev/test override:** `REDIS_URL=` (empty) → falls back to `LocMemCache` (`config/settings/base.py` line 257, [CA §2.3])

Redis is **not backed up** — it is an ephemeral cache. On restart, cache warms from PostgreSQL. The old `research.md` §3.1 omitted Redis entirely ([AC §3.1] A6).

### 3.4 Network Flow

1. **External request** → nginx (ports 80/443, [CA §2.1] line 158, `docker-compose.yml` lines 199–200)
2. **HTTP→HTTPS redirect** on port 80 (`nginx.conf` lines 27–31, [CA §8.1])
3. **Static files** → nginx → `/static/` → proxy → `web:8000` → WhiteNoise (served from `/app/staticfiles`, [CA §2.5])
4. **Media files** → nginx → `/protected-media/` → `internal;` → alias `/media_volume/` (served from `media_volume`, access-controlled by Django per-request — [CA §2.4] lines 158, 223–225, `nginx.conf` lines 73–79, 82–97)
5. **Dynamic requests** → nginx → proxy → `web:8000` (gunicorn, [CA §3.1] line 247)
6. **Telegram webhook/polling** → `bot` (aiogram, [CA §3.2] line 254)
7. **Both processes** → shared `db` (PostgreSQL 18, `postgres_data` volume) + shared `redis` ([CA §3.1] line 247)

### 3.5 Multi-Stage Dockerfile

**File:** `docker/Dockerfile` — 3 stages ([CA §1.5]):

| Stage | FROM | Purpose | Key Steps |
|-------|------|---------|-----------|
| `builder` (STAGE 1) | `python:3.14-slim` | Install deps, build Tailwind/CSS, collectstatic | `uv sync` into `/opt/venv`; Tailwind CLI; `collectstatic`; `compilemessages` for ru/bs/en |
| `runtime` (STAGE 2) | `python:3.14-slim` | Production image: non-root, minimal | Copy venv; non-root uid 1000; `VOLUME ["/app/media"]`; `HEALTHCHECK` curl `/health/`; `ENTRYPOINT ["/app/entrypoint.sh"]` |
| `test-runtime` (STAGE 3) | `runtime AS test-runtime` | Test image with dev deps | Copy `uv`/`uvx`; `uv sync --group dev` for pytest/ruff/basedpyright |

Source: `docker/Dockerfile` lines 1–173 ([CA §1.5]).

### 3.6 Sourced Entrypoint Pattern

`docker/entrypoint.sh` defines shared functions (`check_env_file`, `fix_volume_permissions`, `wait_for_db`, `wait_for_redis`, `compile_messages`) but only **executes** them when run directly — not when sourced:

```bash
if [ "${BASH_SOURCE[0]}" = "$0" ]; then
    check_env_file
    fix_volume_permissions
    wait_for_db
    wait_for_redis
    compile_messages
    exec "$@"
fi
```

`BASH_SOURCE[0] = $0` guard ensures sourcing (e.g., by `entrypoint-seed.sh`, `entrypoint-catalog.sh`, `entrypoint-create-admin.sh` at their line 10) loads only function definitions; the caller invokes them explicitly ([CA §1.6] lines 380–408).

`entrypoint-scheduler.sh` does NOT source `entrypoint.sh` — it redefines `check_env_file()` inline with hardcoded path `/app/src/.env` (line 8), then runs the inline Python scheduler loop ([CA §4.6] line 410).

`entrypoint-test.sh` (lines 1–44): `unset UV_NO_INSTALL_PROJECT`, `uv sync --frozen --no-install-project --group dev`, runs migrate/setup_search_triggers/load_exchange_rates, then pytest with `PYTEST_SKIP_MARKERS` → `-m "not (seed)"` handling ([CA §4.6] lines 412–420).

### 3.7 Healthchecks

| Component | Command | Interval | Source |
|-----------|---------|----------|--------|
| `web` (Dockerfile) | `curl -f http://localhost:8000/health/` | 30s / 10s timeout / 5× retry | `docker/Dockerfile` lines 154–155 |
| `bot` (compose) | `kill -0 1 2>/dev/null \|\| exit 1` | 30s / 10s / 3× retry / 30s start | `docker-compose.yml` lines 189–194 |
| `db` (compose) | `pg_isready -U ${POSTGRES_USER} -d ${POSTGRES_DB}` | 5s / 5s / 5× retry | `docker-compose.yml` lines 15–19 |
| `redis` (compose) | `redis-cli ping` | 5s / 3s / 5× retry | `docker-compose.yml` lines 25–29 |
| `pgbouncer` (prod) | `pg_isready -h localhost -p 6432` | 5s / 5s / 5× retry | `docker-compose.prod.yml` lines 115–119 |

### 3.8 Scheduler (Hourly GDPR Sweeps)

- **File:** `docker/entrypoint-scheduler.sh` (lines 21–65) — inline Python loop ([CA §3.3] line 263)
- **Profile:** `["scheduler"]` (prod compose line 62, [CA §1.2])
- **Hourly commands** (every 3600s, advisory-locked — [CA §3.3] lines 267–275):
  - `archive_sweep` — archive PUBLISHED ads older than 60 days
  - `delete_sweep` — hard-delete ARCHIVED ads older than 120 days
  - `consent_hard_delete` — hard-delete user PII 30 days after consent withdrawal
  - `sweep_drafts` — delete DRAFT ads older than 7 days
  - `cleanup_login_tokens` — remove expired login tokens (+5 min expiry)
  - `purge_failed_ads` — delete ON_MODERATION_FAILED older than 7 days
  - `purge_rejected_ads` — delete REJECTED older than 90 days
  - `purge_deleted_ads` — hard-delete DELETED-status ads older than 120 days

All gated by PostgreSQL advisory locks (`AdvisoryLockId` in `apps/core/enums.py` lines 23–41 — [CA §3.3] line 279). The scheduler also runs `send_alerts` daily at 08:00 UTC ([CA §3.3] line 277).

---

## 4. Failure Points and Critical Data

### 4.1 Critical Failure Scenarios

| Scenario | Impact | Recovery Priority | Data at Risk | Mitigation |
|----------|--------|-------------------|--------------|------------|
| **PostgreSQL volume corruption** | Complete data loss | HIGH (immediate) | All database data (31 tables) | Daily pg_dump + Restic → B2; pg_dump with `--clean --if-exists` for idempotent restore |
| **Media volume loss** | Missing ad photos | HIGH | All uploaded images (~50–200 GB) | Restic backup of `media_volume` at `/app/media` to B2 ([CA §5.1] §Gaps: currently NOT backed up) |
| **`.env.docker` leak** | Security breach, session invalidation | HIGH | `DJANGO_SECRET_KEY`, `BOT_TOKEN`, `POSTGRES_PASSWORD` | File is gitignored (`.gitignore` line 148, [CA §4.3]); never commit; B2 keys scoped to bucket only |
| **Restic password loss** | Unrecoverable backups | CRITICAL | Entire Restic repository | Store password in password manager *and* host file `/opt/mko-bazuna/secrets/restic_repo_key` with `chmod 600` ([BP §4.2], [BP §6.3]) |
| **Disk full on DB volume** | Write failures, DB crash | HIGH | All pending transactions | Monitor disk space; `backups/` is gitignored (`.gitignore` line 239, [CA §5.4]) |
| **Corrupted backup** | Restore impossible | HIGH | Backup integrity | `pg_restore --list` verification post-dump; weekly `restic check --read-data-subset=1/7` ([BP §4.1]); no such verification in current service ([CA §5.1] §Gaps) |
| **B2 bucket misconfiguration** | Backup fails silently | MEDIUM | Offsite copies | Test bucket access during setup (`plan_updated.md` Task 1.2); SSE-S3 enabled at creation |
| **GDPR sweep deletes data during backup** | Inconsistent backup state | LOW | Transient inconsistency | Schedule backup after 08:00 UTC daily sweep window; advisory locks prevent mid-sweep interference ([CA §3.3], `db-retention.md` line 124–126) |

### 4.2 Critical Data Classification

#### 🔴 CRITICAL (Must backup daily)

| Data | Reason | Backup Method | Volume |
|------|--------|--------------|--------|
| **PostgreSQL database** | All business logic, users, ads, analytics | `pg_dump --format=custom --jobs=4` → Restic → B2 | ~200 MB – 1 GB |
| **Media files** | Ad photos (primary value store) | Restic filesystem mode on `media_volume` (`/app/media`) | ~50–200 GB + 3× thumbnails (~150 GB) |

#### 🟡 IMPORTANT (Daily backup, lower frequency acceptable)

| Data | Reason | Backup Method | Volume |
|------|--------|--------------|--------|
| `.env.docker` | Runtime secrets (DB creds, bot token, Django key) | Manual offsite (password manager / encrypted file) | < 1 KB |
| `django_migrations` | Schema version tracking | Part of full pg_dump | < 1 MB |
| `django_admin_log` | Admin action audit | Part of full pg_dump | < 10 MB |

#### 🟢 RECONSTRUCTIBLE (No backup needed)

| Data | Recovery Method |
|------|-----------------|
| Source code, Dockerfiles, entrypoint scripts | Git repository |
| `nginx.conf` | Git repository (`docker/nginx/nginx.conf`) |
| `docker-compose*.yml` | Git repository |
| Static files (`/app/staticfiles`) | `collectstatic` at build time ([CA §2.5] line 231) |
| Python dependencies | `uv.lock` + `uv sync` |
| Redis cache | Ephemeral; warms from PostgreSQL on restart ([CA §2.3]) |
| TLS certificates | Re-issue via Let's Encrypt/ACME or external CA |
| `django_content_type` / `django_sessions` | `migrate --run-syncdb` recreates content types; sessions are transient |

### 4.3 Data Growth Projections

| Entity | Projected Volume (Year 1) | Storage Impact |
|--------|---------------------------|----------------|
| Database (31 tables) | 200 MB – 1 GB (compressed dump ~300 MB) | ~300 MB per daily backup |
| Users | 10,000–50,000 | ~10 MB |
| Ads | 30,000–100,000 | ~200 MB |
| Photos | 50,000–200,000 originals | **50–200 GB** |
| Thumbnails | 3× photos | ~150 GB additional |
| Analytics events | High-volume append | Grows with traffic; SET NULL on user erasure |

---

## 5. Current Backup Implementation

### 5.1 Docker Compose Backup Service

**File:** `docker-compose.prod.yml` lines 65–97 ([CA §5.1])

```yaml
backup:
  image: postgres:18-alpine
  environment:
    POSTGRES_HOST: db
    POSTGRES_PORT: 5432
    POSTGRES_DB: ${POSTGRES_DB:?POSTGRES_DB must be set}
    POSTGRES_USER: ${POSTGRES_USER:?POSTGRES_USER must be set}
    PGPASSWORD: ${POSTGRES_PASSWORD:?POSTGRES_PASSWORD must be set}
  volumes:
    - ./backups:/backups
  command:
    - /bin/sh
    - -c
    - |
      set -e;
      until pg_isready -h $$POSTGRES_HOST -p $$POSTGRES_PORT; do sleep 5; done;
      while true; do
        date=$$(date +%Y%m%d);
        pg_dump -h $$POSTGRES_HOST -p $$POSTGRES_PORT
          -U $$POSTGRES_USER -d $$POSTGRES_DB -F c
          -f /backups/dump_$$date.dump;
        echo "Backup completed: dump_$$date.dump";
        find /backups -name 'dump_*.dump' -mtime +7 -delete 2>/dev/null || true;
        sleep 86400;
      done
  depends_on:
    db:
      condition: service_healthy
  restart: unless-stopped
  profiles:
    - backup
```

**Characteristics** (all confirmed against source — [CA §5.1]):

| Property | Current State |
|----------|---------------|
| Image | `postgres:18-alpine` (line 68) — standalone PostgreSQL client only |
| pg_dump flags | `-F c` only (line 86) — no `--jobs`, `--no-owner`, `--no-privileges`, `--if-exists`, `--clean` |
| Media backup | **NONE** — `media_volume` not mounted ([CA §5.1] §Gaps) |
| Offsite storage | **NONE** — only local `./backups/` volume mount |
| Encryption | **NONE** — plain `pg_dump` output |
| Verification | **NONE** — no `pg_restore --list` check |
| Secrets management | **NONE** — no Docker `secrets:`, no vault |
| Monitoring | **NONE** — no Healthchecks.io |
| Profile | `profiles: ["backup"]` (line 96) — opt-in via `--profile backup` |
| Schedule | `while true; ...; sleep 86400` — daily loop, starts at container launch ([CA §5.1] line 89) |
| Output filename | `dump_YYYYMMDD.dump` (date-stamped, no timestamp) |
| Local retention | `find /backups -name 'dump_*.dump' -mtime +7 -delete` (7-day via `find -mtime +7`) |
| Format | `pg_dump -F c` (custom format, compressed) |

### 5.2 Makefile Backup Targets

**File:** `Makefile` lines 216–245 ([CA §5.2])

```makefile
BACKUPNS_DIR := ./backups

backup:
    @mkdir -p $(BACKUP_DIR)
    @TIMESTAMP=$$(date +%Y%m%d_%H%M%S) && \
        docker compose $(ENV_FILE) -f docker-compose.yml exec -T db \
            pg_dump -U $${POSTGRES_USER} -d $${POSTGRES_DB} -F c \
            > $(BACKUP_DIR)/dump_$${TIMESTAMP}.dump && \
        echo "✓ Backup created: $(BACKUP_DIR)/dump_$${TIMESTAMP}.dump"
    @$(MAKE) prune-backups

restore:
    @if [ -z "$(BACKUP_FILE)" ]; then ... exit 1; fi
    @if [ ! -f "$(BACKUP_FILE)" ]; then ... exit 1; fi
    docker compose $(ENV_FILE) -f docker-compose.yml exec -T db \
        pg_restore -U $${POSTGRES_USER} -d $${POSTGRES_DB} --clean --if-exists $(BACKUP_FILE)
    @echo "✓ Restore completed from $(BACKUP_FILE)"

prune-backups:
    @find $(BACKUP_DIR) -name "dump_*.dump" -mtime +7 -delete -print
    @echo "✓ Old backups (older than 7 days) pruned"
```

**PowerShell equivalents** (`Makefile.ps1` lines 222–289 — [CA §5.3]): `Invoke-Backup`, `Invoke-Restore`, `Invoke-PruneBackups` with platform-specific differences (uses `CreationTime` vs `find -mtime`, `Remove-Item -Force`, no auto-prune in `Invoke-Backup`).

**Key detail:** `make backup` targets the dev project (`COMPOSE_PROJECT_NAME=mko-bazuna-dev` — `Makefile` line 17) and runs pg_dump via `docker compose exec -T db` against the dev `db` container. It does NOT use the backup service from `docker-compose.prod.yml`.

### 5.3 Gaps in Current Implementation

| Gap | Risk | Current Mitigation | Plan Target |
|-----|------|-------------------|-------------|
| **No media backup** | 🔴 Photo loss = business impact | None | `plan_updated.md` Task 3.1 (restic backup `/app/media`) |
| **No offsite storage** | 🔴 Single-point failure (VPS disk) | None | Restic → B2 S3 gateway (`plan_updated.md` Task 1.2) |
| **No backup verification** | 🔴 Corrupted backups undetected | None | `plan_updated.md` Task 3.3 (verify-backup.sh) |
| **No pre-restore safety** | 🟡 Accidental restore | None | `CONFIRM_RESTORE=yes` in restore.sh (`plan_updated.md` Task 3.2) |
| **No encryption** | 🔴 Plaintext dump on disk + local volume | None | Restic AES-256 + B2 SSE-S3 (`plan_updated.md` Tasks 1.2, 3.1) |
| **No monitoring** | 🔴 Silent backup failures | None | Healthchecks.io ping (`plan_updated.md` Tasks 1.1, 3.1) |
| **No secret backup** | 🔴 Cannot restore config | None | Document `.env.docker` + restic password backup (`plan_updated.md` Task 5.2) |
| **pg_dump flags suboptimal** | 🟡 Permission conflicts on restore | `-F c` only | `--format=custom --jobs=4 --no-owner --no-privileges --if-exists --clean` (`plan_updated.md` Task 3.1) |
| **No GDPR sweep coordination** | 🟡 Backup may capture pre-sweep PII | None | Schedule after 08:00 UTC sweeps (`plan_updated.md` §Advisory #4) |

### 5.4 `.gitignore` — backups directory

```gitignore
# PostgreSQL backup dumps — may contain PII from `make backup`
backups/
```

Confirmed at `.gitignore` line 239. The entire `backups/` directory is gitignored — backup dumps are **never committed** ([CA §5.4]). The `secrets/` directory does not exist (audit confirmed — no `secrets/` dir on filesystem).

### 5.5 `docs/ops/restore.md` (176 lines)

The current restore runbook (`docs/ops/restore.md`) has 3 sections:

1. **Automated Backup Service** (lines 27–40): describes the `postgres:18-alpine` container, `pg_dump -F c`, `dump_YYYYMMDD.dump` naming, 7-day prune
2. **Manual Backup** (lines 42–50): `make backup` → `dump_YYYYMMDD_HHMMSS.dump`
3. **Restore Procedure** (lines 52–133): identify file → stop web/bot → `pg_restore --clean --if-exists` → restart

**Known bug (line 104–105):** The manual restore example hard-codes `-U postgres -d postgres`, but the actual `.env.docker` uses `bazuna_user` / `bazuna_db` ([CA §5.5] line 573, [AC §3.4] D6). The Troubleshooting section (lines 135–155) even says "The default is `postgres`" — this is incorrect.

**Missing sections:** No media restore, no Restic restore, no offsite recovery procedure ([AC §3.4] D4).

---

## 6. What to Backup — Detailed Matrix

### 6.1 Database Backup Strategy

| Table/Data | Backup Method | RPO | RTO | Notes |
|------------|--------------|-----|-----|-------|
| **All 31 tables (full pg_dump)** | `pg_dump --format=custom --jobs=4 --no-owner --no-privileges --if-exists --clean` → Restic → B2 | 24h | < 1h | Daily, includes schema + data; `--clean --if-exists` for idempotent restore |
| `users` (telegram_id, chat_id, username) | Full dump (PII) | 24h | — | GDPR: soft-delete + 30-day purge; PII nullified on consent withdrawal |
| `login_tokens` (token_hash) | Full dump | 24h | — | SHA-256 hash only; raw token never stored |
| `consent_records` (ip_address, user_agent) | Full dump | 24h | — | Audit trail preserved; SET NULL on user erasure |
| `ads` + `ad_images` + `ad_features` | Full dump + media restic | 24h | — | Largest tables; media stored in `media_volume` (not DB) |
| `seller_verifications` (phone_number) | Full dump (high-sensitivity PII) | 24h | — | CASCADE-deleted with user on erasure |
| `saved_searches` (unsubscribe_token) | Full dump | 24h | — | Opaque capability token; not user PII |
| `categories` + `cities` + `lookup_*` | Full dump (reference data) | 24h | — | Static; loaded via `load_catalog` one-shot on fresh deploy |
| `exchange_rates` | Full dump | 24h | — | Seed data; `load_exchange_rates` one-shot reloads |
| `analytics_events` + `daily_ad_metrics` | Full dump | 24h | — | Append-heavy; SET NULL on user erasure |
| `moderation_criteria` + `moderation_action_logs` | Full dump | 24h | — | Compliance/audit required |
| `seller_trust_scores` + `ad_moderation_priorities` | Full dump | 24h | — | Derived data; recomputable but expensive |
| **Django built-in tables** | Full dump | 24h | — | `django_migrations` (schema tracking), `django_admin_log`, `django_content_type`, `django_sessions` |

**pg_dump command** (recommended flags from [BP §1.2]):
```bash
pg_dump -h db -p 5432 -U $POSTGRES_USER -d $POSTGRES_DB \
  --format=custom \
  --jobs=4 \
  --no-owner \
  --no-privileges \
  --if-exists \
  --clean \
  --verbose \
  --schema=public \
  -f /backups/db_$(date +%Y%m%d_%H%M%S).dump
```

**Why custom format with `--jobs=4`:** PostgreSQL 18's custom format (`-Fc`) is compressed and supports parallel dump/restore. For a ~1 GB database, this completes in under 30 seconds ([BP §1.2]). `--no-owner` and `--no-privileges` prevent permission conflicts on restore. `--if-exists --clean` ensures idempotent, clean restore targets.

### 6.2 Media Backup Strategy

| Content | Method | Frequency | Notes |
|---------|--------|-----------|-------|
| **Original photos** (`<uuid>.jpg`) | `restic backup /app/media` (filesystem mode) | Daily | ~50–200 GB; Restic per-file deduplication ([BP §4.3]) |
| **Thumbnails** (`<uuid>-small/medium/large.jpg`) | Included in media restic backup | Daily | 3× originals; regenerable from originals but cheap to back up with dedup |
| **Upload queue** | Part of `media_volume` | Daily | Stored in DB (`ad_images` table) |

**Approach:** Restic's native filesystem mode on the mounted `media_volume` at `/app/media` ([CA §2.1] lines 155–157). NOT `tar | restic --stdin` — that treats the entire archive as an opaque blob, defeating per-file deduplication ([BP §4.3] §Media Handling).

**Key detail:** Media files have NO PII in filenames (UUID v4 only — [CA §2.4] line 192). Media backup is safe for cloud storage without additional scrubbing.

### 6.3 Configuration Backup

| Item | Critical | Backup Location | Notes |
|------|----------|----------------|-------|
| `.env.docker` | 🔴 YES | Password manager (encrypted) + B2 encrypted bucket | Contains `DJANGO_SECRET_KEY`, `BOT_TOKEN`, `POSTGRES_PASSWORD` ([CA §4.3]); gitignored (`.gitignore` line 148) |
| TLS certificates | 🟡 Partial | ACME cache or re-issue via Let's Encrypt | `TLS_CERT_PATH=/etc/nginx/certs` ([CA §4.1]); re-issuable |
| `nginx.conf` | 🟢 NO | Git repository | `docker/nginx/nginx.conf` (tracked) |
| `docker-compose*.yml` | 🟢 NO | Git repository | All compose files are tracked ([CA §1.1]) |
| Restic password | 🔴 YES | Password manager + host file `/opt/mko-bazuna/secrets/restic_repo_key` | `chmod 600`; losing it = data unrecoverable ([BP §4.2]) |
| B2 application key | 🔴 YES | Password manager + B2 web console | Scoped to `mko-bazuna-backups` bucket only ([BP §8.3]) |

---

## 7. Recovery Procedures

### 7.1 Database Restore

**From Restic (offsite):**
```bash
# 1. List available snapshots
restic snapshots --repo $RESTIC_REPOSITORY

# 2. Stop write services (use correct prod compose files — CA §1.4)
docker compose --env-use .env.docker \
  -f docker-compose.yml -f docker-compose.prod.yml stop web bot

# 3. Restore DUMP from Restic snapshot to staging
restic restore <snapshot_id> --repo $RESTIC_REPOSITORY \
    --target /tmp/restore --include "backups/db_*.dump"

# 4. Restore DB (use .env.docker vars, NOT hard-coded postgres/postgres)
docker compose --env-file .env.docker \
  -f docker-compose.yml -f docker-compose.prod.yml exec -T db \
    pg_restore \
      --format=custom --jobs=4 \
      --no-owner --no-privileges --if-exists --clean \
      -U $POSTGRES_USER -d $POSTGRES_DB \
      /tmp/restore/backups/db_*.dump

# 5. Run migrations (advisory lock ID 100 — CA §3.3)
docker compose --env-file .env.docker \
  -f docker-compose.yml -f docker-compose.prod.yml run --rm migrate

# 6. Start services
docker compose --env-file .env.docker \
  -f docker-compose.yml -f docker-compose.prod.yml start web bot
```

**From local staging (`make restore`):**
```bash
make restore BACKUP_FILE=./backups/db_YYYYMMDD_HHMMSS.dump
# Internally: docker compose exec -T db pg_restore --clean --if-exists ...
```

**Critical considerations:**
- Use `${POSTGRES_USER}`/`${POSTGRES_DB}` from `.env.docker` (bazuna_user/bazuna_db), NOT hard-coded `postgres`/`postgres` (bug in current restore.md line 104 — [CA §5.5], [AC §3.4] D6)
- Use `docker compose --env-file .env.docker -f docker-compose.yml -f docker-compose.prod.yml` for prod, NOT root `docker-compose.yml` only ([AC §3.7] G2)
- `--clean --if-exists` ensures clean restore target; `--no-owner --no-privileges` prevents permission conflicts ([BP §1.2])

### 7.2 Media Restore

```bash
# 1. Stop write services
docker compose --env-file .env.docker \
  -f docker-compose.yml -f docker-compose.prod.yml stop web bot

# 2. Restore media from Restic snapshot
restic restore <snapshot_id> --repo $RESTIC_REPOSITORY \
    --target /tmp/restore --include "app/media/"

# 3. Copy restored files to media_volume (mounted inside web container)
docker compose --env-file .env.docker \
  -f docker-compose.yml -f docker-compose.prod.yml run --rm web \
    bash -c "cp -a /tmp/restore/app/media/. /app/media/ && \
             chown -R 1000:1000 /app/media"

# 4. Start services
docker compose --env-file .env.docker \
  -f docker-compose.yml -f docker-compose.prod.yml start web bot
```

**UID fix:** Files restored via `docker compose run --rm web` run as uid 1000 (non-root app user — `docker/Dockerfile` line 149, [CA §1.6]). The `chown -R 1000:1000` ensures correct ownership for the `VOLUME ["/app/media"]` ([CA §2.4]).

### 7.3 Offsite Recovery (Full DR)

New VPS with no existing data:

1. **Provision:** New VPS with Docker + Docker Compose + `/opt/mko-bazuna/secrets/restic_repo_key` (restic password file)
2. **Clone repo:** `git clone` the project, copy `.env.docker.example` → `.env.docker`, fill in production values + `B2_KEY_ID`/`B2_APP_KEY`/restic vars
3. **Start db:** `docker compose --env-file .env.docker -f docker-compose.yml up -d db redis`
4. **Restore DB:** Follow §7.1 (Restic → staging → `pg_restore` → `migrate`)
5. **Restore media:** Follow §7.2 (Restic → staging → copy to `media_volume`)
6. **Start services:** `docker compose --env-file .env.docker -f docker-compose.yml -f docker-compose.prod.yml up -d web bot nginx scheduler`
7. **Verify:** Healthcheck `curl -f http://localhost:8000/health/` passes ([CA §1.7])

---

## 8. Recommendations

### 8.1 Immediate (MVP)

1. **Upgrade backup service image** — Replace `postgres:18-alpine` with `docker/Dockerfile.backup` (Alpine + Restic 0.19.1) (`plan_updated.md` Task 2.1)
2. **Add media volume mount** — `media_volume:/app/media:ro` in backup service (`plan_updated.md` Task 2.3); path MUST be `/app/media`, not `/media` (bug in old plan — [AC §3.1])
3. **Replace inline script with backup.sh** — `scripts/backup.sh` using correct pg_dump flags (`--format=custom --jobs=4 --no-owner --no-privileges --if-exists --clean` — [BP §1.2])
4. **Add Restic → B2 offsite sync** — `s3:s3.us-west-002.backblazeb2.com/bucket` backend (NOT `b2:` scheme or `us-west-004` — [BP §3.3])
5. **Add B2 SSE-S3 encryption** — bucket-level server-side encryption ([BP §8.2])
6. **Add backup verification** — `pg_restore --list` post-dump + weekly `restic check --read-data-subset=1/7` ([BP §4.1])
7. **Add Healthchecks.io monitoring** — `curl -fsS --retry 3 https://hc-ping.com/$HEALTHCHECK_UUID` for start/success/fail ([BP §7.1])
8. **Add GDPR sweep coordination** — Schedule backup after 08:00 UTC daily sweep window ([CA §3.3], `db-retention.md` line 41)

### 8.2 Future (Production-grade)

| Feature | Implementation | Timeline |
|---------|---------------|----------|
| **`pg_dumpall --globals-only` monthly job** | Separate Restic-tagged snapshot for role/user definitions ([BP §1.3]) | Post-MVP |
| **B2 lifecycle rules** | Auto-transition to Glacier-style archival for snapshots > 90 days | Post-MVP |
| **Restic password rotation** | `restic key passwd` for periodic key rotation ([BP §4.2]) | Quarterly |
| **Automated DR testing** | Quarterly restore dry-run to ephemeral VPS (`plan_updated.md` Task 6.3) | Quarterly |
| **Self-hosted S3 successor** | If B2 egress costs exceed budget, deploy SeaweedFS S3 or Ceph RGW (MinIO is dead — archived April 2026, [BP §3.2]) | Future |
| **Backup cost alerting** | Monitor B2 usage via `b2 hide-file` lifecycle + Healthchecks.io threshold alerts | Future |
| **WAL archiving** | If RPO requirement shrinks below 24h, add `archive_mode=on` + `archive_command` to `db` service; consider WAL-G ([BP §5]) | Future (only if <24h RPO needed) |

---

## 9. Backup Storage Requirements (Estimation)

### 9.1 Daily Growth Estimates

| Component | Size per item | Projected items/day | Daily Growth |
|-----------|--------------|---------------------|-------------|
| Database dump (compressed, custom format) | ~300 MB | 1 (daily) | ~300 MB |
| Media originals | 1–3 MB avg | 50–200 photos/day | 50–600 MB |
| Media thumbnails (3×) | ~200 KB avg | 3× photos | ~150 MB |
| Analytics events | ~100 bytes | 10,000–50,000/day | ~5 MB |
| User/session data | negligible | 10,000–50,000/month | negligible |

### 9.2 Storage Planning (After Restic Deduplication)

| Retention Policy | Restic Storage (post-dedup) | Local Staging | Notes |
|------------------|----------------------------|---------------|-------|
| Daily (7 days) | DB: ~300 MB × 7 = 2.1 GB; Media: dedup saves ~90% → ~50 GB | `db_*.dump` for 2 days | [BP §4.1] retention: `--keep-daily 7` |
| Weekly (4 weeks) | DB: ~300 MB × 4 = 1.2 GB; Media: ~150 GB | — | `--keep-weekly 4` |
| Monthly (12 months) | DB: ~300 MB × 12 = 3.6 GB; Media: ~450 GB | — | `--keep-monthly 12` |
| Yearly (3 years) | DB: ~300 MB × 3 = 0.9 GB; Media: ~1.35 TB | — | `--keep-yearly 3` |
| **Total B2 estimate** | **~2 TB** (media-dominated, dedup-applied) | — | Restic deduplication on JPEGs is limited by content variance |

**Note:** Restic does not compress already-compressed JPEGs ([BP §4.3] §Large Media Handling). The 60 MB default chunking means most ad photos (1–3 MB) are stored as individual chunks with full deduplication on identical files only. For unique photos, effective dedup ratio on media is ~10–20%. DB dumps dedup well (schema is identical; only row data changes).

---

## 10. Security Considerations for Backup

### 10.1 Encryption at Rest

| Layer | Method | Key Management | Notes |
|-------|--------|---------------|-------|
| **Restic client-side** | AES-256 (repokey) | Password in `/opt/mko-bazuna/secrets/restic_repo_key` (`chmod 600`) | Restic encrypts before upload; B2 never sees plaintext ([BP §8.1]) |
| **B2 server-side** | SSE-S3 (S3-managed key) | B2 manages key | Defense-in-depth: protects against restic password compromise ([BP §8.2]) |
| **Local staging** | Filesystem permissions | `backups/` dir, gitignored | 2-day local retention; files owned by uid 1000 ([CA §5.4], `.gitignore` line 239) |

**What to avoid:**
- **SSE-C (customer-managed keys in B2):** Operational complexity (key rotation, key loss = permanent data loss) without meaningful security gain over SSE-S3 + Restic ([BP §8.4])
- **GPG-on-pg_dump:** Valid but redundant — Restic already encrypts the dump before upload ([BP §8.3])
- **LUKS/disk encryption:** Not applicable for cloud backend uploads; data is already encrypted by Restic before reaching the cloud

### 10.2 Secret Management for Single-VPS Docker Compose

**Current state:** The project uses `.env.docker` (gitignored) for env vars, bind-mounted as `src/.env:ro` into containers ([CA §4.4] lines 354–358). The backup service in `docker-compose.prod.yml` sets PostgreSQL credentials inline via `environment:` with `${VAR:?must be set}` guards ([CA §5.1] lines 69–74).

**2026 best practice (single-VPS)** ([BP §6.1][BP §6.3]):

| Secret | Storage Location | Access Pattern |
|--------|-----------------|----------------|
| `DJANGO_SECRET_KEY` | `.env.docker` (gitignored) | `env_file:` + bind-mount to `src/.env:ro` |
| `BOT_TOKEN` | `.env.docker` (gitignored) | Same as above |
| `POSTGRES_PASSWORD` | `.env.docker` (gitignored) | Compose interpolation `${POSTGRES_PASSWORD:?must be set}` |
| **Restic repository password** | Host file `/opt/mko-bazuna/secrets/restic_repo_key` (`chmod 600`) | Bind-mounted read-only to `/run/secrets/restic_repo_key`; `RESTIC_PASSWORD_FILE` env var points to mount path |
| **B2 application key** | `.env.docker` (gitignored) | `AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY` env vars, scoped to bucket |

**Docker Swarm secrets (`secrets:` block) are NOT applicable** — the project uses single-node Docker Compose, not Swarm mode ([BP §6.1], [AC §3.1] A3–A4). The old plan's `secrets: restic_pass: file: ./secrets/restic_pass.txt` pattern was never implemented and is inapplicable ([AC §3.1]).

**What to avoid:**
- **Inline passwords** in `docker-compose.yml`/`prod.yml` — risks `docker inspect` exposure ([BP §6.3])
- **Hardcoded passwords** in shell scripts within container images — the backup service must read from env/file, never embed credentials

### 10.3 PII Handling in Backups

A full `pg_dump` of all 31 tables contains:

| PII Class | Tables Affected | Protection | Erasure Coordination |
|-----------|----------------|------------|---------------------|
| Telegram identifiers | `users` (telegram_id, chat_id, username) | Restic AES-256 + B2 SSE-S3 | Soft-delete + 30-day `consent_hard_delete` sweep (advisory lock 3 — [CA §6.3]) |
| Phone numbers | `seller_verifications` (phone_number) | Same | CASCADE-delete with user on 30-day erasure |
| Login token hashes | `login_tokens` (token_hash) | Same | 5-minute expiry + `cleanup_login_tokens` sweep (advisory lock 5) |
| Consent records | `consent_records` (ip_address, user_agent) | Same | SET NULL on user erasure; audit trail preserved |
| Search queries | `search_history` (query), `saved_searches` (query) | Same | CASCADE-delete with user; `unsubscribe_token` is capability-only |
| Session data | `django_sessions` | Same | Transient; cleared on expiry |

**GDPR compliance:** The backup captures the full PII state at dump time. The scheduler's hourly sweeps ([CA §3.3]) progressively scrub PII (30-day consent hard-delete, 120-day deleted-ad purge, 90-day rejected purge, 7-day failed-moderation purge). A restore from a backup older than the retention window may re-introduce PII that was legally required to be deleted. This is an **inherent tension** in any logical-backup strategy — acceptable for this platform's RPO (24h, [CA §6.3] §10.2 in old research) given that sweeps run hourly and backups are daily.

---

## 11. Backup Tool Comparison for Small/Budget Projects (2026)

### 11.1 Tool Matrix

| Tool | Type | PITR | Cloud Storage | Incremental | Complexity | Notes |
|------|------|------|---------------|-------------|------------|-------|
| **pg_dump** | Logical | No | Via Restic/B2 | No (full) | Low | Built into PostgreSQL; current choice; portable |
| **pg_basebackup** | Physical | With WAL | Manual | No | Low-Medium | Built-in, consistent physical copy |
| **WAL-G** | Physical | Yes | S3/GCS/Azure/B2 | Delta pages | Low-Medium | Cloud-native; revived after April 2026 crisis ([BP §5.2]) |
| **pgBackRest** | Physical | Yes | S3/GCS/Azure | Block-level | Medium | Gold standard; coalition-funded ([BP §5.3]) |
| **Barman** | Physical | Yes | S3 + dedicated server | File-level (rsync) | Medium-High | Centralized; requires dedicated host |
| **Restic** | File-level | No (for DB) | 15+ backends (S3, B2, etc.) | Deduplication | Low | v0.19.1; AES-256; strong verification |
| **BorgBackup** | File-level | No | SSH/rsync.net | Deduplication | Low | Single-maintainer risk ([BP §11.2]) |
| **Duplicati** | File-level | No | 50+ backends | Deduplication | Low | .NET/Mono; GUI-first |

### 11.2 PostgreSQL-Specific Tools Analysis

#### pg_dump (Current Implementation)

**Pros:**
- Zero setup, built into PostgreSQL (already available via `postgres:18-alpine` — [CA §5.1] line 68)
- Portable format works across PostgreSQL major versions
- Understandable output (custom format can be inspected with `pg_restore --list`)
- Low CPU/memory overhead with `--jobs=4` parallel compression ([BP §1.2])

**Cons:**
- No point-in-time recovery (RPO = 24h)
- Full dump every time (no differential/incremental at DB level)
- Requires consistent filesystem state for media files (mitigated by Restic)

**Best for:** Small databases (<100 GB), simple needs, single-VPS deployments — exactly Mko Bazuna's profile.

#### WAL-G

**Status:** v3.0.8 (January 2026); project revived after the April 2026 crisis ([BP §5.2]).

**The April 2026 crisis:** WAL-G maintainer lost funding; Crunchy Data ended sponsorship. A 9-sponsor consortium (Percona, Severalnines, community) funded a full-time maintainer starting May 2026. v3.0.7 released June 2026; v3.0.8 current.

**Should Mko Bazuna adopt?** No ([BP §5.3]). WAL-G is designed for physical backup + PITR via WAL archiving — overkill for a single ~1 GB database where 24h RPO is acceptable.

#### pgBackRest

**Pros:** Best-in-class block-level incremental; comprehensive features; now coalition-funded.
**Cons:** More complex configuration; C language; overkill for small deployments.
**Verdict:** Correct choice for PITR-critical or >5 GB databases — not for Mko Bazuna.

#### Barman

**Pros:** Centralized multi-server management; EDB support.
**Cons:** Requires dedicated backup server; SSH key management; rsync-based (no block-level incremental).
**Verdict:** For organizations managing many PostgreSQL instances.

#### Restic (v0.19.1)

**Pros:**
- Forever-incremental + deduplication (reduces storage costs by 80–95% for DB dumps)
- 15+ cloud backends including S3-compatible (B2 S3 gateway, R2, S3)
- AES-256 password-based encryption (Argon2 key derivation)
- Strong integrity verification (HMAC-SHA256 + tree verification)
- Active development (v0.19.1, released 2026-07-05)
- Can backup both database dumps AND media volumes in one workflow

**Cons:**
- Not database-aware (needs `pg_dump` piped or filesystem-level for PostgreSQL)
- `forget --prune` required for retention cleanup
- Repository corruption risk if password lost

#### BorgBackup

**Pros:** Excellent variable-block deduplication; authenticated encryption; mature (10+ years).
**Cons:** SSH-focused backend (not native S3); single-maintainer project (bus-factor risk).
**Borgmatic wrapper:** Declarative YAML config for scheduling, retention, hooks, notifications.

#### Duplicati

**Pros:** 50+ cloud backends; AES-256; web GUI.
**Cons:** .NET/Mono dependency; historical database-corruption issues.
**Verdict:** Best for non-technical users wanting a GUI.

### 11.3 Cloud Storage Backends Comparison (2026 Pricing)

| Provider | Storage (per GB/mo) | Egress (per GB) | Free Tier | API | Notes |
|----------|-------------------|-----------------|-----------|-----|-------|
| **Backblaze B2** | $0.00695 ($6.95/TB) | $0.01 (first 10 TB) | 10 GB storage + 1 GB egress/month | S3-compatible | **Winner for archival.** Use S3 gateway, not native `b2:` ([BP §3.3]) |
| **Cloudflare R2** | ~$0.015 ($15/TB) | **$0.00** | 10 GB + 10 GB egress/day | S3-compatible | Winner if frequent downloads/restores |
| **Wasabi** | $0.00699 ($6.99/TB) | $0.00 | None | S3-compatible | 90-day minimum storage fee |
| **AWS S3 Standard** | $0.023 ($23/TB) | $0.09 (first 10 TB) | 5 GB (12 months) | Native S3 | Most expensive; best ecosystem |
| **Hetzner Storage Box** | €0.005/GB (~€13.70/TB ≈ $15/TB) | €0.001/GB (~$0.0015) | None | SMB/SSH/rsync | Not S3-compatible; avoids vendor lock-in |

### 11.4 Self-Hosted S3 Successors (MinIO is Dead)

**MinIO status** ([BP §3.2]):
- GitHub repository archived 2026-04-25
- Pre-built binaries halted October 2025
- Admin UI removed May 2025
- Security patches: case-by-case only

**SUCCESSOR projects for self-hosted S3-compatible gateway:**

| Alternative | License | Est. Stars (Apr 2026) | Min RAM | S3 Coverage | Notes |
|-------------|---------|----------------------|---------|-------------|-------|
| **SeaweedFS S3** | Apache 2.0 | ~23K | ~512 MB | Good | Best all-around replacement; active |
| **Garage** | AGPL v3 | ~4K | 1 GB | Core ops | Lightweight, geo-distributed |
| **RustFS** | Apache 2.0 | ~4K | ~2 GB | Good | MinIO API drop-in; Rust-based |
| **Ceph RGW** | LGPL 2.1 | ~14K | 16+ GB | Excellent | Enterprise scale; complex; via cephadm |

**Recommendation:** Do not self-host S3 unless B2 egress costs exceed budget. If needed, SeaweedFS S3 is the best successor. Remove all MinIO references from planning ([AC §3.5] E4).

---

## 12. Recommendation for Mko Bazuna

### 12.1 Current Architecture Constraints

| Constraint | Value | Impact on Backup |
|-----------|-------|-----------------|
| **Deployment model** | Single VPS, Docker Compose (v2) | No Kubernetes; containerised backup is the only option ([BP §2.1]) |
| **Database size** | ~200 MB – 1 GB | pg_dump sufficient; PITR/WAL-G overkill ([BP §1.1]) |
| **Media files** | ~50–200 GB originals + 150 GB thumbnails | Largest backup concern; Restic dedup required |
| **Redis** | Ephemeral (`--save "" --appendonly no`) | NOT backed up; cache is reconstructible from PostgreSQL ([CA §2.3]) |
| **No dedicated backup server** | Single VPS only | Must backup from within the Compose stack (volume mounts) |
| **Budget constraints** | MVP — minimal cost | B2 at $6.95/TB/mo is the cheapest viable offsite option |
| **GDPR compliance** | 30-day consent hard-delete, 120-day ad purge | Backup must run after hourly sweeps; 24h RPO means PII may be re-introduced on restore |
| **Two-process architecture** | web (gunicorn) + bot (aiogram) | Shared PostgreSQL; Redis for cross-process cache coordination |
| **Startup chain** | db → migrate → load_catalog → create_admin → seed → web/bot | Restore must include migrate step before starting web/bot |
| **Image deployment** | GHCR pre-built images in prod | Backup service must use a standalone image, not the app image |
| **Compose isolation** | `mko-bazuna-dev` / `mko-bazuna-test` | Restore procedures must specify correct compose files + project name |

### 12.2 Recommended Approach: pg_dump + Restic + Backblaze B2

**Rationale:**

1. **pg_dump (logical backup)** remains optimal for PostgreSQL 18 at this scale ([BP §1.2]):
   - Zero additional dependencies — `postgres:18-alpine` already provides `pg_dump`/`pg_restore`/`pg_isready` ([CA §5.1] line 68)
   - Portable format works across PostgreSQL major versions (important: future upgrade path is safe)
   - With `--format=custom --jobs=4`, a ~1 GB database completes in under 30 seconds
   - Sufficient RPO (24h) for a classifieds platform where ads expire naturally

2. **Restic v0.19.1** for the archive layer because ([BP §4.1]):
   - Forever-incremental deduplication reduces storage costs (DB dumps dedup ~90% since schema is identical)
   - S3-compatible backend support (`s3:` scheme — NOT deprecated `b2:` native scheme)
   - AES-256 client-side encryption protects all PII before it reaches B2
   - Strong integrity verification detects corruption early
   - Can backup both DB dumps and media volumes in a single workflow

3. **Backblaze B2** as the cloud storage backend because ([BP §3.1]):
   - $6.95/TB/month — 4x cheaper than AWS S3 ($23/TB)
   - S3-compatible gateway (`s3.us-west-002.backblazeb2.com`) — use `s3:` scheme, NOT native `b2:` (deprecated in Restic 0.19.0)
   - SSE-S3 bucket encryption adds defense-in-depth against restic password compromise
   - 10 GB free tier sufficient for testing

### 12.3 Implementation Strategy

The current backup service (`docker-compose.prod.yml` lines 65–97) is a bare `postgres:18-alpine` container with an inline `/bin/sh -c` daily `pg_dump` loop. The upgrade path is:

1. **Phase 1 — Image:** Create `docker/Dockerfile.backup` (Alpine 3.20 + Restic 0.19.1 + postgresql-client 18) (`plan_updated.md` Task 2.1)
2. **Phase 2 — Compose:** Replace backup service to use the custom image, mount `media_volume` at `/app/media:ro`, mount restic password file, add B2/restic env vars (`plan_updated.md` Tasks 2.2–2.4)
3. **Phase 3 — Scripts:** Create `scripts/backup.sh`, `scripts/restore.sh`, `scripts/verify-backup.sh` (`plan_updated.md` Tasks 3.1–3.3)
4. **Phase 4 — Orchestration:** Add Makefile prod targets (`backup-prod`, `restore-prod`, `verify-backups`, `media-backup`) + `Makefile.ps1` PowerShell equivalents (`plan_updated.md` Tasks 4.1–4.2)
5. **Phase 5 — Documentation:** Fix `docs/ops/restore.md` (postgres/postgres bug + missing media/Restic/offsite sections) + create `docs/ops/backup-operations.md` (`plan_updated.md` Tasks 5.1–5.2)
6. **Phase 6 — Validation:** Test DB backup, media backup, full restore (`plan_updated.md` Tasks 6.1–6.3)

**Key refinements from the old plan** (all from [BP] and [AC]):

| Old Plan Item | Issue | Updated Spec |
|---------------|-------|-------------|
| Restic 0.18 | Outdated | Restic 0.19.1 ([BP §4.1]) |
| B2 backend: `b2:` native, `s3.us-west-004` | Deprecated + wrong region | `s3:` scheme, `s3.us-west-002.backblazeb2.com` ([BP §3.3]) |
| Docker Swarm `secrets:` | Not applicable to single-node compose | File-mounted `RESTIC_PASSWORD_FILE` + `env_file` ([BP §6.1]) |
| Media path: `/media` | Wrong — path does not exist | `/app/media` (matches web/bot mounts — [CA §2.1]) |
| pg_dump: `-F c` only | No parallel/permission-safe flags | `--format=custom --jobs=4 --no-owner --no-privileges --if-exists --clean` ([BP §1.2]) |
| Retention: `--keep-daily 7 --keep-weekly 4 --prune` | Incomplete policy | `--keep-daily 7 --keep-weekly 4 --keep-monthly 12 --keep-yearly 3 --prune` + weekly `restic check --read-data-subset=1/7` ([BP §4.1]) |
| Restic password inline | Security risk | `RESTIC_PASSWORD_FILE` (file-mounted) ([BP §6.3]) |
| No B2 SSE-S3 | Missing encryption layer | Enable SSE-S3 on bucket ([BP §8.2]) |
| No monitoring | Silent failures | Healthchecks.io via `hc-ping.com` ([BP §7.1]) |
| 9 tables documented | 22 missing | All 31 tables documented ([CA §6.1]) |
| No GDPR sweep awareness | Backup may miss scrubbed state | Schedule after 08:00 UTC sweeps ([CA §3.3]) |
| MinIO as S3 alternative | Archived April 2026 | SeaweedFS S3 / Garage / RustFS / Ceph RGW ([BP §3.2]) |

### 12.4 Cost Estimate (2026 — Annual)

**Assumptions:**
- Database: 1 GB (compressed dump ~300 MB)
- Media: 200 GB (growing)
- Daily full backups of DB
- Daily incremental backups of media (Restic dedup)
- 30 days of daily backups retained
- 4 weekly, 12 monthly, 3 yearly snapshots

| Component | Calculation | Annual Cost |
|-----------|-------------|-------------|
| **B2 Storage (DB dumps)** | 300 MB × 7 daily + 12 monthly snapshots ≈ 3 GB × 365 days / 365 | ~0.3 GB × $0.00695 × 12 mo ≈ **$2.50** |
| **B2 Storage (Media)** | 200 GB dedup-applied; ~150 GB effective after dedup (unique photos) × 14-day local retention cycle; annual average ~200 GB | 200 GB × $0.00695 × 12 mo ≈ **$19.00** |
| **B2 Egress (restore testing)** | 50 GB restore test per quarter × 4 = 200 GB/year | 200 GB × $0.012/GB* ≈ **$2.40** |
| **B2 API Calls** | ~10K PUT/LIST calls per day × 365 | Negligible (< $1.00) |
| **Healthchecks.io** | Free tier (20 checks, 1000 pings/month) | **$0** |
| **Host local staging** | `./backups/` (2-day dump retention, gitignored) | $0 (local disk) |
| **Total Annual** | | **~$24/year** |

> *Egress pricing: B2 charges $0.01/GB for first 10 TB (no free tier for egress in 2026 plan pricing; previously had 1 GB free tier which is insufficient for restore testing).
>
> For comparison: AWS S3 would cost ~$490/year; Cloudflare R2 ~$30 (but higher per-request); Wasabi ~$15 (with 90-day minimum lock-in).

### 12.5 Why NOT Other Options

| Tool | Reason for Rejection |
|------|---------------------|
| **WAL-G / pgBackRest** | Overkill for sub-1 GB database; require WAL configuration changes to `db` service; 24h RPO is acceptable for classifieds ([BP §1.1], [BP §5.3]) |
| **Barman** | Requires dedicated backup server (VPS cost + ops overhead) — not feasible for single-VPS deployment |
| **BorgBackup** | SSH-focused; no native S3 backend (needs rclone bridge); single-maintainer project (bus-factor risk — [BP §11.2]) |
| **Duplicati** | GUI-focused; .NET/Mono dependency complicates Alpine-based backup image |
| **MinIO (self-hosted S3)** | Archived April 2026; no security updates; migration risk ([BP §3.2], [AC §3.5] E4) |
| **wal-e** | Legacy, unmaintained since ~2020; superseded by WAL-G |
| **rclone sync (as primary)** | Interim bridge only; Restic directly is preferred for dedup + verification ([BP §2.1, §8.1]) |

---

## Appendix: File References

| File | Purpose | Lines |
|------|---------|-------|
| `docker-compose.yml` | Base services (db, redis, 9 services, 2 named volumes) | 210 |
| `docker-compose.prod.yml` | Production overrides (GHCR images, scheduler, backup, pgbouncer) | 121 |
| `docker-compose.dev.override.yml` | Dev overrides (bind-mounts, runserver hot-reload, seed auto-start) | — |
| `docker-compose.test.yml` | Test overrides (ephemeral DB on port 5433, test-runtime target) | — |
| `docker/Dockerfile` | 3-stage image (builder → runtime → test-runtime) | 173 |
| `docker/entrypoint.sh` | Shared entrypoint with sourced-function pattern | 95 |
| `docker/entrypoint-scheduler.sh` | Scheduler loop (hourly GDPR sweeps) | 66 |
| `docker/entrypoint-test.sh` | Test runner (pytest with seed exclusion) | 44 |
| `Makefile` | GNU Make workflow (dev + test project isolation) | 252 |
| `Makefile.ps1` | PowerShell workflow parity (Windows dev) | 392 |
| `.env.docker` | Runtime env (gitignored, 43 lines) | 43 |
| `.env.docker.example` | Env template (committed, 73 lines) | 73 |
| `.gitignore` | Includes `backups/` (line 239), `.env.docker` (line 148) | 250 |
| `docs/ops/restore.md` | Current restore runbook (176 lines, no media/Restic/offsite) | 176 |
| `docs/ops/docker-deployment.md` | Full deployment doc (compose isolation, startup chain) | 896 |
| `docs/ops/backup-operations.md` | **TO BE CREATED** (`plan_updated.md` Task 5.2) | 0 |
| `docs/02-database/db-schema.md` | Full DB schema (31 tables) | 573 |
| `docs/02-database/db-retention.md` | GDPR retention policies + sweep commands | 127 |
| `src/backend/apps/core/enums.py` | AdvisoryLockId IntEnum (12 IDs) + AdStatus StrEnum | — |
| `src/backend/config/settings/base.py` | Django settings (MEDIA_ROOT=/app/media, Redis config) | — |
| `src/backend/apps/*/models.py` | 27 application models across 10 apps | — |
| `src/telegram_bot/services/media.py` | JPEG validation, EXIF stripping, UUID naming | — |

**Citations:**
- `[CA]` = `current-architecture-report.md` (770 lines, 2026-09-01)
- `[BP]` = `research-best-practices-report.md` (440 lines, 2026-09-01)
- `[AC]` = `audit-conclusion.md` (165 lines, 2026-09-01)
- Source code references use `file:line` format (e.g., `docker-compose.prod.yml:65-97`)