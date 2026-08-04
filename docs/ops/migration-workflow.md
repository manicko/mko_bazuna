---
id: migration-workflow
domain: ops
tags:
  - migration
  - django
  - docker
  - consolidation
  - devops
  - operations
related:
  - docker-deployment
  - architecture
  - spec-index
  - seed-workflow
---

## Purpose

This document defines the **development migration workflow** for the Mko Bazuna project. It captures the
dev-mode philosophy decided in *Specification: Dev Migration Consolidation & Failure Fix*
(`../../.ai/problems/06_dev-migration-consolidation_spec.md`).

The core philosophy is:

- **No backward compatibility in dev.** Migration files are dev artifacts; they may be wiped and
  regenerated at any time. Dev database content is disposable (see PO decision Q2-B).
- **One initial migration per app is the steady state.** Schema drift is reflected only after a
  conscious consolidation step — not by piling up incremental files.
- **Threshold-based consolidation.** When any app accumulates more than **8 migration files**, the
  project is reset back to one `0001_initial.py` per app.
- **Migrations must never depend on the outside world.** No external API calls and no live Python
  imports inside `RunPython`/`RunSQL`. Fragile logic lives in management commands.

This keeps `docker compose up` reliable (the `migrate` service always exits 0 on a fresh DB) and
keeps review/CI fast while the schema is still in flux.

## Migration Architecture

Mko Bazuna runs **two long-lived processes against one database**: the web app (gunicorn, sync WSGI)
and the Telegram bot (aiogram). Both import the same Django project and share the ORM. A one-shot
`migrate` service runs **exactly once** before either starts.

### Two-process startup order

`docker-compose.yml` wires the startup with `depends_on` + `condition: service_completed_successfully`:

```
db  →  migrate  →  web (gunicorn)
               →  bot (aiogram)
```

- `db` is a `postgres:18-alpine` container with a `pg_isready` healthcheck.
- `migrate` runs migrations, then exits. `web` and `bot` both block on `migrate` completing
  successfully.
- `create_admin` and `seed` (when enabled via profile) also depend on `migrate`.

### The migrate service

The `migrate` service is a one-shot container built from `docker/Dockerfile`:

```yaml
migrate:
  build:
    context: .
    dockerfile: docker/Dockerfile
  command: python -c "from apps.core.utils.migrate_locked import main; import sys; sys.exit(main())"
  depends_on:
    db:
      condition: service_healthy
  environment:
    DJANGO_SETTINGS_MODULE: config.settings.prod
    DATABASE_URL: postgres://${POSTGRES_USER}:${POSTGRES_PASSWORD}@db:5432/${POSTGRES_DB}
```

It runs `manage.py migrate --noinput` in the `prod` settings, so the same image path used in
production is exercised in dev.

### Advisory lock (`migrate_locked.py`)

`apps/core/utils/migrate_locked.py` wraps `migrate` in a PostgreSQL **session-scoped** advisory lock
(ID `AdvisoryLockId.MIGRATE = 100`, defined in `apps/core/enums.py`):

```python
from apps.core.enums import AdvisoryLockId
from apps.core.utils.advisory_lock import advisory_lock

with advisory_lock(AdvisoryLockId.MIGRATE, session=True):
    result = subprocess.run(
        [sys.executable, "src/backend/manage.py", "migrate", "--noinput"],
        cwd="/app",
    )
    return result.returncode
```

`apps/core/utils/advisory_lock.py` uses `pg_advisory_lock` (session scope) for the migrate path.
This is safe in dev because **no PgBouncer is attached to the migration database** — the lock is
held by the `migrate` container directly. The session lock is **idempotent**: if a previous run
already holds it, a new run blocks; once released, a re-run sees all migrations already applied
and is a no-op.

> PgBouncer (transaction mode) is **production-only** and is not involved in the dev migrate flow.
> Transaction-scoped `pg_advisory_xact_lock` is used by the scheduled sweep jobs instead (see
> `docs/99-agent/architecture.md`).

## Daily Workflow

Day-to-day Django development follows the standard make/edit/migrate cycle. The Makefile
(`Makefile` for Linux/macOS, `Makefile.ps1` for Windows) keeps the commands portable.

### 1. Create new migrations

After changing models in `src/backend/apps/<app>/models.py`:

```bash
make makemigrations
```

This runs `manage.py makemigrations` inside the `web` container and writes numbered files
(`0XXX_*.py`) into `src/backend/apps/<app>/migrations/`. Review the generated diff before committing.

### 2. Apply migrations

```bash
make migrate
```

This runs the one-shot `migrate` service (advisory-locked). On a running stack, if dev data is
disposable, the fastest path is a fresh DB:

```bash
make clean          # stop containers + remove volumes
make up             # db + migrate + web + bot start in the correct order
make create-admin   # recreate the admin user
```

### 3. Start the stack

```bash
make up              # Linux/macOS
.\Makefile.ps1 up    # Windows
```

The `up` target brings up `db`, `migrate`, `web`, and `bot` in the correct dependency order. On a
fresh volume the `migrate` service creates the schema from the single initial migration per app and
exits 0; `web` and `bot` then start.

### Verifying state

```bash
# List applied migrations
docker compose run --rm web uv run python src/backend/manage.py showmigrations

# Fail CI-style if model drift produced un-committed migrations
docker compose run --rm web uv run python src/backend/manage.py makemigrations --check --dry-run
```

The committed test `apps/core/tests/test_migrations.py` (TST-005) asserts both of the above in CI:
`makemigrations --check --dry-run` yields no pending files, and re-applying all migrations is
idempotent.

## Consolidation Workflow

This is the workflow defined by PO decisions Q1–Q6. It is **dev-mode only** — it assumes a
disposable database.

### Thresholds

| App                | Current migrations | Exceeds 8? |
|--------------------|--------------------|------------|
| `ads`              | 10 | **Yes** |
| `analytics`        | 4  | No  |
| `categories`       | 5  | No  |
| `core`             | 1  | No  |
| `locations`        | 2  | No  |
| `lookups`          | 1  | No  |
| `moderation`       | 4  | No  |
| `search`           | 4  | No  |
| `trust`            | 2  | No  |
| `users`            | 3  | No  |
| **Total**          | **36** | — |

The threshold is **8 files per app** (PO decision Q6; variable `CONSOLIDATE_THRESHOLD ?= 8`).
Today `ads` is the only app above the threshold. After the one-time initial reset described below,
every app returns to **1 `0001_initial.py`**.

### One-time initial reset

Per Q1-B / Q2-B, the launch step is a single wipe-and-regenerate:

1. Delete every `0*.py` migration file across all apps (keep only `__init__.py`).
2. `make makemigrations` → produces one `0001_initial.py` per app (10 total).
3. On a fresh dev DB, `make migrate` succeeds and `django_migrations` is clean.
4. `make makemigrations` again (with `--check --dry-run`) confirms no pending drift.

### Recurring consolidation

Once per day of development (or whenever you notice file counts climbing):

```bash
make consolidate        # check threshold; consolidate only apps that exceed it
make consolidate-force  # ignore threshold; reset every app
```

Both targets depend on the helper script `scripts/consolidate_migrations.py`, which is the single
source of truth for the consolidation logic.

### What `scripts/consolidate_migrations.py` does

1. Walks `src/backend/apps/*/` for `migrations/` directories.
2. Counts `*.py` files matching `0*.py` (excludes `__init__.py`).
3. If **any** app exceeds `CONSOLIDATE_THRESHOLD` (default 8) — or `--force` is passed — it deletes
   every `0*.py` migration file and any `__pycache__` under `migrations/` for that app.
4. Prints a per-app summary of what was deleted.
5. Prints the follow-up instructions: `makemigrations`, then `migrate --fake`.

The script performs **only file operations** — it knows nothing about Django or the database. It is
safe to run locally or inside the `web` container.

### What `make consolidate` / `make consolidate-force` do next

After the script runs, the Makefile target continues inside Docker:

1. `docker compose ... run --rm web uv run python src/backend/manage.py makemigrations`
   — regenerates one `0001_initial.py` per affected app from the current model definitions.
2. `docker compose ... run --rm web uv run python src/backend/manage.py migrate --fake`
   — records those new migrations as applied in `django_migrations` **without** re-running their
   SQL, because the schema already exists in the live dev DB. `--fake` reconciles Django's migration
   history with the real schema.

> **Why `--fake`?** The old migrations are gone, but the database they built still exists. Deleting
> the migration files does **not** roll back the schema. `--fake` tells Django "the new
> `0001_initial` is already applied" so the two stop disagreeing. If you want a truly clean DB
> instead, use `make clean` (drops the volume) before continuing.

If no app exceeds the threshold, the script reports `no consolidation needed` and the target skips
the delete step; `makemigrations --check --dry-run` will simply confirm there is no drift.

### Safe vs. extracted data migrations

Not every `RunPython` is a candidate for extraction. The distinguishing factor is **external
dependency**, not whether the data is "local":

| Migration | Kind | Disposition |
|-----------|------|-------------|
| `ads/0006_backfill_translations` | External API (`deep_translator.GoogleTranslator`) | **Extracted** → `manage.py backfill_translations` |
| `categories/0005_load_catalog` | Live Python import | **Fixed in place** — refactored to accept `apps=` and use `apps.get_model()`; YAML rewrite suppressed when called from a migration |
| `categories/0002_seed_categories` | Hardcoded MPTT raw SQL (`lft`/`rght`) | **Fixed in place** — rewritten to use `apps.get_model("categories", "Category")` + `parent=` FK assignment so MPTT recalculates tree values |
| `locations/0002_seed_cities` | Local static seed data | **Safe to keep** (no external deps; local data may stay) |

Rules of thumb (PO decision Q3, Q4):

- **Extract** any `RunPython` that touches a network, an external API, a third-party SDK, or a
  filesystem path that isn't the committed config. Move it to a `management/commands/` command with
  the same name and call it on demand.
- **Fix in place** any `RunPython` that imports the *live* app modules (e.g.
  `from apps.categories.catalog.builder import load_catalog`) without the `apps` argument. The fix is
  to thread `apps` through and access models only via `apps.get_model(...)`.
- **Keep** purely local, deterministic seed data (`seed_categories`, `seed_cities`) — these are
  safe to retain as `RunPython` in the consolidated migration, or to delegate to `call_command` if
  you prefer to reuse the management-command path.

The two extracted commands:

- `manage.py load_catalog [--config PATH] [--no-rewrite]` — loads/updates the catalog from
  `apps/categories/catalog/categories.yaml`. Uses live imports + rewrites YAML by default; the
  migration calls the same builder with `apps=apps, rewrite_yaml=False`.
- `manage.py backfill_translations [--batch-size N]` — translates existing Russian ads to `en`/`bs`.
  Idempotent: skips ads that already have both target fields populated.

## Migration Rules

These are enforced by code review and by `make consolidate` (which surfaces fragile migrations
during regeneration). Violating them is what caused the original `migrate` service to exit 1.

| Rule | Do | Don't |
|------|----|-------|
| **No external calls** | Put API/SDK work in a `management/commands/` command; call it on demand. | Call `deep_translator`, HTTP clients, or any network code inside `RunPython`/`RunSQL`. |
| **Historical models only** | Access models via `apps.get_model("app", "Model")` in `RunPython`. | `from apps.foo.models import Bar` inside a migration (breaks when model shape diverges). |
| **Idempotent SQL** | `CREATE OR REPLACE FUNCTION ...`, `CREATE INDEX IF NOT EXISTS`, `DROP ... IF EXISTS`. | Bare `CREATE FUNCTION`/`CREATE INDEX` (fails on re-run; fails `--fake` reconciliation). |
| **Idempotent data** | Make `RunPython` safe to run twice (skip already-populated rows). | Assume rows are absent; `INSERT` unconditionally. |
| **Side effects** | Keep migrations free of filesystem mutations unless explicitly gated. | Rewrite source-controlled config files (e.g. YAML) as a side effect of migration execution. |

### Why each rule exists

- **No external calls** — the `migrate` container runs during `docker compose up` with no network
  guarantee and no secrets mounted for translation APIs. The build would hang or fail.
- **Historical models** — a migration's `apps` argument gives the model state *as of that migration*.
  A live import reads the *current* model, which may reference columns/tables that don't exist yet
  at that point in the dependency graph (`categories/0005` was the original offender).
- **Idempotent SQL** — consolidated migrations are re-applied with `migrate --fake` and re-run in
  CI; non-idempotent DDL raises on the second pass.
- **Side effects** — the catalog builder's YAML rewrite was triggered during migration 0005 and could
  mutate the committed `categories.yaml` at build time. The fix passes `rewrite_yaml=False` from the
  migration and reserves rewriting for the `load_catalog` command.

## Reference: App Migration Status

The canonical app list (10 apps) and their current migration inventory, as verified on disk.

| App | Migration count | Latest file | Exceeds 8? | Note |
|-----|-----------------|-------------|------------|------|
| `ads` | 10 | `0010_backfill_listing_purpose.py` | **Yes** | Top-heavy; includes the extracted `0006_backfill_translations` |
| `analytics` | 4 | `0004_analytics_event_fk_set_null_and_index.py` | No | |
| `categories` | 5 | `0005_load_catalog.py` | No | Contains the live-import offender (fixed post-refactor) |
| `core` | 1 | `0001_verify_lifecycle_indexes.py` | No | Schema-only; seed indexes only |
| `locations` | 2 | `0002_seed_cities.py` | No | |
| `lookups` | 1 | `0001_initial.py` | No | Reference data (LookupGroup/LookupItem) |
| `moderation` | 4 | `0004_ad_moderation_priority_default.py` | No | |
| `search` | 4 | `0004_fix_index_name_too_long.py` | No | FTS triggers + indexes |
| `trust` | 2 | `0002_trust_level_default.py` | No | |
| `users` | 3 | `0003_user_telegram_premium.py` | No | |
| **Total** | **36** | — | — | |

**Post-consolidation goal:** 1 `0001_initial.py` per app (10 files total), `0006_backfill_translations`
removed from the migration tree and replaced by the `backfill_translations` command, and `0005_load_catalog`
rewritten to use `apps.get_model()`.

The seed data pipeline that depends on migrations is documented separately in
[the seed data workflow](seed-workflow.md) — categories are loaded via the catalog builder and cities
via the `seed_cities` fixture.

## Troubleshooting

### `migrate` exits with code 1 on a fresh DB

Most often caused by one of the fragile patterns documented above:

1. **Live import in a migration** — `ImportError` or `OperationalError: no such table/column`.
   Confirm the offending migration uses `apps.get_model(...)` instead of a direct `from apps...`
   import. Re-run `make makemigrations --check --dry-run` to catch drift.
2. **External API call** — `deep_translator`/`GoogleTranslator` fails at build time. The migration
   must have been extracted to `manage.py backfill_translations`; run it manually after `up`.
3. **Hardcoded MPTT values** — `categories/0002_seed_categories` raw SQL fails when the `categories`
   table name or column layout diverges. The rewritten ORM version sets `parent=` and lets MPTT
   recompute `lft`/`rght`.

Run interactively to read the full traceback:

```bash
docker compose run --rm migrate 2>&1 | tail -40
```

### Pending migrations / schema drift

```bash
docker compose run --rm web uv run python src/backend/manage.py makemigrations --check --dry-run
```

If this reports files to create, commit a new migration (or consolidate). Do not `--fake` drift
blindly — that hides real schema divergence.

### `django_migrations` out of sync with files

After deleting migration files but keeping the DB, Django reports the new `0001_initial` as
`[ ]`. Reapply with `--fake`:

```bash
docker compose run --rm web uv run python src/backend/manage.py migrate --fake
```

The `make consolidate` target does this for you automatically.

### Migration dependency cycle

If `makemigrations` emits a circular-dependency error, inspect the generated graph:

```bash
docker compose run --rm web uv run python src/backend/manage.py showmigrations --plan
```

Break the cycle with `SeparateDatabaseAndState` (split schema vs. data operations) or by reordering
`dependencies`. The research note (session `ses_036fff4b...`) records that the full-reset approach
normally avoids this; it only recurs if two apps gain cross-data migrations simultaneously.

### MPTT tree corruption

After running `load_catalog` (which reassigns `parent` FKs), the tree's `lft`/`rght` can be stale.
Rebuild from the command line:

```bash
docker compose run --rm web uv run python src/backend/manage.py shell -c \
  "from mptt.templatetags.mptt_tags import cache_tree_children; from apps.categories.models import Category; Category.objects.rebuild()"
```

### Role or database does not exist

```text
psycopg2.OperationalError: FATAL: role "postgres" does not exist
FATAL: database "postgres" does not exist
```

Check `.env.docker` — `POSTGRES_USER`, `POSTGRES_DB` must match the `db` service. In Docker the
`DATABASE_URL` is built from those vars; **do not** set `DATABASE_URL` manually in `.env.docker`
(see [Docker deployment](docker-deployment.md) → Database Configuration).

### After consolidation, new model changes don't generate a migration

You are seeing `makemigrations` report "No changes detected" right after a reset because the DB was
`--fake`-d but the models already match `0001_initial`. This is expected. Make a further model
change, then `make makemigrations`; the next consolidation will fold it back in at the next
threshold crossing.

## Related Documentation

- [Specification: Dev Migration Consolidation & Failure Fix](../../.ai/problems/06_dev-migration-consolidation_spec.md)
- [Docker deployment & operations](docker-deployment.md) — service topology, env vars, one-shot services
- [Architecture guidelines](../99-agent/architecture.md) — two-process/one-DB model, advisory lock allocation
- [Seed data workflow](seed-workflow.md) — how catalog/cities/users/ads are populated after migrate
- [Technical specification index](../01-spec/spec-index.md) — product-level context and PO decisions
