# Phase 02 Audit Findings — Configuration & Secrets Management

**Executor:** audit-executor
**Template:** `.kilo/commands/audit/phases/02-audit-config-secrets.md`
**Status:** complete
**Validated:** no (runtime verified; full prod deploy not available)

Audit scope: dual-process Django (web gunicorn + aiogram bot) sharing one PostgreSQL
18 DB. Settings in `src/backend/config/settings/{base,dev,prod,test}.py`; secrets
injected from a single env source (`.env.docker`) consumed by both processes.

## Mandatory Runtime Verification

| ID | Verification | Result | Evidence |
|---|---|---|---|
| R1 | Import settings per env | PASS | `uv run python` imports dev/test/prod cleanly; prod has DEBUG=False, SECURE_SSL_REDIRECT=True, SESSION_COOKIE_SECURE=True, HSTS=31536000, HSTS_PRELOAD=True; no DB access at import (`<0.01s`). |
| R2 | Valid/invalid secret behavior | PASS | `test_settings_secrets.py` (3 passed). Removing `DJANGO_SECRET_KEY` → `ImproperlyConfigured`. Empty `BOT_TOKEN` under prod → `ImproperlyConfigured` ("BOT_TOKEN must be set in production..."). Error messages contain **no secret value**. |
| R3 | Hardcoded-secret scan | PASS (clean) | `git log -p -S` + code scan: no real secret committed. All `.env*` files hold **placeholders** (`<generate-with-django-secret-key-generator>`, `your-password`). `scripts/seed-images-config.json` holds real Unsplash/Pexels keys but is **gitignored (.gitignore:225) and never tracked** (confirmed via `git ls-files` + history scan). Only test fixtures exist (`test-secret-key-for-testing-only`, `postgres`) — fake/test-only. |
| R4 | Ignore-file coverage | PASS | `.gitignore` ignores `.env`, `.env.dev`, `.env.local`, `.env.docker`; `.dockerignore` excludes `.env*`. Tracked env files = only the 3 `*.example` templates, all placeholder-only. |
| R5 | Linter + type-check | PASS | `uv run ruff check src/backend/config/settings/` → "All checks passed!"; `uv run basedpyright ...` on base/prod/dev → 0 errors, 0 warnings. |
| R6 | Test-suite (config/secret loading) | PASS | `pytest config/settings/tests/test_settings_secrets.py -v` → 3 passed (8.04s). |

## Findings

### CFG-001: Weak default admin credential (`admin`) embedded in compose, defeats fail-safe guard

| Field | Value |
|-------|-------|
| **ID** | CFG-001 |
| **Severity** | HIGH |
| **Type** | SPEC-DEVIATION |
| **Affected Modules** | `docker-compose.yml:99`, `docker-compose.dev.override.yml:15`, `docker/entrypoint-create-admin.sh:18`, `src/backend/apps/core/management/commands/create_admin_user.py:107-116`, `src/backend/config/urls.py:12` |
| **Classification** | mandatory |

**Description:** `docker-compose.yml` (create_admin service) and the dev
override set `ADMIN_PASSWORD=${ADMIN_PASSWORD:-admin}`. The `:-admin` default
activates whenever `ADMIN_PASSWORD` is unset/empty — which is exactly the
documented default (`ADMIN_PASSWORD=` in `.env.docker.example` and the local
`.env.docker`). This **silently defeats** the fail-safe guard in
`entrypoint-create-admin.sh` (`if [ -z "${ADMIN_PASSWORD}" ]; then exit 0`),
which is intended to **skip** admin creation when no password is supplied.

Because the compose substitution yields `admin` (non-empty) before the entrypoint
runs, the skip-guard is bypassed and `create_admin_user` creates a **superuser**
(`is_staff=True, is_superuser=True`, `create_admin_user.py:112-113`) with the
trivially-guessable credentials `admin` / `admin`. The Django admin panel is
**exposed** at `/admin/` (`urls.py:12`).

Every other secret in `docker-compose.yml` uses the fail-fast `${VAR:?…}` form
(`POSTGRES_PASSWORD`, `DJANGO_SECRET_KEY`); `ADMIN_PASSWORD` is the sole exception,
defaulting to a real credential instead of failing.

**Evidence (runtime):**
```
$ docker compose --project-name cfg-audit -f docker-compose.yml -f docker-compose.dev.override.yml --env-file .env.docker config | grep ADMIN_PASSWORD
  ADMIN_PASSWORD: ""        # web/bot: empty from env_file
  ADMIN_PASSWORD: admin     # create_admin service: :-admin default fires (empty→"admin")
```
```
.docker/docker-compose.yml:99:      - ADMIN_PASSWORD=${ADMIN_PASSWORD:-admin}
.docker/docker-compose.dev.override.yml:15:      - ADMIN_PASSWORD=${ADMIN_PASSWORD:-admin}
/docker/entrypoint-create-admin.sh:18:if [ -z "${ADMIN_PASSWORD}" ]; then  # never true once :-admin applies
/docker/entrypoint-create-admin.sh:24:    --password "${ADMIN_PASSWORD}"
```
`.env.docker.example:53: ADMIN_PASSWORD=` (empty, per documented default)

**Consequence:** A deploy that copies the example env file (or forgets to set
`ADMIN_PASSWORD`) boots a superuser authenticated with `admin`/`admin` on the
internet-facing `/admin/` panel → full database read/write compromise.

**Recommendation:** Remove the `:-admin` default from both compose files; align
with the documented and entrypoint-intended behavior: **fail fast when
`ADMIN_PASSWORD` is empty**. If local dev convenience is desired, default to
empty and let the entrypoint skip creation (do **not** default the credential
itself). Effort: trivial. Priority: mandatory.

---

### CFG-002: Dead config — module-level `DATABASE_URL` and `REDIS_URL` settings never consumed

| Field | Value |
|-------|-------|
| **ID** | CFG-002 |
| **Severity** | MEDIUM |
| **Type** | SPEC-DEVIATION |
| **Affected Modules** | `src/backend/config/settings/base.py:169` (`DATABASE_URL`), `base.py:268` (`REDIS_URL`), `base.py:172` (`env.db()`), `base.py:260` (`CACHES["LOCATION"]`) |
| **Classification** | advisory |

**Description:** `base.py` assigns two module-level Django settings that are
**never read by any code**:
- `DATABASE_URL = os.getenv("DATABASE_URL")` (base.py:169)
- `REDIS_URL = env("REDIS_URL", default="redis://localhost:6379/0")` (base.py:268)

The actual consumers bypass these settings and read the env var directly:
`env.db()` (base.py:172) re-reads `os.environ["DATABASE_URL"]`, and
`CACHES["default"]["LOCATION"]` (base.py:260) calls `env("REDIS_URL")` directly.
A grep for `settings.DATABASE_URL` / `settings.REDIS_URL` across `src/` returns
**zero consumers**.

**Evidence:**
```
$ grep -rn "settings.DATABASE_URL\|settings.REDIS_URL" src/   # (no matches)
src/backend/config/settings/base.py:169: DATABASE_URL = os.getenv("DATABASE_URL")
src/backend/config/settings/base.py:260:     "LOCATION": env("REDIS_URL", default="redis://localhost:6379/0"),
src/backend/config/settings/base.py:268: REDIS_URL = env("REDIS_URL", default="redis://localhost:6379/0")
```
The env var `REDIS_URL` / `DATABASE_URL` is consumed; only the redundant
*setting* duplicates are dead.

**Consequence:** Redundant definitions that can silently drift from the real
`DATABASES`/`CACHES` config (e.g., changing the default on line 268 but not 260
would mislead readers into thinking `settings.REDIS_URL` controls the cache).

**Recommendation:** Delete the dead assignments and have `DATABASES`/`CACHES`
reference the canonical `env(...)` value once. Effort: trivial. Priority: advisory.

---

### CFG-003: Boundary DTO gap — moderation bulk API parses JSON by hand, silently ignores unknown keys

| Field | Value |
|-------|-------|
| **ID** | CFG-003 |
| **Severity** | MEDIUM |
| **Type** | BEST-PRACTICE |
| **Affected Modules** | `src/backend/apps/moderation/views/api_bulk.py:37-44`, `src/telegram_bot/schemas/message_payloads.py` (correct pattern) |
| **Classification** | advisory |

**Description:** The bulk-moderation JSON API (`POST /moderation/bulk-action/`)
parses its request body with plain `json.loads` + `dict.get`:
```python
data = json.loads(request.body)          # line 38
action = data.get("action", "")          # line 42
ad_ids: list[int] = data.get("selected_items", [])   # line 43
reason: str = data.get("reason", "")     # line 44
```
There is **no Pydantic v2 DTO**. Per project rule #11 ("DTO/validation layer at
system boundaries"), every external input must pass through a Pydantic schema
before persistence. The bot side already does this correctly
(`telegram_bot/schemas/message_payloads.py`: `TitlePayload`, `PricePayload`, …).

Consequences: unknown/extra JSON keys are **silently ignored** (no
`extra="forbid"`); `selected_items` is **not type-validated** as `list[int]`
(a string, dict, or nested object is accepted and only fails late inside the
`try` per-item); `reason` is unvalidated TEXT written to
`ModeratorActionLog.reason` and logged (`logger.error(...)` at line 66).

**Evidence:**
```
src/backend/moderation/views/api_bulk.py:42:    action = data.get("action", "")
src/backend/moderation/views/api_bulk.py:43:    ad_ids: list[int] = data.get("selected_items", [])
src/backend/moderation/views/api_bulk.py:44:    reason: str = data.get("reason", "")
```
No `model_config`/`BaseModel`/Pydantic import in `api_bulk.py`. The action field
*is* enum-validated (`BulkModerationAction(action)`) and unknown actions return
400 — but the request as a whole is not schema-validated.

**Consequence:** No schema contract at the boundary; a typo'd/renamed client
field silently no-ops instead of failing fast; types/strings not enforced.
Exploit severity is bounded (admin-only, `staff_required_api`, per-item `except`
containment), but the validation gap is a real deviation from rule #11.

**Recommendation:** Introduce a Pydantic v2 DTO (e.g. `BulkModerationRequest`
with `model_config = ConfigDict(extra="forbid")`) and validate `request.body`
through it before any DB write. Effort: small. Priority: advisory.

---

### CFG-004: Inconsistent settings loaders (`os.getenv` vs `env()`) and manual bool parsing

| Field | Value |
|-------|-------|
| **Severity** | LOW |
| **Type** | BEST-PRACTICE |
| **Affected Modules** | `src/backend/config/settings/base.py:52,55,59,62-64,169,180-184,234,239,243,251,260,268` |
| **Classification** | advisory |

**Description:** `base.py` mixes two setting loaders: `django-environ`'s typed
`env()` (with casting) and untyped `os.getenv()`:
- `env(...)` (typed): `SECRET_KEY`, `DEBUG`, `BOT_TOKEN`, `POSTGRES_PASSWORD`, `REDIS_URL`
- `os.getenv(...)` (untyped `str`): `ALLOWED_HOSTS`, `DATABASE_URL`, `POSTGRES_DB/USER/HOST/PORT`,
  `BOT_USERNAME`, `SITE_URL`, `PLAUSIBLE_HOST`, `IMMEDIATE_ALERTS_ENABLED`

`IMMEDIATE_ALERTS_ENABLED` (base.py:243) reinvents boolean parsing by hand:
```python
IMMEDIATE_ALERTS_ENABLED = os.getenv("IMMEDIATE_ALERTS_ENABLED", "false").lower() in (
    "1", "true", "yes",
)
```
instead of `env.bool("IMMEDIATE_ALERTS_ENABLED", default=False)`. Because the
loaders are inconsistent, a value like `DEBUG=True` (string) vs `DEBUG=true` is
handled correctly only because `DEBUG` uses `env()` casting; the same
robustness is absent for the `os.getenv` group.

**Evidence:** `base.py:52` `SECRET_KEY = env("DJANGO_SECRET_KEY")`; `base.py:243`
`IMMEDIATE_ALERTS_ENABLED = os.getenv(...).lower() in (...)`. Ruff/basedpyright
pass despite the inconsistency (no static guard against it).

**Consequence:** Maintenance risk: a future contributor may use `os.getenv`
(returns `str`) where a `bool`/`list` is expected; casting rules diverge across
settings with no single source of truth.

**Recommendation:** Standardize on `env()` with explicit casts
(`env.bool`, `env.list`, `env.str`) throughout `base.py`. Effort: small. Priority:
advisory.

---

### CFG-005: Credential-bearing DB/Redis URLs exposed in container process args at boot

| Field | Value |
|-------|-------|
| **Severity** | LOW |
| **Type** | BEST-PRACTICE |
| **Affected Modules** | `docker/entrypoint.sh:41` (`wait_for_db`), `docker/entrypoint.sh:60` (`wait_for_redis`) |
| **Classification** | advisory |

**Description:** The shared entrypoint expands secret-bearing connection URLs
directly into the `python -c` command-line argument:
```bash
/opt/venv/bin/python -c "import psycopg; psycopg.connect('$DATABASE_URL')"   # line 41
/opt/venv/bin/python -c "import redis; redis.from_url('$REDIS_URL').ping()"  # line 60
```
`$DATABASE_URL` contains the PostgreSQL password and `$REDIS_URL` may contain a
Redis password. Bash expansion places the **full URL (with credential) in the
process argument list**, visible to any process/readable via `/proc/<pid>/cmdline`
inside the container PID namespace during the startup wait loop (~30s).

**Evidence:** `docker/entrypoint.sh:41` and `:60` reproduce verbatim; the vars
are interpolated by the shell before `python -c` is exec'd.

**Consequence:** Transient credential exposure to co-located/untrusted processes
that can read the container's process table.

**Recommendation:** Connect using an env-var-read inside the Python snippet
(`psycopg.connect(os.environ["DATABASE_URL"])`) so the secret never appears in
args, or read the URL from a file/fd. Effort: small. Priority: advisory.

---

### CFG-006: Stale empty root entrypoint stubs tracked in git, shadowing real `docker/entrypoint*.sh`

| Field | Value |
|-------|-------|
| **Severity** | LOW |
| **Type** | SPEC-DEVIATION |
| **Affected Modules** | root `entrypoint.sh`, `entrypoint-catalog.sh`, `entrypoint-seed.sh`, `entrypoint-test.sh` (0 bytes, tracked) vs `docker/entrypoint*.sh` (real impl) |
| **Classification** | advisory |

**Description:** Four root-level entrypoint scripts are **0-byte files committed
to git** (confirmed via `git ls-files` + `Get-Item ... .Length` = 0), duplicating
the names of the real implementations that live in `docker/`. The real scripts
are in `docker/entrypoint*.sh`; the root ones are empty leftovers.

**Evidence:**
```
$ git ls-files entrypoint.sh entrypoint-catalog.sh entrypoint-seed.sh entrypoint-test.sh
  entrypoint-catalog.sh
  entrypoint-seed.sh
  entrypoint-test.sh
  entrypoint.sh
$ Get-Item entrypoint.sh ... # 0 bytes each
```
The shipped image is unaffected because the runtime `Dockerfile` stage does
`COPY --chown=app:app docker/entrypoint*.sh /app/` (overwriting the stubs copied
by the builder's `COPY . .`), and the compose dev/test overrides explicitly bind
`./docker/entrypoint*.sh`. However, the tracked empties are a footgun: any
future compose/volumes stanza that references `./entrypoint.sh` (root, no
`docker/` prefix) would mount a 0-byte script → container silently exits with
no-op behavior.

**Consequence:** Operational hazard / confusion; risk of a silent no-op entrypoint
if the `docker/` path prefix is omitted.

**Recommendation:** Delete the tracked empty root stubs (or add them to
`.dockerignore`), keeping the single source of truth in `docker/`. Effort:
trivial. Priority: advisory.

---

### CFG-007: `.env` source-location discrepancy between code and docs

| Field | Value |
|-------|-------|
| **Severity** | LOW |
| **Type** | DOC-UPDATE |
| **Affected Modules** | `src/backend/config/settings/base.py:16,28-46` vs `.env.example:3` and `docs/ops/docker-deployment.md:79,193` |
| **Classification** | advisory |

**Description:** `base.py` computes `BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent`
(=`src/` layout, base.py:16) and then `env_path = BASE_DIR / ".env"` = **`src/.env`**
(base.py:28). Django's `read_env(src/.env)` therefore reads `<repo>/src/.env`,
**not** the repository-root `.env` that `.env.example` instructs contributors to
create and that `docker-deployment.md` describes as "auto-loaded by Compose".

Locally this works **only** because `uv run` implicitly loads the repo-root
`.env` into `os.environ` (so `env(...)`/`os.getenv` find values via the
environment, not via `read_env`). A direct `python src/backend/manage.py
runserver` (without `uv run`) reads the empty `src/.env`, finds no
`DJANGO_SECRET_KEY`, and `sys.exit(1)` (base.py:44). There is also a stray
empty `src/.env` (0 bytes) in the working tree that is gitignored and masks the
issue.

In Docker the path is correct: compose bind-mounts `.env.docker` to
`/app/src/.env:ro` (`docker-compose.yml:51`), which matches `src/.env`.

**Evidence:**
```
base.py:16: BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent   # = .../src
base.py:28: env_path = BASE_DIR / ".env"                                         # = .../src/.env (empty locally)
.env.example:3: # Copy this file to .env (at the repository root...)
docker-compose.yml:51:  - ./.env.docker:/app/src/.env:ro
```

**Consequence:** The single source of truth for the env file location is
ambiguous; local dev silently depends on `uv`'s implicit `.env` loading rather
than the explicit `read_env` in code, and any non-`uv` invocation fails to load
the repo-root `.env`.

**Recommendation:** Make the source of truth explicit — either point
`env_path` at the repository root (`.env`) and update the Docker bind-mount to
`/app/.env`, or document that the canonical location is `src/.env` and remove
the conflicting repo-root `.env` guidance. Effort: small. Priority: advisory.

---

## Summary

| Severity | Count |
|----------|-------|
| CRITICAL | 0 |
| HIGH | 1 |
| MEDIUM | 2 |
| LOW | 3 |

## Mandatory Fixes

- **CFG-001** (HIGH): Remove the `:-admin` default credential from
  `docker-compose.yml:99` and `docker-compose.dev.override.yml:15`; require
  `ADMIN_PASSWORD` to be explicitly set (fail fast, matching the entrypoint guard
  and the documented "skip if empty" contract). This closes a default
  `admin`/`admin` superuser on the exposed `/admin/` panel.

## Advisory Recommendations

- **CFG-002**: Delete the dead module-level `DATABASE_URL`/`REDIS_URL` settings
  in `base.py`; reference `env(...)` once in `DATABASES`/`CACHES`.
- **CFG-003**: Validate the bulk-moderation request body through a Pydantic v2 DTO
  (`extra="forbid"`) per rule #11.
- **CFG-004**: Standardize settings loading on `env()` with explicit casts
  (`env.bool`, `env.list`) instead of ad-hoc `os.getenv`.
- **CFG-005**: Pass DB/Redis URLs to the boot `psycopg`/`redis` probes via
  `os.environ` inside the Python snippet so credentials are not exposed in
  process args.
- **CFG-006**: Remove the tracked 0-byte root `entrypoint*.sh` stubs; keep the
  canonical implementations in `docker/`.
- **CFG-007**: Resolve the `.env` source-location discrepancy (point
  `env_path` at the repository root, or update the Docker bind-mount/docs to
  `src/.env`).

## Doc Updates Needed

- **CFG-007** (`DOC-UPDATE`): align `.env.example` and `docs/ops/docker-deployment.md`
  with the env file location chosen in the fix.
- **CFG-006** (`DOC-UPDATE`): update any docs that reference the root `entrypoint*.sh`
  paths; confirm the canonical path is `docker/entrypoint*.sh`.
- **CFG-001** (`DOC-UPDATE`): update `.env.docker.example` and
  `docs/ops/docker-deployment.md` admin section to state `ADMIN_PASSWORD` is
  **required** (no silent default), and that omitting it must fail rather than
  create `admin`/`admin`.
