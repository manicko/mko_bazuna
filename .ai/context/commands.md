# Project Commands

## Environment

- **OS:** Windows
- **Package manager (Python):** uv
- **Test database:** PostgreSQL 18 in Docker (`mko-bazuna-test-db-*`, port 5433)
---

---

## Python (backend) — use `uv run` for all commands

| Task | Command |
|------|---------|
| Lint (ruff check) | `uv run ruff check <path>` |
| Format (ruff format) | `uv run ruff format --check <path>` |
| Type check (basedpyright) | `uv run basedpyright <path>` |
| Add dependency | `uv add <package>` |
| Add dev dependency | `uv add --dev <package>` |

## Tests (Docker only — never `uv run pytest` locally)

Tests require a PostgreSQL 18 test database in Docker (container
`mko-bazuna-test-db-*`, host port 5433). Running `uv run pytest` locally fails
with a database connection error because the DB is not reachable on `localhost:5432`.

### Check if the test DB container is running

```powershell
docker ps --filter "name=mko-bazuna-test-db-" --filter "status=running"
```

### Start the test DB if not running

```powershell
docker compose --project-name mko-bazuna-test -f docker-compose.yml -f docker-compose.test.yml up -d db
```

### Run all tests

```powershell
docker compose --project-name mko-bazuna-test -f docker-compose.yml -f docker-compose.test.yml run --rm test
```

### Run a specific test / file / class

```powershell
docker compose --project-name mko-bazuna-test -f docker-compose.yml -f docker-compose.test.yml run --rm `
  -e PYTEST_OPTS="--reuse-db --create-db --tb=short -v src/backend/apps/ads/tests/test_ad_lifecycle.py" `
  test
```

> Do **not** use `--override-ini=addopts=` — it strips `--import-mode=importlib`
> from `pyproject.toml`, which is required for the `src` layout. The `addopts`
> are applied automatically; just append `-v` / a test path to `PYTEST_OPTS`.

---
