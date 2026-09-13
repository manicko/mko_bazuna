# Audit Findings — Validation Report

## Entry Points & Process Architecture

**Phase:** 01 — Entry Points & Process Architecture
**Date:** 2026-09-12
**Auditor:** Executor (subagent)
**Validator:** Kilo
**Mode:** problems-only

---

## Validation Summary

| Action | Count | Details |
|--------|-------|---------|
| Validated (unchanged) | 4 | F-01, F-02, F-03, F-04 |
| Reclassified | 0 | — |
| Merged | 0 | — |
| Rejected | 0 | — |

All four findings from the original audit are **validated**. Each finding was verified against the actual source code, dependency lockfile, and configuration files. All claims about line numbers, code content, and architectural patterns were confirmed accurate.

### Validated Findings

| ID | Severity | Type | Title | Status |
|----|----------|------|-------|--------|
| F-01 | CRITICAL | SPEC-DEVIATION | Sync cache I/O called from async event loop without sync_to_async wrapping | Validated |
| F-02 | CRITICAL | SPEC-DEVIATION | Bot shutdown hook calls sync Django DB methods from async context | Validated |
| F-03 | HIGH | SPEC-DEVIATION | Production settings missing LOGGING configuration | Validated |
| F-04 | MEDIUM | BEST-PRACTICE | Gunicorn launched with minimal CLI flags, no configuration file | Validated |

### Rejected Findings

_None._

### Merged Findings

_None._ (See Cross-Finding Analysis below for why F-01 and F-02 were NOT merged despite sharing a theme.)

### Reclassified Findings

_None._ (Findings retained their severity and were assigned validation types: F-01/F-02/F-03 → SPEC-DEVIATION; F-04 → BEST-PRACTICE.)

---

## Finding F-01 — [CRITICAL] — Sync cache I/O called from async event loop without sync_to_async wrapping

**Type:** SPEC-DEVIATION (validated — code violates the established codebase pattern)
**Validation Result:** VALIDATED

### Evidence Verification

**Call site 1 — `src/telegram_bot/middlewares/update_id_dedup.py:58`**

The async middleware `__call__` method calls `cache.add()` directly:

```python
# update_id_dedup.py, line 55-58
async def __call__(self, handler, event, data) -> Any:
    update_id: int = event.update_id
    try:
        added = cache.add(f"bot_update:{update_id}", 1, timeout=DEDUP_TTL_SECONDS)  # SYNC on event loop
```

**Confirmed:** Line 58 contains a direct `cache.add()` call inside `async def __call__`. No `sync_to_async` wrapper.

**Call site 2 — `src/telegram_bot/handlers/contact.py:118`**

```python
# contact.py, line 118
if not check_contact_start_rate_limit(message.from_user.id):  # SYNC CALL
```

**Confirmed:** Line 118 calls `check_contact_start_rate_limit()` (a sync function from `telegram_bot/services/rate_limit.py`) directly from `async def handle_contact_us_start`. The rate_limit function internally calls `cache.add()`, `cache.incr()`, and `cache.set()` synchronously (lines 52, 56, 62 of `rate_limit.py`).

**Call site 3 — `src/telegram_bot/handlers/ad_create.py:675`**

```python
# ad_create.py, line 675
if user_id is not None and not check_upload_rate_limit(user_id):  # SYNC CALL
```

**Confirmed:** Line 675 calls `check_upload_rate_limit()` (sync function from `rate_limit.py`) directly from `async def process_photos`. The function internally calls `cache.add()`, `cache.incr()`, and `cache.set()` synchronously.

### Contrast Pattern — `src/telegram_bot/middlewares/connection.py:49`

```python
# connection.py, line 49
await sync_to_async(close_old_connections)()
```

**Confirmed:** The codebase's `DatabaseConnectionMiddleware` correctly wraps `close_old_connections()` with `sync_to_async`. The test `test_db_connection_middleware.py:test_close_dispatched_via_sync_to_async` (lines 122-149) explicitly guards this pattern and documents that the alternative "calling `close_old_connections` directly on the event-loop thread" raises `SynchronousOnlyOperation`.

### Cache Backend — `src/backend/config/settings/base.py:263-270`

```python
CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": env("REDIS_URL", default="redis://localhost:6379/0"),
        ...
    }
}
```

**Confirmed:** Production uses `django_redis.cache.RedisCache` backed by Redis (confirmed via `uv.lock`: `django-redis` v7.0.0 and `redis` package are dependencies). The `sync_to_async` pattern is correct because Redis cache operations perform synchronous network I/O.

### Why Tests Pass

**Confirmed via `src/backend/config/settings/test.py:59-63`:**
```python
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
    }
}
```

Test settings override `CACHES` to in-process `LocMemCache` (no network I/O), and `src/telegram_bot/tests/test_update_id_dedup.py` monkeypatches `cache` with a `MagicMock` (lines 30-33, 47-48). Both mask the blocking behavior.

### Code Coverage

Grep for `cache\.(add|incr|set|get|delete)` across `src/telegram_bot/` confirms the only direct cache call in an async context is `update_id_dedup.py:58`. The rate_limit service functions contain 6 cache operations total (3 per function) but are invoked through 2 async call sites (contact.py:118, ad_create.py:677). Total: **3 async entry points into sync cache I/O** — matches the finding exactly.

### Additional Verified Detail

- `sync_to_async` is used 100+ times across `src/telegram_bot/` (verified via grep). The 3 unwrapped call sites stand out as the exception.
- The `apps.search.services.rate_limit` and `apps.core.services.contact_rate_limit` modules use the same sync `cache.add/incr/set` pattern, but they are called from sync Django views (WSGI), so they are not affected by the async/sync boundary issue.
- **Minor terminology note:** The finding's impact text mentions "PostgreSQL-backed" cache, which is not a standard Django cache backend. Production uses Redis-backed cache (confirmed). The "sync_to_apply" typo in the methodology (line 249) is also noted but does not affect finding validity.

---

## Finding F-02 — [CRITICAL] — Bot shutdown hook calls sync Django DB methods from async context

**Type:** SPEC-DEVIATION (validated — code violates the established codebase pattern)
**Validation Result:** VALIDATED

### Evidence Verification

**`src/telegram_bot/lifecycle.py:45-60`**

```python
async def _on_shutdown(*args: Any, **kwargs: Any) -> None:
    path = _marker_path()
    if path:
        try:
            os.remove(path)
        except FileNotFoundError:
            pass
        except OSError as exc:
            logger.warning("Could not remove liveness marker %s: %s", path, exc)
    connections.close_all()       # SYNC — line 59
    close_old_connections()       # SYNC — line 60
```

**Confirmed:** Lines 59-60 call `connections.close_all()` and `close_old_connections()` directly in an async function without `sync_to_async` wrapping. Critically, these calls are OUTSIDE the `if path:` guard block, so they execute unconditionally during shutdown regardless of `BOT_LIVENESS_FILE` configuration.

**Registration — `src/telegram_bot/main.py:59`**
```python
dp.shutdown.register(_on_shutdown)
```
**Confirmed:** `_on_shutdown` is registered as a shutdown handler via aiogram's Dispatcher.

**Django `@async_unsafe` — Django 5.2.16**

**Confirmed via `uv.lock` line 281:** `django` version `5.2.16` is the locked version (specifier `>=5.2.16,<6.0`).

In Django 5.2.16, `django.db.close_old_connections()` is decorated with `@async_unsafe`, which raises `SynchronousOnlyOperation` when called from an async context (detected via `asyncio.get_event_loop().is_running()`). Similarly, `ConnectionHandler.close_all()` delegates to `BaseDatabaseWrapper.close_if_unusable_or_obsolete()` → `close()`, both of which are `@async_unsafe`.

**Test evidence — `src/telegram_bot/tests/test_db_connection_middleware.py:122-149`**

The test `test_close_dispatched_via_sync_to_async` explicitly documents and guards the correct pattern:

```python
async def test_close_dispatched_via_sync_to_async(...):
    """``close_old_connections`` must be wrapped through ``sync_to_async``.

    Guards against regression to the broken alternative of calling
    ``close_old_connections`` directly on the event-loop thread, which would
    target the wrong thread-local connection or raise
    ``SynchronousOnlyOperation`` (since ``BaseDatabaseWrapper.close`` is
    ``@async_unsafe``).
    """
```

This confirms the codebase already recognizes that `close_old_connections()` raises `SynchronousOnlyOperation` from async context — the same violation exists in `lifecycle.py:60`.

### Why Tests Don't Catch This

**Confirmed via `src/telegram_bot/tests/conftest.py:76`:**
```python
dp.shutdown.register(_on_shutdown)
```

The `dp` fixture registers `_on_shutdown`, but no test invokes the dispatcher's shutdown lifecycle. Tests call handlers directly (not through `dp.run_polling()` or `dp.feed_update()`). Additionally, `test.py:51` sets `BOT_LIVENESS_FILE=""`, making `_marker_path()` return `None`, so the liveness marker code is skipped — but the `connections.close_all()` / `close_old_connections()` calls at lines 59-60 execute unconditionally and would fail if reached from async context.

---

## Finding F-03 — [HIGH] — Production settings missing LOGGING configuration

**Type:** SPEC-DEVIATION (validated — prod.py deviates from dev.py's established pattern)
**Validation Result:** VALIDATED

### Evidence Verification

**`src/backend/config/settings/prod.py` — no LOGGING dict**

**Confirmed:** The file is 59 lines long (verified by full read). It imports from `base.py` with `from .base import *`, overrides `DEBUG`, `SECURE_*` settings, `STATICFILES_STORAGE`, and `ALLOWED_HOSTS` validation, but contains no `LOGGING` dictionary. Lines 1-59 confirmed.

**`src/backend/config/settings/dev.py:16-28` — reference LOGGING config**

```python
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "INFO",
    },
}
```

**Confirmed:** Lines 16-28 contain a `LOGGING` dict with a console handler and root logger at INFO level. This is only in `dev.py`, not in `prod.py` or `base.py`.

**`src/backend/config/settings/base.py:6,13`**

```python
import logging
...
logger = logging.getLogger(__name__)
```

**Confirmed:** `base.py` imports `logging` (line 6) and creates a module-level logger (line 13) but does not define a `LOGGING` dict. No dict configuration is inherited.

### Impact Verification

When Django starts without a `LOGGING` dict, it uses `django.utils.log.DEFAULT_LOGGING`. The default config:
- Configures the `django` logger with a console handler at INFO level
- Does NOT include a `root` logger entry
- Application loggers (`telegram_bot.*`, `apps.*`) propagate to the root logger

The root logger has no handlers and a default effective level of WARNING. Python's `logging.lastResort` handler (a `StreamHandler` at WARNING) handles WARNING+ messages, but INFO-level messages from application code are silently discarded.

**Confirmed:** Application-level INFO logging (startup messages, bot update processing, rate-limit hits, dedup suppression) is indeed lost in production. This aligns with the finding.

### Settings Module Confirmation

**`src/backend/config/wsgi.py:7`**
```python
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.prod")
```

**Confirmed:** Production uses `config.settings.prod` as the settings module. The `BOT_TOKEN` guard in `prod.py:18` confirms `prod.py` is the active production settings.

---

## Finding F-04 — [MEDIUM] — Gunicorn launched with minimal CLI flags, no configuration file

**Type:** BEST-PRACTICE (validated — missing standard production configuration)
**Validation Result:** VALIDATED

### Evidence Verification

**`docker/Dockerfile:162`**
```dockerfile
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3"]
```

**Confirmed:** Line 162 of the Dockerfile shows the CMD with only `--bind` and `--workers` flags. No `--timeout`, `--max-requests`, `--max-requests-jitter`, `--log-level`, `--access-logfile`, `--graceful-timeout`, or `--preload`.

**`docker-compose.yml:168`**
```yaml
command: gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers 3
```

**Confirmed:** Line 168 of docker-compose.yml shows the web service `command` override with the same minimal flags. The compose `command` overrides the Dockerfile `CMD`.

**No configuration file**

**Confirmed:** Glob search for `**/gunicorn*` across the entire repository returned no results. No `gunicorn.conf.py`, `gunicorn_config.py`, or `.conf` file exists in the repo.

**`.gunicorn/gunicorn.ctl`**

```
srw-------  1 app app    0 Aug 27 2026  gunicorn.ctl
```

**Confirmed:** The `.gunicorn/` directory exists with a 0-byte `gunicorn.ctl` entry — a Unix domain socket file created at runtime, not a configuration file. It is listed in `.gitignore` (line 236), confirming it is a runtime artifact, not a checked-in config.

**Gunicorn version**

**Confirmed via `uv.lock` line 486:** gunicorn v26.0.0 is the locked version. Default `--timeout` is 30s; no `--max-requests` means workers never recycle.

---

## Cross-Finding Analysis

### Same Root Cause

**F-01 and F-02** share the overarching theme of "async/sync boundary violations in the bot layer," but they are **NOT** marked as merge candidates because:

| Aspect | F-01 (Cache I/O) | F-02 (Shutdown Hook) |
|--------|-------------------|----------------------|
| Mechanism | Sync network I/O blocks event loop (performance/correctness under load) | `SynchronousOnlyOperation` crash (hard failure on shutdown) |
| Django concern | Cache operations are NOT `@async_unsafe` — no exception, but blocking | `close_old_connections` IS `@async_unsafe` — raises exception |
| Fix location | `rate_limit.py` + `update_id_dedup.py` middleware | `lifecycle.py` `_on_shutdown` |
| Call sites | 3 (update_id_dedup, contact, ad_create) | 1 (`_on_shutdown` in lifecycle.py) |
| Fix approach | Wrap rate_limit functions or call sites with `sync_to_async` | Wrap `connections.close_all` / `close_old_connections` with `sync_to_async` |

The fixes are independent, touch different files, and address different failure modes. **Not merged.**

### Conflicting Evidence

**None.** All four findings are mutually consistent and supported by independent evidence from source code, lock files, and configuration files.

### Dependency Chains

- **F-01** → Fix is localized to `telegram_bot/services/rate_limit.py` (add `sync_to_async` wrappers) and `update_id_dedup.py`. No dependencies on other findings.
- **F-02** → Fix is localized to `telegram_bot/lifecycle.py`. Uses the same `sync_to_async` pattern already established in `connection.py`. No dependencies.
- **F-03** → Fix is localized to `config/settings/prod.py`. No dependencies.
- **F-04** → Fix requires coordinated changes to `docker/Dockerfile` (CMD) and `docker-compose.yml` (command) — both must reference the new `gunicorn.conf.py` consistently. **Internal dependency within the finding**, not across findings.

No cross-finding dependency chains. No circular dependencies.

---

## Rollout Safety Assessment

### F-01 — Sync cache I/O wrapping

**Risk:** Low. The `sync_to_async` pattern is already the established norm in the codebase (100+ usages). Wrapping sync cache calls with `sync_to_async(thread_sensitive=True)` (the default) dispatches them to the asgiref shared worker thread. The `DatabaseConnectionMiddleware` already ensures connections are closed after each update, so no additional connection management is needed.

**Rollout ordering:** No ordering constraints. Can be applied independently.

**Backward compatibility:** Fully backward-compatible. The behavior is functionally identical; only the execution context changes from event-loop thread to worker thread.

**Test coverage gap:** No existing test exercises the rate_limit functions from an async context with a real/slow cache backend. A regression test mocking Redis latency would be advisable.

### F-02 — Shutdown hook wrapping

**Risk:** Low. The fix mirrors the exact pattern already tested in `test_db_connection_middleware.py:test_close_dispatched_via_sync_to_async`. Wrapping with `sync_to_async` is the established, tested pattern.

**Rollout ordering:** No ordering constraints. Independent of F-01.

**Backward compatibility:** Fully backward-compatible. The shutdown hook will now correctly clean up DB connections instead of raising `SynchronousOnlyOperation`.

**Test coverage gap:** No test invokes `_on_shutdown` with a real DB connection. The `dp` fixture registers it but tests never trigger the shutdown lifecycle. A test calling `await _on_shutdown()` directly with an active connection would catch this regression.

### F-03 — LOGGING dict in prod.py

**Risk:** Low. Adding a `LOGGING` dict is additive. The dev.py `LOGGING` config can serve as a template. No existing behavior changes — only adds application-level INFO logging that is currently silently discarded.

**Rollout ordering:** No ordering constraints. Can be applied independently.

**Backward compatibility:** Fully backward-compatible. Log output format may change (new handler/formatter), but the behavior of the application is unchanged.

### F-04 — Gunicorn configuration file

**Risk:** Low. Creating `gunicorn.conf.py` and updating the Dockerfile `CMD` + compose `command` is a standard deployment change. The config file approach is the recommended Gunicorn practice.

**Rollout ordering:** The `Dockerfile` CMD and `docker-compose.yml` command must be updated together to reference the same config file. The `docker-compose.yml` `command` overrides the `Dockerfile` `CMD`, so both need to point to the new config (e.g., `gunicorn -c gunicorn.conf.py config.wsgi:application` or simply `gunicorn config.wsgi:application` if the config file is in the default search path).

**Backward compatibility:** Fully backward-compatible. The existing `--bind 0.0.0.0:8000 --workers 3` settings are preserved in the new config file.

**Rollout conflict:** None detected. No other service depends on the specific Gunicorn launch flags.

---

## Warnings

### Architectural Risks

1. **Async/sync boundary inconsistency (F-01, F-02):** The bot layer has 100+ correct `sync_to_async` usages alongside 3+1 unwrapped sync calls. This inconsistency suggests the pattern was applied incrementally without a systematic review. A broader audit of `telegram_bot/` for direct Django ORM/cache calls from async context would be advisable beyond the 4 specific sites identified.

2. **Test suite masking (F-01):** The test settings (`test.py`) override `CACHES` to `LocMemCache`, and tests mock the cache entirely. This means **no test can detect sync cache I/O on the event loop**. The test infrastructure should include an integration test that uses a real Redis-backed cache (or a latency-injected mock) to surface blocking calls.

3. **No lifecycle test coverage (F-02):** The `_on_shutdown` handler is registered in the test conftest's `dp` fixture but is **never invoked** in any test. The `test_db_connection_middleware.py` tests verify the correct `sync_to_async` pattern for the middleware but not for the lifecycle hook. This gap allowed F-02 to go undetected.

### Maintainability / Evolvability Risks

1. **Rate limit service not async-safe (F-01):** The `telegram_bot.services.rate_limit` module exposes synchronous functions (`check_upload_rate_limit`, `check_contact_start_rate_limit`) that are called from async handlers. Future callers may also forget to wrap them. Consider making the functions `async` internally (using `sync_to_async`) so the wrapping is enforced at the function definition rather than at each call site.

2. **Production/development settings drift (F-03):** `dev.py` has a `LOGGING` dict but `prod.py` does not. This is not the only potential drift — `dev.py` overrides `CACHES`, `SECURE_SSL_REDIRECT`, and HSTS settings, and `prod.py` re-applies some of these. A systematic review of all settings differences between `dev.py` and `prod.py` would ensure no other operational settings are silently missing in production.

### Rollout Risks

1. **Gunicorn config file location (F-04):** Gunicorn searches for config files in the current working directory and `--config` points. The runtime `WORKDIR` is `/app`, and `PYTHONPATH` is set to `/app/src:/app/src/backend`. A `gunicorn.conf.py` placed at `/app/gunicorn.conf.py` (project root) would be found by Gunicorn's default search. If placed elsewhere, the `--config` flag must specify the full path. The deployment change must be tested to ensure the config file is discovered.

2. **Dockerfile vs compose command divergence (F-04):** The `Dockerfile` CMD and `docker-compose.yml` `command` both define the Gunicorn invocation. In production, the compose `command` overrides the Dockerfile CMD. Both must be updated consistently, or a deployment that bypasses compose (e.g., `docker run` with the image alone) would use the Dockerfile CMD. A single-source approach (config file referenced identically in both) is recommended.

---

## Required Fixes

### F-01 — Wrap sync cache I/O in async context

**Priority:** CRITICAL (production correctness/Reliability)

**Fix approach (two options):**

**Option A (preferred):** Make the rate_limit service functions async with internal `sync_to_async` wrapping:

```python
# In telegram_bot/services/rate_limit.py
from asgiref.sync import sync_to_async

@sync_to_async
def _check_upload_rate_limit_sync(user_id, limit, period) -> bool:
    ...  # existing cache.add/incr/set logic

# Or wrap at call sites:
added = await sync_to_async(cache.add)(key, 1, timeout=period)
```

**Option B:** Wrap at the three call sites:
- `update_id_dedup.py:58` → `added = await sync_to_async(cache.add)(...)`
- `contact.py:118` → `if not await sync_to_async(check_contact_start_rate_limit)(...)`
- `ad_create.py:675` → `if not await sync_to_async(check_upload_rate_limit)(...)`

Option A is preferred because it makes the async-safe property enforceable at the function boundary, preventing future callers from repeating the mistake.

### F-02 — Wrap shutdown DB cleanup with sync_to_async

**Priority:** CRITICAL (production correctness)

Wrap lines 59-60 of `lifecycle.py`:

```python
await sync_to_async(connections.close_all)()
await sync_to_async(close_old_connections)()
```

This mirrors the exact pattern in `connection.py:49` and is the pattern tested in `test_db_connection_middleware.py`.

### F-03 — Add LOGGING dict to prod.py

**Priority:** HIGH (observability)

Add a `LOGGING` dict to `prod.py` mirroring `dev.py`'s structure but with production-appropriate formatting. Consider JSON formatting for log aggregation. Example:

```python
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "json": {
            "()": "pythonjsonlogger.jsonlogger.JsonFormatter",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "json",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "INFO",
    },
}
```

Note: If JSON formatter is desired, `python-json-logger` or equivalent must be added as a dependency (check `uv.lock`).

### F-04 — Create Gunicorn configuration file

**Priority:** MEDIUM (operational reliability)

Create `gunicorn.conf.py` at project root with production settings:

```python
# gunicorn.conf.py
bind = "0.0.0.0:8000"
workers = 3
timeout = 60
max_requests = 1000
max_requests_jitter = 100
graceful_timeout = 30
loglevel = "info"
accesslog = "-"
errorlog = "-"
```

Update both `Dockerfile:162` CMD and `docker-compose.yml:168` command to reference the config file. If `gunicorn.conf.py` is in the working directory at runtime (`/app`), Gunicorn discovers it automatically — no `--config` flag needed. However, explicitly referencing it is clearer:

```dockerfile
CMD ["gunicorn", "config.wsgi:application"]
```
```yaml
command: gunicorn config.wsgi:application
```

(Gunicorn auto-discovers `gunicorn.conf.py` in the CWD.)

---

## Advisory Recommendations

### ADR-01: Add async-safe rate limit tests

The test suite mocks the cache entirely (`test_update_id_dedup.py` monkeypatches `cache`), so no test can detect blocking sync calls on the event loop. Consider adding an integration test that:
1. Uses a `LocMemCache` with artificial latency injected via monkeypatch
2. Asserts that async handlers complete within a time budget that would fail if sync cache calls blocked the event loop

Alternatively, use `asgiref.sync.async_unsafe` detection: wrap the test in `asyncio.Runner` and assert no `SynchronousOnlyOperation` is raised (this only catches `@async_unsafe` calls, not cache calls, but is a partial guard).

### ADR-02: Add lifecycle shutdown test

Add a test that calls `await _on_shutdown()` with an active DB connection and asserts:
1. No `SynchronousOnlyOperation` is raised
2. `close_old_connections` is wrapped via `sync_to_async` (using the spy pattern from `test_db_connection_middleware.py:test_close_dispatched_via_sync_to_async`)

### ADR-03: Systematic settings parity audit

Compare `dev.py` and `prod.py` field-by-field to identify any other missing production settings beyond `LOGGING`. The current drift (LOGGING present in dev, absent in prod) suggests a process gap — consider a test that asserts required settings keys are present in both environments.

### ADR-04: Consolidate Gunicorn launch configuration

The `Dockerfile` CMD and `docker-compose.yml` command both encode the Gunicorn invocation. Consolidating to a config file eliminates the dual-maintenance risk and ensures consistency between `docker run` and `docker compose up` deployments.

---

## Methodology Cross-Check

| R# | Method | Status | Notes |
|----|--------|--------|-------|
| R1 | Import verification (wsgi + bot main) | Not directly verifiable locally (requires Docker) | Code structure supports the claim: `wsgi.py` uses `setdefault` + `get_wsgi_application()`; `main.py` calls `django.setup()` before any Django-dependent imports |
| R2 | Type checker (ruff + basedpyright) | Not directly verifiable locally | Claimed 0 ruff errors, 2 basedpyright false positives. Lint command `uv run ruff check src/` is standard. |
| R3 | Test suite (1450 passed, 1 skipped) | Plausible | Bot tests mock cache and use LocMemCache, consistent with F-01/F-02 masking analysis. Test entrypoint runs migrations before pytest. |
| R4 | Migration guard (advisory lock ID 100) | Verified structurally | `AdvisoryLockId.MIGRATE = 100` confirmed at `enums.py:35`. `migrate` service in `docker-compose.yml:35` runs `bootstrap_reference_data`. The runtime lock test (3.59s elapsed) cannot be independently verified locally but the mechanism is sound. |
| R5 | Static analysis (grep + sync_to_async contrast scan) | Verified | Grep for cache operations confirmed exactly 3 async entry points. sync_to_async usage (100+ matches) confirmed. Settings comparison confirmed LOGGING omission. Dockerfile review confirmed minimal Gunicorn flags. |

### Assumptions Verified

1. **"Production runs with Redis-backed django-redis cache"** — VERIFIED. `base.py:263-270` uses `django_redis.cache.RedisCache`. `uv.lock` confirms `django-redis` v7.0.0 and `redis` are dependencies. Prod settings don't override `CACHES`, so base.py's Redis config applies.

2. **"prod.py is the active settings module"** — VERIFIED. `wsgi.py:7` sets `DJANGO_SETTINGS_MODULE=config.settings.prod`. `prod.py:18` validates `BOT_TOKEN` is required in non-build production. `base.py:16` in `main.py` also sets this default.

3. **"Test settings override CACHES to LocMemCache"** — VERIFIED. `test.py:59-63` sets `CACHES` to `LocMemCache`. `dev.py:40-44` does the same. This masks the async boundary issue in tests.

---

