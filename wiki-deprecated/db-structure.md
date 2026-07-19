---
id: db-structure
domain: wiki
tags:
  - database
  - schema
  - postgresql
  - fts
related:
  - technical-specification
  - architecture-structure
  - packages
---

## Purpose

Database schema and search design for phase 1. Single source of truth for tables, columns,
status enums, indexes, and the `search_vector` trigger logic.

## Principles
- One ads table.
- Category tree: django-mptt>=0.18.0 (single source of truth; no denormalized path/level columns).
- Category-specific attributes (EAV) — DEFERRED (post-MVP).
- Tags — DEFERRED (no generation source in phase 1).
- Search: native PostgreSQL FTS (`search_vector` TSVECTOR + GIN + pg_trgm, russian config).
- One user = one Telegram account.

### Top-level relationships
```
users ── ads ──┬── categories
               ├── cities
               └── ad_images
```
(`category_attributes`/`ad_attribute_values` and `tags`/`ad_tags` are out of phase 1 scope.)

---

### users
```
id (PK)
telegram_id (BIGINT, UNIQUE, nullable)   # nullable for admin-created accounts
username (VARCHAR, nullable)             # optional public @username; NOT used for t.me link or publishing (decision C)
is_staff / is_superuser                  # admin/moderator role (decision A)
is_banned (BOOL)                          # account block (US-A4)
is_deleted (BOOL)                         # soft delete (US-S8)
ads_auto_publish (BOOL, default True)     # publishing ban (US-S9)
deleted_at (TIMESTAMP, nullable)
consent_given_at (TIMESTAMP, nullable)    # US-A8 / decision F
consent_revoked_at (TIMESTAMP, nullable)
hard_delete_at (TIMESTAMP, nullable)      # telegram_id nulled 30 days after consent withdrawal
created_at (TIMESTAMP)
```

**`login_tokens`** (decision H / US-S1, zone C1) — separate table for atomic Telegram login. Bot and web are two processes; token claimed exactly once under shared lock.
```
id (PK)
token_hash (CHAR(64) UNIQUE, indexed)   # SHA-256 of raw 32-char URL-safe token; raw token NEVER stored
telegram_id (BIGINT, nullable)          # filled by BOT on /start login_<token>
created_at (TIMESTAMP)
expires_at (TIMESTAMP)                  # +5 min from creation
consumed_at (TIMESTAMP, nullable)       # filled by WEB on login completion
```
Two-phase atomic claim (each = one UPDATE under transaction):
1. Bot: `UPDATE login_tokens SET telegram_id=<tg> WHERE token_hash=? AND telegram_id IS NULL AND consumed_at IS NULL AND expires_at > now()`
2. Web: `UPDATE login_tokens SET consumed_at=now() WHERE token_hash=? AND telegram_id IS NOT NULL AND consumed_at IS NULL AND expires_at > now()`
Both check `expires_at > now()`; token compare via `hmac.compare_digest` (constant time). Background task deletes expired/consumed tokens. Session cookies: `SECURE` + `HTTPONLY` + `SAMESITE=Lax`.

---

### ads (single table)
```
id (PK)
user_id (FK → users.id)
title (VARCHAR)
description (TEXT)
price (INT, nullable)                  # whole BAM units; multi-currency deferred (D11: `currency` column removed — YAGNI)
category_id (FK → categories.id)
city_id (FK → cities.id)
category_name (VARCHAR, editable=False) # zone D1 (hybrid C, O5): denormalized RUSSIAN category name; trigger-synced; in search_vector (weight 'C')
status (TextChoices — see AdStatus)
source (TextChoices: TELEGRAM)          # phase 1 = bot only (decision B)
created_at / updated_at
published_at (TIMESTAMP, nullable)      # drives archive/delete timers; UPDATED on every PUBLISHED transition (timer reset, decision J / zone C3)
original_published_at (TIMESTAMP, nullable) # set once on FIRST publish; IMMUTABLE, audit only (does NOT drive sweep)
archived_at (TIMESTAMP, nullable)
deleted_at (TIMESTAMP, nullable)
moderation_failed_at (TIMESTAMP, nullable) # zone C4/D12: set on ON_MODERATION → ON_MODERATION_FAILED; drives 7-day purge. Mutually exclusive with rejected_at
rejected_at (TIMESTAMP, nullable)        # zone D4: set on manual REJECTED; drives 90-day cleanup. Mutually exclusive with moderation_failed_at
search_vector (TSVECTOR)                 # NOT GENERATED ALWAYS — maintained by trigger (needs FK-lookup of category_name)
published_by (FK → users.id, nullable, SET_NULL)  # moderator who manually published
moderated_by (FK → users.id, nullable, SET_NULL)  # moderator who manually rejected
```

`search_vector` (zone D1, hybrid C): `setweight(to_tsvector('russian', title),'A') || setweight(to_tsvector('russian', description),'B') || setweight(to_tsvector('russian', category_name),'C')`. `category_name` is denormalized from `categories.name` (Russian base) and synced by triggers, so it cannot be `GENERATED ALWAYS` (needs FK lookup at write time). GIN index `IX_ads_search_gin` on top. Code writes title/description/category_id; trigger fills `category_name` + `search_vector`. Bosnian query translated to Russian before search (decision G), so it matches the Russian category name.

Category search works TWO ways: (1) FTS matches the category word via `category_name` in `search_vector`; (2) app-level fuzzy detect (`difflib`, as for cities) applies an explicit `category_id` filter when the query is a single word similar to a category name.

`published_at` DRIVES archive (2mo) / delete (4mo) timers from decision J. `original_published_at` is an immutable audit marker. `moderation_failed_at` and `rejected_at` are mutually exclusive. `published_by`/`moderated_by` complement `ModeratorActionLog` with a quick "last moderator" pointer.

**AdStatus** (Django TextChoices / StrEnum, rule 10):
- `DRAFT` — bot draft, not sent
- `ON_MODERATION` — awaiting auto-check (hidden)
- `PUBLISHED` — published (only buyer-visible status)
- `REJECTED` — manually rejected by moderator (kept 90 days, then purge; zone D4)
- `ON_MODERATION_FAILED` — failed auto-check (purged after 7 days via `moderation_failed_at`, decision A / zone C4)
- `ARCHIVED` — auto-archive (2mo) / manual archive
- `DELETED` — soft delete

**Transitions:**
- DRAFT → ON_MODERATION
- ON_MODERATION → PUBLISHED | REJECTED | ON_MODERATION_FAILED
- PUBLISHED → ARCHIVED → PUBLISHED (reactivation, text re-moderation)
- PUBLISHED → ON_MODERATION (zone C2: text edits only; ad IMMEDIATELY hidden; price/photo edits publish instantly; mixed edit follows text rule)
- any → DELETED

---

### categories (tree)
```
id (PK)
name (VARCHAR)                       # Russian name (base storage language)
name_i18n (JSONB, nullable)          # zone D2: {"ru": <str>, "bs": <str>}; NULL → fallback to `name`
slug (VARCHAR)
parent_id (FK → categories.id, NULL)
is_active (BOOL)
```
Implemented via **django-mptt>=0.18.0** (single source of truth: `lft`/`rght`/`tree_id`/`level`). No denormalized `path`/`level` columns. Subtree filtering via `get_descendants()`. UI name via `get_name(locale)` with Russian fallback. Russian `name` denormalized into `ads.category_name` and indexed in `search_vector` (zone D1).

### cities
```
id (PK)
country_code
name (VARCHAR)                       # Russian name (base storage language)
name_i18n (JSONB, nullable)          # zone D2: {"ru": <str>, "bs": <str>}
region (VARCHAR)
slug (VARCHAR)
```
City match is EXACT against the closed list; unrecognized city → "general / no city" (not searchable). Typos → `difflib.get_close_matches` "did you mean" (decision G).

### ad_images
```
id (PK)
ad_id (FK → ads.id)
image (VARCHAR / storage key)        # served URL/key (our storage). Phase 1: local MEDIA_ROOT via FileSystemStorage.
                                      #   Key contains NO user_id/telegram_id/username — only ad_id + UUID v4 (zone R6: URL anonymity)
telegram_file_id (VARCHAR, nullable) # dedup/re-download metadata; NOT used in <img src>
position (INT)
```
Only compressed Telegram photos (`message.photo`) accepted; `message.document` rejected. Bot downloads bytes and stores in our storage; `image` holds the served URL/key. `file_id` is NOT a URL and not usable in `<img src>` — stored as metadata only.
**Zone R8 (storage-boundary validation):** JPEG validated strictly (magic bytes / PIL) on save; non-JPEG rejected with 415. Key = UUID v4 (unguessable, non-sequential). nginx `/media/` sets `X-Content-Type-Options: nosniff`, whitelists `image/jpeg`, default `application/octet-stream`, `Content-Disposition: inline`.

### analytics_events (decision L)
```
id (PK)
event_type (TextChoices/StrEnum: REGISTRATION_CREATED, AD_PUBLISHED, SEARCH_PERFORMED, CONTACT_INITIATED)
timestamp (TIMESTAMP, default now)
user_id (FK → users.id, nullable)    # only for authed actions (telegram_id already collected). On consent withdrawal/soft-delete → SET NULL (keep aggregates, zone R1/R5)
```
Aggregated via ORM (`.filter(event_type=..., timestamp__date=...).count()`). Admin/CLI `show_metrics` access. No PII beyond already-collected `telegram_id`.

---

### Search (logic, not a table)
- `search_vector` on `ads` (trigger-maintained: title + description + category_name).
- `GIN index` on `search_vector` (`IX_ads_search_gin`).
- `pg_trgm` for typos (optional).
- App-level category fuzzy detect (`difflib`) → `category_id` filter (zone D1).
- Search fill: **title (weight A) + description (weight B) + category_name (weight C)**, `to_tsvector('russian', …)`. Bosnian query translated to Russian before search.

### search_vector triggers (zone D1, sync-safety)
Because `search_vector` includes the category name (another table), the column cannot be `GENERATED ALWAYS` — a plpgsql trigger fills it. All computation lives in ONE function so INSERT and UPDATE paths don't diverge.
```sql
CREATE OR REPLACE FUNCTION ads_search_vector_fn() RETURNS TRIGGER AS $$
DECLARE v_cat TEXT;
BEGIN
  SELECT name INTO v_cat FROM categories WHERE id = NEW.category_id;
  NEW.category_name := v_cat;
  NEW.search_vector :=
    setweight(to_tsvector('russian', coalesce(NEW.title,'')), 'A') ||
    setweight(to_tsvector('russian', coalesce(NEW.description,'')), 'B') ||
    setweight(to_tsvector('russian', coalesce(v_cat,'')), 'C');
  RETURN NEW;
END; $$ LANGUAGE plpgsql;

CREATE TRIGGER ads_search_vector_update
  BEFORE INSERT OR UPDATE ON ads
  FOR EACH ROW EXECUTE FUNCTION ads_search_vector_fn();

CREATE OR REPLACE FUNCTION categories_name_propagate() RETURNS TRIGGER AS $$
BEGIN
  UPDATE ads SET category_id = ads.category_id  -- trigger #2 recomputes category_name+search_vector
  WHERE category_id = NEW.id;
  RETURN NEW;
END; $$ LANGUAGE plpgsql;

CREATE TRIGGER on_category_name_update
  AFTER UPDATE OF name ON categories
  FOR EACH ROW EXECUTE FUNCTION categories_name_propagate();
```
Migration: one-time `UPDATE ads SET category_id = category_id` (or backfill) to fill `category_name`+`search_vector` for existing rows. O(n_ads) per category rename — acceptable for ~30-50 categories.

### Indexes — ads
```python
models.Index(name='IX_ads_pub_listing',
    fields=['status', 'category_id', 'city_id', '-published_at'],
    condition=Q(status=AdStatus.PUBLISHED))                 # partial: ~99% of public reads
models.Index(name='IX_ads_user_status', fields=['user_id', 'status'])
GinIndex(name='IX_ads_search_gin', fields=['search_vector'])  # real GIN on TSVECTOR
models.Index(name='IX_ads_archive_sweep', fields=['status', 'published_at'],
    condition=Q(status=AdStatus.PUBLISHED))                 # archive @2mo
models.Index(name='IX_ads_delete_sweep', fields=['status', 'published_at'],
    condition=Q(status=AdStatus.ARCHIVED))                 # delete @4mo
models.Index(name='IX_ads_purge_failed', fields=['status', 'moderation_failed_at'],
    condition=Q(status=AdStatus.ON_MODERATION_FAILED))      # 7-day purge
models.Index(name='IX_ads_rejected_sweep', fields=['status', 'rejected_at'],
    condition=Q(status=AdStatus.REJECTED))                 # REJECTED @90d (zone D4)
```
Standalone `status`/`category_id`/`city_id` indexes not needed — covered by composites. `price` has no index (rare filter in phase 1; add only after EXPLAIN ANALYZE at 500k, zone C7).

### Indexes — users
```python
models.Index(name='IX_users_erasure_sweep', fields=['consent_revoked_at'])  # zone R1: idempotent 30-day hard-delete sweep
```

---

### moderation_criteria (zone D3/D4, US-A11, O4 RESOLVED)
Singleton table (exactly one active row), edited by admin at runtime. Applied to NEW ads (read current row at submit; no per-ad `criteria_version` needed).

**Layer 1 — Automatic check** (bot/API, synchronous at submit, decision A / US-A10):
```
id (PK)
title_min_length (INT, default 5)
title_max_length (INT, default 100)
description_min_length (INT, default 10)
description_max_length (INT, default 2000)
price_required (BOOL, default TRUE)
min_images (INT, default 1)
max_images (INT, default 5)
banned_words (JSONB, default [])
max_ads_per_user (INT, default 10)
duplicate_title_threshold (INT, default 85)  # % title similarity for duplicate-spam detection (0..100)
updated_at (TIMESTAMP)
updated_by (FK → users.id, nullable, SET_NULL)
```
Stored in DB (NOT settings.py) so it is editable at runtime per US-A11. Field `min_text_length` (old aggregate) REMOVED — duplicated by `title_min_length`/`description_min_length`.

**Layer 2 — Manual moderation by admin** (photos + prohibited content, US-A11; future ML/OCR). Admin checklist + basis for future ML, NOT table columns. Prohibited-content categories (logged as `reason` in `ModeratorActionLog`, NEVER shown to seller):
`adult_content`, `violence_gore`, `drugs_weapons`, `hate_speech`, `counterfeit_goods`, `illegal_goods`, `spam_scam`, `off_topic`.

### ModeratorActionLog (zone D8, US-A11)
```
id (PK)
ad_id (FK → ads.id, nullable, SET_NULL)
user_id (FK → users.id, nullable, SET_NULL)  # moderator/admin (NULL after erasure, zone R1 — keep reason/admin/timestamp)
action_type (StrEnum: REJECT, BAN_ACCOUNT, SOFT_DELETE, CRITERIA_CHANGE, OTHER)
reason (TEXT)                                # rejection reason; NEVER shown to seller (US-A11)
created_at (TIMESTAMP, default now)
```
`published_by`/`moderated_by` on `ads` duplicate "last moderator"; NULL = auto action (bot/auto-check). Log is permanent, not purged with the ad (kept for audit; on user erasure `user_id` SET NULL, reason text retained).
