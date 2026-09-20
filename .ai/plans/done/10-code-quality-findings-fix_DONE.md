---
id: code-quality-findings-fix
domain: plan
status: COMPLETED (QLT-002, QLT-003 implemented and committed in 55ea635)
source: .ai/audit/99-validation/10-code-quality-validated-findings.md
commit: 55ea635
verification: tests/test_callbacks.py, tests/test_immediate_alerts.py, tests/test_unsubscribe.py, tests/test_language_middleware.py, tests/test_city_resolution_middleware.py, tests/test_preferred_city_middleware.py, tests/test_js_execution.py
tags:
  - code-quality
  - str-enum
  - middleware
  - type-safety
related:
  - .ai/audit/99-validation/10-code-quality-validated-findings.md
  - src/telegram_bot/schemas/callbacks.py
  - src/telegram_bot/handlers/alerts.py
  - src/telegram_bot/handlers/language.py
  - src/backend/apps/search/services/immediate_alerts.py
  - src/backend/apps/core/middleware/language.py
  - src/backend/apps/core/middleware/preferred_city.py
  - src/backend/apps/core/middleware/city_resolution.py
  - src/backend/apps/core/middleware/js_check.py
  - src/telegram_bot/tests/test_callbacks.py
---

# Execution Plan 10 — Code Quality Findings Fix (QLT-002, QLT-003)

> **Source:** `.ai/audit/99-validation/10-code-quality-validated-findings.md` (3 findings: 1 rejected, 2 validated)
> **Status:** QLT-002 and QLT-003 COMPLETED and committed; QLT-001 REJECTED (duplicate of Phase 05 AD-006)

---

## 0. Resolution Status

| ID | Findings (Validated) | Severity | Status |
|----|----|--------|--------|
| QLT-001 | Unused local variable `top` in `profile_queries.py:293` (F841) | LOW | **REJECTED** — duplicate of Phase 05 AD-006 |
| QLT-002 | Three callback-data prefix constants as raw strings outside `BotCallbackPrefix` StrEnum | HIGH | **COMPLETED** |
| QLT-003 | Middleware layer types `request`/`response` as `Any` instead of concrete Django HTTP types | HIGH | **COMPLETED** |

---

## 1. Block Summary

### 1.1 QLT-003 — Middleware `Any` → concrete types (COMPLETED)

**Files modified:**

| File | Change |
|---|---|
| `src/backend/apps/core/middleware/js_check.py` | `Any` → `HttpRequest`; removed `from typing import Any`; added `from django.http import HttpRequest` |
| `src/backend/apps/core/middleware/language.py` | 5 `Any` → `HttpRequest`/`HttpResponse`; replaced `-> Any` with `-> HttpResponse` in `process_response`; updated imports |
| `src/backend/apps/core/middleware/preferred_city.py` | 3 `Any` → `HttpRequest`/`HttpResponse`; replaced `-> Any` with `-> HttpResponse` in `process_response`; updated imports |
| `src/backend/apps/core/middleware/city_resolution.py` | 1 `Any` → `HttpRequest`; updated imports |

**Safety:** Annotation-only change. `reportAttributeAccessIssue = "none"` in `pyproject.toml` suppresses errors on dynamically-set request attributes (`request.preferred_city`, `request.current_city`, `request.js_verified`, `request._lang_cookie_value`).

### 1.2 QLT-002 — Callback-data prefix StrEnum consolidation (COMPLETED)

**Files modified:**

| File | Change |
|---|---|
| `src/telegram_bot/schemas/callbacks.py` | Added `UNSUB = "unsub:"`, `UNSUB_ON = "unsub_on:"`, `LANG = "lang:"` members to `BotCallbackPrefix` StrEnum |
| `src/backend/apps/search/services/immediate_alerts.py` | `UNSUB_CALLBACK_PREFIX = "unsub:"` → `UNSUB_CALLBACK_PREFIX = BotCallbackPrefix.UNSUB` (enum reference); added `from telegram_bot.schemas.callbacks import BotCallbackPrefix` |
| `src/telegram_bot/handlers/alerts.py` | Removed `UNSUB_ON_PREFIX = "unsub_on:"` and import of `UNSUB_CALLBACK_PREFIX` from backend; all usages now use `BotCallbackPrefix.UNSUB` / `BotCallbackPrefix.UNSUB_ON` directly |
| `src/telegram_bot/handlers/language.py` | Removed `LANG_CALLBACK_PREFIX = "lang:"`; all usages now use `BotCallbackPrefix.LANG` directly |

**Dependency direction:** The `UNSUB_CALLBACK_PREFIX` constant definition is preserved in `immediate_alerts.py` (backend) to avoid a backend→bot dependency reversal on the definition. It references the enum value (`BotCallbackPrefix.UNSUB`) as the single source of truth. This is safe because `callbacks.py` only imports from `enum.StrEnum` — no circular import.

### 1.3 Tests added

| File | Test | Purpose |
|---|---|---|
| `src/telegram_bot/tests/test_callbacks.py` (new) | `TestBotCallbackPrefixValues` | Regression guard: all enum members (including new UNSUB/UNSUB_ON/LANG) produce the exact string values expected by callback routing filters and f-string construction |

---

## 2. Verification

| Check | Command | Result |
|---|---|---|
| Lint (ruff) | `uv run ruff check <all modified files>` | PASS — 0 errors |
| Type check (basedpyright) | `uv run basedpyright <all modified files>` | PASS — 0 errors, 0 warnings, 0 notes |
| Callback + middleware tests | Docker Compose `test` service | PASS — 80 tests, 13.89s |

**Tests run:** `test_callbacks.py`, `test_immediate_alerts.py`, `test_unsubscribe.py`, `test_language_middleware.py`, `test_city_resolution_middleware.py`, `test_preferred_city_middleware.py`, `test_js_execution.py`

---

## 3. Rollout Safety

| Finding | Risk | Backward-compatible? | Test gap |
|---|---|---|---|
| QLT-002 | Low — enum values are identical strings | Yes — `StrEnum` members are `str` subclasses; f-strings, `startswith()`, and `len()` all work unchanged | Regression test asserting enum values + f-string/startswith interop |
| QLT-003 | Low — annotation-only change | Yes — no runtime change | Existing middleware tests cover all behavior |
| QLT-001 | N/A — rejected | N/A — rejected (duplicate of Phase 05 AD-006) | N/A |
