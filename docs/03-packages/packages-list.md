---
id: packages-list
domain: packages
tags:
  - stack
  - dependencies
  - versions
related:
  - technical-specification
  - architecture-structure
  - db-schema
  - dependency-collisions
---

## Purpose

Authoritative, English-only list of all Python packages and non-PyPI runtime components for the
Mko Bazuna MVP (phase 1). This is the **single source of truth** for the dependency set.
Versions validated against PyPI stable (audit 2026-07-18), Django 5.2 LTS, Python 3.14.

**Versioning rule:** use `>=` (minimum) for every package. Use `=` / upper bound ONLY where a
critical incompatibility exists. Django is pinned to the LTS 5.2 line (`>=5.2.16,<6.0`) because
django-mptt is not yet validated against Django 6.0.

## Stack Summary

- Django 5.2 LTS + PostgreSQL 18
- Admin: Django Admin
- Filtration: django-filter, django-mptt
- Search: PostgreSQL native FTS (`search_vector` TSVECTOR + GIN, russian config)
- UI: Django Templates + HTMX + Alpine.js MPA (phase 1)
- Telegram bot (phase 1): aiogram 3.x (Bot API). Telethon NOT used in phase 1.
- Background jobs: Django management commands + systemd timer / cron (Celery deferred)
- **Async bot + sync Django ORM:** bot runs `django.setup()` and shares the ORM. Blocking ORM calls and Telegram photo downloads wrapped in `sync_to_async`. Each process holds its OWN psycopg3 pool (`CONN_MAX_AGE=0`); shared external PgBouncer (transaction mode) recommended.
- Query translation: deep-translator (Bosnian → Russian at search time; hard timeout ~500ms + fallback to original query).

## Package List (pyproject.toml)

```
# Core / Web
django>=5.2.16,<6.0              # LTS until Apr 2028; <6.0 protects django-mptt.
psycopg[binary]>=3.2.0            # psycopg 3 (Django 5.2 native driver). For PgBouncer tx mode set OPTIONS={"prepare_threshold": None}.
django-environ>=0.11.0            # Typed .env casting. python-dotenv is TRANSITIVE (do not declare).
django-mptt>=0.18.0               # Hierarchical categories. First Django 5.2-compatible release. Unmaintained — keep <6.0.
django-filter>=26.1               # List filters. Requires Django>=5.2.
django-tailwind>=4.4.0            # Tailwind standalone CLI (NO Node.js). daisyUI EXCLUDED (project choice).
django-htmx>=1.19.0               # HTMX for the MPA.
pillow>=10.4.0                    # Image handling + strict JPEG validation (zone R8). REQUIRED phase 1.
aiogram>=3.15.0                   # Bot API bot (login/contact/publish). NO built-in PG FSM storage — draft Ad stored via ORM.
deep-translator>=1.11.0           # Bosnian→Russian query translation. Fragile backend → hard timeout + fallback wrapper.
# Search: native PostgreSQL FTS only (no haystack/Whoosh).
# API (DRF): DEFERRED to post-MVP.
# Tasks (celery/redis): DEFERRED to post-MVP (management commands + cron instead).
# Storage (django-storages/boto3): DEFERRED (YAGNI; swap later via STORAGES contract).
# Testing / Dev
pytest>=9.1.1
pytest-django>=4.9.0              # REQUIRED.
pytest-asyncio>=1.4.0             # REQUIRED for aiogram async tests. Set asyncio_mode="strict".
model-bakery>=1.23.0              # Preferred over pytest-factoryboy.
basedpyright>=1.39.9              # Type checking.
ruff>=0.15.20                     # Lint + format.
# Web runtime (add to deps)
gunicorn>=26.0                    # Sync WSGI; Django 5.2 + py3.14 OK.
whitenoise>=6.12.0                # /static/ only (NOT media). Add if used in prod.
```

## Infrastructure & Runtime (Docker)

Pinned in `docker/Dockerfile`, `docker-compose.yml`. All compatible with Django 5.2 + Python 3.14 + psycopg3.

- **PostgreSQL 18:** FTS stack (TSVECTOR + GIN + plpgsql triggers + `to_tsvector('russian')`) fully compatible.
- **uv:** pin `uv>=0.11.28` in Dockerfile.
- **gunicorn:** pin `gunicorn>=26.0`.
- **whitenoise:** add if used for `/static/` (media still needs nginx).
- **PgBouncer:** pin `pgbouncer>=1.25.2`. Keep `prepare_threshold=None`.
- **nginx:** `nginx:alpine` tracks 1.30.x.

## Key Compatibility Decisions

| Item | Decision | Note |
|------|----------|------|
| django | `>=5.2.16,<6.0` | LTS; `<6.0` protects unmaintained django-mptt. |
| psycopg3 | `>=3.2.0` | Recommended driver; `prepare_threshold=None` for PgBouncer. |
| django-mptt | `>=0.18.0` | First Django 5.2-compatible. Plan replacement before any Django 6.0 move. |
| django-filter | `>=26.1` | List filters. Requires Django>=5.2. |
| aiogram FSM | use `Ad.DRAFT` in ORM | No built-in PG FSM storage; never Redis/Mongo. |
| django-tailwind | `>=4.4.0` | daisyUI excluded (standalone has no plugin support). |
| deep-translator | `>=1.11.0` | Google-scrape fragility → enforce timeout + fallback wrapper. |
| pytest-asyncio | `>=1.4.0` | Major jump from 0.24; set `asyncio_mode="strict"`, `minversion="8.4"`. |

## Residual Risks

| Risk | Level | Mitigation |
|------|-------|------------|
| deep-translator Google-scrape fragility | HIGH | Hard timeout ~500ms + mandatory fallback to original query. |
| aiogram FSM "PostgreSQL storage" misconception | HIGH | Use `Ad.DRAFT` in shared Django ORM; no DB-backed FSM. |
| django-mptt abandonment | MEDIUM | Plan replacement (recursive CTE / django-tree-queries) before Django 6.0; keep `<6.0`. |
| django-tailwind without daisyUI | MEDIUM | Plain Tailwind suffices for MVP. |
| django-storages maintenance-at-risk | LOW | Re-validate at S3/R2 swap. |
| pytest-asyncio strict-mode surprises | LOW | `asyncio_mode="strict"`, `minversion="8.4"` when writing bot tests. |
