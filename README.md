# Mko Bazuna

> Documents the target specification/architecture (source of truth: `docs/wiki/`). Implementation is in progress.

Telegram-driven classifieds board (Avito-like) with a Django website. Sellers post ads through a
Telegram bot; published ads appear on the site. Buyers browse, search, and filter without login.

**Launch market:** Bosnia & Herzegovina
**Content language:** Russian (base)
**UI:** Russian + Bosnian (latin)

## Stack
Python 3.14 · Django 5.2 LTS · PostgreSQL 18 · aiogram 3.x (Telegram bot) · PostgreSQL native FTS ·
django-mptt (categories) · django-tailwind + django-htmx (MPA) · Docker (db + web + bot + nginx)

## Architecture
Two long-lived processes share one Django project + one DB:
- **web:** sync WSGI (gunicorn), server-rendered HTMX MPA
- **bot:** aiogram, runs `django.setup()`, shares the ORM. The step-by-step ad dialog is persisted as an `Ad` row (`DRAFT`) via the shared ORM.

**Migrations run exactly once** before web+bot start. **Search:** native PostgreSQL full-text search (`search_vector` TSVECTOR + GIN, russian config).

## Quick start
```bash
cp .env.example .env        # set BOT_TOKEN, DB, SECRET_KEY
docker compose up --build   # db + web + bot + nginx
```

Web is served behind nginx (ports 80/443); the web container is not exposed directly.

## Documentation
| Doc | Purpose |
|-----|---------|
| `docs/SPEC.md` | Concise technical summary for agents/developers |
| `docs/wiki/technical-specification.md` | Product & domain spec (decisions A–L) |
| `docs/wiki/db-structure.md` | Database schema, FTS triggers, indexes |
| `docs/wiki/architecture-structure.md` | Source layout & Docker deployment |
| `docs/wiki/packages.md` | Dependency set & versions |
| `docs/wiki/audit-resolutions.md` | Owner decisions (O1–O5) & audit zone summaries |

## Commands
| Task | Command |
|------|---------|
| Run tests | `uv run pytest <path>` |
| Lint | `uv run ruff check <path>` |
| Type check | `uv run basedpyright <path>` |
| Add dependency | `uv add <package>` |

## Notes
**Phase 1 scope:** ads only via our Telegram bot.

**Deferred (post-MVP):** DRF API, Celery/Redis, S3/R2 storage, Telethon scraping, EAV attributes, tags, multi-currency.