---
id: packages
domain: wiki
tags:
  - stack
  - dependencies
  - versions
  - compatibility
related:
  - 01-technical-specification
  - 03-structure
  - 04-db-structure
---

## Purpose

Authoritative list of all Python packages, their pinned/minimum versions, and cross-compatibility
decisions for Mko Bazuna MVP (phase 1). This file is the **single source of truth** for the
dependency set. Every version here was validated against PyPI stable releases, Django 5.2 LTS,
and Python 3.14.

> **Owner versioning rule:** Use `>=` (minimum) for every package. Use `=` (or an upper bound
> like `<6.0`) ONLY where a critical incompatibility exists. Django is pinned to the LTS 5.2 line
> (`>=5.2.16,<6.0`) to avoid drift into 6.0, which several dependencies do not yet officially support.

## Stack Summary

*  Django 5.2 LTS + PostgreSQL 17
*  Django Admin
*  Filtration: django-filter, django-mptt
*  Search: PostgreSQL native FTS (search_vector TSVECTOR + GIN + pg_trgm, russian config)
*  API: Django Templates + HTMX + Alpine.js MPA for phase 1
*  Telegram bot (phase 1): aiogram 3.x — Bot API bot for login/contact/publish. Telethon is NOT used in phase 1.
*  Background jobs: Django management commands + systemd timer / cron (Celery + Redis deferred)
*  **Async bot + sync Django ORM (zone C5):** the bot runs `django.setup()` and shares the ORM.
   Blocking ORM calls and Telegram photo downloads are wrapped in `sync_to_async`. Each process
   holds its OWN psycopg3 pool (`CONN_MAX_AGE=0`); a shared external PgBouncer (transaction mode)
   is recommended. Migrations run exactly once before both processes start (see 03_structure.md).
*  Query translation: deep-translator (Bosnian -> Russian at search time; hard timeout ~500ms +
   fallback to the original query against GIN `search_vector`, zones C7/D5)

## Package List

```
# Core / Web
django>=5.2.16,<6.0              # Django 5.2 LTS (Python 3.14 supported since 5.2.8; LTS until Apr 2028).
                                  # Upper bound <6.0 blocks the major bump: django-filter / django-mptt
                                  # are not yet validated against Django 6.0.

# Database / Drivers
psycopg[binary]>=3.2.0            # psycopg 3 (Django 5.2 native support). Replaces psycopg2-binary.
                                  # psycopg2-binary has NO Python 3.14 wheel -> unusable on python:3.14-slim.
                                  # NOTE for PgBouncer transaction mode: set OPTIONS={"prepare_threshold": None}
                                  # to avoid server-side prepared-statement conflicts.

# Environment handling
django-environ>=0.11.0            # Typed .env casting (env.bool, env.db, env.int) — prevents "False"->True bugs.
                                  # python-dotenv becomes a transitive dependency.

# Models / Utils
django-mptt>=0.18.0               # Hierarchical categories. 0.18.0 is the first version officially
                                  # compatible with Django 5.2. (0.16.0 from the old doc is NOT validated.)
django-filter>=26.1              # List/API filters. 26.1 requires Django>=5.2 (CalVer: year.release).

# Search
# Native PostgreSQL full-text search (no external engine). No django-haystack / Whoosh.

# API
# djangorestframework==3.15.2  # DEFERRED to post-MVP (HTMX MPA in phase 1)

# Telegram integration (phase 1)
aiogram>=3.15.0                  # Bot API bot: login (decision H/Z25), contact (decision C),
                                  # seller publish dialog (US-S2). Free built-in FSM keeps the US-S2
                                  # step-by-step dialog simple. Telethon CAN also run a bot account
                                  # (bot-token login, serves deep links) but has NO built-in FSM.
                                  # Per owner rule, if the bot is harder in Telethon we use aiogram.
                                  # => aiogram for phase 1.
                                  # Group-scraping userbot (Telethon) is a SEPARATE future phase-2
                                  # service (decision B).
                                  #
                                  # IMPORTANT (zone C5): aiogram has NO built-in PostgreSQL FSM storage.
                                  # Built-in backends are MemoryStorage, RedisStorage, MongoStorage (+ 3rd-party
                                  # SQLite). We therefore DO NOT use a DB-backed FSM storage. Instead, the
                                  # in-progress ad is persisted as an `Ad` row with status=DRAFT via the shared
                                  # Django ORM (the same psycopg3 pool). The aiogram FSM is used only as a
                                  # lightweight step tracker on top of that draft — no second driver, no
                                  # separate FSM migration owner. (See 03_structure.md migration note.)

# Query translation (decision G: Bosnian query -> Russian)
deep-translator>=1.11.0           # Pure-Python; last release 2023 but works on 3.14. RISK: the default
                                  # Google-scrape backend is fragile (external HTML). Mitigation: hard
                                  # requests timeout (~500ms) + mandatory fallback to the original query.
                                  # Wrap calls in sync_to_async; isolate behind a TranslationBackend
                                  # interface so the backend can be swapped later (official API / LibreTranslate).

# Tasks
# celery==5.4.0 / redis==5.1.1  # DEFERRED to post-MVP.
# Phase-1 scheduled jobs (archive@2mo, delete@4mo, 7-day purge, 30-day consent hard-delete,
# 30-min draft sweep) run as Django management commands via systemd timer / cron.

# Frontend / Styling
django-tailwind>=4.4.0            # Tailwind CSS (standalone CLI mode — NO Node.js at runtime/build for
                                  # plain Tailwind). NOTE: standalone mode does NOT support plugins, so
                                  # daisyUI is intentionally EXCLUDED from phase 1 (it would require npm mode
                                  # + Node.js in the Dockerfile). Add daisyUI later via npm mode if needed.
django-htmx>=1.19.0               # HTMX integration for the MPA.

# Images / Media
pillow>=10.4.0                    # Image handling: download from Telegram, strict JPEG validation (zone R8).
                                  # REQUIRED in phase 1 (was missing from the old manifest).
#
# django-storages / boto3 — DEFERRED (YAGNI for phase 1).
# Phase 1 uses the built-in Django FileSystemStorage via STORAGES + local MEDIA_ROOT behind nginx.
# The STORAGES contract already lets us swap to S3/R2/MinIO later WITHOUT rewriting code — just add
# `django-storages>=1.14.6` + `boto3>=1.35.0` and one STORAGES line at swap time.
# django-storages 1.14.6 is compatible with Django 5.2 but is "maintenance at risk"; re-validate on swap.

# Analytics
# Web analytics: Plausible (cookieless, EU-hosted SaaS, ~$9/mo for 10k pageviews) — JS snippet only,
# NO Python dep. Fallback: self-host Plausible CE / Umami via Docker. Product metrics = internal
# AnalyticsEvent model (see spec decision L).

# Testing / Dev tools
pytest>=9.1.1                     # Tests (pyproject already on 9.1.1; old doc said 8.3.3).
pytest-django>=4.9.0             # Django fixtures / client for pytest. REQUIRED (was missing from manifest).
pytest-factoryboy>=2.7.0         # Model factories. Alternatively use model-bakery>=1.23.0
                                  # (actively maintained, Django 5.2 + Python 3.14) — preferred for MVP.

# Linting / Formatting
ruff>=0.15.20                     # Linter + formatter (pyproject already on 0.15.20).
```

## Compatibility Decisions (audit outcome)

| Package | Old doc | Recommended | Status | Note |
|---------|---------|-------------|--------|------|
| django | `==5.1.2` | `>=5.2.16,<6.0` | FIX | LTS 5.2; `<6.0` upper bound blocks unvalidated major bump. |
| psycopg[binary] | `>=3.2.0` (doc) / `psycopg2-binary` (pyproject) | `>=3.2.0` | FIX | psycopg2-binary has no 3.14 wheel; replace in pyproject. |
| django-environ | `>=0.11.0` | `>=0.11.0` | OK | |
| django-mptt | `==0.16.0` | `>=0.18.0` | FIX | 0.18.0 = first Django 5.2-compatible release. |
| django-filter | `==24.3` | `>=26.1` | FIX | 26.1 requires Django>=5.2. |
| aiogram | `>=3.15.0` | `>=3.15.0` | RISK | "PostgreSQL SQLStorage" does NOT exist — use Ad.DRAFT in ORM. |
| deep-translator | `>=1.11.0` | `>=1.11.0` | RISK | Google-scrape fragility; mitigate with timeout+fallback. |
| django-tailwind | `==4.4.2` (+daisyUI) | `>=4.4.0` | RISK | daisyUI excluded (standalone has no plugin support). |
| django-htmx | `==1.19.0` | `>=1.19.0` | OK | |
| django-storages | `==1.14.4` | DEFERRED | POSTPONE | YAGNI phase 1; built-in STORAGES suffices. |
| boto3 | `==1.35.0` | DEFERRED | POSTPONE | YAGNI phase 1; only for S3/R2 swap. |
| pillow | `>=10.4.0` | `>=10.4.0` | MISSING | Add to pyproject (needed phase 1). |
| pytest | `==8.3.3` | `>=9.1.1` | FIX | pyproject already 9.1.1. |
| pytest-django | `==4.9.0` | `>=4.9.0` | MISSING | Add to pyproject dev deps. |
| pytest-factoryboy | `==2.7.0` | `>=2.7.0` | OK | Or prefer model-bakery>=1.23.0. |
| ruff | `==0.9.0` | `>=0.15.20` | FIX | pyproject already 0.15.20. |

## Residual Risks

| Risk | Level | Mitigation |
|------|-------|------------|
| deep-translator Google-scrape fragility | HIGH | Hard timeout ~500ms + mandatory fallback to original query. |
| aiogram FSM "PostgreSQL SQLStorage" misconception | HIGH | Use `Ad.DRAFT` in shared Django ORM; no DB-backed FSM storage. |
| pillow / pytest-django missing from manifest | HIGH | Add to pyproject.toml (see above). |
| django-tailwind without daisyUI | MEDIUM | Plain Tailwind utilities suffice for MVP; add daisyUI later via npm mode. |
| django-storages maintenance-at-risk | LOW | Re-validate at S3/R2 swap time (post-MVP). |
