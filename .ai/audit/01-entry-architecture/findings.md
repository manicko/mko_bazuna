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
Either (a) install the project as an editable/installed package in the image
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
