---
id: spec-index
domain: spec
tags:
  - specification
  - summary
  - agent-reference
related:
  - ui-patterns
  - search-patterns
  - filter-ui
  - technical-specification
  - db-schema
  - db-indexes
  - db-enums
  - architecture-structure
  - packages-list
  - user-stories-index
  - design-system
  - owner-decisions-index
  - migration-workflow
---

# Mko Bazuna — Technical Specification (Agent Summary)

> Documents the target specification/architecture (source of truth: `docs/01-spec/`). Implementation is in progress.
> Concise reference for agents and developers. Full detail in `docs/01-spec/`.

## Purpose

Concise technical summary of the phase-1 specification for agents and developers. Pointers to the
authoritative detail in the sibling spec/DB/package docs. This file is the entry point; it must not
duplicate content that lives in those files.

## What the system is

Telegram-driven classifieds board (Avito-like) with a Django website. Sellers post ads through a **Telegram bot**; published ads appear on the site. Buyers browse/search/filter without login.

- **Launch market:** Montenegro
- **Content language:** Russian (base)
- **UI:** Russian + Montenegrin (latin)

## Stack

- Python 3.14, Django 5.2 LTS (`>=5.2.16,<6.0`), PostgreSQL 18
- django-mptt (categories), django-filter, django-tailwind + django-htmx (MPA), Pillow
- aiogram 3.x (Telegram bot), deep-translator (Montenegrin→Russian at ad publication only; search is per-language FTS, no query-time translation)
- Search: native PostgreSQL FTS (per-language `search_vector_ru/bs/en` TSVECTOR + GIN)
- Background jobs: Django management commands + cron (Celery deferred)
- Deployment: Docker (db + web[gunicorn sync WSGI] + bot + nginx)

## Two processes, one DB

- **web:** sync WSGI (gunicorn), server-rendered HTMX MPA
- **bot:** aiogram, runs `django.setup()`, shares the ORM
- Each process holds its own psycopg3 pool (`CONN_MAX_AGE=0`)
- PgBouncer (tx mode) recommended with `OPTIONS={"prepare_threshold": None}`
- **Migrations run exactly once** before web+bot start. The dev migration workflow (threshold-based consolidation, advisory-lock `migrate` service) is documented in [`docs/ops/migration-workflow.md`](../../ops/migration-workflow.md).
- aiogram has **no built-in PG FSM storage**: the step-by-step dialog is persisted as an `Ad` row with status `DRAFT` in the shared ORM

## Core domain rules

Product decisions (A–L) and zone resolutions are the single source of truth in
[`technical-specification.md`](technical-specification.md) and the database docs
([`db-schema.md`](../02-database/db-schema.md), [`db-indexes.md`](../02-database/db-indexes.md),
[`db-enums.md`](../02-database/db-enums.md)). High-impact rules for code:

- **Moderation (A):** auto-check is the only gate before `PUBLISHED`; moderator = admin role. Failed ads purged ≤1 week.
- **Contact (C):** no seller identity on site; "Contact" deep-link `t.me/<bot>?start=contact_<ad_id>`; rendered only if `PUBLISHED` + seller valid + consent not revoked.
- **Categories (D):** closed admin mptt tree; category-name search REQUIRED (denormalized `category_name` + per-language `search_vector_*` weight 'C' + `difflib` fuzzy → `category_id`). Search runs per-language FTS; no query-time translation.
- **Photos (E):** 1–5 Telegram-compressed JPEG only; local `MEDIA_ROOT` via `FileSystemStorage`.
- **Consent (F):** DECLINE (browse-only) ≠ WITHDRAW (`consent_revoked_at` → soft-delete + PII erasure after 30 days).
- **Language/search (G):** content stored Russian; Montenegrin query translated before FTS; exact city match + did-you-mean.
- **Consent banner (K):** buyers browse `PUBLISHED` ads before accepting; DECLINE blocks seller login only (no erasure, contact still works) ≠ WITHDRAW (`consent_revoked_at` + erasure). Banner covers bot too — no separate bot confirmation.
- **Login (H):** QR deep-link `login_<token>` (32-char), `LoginToken` two-phase atomic claim, `hmac.compare_digest`.
- **Lifecycle (J):** timers from `published_at` (reset on every PUBLISHED transition); text edits → `PUBLISHED→ON_MODERATION` + hide; archive@2mo, delete@4mo.

## AdStatus state machine

`DRAFT → ON_MODERATION → PUBLISHED | REJECTED | ON_MODERATION_FAILED`;
`PUBLISHED → ARCHIVED → PUBLISHED` (reactivation); `PUBLISHED → ON_MODERATION` (text edit);
any → `DELETED`.

- `REJECTED` purged @90d; `ON_MODERATION_FAILED` purged @7d (`moderation_failed_at`)

## Key tables

`users`, `login_tokens`, `ads`, `categories`, `category_paths`, `lookup_groups`, `lookup_items`, `category_listing_purposes`, `category_listing_features`, `ad_features`, `cities`, `ad_images`, `exchange_rates`, `analytics_events`, `moderation_criteria`, `ModeratorActionLog`, `DailyAdMetrics`, `SavedSearch`, `SavedSearchNotification`, `PopularSearch`, `SearchHistory`, `AdFavorite`, `SellerTrustScore`, `SellerVerification`, `AdModerationPriority`, `consent_records`.

- PII erasure sweep index: `IX_users_erasure_sweep`
- Search index: `GinIndex IX_ads_search_gin`

## UI Patterns

UI/UX patterns are documented in [`ui-patterns.md`](ui-patterns.md):

- **Responsive Grid Layout:** `grid-cols-1 md:grid-cols-2 lg:grid-cols-3` adaptive grid
- **Card-Based Ad Display:** Image, title, price, location hierarchy for quick scanning
- **Price Display:** Prominent `text-blue-600` styling
- **Contact Seller Button:** Deep-link to Telegram bot, anonymity-preserving
- **Image Gallery:** 1-5 Telegram photos in responsive grid with GLightbox v3.3.1 fullscreen overlay
- **Shared Navigation Headers:** Two variants — catalog header (list/detail, now includes auth/cabinet entry + favorites badge) and auth header (dashboards)
- **Touch Target Guidelines:** 44px minimum for interactive elements
- **Progressive Disclosure:** Truncated descriptions, empty states, HTMX pagination

## Search Patterns

Search UI patterns documented in [`search-patterns.md`](search-patterns.md):

- **Hero Search with Location:** Combined keyword + city selector on homepage
- **Language-aware FTS Search:** Per-language search vectors; no query-time translation
- **Did-You-Mean:** City typo suggestions via `difflib.get_close_matches`
- **Sort Options:** Date (newest) or price (low/high)
- **Empty States:** Friendly guidance when no results found

## Filter UI

Filter patterns documented in [`filter-ui.md`](filter-ui.md):

- **Sticky Sidebar Filters:** Desktop sidebar with category/city/price controls
- **Mobile Filter Drawer:** Slide-up panel on mobile devices
- **Filter Chips/Tags:** Removable active filter indicators
- **Category Hierarchical Navigation:** django-mptt tree traversal
- **Location-Based Filtering:** Closed Montenegro city list
- **Price Range Filter:** Min/max input fields

## Design System

Component catalog documented in [`design-system.md`](design-system.md):

- **Atomic Design:** Atoms (buttons, inputs), Molecules (search bar, price display), Organisms (ad cards, headers)
- **Button Variants:** Primary, secondary, disabled, danger, icon with accessibility states
- **Card Patterns:** Ad card, dashboard card, image placeholder patterns
- **Form Elements:** Input, textarea, select with error states and validation
- **Navigation:** Header with breadcrumbs, pagination controls, mobile drawer
- **Status Indicators:** Badges for ad status, trust signals, loading states
- **Layout:** Responsive grid system, spacing scale based on 8px grid

## User stories

Full acceptance behavior per role: [index](../04-user-stories/index.md) —
[seller](../04-user-stories/seller-stories.md), [buyer](../04-user-stories/buyer-stories.md),
[admin](../04-user-stories/admin-stories.md).

## Owner decisions

Owner decisions O1–O5 (plain, owner-readable) live in
[`../05-owner-decisions/index.md`](../05-owner-decisions/index.md). The full
zone-resolution summary (C1–C8, R1–R9, D1–D12) is distributed inline across the spec and database
docs by zone ID.

## Deferred to post-MVP

DRF API, Celery/Redis, django-storages/boto3, Telethon group-scraping.

## Phase 2 Features

The following significant features have been implemented beyond the Phase 1 baseline and are documented in the relevant subsystem docs:

| Feature | Description | Key Components |
|---------|-------------|----------------|
| **Seller Dashboard Statistics** | Per-ad analytics with time-range filtering for sellers | `SellerStats` service, `DailyAdMetrics` model, `AD_VIEWED` event, caching |
| **Photo Thumbnails** | Three-size thumbnail generation (small/medium/large) for ad images | `ThumbnailService`, `AdImage` thumbnail fields, media app |
| **Search Autocomplete** | Hybrid autocomplete from user history, popular searches, and entity matching | `PopularSearch`, `SearchHistory`, `SavedSearch`, `AutocompleteView`, rate limiting |
| **Saved Search Alerts** | Buyers save search queries and receive notifications when matching ads appear | `SavedSearch`, `SavedSearchNotification`, `AlertQueryService` |
| **Filter UI** | Sticky sidebar filters (desktop), slide-up drawer (mobile), removable filter chips, hierarchical category tree, closed-list city selector, and price range inputs with HTMX partial updates | [`filter-ui.md`](filter-ui.md), `CategoryFilterForm`, query params `category`/`city`/`price_min`/`price_max` |
| **Catalog Filters & Sorting** | New buyer filter dimensions `listing_purpose` (single-select) and `features` (multi-select, AND semantics) with category-constrained option resolution; price filter/sort on `price_normalized_eur` with `NULLS LAST` and a `-rank, -published_at, -id` relevance tiebreaker | [`filter-ui.md`](filter-ui.md), [`search-patterns.md`](search-patterns.md), `Ad.listing_purpose`, `Ad.features`, `AdFeature`, `IX_ads_pub_purpose`, `IX_ad_features_feature_id`, query params `listing_purpose`/`features` |
| **Multi-Currency Price Model** | Sellers set an original amount + currency (EUR/RSD/BAM); ads store `price_amount`, `price_currency`, and a derived `price_normalized_eur` (EUR) used for all cross-currency filter/sort. Current exchange rates live in `exchange_rates`; normalization is centralized in `PriceNormalizer` (cached current-rate lookup) and re-derivable via the `recompute_normalized_prices` command. Legacy `price` (BAM) backfilled ×0.512 on migration | `apps/currencies` app (`CurrencyCode`, `ExchangeRate`, `PriceNormalizer`, `recompute_normalized_prices`), `Ad.price_amount`/`price_currency`/`price_normalized_eur`, `IX_ads_price_normalized_eur`, [`db-schema.md`](../02-database/db-schema.md), [`db-enums.md`](../02-database/db-enums.md), [`db-indexes.md`](../02-database/db-indexes.md) |
| **Trust Signals** | Seller trust scoring, verification, and badge display | `SellerTrustScore`, `SellerVerification`, `TrustCalculator`, trust badges |
| **Enhanced Moderation** | Priority-based moderation queue with scoring and analytics | `AdModerationPriority`, `PriorityCalculator`, `ModerationAnalytics` |
| **Seed Data Module** | Development-only demo data generation with configurable CLI parameters | `apps.seed` app, `SeedService`, `UserGenerator`, `AdGenerator`, `ImageGenerator`, `AnalyticsGenerator`, `Seed` advisory lock (ID 110). See [`docs/seed-workflow.md`](../seed-workflow.md) for full workflow documentation. |
| **Seed Content Fixtures** | Realistic bundled photos and multi-language ad templates for seed data | `ImageGenerator` manifest loading, `AdGenerator` template interpolation, `photo_manifest.json`, `ads_templates.json`, `word_lists.json` |
| **Category & Lookup Architecture** | Universal reference data system with multi-parent category navigation, config-driven catalog builder, and inheritance-based lookup resolution | `apps.lookups` app (LookupGroup, LookupItem), `CategoryPath` multi-parent model, `CategoryLookupResolver` service, `categories.yaml` + `builder.py`, `FileHashService` for photo dedup |
| **Seed-Category Integration Audit** | Audited and remediated seed module to be fully compatible with the canonical `categories.yaml` category system; removed old-slug references, orphaned fixtures, and dead code; documented the seed workflow | `apps.seed` code/test updates, `.ai/llm-tasks/seed-content-generation.md` rewrite, `scripts/seed-images-config.json` bump, `docs/seed-workflow.md` |
| **Preferred City** | Persistent default-city selector in the catalog header with hybrid persistence (DB FK for authenticated users; consent-gated 1-year cookie for guests) and login reconciliation | `PreferredCityMiddleware`, `header_context`, `apps/search/views/preferred_city.py`, `User.preferred_city` FK |
| **Consent & GDPR Compliance** | Consent banner, granular cookie consent, `/privacy/` policy page, `ConsentRecord` audit log, and Plausible/GLightbox script gating | `apps/users/views/consent.py`, `apps/users/context_processors.py` (`consent_state`), `consent_records` table, `core/urls.py` (`/privacy/`) |

## Commands

| Task | Command |
|------|---------|
| Tests | `uv run pytest <path>` |
| Lint | `uv run ruff check <path>` |
| Type check | `uv run basedpyright <path>` |
| Add dep | `uv add <package>` |