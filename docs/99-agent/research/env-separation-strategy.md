# Docker Compose Environment Separation Strategy — Research & Recommendations

> **Project:** Mko Bazuna (Django 5.2 + PostgreSQL 18 + Redis 7, HTMX MPA + aiogram bot)  
> **Date:** 2026-09-16  
> **Methodology:** Findings derived from official Docker documentation ([docs.docker.com](https://docs.docker.com)), the 12-Factor App methodology ([12factor.net](https://12factor.net)), django-environ official docs ([readthedocs.io](https://django-environ.readthedocs.io)), Django deployment checklist ([docs.djangoproject.com](https://docs.djangoproject.com)), cookiecutter-django reference patterns, and direct source-code inspection of this project. Each claim is tagged with a confidence level (HIGH/MEDIUM/LOW).  
> **Companion docs:** `docs/99-agent/research/docker-compose-env-best-practices.md` (mechanism deep-dive), `docs/99-agent/env-files-audit-findings.md` (audit findings), `docs/99-agent/env-audit-findings.md` (security findings).

---

## Executive Summary

This project already uses **separate `.env` files per environment** (`.env.dev`, `.env.prod`, `.env.test`) and a **base + override Compose pattern** (`docker-compose.yml` + `docker-compose.dev.override.yml` / `.prod.yml` / `.test.yml`). The architecture is fundamentally sound but has **three systemic issues**:

1. **`--env-file` and `env_file:` are conflated** — the base `docker-compose.yml` hardcodes `env_file: .env.dev` in every service, which is then manually overridden to `.env.prod` / `.env.test` in each override file. This causes the [ENV-002] finding where 5 services in the test compose inherit `.env.dev` + `config.settings.prod` because they're missing from the override.
2. **`.env` files are bind-mounted into containers** as `/app/src/.env` (django-environ reads from there), but `.dockerignore` does not exclude `src/.env` — [ENV-001] finds a defense-in-depth gap where secrets placed in `src/.env` would be baked into images.
3. **Makefiles diverge** — the bash `Makefile` does not source `.env.dev` for shell-level variable expansion ([ENV-006]), while `Makefile.ps1` does.

The recommendations below address each of the 7 research questions with evidence-backed best practices and concrete before/after code for this project.

---

## 1. Environment File Strategy

### Question

Should you use separate `.env` files per environment (`.env.dev`, `.env.prod`, `.env.test`) or a single `.env` with conditionals?

### Findings

**12-Factor App (III. Config)** — [12factor.net/config](https://12factor.net/config) (confidence: HIGH):

> "The twelve-factor app stores config in environment variables... Env vars are easy to change between deploys without changing any code... unlike config files, there is little chance of them being checked into the code repo accidentally... they are a language- and OS-agnostic standard."

Key elaboration from the updated manifest ([github/twelve-factor](https://github.com/twelve-factor/twelve-factor/blob/next/content/config.md)):

> "Env vars are granular controls, never grouped together as 'environments,' but instead are independently managed for each deploy."

**Docker official docs** — [docs.docker.com/compose/how-tos/environment-variables](https://docs.docker.com/compose/how-tos/environment-variables) (confidence: HIGH):

> "You can use different `.env` files for different environments. The `--env-file` flag lets you specify which to use... This method is useful if you want to temporarily override an `.env` file that is already referenced in your `compose.yaml` file. For example you may have different `.env` files for production (`.env.prod`) and testing (`.env.test`)."

**Docker — Environment Variables Best Practices** ([docker.recipes](https://docker.recipes/docs/environment-variables)):

> "Use `.env` for interpolation + non-secrets; use Docker Compose `secrets` for anything sensitive."

### Decision: Separate `.env` files per environment

**Recommended approach:** ``.env.dev`` / ``.env.prod`` / ``.env.test`` + ``.env.example`` as the template. This is what the project already does — **keep this pattern.**

This aligns with:
- **12-Factor principle:** Config varies across deploys; env vars are managed independently. While 12-factor cautions against "grouping as environments," using separate files per environment is the practical Docker implementation of granular control — each deploy (dev, test, prod) gets its own file with only the variables it needs.
- **Docker `--env-file` design:** The CLI flag is specifically built for selecting alternate `.env` files per environment.
- **Cookiecutter-Django** (the de facto Django+Docker reference): uses `.envs/.local/.django`, `.envs/.production/.django`, `.envs/.production/.postgres` — separate files per environment and service, with a top-level `.env` only for build-time interpolation needs.

**What NOT to do:** A single `.env` with `if ENV=prod then...else...` conditionals inside `docker-compose.yml`. Docker Compose's `${VAR:-default}` and `${VAR:?error}` syntax provides per-variable defaults, but does not (and should not) branch on environment. Environment selection should happen at the **command line** via `--env-file`, not inside the YAML.

### Concrete recommendation for this project

**Current state (before):**
```
.env.example          # Comprehensive template (all tiers)
.env.dev              # Real dev values (gitignored)
.env.dev.example      # Dev-specific template
.env.prod             # Placeholder prod values (gitignored)
.env.prod.example     # Prod-specific template
.env.test             # Test-only values (gitignored)
.env.test.example     # Test-specific template
src/.env              # Empty placeholder (bind-mounted target for django-environ)
```

**Recommended state (after):**
Consolidate to a **single `.env.example` template** that includes all variables with tier-specific comments. Remove the per-tier `.env.*.example` files to eliminate duplication drift (see §2 for details). Keep `.env.dev`, `.env.prod`, `.env.test` as runtime files (gitignored).

**Rationale:** The Docker `--env-file` mechanism handles interpolation; the application reads config via django-environ from `os.environ` (injected by `env_file:`). Separate runtime `.env` files are necessary; separate template files are not.

---

## 2. Single Source of Truth for Env Vars

### Question

How to avoid duplicating variable definitions across `.env` files? Should `.env.example` be the single template, or should each tier have its own example?

### Findings

**django-environ docs** — [django-environ.readthedocs.io](https://django-environ.readthedocs.io/en/latest/quickstart.html) (confidence: HIGH):

> "The `.env` file should be specific to the environment and not checked into version control, it is best practice documenting the `.env` file with an example... A good `.env.dist` could look like this."

**Docker best practices** ([docker.recipes](https://docker.recipes/docs/environment-variables)):

> "Always Include `.env.example` — Never commit `.env` to version control (it contains secrets). Instead, provide a `.env.example` template that documents all required variables."

**Cookiecutter-Django** uses `.envs/.local/.django` + `.envs/.production/.django` — separate files, but each generated from a code template, not hand-maintained.

### Decision: Single `.env.example` template

**Recommended approach:** A single `.env.example` file in the project root serves as the canonical schema definition. All variables are documented with:
- A description comment
- The expected type/format
- Tier-specific guidance (dev/test/prod values)
- `${VAR:-default}` or `${VAR:?required}` patterns where applicable

**Why not separate per-tier examples?** The project currently has `.env.dev.example`, `.env.prod.example`, `.env.test.example`, and `.env.example` — four templates that must be kept in sync. Audit finding [ENV-005] found that `.env.test` and `.env.test.example` are missing 6 variables (`GOOGLE_TRANSLATE_API_KEY`, `SITE_URL`, `IMMEDIATE_ALERTS_ENABLED`, `TLS_CERT_PATH`, `PLAUSIBLE_HOST`, `FIX_PERMISSIONS`) that exist in the other tiers — exactly the kind of drift a single template prevents.

### Concrete recommendation for this project

**Before (multiple templates, drifted):**

```
.env.example           # 20 vars (missing REGISTRY/REPOSITORY/IMAGE_TAG)
.env.dev.example       # 20 vars (same missing set, different placeholders)
.env.prod.example      # 23 vars (has REGISTRY/REPOSITORY/IMAGE_TAG)
.env.test.example      # 17 vars (missing 6 vars — [ENV-005])
```

**After (single template):**

```dotenv
# .env.example — Single schema template for all environments
#
# Copy to create your runtime file:
#   cp .env.example .env.dev     # development
#   cp .env.example .env.prod    # production
#   cp .env.example .env.test    # testing
#
# Tier-specific guidance is inline. Variables absent in a tier use base.py defaults.

# === Django ===
# Generate: python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
# Single-quote values containing $ to prevent shell interpolation: DJANGO_SECRET_KEY='my$key'
DJANGO_SECRET_KEY=<required-for-all-tiers>

# Dev: True (overridden by compose.dev.override.yml)
# Prod: must be False (hardcoded in prod.py)
# Test: True (hardcoded in test.py)
DEBUG=False

# Dev:  localhost,127.0.0.1,0.0.0.0
# Prod:  your-domain.com,www.your-domain.com
# Test:  localhost,127.0.0.1
ALLOWED_HOSTS=localhost,127.0.0.1,0.0.0.0

# === Database ===
# Compose constructs DATABASE_URL from POSTGRES_*. Do NOT set DATABASE_URL here.
POSTGRES_USER=bazuna_user
POSTGRES_DB=bazuna_db
POSTGRES_PASSWORD=<required-for-all-tiers>

# === Redis ===
# Docker: redis://redis:6379/0 (service name)
# Empty string: use LocMemCache (dev/test override CACHES)
REDIS_URL=redis://redis:6379/0

# === Telegram Bot ===
BOT_USERNAME=<your-bot-username>
# Required in production; placeholder accepted in dev/test
BOT_TOKEN=<your-bot-token-from-botfather>

# === Google Cloud Translation (production only) ===
# Required in production (prod.py guard). Empty in dev/test → no-op.
GOOGLE_TRANSLATE_API_KEY=

# === Public site ===
# Prod: REQUIRED (prod.py guard). Dev/test: defaults to http://localhost:8000
SITE_URL=http://localhost:8000

# === Analytics (optional) ===
IMMEDIATE_ALERTS_ENABLED=false
PLAUSIBLE_HOST=

# === Admin ===
ADMIN_USERNAME=admin
ADMIN_PASSWORD=<your-admin-password>
ADMIN_TELEGRAM_ID=-1

# === TLS Certificates (production nginx) ===
TLS_CERT_PATH=/etc/nginx/certs

# === Container image (production only) ===
# Used by docker-compose.prod.yml for image pull from registry
REGISTRY=ghcr.io
REPOSITORY=manicko/mko_bazuna
IMAGE_TAG=latest

# === Container runtime ===
# 1 = fix volume permissions (Windows/WSL2 bind mounts)
FIX_PERMISSIONS=0
# 1 = skip entrypoint.sh .env existence check (test mode)
SKIP_ENV_CHECK=
```

**Verification approach:** Add a test that validates all `.env.*` files against the template key set (every key in `.env.example` must be present in `.env.dev`, `.env.prod`, `.env.test`). See `src/backend/config/settings/tests/test_settings_secrets.py` for the existing test infrastructure that could host this check.

---

## 3. Docker Compose Base + Override Pattern

### Question

How should the base file reference env files? Should the base use `env_file: .env` (generic) and let overrides change it? Or should each service not specify `env_file` at all and rely entirely on `--env-file` CLI flag + Docker's default `.env`?

### Findings

**Docker — Merge Compose files** ([docs.docker.com/compose/how-tos/multiple-compose-files/merge](https://docs.docker.com/compose/how-tos/multiple-compose-files/merge)) (confidence: HIGH):

> "When merging Compose files, all relative paths (for build contexts, environment files, bind-mounted volumes, and other resources) are resolved relative to the base Compose file."

**Docker — `--env-file` does NOT override service `env_file:`** ([docker/compose#12264](https://github.com/docker/compose/issues/12264), verified-as-intended) (confidence: HIGH):

> "The `--env-file` flag used on the `docker compose ...` command has no impact on the [service `env_file`] attribute. ... the `env_file` attribute in the compose file is set to replicate `VALUE` from the local environment."

This is the root cause of a class of bugs (see [ENV-002]): passing `--env-file .env.test` resolves `${VAR}` interpolation but does **not** change which file the service's `env_file:` directive reads.

**Source code verification** (Context7 fetch of `docker/compose`):

- Phase 1 (interpolation): `cli.WithEnvFiles` + `cli.WithDotEnv` load `--env-file`/`.env` content into `project.Environment` — used **only** for `${VAR}` resolution.
- Phase 2 (container env): `WithServicesEnvironmentResolved(true)` reads each service's `env_file:` directive and merges into `service.Environment` → `container.Config.Env`.

**.env vs `env_file:` distinction** — [Docker Docs](https://docs.docker.com/compose/how-tos/environment-variables/set-environment-variables/):

> "The `.env` file is the default method for setting variables... The `.env` file should be placed at the root of the project directory next to your `compose.yaml` file."
>
> "A container's environment can also be set using `.env` files along with the `env_file` attribute."

### Decision: Override `env_file` paths in each environment file; do NOT rely on `--env-file` alone

The project uses `env_file:` (service-level directive) to inject values into containers, and `--env-file` to resolve `${VAR}` interpolation in the Compose YAML. **Both are needed** and they serve different purposes. The correct pattern is:

1. **Base file (`docker-compose.yml`):** Declare `env_file:` paths relative to the base file. Use a **variable-interpolated path** so overrides can change which file is loaded, OR keep a generic path and override it in environment files.
2. **Environment overrides (`docker-compose.dev.override.yml`, etc.):** Override the `env_file:` path AND the bind-mount volume for the application's `.env` reader (django-environ).
3. **CLI `--env-file`:** Used only for `${VAR}` interpolation in Compose YAML (e.g., `DATABASE_URL=postgres://${POSTGRES_USER}@...`).

### Concrete recommendation for this project

**Problem (before):** The base `docker-compose.yml` hardcodes `env_file: .env.dev` in 7 services (lines 49, 76, 103, 129, 157, 184, 211). The prod and test overrides must individually re-declare `env_file: .env.prod` / `.env.test` for each service they override. Because the test override only touches 4 services, the other 5 (`bot`, `web`, `load_cities`, `load_catalog`, `seed`) silently inherit `.env.dev` + `config.settings.prod` — [ENV-002].

**Recommended pattern (after):**

```yaml
# docker-compose.yml (base — production contract)
services:
  web:
    build:
      context: .
      dockerfile: docker/Dockerfile
    command: gunicorn config.wsgi:application
    env_file:
      # Interpolate the env file path from a Compose-level variable.
      # Default to .env.prod (the production contract). Overrides change APP_ENV.
      - "${ENV_FILE:-.env.prod}"
    environment:
      DJANGO_SETTINGS_MODULE: ${DJANGO_SETTINGS_MODULE:-config.settings.prod}
      DATABASE_URL: postgres://${POSTGRES_USER}:${POSTGRES_PASSWORD}@${POSTGRES_HOST:-db:5432}/${POSTGRES_DB}
      # ... other interpolated vars
    volumes:
      # The application's own .env reader (django-environ) reads /app/src/.env
      - "${ENV_FILE:-.env.prod}:/app/src/.env:ro"
    depends_on:
      # ...
```

```yaml
# docker-compose.dev.override.yml
services:
  web:
    env_file:
      - ".env.dev"
    volumes:
      - ".env.dev:/app/src/.env:ro"
      - ".:/app"  # hot-reload bind mount
    environment:
      DJANGO_SETTINGS_MODULE: config.settings.dev
      DEBUG: "True"
    command: >
      sh -c "tailwindcss ... && python src/backend/manage.py runserver 0.0.0.0:8000"
```

```yaml
# docker-compose.prod.yml
services:
  web:
    image: ${REGISTRY:-ghcr.io}/${REPOSITORY:-manicko/mko_bazuna}:${IMAGE_TAG:-latest}
    env_file:
      - ".env.prod"
    volumes:
      - ".env.prod:/app/src/.env:ro"
```

```yaml
# docker-compose.test.yml
services:
  db:
    env_file:
      - ".env.test"
    volumes:
      - ".env.test:/app/src/.env:ro"
    environment:
      DJANGO_SETTINGS_MODULE: config.settings.test
  
  # MUST override EVERY service to prevent .env.dev inheritance
  web: { env_file: [".env.test"], volumes: [".env.test:/app/src/.env:ro"], environment: { DJANGO_SETTINGS_MODULE: config.settings.test } }
  bot: { env_file: [".env.test"], volumes: [".env.test:/app/src/.env:ro"], environment: { DJANGO_SETTINGS_MODULE: config.settings.test } }
  load_cities: { env_file: [".env.test"], volumes: [".env.test:/app/src/.env:ro"], environment: { DJANGO_SETTINGS_MODULE: config.settings.test } }
  load_catalog: { env_file: [".env.test"], volumes: [".env.test:/app/src/.env:ro"], environment: { DJANGO_SETTINGS_MODULE: config.settings.test } }
  migrate: { env_file: [".env.test"], volumes: [".env.test:/app/src/.env:ro"], environment: { DJANGO_SETTINGS_MODULE: config.settings.test } }
  create_admin: { env_file: [".env.test"], volumes: [".env.test:/app/src/.env:ro"], environment: { DJANGO_SETTINGS_MODULE: config.settings.test } }
  seed: { env_file: [".env.test"], volumes: [".env.test:/app/src/.env:ro"], environment: { DJANGO_SETTINGS_MODULE: config.settings.test } }
```

**Alternative (cleaner) approach:** Use the `ENV_FILE` interpolation variable in the base compose, then set it via `--env-file` or `COMPOSE_ENV_FILE` in the Makefile. This eliminates the need for every override to re-declare `env_file:`:

```yaml
# docker-compose.yml — single source of truth for env_file path
env_file:
  - "${ENV_FILE:-.env.prod}"
```

Then:
```makefile
COMPOSE_DEV = ENV_FILE=.env.dev --env-file .env.dev -f docker-compose.yml -f docker-compose.dev.override.yml
COMPOSE_TEST = ENV_FILE=.env.test --env-file .env.test -f docker-compose.yml -f docker-compose.test.yml
COMPOSE_PROD = ENV_FILE=.env.prod --env-file .env.prod -f docker-compose.yml -f docker-compose.prod.yml
```

> **Why this works:** `ENV_FILE=.env.test` is a shell environment variable passed on the `docker compose` command line. Docker Compose reads it during `${ENV_FILE}` interpolation. The `--env-file .env.test` flag separately resolves other `${VAR}` tokens (like `${POSTGRES_USER}`). This cleanly separates "which env file to inject into containers" from "which values to interpolate into the YAML."

**Confidence: HIGH** for the interpolation mechanism (Docker docs, Context7 source). **Caveat (LOW):** interpolation of `${VAR}` *inside* an `env_file:`'s contents does not reliably resolve — but interpolating the *path* (which file to load) always works.

---

## 4. Django-Specific Considerations

### Question

How does Django load `.env` files (django-environ, python-dotenv)? In Docker, should env vars be injected via container `env_file:` or via Docker's `--env-file` interpolation? What about bind-mounting `.env` files as volumes?

### Findings

**django-environ documentation** — [django-environ.readthedocs.io](https://django-environ.readthedocs.io/en/latest/api.html) (confidence: HIGH):

> `environ.Env.read_env(env_file=None, overwrite=False, ...)` — "Read a `.env` file into `os.environ`. Existing environment variables take precedent and are NOT overwritten by the file content."

This is critical: `read_env()` uses `setdefault`-style semantics. Values already in `os.environ` (injected by Docker's `env_file:` or `environment:`) are **not overwritten** by the `.env` file. The file only fills in gaps.

**Django deployment checklist** — [docs.djangoproject.com/en/5.2/howto/deployment/checklist](https://docs.djangoproject.com/en/5.2/howto/deployment/checklist/) (confidence: HIGH):

> "`SECRET_KEY`: The secret key must be a large random value and it must be kept secret... Instead of hardcoding the secret key in your settings module, consider loading it from an environment variable: `SECRET_KEY = os.environ['SECRET_KEY']`"

> "`DATABASES`: Database passwords are very sensitive. You should protect them exactly like `SECRET_KEY`."

**12-Factor:** Environment variables, not config files, for all config.

### Decision: Inject via `env_file:` (container env); bind-mount only for the application's own `.env` reader

There are **two valid approaches**, and the project's current choice (bind-mounting to `/app/src/.env`) is correct but has a subtlety:

| Approach | Mechanism | When to use |
|---|---|---|
| **`env_file:` directive** | Docker Compose reads `.env.dev` → injects vars into container's `os.environ` at startup | Standard approach; Django reads from `os.environ` directly |
| **Bind-mount `.env` as `/app/src/.env`** | File mounted at runtime; django-environ's `read_env()` reads it into `os.environ` | Needed when Django settings explicitly call `read_env()` (which this project does in `base.py` line 53) |

**Important interaction — precedence chain (highest to lowest):**

1. Docker `environment:` with interpolation (`DEBUG=${DEBUG}`) — resolved from shell/`.env`/`--env-file`
2. Docker `environment:` literal (`DEBUG=True`)
3. Docker `env_file:` (file contents injected into container `os.environ`)
4. `read_env()` (bind-mounted `.env` file fills gaps only — does NOT overwrite existing env vars per django-environ docs)
5. Image `ENV` (Dockerfile)

**Evidence from project code:**

`src/backend/config/settings/base.py` lines 29-53:
```python
env_path = BASE_DIR / ".env"  # = src/.env (BASE_DIR is 4 levels up from base.py)
if not env_path.exists():
    # Skip validation during Docker build, in test environments,
    # or when environment variables are provided via docker-compose env_file or CI directly.
    if os.getenv("DJANGO_SETTINGS_MODULE") and "test" not in os.getenv("DJANGO_SETTINGS_MODULE", "") \
       and not os.getenv("DJANGO_BUILD") and not os.getenv("DJANGO_SECRET_KEY"):
        logger.error("ERROR: .env file not found...")
        sys.exit(1)
else:
    if "test" not in os.getenv("DJANGO_SETTINGS_MODULE", ""):
        environ.Env.read_env(env_path)
```

This shows:
1. In Docker (non-test), `src/.env` is bind-mounted (`.env.dev` → `/app/src/.env`) and `read_env()` reads it.
2. In test mode, `read_env()` is **skipped** — all vars come from Docker's `env_file:`/`environment:` injection into `os.environ`. This is documented as intentional: "Skip read_env() to prevent the bind-mounted `.env` file from masking test cases that intentionally unset env vars."
3. In Docker build (`DJANGO_BUILD=1`), `.env` missing is OK — placeholder `ENV` values are used.

### Concrete recommendation for this project

**The current two-channel approach is correct.** Keep both:
- `env_file:` for Docker Compose interpolation + container env injection
- Bind-mount `/app/src/.env` for django-environ's `read_env()` (non-test only)

**What to fix:**

1. **Standardize on `env_file:` as the primary mechanism**, with bind-mount as secondary. The bind-mount of `/app/src/.env` is what makes `read_env()` work in non-test Docker environments. Without it, `base.py` would `sys.exit(1)` because `src/.env` doesn't exist in the image at runtime (it's excluded by `.dockerignore` — see [ENV-001]).

2. **Remove `src/.env` from the image entirely** (fix `.dockerignore` — see §6). The bind-mount ensures it exists at runtime. In the image, `base.py` sees no `.env` file but has `DJANGO_BUILD=1` (build) or `DJANGO_SECRET_KEY` in `os.environ` (runtime via `env_file:`), so the `sys.exit(1)` guard is bypassed.

3. **Document the precedence** at the top of `base.py`:
   ```python
   # Env var resolution order (highest to lowest priority):
   # 1. Docker environment:  (set by env_file / environment / CLI)
   # 2. bind-mounted .env    (read via read_env() — only non-test)
   # 3. Image ENV             (Docker build placeholders)
   # read_env() uses setdefault semantics — does NOT overwrite os.environ.
   ```

---

## 5. Test Environment Strategy

### Question

Should the test compose file fully override ALL services, or only the ones that need to change?

### Findings

**Docker — Merge Compose files** ([docs.docker.com/compose/how-tos/multiple-compose-files/merge](https://docs.docker.com/compose/how-tos/multiple-compose-files/merge)) (confidence: HIGH):

> "Compose copies configurations from the original service over to the local one. If a configuration option is defined in both the original service and the local service, the local value replaces or extends the original value."
>
> For `environment`/`labels`/volumes: "Compose 'merges' entries together with locally defined values taking precedence."

**Docker — Using profiles** ([docs.docker.com/compose/how-tos/profiles](https://docs.docker.com/compose/how-tos/profiles/)) (confidence: HIGH):

> "Services without a `profiles` attribute are always enabled." / "A service is ignored by Compose when none of the listed `profiles` match the active ones."

**Audit finding [ENV-002]** documents the exact failure: `docker-compose.test.yml` overrides only `db`, `migrate`, `create_admin`, and adds `test`. The remaining 5 services (`bot`, `web`, `load_cities`, `load_catalog`, `seed`) inherit from the base compose with `.env.dev` and `config.settings.prod`.

### Decision: Override ALL services that could start in the target environment

The "only override what changes" approach is a **common Compose pitfall** (documented in the `docker-production-patterns` ADR and in [TheLinuxCode article](https://thelinuxcode.com/what-is-docker-compose-override-a-practical-guide-to-layered-compose-files/2026-02-14)):

> "Mistake 1: Treating override as a patch file for everything. ... Mistake 8: Accidentally inheriting dev volumes in non-dev runs."

When you run `docker compose -f docker-compose.yml -f docker-compose.test.yml up -d`, Compose starts ALL non-profiled services. The test override must either:
- **(A)** Override every service to set the correct `env_file`, `DJANGO_SETTINGS_MODULE`, and bind-mount, OR
- **(B)** Assign `profiles` to dev-only services in the base compose so they don't start under the test combination.

**Option B is cleaner** — it moves the gating logic into the base file (production contract) rather than requiring every override to remember to override every service.

### Concrete recommendation for this project

**Before (current — partial override):**

```yaml
# docker-compose.test.yml — only 4 services overridden
services:
  db:      # ✓ overridden
  migrate: # ✓ overridden
  create_admin: # ✓ overridden
  test:   # ✓ added (profile: ["test"])
  # ✗ bot, web, load_cities, load_catalog, seed — NOT overridden → inherit .env.dev + prod settings
```

**After (Option A — comprehensive override):**

```yaml
# docker-compose.test.yml
services:
  # Override ALL services that could start in test mode
  db:
    env_file: [".env.test"]
    volumes: [".env.test:/app/src/.env:ro"]
    environment:
      - DJANGO_SETTINGS_MODULE=config.settings.test

  migrate:
    env_file: [".env.test"]
    volumes: [".env.test:/app/src/.env:ro"]
    environment:
      - DJANGO_SETTINGS_MODULE=config.settings.test

  create_admin:
    env_file: [".env.test"]
    volumes: [".env.test:/app/src/.env:ro"]
    environment:
      - DJANGO_SETTINGS_MODULE=config.settings.test
      - ADMIN_PASSWORD=test-admin-password

  web:
    env_file: [".env.test"]
    volumes: [".env.test:/app/src/.env:ro"]
    environment:
      - DJANGO_SETTINGS_MODULE=config.settings.test

  bot:
    env_file: [".env.test"]
    volumes: [".env.test:/app/src/.env:ro"]
    environment:
      - DJANGO_SETTINGS_MODULE=config.settings.test

  load_cities:
    env_file: [".env.test"]
    volumes: [".env.test:/app/src/.env:ro"]
    environment:
      - DJANGO_SETTINGS_MODULE=config.settings.test

  load_catalog:
    env_file: [".env.test"]
    volumes: [".env.test:/app/src/.env:ro"]
    environment:
      - DJANGO_SETTINGS_MODULE=config.settings.test

  seed:
    profiles: ["test"]  # or !reset [] to auto-run in test
    env_file: [".env.test"]
    volumes: [".env.test:/app/src/.env:ro"]
    environment:
      - DJANGO_SETTINGS_MODULE=config.settings.test

  test:
    profiles: ["test"]
    # ... as before
```

**After (Option B — profiles in base compose, cleaner):**

```yaml
# docker-compose.yml (base) — add profiles to non-core services
services:
  migrate:
    profiles: ["init"]     # one-shot: run with --profile init
  load_cities:
    profiles: ["init"]
  load_catalog:
    profiles: ["init"]
  create_admin:
    profiles: ["init"]
  seed:
    profiles: ["seed"]     # opt-in via --profile seed

  web:
    # no profile — always enabled (core service)
  bot:
    # no profile — always enabled (core service)
  db:
    # no profile — always enabled (core service)
  redis:
    # no profile — always enabled (core service)
  nginx:
    # no profile — always enabled (core service)
```

```yaml
# docker-compose.test.yml — now only needs to override what actually changes
services:
  db:
    env_file: [".env.test"]
    # postgres_data volume preserved from base (merged)
    environment:
      - DATABASE_URL=postgres://postgres:postgres@db:5432/mko_bazuna
    ports: ["5433:5432"]

  test:
    profiles: ["test"]
    # one-shot test runner
```

```makefile
# Makefile — test target with explicit profiles
test:
	docker compose $(COMPOSE_TEST) --profile init up -d
	docker compose $(COMPOSE_TEST) --profile test run --rm test
```

**Recommendation:** Use **Option B (profiles)** as the primary strategy. It scales better because new services added to the base compose are automatically excluded from non-matching environments. Use Option A (comprehensive override) as a **belt-and-suspenders** complement for services that must start in every environment (like `web`/`bot` in dev).

> **Note on `profiles: !reset []`:** The dev override uses `profiles: !reset []` on `seed` to remove the profile gate and make seed auto-run. This works per Docker's merge `!reset` tag (v2.30+). See [compose-spec merge docs](https://docs.docker.com/reference/compose-file/merge/).

---

## 6. The `COPY . .` Docker Build Problem

### Question

How to prevent env files from being baked into images? What `.dockerignore` patterns work?

### Findings

**Docker Builder Reference — `.dockerignore` file** ([docs.docker.com/reference/dockerfile/#dockerignore-file](https://docs.docker.com/reference/dockerfile/#dockerignore-file)) (confidence: HIGH):

> "Before the docker CLI sends the context to the docker daemon, it looks for a file named `.dockerignore` in the root directory of the context. If this file exists, the CLI modifies the context to exclude files and directories that match patterns in it."

> "Beyond Go's filepath.Match rules, Docker also supports a special wildcard string `**` that matches any number of directories (including zero)."

**Docker Build Best Practices** ([docs.docker.com/build/building/best-practices](https://docs.docker.com/build/building/best-practices/)) (confidence: HIGH):

> "Exclude files not relevant to the build... use a `.dockerignore` file."

**Security analysis** — [safeguard.sh](https://safeguard.sh/resources/blog/docker-secrets-management) + [devopsness](https://www.devopsness.com/blog/dockerignore-best-practices) + [techearl](https://techearl.com/dockerignore-best-practices) (confidence: HIGH):

> "A `.dockerignore` that lists `.env`, `*.pem`, and `secrets/` is a real control here, not hygiene theater. It means a careless `COPY . .` can't scoop up a credential that never should have left the developer's machine."

> "If you're already fighting build failures, a lean context also makes them easier to reason about."

**Audit finding [ENV-001]** — empirically verified:

The project's `.dockerignore` line 5 is `.env*`, which correctly excludes root-level `.env.dev`, `.env.prod`, `.env.test`, `.env.example` etc. But `.env*` uses Go's `filepath.Match` where `*` does **not** cross `/` separators, so `src/.env` (relative path `src/.env`) does **NOT** match `.env*`.

**Verification (from [ENV-001] empirical test):**

```
Build context test with:
  .env      (secret_value=leaked)
  .env.dev  (dev secret)
  src/.env  (SECRET=deeply-nested-secret)

.dockerignore has: .env*

Result:
  .env      — EXCLUDED ✓
  .env.dev  — EXCLUDED ✓  
  src/.env  — PRESENT IN IMAGE ✗ (path "src/.env" does not match pattern ".env*")
```

### Decision: Use `**/.env*` (or explicit `src/.env`) in `.dockerignore`

The pattern `.env*` only matches at the build context root. To exclude `.env` files in **all** subdirectories, use `**/.env*` (the `**` matches any number of path segments including zero).

Per the Docker source code and docs:
- `.env*` → matches `.env`, `.env.dev` at root **only**
- `**/.env*` → matches `.env`, `.env.dev` at root **and** `src/.env`, `src/.env.dev` at any depth
- `**/src/.env` → matches only `src/.env` specifically

### Concrete recommendation for this project

**Before (current `.dockerignore` line 5):**
```
.env*
```

**After:**
```dockerignore
# Environment files — NEVER bake into images
# .env* matches root-level only; **/.env* catches src/.env and any subdirectory
.env*
**/.env
**/.env*
!/.env.example        # allow the template (if at root)
```

Additionally, the project should verify this with a CI check:
```makefile
# Add to Makefile as a verification target
verify-dockerignore:
	@docker build --target builder -t envcheck --no-cache . && \
	docker run --rm envcheck ls /app/src/.env 2>/dev/null && \
	echo "ERROR: .env leaked into image" && exit 1 || \
	echo "OK: no .env files in image"
```

> **Alternative approach:** Instead of bind-mounting a `.env` file into the container, inject all variables via `env_file:` (container env injection). This eliminates the need for `src/.env` to exist at runtime. However, the project's `base.py` explicitly calls `read_env()` for non-Docker local development (where `env_file:` is not available), so the bind-mount pattern is needed for the Docker case unless `base.py` is refactored to skip `read_env()` entirely in Docker (relying solely on `env_file:` injection).

---

## 7. Makefile Integration

### Question

How to correctly pass `--env-file` in Makefiles so shell variables are available for expansion?

### Findings

**Makefile semantics:** Make recipes are executed by `/bin/sh`. In Make:
- `$(VAR)` → Make variable expansion (performed by Make itself)
- `$$VAR` → escaped to `$VAR`, performed by the shell at runtime
- `$${VAR}` → becomes `${VAR}` in the shell (parameter expansion, including `:-default` syntax)

**Key insight:** `--env-file .env.dev` passed to `docker compose` makes variables available to **Docker Compose's interpolation engine**, NOT to the **host shell** that runs the Makefile recipe. If a recipe uses `$${POSTGRES_USER}` for shell-level purposes (e.g., passing to `psql -U`), the shell variable must be set in the shell environment — `--env-file` does not do this.

**Audit finding [ENV-006]** documents this precisely:

> `Makefile` line 9: `ENV_FILE := --env-file .env.dev`
>
> `db-shell` target (line 220): `docker compose $(COMPOSE_FILES) exec db psql -U $${POSTGRES_USER} -d $${POSTGRES_DB}`
>
> `--env-file .env.dev` only makes variables available to Docker Compose for compose-file `${VAR}` interpolation. It does **NOT** export variables to the host shell's environment.

Contrast with `Makefile.ps1` (lines 18-33), which explicitly reads `.env.dev` and sets environment variables in the PowerShell session before using `$env:POSTGRES_USER`.

**Docker — Environment Variables Best Practices** ([docker.recipes](https://docker.recipes/docs/environment-variables)):

> "Validate required variables fail fast" — use `${VAR:?error}` to catch missing variables early.

**12-Factor:** "Env vars are easy to change between deploys without changing any code."

### Decision: Source the appropriate `.env` file before shell-level variable expansion

Two patterns are available:

| Pattern | Mechanism | When to use |
|---|---|---|
| **Shell `set -a; . .env; set +a`** | Sources the `.env` file into the shell environment | When Makefile recipes use `$${VAR}` for host-level commands (`psql`, `pg_dump`, etc.) |
| **`--env-file .env.dev`** | Passes the file to Docker Compose for YAML interpolation | When only Docker Compose interpolation is needed (no host shell expansion) |

The project's Makefile uses **both**: `--env-file .env.dev` (via `$(COMPOSE_FILES)`) for Docker Compose interpolation, AND `$${POSTGRES_USER}` (shell expansion) for host-level `psql` commands. The second pattern is broken because `.env.dev` is not sourced into the shell.

### Concrete recommendation for this project

**Before (bash `Makefile`):**

```makefile
ENV_FILE := --env-file .env.dev
COMPOSE_FILES := $(ENV_FILE) -f docker-compose.yml -f docker-compose.dev.override.yml
COMPOSE_TEST := --env-file .env.test -f docker-compose.yml -f docker-compose.test.yml

db-shell:
	docker compose $(COMPOSE_FILES) exec db psql -U $${POSTGRES_USER} -d $${POSTGRES_DB}

backup:
	@TIMESTAMP=$$(date +%Y%m%d_%H%M%S) && \
		docker compose $(ENV_FILE) -f docker-compose.yml exec -T db \
			pg_dump -U $${POSTGRES_USER} -d $${POSTGRES_DB} -F c \
			> $(BACKUPS_DIR)/dump_$${TIMESTAMP}.dump
```

When the user runs `make db-shell` without manually exporting `POSTGRES_USER`:
- `$${POSTGRES_USER}` → empty string → `psql -U "" -d ""` → connects to wrong DB or fails.

**After (bash `Makefile` with sourced env):**

```makefile
ENV_FILE := --env-file .env.dev
COMPOSE_FILES := $(ENV_FILE) -f docker-compose.yml -f docker-compose.dev.override.yml
COMPOSE_TEST := --env-file .env.test -f docker-compose.yml -f docker-compose.test.yml

# Source .env files into the shell environment so $${VAR} expansions work
# for host-level commands (psql, pg_dump, etc.). This mirrors Makefile.ps1's
# approach (lines 18-33) which reads .env.dev into the PowerShell session.
# Uses `set -a` to auto-export all variables, `. ./.env.<tier>` to source,
# and `set +a` to disable auto-export. Falls back to empty config if the file
# doesn't exist (e.g., in CI where env vars are set directly).
define SHELL_EXPORT
	@set -a; [ -f .env.dev ] && . .env.dev; set +a
endef

define SHELL_EXPORT_TEST
	@set -a; [ -f .env.test ] && . .env.test; set +a
endef

db-shell:
	$(SHELL_EXPORT)
	docker compose $(COMPOSE_FILES) exec db psql -U "$${POSTGRES_USER}" -d "$${POSTGRES_DB}"

backup:
	$(SHELL_EXPORT)
	@mkdir -p $(BACKUPS_DIR)
	@TIMESTAMP=$$(date +%Y%m%d_%H%M%S) && \
		docker compose $(ENV_FILE) -f docker-compose.yml exec -T db \
			pg_dump -U "$${POSTGRES_USER}" -d "$${POSTGRES_DB}" -F c \
			> $(BACKUPS_DIR)/dump_$${TIMESTAMP}.dump && \
		echo "✓ Backup created: $(BACKUPS_DIR)/dump_$${TIMESTAMP}.dump"

restore:
	$(SHELL_EXPORT)
	@if [ -z "$(BACKUP_FILE)" ]; then \
		echo "Error: BACKUP_FILE not specified"; \
		exit 1; \
	fi
	docker compose $(ENV_FILE) -f docker-compose.yml exec -T db \
		pg_restore -U "$${POSTGRES_USER}" -d "$${POSTGRES_DB}" --clean --if-exists $(BACKUP_FILE)

create-admin:
	$(SHELL_EXPORT)
	docker compose $(COMPOSE_FILES) run --rm web uv run python src/backend/manage.py create_admin_user \
		--username "$${ADMIN_USERNAME:-admin}" \
		--password "$${ADMIN_PASSWORD}" \
		--telegram-id "$${ADMIN_TELEGRAM_ID:--1}"
```

**Key changes explained:**

1. **`$(SHELL_EXPORT)` macro** — Sources `.env.dev` into the shell before each recipe that uses `$${VAR}`. This makes `POSTGRES_USER`, `POSTGRES_DB`, `ADMIN_PASSWORD`, etc. available to the shell for host-level commands. The `[ -f .env.dev ] &&` guard prevents failure if the file doesn't exist (CI path).

2. **`$$` escaping** — Changed `$${VAR}` to `"$${VAR}"` (quoted) to handle values with spaces. Changed `${VAR:-default}` (Make expansion) to `"$${VAR:-default}"` (shell expansion) since the default syntax is shell-specific.

3. **`--env-file` retained** — Still passed to `docker compose` for YAML interpolation (`${POSTGRES_DB:?}` in `docker-compose.yml`). The shell sourcing and the `--env-file` are complementary: shell sourcing for host-level commands, `--env-file` for Compose interpolation.

> **Confidence: HIGH** for the mechanism. **`set -a; . file; set +a`** is the POSIX-standard way to source a dotenv file into the shell environment. `Makefiles` do not automatically source `.env` files — this must be done explicitly. The `Makefile.ps1` already does the equivalent (PowerShell `Get-Content` + `Set-Item -Path "env:$name"`).

---

## Cross-Reference: Project-Specific Issues Addressed

| Audit ID | Issue | Section that addresses it |
|---|---|---|
| [ENV-001] | `.dockerignore` `.env*` doesn't exclude `src/.env` | §6 |
| [ENV-002] | Test compose doesn't override bot/web/load_cities/load_catalog/seed | §5 |
| [ENV-003] | migrate/create_admin in test mount `.env.dev` at `/app/src/.env` | §5 |
| [ENV-004] | `env_file` invisible in `docker compose config` | §3, §4 |
| [ENV-005] | `.env.test` missing 6 variables | §2 |
| [ENV-006] | Bash Makefile uses shell vars not sourced from `.env.dev` | §7 |
| [ENV-008] | `${VAR:?}` warns instead of failing when `--env-file` omitted | §3, §7 |
| [ENV-009] | CI vs Compose env var divergence | §4, §7 |
| [ENV-013] | Test `db` service has unnecessary Django env vars | §5 |

---

## Sources

1. **Docker — Environment variables precedence in Docker Compose.** Official precedence table, two-`.env`-file behavior, `:?`/`:-` interpolation syntax. <https://docs.docker.com/compose/how-tos/environment-variables/envvars-precedence> (verified via direct fetch, Sept 2026).
2. **Docker — Variable interpolation.** Interpolation sources, `.env` file syntax rules (single-quote = literal, double-quote = interpolation), `--env-file` behavior and path resolution. <https://docs.docker.com/compose/how-tos/environment-variables/variable-interpolation> (verified via direct fetch).
3. **Docker — Set environment variables within your container's environment.** `environment:` vs `env_file:` attributes, `required` field (v2.24+), `format: raw` (v2.30+), env-file syntax parsing rules. <https://docs.docker.com/compose/how-tos/environment-variables/set-environment-variables> (verified via direct fetch).
4. **Docker — Best practices for environment variables.** `.env.example` template, secrets via Docker secrets, validation with `${VAR:?}`. <https://docs.docker.com/compose/how-tos/environment-variables/best-practices> (verified via direct fetch).
5. **Docker — Merge Compose files.** Base + override merge rules: scalars replaced, maps merged, sequences concatenated. `!reset` and `!override` tags. <https://docs.docker.com/compose/how-tos/multiple-compose-files/merge> (verified via direct fetch).
6. **Docker — Using profiles with Compose.** `profiles` attribute for conditional service inclusion. <https://docs.docker.com/compose/how-tos/profiles/> (verified via direct fetch).
7. **Docker — `.dockerignore` file.** Pattern matching, `**` wildcard, Go `filepath.Match` semantics. <https://docs.docker.com/reference/dockerfile/#dockerignore-file> (verified via direct fetch).
8. **Docker — Build best practices.** Use `.dockerignore`, narrow `COPY` for cache efficiency. <https://docs.docker.com/build/building/best-practices> (verified via direct fetch).
9. **Docker — Dockerfile reference.** `.dockerignore` section, `COPY` instruction, `ENV` persistence. <https://docs.docker.com/reference/dockerfile/> (verified via direct fetch).
10. **Compose Specification — `spec.md`.** Authoritative definition of `env_file` (`path`, `required`, `format`), env-file syntax, secrets element. <https://github.com/compose-spec/compose-spec/blob/main/spec.md> (verified via Context7).
11. **Compose Specification — `09-secrets.md`.** Secrets top-level element with `file`/`environment`/`external`/`name`. <https://github.com/compose-spec/compose-spec/blob/main/09-secrets.md> (verified via Context7).
12. **Docker Compose source — `cmd/compose/compose.go`.** Two-phase loading: `cli.WithEnvFiles`/`cli.WithDotEnv` into `project.Environment` (interpolation only), `WithOsEnv` (shell wins), `COMPOSE_FILE` resolution. <https://github.com/docker/compose/blob/main/cmd/compose/compose.go> (verified via Context7).
13. **Docker Compose source — `pkg/compose/create.go`.** `env_file` content merged into `service.Environment` → `container.Config.Env` (proving `env_file:` IS injected into container). <https://github.com/docker/compose/blob/main/pkg/compose/create.go> (verified via Context7).
14. **Docker Compose source — `cmd/compose/config.go`.** Sequences (ports, expose) are appended on merge, not replaced. <https://github.com/docker/compose/blob/main/cmd/compose/config.go> (verified via Context7).
15. **docker/compose#12264.** `--env-file` does not override service `env_file:` values (working-as-intended). <https://github.com/docker/compose/issues/12264> (verified via web search).
16. **12-Factor App — Config.** Store config in environment variables; config varies across deploys, code does not. <https://12factor.net/config> (verified via direct fetch).
17. **Updated Twelve-Factor manifest — `content/config.md`.** Env vars are granular controls, never grouped by environment. <https://github.com/twelve-factor/twelve-factor/blob/next/content/config.md> (verified via direct fetch).
18. **django-environ — Quick Start & API.** `Env.read_env(env_file, overwrite=False)` uses setdefault semantics; `.env` should not be committed; `.env.dist` as template. <https://django-environ.readthedocs.io/en/latest/quickstart.html> and <https://django-environ.readthedocs.io/en/latest/api.html> (verified via web search + direct fetch).
19. **Django — Deployment checklist.** `SECRET_KEY` from env var; `DEBUG=False` in production; `ALLOWED_HOSTS`; database passwords protected like `SECRET_KEY`. <https://docs.djangoproject.com/en/5.2/howto/deployment/checklist/> (verified via direct fetch).
20. **Cookiecutter-Django — Local development with Docker.** Separate `.envs/.local/.django`, `.envs/.production/.django`, `.envs/.production/.postgres` files; `env_file:` per service; merge script for prod. <https://cookiecutter-django.readthedocs.io/en/stable/2-local-development/developing-locally-docker.html> (verified via web search).
21. **Docker production patterns (markof88).** ADR 0003: compose-override-pattern (base holds production contract, overrides hold environment ergonomics). <https://github.com/markof88/docker-production-patterns/blob/main/docs/decisions/0003-compose-override-pattern.md> (verified via web search).
22. **TheLinuxCode — Docker Compose Override Guide.** Dev/prod/test file layering; merge rules (scalars replace, lists concatenate, maps merge). <https://thelinuxcode.com/what-is-docker-compose-override-a-practical-guide-to-layered-compose-files/> (verified via web search, 2026-02-14).
23. **DevOpsNess — `.dockerignore` Best Practices.** `.env` / `.env.*` / `*.pem` / `secrets/` must be excluded; `COPY . .` ships everything without `.dockerignore`. <https://www.devopsness.com/blog/dockerignore-best-practices> (verified via web search, 2026-07-12).
24. **Safeguard.sh — Docker Secrets Management.** BuildKit `--mount=type=secret` for build-time secrets; `ARG`/`ENV` persistence in layers; `.dockerignore` defense-in-depth. <https://safeguard.sh/resources/blog/docker-secrets-management> (verified via web search, 2026-07-06).
25. **Simi.studio — Docker Compose Best Practices.** Three-rule env discipline (`.env` for substitution, `env_file:` for container injection, commit `.env.example` not `.env`); `docker compose config` for debugging. <https://simi.studio/en/posts/docker-compose-best-practices/> (verified via web search, 2026-03-28).
26. **GnTech Blog — Docker Compose Environment Variables.** `--env-file` chains; `env_file` passes values verbatim (no interpolation); host env wins over `.env`. <https://blog.gntech.me/posts/2026-05-24-docker-compose-env-variables/> (verified via web search, 2026-05-24).
27. **Docker — Using Docker secrets.** Secrets mounted as files at `/run/secrets/`; `*_FILE` convention for images that only accept env vars; Linux-only tmpfs. <https://docs.docker.com/compose/how-tos/use-secrets> (verified via direct fetch).
28. **Docker — Secrets reference (compose-file).** `secrets:` top-level `file`, `environment` (Compose-only), `external`, `name` fields. <https://docs.docker.com/reference/compose-file/secrets> (verified via direct fetch).
29. **docker/compose#9980 & docker/compose#11741.** Interpolation of `${VAR}` inside service `env_file:` contents does not reliably resolve from `--env-file`/`include`-supplied sources. <https://github.com/docker/compose/issues/9980>, <https://github.com/docker/compose/issues/11741> (verified via web search).
30. **Docker — Build context `.dockerignore` files.** Per-Dockerfile `.dockerignore` naming convention; `**` matches any number of directories (including zero). <https://docs.docker.com/build/concepts/context/> (verified via direct fetch).
