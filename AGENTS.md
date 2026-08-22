---
name: Agent Guidelines
description: Mandatory rules and context for the project
alwaysApply: true
---

# Mko Bazuna — Agent Guidelines

A Telegram-driven classifieds board (Avito-like) with a Django website. Sellers post ads through a **Telegram bot**; published ads appear on the site. Buyers browse, search, and filter without login.

## Quick Reference

- **Package Manager:** `uv` (Python)
- **Test (fast gate):** `make test` — skips nightly `seed` suite (~300s); auto-starts test DB. Start DB only: `make test-db`.
- **Test (full suite):** `make test-all` (~35 min, includes `seed`).
- **Test (fresh schema):** `make test-recreate` (`--no-reuse-db --create-db`).
- **Lint:** `uv run ruff check <path>`
- **Typecheck:** `uv run basedpyright <path>`
- **Add dep:** `uv add <package>`

## Core Context

- **Stack:** Python 3.14 · Django 5.2 LTS (`>=5.2.16,<6.0`) · PostgreSQL 18 · aiogram 3.x · native PostgreSQL FTS.
- **Two processes, one DB:** web (gunicorn sync WSGI, HTMX MPA) + bot (aiogram, `django.setup()` + shared ORM). Migrations run exactly once before both start.
- **Fixed values:** use `StrEnum` — never plain strings/dicts for constants.
- **Bot FSM:** no built-in PG storage — the ad dialog is persisted as an `Ad` row (`DRAFT`) via the ORM.

## Test Environment (Docker)

Tests require a PostgreSQL test database in Docker (container `mko-bazuna-test-db-*`).
Running `uv run pytest` locally will fail. Always:

1. Check the test DB is running: `docker ps --filter "name=mko-bazuna-test-db-"`
2. If not running, start it: `docker compose --project-name mko-bazuna-test -f docker-compose.yml -f docker-compose.test.yml up -d db`
3. Run tests via the `test` Compose service (see `.ai/context/commands.md` for full commands).

## Detailed Instructions

For specific guidelines, see:
- [Architecture](docs/99-agent/architecture.md)
- [Rules](docs/99-agent/rules.md)
- [References](docs/99-agent/references.md)
- [Spec summary](docs/01-spec/spec-index.md) · [User stories](docs/04-user-stories/index.md) · [Doc rules](docs/00-overview/doc-maintenance-rules.md)