# Research Report: ENT-005 — Bot Docker Healthcheck Readiness Probe

## 1. Executive Summary

**Finding:** The bot container healthcheck (`docker-compose.yml:190`) is `kill -0 1` — pure PID liveness. It does not verify that the bot has reached the polling loop, that the Django ORM is functional, or that updates are being received.

**Chosen solution:** **Approach A — File-based liveness marker** (the audit's selected approach). A new `src/telegram_bot/lifecycle.py` module holds:
- `_on_startup` — writes a timestamped marker file at `settings.BOT_LIVENESS_FILE`
- `_on_shutdown` — removes the marker file (reusing ENT-004's `_on_shutdown` in a shared module)
- `LivenessMiddleware` — `os.utime()`-touches the marker on each update via `asyncio.to_thread`

The Docker healthcheck is replaced by a new `docker/healthcheck-bot.sh` that checks PID liveness + marker existence (+ optional mtime freshness via `BOT_HEALTH_STALE_SECONDS`).

**Confidence: HIGH** — all source paths, line numbers, and API behaviors verified against the installed aiogram 3.30.0 and the codebase.

---

## 2. Verified Evidence

### 2.1 Bot entrypoint — polling-only, no HTTP server

| Item | File | Lines | Content |
|------|------|-------|---------|
| `run_polling` call | `src/telegram_bot/main.py` | 65 | `dp.run_polling(bot)` |
| Dispatcher creation | `src/telegram_bot/main.py` | 40 | `dp = Dispatcher(storage=MemoryStorage())` |
| Middleware registration | `src/telegram_bot/main.py` | 43 | `dp.message.middleware(AccountStateMiddleware())` |
| Router inclusion | `src/telegram_bot/main.py` | 55-60 | 6 routers included |
| No startup/shutdown hooks | `src/telegram_bot/main.py` | 1-71 | Zero `dp.startup.register` or `dp.shutdown.register` calls. Grep confirmed: 0 matches for `on_shutdown\|on_startup\|shutdown\.register\|startup\.register` in `src/telegram_bot/` |
| Bot token source | `src/telegram_bot/main.py` | 26 | `token = settings.BOT_TOKEN` |
| Django setup | `src/telegram_bot/main.py` | 10-11 | `django.setup()` before bot imports |

### 2.2 Current healthcheck (the problem)

| Item | File | Lines | Content |
|------|------|-------|---------|
| Bot healthcheck | `docker-compose.yml` | 189-194 | `test: ["CMD-SHELL", "kill -0 1 2>/dev/null \|\| exit 1"]`, interval 30s, timeout 10s, retries 3, start_period 30s |
| Dockerfile HEALTHCHECK (inherited) | `docker/Dockerfile` | 154-155 | `HEALTHCHECK ... CMD curl -f http://localhost:8000/health/ \|\| exit 1` — overridden by compose for bot |
| Bot container command | `docker-compose.yml` | 168 | `python -m telegram_bot.main` |

### 2.3 Web reference healthcheck (the pattern to mirror)

| Item | File | Lines | Content |
|------|------|-------|---------|
| Health view | `src/backend/apps/core/views.py` | 41-56 | `health_check()` — `connection.cursor()` + `SELECT 1` → 200 or 503 |
| Health URL route | `src/backend/apps/core/urls.py` | 9 | `path("health/", views.health_check, name="health")` |

### 2.4 Boot-time DB wait (not ongoing)

| Item | File | Lines | Content |
|------|------|-------|---------|
| `wait_for_db` function | `docker/entrypoint.sh` | 33-49 | `psycopg.connect('$DATABASE_URL')` in a 30-iteration polling loop |
| `wait_for_db` call site | `docker/entrypoint.sh` | 90 | Called once at boot inside the `if __name__ ==` block, then `exec "$@"` |
| Test entrypoint (no migrate_locked) | `docker/entrypoint-test.sh` | 21-23 | Calls `manage.py migrate --run-syncdb`, `load_exchange_rates`, `setup_search_triggers` directly — never invokes `migrate_locked.main()` |

### 2.5 Settings — existing path-like settings & DB connection config

| Item | File | Lines | Content |
|------|------|-------|---------|
| `BASE_DIR` | `src/backend/config/settings/base.py` | 16 | `Path(__file__).resolve().parent.parent.parent.parent` → 4 parents → `/app/src` |
| `MEDIA_ROOT` | `src/backend/config/settings/base.py` | 208 | `BASE_DIR.parent / "media"` → `/app/media` (matches Dockerfile VOLUME) |
| `STATIC_ROOT` | `src/backend/config/settings/base.py` | 199 | `BASE_DIR.parent / "staticfiles"` |
| `BOT_TOKEN` | `src/backend/config/settings/base.py` | 59 | `env("BOT_TOKEN", default="")` |
| `BOT_USERNAME` | `src/backend/config/settings/base.py` | 236 | `os.getenv("BOT_USERNAME", "")` |
| `REDIS_URL` | `src/backend/config/settings/base.py` | 269 | `env("REDIS_URL", default="redis://localhost:6379/0")` |
| **DB: DATABASE_URL branch** (CONN_MAX_AGE) | `src/backend/config/settings/base.py` | 172-177 | `env.db()` — no `CONN_MAX_AGE` set → Django defaults to 0 |
| **DB: else branch** (CONN_MAX_AGE) | `src/backend/config/settings/base.py` | 188 | `CONN_MAX_AGE: 0` — explicit |
| prod.py CONN_MAX_AGE override | `src/backend/config/settings/prod.py` | Full file (51 lines) | No `CONN_MAX_AGE` override |
| dev.py CONN_MAX_AGE override | `src/backend/config/settings/dev.py` | Full file (44 lines) | No `CONN_MAX_AGE` override |

### 2.6 No `BOT_LIVENESS_FILE` setting exists

Grep for `BOT_LIVENESS|LIVENESS|HEARTBEAT|liveness_marker|BOT_HEALTH` across the entire repo returned matches only in audit `.ai/` and `.ai/plans/` documents — **zero matches in production source or compose/env files**.

### 2.7 Fix matrix path error

The fix matrix references `src/backend/apps/core/settings/` as the settings directory to add `BOT_LIVENESS_FILE`. **This path does not exist.** Verified via filesystem enumeration: `src/backend/config/settings/` is the actual settings directory (contains `base.py`, `dev.py`, `prod.py`, `test.py`). The setting must be added to `src/backend/config/settings/base.py`.

### 2.8 Webhook absence confirmed

Recursive grep for `set_webhook|webhook|WEBHOOK|Webhook` across `src/` returns **zero** production-code matches (4 matches are audit docs referencing the absence). The bot is polling-only per aiogram's `run_polling(handle_signals=True)` default.

### 2.9 aiogram 3.30.0 API verification

| API | Verified signature | Notes |
|-----|-------------------|-------|
| `dp.startup.register(callback)` | `(callback: CallbackType) -> None` | `CallbackType = (*args, **kwargs)`. Receives `bot`, `dispatcher`, `bots` kwargs via `emit_startup(bot=bots[-1], **workflow_data)`. |
| `dp.shutdown.register(callback)` | `(callback: CallbackType) -> None` | Fires in `start_polling`'s `finally` block AFTER stop signal, BEFORE `close_bot_session` (bot.session.close()). |
| `dp.update.middleware(mw)` | `BaseMiddleware \| Callable \| None` | Outer middleware on the **update-level** observer — fires on ALL update types (message, callback_query, edited_message, inline_query, etc.). |
| `dp.message.middleware(mw)` | Same signature | Outer middleware on the **message-level** observer — fires only on Updates containing a Message. Event at outer-middleware level IS an `Update` (confirmed by `Router.propagate_event` source: `observer.wrap_outer_middleware(_wrapped, event=event, ...)` passes the original Update). |
| `dp.run_polling(...)` | `(*bots, handle_signals=True, close_bot_session=True, ...)` | `handle_signals=True` is the default — SIGTERM/SIGINT are already handled internally by aiogram (sets `_stop_signal` → exits polling loop → `emit_shutdown` → `bot.session.close()`). No `close_bot_session_timeout` parameter exists. |
| `BaseMiddleware.__call__` | `(self, handler, event: TelegramObject, data: dict) -> Any` | Standard aiogram middleware interface. |

### 2.10 Established codebase patterns (reuse for consistency)

| Pattern | File | Lines | Relevance |
|---------|------|-------|-----------|
| `asyncio.to_thread` for blocking I/O in bot | `src/telegram_bot/handlers/ad_create.py` | 141, 998, 1272 | File I/O and translation calls already offloaded via `asyncio.to_thread`; the liveness middleware should follow the same pattern for `os.utime()`. |
| `cache.add` atomic idiom | `src/telegram_bot/services/rate_limit.py` | 49-63 | `cache.add(key, 1, timeout=period)` returns `True` only on first insertion — the codebase's established atomic primitive. |
| `AccountStateMiddleware` (existing middleware) | `src/telegram_bot/middlewares/permissions.py` | 21-91 | Existing `BaseMiddleware` that checks `isinstance(event, Update)` and extracts message from `event.message`/`event.callback_query.message`. |
| `dp` test fixture (mirrors main.py) | `src/telegram_bot/tests/conftest.py` | 42-65 | Replicates production setup; MUST be updated to register ENT-004 + ENT-005 hooks. |
| Liveness lifecycle gaps | `ENT-004 validated findings.md` | 167-195 | ENT-004 defines `_on_shutdown` calling `connections.close_all()` + `close_old_connections()`. |
| Fix matrix ENT-005 plan | `01_entry_architecture_fix_matrix.md` | 165-197 | Defines `lifecycle.py` + `healthcheck-bot.sh` + compose replacement. |

### 2.11 Architecture model confirmation

| Item | File | Line | Content |
|------|------|------|---------|
| Two-process model | `docs/99-agent/architecture.md` | 20 | "Two processes, one DB: Web gunicorn WSGI + Telegram bot share one Django project + PostgreSQL. Migrations run exactly once before both processes start." |
| Cache backend | `docs/99-agent/architecture.md` | 39-57 | Shared Redis (`django-redis`) is the production cache; LocMemCache in dev/test. |

---

## 3. Viable Healthcheck/Readiness Approaches — Evaluation

### Approach A: File-based liveness marker (AUDIT SELECTED)

**Mechanism:** Startup callback writes a marker file at a configurable path. Shutdown callback removes it. A middleware `os.utime()`-touches the marker on each inbound update. Docker healthcheck script checks: (a) PID alive, (b) marker file exists, (c) optional mtime freshness.

**Evidence of correctness:**
- `dp.startup.register(on_startup)` fires inside `start_polling` via `emit_startup(bot=bots[-1], **workflow_data)` — AFTER `Bot(token=token)` succeeds and AFTER all routers/middlewares are registered in `main()`. A malformed token raises `TokenValidationError` in the `Bot()` constructor (verified: `TokenValidationError` is raised for invalid format at `aiogram.utils.token.validate_token`), so the marker is never written → healthcheck fails correctly.
- `dp.shutdown.register(on_shutdown)` fires in `start_polling`'s `finally` block before `bot.session.close()` — the marker is removed on graceful SIGTERM/SIGINT.
- `dp.update.middleware(LivenessMiddleware())` fires on ALL update types, ensuring the mtime advances on any Telegram interaction.

| Criterion | Assessment |
|-----------|------------|
| **Correctness** | HIGH — marker existence proves the bot reached `run_polling`; mtime freshness proves it's receiving updates (catches retry loops, stuck polling, silent failures) |
| **Fit (non-HTTP polling bot)** | EXCELLENT — no HTTP server needed; uses the filesystem (Ephemeral storage is fine for `/tmp`); works with Docker's `CMD-SHELL` healthcheck |
| **Maintainability** | HIGH — single `lifecycle.py` module (~40-60 lines); reuses existing `dp.startup/register`/`dp.shutdown.register`/`dp.update.middleware` APIs already in the codebase |
| **Rollout risk** | LOW — new code is additive; healthcheck degrades gracefully (missing marker → unhealthy) |
| **Rollback ease** | HIGH — revert compose healthcheck to `kill -0 1`, delete `lifecycle.py` + `healthcheck-bot.sh`, remove setting + registration lines |
| **False-positive/negative** | **False negative (stale marker):** On SIGKILL or container crash, the shutdown callback never fires, so the marker persists. Mitigated by: (1) Docker kills the container and recreates it fresh (new container → new marker on next startup); (2) the mtime freshness check (`BOT_HEALTH_STALE_SECONDS`) catches stale markers from a zombie/stuck process. **False positive (missing marker during startup):** The `start_period: 30s` gives the bot 30s to write the marker before healthcheck failures count. |
| **Dependency on ENT-004** | The `on_shutdown` that removes the marker IS ENT-004's `on_shutdown` (plus `connections.close_all()` + `close_old_connections()`). Shared module. |

**Minor correction to audit recommendation (findings.md:230, fix_matrix.md:176):** The audit recommends registering `LivenessMiddleware` via `dp.message.middleware(...)`. This is **inadequate** for a liveness signal — `dp.message.middleware()` fires only on Updates containing messages, missing callback_query, inline_query, and edited_message updates. A bot receiving only inline keyboard button presses (callback queries) would have a stale marker despite being active. **The correct registration is `dp.update.middleware(LivenessMiddleware())`**, which fires on ALL update types. This is also the pattern already established by the codebase's own `UpdateIdDedupMiddleware` (EXT-005, `09-external-api-validated-findings.md:217`).

### Approach B: DB-based heartbeat (periodic heartbeat row in PostgreSQL)

**Mechanism:** A background `asyncio.Task` writes a heartbeat row to a dedicated `bot_liveness` table (or a `SiteConfig`/singleton row) every N seconds. The Docker healthcheck script runs a `python -c "..."` that queries the table for the latest heartbeat.

| Criterion | Assessment |
|-----------|------------|
| **Correctness** | HIGH — verifies both DB connectivity AND polling activity (the heartbeat task only runs if the event loop is healthy) |
| **Fit (non-HTTP polling bot)** | GOOD — the bot already does ORM via `sync_to_async`; a heartbeat task is natural |
| **Maintainability** | MEDIUM — requires a new DB table + migration + a background asyncio task that must be properly created/cancelled in startup/shutdown |
| **Rollout risk** | MEDIUM — new migration, background task lifecycle, and a DB-dependent healthcheck script (needs DB creds in the healthcheck environment, though the bot container has `DATABASE_URL`) |
| **Rollback ease** | MEDIUM — requires a migration rollback |
| **False-positive/negative** | Heartbeat row is accurate, but a background task competes with polling for the event loop; if the task crashes, the marker goes stale even if polling is fine |
| **Verdict** | REJECTED — disproportionate complexity (migration + task lifecycle) for a LOW-severity finding. The file-based approach achieves the same readiness signal with zero DB schema changes. |

### Approach C: TCP probe (in-process TCP listener)

**Mechanism:** The bot opens a trivial `asyncio.start_server` listener on a local port (e.g., 8099). The Docker healthcheck does `nc -z localhost 8099` or `curl` a tiny responder.

| Criterion | Assessment |
|-----------|------------|
| **Correctness** | LOW — verifies the event loop is alive and the server task is running, but does NOT verify the bot reached `run_polling` or is connected to Telegram |
| **Fit (non-HTTP polling bot)** | POOR — the bot currently has ZERO non-Telegram networking; this introduces a new network surface. The Dockerfile's `EXPOSE 8000` is for the web process, not the bot. |
| **Maintainability** | LOW — adds a server task with bind/cancel lifecycle; must handle bind failures (port in use), SO_REUSEADDR, graceful shutdown of the listener |
| **Rollout risk** | MEDIUM — new network listener in a container that previously had none; port selection must avoid conflicts |
| **Rollback ease** | HIGH |
| **False-positive/negative** | The server accepts connections but does nothing — it can't detect a polling retry loop or Telegram API failure. Pure liveness, not readiness. |
| **Verdict** | REJECTED — introduces HTTP/TCP networking to a pure polling bot; provides liveness only, not readiness; violates the "two processes, one DB" simplicity. |

### Approach D: aiogram internal metrics / update-receiver state introspection

**Mechanism:** Inspect aiogram's internal state (e.g., `dp.update.parse_thread`, the polling receiver's `last_update_id`, or `self._stop_signal`/`self._stopped_signal` flags).

| Criterion | Assessment |
|-----------|------------|
| **Correctness** | LOW-MEDIUM — some internal flags exist but are private/undocumented |
| **Fit** | POOR — `run_polling` is opaque; the `_running_lock`, `_stop_signal`, `_stopped_signal` attributes are private (underscore-prefixed) and not part of the public API |
| **Maintainability** | LOW — private API introspection breaks across aiogram minor versions |
| **Rollout risk** | LOW |
| **Rollback ease** | HIGH |
| **False-positive/negative** | Unreliable — internal state may not reflect actual polling health |
| **Verdict** | REJECTED — fragile, undocumented, version-coupled. The audit (findings.md:230) already rejected this in favor of the file-based approach. |

### Approach E: Periodic subprocess querying Telegram `getMe` API

**Mechanism:** The Docker healthcheck script runs `python -c "from aiogram import Bot; bot=Bot(token=settings.BOT_TOKEN); print(bot.get_me())"` to verify the token is accepted by Telegram.

| Criterion | Assessment |
|-----------|------------|
| **Correctness** | LOW — `getMe` only verifies the token string is valid; it does NOT verify that polling is active, that updates are being received, or that the bot hasn't entered a retry loop after a transient Telegram API failure |
| **Fit (non-HTTP polling bot)** | PARTIAL — the token IS available in the container env; the call is simple |
| **Maintainability** | LOW — requires importing Django settings + aiogram in the healthcheck script (heavyweight); adds a Telegram API call every 30s, consuming rate-budget |
| **Rollout risk** | MEDIUM — if `BOT_TOKEN` isn't set (dev mode, see `main.py:29-31`), the script must handle the empty-token case |
| **Rollback ease** | HIGH |
| **False-positive/negative** | HIGH false-positive risk: token valid + bot not polling = "healthy". HIGH false-negative risk: temporary Telegram API 429/ratelimit during healthcheck → container marked unhealthy → restart loop |
| **Verdict** | REJECTED — tests token validity, not polling readiness; adds external API call load; the audit (findings.md:230) already rejected webhooks/API wrappers in favor of the file-based approach. |

### Approach F: Shared HTTP sidecar container

**Mechanism:** Deploy a tiny HTTP server (e.g., a 10-line Python/Flask app) as a sidecar container; the bot pings it on startup/shutdown/update; Docker healthchecks the HTTP endpoint.

| Criterion | Assessment |
|-----------|------------|
| **Correctness** | HIGH — full HTTP health semantics |
| **Fit (non-HTTP polling bot)** | POOR — violates the established "two processes, one DB" architecture. The project deliberately runs exactly two long-lived processes (web + bot). Adding a third container per deployment is architecturally disproportionate. |
| **Maintainability** | LOW — new container, new image, new compose service, new deployment surface, new inter-process communication channel (bot → sidecar) that must be wired |
| **Rollout risk** | HIGH — changes the deployment topology; nginx, compose, prod overrides must all be updated |
| **Rollback ease** | MEDIUM |
| **False-positive/negative** | The sidecar could be healthy while the bot is dead (no liveness link unless the bot actively pings it, which adds complexity) |
| **Verdict** | REJECTED — disproportionate for a LOW-severity finding; breaks the two-process model; the audit (findings.md:230) explicitly recommends file-based over "HTTP wrapper." |

### Approach G: DB connectivity check from healthcheck (mimic `wait_for_db`)

**Mechanism:** Healthcheck script runs `python -c "import psycopg; psycopg.connect('$DATABASE_URL')"` (same as `entrypoint.sh:41`).

| Criterion | Assessment |
|-----------|------------|
| **Correctness** | LOW — verifies DB connectivity only. Does NOT verify the bot reached `run_polling`, that the token is valid, or that polling is active. A bot stuck in a retry loop with a valid DB connection passes this check. |
| **Fit (non-HTTP polling bot)** | PARTIAL — the bot container has `DATABASE_URL`; the psycopg driver is installed |
| **Maintainability** | HIGH — trivial script |
| **Rollout risk** | LOW |
| **Rollback ease** | HIGH |
| **False-positive/negative** | HIGH false-positive: process alive + DB reachable = "healthy" even if bot polling failed |
| **Verdict** | REJECTED as sole approach — but could be USED AS A COMPLEMENT within `healthcheck-bot.sh`. The file-based marker is superior because it proves the bot reached the polling loop (which requires both a valid token AND successful startup). |

### Approach H: Wrapper script monitoring run_polling exit code

**Mechanism:** Replace `python -m telegram_bot.main` with a shell wrapper that monitors the child process's exit code.

| Criterion | Assessment |
|-----------|------------|
| **Correctness** | LOW — identical to PID liveness; `run_polling` runs forever (until signaled), so the exit code is only available after the process has already exited |
| **Fit / Maintainability / Rollout / Rollback** | Trivial |
| **False-positive/negative** | Pure liveness; no readiness signal |
| **Verdict** | REJECTED — same problem as the current `kill -0 1` check, just packaged differently. |

---

## 4. Selected Solution: Approach A (File-Based Liveness Marker)

### Rationale

A is the only approach that:
1. **Detects readiness, not just liveness** — the marker is written only after `Bot(token)` succeeds and `emit_startup` fires, proving the bot reached the polling loop (catches bad-token crashes, startup exceptions).
2. **Detects staleness/retry loops** — the middleware `os.utime()`-touch on each update proves the bot is actively receiving Telegram updates. A bot stuck in aiogram's backoff retry loop (transient Telegram API failure) will have a marker but stale mtime → caught by the optional `BOT_HEALTH_STALE_SECONDS` freshness check.
3. **Requires no architectural change** — no HTTP server, no new container, no new DB table/migration. Uses only the filesystem and aiogram's existing lifecycle hooks.
4. **Composes with ENT-004** — `_on_shutdown` is shared: it removes the liveness marker AND calls `connections.close_all()` + `close_old_connections()` (ENT-004's Django cleanup). Both findings touch `main.py` and the same lifecycle module.
5. **Matches the established two-process model** — the bot is a Telegram-polling client by design (`architecture.md:20`). Adding TCP/HTTP sidecars or DB heartbeat tables violates the simplicity of the architecture.

### Rejected Alternatives (summary)

| Approach | Verdict | Reason |
|----------|---------|--------|
| B — DB heartbeat table | REJECTED | Requires migration + background task lifecycle; file-based achieves same signal with zero schema changes |
| C — TCP probe | REJECTED | Introduces HTTP/TCP networking to a pure polling bot; liveness-only, not readiness |
| D — aiogram internal state | REJECTED | Private API introspection; breaks across versions |
| E — Telegram getMe subprocess | REJECTED | Tests token validity only, not polling readiness; adds 30s API call load + ratelimit risk |
| F — HTTP sidecar | REJECTED | Breaks two-process architecture; disproportionate for LOW severity |
| G — DB connectivity check | REJECTED (as sole) | Liveness-only (DB reachable ≠ bot polling); could supplement A in the healthcheck script |
| H — Wrapper exit-code monitor | REJECTED | Identical to current PID liveness |

### Correction to audit recommendation

The audit (findings.md:230, fix_matrix.md:176) recommends registering `LivenessMiddleware` via `dp.message.middleware(...)`. This is **incorrect** for a liveness signal — `dp.message.middleware()` fires only on Updates containing messages, missing callback_query, inline_query, and edited_message updates. A bot receiving only inline keyboard button presses (callback queries) would show a stale marker despite being active. **Use `dp.update.middleware(LivenessMiddleware())`** instead — this fires on ALL update types and is the pattern already established by the codebase's own `UpdateIdDedupMiddleware` (EXT-005, `09-external-api-validated-findings.md:217`).

---

## 5. Design Details — Composed ENT-004 + ENT-005

### 5.1 Shared module: `src/telegram_bot/lifecycle.py` (NEW)

This module unifies ENT-004 (shutdown cleanup) and ENT-005 (liveness marker) in a single file, since both are bot-lifecycle hooks that edit the same entry point.

**Structure:**

```python
"""Bot lifecycle hooks: graceful shutdown (ENT-004) and liveness marker (ENT-005).

Shared module so both findings are co-located and tested together.
Registered via dp.startup.register / dp.shutdown.register in main.py.
"""

import logging
from typing import Any

from django.conf import settings

logger = logging.getLogger(__name__)


def _touch_marker() -> None:
    """Create or update the liveness marker file mtime."""
    path = settings.BOT_LIVENESS_FILE
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()          # creates if absent
        path.utime()           # updates mtime to now (atomic on POSIX)
    except OSError as exc:
        logger.warning("Could not write liveness marker %s: %s", path, exc)


async def on_startup(*args: Any, **kwargs: Any) -> None:
    """Write liveness marker once the bot enters run_polling.

    Fires after Bot(token) succeeds and Dispatcher is wired (via emit_startup).
    A missing marker after start_period means the bot never reached polling
    (bad token / startup crash).
    """
    _touch_marker()
    logger.info("Bot liveness marker written to %s", settings.BOT_LIVENESS_FILE)


async def on_shutdown(*args: Any, **kwargs: Any) -> None:
    """Remove liveness marker and close Django DB connections.

    Combines ENT-004 (connections.close_all) and ENT-005 (marker cleanup).
    Fires in start_polling's finally block, BEFORE bot.session.close().
    """
    path = settings.BOT_LIVENESS_FILE
    try:
        path.unlink(missing_ok=True)
    except OSError as exc:
        logger.warning("Could not remove liveness marker %s: %s", path, exc)

    from django.db import close_old_connections, connections
    connections.close_all()
    close_old_connections()
    logger.info("Bot shutdown: marker removed, DB connections closed.")


class LivenessMiddleware:
    """Touch the liveness marker on each inbound update.

    Registered at dp.update.middleware() (NOT dp.message) so it fires on
    ALL update types — messages, callback queries, inline queries, etc.
    A stale marker mtime (relative to BOT_HEALTH_STALE_SECONDS) indicates
    the bot is alive but not receiving updates (stuck retry loop).
    """

    async def __call__(self, handler, event, data):
        import asyncio
        asyncio.to_thread(_touch_marker)  # defer: file I/O can block
        return await handler(event, data)
```

**Design decision notes:**

1. **`asyncio.to_thread` for file I/O** — The codebase already uses `asyncio.to_thread` for blocking I/O in the bot (`ad_create.py:141, 998, 1272`). File `touch`/`utime` are nanosecond syscalls, but consistency with the codebase pattern warrants offloading. Calling `pathlib.Path.touch()` + `os.utime()` synchronously in the event loop is also defensible (sub-microsecond), but `asyncio.to_thread` is the safer choice per the codebase convention and avoids any theoretical loop-blocking concern.

2. **Fail-open middleware** — The middleware always calls `handler(event, data)`, even if `_touch_marker` fails (errors are logged inside `_touch_marker`, never raised). This ensures a filesystem error never blocks bot functionality.

3. **`dp.update.middleware` not `dp.message.middleware`** — Fires on all update types (see correction above).

4. **`on_startup`/`on_shutdown` signature** — `CallbackType = (*args, **kwargs)`; aiogram calls `emit_startup(bot=bots[-1], **workflow_data)` so the callbacks receive `bot`, `dispatcher`, `bots` as kwargs. Using `*args, **kwargs` is the correct signature (matches the aiogram convention; `CallableType` is documented as variadic).

5. **`on_shutdown` ordering** — Fires in `start_polling`'s `finally` block AFTER the stop signal is set but BEFORE `bot.session.close()`. Django DB connections are independent of the bot's aiohttp session, so closing Django connections first is correct and safe.

### 5.2 `src/telegram_bot/main.py` changes

| Current line | Change |
|-------------|--------|
| 13-16 (imports) | Add `from telegram_bot.lifecycle import LivenessMiddleware, on_shutdown, on_startup` |
| 43 (`dp.message.middleware(...)`) | No change (existing middleware stays) |
| 56-60 (router inclusion) | No change |
| 62-65 (`bot = Bot(...)` + `logger.info(...)`) | No change |
| After line 64, before line 67 | Add: `dp.startup.register(on_startup)` and `dp.shutdown.register(on_shutdown)` |
| After line 43 | Add: `dp.update.middleware(LivenessMiddleware())` |

### 5.3 Settings — `src/backend/config/settings/base.py`

**Note:** The fix matrix references `src/backend/apps/core/settings/` which does NOT exist. The correct location is `src/backend/config/settings/base.py`.

Add after `BOT_USERNAME` (base.py:236):

```python
# Liveness marker file for bot healthcheck (ENT-005).
# On startup the bot touches this file; the Docker healthcheck verifies
# its existence (readiness) and optional mtime freshness (staleness).
# Defaults to /tmp which is writable by the app user (uid 1000) in the
# production Dockerfile.
BOT_LIVENESS_FILE = Path(os.getenv("BOT_LIVENESS_FILE", "/tmp/mko_bazuna_bot_alive"))

# If set (non-zero), the bot healthcheck verifies the marker mtime is
# within this many seconds — catching retry-loop/stuck-polling states.
# Empty/zero disables the freshness check (existence-only readiness).
BOT_HEALTH_STALE_SECONDS = int(os.getenv("BOT_HEALTH_STALE_SECONDS", "0"))
```

`Path` is already imported at `base.py:9` (`from pathlib import Path`). `os` is imported at `base.py:7`.

### 5.4 Docker healthcheck script — `docker/healthcheck-bot.sh` (NEW)

```bash
#!/bin/bash
# Bot healthcheck (ENT-005).
# Replaces the PID-only `kill -0 1` check.
# Verifies: (a) process liveness, (b) readiness (marker file exists),
# (c) freshness (optional, via BOT_HEALTH_STALE_SECONDS).
#
# Runs as the container's USER app (uid 1000) in the production image.
# /tmp is world-writable (1777), so the app user can read/write the marker.
set -e

MARKER_FILE="${BOT_LIVENESS_FILE:-/tmp/mko_bazuna_bot_alive}"
STALE_SECONDS="${BOT_HEALTH_STALE_SECONDS:-0}"

# (a) PID liveness (inherited from Dockerfile default)
kill -0 1 2>/dev/null || exit 1

# (b) Readiness: marker file must exist (bot reached run_polling)
if [ ! -f "$MARKER_FILE" ]; then
    echo "UNHEALTHY: liveness marker $MARKER_FILE not found"
    exit 1
fi

# (c) Freshness: if enabled, marker mtime must be within window
if [ "$STALE_SECONDS" -gt 0 ]; then
    NOW_EPOCH=$(date +%s)
    # GNU coreutils (production Debian image): stat -c %Y; BSD fallback: stat -f %m
    FILE_EPOCH=$(stat -c %Y "$MARKER_FILE" 2>/dev/null || stat -f %m "$MARKER_FILE" 2>/dev/null)
    AGE=$((NOW_EPOCH - FILE_EPOCH))
    if [ "$AGE" -gt "$STALE_SECONDS" ]; then
        echo "UNHEALTHY: liveness marker stale ($AGE > $STALE_SECONDS s) — bot not receiving updates"
        exit 1
    fi
fi

echo "HEALTHY"
exit 0
```

**Portability note:** `stat -c %Y` is GNU coreutils (Linux, production `python:3.14-slim` is Debian-based). The `stat -f %m` fallback handles macOS (local dev). Both branches are harmless on the correct platform.

**Dockerfile COPY consideration:** `Dockerfile:127` currently copies `docker/entrypoint*.sh` to `/app/` (flat, not preserving `docker/` subdir). The healthcheck script must be copyable. Two options:
- Option 1: `COPY --chown=app:app docker/healthcheck-bot.sh /app/docker/` → compose references `/app/docker/healthcheck-bot.sh`
- Option 2: `COPY --chown=app:app docker/healthcheck-bot.sh /app/` → compose references `/app/healthcheck-bot.sh`

The compose fix matrix (line 179) says `/app/docker/healthcheck-bot.sh`, so **Option 1** matches. The Dockerfile needs a corresponding COPY line.

### 5.5 `docker-compose.yml` bot healthcheck (lines 189-194)

Replace:

```yaml
healthcheck:
  test: ["CMD-SHELL", "kill -0 1 2>/dev/null || exit 1"]
  interval: 30s
  timeout: 10s
  retries: 3
  start_period: 30s
```

With:

```yaml
healthcheck:
  test: ["CMD-SHELL", "/app/docker/healthcheck-bot.sh || exit 1"]
  interval: 30s
  timeout: 10s
  retries: 3
  start_period: 30s
```

Add `BOT_LIVENESS_FILE` env var to the bot service environment block (lines 174-182):

```yaml
      BOT_LIVENESS_FILE: /tmp/mko_bazuna_bot_alive
      BOT_HEALTH_STALE_SECONDS: 0
```

(`BOT_HEALTH_STALE_SECONDS` defaults to 0 = freshness check disabled; can be set to e.g. `300` for retry-loop detection. The healthcheck script reads the env var directly.)

### 5.6 `docker-compose.prod.yml` consideration

Verified: `docker-compose.prod.yml` overrides the bot service only for image pulling (registry/repository/image_tag). The healthcheck is in the base `docker-compose.yml` and is inherited by prod. **No change needed in prod override** — the `BOT_LIVENESS_FILE` env var flows from `.env.docker` (already mounted into both base and prod compose). The `.env.docker.example` should get a new documented variable.

### 5.7 `.env.docker.example` update

Add after the Telegram Bot section (after line 28):

```env
# ====================== Bot Healthcheck (ENT-005) ======================
# Liveness marker path for the bot readiness probe. The bot writes this file
# on startup (after reaching run_polling) and removes it on shutdown.
# The Docker healthcheck verifies the file exists (readiness) and optionally
# its mtime freshness (BOT_HEALTH_STALE_SECONDS > 0).
# BOT_LIVENESS_FILE=/tmp/mko_bazuna_bot_alive
# BOT_HEALTH_STALE_SECONDS=0   # set to e.g. 300 to detect stuck/retry-loop states
```

Both default to the same values as the compose env and the settings defaults, so they're optional.

### 5.8 Test considerations

| Test file | Action |
|-----------|--------|
| `src/telegram_bot/tests/conftest.py` (dp fixture, lines 42-65) | **Update** — register `on_startup` + `on_shutdown` + `LivenessMiddleware` in the `dp` fixture to mirror production (mirrors ENT-004 conftest update requirement) |
| `src/telegram_bot/tests/test_bot_liveness.py` (NEW) | **Create** — verify marker file is created on startup hook call, touched by middleware on update propagation, and removed on shutdown hook call |

**Key test subtlety:** The `on_startup`/`on_shutdown` callbacks receive `bot` and `dispatcher` kwargs (from `emit_startup(bot=bots[-1], **workflow_data)`). Tests calling `on_startup()` directly must pass `**kwargs` or use `*args, **kwargs` signature (which the design does). The `LivenessMiddleware.__call__` follows the standard aiogram `(handler, event, data)` signature verified from `BaseMiddleware.__call__`.

---

## 6. Rollout Ordering

```
ENT-004 (shutdown hook: on_shutdown with connections.close_all)
    └── ENT-005 (liveness marker: on_startup + LivenessMiddleware + healthcheck-bot.sh)
```

Both findings edit `main.py` and a shared `lifecycle.py`. The fix matrix (line 300) and validated findings (line 321) confirm: ENT-005 depends on ENT-004. The `on_shutdown` function must be implemented first (ENT-004), then the liveness hooks are added to the same `lifecycle.py` module (ENT-005). The conftest `dp` fixture must register both hooks in the same change to keep tests representative.

### Sequential ordering (per fix_matrix.md lines 320-331):

| Step | Finding | Action |
|------|---------|--------|
| 1 | ENT-004 | Create `lifecycle.py` with `on_shutdown` (ENT-004's `connections.close_all()`). Register in `main.py` + conftest. |
| 2 | ENT-005 | Extend `lifecycle.py` with `on_startup` + `LivenessMiddleware`. Add `BOT_LIVENESS_FILE` setting. Create `healthcheck-bot.sh`. Replace compose healthcheck. Update conftest. |
| 3 | ENT-005 | Write `test_bot_liveness.py`. |

---

## 7. Risk Analysis

### 7.1 Startup failure detection

- **Malformed token (e.g., `BOT_TOKEN=x`):** `Bot(token=token)` at `main.py:63` raises `TokenValidationError` (verified: `TokenValidationError` is raised for invalid format at `aiogram.utils.token.validate_token`). `emit_startup` never fires → marker never written → healthcheck fails after `start_period: 30s`. **Correct.**
- **Valid token but bad Telegram API response:** `Bot()` succeeds → `emit_startup` fires → marker written → polling starts → `getUpdates` fails → aiogram enters backoff retry. Marker stays present but freshness check (`BOT_HEALTH_STALE_SECONDS`) catches the stale mtime if updates stop arriving. **Correct.**
- **Empty token (dev mode, `main.py:29-31`):** `main()` returns early → no marker → healthcheck fails. This is **acceptable** — the bot isn't running in dev mode; the container should be marked unhealthy (or the healthcheck should be disabled for dev). In dev, the bot container typically isn't started or `BOT_TOKEN` is set.

### 7.2 Hard kill (SIGKILL / container crash)

- Docker sends `SIGTERM` first (default 10s grace), then `SIGKILL`. On `SIGTERM`, aiogram's `handle_signals=True` (default) catches it → `_signal_stop_polling` → polling loop exits → `emit_shutdown` fires → marker removed + connections closed. **Correct.**
- On `SIGKILL` or hard crash, `emit_shutdown` never fires → marker persists. On container recreation, a new container starts fresh with no marker until startup. The old marker is on the old container's filesystem (ephemeral `/tmp`), so it's gone. **Not an issue in Docker** — each container has its own filesystem.

### 7.3 Filesystem permissions

- The production Dockerfile runs as `USER app` (uid 1000, `Dockerfile:149`). The marker is at `/tmp/mko_bazuna_bot_alive` — `/tmp` is world-writable (`1777` perms on Debian). The `on_startup` handler creates the file as uid 1000. The `healthcheck-bot.sh` runs as the same user (Docker healthcheck runs as the container's user). **Correct.**
- `path.parent.mkdir(parents=True, exist_ok=True)` handles the case where a custom `BOT_LIVENESS_FILE` path has non-existent parent directories.

### 7.4 Test environment

- In the Docker test environment (`make test`), the bot service is NOT started (tests run via `entrypoint-test.sh` → pytest). The `dp` test fixture mirrors `main.py` and must register the hooks. The `BOT_LIVENESS_FILE` setting defaults to `/tmp/...` which is writable in the test container. Tests should use a temp path (via `tmp_path` fixture or `override_settings`) to avoid cross-test contamination.
- The test for `test_bot_liveness.py` should call `on_startup()` and `on_shutdown()` directly (simulating the hooks, not via `run_polling`).
- The `LivenessMiddleware.__call__` can be tested by constructing a mock `handler` coroutine and verifying `_touch_marker` is called (via `asyncio.to_thread`).

---

## 8. Files Summary (Remediation Checklist)

| # | File | Action | Depends on |
|---|------|--------|------------|
| 1 | `src/telegram_bot/lifecycle.py` | **CREATE** — `on_startup`, `on_shutdown`, `LivenessMiddleware` | ENT-004 (shutdown portion) |
| 2 | `src/telegram_bot/main.py` | **UPDATE** — import + register startup, shutdown, update middleware (lines 43, 65) | ENT-004 |
| 3 | `src/backend/config/settings/base.py` | **UPDATE** — add `BOT_LIVENESS_FILE` + `BOT_HEALTH_STALE_SECONDS` (after line 236) | — |
| 4 | `docker/Dockerfile` | **UPDATE** — add `COPY --chown=app:app docker/healthcheck-bot.sh /app/docker/` (near line 127) | — |
| 5 | `docker/healthcheck-bot.sh` | **CREATE** — PID + marker-existence + optional freshness check | — |
| 6 | `docker-compose.yml` | **UPDATE** — replace healthcheck (lines 189-194), add `BOT_LIVENESS_FILE` + `BOT_HEALTH_STALE_SECONDS` env (lines 174-182) | — |
| 7 | `.env.docker.example` | **UPDATE** — document new env vars (after line 28) | — |
| 8 | `src/telegram_bot/tests/conftest.py` | **UPDATE** — `dp` fixture registers ENT-004 + ENT-005 hooks (lines 42-65) | ENT-004 |
| 9 | `src/telegram_bot/tests/test_bot_liveness.py` | **CREATE** — marker creation, middleware touch, shutdown removal | ENT-005 |

---

## 9. Confidence Assessment

| Evidence | Confidence |
|----------|-----------|
| `main.py` structure (run_polling, Dispatcher, middleware, imports) | HIGH — read in full (71 lines) |
| Compose healthcheck, Dockerfile HEALTHCHECK, entrypoint.sh | HIGH — read in full |
| aiogram 3.30.0 API (`run_polling`, `emit_startup`/`emit_shutdown` timing, middleware registration, `CallbackType` signature) | HIGH — introspected runtime signatures and source of `start_polling`, `feed_update`, `Router.propagate_event`, `MiddlewareManager.wrap_middlewares`, `TelegramEventObserver.trigger` |
| Settings layout (`base.py` is the correct location, not `apps/core/settings/`) | HIGH — filesystem enumeration confirmed `src/backend/apps/core/settings/` does not exist |
| Webhook absence (polling-only) | HIGH — grep returned 0 production matches |
| CONN_MAX_AGE=0 (ENT-004 basis) | HIGH — verified in both branches of `base.py` + `prod.py`/`dev.py`/`test.py` have no override |
| Established codebase patterns (`asyncio.to_thread`, `cache.add`, `AccountStateMiddleware`, `dp` test fixture) | HIGH — all source verified |
| `os.utime` + `pathlib.Path` availability | HIGH — verified at runtime |
| aiogram `dp.update.middleware()` fires on all update types | HIGH — verified via `Router.propagate_event` source confirming outer middleware receives the `Update` object; `dp.update` observer wraps with the full Update, not an extracted sub-type |
| `stat -c %Y` (GNU coreutils) in production container | HIGH — `python:3.14-slim` is Debian-based |
| `start_period: 30s` in compose healthcheck | HIGH — `docker-compose.yml:194` |

---

## 10. Recommendation for Implementation

Implement **Approach A** exactly as designed in Section 5, with the two corrections:
1. **Use `dp.update.middleware()` not `dp.message.middleware()`** for the `LivenessMiddleware` (fires on all update types).
2. **Add `BOT_LIVENESS_FILE` to `config/settings/base.py`, not `apps/core/settings/`** (the fix matrix path is incorrect).

The remediation is **not implemented** per task instructions — this is the research/design phase. The implementation checklist in Section 8 defines the complete change set.