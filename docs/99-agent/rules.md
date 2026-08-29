---
id: rules
domain: agent
tags:
  - rules
related:
  - architecture
  - references
---

## Purpose

This file contains coding standards and rules for the Mko Bazuna project.

## Rules

### Quality & Maintenance

- **Type safety:** Type hints on all public functions. Use strict typing throughout.
- **Logging:** `logger = logging.getLogger(__name__)` — never `print()`.
- **Error handling:** Custom exceptions from `core/errors.py`. Never silently swallow errors.
- **Cleanup:** Clean up temp files with `try/finally` — never leave orphaned cache files.
- **English only:** English only in code, comments, logs.
- **Production code is king:** If tests conflict with architecture/business logic, fix or remove tests; never distort production code for tests.
- **Audit reports:** Write audit reports incrementally — append blocks of ≤100 lines per tool call.

### Coding Standards

- **Indentation:** 4-space indentation, never tabs.
- **Code review:** Read full function/class before rewriting.
- **Linting:** After edits run `uv run ruff check <path>` and `uv run basedpyright <path>`.

### Testing Conventions

- **Framework:** pytest-django. Test classes are plain `class TestX:` — do NOT use `django.test.TestCase` or `unittest.TestCase`.
- **Markers:** Pytest-django + pytest-asyncio. Custom markers are registered in `pyproject.toml` under `[tool.pytest.ini_options].markers`. Use `pytestmark` at module level. The fast gate (`make test`) excludes **only** the `seed` marker (`-m "not (seed)"` via `PYTEST_SKIP_MARKERS=seed`); all other markers run in both the fast gate and the full suite (`make test-all` — the `slow` marker is **not** excluded by the fast gate).

  | Marker | Scope / purpose |
  |---|---|
  | `unit` | Pure unit tests, no database — runs in the fast gate |
  | `integration` | Tests that exercise the DB / Django `Client` stack |
  | `seed` | Nightly-only; invokes `call_command('seed')` or `ImageGenerator`. Excluded from `make test`, included in `make test-all` |
  | `settings` | Import-time settings validation in a subprocess (e.g. `config/settings/tests/test_settings_secrets.py`) |
  | `concurrent` | Requires `transaction=True` (TRUNCATE per test) — bot tests mutating shared DB state |
  | `slow` | Individually slow tests (>5 s); **not** excluded by the fast gate |
  | `real_images` | Opts out of the no-op `ImageGenerator` stub in `apps/seed/tests/conftest.py` to use the real pipeline |
  | `xdist_group("name")` | Pins tests to a single xdist worker via `--dist loadgroup` (e.g. `"bot_concurrent"`) |
  | `django_db` (pytest-django) | DB-backed tests; use `transaction=True` when a test needs TRUNCATE isolation (bot tests) |
  | `asyncio` (pytest-asyncio, strict mode) | Async Telegram bot handlers |

  The `e2e` marker was removed — do not reference it.
- **Fixtures:** Root `conftest.py` at `src/backend/conftest.py` provides canonical `seller`, `user`, `category`, `city` fixtures. Do NOT redefine these locally — import or use directly. Bot tests under `src/telegram_bot/` have a separate conftest and cannot resolve backend fixtures.
- **Ad creation:** Use `from conftest import create_test_ad(user, category, city, *, title, description, status, price, source, **kwargs)` — it sets status-specific timestamps automatically. Add `status=AdStatus.PUBLISHED` explicitly if the test requires it.
- **Backdating `created_at`:** `create_test_ad` cannot backdate `created_at` (auto_now_add=True). Use: `ad = create_test_ad(...)` then `Ad.objects.filter(pk=ad.pk).update(created_at=...)` then `ad.refresh_from_db()`.
- **Assertions:** Use plain `assert` statements — do NOT use `self.assertEqual`, `self.assertTrue`, etc.
- **Local `uv run pytest` runs require `--create-db`** (no `--reuse-db` — stale-schema errors, ~527 on reuse). When using the Docker entrypoint via `make test`/`make test-all`, the entrypoint defaults to `--reuse-db` (safe: the test PG container persists via a named volume); use `make test-recreate` (`--no-reuse-db --create-db`) to force a fresh schema. CI may use `--reuse-db` (ephemeral service DB). Root conftest at `src/backend/conftest.py` provides canonical fixtures and `create_test_ad`.

## Test Infrastructure

### Test database lifecycle

- **Test DB:** PostgreSQL 18 in Docker (`mko-bazuna-test` project, host port 5433).
- **`--reuse-db`:** The Docker entrypoint (`docker/entrypoint-test.sh`) defaults to `--reuse-db`, caching the `test_mko_bazuna` schema between runs (~1.5 s saved per run). CI may also use `--reuse-db` since the service DB is ephemeral.
- **`test-clean-db`:** Pre-flight target that drops stale `test_mko_bazuna*` and `gw*` databases (from crashed xdist workers) before `test-recreate`. Run automatically as the first step of `make test-recreate`.
- **`test-recreate`:** Drops and rebuilds the test DB schema (`--no-reuse-db --create-db`). Use after migration changes or interrupted runs.
- **Local `uv run pytest`** always requires `--create-db` (no `--reuse-db`) — the test DB on `localhost:5432` is not reachable; tests must run in Docker.

### Parallel execution

- **`--dist loadgroup`** with `xdist_group("name")` pins tests that mutate shared DB state (e.g. bot tests with `transaction=True`) to the same worker.
- `-n auto` auto-detects CPU cores; bot tests use `transaction=True` (TRUNCATE isolation) for correctness.

## CI Workflow

The CI pipeline (`.github/workflows/ci.yml`, `name: CI`) runs on `ubuntu-latest` for pushes to `main`/`develop`:

| Job | Purpose | Key steps |
|---|---|---|
| `build` | Docker image + test env | Checkout → Buildx → Build image → Start PG → Run migrations → `compilemessages` → pytest with coverage |
| `lint` | Code linting | `uv sync` → `ruff check .` |
| `typecheck` | Type checking | `uv sync` → `basedpyright .` |
| `lint-templates` | Template linting | `uv sync` → `djlint templates/` |
| `i18n` | i18n completeness gate | `uv sync` → `compilemessages` → `pytest test_i18n_completeness.py test_i18n_pipeline.py -v` |

- The `test` job in CI runs `compilemessages` **before** pytest to ensure `.mo` files are present (T-01).
- Coverage report is uploaded as an artifact (`src/backend/coverage.xml`, 30-day retention).
- CI uses SQLite-backed PostgreSQL service (not Docker Compose) — migrations run via `migrate_locked.py`.

## i18n Pipeline

### Workflow

1. **Tag strings** in templates (`{% trans %}` / `{% blocktrans %}`) and Python (`gettext` / `gettext_lazy`)
2. **`make makemessages`** (`Makefile:167`) — extracts strings into `.po` files for `ru`, `bs`, `en` via `manage.py makemessages -l ru -l bs -l en --no-location`
3. **Edit `.po` files** — fill `msgstr` for `ru` and `bs` (non-empty); `en` may be empty (msgid is English)
4. **`make compilemessages`** (`Makefile:170`) — compiles `.po` → `.mo` with ignore patterns: `--ignore=.venv --ignore=.git --ignore=.kilo --ignore=__pycache__ --ignore='*.pyc'`
5. **Runtime:** `LanguagePreMiddleware` activates the locale; gettext reads `.mo` catalogs under `LOCALE_PATHS` (`src/backend/locale/`)

### Completeness gate

`apps/ads/tests/test_i18n_completeness.py` (4 tests, marked `@pytest.mark.unit`) enforces the multilingual Definition of Done:
- `test_no_hardcoded_visible_text` — scans public/seller-facing templates for visible text not wrapped in `{% trans %}`
- `test_extraction_completeness` — every `{% trans %}` / `{{ _("…") }}` msgid exists in all 3 `.po` files
- `test_no_empty_msgstr` — `ru` and `bs` have 0 empty `msgstr` for non-header entries
- `test_mo_compiled` — `.mo` files exist for all 3 locales

A dedicated `i18n` CI job runs `compilemessages` + these tests on every push.

### Key facts
- `.mo` files are **not** in version control (`.gitignore` line 55) — build-time artifacts
- DB-based i18n (`components/feature_tag.html` via `get_lookup_name`) is exempt from the completeness gate
- Scan scope excludes `admin/` staff templates, `analytics/moderation_dashboard.html`, and `components/feature_tag.html`