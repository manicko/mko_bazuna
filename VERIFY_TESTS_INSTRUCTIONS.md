# How to Verify Tests Run After Changes

This guide walks through verifying that all test-infra fixes work end-to-end using Docker in **dev mode** (bind mounts).

## Prerequisites

- Docker Desktop running on Windows
- Windows PowerShell 5.1+ or Windows Terminal
- Project files at `C:\py_dev\mko_bazuna` (workspace root)

---

## Step 1 — Confirm No Stale Containers or Volumes

```pwsh
docker compose ls
docker ps -a
docker volume ls | Where-Object { $_ -like "*mko_bazuna*" }
```

If stale containers exist (e.g. from dev compose), stop and remove them:

```pwsh
docker compose --env-file .env.docker -f docker-compose.yml -f docker-compose.dev.override.yml down -v
```

The `-v` flag also removes anonymous volumes (including the ephemeral test DB volume if it was created).

---

## Step 2 — Rebuild the Docker Image

The Dockerfile builds the venv from `uv.lock` (production deps only via `--no-dev`). The test entrypoint (`entrypoint-test.sh`) re-syncs with `UV_DEFAULT_GROUPS=dev` to add pytest/ruff. Always rebuild after changes to `pyproject.toml`, `uv.lock`, or source code:

```pwsh
docker compose --env-file .env.docker -f docker-compose.yml -f docker-compose.dev.override.yml build db
```

> If the image is unchanged and you only changed Python source, you can skip the rebuild. For `pyproject.toml`/`uv.lock`/`Dockerfile` changes, rebuild.

---

## Step 3 — Start Dev Containers (DB Only)

Start just the database in dev mode (web/bot will start too, but we'll focus on the test flow):

```pwsh
docker compose --env-file .env.docker -f docker-compose.yml -f docker-compose.dev.override.yml up -d db
```

Wait for PostgreSQL to be healthy:

```pwsh
docker compose --env-file .env.docker -f docker-compose.yml -f docker-compose.dev.override.yml ps db
```

Look for `healthy` in the `State` column. The healthcheck tests `pg_isready`.

---

## Step 4 — Run Migrations (One-Shot Container)

Run migrations in a throwaway container that uses the dev override (bind-mounts source code so the latest migrations apply):

```pwsh
docker compose --env-file .env.docker -f docker-compose.yml -f docker-compose.dev.override.yml run --rm migrate
```

Expected output: `Migrations complete` (or no output if already applied). The `migrate_locked.py` uses an advisory lock (ID 100) so this is safe to re-run.

---

## Step 5 — Load Categories (One-Shot Container)

Seed the category catalog into the DB:

```pwsh
docker compose --env-file .env.docker -f docker-compose.yml -f docker-compose.dev.override.yml run --rm load_catalog
```

This runs `entrypoint-catalog.sh` which calls `load_catalog.py`. If the `CATALOG_PATH` fix (`parents[2]`) is working, output will show category counts.

---

## Step 6 — Run the Test Suite

Run a one-shot test container using the **test** compose file (ephemeral PostgreSQL, test settings). This is the most reliable way — it doesn't need `.env.docker` and uses isolated test DB:

```pwsh
docker compose --env-file .env.docker -f docker-compose.yml -f docker-compose.test.yml --profile test up --build test
```

This will:
1. Build the image (if `--build` is passed)
2. Start the ephemeral `db` service (postgres:18-alpine, no persistent volume)
3. Run migrations via `entrypoint-test.sh` (uses `migrate_locked.py`)
4. Run `pytest --tb=short`
5. Exit with the pytest exit code (0 = all pass, non-zero = failures)

**Alternative** (if you just want to run tests against the already-running dev DB):

```pwsh
docker compose --env-file .env.docker -f docker-compose.yml -f docker-compose.dev.override.yml run --rm --no-deps test
```

> Note: The `test` service is defined in `docker-compose.test.yml`. Using the `--profile test` flag with `up` is the primary method because it brings up the ephemeral DB dependency automatically.

---

## Step 7 — Run Lint and Type Check

Lint all changed Python files:

```pwsh
docker compose --env-file .env.docker -f docker-compose.yml -f docker-compose.dev.override.yml run --rm --no-deps test ruff check src/backend/apps/seed/tests/test_seed.py src/backend/apps/categories/management/commands/load_catalog.py src/backend/apps/seed/services/seed_service.py src/backend/apps/core/utils/migrate_locked.py
```

Type check all changed Python files:

```pwsh
docker compose --env-file .env.docker -f docker-compose.yml -f docker-compose.dev.override.yml run --rm --no-deps test uv run basedpyright src/backend/apps/seed/tests/test_seed.py src/backend/apps/categories/management/commands/load_catalog.py src/backend/apps/seed/services/seed_service.py src/backend/apps/core/utils/migrate_locked.py
```

> The `test` service has `UV_DEFAULT_GROUPS=dev` set in its entrypoint, so ruff/basedpyright/pytest are available. The `--no-deps` flag skips waiting for the DB healthcheck. If you get `--no-deps` issues, drop it and let the DB start first.

---

## Step 8 — Verify Specific B-Fixes

### B3 — CATALOG_PATH resolves correctly

In the test container, verify the path resolution:

```pwsh
docker compose --env-file .env.docker -f docker-compose.yml -f docker-compose.test.yml run --rm --no-deps test python -c "from pathlib import Path; p = Path('/app/src/backend/apps/seed/tests/test_seed.py'); print(p.resolve().parents[2] / 'categories' / 'catalog' / 'categories.yaml'); print((p.resolve().parents[2] / 'categories' / 'catalog' / 'categories.yaml').exists())"
```

Expected: prints the full path and `True`.

### B1 — `UV_DEFAULT_GROUPS=dev` enables test deps

In the test container, verify pytest is available:

```pwsh
docker compose --env-file .env.docker -f docker-compose.yml -f docker-compose.test.yml run --rm --no-deps test python -c "import pytest; print(pytest.__version__)"
```

Expected: prints a version number (e.g. `8.3.4`).

### B2 — `uv.lock` is committed and not ignored

```pwsh
git status --short uv.lock
git check-ignore -q uv.lock; echo "exit: $?"
```

Expected: `git status` shows nothing for `uv.lock` (it's tracked), and `exit: 1` (not ignored).

### B4 — `migrate_locked.py` works without CWD

The `migrate_locked.py` now uses `Path(__file__).resolve().parents[3]` to find `manage.py`. Run migrations from any directory:

```pwsh
docker compose --env-file .env.docker -f docker-compose.yml -f docker-compose.dev.override.yml run --rm --no-deps --workdir /tmp migrate python -c "from apps.core.utils.migrate_locked import main; import sys; print('CATALOG_PATH parent:', main.__module__); sys.exit(main())"
```

Expected: migrations run regardless of CWD.

---

## Step 9 — Cleanup

After verifying, stop and clean up ephemeral containers:

```pwsh
docker compose --env-file .env.docker -f docker-compose.yml -f docker-compose.dev.override.yml down -v
docker compose --env-file .env.docker -f docker-compose.yml -f docker-compose.test.yml down -v
```

---

## Troubleshooting

| Symptom | Likely Cause | Fix |
|---|---|---|
| `ERROR: .env file not found` | Test service doesn't set `SKIP_ENV_CHECK` but compose vars are provided | Add `SKIP_ENV_CHECK=1` env var to test service, or ensure `.env.docker` is mounted |
| `uv: command not found` | Image wasn't rebuilt after Dockerfile changes | Run `docker compose build` |
| `uv sync --frozen` fails with lockfile out of date | `uv.lock` doesn't match `pyproject.toml` | Run `uv lock --upgrade` locally then commit |
| pytest not found | `UV_DEFAULT_GROUPS=dev` not set | Check `entrypoint-test.sh` has `export UV_DEFAULT_GROUPS=dev` |
| `categories.yaml not found` | Wrong `parents[n]` index | Verify with Step 8 path check |