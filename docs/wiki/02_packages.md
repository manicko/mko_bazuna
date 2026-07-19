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
dependency set. Every version here was validated against PyPI stable releases (audit dated
2026-07-18), Django 5.2 LTS, and Python 3.14.

> **Version audit status (2026-07-18):** All packages below were re-checked against PyPI stable
> releases by a 3x Research + 2x Audit + 1x Validation pipeline. The Validator **APPROVED** the
> version set. The only mandatory code correction identified was bumping `pytest-asyncio` to
> `>=1.4.0` in `pyproject.toml` (pending implementation — this audit is documentation only).
> `pyproject.toml` is currently consistent with this document for runtime deps (psycopg3 + all
> required runtime/dev deps present; `python-dotenv` is transitive via django-environ).

> **Owner versioning rule:** Use `>=` (minimum) for every package. Use `=` (or an upper bound
> like `<6.0`) ONLY where a critical incompatibility exists. Django is pinned to the LTS 5.2 line
> (`>=5.2.16,<6.0`) to avoid drift into 6.0, which django-mptt does not yet officially support.

## Stack Summary

*  Django 5.2 LTS + PostgreSQL 18 (upgrade from 17 — see Infrastructure & Runtime section)
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
                                   # Upper bound <6.0 blocks the major bump: django-mptt is NOT validated
                                   # against Django 6.0 (only 0.19rc1 exists, and the package is now unmaintained).

# Database / Drivers
psycopg[binary]>=3.2.0            # psycopg 3 (Django 5.2 native-support, recommended driver). Replaces psycopg2-binary.
                                   # NOTE (2026-07 audit): psycopg2-binary 2.9.11+ NOW ships Python 3.14 wheels, so the
                                   # old "no 3.14 wheel" rationale is obsolete. We still use psycopg3 because it is the
                                   # Django-recommended driver and the documented PgBouncer recipe (below) is psycopg3-specific.
                                   # For PgBouncer transaction mode set OPTIONS={"prepare_threshold": None}
                                   # to avoid server-side prepared-statement conflicts (verified correct at psycopg 3.3.x).

# Environment handling
django-environ>=0.11.0            # Typed .env casting (env.bool, env.db, env.int) — prevents "False"->True bugs.
                                   # python-dotenv is TRANSITIVE (do NOT declare it as a direct dep).

# Models / Utils
django-mptt>=0.18.0               # Hierarchical categories. 0.18.0 is the first version officially
                                   # compatible with Django 5.2. 0.19 is pre-release only (0.19rc1). Package is now
                                   # best-effort maintained — see Residual Risks (R-mptt).
django-filter>=26.1              # List/API filters. 26.1 requires Django>=5.2 (CalVer: year.release).

# Search
# Native PostgreSQL full-text search (no external engine). No django-haystack / Whoosh.

# API
# djangorestframework>=3.15.2  # DEFERRED to post-MVP (HTMX MPA in phase 1)

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
                                   # Built-in backends are MemoryStorage, RedisStorage, PyMongoStorage (+ 3rd-party
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
# celery>=5.4.0 / redis>=5.1.1  # DEFERRED to post-MVP.
# Phase-1 scheduled jobs (archive@2mo, delete@4mo, 7-day purge, 30-day consent hard-delete,
# 30-min draft sweep) run as Django management commands via systemd timer / cron.

# Frontend / Styling
django-tailwind>=4.4.0            # Tailwind CSS (standalone CLI mode — NO Node.js at runtime/build for
                                   # plain Tailwind). NOTE: standalone mode does NOT support plugins, so
                                   # daisyUI is intentionally EXCLUDED from phase 1 (would require npm mode
                                   # + Node.js in the Dockerfile). Add daisyUI later via npm mode if needed.
                                   # 2026-07 audit: `django-tailwind` (timonweb, 4.5.0) and the separate
                                   # `django-tailwind-cli` (django-commons, 4.6.2) are BOTH maintained. Both
                                   # technically support daisyUI — its exclusion is a PROJECT CHOICE, not a
                                   # technical limitation. We keep `django-tailwind` (timonweb) per prior decision.
django-htmx>=1.19.0               # HTMX integration for the MPA.

# Images / Media
pillow>=10.4.0                    # Image handling: download from Telegram, strict JPEG validation (zone R8).
                                   # REQUIRED in phase 1. JPEG API (Image.open / verify / format=="JPEG")
                                   # is unchanged in Pillow 12.x.
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
pytest>=9.1.1                     # Tests (pyproject already on 9.1.1).
pytest-django>=4.9.0             # Django fixtures / client for pytest. REQUIRED.
pytest-factoryboy>=2.7.0         # Model factories. Alternatively use model-bakery>=1.23.0
                                   # (actively maintained, Django 5.2 + Python 3.14) — preferred for MVP
                                   # (model-bakery>=1.23.0 is already in the dev group).
pytest-asyncio>=0.24              # REQUIRED for aiogram async handler tests. ACTION: bump to >=1.4.0
                                   # (1.x removed legacy mode + event_loop fixture, strict default, needs pytest>=8.4).
                                   # Add asyncio_mode="strict" to [tool.pytest.ini_options] when bot tests are written.

# Linting / Formatting
ruff>=0.15.20                     # Linter + formatter (pyproject already on 0.15.20). 0.15.x introduced
                                   # the 2026 formatter style guide (opt-in via preview); project selects only
                                   # E,F,I,B,UP so new ASYNC* rules do not fire. No action needed.
```

## Latest Stable Versions (audit 2026-07-18)

Latest stable release found on PyPI at audit time, with the recommended floor from this document.

| Package | Current (doc/toml) | Latest stable | Recommended | Compat status | Comment / risk |
|---------|--------------------|---------------|-------------|---------------|----------------|
| django | `>=5.2.16,<6.0` | 5.2.16 | `>=5.2.16,<6.0` | VALID | LTS until Apr 2028; `<6.0` protects django-mptt. |
| psycopg[binary] | `>=3.2.0` | 3.3.4 | `>=3.2.0` | VALID | psycopg3 native py3.14 wheels; `prepare_threshold=None` for PgBouncer verified. |
| django-environ | `>=0.11.0` | 0.14.0 | `>=0.11.0` | VALID | python-dotenv is transitive. |
| django-mptt | `>=0.18.0` | 0.18.0 | `>=0.18.0` | VALID | First Django 5.2-compatible; pure Python (py3.14 ok in practice). No stable 0.19. |
| django-filter | `>=26.1` | 26.1 | `>=26.1` | VALID | CalVer floor Django>=5.2, py3.14 OK. |
| aiogram | `>=3.15.0` | 3.30.0 | `>=3.15.0` | VALID | Py>=3.10,<3.15 (3.14 OK). No PG FSM storage; use ORM draft row. |
| deep-translator | `>=1.11.0` | 1.11.4 | `>=1.11.0` | RISK | Google-scrape fragility; hard timeout + fallback required. |
| django-tailwind | `>=4.4.0` | 4.5.0 | `>=4.4.0` | RISK | Standalone CLI no Node; daisyUI exclusion is a project choice. |
| django-htmx | `>=1.19.0` | 1.28.0 | `>=1.19.0` | VALID | Pure Python, Django 5.2 compatible. |
| pillow | `>=10.4.0` | 12.3.0 | `>=10.4.0` | VALID | py3.14 wheels; JPEG API unchanged (zone R8). |
| pytest | `>=9.1.1` | 9.1.1 | `>=9.1.1` | VALID | Latest stable; compatible with pytest-asyncio 1.4.0. |
| pytest-django | `>=4.9.0` | 4.12.0 | `>=4.9.0` | VALID | Django 5.2/6.0 + py3.14 support. |
| pytest-factoryboy | `>=2.7.0` | 2.8.1 | `>=2.7.0` | VALID | Or prefer model-bakery>=1.23.0 (already in dev group). |
| pytest-asyncio | `>=0.24` | 1.4.0 | `>=1.4.0` (ACTION) | VALID | REQUIRED for aiogram async tests; bump from 0.24 (major breaking jump). |
| pytest-cov | `>=7.1.0` | 7.1.0 | `>=7.1.0` | VALID | Coverage plugin. |
| model-bakery | `>=1.23.0` | 1.24.0 | `>=1.23.0` | VALID | Preferred over pytest-factoryboy. |
| hypothesis | `>=6.156.1` | 6.156.x | `>=6.156.1` | VALID | Property-based testing. |
| basedpyright | `>=1.39.9` | 1.39.9 | `>=1.39.9` | VALID | Type checking. |
| pyright | `>=1.1.411` | 1.1.411 | `>=1.1.411` | VALID | Type checking. |
| ruff | `>=0.15.20` | 0.15.22 | `>=0.15.20` | VALID | Lint/format; py3.14 OK. |
| radon | `>=6.0.1` | 6.0.1 | `>=6.0.1` | VALID | Complexity metrics (2023, still works). |
| python-dotenv | (transitive) | 1.2.2 | transitive | VALID | NOT a direct dep — pulled in by django-environ. |
| postgres (image) | `postgres:17` / `postgres:17-alpine` | 18.4 | `postgres:18` / `postgres:18-alpine` | VALID | PG 18 GA/stable (Sep 2025). Safe upgrade: plpgsql triggers, GIN, `to_tsvector('russian')`, `pg_trgm` all compatible; reindex FTS/trgm after upgrade. |
| python (base image) | `python:3.14-slim` | 3.14.6 | `python:3.14-slim` | VALID | 3.14 is current stable; supported to 2030. |
| uv | unpinned (`pip install uv`) | 0.11.28 | `uv>=0.11.28` | VALID | Pin for reproducibility in Dockerfile. |
| nginx | `nginx:alpine` | 1.30.4 | `nginx:stable` or `nginx:alpine` | VALID | 1.28.x now EOL; alpine tracks 1.30.x. |
| gunicorn | unpinned (not in pyproject) | 26.0.0 | `gunicorn>=26.0` | VALID | Sync WSGI; Django 5.2 + py3.14 OK. Add to deps. |
| whitenoise | implied for /static/ | 6.12.0 | `whitenoise>=6.12.0` | VALID | Used for /static/; NOT yet in pyproject — add. Media still needs nginx. |
| pgbouncer | unpinned (recommended) | 1.25.2 | `pgbouncer>=1.25.2` | VALID | Transaction-mode pooler. Use >=1.25.2 (SCRAM regression in 1.25.1 w/ PG18). |
| django-storages | `>=1.14.6` (deferred) | 1.14.6 | DEFERRED | VALID | Django 5.2 OK; re-validate at S3/R2 swap. |
| boto3 | `>=1.35.0` (deferred) | 1.43.46 | DEFERRED | VALID | Python 3.14 OK; only for S3/R2 swap. |
| celery | `==5.4.0` (deferred) | 5.6.2 | DEFERRED | VALID | Python 3.14 + Django 5.2 OK; post-MVP. |
| redis-py | `==5.1.1` (deferred) | 8.0.1 | DEFERRED | VALID | 8.x uses RESP3 by default (breaking); only for celery broker, post-MVP. |
| telethon | phase-2 only | 1.44.0 | DEFERRED (phase 2) | VALID | Python 3.14 OK; userbot scraping, NOT phase 1. Latest stable 1.44.0 (released 2026-06-15); phase-5 plan pins `telethon>=1.44.0`. |

## Infrastructure & Runtime

These are non-PyPI components pinned in `docker/Dockerfile`, `docker-compose.yml`, and the
structure docs. They were added to the audit on 2026-07-19 after the initial PyPI-only pass.
All are compatible with Django 5.2 + Python 3.14 + psycopg3.

* **PostgreSQL 17 -> 18:** PG 18.4 is GA and stable. The project's FTS stack
  (`TSVECTOR` + GIN + `pg_trgm` + plpgsql triggers + `to_tsvector('russian')`) is fully
  compatible. Breaking-change notes: page checksums on by default for NEW clusters, MD5 auth
deprecated (use SCRAM), `VACUUM`/`ANALYZE` now include inheritance children by default.
  ACTION: bump `postgres:17` -> `postgres:18` in `docker-compose.yml` and `postgres:17-alpine`
  -> `postgres:18-alpine` in `03_structure.md`; plan a `pg_upgrade`/dump-restore + reindex of
  GIN and `pg_trgm` indexes.
* **uv:** pin `uv>=0.11.28` in the Dockerfile instead of unpinned `pip install uv`.
* **gunicorn:** pin `gunicorn>=26.0` and add to `[project].dependencies` (web is sync WSGI).
* **whitenoise:** docs reference it for `/static/` but it is absent from `pyproject.toml`;
  add `whitenoise>=6.12.0` if used in production (media still served by nginx).
* **PgBouncer:** when deployed, pin `pgbouncer>=1.25.2` (>=1.25.2 avoids the SCRAM regression
  with PG 18 present in 1.25.1). The `prepare_threshold=None` psycopg3 recipe stays.
* **nginx:** `nginx:alpine` now tracks 1.30.x (1.28.x EOL) — acceptable; `nginx:stable` is
  the explicit alternative.
* **Deferred (phase 2 / swap):** django-storages, boto3, celery, redis-py, telethon — keep
  deferred per YAGNI; their latest stable versions are noted above for when they are adopted.
## Compatibility Decisions (audit outcome)

| Package | Old doc | Recommended | Status | Note |
|---------|---------|-------------|--------|------|
| django | `==5.1.2` | `>=5.2.16,<6.0` | FIX | LTS 5.2; `<6.0` upper bound blocks unvalidated major bump (mptt). |
| psycopg[binary] | `>=3.2.0` (doc) / `psycopg2-binary` (old pyproject) | `>=3.2.0` | FIX | psycopg2-binary now HAS 3.14 wheels (2.9.11+), but psycopg3 remains the recommended driver; pyproject already updated. |
| django-environ | `>=0.11.0` | `>=0.11.0` | OK | In pyproject; python-dotenv transitive. |
| django-mptt | `==0.16.0` | `>=0.18.0` | FIX | 0.18.0 = first Django 5.2-compatible release. |
| django-filter | `==24.3` | `>=26.1` | FIX | 26.1 requires Django>=5.2. |
| aiogram | `>=3.15.0` | `>=3.15.0` | RISK | "PostgreSQL SQLStorage" does NOT exist — use Ad.DRAFT in ORM. |
| deep-translator | `>=1.11.0` | `>=1.11.0` | RISK | Google-scrape fragility; mitigate with timeout+fallback. |
| django-tailwind | `==4.4.2` (+daisyUI) | `>=4.4.0` | RISK | daisyUI excluded by project choice (standalone has no plugin support). |
| django-htmx | `==1.19.0` | `>=1.19.0` | OK | |
| django-storages | `==1.14.4` | DEFERRED | POSTPONE | YAGNI phase 1; built-in STORAGES suffices. |
| boto3 | `==1.35.0` | DEFERRED | POSTPONE | YAGNI phase 1; only for S3/R2 swap. |
| pillow | `>=10.4.0` | `>=10.4.0` | OK | Now in pyproject (needed phase 1). |
| pytest | `==8.3.3` | `>=9.1.1` | FIX | pyproject already 9.1.1. |
| pytest-django | `==4.9.0` | `>=4.9.0` | OK | Now in pyproject dev deps. |
| pytest-factoryboy | `==2.7.0` | `>=2.7.0` | OK | Or prefer model-bakery>=1.23.0 (in dev group). |
| pytest-asyncio | `>=0.24` | `>=1.4.0` (ACTION) | FIX | Bump pending — major breaking jump (legacy mode + event_loop fixture removed). |
| ruff | `==0.9.0` | `>=0.15.20` | FIX | pyproject already 0.15.20. |

## Prioritized Compatibility Checklist (audit 2026-07-18)

Evidence the Validator confirmed. Cite architecture zones from 03/04.

### P0 — Mandatory / architecture-breaking

* **P0-1 django-mptt 0.18.0 vs Django 5.2 (zone D1).** 0.18.0 IS validated against Django 5.2
  (changelog: "Added support for Python 3.13 and Django 5.1 and 5.2"). The `<6.0` pin is
  defense-in-depth: the package is now **best-effort / unmaintained** and only `0.19rc1` exists
  (with Django 6.0 support). Keep `<6.0` until mptt is replaced or 0.19 stable ships.
* **P0-2 pyproject/settings drift (zones C5, D10).** RESOLVED at audit time for the manifest:
  `pyproject.toml` already declares `psycopg[binary]>=3.2.0` + all 8 required runtime deps + dev
  deps; `python-dotenv` is no longer a direct dep. OUTSTANDING (code, not doc): `settings.py` must
  default to the PostgreSQL engine with `OPTIONS={"prepare_threshold": None}` + `CONN_MAX_AGE=0`
  (see 03_structure.md C5).
* **P0-3 aiogram 3.30 in a separate process (zone C5).** NO event-loop conflict — the bot is a
  separate OS process with its own asyncio loop; the web is sync WSGI. aiogram requires
  `Python >=3.10,<3.15` (3.14 OK) and shares no deps with Django/psycopg3. REAL risk: the FSM
  "PostgreSQL storage" misconception — must persist `Ad.DRAFT` via the shared ORM, never Redis/Mongo.

### P1 — Important / version-bump sensitive

* **P1-1 psycopg3 3.3.x + PgBouncer (zone C5).** `OPTIONS={"prepare_threshold": None}` is still
  correct and recommended. psycopg3's newer PgBouncer prepared-statement path needs PgBouncer>=1.22
  + libpq 17 — keep `None` until those are guaranteed.
* **P1-2 django-filter 26.1 (US-A2/US-B3).** `Django>=5.2`, py3.14 OK. Add to `INSTALLED_APPS`.
* **P1-3 pytest-asyncio 0.24 -> 1.4.0 (bot tests).** Major: legacy mode + `event_loop` fixture
  removed; strict default; requires pytest>=8.4. Set `asyncio_mode="strict"` + `minversion="8.4"`
  when bot tests are written. ACTION: bump in pyproject.
* **P1-4 pillow 12.3.0 (zone R8).** py3.14 wheels; `Image.open`/`verify`/`format=="JPEG"` unchanged.

### P2 — Advisory / hygiene

* **P2-1 django-tailwind 4.5.0.** `django-tailwind` (timonweb) and `django-tailwind-cli`
  (django-commons) are BOTH maintained; both technically support daisyUI. Exclusion is a project
  choice. Keep `django-tailwind`; mind the `TAILWIND_CLI_SRC_CSS` default change if configured later.
* **P2-2 ruff 0.15.22.** 2026 style guide reformats on next `ruff format`; project selects only
  E,F,I,B,UP so new ASYNC* rules do not fire. The referenced `ruff.toml` in 03_structure.md does
  not exist — config lives in `[tool.ruff]` in pyproject.toml.
* **P2-3 Django 5.2.16.** Current LTS, correct pin. No action.
* **P2-4 deep-translator 1.11.4 (zones D5/C7).** Backend fragility unchanged; enforce timeout+fallback wrapper.
* **P2-5 django-htmx 1.28.0.** Compatible with Django 5.2.

## Residual Risks

| Risk | Level | Mitigation |
|------|-------|------------|
| deep-translator Google-scrape fragility | HIGH | Hard timeout ~500ms + mandatory fallback to original query. |
| aiogram FSM "PostgreSQL SQLStorage" misconception | HIGH | Use `Ad.DRAFT` in shared Django ORM; no DB-backed FSM storage. |
| django-mptt abandonment (R-mptt) | MEDIUM | Plan replacement (recursive CTE / django-tree-queries) BEFORE any Django 6.0 move; keep `<6.0`. |
| django-tailwind without daisyUI | MEDIUM | Plain Tailwind utilities suffice for MVP; add daisyUI later via npm mode. |
| django-storages maintenance-at-risk | LOW | Re-validate at S3/R2 swap time (post-MVP). |
| pytest-asyncio strict-mode surprises | LOW | Set `asyncio_mode="strict"`, `minversion="8.4"` when writing bot tests. |
