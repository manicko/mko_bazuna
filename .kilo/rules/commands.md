# Project Commands

**Environment:** Windows 11 · `uv` (Python) · PostgreSQL 18 in Docker (`mko-bazuna-test`, port 5433)

## Python (PowerShell)

| Task | Command |
|---|---|
| Lint | `uv run ruff check <path>` |
| Auto-fix | `uv run ruff check --fix <path>` |
| Lint templates | `uv run djlint src/backend/templates/` |
| Format | `uv run ruff format <path>` |
| Typecheck | `uv run basedpyright <path>` |
| Add dep | `uv add <pkg>` / `uv add --dev <pkg>` |

> `ruff check --fix` handles import sorting (I001) and other fixable lint rules. `ruff format` only formats code (line wrapping, quotes) — it does **NOT** sort imports. The `make format` target runs `ruff check --fix src/` (not `ruff format`).

## Tests (Docker only — never `uv run pytest` locally)

Local `uv run pytest` fails — no DB on `localhost:5432`. All test commands below use the `mko-bazuna-test` Compose project.

**PowerShell alias (copy once):**
```powershell
$dc='docker compose --project-name mko-bazuna-test -f docker-compose.yml -f docker-compose.test.yml'
```

| Task | Command | When to use |
|---|---|---|
| Start DB | ` $dc up -d db` | Before running tests |
| Fast gate | `$dc run --rm --env PYTEST_SKIP_MARKERS=seed test` | Default dev iteration (skips seed suite) |
| Full suite | `$dc run --rm test` | Changes touch seeding/images (~35 min) |
| Fresh schema | `$dc run --rm --env PYTEST_OPTS="--create-db --tb=short -n auto --maxprocesses=4 --dist loadgroup" test` | After migration changes or interrupted run |
| Stop DB | `$dc down` | Done testing (preserves data volume) |

**Run a single test** (override all pytest flags via `PYTEST_OPTS`; never `--override-ini=addopts=` — strips `--import-mode=importlib`):
```powershell
$dc run --rm -e PYTEST_OPTS="-k test_name" test
```

**Test entrypoint flow** (Dockerfile `ENTRYPOINT` = `entrypoint.sh`, `command` = `entrypoint-test.sh`): `compilemessages` (.po→.mo), `uv sync --group dev`, `migrate --run-syncdb`, `load_exchange_rates`, `setup_search_triggers`, then pytest. Default flags: `--reuse-db --tb=short --durations=10 -n auto --maxprocesses=4 --dist loadgroup`.

## Test fixtures

Source of truth: `src/backend/conftest.py`. Import `from conftest import create_test_ad` (pyproject.toml: `pythonpath = ["src", "src/backend"]`). Key fixtures: `seller` (900000001), `user` (900000002), `category`, `city`. `create_test_ad(..., status=AdStatus.PUBLISHED)` sets status timestamps. **Exception:** `src/telegram_bot/tests/conftest.py` redefines these (async `user`) — bot tests live outside the `src/backend/` conftest hierarchy.

## i18n

Wrap templates in `{% trans %}` / `{% blocktrans %}` and Python in `gettext` / `gettext_lazy` (project rule #16). Extract: `uv run python src/backend/manage.py makemessages -l ru -l bs -l en --no-location`; compile: `uv run python src/backend/manage.py compilemessages --locale ru --locale bs --locale en`. `.mo` files are gitignored — auto-compiled by the test entrypoint (`entrypoint.sh` `compile_messages`); production compiles at image build time and re-compiles at container startup. Verify with `test_i18n_completeness.py`. DB-based i18n (`feature_tag.html` via `get_lookup_name`) is exempt.
