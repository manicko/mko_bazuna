# Project Commands

**Environment:** Windows · `uv` (Python) · PostgreSQL 18 in Docker (`mko-bazuna-test-db-*`, port 5433)

## Python

| Task | Command |
|---|---|
| Lint | `uv run ruff check <path>` |
| Lint templates | `uv run djlint src/backend/templates/` |
| Format | `uv run ruff format --check <path>` |
| Typecheck | `uv run basedpyright <path>` |
| Add dep | `uv add <pkg>` / `uv add --dev <pkg>` |

## Tests (Docker only — never `uv run pytest` locally)

Tests need PostgreSQL 18 in Docker on port 5433; local `uv run pytest` fails (DB unreachable on `localhost:5432`).

**Start test DB:**
```powershell
docker compose --project-name mko-bazuna-test -f docker-compose.yml -f docker-compose.test.yml up -d db
```

**Run a specific test:**
```powershell
docker compose --project-name mko-bazuna-test -f docker-compose.yml -f docker-compose.test.yml run --rm `
  -e PYTEST_OPTS="<opts>" test
```

> Never pass `--override-ini=addopts=` (it strips `--import-mode=importlib`). Append opts directly to `PYTEST_OPTS`. Docker entrypoint defaults to `--reuse-db` (safe via named volume); use `--create-db` locally or after migrations. **Never** use `--reuse-db` against a local persistent DB — stale schema causes ~527 errors.

| Command | What it does | When to use |
|---|---|---|
| `make test` | Fast gate: skips `seed` tests (~300s) | Default dev iteration |
| `make test-all` | Full suite incl. `seed` (~35 min) | Changes touch seeding/images |
| `make test-recreate` | Fresh schema (`--create-db`) | After migration changes or interrupted run |

> **Fast gate:** `make test` sets `PYTEST_SKIP_MARKERS=seed`; the Docker entrypoint (`docker/entrypoint-test.sh`) turns this into `-m "not (seed)"`.

## Test fixtures

Canonical source of truth: `src/backend/conftest.py`. Import via `from conftest import create_test_ad` (`pyproject.toml` sets `pythonpath = ["src", "src/backend"]`). Key fixtures: `seller` (900000001), `user` (900000002), `category`, `city`. `create_test_ad(..., status=AdStatus.PUBLISHED)` sets status-specific timestamps automatically.

**Exception:** `src/telegram_bot/tests/conftest.py` redefines these (async `user`) because bot tests live outside the `src/backend/` conftest-discovery hierarchy — keep them separate.

## i18n

See **project rule #16** (Definition of Done): wrap template strings in `{% trans %}` / `{% blocktrans %}` and Python strings in `gettext` / `gettext_lazy`. Run `make makemessages` then `make compilemessages` before committing. Languages: `ru` (primary), `en`, `bs`. Verify with `test_i18n_completeness.py` (run as a specific test, see above). Database-based i18n (`feature_tag.html` via `get_lookup_name`) is exempt.
