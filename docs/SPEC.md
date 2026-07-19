---
id: spec
domain: spec
tags:
  - specification
  - summary
  - agent-reference
related:
  - wiki/technical-specification
  - wiki/db-structure
  - wiki/architecture-structure
  - wiki/packages
  - wiki/audit-resolutions
---

# Mko Bazuna — Technical Specification (Agent Summary)

> Concise reference for agents and developers. Full detail in `docs/wiki/`.

## What the system is
Telegram-driven classifieds board (Avito-like) with a Django website. Sellers post ads through a **Telegram bot**; published ads appear on the site. Buyers browse/search/filter without login.

- **Launch market:** Bosnia & Herzegovina
- **Content language:** Russian (base)
- **UI:** Russian + Bosnian (latin)

## Stack
- Python 3.14, Django 5.2 LTS (`>=5.2.16,<6.0`), PostgreSQL 18
- django-mptt (categories), django-filter, django-tailwind + django-htmx (MPA), Pillow
- aiogram 3.x (Telegram bot), deep-translator (Bosnian→Russian query translation)
- Search: native PostgreSQL FTS (`search_vector` TSVECTOR + GIN + pg_trgm, russian config)
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
**Moderation (A):** auto-check is the only gate before `PUBLISHED`; moderator = admin role. Failed ads kept ≤1 week.

**Contact (C):** no seller identity on site; "Contact" = deep-link `t.me/<bot>?start=contact_<ad_id>`; rendered only if ad `PUBLISHED` + seller valid + consent not revoked.

**Categories (D):** closed admin tree (mptt); category-name search REQUIRED (denormalized `category_name` in `search_vector`, weight 'C' + difflib fuzzy → `category_id`).

**Photos (E):** 1–5, Telegram-compressed JPEG only; local `MEDIA_ROOT` via `FileSystemStorage` (django-storages deferred).

**Consent (F/K):** DECLINE (browse-only, no erase) ≠ WITHDRAW (sets `consent_revoked_at`, soft-delete + PII erasure after 30 days).

**Language/search (G):** content stored Russian; Bosnian query translated to Russian before FTS; exact city match + did-you-mean.

**Login (H):** QR deep-link `login_<token>` (32-char), `LoginToken` two-phase atomic claim, `hmac.compare_digest`.

**Lifecycle (J):** timers from `published_at` (reset on every PUBLISHED transition); text edits → `PUBLISHED→ON_MODERATION` + immediate hide; archive@2mo, delete@4mo.

## AdStatus state machine
`DRAFT → ON_MODERATION → PUBLISHED | REJECTED | ON_MODERATION_FAILED`;
`PUBLISHED → ARCHIVED → PUBLISHED` (reactivation); `PUBLISHED → ON_MODERATION` (text edit);
any → `DELETED`.

- `REJECTED` purged @90d; `ON_MODERATION_FAILED` purged @7d (`moderation_failed_at`)

## Key tables
`users`, `login_tokens`, `ads`, `categories`, `cities`, `ad_images`, `analytics_events`, `moderation_criteria`, `ModeratorActionLog`.

- PII erasure sweep index: `IX_users_erasure_sweep`
- Search index: `GinIndex IX_ads_search_gin`

## Owner decisions
O1: three independent states (ban / delete / publish-ban)
O2: "Decline" vs "Delete" banner
O3: full erasure
O4: two-layer moderation (auto criteria + manual photo review)
O5: category-name search required

## Deferred to post-MVP
DRF API, Celery/Redis, django-storages/boto3, Telethon group-scraping, EAV attributes, tags, multi-currency.

## Commands
| Task | Command |
|------|---------|
| Tests | `uv run pytest <path>` |
| Lint | `uv run ruff check <path>` |
| Type check | `uv run basedpyright <path>` |
| Add dep | `uv add <package>` |