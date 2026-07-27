---
id: db-schema
domain: database
tags:
  - database
  - schema
  - postgresql
related:
  - db-indexes
  - db-enums
  - technical-specification
  - architecture-structure
  - packages-list
---

## Purpose

Database schema for phase 1. Single source of truth for tables, columns, relationships, status
enums, and the `moderation_criteria` / `ad_images` storage design. Index, trigger, and enum
details live in sibling files: [db-indexes.md](db-indexes.md) and [db-enums.md](db-enums.md).

## Principles
- One ads table.
- Category tree: django-mptt>=0.18.0 (single source of truth; no denormalized path/level columns).
- Category-specific attributes (EAV).
- Tags — generation source to be determined in reserach phase.
- Search: native PostgreSQL FTS (`search_vector` TSVECTOR + GIN, russian config).
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
is_deleted (BOOL)                         # soft-delete (US-S8); Phase 3: immediate flag + PII null; Phase 4: ads hard-deleted
ads_auto_publish (BOOL, default True)     # publishing ban (US-S9)
deleted_at (TIMESTAMP, nullable)
consent_given_at (TIMESTAMP, nullable)    # US-A8 / decision F
consent_revoked_at (TIMESTAMP, nullable)    # Phase 3: triggers immediate soft-delete cascade
created_at (TIMESTAMP)
```

> Account State Separation (O1/R4): Three independent states:
> 1. `ads_auto_publish=False` — reversible publish restriction; existing ads hidden while active.
> 2. `is_banned=True` — admin action; `telegram_id`/`username` retained for enforcement; reversible.
> 3. `is_deleted=True` + `consent_revoked_at` — consent withdrawal; Phase 3: soft-delete + PII null;
>    Phase 4: `consent_revoked_at + 30 days` targeted by `consent_hard_delete` sweep via `IX_users_erasure_sweep`.

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
title (VARCHAR)                                    # Russian title (base storage; renamed from original in MVP)
title_ru (VARCHAR, nullable)                      # Explicit Russian title for multi-language support
title_en (VARCHAR, nullable)                      # English translation for UI display
title_bs (VARCHAR, nullable)                      # Bosnian translation for UI display
description (TEXT)                                # Russian description (base storage)
description_ru (TEXT, nullable)                   # Explicit Russian description for multi-language support
description_en (TEXT, nullable)                   # English translation for UI display
description_bs (TEXT, nullable)                   # Bosnian translation for UI display
original_language (VARCHAR(5), nullable)            # Source language code (e.g. 'ru', 'bs', 'en')
price (INT, nullable)                             # whole BAM units; multi-currency deferred (currency column removed — YAGNI)
category_id (FK → categories.id)
city_id (FK → cities.id)
category_name (VARCHAR, editable=False)             # zone D1 (hybrid C): denormalized RUSSIAN category name; trigger-synced; in search_vector (weight 'C')
status (StrEnum — see AdStatus)                    # see db-enums.md
source (StrEnum: TELEGRAM)                         # phase 1 = bot only (decision B)
created_at / updated_at
published_at (TIMESTAMP, nullable)                 # drives archive/delete timers; UPDATED on every PUBLISHED transition (timer reset)
original_published_at (TIMESTAMP, nullable)        # set once on FIRST publish; IMMUTABLE, audit only
archived_at (TIMESTAMP, nullable)
deleted_at (TIMESTAMP, nullable)
moderation_failed_at (TIMESTAMP, nullable)         # zone C4/D12: drives IX_ads_purge_failed for 7-day auto-purge
rejected_at (TIMESTAMP, nullable)                  # zone D4: drives IX_ads_rejected_sweep for 90-day manual-reject cleanup
search_vector (TSVECTOR)                            # NOT GENERATED ALWAYS — maintained by trigger (needs FK-lookup of category_name)
published_by (FK → users.id, nullable, SET_NULL)    # moderator who manually published
moderated_by (FK → users.id, nullable, SET_NULL)    # moderator who manually rejected
```

**AdStatus** (StrEnum) — see [db-enums.md](db-enums.md) for the authoritative list and values.

**Transitional note:** For backward compatibility, the original `title` and `description` columns
are repurposed as `title_ru` and `description_ru`. New ads receive `title_ru`/`description_ru`
populated with translated content; legacy ads fall back to `title`/`description`. The
`get_title(locale)` and `get_description(locale)` methods implement the fallback chain:
locale-specific column > Russian > original column.

**Transitions:**
- DRAFT → ON_MODERATION
- ON_MODERATION → PUBLISHED | REJECTED | ON_MODERATION_FAILED
- PUBLISHED → ARCHIVED → PUBLISHED (reactivation, text re-moderation)
- PUBLISHED → ON_MODERATION (text edits only; immediate hide; mixed edit follows text rule)
- any → DELETED

> Zone D1 (hybrid C, decision O5): `category_name` is denormalized + indexed as described above; see [db-indexes.md](db-indexes.md) for the trigger SQL that syncs it.

> Zone C2 / C3: `PUBLISHED → ON_MODERATION` (text edits, hidden). Timers on `published_at`;
> `original_published_at` is the IMMUTABLE first-publish audit marker.

> Zone C4 / D12: `moderation_failed_at` drives the 7-day purge via `IX_ads_purge_failed`;
> `rejected_at` (zone D4) drives the 90-day cleanup via `IX_ads_rejected_sweep`. The two are
> mutually exclusive. See [db-indexes.md](db-indexes.md) for the partial index definitions.

---

### categories (tree)
```
id (PK)
name (VARCHAR)                       # Russian name (base storage language)
name_i18n (JSONB, nullable)          # zone D2: {"ru": <str>, "bs": <str>, "en": <str>}; NULL → fallback to `name`
slug (VARCHAR)
parent_id (FK → categories.id, NULL)
is_active (BOOL)
```
Implemented via **django-mptt>=0.18.0**. No denormalized `path`/`level` columns.

> Zone D2: i18n names stored in `name_i18n` JSONB (`ru`/`bs`/`en`); UI uses `get_name(locale)` with
> Russian fallback.

### cities
```
id (PK)
country_code
name (VARCHAR)                       # Russian name (base storage language)
name_i18n (JSONB, nullable)          # zone D2: {"ru": <str>, "bs": <str>, "en": <str>}
region (VARCHAR)
slug (VARCHAR)
```
City match is EXACT against the closed list; unrecognized city → "general / no city". Typos → `difflib.get_close_matches` "did you mean".

> Zone D11: `currency` column removed; `price` is INT whole BAM units.

### ad_images
```
id (PK)
ad_id (FK → ads.id)
image (VARCHAR / storage key)        # served URL/key (our storage). Phase 1: local MEDIA_ROOT via FileSystemStorage.
                                     #   Key contains NO user_id/telegram_id/username — only ad_id + UUID v4 (zone R6: URL anonymity)
telegram_file_id (VARCHAR, nullable) # dedup/re-download metadata; NOT used in <img src>
position (INT)
thumbnail_small (VARCHAR, nullable)    # 240x180 thumbnail storage key
thumbnail_medium (VARCHAR, nullable) # 640x480 thumbnail storage key
thumbnail_large (VARCHAR, nullable)  # 1280x960 thumbnail storage key
```
Only compressed Telegram photos (`message.photo`) accepted; `message.document` rejected. Bot downloads bytes and stores in our storage; `image` holds the served URL/key. `file_id` is NOT a URL and not usable in `<img src>` — stored as metadata only.

> Zone R6 / R8 (storage-boundary validation): `ad_images.image` key is ad-scoped + UUID v4
> (unguessable, non-sequential). JPEG validated strictly (magic bytes / PIL) on save; non-JPEG
> rejected with 415. nginx `/media/` sets `X-Content-Type-Options: nosniff`, whitelists
> `image/jpeg`, default `application/octet-stream`, `Content-Disposition: inline`.

### analytics_events
```
id (PK)
event_type (StrEnum: REGISTRATION_CREATED, AD_PUBLISHED, SEARCH_PERFORMED, CONTACT_INITIATED)  # see db-enums.md
timestamp (TIMESTAMP, default now)
user_id (FK → users.id, nullable)    # SET NULL on erasure (zone R5)
```
Aggregated via ORM; admin/CLI `show_metrics` access.

> Zone R5: `analytics_events.user_id` is SET NULL on erasure (aggregates kept). Full erasure
> completeness is decision O3 / zone R1.

---

### Search (logic, not a table)
- `search_vector` on `ads` (trigger-maintained: title + description + category_name).
- `GIN index` on `search_vector` (`IX_ads_search_gin`) — see [db-indexes.md](db-indexes.md).
- **PG18 upgrade note:** On PostgreSQL 18, FTS/collation-dependent processing uses the cluster's default collation provider; reindex `ads` GIN index after any major PostgreSQL collation-provider upgrade (per PG18 release notes). Fresh MVP cluster initialized on PG18 with ICU needs no reindex.
- App-level category fuzzy detect (`difflib`) → `category_id` filter (zone D1).
- Search fill: **title (weight A) + description (weight B) + category_name (weight C)**, `to_tsvector('russian', …)`. Queries detected by language and translated to Russian before search (decision G), so they match the Russian content.

> Zone D5 / D6: seller input may be Montenegrin/Russian/English, but the bot MUST translate
> title+description to Russian on ad creation so `to_tsvector('russian', …)` is correct. Montenegrin/English
> UI translates back on display.

Category search works TWO ways: (1) FTS matches the category word via `category_name` in `search_vector`; (2) app-level fuzzy detect (`difflib`, as for cities) applies an explicit `category_id` filter when the query is a single word similar to a category name.

---

### moderation_criteria (zone D3/D4, US-A11, decision O4)
Singleton table (exactly one active row), edited by admin at runtime. Applied to NEW ads (read current row at submit; no per-ad `criteria_version` needed). Stored in DB (NOT `settings.py`) so it is editable at runtime per US-A11.

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
**Note:** `ModerationCriteria` has no `min_price`/`max_price` or price-range fields. Criteria are length, count, and text-based only.

**Layer 2 — Manual moderation by admin** (photos + prohibited content, US-A11; future ML/OCR). Admin checklist + basis for future ML, NOT table columns. Prohibited-content categories (logged as `reason` in `ModeratorActionLog`, NEVER shown to seller): `adult_content`, `violence_gore`, `drugs_weapons`, `hate_speech`, `counterfeit_goods`, `illegal_goods`, `spam_scam`, `off_topic`.

### ModeratorActionLog
```
id (PK)
ad_id (FK → ads.id, nullable, SET_NULL)
user_id (FK → users.id, nullable, SET_NULL)  # NULL after erasure, reason text retained (zone D8)
action_type (StrEnum: REJECT, BAN_ACCOUNT, SOFT_DELETE, CRITERIA_CHANGE, OTHER)  # see db-enums.md
reason (TEXT)                                # NEVER shown to seller
created_at (TIMESTAMP, default now)
```

> Zone D8: `ModeratorActionLog` keeps `ad_id`, `user_id` (SET NULL on erasure, reason text
> retained), `action_type`, `reason`, `created_at`.