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
  - db-retention
  - technical-specification
  - architecture-structure
  - packages-list
  - spec-index
  - i18n-spec
---

## Purpose

Database schema for phases 1 and 2. Single source of truth for tables, columns, relationships, status
enums, and the `moderation_criteria` / `ad_images` storage design. Index, trigger, and enum
details live in sibling files: [db-indexes.md](db-indexes.md) and [db-enums.md](db-enums.md).

## Principles
- One ads table.
- Category tree: django-mptt>=0.18.0 (single source of truth; no denormalized path/level columns).
- Category-specific attributes (EAV).
- Tags — generation source to be determined in reserach phase.
- Search: native PostgreSQL FTS (per-language `search_vector_ru/bs/en` TSVECTOR + GIN, ru/bs/en configs).
- One user = one Telegram account.

### Top-level relationships
```
users ── ads ──┬── categories
                │      └── category_paths
                │      └── category_listing_purposes ── lookup_items
                │      └── category_listing_features ── lookup_items
                │      └── category_listing_conditions ── lookup_items
                ├── cities
                ├── ad_images
                └── ad_features ── lookup_items

lookups ── lookup_groups ── lookup_items
                └── category_listing_purposes
                └── category_listing_features
                └── category_listing_conditions
                └── ad_features
```
(`category_attributes`/`ad_attribute_values` and `tags`/`ad_tags` are out of phase 1 scope.)

---

### users
```
id (PK)
telegram_id (BIGINT, UNIQUE, nullable)   # nullable for admin-created accounts
chat_id (BIGINT, UNIQUE, nullable)       # stable Telegram chat ID; set on first bot contact, never nullified
username (VARCHAR, nullable)             # optional public @username; NOT used for t.me link or publishing (decision C)
is_staff / is_superuser                  # admin/moderator role (decision A)
is_banned (BOOL)                          # account block (US-A4)
is_deleted (BOOL)                         # soft-delete (US-S8); Phase 3: immediate flag + PII null; Phase 4: ads hard-deleted; checked by template consent-banner guard in 5 templates
is_declined (BOOL, default False)         # user declined consent (browse-only mode)
ads_auto_publish (BOOL, default True)     # publishing ban (US-S9)
telegram_premium (BOOL, default False)    # Telegram Premium subscription status
  preferred_city_id (FK → cities.id, nullable, SET_NULL, related_name="+")  # default city for search/filter for authenticated users (plan 15); guests use a 1-year consent-gated cookie instead
  telegram_language (VARCHAR(5), default 'ru', choices=LanguageLocale)     # Telegram-reported UI language; per-user locale for localized bot alerts (migration 0005)
  deleted_at (TIMESTAMP, nullable)
consent_given_at (TIMESTAMP, nullable)    # US-A8 / decision F
consent_revoked_at (TIMESTAMP, nullable)    # Phase 3: triggers immediate soft-delete cascade
created_at (TIMESTAMP)
source (StrEnum: TELEGRAM | SEED, default TELEGRAM)  # account creation origin (bot login vs. seed-generated)
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

### consent_records (zone F / Plan 21)
Audit log of consent decisions (accept / decline / withdraw). One row is **inserted** per
decision epoch — withdrawal writes a NEW row (history is never overwritten). `consent_records.user_id`
is nullable so **anonymous** buyers can consent via cookies only; authenticated users tie the
record to their `users` row (SET NULL on erasure keeps the audit trail after account deletion).
`choice` is backed by the `ConsentChoice` StrEnum (see [db-enums.md](db-enums.md)). The `categories`
JSONB carries granular flags (`{"analytics": bool, "preferences": bool}`).
```
id (PK)
user_id (FK → users.id, nullable, SET_NULL)   # NULL for anonymous/guest consent (cookie-only sessions)
choice (StrEnum — ConsentChoice)              # see db-enums.md
categories (JSONB)                            # {"analytics": bool, "preferences": bool}
ip_address (INET, nullable)                   # anonymous records only (audit traceability)
user_agent (TEXT, nullable)                   # anonymous records only
consented_at (TIMESTAMP, default now)
revoked_at (TIMESTAMP, nullable)             # set when choice = WITHDRAWN → triggers consent_hard_delete sweep + 30-day PII erasure
db_table: consent_records
```
Index on `user_id` supports the `consent_hard_delete` sweep. `consent_hard_delete` reads
`users.consent_revoked_at` (zone F) — the 30-day PII null + hard-delete of the row runs only
after the full grace window.

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
price_amount (DECIMAL(10,2), nullable)            # seller's original price amount (source of truth)
price_currency (VARCHAR(3), nullable)             # original currency (CurrencyCode StrEnum): EUR (default) / RSD / BAM
price_normalized_eur (DECIMAL(12,4), nullable)    # derived EUR-normalized value for cross-currency filter/sort; not user-editable (indexed)
category_id (FK → categories.id)
listing_purpose_id (FK → lookup_items.id, nullable)  # resolved via CategoryLookupResolver; group=listing_purpose
listing_condition_id (FK → lookup_items.id, nullable)  # resolved via CategoryLookupResolver; group=listing_condition (Plan 12)
city_id (FK → cities.id)
category_name (VARCHAR, editable=False)             # zone D1 (hybrid C): denormalized RUSSIAN category name; trigger-synced; in search_vector (weight 'C')
status (StrEnum — see AdStatus)                    # see db-enums.md
source (StrEnum: TELEGRAM | SEED)                   # TELEGRAM = bot source (decision B); SEED = seed-generated demo data
created_at / updated_at
published_at (TIMESTAMP, nullable)                 # drives archive/delete timers; UPDATED on every PUBLISHED transition (timer reset)
original_published_at (TIMESTAMP, nullable)        # set once on FIRST publish; IMMUTABLE, audit only
archived_at (TIMESTAMP, nullable)
deleted_at (TIMESTAMP, nullable)
moderation_failed_at (TIMESTAMP, nullable)         # zone C4/D12: drives IX_ads_purge_failed for 7-day auto-purge
rejected_at (TIMESTAMP, nullable)                  # zone D4: drives IX_ads_rejected_sweep for 90-day manual-reject cleanup
search_vector (TSVECTOR)                            # NOT GENERATED ALWAYS — legacy concatenated vector (maintained by trigger)
search_vector_ru (TSVECTOR, nullable)              # NOT GENERATED ALWAYS — per-language vector (russian config), trigger-maintained
search_vector_bs (TSVECTOR, nullable)              # NOT GENERATED ALWAYS — per-language vector (simple config), trigger-maintained
search_vector_en (TSVECTOR, nullable)              # NOT GENERATED ALWAYS — per-language vector (english config), trigger-maintained
published_by (FK → users.id, nullable, SET_NULL)    # moderator who manually published
moderated_by (FK → users.id, nullable, SET_NULL)    # moderator who manually rejected
```

**AdStatus** (StrEnum) — see [db-enums.md](db-enums.md) for the authoritative list and values.

**Transitional note:** For backward compatibility, the original `title` and `description` columns
are repurposed as `title_ru` and `description_ru`. New ads receive `title_ru`/`description_ru`
populated with translated content; legacy ads fall back to `title`/`description`. The
`get_title(locale)` and `get_description(locale)` methods implement the fallback chain:
locale-specific column > Russian > original column.

**`ad_features`** (through table for `Ad.features` M2M) — see below.

**Transitions:**
- DRAFT → ON_MODERATION
- ON_MODERATION → PUBLISHED | REJECTED | ON_MODERATION_FAILED
- ON_MODERATION_FAILED → REJECTED (manual review of auto-failed ads; AD-001)
- PUBLISHED → ARCHIVED → PUBLISHED (reactivation, text re-moderation)
- PUBLISHED → ON_MODERATION (text edits only; immediate hide; mixed edit follows text rule)
- any → DELETED

> Zone C4 / D12 (AD-001): Six `CheckConstraint`s enforce timestamp presence at the DB level:
> `published_at` (PUBLISHED), `archived_at` (ARCHIVED), `rejected_at` (REJECTED),
> `moderation_failed_at` (ON_MODERATION_FAILED), `deleted_at` (DELETED), and the mutual
> exclusivity of `moderation_failed_at` and `rejected_at`. See [db-indexes.md > Check Constraints](db-indexes.md#check-constraints--ads-ad-001).

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

Runtime resolution of inherited listing purposes/features and the YAML-driven catalog builder
are documented in [db-categories.md](db-categories.md).

### category_paths
Multi-parent navigation support. Each category can have zero or more alternative parent routes while keeping a single canonical MPTT parent. Alternative paths are navigation-only — they do not affect lookup inheritance or canonical category assignment.
```
id (PK)
category_id (FK → categories.id)         # the leaf/child being navigated to
parent_id (FK → categories.id)           # the alternative parent in the navigation path
sort_order (INT, default 0)              # ordering within alternative parent's children
is_automatic (BOOL, default False)       # True if created by system rule (e.g. price=0 → charity)
Unique: (category, parent)
db_table: category_paths
```

### category_listing_purposes
Binds listing purposes (LookupItem, group=listing_purpose) to categories. Used by `CategoryLookupResolver` for inherited purpose resolution.
```
id (PK)
category_id (FK → categories.id)
listing_purpose_id (FK → lookup_items.id, limit_choices_to: group=listing_purpose)
is_default (BOOL, default False)         # auto-selected when seller doesn't choose explicitly
Unique: (category, listing_purpose)
db_table: category_listing_purposes
```
Composite index: `(category_id, listing_purpose_id)`. Index: `listing_purpose_id`.

### category_listing_features
Binds listing features (LookupItem, group=listing_feature) to categories. Used by `CategoryLookupResolver` for inherited feature resolution.
```
id (PK)
category_id (FK → categories.id)
feature_id (FK → lookup_items.id, limit_choices_to: group=listing_feature)
Unique: (category, feature)
db_table: category_listing_features
```
Composite index: `(category_id, feature_id)`. Index: `feature_id`.

### category_listing_conditions
Binds listing conditions (LookupItem, group=listing_condition) to categories. Used by `CategoryLookupResolver`
for inherited condition resolution. Single-select per ad (Plan 12).
```
id (PK)
category_id (FK → categories.id)
condition_id (FK → lookup_items.id, limit_choices_to: group=listing_condition)
is_default (BOOL, default False)         # auto-selected when seller doesn't choose explicitly
Unique: (category, condition)
db_table: category_listing_conditions
```
Composite index: `(category_id, condition_id)`. Index: `condition_id`.

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

> Multi-currency: `price_currency` is a `CurrencyCode` StrEnum (EUR / RSD / BAM,
> EUR default — see [db-enums.md](db-enums.md)). The seller's original amount and
> currency are the source of truth; `price_normalized_eur` enables cross-currency
> filter/sort. Rates live in the `exchange_rates` table (below).

### exchange_rates (single table)
```
id (PK)
currency (VARCHAR(3), unique)                 # CurrencyCode StrEnum: EUR / RSD / BAM
rate_to_eur (DECIMAL(14,8))                   # EUR per 1 unit of currency (EUR base = 1.0)
effective_date (DATE)                         # audit trail for rate changes
source (VARCHAR(50))                          # origin, e.g. 'manual_seed' or an official provider
is_current (BOOL, default True)               # only current rows are used for normalization
created_at / updated_at
```
Constraint: at most one `is_current=True` row per currency (partial unique index
`uq_exchange_rate_current_per_currency`). `PriceNormalizer` reads the current rate
(cached 5 min) to compute `price_normalized_eur`; `recompute_normalized_prices`
re-derives it after rate changes.

### lookup_groups
Reference data groups (e.g. `listing_purpose`, `listing_feature`). Managed through Django admin. System groups are protected from deletion.
```
id (PK)
code (VARCHAR, unique)                   # machine-readable, immutable after creation
name_i18n (JSONB, nullable)              # {"ru": str, "bs": str, "en": str}
is_system (BOOL, default False)          # protected from admin deletion
sort_order (INT, default 0)
db_table: lookup_groups
```

### lookup_items
Individual values within a lookup group (e.g. `sell`, `new`, `urgent`). The `slug` is globally unique and serves as the identifier. Active items are used in resolution; inactive items are preserved for data integrity but hidden from UI.
```
id (PK)
group_id (FK → lookup_groups.id, CASCADE)
slug (SlugField, unique)                 # globally unique identifier
name_i18n (JSONB, nullable)              # {"ru": str, "bs": str, "en": str}
sort_order (INT, default 0)              # per-group ordering
is_active (BOOL, default True)
icon (VARCHAR(50), blank)                # emoji or SVG icon name
color (VARCHAR(7), blank)                # hex color (#RRGGBB)
db_table: lookup_items
```

### ad_images
```
id (PK)
ad_id (FK → ads.id)
image (VARCHAR / storage key)        # served URL/key (our storage). Phase 1: local MEDIA_ROOT via FileSystemStorage.
                                     #   Key contains NO user_id/telegram_id/username — only ad_id + UUID v4 (zone R6: URL anonymity)
telegram_file_id (VARCHAR, nullable) # dedup/re-download metadata; NOT used in <img src>
sha256 (CHAR(64), db_index=True)     # SHA-256 hex digest for per-user deduplication; auto-computed on save
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

### ad_features
Through table for the `Ad.features` M2M relationship. An ad can have 0..N listing features.
```
id (PK)
ad_id (FK → ads.id, CASCADE)
feature_id (FK → lookup_items.id, CASCADE, limit_choices_to: group=listing_feature)
sort_order (INT, default 0)              # display order of this feature on the ad page
Unique: (ad, feature)
db_table: ad_features
```

### analytics_events
```
id (PK)
event_type (StrEnum — see EventType in db-enums.md)
timestamp (TIMESTAMP, default now)
user_id (FK → users.id, nullable)    # SET NULL on erasure (zone R5)
ad_id (FK → ads.id, nullable)        # CASCADE; null for non-ad events
source (StrEnum: TELEGRAM | SEED, nullable, default NULL)  # event origin; 'SEED' marks seed-generated rows for cleanup
```
Aggregated via ORM; admin/CLI `show_metrics` access.

> Zone R5: `analytics_events.user_id` is SET NULL on erasure (aggregates kept). Full erasure
> completeness is decision O3 / zone R1.

---

### Search (logic, not a table)
- Per-language `search_vector_ru/bs/en` on `ads` (trigger-maintained: title + description + localized category_name; see [db-indexes.md](db-indexes.md) for the dual-write trigger SQL).
- `GIN index` on each vector (`IX_ads_search_gin_ru/_bs/_en`) — see [db-indexes.md](db-indexes.md).
- Legacy `search_vector` retained during dual-write transition (to be dropped in Phase 3).
- **PG18 upgrade note:** On PostgreSQL 18, FTS/collation-dependent processing uses the cluster's default collation provider; reindex `ads` GIN indexes after any major PostgreSQL collation-provider upgrade (per PG18 release notes). Fresh MVP cluster initialized on PG18 with ICU needs no reindex.
- App-level category fuzzy detect (`difflib`) → `category_id` filter (zone D1).
- Search fill per language: **title (weight A) + description (weight B) + category_name (weight C)**, using the locale-appropriate `to_tsvector` config (`russian`/`simple`/`english`). Queries are searched **in the buyer's own language** against the matching per-language vector — no query-time translation (decision G). Single-word queries matching category names also apply an explicit `category_id` filter (locale-aware via `Category.get_name(locale)`).

> Zone D5 / D6: seller input may be Montenegrin/Russian/English, but the bot MUST translate
> title+description to Russian on ad creation so `to_tsvector('russian', …)` is correct. Montenegrin/English
> UI translates back on display.

The implemented translation egress pipeline (publication-time Google Translate, circuit
breaker, 500 ms timeout, LRU cache, no-PII boundary) is documented in
[i18n-translation-egress.md](../96-researches/i18n-translation-egress.md).

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

---

### DailyAdMetrics
Pre-aggregated daily metrics for efficient dashboard queries.

```
id (PK)
ad_id (FK → ads.id, CASCADE)
date (DATE)
views_count (POSITIVE INT, default 0)
contacts_count (POSITIVE INT, default 0)
trust_score (FLOAT, nullable)
avg_response_time (FLOAT, nullable)
created_at (TIMESTAMP)
updated_at (TIMESTAMP)

Unique constraint: (ad_id, date) — name: uq_daily_ad_metrics_ad_date
Index: idx_daily_metrics_date_views (date, -views_count)
db_table: daily_ad_metrics
```

---

### SavedSearch
Buyers save search queries with filters for ongoing monitoring.

```
id (PK)
user_id (FK → users.id, CASCADE)
query (TEXT, nullable)
city_id (FK → cities.id, SET_NULL, nullable)
category_id (FK → categories.id, SET_NULL, nullable)
min_price (POSITIVE INT, nullable)
max_price (POSITIVE INT, nullable)
is_active (BOOL, default True)
language (VARCHAR(5), nullable, default 'bs')   # Saved-search query language: selects the per-language FTS vector (search_vector_ru/bs/en) for matching. Set from request.LANGUAGE_CODE at save time; does NOT control alert-message rendering (that uses User.telegram_language). Legacy rows backfilled to 'ru'
created_at (TIMESTAMP)
updated_at (TIMESTAMP, auto_now=True)          # last-modified (plan 16 / FND-001)
last_notified_at (TIMESTAMP, nullable)          # last time this search produced a notification
unsubscribe_token (VARCHAR(40), unique, db_index, nullable)  # opaque capability token (32 URL-safe chars)

Index: IX_saved_searches_user_active (user_id, is_active)
db_table: saved_searches
```

---

### AdFavorite
A user's favorite (bookmarked) ad for the cabinet Favorites section (plan 16 / FND-002).

```
id (PK)
user_id (FK → users.id, CASCADE, related_name=favorites)
ad_id (FK → ads.id, CASCADE, related_name=favorites)
created_at (TIMESTAMP, auto_now_add=True)

Unique constraint: (user_id, ad_id) — name: uq_user_ad_favorite
Index: ad_favorites_user_created_idx (user_id, -created_at)
db_table: ad_favorites
```

---

### SavedSearchNotification
Tracks notification delivery to prevent duplicates per search-ad pair.

```
id (PK)
saved_search_id (FK → saved_searches.id, CASCADE)
ad_id (FK → ads.id, CASCADE)
sent_at (TIMESTAMP)

Unique constraint: (saved_search_id, ad_id)
db_table: saved_search_notifications
```

---

### PopularSearch
Tracks popular search queries for autocomplete suggestions.

```
id (PK)
query (VARCHAR(200), db_index=True)
query_normalized (VARCHAR(200), db_index=True)
hit_count (POSITIVE INT, default 1)
last_seen (TIMESTAMP, auto_now=True)
source (StrEnum: TELEGRAM | SEED, nullable, default NULL)  # 'SEED' marks seed-generated rows for cleanup
db_table: popular_searches
```

---

### SearchHistory
Per-user search query tracking for personalized autocomplete.

```
id (PK)
user_id (FK → users.id, CASCADE, nullable)
query (VARCHAR(200))
query_normalized (VARCHAR(200), db_index=True)
created_at (TIMESTAMP, auto_now_add=True)

db_table: search_history
```

---

### SellerTrustScore
Persisted trust score for each seller, recalculated on ad publish.

```
id (PK)
user_id (FK → users.id, ONE_TO_ONE, CASCADE)
trust_level (VARCHAR(20), choices=TrustLevel)
score (POSITIVE SMALL INT, default 0)
ad_count_lifetime (POSITIVE INT, default 0)
ad_count_active (POSITIVE INT, default 0)
rejection_rate (DECIMAL(5,2), default 0.0)
contact_response_rate (DECIMAL(5,2), default 0.0)
last_calculated (TIMESTAMP, auto_now=True)

db_table: seller_trust_scores
```

---

### SellerVerification
Tracks seller verification status (admin and Telegram Premium).

```
id (PK)
user_id (FK → users.id, ONE_TO_ONE, CASCADE)
phone_number (VARCHAR(20), nullable)
verified_by_admin (BOOL, default False)
verified_at (TIMESTAMP, nullable)

db_table: seller_verifications
```

---

### AdModerationPriority
Priority scoring for moderation queue triage.

```
id (PK)
ad_id (FK → ads.id, ONE_TO_ONE, CASCADE, related_name="moderation_priority")
base_score (POSITIVE SMALL INT, default 0)
priority_level (VARCHAR(10), choices=AdPriorityLevel)
flags (JSONB, default=[])
confidence_score (FLOAT, default 0.0)
escalation_required (BOOL, default False)

Indexes: priority_level, base_score, escalation_required
db_table: ad_moderation_priorities
```