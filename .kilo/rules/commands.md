# Project Commands

**Env:** Windows 11 · `uv` (Python) · PostgreSQL 18 in Docker (`mko-bazuna-test` project, host port 5433)

`make` (WSL/macOS/Linux) and `.\Makefile.ps1 <target>` (Win PowerShell) are the canonical entry points — each exports the correct `COMPOSE_PROJECT_NAME` (`mko-bazuna-dev` or `mko-bazuna-test`). The raw `docker compose` forms below are for one-off overrides.

## Quick start

| Task | Command |
|---|---|
| Dev up (web :8000 + test DB :5433) | `make up` |
| Fast test gate (skips nightly `seed` tests) | `make test` |
| Full suite (incl. nightly `seed`) | `make test-all` |
| Fresh test schema (after migration changes) | `make test-recreate` |

## Python (local, PowerShell)

| Task | Command |
|---|---|
| Lint | `uv run ruff check <path>` |
| Auto-fix (incl. import sorting, I001) | `uv run ruff check --fix <path>` |
| Lint templates | `uv run djlint src/backend/templates/` |
| Typecheck | `uv run basedpyright <path>` |
| Add dep | `uv add <pkg>` / `uv add --dev <pkg>` |

> `ruff check --fix` handles import sorting (I001). `ruff format` only reformats (line wraps, quotes) and does **NOT** sort imports — `make format` runs `ruff check --fix src/`, not `ruff format`.

## Tests (Docker only — never `uv run pytest` locally)

Local `uv run pytest` fails: there is no DB on `localhost:5432`. Runs go through the `test` service of the `mko-bazuna-test` Compose project (PostgreSQL on host port 5433).

**Alias (copy once):**
```powershell
$dc = 'docker compose --project-name mko-bazuna-test --env-file .env.test -f docker-compose.yml -f docker-compose.test.yml'
```
`--env-file .env.test` is **required** — compose interpolates `${POSTGRES_*?}` from it; omitting it aborts with "must be set".

| Task | Command | When |
|---|---|---|
| Start DB | `$dc up -d db` | Once per session (persistent volume → `--reuse-db` caching) |
| Fast gate | `$dc run --rm --env PYTEST_SKIP_MARKERS=seed test` | Default dev iteration (skips `seed`) |
| Full suite | `$dc run --rm test` | Changes touch seeding/images |
| Fresh schema | `$dc run --rm --env PYTEST_OPTS="--create-db --tb=short -n auto --maxprocesses=4 --dist loadgroup" test` | After migration changes or interrupted run |
| Stop | `$dc down` | Done (preserves named volume) |

**Run a single test / file** — pass pytest args via `PYTEST_OPTS`:
```powershell
$dc run --rm -e PYTEST_OPTS="-k test_name" test
$dc run --rm -e PYTEST_OPTS="src/backend/apps/ads/tests/test_edit.py src/backend/apps/ads/tests/test_submission.py --tb=short" test
```
Two caveats (verified): the value is **unquoted** in `docker/entrypoint-test.sh`, so each token is word-split on spaces — `-k test_name` and bare file paths work, but quoted multi-token values (e.g. `-k "a b"`) do **not**. Setting `PYTEST_OPTS` also **replaces** the defaults (`--reuse-db -n auto --maxprocesses=4 --dist loadgroup`), so targeted runs lose xdist parallelism and DB reuse. Never use `--override-ini=addopts=` — it strips `--import-mode=importlib` (set in `pyproject.toml`).

**Entry-point flow** (`docker/entrypoint.sh` = image `ENTRYPOINT`; `docker/entrypoint-test.sh` = `test` service `command`):
1. `entrypoint.sh` — wait for DB/Redis, `compilemessages` (.po→.mo), `check --deploy` (non-fatal).
2. `entrypoint-test.sh` — `uv sync --frozen --no-install-project --group dev`, `bootstrap_reference_data` (`migrate --run-syncdb` + `setup_search_triggers` + `load_exchange_rates` under advisory lock 100), then `pytest` with defaults `--reuse-db --tb=short --durations=10 -n auto --maxprocesses=4 --dist loadgroup` (overridable via `PYTEST_OPTS`).

**Test fixtures** — source of truth: `src/backend/conftest.py` (`pyproject.toml` sets `pythonpath = ["src", "src/backend"]`, `testpaths = ["src/backend", "src/telegram_bot"]`). Canonical fixtures: `seller` (900000001), `user` (900000002), `category`, `city`. Use `create_test_ad(user, category, city, *, status=AdStatus.PUBLISHED, **kwargs)` (sets status timestamps). `src/telegram_bot/tests/conftest.py` redefines these (async `user`) — bot tests cannot import the backend conftest.

## i18n

Wrap user-visible strings in `{% trans %}` / `{% blocktrans %}` (templates) or `gettext` / `gettext_lazy` (Python). `msgstr` must be non-empty for `ru` and `bs`; `en` may be empty (msgid is English). `.mo` files are gitignored (`*.mo`) and are compiled **automatically** at image build, at container start (`entrypoint.sh` → `compile_messages`), and in the CI `i18n` job — so manual `compilemessages` is rarely needed.

**`make makemessages` does NOT work on Win 11 + Docker Desktop.** Verified causes:
- The dev `web` service `depends_on` `load_catalog`, `redis`, and `seed` (i.e. the whole chain `db→redis→migrate→load_cities→load_catalog→seed→web`) is booted to serve a static string-extraction scan.
- `uv run` inside a one-shot `run` container triggers a venv sync that fails with `Read-only file system` on `/opt/venv`.

Use this lightweight form instead — `--no-deps` skips the dependency chain, `--entrypoint ""` skips the entrypoint DB-wait/compile, and the venv `python` is called directly (no `uv run` sync):

**Alias (copy once):**
```powershell
$dev = 'docker compose --env-file .env.dev -f docker-compose.yml -f docker-compose.dev.override.yml --project-name mko-bazuna-dev'
```

Extract (same flags as `make makemessages`):
```powershell
$dev run --rm --no-deps --entrypoint "" web python src/backend/manage.py makemessages -l ru -l bs -l en --no-location
```

Compile (`.mo` gitignored — only needed manually after editing `.po`):
```powershell
$dev run --rm --no-deps --entrypoint "" web python src/backend/manage.py compilemessages --ignore=.venv --ignore=.git --ignore=__pycache__ --ignore=*.pyc --ignore=node_modules --locale ru --locale bs --locale en
```

Requires `.env.dev` (copy `.env.dev.example`). Verified in-image: `xgettext` (GNU gettext 0.23.1), `msgfmt`, and `makemessages`/`compilemessages --help` run with exit 0 and **no database**. DB-based i18n (`feature_tag.html` → `get_lookup_name`) is exempt from the completeness gate; after changing strings, `make test` (or `test_i18n_completeness.py`) must pass.
