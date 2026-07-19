---
name: Agent Guidelines
description: Mandatory rules and context for the project
alwaysApply: true
---

# Agent Guidelines

## Project
Django 5.2 LTS + Telegram bot (aiogram 3.x) classifieds board (Avito-like) for the Bosnia & Herzegovina market; content in Russian, UI Russian + Bosnian. Sellers post via Telegram bot; buyers browse/search on the Django site (HTMX MPA). Two long-lived processes (web gunicorn WSGI + bot) share one Django project + PostgreSQL.

## Commands

| Task | Command |
|------|---------|
| Test | `uv run pytest <path>` |
| Lint | `uv run ruff check <path>` |
| Type check | `uv run basedpyright <path>` |
| Add dependency | `uv add <package>` |

## Architecture

- Fixed values: `StrEnum` only — never plain strings/dicts/lists for constants.
- Small modules and functions.
- Two processes, one DB; migrations run once before web+bot.
- Search: native PostgreSQL FTS.

## Rules

- Type hints on all public functions. `logger = logging.getLogger(__name__)` — never `print()`.
- Custom exceptions from `core/errors.py`. Never silently swallow errors. (Note: core/errors.py is planned per spec; keep the rule.)
- Clean up temp files with `try/finally` — never leave orphaned cache files.
- English only in code, comments, logs.
- Production code is king — if tests conflict with architecture/business logic, fix or remove tests; never distort production code for tests.
- Write audit reports incrementally — append blocks of ≤100 lines per tool call.
- 4-space indentation, never tabs; read full function/class before rewriting; after edits run `uv run ruff check <path>` and `uv run basedpyright <path>`.

## References

- [Specification summary](docs/SPEC.md)
- [Readme](README.md)
- [Doc maintenance rules](docs/00-overview/doc-maintenance-rules.md)
- [Technical specification (wiki)](docs/wiki/technical-specification.md)
- [DB structure (wiki)](docs/wiki/db-structure.md)
- [Architecture (wiki)](docs/wiki/architecture-structure.md)
