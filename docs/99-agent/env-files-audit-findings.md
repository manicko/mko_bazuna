# Environment Variable Files Audit — Findings

**Project:** Mko Bazuna  
**Audit Scope:** `.env` files, Dockerfile loading mechanism, Docker Compose interpolation, Django settings loading, CI/CD env var handling, Makefile references  
**Method:** File analysis + `docker compose config` runtime verification + empirical `.dockerignore` build-context test  
**Date:** 2026-09-16  

---

## 1. .env File Inventory

### Tracked in git (templates)
| File | Tracked | Purpose |
|------|---------|---------|
| `.env.example` | Yes | Comprehensive template covering all tiers |
| `.env.dev.example` | Yes | Dev template (no REGISTRY/REPOSITORY/IMAGE_TAG) |
| `.env.test.example` | Yes | Test template |
| `.env.prod.example` | Yes | Prod template (includes REGISTRY/REPOSITORY/IMAGE_TAG) |

### Gitignored (runtime secrets)
| File | Tracked | Content |
|------|---------|---------|
| `.env` | No (line 145) | Not present at root |
| `.env.dev` | No (line 146) | Real dev secret key, placeholder bot token |
| `.env.prod` | No (line 147) | Placeholder values for all secrets |
| `.env.test` | No (line 148) | Test-only values |
| `src/.env` | No (line 145: `.env` matches any dir) | Empty file (0 bytes) |
| `/entrypoint*.sh` | No (line 251) | Empty root-level stubs (real scripts in `docker/`) |

### Variable catalog per file

**Complete variable universe (from `.env.example`), 2026-09-16**

| Variable | .env.dev | .env.prod | .env.test | .env.dev.example | .env.test.example | .env.prod.example |
|----------|----------|-----------|-----------|-------------------|-------------------|-------------------|
| `DJANGO_SECRET_KEY` | Real key | Placeholder | Test key | Placeholder | Test key | Placeholder |
| `DEBUG` | `True` | `False` | `True` | `True` | `True` | `False` |
| `ALLOWED_HOSTS` | `localhost,127.0.0.1,0.0.0.0` | `<domain>` | `localhost,127.0.0.1` | `localhost,127.0.0.1,0.0.0.0` | `localhost,127.0.0.1` | `<domain>` |
| `POSTGRES_USER` | `bazuna_user` | `bazuna_user` | `postgres` | `bazuna_user` | `postgres` | `bazuna_user` |
| `POSTGRES_DB` | `bazuna_db` | `bazuna_db` | `mko_bazuna` | `bazuna_db` | `mko_bazuna` | `bazuna_db` |
| `POSTGRES_PASSWORD` | `your-password` | `<secure>` | `postgres` | `<dev-db-password>` | `postgres` | `<secure>` |
| `POSTGRES_HOST` | (absent) | (absent) | `db` | (absent) | `db` | (absent) |
| `REDIS_URL` | `redis://redis:6379/0` | `redis://redis:6379/0` | (empty) | `redis://redis:6379/0` | (empty) | `redis://redis:6379/0` |
| `BOT_USERNAME` | Placeholder | Placeholder | `test-bot` | Placeholder | `test-bot` | Placeholder |
| `BOT_TOKEN` | Placeholder | Placeholder | Test token | Placeholder | Test token | Placeholder |
| `GOOGLE_TRANSLATE_API_KEY` | Dummy key | Placeholder | **MISSING** | Dummy key | **MISSING** | Placeholder |
| `SITE_URL` | `http://localhost:8000` | `<prod-url>` | **MISSING** | `http://localhost:8000` | **MISSING** | `<prod-url>` |
| `IMMEDIATE_ALERTS_ENABLED` | `false` | `false` | **MISSING** | `false` | **MISSING** | `false` |
| `TLS_CERT_PATH` | `/etc/nginx/certs` | `/etc/nginx/certs` | **MISSING** | `/etc/nginx/certs` | **MISSING** | `/etc/nginx/certs` |
| `PLAUSIBLE_HOST` | (empty) | (empty) | **MISSING** | (empty) | **MISSING** | (empty) |
| `ADMIN_USERNAME` | `admin` | `admin` | `admin` | `admin` | `admin` | `admin` |
| `ADMIN_PASSWORD` | (empty) | `<secure>` | `test-admin-password` | (empty) | `test-admin-password` | `<secure>` |
| `ADMIN_TELEGRAM_ID` | `-1` | `-1` | `-1` | `-1` | `-1` | `-1` |
| `SEED_USERS` | `10` | `10` | `2` | `10` | `2` | `10` |
| `SEED_ADS` | `600` | `600` | `10` | `600` | `10` | `600` |
| `FIX_PERMISSIONS` | `0` | `0` | **MISSING** | `0` | **MISSING** | `0` |
| `SKIP_ENV_CHECK` | (empty) | (empty) | `1` | (empty) | `1` | (empty) |
| `REGISTRY` | (absent) | `ghcr.io` | (absent) | (absent) | (absent) | `ghcr.io` |
| `REPOSITORY` | (absent) | `manicko/mko_bazuna` | (absent) | (absent) | (absent) | `manicko/mko_bazuna` |
| `IMAGE_TAG` | (absent) | `latest` | (absent) | (absent) | (absent) | `latest` |

---

## 2. Findings

### ENV-001 [CRITICAL] `.dockerignore` pattern `.env*` does NOT exclude `src/.env`

**File:** `.dockerignore` line 5 (`*.env*`)  
**Dockerfile:** `docker/Dockerfile` lines 57 (`COPY . .`), 117 (`COPY --from=builder --chown=app:app /app/src /app/src`)  

**Evidence (empirical build-context test):**

Built a Docker image from a test context containing `src/.env` (with `secret_value=leaked`) and root-level `.env` / `.env.dev`. `.dockerignore` had `.env*` (same as project):

```
=== Root files ===      (no .env, no .env.dev — both excluded by .env*)
=== src/ files ===
-rw-r--r-- 1 root root 44 Sep 16 ... .env  ← src/.env is PRESENT in the image!
```

**Analysis:**

Docker's `.dockerignore` uses Go's `path.Match` where `*` does **not** cross path separators (`/`). The pattern `.env*` is matched against the full relative path of each file relative to the build context root:
- `.env` at root → relative path `.env` → matches `.env*` ✓ (excluded)
- `.env.dev` at root → relative path `.env.dev` → matches `.env*` ✓ (excluded)
- `src/.env` → relative path `src/.env` → does NOT start with `.env` → does NOT match `.env*` ✗ (NOT excluded)

**Dockerfile flow:**
1. Line 57: `COPY . .` copies the entire build context into the builder stage at `/app`. `src/.env` IS included (not excluded by `.dockerignore`).
2. Line 117: `COPY --from=builder --chown=app:app /app/src /app/src` propagates `/app/src` (including `.env`) to the runtime stage.
3. Line 174 (test-runtime): inherits from runtime — `/app/src/.env` exists in the test image.

At runtime, the volume mount `.env.dev:/app/src/.env:ro` (or `.env.test` / `.env.prod`) overrides the file. So the currently-empty `src/.env` is harmless at runtime. **However**, if any developer writes secrets into `src/.env` (e.g., for local Django CLI usage without Docker, which is the documented purpose per `base.py` line 29: `env_path = BASE_DIR / ".env"`), those secrets would be baked into every Docker image build and propagated through all stages.

**Consequence:**

Defense-in-depth failure. The `.dockerignore` is the last line of defense against `.env` files entering the build context. `.env*` covers root-level files but `src/.env` slips through. If secrets are ever placed there (and the file already exists locally as an empty placeholder), they become permanently embedded in the image and can be extracted by anyone with image access.

**Recommendation:**

Add `src/.env` or a broader pattern like `**/.env` to `.dockerignore` (in addition to the existing `.env*`). This is a defense-in-depth measure. Effort: **trivial**. Priority: **recommended** (security hardening).

---

### ENV-002 [CRITICAL] 5 services in test compose retain `.env.dev` env_file, `.env.dev` volume mount, and `config.settings.prod`

**Files:** `docker-compose.yml` (base), `docker-compose.test.yml` (override)

**Evidence (runtime `docker compose config` — service-by-service):**

```
Service       | .env volume mount | DJANGO_SETTINGS_MODULE  | DJANGO_SECRET_KEY       | BOT_TOKEN                     |
--------------|-------------------|------------------------|------------------------|------------------------------|
bot           | .env.dev          | config.settings.prod   | *wndq(7qkw(1$...)       | <your-bot-token-from-botfather> |
web           | .env.dev          | config.settings.prod   | *wndq(7qkw(1$...)       | <your-bot-token-from-botfather> |
load_cities   | .env.dev          | config.settings.prod   | test-secret-key-for...  | test-bot-token-for-testing     |
load_catalog  | .env.dev          | config.settings.prod   | test-secret-key-for...  | test-bot-token-for-testing     |
seed          | .env.dev          | config.settings.prod   | (behind profile)        | (behind profile)              |
migrate       | .env.dev          | config.settings.test   | test-secret-key-for...  | test-bot-token-for-testing     |
create_admin  | .env.dev          | config.settings.test   | test-secret-key-for...  | test-bot-token-for-testing     |
db            | .env.test         | config.settings.test   | test-secret-key-for...  | test-bot-token-for-testing     |
```

(Services `test` and `seed` are behind profiles and excluded from default `config` output. `seed` uses `env_file: .env.dev` and `DJANGO_SETTINGS_MODULE=config.settings.prod` from the base compose.)

`docker-compose.test.yml` only overrides **4 services**: `db`, `migrate`, `create_admin`, and adds `test`. The remaining 5 services (`bot`, `web`, `load_cities`, `load_catalog`, `seed`) are **completely absent** from the test override.

**Subtle detail — mixed env resolution for `load_cities`/`load_catalog`:**

The base compose's `environment:` section for `load_cities` (line 94-100) and `load_catalog` (line 120-126) includes:
```yaml
DJANGO_SECRET_KEY: ${DJANGO_SECRET_KEY:?DJANGO_SECRET_KEY must be set}
BOT_TOKEN: ${BOT_TOKEN}
```

Since `--env-file .env.test` is passed, these are interpolated from `.env.test` (test values). Docker Compose's `environment` takes precedence over `env_file` for overlapping keys. So `DJANGO_SECRET_KEY` and `BOT_TOKEN` resolve to test values for these services.

**BUT** `GOOGLE_TRANSLATE_API_KEY`, `SITE_URL`, `FIX_PERMISSIONS`, `PLAUSIBLE_HOST`, `IMMEDIATE_ALERTS_ENABLED`, `TLS_CERT_PATH`, `ADMIN_PASSWORD` are NOT in the `environment:` section — they come from `env_file: .env.dev` (dev values). And `ADMIN_PASSWORD` is `""` (empty in .env.dev).

**Subtle detail — `bot`/`web` get dev secret key directly from `env_file`:**

The `bot` (line 145-155) and `web` (line 174-185) services' `environment:` section does NOT include `DJANGO_SECRET_KEY` or `BOT_TOKEN`. These come purely from `env_file: .env.dev` → the REAL dev secret key (`*wndq(7qkw(1$...)`) and PLACEHOLDER bot token (`<your-bot-token-from-botfather>`).

**Command that triggers the issue:**

```bash
$ docker compose --env-file .env.test -f docker-compose.yml -f docker-compose.test.yml up -d
```

This starts `web`, `bot`, `load_cities`, `load_catalog`, `migrate`, `create_admin`, `redis`, `nginx`, `db` — all non-profiled services. The `web` and `bot` services would:
1. Run with `DJANGO_SETTINGS_MODULE=config.settings.prod` (production settings, NOT overridden)
2. Use the REAL dev `DJANGO_SECRET_KEY` from `.env.dev` for session/CSRF signing
3. Use a PLACEHOLDER `BOT_TOKEN` (`<your-bot-token-from-botfather>`) — the bot would attempt Telegram API calls with an invalid token and fail at runtime
4. Connect to PostgreSQL via `DATABASE_URL` interpolated from `.env.test` (`postgres://postgres:postgres@db:5432/mko_bazuna`) — the test database
5. Have `.env.dev` (with real dev secrets) bind-mounted at `/app/src/.env`

The `prod.py` settings guards would pass because the placeholder values are non-empty strings (they check `if not BOT_TOKEN`, not `if BOT_TOKEN == "<placeholder>"`).

**Note:** `make test` and `make test-all` avoid this because they only start the `db` service and run the `test` one-shot service. But the risk exists for anyone running `docker compose up` with the test flag files.

**Recommendation:**

Add explicit overrides for `bot`, `web`, `load_cities`, `load_catalog`, and `seed` in `docker-compose.test.yml` to set `DJANGO_SETTINGS_MODULE=config.settings.test`, `env_file: .env.test`, and `.env.test:/app/src/.env:ro` volume mount. Alternatively, assign `profiles: ["seed"]` to the `seed` service in the base compose so it doesn't start without explicit profiling. Effort: **small**. Priority: **recommended** (prevents accidental production-secret exposure and settings mismatch).

---

### ENV-003 [HIGH] `migrate` and `create_admin` in test compose still bind-mount `.env.dev` at `/app/src/.env`

**File:** `docker-compose.yml` lines 113-115 (base `migrate` volumes), `docker-compose.test.yml` lines 30-34 (test override)

**Evidence (runtime `docker compose config`):**

```
migrate:
  volumes:
    - type: bind
      source: C:\py_dev\mko_bazuna\.env.dev
      target: /app/src/.env        ← .env.dev, NOT .env.test!
      read_only: true
create_admin:
  volumes:
    - type: bind
      source: C:\py_dev\mko_bazuna\.env.dev
      target: /app/src/.env        ← .env.dev, NOT .env.test!
      read_only: true
```

The test override for `migrate` (lines 30-34) changes `env_file` to `.env.test` and adds `DJANGO_SETTINGS_MODULE=config.settings.test` to the `environment:` section, but does NOT override `volumes:`. Docker Compose merges volume lists (base + override), so the base's `./.env.dev:/app/src/.env:ro` survives unchanged.

**Consequence:**

Inside the `migrate` and `create_admin` containers, `/app/src/.env` contains `.env.dev` content (real dev secret key, placeholder bot token). The `base.py` code skips `read_env()` when `DJANGO_SETTINGS_MODULE` contains `"test"` (line 52), so the file is never read by Django. However:

1. The `entrypoint.sh` `check_env_file()` function checks for the file's existence — it passes because the file exists, but with the wrong content (dev, not test).
2. Any debugging that reads `/app/src/.env` inside the container would see dev secrets, not test values.
3. The `create_admin` entrypoint (`entrypoint-create-admin.sh`) sources `entrypoint.sh` which calls `check_env_file()`. `SKIP_ENV_CHECK=1` from `.env.test` (loaded via `env_file`) bypasses the check, but the volume mount still exposes `.env.dev` on the filesystem.

**Recommendation:**

Add `volumes: - ./.env.test:/app/src/.env:ro` to the `migrate` and `create_admin` overrides in `docker-compose.test.yml` to override the base compose's volume mount. Effort: **trivial**. Priority: **recommended** (consistency/clarity).

---

### ENV-004 [HIGH] Docker Compose `env_file` directive is invisible in `docker compose config` output

**File:** Docker Compose v5 behavior

**Evidence:**

```bash
$ docker compose --env-file .env.test -f docker-compose.yml -f docker-compose.test.yml config | grep env_file
(no output — the `env_file` key does not appear)
```

Docker Compose v5 resolves `env_file` directives by reading the referenced files at config time and merging their contents into the `environment` section of each service in the resolved config. The `env_file` key itself does NOT appear in the output. This makes it impossible to determine from `docker compose config` alone which `.env` file was specified as `env_file` for each service — the values are indistinguishable from explicitly-set `environment:` entries.

**Consequence:**

This is the root cause of why ENV-002 and ENV-003 went undetected during normal review. An auditor running `docker compose config` sees a flat `environment:` section with all variables and cannot tell that:
- `bot` and `web` get `DJANGO_SECRET_KEY` from `.env.dev` (via `env_file`)
- `load_catalog` gets `GOOGLE_TRANSLATE_API_KEY` from `.env.dev` (via `env_file`) while its `DJANGO_SECRET_KEY` comes from `.env.test` (via `environment:` interpolation)
- `migrate` and `create_admin` have `.env.dev` bind-mounted at `/app/src/.env` (via `volumes:` from base compose) despite `env_file: .env.test`

**Recommendation:**

This is a Docker Compose limitation, not a project code issue. However, the project should document this behavior for future auditors. Add a comment block at the top of `docker-compose.test.yml` noting: "Docker Compose v5 resolves `env_file` into `environment` in `config` output — use the volumes section to verify which .env file is bind-mounted for each service." Effort: **trivial**. Priority: **recommended** (auditability).

---

### ENV-005 [HIGH] `.env.test` is missing 6 variables present in all other .env tiers

**Files:** `.env.test` (35 lines), `.env.dev` (65 lines), `.env.test.example` (35 lines)

**Missing variables (present in `.env.dev` and `.env.dev.example` but absent from `.env.test` and `.env.test.example`):**

| Variable | `base.py` default | Loaded by | Risk if absent in test |
|----------|-------------------|-----------|----------------------|
| `GOOGLE_TRANSLATE_API_KEY` | `""` (line 71) | `env("GOOGLE_TRANSLATE_API_KEY", default="")` | None (default used) |
| `SITE_URL` | `"http://localhost:8000"` (line 255) | `env.str("SITE_URL", default=...)` | None (default used) |
| `IMMEDIATE_ALERTS_ENABLED` | `False` (line 259) | `env.bool(..., default=False)` | None (default used) |
| `TLS_CERT_PATH` | (not in base.py) | Used only in docker-compose.prod.yml | None (prod-only) |
| `PLAUSIBLE_HOST` | `""` (line 263) | `env("PLAUSIBLE_HOST", default="")` | None (default used) |
| `FIX_PERMISSIONS` | (not in base.py) | Bash: `[ "$FIX_PERMISSIONS" = "1" ]` (entrypoint.sh:26) | None (DEBUG=True triggers fix_volume_permissions anyway) |

**Evidence:**

`base.py` line 255:
```python
SITE_URL = env.str("SITE_URL", default="http://localhost:8000").rstrip("/")
```

`docker/entrypoint.sh` line 26:
```bash
if [ "$DEBUG" = "True" ] || [ "$FIX_PERMISSIONS" = "1" ]; then
```

**Consequence:**

No immediate runtime failure — all missing variables have defaults in `base.py` or `entrypoint.sh`. However:

1. The `.env.test.example` template is incomplete. A developer following it will not know these 6 variables exist.
2. If a future code change removes the default for any of these variables (e.g., making `SITE_URL` required in `base.py`), tests would fail with a cryptic `ImproperlyConfigured` error that doesn't mention which `.env` file is missing the variable.
3. `FIX_PERMISSIONS` is absent from `.env.test`, but `DEBUG=True` in `.env.test` triggers `fix_volume_permissions` anyway (entrypoint.sh:26), so the absence is masked. If a future change sets `DEBUG=False` in test, `fix_volume_permissions` would silently not run because `FIX_PERMISSIONS` is unset.
4. `IMMEDIATE_ALERTS_ENABLED` defaults to `False` via `env.bool(..., default=False)`. But if the Env schema's default changes, it could behave differently.

**Recommendation:**

Add the 6 missing variables (with test-appropriate values: empty strings or `False` where applicable) to both `.env.test` and `.env.test.example`. This ensures parity with the `.env.example` template and `.env.dev`/`.env.prod`. Effort: **small**. Priority: **recommended** (maintainability).

---

### ENV-006 [HIGH] Bash Makefile uses shell variables not sourced from `.env.dev`

**File:** `Makefile` lines 9, 187-191, 219-220, 229-235, 248-249

**Evidence:**

`Makefile` line 9: `ENV_FILE := --env-file .env.dev`

`create-admin` target (lines 187-191):
```makefile
create-admin:
	docker compose $(COMPOSE_FILES) run --rm web uv run python src/backend/manage.py create_admin_user \
		--username "${ADMIN_USERNAME:-admin}" \
		--password "${ADMIN_PASSWORD}" \
		--telegram-id "${ADMIN_TELEGRAM_ID:--1}"
```

`db-shell` target (lines 219-220):
```makefile
db-shell:
	docker compose $(COMPOSE_FILES) exec db psql -U $${POSTGRES_USER} -d $${POSTGRES_DB}
```

`backup` target (lines 229-235):
```makefile
backup:
	@mkdir -p $(BACKUPS_DIR)
	@TIMESTAMP=$$(date +%Y%m%d_%H%M%S) && \
		docker compose $(ENV_FILE) -f docker-compose.yml exec -T db \
			pg_dump -U $${POSTGRES_USER} -d $${POSTGRES_DB} -F c \
			> $(BACKUPS_DIR)/dump_$${TIMESTAMP}.dump && \
		echo "✓ Backup created: $(BACKUPS_DIR)/dump_$${TIMESTAMP}.dump"
```

`restore` target (lines 248-249):
```makefile
	docker compose $(ENV_FILE) -f docker-compose.yml exec -T db \
		pg_restore -U $${POSTGRES_USER} -d $${POSTGRES_DB} --clean --if-exists $(BACKUP_FILE)
```

**Analysis:**

In a Makefile recipe, `$${VAR}` becomes `${VAR}` in the shell — a **shell environment variable**. `${VAR:-default}` is a shell parameter expansion with a fallback. These are expanded by the shell **before** Docker Compose receives the command.

The `--env-file .env.dev` flag (`$(ENV_FILE)`) only makes variables available to Docker Compose for compose-file `${VAR}` interpolation and for the container's `env_file` directive. It does **NOT** export variables to the host shell's environment.

So:
- `${ADMIN_PASSWORD}` (no `:-` default) → expands to empty string if not in shell's environment
- `${ADMIN_USERNAME:-admin}` → uses shell var if set, otherwise `admin`
- `${ADMIN_TELEGRAM_ID:--1}` → uses shell var if set, otherwise `-1`
- `$${POSTGRES_USER}` / `$${POSTGRES_DB}` → empty if not in shell's environment

**Contrast with `Makefile.ps1`:**

`Makefile.ps1` lines 18-33 explicitly read `.env.dev` and set environment variables in the PowerShell session:
```powershell
$envContent = Get-Content -Path ".env.dev" -ErrorAction SilentlyContinue
if ($envContent) {
    foreach ($line in $envContent) {
        if ($line -match "^([^#=]+)=(.*)$") {
            $name = $matches[1].Trim()
            $value = $matches[2].Trim()
            $current = Get-Item -Path "env:$name" -ErrorAction SilentlyContinue
            if (-not $current -or -not $current.Value) {
                Set-Item -Path "env:$name" -Value $value
            }
        }
    }
}
```

And the PowerShell `Invoke-Backup` function (lines 239-245) explicitly validates these vars are set:
```powershell
$pgUser = $env:POSTGRES_USER
$pgDb = $env:POSTGRES_DB
if (-not $pgUser -or -not $pgDb) {
    Write-Host "Error: POSTGRES_USER and POSTGRES_DB must be set in .env.dev or environment" -ForegroundColor Red
    exit 1
}
```

The bash Makefile has **no such loading or validation** — it silently passes empty values.

**Consequence:**

- `make create-admin` → `--password ""` (empty). The `create_admin_user` management command may fail or create a superuser with an empty password.
- `make db-shell` → `psql -U "" -d ""` → psql defaults to the current OS user and database. On a developer machine, this likely connects to the wrong PostgreSQL instance or fails.
- `make backup` → `pg_dump -U "" -d ""` → connection error or dumps the wrong database.
- `make restore` → same issue as backup.

These targets only work if the user manually `export POSTGRES_USER=... PGPASSWORD=... ADMIN_PASSWORD=...` in their shell before running `make`. This is **undocumented** and **error-prone**.

**Recommendation:**

The bash Makefile should source `.env.dev` before running these targets, following the same pattern as `Makefile.ps1`. The simplest fix: add a shared `export` preamble. For example:

```makefile
# Load .env.dev vars for make-level shell variable expansion (db-shell, backup, etc.)
SHELL_EXPORT := $(shell [ -f .env.dev ] && echo "set -a; . .env.dev; set +a")
SHELL_EXPORT := SHELL_EXPORT=$(SHELL_EXPORT)
```

Or use the bash-specific approach:
```makefile
db-shell:
	@set -a; . .env.dev; set +a; docker compose $(COMPOSE_FILES) exec db psql -U "$$POSTGRES_USER" -d "$$POSTGRES_DB"
```

Effort: **small**. Priority: **recommended** (usability/correctness).

**Not a problem:** `Makefile.ps1` (PowerShell/Windows path) handles this correctly. Windows users should use `Makefile.ps1`.

---

### ENV-007 [MEDIUM] Inaccurate comments in `docker-compose.test.yml` about `.env` bind-mount and `volumes:` override

**File:** `docker-compose.test.yml` lines 7, 56

**Evidence:**

Line 7 (above `db` service):
```yaml
  # Override db service for test: long-running, persistent PostgreSQL.
  # `volumes` is NOT overridden here, so the base `postgres_data` volume applies
```

**Reality:** The `volumes:` section IS present in the `db` override (lines 16-17). Docker Compose **merges** volume lists (base + override), so both `postgres_data` (from base) and `./.env.test:/app/src/.env:ro` (from override) are present. The comment says "volumes is NOT overridden" but it clearly IS overridden — a `volumes:` key is present in the YAML. The intent (postgres_data is preserved) is correct, but the wording is wrong.

Line 56 (above `SKIP_ENV_CHECK`):
```yaml
      # .env is not bind-mounted; entrypoint.sh skips its existence check (CR3 safety)
```

**Reality:** Line 61 shows `.env.test` IS bind-mounted to `/app/src/.env:ro`:
```yaml
    volumes:
      - .:/app
      - ./.env.test:/app/src/.env:ro
```

The comment likely means "the root-level `.env` file is not present" (there's no `.env` at the project root — only `.env.dev`, `.env.test`, etc.). But `/app/src/.env` IS bind-mounted (as `.env.test` content), so the `check_env_file()` function in `entrypoint.sh` would find the file. The `SKIP_ENV_CHECK=1` bypass is still needed because the `check_env_file` logic checks `DJANGO_SETTINGS_MODULE != config.settings.test`, and the entrypoint.sh is shared across all services.

**Consequence:**

Misleading comments cause confusion. A developer reading "volumes is NOT overridden" might remove the `volumes:` section thinking it's unnecessary, accidentally losing the `.env.test` bind-mount. The "`.env is not bind-mounted" comment contradicts the actual volume mount on line 61.

**Recommendation:**

Fix the comment on line 7: `# volumes: extends the base — both postgres_data (from base) and .env.test:/app/src/.env:ro (from override) are mounted`.

Fix the comment on line 56: `# .env.test is bind-mounted as /app/src/.env; SKIP_ENV_CHECK=1 bypasses entrypoint.sh's existence check (CR3 safety)`.

Effort: **trivial**. Priority: **recommended** (clarity).

---

### ENV-008 [MEDIUM] `${VAR:?}` warns instead of failing when `--env-file` is omitted

**File:** `docker-compose.yml` lines 10-12, 41-43, 67-69, 94-96, 119-122, 145-149, 174-177, 195-198, 203-206

**Evidence:**

```bash
$ docker compose -f docker-compose.yml -f docker-compose.test.yml config 2>&1 | head -5
time="2026-09-16T11:07:21+02:00" level=warning msg="The \"POSTGRES_USER\" variable is not set. Defaulting to a blank string."
time="2026-09-16T11:07:21+02:00" level=warning msg="The \"POSTGRES_PASSWORD\" variable is not set. Defaulting to a blank string."
time="2026-09-16T11:07:21+02:00" level=warning msg="The \"POSTGRES_DB\" variable is not set. Defaulting to a blank string."
...
(exit code: 0 — command SUCCEEDED)
```

The base `docker-compose.yml` uses `${VAR:?error message}` syntax (e.g., `${POSTGRES_DB:?POSTGRES_DB must be set}` on line 10). Docker Compose v5 treats `:?` as a **warning-only** mechanism — it prints a warning to stderr and defaults to a blank string instead of failing. The command exits with code 0 and produces valid output with blank values.

**Consequence:**

If a developer runs `docker compose -f docker-compose.yml -f docker-compose.test.yml up` without `--env-file .env.test`, all services would start with blank `POSTGRES_USER`, `POSTGRES_DB`, `POSTGRES_PASSWORD`, `DJANGO_SECRET_KEY`. The PostgreSQL container would fail to start (blank `POSTGRES_PASSWORD` is rejected by PostgreSQL's init script). The Django services would fail with `ImproperlyConfigured` (empty `DJANGO_SECRET_KEY` causes `env("DJANGO_SECRET_KEY")` to raise). But the failure is delayed and the error messages are confusing — the developer sees warnings about variables being "not set" scattered among other output, and then unrelated container crash errors.

When `--env-file .env.test` IS passed (as `make test` does via `COMPOSE_TEST := --env-file .env.test`), all `${VAR:?}` interpolations resolve correctly and no warnings appear.

**Recommendation:**

No code fix needed — this is Docker Compose's defined behavior with the `:?` syntax. However, consider adding a pre-flight validation step in the Makefile to catch missing env files early:
```makefile
config-check:
	docker compose $(COMPOSE_TEST) config --quiet 2>&1 | grep -v "warning msg" || true
```

Or document that `--env-file` must always be used. Effort: **trivial**. Priority: **recommended** (operational reliability).

**Not a problem:** With `--env-file .env.test` (as `make test` does), all `${VAR:?}` interpolations resolve correctly and the config produces no warnings.

---

### ENV-009 [MEDIUM] CI/CD sets different env vars than Docker Compose; divergence is by design but undocumented

**File:** `.github/workflows/ci.yml` (lines 68, 84-85, 94-95, 107-110, 124-126, 217-218, 233-235, 258-260)

**Evidence — CI only sets 3 env vars directly:**

```yaml
- DJANGO_SETTINGS_MODULE: config.settings.test    # CI only
- DATABASE_URL: postgres://postgres:postgres@localhost:5432/mko_bazuna  # CI only
- DJANGO_SECRET_KEY: test-secret-key-for-testing-only  # CI only
```

**Comparison table (CI vs Docker Compose `.env.test` vs `base.py` defaults):**

| Variable | CI (GitHub Actions) | Docker Compose test | `base.py` default |
|----------|---------------------|---------------------|-------------------|
| `BOT_TOKEN` | (unset → `""`) | `test-bot-token-for-testing` | `""` |
| `REDIS_URL` | (unset → uses default) | (empty) | `redis://localhost:6379/0` |
| `ALLOWED_HOSTS` | (unset → `[]`) | `localhost,127.0.0.1` | `[]` |
| `SITE_URL` | (unset → default) | (missing from .env.test) | `http://localhost:8000` |
| `GOOGLE_TRANSLATE_API_KEY` | (unset → `""`) | (missing from .env.test) | `""` |
| `PLAUSIBLE_HOST` | (unset → `""`) | (missing from .env.test) | `""` |
| `POSTGRES_HOST` | (not needed — DATABASE_URL set directly) | `db` (in .env.test) | `localhost` |
| `POSTGRES_USER` | (not needed — DATABASE_URL set directly) | `postgres` | (not used if DATABASE_URL set) |

**Key difference:** CI runs tests natively (no Docker). It sets `DATABASE_URL` directly (pointing to `localhost:5432`), while Docker Compose constructs `DATABASE_URL` from `POSTGRES_*` variables (pointing to `db:5432`). CI does NOT set `POSTGRES_USER`, `POSTGRES_DB`, `POSTGRES_PASSWORD` — it uses a single `DATABASE_URL` string. Docker Compose sets individual `POSTGRES_*` vars AND constructs `DATABASE_URL`.

In CI, `base.py` line 181 checks `if os.getenv("DATABASE_URL"):` → True → uses `env.db()` to parse it → skips the `POSTGRES_*` fallback (lines 187-202). This works.

In Docker Compose (test mode), both `DATABASE_URL` (via `environment:` interpolation) and `POSTGRES_*` vars (via `env_file` and `environment:`) are present. `base.py` uses `DATABASE_URL` first. This also works.

**Consequence:**

No immediate failure — both environments produce working test runs. But:

1. The env var sets are different between CI and Docker Compose. A developer debugging a test failure that only occurs in one environment may need to check both.
2. CI doesn't exercise the `POSTGRES_*` → `DATABASE_URL` fallback path (base.py lines 187-202). Any bug in that code path would only be caught in Docker Compose, not CI.
3. CI doesn't test with `POSTGRES_HOST` set — if code changes introduced a dependency on `POSTGRES_HOST` via the `else` branch in `base.py`, CI would silently use the `DATABASE_URL` path and skip the `else` branch entirely.
4. CI doesn't set `SITE_URL`, `GOOGLE_TRANSLATE_API_KEY`, etc. — it relies on `base.py` defaults. Docker Compose test mode (for services using `env_file: .env.test`) also relies on defaults for these. So both are consistent in this regard — but a future change to defaults would affect both differently.

**Recommendation:**

Document the CI/Docker Compose env var divergence in `docs/99-agent/architecture.md`. Specifically: "CI sets `DATABASE_URL`, `DJANGO_SECRET_KEY`, `DJANGO_SETTINGS_MODULE` directly as GitHub Actions env vars. Docker Compose constructs `DATABASE_URL` from `POSTGRES_*` vars. Both environments set `DJANGO_SETTINGS_MODULE=config.settings.test`. Other variables rely on `base.py` defaults in CI and on `.env.test` in Docker Compose." Effort: **trivial**. Priority: **informational**.

---

### ENV-010 [LOW] Root-level `entrypoint.sh` and `entrypoint-test.sh` are empty stubs (0 bytes)

**Files:** `entrypoint.sh` (0 bytes), `entrypoint-test.sh` (0 bytes)  
**Git status:** Both gitignored via `.gitignore` line 251: `/entrypoint*.sh`

**Evidence:**

```bash
$ git ls-files '**/entrypoint*.sh'
docker/entrypoint-catalog.sh
docker/entrypoint-cities.sh
docker/entrypoint-create-admin.sh
docker/entrypoint-scheduler.sh
docker/entrypoint-seed.sh
docker/entrypoint-test.sh
docker/entrypoint.sh
# (no root-level entrypoint*.sh — they are gitignored)
```

**Analysis:**

The Dockerfile flow:
- Line 57: `COPY . .` copies the root-level empty `entrypoint*.sh` stubs to `/app/entrypoint*.sh` in the builder stage.
- Line 129: `COPY --chown=app:app docker/entrypoint*.sh /app/` overwrites them with the REAL scripts from `docker/`.

So the empty stubs are harmless — they're overwritten by the real scripts before the image is finalized.

**Consequence:**

Low risk. The empty stubs are overwritten during the Docker build. But a developer might see both root-level and `docker/`-level entrypoint scripts and edit the wrong (empty) one, introducing confusion.

**Recommendation:**

Remove the root-level empty stubs, or replace them with a redirect notice (e.g., `# See docker/entrypoint.sh — canonical scripts live in docker/`). Effort: **trivial**. Priority: **informational**.

**Not a problem:** The Dockerfile correctly overwrites the stubs (line 129 runs after line 57). The image has the correct entrypoint scripts.

---

### ENV-011 [LOW] `src/.env` empty file not excluded from Docker build context

**File:** `src/.env` (0 bytes, empty)

**Git status:** Ignored via `.gitignore` line 145 (`.env` pattern matches `src/.env` at any directory level):

```bash
$ git check-ignore -v src/.env
.gitignore:145:.env	src/.env
```

**Docker behavior:** NOT excluded by `.dockerignore` `.env*` pattern (see ENV-001).

**Analysis:**

The `src/.env` file is the file that `base.py` line 29 expects: `env_path = BASE_DIR / ".env"` where `BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent` = `src/` (4 levels up from `src/backend/config/settings/base.py`).

In Docker:
1. At build time: `COPY . .` (line 57) copies `src/.env` (empty) into the builder at `/app/src/.env`. Then `COPY --from=builder ... /app/src` (line 117) propagates it to the runtime image.
2. At runtime: the volume mount `./.env.dev:/app/src/.env:ro` (or `.env.test`/`.env.prod`) overrides the file.

The `base.py` lines 30-45 handle the case where `.env` is missing:
```python
env_path = BASE_DIR / ".env"
if not env_path.exists():
    if (os.getenv("DJANGO_SETTINGS_MODULE") and "test" not in ...
        and not os.getenv("DJANGO_BUILD") and not os.getenv("DJANGO_SECRET_KEY")):
        logger.error("ERROR: .env file not found...")
        sys.exit(1)
else:
    if "test" not in os.getenv("DJANGO_SETTINGS_MODULE", ""):
        environ.Env.read_env(env_path)
```

In the Docker image, `src/.env` exists (empty). The `.env` file existence check passes. But `read_env()` is skipped in test mode. During Docker build, `DJANGO_BUILD=1` is set (line 70 of Dockerfile), so the `sys.exit(1)` is not triggered.

**Consequence:**

None in the current configuration. But the empty `src/.env` in the image is confusing — an operator inspecting the image would find an empty `.env` file and might assume it's a problem. If secrets are written to `src/.env` locally, they would be baked into the image (see ENV-001).

**Recommendation:**

Fix the `.dockerignore` to exclude `src/.env` (see ENV-001). No other action needed for the empty file itself. Effort: **trivial** (depends on ENV-001 fix). Priority: **informational** (not a problem if ENV-001 is fixed).

---

### ENV-012 [LOW] `POSTGRES_HOST` inconsistency across .env files

**Files:** `.env.test` line 16 (`POSTGRES_HOST=db`), `.env.dev` (no `POSTGRES_HOST`), `.env.prod` (no `POSTGRES_HOST`)

**Evidence:**
- `.env.test`: `POSTGRES_HOST=db` (explicitly defined)
- `.env.dev`: no `POSTGRES_HOST` — set via `environment: POSTGRES_HOST: db` in docker-compose.yml (lines 44, 66, 94, etc.)
- `.env.prod`: no `POSTGRES_HOST` — same, set via `environment:` in docker-compose.yml
- `base.py` line 194: `env("POSTGRES_HOST", default="localhost")`

**Analysis:**

`.env.test` redundantly defines `POSTGRES_HOST=db`, which is also set in the `environment:` section of docker-compose.yml. Docker Compose's `environment` takes precedence over `env_file`, so the `.env.test` value is overridden — it's redundant. But `.env.test.example` also has `POSTGRES_HOST=db` (line 16), so the template is consistent with `.env.test`.

`.env.dev.example` and `.env.prod.example` do NOT have `POSTGRES_HOST`, which is inconsistent with `base.py` reading it via `env("POSTGRES_HOST", default="localhost")`.

In CI: `POSTGRES_HOST` is not set. But `DATABASE_URL=postgres://postgres:postgres@localhost:5432/mko_bazuna` is set directly, so `base.py` line 181 uses `env.db()` and never reads `POSTGRES_HOST`. This is correct.

**Consequence:**

If the `DATABASE_URL` path is not used (i.e., `os.getenv("DATABASE_URL")` is falsy), `base.py` falls back to individual `POSTGRES_*` vars. `POSTGRES_HOST` would be `localhost` (default) in dev/prod (since it's not in `.env.dev`/`.env.prod`, but `environment: POSTGRES_HOST: db` overrides it). In CI, it would also be `localhost`. The inconsistency between `.env.test` (explicit `POSTGRES_HOST=db`) and `.env.dev`/`.env.prod` (not present) is cosmetic.

**Recommendation:**

Add `POSTGRES_HOST=db` to `.env.dev.example` and `.env.prod.example` for consistency, or remove it from `.env.test`/`.env.test.example` since it's redundantly set in the compose `environment:` section. Effort: **trivial**. Priority: **low** (consistency).

---

### ENV-013 [LOW] `db` service in test compose has unnecessary Django env vars and `.env.test` bind-mount

**File:** `docker-compose.test.yml` lines 11-27

**Evidence:**

```yaml
  db:
    image: postgres:18-alpine
    restart: unless-stopped
    env_file:              # ← unnecessary for a PostgreSQL container
      - .env.test
    volumes:
      - ./.env.test:/app/src/.env:ro   # ← unnecessary mount for PostgreSQL
    environment:
      - DATABASE_URL=postgres://postgres:postgres@db:5432/mko_bazuna
      - DJANGO_SETTINGS_MODULE=config.settings.test   # ← meaningless for PostgreSQL
    ports:
      - "5433:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres -d mko_bazuna"]
```

The `db` (PostgreSQL) service in the test override has:
- `env_file: .env.test` — loads ALL `.env.test` variables into the PostgreSQL container's environment. PostgreSQL only uses `POSTGRES_*` variables. The other variables (`DJANGO_SECRET_KEY`, `BOT_TOKEN`, etc.) are ignored but present in the container's environment and visible via `docker inspect`.
- `./.env.test:/app/src/.env:ro` — bind-mounts `.env.test` at `/app/src/.env` inside the PostgreSQL container. PostgreSQL never accesses this path.
- `DJANGO_SETTINGS_MODULE=config.settings.test` — PostgreSQL doesn't use Django. This var is meaningless in the container.

**Consequence:**

No functional impact — PostgreSQL ignores unknown env vars. But:
1. The `env_file` directive loads sensitive variables (`DJANGO_SECRET_KEY=test-secret-key-for-testing-only`) into a PostgreSQL container that doesn't need them. If the container is inspected, these would be visible.
2. The `.env.test` bind-mount creates a file (`/app/src/.env`) in the PostgreSQL container that serves no purpose.
3. `DJANGO_SETTINGS_MODULE` in a PostgreSQL container's environment is misleading — it suggests the database service uses Django settings.

**Recommendation:**

Remove `env_file`, the `./.env.test:/app/src/.env:ro` volume mount, and `DJANGO_SETTINGS_MODULE` from the test `db` service. Keep only `POSTGRES_*` env vars (from the base compose) and the `DATABASE_URL` override if needed by `wait_for_db` logic. Note: `wait_for_db` in `entrypoint.sh` checks `DATABASE_URL`, but the `db` service doesn't use `entrypoint.sh` (it uses the default PostgreSQL entrypoint).

Effort: **trivial**. Priority: **recommended** (clarity/security — don't expose .env contents in containers that don't need them).

**Not a problem:** The `db` service works correctly — PostgreSQL ignores unknown env vars, the `postgres_data` volume is preserved (merged from base compose), and the healthcheck (`pg_isready`) validates the connection.

---

## 3. Summary Table

| ID | Severity | Title | Key Files |
|----|----------|-------|-----------|
| ENV-001 | CRITICAL | `.dockerignore` `.env*` doesn't exclude `src/.env` | `.dockerignore:5`, `docker/Dockerfile:57,117` |
| ENV-002 | CRITICAL | Test compose doesn't override `bot`/`web`/`load_cities`/`load_catalog`/`seed` — they use `.env.dev` + `config.settings.prod` | `docker-compose.yml`, `docker-compose.test.yml` |
| ENV-003 | HIGH | `migrate`/`create_admin` in test still mount `.env.dev` at `/app/src/.env` | `docker-compose.yml:113-115`, `docker-compose.test.yml:30-34` |
| ENV-004 | HIGH | `env_file` invisible in `docker compose config` output — root cause of undetected misconfigurations | Docker Compose v5 behavior |
| ENV-005 | HIGH | `.env.test` missing 6 variables present in other tiers | `.env.test:35 lines`, `.env.test.example:35 lines` |
| ENV-006 | HIGH | Bash Makefile uses shell vars (`$${POSTGRES_USER}`, `${ADMIN_PASSWORD}`) not sourced from `.env.dev` | `Makefile:9,187-191,219-220,229-235,248-249` |
| ENV-007 | MEDIUM | Inaccurate comments in `docker-compose.test.yml` about `.env` bind-mount and `volumes:` override | `docker-compose.test.yml:7,56` |
| ENV-008 | MEDIUM | `${VAR:?}` warns instead of failing when `--env-file` omitted | `docker-compose.yml:10-12,41-43,...` |
| ENV-009 | MEDIUM | CI/CD sets different env vars than Docker Compose; divergence undocumented | `.github/workflows/ci.yml` |
| ENV-010 | LOW | Root-level `entrypoint.sh` and `entrypoint-test.sh` are empty stubs (0 bytes) | `entrypoint.sh`, `entrypoint-test.sh` |
| ENV-011 | LOW | `src/.env` empty file not excluded from Docker build context | `src/.env`, `.dockerignore:5`, `.gitignore:145` |
| ENV-012 | LOW | `POSTGRES_HOST` inconsistency across .env files | `.env.test:16`, `.env.dev`, `.env.prod` |
| ENV-013 | LOW | `db` service in test compose has unnecessary Django env vars and `.env.test` bind-mount | `docker-compose.test.yml:11-27` |

---

## 4. Not-a-Problems (verified OK)

### 4.1 `docker compose config --env-file .env.test` succeeds with no warnings

```bash
$ docker compose --env-file .env.test -f docker-compose.yml -f docker-compose.test.yml config --quiet
EXIT_CODE: True  (success, no output)
```

All `${VAR:?}` interpolations resolve correctly when `.env.test` is passed. No missing-variable errors.

### 4.2 `DATABASE_URL` handling is correct for Docker Compose

- `.env.example` explicitly says "DO NOT set DATABASE_URL in Docker environments" (line 29)
- `base.py` line 181 checks `os.getenv("DATABASE_URL")` first → uses `env.db()` to parse it
- docker-compose.yml constructs `DATABASE_URL` via `environment: DATABASE_URL=postgres://${POSTGRES_USER}:${POSTGRES_PASSWORD}@db:5432/${POSTGRES_DB}`
- The individual `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD` env vars are ALSO set in the `environment:` section
- In Docker Compose (test mode), `DATABASE_URL` is always set (from environment interpolation), so the `else` fallback (individual POSTGRES_* vars) is never used at runtime
- In CI, `DATABASE_URL` is set directly as a GitHub Actions env var, so the `else` fallback is also never used
- This is consistent and correct.

### 4.3 `base.py` `.env` loading skip in test mode is correct

- `base.py` line 52: `if "test" not in os.getenv("DJANGO_SETTINGS_MODULE", ""):` → skips `read_env()`
- In test mode, `DJANGO_SETTINGS_MODULE=config.settings.test` is set via `environment:` or `env_file`
- All env vars come from `os.environ` (set by Docker Compose's `env_file` and `environment` directives)
- `read_env()` is skipped to prevent the bind-mounted `.env` file from masking test cases that intentionally unset env vars (per the comment on lines 47-51)
- The `.env` file IS bind-mounted (as `.env.test`) but is never read by Django in test mode

### 4.4 `.env.test` variables satisfy all `${VAR:?}` interpolations

All variables referenced with `${VAR:?}` in docker-compose.yml are present in `.env.test`:
- `POSTGRES_DB` = `mko_bazuna` ✓
- `POSTGRES_USER` = `postgres` ✓
- `POSTGRES_PASSWORD` = `postgres` ✓
- `DJANGO_SECRET_KEY` = `test-secret-key-for-testing-only` ✓

### 4.5 `Makefile.ps1` (PowerShell) correctly handles env vars

`Makefile.ps1` lines 18-33 load `.env.dev` into the PowerShell session environment, making `POSTGRES_USER`, `POSTGRES_DB`, `ADMIN_PASSWORD`, etc. available to the shell. The `Invoke-Backup` and `Invoke-Restore` functions explicitly validate these are set (lines 239-245, 270-276). This is the correct approach — the bash Makefile should follow the same pattern (see ENV-006).

### 4.6 `src/.env` is properly gitignored

`git check-ignore -v src/.env` → `.gitignore:145:.env — src/.env` — confirmed ignored. The file exists locally (empty) but is not tracked by git. A fresh clone will not have this file.

### 4.7 `.dockerignore` correctly excludes root-level `.env*` files

The `.env*` pattern on line 5 of `.dockerignore` correctly excludes `.env.dev`, `.env.prod`, `.env.test`, `.env.dev.example`, `.env.prod.example`, `.env.test.example` (all gitignored or template files) from the Docker build context. The empirical build test confirmed these are NOT present in the built image.

---

## 5. Cross-Reference: What Specifically Goes Wrong for Agents

This section directly answers the audit question: **"What specifically goes wrong for agents when .env files are missing variables, misnamed, or don't load at the right time?"**

### Scenario 1: Agent runs `docker compose --env-file .env.test -f docker-compose.yml -f docker-compose.test.yml up -d`

**What happens:**
- `web` and `bot` services start with `config.settings.prod` (not test)
- `DJANGO_SECRET_KEY` = the real dev secret key from `.env.dev` (via `env_file`), NOT the test key
- `BOT_TOKEN` = placeholder `<your-bot-token-from-botfather>` (from `.env.dev` env_file, not overridden in web/bot's environment section)
- `DATABASE_URL` = `postgres://postgres:postgres@db:5432/mko_bazuna` (test DB, interpolated from .env.test)
- `prod.py` guards pass because placeholders are non-empty strings
- Bot fails at runtime: invalid BOT_TOKEN cannot authenticate with Telegram
- Web app runs but uses dev secret key for session signing — sessions may be forgeable

**Agent gets:** `web` container runs (exit code 0 from healthcheck), `bot` container may crash-loop (Telegram API auth failure), but the `test` service is NOT started (behind profile).

### Scenario 2: Agent runs `make test` on a Windows machine with PowerShell

**What happens:**
- `Makefile.ps1` is invoked (not `Makefile`)
- `Makefile.ps1` loads `.env.dev` into the PowerShell environment (lines 18-33)
- `docker compose --env-file .env.test -f docker-compose.yml -f docker-compose.test.yml up -d db` — starts PostgreSQL on port 5433
- `docker compose --env-file .env.test ... run --rm --env "PYTEST_SKIP_MARKERS=seed" test` — starts the test container
- Everything works correctly

**Agent gets:** Tests run successfully (assuming .env.dev and .env.test are properly configured)

### Scenario 3: Agent runs `make test` on Linux/macOS with bash Makefile

**What happens:**
- `Makefile` is used
- `COMPOSE_TEST := --env-file .env.test -f docker-compose.yml -f docker-compose.test.yml`
- `docker compose $(COMPOSE_TEST) up -d db` — starts PostgreSQL on port 5433
- `docker compose $(COMPOSE_TEST) run --rm --env PYTEST_SKIP_MARKERS=seed test` — starts the test container
- The `test` service uses `env_file: .env.test` and `environment: DJANGO_SETTINGS_MODULE=config.settings.test` — correct
- Tests run successfully

**Agent gets:** Tests run correctly (the `test` service is properly configured by docker-compose.test.yml)

### Scenario 4: Agent runs `make db-shell` (bash Makefile) on Linux/macOS

**What happens:**
- Shell variable `POSTGRES_USER` is NOT set (Makefile doesn't source .env.dev)
- `docker compose $(COMPOSE_FILES) exec db psql -U "" -d ""` runs
- psql uses the default OS user and database

**Agent gets:** `psql: error: connection to the server at "localhost" (127.0.0.1), port 5432: FATAL: role "" does not exist` or connects to the wrong database. The `$${POSTGRES_USER}` shell variable is empty because `--env-file .env.dev` only loads vars for Docker Compose, not the host shell.

### Scenario 5: Agent runs `make create-admin` (bash Makefile) without exporting ADMIN_PASSWORD

**What happens:**
- Shell variable `ADMIN_PASSWORD` is NOT set
- `docker compose $(COMPOSE_FILES) run --rm web uv run python ... --password "" --telegram-id "-1"` runs
- The `create_admin_user` command receives an empty password

**Agent gets:** Either a successful admin creation with an empty password (security risk) or a validation error: `Error: --password cannot be empty` (depending on the command's validation logic)

### Scenario 6: Agent runs `docker compose --env-file .env.test -f docker-compose.yml -f docker-compose.test.yml config` and inspects the output

**What happens:**
- Docker Compose v5 resolves `env_file` directives into the `environment` section
- The `env_file` key does NOT appear in the output
- The agent sees all env vars in the `environment` section but cannot tell which came from `env_file: .env.dev` vs. `env_file: .env.test` vs. `environment:` interpolation

**Agent gets confused:** The agent sees `DJANGO_SECRET_KEY: *wndq(...)` for `bot` and might assume it's the test key, but it's actually the real dev secret key from `.env.dev`. The agent cannot distinguish the source without knowing the internal resolution order (environment > env_file).

### Scenario 7: Agent forgets `--env-file .env.test` and runs `docker compose -f docker-compose.yml -f docker-compose.test.yml up -d`

**What happens:**
- Docker Compose looks for `.env` in the current directory — not found (gitignored)
- All `${VAR:?msg}` variables default to blank (with warnings)
- `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` are blank
- `DJANGO_SECRET_KEY` is blank
- PostgreSQL container fails to start (blank password rejected)

**Agent gets:** Warnings about unset variables, PostgreSQL container crash-looping, and then Django services failing with `ImproperlyConfigured: The SECRET_KEY setting must not be empty`. The error chain is confusing because the root cause (missing `--env-file`) is buried among warnings.

### Scenario 8: Agent builds a Docker image with `src/.env` containing secrets

**What happens:**
- Developer writes `DJANGO_SECRET_KEY=super-secret-key` to `src/.env` for local Django CLI testing
- Runs `docker compose --env-file .env.dev -f docker-compose.yml -f docker-compose.dev.override.yml build`
- `.dockerignore` `.env*` does NOT exclude `src/.env` (only excludes root-level `.env*`)
- `COPY . .` (Dockerfile line 57) copies `src/.env` with the secret into the builder image
- `COPY --from=builder ... /app/src` (line 117) propagates it to the runtime image

**Agent gets:** The secret key is baked into the Docker image. The image can be inspected with `docker run --rm image cat /app/src/.env` to extract the key. The bind-mount at runtime overrides it, but the image is permanently compromised.
