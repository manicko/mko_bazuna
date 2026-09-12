# Phase 02 Execution Plan — Configuration & Secrets (CFG-001 through CFG-007)

**Source:** Validated findings — `.ai/audit/99-validation/02-config-secrets-validated-findings.md`
**Working-tree context:** `.ai/plans/code-context-02-config-secrets.md`
**Status:** Ready for execution (all 7 findings validated against working tree)

---

## 1. Execution DAG

```
 ┌─────────────────────────────────────────────────────────┐
 │  PARALLEL-GROUP 1 — Independent, no shared files        │
 │  (all Implementor tasks)                                 │
 │                                                          │
 │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐
 │  │ CFG-001      │  │ CFG-003      │  │ CFG-005      │  │ CFG-006      │
 │  │ HIGH / MAND  │  │ MEDIUM       │  │ LOW          │  │ LOW          │
 │  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘
 │         │                  │                  │                 │
 │         ▼                  ▼                  ▼                 ▼
 │  verify-001 ◄         verify-003 ◄         verify-005 ◄      verify-006 ◄
 └─────────┬──────────────────┬──────────────────┬──────────────────┘
           │                  │                  │
           │                  │                  │
 ┌─────────▼──────────────────▼──────────────────▼──────────┐
 │  SEQUENTIAL PAIR — same source file (base.py)               │
 │                                                            │
 │  ┌──────────────┐     ┌──────────────┐                     │
 │  │ CFG-002      │────▶│ CFG-004      │                     │
 │  │ MEDIUM       │     │ LOW          │                     │
 │  └──────┬───────┘     └──────┬───────┘                     │
 │         ▼                    ▼                              │
 │  verify-002/004                                           │
 └───────────────────────────────────────────────────────────┘

 CFG-007 (docs) runs AFTER CFG-001 — same doc file (docker-deployment.md),
 non-overlapping sections, sequenced to preserve edit-context stability.
```

### Dependency summary

| Block | Depends on | Blocks in parallel | Agent |
|---|---|---|---| 
| CFG-001 | — | CFG-003, CFG-005, CFG-006, CFG-002 | Implementor |
| CFG-002 | — | CFG-001, CFG-003, CFG-005, CFG-006 | Implementor |
| CFG-003 | — | CFG-001, CFG-002, CFG-005, CFG-006 | Implementor |
| CFG-004 | CFG-002 | — (same file; sequential after CFG-002) | Implementor |
| CFG-005 | — | CFG-001, CFG-002, CFG-003, CFG-006 | Implementor |
| CFG-006 | — | CFG-001, CFG-002, CFG-003, CFG-005 | Implementor |
| CFG-007 | CFG-001 | — (shares docker-deployment.md; after CFG-001) | Implementor |

---

## 2. Block Specifications

### Block CFG-001 — Remove weak default admin credential (HIGH / MANDATORY)

**Agent type:** Implementor
**Risk:** HIGH (security-critical), but change is trivial: two compose substitutions.

**Semantic targets:**
- `docker-compose.yml` — `create_admin` service `environment` list, the `ADMIN_PASSWORD`
  substitution (currently `${ADMIN_PASSWORD:-admin}`)
- `docker-compose.dev.override.yml` — `web` service `environment` list, the `ADMIN_PASSWORD`
  substitution (currently `${ADMIN_PASSWORD:-admin}`)
- `.env.docker.example` — `Admin` section (`ADMIN_PASSWORD=` comment)
- `docs/ops/docker-deployment.md` — `Admin User Setup` section

**Implementation spec:**
1. In `docker-compose.yml` and `docker-compose.dev.override.yml`, change:
   `${ADMIN_PASSWORD:-admin}` -> `${ADMIN_PASSWORD:?ADMIN_PASSWORD must be set}`
   This makes the variable fail-fast at compose-interpolation time when unset/empty, restoring the
   intended contract of `docker/entrypoint-create-admin.sh`'s
   `if [ -z "${ADMIN_PASSWORD}" ]; then exit 0` skip-guard.
2. In `.env.docker.example`, ensure the `Admin` section comment clarifies that `ADMIN_PASSWORD` is
   required for auto-creation (empty = skip per entrypoint guard; unset in compose env = fail-fast
   via `:?`). The existing empty value `ADMIN_PASSWORD=` is correct for the env-file template; the
   comment should state the compose substitution now uses `:?`.
3. In `docs/ops/docker-deployment.md` -> `Admin User Setup` section, update prose to state
   `ADMIN_PASSWORD` is **required** in the compose environment (no silent `admin`/`admin` default);
   omitting it fails fast rather than creating a default superuser.

**Dependencies:** None. This is the root mandatory fix.

**Tests / verification:**
- verify-001a: `docker compose --project-name cfg-check -f docker-compose.yml
  -f docker-compose.dev.override.yml config` (without `ADMIN_PASSWORD` in env) must emit
  a `required`/interpolation error — confirms fail-fast.
- verify-001b: Same command with `--env-file .env.docker` piped to `grep ADMIN_PASSWORD`
  must show the env value (or empty from `env_file`), NOT `admin`.
- verify-001c: `bash -n docker/entrypoint-create-admin.sh` — syntax check (entrypoint unchanged,
  but confirm skip-guard path still parses).
- No unit-test impact (compose/env-only change; no Python or test code touched).

**Documentation affected:** `.env.docker.example` (admin section comment),
`docs/ops/docker-deployment.md` (Admin User Setup section).

---

### Block CFG-002 — Remove dead `DATABASE_URL` / `REDIS_URL` module-level settings (MEDIUM)

**Agent type:** Implementor
**Risk:** LOW — zero external consumers (grep-confirmed); `DATABASES`/`CACHES` already build from
`env(...)` directly.

**Semantic targets:**
- `src/backend/config/settings/base.py` — the `DATABASE_URL` module-level assignment and the
  `REDIS_URL` module-level assignment (the `DATABASES` `if/else` block and the `CACHES` dict remain)

**Implementation spec:**
1. Delete the `DATABASE_URL = os.getenv("DATABASE_URL")` module-level assignment.
2. In the `if` guard that referenced the deleted variable (`if DATABASE_URL:`), replace with a
   direct env-var read: `if os.getenv("DATABASE_URL"):`. **Rationale:** this is a control-flow
   guard (chooses between `env.db()` URL-parsing branch and the discrete `POSTGRES_*` branch), not a
   setting consumed elsewhere — CFG-004 explicitly permits `os.getenv` for control-flow guards.
3. Delete the dead `REDIS_URL = env(...)` module-level assignment.
   `CACHES["default"]["LOCATION"]` already calls `env("REDIS_URL", default=...)` inline — no change
   needed there.

**Dependencies:** Must precede CFG-004 (same file, `base.py`). No other finding depends on the
deleted settings attributes (`settings.DATABASE_URL` / `settings.REDIS_URL` have zero consumers per
grep).

**Tests / verification:**
- verify-002a: `test_settings_secrets.py` (3 tests, subprocess-isolated import-time guards) —
  `pytest config/settings/tests/test_settings_secrets.py -v`
- verify-002b: Settings import smoke: `python -c "import django; django.setup()"`
  under dev/test/prod modules.
- verify-002c: Confirm `settings.DATABASE_URL` and `settings.REDIS_URL` no longer exist as
  attributes (AttributeError) — prevents accidental future consumers.
- verify-002d: `ruff check src/backend/config/settings/` and
  `basedpyright src/backend/config/settings/base.py`

**Documentation affected:** None.

---

### Block CFG-004 — Standardize settings loaders on `env()` with explicit casts (LOW)

**Agent type:** Implementor
**Risk:** LOW — purely local to settings loading; settings import-time tests guard regressions.

**Semantic targets:**
- `src/backend/config/settings/base.py` — the `os.getenv(...)` calls that load Django settings
  (not control-flow guards)

**Implementation spec:**

Replace the following `os.getenv` calls with `django-environ` typed loaders:

| Setting (base.py) | Current | Replacement |
|---|---|---|
| `GOOGLE_TRANSLATE_API_KEY` | `os.getenv("...", "")` | `env("...", default="")` |
| `ALLOWED_HOSTS` | `os.getenv(...).split(",")` if non-empty else `[]` | `env.list("ALLOWED_HOSTS", default=[])` |
| `POSTGRES_DB` | `os.getenv(..., "mko_bazuna")` | `env(..., default="mko_bazuna")` |
| `POSTGRES_USER` | `os.getenv(..., "postgres")` | `env(..., default="postgres")` |
| `POSTGRES_HOST` | `os.getenv(..., "localhost")` | `env(..., default="localhost")` |
| `POSTGRES_PORT` | `os.getenv(..., "5432")` | `env(..., default="5432")` |
| `BOT_USERNAME` | `os.getenv(..., "")` | `env(..., default="")` |
| `BOT_LIVENESS_FILE` | `os.getenv(..., "/tmp/...")` | `env(..., default="/tmp/...")` |
| `SITE_URL` | `os.getenv(...).rstrip("/")` | `env(..., default="...").rstrip("/")` |
| `IMMEDIATE_ALERTS_ENABLED` | manual `.lower() in ("1","true","yes")` | `env.bool(..., default=False)` |
| `PLAUSIBLE_HOST` | `os.getenv(..., "")` | `env(..., default="")` |

`POSTGRES_PASSWORD` already uses typed `env(...)` — leave as-is.

**Retained `os.getenv` (control-flow guards only):**
- `base.py` — the `DJANGO_BUILD` / `DJANGO_SETTINGS_MODULE` / `DJANGO_SECRET_KEY` guard that decides
  whether to `sys.exit(1)` when `.env` is missing.
- `prod.py` — `os.getenv("DJANGO_BUILD")` and `os.getenv("SITE_URL")` guards in fail-fast checks.

**Dependencies:** Must run AFTER CFG-002 (same file). No other finding depends on these loaders.

**Tests / verification:**
- verify-004a: `test_settings_secrets.py` (3 tests) —
  `pytest config/settings/tests/test_settings_secrets.py -v`
- verify-004b: `ruff check src/backend/config/settings/`
- verify-004c: `basedpyright src/backend/config/settings/base.py` (0 errors, 0 warnings — matches
  audit R5)
- verify-004d: Settings import smoke across dev/prod/test modules with sample env.

**Documentation affected:** None (code-only cleanup).

---

### Block CFG-003 — Add Pydantic DTO for bulk moderation API (MEDIUM)

**Agent type:** Implementor
**Risk:** LOW — admin-only endpoint (`@staff_required_api`), no frontend/template caller
  (grep-confirmed), per-item `try/except` containment already present.

**Semantic targets:**
- **New file:** `src/backend/apps/moderation/schemas.py`
- **Modify:** `src/backend/apps/moderation/views/api_bulk.py` — the request-body parsing in
  `bulk_moderation_action()`

**Implementation spec:**

1. **Create `src/backend/apps/moderation/schemas.py`** following the established pattern in
   `apps/users/schemas.py` and `src/telegram_bot/schemas/message_payloads.py`:

   ```python
   from __future__ import annotations

   from pydantic import BaseModel, ConfigDict

   from apps.core.enums import BulkModerationAction


   __all__ = ["BulkModerationRequest"]


   class BulkModerationRequest(BaseModel):
       """Pydantic v2 DTO for the bulk-moderation JSON API boundary (rule 11).

       Validates the request body before any DB write. ``extra="forbid"``
       rejects unknown keys instead of silently dropping them.
       """

       model_config = ConfigDict(extra="forbid")

       action: BulkModerationAction
       selected_items: list[int]
       reason: str = ""
   ```

2. **Modify `bulk_moderation_action()` in `api_bulk.py`:**
   - Remove `import json` (no longer needed directly).
   - Add imports: `from pydantic import ValidationError` and
     `from apps.moderation.schemas import BulkModerationRequest`.
   - Replace the `json.loads(request.body)` + `dict.get(...)` block with:
     ```python
     try:
         payload = BulkModerationRequest.model_validate_json(request.body)
     except ValidationError as e:
         logger.warning("Invalid bulk moderation request body: %s", e)
         return JsonResponse(
             {"error": "Invalid request body", "details": e.errors()},
             status=400,
         )
     ```
   - Replace `action = data.get("action", "")` with `payload.action` (already a
     `BulkModerationAction`).
   - Replace `ad_ids: list[int] = data.get("selected_items", [])` with `payload.selected_items`.
   - Replace `reason: str = data.get("reason", "")` with `payload.reason`.
   - Remove the now-redundant `try/except ValueError` around `BulkModerationAction(action)` (the DTO
     already validates the enum).
   - Keep the `MAX_BULK_ACTIONS` cap check (now: `if len(payload.selected_items) > MAX_BULK_ACTIONS`)
     and the per-item processing loop unchanged.

**Dependencies:** `BulkModerationAction` enum exists in `apps/core/enums.py`. Pydantic v2 is a
  declared dependency. No other finding affects this module.

**Tests / verification:**
- verify-003a: **Existing tests must pass unchanged** (backward-compatible valid payloads):
  `pytest apps/moderation/tests/test_priority_service.py::TestBulkModerationActionView -v`
  - `test_bulk_approve`, `test_bulk_reject`, `test_bulk_flag`,
    `test_error_messages_sanitized`, `test_bulk_exceeds_max_actions_returns_400`,
    `test_bulk_at_max_actions_accepted` — unaffected.
- verify-003b: **Existing error-message tests must be updated** (error response format changes with
  Pydantic validation; per "Production Code is King" rule, update tests to match):
  - `test_unknown_action_returns_400` — `action="unknown"` now fails at DTO validation (not the
    manual `BulkModerationAction(action)` coercion). Update to assert 400 + new error structure.
  - `test_malformed_json_body_returns_400` — `"not-json"` body now raises `ValidationError` from
    `model_validate_json`. Update assertion to match new 400 response.
  - `test_empty_body_returns_400` — empty body -> `ValidationError`. Update assertion.
- verify-003c: **Add new test:** extra key in request body
  (`{"action":"approve","selected_items":[],"rogue":"x"}`) -> 400 (enforced by `extra="forbid"`).
- verify-003d: **Add new test:** `selected_items` as non-list (`"not-a-list"`) -> 400 (Pydantic
  type validation).
- verify-003e: `ruff check src/backend/apps/moderation/schemas.py
  src/backend/apps/moderation/views/api_bulk.py`
- verify-003f: `basedpyright` on both files.

**Documentation affected:** None (admin-only API, no template/frontend caller, no public spec section
  that documents the exact 400 error payload).

---

### Block CFG-005 — Prevent credential exposure in entrypoint process args (LOW)

**Agent type:** Implementor
**Risk:** LOW — same env vars used; only the mechanism changes (inside-Python vs shell-expanded args).

**Semantic targets:**
- `docker/entrypoint.sh` — the `wait_for_db()` function's Python probe and the
  `wait_for_redis()` function's Python probe

**Implementation spec:**

1. In `wait_for_db()`, change:
   ```bash
   /opt/venv/bin/python -c "import psycopg; psycopg.connect('$DATABASE_URL')" 2>/dev/null
   ```
   to:
   ```bash
   /opt/venv/bin/python -c "import os, psycopg; psycopg.connect(os.environ['DATABASE_URL'])" 2>/dev/null
   ```
   The shell no longer interpolates the credential-bearing URL into the process argument list;
   Python reads it from `os.environ` at runtime.

2. In `wait_for_redis()`, change:
   ```bash
   /opt/venv/bin/python -c "import redis; redis.from_url('$REDIS_URL').ping()" 2>/dev/null
   ```
   to:
   ```bash
   /opt/venv/bin/python -c "import os, redis; redis.from_url(os.environ['REDIS_URL']).ping()" 2>/dev/null
   ```

**Dependencies:** None. Independent of all other findings.

**Tests / verification:**
- verify-005a: `bash -n docker/entrypoint.sh` — syntax check.
- verify-005b: Manual compose deploy verification — during container startup, confirm
  `/proc/<python-pid>/cmdline` does NOT contain `postgres://user:pass@...` or
  `redis://:password@...`. The cmdline should show only the Python source with `os.environ[...]`.
- No automated unit test exists for this shell script; verification is operational (manual
  inspection of process args during deploy).

**Documentation affected:** None.

---

### Block CFG-006 — Remove stale 0-byte root entrypoint stubs (LOW)

**Agent type:** Implementor
**Risk:** ZERO — stubs are 0 bytes, tracked only. Real implementations live in `docker/entrypoint*.sh`.
  The shipping Docker image is unaffected (Dockerfile runtime stage `COPY`s
  `docker/entrypoint*.sh` after the builder's `COPY . .`, overwriting the stubs).

**Semantic targets:**
- Root-level tracked files: `entrypoint.sh`, `entrypoint-catalog.sh`, `entrypoint-seed.sh`,
  `entrypoint-test.sh` (all 0 bytes)

**Implementation spec:**
```bash
git rm entrypoint.sh entrypoint-catalog.sh entrypoint-seed.sh entrypoint-test.sh
```
This removes the four 0-byte, git-tracked root stub files. No replacement content is needed — the
canonical implementations in `docker/entrypoint*.sh` are already the single source of truth.

**Dependencies:** None. Independent. Must be done before any deploy verification that references
entrypoint paths.

**Tests / verification:**
- verify-006a: `git ls-files entrypoint*.sh` (root) returns empty — confirms all four are removed.
- verify-006b: `git status --short` shows the four deletions as staged removals.
- verify-006c: Confirm no compose YAML or Makefile references the root `./entrypoint*.sh` path
  (already grep-confirmed: compose files all use `docker/entrypoint*.sh` or `/app/entrypoint*.sh`;
  Makefile references are comments only). Re-confirm after removal.
- verify-006d: `docker compose config` resolves successfully.

**Documentation affected:** Confirm no docs reference root `./entrypoint*.sh` paths. Per audit, all
docs point at `docker/entrypoint*.sh`. No doc edits required.

---

### Block CFG-007 — Align `.env` file-path documentation (LOW / DOC)

**Agent type:** Implementor
**Risk:** ZERO — doc-only changes + deletion of a gitignored 0-byte file. No code or compose
  changes. Zero production risk.

**Semantic targets:**
- `.env.example` (header comment, lines 2-3)
- `docs/ops/docker-deployment.md` (Database Configuration section, ~lines 193-194)
- `src/.env` (stray 0-byte gitignored file to delete)

**Implementation spec:**

1. **`.env.example`** header comment: Change from:
   `# Copy this file to .env (at the repository root, NOT inside src/backend/)`
   to:
   `# Copy this file to src/.env`

2. **`docs/ops/docker-deployment.md`** Database Configuration section: Update the local-dev note.
   Current:
   > For local Django development outside Docker (using `uv run` directly), use `.env`
   > (auto-loaded by Compose) with `DATABASE_URL` pointing to `localhost`
   Change to:
   > For local Django development outside Docker (using `uv run` directly), copy
   > `.env.example` to `src/.env`. Django's settings (`base.py`) call
   > `environ.Env.read_env(BASE_DIR / ".env")`, which resolves to `src/.env`
   > (`BASE_DIR` = `<repo>/src`). `uv run` also implicitly injects `src/.env` into the
   > process environment, so both paths resolve to the same file.

3. **Delete `src/.env`** (0-byte, gitignored): `rm src/.env`. This file currently masks the
   `.env`-not-found issue by satisfying `env_path.exists()` in `base.py`. Deleting it ensures
   the explicit `read_env` contract is visible (non-`uv` invocations correctly fail-fast if
   `src/.env` is not created).

**Dependencies:** Must run AFTER CFG-001 (both edit `docs/ops/docker-deployment.md`; non-overlapping
  sections, sequenced for edit-context stability). No code dependency.

**Tests / verification:**
- verify-007a: Read `.env.example` header — confirm it reads `Copy this file to src/.env`.
- verify-007b: Read `docs/ops/docker-deployment.md` Database Configuration section — confirm the
  local-dev note states `src/.env` is the canonical path.
- verify-007c: Confirm `src/.env` is deleted (`Test-Path src/.env` returns False).
- No test suite impact (doc-only + gitignored file).

**Documentation affected:** This block IS the documentation update (`.env.example`,
  `docs/ops/docker-deployment.md`).

---

## 3. Verification Matrix

| Block | Gate type | Command / check | Pass criteria |
|---|---|---|---|
| CFG-001 | Compose config | `docker compose ... config` (no `ADMIN_PASSWORD`) | Fails with required-interpolation error |
| CFG-001 | Compose config | `docker compose ... --env-file .env.docker config \| grep ADMIN_PASSWORD` | Shows env value, not `admin` |
| CFG-002 | Settings import | `pytest config/settings/tests/test_settings_secrets.py -v` | 3 passed |
| CFG-002 | Settings import | `python -c "import django; django.setup()"` (dev/test/prod) | Imports cleanly |
| CFG-002 | Attribute check | `settings.DATABASE_URL` / `settings.REDIS_URL` | AttributeError (deleted) |
| CFG-002/004 | Lint+types | `ruff check src/backend/config/settings/` `basedpyright ... base.py` | 0 errors, 0 warnings |
| CFG-003 | API regression | `pytest apps/moderation/tests/test_priority_service.py::TestBulkModerationActionView -v` | All existing assertions pass (updated where doc-specified) |
| CFG-003 | New DTO tests | (new tests added in Block CFG-003) | 400 on extra keys; 400 on type mismatch |
| CFG-003 | Lint+types | `ruff check` `basedpyright` on `schemas.py` + `api_bulk.py` | 0 errors |
| CFG-005 | Shell syntax | `bash -n docker/entrypoint.sh` | Exit 0, no syntax errors |
| CFG-005 | Proc-args | Manual `/proc/<pid>/cmdline` inspection during startup | No credential URL in cmdline |
| CFG-006 | Git tracking | `git ls-files entrypoint*.sh` (root) | Empty output |
| CFG-007 | Doc read-back | Inspect `.env.example` + `docker-deployment.md` | Both reference `src/.env` |
| CFG-007 | File deletion | `Test-Path src/.env` | False |

---

## 4. Execution Phases & Ordering

### Phase A — Parallel (no shared files)
**Can be executed concurrently by separate Implementor agents:**
- CFG-001 (compose files + `.env.docker.example` + docker-deployment.md admin section)
- CFG-003 (new `moderation/schemas.py` + `api_bulk.py`)
- CFG-005 (`docker/entrypoint.sh`)
- CFG-006 (git rm root stubs)
- CFG-002 (start of base.py edits)

> **Note:** CFG-002 and CFG-004 both edit `base.py` — only one should hold the file at a time.
> CFG-002 starts first; CFG-004 cannot begin until CFG-002 is complete (staged or committed).

### Phase B — Sequential (same file: `base.py`)
1. **CFG-002** — delete dead `DATABASE_URL`/`REDIS_URL` assignments; simplify the `if` guard.
2. **verify-002** — settings_secrets tests + import smoke + lint/typecheck.
3. **CFG-004** — standardize `os.getenv` -> `env()`/`env.bool`/`env.list`; keep `os.getenv` for
   control-flow guards only.
4. **verify-004** — settings_secrets tests + lint + typecheck.

### Phase C — Doc alignment (after CFG-001)
- **CFG-007** — update `.env.example` header comment, `docker-deployment.md` Database Configuration
  section, delete `src/.env`. Runs after CFG-001 completes to preserve `docker-deployment.md`
  edit context.

---

## 5. Rollout Constraints

| Constraint | Applies to | Detail |
|---|---|---|
| Docker-only tests | CFG-002, CFG-003, CFG-004 | `make test` gate runs in Docker Compose `mko-bazuna-test` project (port 5433); never `uv run pytest` locally. |
| Settings import-time isolation | CFG-002, CFG-004 | `test_settings_secrets.py` uses `subprocess.run` to verify import-time guards. Changes must not break import under dev/test/prod modules. |
| Pydantic v2 available | CFG-003 | `pydantic>=2.13.4` declared in `pyproject.toml`; no new dependency needed. |
| No DB migration needed | All | No schema changes; CFG-003 is in-memory DTO validation only. |
| Compose `${VAR:?msg}` syntax | CFG-001 | Already used by `POSTGRES_*`/`DJANGO_SECRET_KEY` in the same compose files — `ADMIN_PASSWORD` simply joins the existing fail-fast pattern. |
| `base.py` env guards | CFG-002, CFG-004 | `os.getenv` retained for `DJANGO_BUILD`/`DJANGO_SETTINGS_MODULE`/`DJANGO_SECRET_KEY` control-flow guards and `prod.py` fail-fast checks. |
| i18n DoD | CFG-007 (docs) | Only doc text changes; no new user-visible strings in Python/templates. `test_i18n_completeness.py` unaffected. |

---

## 6. Post-Rollout Validation

After all 7 blocks complete:

1. **Fast test gate:** `make test` (skips `seed` suite; runs settings tests + moderation tests + full
   unit/integration suite excluding nightly seed).
2. **Lint gate:** `uv run ruff check src/` (entire backend).
3. **Typecheck gate:** `uv run basedpyright src/backend/config/settings/
   src/backend/apps/moderation/`.
4. **Compose deploy check:** `docker compose --env-file .env.docker.example -f docker-compose.yml
   config` (should fail-fast on `ADMIN_PASSWORD` -> confirms CFG-001).
5. **Git cleanliness:** `git status --short` — 4 root entrypoint deletions staged, `base.py` +
   `api_bulk.py` + `schemas.py` modified, `.env.docker.example` + `.env.example` +
   `docs/ops/docker-deployment.md` updated, `src/.env` deleted.

---

*End of plan.*
