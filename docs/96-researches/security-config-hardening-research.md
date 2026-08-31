# Security & Config Hardening Research Report

**Date:** 2026-08-16  
**Project:** Mko Bazuna (Django 5.2 LTS + aiogram 3.x + Docker Compose + PostgreSQL 18)  
**Researcher:** Agent  
**Status:** Complete  
**Confidence Levels:** See confidence tags per section (HIGH = verified against source code + official docs, MEDIUM = cross-referenced with external best-practice sources, LOW = inferred/possible change)

---

## Table of Contents

1. [Fail-fast Secret Handling in Docker Compose](#1-fail-fast-secret-handling-in-docker-compose)
2. [Django Settings Fail-fast for Secrets](#2-django-settings-fail-fast-for-secrets)
3. [Docker Entrypoint `.env` File Validation](#3-docker-entrypoint-env-file-validation)
4. [Django Test Patterns for Settings Validation](#4-django-test-patterns-for-settings-validation)
5. [Dead Code Removal: 0-byte Git-tracked Stubs](#5-dead-code-removal-0-byte-git-tracked-stubs)
6. [Summary & Prioritized Recommendations](#6-summary--prioritized-recommendations)

---

## 1. Fail-fast Secret Handling in Docker Compose

### 1.1 Problem in Current Project

The project currently uses `:-` defaults for required-seeming secrets in `docker-compose.yml`:

```yaml
# docker-compose.yml (base, lines 10-12)
POSTGRES_DB: ${POSTGRES_DB:-postgres}
POSTGRES_USER: ${POSTGRES_USER:-postgres}
POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-postgres}

# docker-compose.yml (all services, lines 36, 60)
DJANGO_SECRET_KEY: ${DJANGO_SECRET_KEY:-placeholder}

# docker-compose.yml (lines 37, 61)
BOT_TOKEN: ${BOT_TOKEN}
```

The `DJANGO_SECRET_KEY: ${DJANGO_SECRET_KEY:-placeholder}` default is especially dangerous: Django silently accepts `placeholder` as a valid `SECRET_KEY` (it's 11 characters, a valid string), meaning the app boots in production with a known-weak signing key — enabling session/CSRF forgery.

### 1.2 `:?` vs `:-` Syntax

**Verified against official Docker/Compose specification:** [Docker Compose Interpolation](https://docs.docker.com/reference/compose-file/interpolation/) and [Compose Specification](https://compose-spec.github.io/compose-spec/12-interpolation.html).

| Syntax | Behavior | When it triggers |
|---|---|---|
| `${VAR}` | Empty string if unset | Unset only |
| `${VAR:-default}` | Use `default` if unset **or empty** | Unset OR empty string |
| `${VAR-default}` | Use `default` if unset | Unset only (empty string passes through) |
| `${VAR:?err}` | **Exit with error** if unset **or empty** | Unset OR empty string |
| `${VAR?err}` | **Exit with error** if unset | Unset only (empty string passes through) |

**Key distinction (HIGH confidence):** The colon variants (`:-`, `:?`) treat an **empty string as missing**, while the non-colon variants (`-`, `?`) treat an empty string as a valid value. For startup guards, the colon variants are almost always what you want.

### 1.3 `${VAR:?error message}` vs `${VAR:?}`

**Trade-offs:**

- **`${VAR:?message}`** — Compose prints your custom message alongside the error. This is maximally helpful for onboarding: the operator immediately knows which variable to set and what it's for.
- **`${VAR:?}`** — Compose prints a generic `required` message. Less verbose but less actionable.

**Best practice (MEDIUM confidence, cross-referenced with [cr0x.net](https://cr0x.net/en/docker-compose-env-file-mistakes/) and [LocalEnvAuto](https://www.local-environment-automation.com/environment-sync-secrets-ci-parity/environment-variable-validation/catching-missing-env-vars-before-container-startup/)):**
- Always use `${VAR:?message}` for required secrets — never `${VAR:?}` alone. A descriptive message prevents hours of debugging.
- The colon form `${VAR:?message}` (rejects empty string) is preferred over the non-colon form `${VAR?message}` for secrets.

### 1.4 Optional vs Required Variables

The three-guard pattern from [LocalEnvAuto](https://www.local-environment-automation.com/environment-sync-secrets-ci-parity/environment-variable-validation/catching-missing-env-vars-before-container-startup/) (MEDIUM confidence):

1. **Compose interpolation guard** (`${VAR:?msg}`) — fires at `docker compose up` boundary.
2. **Entrypoint script check** — fires inside the image on every launch path (CI `docker run`, Kubernetes Job, etc.).
3. **CI schema gate** — validates `.env` against a JSON schema before deployment.

**Classification rule:** A variable is "required" if the service cannot function correctly without it and there is no safe default. Anything with a sensible fallback (log level, feature flag, cache TTL) should get a default in code, **not** a hard guard. For this project:

| Variable | Required? | Rationale | Recommended Syntax |
|---|---|---|---|
| `DJANGO_SECRET_KEY` | **Yes** | Session/CSRF signing; empty or `placeholder` is a security vulnerability | `${DJANGO_SECRET_KEY:?DJANGO_SECRET_KEY must be set in .env.docker}` |
| `POSTGRES_DB` | No | Can default to `postgres` or `mko_bazuna` | `${POSTGRES_DB:-postgres}` |
| `POSTGRES_USER` | No | Can default to `postgres` | `${POSTGRES_USER:-postgres}` |
| `POSTGRES_PASSWORD` | **Yes** | Database authentication; `postgres` as default is a weak credential | `${POSTGRES_PASSWORD:?POSTGRES_PASSWORD must be set in .env.docker}` |
| `BOT_TOKEN` | **Yes (prod)** / No (dev) | Bot cannot function without it; dev allows empty for web-only testing | `${BOT_TOKEN:?BOT_TOKEN must be set in .env.docker}` (prod), bare `${BOT_TOKEN}` or `:-` with warning (dev) |
| `DATABASE_URL` | No | Constructed from `POSTGRES_*` in compose; only needed for local/standalone | `${DATABASE_URL:-}` |
| `DEBUG` | No | Boolean, defaults to `False` | `${DEBUG:-False}` |
| `ALLOWED_HOSTS` | **Yes (prod)** | Django returns 400 on all requests if empty in production | `${ALLOWED_HOSTS:?ALLOWED_HOSTS must be set}` |

**Multi-environment strategy (HIGH confidence):** Use environment-specific `.env` files:
- `.env.docker` — runtime secrets (gitignored, per CFG-003 recommendation)
- `.env.docker.example` — tracked template (already exists)
- Pass with `--env-file` in CI/automation to ensure deterministic rendering

### 1.5 Important Caveat: `env_file` vs Interpolation

**Critical distinction (HIGH confidence, verified against [Docker docs](https://docs.docker.com/compose/how-tos/environment-variables/set-environment-variables) and [env.dev guide](https://env.dev/guides/docker-compose-env-variables)):**

- `.env` file → only feeds `${VAR}` substitution in the Compose YAML. It does **NOT** inject variables into the container.
- `env_file:` directive → injects variables into the container environment at runtime.

The project uses **both**: `.env.docker` as the `--env-file` (for interpolation via `Makefile: ENV_FILE := --env-file .env.docker`) AND `env_file: .env.docker` in each service (for container injection). The `.env.docker` is also bind-mounted as a read-only volume at `/app/src/.env:ro`. This triple-use is correct but means the fail-fast guard `${VAR:?msg}` should be applied to the `environment:` blocks where the variable is explicitly passed into the container.

**Note on `BOT_TOKEN: ${BOT_TOKEN}`** — This current form (line 37, 61) has no `:` or default, so Compose substitutes an empty string with a **warning** but does **not** fail. Per [docker/compose#3768](https://github.com/docker/compose/issues/3768), empty string is not the same as unset, and `${BOT_TOKEN}` treats both as "ordinary, valid inputs." This is why the bot silently boots with an empty token.

---

## 2. Django Settings Fail-fast for Secrets

### 2.1 Current State

The project uses `django-environ` 0.11+ (declared in `pyproject.toml:13`):

```python
# src/backend/config/settings/base.py (lines 19-49)
env = environ.Env(
    DEBUG=(bool, False),
    BOT_TOKEN=(str, ""),
)

env_path = BASE_DIR / ".env"
if not env_path.exists():
    if (
        os.getenv("DJANGO_SETTINGS_MODULE")
        and "test" not in os.getenv("DJANGO_SETTINGS_MODULE", "")
        and not os.getenv("DJANGO_BUILD")
    ):
        logger.error("ERROR: .env file not found...")
        sys.exit(1)
else:
    environ.Env.read_env(env_path)

SECRET_KEY = env("DJANGO_SECRET_KEY")  # raises ImproperlyConfigured if unset ✓
BOT_TOKEN = env("BOT_TOKEN", default="")  # silently defaults to "" ✗ (CFG-001)
```

**Findings:**
- `SECRET_KEY` correctly uses `env("DJANGO_SECRET_KEY")` without a default → raises `ImproperlyConfigured` (django-environ behavior, verified against [django-environ source](https://github.com/joke2k/django-environ) and docs).
- `BOT_TOKEN` uses `default=""` → silently allows a missing token. The bot's `main.py:28-30` logs a warning and exits 0 instead of failing.
- The `.env` file existence check in `base.py:29-34` is a coarse fail-fast that bypasses proper Django settings validation.

### 2.2 Idiomatic Fail-fast Pattern for BOT_TOKEN

**Recommended approach (HIGH confidence, verified against django-environ docs and Django settings docs):**

```python
# In base.py — remove default="" from the env() schema declaration
env = environ.Env(
    DEBUG=(bool, False),
)

# BOT_TOKEN: required in production, optional in development
BOT_TOKEN = env("BOT_TOKEN")
if not BOT_TOKEN and not DEBUG:
    raise ImproperlyConfigured(
        "BOT_TOKEN is required in production. "
        "Set it in your .env file or environment. "
        "In development (DEBUG=True), an empty BOT_TOKEN disables the bot process."
    )
```

**Rationale:**
- `env("BOT_TOKEN")` without a default raises `ImproperlyConfigured` via django-environ's `Env.__getitem__` → `Env._get_value` → raises `ImproperlyConfigured(f"Set the {var_name} environment variable")`.
- The `if not BOT_TOKEN and not DEBUG` guard allows dev to skip the bot (web-only mode) while ensuring production never boots without a token.
- The `DEBUG` variable is already loaded via the `Env` schema cast, so referencing it at module level is safe.

**Alternative: Django System Check (MEDIUM confidence):**

Django's [system check framework](https://docs.djangoproject.com/en/5.2/topics/checks/) offers a deployable approach. A custom check registered in `AppConfig.ready()` can validate `BOT_TOKEN` at boot:

```python
from django.conf import settings
from django.core.checks import Error, register, Tags


@register(Tags.security, deploy=True)
def check_bot_token(app_configs, **kwargs):
    errors = []
    if not settings.DEBUG and not settings.BOT_TOKEN:
        errors.append(
            Error(
                "BOT_TOKEN is empty in production.",
                hint="Set BOT_TOKEN in your environment or .env file.",
                id="core.E001",
            )
        )
    return errors
```

**Pros:** Integrates with `manage.py check --deploy`, testable via `call_command("check", ...)`.
**Cons:** Checks don't run on the WSGI stack by default ([Django docs](https://docs.djangoproject.com/en/5.2/topics/checks/#how-to-read-the-results)). You'd need to explicitly call `call_command("check")` in the entrypoint. The settings-module guard is simpler and fires on every import.

**Recommendation:** Use the settings-module guard (section 2.2) as the primary fail-fast, optionally supplemented by a system check for `manage.py check --deploy` parity.

### 2.3 Removing the Coarse `.env` Existence Check

The current `base.py:29-34` checks for a `.env` file and exits. This is fragile because:

1. In Docker, environment variables come from `env_file:` (container-level), not `.env` (interpolation-level). The bind-mount puts `.env.docker` at `/app/src/.env`, but the check path `BASE_DIR / ".env"` = `/app/src/.env` happens to match by accident of the bind-mount destination.
2. The `DJANGO_BUILD` and `test` exclusions are ad-hoc.
3. `sys.exit(1)` in settings is not catchable by Django's error handling.

**Better approach (HIGH confidence):** Let django-environ's `read_env()` handle missing files gracefully (it already logs a warning per [django-environ source](https://github.com/joke2k/django-environ/blob/main/environ/environ.py)), and rely on `env("VAR")` without defaults for required variables. Remove the manual file-existence check entirely. This is the [django-environ recommended pattern](https://django-environ.readthedocs.io/en/stable/quickstart.html).

### 2.4 `os.environ["KEY"]` vs `env("KEY")` vs `os.getenv("KEY")`

**Verified against [env.dev guide](https://env.dev/guides/django-env-variables) and Django docs (HIGH confidence):**

| Pattern | Behavior | Use Case |
|---|---|---|
| `os.environ["KEY"]` | Raises `KeyError` if unset | Bare-metal fail-fast, no `.env` loading |
| `env("KEY")` (django-environ) | Raises `ImproperlyConfigured` if unset | **Best for Django projects** — integrates with Django's error handling, supports type casting |
| `os.getenv("KEY")` | Returns `None` if unset | Optional vars only |
| `os.getenv("KEY", default)` | Returns `default` if unset | Optional vars with defaults |

Since the project already depends on `django-environ`, the idiomatic pattern is `env("KEY")` without a default for required variables.

---

## 3. Docker Entrypoint `.env` File Validation

### 3.1 Current State

**`docker/entrypoint.sh` (lines 9-21)** — checks `/app/src/.env` then `/app/.env`:
```bash
check_env_file() {
    ENV_PATH="/app/src/.env"
    if [ ! -f "$ENV_PATH" ]; then
        ENV_PATH="/app/.env"
    fi
    if [ -z "$SKIP_ENV_CHECK" ] && [ ! -f "$ENV_PATH" ]; then
        if [ "$DJANGO_SETTINGS_MODULE" != "config.settings.test" ]; then
            echo "ERROR: .env file not found. Copy .env.example to .env and configure values." >&2
            exit 1
        fi
    fi
}
```

**`docker/entrypoint-scheduler.sh` (line 8)** — checks **only** `/app/.env`:
```bash
if [ -z "$SKIP_ENV_CHECK" ] && [ ! -f "/app/.env" ]; then
```

### 3.2 The Bug: `/app/.env` vs `/app/src/.env`

**Confirmed bug (HIGH confidence):** The bind-mount in `docker-compose.yml` and `docker-compose.prod.yml` is:
```yaml
volumes:
  - ./.env.docker:/app/src/.env:ro
```

This places the secret file at `/app/src/.env`, **not** `/app/.env`. The `entrypoint.sh` correctly checks `/app/src/.env` first. But `entrypoint-scheduler.sh` checks `/app/.env` — which **never exists** — causing a crash loop under `restart: unless-stopped` with `profiles: ["scheduler"]`.

The existing project audit (`.ai/audit/02-config-secrets/findings.md`, finding CFG-004) already identified and documented this. The recommendation is to fix `entrypoint-scheduler.sh` to check `/app/src/.env` (matching the bind-mount), or source the shared `check_env_file` function from `entrypoint.sh`.

### 3.3 The Path to Check: `/app/src/.env`

**Verified (HIGH confidence):**
- `BASE_DIR` in `base.py:16` is `Path(__file__).resolve().parent.parent.parent.parent`
  - `__file__` = `/app/src/backend/config/settings/base.py`
  - `.parent` = `/app/src/backend/config/settings`
  - `.parent.parent` = `/app/src/backend/config`
  - `.parent.parent.parent` = `/app/src/backend`
  - `.parent.parent.parent.parent` = `/app/src`
- So `env_path = BASE_DIR / ".env"` = `/app/src/.env` — **matches the bind-mount destination**.

The entrypoint should check `/app/src/.env` because:
1. It matches the `BASE_DIR / ".env"` location in settings.
2. It matches the bind-mount destination `./.env.docker:/app/src/.env:ro`.
3. It is the path where Django actually reads the file.

### 3.4 More Robust Approaches

**Option A: Source shared function (RECOMMENDED, HIGH confidence):**

Create a shared library file `docker/lib/env_check.sh` that all entrypoints source:
```bash
#!/bin/bash
# Shared environment validation for all entrypoint scripts.
# Checks the same .env path that Django's settings.py reads (BASE_DIR / ".env").

check_env_file() {
    local env_path="/app/src/.env"
    if [ -z "${SKIP_ENV_CHECK:-}" ] && [ ! -f "$env_path" ]; then
        if [ "${DJANGO_SETTINGS_MODULE}" != "config.settings.test" ]; then
            echo "ERROR: .env file not found at $env_path." >&2
            echo "       Copy .env.docker.example to .env.docker and configure values." >&2
            exit 1
        fi
    fi
}
```

All entrypoints source this and call `check_env_file`. This eliminates path drift.

**Option B: Don't check for `.env` file at all (MEDIUM confidence):**

Rely entirely on Django's settings module to fail-fast via `env("VAR")` without defaults. The `.env` file existence check is a Docker-specific concern that doesn't belong in Django settings. If env vars are injected via `env_file:` or `environment:` blocks, the `.env` file may not exist at all.

**Trade-off:** Option A provides an earlier, clearer error message (at container boot, before Python starts). Option B is simpler and more correct for 12-factor deployments where the `.env` file is an optional dev convenience.

**Hybrid recommendation (HIGH confidence):** Use the shared `check_env_file` (Option A) but make it a **secondary** validation — the primary validation should be Django's `env("VAR")` with no defaults. The entrypoint check is a fast-fail safety net; the settings-module guard is the authoritative validation. This follows the three-guard pattern from [LocalEnvAuto](https://www.local-environment-automation.com/environment-sync-secrets-ci-parity/environment-variable-validation/catching-missing-env-vars-before-container-startup/).

---

## 4. Django Test Patterns for Settings Validation

### 4.1 Current State

There is **no existing settings test module** in the project. The audit finding CFG-005 (`.ai/audit/02-config-secrets/findings.md:125-145`) confirms that no tests assert `ImproperlyConfigured` is raised when required env vars are missing, and the BOT_TOKEN policy (required in prod, optional in dev) is untested.

The CI sets all env vars directly (`.github/workflows/ci.yml:76,84,92`): `DJANGO_SECRET_KEY: test-secret-key-for-testing-only`. The test compose (`docker-compose.test.yml`) sets them inline (lines 19-21, 39, 61-62). No root-level `conftest.py` stamps defaults — the tests rely on the environment.

### 4.2 Testing `ImproperlyConfigured` — The Core Challenge

**Key insight (HIGH confidence, verified against Django 5.2 source):** Django settings are evaluated **once** at first access. `django.setup()` loads and caches the settings module. `override_settings` and `modify_settings` work by swapping the settings wrapper **object** — they don't re-import the settings module. So:

- ✅ `override_settings(DJANGO_SECRET_KEY="")` → can override already-loaded settings via the `settings` fixture.
- ✅ `monkeypatch.setenv("FOO", "bar")` → works for code that reads `os.environ` **at runtime** (after Django is configured).
- ❌ Neither `override_settings` nor `monkeypatch.setenv` can test "what happens when `env("SECRET_KEY")` raises at import time" — because the settings module is already imported and cached.

To test that a settings module raises `ImproperlyConfigured` when an env var is missing, you must:

1. Manipulate `os.environ` **before** the settings module is imported.
2. **Force a re-import** using `importlib.reload()` or by manipulating `sys.modules`.

### 4.3 Recommended Test Pattern

**For testing fail-fast on missing `DJANGO_SECRET_KEY` (HIGH confidence):**

```python
import importlib
import sys
from unittest import mock

import pytest
from django.core.exceptions import ImproperlyConfigured


class TestSettingsValidation:
    """Tests that settings fail-fast when required env vars are missing."""

    @pytest.fixture
    def fresh_settings(self):
        """Provide a way to re-import the settings module with controlled env."""
        # Remove the cached settings module so Django re-imports it
        modules_to_clean = [
            name for name in sys.modules if name.startswith("config.settings")
        ]
        for name in modules_to_clean:
            del sys.modules[name]

        # Force Django to re-evaluate settings
        from django.conf import settings

        settings._wrapped = None

        yield

        # Restore
        for name in modules_to_clean:
            del sys.modules[name]
        settings._wrapped = None

    def test_missing_django_secret_key_raises(self, fresh_settings):
        """DJANGO_SECRET_KEY without a value triggers ImproperlyConfigured."""
        with mock.patch.dict("os.environ", {}, clear=False):
            os.environ.pop("DJANGO_SECRET_KEY", None)
            with pytest.raises(ImproperlyConfigured, match="Set the DJANGO_SECRET_KEY"):
                importlib.import_module("config.settings.base")
```

**Simpler alternative: extract validation logic into a testable function (HIGH confidence):**

Instead of testing the import side-effect, refactor the validation into a callable that can be tested directly:

```python
# src/backend/config/settings/base.py
from django.core.exceptions import ImproperlyConfigured


def _require_secret_key() -> str:
    """Return DJANGO_SECRET_KEY, raising ImproperlyConfigured if unset."""
    key = env("DJANGO_SECRET_KEY")
    if not key:
        raise ImproperlyConfigured("DJANGO_SECRET_KEY must not be empty.")
    return key


SECRET_KEY = _require_secret_key()
```

Then test:
```python
class TestSecretKeyValidation(SimpleTestCase):
    def test_raises_when_unset(self):
        with mock.patch.dict("os.environ", {}, clear=False):
            os.environ.pop("DJANGO_SECRET_KEY", None)
            with self.assertRaises(ImproperlyConfigured):
                _require_secret_key()
```

This is the pattern recommended when settings logic is complex (per [doroshev.com blog](https://dev.doroshev.com/blog/django-settings-reload-patch/) — "Avoid putting non-trivial logic at module scope").

### 4.4 Testing the BOT_TOKEN Policy (Required in Prod, Optional in Dev)

**Using `SimpleTestCase` with `override_settings` (HIGH confidence, matches existing project test style):**

The project already uses `SimpleTestCase` for non-DB tests (e.g., `test_context_processors.py:11`, `test_language_middleware.py:17`). The pattern is consistent:

```python
from django.test import SimpleTestCase


class TestBotTokenPolicy(SimpleTestCase):
    """BOT_TOKEN is required in production (DEBUG=False), optional in dev (DEBUG=True)."""

    def test_allows_empty_in_dev(self):
        """In DEBUG mode, empty BOT_TOKEN is permitted."""
        # This tests the *runtime* behavior, not the import-time setting.
        # For import-time testing, use the function-extraction pattern above.
        ...

    def test_rejects_empty_in_prod(self):
        """In production (DEBUG=False), empty BOT_TOKEN raises ImproperlyConfigured."""
        ...
```

**For the current project's `base.py` which uses django-environ's `Env` schema with `default=""`:**

Since the current code reads `BOT_TOKEN` at module level with a default, testing the policy requires either:
1. The function-extraction pattern (recommended for new code), OR
2. `importlib.reload` of the settings module with `os.environ` patched (works but fragile).

**Using `monkeypatch.setenv` / `monkeypatch.delenv` (HIGH confidence, [pytest docs](https://docs.pytest.org/en/stable/how-to/monkeypatch.html)):**

```python
def test_bot_token_required_in_prod(monkeypatch):
    """When DEBUG=False and BOT_TOKEN is unset, settings import fails."""
    monkeypatch.delenv("BOT_TOKEN", raising=False)
    monkeypatch.setenv("DJANGO_SETTINGS_MODULE", "config.settings.prod")
    # Then force reload...
```

But this is fragile because `DJANGO_SETTINGS_MODULE=` is already set in the test env. The function-extraction approach is more robust.

### 4.5 Best Practices for Settings Tests

**Verified against Django's own test suite** ([`tests/settings_tests/tests.py`](https://github.com/django/django/blob/main/tests/settings_tests/tests.py)) and [pytest-django docs](https://pytest-django.readthedocs.io/en/stable/configuring_django.html):

1. **Use `SimpleTestCase`** — settings validation is a pure-logic, no-database operation. The project follows this convention already (`test_context_processors.py`, `test_language_middleware.py`).
2. **Use `monkeypatch` for env vars** — `monkeypatch.setenv()` / `monkeypatch.delenv()` are automatically cleaned up after each test. Never use `os.environ` directly in tests.
3. **For import-time validation:** Extract the validation logic into a function and test the function directly. Testing module-import side effects requires `importlib.reload` which is fragile and can leave `sys.modules` in an inconsistent state.
4. **Use `override_settings` fixture (pytest-django)** — The `settings` fixture from `pytest-django` can modify settings at runtime: `def test_x(settings): settings.DEBUG = False`. This works for code that reads `settings.DEBUG` at runtime, not at import time.
5. **For deployment checks:** Use `call_command("check", "--deploy", "-t myapp")` and assert on `stderr` output, per [Django system check testing example](https://docs.djangoproject.com/en/5.2/topics/checks/#testing-checks).

---

## 5. Dead Code Removal: 0-byte Git-tracked Stubs

### 5.1 Current State

**Confirmed dead code (HIGH confidence, git evidence):**

| File | Size (bytes) | Git blob hash |
|---|---|---|
| `entrypoint.sh` | 0 | `e69de29bb2d1d6434b8b29ae775ad8c2e48c5391` |
| `entrypoint-test.sh` | 0 | `e69de29bb2d1d6434b8b29ae775ad8c2e48c5391` |
| `entrypoint-catalog.sh` | 0 | `e69de29bb2d1d6434b8b29ae775ad8c2e48c5391` |
| `entrypoint-seed.sh` | 0 | `e69de29bb2d1d6434b8b29ae775ad8c2e48c5391` |

All four share the same SHA-1 blob hash (`e69de29...` = git's hash for an empty file). They were introduced in commit `8d66138` ("fix(docker):uv not found") as empty placeholder files.

### 5.2 The Real Scripts Live in `docker/`

| File | Size (bytes) | Referenced By |
|---|---|---|
| `docker/entrypoint.sh` | ~1.7 KB | `Dockerfile:151` ENTRYPOINT, compose `entrypoint: /app/entrypoint-catalog.sh` |
| `docker/entrypoint-test.sh` | ~1.5 KB | `docker-compose.test.yml:50,71` |
| `docker/entrypoint-catalog.sh` | ~0.7 KB | `docker-compose.yml:49`, `docker-compose.dev.override.yml:37` |
| `docker/entrypoint-seed.sh` | ~0.9 KB | `docker-compose.yml:99`, `docker-compose.dev.override.yml:50` |
| `docker/entrypoint-scheduler.sh` | ~6.5 KB | `docker-compose.prod.yml:42` |
| `docker/entrypoint-create-admin.sh` | ~1.8 KB | `docker-compose.yml:73` |

The `Dockerfile:121` copies `docker/entrypoint*.sh` into `/app/` and the compose files explicitly bind-mount `./docker/entrypoint*.sh:/app/entrypoint*.sh`, overriding any root-level stubs in the dev override.

### 5.3 Verification: No References to Root Stubs

**Grepped all `.yml`, `.yaml`, `.py`, `.sh`, `.md`, `.toml` files** for any reference to the root-level stubs. The only matches are:
- `docker-compose.yml` lines 49, 99 → `/app/entrypoint-catalog.sh`, `/app/entrypoint-seed.sh` (the **container** path, populated from `docker/` by the Dockerfile or bind-mount)
- `docker-compose.test.yml` line 50 → `/app/entrypoint-test.sh` (container path)
- `docker-compose.dev.override.yml` lines 37, 40, 50, 53 → `/app/entrypoint-*.sh` (container paths) + `./docker/entrypoint-*.sh:/app/entrypoint-*.sh` (bind-mounts)

**None** of these reference the root-level `./entrypoint-*.sh` stubs. The `Dockerfile:54` `COPY . .` copies everything from the build context root, but `.dockerignore:5` (`.env*`) excludes `.env` files, and the Dockerfile only `COPY`s `docker/entrypoint*.sh` explicitly (line 121), not the root stubs.

### 5.4 Recommended Removal Procedure

**Best-practice dead code removal (HIGH confidence, cross-referenced with [cr0x.net](https://cr0x.net/en/docker-compose-env-file-mistakes/) and standard Git hygiene):**

```bash
# 1. Verify they're truly unreferenced (already done above)
git ls-files '*entrypoint*'

# 2. Check for any remaining references in non-YAML files
grep -r 'entrypoint\.' --include='*.py' --include='*.sh' --include='*.md' --include='*.toml' .

# 3. Remove via git rm (preserves git history awareness)
git rm entrypoint.sh entrypoint-test.sh entrypoint-catalog.sh entrypoint-seed.sh

# 4. Commit
git commit -m "chore: remove dead 0-byte root entrypoint stubs (CFG-007)"
```

**Why `git rm` instead of `rm` + `git add`?** `git rm` stages the deletion in a single step and works correctly with tracked files. Since these files contain no content, there's no risk of losing real code.

---

## 6. Summary & Prioritized Recommendations

### Already Documented in Project Audit

The `.ai/audit/02-config-secrets/findings.md` file already identified all five issues (CFG-001 through CFG-007). The findings are accurate and the recommendations match the research below. **No new findings were discovered** — this research validates and refines the existing audit.

### Prioritized Action List

| Priority | Finding | Action | Effort |
|---|---|---|---|
| **P0** | CFG-002 | Replace `:-placeholder` / `:-postgres` with `${VAR:?message}` in compose for `DJANGO_SECRET_KEY`, `POSTGRES_PASSWORD`, `BOT_TOKEN` (prod) | Small |
| **P0** | CFG-001 | Remove `default=""` from `BOT_TOKEN` env schema; add `if not BOT_TOKEN and not DEBUG: raise ImproperlyConfigured(...)` guard; fix misleading comment in `main.py:23-24` | Small |
| **P0** | CFG-004 | Fix `entrypoint-scheduler.sh:8` to check `/app/src/.env` (not `/app/.env`); or source shared `check_env_file` from `entrypoint.sh` | Trivial |
| **P0** | CFG-003 | Add `.env.docker` to `.gitignore`; keep `.env.docker.example` as tracked template; document that `.env.docker` is runtime-only | Small |
| **P1** | CFG-005 | Add `test_settings_validation.py` using `SimpleTestCase` + `monkeypatch` for missing-key rejection and BOT_TOKEN policy tests | Small |
| **P1** | CFG-007 | `git rm entrypoint.sh entrypoint-test.sh entrypoint-catalog.sh entrypoint-seed.sh` | Trivial |
| **P2** | CFG-006 | Update `docs/ops/docker-deployment.md:396` — Test `DEBUG = True` (not `False`) | Trivial |

### Cross-cutting Recommendation: Three-Layer Defense

Following the pattern from [LocalEnvAuto](https://www.local-environment-automation.com/environment-sync-secrets-ci-parity/environment-variable-validation/catching-missing-env-vars-before-container-startup/):

1. **Compose interpolation layer** (`${VAR:?message}`) — catches missing vars at `docker compose up` time.
2. **Entrypoint script layer** (shared `check_env_file`) — catches missing vars at container boot, even outside Compose.
3. **Django settings layer** (`env("VAR")` without default) — the authoritative guard that fires on `django.setup()`.

All three should be kept in sync: a JSON schema (`env-schema.json`) as single source of truth, with the Compose `:?` guards and the entrypoint `REQUIRED` array derived from it. This is a future-state recommendation (MEDIUM confidence) — the project currently doesn't have a schema file, and introducing one adds complexity. The immediate-priority is applying `:?` to the compose files and the settings guard for BOT_TOKEN.

---

**Sources consulted (all verified):**
- [Docker Compose Interpolation spec](https://docs.docker.com/reference/compose-file/interpolation/) — `${VAR:?err}` syntax semantics
- [Compose Specification interpolation](https://compose-spec.github.io/compose-spec/12-interpolation.html) — colon vs non-colon variants
- [docker/compose#3768](https://github.com/docker/compose/issues/3768) — empty-string vs unset behavior
- [docker/compose env_file optional `required: false`](https://docs.docker.com/compose/how-tos/environment-variables/set-environment-variables) — v2.24+ feature
- [django-environ source + docs](https://github.com/joke2k/django-environ) — `ImproperlyConfigured` behavior, `read_env` graceful-missing handling
- [Django 5.2 System Check Framework](https://docs.djangoproject.com/en/5.2/topics/checks/) — custom checks, deploy=True, testing via `call_command("check", ...)`
- [Django 5.2 Settings documentation](https://docs.djangoproject.com/en/5.2/topics/settings/) — settings module lifecycle
- [Django settings_tests/tests.py (source)](https://github.com/django/django/blob/main/tests/settings_tests/tests.py) — `override_settings` + `SimpleTestCase` patterns
- [pytest monkeypatch docs](https://docs.pytest.org/en/stable/how-to/monkeypatch.html) — `setenv`/`delenv` for env var testing
- [pytest-django settings docs](https://pytest-django.readthedocs.io/en/stable/configuring_django.html) — `settings` fixture for runtime overrides
- [Django 5.2 test utils source](https://github.com/django/django/blob/stable/5.2.x/django/test/utils.py) — `override_settings` internals
- Project source code: `docker-compose.yml`, `docker-compose.prod.yml`, `docker-compose.test.yml`, `docker-compose.dev.override.yml`, `docker/entrypoint*.sh`, `src/backend/config/settings/base.py|prod.py|dev.py|test.py`, `.github/workflows/ci.yml`, `pyproject.toml`, `Makefile`, `.env.*`, `.gitignore`