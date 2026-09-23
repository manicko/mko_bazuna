---
id: architecture
domain: agent
tags:
  - architecture
related:
  - rules
  - references
  - migration-workflow
  - db-enums
---

## Purpose

This file contains architecture guidelines and patterns for the Mko Bazuna project.

## Main Concepts

- **Fixed values:** `StrEnum` only — never plain strings/dicts/lists for constants.
- **Small modules and functions:** Modules, services, components, and functions must be small and focused on one thing.
- **Two processes, one DB (+ scheduler service):** Web gunicorn WSGI + Telegram bot share
  one Django project + PostgreSQL. Migrations run exactly once before all processes start.
  Bot lifecycle hooks (`telegram_bot/lifecycle.py`) write two liveness markers: a file-based
  marker (`/tmp/mko_bazuna_bot_alive`) consumed by the file-based `healthcheck-bot.sh`
  (process + marker freshness), and a Redis-based `bot:liveness` key (epoch timestamp)
  consumed by the web `/health/ready/` readiness probe via `BOT_HEALTH_CHECK_ENABLED` /
  `BOT_HEALTH_STALE_SECONDS` (OPS-003). The scheduler service (gated by
  `profiles: ["scheduler"]`) runs the hourly sweeps + daily jobs via the extracted module
  `apps.core.utils.scheduler` (`python -m apps.core.utils.scheduler` from
  `docker/entrypoint-scheduler.sh`); it writes a file-based liveness marker
  (`SCHEDULER_LIVENESS_FILE`, default `/tmp/mko_bazuna_scheduler_alive`) after each hourly
  cycle, consumed by `healthcheck-scheduler.sh` with staleness governed by
  `SCHEDULER_HEALTH_STALE_SECONDS` (default `7200`).
- **Search:** Native PostgreSQL full-text search.
- **Multi-currency pricing:** Sellers enter an original amount + `CurrencyCode` (EUR/RSD/BAM);
  `price_normalized_eur` is derived by `PriceNormalizer` (cached current `ExchangeRate` rate)
  and re-derivable via the advisory-locked `recompute_normalized_prices` management command. Both
  processes read rates from the shared DB. The web edit path
  (`ads.views.edit._apply_price_change`) and the submission path
  (`ads.services.submission.submit_ad`) delegate to the shared
  `normalize_price_to_eur(ad, amount, currency)` free function in
  `apps/currencies/services/price_normalizer.py` — the single seam for the broad
  `except Exception` + `None`-fallback pattern (10-QLT-001). The management command
  `recompute_normalized_prices` is intentionally *not* routed through this utility: it
  uses a distinct `ExchangeRateNotFoundError` and a stored normalizer instance (out of
  scope). See [`db-schema`](../02-database/db-schema.md) ([`db-enums`](../02-database/db-enums.md),
  [`db-indexes`](../02-database/db-indexes.md)).
- **Migrations:** Dev-mode workflow with threshold-based consolidation (max 8 files/app → reset to one `0001_initial.py`). The `migrate` service runs once before web+bot via `apps.core.utils.migrate_locked.main` (session-scoped advisory lock ID 100), which executes `migrate --run-syncdb`, `setup_search_triggers`, and `load_exchange_rates` as an atomic sequence, with an optional `backfill_translations` step included when `RUN_TRANSLATION_BACKFILL=true`. See [migration-workflow](../ops/migration-workflow.md).

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
- **Site name (cross-process branding):** The admin-edited `SiteConfig.name` singleton
  (`site_config` table) is cached (`SITE_CONFIG_CACHE_KEY`, 1 h TTL) and read by **both**
  long-lived processes — the web via the `site_config` context processor (`site_name`) and the
  Telegram bot via `get_site_name_async()` (greetings on `/start` and `/post`). The shared
  cache is what keeps the brand name identical between the web header and the bot greeting
  without a redeploy. See [site_config](../02-database/db-schema.md#site_config).
- **Redis-specific APIs:** `cache.delete_pattern()` is called (with `hasattr` guards) at
  `apps/categories/services/lookup_resolution.py:112` and
  `apps/lookups/services/cache_service.py:77` — these are no-ops under LocMemCache and
  become functional under Redis.
- **Dev/test:** `config/settings/dev.py` and `config/settings/test.py` override `CACHES` to
  `LocMemCache` — no Redis needed for local development or testing.
- **Docker:** `redis:7-alpine` service in `docker-compose.yml`; wired into `web`, `bot`,
   and `scheduler` via `REDIS_URL` env var and `depends_on` healthchecks. The `scheduler`
   service also `depends_on: load_catalog (completed successfully)` so sweep commands never
   start before the category catalog is loaded.

## Environment Variable Resolution

This project resolves environment variables through two distinct but related mechanisms:
**Docker Compose** (for local dev, test, and production) and **GitHub Actions CI** (which runs
pytest directly with `uv`, no Docker). The two are **not equivalent** — they reach the same
runtime configuration via different paths, and that divergence is intentional.

### Docker Compose Two-Phase Model

Docker Compose processes environment variables in two phases that are frequently confused:

1. **Parse-time interpolation** (`--env-file` CLI flag): The `--env-file .env.test` /
   `.env.dev` / `.env.prod` flag supplies values for `${VAR}` substitution **in the Compose YAML
   itself**. For example, `DATABASE_URL: postgres://${POSTGRES_USER}:${POSTGRES_PASSWORD}@db:5432/${POSTGRES_DB}`
   in [`docker-compose.yml`](../../docker-compose.yml) is resolved to a literal string at parse
   time. `--env-file` values are **NOT** injected into the container's runtime environment — they
   only feed interpolation of `${VAR}` placeholders in `environment:` blocks. The `Makefile`
   wires this per tier (e.g. line 11: `COMPOSE_TEST := --env-file .env.test -f
   docker-compose.yml -f docker-compose.test.yml`).
2. **Container-env phase** (`env_file:` directive): The per-service
   [`env_file:`](https://docs.docker.com/reference/compare/compose-file/env_file/) directive
   reads a file and injects each `KEY=value` line as a container environment variable
   (`os.environ`). In `docker-compose.test.yml` every service (`migrate`, `test`, `bot`, `web`,
   `load_cities`, `load_catalog`, `seed`) declares `env_file: .env.test`.

> **Hard-error guard (`${VAR:?}`):** The base `docker-compose.yml` uses `${VAR:?}`
> interpolation for required variables (`POSTGRES_DB`, `POSTGRES_USER`,
> `POSTGRES_PASSWORD`, `DJANGO_SECRET_KEY`). In Docker Compose, `${VAR:?}` is a
> **hard error** (exit code 1) when the variable is unset — it is not a warning
> (ENV-008). Because of this, `--env-file` must **always** be passed when running
> compose commands against `docker-compose.yml`; without it the variable cannot be
> resolved and Compose fails before any container starts.

The same `.env.*` files are also **bind-mounted** into the container at `/app/src/.env` (see
`volumes:` entries like `./.env.test:/app/src/.env:ro`) so Django's `django-environ` can read
them as a file — but only for services whose settings actually call `read_env()` (see below).

The `.env.*` files are gitignored (`.gitignore` lines 145–148); `.env.example`,
`.env.dev.example`, `.env.test.example`, and `.env.prod.example` are the tracked templates to
copy from.

### Precedence Chain (highest to lowest)

When multiple mechanisms provide the same variable, the following precedence applies:

1. **`environment:` in compose YAML** (literal value or interpolated `${VAR}` resolved from
   `--env-file`) — wins over `env_file:` on a per-key basis. This is why each test service sets
   `DJANGO_SETTINGS_MODULE=config.settings.test` in `environment:` rather than relying on
   `.env.test` alone, and why the `test` service sets `UV_NO_INSTALL_PROJECT=0` and
   `SKIP_ENV_CHECK=1`.
2. **`env_file:` directive** (bulk injection of file contents into the container's `os.environ`).
   Merge semantics apply when overrides are layered: `docker-compose.test.yml`'s
   `env_file: .env.test` *concatenates* with the base `docker-compose.yml`'s `env_file: .env.dev`
   (per the comment block at the top of `docker-compose.test.yml`), with the later file winning
   on key conflicts.
3. **Docker Compose `--env-file` flag** — supplies `${VAR}` interpolation only; it does **not**
   inject into the container directly. Its influence surfaces only where `environment:` values
   reference `${VAR}`, so it is lower priority than the explicit `env_file:` and `environment:`
   keys.
4. **Image `ENV` (Dockerfile)** — the lowest priority. Placeholder build-time values such as
   `DJANGO_SECRET_KEY=build-placeholder-do-not-use-in-production`,
   `DATABASE_URL=postgres://postgres:build-placeholder@localhost:5432/postgres`, and
   `DJANGO_SETTINGS_MODULE=config.settings.prod` (`docker/Dockerfile` lines 68–75) are baked
   into the image but are overridden by any compose `environment:` / `env_file:` value at
   runtime. `docker build` itself sets `DJANGO_BUILD=1`, which the settings module checks to
   skip `.env` validation (see below).

> Note: running `docker compose config` shows a flat merged `environment:` list and does **not**
> reveal which `.env` file a given key originated from. Inspect the `volumes:` section of the
> rendered config to confirm which `.env` is bind-mounted to `/app/src/.env`.

### Django Loading (`base.py`)

`config/settings/base.py` controls when `django-environ`'s `read_env()` is invoked:

- The `.env` file path resolves to `BASE_DIR / ".env"` → `/app/src/.env` (the bind-mount target).
- `read_env()` is called **only** when `.env` exists **and** `DJANGO_SETTINGS_MODULE` does **not**
  contain `"test"` (see `base.py` lines 30–53).
- **In test mode** (`DJANGO_SETTINGS_MODULE` contains `"test"`, e.g. `config.settings.test`):
  `read_env()` is **skipped** — all variables come from `os.environ`, which is populated by
  Docker Compose's `env_file:` / `environment:` directives. This prevents the bind-mounted
  `.env` from masking test cases that intentionally unset environment variables (e.g.
  `test_settings_secrets.py`).
- **In non-test Docker environments** (`dev`, `prod`): `read_env()` reads the bind-mounted
  `/app/src/.env` (i.e. `.env.dev` or `.env.prod`).
- **In CI**: no `.env` file is bind-mounted and `read_env()` is never reached; every variable is
  set directly as a step-level `env:` in the workflow. The `DJANGO_BUILD=1` Dockerfile `ENV` is
  never set in CI, so it has no effect there.

**Database resolution** (`base.py` lines 181–202): `base.py` checks `os.getenv("DATABASE_URL")`
first. If set, it parses the URL via `env.db()` and the `POSTGRES_*` fallback is skipped
entirely (lines 187–202 are never reached). If `DATABASE_URL` is unset, `base.py` constructs
the connection from discrete `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`,
`POSTGRES_HOST`, and `POSTGRES_PORT` variables. CI always sets `DATABASE_URL` directly
(`localhost:5432`), so CI exercises only the `env.db()` branch. Docker Compose test services
(`web`, `bot`, `migrate`) also set `DATABASE_URL` via YAML interpolation (constructed from
`POSTGRES_*` → `db:5432`), so they too take the `env.db()` path. Only the `test` service in
`docker-compose.test.yml` omits `DATABASE_URL` from its `environment:` block, causing `base.py`
to fall back to the discrete `POSTGRES_*` vars (lines 187–202) — a code path **not** exercised
by CI.

### CI vs Docker Compose Divergence

| Variable | CI (GitHub Actions) | Docker Compose (test) | base.py default |
|---|---|---|---|
| DJANGO_SETTINGS_MODULE | `config.settings.test` (step `env:`, 6 steps) | `config.settings.test` (`environment:` on each service) | — |
| DATABASE_URL | `postgres://postgres:postgres@localhost:5432/mko_bazuna` (step `env:`) | `postgres://postgres:postgres@db:5432/mko_bazuna` (constructed from `POSTGRES_*` via YAML interpolation in `docker-compose.yml`) | falls back to discrete `POSTGRES_*` vars (lines 187–202) |
| DJANGO_SECRET_KEY | `test-secret-key-for-testing-only` (step `env:`) | `test-secret-key-for-testing-only` (`env_file: .env.test`) | — |
| All other variables | rely on `base.py` defaults (e.g. `SITE_URL`, `REDIS_URL`, `BOT_TOKEN`) | explicitly set in `.env.test` (`env_file:`) — 16+ variables | — |

**CI** (`.github/workflows/ci.yml`, `.github/workflows/ci-nightly.yml`) runs pytest directly with
`uv` against a PostgreSQL GitHub Actions **service container**:

- **Database**: CI sets a single `DATABASE_URL: postgres://postgres:postgres@localhost:5432/mko_bazuna`
  as step-level `env:`. It does **not** set `POSTGRES_USER`, `POSTGRES_DB`, or
  `POSTGRES_PASSWORD` for the application process — the `POSTGRES_*` vars in the workflow
  (`ci.yml` lines 42–45) initialize the `postgres:18-alpine` service container only. CI connects
  via `localhost:5432` (the service port mapping), not the Docker-internal hostname `db`.
- **Secrets**: CI sets `DJANGO_SECRET_KEY=test-secret-key-for-testing-only` and
  `DJANGO_SETTINGS_MODULE=config.settings.test` as step-level `env:` (lines 83–85, 94–96,
  108–110, 124–126, 233–235, 244–246, 258–260). No `.env` file is involved.
- **Defaults**: CI relies entirely on `base.py` defaults for `SITE_URL` (`http://localhost:8000`),
  `GOOGLE_TRANSLATE_API_KEY` (empty), `REDIS_URL` (`redis://localhost:6379/0`),
  `PLAUSIBLE_HOST` (empty), `BOT_TOKEN` (empty), `IMMEDIATE_ALERTS_ENABLED` (`False`), and
  other settings — only `DJANGO_SETTINGS_MODULE`, `DATABASE_URL`, and `DJANGO_SECRET_KEY` are
  supplied explicitly.

**Docker Compose (test)** (`docker-compose.yml` + `docker-compose.test.yml`) provides the same
values via `.env.test` through the `env_file:` / `environment:` directives and `--env-file .env.test`
interpolation:

- **Database**: `POSTGRES_USER`, `POSTGRES_DB`, `POSTGRES_PASSWORD`, and `POSTGRES_HOST` are set
  individually in `.env.test` (via `env_file`), and `DATABASE_URL` is constructed from them via
  `environment:` interpolation in `docker-compose.yml` (e.g.
  `postgres://${POSTGRES_USER}:${POSTGRES_PASSWORD}@db:5432/${POSTGRES_DB}`) on the app services
  (`web`, `bot`, `migrate`). The `db` service in `docker-compose.test.yml` overrides
  `DATABASE_URL` to `postgres://postgres:postgres@db:5432/mko_bazuna` (line 39). The app
  processes connect via the Docker-internal hostname `db`, not `localhost`. The `test` service
  itself does not inherit a `DATABASE_URL` from the base compose (it is defined only in the
  test override) and instead relies on the discrete `POSTGRES_*` vars, which `base.py` falls
  back to when `DATABASE_URL` is unset (base.py lines 181–202).
- **Secrets**: `DJANGO_SECRET_KEY` comes from `.env.test` (`env_file`), and
  `DJANGO_SETTINGS_MODULE=config.settings.test` is set via `environment:` on each service.
- **Explicit vars**: `.env.test` now provides all six previously-defaulted variables —
  `SITE_URL`, `GOOGLE_TRANSLATE_API_KEY`, `REDIS_URL`, `PLAUSIBLE_HOST`, `BOT_TOKEN`, and
  `IMMEDIATE_ALERTS_ENABLED` — after the ENV-005 fix, so the test container's environment is
  self-contained and mirrors what CI obtains from `base.py` defaults. `REDIS_URL` is empty in
  `.env.test`, which is fine because `test.py` overrides `CACHES` to `LocMemCache` (no Redis
  needed — see [Cache Backend](#cache-backend)).

The net effect is that both CI and Docker Compose reach the same runtime configuration for the
**test** settings module, but they arrive there via different paths: CI leans on `base.py`
defaults and step-level `env:` with no `.env` file, while Docker Compose leans on `.env.test`
`env_file` injection plus YAML interpolation and an explicit bind-mount to `/app/src/.env`.

## Price Normalization Seam (10-QLT-001)

A shared free function `normalize_price_to_eur(ad, amount, currency)` lives in
[`apps/currencies/services/price_normalizer.py`](../../src/backend/apps/currencies/services/price_normalizer.py),
co-located with the `PriceNormalizer` class (single responsibility: currency conversion).
It encapsulates the broad `except Exception` + `logger.exception` + `None`-fallback pattern that
both the web edit path and the submission path previously duplicated:

- **Web edit path** — `ads.views.edit._apply_price_change` delegates to this utility when a
  PUBLISHED ad's price is edited. Edit branches are **not** routed through `submit_ad`
  (that would trigger thumbnail generation, staging-file moves, `DraftAdImage` creation,
  and the DRAFT→ON_MODERATION transition — all wrong for status-preserving edits).
- **Submission path** — `ads.services.submission.submit_ad` delegates to the same utility at
  the `# Price normalization (BR-03)` step.

The management command `recompute_normalized_prices` is intentionally **out of scope**: it uses a
distinct `ExchangeRateNotFoundError` exception and a stored normalizer instance, so merging it
into the shared utility would change its error semantics. See
[`db-enums`](../02-database/db-enums.md#currencycode) for the `CurrencyCode` StrEnum and
[`db-schema`](../02-database/db-schema.md) for the `exchange_rates` table.

## Consent Version Tracking (10-QLT-002)

`ConsentVersion(StrEnum)` (defined in `apps/core/enums.py`, see
[`db-enums`](../02-database/db-enums.md#consentversion)) is the single source of truth for the
consent-banner version. It replaces five raw `"1.0"` string literals across the consent
subsystem. `ConsentVersion.V1_0.value == "1.0"` matches all existing database values — the change
is backward-compatible and required no data migration. The historical migration
`users/migrations/0001_initial.py` was left untouched (records past state).

Three layers consume it:

1. **Model default** — `ConsentRecord.consent_version` (`users/models.py`) defaults to
   `ConsentVersion.V1_0.value`.
2. **Context processor** — `apps.users.context_processors.consent_version` exposes the
   `ConsentVersion.V1_0` enum member to templates (mirrors the `price_step` context processor
   pattern). `consent_banner.html` renders
   `value="{{ consent_version.value }}"` in both the Accept and Decline hidden inputs, removing
   the raw `"1.0"` literals at the browser boundary. Registered in
   `config/settings/base.py` `TEMPLATES.context_processors`.
3. **DTO validation** — `ConsentSubmission.consent_version` (`users/schemas.py`) carries a
   lenient Pydantic `@field_validator` (`mode="before"`) that coerces unrecognized/empty values
to `ConsentVersion.V1_0.value` with a warning log, never rejecting a legitimate
  `consent_version=1.0` submission.

The `record_consent_action` service (`users/services/consent_record.py`) defaults its
`consent_version` parameter to `ConsentVersion.V1_0.value`, which also covers the implicit
consumer (`consent_withdraw` calls it without the argument).

## Bot Handler Module Decomposition (10-QLT-003)

The monolithic 930-line `telegram_bot/handlers/ad_create.py` was split into a package:
`telegram_bot/handlers/ad_create/` with a single shared `router` (`Router()` instance) and
`AdCreateForm(StatesGroup)` defined in `__init__.py`. Sub-modules import the shared router and
register handlers against it via `@router.message(...)` / `@router.callback_query(...)` decorators:

| Sub-module | Contents |
|------------|----------|
| `__init__.py` | Package docstring, shared `router`, `AdCreateForm` FSM states, `MAX_PHOTO_BYTES`, re-exports |
| `preview.py` | `show_preview`, `_format_preview_price` |
| `category.py` | 7 FSM category/purpose/condition/features selection handlers |
| `city.py` | `process_city` |
| `text.py` | `process_title`, `process_description` |
| `price.py` | 3 price entry/validation handlers |
| `photos.py` | `process_photos` |
| `entry.py` | `cmd_post`, `cmd_cancel` (command entry points) |
| `submit.py` | `process_preview`, calls `submit_ad` |

Test patch paths in `test_ad_create.py` and `test_site_name_greeting.py` were updated to reflect
the new package import paths. The `submit_ad` interface (signature + return tuple) is unchanged,
so the 10-QLT-001 refactoring does not block the split.
