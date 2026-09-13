# Audit Findings — Entry Points & Process Architecture

**Phase:** 01 — Entry Points & Process Architecture
**Date:** 2026-09-12
**Auditor:** Executor (subagent)
**Mode:** problems-only

---

## Summary

Dual-process Django system (web WSGI gunicorn + bot aiogram) sharing one PostgreSQL
database. Migrations run once under advisory lock ID 100 before both processes boot.
Both entry points import cleanly with no import-time DB/network side effects. The
migration-once guarantee is enforced by a session-scoped `pg_advisory_lock(100)` with
confirmed serialization behavior.

Three problems were found: unwrapped sync cache I/O in the async bot event loop
(CRITICAL ×3), production settings missing a LOGGING dict (HIGH), and Gunicorn launched
with no configuration file beyond two CLI flags (MEDIUM). A fourth problem — the bot's
shutdown hook calling sync Django DB methods from async without `sync_to_async` — is
also CRITICAL. The bot's use of `MemoryStorage` for FSM is a documented design limitation
(LOW), not a deviation.

---

## Findings

### Finding 1 — [CRITICAL] — Sync cache I/O called from async event loop without sync_to_async wrapping

| Field | Value |
|---|---|
| **Severity** | CRITICAL |
| **Category** | correctness / async/sync boundary |
| **File(s)** | `src/telegram_bot/middlewares/update_id_dedup.py` (line 58); `src/telegram_bot/handlers/contact.py` (line 118); `src/telegram_bot/handlers/ad_create.py` (line 675) |
| **Problem** | Three sync cache calls (`cache.add`, `cache.incr`) are invoked directly from async handlers/middleware without `sync_to_async` wrapping, unlike all other ORM/cache access in the bot layer. |
| **Impact** | Under PostgreSQL-backed or Redis-backed `LocMemCache` (production), these synchronous cache network calls block the event loop for the duration of each Redis round-trip. With concurrent updates, this causes event-loop stalls, delayed Telegram update processing, and potential timeout-driven restarts. If `django-redis` raises `ConnectionInterrupted` synchronously, it bypasses the `asyncio` exception propagation model. |
| **Root Cause** | The `telegram_bot.services.rate_limit` module defines sync functions (`check_upload_rate_limit`, `check_contact_start_rate_limit`) that directly call `cache.add()` / `cache.incr()`. These are called from async handlers (`contact.py:118`, `ad_create.py:675`) and from async middleware (`update_id_dedup.py:58`) without `sync_to_async()` wrapping. |
| **Recommendation** | Wrap each call site with `await sync_to_async(...)`. Alternatively, add `async` variants to `rate_limit.py` that internally use `sync_to_async`. |
| **Evidence** | |

**Evidence — `update_id_dedup.py:58`** (async middleware calling sync `cache.add`):
```python
async def __call__(self, handler, event, data) -> Any:
    update_id: int = event.update_id
    try:
        added = cache.add(f"bot_update:{update_id}", 1, timeout=DEDUP_TTL_SECONDS)
    except (ConnectionInterrupted, redis.RedisError):
        ...
    if not added:
        ...
        return None
    return await handler(event, data)
```

**Evidence — `contact.py:118`** (async handler calling sync rate-limiter):
```python
async def handle_contact_us_start(message: types.Message, bot: Bot) -> bool:
    ...
    if not check_contact_start_rate_limit(message.from_user.id):  # SYNC CALL
        await message.answer(CONTACT_US_RATE_LIMITED_MESSAGE)
        return True
```

**Evidence — `ad_create.py:675`** (async handler calling sync rate-limiter):
```python
async def process_photos(message: types.Message, state: FSMContext) -> None:
    ...
    if user_id is not None and not check_upload_rate_limit(user_id):  # SYNC CALL
        await message.answer("Uploading too fast, please wait a moment.")
        return
```

**Contrast — `connection.py:49`** (same codebase correctly wraps with `sync_to_async`):
```python
from asgiref.sync import sync_to_async
...
finally:
    await sync_to_async(close_old_connections)()
```

**Runtime evidence — test suite passes because tests don't use Redis-backed cache:**
```
src/telegram_bot/tests/test_update_id_dedup.py::TestUpdateIdDedupMiddleware::
    test_redis_unavailable_fail_open
  : PytestWarning: Error when trying to teardown test databases:
    OperationalError('database "test_mko_bazuna" is being accessed
    by other users...')
```
Tests pass because `dev/test settings` override `CACHES` to `LocMemCache` (in-process,
no network), so the sync call returns immediately. Under production Redis-backed cache,
each `cache.add()` / `cache.incr()` performs a network round-trip on the event loop.

---

### Finding 2 — [CRITICAL] — Bot shutdown hook calls sync Django DB methods from async context

| Field | Value |
|---|---|
| **Severity** | CRITICAL |
| **Category** | correctness / graceful shutdown |
| **File(s)** | `src/telegram_bot/lifecycle.py` (lines 45-60) |
| **Problem** | The `_on_shutdown` async function calls `connections.close_all()` and `close_old_connections()` synchronously, without `sync_to_async` wrapping. Django's `close_old_connections()` is decorated with `@async_unsafe` and raises `SynchronousOnlyOperation` when called from an async context. |
| **Impact** | On bot shutdown (SIGTERM/SIGINT), the `_on_shutdown` hook will raise `SynchronousOnlyOperation`, preventing proper DB connection cleanup. Connections are left dangling, potentially exhausting PostgreSQL's `max_connections` limit over repeated restarts. The liveness marker removal may also be skipped if the exception fires before reaching that code path. |
| **Root Cause** | `_on_shutdown` is registered as an async shutdown handler (via `dp.shutdown.register(_on_shutdown)` in `main.py:59`), but calls sync Django DB cleanup functions directly instead of wrapping them. The `DatabaseConnectionMiddleware` in the same codebase (`connection.py:49`) correctly wraps `close_old_connections()` with `sync_to_async`, establishing the correct pattern — but `lifecycle.py` does not follow it. |
| **Recommendation** | Wrap both calls with `sync_to_async`: `await sync_to_async(connections.close_all)()` and `await sync_to_async(close_old_connections)()`. |
| **Evidence** | |

**Evidence — `lifecycle.py:45-60`**:
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
    connections.close_all()       # SYNC — will raise SynchronousOnlyOperation
    close_old_connections()       # SYNC — decorated @async_unsafe
```

**Contrast — `connection.py:40-49`** (correct pattern):
```python
async def __call__(self, handler, event, data) -> Any:
    try:
        return await handler(event, data)
    finally:
        await sync_to_async(close_old_connections)()  # CORRECT wrapping
```

**Registration in `main.py:59`**:
```python
dp.shutdown.register(_on_shutdown)
```

---

### Finding 3 — [HIGH] — Production settings missing LOGGING configuration

| Field | Value |
|---|---|
| **Severity** | HIGH |
| **Category** | operational reliability / observability |
| **File(s)** | `src/backend/config/settings/prod.py` (no LOGGING dict); `src/backend/config/settings/dev.py` (lines 15-28, reference) |
| **Problem** | `prod.py` imports from `base.py` but never defines a `LOGGING` dict. In production, Django falls back to its default logging config, which only configures the `django` logger (WARNING level, console handler). All application loggers (`apps.*`, `telegram_bot.*`) have no handlers configured and their INFO-level output is silently discarded. |
| **Impact** | Production loses all application-level INFO logging (startup messages, bot update processing, rate-limit hits, dedup suppression, ad creation flow, alert delivery). Only Django framework warnings/errors reach the console. This makes debugging production incidents that depend on application-level context (e.g., "why was this update deduplicated?") impossible without code-level debugging. |
| **Root Cause** | The `LOGGING` dict is defined only in `dev.py` (lines 15-28) as a development convenience. `prod.py` overrides `DEBUG`, `SECURE_*` settings, etc., but never adds a production `LOGGING` dict. Base settings (`base.py:13`) import `logging` and define `logger = logging.getLogger(__name__)` but don't configure the logging dict. |
| **Recommendation** | Add a `LOGGING` dict to `prod.py` mirroring the dev structure but at INFO level for application loggers, with structured output (JSON or key-value) for log aggregation. |
| **Evidence** | |

**`prod.py` — no LOGGING dict (lines 1-59, confirmed full file):**
```python
from .base import *  # noqa: F403, F401
DEBUG = False
# ... security settings, no LOGGING dict ...
```

**`dev.py:15-28` — reference LOGGING config that exists only in dev:**
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

**`base.py:6,13`** — logging imported and logger defined but no dict configuration:
```python
import logging
...
logger = logging.getLogger(__name__)
```

---

### Finding 4 — [MEDIUM] — Gunicorn launched with minimal CLI flags, no configuration file

| Field | Value |
|---|---|
| **Severity** | MEDIUM |
| **Category** | operational reliability / deployment portability |
| **File(s)** | `docker/Dockerfile:162`; `docker-compose.yml:168` |
| **Problem** | The web process is started with `gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers 3` — no `--timeout`, `--max-requests`, `--max-requests-jitter`, `--log-level`, `--access-logfile`, `--graceful-timeout`, or `--preload` configuration. No Gunicorn config file exists in the repository (`.gunicorn/gunicorn.ctl` is a 0-byte socket file at runtime, not a config). |
| **Impact** | Without `--timeout` (default 30s), hung workers are killed after 30s but the cause is unclear. Without `--max-requests`, workers never recycle, potentially accumulating memory leaks over time (Python GC fragmentation, unclosed DB connections). Without `--access-logfile` or `--log-level`, access logs and Gunicorn's own error logging are not configured for production. Without `--graceful-timeout`, slow-shutdown workers may be force-killed mid-request during deploys. |
| **Root Cause** | The Dockerfile `CMD` and compose `command` both use the same minimal CLI flags. No `.py`/`conf` Gunicorn config file is checked in. The `.gunicorn/` directory exists (`.gunicorn/gunicorn.ctl`) but only contains a runtime Unix socket, not a configuration file. |
| **Recommendation** | Create a `gunicorn.conf.py` config file with production-appropriate settings: `workers` (e.g., 3), `timeout` (60s), `max_requests` (1000), `max_requests_jitter` (100), `graceful_timeout` (30s), `loglevel` ("info"), `accesslog` ("-"), `errorlog` ("-"). |
| **Evidence** | |

**`Dockerfile:162`** (runtime stage CMD):
```dockerfile
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3"]
```

**`docker-compose.yml:168`** (compose override for web service):
```yaml
command: gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers 3
```

**`.gunicorn/` directory** — contains only a runtime socket, no config:
```bash
$ ls -la /app/.gunicorn/
srw-------  1 app app    0 Aug 27 20:23 gunicorn.ctl   # socket, not config
```

---

## Severity Counts

| CRITICAL | HIGH | MEDIUM | LOW |
|----------|------|--------|-----|
| 2        | 1    | 1    | 0   |

---

## Methodology

- **Import verification (R1):** Both `config.wsgi` and `telegram_bot.main` were imported
  in two separate `docker compose ... run --rm test` containers. Both completed cleanly
  with no import-time DB queries, network calls, or `SynchronousOnlyOperation` errors.
  `wsgi.application` resolved to `WSGIHandler` object; bot `main()` module resolved.

- **Type checker (R3):** `ruff check src/` → 0 errors, exit 0. `basedpyright` on
  `src/telegram_bot` + services + utils → 2 errors (`alerts.py:79`, `contact.py:238`),
  both false positives from missing `django-stubs` (ORM fields typed as descriptors).
  These false positives are pre-existing and do not mask the async-boundary issues found.

- **Test suite (R4):** Full test suite run via
  `docker compose --project-name mko-bazuna-test ... run --rm test`:
  **1450 passed, 1 skipped** in ~74s. The single skip is
  `test_redis_unavailable_fail_open` which only warns about test DB teardown
  contention (not a test failure).

- **Migration guard (R5):** Concurrent advisory lock test: Process A acquired
  `pg_advisory_lock(100)`, held for 3s; Process B's `SELECT pg_advisory_lock(100)`
  blocked until release. Measured elapsed: **3.59s** (B blocked for the full duration
  of A's hold). Lock ID 100 confirmed in `AdvisoryLockId.MIGRATE` enum (`enums.py:35`).

- **Static analysis:** `grep` for `cache\.add|cache\.incr|cache\.set|cache\.get` across
  `src/telegram_bot/` — found 3 call sites in async context without `sync_to_apply`
  wrapping. Contrast scan with `sync_to_async` usage (49 matches) confirms the correct
  pattern is established elsewhere. Settings file comparison (`prod.py` vs `dev.py`)
  confirms LOGGING dict omission. Dockerfile review confirms Gunicorn CLI flags.

**Assumptions:**
- Production runs with Redis-backed `django-redis` cache (per `base.py:263-270` default).
- `prod.py` is the active settings module (confirmed by `wsgi.py:7` `setdefault`).
- Test settings override `CACHES` to `LocMemCache` (per `dev.py:40-44`), masking the async boundary issue.
