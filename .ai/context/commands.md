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
  -e PYTEST_OPTS="--create-db --tb=short -v src/backend/apps/ads/tests/test_ad_lifecycle.py" `
  test
```

> Do **not** use `--override-ini=addopts=` — it strips `--import-mode=importlib`
> from `pyproject.toml`, which is required for the `src` layout. The `addopts`
> are applied automatically; just append `-v` / a test path to `PYTEST_OPTS`.
>
> **Note on `--create-db`:** Always pass `--create-db`. It forces Django to check
> for pending schema changes and rebuilds the test schema from scratch. The
> `--reuse-db` flag is **not** used (it reuses stale schema and causes ~527
> errors after any migration change; see plan risk §7).

### Test fixtures (canonical source of truth)

The canonical fixtures live in `src/backend/conftest.py` and are the single
source of truth for backend tests:

- `seller` → `User(telegram_id=900000001, chat_id=900000001, password="x")`
- `user` → `User(telegram_id=900000002, chat_id=900000002, password="x")`
- `category` → `Category(name="Транспорт", slug="transport")`
- `city` → `City(country_code="ME", name="Тестград", region="Central", slug="test-grad")`
- `create_test_ad(user, category, city, *, title, description, status, price, source, **kwargs)`
  → creates an `Ad` row with the status-specific timestamp set automatically
  (satisfies the Ad check constraints). Pass `status=AdStatus.PUBLISHED` if
  your test needs a published ad (the default is `ON_MODERATION`).

Import the helper from any test file: `from conftest import create_test_ad`
(`pyproject.toml` sets `pythonpath = ["src", "src/backend"]`).

**Exception:** `src/telegram_bot/tests/conftest.py` redefines `seller` /
`category` / `city` / `user` because bot tests live outside the `src/backend/`
conftest-discovery hierarchy and `user` must be async. Do not move these
fixtures into backend tests — see the explanatory comment in that file.

---
