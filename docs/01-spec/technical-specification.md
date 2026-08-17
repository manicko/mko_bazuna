---
id: technical-specification
domain: spec
tags:
  - specification
  - domain
  - requirements
related:
  - db-schema
  - db-indexes
  - db-enums
  - architecture-structure
  - packages-list
  - user-stories-index
  - spec-index
---

## Purpose

Authoritative phase-1 product & domain specification for **Mko Bazuna** — a Telegram-driven classifieds board (Avito-like) with a Django website. This is the single source of truth for product behavior. Technical implementation details live in [`../02-database/db-schema.md`](../02-database/db-schema.md), `architecture-structure.md`, and [`../03-packages/packages-list.md`](../03-packages/packages-list.md).

## Product Summary

- Sellers create ads via a **Telegram bot**; published ads appear on the website.
- Buyers browse/search/filter without registration.
- Launch geography: **Montenegro**. Target languages: **Russian (content base)** + **Montenegrin (UI shell)**.
- Scale targets: ~300 daily users, up to 500k ads, server response < 2s.
- Stack: Python 3.14 + Django 5.2 LTS + PostgreSQL 18 (see [`../03-packages/packages-list.md`](../03-packages/packages-list.md)).

## Fixed Domain Decisions (A–L)

Product decisions taken outside code. Each letter is referenced from other docs as "decision X".
Zone-resolution evidence (C1–C8, R1–R9, D1–D12) is distributed inline by zone ID across the domain
docs ([db-schema.md](../02-database/db-schema.md), [db-indexes.md](../02-database/db-indexes.md),
[architecture-structure.md](architecture-structure.md)). Owner decisions O1–O5 live in
[`../05-owner-decisions/index.md`](../05-owner-decisions/index.md). This file links zones rather than
repeating them.

### A. Moderation model
- Automatic check (US-A10) is the **only** automatic gate before `PUBLISHED`.
- Ads failing auto-check are kept ≤ 1 week, then deleted (`ON_MODERATION_FAILED`).
- **Moderator = admin role** (no separate moderator role).
- Moderator powers: unpublish, review failed ads, **edit moderation criteria** (US-A11), ban all of a user's ads.
- Launch with a moderator from day one.
- Seller rejection path: bot replies "ad failed moderation" + rules link; **no specific reason disclosed**.
- **ModerationCriteria has no price-range fields** (no min_price/max_price); criteria are length, count, and text-based only (zone D3/D4, US-A11, O4).

### B. Third-party group monitoring — OUT OF PHASE 1
Phase 1 accepts ads **only via our Telegram bot** (US-S2). Group/channel monitoring is a separate future phase.

### C. Seller contact & anonymity (US-B4/B5)
- **No seller identity** shown on site (no `@username`, name, or `telegram_id`).
- Only a "Contact seller" button → deep-link `https://t.me/<bot_username>?start=contact_<ad_id>`.
- Bot maps `ad_id` → seller `telegram_id` and relays, never revealing seller PII.
- Contact requires **no login** on our side; interaction moves to Telegram.
- **Button renders on site ONLY if** ad is `PUBLISHED` AND seller `telegram_id` NOT NULL AND seller NOT `is_deleted`/`is_banned` and consent NOT revoked.
- `username` is NOT required for publishing or contact.

### D. Geography & categories (US-B6/B7, US-A7)
- Launch geography: Montenegro. Languages: Russian + Montenegrin (latin).
- **City:** seller picks from a preset closed list of Montenegro cities. Unrecognized city → "general / no city", not searchable by city.
- **Categories are NOT user-defined.** Closed tree set by admin (django-mptt is the single source of truth). Bot suggests top 3–5 by keyword, requires explicit seller confirmation. Free-text as new category is **rejected**; choice only from suggested or full tree.
- i18n names (zone D2): `name` in Russian; Montenegrin in `name_i18n` JSONB — see column detail in [db-schema.md](../02-database/db-schema.md). UI uses `get_name(locale)` with Russian fallback.
- **Category-name search is REQUIRED in phase 1 (zone D1 / O5, hybrid C):** `category_name` is denormalized into `ads.category_name` and included in `search_vector` (weight 'C') + app-level fuzzy detect (`difflib`) sets `category_id` filter for single-word queries. Montenegrin query is translated to Russian before search, so it matches the Russian category name.
- Preset tree (recommendation):
  - **Goods:** Electronics, Clothing, Children, Furniture, Tools, Sport, Books, Other
  - **Services:** Repair, Translation, Tutors, Courses, Beauty, Transport, Freelance, Other
  - **Real Estate:** Apartments, Houses, Rooms, Commercial, Parking, Other

### E. Photos & moderation (US-S2, US-A10)
- **1 to 5 photos** per ad.
- Only **compressed Telegram photos** accepted (`message.photo`); `message.document` with `image/*` is rejected.
- Format: JPEG (Telegram-converted). Limit: up to 2560px long side, ~2 MB/photo; ≤ 5 photos / 10 MB per ad.
- Phase-1 moderation is **text-only** (US-A10). Bad photos removed manually by moderator (incl. account ban).
- **No server-side photo optimization in phase 1** — accept Telegram-compressed images, store in our storage (decision E-storage), serve as-is.
- **Storage (E-storage):** phase 1 = local `MEDIA_ROOT` (Docker volume) behind nginx via Django `FileSystemStorage` (the `STORAGES` contract). `django-storages` deferred to S3/R2/MinIO swap (YAGNI); later swap = add `django-storages`+`boto3` + one `STORAGES` line, no code rewrite.
- **Thumbnails:** phase 1 serves full-size compressed photos; Pillow thumbnail generation 

### F. PII & consent (US-A8)
- Jurisdiction: Montenegro (GDPR-equivalent). Collect minimum: `telegram_id`, optional `username`.
- Users are maximally anonymous; nothing beyond Telegram login is stored.
- **Privacy policy / Terms required from launch** (visible to buyers without login).
- **Two distinct consent states (zone R3, decision K):** DECLINE (browse-only, no erasure) ≠ WITHDRAW (`consent_revoked_at` → soft-delete + 30-day PII erasure). Banner behavior in decision K.
- **Post-withdrawal erasure:** soft-delete immediately (`is_deleted=True`, `deleted_at=now()`) + full PII erasure exactly **30 days** after `consent_revoked_at` (idempotent `consent_hard_delete` sweep, advisory lock 3, `ERASURE_RETENTION_DAYS=30`; index `IX_users_erasure_sweep`):
  - NULL `telegram_id` + `username`; SET NULL `analytics_events.user_id` and `ModeratorActionLog.user_id`
  - DELETE user's Ad + AdImage rows via ORM `on_delete=CASCADE`; physical media files removed via `delete_photo()` after transaction commits (TX-then-FS pattern)
  - Anonymized ads (post-withdrawal, pre-hard-delete) persist for 30 days only — NOT the 120-day `purge_deleted_ads` window
  - **PII logging:** All `telegram_id` values in logger calls and `stdout.write` output are masked via `mask_telegram_id()` (SHA-256 hash, non-reversible, `tg_` prefix) from `apps/core/utils/sanitize.py`. Raw telegram_id must never appear in logs.
  - **Withdrawal UI:** Authenticated sellers can withdraw consent via a "Withdraw Data" POST button on the seller dashboard (`/dashboard/`), beside the Logout link. Requires CSRF token + confirmation dialog. Triggers `consent_withdraw` view → `withdraw_consent()`.
  - **Deleted-user banner guard:** No web-side middleware redirects soft-deleted users; the consent banner `{% include %}` is guarded by `{% if not request.user.is_authenticated or not request.user.is_deleted %}` in all 5 template sites (dashboard, detail, list, seller_dashboard, moderation_dashboard) to suppress rendering. `AnonymousUser` lacks `is_deleted`, so `is_authenticated` is checked first.
- Failed-check logs auto-purged after 7 days (separate sweep, zone D12).

### K. Consent banner & privacy behavior (zone R3, see O2)
- Browse before consent: buyer freely views published ads before accepting the banner.
- **DECLINE = browse-only:** blocks only seller login/actions. `consent_revoked_at` NOT set, no erasure, external "Contact seller" keeps working.
- **WITHDRAW/delete = WITHDRAW:** sets `consent_revoked_at`, triggers soft-delete + 30-day PII erasure (decision F). NOT the same as "decline".
- After accept, banner stays hidden on return.
- Site banner consent covers all PII processing including the bot; **no separate bot confirmation** required.
- Consent acceptance time recorded; withdrawal/deletion per decision F.

### G. Content language, search, city match (US-B2/B3/B7, US-B9)
- **Three UI languages:** Russian (ru), Bosnian (bs-latin), and English (en). Language preference detected via `LanguagePreMiddleware` which reads `?lang=X` query parameter, `lang_pref` cookie, or `Accept-Language` header (priority order), defaulting to Russian.
- **Language switcher UI:** Dropdown component in header allows users to switch languages; selection sets `lang_pref` cookie for persistence and navigates via `?lang=X` parameter.
- **Content stored in Russian** as base language. Multi-language columns (`title_en`, `title_bs`, `description_en`, `description_bs`) store translated content for UI display. `original_language` tracks source language for audit.
- **Search (phase 1) is over Russian content.** Queries in Bosnian or English translate to Russian at search time via `apps/search/services/query_translator.py`. Multi-language search vector includes all language variants using appropriate FTS configurations (`russian`, `simple`, `english`).
- **Stored-content-invariant (zone D5):** seller may input in any supported language, but the bot MUST translate title+description to Russian on ad creation. The bot delegates to the shared `apps.core.services.translation.translate_text` function (invoked in parallel via `asyncio.gather` + `asyncio.to_thread`), inheriting the same 500ms timeout, circuit breaker (3 failures → 60s cooldown), and LRU cache as the search-side translator, so `to_tsvector('russian', …)` is correct. UI displays localized content via `Ad.get_title(locale)` and `Ad.get_description(locale)` template filters.
- **Translation egress (data flow):** The `deep-translator` wrapper sends ad title/description (on creation) and search queries (on lookup) to **Google Translate** for language normalization. This is a best-effort, non-identifying content transfer — no user PII (`telegram_id`, `username`, IP) is included in the translation request. The egress is documented in the privacy/consent material (see zone R3, decision F).
- **Result sorting:** buyer chooses — by date (newest first) or by price.
- **City match is exact** against the closed preset list. Unrecognized city → "general / no city", not searchable.
- **City typos:** show "did you mean" suggestion via `difflib.get_close_matches` (no separate fuzzy lib needed for MVP).
- **Empty results:** friendly "nothing found" with a suggestion to broaden filters.

### H. Telegram login behavior (US-S1)
- Site "Login via Telegram" button opens a QR / code page.
- QR encodes deep-link `https://t.me/<bot_username>?start=login_<token>` (32-char URL-safe token, generated on site).
- Completion: user taps "Login" in bot → bot writes sender `telegram_id` into `LoginToken` via shared ORM → site checks token readiness and authenticates by `telegram_id` (create/find).
- Expired/invalid token: clear message + retry path. No silent failures.
- **Session:** persistent cookie, survives browser restart until explicit logout or long idle.
- Re-login reuses existing `telegram_id` (no duplicate account). Token is atomic, one-time, constant-time compare (`hmac.compare_digest`).

### I. Bot ad-creation dialog (US-S2)
- Strictly step-by-step, one field at a time: category → city → title → description → price (if applicable) → photos, each confirmed.
- Category: closed admin tree; bot suggests top 3–5; free-text-as-new-category rejected.
- Photos: 1–5 mandatory, **Telegram-compressed only**; document/file upload rejected with clear message; cannot publish without ≥1 photo.
- Preview before send; seller can fix mismatches (incl. city/category mapping).
- Abandoned draft auto-deleted on idle timeout (e.g. 30 min). No partial ads saved.

### J. Ad lifecycle & re-moderation (US-S5, US-S7, decision A)
- **Edits requiring re-moderation:** text edits (title/description) return ad to `ON_MODERATION` (`PUBLISHED → ON_MODERATION`, zone C2). Price/photo edits publish immediately.
- **Visibility on re-check:** ad pulled from public site immediately until it passes.
- **Archive/delete timers count from `published_at` (zone C3):** `published_at` updates on EVERY transition to `PUBLISHED` (incl. reactivation, price/photo edits) — this is the "timer reset on edit". `original_published_at` is a separate IMMUTABLE first-publish marker for audit only (does NOT drive sweep).
- **Reactivation:** seller can reactivate `ARCHIVED` ad from dashboard; re-publishes (text re-checked).
- **Independent timers:** failed-auto-check deletion (1 week, decision A, `moderation_failed_at`) and consent-withdrawal hard-delete (30 days, decision F) are separate from the archive/delete timers above.

### L. Usage analytics (phase 1)
- **Web traffic:** Plausible (cookieless, <1KB JS, EU-hosted SaaS) — JS snippet only, no Python dep, no consent banner needed (legitimate interest). Fallback: self-host Plausible CE / Umami via Docker.
- **Product metrics:** internal `AnalyticsEvent` model — `event_type` (StrEnum: `REGISTRATION_CREATED`, `AD_PUBLISHED`, `SEARCH_PERFORMED`, `CONTACT_INITIATED`), `timestamp`, optional `user_id`. Aggregated via ORM; admin/CLI `show_metrics` access.
- Privacy: Plausible collects no PII; mention traffic measurement in privacy policy. `user_id` references already-collected `telegram_id`.

### M. Trust signals system
- **Seller trust scoring** (`TrustCalculator`, `SellerTrustScore`): computed from activity (ad count, published ratio), quality (rejection rate), and response metrics (contact response rate). Score mapped to `TrustLevel` enum (`UNVERIFIED`, `VERIFIED`, `TRUSTED`, `PRO`). Recalculated on every ad publish via auto-moderation hook.
- **Seller verification** (`SellerVerification`): two verification paths — admin verification (manual, US-A11) and Telegram Premium auto-verification (`telegram_premium` field on `User`). Verified sellers receive the `VERIFIED` trust level.
- **Trust badges** (UI): rendered on ad detail and list pages via `trust_badge` template tag. Three badge templates (`verified_badge.html`, `trusted_badge.html`, `pro_badge.html`) with SVG icons and Tailwind styling.
- **Trust analytics** (`TrustAnalytics` service): daily trust score tracking, trust level distribution, and seller-level metrics for the seller dashboard.

### N. Photo thumbnails
- **Thumbnail generation** (`ThumbnailService`): three size variants — small (240x180), medium (640x480), large (1280x960) — generated via Pillow with LANCZOS resampling, EXIF orientation correction, and progressive JPEG (quality=85).
- **Storage**: thumbnail keys stored alongside originals in `MEDIA_ROOT`; keys follow `<uuid>-<size>.jpg` pattern. Original images preserved; thumbnails are additive.
- **Integration**: bot's `update_ad_and_moderate()` triggers thumbnail generation after each photo upload. Thumbnails served via `thumbnail_small_url`/`thumbnail_medium_url`/`thumbnail_large_url` properties on `AdImage`.

### O. Saved searches and autocomplete
- **Autocomplete** (`AutocompleteView`): hybrid suggestions from three sources — user search history (`SearchHistory`), popular searches (`PopularSearch`), and entity matching (categories + cities). Rate-limited (30 req/min per IP via cache). Results deduplicated and capped at 10.
- **Saved searches** (`SavedSearch`, `SavedSearchNotification`): buyers save search queries with city/category/price filters. New matching ads trigger notifications (deduplicated per search-ad pair).
- **Search history** (`SearchHistory`): per-user search query tracking with deduplication and 50-entry cap. Supports both authenticated and anonymous users.

### P. Seller dashboard statistics
- **Per-ad analytics** (`AnalyticsEvent.ad` FK): every analytics event can now be associated with a specific ad, enabling per-ad view and contact statistics.
- **AD_VIEWED event**: recorded on ad detail page views (seller-scoped — `user_id` is the seller, not the viewer).
- **SellerStats service**: aggregates events with 5-minute cache TTL; returns `total_views`, `total_contacts`, `ads_published`, and per-ad statistics filtered by `TimeRange` (`ALL_TIME`, `THIRTY_DAYS`, `SEVEN_DAYS`).
- **DailyAdMetrics model**: pre-aggregated daily view/contact counts per ad, supporting efficient dashboard queries without real-time ORM aggregation.
- **Rollup command** (`rollup_daily_metrics`): management command that computes `DailyAdMetrics` for all published ads, updates trust scores, and records moderation events. Uses advisory lock for idempotency.

### Q. Enhanced moderation tooling
- **AdModerationPriority model**: one-to-one with `Ad`; stores `base_score`, `priority_level` (`HIGH`/`MEDIUM`/`LOW`), risk `flags`, `confidence_score`, and `escalation_required` flag.
- **PriorityCalculator service**: computes priority scores from content risk (banned words) and user history (repeat offender, trust level). Maps score to `AdPriorityLevel` enum.
- **ModerationAnalytics service**: aggregates moderation statistics — pending queue size, moderator performance metrics, rejection reason breakdowns.
- **Auto-moderation integration**: `_pass_moderation()` and `_fail_moderation()` now create `AnalyticsEvent` records with `ad_id` for moderation tracking (`MODERATION_APPROVED`, `MODERATION_REJECTED`, `MODERATION_FLAGGED`).

### R. Seed data module (development-only)
- **Purpose:** Development-only demo data generation for visual evaluation, pagination testing, search/filter verification, and load testing.
- **Architecture:** A zero-model Django app (`apps.seed`) with no migrations. Registered in `INSTALLED_APPS` as `"apps.seed"`.
- **Management command:** `python manage.py seed [--users N] [--ads N] [--force] [--status-distribution JSON] [--analytics BOOL]`.
- **Generators** (all use `bulk_create` with chunking, no individual saves):
  - `UserGenerator` — creates fake seller users via Faker (`ru_RU`). Uses `itertools.count()` for unique `telegram_id`/`chat_id`. 30% probability of non-null `username`.
  - `AdGenerator` — creates ads referencing existing users/categories/cities. Reads category-specific templates from `ads_templates.json` (51+ templates across 30 categories). Multi-language support: populates `title`/`description` (ru), `title_en`/`description_en`, `title_bs`/`description_bs`, sets `original_language = "ru"`. Variable interpolation via `word_lists.json` (conditions, brands, features, cities, item_ages).
  - `ImageGenerator` — loads bundled CC0 photos from `photo_manifest.json` (~90 photos across 30 categories, 3-16 per category). Selects photos by ad category slug, falls back to default pool. Pre-processes all photos once: writes to `MEDIA_ROOT/seed/`, generates 3 thumbnail sizes via `ThumbnailService`.
  - `AnalyticsGenerator` — creates `AnalyticsEvent` records (`AD_VIEWED`) spread across 90 days with recent-biased distribution. Optionally creates `DailyAdMetrics` rollup records.
- **SeedService orchestrator:** Coordinates all generators, cleans seedable tables in FK-safe order (`DailyAdMetrics` → `AnalyticsEvent` → `AdImage` → `Ad` → seed `User`) plus `MEDIA_ROOT/seed/` directory. Uses session-scoped advisory lock ID 110 to prevent concurrent seeds.
- **Configuration:** `config/seed.default.json` — tunable parameters (status distribution weights, image count range, analytics range, Faker seed).
- **Static fixtures:**
  - `fixtures/categories.json` — real Montenegro classifieds category tree (django-mptt compatible, Russian names, 30 categories).
  - `fixtures/cities.json` — real Montenegro cities with `country_code="ME"`, regions, slugs.
  - `fixtures/ads_templates.json` — 50+ hierarchical templates with per-category patterns in ru/en/bs.
  - `fixtures/word_lists.json` — per-language word lists for template variable interpolation.
  - `fixtures/images/` — ~90 bundled CC0 JPEGs (≤100KB each, EXIF stripped) + `photo_manifest.json`.
- **Docker Compose integration:** One-shot `seed` service gated by `profiles: ["seed"]`. Follows `create_admin` pattern: `depends_on: migrate (completed)`, environment variables `SEED_USERS`/`SEED_ADS`, mounts `media_volume`. Run with `docker compose --profile seed run --rm seed`.
- **AdSource:** Seed ads are tagged with `AdSource.SEED = "seed"` for identification and cleanup.
- **Constraints:** Development-only (never run in production). Deterministic output via `Faker.seed_instance(42)`. No network dependencies at seed time (all resources bundled). Repo size increase ~9MB for photos (no Git LFS needed).

### S. Category & lookup architecture

A universal reference data system for ad categories and variable attributes, replacing hardcoded fixtures with a config-driven catalog builder.

**Multi-parent navigation** (`CategoryPath`): each category keeps exactly one canonical MPTT parent (unchanged) but can have zero or more alternative parent routes. Categories like "Bicycles" appear under both Transport and Sports & Hobbies through alternative paths. Alternative paths are navigation-only — they do not affect lookup inheritance or canonical category assignment. A special top-level category "Благотворительность" is auto-populated via system-created `CategoryPath` entries when `Ad.price = 0 | NULL`.

**Universal lookup system** (`LookupGroup` + `LookupItem`): variable ad attributes (listing purpose, item condition, features) are managed through a unified lookup system. Two built-in lookup groups ship with the project:
- `listing_purpose` — what the seller wants to do (sell, buy, rent, exchange, etc.). Every ad must have exactly one purpose.
- `listing_feature` — characteristics of the listing (new, used, urgent, with-delivery, etc.). An ad can have 0..N features.

**Category-lookup bindings** (`CategoryListingPurpose` + `CategoryListingFeature`): M:N through tables that link lookup values to categories. Each category defines which purposes and features are applicable. Inherited via the nearest-explicit-ancestor-wins algorithm: purposes/features defined on a parent category inherit to all MPTT descendants; an explicit definition on a subcategory replaces (not merges) the inherited set.

**Resolution service** (`CategoryLookupResolver`): a service that implements the inheritance algorithm with 5-minute cache TTL. Walks the canonical MPTT ancestor chain (leaf → root) to find the nearest category with explicit bindings. Signal-based invalidation on through-table changes, LookupItem toggles, and Category MPTT moves.

**Catalog builder** (`categories.yaml` + `builder.py`): a single YAML config file as the canonical source of truth for the category tree, lookup definitions, and their bindings. The builder module reads the YAML and creates/updates all records via Django ORM (`update_or_create` by slug). Supports category renames via `new_slug` transient field with automatic YAML rewrite. Used by both data migrations and the seed service.

**Photo deduplication** (`FileHashService` + `AdImage.sha256`): each uploaded image gets a SHA-256 hash computed on `save()`. If the same user already has an image with the same hash, the duplicate is skipped (reuses existing storage). Backfill migration computes hashes for existing rows.

**Key components:**
| Component | Location | Purpose |
|-----------|----------|---------|
| `apps.lookups` app | `src/backend/apps/lookups/` | LookupGroup, LookupItem models + admin |
| LookupGroupCode StrEnum | `apps/lookups/enums.py` | Machine-readable group codes |
| CategoryPath model | `apps/categories/models.py` | Alternative parent routes |
| Through models | `apps/categories/models.py` | CategoryListingPurpose, CategoryListingFeature |
| CategoryLookupResolver | `apps/categories/services/lookup_resolution.py` | Inheritance resolution with caching |
| LookupCacheService | `apps/lookups/services/cache_service.py` | Cache layer with signal-based invalidation |
| Catalog builder | `apps/categories/catalog/builder.py` | YAML-to-DB loader with rename support |
| Catalog YAML | `apps/categories/catalog/categories.yaml` | Canonical config for tree + lookups + paths |
| Ad.listing_purpose | `apps/ads/models.py` | Required FK to LookupItem |
| Ad.features | `apps/ads/models.py` | Optional M2M through AdFeature |
| FileHashService | `apps/media/services/hash_service.py` | SHA-256 computation for photo dedup |

**Schema details:** see [db-schema.md](../02-database/db-schema.md) for `lookup_groups`, `lookup_items`, `category_paths`, `category_listing_purposes`, `category_listing_features`, and `ad_features` tables.
**Enum details:** see [db-enums.md](../02-database/db-enums.md) for `LookupGroupCode`.
**Index details:** see [db-indexes.md](../02-database/db-indexes.md) for new indexes on through tables and `ad_images.sha256`.

## Functional Stories by Role

Full user stories (acceptance behavior per role) are the single source of truth in
[../04-user-stories/index.md](../04-user-stories/index.md):

- [Seller stories](../04-user-stories/seller-stories.md) — US-S1, S2, S5, S6, S7, S8, S9, S10, S11
- [Buyer stories](../04-user-stories/buyer-stories.md) — US-B1–B9, B10, B11, B12
- [Admin stories](../04-user-stories/admin-stories.md) — US-A1–A11, A12, A13, A14

## Owner Decisions (O1–O5)

Owner-level decisions are **owned by the product owner** and recorded in plain, owner-readable
language in [`../05-owner-decisions/index.md`](../05-owner-decisions/index.md) (single source of
truth). That file holds the full Decision / Technical-consequence split; this spec only links to it to
avoid duplicating owner decisions.

Each owner decision maps to one or more audit zones resolved inline above and in the database docs:

| Owner decision | Resolves audit zone(s) |
|----------------|------------------------|
| **O1** — turn-off-posting vs. delete vs. ban | R4 |
| **O2** — decline banner ≠ delete account | R3 |
| **O3** — full erasure 30 days after account deletion | R1 |
| **O4** — automated + manual moderation criteria | D3 / D4 |
| **O5** — category-name search in phase 1 | D1 / D2 |

### Account State Separation (O1/R4)

Phase 3 introduces three distinct account states that must not be conflated (zone R4):

| State | Field | Effect | Reversible | Phase 3 Implementation |
|-------|-------|--------|-----------|------------------------|
| **Publish restriction** | `ads_auto_publish = False` | Bot rejects NEW ads; existing ads hidden from public while active | Yes | Toggle via dashboard or admin; no deletion triggered |
| **Account ban** | `is_banned = True` | Blocks login and ALL ad actions; `telegram_id`/`username` retained for enforcement | Yes (admin unban) | Admin sets via `/admin/users/` |
| **Account deletion** | `is_deleted = True`, `consent_revoked_at = now()` | Triggers immediate soft-delete cascade + 30-day hard delete (Phase 4) | No | `telegram_id`/`username` nulled immediately; Phase 4 sweep handles final erasure |