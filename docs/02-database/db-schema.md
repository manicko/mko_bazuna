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
is_staff / is_superuser                  # admin/moderator role (decision A); resolved to UserRole.ADMIN via the User.role property (see db-enums.md)
is_banned (BOOL)                          # account block (US-A4)
is_deleted (BOOL)                         # soft-delete (US-S8); Phase 3: immediate flag + PII null; Phase 4: ads hard-deleted; checked by template consent-banner guard in 5 templates
is_declined (BOOL, default False)         # user declined consent (browse-only); PUBLISHED ads excluded from public search/listings and direct URL access — `user__is_declined=False` in ListingsQuery, `ad_detail` queryset, and `ad__user__is_declined=False` in `media_gate` non-staff filter; search cache version bumped to invalidate cached results
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
token_hash (CHAR(64) UNIQUE, indexed)   # SHA-256 of raw 32-char URL-safe token; raw token NEVER stored (192-bit CSPRNG; exceeds NIST SP 800-63B §5.1.1.2 128-bit authenticator minimum)
telegram_id (BIGINT, nullable)          # filled by BOT on /start login_<token>
created_at (TIMESTAMP)
expires_at (TIMESTAMP)                  # +5 min from creation
consumed_at (TIMESTAMP, nullable)       # filled by WEB on login completion
browser_binding (CHAR(64), nullable)    # SHA-256 digest of the issuing browser's login-binding cookie; raw id NEVER stored; NULL = row predates the binding and is never redeemable
```
Two-phase atomic claim (each = one UPDATE under transaction):
1. Bot: `UPDATE login_tokens SET telegram_id=<tg> WHERE token_hash=? AND telegram_id IS NULL AND consumed_at IS NULL AND expires_at > now()`
2. Web: `UPDATE login_tokens SET consumed_at=now() WHERE token_hash=? AND telegram_id = <observed> AND consumed_at IS NULL AND expires_at > now() AND browser_binding = <presented digest>`
Token validation: SHA-256 hash stored (raw token never persisted). Claim via atomic `UPDATE ... RETURNING` with `WHERE token_hash = %s AND telegram_id IS NULL AND consumed_at IS NULL AND expires_at > %s` — only first valid claimer wins (zero-TOCTOU). 192-bit token entropy makes brute-force infeasible. Background task deletes expired/consumed tokens. Session cookies: `SECURE` + `HTTPONLY` + `SAMESITE=Lax`.
The web consume re-asserts the browser binding alongside `telegram_id` / `consumed_at` / `expires_at`: a row whose binding is `NULL`, or whose presented browser id is absent, malformed, or digests to a different value, is refused with HTTP `410` and is **not** burned (fail closed). The login-binding cookie is a session cookie (`HttpOnly`, `SameSite=Lax`, `path=/`, no `max_age`), classified essential. Its name and `Secure` flag are resolved from the single transport setting `LOGIN_BROWSER_ID_COOKIE_HOST_PREFIX`: on a transport-secure origin (production, behind TLS) it is `__Host-login_browser_id` + `Secure`; on a plain-HTTP origin (dev/test) it is `login_browser_id` with no `Secure`. The prefix and its mandatory `Secure` can never disagree, because both derive from that one setting. The `__Host-` prefix is required, not cosmetic: without it a sibling subdomain could set the cookie for a parent domain (RFC 6265 §5.3) and choose the binding value, defeating the control. `__Host-` mandates exactly `Secure` + `Path=/` + no `Domain`; on an HTTP-only origin the prefix control is absent by design, not by oversight.
Token consumption is POST-only (token submitted in request body, never as a URL query parameter) and guarded by CSRF protection.

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
ip_address (INET, nullable)                   # anonymised CLIENT address, masked /24 (IPv4) or /64 (IPv6) — see the note below
user_agent (TEXT, nullable)                   # anonymous records only
consented_at (TIMESTAMP, default now)
revoked_at (TIMESTAMP, nullable)             # set when choice = WITHDRAWN → triggers consent_hard_delete sweep + 30-day PII erasure
db_table: consent_records
```
`ip_address` stores the **anonymised client** address, not the direct socket peer. It is
resolved by `apps/core/utils/client_ip.py::get_client_ip` (peer gate + `X-Real-IP` /
right-to-left `X-Forwarded-For`) and then masked by
`apps/users/services/consent_record.py::_anonymize_ip` — IPv4 last octet zeroed (`/24`),
IPv6 lower 64 bits zeroed (`/64`); an absent or unparseable peer stores `NULL`. This
replaced an earlier value that held the anonymised **nginx container** address
(`172.x.0.0`, a constant identical for every production row), which carried zero
evidentiary value; the masking strength was sized for that coarser input and is now
materially more identifying (a `/24` is 256 addresses). Both `ip_address` and `user_agent`
are written whenever the request is present; when `request` is absent (e.g. the Telegram
bot `/start` path) they are left blank (`NULL` / empty).

Index on `user_id` supports the `consent_hard_delete` sweep. `consent_hard_delete` reads
`users.consent_revoked_at` (zone F) — the 30-day PII null + hard-delete of the row runs only
after the full grace window.

`IX_consent_records_sweep` on `consent_given_at` supports the `purge_consent_records`
retention sweep, which **anonymises** (never deletes) rows older than the ratified
fingerprint window. `Meta.ordering = ["-consent_given_at"]` does not create an index, so the
sweep column leads this real index.

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
                    # updated_at (not created_at) drives DRAFT retention: the 30-min sweep
                    # measures seller INACTIVITY (03-DB-003), refreshed by the bot dialog
                    # heartbeat and the web edit form. Do not revert the predicate.
published_at (TIMESTAMP, nullable)                 # drives archive_sweep timer (60d); UPDATED on every PUBLISHED transition (timer reset)
original_published_at (TIMESTAMP, nullable)        # set once on FIRST publish; IMMUTABLE, audit only
archived_at (TIMESTAMP, nullable)                  # drives delete_sweep timer (60d from archive, AD-005); cleared on every -> PUBLISHED transition
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
- PUBLISHED → ARCHIVED → PUBLISHED (reactivation); ARCHIVED → ON_MODERATION (edit-then-re-moderate)
- PUBLISHED → ON_MODERATION (text edits only; immediate hide; mixed edit follows text rule)
- any → DELETED

The list above is the module-level `ALLOWED_TRANSITIONS` in `apps/ads/models.py`, keyed by all
**seven** `AdStatus` values: `DRAFT`, `ON_MODERATION`, `PUBLISHED`, `ARCHIVED`, `REJECTED`,
`ON_MODERATION_FAILED`, `DELETED`. `REJECTED` and `DELETED` are terminal (empty target sets), and
`any → DELETED` is handled ahead of the matrix lookup, so those are the complete contracts.

**`ON_MODERATION_FAILED → PUBLISHED` is refused by design.** A human approval accepts an
auto-failed ad as its *input* (the approvable set is `{ON_MODERATION, ON_MODERATION_FAILED}`), but
the matrix has no such edge, so the approval is reported as a refusal and the ad is not
published. What a seller may do with an auto-failed ad is an open owner question (gate Q5, BLOCK
8B) recorded in
[ad-lifecycle-remediation-record.md](../99-agent/ad-lifecycle-remediation-record.md). No edge has
been added and no code has shipped for it.

> Zone C4 / D12 (AD-001): Six `CheckConstraint`s enforce timestamp presence at the DB level:
> `published_at` (PUBLISHED), `archived_at` (ARCHIVED), `rejected_at` (REJECTED),
> `moderation_failed_at` (ON_MODERATION_FAILED), `deleted_at` (DELETED), and the mutual
> exclusivity of `moderation_failed_at` and `rejected_at`. See [db-indexes.md > Check Constraints](db-indexes.md#check-constraints--unique-constraints--ads-ad-001).

> `Ad.transition_to` **clears `archived_at`** on every `→ PUBLISHED` transition (and clears the
> moderation and archive timestamps on `→ ON_MODERATION`), so a reactivated ad carries no stale
> archive timestamp and its timers restart from the new `published_at`. There is deliberately **no
> reverse `CheckConstraint`** requiring `archived_at IS NULL` outside `ARCHIVED`: the six presence
> constraints stay one-way, and the clearing is the transition's job, not the database's. Do not
> add one.

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
re-derives it after rate changes, locking each batch row via `select_for_update()`
to prevent concurrent writes (zone DB-001).

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
position (INT)                                    # unique per ad (uq_ad_images_ad_position); NOT required to be contiguous
thumbnail_small (VARCHAR, nullable)    # 240x180 thumbnail storage key
thumbnail_medium (VARCHAR, nullable) # 640x480 thumbnail storage key
thumbnail_large (VARCHAR, nullable)  # 1280x960 thumbnail storage key
```
Only compressed Telegram photos (`message.photo`) accepted; `message.document` rejected. Bot downloads bytes and stores in our storage; `image` holds the served URL/key. `file_id` is NOT a URL and not usable in `<img src>` — stored as metadata only.

**`UNIQUE (ad, position)`** — constraint `uq_ad_images_ad_position`, migration
`src/backend/apps/ads/migrations/0009_adimage_uq_ad_position.py`. A position is unique **within
one ad** and that is the whole rule: **contiguity is deliberately not enforced, so gaps are
permitted and preserved** (`copy_ad` carries a source ad's positions such as `[0, 2, 5]` through
verbatim). Do not add a contiguity check to `AdImage.Meta.constraints`.

A storage key is **not** unique to one row: `copy_ad` points the copy at the source ad's
keys instead of duplicating files, so one key can be legitimately referenced by several
`AdImage` rows. Deletion is therefore guarded in the `AdImage` `pre_delete` signal
(`apps.media.signals`) — `delete_photo()` is skipped while another `AdImage` row still
references that key. That per-key existence check **is** the AD-003 fix (retired as `64a9de6`):
it is the minimal correct mechanism at the one seam every deletion path shares, not a reference
count, and `delete_photo()` itself remains unconditional once a key is unreferenced.

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

The implemented translation egress pipeline (publication-time Google Cloud Translation API via httpx, circuit
breaker, 500 ms timeout, LRU cache, no-PII boundary) is documented in
[i18n-translation-egress.md](../96-researches/i18n-translation-egress.md).

Category search works TWO ways: (1) FTS matches the category word via `category_name` in `search_vector`; (2) app-level fuzzy detect (`difflib`, as for cities) applies an explicit `category_id` filter when the query is a single word similar to a category name.

---

### site_config (singleton)

Admin-editable site/brand name and Telegram bot username. Replaces 22 hardcoded
`"Mko Bazuna"` occurrences across page `<title>` tags, header/footer brand links,
the auth & privacy `blocktrans`, and the admin review page with a single
runtime-configurable value. The stored `bot_username` — not the `BOT_USERNAME`
env var — is the source of truth for all deep-link rendering (Spec 18); the env
var is a seed value for migration `0003` and a production boot guard, and no
render path reads it. Modeled on the `ModerationCriteria` singleton
pattern — exactly one row (`pk=1`, created lazily via `get_or_create(pk=1)` and
seeded explicitly by the `0002_seed_default` data migration using `RunPython`,
then `0003_add_bot_username` seeds `bot_username` from the `BOT_USERNAME` env var,
validating it against the field's own `RegexValidator` and calling `full_clean()`
before `save()` — an empty, placeholder or malformed value resolves to the field
default instead of being written, and an admin-edited value is never overwritten.
It is the first project
migration to seed data this way; under
`DisableMigrations` (tests) the lazy
`get_or_create` in `get_singleton()` is the fallback):
```
id (PK)
name (VARCHAR, default "Bazuna")      # site/brand name shown in page titles, headers, footer, and bot greetings
bot_username (VARCHAR, default "bazuna_bot")  # Telegram bot username WITHOUT @ prefix; RegexValidator ^[A-Za-z0-9_]{3,32}$
db_table: site_config
```
The admin (`apps/core/admin.py`) registers `SiteConfigAdmin` with
`has_add_permission = has_delete_permission = False`. A `post_save` signal
(`apps/core/signals.py`, wired in `CoreConfig.ready()`) invalidates the cached value
(`SITE_CONFIG_CACHE_KEY = "site_config:v1"`, 1 h TTL in `apps/core/utils/cache.py`) on
every save.

The cached config (both `name` and `bot_username`) is read by **both** long-lived
processes — the web via the `site_config` context processor (`site_name`) and the
`get_bot_username()` service, and the Telegram bot via `get_site_name_async()` (greetings
on `/start` and `/post`) and `get_bot_username_async()` (deep-link construction); see
[Cache Backend](../99-agent/architecture.md#cache-backend) for the two-process
shared-cache model (Redis in prod, `LocMemCache` in tests). `get_site_name()` and
`get_bot_username()` defensively fall back to `"Bazuna"` and `"bazuna_bot"`
respectively if the row or cache is unavailable. The `BOT_USERNAME` env var is now a
**seed value plus a production boot guard only** — migration `0003` consumes it once,
and `config/settings/prod.py` rejects an empty, placeholder or malformed value at
import (contract: `config/settings/secret_validation.py`); all runtime reads go through the
`get_bot_username()` service. Correcting `.env.prod` does **not** repair an
already-seeded row: run `manage.py repair_bot_username`, or edit the singleton in the
Django admin. See [`contact-us.md`](../01-spec/contact-us.md) for the
full deep-link obfuscation and rate-limiting architecture.

After the site name, the bot username is the second field of this singleton; see
[architecture-structure.md](../01-spec/architecture-structure.md#context-processors) for
the context-processor inventory.

---

### scheduler_daily_state (singleton)

Durable marker for the scheduler's daily command set (`apps/core/models.py`,
`SchedulerDailyState`; migration `0005_scheduler_daily_state`; service
`apps/core/services/scheduler_daily_state.py`). Records the calendar date the daily set
(`send_alerts`, `rollup_daily_metrics`) last completed cleanly. `run_scheduler` reads it
once on start-up, and `run_one_cycle` writes it only when every daily command exited `0`
with no stop request; a failed day is retried on the next hourly tick. The implicit `pk=1`
is the singleton invariant (no `UniqueConstraint` needed). Two overlapping schedulers during
a deploy are benign: each daily command takes its own advisory lock, so the second collects
nothing and both write the same value; the `get_or_create(pk=1)` shape absorbs the
concurrent-insert race. Both the read and the write are **fail-open** — a marker problem
causes a re-run, never a silent skip. Redis is deliberately **not** the substrate (it is a
disposable cache, not durable storage; see [Cache Backend](../99-agent/architecture.md#cache-backend)):
```
id (PK, fixed at 1)                        # the singleton invariant
last_daily (DATE, null)                    # calendar date the daily set last completed cleanly
last_daily_completed_at (TIMESTAMP, null)  # when the daily set last completed cleanly
updated_at (TIMESTAMP, auto_now)           # when the marker row was last written
db_table: scheduler_daily_state
```
Inspect with:
```sql
SELECT last_daily, last_daily_completed_at FROM scheduler_daily_state;
```

---

### support_contacts

Admin-managed support channels (email or Telegram) that the bot delivers support tickets to
(`apps/core/models.py`, `SupportContact`; migration `0004_support_models`). Exactly one
channel-type/value pair is required: an `EMAIL` row must populate `email` (and leave
`telegram_id` null), and a `TELEGRAM` row must populate `telegram_id` (and leave `email` null).
The `support_contact_channel_value_required` `CheckConstraint` enforces this at the DB layer.
Active rows are cached (`SUPPORT_CONTACTS_CACHE_KEY = "support_contacts:v1"`, 1 h TTL in
`apps/core/utils/cache.py`) and invalidated on admin save/delete via `post_save`/`post_delete`
receivers in `apps/core/signals.py`.

| Column | Type | Notes |
|---|---|---|
| `id` | PK | `BigAutoField` |
| `channel_type` | VARCHAR(10), choices=`SupportChannelType` | `email` or `telegram` |
| `label` | VARCHAR(255) | Human-readable label |
| `email` | VARCHAR, nullable | Required when `channel_type=email` |
| `telegram_id` | BIGINT, nullable | Required when `channel_type=telegram` |
| `is_active` | BOOL, default TRUE | Only active rows are offered |
| `ordering` | SMALLINT, default 0 | Display order (lower first) |
| — | — | `db_table: support_contacts`; `ordering: [ordering, id]`; constraint `support_contact_channel_value_required` |

The bot reads active contacts via `apps.core.services.support.get_support_contacts()` (cached,
1 h TTL, fails open to `[]`); email recipients may also be sourced from the
`SUPPORT_NOTIFICATION_RECIPIENTS` setting. Admin: `SupportContactAdmin` (`list_display`,
`list_editable` on `is_active`/`ordering`, `list_filter`/`search_fields`). See
[`db-enums.md`](db-enums.md#supportchanneltype).

### support_tickets

Support tickets submitted by sellers/buyers via the bot (`/start` → "Contact support" → free-text
message) (`apps/core/models.py`, `SupportTicket`; migration `0004_support_models`). The `ticket_ref`
(`SUP-YYYYMM-NNN`) is auto-generated in `save()` on first save by counting same-month rows.
`SupportTicketAdmin` is view-and-filter only (add/delete disabled); a ticket is not an audit trail —
it is personal data deleted with its subject (06-PII-101).

| Column | Type | Notes |
|---|---|---|
| `id` | PK | `BigAutoField` |
| `user_id` | FK → users.id, nullable, **CASCADE** (`related_name="support_tickets"`) | Deleted with the user; null only for a legacy unattributed row |
| `chat_id` | BIGINT | Telegram `chat_id` of the submitter |
| `telegram_id` | BIGINT | Submitter's Telegram ID |
| `username` | VARCHAR(255), nullable | Telegram username (if available) |
| `text` | TEXT | Ticket body |
| `status` | VARCHAR(10), default `open`, choices=`SupportTicketStatus` | `open`/`replied`/`closed` |
| `ticket_ref` | VARCHAR(32), UNIQUE, editable=False | Auto-generated `SUP-YYYYMM-NNN` |
| `created_at` | TIMESTAMP, default now | |
| — | — | `db_table: support_tickets`; `ordering: [-created_at]` |

The bot persists tickets in a single `sync_to_async` ORM call (`handle_support_orm` in
`telegram_bot/handlers/support.py`) and confirms to the user with the generated `ticket_ref`.
Delivery channels are the `[support_contacts](#support_contacts)` rows (email + Telegram) and the
`SUPPORT_NOTIFICATION_RECIPIENTS` setting. See [`db-enums.md`](db-enums.md#supporttickestatus).

**Erasure (06-PII-101).** A ticket is deleted, not scrubbed: `withdraw_consent` deletes the user's
tickets inside its existing `transaction.atomic()`, the `CASCADE` on `user_id` removes them on a
hard user delete (the 30-day sweep and superuser admin delete), and `consent_hard_delete` also
sweeps any already-orphaned (`user_id IS NULL`) rows. The bot refuses to create a ticket for a
sender who has not consented to personal-data storage, so no new unattributed ticket is written.

**Known limitation — `ticket_ref` reuse.** `ticket_ref` is computed as
`count() + 1` over live same-month rows, so deleting a mid-month ticket makes the next ticket reuse
a reference a user may already have quoted to the desk. This is a documented limitation, not fixed
here: changing a user-visible identifier is a separate, behaviour-visible change (follow-up:
06-PII-101 ticket-ref sequence hardening).

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
unsubscribe_token (VARCHAR(40), unique, db_index, nullable)  # opaque capability token (32 URL-safe chars); resolved under transaction.atomic() + select_for_update() in alerts.py _resolve_owned to prevent lost-update races on the unsubscribe toggle

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
Record of one alert attempt for a (saved search, ad) pair (03-DB-007). The row is an
**attempt record**; `delivered_at` is the **receipt**. `delivered_at IS NULL` means
"recorded but not delivered" and the pair stays eligible for both the immediate and the
daily delivery paths, so a failed or skipped send is retried rather than lost.

```
id (PK)
saved_search_id (FK → saved_searches.id, CASCADE)
ad_id (FK → ads.id, CASCADE)
sent_at (TIMESTAMP)          # when the notification record was created (auto_now_add)
delivered_at (TIMESTAMP, NULL, no default)  # when Telegram accepted the alert; written AFTER a successful send

Unique constraint: (saved_search_id, ad_id)
db_table: saved_search_notifications
```

`delivered_at` is written **after** a successful send by both delivery paths
(`notification_delivery.mark_delivered`). It is **backfilled from `sent_at`** for
pre-existing rows so a deploy is behaviour-preserving. **One alert per
`(saved_search_id, ad_id)` for the life of the listing — including across a re-publish —
is a recorded product decision**, not an accident.

Whether **editing a live ad** should re-alert matching buyers is an **open product
question**; today it does not. Any future epoch for that decision must be a
**content-revision column, not `Ad.published_at`** — `published_at` is reset by
`ad_reactivate` and price/photo edits too, so it would re-alert on the wrong half
of the transitions.

---

### PopularSearch
Tracks popular search queries for autocomplete suggestions.

```
id (PK)
query (VARCHAR(200), db_index=True)                              # PII-redacted at write time (SRH-004); phones, emails, multi-word names masked via redact_search_query() — query_normalized remains the raw lookup/dedup key
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
query (VARCHAR(200))                                            # PII-redacted at write time (SRH-004); phones, emails, multi-word names masked via redact_search_query()
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