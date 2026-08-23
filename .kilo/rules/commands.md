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
| Lint templates (djlint) | `uv run djlint src/backend/templates/` |
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

### Run all tests (full suite — includes nightly `seed`, ~35 min)

This runs **everything** including the nightly `seed` suite (~35 min).
For the fast gate that skips seed tests (~300s), use `make test` (see
*Fast gate vs full suite vs fresh schema* below).

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
> **Note on `--reuse-db` vs `--create-db`:** The Docker test entrypoint
> (`docker/entrypoint-test.sh`) defaults to `--reuse-db` — the test PG container
> persists across runs via a named volume, so schema reuse is safe inside Docker.
> `make test` / `make test-all` rely on this default. To force a fresh schema
> (e.g. after migration changes or an interrupted SIGKILL'd run), use `make
> test-recreate` (`--no-reuse-db --create-db`) or override `PYTEST_OPTS`.
> **Do not** pass `--reuse-db` when running `uv run pytest` directly against a
> local persistent DB — it reuses stale schema and causes ~527 errors; use
> `--create-db` locally instead. CI may use `--reuse-db` (ephemeral service DB per run).

### Fast gate vs full suite vs fresh schema

| Command | What it does | When to use |
|---|---|---|
| `make test` | Fast gate: skips the nightly `seed` suite (~17 min) via `PYTEST_SKIP_MARKERS=seed`. Runs in ~300s. Auto-starts the test DB. | Default for dev iteration |
| `make test-all` | Complete suite **including** the nightly `seed` tests (~35 min). | When changes touch seeding or image generation |
| `make test-recreate` | Fast gate + fresh schema: overrides `PYTEST_OPTS="--no-reuse-db --create-db"` to drop the cached test DB. | After migration changes or interrupted run |

**How the fast gate works:** `docker/entrypoint-test.sh` checks `PYTEST_SKIP_MARKERS` and appends `-m "not (seed)"` to the pytest invocation:

```bash
PYTEST_MARK_ARGS=()
if [ -n "${PYTEST_SKIP_MARKERS:-}" ]; then
    PYTEST_MARK_ARGS+=(-m "not (${PYTEST_SKIP_MARKERS})")
fi
uv run pytest ${PYTEST_OPTS:- --reuse-db --tb=short --durations=10} "${PYTEST_MARK_ARGS[@]}"
```

`make test` passes `--env PYTEST_SKIP_MARKERS=seed` to the Compose `test` service;
`make test-all` omits it so seed tests run.

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

## Internationalization (i18n) Development Checklist

Translation is part of the Definition of Done (see `.ai/problems/08_multilingual-dev_spec.md`).
Languages: `ru` (primary), `en`, `bs` (secondary). The pipeline infrastructure
(middleware, `compilemessages` in Dockerfile/entrypoints, Makefile targets) is
already operational.

### Before committing a feature with user-visible strings

1. **Templates** — Every user-visible string is wrapped in `{% trans "..." %}` or
   `{% blocktrans %}`. If the template doesn't already have `{% load i18n %}`,
   add it at the top. Exception: `feature_tag.html` uses database-based i18n
   (`get_lookup_name`); `value`/`name` attributes and brand names are not
   translatable.

2. **Python** — User-facing string literals use `gettext_lazy` (class-level /
   model) or `gettext` (runtime context processors, views). Never hardcode
   visible text in Python.

3. **Enums** — `StrEnum` values used in `.choices()` that render to the UI must
   have their labels wrapped in `gettext_lazy` (e.g., `TimeRange` at
   `apps/core/enums.py:125`).

### After wrapping strings

4. **Extract** — Run `make makemessages` to regenerate `.po` files:

   ```powershell
   uv run python -m django makemessages -l ru -l en -l bs --settings=config.settings.dev
   ```

5. **Translate** — Populate `msgstr` for `ru` and `bs` (main + secondary
   languages). `en` msgstr may be empty (msgid is already English). Use
   `translation_service.py` (deep-translator) for bootstrapping, then
   human-review the `ru` entries.

6. **Compile** — Run `make compilemessages` to generate `.mo` files:

   ```powershell
   uv run python -m django compilemessages --settings=config.settings.dev
   ```

7. **Verify** — New tests in `test_i18n_completeness.py` must pass:

   ```powershell
   docker compose --project-name mko-bazuna-test -f docker-compose.yml -f docker-compose.test.yml run --rm `
     -e PYTEST_OPTS="src/backend/apps/ads/tests/test_i18n_completeness.py" `
     test
   ```

8. **Existing tests** — If you change a string that existing tests assert on,
   add explicit `translation.activate("ru")` in the test and assert on the
   rendered output.

