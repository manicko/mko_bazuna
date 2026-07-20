# Research Report: Bot Bootstrap Import-Order Restructure

**Task ID:** task_002_research_bot_bootstrap  
**Date:** 2026-07-20  
**Status:** COMPLETE — RECOMMENDATION: GO-WITH-CHANGES  
**Feeds:** task_007_fix_bot_import_order (ENT-002)

---

## 1. Problem Statement (ENT-002)

Two bootstrap defects combine to raise `django.core.exceptions.AppRegistryNotReady`
(or `ImproperlyConfigured`) before the bot event loop starts:

1. **Eager package import** — `telegram_bot/__init__.py` imports the `handlers`
   subpackage at package-import time. The handler modules import Django models at
   module level, so merely `import telegram_bot` touches an unready app registry.
2. **Wrong import order in `main.py`** — line 9 performs
   `from telegram_bot.middlewares import AccountStateMiddleware` at *module top
   level*, i.e. **before** `django.setup()` (line 15). `middlewares/permissions.py`
   imports `apps.users.models.User` at module level, so this import itself trips
   the unready registry.

---

## 2. Module Inventory (eager import chain)

### 2.1 `telegram_bot/__init__.py` (eager)

| Import | Resolves to | Touches Django models at import time? |
|--------|-------------|----------------------------------------|
| `from .states import AdCreateState` | `states.py` (pure `StrEnum`) | No — safe |
| `from .handlers import login_router, ad_create_router` | `handlers/__init__.py` | **Yes — see 2.3** |

### 2.2 `telegram_bot/middlewares/__init__.py` → `permissions.py`

| Import | Module-level Django dependency |
|--------|-------------------------------|
| `from apps.users.models import User` | **Yes** — `User` referenced at class/method definition (`User.DoesNotExist`, `User.objects`) |

### 2.3 `telegram_bot/handlers/__init__.py` → `{login, ad_create}.py`

**`handlers/login.py` (module level):**
- `from apps.users.models import User, LoginToken` — **Django models**
- `from apps.analytics.models import AnalyticsEvent` — **Django models**
- `from apps.core.enums import AnalyticsEventType` — enum only, safe

**`handlers/ad_create.py` (module level):**
- `from apps.ads.models import Ad, AdImage` — **Django models**
- `from apps.analytics.models import AnalyticsEvent` — **Django models**
- `from apps.categories.models import Category` — **Django models**
- `from apps.core.enums import AdStatus, AnalyticsEventType` — enum only, safe
- `from apps.locations.models import City` — **Django models**
- `from apps.moderation.models import ModerationCriteria` — **Django models**
- `from telegram_bot.states import AdCreateState` — pure enum, safe
- `from telegram_bot.schemas.message_payloads import (...)` — Pydantic only, safe
- `from telegram_bot.services.media import generate_storage_key, validate_photo` — PIL only, safe

> Note: `handlers/contact.py` imports its Django models **lazily inside functions**
> (`from apps.ads.models import Ad` at line 125, etc.), so it is NOT part of the
> eager chain.

---

## 3. Consumers of the `telegram_bot` Package (import-time dependents)

A repository-wide search (`grep -rn "import telegram_bot|from telegram_bot"`) across
all Python sources reveals **no external consumer** (no test, `manage.py`, config, or
web app imports the package).

### 3.1 Internal consumers

| Consumer | Import | Location | Timing |
|----------|--------|----------|--------|
| `main.py` | `from telegram_bot.middlewares import AccountStateMiddleware` | line 9 | **Top-level — BEFORE `django.setup()` (the bug)** |
| `main.py` | `from telegram_bot.handlers import login_router, ad_create_router` | line 33 | Lazy — inside `main()`, AFTER `django.setup()` |
| `handlers/login.py` | `from telegram_bot.handlers.contact import handle_contact_start` | line 53 | Lazy — inside `handle_login_deep_link()` |

### 3.2 Do any consumers rely on `import telegram_bot` side-effects?

The package `__init__.py` currently exposes `AdCreateState`, `login_router`,
`ad_create_router` via `__all__`. Verification of reliance:

- `login_router` / `ad_create_router` are consumed by `main.py` **directly from
  `telegram_bot.handlers`** (line 33), not from the package namespace
  (`telegram_bot.login_router`). → No reliance on package-level export.
- `AdCreateState` is consumed by `ad_create.py` **directly from
  `telegram_bot.states`**, not the package namespace. → No reliance.
- No test or module does `import telegram_bot` expecting the handler side-effects.

**Conclusion:** Removing the eager imports from `telegram_bot/__init__.py` breaks
nothing. The `AccountStateMiddleware` import in `main.py` targets the `middlewares`
submodule directly and is fully independent of the package `__init__`.

### 3.3 Dead/legacy paths

`src/telegram_bot/bot/{filters,handlers,states}/` are **empty directories** (no
`__init__.py`, no modules). They are not importable and have no effect on bootstrap.

---

## 4. Router Registration Order (correctness check)

- `login_router` and `ad_create_router` are module-level `Router()` instances
  (`router = Router()`), and all handlers are bound via `@router.message(...)` decorators
  **at module import time**.
- Registration only requires the handler modules to be imported (which happens after
  `django.setup()` once the eager `__init__.py` import and `main.py` top-level import
  are fixed). The relative order of including the two routers (`dp.include_router(...)`)
  is immaterial to correctness.

**Conclusion:** Reordering does not disturb router registration.

---

## 5. Recommended Import-Order Sequence

**BEFORE (broken):**

```python
import django
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from telegram_bot.middlewares import AccountStateMiddleware   # ❌ pulls apps.users.models

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.prod")
django.setup()                                                 # ❌ too late
```

**AFTER (fixed):**

```python
import django
import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.prod")
django.setup()                                                 # ✅ first

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from telegram_bot.middlewares import AccountStateMiddleware    # ✅ registry ready
```

**`telegram_bot/__init__.py` (make package import side-effect-free):**

```python
"""Telegram bot package for Mko Bazuna."""

# No eager submodule imports — Django models must only load after django.setup().
__all__: list[str] = []
```

(The `states` import may be retained since `states.py` is a pure `StrEnum` with no
Django dependency, but dropping it makes the package fully side-effect-free and is the
cleaner choice. Either is safe; recommend dropping for consistency.)

**`main.py` lazy handler import (already correct, keep as-is):** the
`from telegram_bot.handlers import login_router, ad_create_router` inside `main()`
remains valid because it runs after `django.setup()`.

---

## 6. Research Conclusion

### Verdict: **GO-WITH-CHANGES**

**Reasons to proceed:**
1. The reorder is **necessary** — `main.py` line 9 imports a Django-model-dependent
   submodule before `django.setup()`, guaranteeing `AppRegistryNotReady` at boot.
2. The reorder is **safe** — moving `django.setup()` to the very top of `main.py`,
   before any `telegram_bot.*` import, satisfies Django's requirement with no
   behavioural change.
3. Removing eager imports from `telegram_bot/__init__.py` is **safe** — no consumer
   (internal or external) relies on the package exposing `AdCreateState`,
   `login_router`, or `ad_create_router`. Verified by repo-wide grep: the only
   internal consumer of the routers imports them from `telegram_bot.handlers`
   directly.
4. Router registration is **unaffected** — handler modules are still imported after
   `django.setup()`; decorators bind at import time as before.

**Changes required (for task_007):**
1. In `main.py`: move `os.environ.setdefault(...)` + `django.setup()` to the top,
   before the `from telegram_bot.middlewares import AccountStateMiddleware` import.
2. In `telegram_bot/__init__.py`: remove the eager `from .handlers import ...`
   (and optionally `from .states import ...`) so the package has no side-effecting
   imports.
3. Keep the lazy `from telegram_bot.handlers import ...` inside `main()` — already
   safe.

**No hidden consumers found.** No tests import the package; no code depends on
`import telegram_bot` side-effects. The empty `bot/` subtree is inert.

---

## 7. Files Inspected (read-only)

- `src/telegram_bot/__init__.py`
- `src/telegram_bot/main.py`
- `src/telegram_bot/handlers/__init__.py`
- `src/telegram_bot/handlers/{login,ad_create,contact}.py`
- `src/telegram_bot/middlewares/__init__.py`
- `src/telegram_bot/middlewares/permissions.py`
- `src/telegram_bot/states.py`
- `src/telegram_bot/schemas/message_payloads.py`
- `src/telegram_bot/services/media.py`

No files modified for this research. Implementation is tracked in task_007.
