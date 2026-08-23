---
id: architecture
domain: agent
tags:
  - architecture
related:
  - rules
  - references
  - migration-workflow
---

## Purpose

This file contains architecture guidelines and patterns for the Mko Bazuna project.

## Main Concepts

- **Fixed values:** `StrEnum` only — never plain strings/dicts/lists for constants.
- **Small modules and functions:** Modules, services, components, and functions must be small and focused on one thing.
- **Two processes, one DB:** Web gunicorn WSGI + Telegram bot share one Django project + PostgreSQL. Migrations run exactly once before both processes start.
- **Search:** Native PostgreSQL full-text search.
- **Multi-currency pricing:** Sellers enter an original amount + `CurrencyCode` (EUR/RSD/BAM);
  `price_normalized_eur` is derived by `PriceNormalizer` (cached current `ExchangeRate` rate)
  and re-derivable via the advisory-locked `recompute_normalized_prices` management command. Both
  processes read rates from the shared DB. See
  [`db-schema`](../../02-database/db-schema.md) ([`db-enums`](../../02-database/db-enums.md),
  [`db-indexes`](../../02-database/db-indexes.md)).
- **Migrations:** Dev-mode workflow with threshold-based consolidation (max 8 files/app → reset to one `0001_initial.py`). The `migrate` service runs once before web+bot via advisory lock. See [migration-workflow](../../ops/migration-workflow.md).

## Commands

| Task | Command |
|------|---------|
| Test (Docker) | `make test` (fast gate) · `make test-all` (full) · `make test-recreate` (fresh schema) |
| Lint | `uv run ruff check <path>` |
| Type check | `uv run basedpyright <path>` |
| Add dependency | `uv add <package>` |

## Cache Backend

- **Shared cache (production):** Redis via `django-redis`. Required because the web process
  runs 3 gunicorn workers and the bot runs as a separate process; `LocMemCache` is per-process
  only and cannot share rate-limit counters or cache invalidations across processes.
- **Redis-specific APIs:** `cache.delete_pattern()` is called (with `hasattr` guards) at
  `apps/categories/services/lookup_resolution.py:112` and
  `apps/lookups/services/cache_service.py:77` — these are no-ops under LocMemCache and
  become functional under Redis.
- **Dev/test:** `config/settings/dev.py` and `config/settings/test.py` override `CACHES` to
  `LocMemCache` — no Redis needed for local development or testing.
- **Docker:** `redis:7-alpine` service in `docker-compose.yml`; wired into `web`, `bot`,
  and `scheduler` via `REDIS_URL` env var and `depends_on` healthchecks.