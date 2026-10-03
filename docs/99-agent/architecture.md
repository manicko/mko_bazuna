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
  - pii-consent-remediation-record
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
   a `finally` teardown (ENT-002). The daily set (`send_alerts`, `rollup_daily_metrics`,
   `purge_consent_records`) is
   gated on a **durable** marker in the `scheduler_daily_state` singleton ([`db-schema`](../02-database/db-schema.md#scheduler_daily_state-singleton)),
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
   for dev one-shot services, which run the bootstrap module `config.settings.oneshot`
   with `DJANGO_ONESHOT=1`; under `config.settings.prod` the `DJANGO_ONESHOT` flag is
   inert and the guard always runs. The real URL is provided at runtime via `.env.prod`.

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

The `.env.*` files are gitignored (`.gitignore` lines 145–148); `.env.dev.example`,
`.env.test.example`, and `.env.prod.example` are the tracked templates to copy from, while
`.env.example` is a cross-tier reference stub (deliberately not exhaustive) that points at
those three.

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
  The allowlist is gated in **both** directions:
  `config/settings/tests/test_env_allowlist.py` asserts that every `KEY=` in the four tracked
  `.env.*.example` templates is allowlisted (and that `DJANGO_BUILD` / `DJANGO_ONESHOT` are absent
  from them), while `config/settings/tests/test_env_allowlist_reverse.py` AST-scans the Python tree
  and asserts that every `os.getenv` / `env(...)` read is allowlisted. A new env var therefore
  lands with its `ALLOWED_ENV_VARS` entry **and** its template updates in one commit.
- **Shared secret-validation helpers (`config/settings/secret_validation.py`):** the `^<[^>]+>$`
  placeholder pattern and the bot-username contract (`is_placeholder`,
  `is_valid_bot_username`, `validate_bot_username`) live in one module instead of being compiled
  separately in each settings module. `prod.py` imports it; the `repair_bot_username` management
  command imports `is_valid_bot_username`, so "what the boot guard accepts" and "what the repair
  command repairs" cannot drift. It must never import another settings module or `apps.*`
  (settings are imported before the app registry exists, and `prod.py` importing it would cycle).
  `BOT_USERNAME_PATTERN` duplicates `SiteConfig.bot_username`'s `RegexValidator` because settings
  cannot import the model; the two are held together by
  `test_bot_username_validation.py::test_bot_username_helper_agrees_with_model_validator`.

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

**Status: `04-AUT-001` is CLOSED with a mechanism.** The finding's live vectors
are closed by a **browser binding**:

- `LoginToken.browser_binding` is a SHA-256 digest column (the raw id is never
  stored), added by migration `0003_logintoken_browser_binding`.
- The digest is of the `__Host-login_browser_id` cookie value (unprefixed
  `login_browser_id` on HTTP-only dev/test origins), resolved per settings.
- `consume_token` fails **closed**: a `NULL` binding, an absent/malformed
  presented id, or a digest mismatch returns `ConsumeOutcome.UNBOUND`, which the
  view maps to HTTP **410**, and the token is **not** burned.
- Delivered by commits `8c65548` / `818c450` / `a0bd928`.

**Residuals, stated so the closure is not read as absolute.** A raw bearer token
is still rendered into the page (`users/login_issue.html`), so a **shared
device** or a **stolen raw token value** remains an attack vector — the binding
narrows *who may redeem* the token, it does not remove the token from the client.
Separately, the **CSRF / `GET`-writes half** of the finding is **owned by phase
15 `15-AUTHZ-004`** and is not closed here.

**Gate `G-1h` re-banding — owed to the Validator, never performed.** The source
audit report justified the HIGH rating with a **`Referer`-header** leak. That
rationale is **NOT supported** by the shipped code: the token never appears in a
**first-party web URL** — `login_status` is `@require_POST` and reads
`request.POST["token"]`, so the only URL that carries it is the Telegram deep
link to a **third-party** origin, which is the designed transport and is exactly
why no `Referer` leak occurs. `Referrer-Policy` is set at **three nginx
locations per file** (`nginx.conf`, `nginx.dev.conf`), and Django's default
`SECURE_REFERRER_POLICY` is `same-origin`. The **re-worded HIGH rationale** is
therefore: the live vectors are a **shared device** and a **stolen raw token
value**. The mechanism is unchanged; only the stated rationale is corrected.

**Recorded deferral.** The `privacy.html` ePrivacy cookie-inventory row for
`login_browser_id` is **deferred, not fixed** (gate `G-1g`) — see the
`### Deferred: login_browser_id Missing From the Privacy Page (04-AUT-001)`
sub-section below.

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

### The `04-AUT-007` boundary and the two existing deleters

`issue_token` supersedes a browser's earlier **live, unclaimed** token at issue
time, so one browser profile holds at most **one live unclaimed token**. The
supersession predicate has exactly four conjuncts and all four are load-bearing:

- `browser_binding = <digest of the resolved browser id>` — scoped to this
  browser only. There is deliberately **no** `OR browser_binding IS NULL`
  disjunct: a `NULL` row is already never redeemable (`G-1a` → `UNBOUND` in
  `consume_token`), so excluding it loses no control, and the disjunct would let
  one browser's issue reach across bindings.
- `telegram_id IS NULL` — **required**. At issue time no identity exists, so
  this excludes every token the bot has **already claimed**. A claimed row is
  mid-handshake; burning it would let a same-site prefetch of `/login/issue/`
  kill a login whose user already tapped the Telegram button — strictly worse
  than `04-AUT-007`. This applies `B-03`'s `UNBOUND` non-burning rule to
  supersession.
- `consumed_at IS NULL AND expires_at > now` — only a currently live token is
  superseded; an already-consumed or expired row is left untouched.

The verb is `UPDATE ... SET consumed_at`, **never** `DELETE`: it reuses an
existing column (**no migration**), and `claim_token`'s `WHERE` plus
`consume_token`'s read guard already refuse a burned row as `GONE`. This module
therefore remains a **burn, not a third deleter** —
`users/services/deletion.py`'s `withdraw_consent` and
`core/management/commands/cleanup_login_tokens.py` stay the **only two**
deleters.

The predicate is bounded by `TOKEN_TTL_SECONDS` (≤300 s): at most one unclaimed
row per browser can be live at a time, and any row the supersession misses
expires within the window. The framing is **one live unclaimed token per browser
profile**, not "one live token per user": `telegram_id` is `NULL` at issue time,
so a per-user invariant is not expressible here. The likeliest real-world
trigger is a **second tab of the same profile**: opening `/login/issue/` there
silently supersedes the first tab's still-live unclaimed token, so only the
second tab's deep-link stays redeemable.

**Issuance is GET-renderable — `login_issue` is not `@require_POST`.** It
carries only `@never_cache`; `@require_POST` guards the *consume* half
(`login_status`) alone. Any same-origin navigation, prefetch or `<img>` to
`/login/issue/` therefore mints a token **and** runs the supersession, which is
precisely why the predicate above is bounded to **unclaimed** rows instead of
being allowed to burn a claimed one. Cross-site CSRF-forged issuance is
rate-limited (`login_rate_limit_check`, `check_deep_link_render_rate_limit`, both
`429`) but not forbidden. Closing it means moving the deep-link page behind a
POST, which changes the entry point of the whole login funnel. **Recorded here
as a known gap; this phase did not close it.**

### `04-AUT-007` verdict and the `G-4h` residual

**Status: `04-AUT-007` is WEAKENED, not closed.** The invalidation half is
delivered: `issue_token` supersedes the issuing browser's earlier **live,
unclaimed** token, so a repeated issuance no longer accumulates redeemable
pending tokens — one browser profile holds at most one. The audit's own `R-16`
check (*"Repeated issuance invalidates the browser's previous outstanding
token"*) therefore now **PASSES**, pinned by
`apps/users/tests/test_login_token.py::TestIssueTokenSupersession::test_second_issue_supersedes_the_first`
(the first token is neither claimable nor redeemable after a re-issue). It is
**weakened rather than closed** because the residual below survives, and because
the CSRF / `GET`-writes half is owned by phase 15 `15-AUTHZ-004`.

**The `G-4h` residual, verbatim (the plan requires the exact wording):**

> a raw token leaked from the same browser profile stays redeemable by a holder of that profile's cookie for the remainder of the 300 s TTL.

**Provenance.** `G-4h` is a **Validator** obligation, not an Implementor one
(execution plan §H routes `B-04` → Validator: *"NOT a gate on the Implementor —
an owed action"*). The two `B-04` commits have empty bodies and history is not
rewritten, so this tracked block is where the obligation is discharged. **The
Planner does not set the finding's status; this record does.**

## Account-State Predicate Seam (06-PII-104, 06-PII-109)

Four declarations in `src/backend/apps/users/services/account_state.py` answer four different
questions about an account. They are **composed, not merged**: each answers exactly one question,
and no predicate mutates another. Confusing them is what produced the pre-phase-06 defects, so the
split is recorded here rather than left to the docstrings.

| Predicate | Shape | Question it answers | Deliberate omission |
|---|---|---|---|
| `account_state_q(prefix="") -> Q` | queryset-level, returns a **new `Q`** on every call | *"Which rows' owners may receive messages?"* — the filterable form of the access-control flags | omits `ads_auto_publish`: a publishing restriction is orthogonal to whether an account may be contacted |
| `get_account_state(user) -> AccountState` | instance-level `NamedTuple` of the **six** flags | *"What is this account's state?"* | — |
| `can_login(user)` | instance-level | *"May this identity obtain and hold a web session?"* | does not read `is_declined` (Q-D1, below) and not `is_deleted` (a deleted user has `telegram_id` nulled and cannot be looked up at all) |
| `can_publish_ad(user)` | instance-level | *"Is this account allowed to publish at all?"* | does not read `consent_given_at`; does not read `is_declined` (the decline travels on `ads_auto_publish=False`) |
| `can_store_personal_data(user)` | instance-level | *"May this account have personal data stored for it?"* — the storage-consent gate support intake needs | omits `is_active` (that is the operator access switch, and plan 19's support carve-out depends on it staying omitted) |
| `can_create_ad(user)` | instance-level, a **conjunction** | *"May this account create or edit an ad?"* | does not add `is_active` (already covered by `ModelBackend` and by the bot's `_evaluate_user_state`) |

**`account_state_q` is a pure function, never a manager.** It is not installed on a manager and
no `get_queryset()` overrides it. That is load-bearing: `AccountStateMiddleware._resolve_user`
does `User.objects.get(chat_id=...)` and treats a miss as an unregistered, **fail-open** identity,
so a default-manager filter would invert the deny gates the predicate exists to enforce. Its five
conjuncts are `is_deleted`, `consent_revoked_at IS NULL`, `is_declined=False`, `is_banned=False`,
`is_active=True`; `prefix` is the ORM lookup prefix to `User` (`""` on a `User` queryset,
`"user__"` on a model that reaches the owner through its FK). `Q` is immutable and `__and__`
returns a new object, so callers may narrow it without mutating the declaration or a sibling
result. A never-consented but otherwise unblocked registered user passes all five conjuncts —
which is exactly why `can_store_personal_data` exists as a separate predicate.

**The alert fan-out is gated by the same declaration, on both sides (06-PII-104).** An ad whose
owner is withdrawn, declined, banned or deactivated is hidden from public search, listings, direct
URL and the media gate, so it must not fan its title and price out to subscribers either:

- `apps/search/services/alert_query.py::find_matching_ads` applies `account_state_q("user__")` to
  the **ad** queryset — this is the ad-side audience filter.
- `find_matching_saved_searches` applies `account_state_q("user__")` to the **`SavedSearch`**
  queryset — a withdrawn, declined, banned or deactivated **subscriber** receives no alerts. Its
  docstring is explicit that the ad's *owner* is deliberately not filtered there (an `Ad` filter
  cannot constrain a `SavedSearch` queryset) and that its one production caller,
  `immediate_alerts.deliver_immediate_alerts`, applies the same predicate to its own ad fetch.
- The **daily** path (`send_alerts`) and the **immediate** path both go through these two
  functions, so gating the audience in the two matchers is what gates all three delivery paths;
  there is no separate per-path audience filter to forget. The `chat_id` check remains a
  **delivery precondition** applied at the record/payload stage, not an audience filter.

**Import-cycle hazard (frozen).** `account_state.py`'s transitive import closure already reaches
`apps.search.services.cache` through `apps/users/services/__init__.py` → `deletion` →
`bump_search_cache_version`. The alert path consuming `account_state_q` therefore depends on
`apps/search/services/__init__.py` staying **import-free**; a submodule import added there closes
the loop and breaks the whole alert path. A fresh-interpreter probe in
`apps/users/tests/test_account_state.py` is the tripwire. Do not "tidy" that `__init__.py`.

**A DECLINE no longer blocks login (Q-D1, ratified 2026-10-03).** `is_declined` was dropped from
`can_login()`; publishing stays restricted via `ads_auto_publish=False` and listing/search
visibility via `account_state_q`. The bot tier is deliberately **stricter than `can_login`**: a
declined user may hold a web session but is **browse-only** in the bot, with exactly two
carve-outs — the contact deep-link (contact still works while publishing does not) and the
`login_<token>` deep-link, which is the **route back**. The login carve-out is pattern-based
(`_is_login_deep_link`, matching the same `LOGIN_PATTERN` the handler matches, imported lazily to
avoid a middleware/handler cycle) precisely so a bare `startswith("login_")` cannot also swallow
`login_start`, `login_email` and `login_help`. It is scoped to `is_declined` alone: a deactivated,
banned, deleted or withdrawn account is refused even a well-formed login deep-link. Full decision
record:
[pii-consent-remediation-record.md](pii-consent-remediation-record.md#decline-1-q-d1--a-decline-is-reversible).

**The ad-creation gate (06-PII-109).** `can_create_ad` is `can_publish_ad AND
can_store_personal_data`, and the composition is the rule — neither predicate alone is. Creating
an ad stores the seller's user-authored text and photos, so it is also a personal-data-storage
act. It is enforced at the **writers**, not only at the entry point:

- Bot — two refusals, the shape `support.py` uses. `AccountStateMiddleware._evaluate_publish_permission`
  returns `AD_CONSENT_REQUIRED_MESSAGE` (the `ads_auto_publish` branch is kept first), and
  `submit_ad` returns `SubmitAdOutcome.CONSENT_REQUIRED` as its **first statement**, before any
  filesystem work, staged-media plan, thumbnail generation or `transaction.atomic()`. `process_preview`
  answers the outcome's message and clears the FSM.
- Web — four seller surfaces through one shared pair of helpers in `apps/ads/views/edit.py`
  (`_seller_may_create_ad`, the thin seam over `can_create_ad`, and
  `_consent_required_forbidden`, the distinct `HttpResponseForbidden`) used by `ad_edit`,
  `ad_archive` and `ad_reactivate`; `dashboard` lives in its own module but imports the same
  helpers. Existing ownership-`403` wording and lock-timeout re-render paths are preserved.
  `ad_delete` (`apps/ads/views/delete.py`) is deliberately **not** gated.

## Account-State and Session Revocation (04-AUT-002)

**Status: `04-AUT-002` is NOT closed.** The web tier has **no per-request gate
for `is_banned` / `is_deleted` / `is_declined`**: `MIDDLEWARE` is a pinned
15-entry list with no gate that re-checks those three flags on an authenticated
request. A `django_session` row is therefore never invalidated when those flags
change. (`is_active` is the exception — it *is* re-checked per request by
Django's own `ModelBackend`, see
[Operator-Facing Account Kill-Switch](#operator-facing-account-kill-switch-emergent-from-b-01-b-05)
below.)

Of the five **logout-flushable** account-state transitions, the only one a **subject** can
trigger on themselves is `consent_withdraw`, and it is closed. The rest are correct-by-design
no-logout transitions or operator-driven surfaces where a `logout()` would target the wrong
identity:

- `users/views/consent.py::consent_withdraw` is **CLOSED** — it calls
  `logout(request)`, which flushes the withdrawing browser's session.
- `users/views/consent.py::consent_accept` is **correct** — it restores
  capability; no logout belongs on it.
- `users/views/consent.py::consent_decline` is deliberately left untouched
  (`B-07` gate `G-7b`) — and after phase 06 that reasoning rests on a
  **different** predicate. A decline does not flush the session, and it must not:
  the only clearer of `is_declined` is the **authenticated** `consent_accept`, so a
  decline logout would strand the subject. Under the pre-phase-06 design the strand
  was unavoidable (`can_login(is_declined=True) is False`); **owner decision Q-D1
  (ratified 2026-10-03) removed that**: `is_declined` is no longer a login blocker,
  and `AccountStateMiddleware` lets a declined user through the `login_<token>`
  deep-link specifically, so recovery does not depend on the session that recorded the
  decline. See
  [pii-consent-remediation-record.md](pii-consent-remediation-record.md#decline-1-q-d1--a-decline-is-reversible).
  Acceptance retention (`G-E`) is the missing double-fencing.
- `users/admin.py::UserAdmin.withdraw_consent_action` is now **wired and reachable**
  (phase 06, `06-PII-107`, Q-D7 = WIRE): registered in `UserAdmin.actions` and gated
  superuser-only through `permissions=["delete"]` → `has_delete_permission`, which
  delegates to the superuser-only predicate. The `B-01` retirement of the form's
  `is_deleted` / `is_declined` writes therefore *does* have a compensating operator
  trigger. It is still **logout-less** — the subject is never the caller, so a
  `logout()` would be the same wrong-target trap as `ban_user` — and it writes the
  `WITHDRAWN` `ConsentRecord` inside the withdrawal transaction with **no actor
  column and no IP/user-agent**, which is the open `06-NEW-02` limitation recorded in
  [`db-schema.md`](../02-database/db-schema.md#consent_records-zone-f--plan-21).
- `moderation/views/review.py::ban_user` is **reachable but unfixable with a
  `logout()`**: it is `@staff_required`, so `request.user` is the **moderator**
  while the changed identity is `ad.user`. `django.contrib.auth.logout(request)`
  takes no target-user argument, so adding it would log out the moderator and
  leave the banned seller's session fully live — a trap the five pre-existing
  ban tests structurally cannot detect.

Two further account-state write surfaces were added by plan 18 and are **also
logout-less**: `users/admin.py::UserAdmin.deactivate_user` /
`reactivate_user` (delegating to `apps.users.services.deactivation`). They are
operator-driven, so the subject is never the caller and a `logout()` would be
the same wrong-target trap as `ban_user`. They are **not** in the list above
because that list is scoped to the consent transitions;
`deactivate_user` is the one operator transition that **does** revoke the
subject's live session, and it does so through `ModelBackend`, not a logout.
(`withdraw_consent_action` **is** in the list above and is operator-driven for the
same wrong-target reason; it gained no logout when phase 06 wired it.)

`django_session` cannot be enumerated cheaply: it has no user column, and
`session_data` is `signing.dumps(..., compress=True)` — zlib-compressed, base64,
HMAC-signed, **never encrypted** — so no `LIKE` scan is possible. An O(live
sessions) decode scan would also run inside `ban_user`'s already-locked window.
`ConsentRecord.session_key` is not a shortcut: `auth_login`'s `cycle_key()`
invalidates it.

**Residual (knowingly accepted, HIGH):** a banned seller who already holds a web
session keeps it for the remainder of its 14-day life, and can reach the
dashboard, `ad_edit`, `ad_archive`, `ad_reactivate`, cabinet, search history and
seller analytics. **The sanction is defeatable:** `ad_edit` and `ad_reactivate`
have no account-state check and call the real
`apps.moderation.services.auto_moderation.auto_moderate`, which reads
`ModerationCriteria` only and **never `is_banned`** — so a banned seller can
archive an ad, re-post it, and auto-moderation can return it to `PUBLISHED`. A
ban that lets the seller relist is not a ban. Executed and pinned by
`apps/ads/tests/test_edit.py::TestBannedSellerRelistKnownGap`. **Owner of the
fix: phase 15, `15-AUTHZ-001`** (a per-request account-state gate), which is
also what turns `TestConsentBannerGuard::test_banner_hidden_for_deleted_user`
red; that test currently encodes the defect (`GET /dashboard/` → `200` for a
soft-deleted user) and phase 15 must budget its rewrite.

**Bot-tier residual (asked-for-here so `04-AUT-002` reads in one place):** the
Telegram bot tier now **enforces `is_active`, with a support carve-out** (plan
19, 2026-10-03). `AccountStateMiddleware` reads the shared
`get_account_state` predicate, which now carries `is_active`; a deactivated user
is refused every bot path **except** the no-argument `/start` greeting,
the `SUPPORT_START` callback, and free text inside the support-intake FSM — the
restoration channel (plan 19 `19-D2`/`19-D6`). This closes plan 18's
deferred-work `D-2`. Probed and pinned by
`src/telegram_bot/tests/test_bot_deactivation_matrix.py`. **The three-flag
remainder is still open:** `is_banned` / `is_deleted` / `is_declined` still have
**no bot-tier gate** and no per-request web gate. **Owner of the remainder:
phase 15, `15-AUTHZ-001`.** This is the open piece of `04-AUT-002`, alongside
the unrevoked `is_banned` / `is_deleted` / `is_declined` sessions and the absent
`django_session` janitor.

**No `django_session` janitor exists:** `clearsessions` appears nowhere in
`src/`, `docs/`, `docker/`, `.github/`, `Makefile` or `Makefile.ps1`, so the
table is unbounded in row count. `SESSION_ENGINE` is unset (the backend is the
DB) and `SESSION_COOKIE_AGE` is now declared in [`base.py`](../../src/backend/config/settings/base.py)
as `60 * 60 * 24 * 14` (`SESSION_SAVE_EVERY_REQUEST` stays `False`). This is a
retention/row-count control, **not** a session-revocation control
(`clear_expired()` deletes only rows past `expire_date`); it is re-filed against
[`db-retention.md`](../02-database/db-retention.md) / phase 12 (`B-07` gate
`G-E`), because adding it to `HOURLY_COMMANDS` (9→10) or `DAILY_COMMANDS` (3→4
after phase 06 added `purge_consent_records`) would break the exact-`==` pinned
lists in `apps/core/tests/test_scheduler.py`.

## Operator-Facing Account Kill-Switch (Emergent from B-01 + B-05)

**Status: the operator-facing disable path now exists; `04-AUT-002` remains NOT
closed.** This gap was **not a defect in any single block** — it was an
**emergent consequence** of two independently-accepted blocks. It is closed by
plan 18 with an admin action, and the web-session half of `04-AUT-002` on the
`is_active` flag is now revoked per request.

The two original facts, and the fix:

- **`B-01` made `User.is_active` read-only in the admin change form.** This was
  **correct**: `UserAdmin.has_change_permission` returns `request.user.is_staff`
  and **ignores `obj`** (verified in
  [`apps/users/admin.py`](../../src/backend/apps/users/admin.py)), so a writable
  `is_active` would have let any moderator disable arbitrary users, including
  superusers. The change form's writable fields are still exactly
  `['preferred_city']`, and `is_active in readonly_fields` is still `True`.
- **`B-05` hardened the issuance point** so a disabled account receives no
  session cookie: `login_status` refuses `is_active = False` with a uniform `410`
  before the first session write (see
  [`technical-specification.md` §H](../01-spec/technical-specification.md)). Also
  correct.

**The operator path.** Plan 18 `B-2` registers two named admin actions on
`UserAdmin` — *Deactivate selected users* and *Reactivate selected users* — gated
by a new named predicate `UserAdmin.has_deactivate_permission`
(`is_staff or is_superuser`, i.e. `User.role == ADMIN`). They delegate to
`apps.users.services.deactivation` (`B-1`), which is the single writer of the
operator `is_active` lever. A non-superuser actor may act only on **non-privileged**
targets: the service excludes `is_staff` / `is_superuser` rows and self, and
reports the refused counts (product decision `18-D1` / `18-Q7`). `manage.py
shell` is no longer the only writer.

**Ban parity (plan 19).** The `is_banned` lever now carries the same kind of
target scope, at its own single home: `apps.moderation.admin_actions._resolve_ban_targets`,
called by **both** production writers of the flag (`ban_user_for_ad` and
`bulk_ban_users`). A non-superuser operator may act only on **non-privileged**
targets — `is_staff` / `is_superuser` rows and self are excluded, a superuser's
selection is unrestricted — and both operator surfaces now **report** the
refusal instead of applying it silently: `AdAdmin`'s toast counts the dropped
`self` / `privileged` / already-banned rows and escalates to `error` when the
whole selection was refused, and the `moderation:ban` view posts a
`messages.warning` naming the refusal. On that view the tier clause appears only
on the **refusal** path — a successful ban posts no message, so a moderator gets
no tier statement and no confirmation there. Before plan 19 the flag was writable
against any row, so a moderator could ban a superuser. Like deactivation this is
a **target** scope, not an actor gate; "moderator" remains the documented synonym
for `is_staff`, so a **peer moderator is `is_staff=True`** and is excluded by the
same clause as staff and superusers.

**The two levers have opposite tier profiles**, and the operator copy says so on
both surfaces rather than claiming a total lockout: a ban refuses **login and
publishing** and is enforced in the **Telegram bot**, but it does **not** revoke
an existing web session, which keeps working until it expires. Publishing is
refused at two independent seams: `AccountStateMiddleware` denies *every* bot
interaction, and the **create-time gate** `can_create_ad` refuses the writers
themselves — `submit_ad` returns `SubmitAdOutcome.CONSENT_REQUIRED` as its first
statement and the four web seller surfaces return `403` (see
[Account-State Predicate Seam](#account-state-predicate-seam-06-pii-104-06-pii-109)).
`can_publish_ad()` is half of that composition, so it is **no longer a dead
predicate** (it had no production call site until phase 06). `is_active` is no
longer the mirror image: since plan 19
(2026-10-03) it is enforced on **both** tiers — the web's `ModelBackend` **and**
the bot's `AccountStateMiddleware` (with the support carve-out).

**What plan 19 does NOT close.** No **un-ban path** exists anywhere in
production, so a ban is still one-way from the UI (`D-19-2`). There is no
per-request web gate for `is_banned`, so a **banned seller keeps a session and
can still re-list**; the bot-tier `is_banned` / `is_deleted` / `is_declined`
residual and the `django_session`
janitor are likewise untouched (`D-19-3`, owner `15-AUTHZ-001`). The dead
`<id>/password/` route is still rendered (`D-19-5`). And the whole moderator
contract — `UserRole.MODERATOR`, `media_gate`, `AdminSite.has_permission`, the
15-of-17 `ModelAdmin` permission overrides — is `15-AUTHZ-003`'s and is
**untouched**; this landing must **not** be read as phase 15 closing. The
remaining items (asymmetric `ModeratorActionLog` coverage, the un-locked read of
the actor's privilege, the deliberately undecided flag taxonomy) are enumerated
with owners in **plan 19 §7** and are deliberately not absorbed here. (The fourth
item plan 19 listed, "the dead `can_publish_ad()` predicate", is **retired** by
phase 06: `can_create_ad` composes it and is wired into both tiers.) Separately,
approve / reject / soft-delete are
**ad-level** actions with no target guard: a moderator may still act on a
privileged account's ads.

**The web-tier revocation is now proven, and an earlier record here was wrong.**
A `django_session` row is still never **deleted** on an account-state change, but
`is_active = False` **does revoke an already-authenticated session on the next
request** — the prior claim that it "only blocks future issuance" was false. The
mechanism runs per request:

```
AuthenticationMiddleware.request.user
  -> django.contrib.auth.get_user(request)
     -> load_backend(...).get_user(user_id)
        -> ModelBackend.get_user()  ->  user_can_authenticate(user)  ->  user.is_active
     -> None becomes AnonymousUser()
```

Runtime evidence (plan 18 §1; now promoted to a permanent test,
`test_admin_deactivate_user.py::test_deactivate_user_revokes_an_existing_web_session`):
an existing session and a fresh issuance are indistinguishable — both are killed.
This guarantee holds **unconditionally today** because `AUTHENTICATION_BACKENDS`
is unset in `src/backend/config/settings/`, so Django uses exactly one backend,
`ModelBackend`, and it consults `user_can_authenticate()`. It is **conditional on
that staying true**: a second backend that does not consult
`user_can_authenticate()` would weaken it, so anyone adding an auth backend must
re-read this note. `is_banned` / `is_deleted` / `is_declined` remain unrevoked
(`D-1`); this correction is about `is_active` only and must **not** be generalised
to the other flags.

**The bot (Telegram) tier now enforces `is_active` — with a support carve-out.**
The bot holds no web session and resolves identity per message;
`AccountStateMiddleware` reads `is_banned` / `is_deleted` / `is_declined` /
`consent_revoked` **and, since plan 19, `is_active`**. A deactivated user is
refused every path except the no-argument `/start` greeting, the
`SUPPORT_START` callback, and free text in the support-intake FSM — the
restoration channel (plan 19 `19-D2`/`19-D6`, closing plan 18 `D-2`). Probed and
pinned by `test_bot_deactivation_matrix.py`. The operator toast
(`DEACTIVATION_ENFORCEMENT_NOTE`) now states both-tier enforcement plus the
Support carve-out. **`is_banned` / `is_deleted` / `is_declined` remain
bot-unenforced** (`D-1`, owner `15-AUTHZ-001`).

**`04-AUT-002` is NOT closed.** What remains open is enumerated in
[Account-State and Session Revocation (04-AUT-002)](#account-state-and-session-revocation-04-aut-002)
above: no per-request gate for `is_banned` / `is_deleted` / `is_declined`, no
`django_session` janitor, and **no bot-tier enforcement for those same three
flags** (`is_active` is now bot-enforced with a support carve-out; plan 19).

**Operationally:** a moderator **can** disable an ordinary seller and **can**
revoke their live web session; a moderator **cannot** touch a staff/superuser row;
the bot tier enforces `is_active` (with the support carve-out) but not
`is_banned` / `is_deleted` / `is_declined`. The reachability facts are
enumerated in the operator
inventory in
[`docker-deployment.md`](../ops/docker-deployment.md#the-admin-user-change-form-contract-04-aut-005).

**Ownership.** The remaining work is phase 15: `15-AUTHZ-001` (session revocation
for the other flags + bot-tier gate) and `15-AUTHZ-003` (the broader moderator
contract, which must discover `has_deactivate_permission`). This plan is
**pre-work for BLOCK 9**, not a substitute: it does not resolve the moderator
contract and its landing must **not** be read as `15-AUTHZ-003` closing.


### Session Lifetime Policy (04-AUT-006)

**Status: `04-AUT-006` is WEAKENED, not closed.** `B-10` declared the session
lifetime and refresh policy explicitly in `config/settings/base.py`
(`SESSION_COOKIE_AGE = 60 * 60 * 24 * 14` and `SESSION_SAVE_EVERY_REQUEST =
False`), which retires the finding's premise that the value "falls back to the
14-day Django default". It does **not** alter the policy:

- **The exposure window is unchanged at 14 days** — the declared value matches
  the inherited Django default, so no session lives longer or shorter than before.
- **No product decision has been taken on the value.** The number is a named,
  owned decision that still belongs to the coordinator / product owner, not to a
  code commit. Do not record the finding as fixed.
- **The HIGH residual belongs to phase 15, `15-AUTHZ-001`.** A `django_session`
  janitor would **not** help: `clear_expired()` deletes only rows already past
  `expire_date` and cannot shorten a live session, so it does not bound the
  exposure window (see the `04-AUT-002` section above).

The policy is **write-triggered, not a sliding idle window**: Django re-stamps
`expire_date` only on a real save. An authenticated session is written at
`auth_login` and again only on a `?lang=` language switch (pinned by
`config/settings/tests/test_session_policy.py`); an anonymous session is refreshed
by each recorded non-empty search. See
[`technical-specification.md` §H](../01-spec/technical-specification.md).

**Known gap: anonymous `django_session` growth.** A non-empty `?q=` search
request performs **one write per request** against the 30 req/60 s/IP search rate
limit, so the ceiling is **43,200 anonymous session rows per IP per day**,
roughly **604,800 resident rows at steady state**. There is **no `clearsessions`
janitor anywhere in the repository**. Owner: **phase 12** / whoever adds the
janitor. The `django_session` retention row is phase 12's to add; it is
deliberately **not** added to
[`db-retention.md`](../02-database/db-retention.md) by this pass.

**Known gap: ad-edit form loss at session expiry.** Accepted product trade-off of
gate `G-10a`: a long-lived session means an unsubmitted ad-edit form can be lost
when the session expires. This is UX friction, **not data loss**. Owner:
**product**.

## Login-Issuance Rate-Limit Keying (04-AUT-003)

**Status: `04-AUT-003` is PARTIALLY CLOSED.** The **Python** half is closed; the
**nginx edge** half is **DEFERRED, not fixed**.

**Python half (closed).** `apps/core/utils/client_ip.py::get_client_ip` is the
shared peer-gated resolver. The three identical private `_get_client_ip` copies
in `login_rate_limit.py`, `contact_rate_limit.py` and `rate_limit.py` were
**deleted, not merged**. The gate reads `REMOTE_ADDR` first and returns the peer
with **no header read at all** when the peer is not loopback/private/
`TRUSTED_PROXY_NETWORKS`; only when the gate is open does it prefer
`X-Real-IP`, else walk `X-Forwarded-For` right-to-left to the first non-private
hop. A public peer sending either header lands on the **byte-identical** key to
sending neither.

**Edge half (deferred, why).** `X-Real-IP` is set at **9/9** prod and **6/6**
dev `proxy_pass` locations and `get_client_ip` returns on it **before**
`X-Forwarded-For`, so the XFF branch is **unreachable in production** and
`XFF[0]` being attacker-controlled is **inert by construction**. Separately, the
edge work **cannot be delivered**: `actions/checkout@v4` runs on an ephemeral
`ubuntu-latest` runner, the deploy SSH script contains **no `git` command**, and
the nginx config is a **`:ro` bind mount**, so `up -d` will not recreate the
service. `real_ip` was **refused as harmful**, not deferred: nginx is the first
hop, so `set_real_ip_from` has no legitimate value to name, and
`set_real_ip_from 0.0.0.0/0` would make every client a trusted proxy and —
because `limit_req_zone` keys on `$binary_remote_addr` — **destroy the nginx
rate limiting**.

**The exposure this leaves.** In production `REMOTE_ADDR` at Django is always
nginx's container IP, so the **peer gate is always open** and correctness rests
on one directive in 15 places. Three textual tests in
`src/backend/tests/test_nginx_config.py` now pin that invariant, so a future edit
that deletes, repoints or wildcards it turns a test red.

**Owner and promotion trigger.** Owned by **phase 09** (both `.conf` files) and
**phase 15 `15-AUTHZ-003`** (the `X-Real-IP` directive is load-bearing and is
the likelier thing to be touched). It becomes an ordinary change when
`deploy.yml` gains `git pull` + `nginx -t` + `reload` **with nginx in the
rollback**, **or** the config is baked into the image instead of bind-mounted.
**A separate trigger: putting a CDN or load balancer in front of nginx
invalidates the model and makes `set_real_ip_from` necessary for the first
time — then this deferral must be revisited immediately, not optionally.** The
five manual steps for applying an nginx config change are in the operator
runbook, [`docker-deployment.md`](../ops/docker-deployment.md#applying-a-change-to-the-nginx-configuration).

### Comment-Half Tracker Qualification (04-VAL-002)

**Status: `04-VAL-002` is PARTIALLY CLOSED.** The **tracker-key** half is
delivered — the in-source finding references are phase-qualified
(`04-AUT-001`, not `AUT-001`) so a tracker lookup resolves against the phase's
own identifier space. The **in-source comment** half is **DEFERRED, not
delivered**: the phase's `G-11` gate closed *by boundary* and deliberately did
not sweep the pre-existing bare citations, so the bare `AUT-00N` references in
source remain until their own passes qualify them (see gate `G-11`).

### Deferred: Untranslated `create_admin_user` Password-Policy Msgid (04-AUT-005)

**Recorded deferral, not a fix.** The msgid
`"Password does not meet the password policy: %(errors)s"` was added to
`apps/core/management/commands/create_admin_user.py::Command.handle` via
`gettext_lazy as _`. The string is **operator-facing** — it is surfaced by the
`create_admin_user` one-shot service when an operator-supplied `ADMIN_PASSWORD`
fails `validate_password`. It is **currently untranslated in `ru`, `bs` and
`en`**: the msgid has no catalog entry in any of the three `.po` files, so a
Russian or Bosnian operator sees the English text.

The i18n completeness gate (`test_i18n_completeness.py`) **does not cover it**:
that gate scans templates and `telegram_bot/handlers/` only, and performs no
catalog-parity check for Python `gettext_lazy` msgids, so the gap is invisible
to CI. This is the direct, defensible cost of the phase's "no `.po` modified"
boundary, which existed because another agent owned the catalogs concurrently.
The msgid is **queued for the `.po` owner**; translating it is out of scope for
this pass. The call site carries an inline pointer back to this record.

### Deferred: `login_browser_id` Missing From the Privacy Page (04-AUT-001)

**Recorded deferral, not a fix.** The login-binding cookie is described as
classified essential in [`db-schema.md`](../02-database/db-schema.md) and
[`db-enums.md`](../02-database/db-enums.md), but the cookie-inventory table in
`templates/privacy.html` has **no row for it** — that table still lists only
`sessionid`, `csrftoken`, `consent_given`, `lang_pref` and `preferred_city`. The
site therefore issues a first-party cookie that its own privacy page does not
disclose.

The row cannot land from this pass: it needs a `{% trans %}` description with
non-empty `ru` and `bs` msgstr, and the `.po` catalogs are owned elsewhere — the
same boundary as the `04-AUT-005` deferral above. Nothing enforces the table's
completeness: `apps/core/tests/test_privacy.py::test_privacy_page_lists_cookies`
asserts that a **fixed list** of five cookies is described, not that every issued
cookie is named, so the gap is invisible to CI.

**Owed to the i18n owner**: add the row, and add `login_browser_id` to that test
so the next missing cookie turns a test red. Until then, treat
[`db-schema.md`](../02-database/db-schema.md) as the accurate disclosure record
and the privacy page as incomplete.

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
banned/deleted/consent-revoked users are blocked before the handler runs, and DECLINE users cannot
reach support because `SUPPORT_START` is not a contact deep-link (pre-existing). A deactivated user
reaches the intake only through the plan-19 support carve-out. A declined user has **two** bot-tier
carve-outs, both peers: the contact deep-link and the `login_<token>` deep-link (the recovery route
back to the authenticated consent form, since a decline is reversible); neither is granted to a
banned/deleted/withdrawn account — see
[Account-State Predicate Seam](#account-state-predicate-seam-06-pii-104-06-pii-109).
**Storage-consent gate (06-PII-101).** Support intake additionally requires consent to personal-data
storage: the handler resolves the actor server-side from the Telegram-signed `chat_id` and enforces
`apps.users.services.account_state.can_store_personal_data` (the six account flags plus a granted
`consent_given_at`). An unregistered `chat_id`, an account without consent, or a stale FSM `user_id`
that disagrees with the resolved actor is refused with a notice pointing at sign-in and consent — no
ticket is created. The bot's handler is the only ticket writer; the model still accepts an
unattributed ticket, but the bot never creates one. For `callback_query` updates the acting-user
identity is resolved from `callback_query.from_user.id` (the button-clicker), **not**
`callback_query.message.from_user.id` (the bot account that sent the inline keyboard) — the prior
use of `message.from_user` produced a fail-open `User.DoesNotExist` bypass of account-state gating on
all callback-driven bot interactions. The middleware resolves the acting user exactly once per update
by the stable `chat_id` (never `telegram_id`, which is nulled on GDPR withdrawal) and reuses that
single instance for the interaction gate, the publish gate, and the FSM `user_id` backfill; an
unregistered `chat_id` is a memoised absent state (`None`), not an error.
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
| `EMAIL_BACKEND` | `smtp.EmailBackend` | `console.EmailBackend` | `locmem.EmailBackend` | `smtp.EmailBackend` — **pinned; the env var is ignored** |
| `EMAIL_HOST` | `""` | — | — | **required** (fail-fast guard, skipped under `DJANGO_BUILD=1` at build or for dev one-shots via `config.settings.oneshot` + `DJANGO_ONESHOT=1`) |
| `EMAIL_PORT` | `587` | — | — | — |
| `EMAIL_HOST_USER` | `""` | — | — | — |
| `EMAIL_HOST_PASSWORD` | `""` | — | — | — |
| `EMAIL_USE_TLS` | `True` | — | — | — |
| `EMAIL_TIMEOUT` | `10` | — | — | — |
| `DEFAULT_FROM_EMAIL` | `noreply@<SITE_URL>` | — | — | — |
| `SUPPORT_NOTIFICATION_RECIPIENTS` | `[]` (`env.list`) | — | — | — |

- `EMAIL_*` are the classic Django SMTP settings; `prod.py` raises `ImproperlyConfigured` if
  `EMAIL_HOST` is empty at runtime (ensures transactional email deliverability).
- **`EMAIL_BACKEND` is not operator-configurable in production.** `base.py` still honours the env
  var, but `prod.py` re-pins `EMAIL_BACKEND` to `smtp.EmailBackend` unconditionally after the
  import, so a console or locmem backend cannot be injected into a deployed environment (message
  bodies — confirmations, support-ticket text — would otherwise be written to stdout instead of
  delivered). `dev.py` and `test.py` still override it.
- `SUPPORT_NOTIFICATION_RECIPIENTS` is an optional `env.list` of admin email addresses that
  support-ticket notifications are delivered to. When empty, the email delivery service falls back
  to the `email` addresses of active `EMAIL`-type `SupportContact` rows.
- Template variables (`EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`,
  `EMAIL_USE_TLS`, `EMAIL_TIMEOUT`, `DEFAULT_FROM_EMAIL`, `SUPPORT_NOTIFICATION_RECIPIENTS`) are
  present in `.env.dev.example`, `.env.prod.example`, and `.env.test.example` (these `.example`
  templates are the tracked source; live `.env.*` files are gitignored). See
  [`docker-deployment.md`](../ops/docker-deployment.md#environment-variables) for the full runtime
  environment-variable catalog.
