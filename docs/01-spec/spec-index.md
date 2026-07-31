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
- aiogram 3.x (Telegram bot), deep-translator (Montenegrin→Russian query translation)
- Search: native PostgreSQL FTS (`search_vector` TSVECTOR + GIN, russian config)
- Background jobs: Django management commands + cron (Celery deferred)
- Deployment: Docker (db + web[gunicorn sync WSGI] + bot + nginx)

## Two processes, one DB

- **web:** sync WSGI (gunicorn), server-rendered HTMX MPA
- **bot:** aiogram, runs `django.setup()`, shares the ORM
- Each process holds its own psycopg3 pool (`CONN_MAX_AGE=0`)
- PgBouncer (tx mode) recommended with `OPTIONS={"prepare_threshold": None}`
- **Migrations run exactly once** before web+bot start
- aiogram has **no built-in PG FSM storage**: the step-by-step dialog is persisted as an `Ad` row with status `DRAFT` in the shared ORM

## Core domain rules

Product decisions (A–L) and zone resolutions are the single source of truth in
[`technical-specification.md`](technical-specification.md) and the database docs
([`db-schema.md`](../02-database/db-schema.md), [`db-indexes.md`](../02-database/db-indexes.md),
[`db-enums.md`](../02-database/db-enums.md)). High-impact rules for code:

- **Moderation (A):** auto-check is the only gate before `PUBLISHED`; moderator = admin role. Failed ads purged ≤1 week.
- **Contact (C):** no seller identity on site; "Contact" deep-link `t.me/<bot>?start=contact_<ad_id>`; rendered only if `PUBLISHED` + seller valid + consent not revoked.
- **Categories (D):** closed admin mptt tree; category-name search REQUIRED (denormalized `category_name` in `search_vector`, weight 'C' + `difflib` fuzzy → `category_id`).
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

`users`, `login_tokens`, `ads`, `categories`, `cities`, `ad_images`, `analytics_events`, `moderation_criteria`, `ModeratorActionLog`, `DailyAdMetrics`, `SavedSearch`, `SavedSearchNotification`, `PopularSearch`, `SearchHistory`, `SellerTrustScore`, `SellerVerification`, `AdModerationPriority`.

- PII erasure sweep index: `IX_users_erasure_sweep`
- Search index: `GinIndex IX_ads_search_gin`

## UI Patterns

UI/UX patterns are documented in [`ui-patterns.md`](ui-patterns.md):

- **Responsive Grid Layout:** `grid-cols-1 md:grid-cols-2 lg:grid-cols-3` adaptive grid
- **Card-Based Ad Display:** Image, title, price, location hierarchy for quick scanning
- **Price Display:** Prominent `text-blue-600` styling
- **Contact Seller Button:** Deep-link to Telegram bot, anonymity-preserving
- **Image Gallery:** 1-5 Telegram photos in responsive grid
- **Sticky Navigation Header:** Consistent header with shadow separation
- **Touch Target Guidelines:** 44px minimum for interactive elements
- **Progressive Disclosure:** Truncated descriptions, empty states, HTMX pagination

## Search Patterns

Search UI patterns documented in [`search-patterns.md`](search-patterns.md):

- **Hero Search with Location:** Combined keyword + city selector on homepage
- **Query Translation:** Montenegrin→Russian before PostgreSQL FTS
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

DRF API, Celery/Redis, django-storages/boto3, Telethon group-scraping, multi-currency.

## Phase 2 Features

The following significant features have been implemented beyond the Phase 1 baseline and are documented in the relevant subsystem docs:

| Feature | Description | Key Components |
|---------|-------------|----------------|
| **Seller Dashboard Statistics** | Per-ad analytics with time-range filtering for sellers | `SellerStats` service, `DailyAdMetrics` model, `AD_VIEWED` event, caching |
| **Photo Thumbnails** | Three-size thumbnail generation (small/medium/large) for ad images | `ThumbnailService`, `AdImage` thumbnail fields, media app |
| **Search Autocomplete** | Hybrid autocomplete from user history, popular searches, and entity matching | `PopularSearch`, `SearchHistory`, `SavedSearch`, `AutocompleteView`, rate limiting |
| **Saved Search Alerts** | Buyers save search queries and receive notifications when matching ads appear | `SavedSearch`, `SavedSearchNotification`, `AlertQueryService` |
| **Trust Signals** | Seller trust scoring, verification, and badge display | `SellerTrustScore`, `SellerVerification`, `TrustCalculator`, trust badges |
| **Enhanced Moderation** | Priority-based moderation queue with scoring and analytics | `AdModerationPriority`, `PriorityCalculator`, `ModerationAnalytics` |
| **Seed Content Fixtures** | Realistic bundled photos and multi-language ad templates for seed data | `ImageGenerator` manifest loading, `AdGenerator` template interpolation, `photo_manifest.json`, `ads_templates.json`, `word_lists.json` |

## Commands

| Task | Command |
|------|---------|
| Tests | `uv run pytest <path>` |
| Lint | `uv run ruff check <path>` |
| Type check | `uv run basedpyright <path>` |
| Add dep | `uv add <package>` |