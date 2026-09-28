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
  (process + marker freshness) — the primary bot alert — and a Redis-based `bot:liveness`
  key (epoch timestamp) consumed by the web `/health/ready/` readiness probe as a
  soft/alert dimension via `BOT_HEALTH_CHECK_ENABLED` / `BOT_HEALTH_STALE_SECONDS`
  (OPS-003). `BOT_HEALTH_CHECK_ENABLED` defaults off, so the Redis key does not gate web
  readiness by default (the probe reports bot as `"disabled"`). The scheduler service (gated by
  `profiles: ["scheduler"]`) runs the hourly sweeps + daily jobs via the extracted module
  `apps.core.utils.scheduler` (`python -m apps.core.utils.scheduler` from
  `docker/entrypoint-scheduler.sh`); it writes a file-based liveness marker
  (`SCHEDULER_LIVENESS_FILE`, default `/tmp/mko_bazuna_scheduler_alive`) after each
  clean cycle, consumed by `healthcheck-scheduler.sh` with staleness governed by
   `SCHEDULER_HEALTH_STALE_SECONDS` (env var; default `0`/disabled, `7200` in prod). Each command is dispatched via
  `subprocess.run(check=False, timeout=settings.SCHEDULER_COMMAND_TIMEOUT)`; a command that
  exceeds the timeout (`TimeoutExpired`) is logged and skipped so the cycle continues
   (ENT-001). On `SIGTERM`/`SIGINT` the scheduler sets a stop flag: the inter-cycle
   wait is interruptible (backed by the stop event), a stop during a cycle short-circuits the
   commands not yet started, and the in-flight command is never interrupted. The loop then
   breaks at its next top-of-loop check and closes Django DB connections in
   a `finally` teardown (ENT-002). The daily set (`send_alerts`, `rollup_daily_metrics`) is
   gated on a **durable** marker in the `scheduler_daily_state` singleton ([`db-schema`](../02-database/db-schema.md#scheduler_daily_state)),
   read at start-up and written only on a clean daily cycle; a failed daily cycle is retried
   on the next hourly tick.
- **Search:** Native PostgreSQL full-text search.
- **Multi-currency pricing:** Sellers enter an original amount + `CurrencyCode` (EUR/RSD/BAM);
  `price_normalized_eur` is derived by `PriceNormalizer` (cached current `ExchangeRate` rate,
  5 min TTL) and re-derivable via the advisory-locked `recompute_normalized_prices` management
  command (lock 12). The command locks each batch row with `select_for_update()` to
  prevent concurrent writes racing on `price_normalized_eur` (zone DB-001). Both
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
   start before the category catalog is loaded. **Redis is a disposable cache, not durable
   storage.** The service runs `redis-server --save "" --appendonly no --dir /tmp` with
   `read_only: true`, `tmpfs: /tmp` and **no `redis_data` volume** — persistence is disabled
   by design, so the entire dataset is lost on every container recreation. Redis is therefore
   never a candidate for state that must survive a restart (the scheduler's daily-dispatch
   marker, the bot liveness key, FSM state). Anything durable belongs in PostgreSQL. (The
   bot liveness key is deliberately non-durable: a lost key degrades the readiness probe's
   soft dimension, which is the correct failure mode for a *freshness* signal, and
   `BOT_HEALTH_CHECK_ENABLED` defaults to `False`.)
- **Production fail-fast (CFG-001):** `config/settings/prod.py` raises
   `ImproperlyConfigured` at import time if `REDIS_URL` is empty, because an unset URL
   would silently fall back to `MemoryStorage` for the bot FSM (ephemeral state) and an
   empty cache location. The guard is skipped under `DJANGO_BUILD=1` (image build) and
   `DJANGO_ONESHOT=1` (dev one-shot services); the real URL is provided at runtime via
   `.env.prod`.

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
   skip `.env` validation (see [Deployment Checks](../ops/docker-deployment.md#deployment-checks)).

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
- **Env-var allowlist:** After `read_env()` loads keys from `.env`, `base.py` calls
  `_warn_unknown_env_vars()`, which logs a non-fatal warning for any loaded key not in the
  `ALLOWED_ENV_VARS` frozenset (e.g. a typo like `BOT_T0KEN`). The warning names the key and
  suggests adding it to the allowlist if intentional; it does not block startup.

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

## Input DTO Validation Convention (CFG-004)

`BaseInputModel` (`apps/core/schemas.py`) is the shared base for every client-input DTO. It sets
`model_config = ConfigDict(extra="forbid")`, so unknown or misspelled fields are rejected at the
HTTP boundary with a `400` error instead of being silently dropped. It backs `SubmitAdInput`,
`AdEditInput`, `ListingsQueryParams`, `SubmittedPhoto`, `ConsentSubmission`, the saved-search
payloads (`SavedSearchQueryPayload`, `SavedSearchPricePayload`), the message-editing payloads
(`TitlePayload`, `DescriptionPayload`, `PricePayload`, `PhotoCountPayload`), and
`BulkModerationRequest`.

Two DTOs intentionally override `extra`: `AutocompleteSuggestion` (`apps/search/schemas.py`,
`extra="allow"` — a response DTO that tolerates additional upstream keys) and `CSPReportPayload`
(`apps/core/views.py`, `extra="ignore"` — absorbs spec-varying browser keys).

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

## Ad-Data Service Package Split (10-QLT-006)

The monolithic 598-line `telegram_bot/services/ad_data.py` was split into a package:
`telegram_bot/services/ad_data/` with a façade `__init__.py` that re-exports all public names so
that all 32 importers across the codebase keep resolving names from
`telegram_bot.services.ad_data` unchanged. Sub-modules are organized by concern and import only
from `apps.*` or `telegram_bot.schemas.*` — never from a sibling `ad_data.*` submodule:

| Sub-module | Contents |
|------------|----------|
| `__init__.py` | Package docstring, re-exports of all 22 public names, `__all__` |
| `orm.py` | DB helpers (``sync_to_async``): `create_draft_ad`, `delete_draft`, `_get_ad_status`, `get_all_cities`, `get_category`, `get_city`, `get_city_by_name`, `search_categories` |
| `media.py` | Bounded photo download + atomic staging: `download_photo`, `save_photo` |
| `translation.py` | Parallel multi-language translation orchestration: `translate_all_languages` |
| `feature_helpers.py` | Purpose/feature/condition resolution + lookups: `get_default_purpose`, `get_feature_names`, `get_lookup_item`, `get_lookup_item_by_slug`, `get_resolved_conditions`, `get_resolved_features`, `get_resolved_purposes` |
| `keyboards.py` | Inline keyboard builders: `build_currency_keyboard`, `build_purpose_keyboard`, `build_condition_keyboard`, `build_feature_keyboard` |

`build_currency_keyboard` (in `keyboards.py`) now loops over `CurrencyCode` enum members instead of
hardcoding `"EUR"`/`"RSD"`/`"BAM"` tokens — the enum's definition order (EUR, RSD, BAM) keeps EUR
first (10-QLT-003). `delete_photo` is deliberately absent from the re-export surface: it is an
imported name used internally by `orm.delete_draft` and is resolved through `orm`'s module globals;
patch targets must use `telegram_bot.services.ad_data.orm.delete_photo`.

Test patch targets referencing `telegram_bot.services.ad_data` (e.g. in
`test-audit-block-f-findings.md`) remain valid — the façade preserves the import path.

## Login Token Lifecycle Seam (ENT-005)

`apps/users/services/login_token.py` owns the `LoginToken` lifecycle end to end:
issuance (web), claim (bot, phase 1), consume (web, phase 2). The two callers
are `users.views.consent.login_issue` / `login_status` (web) and
`telegram_bot.handlers.login.handle_login_orm` (bot, via the thin
`_claim_login_token` wrapper). Web-side SHA-256 hashing lives only in this
module. Cross-link: the token protocol's rationale (192-bit CSPRNG, POST-only +
CSRF, two-phase background) is in
[`technical-specification.md` §H](../01-spec/technical-specification.md) and
[`db-schema.md`](../02-database/db-schema.md) — single source of truth, not
re-documented here.

### The two predicates and why they are not unified

The claim and consume operations have **different** predicates and must never
be unified into a shared helper:

- Claim (bot) — `telegram_id IS NULL AND consumed_at IS NULL AND expires_at > now`.
  A single `UPDATE ... RETURNING` statement with no prior read: there is no
  read-then-write window, and Postgres re-evaluates the `WHERE` under READ
  COMMITTED after the row lock, so a concurrent claim matches zero rows.
- Consume (web) — `telegram_id = <observed> AND consumed_at IS NULL AND
  expires_at > now`. The consume must read first (it needs `token.telegram_id`
  to pick the user); its read may be stale, but every guard is re-asserted
  inside the `UPDATE` and the affected-row count is the arbiter.

The shared live-ness conjuncts are deliberately re-spelled in both functions
rather than factored out. Phase 04 rated the two-phase claim zero-TOCTOU and
sound; there is no defect to fix by merging them.

### The caller-owns-the-transaction rule

The service functions open no `transaction.atomic()` of their own: the bot's
`handle_login_orm` owns its single `atomic()` (and calls `claim_token` inside
it), and the web's `login_status` owns its `atomic()` (and calls
`consume_token` inside it). The caller owns the transaction; the service owns
the predicate.

### The `AUT-007` boundary and the two existing deleters

`issue_token` issues a fresh token per page view, so a browser can hold several
live tokens; no invalidation of prior outstanding tokens is implemented here.
That is `AUT-007` (phase 04, VAL-002), filed separately and retained-not-merged
with `ENT-005`; when it lands it lands inside `issue_token` in this module.
This module does **not** delete tokens — `users/services/deletion.py`'s
`withdraw_consent` and `core/management/commands/cleanup_login_tokens.py`
remain the only two deleters.

## Bot Command Menu

The bot registers a localized command menu at startup (EC-3). In `telegram_bot/lifecycle.py`,
`_on_startup` calls `_set_bot_commands(bot)`, which invokes
`bot.set_my_commands(commands, language=lang)` once per configured language — `ru`, `bs`, `en` —
so users see the bot menu (`/start`, `/language`, `/post`, `/alerts`) in their preferred locale, plus
a no-language default scope (`_COMMANDS["en"]`) so the menu never renders empty.

| Locale | `start` | `language` | `post` | `alerts` |
|---|---|---|---|---|
| `ru` | Начать | Язык | Разместить объявление | Уведомления |
| `bs` | Početak | Jezik | Objavi oglas | Obavještenja |
| `en` | Start | Language | Post ad | Alerts |

The `ru`/`bs`/`en` descriptions are stored as localized literals. Notably, the `en`
descriptions are English literals (NOT `gettext` msgids): eager `_()` at module
scope would freeze them to the import-time locale (`settings.LANGUAGE_CODE`,
Russian in production), leaking Russian into the `language="en"` menu. Failures on any
scope are logged and skipped — the bot still starts polling (fail-open). The registered handlers
live in the 7 routers wired by `configure_dispatcher` in `telegram_bot/main.py` (see
[Bot Support Intake Flow](#bot-support-intake-flow)).

## Bot Language Switch

The `/start` greeting shown to unauthenticated/DECLINE users now renders an inline keyboard with
three buttons: "🌐 Language" (`BotCallbackPrefix.LANG_OPEN`), "Contact us"
(`BotCallbackPrefix.CONTACT_US`), and "Contact support" (`BotCallbackPrefix.SUPPORT_START`)
(`telegram_bot/handlers/login.py` `handle_login_deep_link` no-arg branch). The "🌐 Language"
button opens the language-selection keyboard from `telegram_bot/handlers/language.py`.

`/language` is **not** login-gated (EC-4/EC-5): the same keyboard is served to anonymous users, and
the selected language is stashed in a temporary cache keyed `bot_anon_lang:{telegram_id}` (TTL 3600,
`ANON_LANG_CACHE_TTL` in `apps/core/utils/cache.py`) rather than — for registered users — written to
`User.telegram_language`. At login, `handle_login_orm` backfills the temp-cached language onto a
freshly-created `User` row and then clears the temp cache (`invalidate_anon_language_cache`).

Per-update locale activation is performed by `LanguageMiddleware`
(`telegram_bot/middlewares/language.py`, FQ-001), registered **before** `AccountStateMiddleware`,
resolving each update to: `User.telegram_language` → the `bot_anon_lang` temp cache →
`settings.LANGUAGE_CODE`. Full runtime mechanics (fallback chain, `translation.activate()`/`deactivate()`
lifecycle, `language` context processor) are documented in [`i18n-spec.md`](../01-spec/i18n-spec.md).

## Bot Support Intake Flow

Support intake (EC-2/EC-9) is handled by a dedicated `support_router` in
`telegram_bot/handlers/support.py` — the 7th router included by `configure_dispatcher`
(`telegram_bot/main.py`) alongside `login`, `ad_create`, `alerts`, `ad_copy`, `language`, and
`contact`.

Flow:
1. A user taps "Contact support" on the `/start` greeting → callback `BotCallbackPrefix.SUPPORT_START`
   = `support_start`.
2. `handle_support_start` rejects bots first (fail fast), then applies the per-user support-message
   rate limit (5 messages per 600 s, cache key `bot_support_rl:{user_id}`, see
   `telegram_bot/services/rate_limit.py` `check_support_message_rate_limit`), then sets
   `ContactUsState.AWAITING_MESSAGE` (a `StrEnum` in `telegram_bot/states.py`) and prompts
   *"Write your question — we will reply as soon as possible."*
3. The user's reply is handled by `handle_support_message`, which validates the input (bots rejected,
   empty text rejected, 4000-char cap), persists a `SupportTicket` (status `OPEN`) in a single
   `sync_to_async` ORM call (`handle_support_orm`), then delivers it and confirms the user with the
   generated `ticket_ref` (*"Your request has been received. Reference: SUP-YYYYMM-NNN"*), resetting
   the FSM to `IDLE`.

Delivery targets admin-configured channels via two fail-open seams:
- **Email** — `telegram_bot/services/support_delivery_email.py` resolves recipients from
  `SUPPORT_NOTIFICATION_RECIPIENTS` (then falls back to `EMAIL`-type `SupportContact` rows) and sends
  via `sync_to_async(send_mail(...))` so blocking SMTP I/O never blocks the async event loop.
- **Telegram** — `telegram_bot/services/support_delivery_telegram.py` DMs each active `TELEGRAM`-type
  `SupportContact` via `bot.send_message`, isolating per-recipient failures (including a single
  429 `TelegramRetryAfter` retry-after retry); `EMAIL`-type contacts are skipped.

Access control is enforced upstream by `AccountStateMiddleware` (`telegram_bot/middlewares/permissions.py`):
anonymous and DECLINE users may reach support, while banned/deleted/consent-revoked users are
blocked before the handler runs. For `callback_query` updates the acting-user identity is resolved
from `callback_query.from_user.id` (the button-clicker), **not** `callback_query.message.from_user.id`
(the bot account that sent the inline keyboard) — the prior use of `message.from_user` produced a
fail-open `User.DoesNotExist` bypass of account-state gating on all callback-driven bot interactions.
The middleware resolves the acting user exactly once per update by the stable `chat_id` (never
`telegram_id`, which is nulled on GDPR withdrawal) and reuses that single instance for the interaction
gate, the publish gate, and the FSM `user_id` backfill; an unregistered `chat_id` is a memoised absent
state (`None`), not an error.
The handler additionally guards against bots (mirroring `contact.py`). `SupportContact`/`SupportTicket` schema
and the `SupportChannelType`/`SupportTicketStatus` enums are documented in
[`db-schema.md`](../02-database/db-schema.md#support_contacts) /
[`db-enums.md`](../02-database/db-enums.md#supportchanneltype).

## Email and Support Notification Settings

Email/SMTP and support-notification configuration are read from environment variables in
`config/settings/base.py` via `django-environ`. `dev.py`, `test.py`, and `prod.py` override the
backend (see [Environment Variable Resolution](#environment-variable-resolution)):

| Setting | base.py default | dev.py | test.py | prod.py |
|---|---|---|---|---|
| `EMAIL_BACKEND` | `smtp.EmailBackend` | `console.EmailBackend` | `locmem.EmailBackend` | `smtp.EmailBackend` |
| `EMAIL_HOST` | `""` | — | — | **required** (fail-fast guard, skipped under `DJANGO_BUILD=1` at build or `DJANGO_ONESHOT=1` on dev one-shots) |
| `EMAIL_PORT` | `587` | — | — | — |
| `EMAIL_HOST_USER` | `""` | — | — | — |
| `EMAIL_HOST_PASSWORD` | `""` | — | — | — |
| `EMAIL_USE_TLS` | `True` | — | — | — |
| `EMAIL_TIMEOUT` | `10` | — | — | — |
| `DEFAULT_FROM_EMAIL` | `noreply@<SITE_URL>` | — | — | — |
| `SUPPORT_NOTIFICATION_RECIPIENTS` | `[]` (`env.list`) | — | — | — |

- `EMAIL_*` are the classic Django SMTP settings; `prod.py` raises `ImproperlyConfigured` if
  `EMAIL_HOST` is empty at runtime (ensures transactional email deliverability).
- `SUPPORT_NOTIFICATION_RECIPIENTS` is an optional `env.list` of admin email addresses that
  support-ticket notifications are delivered to. When empty, the email delivery service falls back
  to the `email` addresses of active `EMAIL`-type `SupportContact` rows.
- Template variables (`EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`,
  `EMAIL_USE_TLS`, `EMAIL_TIMEOUT`, `DEFAULT_FROM_EMAIL`, `SUPPORT_NOTIFICATION_RECIPIENTS`) are
  present in `.env.dev.example`, `.env.prod.example`, and `.env.test.example` (these `.example`
  templates are the tracked source; live `.env.*` files are gitignored). See
  [`docker-deployment.md`](../ops/docker-deployment.md#environment-variables) for the full runtime
  environment-variable catalog.
