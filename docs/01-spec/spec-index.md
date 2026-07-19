---
id: spec-index
domain: spec
tags:
  - specification
  - summary
  - agent-reference
related:
  - technical-specification
  - db-schema
  - db-indexes
  - db-enums
  - architecture-structure
  - packages-list
  - user-stories-index
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
Product decisions (A–L) and zone resolutions are the single source of truth in
[`technical-specification.md`](technical-specification.md) and the database docs
([`db-schema.md`](../02-database/db-schema.md), [`db-indexes.md`](../02-database/db-indexes.md),
[`db-enums.md`](../02-database/db-enums.md)). High-impact rules for code:

- **Moderation (A):** auto-check is the only gate before `PUBLISHED`; moderator = admin role. Failed ads purged ≤1 week.
- **Contact (C):** no seller identity on site; "Contact" deep-link `t.me/<bot>?start=contact_<ad_id>`; rendered only if `PUBLISHED` + seller valid + consent not revoked.
- **Categories (D):** closed admin mptt tree; category-name search REQUIRED (denormalized `category_name` in `search_vector`, weight 'C' + `difflib` fuzzy → `category_id`).
- **Photos (E):** 1–5 Telegram-compressed JPEG only; local `MEDIA_ROOT` via `FileSystemStorage`.
- **Consent (F):** DECLINE (browse-only) ≠ WITHDRAW (`consent_revoked_at` → soft-delete + PII erasure after 30 days).
- **Language/search (G):** content stored Russian; Bosnian query translated before FTS; exact city match + did-you-mean.
- **Consent banner (K):** buyers browse `PUBLISHED` ads before accepting; DECLINE blocks seller login only (no erasure, contact still works) ≠ WITHDRAW (`consent_revoked_at` + erasure). Banner covers bot too — no separate bot confirmation.
- **Login (H):** QR deep-link `login_<token>` (32-char), `LoginToken` two-phase atomic claim, `hmac.compare_digest`.
- **Lifecycle (J):** timers from `published_at` (reset on every PUBLISHED transition); text edits → `PUBLISHED→ON_MODERATION` + hide; archive@2mo, delete@4mo.

## AdStatus state machine
`DRAFT → ON_MODERATION → PUBLISHED | REJECTED | ON_MODERATION_FAILED`;
`PUBLISHED → ARCHIVED → PUBLISHED` (reactivation); `PUBLISHED → ON_MODERATION` (text edit);
any → `DELETED`.

- `REJECTED` purged @90d; `ON_MODERATION_FAILED` purged @7d (`moderation_failed_at`)

## Key tables
`users`, `login_tokens`, `ads`, `categories`, `cities`, `ad_images`, `analytics_events`, `moderation_criteria`, `ModeratorActionLog`.

- PII erasure sweep index: `IX_users_erasure_sweep`
- Search index: `GinIndex IX_ads_search_gin`

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
DRF API, Celery/Redis, django-storages/boto3, Telethon group-scraping, EAV attributes, tags, multi-currency.

## Commands
| Task | Command |
|------|---------|
| Tests | `uv run pytest <path>` |
| Lint | `uv run ruff check <path>` |
| Type check | `uv run basedpyright <path>` |
| Add dep | `uv add <package>` |
