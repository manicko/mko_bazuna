# Bug Report: Test Infrastructure Issues

## Date: 2026-08-08T10:41:00+02:00
## Severity: Medium
## Status: Open

---

## Summary

Two categories of test infrastructure issues: (A) errors encountered during local test validation; (B) pre-existing broken infrastructure discovered by researcher agent analysis.

---

## How Integration Tests Were Designed To Run

**Local/Docker path:**
```
make test → docker compose -f docker-compose.yml -f docker-compose.test.yml run --rm test
```
Spins up ephemeral `postgres:18-alpine` container (DB: `mko_bazuna`, user/pass: `postgres`) and runs `entrypoint-test.sh` which: (1) waits for DB readiness, (2) runs migrations via advisory-locked `migrate_locked.py`, (3) runs `uv run pytest --tb=short`.

**CI path (GitHub Actions):**
Uses `postgres:18` service container, then from `working-directory: src/backend`:
```
uv sync --frozen --no-install-project → migrations → uv run pytest --tb=short --cov
```

**Test DB connection:**
`TestSeedCategoryIntegration` uses `django.test.TestCase` — pytest-django auto-detects it and creates a `test_mko_bazuna` database (prepends `test_` to `NAME="mko_bazuna"` from `config.settings.test`). Root `conftest.py` sets `DJANGO_SETTINGS_MODULE=config.settings.test` with a `DATABASE_URL` default for local testing. No custom fixtures — uses pytest-django defaults.

---

## Category A: Errors Encountered During Validation

### Issue A1: UnicodeEncodeError in round-trip preservation test

- **File:** `test_roundtrip.py` (temporary, deleted after run)
- **Component:** `src/backend/apps/categories/catalog/builder.py` validation
- **Error:**

```
UnicodeEncodeError: 'charmap' codec can't encode character '\u043f' in position 35: invalid terminal
```

### Full Traceback

```
Traceback (most recent call last):
  File "test_roundtrip.py", line 34, in <module>
    print(result)
UnicodeEncodeError: 'charmap' codec can't encode character '\u043f' in position 35: invalid terminal
```

### Root Cause

The test script uses `print(result)` to display the round-trip YAML output containing Cyrillic characters. On Windows, PowerShell's default console encoding is cp1252, which cannot encode Cyrillic text. The Python `sys.stdout` is not configured for UTF-8 by default in this environment.

### Impact

This is a **test artifact only** — not a production code issue. The round-trip preservation test passed all assertions before the `print()` call:

- ✅ Import of `ruamel.yaml` succeeded
- ✅ Data loaded correctly (flow style + Cyrillic preserved)
- ✅ Comments preserved (all 3 header comment lines)
- ✅ Flow style `{ru: "Продажа", ...}` preserved
- ✅ Double-quoted strings with Cyrillic preserved
- ✅ `new_slug` key removed after rename
- ✅ `slug` updated from `give-away` to `giveaway`

### Resolution

The test was rewritten to use `sys.stdout.reconfigure(encoding="utf-8")` and redirect output to a file. All assertions passed. The temporary test file was deleted after verification.

---

### Issue A2: Integration tests require PostgreSQL database

- **File:** `src/backend/apps/seed/tests/test_seed.py`
- **Classes:** `TestSeedCategoryIntegration`
- **Error:**

```
django.db.utils.OperationalError: could not connect to server: Connection refused
```

### Root Cause

The integration tests in `TestSeedCategoryIntegration` call `load_catalog()` which uses Django's `transaction.atomic()` and queries the PostgreSQL database. No PostgreSQL server was running in the local development environment at the time of testing.

### Impact

Cannot run integration tests for the seed/categorization pipeline locally. These tests validate the full `load_catalog()` → ORM → database flow including:

- Category model creation from YAML
- Slug rename mapping application
- Lookup creation (listing_purpose, etc.)
- Hierarchical category path binding

### Resolution

None — requires a running PostgreSQL 18 instance with the Django app configured. Can be run via Docker (`make test`) or against a local PostgreSQL container.

---

## Category B: Pre-existing Broken Infrastructure (Discovered by Researcher Agent)

The researcher agent analyzed the intended test infrastructure (Docker + CI) and found 5 issues that would prevent tests from running even with a PostgreSQL server available.

### Issue B1: `default-groups = []` prevents dev tool installation

- **File:** `pyproject.toml`, `[tool.uv]` section
- **Commit:** `8d66138` (Jul 23)
- **Impact:** `uv sync` skips the `dev` group, so `pytest`, `pytest-django`, `pytest-cov`, `ruff`, and `basedpyright` are never installed. CI's `uv sync --frozen --no-install-project` does not specify `--group dev`, so dev tools are absent in CI too. This is the primary blocker for running any tests.
- **Resolution:** Either remove `default-groups = []` or add `--group dev` to every `uv sync` command in CI and `entrypoint-test.sh`.

### Issue B2: `uv.lock` is gitignored

- **File:** `.gitignore` (line 101)
- **Impact:** CI's `uv sync --frozen` requires a committed lockfile, but `uv.lock` is gitignored. CI would fail at the sync step.
- **Resolution:** Remove `uv.lock` from `.gitignore` and commit the lockfile.

### Issue B3: Relative path conflict for CATALOG_PATH

- **File:** `src/backend/apps/seed/tests/test_seed.py`, line ~21
- **Value:** `CATALOG_PATH = "src/backend/apps/categories/catalog/categories.yaml"`
- **Commit:** `5182153` (Aug 5)
- **Impact:** Works when CWD is repo root (Docker's `WORKDIR /app`), but breaks in CI where `working-directory: src/backend` makes the path resolve to `src/backend/src/backend/apps/categories/catalog/categories.yaml` (nonexistent).
- **Resolution:** Use an absolute path derived from the test file location (e.g., `Path(__file__).resolve().parents[4] / "catalog/categories.yaml"`) or use `settings.BASE_DIR`.

### Issue B4: Hardcoded `cwd="/app"` in migrate_locked.py

- **File:** `src/backend/migrate_locked.py`
- **Impact:** CI runs on `ubuntu-latest` where `/app` doesn't exist, breaking the "Run migrations" step before tests even start.
- **Resolution:** Use a configurable path — derive from `settings.BASE_DIR` or `os.getcwd()`.

### Issue B5: Deleted `src/backend/conftest.py`

- **File:** `src/backend/conftest.py` (source deleted; stale `.pyc` in `__pycache__/`)
- **Impact:** Low — the root `conftest.py` supersedes it and sets `DJANGO_SETTINGS_MODULE=config.settings.test`. Likely incidental rather than a regression.
- **Resolution:** No action needed unless the deleted conftest had unique fixtures.

---

## Summary Table

| # | Category | Issue | Commit/Date | Severity |
|---|----------|-------|-------------|----------|
| A1 | Validation error | UnicodeEncodeError on print() | Test artifact | Low (fixed) |
| A2 | Validation error | PostgreSQL not running locally | Environment | Medium (infra) |
| B1 | Broken infra | `default-groups = []` blocks dev tools | `8d66138` (Jul 23) | **Critical** |
| B2 | Broken infra | `uv.lock` gitignored, breaks `--frozen` | Pre-existing | **Critical** |
| B3 | Broken infra | CATALOG_PATH relative path breaks in CI | `5182153` (Aug 5) | High |
| B4 | Broken infra | Hardcoded `cwd="/app"` breaks on ubuntu CI | Pre-existing | High |
| B5 | Broken infra | Deleted conftest.py | Pre-existing | Low |

- **File:** `test_roundtrip.py` (temporary, deleted after run)
- **Component:** `src/backend/apps/categories/catalog/builder.py` validation
- **Error:**

```
UnicodeEncodeError: 'charmap' codec can't encode character '\u043f' in position 35: invalid terminal
```

### Full Traceback

```
Traceback (most recent call last):
  File "test_roundtrip.py", line 34, in <module>
    print(result)
UnicodeEncodeError: 'charmap' codec can't encode character '\u043f' in position 35: invalid terminal
```

### Root Cause

The test script uses `print(result)` to display the round-trip YAML output containing Cyrillic characters. On Windows, PowerShell's default console encoding is cp1252, which cannot encode Cyrillic text. The Python `sys.stdout` is not configured for UTF-8 by default in this environment.

### Impact

This is a **test artifact only** — not a production code issue. The round-trip preservation test passed all assertions before the `print()` call:

- ✅ Import of `ruamel.yaml` succeeded
- ✅ Data loaded correctly (flow style + Cyrillic preserved)
- ✅ Comments preserved (all 3 header comment lines)
- ✅ Flow style `{ru: "Продажа", ...}` preserved
- ✅ Double-quoted strings with Cyrillic preserved
- ✅ `new_slug` key removed after rename
- ✅ `slug` updated from `give-away` to `giveaway`

### Resolution

The test was rewritten to use `sys.stdout.reconfigure(encoding="utf-8")` and redirect output to a file. All assertions passed. The temporary test file was deleted after verification.

---

## Issue 2: Integration tests require PostgreSQL database

- **File:** `src/backend/apps/seed/tests/test_seed.py`
- **Classes:** `TestSeedCategoryIntegration`
- **Error:**

```
django.db.utils.OperationalError: could not connect to server: Connection refused
```

### Root Cause

The integration tests in `TestSeedCategoryIntegration` call `load_catalog()` which uses Django's `transaction.atomic()` and queries the PostgreSQL database. No PostgreSQL server is available in the local development environment.

### Impact

Cannot run integration tests for the seed/categorization pipeline locally. These tests validate the full `load_catalog()` → ORM → database flow including:

- Category model creation from YAML
- Slug rename mapping application
- Lookup creation (listing_purpose, etc.)
- Hierarchical category path binding

### Resolution

None — requires a running PostgreSQL 18 instance with the Django app configured. Can be run in CI or against a local Docker PostgreSQL container.
