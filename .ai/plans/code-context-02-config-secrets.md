# code_context — Phase 02 Config & Secrets (CFG-001 through CFG-007)

**Status:** Audit findings validated; line drift noted in audit (file unchanged since audit).
**Scope:** Current working tree at `C:\py_dev\mko_bazuna`.

## Dependencies & Environment

- **Python 3.14**, **Django 5.2 LTS**, **aiogram 3.x**, **PostgreSQL 18**
- `pydantic>=2.13.4` declared (see `pyproject.toml`) — available for CFG-003 DTO
- `django-environ>=0.11.0` declared — the `env()` typed loader
- Test gate: `make test` (Docker Compose `mko-bazuna-test` project, port 5433); tests bind-mount `.:/app` so no image rebuild needed
- Settings import-time validation tested via subprocess (`test_settings_secrets.py` pattern)
- `.gitignore` covers `.env`, `.env.dev`, `.env.local`, `.env.docker` (lines 145-148); `.dockerignore` excludes `.env*`. Only 3 `*.example` templates are tracked.

## Finding — Current State & Line Drift

### CFG-001 (HIGH / mandatory) — Weak default admin credential
- **Current state:** NOT fixed — still vulnerable.
- `docker-compose.yml:126` → `- ADMIN_PASSWORD=${ADMIN_PASSWORD:-admin}` (audit cited :99 — **line drift**; the create_admin block moved down as services were added)
- `docker-compose.dev.override.yml:15` → `- ADMIN_PASSWORD=${ADMIN_PASSWORD:-admin}` (matches audit)
- `docker/entrypoint-create-admin.sh:18` → `if [ -z "${ADMIN_PASSWORD}" ]; then` — skip-guard bypassed by the `:-admin` default (matches audit)
- `src/backend/apps/core/management/commands/create_admin_user.py:107-116` → creates `is_staff=True, is_superuser=True` (matches audit)
- `src/backend/config/urls.py:12` → `path("admin/", admin.site.urls)` (matches audit)
- `.env.docker.example:61` → `ADMIN_PASSWORD=` (empty, matches documented "skip" intent)
- `.env.example:65` → `ADMIN_PASSWORD=  # Set in production via secret management` (empty)
- `.env.dev.example:57` → `ADMIN_PASSWORD=` (empty)
- **Fix:** Change `${ADMIN_PASSWORD:-admin}` → `${ADMIN_PASSWORD:?ADMIN_PASSWORD must be set}` in both compose files.

### CFG-002 (MEDIUM advisory) — Dead module-level settings
- `base.py:176` → `DATABASE_URL = os.getenv("DATABASE_URL")` (audit cited :169 — **line drift**)
- `base.py:179` → `DATABASES = {"default": env.db()}` (real consumer; `env.db()` reads `os.environ["DATABASE_URL"]` directly, NOT `settings.DATABASE_URL`)
- `base.py:272` → `"LOCATION": env("REDIS_URL", default="redis://localhost:6379/0")` (audit cited :260 — **line drift**)
- `base.py:279` → `REDIS_URL = env("REDIS_URL", default="redis://localhost:6379/0")` (dead duplicate; audit cited :268 — **line drift**)
- Zero consumers of `settings.DATABASE_URL` / `settings.REDIS_URL` in `src/` (grep-confirmed).
- **Fix:** Delete lines 176 and 279; `DATABASES`/`CACHES` already reference `env(...)` directly.

### CFG-003 (MEDIUM advisory) — Bulk moderation API manual JSON parsing
- `src/backend/apps/moderation/views/api_bulk.py:42` → `data = json.loads(request.body)`
- `:46-48` → `data.get("action", "")`, `data.get("selected_items", [])`, `data.get("reason", "")`
- No Pydantic import / `BaseModel` / `ConfigDict` in the file.
- `action` is enum-validated (`BulkModerationAction(action)` at :62), but body has no schema contract; `selected_items` not type-checked; extra keys silently ignored.
- **Correct pattern reference:** `src/telegram_bot/schemas/message_payloads.py` — `TitlePayload`, `DescriptionPayload`, `PricePayload`, `PhotoCountPayload` as `pydantic.BaseModel` with `Annotated`/`Field`.
- **No `apps/moderation/schemas.py` exists** — DTO would be a new file in the moderation app.
- `BulkModerationAction` enum in `src/backend/apps/core/enums.py:155` — `APPROVE`, `REJECT`, `FLAG`.
- **Blast radius:** No in-repo frontend/template caller of `/moderation/api/v1/bulk-action/` (grep-confirmed — only the view, route, and tests reference it). Safe to add `extra="forbid"` DTO.
- **Tests:** `src/backend/apps/moderation/tests/test_priority_service.py:466-754` — `TestBulkModerationActionView` (9 tests; uses `Client` + `force_login(staff_user)` + `json.dumps` body + `content_type="application/json"`).
- **Fix:** Create `apps/moderation/schemas.py` with `BulkModerationRequest(BaseModel)` (`extra="forbid"`, `action: BulkModerationAction`, `selected_items: list[int]`, `reason: str = ""`); validate in the view before dispatch.

### CFG-004 (LOW advisory) — Inconsistent settings loaders
- `base.py` mixes `env()` (typed) and `os.getenv()` (untyped str).
- `env()`: lines 52 (`SECRET_KEY`), 55 (`DEBUG`), 59 (`BOT_TOKEN`), 189 (`POSTGRES_PASSWORD`), 272 (`REDIS_URL` in CACHES)
- `os.getenv()`: line 64 (`GOOGLE_TRANSLATE_API_KEY`), 68 (`ALLOWED_HOSTS`), 176 (`DATABASE_URL`), 187-191 (`POSTGRES_DB/USER/HOST/PORT`), 241 (`BOT_USERNAME`), 251 (`SITE_URL`), 255 (`IMMEDIATE_ALERTS_ENABLED`), 263 (`PLAUSIBLE_HOST`), 246 (`BOT_LIVENESS_FILE`)
- `base.py:255-259` → manual bool parsing: `os.getenv("IMMEDIATE_ALERTS_ENABLED", "false").lower() in ("1", "true", "yes")` instead of `env.bool(...)`.
- `base.py:67-69` → `ALLOWED_HOSTS` parsed via `os.getenv(...).split(",")` instead of `env.list(...)`.
- **Fix:** Replace `os.getenv` calls with `env()`/`env.bool`/`env.list` where the value is read as a setting. Keep `os.getenv` only for control-flow guards (e.g., `DJANGO_BUILD`, `DJANGO_SETTINGS_MODULE` checks at lines 35-40) and `prod.py`'s `os.getenv("SITE_URL")` guard.

### CFG-005 (LOW advisory) — Credentials in process args
- `docker/entrypoint.sh:41` → `/opt/venv/bin/python -c "import psycopg; psycopg.connect('$DATABASE_URL')"` (shell interpolation → credential in args)
- `docker/entrypoint.sh:60` → `/opt/venv/bin/python -c "import redis; redis.from_url('$REDIS_URL').ping()"` (same issue)
- Both inside retry loops (~30s/15 iterations).
- **Fix:** Use `python -c "import os, psycopg; psycopg.connect(os.environ['DATABASE_URL'])"` and equivalent for Redis.

### CFG-006 (LOW advisory) — Stale 0-byte root entrypoint stubs
- Root `entrypoint.sh`, `entrypoint-catalog.sh`, `entrypoint-seed.sh`, `entrypoint-test.sh` — all 0 bytes, all git-tracked.
- Real implementations live in `docker/entrypoint*.sh`.
- **Fix:** `git rm` the 4 root stubs.

### CFG-007 (LOW / doc) — `.env` source-location discrepancy
- `base.py:16` → `BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent` = `<repo>/src`
- `base.py:28` → `env_path = BASE_DIR / ".env"` = `<repo>/src/.env`
- `base.py:46` → `environ.Env.read_env(env_path)` loads `src/.env`
- But `.env.example:2` says "Copy this file to .env (at the repository root...)" — misleading.
- `docs/ops/docker-deployment.md:193-194` describes local dev using repo-root `.env` "auto-loaded by Compose" — misleading.
- `docker-compose.yml:51,78,105,131,159,186,213` → `.env.docker:/app/src/.env:ro` (7 bind-mounts, all target `src/.env` — already correct).
- `src/.env` exists as a 0-byte gitignored stray file (masks the issue).
- Works locally only because `uv run` implicitly injects the repo-root `.env` into `os.environ`.
- **Fix:** Update `.env.example:2` to point to `src/.env`; update `docs/ops/docker-deployment.md:193-194`; delete stray `src/.env`. No code or compose changes needed.

## Key Constraints for Implementation
- No frontend/template caller of the bulk-action API — CFG-003 is safe to add `extra="forbid"`.
- Settings import-time tests use subprocess isolation (`test_settings_secrets.py`) — CFG-002/004 must not break import-time secret validation.
- Docker bind-mounts already target `/app/src/.env` — CFG-007 needs no compose changes.
- Test DB runs in Docker (`mko-bazuna-test`, port 5433); tests run via `make test`.
- `make format`/`make lint`/`make typecheck` are available gates (`ruff`, `basedpyright`).
