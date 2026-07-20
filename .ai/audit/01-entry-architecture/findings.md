---
name: audit-findings
description: Phase 01 — Entry Points & Process Architecture findings
agent: auditor
alwaysApply: false
---

# Phase 01 Audit Findings — Entry Points & Process Architecture

**Executor:** auditor
**Template:** .kilo/commands/audit/phases/01-audit-entry-architecture.md
**Status:** complete
**Validated:** no

> `problems-only: true` — only problems, bugs, and deviations are documented.
> Roles referenced per phase handbook; concrete file:line evidence attached.

---

## Findings

### ENT-001: Container processes cannot boot — missing Python import paths for `config`/`apps`/`telegram_bot`

| Field | Value |
|-------|-------|
| **ID** | ENT-001 |
| **Severity** | CRITICAL |
| **Type** | RUNTIME-ERROR |
| **Affected Modules** | docker/Dockerfile, docker-compose.yml, docker-compose.dev.override.yml, docker/entrypoint-test.sh, docker/entrypoint-scheduler.sh, pyproject.toml |
| **Classification** | mandatory |

**Description:** The image build derives the import root incorrectly for all three
process entrypoints. `docker/Dockerfile` sets `WORKDIR /app` (line 55) and copies
only the tree (`COPY . .` then `COPY --from=builder /app/src /app/src`), and installs
dependencies with `uv sync --frozen --no-install-project` (line 26) — i.e. the project
package is **never installed**. No `PYTHONPATH` is set anywhere (compose, entrypoints,
Dockerfile). The actual top-level packages live at `src/backend/{apps,config}` and
`src/telegram_bot`.

Consequences at runtime:
- `migrate` service command `uv run python -c "from apps.core.utils.migrate_locked import main"` fails — `apps` needs `/app/src/backend` on `sys.path`.
- `web` command `gunicorn config.wsgi:application` fails — `config` needs `/app/src/backend`.
- `bot` command `python -m telegram_bot.main` fails — `telegram_bot` needs `/app/src`.
- `test` service (`entrypoint-test.sh`) runs `uv run pytest` from `/app`; conftest does `django.setup()` → `config.settings.test` → `ModuleNotFoundError` (see evidence).

`uv run` adds **only the current working directory** to `sys.path`, not `/app/src` or
`/app/src/backend`. With `WORKDIR /app`, none of the required roots are importable, so
**no process boots in the built image**. This is a deployment-blocking defect, not a
local-dev-only quirk.

**Evidence:**
```
# From repo root (mirrors container WORKDIR=/app, no PYTHONPATH):
$ uv run python -c "import os,sys; print('PYTHONPATH='+os.environ.get('PYTHONPATH','NONE')); import config"
PYTHONPATH=NONE
ModuleNotFoundError: No module named 'config'

# With cwd=src/backend it works (uv injects cwd only):
$ pushd src/backend; uv run python -c "import config; print('OK')"; popd
CONFIG OK from src/backend

# Migrate command shape (docker-compose.yml:25) has no path coverage from /app:
command: uv run python -c "from apps.core.utils.migrate_locked import main; ..."
# Internally runs subprocess src/backend/manage.py (migrate_locked.py:19) -> also needs path.

# Test entrypoint (docker/entrypoint-test.sh:24,28) fails at conftest import:
conftest.py:15: in <module>  django.setup()
... ModuleNotFoundError: No module named 'config'
```

**Recommendation:** Make the import roots explicit and uniform across all entrypoints.
Either (a) install the project as an installed package in the image
(`uv sync --frozen` without `--no-install-project`, with `pyproject.toml`
`[tool.setuptools.packages.find]` corrected to discover `apps`, `config`,
`telegram_bot`), or (b) set `PYTHONPATH=/app/src/backend:/app/src` in the Dockerfile
`ENV` and compose `environment`. Prefer (a) for portability. This single fix also
unblocks the test suite (ENT-006).

---

### ENT-002: Bot entrypoint imports Django models before `django.setup()` → `AppRegistryNotReady`

| Field | Value |
|-------|-------|
| **ID** | ENT-002 |
| **Severity** | CRITICAL |
| **Type** | RUNTIME-ERROR |
| **Affected Modules** | src/telegram_bot/__init__.py, src/telegram_bot/main.py, src/telegram_bot/handlers/__init__.py |
| **Classification** | mandatory |

**Description:** The bot package `__init__.py` eagerly imports handler modules at
package-import time. `main.py` performs `from telegram_bot.middlewares import AccountStateMiddleware`
at module top level (line 9), which imports the `telegram_bot` package → triggers
`telegram_bot/__init__.py:4` (`from .handlers import login_router, ad_create_router`)
→ `handlers/__init__.py:3` → `login.py:17` `from apps.users.models import User, LoginToken`.
This model import requires the Django app registry. But `django.setup()` is only called
later inside `main()` at `main.py:15`. So the Django app registry is not loaded when the
model is imported, raising `AppRegistryNotReady` during import — the bot process cannot
even be imported, let alone poll.

This violates the phase invariant "Bot entrypoint calls `django.setup()` before any
ORM/model import" and is independent of the path issue (ENT-001): it reproduces even
when both `src` and `src/backend` are on the path.

**Evidence:**
```
$ uv run python -c "import sys; sys.path.insert(0,'src'); sys.path.insert(0,'src/backend'); import telegram_bot.main"
  File ".../telegram_bot/handlers/login.py", line 17, in <module>
    from apps.users.models import User, LoginToken
  File ".../apps/users/models.py", line 8, in <module>
    from django.contrib.auth.models import AbstractUser
  ...
    raise AppRegistryNotReady("Apps aren't loaded yet.")
django.core.exceptions.AppRegistryNotReady: Apps aren't loaded yet.
```
Import order in `main.py`: line 9 imports `telegram_bot.middlewares` (→ package __init__
→ handlers → models) BEFORE line 14 `os.environ.setdefault("DJANGO_SETTINGS_MODULE", ...)`
and line 15 `django.setup()`.

**Recommendation:** Do not import handler/router modules at package-import time.
Remove the eager `from .handlers import ...` from `telegram_bot/__init__.py` (keep only
non-Django symbols such as `AdCreateState`). In `main.py`, set `DJANGO_SETTINGS_MODULE`
and call `django.setup()` at the very top (before any `telegram_bot.*` import), then
import routers inside `main()`. This guarantees models are only touched after setup.

---

### ENT-003: Blocking filesystem write on the async bot event loop

| Field | Value |
|-------|-------|
| **ID** | ENT-003 |
| **Severity** | HIGH |
| **Type** | RUNTIME-ERROR |
| **Affected Modules** | src/telegram_bot/handlers/ad_create.py |
| **Classification** | mandatory |

**Description:** `save_photo()` is an `async def` that performs a synchronous blocking
filesystem write (`os.makedirs` + `open(...).write()`) directly on the event loop, and is
`await`ed from the photo handler (`ad_create.py:282`). Because aiogram runs a single
event loop, this blocking IO stalls **all** concurrent bot updates for the duration of
the disk write. The handler correctly wraps every ORM call in `sync_to_async`, but the
media write is left unwrapped — an async/sync boundary gap.

**Evidence:**
```
ad_create.py:431-437
async def save_photo(storage_key: str, photo_bytes: bytes) -> None:
    media_path = os.path.join(settings.MEDIA_ROOT, storage_key)
    os.makedirs(os.path.dirname(media_path), exist_ok=True)
    with open(media_path, "wb") as f:
        f.write(photo_bytes)        # blocking, runs on event loop
# awaited at ad_create.py:282  await save_photo(storage_key, photo_bytes)
```
No `sync_to_async` / `run_in_executor` wrapper; contrast with sibling helpers
(`create_draft_ad`, `search_categories`, etc.) which all use `sync_to_async`.

**Recommendation:** Wrap the media write in `sync_to_async` (or `asyncio.to_thread` /
`run_in_executor`) so it executes off the event loop, consistent with the other ORM
helpers in the same file. This keeps the single loop responsive to all users during
uploads.

---

### ENT-004: Blocking network IO (synchronous translation) on the async bot event loop

| Field | Value |
|-------|-------|
| **ID** | ENT-004 |
| **Severity** | HIGH |
| **Type** | RUNTIME-ERROR |
| **Affected Modules** | src/telegram_bot/handlers/ad_create.py |
| **Classification** | mandatory |

**Description:** On ad-submit confirmation, `translate_to_russian()` performs a
synchronous outbound network call via `deep_translator.GoogleTranslator(...).translate()`
inside an `async def` that is `await`ed at `ad_create.py:327`. The HTTP request blocks the
single bot event loop for its full latency (network round-trip + retries), so **every**
in-flight Telegram update from every user is frozen while one ad is being translated.
There is no timeout, no async client, and no off-loop executor.

**Evidence:**
```
ad_create.py:468-482
async def translate_to_russian(title, description):
    from deep_translator import GoogleTranslator
    title_ru = GoogleTranslator(source="auto", target="ru").translate(title)   # blocking network
    desc_ru  = GoogleTranslator(source="auto", target="ru").translate(description)
    return title_ru, desc_ru
# awaited at ad_create.py:327  title_ru, desc_ru = await translate_to_russian(...)
```
No `sync_to_async`/executor, no timeout; a slow/failed translator endpoint hangs the loop.

**Recommendation:** Move the translation off the event loop (e.g. `sync_to_async` with a
bounded timeout, or an async HTTP client). Also add a hard timeout so a stalled external
translation cannot indefinitely block the loop. Consider making translation best-effort
and non-blocking to submission latency.

---

### ENT-005: Inconsistent / undefined restart policy for the long-lived web process

| Field | Value |
|-------|-------|
| **ID** | ENT-005 |
| **Severity** | MEDIUM |
| **Type** | SPEC-DEVIATION |
| **Affected Modules** | docker-compose.yml |
| **Classification** | advisory |

**Description:** The cross-cutting concern "restart-policy expectations" requires defined
restart semantics for long-lived processes. In `docker-compose.yml` the `bot` and `nginx`
services declare `restart: unless-stopped`, but the `web` (gunicorn) service has **no**
`restart` key. If the web process crashes or is OOM-killed, Docker will not restart it and
the site goes down silently while the bot keeps running — a split-brain where Telegram can
still post ads that the website cannot serve.

**Evidence:**
```
# docker-compose.yml
  web:
    build: { context: ., dockerfile: docker/Dockerfile }
    command: gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers 3
    depends_on:
      migrate:
        condition: service_completed_successfully
    # <-- no `restart:` key here

  bot:
    ...
    restart: unless-stopped   # present
```
Production override (`docker-compose.prod.yml:6-7`) adds `restart: unless-stopped` to
`web`, so the gap is dev/base-only — but base compose is what `docker compose up` runs by
default and is what the audit's runtime model describes.

**Recommendation:** Give `web` an explicit `restart: unless-stopped` (or `on-failure`)
in the base `docker-compose.yml` so the web and bot processes share consistent restart
semantics. This also satisfies the audit's restart-policy expectation uniformly.

---

### ENT-006: Test suite is un-runnable from the CI/test entrypoint (same root cause as ENT-001)

| Field | Value |
|-------|-------|
| **ID** | ENT-006 |
| **Severity** | MEDIUM |
| **Type** | BEST-PRACTICE |
| **Affected Modules** | conftest.py, docker/entrypoint-test.sh, docker-compose.test.yml |
| **Classification** | advisory |

**Description:** The `test` compose service runs `docker/entrypoint-test.sh`, which does
`uv run pytest` from `WORKDIR /app`. `conftest.py:7,13` sets `DJANGO_SETTINGS_MODULE` and
calls `django.setup()` at import time, which imports `config.settings.test` →
`ModuleNotFoundError: No module named 'config'` (identical to ENT-001). The test container
therefore fails at collection, so R4 (test-suite run) cannot pass in CI. Locally the suite
collects 62 tests only after manually adding `src/backend` (and `src`) to `PYTHONPATH`.

**Evidence:**
```
# Without path fix (mirrors container):
$ uv run pytest tests -q -x --co
conftest.py:15: in <module>  django.setup()
E   ModuleNotFoundError: No module named 'config'

# With PYTHONPATH=src/backend;src (62 tests collected):
$ uv run pytest src/backend --co
62 tests collected in 0.23s
```

**Recommendation:** Resolving ENT-001 (install the project / set PYTHONPATH) also fixes
the CI test entry. Additionally, point the test runner at the real test tree
(`src/backend`, not the empty top-level `tests/`) and add a smoke check that `import config`
succeeds inside the built image before invoking pytest.

---

### ENT-007: `pyproject.toml` package discovery does not match the actual source layout

| Field | Value |
|-------|-------|
| **ID** | ENT-007 |
| **Severity** | LOW |
| **Type** | DOC-UPDATE |
| **Affected Modules** | pyproject.toml |
| **Classification** | advisory |

**Description:** `[tool.setuptools.packages.find]` declares `where = ["."]` and
`include = ["mko_bazuna*", "mko_bazuna.src", "mko_bazuna.core"]`, but the repository has
no `mko_bazuna*` package — the importable top-level names are `apps`, `config`,
`telegram_bot`. Combined with `uv sync --no-install-project` in the Dockerfile, the project
is never placed on `sys.path` by installation. This is the root-cause config defect behind
ENT-001/ENT-006 and should be reconciled with the real layout (or replaced by an explicit
`PYTHONPATH`).

**Evidence:**
```
# pyproject.toml:41-45
[tool.setuptools.packages.find]
where = ["."]
include = ["mko_bazuna*", "mko_bazuna.src", "mko_bazuna.core"]
exclude = ["tests/.pytest_cache*"]
# Actual top-level packages: src/backend/{apps,config}, src/telegram_bot
```

**Recommendation:** Update the packaging config to reflect reality (set `where` to the
directory containing `apps`/`config`/`telegram_bot`, or switch to an explicit `PYTHONPATH`
in the image), and document the chosen import-root strategy so the deployment contract is
clear. Mark as DOC-UPDATE because the layout works locally only by accident of `uv run`
cwd injection, which the container does not replicate.

---

## Summary

| Severity | Count |
|----------|-------|
| CRITICAL | 2 |
| HIGH | 2 |
| MEDIUM | 2 |
| LOW | 1 |

## Mandatory Fixes

- **ENT-001** (CRITICAL) — Container processes cannot boot: missing import paths for `config`/`apps`/`telegram_bot`.
- **ENT-002** (CRITICAL) — Bot imports Django models before `django.setup()` → `AppRegistryNotReady`; bot cannot boot.
- **ENT-003** (HIGH) — Blocking filesystem write on the async bot event loop (`save_photo`).
- **ENT-004** (HIGH) — Blocking network IO (synchronous translation) on the async bot event loop (`translate_to_russian`).

## Advisory Recommendations

- **ENT-005** (MEDIUM) — Give the `web` service an explicit `restart` policy in base compose.
- **ENT-006** (MEDIUM) — Fix CI test entry path so the test suite can run in-container (same root cause as ENT-001).
- **ENT-007** (LOW) — Reconcile `pyproject.toml` package discovery with the actual `src` layout / document the import-root strategy.

## Doc Updates Needed

- **ENT-007** — Update packaging/layout docs to reflect how `apps`/`config`/`telegram_bot` become importable in the container (currently only works locally by `uv run` cwd injection).

---

## Runtime Verification Notes

- **R1 (Import):** `import config` / `import telegram_bot.main` fail from repo root (ENT-001); `telegram_bot.main` import raises `AppRegistryNotReady` even with paths fixed (ENT-002). Both captured as tracebacks.
- **R2 (Boot):** Not reached — processes abort at import before any boot/init sequence (ENT-001/ENT-002).
- **R3 (Lint/Type):** `ruff check` → "All checks passed!"; `basedpyright` → 0 errors/warnings. No async/sync type errors surfaced (the blocking calls in ENT-003/ENT-004 are untyped `async def` wrappers, invisible to the checker).
- **R4 (Tests):** Suite cannot run from repo root / container (`ModuleNotFoundError: config`); collects 62 tests only after `PYTHONPATH=src/backend;src` is set (ENT-006).
- **R5 (Migration guard):** Advisory lock in `migrate_locked.py` is session-scoped and held on the parent connection for the whole subprocess duration; a second container blocks at `pg_advisory_lock(100)` until release, so concurrent migrate containers are serialized. **No defect found** in the migration-once guarantee — omitted from findings per problems-only rules.
- **R6 (Process isolation):** Shared state correctly lives only in DB / media FS (FSM in `MemoryStorage`, ad draft in ORM). No process-local-state assumption detected in entry layers.
