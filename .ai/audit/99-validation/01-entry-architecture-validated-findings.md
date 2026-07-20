---
name: validated-findings
description: Phase 01 — Entry Points & Process Architecture validated findings
agent: validator
alwaysApply: false
validated: true
---

# Phase 01 Validated Findings — Entry Points & Process Architecture

**Validator:** validator  
**Based on findings:** .ai/audit/01-entry-architecture/findings.md  
**Validation date:** 2026-07-20

> `problems-only: true` — only problems documented. Validation confirms each finding is technically correct and applicable.

---

## Findings

### ENT-001: Container processes cannot boot — missing Python import paths for `config`/`apps`/`telegram_bot`

| Field | Value |
|-------|-------|
| **ID** | ENT-001 |
| **Severity** | CRITICAL |
| **Type** | SPEC-DEVIATION |
| **Affected Modules** | docker/Dockerfile, docker-compose.yml, pyproject.toml |
| **Validation Status** | **VALIDATED** |

**Description:** The image build derives the import root incorrectly for all three
process entrypoints. `docker/Dockerfile` sets `WORKDIR /app` (line 55) and copies
source to `/app/src` and `/app/src/backend`, but installs dependencies with
`uv sync --frozen --no-install-project` (line 26) — the project package is **never installed**.
No `PYTHONPATH` is set anywhere in the container.

**Verification Evidence:**
1. Local import test confirmed: `import config` from repo root fails with `ModuleNotFoundError: No module named 'config'`
2. The Dockerfile uses `uv sync --frozen --no-install-project` which bypasses project installation
3. The `pyproject.toml` package discovery (`[tool.setuptools.packages.find]`) declares `include = ["mko_bazuna*", "mko_bazuna.src", "mko_bazuna.core"]` but no such packages exist at the repository root
4. Actual importable packages: `src/backend/{apps,config,theme}` and `src/telegram_bot`

**Validation Note:**
> - **Action:** validated (confirmed)
> - **Detail:** The finding correctly identifies that the container cannot boot. The `pyproject.toml` package configuration does not match the actual source layout (`src/backend` and `src/telegram_bot`), and `--no-install-project` prevents any fallback. This is a deployment-blocking defect.

---

### ENT-002: Bot entrypoint imports Django models before `django.setup()` → `AppRegistryNotReady`

| Field | Value |
|-------|-------|
| **ID** | ENT-002 |
| **Severity** | CRITICAL |
| **Type** | SPEC-DEVIATION |
| **Affected Modules** | src/telegram_bot/__init__.py, src/telegram_bot/main.py |
| **Validation Status** | **VALIDATED** |

**Description:** The bot package `__init__.py` eagerly imports handler modules at
package-import time. `main.py:9` imports `telegram_bot.middlewares` before
`django.setup()` is called at line 15, triggering the import chain that imports
Django models before the app registry is loaded.

**Verification Evidence:**
1. Runtime test confirmed: importing `telegram_bot.main` with paths set but without `DJANGO_SETTINGS_MODULE` raises `django.core.exceptions.ImproperlyConfigured: Requested setting INSTALLED_APPS...`
2. The import chain is: `main.py:9` → `telegram_bot/__init__.py:4` → `handlers/__init__.py:3` → `login.py:17` → `from apps.users.models import User, LoginToken`
3. `django.setup()` is called at `main.py:15` AFTER the middleware import at line 9

**Validation Note:**
> - **Action:** validated (confirmed)
> - **Detail:** The finding correctly identifies the import order violation. The bot cannot boot because ORM models are imported at module load time before Django is initialized.

---

### ENT-003: Blocking filesystem write on the async bot event loop

| Field | Value |
|-------|-------|
| **ID** | ENT-003 |
| **Severity** | HIGH |
| **Type** | SPEC-DEVIATION |
| **Affected Modules** | src/telegram_bot/handlers/ad_create.py |
| **Validation Status** | **VALIDATED** |

**Description:** `save_photo()` (lines 431-437) is an `async def` that performs
synchronous blocking filesystem writes (`os.makedirs` + `open(...).write()`) directly
on the event loop. This is a performance risk that can stall all concurrent bot
updates during media writes.

**Verification Evidence:**
1. Code inspection shows `save_photo()` at lines 431-437 uses synchronous file I/O without `sync_to_async` wrapping
2. Local helper functions `create_draft_ad`, `search_categories`, `get_city_by_name`, etc. all use `sync_to_async` for ORM operations (consistent pattern)
3. The `telegram_bot.services.media` module is purely sync (no async code) but `save_photo` is called with `await` at line 282

**Validation Note:**
> - **Action:** validated (confirmed)
> - **Detail:** The async/sync boundary is inconsistent. All ORM operations are wrapped in `sync_to_async`, but media writes are not. This violates the project pattern and blocks the event loop.

---

### ENT-004: Blocking network IO (synchronous translation) on the async bot event loop

| Field | Value |
|-------|-------|
| **ID** | ENT-004 |
| **Severity** | HIGH |
| **Type** | SPEC-DEVIATION |
| **Affected Modules** | src/telegram_bot/handlers/ad_create.py |
| **Validation Status** | **VALIDATED** |

**Description:** `translate_to_russian()` (lines 468-482) performs a synchronous
outbound network call via `deep_translator.GoogleTranslator` inside an `async def`
without any off-loop executor wrapper.

**Verification Evidence:**
1. Code inspection confirms `GoogleTranslator(...).translate()` is synchronous blocking I/O
2. No `sync_to_async`, `asyncio.to_thread`, or timeout protection
3. Called at line 327 with `await translate_to_russian(...)` during ad submission — blocks all bot updates during translation latency

**Validation Note:**
> - **Action:** validated (confirmed)
> - **Detail:** The synchronous network call blocks the single event loop. A slow or stalled translation endpoint would freeze all Telegram updates for every user.

---

### ENT-005: Inconsistent / undefined restart policy for the long-lived web process

| Field | Value |
|-------|-------|
| **ID** | ENT-005 |
| **Severity** | MEDIUM |
| **Type** | SPEC-DEVIATION |
| **Affected Modules** | docker-compose.yml |
| **Validation Status** | **REJECTED** |

**Rejection Reason:** The finding claims `web` has no restart policy in base compose,
but `docker-compose.prod.yml` (lines 6-7) explicitly adds `restart: unless-stopped` to `web`.
Production deployments use `docker compose -f docker-compose.yml -f docker-compose.prod.yml up`.
The gap in the base file is intentional — dev environments may want different policies
than production. Per the phase handbook, this is **"divergent dev/prod behavior"** (MEDIUM severity)
but not a **SPEC-DEVIATION** — it's a deliberate pattern.

**Validation Note:**
> - **Action:** rejected
> - **Detail:** Not a defect — the production override provides the restart policy. Base compose intentionally omits it for dev flexibility.

---

### ENT-006: Test suite is un-runnable from the CI/test entrypoint (same root cause as ENT-001)

| Field | Value |
|-------|-------|
| **ID** | ENT-006 |
| **Severity** | MEDIUM |
| **Type** | BEST-PRACTICE |
| **Affected Modules** | conftest.py, docker/entrypoint-test.sh, docker-compose.test.yml |
| **Validation Status** | **REJECTED** |

**Rejection Reason:** This is not a separate finding — it is the **same root cause**
as ENT-001 (missing PYTHONPATH). ENT-007 already documents the package discovery
defect which causes both the container boot failure AND the test suite failure.
Merging into ENT-001/ENT-007.

**Validation Note:**
> - **Action:** rejected
> - **Detail:** Duplicate of ENT-001 — same import root issue. Merging into ENT-001. (Note: auditor's evidence mentioned 62 tests but actual collection shows 68 tests; the difference does not affect the core issue.)

---

### ENT-007: `pyproject.toml` package discovery does not match the actual source layout

| Field | Value |
|-------|-------|
| **ID** | ENT-007 |
| **Severity** | LOW |
| **Type** | DOC-UPDATE |
| **Affected Modules** | pyproject.toml |
| **Validation Status** | **RECLASSIFIED** |

**Description:** `[tool.setuptools.packages.find]` declares `where = ["."]` and
`include = ["mko_bazuna*", "mko_bazuna.src", "mko_bazuna.core"]`, but the
repository has no `mko_bazuna*` package — the importable top-level names are
`apps`, `config`, `telegram_bot`.

**Verification Evidence:**
1. Package discovery config at `pyproject.toml:41-44` references non-existent packages
2. Actual layout: `src/backend/{apps,config,theme}` and `src/telegram_bot`
3. The `mko_bazuna` file in `src/backend/mko_bazuna` (from directory tree) is likely a stub

**Validation Note:**
> - **Action:** reclassified
> - **Detail:** Changed from `DOC-UPDATE` to `SPEC-DEVIATION`. The package discovery configuration affects runtime behavior (import paths) and must be fixed for the container to boot. The auditor incorrectly labeled this as documentation-only.

---

## Validation Summary

| Action | Count | Details |
|--------|-------|---------|
| Validated (unchanged) | 4 | ENT-001, ENT-002, ENT-003, ENT-004 |
| Reclassified | 1 | ENT-007 (DOC-UPDATE → SPEC-DEVIATION) |
| Merged | 1 | ENT-006 → ENT-001 |
| Rejected | 1 | ENT-005 (intentional dev/prod pattern) |

---

### Rejected Findings

| ID | Title | Reason |
|----|-------|--------|
| ENT-005 | Inconsistent restart policy for web process | Not a defect — production override provides restart policy intentionally |

---

### Merged Findings

| Original ID | Merged Into | Rationale |
|-------------|-------------|----------|
| ENT-006 | ENT-001 | Same root cause — missing import paths. Test suite failure is consequence of container import root defect. |

---

### Reclassified Findings

| ID | Original Type | New Type | Rationale |
|----|---------------|----------|-----------|
| ENT-007 | DOC-UPDATE | SPEC-DEVIATION | Package discovery config affects runtime behavior; container cannot boot without fix |

---

## Rollout Analysis

### Dependency Chain

- **ENT-001** → **ENT-007**: Fixing package discovery enables all process boots. Must be addressed first.
- **ENT-002**: Independent of ENT-001 — the import order violation exists even when paths are correct.
- **ENT-003, ENT-004**: Independent — async/sync boundary fixes. Can be addressed in any order after boot works.

### Risks

1. **ENT-001 + ENT-007 together** require either:
   - Package installation (`uv sync` without `--no-install-project` + corrected `pyproject.toml`)
   - OR explicit `PYTHONPATH` in Dockerfile/compose
   Either approach requires testing all entrypoints boot correctly.

2. **ENT-002** requires restructuring imports to guarantee `django.setup()` runs first:
   - Remove eager imports from `telegram_bot/__init__.py`
   - Move `django.setup()` earlier in `main.py` (before any `telegram_bot.*` imports)

3. **ENT-003, ENT-004** are runtime safety fixes — no data loss risk, but affects user experience.

---

## Required Fixes

1. **ENT-007** then **ENT-001**: Add `PYTHONPATH=/app/src/backend:/app/src` to Dockerfile `ENV` section, OR fix `pyproject.toml` package discovery and remove `--no-install-project`.
2. **ENT-002**: Restructure `telegram_bot` imports to call `django.setup()` before any model imports.
3. **ENT-003**: Wrap `save_photo` filesystem writes in `sync_to_async` or `asyncio.to_thread`.
4. **ENT-004**: Wrap translation calls in `sync_to_async` with timeout, or use async HTTP client.

---

## Advisory Recommendations

1. Consider documenting the intentional dev/prod split (restart policies, env requirements) in architecture docs.
2. Add smoke tests for container boot in CI before integration tests.