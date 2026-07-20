# Phase 02 Audit Findings — Configuration & Secrets Management

**Executor:** audit-executor
**Template:** .kilo/commands/audit/phases/02-audit-config-secrets.md
**Status:** complete
**Validated:** no

> problems-only mode: passing checks and healthy rows omitted. All findings below are backed by runtime evidence.

---

## Findings

### CFG-001: Orphaned `src/backend/.env` contains SQLite URL and duplicate keys

| Field | Value |
|-------|-------|
| **ID** | CFG-001 |
| **Severity** | MEDIUM |
| **Type** | RUNTIME-ERROR |
| **Affected Modules** | `src/backend/.env` (orphan), `src/backend/config/settings/base.py` |
| **Classification** | advisory |

**Description:** A file `src/backend/.env` exists on disk (not git-tracked; covered by `.gitignore` `.env` pattern) but is **never read** by the settings layer. `base.py:26` computes `BASE_DIR` as the repo root and reads `.env` from there, never from `src/backend/`. The orphan file contains `DATABASE_URL=sqlite:///db.sqlite3`, which directly violates the documented zone C5 "PostgreSQL ONLY (no SQLite fallback)" rule, and declares `DJANGO_SECRET_KEY` twice (lines 1 and 6) with different values. Any operator who points an application at this file would silently get SQLite instead of PostgreSQL and ambiguous secret key resolution.

**Evidence:**
- `base.py:16` `BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent` → repo root.
- `base.py:26-33` reads `BASE_DIR / ".env"` only; no reference to `src/backend/.env` anywhere (Grep for `backend/.env` → 0 matches).
- `src/backend/.env:4` `DATABASE_URL=sqlite:///db.sqlite3`; `src/backend/.env:1,6` duplicate `DJANGO_SECRET_KEY`.
- Architecture doc `docs/01-spec/architecture-structure.md:110` (db-schema) and base.py:110 comment both state PostgreSQL only, no SQLite fallback.
- `git check-ignore -v src/backend/.env` → ignored (so not a VCS-leak), but the file persists on disk.

**Recommendation:** Delete `src/backend/.env` from the working tree (it is unused, git-ignored, and misleading). If a local dev env is needed under `src/backend/`, document the exact path the settings layer expects (repo-root `.env`) instead of maintaining a divergent copy. Effort: trivial. Priority: recommended.

---

### CFG-002: `POSTGRES_PASSWORD` falls back to empty string (silent default for a credential)

| Field | Value |
|-------|-------|
| **ID** | CFG-002 |
| **Severity** | MEDIUM |
| **Type** | BEST-PRACTICE |
| **Affected Modules** | `src/backend/config/settings/base.py` |
| **Classification** | mandatory |

**Description:** In the discrete-vars DB path, `POSTGRES_PASSWORD` defaults to `""` when unset. Unlike `SECRET_KEY` (which has no default and raises `ImproperlyConfigured`), a missing database password is silently accepted. If `DATABASE_URL` is also unset and the `.env` omits `POSTGRES_PASSWORD`, Django attempts a connection with an empty password and fails later with an opaque auth error rather than an actionable, value-free message at boot.

**Evidence:**
- `base.py:126` `"PASSWORD": os.getenv("POSTGRES_PASSWORD", "")` — empty-string default.
- Contrast with `base.py:39` `SECRET_KEY = env("DJANGO_SECRET_KEY")` (no default → raises).
- Runtime R2: missing `DJANGO_SECRET_KEY` → `ImproperlyConfigured: Set the DJANGO_SECRET_KEY environment variable` (value-free, good). No equivalent guard exists for the DB password.

**Recommendation:** Require the credential explicitly: read it through `env("POSTGRES_PASSWORD")` (no default) in the discrete path, or derive the whole `DATABASES` entry from `DATABASE_URL` only and fail clearly when neither source is present. Effort: small. Priority: recommended.

---

### CFG-003: Bot loads `BOT_TOKEN` via raw `os.getenv` with no validation and a divergent, silent failure mode

| Field | Value |
|-------|-------|
| **ID** | CFG-003 |
| **Severity** | HIGH |
| **Type** | SPEC-DEVIATION |
| **Affected Modules** | `src/telegram_bot/main.py`, `src/backend/config/settings/base.py` |
| **Classification** | mandatory |

**Description:** The web/migrate/scheduler processes load secrets through the django-environ `environ.Env` schema (typed, validated, fail-fast). The bot process, however, reads its single required secret `BOT_TOKEN` via a bare `os.getenv("BOT_TOKEN")` and on absence merely logs a warning and returns — the process exits cleanly (exit 0) with the bot silently not running. This is a process-divergence risk: the two processes in the same deployment use two different secret-loading mechanisms, and a missing bot token is not an actionable boot failure. A deployment can report "healthy" while the bot is dead.

**Evidence:**
- `src/telegram_bot/main.py:20-23`:
  ```python
  token = os.getenv("BOT_TOKEN")
  if not token:
      logger.warning("BOT_TOKEN not set - bot not running")
      return
  ```
  `main()` returns `None`; `if __name__ == "__main__": main()` → process exits 0.
- `base.py:19-22` declares only `DEBUG` in the `environ.Env(...)` schema; `BOT_TOKEN` is never part of the validated schema.
- Per the phase taxonomy, "Secret validation absent (silent defaults)" maps to HIGH; the bot lacks validation and fails silently.
- Docker `bot` service (`docker-compose.yml:59-74`) sets `restart: unless-stopped` — it would keep restarting a dead bot only if it crashed; a clean exit 0 defeats that safety net.

**Recommendation:** Move bot secret loading into the same validated path: declare `BOT_TOKEN` in the environ schema (e.g., `BOT_TOKEN = env("BOT_TOKEN")`) so a missing/invalid token raises `ImproperlyConfigured` at `django.setup()` exactly like `DJANGO_SECRET_KEY`. This unifies both processes on one mechanism and makes a missing token an explicit, actionable boot failure. Effort: small. Priority: recommended.

---

### CFG-004: `:-placeholder` fallback for `DJANGO_SECRET_KEY` in compose `environment`

| Field | Value |
|-------|-------|
| **ID** | CFG-004 |
| **Severity** | LOW |
| **Type** | BEST-PRACTICE |
| **Affected Modules** | `docker-compose.yml`, `docker-compose.prod.yml` |
| **Classification** | advisory |

**Description:** The `migrate`, `web`, `scheduler` services set `DJANGO_SECRET_KEY=${DJANGO_SECRET_KEY:-placeholder}`. In the normal flow the root `.env` is present and compose interpolates the real key (verified: `docker compose config` rendered `REAL_KEY_FROM_ENV_FILE` when `.env` held it), so the placeholder is effectively unreachable. It remains a weak-looking default that would only surface if `.env` is absent — at which point compose itself errors (`env file ... not found`) and base.py also fails. Low real risk, but the literal string `placeholder` as a signing-key fallback is a code smell worth removing.

**Evidence:**
- `docker-compose.yml:36` and `docker-compose.prod.yml:35`: `- DJANGO_SECRET_KEY=${DJANGO_SECRET_KEY:-placeholder}`.
- Runtime: created temp root `.env` with `DJANGO_SECRET_KEY=REAL_KEY_FROM_ENV_FILE`; `docker compose config` → `DJANGO_SECRET_KEY: REAL_KEY_FROM_ENV_FILE` (real value wins). Without `.env`, `docker compose config` aborts: `env file C:\py_dev\mko_bazuna\.env not found`.
- `environment` overrides `env_file` per compose precedence, so the `.env` value is in fact honored via interpolation, not shadowed.

**Recommendation:** Drop the `:-placeholder` fallback and reference the key directly (`DJANGO_SECRET_KEY=${DJANGO_SECRET_KEY}`) or rely solely on `env_file: .env`; let boot fail loudly when the key is missing. Effort: trivial. Priority: recommended.

---

### CFG-005: No automated tests for config/secret loading surface

| Field | Value |
|-------|-------|
| **ID** | CFG-005 |
| **Severity** | MEDIUM |
| **Type** | BEST-PRACTICE |
| **Affected Modules** | `tests/`, `src/backend/config/settings/` |
| **Classification** | advisory |

**Description:** The mandatory runtime checks (R2 missing-secret rejection, R6) are currently verified only by manual execution, not by the test suite. `pytest -k "secret|env|token|settings"` collected no relevant tests; only unrelated sweep-command tests matched. The fail-fast behavior of the settings layer (R2 proved it raises `ImproperlyConfigured` with a value-free message) can silently regress if a default is added to `SECRET_KEY` or `BOT_TOKEN`.

**Evidence:**
- R6: `uv run pytest -k "secret or env or token or settings" --co` → only `test_sweep_commands.py` (unrelated).
- R2 (manual) confirmed rejection works today, but nothing guards it.

**Recommendation:** Add a small settings-loading test module that asserts (a) importing prod settings without `DJANGO_SECRET_KEY` raises `ImproperlyConfigured` and the message contains no secret value, and (b) `BOT_TOKEN` absence is rejected once CFG-003 is fixed. Effort: small. Priority: recommended.

---

### CFG-006: Weak / real-looking placeholder values in example env files

| Field | Value |
|-------|-------|
| **ID** | CFG-006 |
| **Severity** | LOW |
| **Type** | DOC-UPDATE |
| **Affected Modules** | `.env.dev.example`, `.env.example` |
| **Classification** | advisory |

**Description:** The example files are placeholder-only (good — no real credentials), but `.env.dev.example` uses concrete weak values that look like real secrets rather than obvious placeholders: `POSTGRES_PASSWORD=111` (line 19) and `DATABASE_URL=postgres://bazuna_user:111@db:5432/bazuna_db` (line 14). A developer could copy these verbatim into a non-dev environment and ship a trivially guessable DB password. Consistency with `.env.example` (which uses `<...>` angle-bracket placeholders) is preferable.

**Evidence:**
- `.env.dev.example:14` `DATABASE_URL=postgres://bazuna_user:111@db:5432/bazuna_db`
- `.env.dev.example:19` `POSTGRES_PASSWORD=111`
- `.env.example:7,22,26` use `<generate-with-django-secret-key-generator>`, `<your-bot-username>`, `<your-bot-token-from-botfather>` (clear placeholders).

**Recommendation:** Align `.env.dev.example` with the angle-bracket placeholder style (e.g., `POSTGRES_PASSWORD=<dev-db-password>`) so no example file carries a value that could be mistaken for a usable secret. Effort: trivial. Priority: recommended.

---

## Summary

| Severity | Count |
|----------|-------|
| CRITICAL | 0 |
| HIGH | 1 |
| MEDIUM | 3 |
| LOW | 2 |

## Mandatory Fixes

- CFG-002 — Require `POSTGRES_PASSWORD` explicitly; remove empty-string default.
- CFG-003 — Load `BOT_TOKEN` through the validated environ schema (unify with web process; fail fast).

## Advisory Recommendations

- CFG-001 — Remove orphaned `src/backend/.env` (SQLite URL + duplicate keys).
- CFG-004 — Drop `:-placeholder` signing-key fallback in compose.
- CFG-005 — Add tests for settings/secret loading (missing-secret rejection).
- CFG-006 — Use obvious placeholders in `.env.dev.example`.

## Doc Updates Needed

- CFG-006 — `.env.dev.example` should follow the placeholder convention of `.env.example`.
