# Test Suite Audit — Step 1: Current State

**Date:** 2026-08-26  
**Method:** Static analysis only (no tests executed)  
**Scope:** `src/backend/` (Django tests) + `src/telegram_bot/tests/` (bot tests)  

---

## 1. Summary

| Metric | Value |
|---|---|
| Total test files | 89 (88 under `apps/` + `telegram_bot/tests/`; 1 under `config/settings/tests/`) |
| Total test functions | 1091 (1009 backend + 80 bot + 2 config/settings) |
| Test functions counted (apps + bot) | 1089 (measured via `def test_` grep) |
| Conftest files | 3 (`src/backend/conftest.py`, `src/telegram_bot/tests/conftest.py`, `src/backend/apps/seed/tests/conftest.py`) |
| Root conftest.py | None (no project-root `conftest.py`) |
| pytest.ini / setup.cfg / tox.ini | None — config lives in `pyproject.toml` `[tool.pytest.ini_options]` (p.155–172) |
| Registered custom markers | 8 |
| Files with module-level `pytestmark` | 84 of 89 |
| Per-test `@pytest.mark.*` decorator uses (custom markers only) | 13 |
| Dev test dependencies | 9 (ruff, basedpyright, pytest, pytest-asyncio, pytest-cov, pytest-django, pytest-xdist, coverage, djlint) |

---

## 2. Test Configuration (`pyproject.toml`)

**Source:** `pyproject.toml` lines 155–172

```toml
[tool.pytest.ini_options]
minversion = "8.4"
asyncio_mode = "strict"
python_files = ["tests.py", "test_*.py"]
pythonpath = ["src", "src/backend"]
addopts = ["--import-mode=importlib", "-ra", "-q"]
console_output_style = "classic"
```

| Key | Value | Notes |
|---|---|---|
| `addopts` | `--import-mode=importlib -ra -q` | **No `--cov`** — coverage is injected via CI/entrypoint `--cov` flag, not in addopts. |
| `asyncio_mode` | `strict` | `await` tests require `@pytest.mark.asyncio` or `@pytest_asyncio.fixture` |
| `python_files` | `["tests.py", "test_*.py"]` | Standard Django test discovery patterns |
| `pythonpath` | `["src", "src/backend"]` | Enables `from conftest import create_test_ad` (p.159 comment) |
| `minversion` | `8.4` | Minimum pytest version |
| `console_output_style` | `classic` | Non-default output format |

### Registered markers (8)

| Marker | Description (from pyproject.toml) |
|---|---|
| `unit` | Tests requiring no database (pure unit tests) |
| `integration` | Tests requiring a database (use `-m integration` to run) |
| `seed` | Tests invoking `call_command('seed')` or `ImageGenerator` (nightly only) |
| `settings` | Import-time settings validation using subprocess isolation |
| `concurrent` | Tests requiring `transaction=True` (TRUNCATE per test) |
| `slow` | Tests taking >5 seconds individually (use `-m 'not slow'` to skip) |
| `real_images` | Keep the real seed image pipeline for tests asserting on it |
| `xdist_group` | Tests pinned to a single xdist worker |

### Coverage configuration (`pyproject.toml` lines 175–183)

| Key | Value |
|---|---|
| `[tool.coverage.run].branch` | `true` |
| `[tool.coverage.run].source` | `["src/backend", "src/telegram_bot"]` |
| `[tool.coverage.run].omit` | `*/migrations/*`, `*/tests/*`, `*/test_*.py`, `*/conftest.py`, `*/manage.py`, `*/wsgi.py`, `*/asgi.py` |
| `[tool.coverage.report].fail_under` | **80** |
| `[tool.coverage.report].show_missing` | `true` |
| `[tool.coverage.report].skip_empty` | `true` |

**Coverage is NOT in `addopts`.** The `--cov` flag is passed explicitly at the command line in CI (ci.yml:l87) and is **not** part of the default `addopts`. Local `make test` / entrypoint runs do **not** pass `--cov`.

---

## 3. Test Structure & Inventory

### Test file count by app

| App (path) | Test files | Test functions |
|---|---|---|
| `apps/ads/` | 22 | 211 |
| `apps/search/` | 7 | 129 |
| `apps/core/` | 15 | 154 |
| `apps/moderation/` | 7 | 127 |
| `apps/seed/` | 2 | 119 |
| `apps/users/` | 7 | 102 |
| `apps/analytics/` | 6 | 90 |
| `apps/trust/` | 3 | 34 |
| `apps/media/` | 3 | 20 |
| `apps/cabinet/` | 2 | 9 |
| `apps/categories/` | 1 | 7 |
| `apps/currencies/` | 2 | 7 |
| `config/settings/tests/` | 1 | 2 |
| **Total backend** | **78** | **1009** |
| `telegram_bot/tests/` | 10 | 80 |
| **Grand total** | **89** | **1091** |

> Test-function counts measured via `def test_` occurrences per file (PowerShell `Select-String -Pattern "def test_"`). Backend count (1009) excludes `config/settings/tests/test_settings_secrets.py` (2 funcs, 1091 total).

### Largest test files

| File | Test funcs | Lines | Notes |
|---|---|---|---|
| `src/backend/apps/seed/tests/test_seed.py` | 60 | 1586 | Contains 5 `@pytest.mark.seed` class-level decorators + 1 method-level seed + 1 real_images |
| `src/backend/apps/seed/tests/test_download_seed_photos.py` | 59 | 956 | Pure unit tests (no DB); `pytestmark = [pytest.mark.unit]` (l.45) |
| `src/backend/apps/search/tests/test_autocomplete.py` | 42 | — | `pytestmark = [django_db, slow, integration]` (l.33) |
| `src/backend/apps/analytics/tests/test_alert_query.py` | 32 | — | `pytestmark = [django_db, slow, integration]` (l.30) |
| `src/backend/apps/core/tests/test_contact.py` | 28 | — | 4× `@pytest.mark.parametrize`; `pytestmark = [django_db, slow, integration]` (l.21) |
| `src/telegram_bot/tests/test_unsubscribe.py` | 7 | 166 | 7× `@pytest.mark.asyncio`; `pytestmark = [django_db(transaction=True), slow, integration, concurrent]` + `xdist_group("bot_concurrent")` |

### Test files without `pytestmark` (4 of 89)

| File | Lines | Approach |
|---|---|---|
| `apps/ads/tests/test_price_format.py` | 49 | 6 plain `def test_` functions; pure unit, no markers |
| `apps/core/tests/test_sanitize.py` | 38 | 5 methods in `TestMaskTelegramId`; pure unit, no markers |
| `apps/media/tests/test_thumbnails.py` | 182 | 9 methods in `TestThumbnailService`; pure unit, no markers |
| `apps/moderation/tests/test_auto_moderation.py` | 260 | Mixed: 19 pure unit test methods (no markers) + 4 DB-backed methods in `TestCheckFunction` class decorated with `@pytest.mark.django_db`, `@pytest.mark.slow`, `@pytest.mark.integration` (l.179–181) |

These 4 files rely on pytest-django's default `db` fixture or no DB at all, but lack even the `unit` marker that all nearby test files use. The bot suite's `test_auto_moderation.py` is notable for using **class-level** `@pytest.mark.*` decorators instead of `pytestmark`, the only file in the suite to do so.

---

## 4. Conftest Files & Fixtures

### 4.1 Root conftest — `src/backend/conftest.py` (184 lines)

Provides 5 shared fixtures + 2 helper functions:

| Symbol | Type | Scope | DB ID / Key | Notes |
|---|---|---|---|---|
| `seller` | fixture | function | `telegram_id=900000001` | `User.objects.create(...)` |
| `user` | fixture | function | `telegram_id=900000002` | Alias of seller for modules using `user` |
| `category` | fixture | function | slug `transport` | `Category.objects.create(name="Транспорт", ...)` |
| `city` | fixture | function | slug `test-grad` | `City.objects.create(country_code="ME", ...)` |
| `create_test_ad` | helper (not fixture) | n/a | n/a | Module-level function; sets status-specific timestamps to satisfy `CheckConstraint` rules (e.g. `ck_ads_published_at_if_published`). Imported via `from conftest import create_test_ad` (38 import sites). |
| `create_test_ads_bulk` | helper | n/a | n/a | Uses `bulk_create`; companion to `create_test_ad` for bulk tests. Imported in 2 files. |

**Usage pattern:** 38 test files import `create_test_ad` (or `create_test_ads_bulk`) from `conftest` — the root conftest is on `pythonpath` (`["src", "src/backend"]`, p.159).

### 4.2 Bot conftest — `src/telegram_bot/tests/conftest.py` (233 lines)

**Redefines** (not reuses) `seller`, `category`, `city`, and `user` fixtures from the root conftest because bot tests (`src/telegram_bot/tests/`) sit in a directory ancestry chain that does **not** pass through `src/backend/`, so the root conftest is not discoverable (documented at l.66–84):

| Symbol | Type | Scope | DB ID / Key | Notes |
|---|---|---|---|---|
| `bot` | fixture | **session** | — | `Bot(token=settings.BOT_TOKEN)` — placeholder token, never calls Telegram API |
| `dp` | fixture | function | — | Real `Dispatcher` with `MemoryStorage`, registers `AccountStateMiddleware` + all 3 routers (`login_router`, `ad_create_router`, `alerts_router`) |
| `user` | **pytest_asyncio** fixture | function | `telegram_id=900000100` | Async; uses `sync_to_async(User.objects.get_or_create)`. Different ID from root (900000001/002) to avoid collisions |
| `seller` | fixture | function | `telegram_id=900000100` | Sync; matches bot convention |
| `category` | fixture | function | slug `test-category` | Leaf category |
| `city` | fixture | function | slug `test-city` | |
| `login_token_factory` | fixture | function | — | Factory returning async callable for `LoginToken` creation |
| `_reap_worker_connections` | **autouse** fixture | function | — | Closes `sync_to_async` worker-thread DB connections after each test |
| `_reap_stale_backends_session` | **autouse** fixture | **session** | — | Closes stale DB connections at session start/end |

**Thread-connection cleanup (l.161–233):** Bot handlers run inside `@sync_to_async` (asgiref 3.12, `thread_sensitive=True`). The worker thread gets its own Django `ConnectionHandler` (thread-local when `thread_critical=False`). With `django_db(transaction=True)`, the next test's `TRUNCATE ... CASCADE` can deadlock against locks held by the leaked worker backend. The conftest registers every connection via `connection_created` signal and closes them all after each test (using `BaseDatabaseWrapper.close()`, not `pg_terminate_backend`).

### 4.3 Seed conftest — `src/backend/apps/seed/tests/conftest.py` (49 lines)

| Symbol | Type | Scope | Notes |
|---|---|---|---|
| `_no_op_image_generator` | **autouse** fixture | function | Patches `apps.seed.services.seed_service.ImageGenerator` with a no-op stub to skip the real image pipeline (~1004-photo manifest + SHA-256 backfill). Skipped for `real_images`-marked tests (l.43–45). |

---

## 5. Marker Usage

### 5.1 Module-level `pytestmark` — summary counts

| Marker | Module-level files | Per-test decorators | Files with decorators |
|---|---|---|---|
| `unit` | 22 (18 `unit`-only + 1 `asyncio,unit` + 1 `unit,settings` + 2 bot) | 0 | — |
| `integration` | 65 (57 backend + 8 bot) | 4 | `test_trust_calculator.py` (3), `test_auto_moderation.py` (1) |
| `seed` | 0 | 7 | `test_seed.py` (lines 295, 458, 900, 983, 1351, 1392, 1459) |
| `settings` | 1 (`test_settings_secrets.py:23`) | 0 | — |
| `concurrent` | 7 (bot only) | 0 | — |
| `slow` | 55 (47 backend + 8 bot) | 1 | `test_auto_moderation.py:180` |
| `real_images` | 0 | 1 | `test_seed.py:915` |
| `xdist_group` | 7 (bot only, via `pytestmark.append`) | 0 | — |

**Total module-level `pytestmark` lines:** 84 files (of 89 total). 7 bot files append `xdist_group("bot_concurrent")` via `pytestmark.append(pytest.mark.xdist_group(...))` (lines: `test_ad_create.py:19`, `test_ad_create_condition.py:36`, `test_claim_login_token.py:19`, `test_create_draft_ad.py:15`, `test_login_claim.py:17`, `test_unsubscribe.py:24`, `test_save_photo_integration.py:42`).

**Total per-test decorator uses (custom markers):** 13 (7 `seed` + 1 `real_images` + 1 `slow` + 4 `integration`). All concentrated in just 2 files (`test_seed.py` and `test_trust_calculator.py` + `test_auto_moderation.py`).

#### Additional pytest-bundled markers (per-test decorators)

| Marker | Count | Files |
|---|---|---|
| `@pytest.mark.asyncio` | 27 | 6 bot test files: `test_ad_create_condition` (4), `test_ad_create` (2), `test_unsubscribe` (7), `test_create_draft_ad` (5), `test_save_photo_integration` (2), `test_claim_login_token` (7) |
| `@pytest.mark.django_db` | 4 | `test_trust_calculator.py` (3), `test_auto_moderation.py` (1) — note: 1 false-positive in docstring `test_priority.py:8` |
| `@pytest.mark.parametrize` | 9 | `test_login.py` (2), `test_priority.py` (1), `test_ad_constraints.py` (1), `test_admin_actions.py` (1), `test_contact.py` (4) |
| `@pytest.mark.xdist_group` | 0 | None as per-test decorators — only via `pytestmark.append` |

### 5.2 Blanket `slow` usage

The pattern `pytestmark = [pytest.mark.django_db, pytest.mark.slow, pytest.mark.integration]` appears in **47 backend files**. An additional 8 bot files apply `slow` in their module-level `pytestmark` (7 with `django_db(transaction=True)` + 1 simple `django_db`).

**Total:** 55 files (62% of 89 test files) carry `slow` at module level. With `fail_under = 80` and CI running `-m "not seed"`, these 55 files' tests are NOT excluded by the `not seed` filter — they run in CI unless individually slow.

### 5.3 `seed` marker strategy

The `seed` marker is **never** applied at module level. `test_seed.py` (l.32) has `pytestmark = [pytest.mark.django_db, pytest.mark.slow, pytest.mark.integration]` — it does NOT include `seed`. The `seed` marker is applied **per-test/class** via `@pytest.mark.seed` on 5 classes + 1 method:

- `TestSeedCommand` (l.458) — 5 test methods
- `test_generates_ad_images` method (l.295, inside `TestImageGenerator`)
- `TestSeedCommandEnhanced` (l.900) — 2 test methods
- `TestSeedCategoryIntegration` (l.983) — 3 test methods
- `TestLeafCategoryFiltering` (l.1351) — 2 test methods
- `TestAdGeneratorLeafOnly` (l.1392) — 2 test methods
- `TestSeedFilterCoverage` (l.1459) — 6 test methods

**7 `@pytest.mark.seed` + 1 `@pytest.mark.real_images` = 8 seeded tests** out of 60 total in `test_seed.py`. The remaining 52 tests in `test_seed.py` run in the fast gate (they don't invoke `call_command('seed')`).

### 5.4 `concurrent` + `xdist_group` pairing

All 7 files using `concurrent` also append `xdist_group("bot_concurrent")`. The `concurrent` marker (per pyproject.toml description) means "transaction=True, TRUNCATE per test." All 7 are bot test files that use `django_db(transaction=True)` to permit cross-thread DB access from `@sync_to_async` worker threads.

---

## 6. Coverage & i18n Gates

### 6.1 Coverage gate

- **`fail_under = 80`** (pyproject.toml l.181, `[tool.coverage.report]`)
- Coverage source: `["src/backend", "src/telegram_bot"]` (l.177)
- Omit: migrations, tests, conftest, manage.py, wsgi.py, asgi.py (l.178)
- `--cov` is **not** in `addopts` — passed only via CI command line and `--cov-report=term --cov-report=xml`

### 6.2 i18n completeness gate

**File:** `src/backend/apps/ads/tests/test_i18n_completeness.py` (312 lines, 5 test methods)
**Marker:** `pytestmark = [pytest.mark.unit]` (l.30) — runs in fast gate (no DB)

Four guard tests enforce the multilingual Definition of Done (Spec_29 T-13):

| Test method | Line | Asserts |
|---|---|---|
| `test_no_hardcoded_visible_text` | 151 | Scans public/seller templates for visible text not wrapped in `{% trans %}` / `{% blocktrans %}` / `{{ _("...") }}` |
| `test_extraction_completeness` | 254 | Every msgid exists in all 3 `.po` files (ru, bs, en) |
| `test_no_empty_msgstr` | 277 | `ru` and `bs` have 0 empty `msgstr` for non-header entries (`en` exempt) |
| `test_no_raw_get_name_in_templates` | 290 | No raw `{{ obj.get_name }}` calls in templates |
| `test_mo_compiled` | 308 | Compiled `.mo` files exist for every `.po` |

**CI runs i18n separately** (ci.yml l.157–183): the `i18n` job runs `compilemessages` then `pytest test_i18n_completeness.py test_i18n_pipeline.py -v` — NOT included in the main `test` job's `-m "not seed"` run.

### 6.3 Seed conftest coverage interaction

`src/backend/apps/seed/tests/conftest.py` (l.36–49) patches `ImageGenerator` to a no-op stub via autouse fixture `_no_op_image_generator`. Tests marked `@pytest.mark.real_images` opt out (l.43: `if "real_images" in request.keywords`). This means most seed tests run fast (no image pipeline), but the 1 `real_images`-marked test (`TestSeedCommandEnhanced.test_media_cleanup`, l.915) uses the real pipeline.

---

## 7. CI & Runner Commands

### 7.1 CI workflow — `.github/workflows/ci.yml`

**`test` job (l.26–99):** Runs on `ubuntu-latest` with `postgres:18-alpine` service container on port 5432.

Steps: checkout → uv install (`--group dev`) → wait for DB → migrate (advisory lock) → compilemessages → **pytest**.

Test command (ci.yml:l91):
```
uv run pytest -m "not seed" -n auto --dist loadgroup --tb=short --cov --durations=10 --cov-report=term --cov-report=xml --reuse-db
```

Key flags:
| Flag | Purpose |
|---|---|
| `-m "not seed"` | Excludes 8 seed-marked tests (fast gate) |
| `-n auto` | xdist parallelism (all CPU cores) |
| `--dist loadgroup` | Distribution strategy — respects `xdist_group` markers (groups bot tests on same worker) |
| `--cov` | Enables coverage (fail_under=80) |
| `--cov-report=term --cov-report=xml` | Coverage output formats |
| `--reuse-db` | Reuses test DB schema between runs |
| `--durations=10` | Reports 10 slowest tests |

**`lint` job (l.101–117):** `ruff check .`
**`typecheck` job (l.119–135):** `basedpyright .`
**`lint-templates` job (l.137–156):** `djlint templates/`
**`i18n` job (l.157–183):** compilemessages + `pytest test_i18n_completeness.py test_i18n_pipeline.py -v` (no coverage, no xdist, no marker filter)

### 7.2 Nightly workflow — `.github/workflows/ci-nightly.yml`

**`seed-tests` job (l.14–82):** Runs daily at 03:00 UTC + `workflow_dispatch`.

Test command (ci-nightly.yml:l73):
```
uv run pytest -m "seed" --tb=short --cov --durations=10 --cov-report=term --cov-report=xml --reuse-db
```

Key differences from CI:
- `-m "seed"` (selects only seed-marked tests, not excludes)
- **No `-n auto` / `--dist loadgroup`** — nightly seed tests run sequentially
- No `compilemessages` step (only in regular CI's `test` job and `i18n` job)

### 7.3 Test entrypoint — `docker/entrypoint-test.sh` (56 lines)

Runs in the `test` Docker service. Pipeline: `uv sync` → wait for DB → migrate → compilemessages → pytest.

Pytest invocation (l.56):
```bash
uv run pytest ${PYTEST_OPTS:- --reuse-db --tb=short --durations=10} "${PYTEST_MARK_ARGS[@]}"
```

| Mechanism | Behavior |
|---|---|
| `PYTEST_OPTS` | If set, **overrides ALL pytest flags** (entrypoint comment l.40: "single-token flags only; multi-token values like `-m 'not seed'` are fragile") |
| `PYTEST_SKIP_MARKERS` | If set, appends `-m "not (${PYTEST_SKIP_MARKERS})"` to pytest. Used by `make test` to skip seed tests |
| Default (no PYTEST_OPTS) | `--reuse-db --tb=short --durations=10` (no xdist, no coverage) |

**Critical distinction:** The entrypoint does **NOT** include `-n auto` or `--cov`. CI runs pytest directly (bypassing the entrypoint) with xdist + coverage. Local `make test` runs sequentially without coverage.

### 7.4 Makefile vs Makefile.ps1

| Command | Makefile (`make`) | Makefile.ps1 (PowerShell) |
|---|---|---|
| `test` | `docker compose $(COMPOSE_TEST) up -d db` + `run --rm --env PYTEST_SKIP_MARKERS=seed test` | Same logic, also auto-starts test DB |
| `test-all` | `run --rm test` (no PYTEST_SKIP_MARKERS) | Same, auto-starts DB |
| `test-db` | `docker compose $(COMPOSE_TEST) up -d db` | Same |
| `test-recreate` | `run --rm --env PYTEST_OPTS="--no-reuse-db --create-db --tb=short" test` | Same |
| `test-down` | `down` | Same |

| Command | Effect |
|---|---|
| `make test` | Fast gate: skips seed tests via `PYTEST_SKIP_MARKERS=seed` → entrypoint adds `-m "not (seed)"`. Default flags: `--reuse-db --tb=short --durations=10`. **No xdist, no coverage.** |
| `make test-all` | Full suite: no marker exclusion. Same default flags. Runs seed tests sequentially. ~35 min (per Makefile.ps1 help text l.49) |
| `make test-recreate` | Overrides `PYTEST_OPTS` to `--no-reuse-db --create-db --tb=short` — forces fresh DB schema; seed tests still included |

### 7.5 Key discrepancy: xdist not in local runs

| Environment | xdist (`-n`) | coverage (`--cov`) | marker filter |
|---|---|---|---|
| CI (`ci.yml`) | `-n auto --dist loadgroup` | Yes (XML + term) | `-m "not seed"` |
| Nightly (`ci-nightly.yml`) | **No** | Yes (XML + term) | `-m "seed"` |
| Local `make test` | **No** | **No** | `-m "not (seed)"` (via entrypoint) |
| Local `make test-all` | **No** | **No** | None |
| Local `make test-recreate` | **No** | **No** | None |

The `xdist_group("bot_concurrent")` marker (7 bot test files) is only effective in CI (`-n auto --dist loadgroup`). In local Docker runs, these tests run sequentially and the `xdist_group` marker has no effect.

---

## 8. Dev Dependencies

**Source:** `pyproject.toml` lines 198–209 (`[dependency-groups].dev`)

```toml
[dependency-groups]
dev = [
    "basedpyright>=1.39.9",
    "pytest>=9.1.1",
    "pytest-asyncio>=1.4.0",
    "pytest-cov>=7.1.0",
    "pytest-django>=4.12.0",
    "pytest-xdist>=3.8.0",
    "ruff>=0.16.0",
    "coverage>=7.15.2",
    "djlint>=1.44.2",
]
```

**Import verification** (grep for imports in `src/`):

| Package | Imported in src/ | Evidence / usage |
|---|---|---|
| `ruff` | No (lint tool only) | Config in `[tool.ruff]` l.88; CI `ruff check .` ci.yml:l116 |
| `basedpyright` | No (type checker only) | Config in `[tool.basedpyright]` l.185; CI `basedpyright .` ci.yml:l134 |
| `pytest` | Yes | All test files import `pytest` directly |
| `pytest-asyncio` | Yes | `src/telegram_bot/tests/conftest.py:l14` (`import pytest_asyncio`); `asyncio_mode = "strict"` (p.157) |
| `pytest-cov` | No (CLI plugin) | `--cov` flag in CI; not in `addopts` |
| `pytest-django` | Implicit | `django_db` string appears 73× (grep); ~57 in module-level `pytestmark`, 4 as per-test class decorators, remainder in docstrings/comments; no direct import |
| `pytest-xdist` | No (CLI plugin) | `-n auto --dist loadgroup` in CI only |
| `coverage` | No (via pytest-cov) | `[tool.coverage.run]` / `[tool.coverage.report]` config p.175–183 |
| `djlint` | No (template linter only) | `[tool.djlint]` config p.225; CI `djlint templates/` ci.yml:l152; Makefile `lint-templates` |

**Note:** `default-groups = []` (p.196) keeps dev tools out of the production image. The entrypoint-test.sh explicitly runs `uv sync --group dev` (l.14) to install test deps.

---

## 9. Key Structural Observations

1. **Two independent test hierarchies.** Bot tests (`src/telegram_bot/tests/`) do NOT share the root `src/backend/conftest.py` — fixtures are redefined (documented at bot conftest l.66–84). Only `create_test_ad`/`create_test_ads_bulk` are shared via `pythonpath`-resolved `from conftest import ...`.

2. **Heavy reliance on module-level `pytestmark`.** 84 of 89 files use module-level `pytestmark`. Only 13 per-test custom-marker decorators exist, concentrated in `test_seed.py` (8) and `test_trust_calculator.py`/`test_auto_moderation.py` (5).

3. **Blanket `slow` marker.** 55 files apply `slow` at module level with no per-test granularity — every test in those files inherits the `slow` tag, making it impossible to run fast individual tests from slow-marked files without deselecting the whole file.

4. **Seed gating is clean.** The `seed` marker is applied only to the 8 specific tests that call `call_command('seed')` or use the real `ImageGenerator`, not to the entire `test_seed.py` file's 60 tests. The remaining 52 tests in that file exercise generators directly and run in the fast gate.

5. **i18n gate is CI-only.** `test_i18n_completeness.py` runs in both the main CI `test` job (as part of `-m "not seed"`) and a dedicated `i18n` CI job (ci.yml l.179–183). It is marked `unit` (no DB), so it's fast.

6. **No xdist for local runs.** The entrypoint-test.sh default has no `-n` flag; only CI adds `-n auto --dist loadgroup`. The `xdist_group("bot_concurrent")` markers in 7 bot files are inert during local `make test` / `make test-all`.

7. **Coverage only in CI.** `fail_under = 80` is configured but `--cov` is not in `addopts` — coverage is enforced only in CI (ci.yml l.91 and ci-nightly.yml l.73), not in local Docker runs.

8. **4 test files lack any marker.** `test_price_format.py`, `test_sanitize.py`, `test_thumbnails.py` are pure unit tests with no `pytest.mark.unit`, and `test_auto_moderation.py` mixes unmarked unit tests with a class-level `@pytest.mark` decorated section — inconsistent with the 84-file module-level convention.
