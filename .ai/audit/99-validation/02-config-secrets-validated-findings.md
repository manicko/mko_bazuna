# Phase 02 Audit Findings — Configuration & Secrets Management (Validated)

**Executor:** audit-executor → validated by validator
**Source:** `.ai/audit/02-config-secrets/findings.md`
**Status:** complete
**Validated:** yes

> problems-only mode: passing checks and healthy rows omitted. All findings below are backed by runtime evidence.

---

## Findings

### CFG-001: Orphaned `src/backend/.env` contains SQLite URL and duplicate keys

| Field | Value |
|-------|-------|
| **ID** | CFG-001 |
| **Severity** | MEDIUM |
| **Type** | ~~RUNTIME-ERROR~~ [DOC-UPDATE] |
| **Affected Modules** | `src/backend/.env` (orphan), `src/backend/config/settings/base.py` |
| **Classification** | advisory |

> **Validation Note:**
> - **Action:** reclassified
> - **Detail:** The finding is technically correct — the orphaned file exists with SQLite and duplicate keys. However, the file is git-ignored (`.gitignore` line 151: `.env`) and not tracked in version control. The recommendation to delete the file is valid, but this is better classified as a documentation/operational issue rather than a runtime error since the settings layer correctly reads from the repo root `.env`. The code behavior is correct; the issue is an unused local file that could mislead operators.

**Description:** A file `src/backend/.env` exists on disk (not git-tracked; covered by `.gitignore` `.env` pattern) but is **never read** by the settings layer. `base.py:16` computes `BASE_DIR` as the repo root and reads `.env` from there, never from `src/backend/`. The orphan file contains `DATABASE_URL=sqlite:///db.sqlite3`, which directly violates the documented zone C5 "PostgreSQL ONLY (no SQLite fallback)" rule, and declares `DJANGO_SECRET_KEY` twice (lines 1 and 6) with different values. Any operator who points an application at this file would silently get SQLite instead of PostgreSQL and ambiguous secret key resolution.

**Evidence:**
- `base.py:16` `BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent` → repo root.
- `base.py:26-33` reads `BASE_DIR / ".env"` only; no reference to `src/backend/.env` anywhere (Grep for `backend/.env` → 0 matches).
- `src/backend/.env:4` `DATABASE_URL=sqlite:///db.sqlite3`; `src/backend/.env:1,6` duplicate `DJANGO_SECRET_KEY`.
- Architecture doc `docs/01-spec/architecture-structure.md:110` states PostgreSQL only, no SQLite fallback.
- `git check-ignore -v src/backend/.env` confirms it is ignored, so not a VCS-leak.

**Recommendation:** Delete `src/backend/.env` from the working tree. Document that `.env` must be placed at the repository root for the settings layer to find it. Effort: trivial. Priority: recommended.

---

### CFG-002: `POSTGRES_PASSWORD` falls back to empty string (silent default for a credential)

| Field | Value |
|-------|-------|
| **ID** | CFG-002 |
| **Severity** | MEDIUM |
| **Type** | SPEC-DEVIATION |
| **Affected Modules** | `src/backend/config/settings/base.py` |
| **Classification** | mandatory |

> **Validation Note:**
> - **Action:** validated (unchanged)
> - **Detail:** Confirmed: `base.py:126` uses `os.getenv("POSTGRES_PASSWORD", "")` with empty-string default. This violates the fail-fast principle established for `SECRET_KEY` (no default) in `base.py:39`. In production, an empty password would cause unclear authentication errors later.

**Description:** In the discrete-vars DB path, `POSTGRES_PASSWORD` defaults to `""` when unset. Unlike `SECRET_KEY` (which has no default and raises `ImproperlyConfigured`), a missing database password is silently accepted. If `DATABASE_URL` is also unset and the `.env` omits `POSTGRES_PASSWORD`, Django attempts a connection with an empty password and fails later with an opaque auth error rather than an actionable, value-free message at boot.

**Evidence:**
- `base.py:126` `"PASSWORD": os.getenv("POSTGRES_PASSWORD", "")` — empty-string default.
- Contrast with `base.py:39` `SECRET_KEY = env("DJANGO_SECRET_KEY")` (no default → raises).
- Runtime test confirmed: `docker-compose.yml` and `docker-compose.prod.yml` use `POSTGRES_PASSWORD:-postgres` fallbacks, but these do not override the code-level default.

**Recommendation:** Require the credential explicitly: read it through `env("POSTGRES_PASSWORD")` (no default) in the discrete path, or derive the whole `DATABASES` entry from `DATABASE_URL` only and fail clearly when neither source is present. Effort: small. Priority: mandatory.

---

### CFG-003: Bot loads `BOT_TOKEN` via raw `os.getenv` with no validation and a divergent, silent failure mode

| Field | Value |
|-------|-------|
| **ID** | CFG-003 |
| **Severity** | HIGH |
| **Type** | SPEC-DEVIATION |
| **Affected Modules** | `src/telegram_bot/main.py`, `src/backend/config/settings/base.py` |
| **Classification** | mandatory |

> **Validation Note:**
> - **Action:** validated (unchanged)
> - **Detail:** Confirmed: The bot process uses `os.getenv("BOT_TOKEN")` at `main.py:20` and silently returns on absence, exiting with code 0. The web process uses `environ.Env` schema with fail-fast for `SECRET_KEY`. This is a genuine process-divergence risk as the bot could appear healthy while silently not running.

**Description:** The web/migrate/scheduler processes load secrets through the django-environ `environ.Env` schema (typed, validated, fail-fast). The bot process, however, reads its single required secret `BOT_TOKEN` via a bare `os.getenv("BOT_TOKEN")` and on absence merely logs a warning and returns — the process exits cleanly (exit 0) with the bot silently not running. This is a process-divergence risk: the two processes in the same deployment use two different secret-loading mechanisms, and a missing bot token is not an actionable boot failure.

**Evidence:**
- `src/telegram_bot/main.py:20-23`:
  ```python
  token = os.getenv("BOT_TOKEN")
  if not token:
      logger.warning("BOT_TOKEN not set - bot not running")
      return
  ```
  `main()` returns `None`; the process exits 0.
- `base.py:19-22` declares only `DEBUG` in the `environ.Env(...)` schema; `BOT_TOKEN` is never part of the validated schema.
- Docker `bot` service (`docker-compose.yml:59-74`) sets `restart: unless-stopped` — it would keep restarting a dead bot only if it crashed; a clean exit 0 defeats that safety net.

**Recommendation:** Move bot secret loading into the same validated path: declare `BOT_TOKEN` in the environ schema (e.g., `BOT_TOKEN = env("BOT_TOKEN")`) so a missing/invalid token raises `ImproperlyConfigured` at `django.setup()` exactly like `DJANGO_SECRET_KEY`. This unifies both processes on one mechanism and makes a missing token an explicit, actionable boot failure. Effort: small. Priority: mandatory.

---

### CFG-004: `:-placeholder` fallback for `DJANGO_SECRET_KEY` in compose `environment`

| Field | Value |
|-------|-------|
| **ID** | CFG-004 |
| **Severity** | LOW |
| **Type** | BEST-PRACTICE |
| **Affected Modules** | `docker-compose.yml`, `docker-compose.prod.yml` |
| **Classification** | advisory |

> **Validation Note:**
> - **Action:** rejected
> - **Detail:** The `:-placeholder` fallback is present but effectively unreachable in normal operation. Verified: `docker-compose.yml:36` and `docker-compose.prod.yml:35` use the fallback, but both `migrate` service (line 38) and `scheduler` service (line 37) also specify `env_file: .env`, and compose precedence ensures `.env` values override the inline defaults. Without `.env`, compose aborts with "env file not found". The fallback creates a code smell but no real operational risk. Rejection rationale: the finding adds complexity (removing it requires changes) without clear maintenance benefit; the current behavior already fails loudly when `.env` is absent, and the real value is always used when `.env` is present.

~~CFG-004: `:-placeholder` fallback for `DJANGO_SECRET_KEY` in compose `environment`~~ [REJECTED]

> **Rejection reason:** The fallback is unreachable in normal operation — when `.env` exists, its value is used; when it doesn't, compose aborts with an error. The placeholder creates no real risk and removing it adds complexity without meaningful safety benefit. This is speculative complexity.

---

### CFG-005: No automated tests for config/secret loading surface

| Field | Value |
|-------|-------|
| **ID** | CFG-005 |
| **Severity** | MEDIUM |
| **Type** | BEST-PRACTICE |
| **Affected Modules** | `tests/`, `src/backend/config/settings/` |
| **Classification** | advisory |

> **Validation Note:**
> - **Action:** validated (unchanged)
> - **Detail:** Confirmed: Existing test file `src/backend/apps/core/tests/test_sweep_commands.py` covers sweep commands but not secret/loading validation. No test module exists for settings validation. The fail-fast behavior for `SECRET_KEY` is not tested and could silently regress.

**Description:** The mandatory runtime checks (R2 missing-secret rejection, R6) are currently verified only by manual execution, not by the test suite. The fail-fast behavior of the settings layer (R2 proved it raises `ImproperlyConfigured` with a value-free message) can silently regress if a default is added to `SECRET_KEY` or `BOT_TOKEN`.

**Evidence:**
- Test files in `src/backend/apps/core/tests/` and other `tests/` directories cover sweep commands, ads, moderation, etc., but none cover settings/secret loading.
- Manual runtime confirmed the behavior works today, but nothing guards it.

**Recommendation:** Add a small settings-loading test module that asserts (a) importing prod settings without `DJANGO_SECRET_KEY` raises `ImproperlyConfigured` and the message contains no secret value, and (b) `BOT_TOKEN` absence is rejected once CFG-003 is fixed. Effort: small. Priority: advisory.

---

### CFG-006: Weak / real-looking placeholder values in example env files

| Field | Value |
|-------|-------|
| **ID** | CFG-006 |
| **Severity** | LOW |
| **Type** | DOC-UPDATE |
| **Affected Modules** | `.env.dev.example`, `.env.example` |
| **Classification** | advisory |

> **Validation Note:**
> - **Action:** validated (unchanged)
> - **Detail:** Confirmed: `.env.dev.example` uses `POSTGRES_PASSWORD=111` and `DATABASE_URL=postgres://bazuna_user:111@db:5432/bazuna_db` (lines 14, 19). `.env.example` correctly uses angle-bracket placeholders like `<generate-with-django-secret-key-generator>` and `your-password`. The inconsistency could lead to accidental use of weak credentials.

**Description:** The example files are placeholder-only (good — no real credentials), but `.env.dev.example` uses concrete weak values that look like real secrets rather than obvious placeholders: `POSTGRES_PASSWORD=111` (line 19) and `DATABASE_URL=postgres://bazuna_user:111@db:5432/bazuna_db` (line 14). A developer could copy these verbatim into a non-dev environment and ship a trivially guessable DB password.

**Evidence:**
- `.env.dev.example:14` `DATABASE_URL=postgres://bazuna_user:111@db:5432/bazuna_db`
- `.env.dev.example:19` `POSTGRES_PASSWORD=111`
- `.env.example:7,19` uses `<generate-with-django-secret-key-generator>` and `your-password` (clear placeholders)

**Recommendation:** Align `.env.dev.example` with the angle-bracket placeholder style (e.g., `POSTGRES_PASSWORD=<dev-db-password>`) so no example file carries a value that could be mistaken for a usable secret. Effort: trivial. Priority: advisory.

---

## Validation Summary

| Action | Count | Details |
|--------|-------|---------|
| Validated (unchanged) | 4 | CFG-002, CFG-003, CFG-005, CFG-006 |
| Reclassified | 1 | CFG-001: RUNTIME-ERROR → DOC-UPDATE |
| Merged | 0 | — |
| Rejected | 1 | CFG-004 |

### Rejected Findings

| ID | Title | Reason |
|----|-------|--------|
| CFG-004 | `:-placeholder` fallback for `DJANGO_SECRET_KEY` in compose | The fallback is unreachable in normal operation — when `.env` exists, its value is used; when it doesn't, compose aborts. Removing it adds complexity without real safety benefit. |

### Merged Findings

None.

### Reclassified Findings

| ID | Original Type | New Type | Rationale |
|----|---------------|----------|-----------|
| CFG-001 | RUNTIME-ERROR | DOC-UPDATE | The orphaned file is a documentation/operational issue, not a runtime error. The code correctly reads from repo-root `.env`. The risk is operator confusion, not code malfunction. |

---

## Cross-Phase Analysis

Scanned for conflicts with other audit phases — none detected.

## Rollout Safety Assessment

- CFG-002 and CFG-003 are independent fixes; order does not matter.
- Both changes are additive/improvements to validation; no data migration required.
- No circular dependencies or hidden risks identified.