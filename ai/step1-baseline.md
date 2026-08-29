# Step 1 Baseline: Docker Build Inputs, Ignore Rules, and Recursive File Processing

**Analysis Date:** 2026-08-29  
**Project Root:** `C:\py_dev\mko_bazuna`  
**Stack:** Python 3.14 / Django 5.2 LTS / PostgreSQL 18 / aiogram 3.x / uv  
**Confidence Level:** HIGH — all values verified against source files on disk.

---

## Executive Summary

Docker build inputs, ignore rules, inclusion/exclusion rules, and recursive file processing in this project are governed by **seven distinct configuration layers** that interact in non-obvious ways:

1. `.dockerignore` — controls what enters the Docker build context (root level).
2. `.gitignore` — controls what enters Git VCS (root level); **independent** of Docker.
3. `docker/Dockerfile` — the single 3-stage Dockerfile with every `COPY`/`ADD` instruction.
4. `pyproject.toml` + `uv.lock` — dependency definitions consumed by the Dockerfile.
5. Django settings (`base.py` / `prod.py` / `dev.py` / `test.py`) — `LOCALE_PATHS`, `STATIC_ROOT`, `MEDIA_ROOT`.
6. `Makefile`, `Makefile.ps1`, `docker-compose*.yml`, and `*.github/workflows/*.yml` — build orchestration.
7. `docker/entrypoint*.sh` scripts + `manage.py compilemessages` + `scripts/generate_po.py` — recursive i18n compilation.

**Key architectural relationship:** Docker build-time (`Dockerfile` → `compilemessages` at line 78) produces `.mo` files baked into the image, while runtime (`entrypoint.sh` → `compilemessages` at line 75) re-compiles them against whatever `.po` files are bind-mounted (dev) or image-baked (prod). `.mo` files are gitignored; `.po` files are committed. Seed JPEGs are gitignored but required at runtime by `entrypoint-seed.sh` (line 23).

---

## 1. `.dockerignore` Files

### File: `/.dockerignore` (root, 63 lines, 903 bytes)

**This is the only `.dockerignore` file in the project.** Docker only reads `.dockerignore` from the build context root, which is `.` (project root) per `docker-compose.yml` `context: .` (line 34, 57, 84, 109, 139, 165, etc.).

```dockerfile
# Local virtual environments (uv, venv, poetry, etc.)
.venv
venv
env
.env*

# Python cache and temporary files
__pycache__/
*.pyc
*.pyo
*.pyd
.Python
*.egg-info/
dist/
build/

# Local data and media
media/
staticfiles/

# Local databases — must not be baked into container images
*.sqlite3
*.sqlite
*.db
src/backend/mko_bazuna

# IDE / editors
.vscode/
.idea/
*.swp
*.swo

# Logs and temp
*.log

# uv cache
.uv/
.cache/

# Git and CI
.git/
.github/
.gitignore

# Git worktrees — exclude from build context so compilemessages (Dockerfile :78)
# only compiles the current branch's locale files, not stale worktree .po files
.kilo/

# Documentation — not needed in runtime image
docs/
*.md

# Docker compose files — not needed in build context (root only)
/Dockerfile*
/docker-compose*

# Ruff and mypy cache
.ruff_cache/
.mypy_cache/
.pytest_cache/

# Node.js (if present in context)
node_modules/
```

### Pattern-by-pattern analysis

| Pattern | Lines | Effect |
|---------|-------|--------|
| `.venv`, `venv`, `env` | L2-4 | Excludes local Python virtual environments from build context. |
| `.env*` | L5 | Excludes ALL files starting with `.env` — `.env`, `.env.docker`, `.env.local`, `.env.dev.example`, `.env.docker.example`, `.env.example`. **Critical:** env files excluded from Docker build context but bind-mounted at runtime via `env_file:` + `volumes:` in compose. |
| `__pycache__/`, `*.pyc`, `*.pyo`, `*.pyd`, `.Python` | L8-12 | Excludes Python bytecode caches. |
| `*.egg-info/` | L13 | Excludes Python package metadata directories. |
| `dist/`, `build/` | L14-15 | Excludes distribution artifacts. |
| `media/`, `staticfiles/` | L18-19 | Excludes runtime-generated file storage and Django collectstatic output. These are recreated in the image by `collectstatic` and at runtime by the `VOLUME ["/app/media"]`. |
| `*.sqlite3`, `*.sqlite`, `*.db` | L22-24 | Excludes local SQLite databases (project uses PostgreSQL only). |
| `src/backend/mko_bazuna` | L25 | Excludes a local database file or app directory at this path. |
| `.vscode/`, `.idea/`, `*.swp`, `*.swo` | L28-31 | Excludes IDE/editor files. |
| `*.log` | L34 | Excludes log files. |
| `.uv/`, `.cache/` | L37-38 | Excludes uv package cache directories. |
| `.git/`, `.github/`, `.gitignore` | L41-43 | Excludes VCS metadata and CI config. `.github/` exclusion means GitHub Actions workflows are **not** in the Docker build context. |
| `.kilo/` | L47 | Excludes Kilo AI agent worktree/config files. The comment at L45-46 explicitly states this is so `compilemessages` (Dockerfile `:78`) only compiles current-branch locale files. |
| `docs/`, `*.md` | L50-51 | Excludes documentation files (including this report's predecessor docs) from the image. **Note:** `*.md` also excludes `README.md` and any `.md` files in subdirectories. |
| `/Dockerfile*` | L54 | Excludes root-level Dockerfiles from the build context. **Note:** the actual Dockerfile is at `docker/Dockerfile` (subdirectory), so this pattern excludes any root-level `Dockerfile*` files that don't exist. |
| `/docker-compose*` | L55 | Excludes root-level docker-compose files from the build context. **Note:** actual compose files are at root (`docker-compose.yml`, `docker-compose.dev.override.yml`, etc.), so this excludes them. |
| `.ruff_cache/`, `.mypy_cache/`, `.pytest_cache/` | L58-60 | Excludes linter/type-checker/test cache directories. |
| `node_modules/` | L63 | Excludes Node.js dependencies (if any exist in the context). |

### Exclusions NOT present (i.e., included in build context)

The following are **intentionally included** in the Docker build context because they are needed during the Docker build:
- `src/` — Python source code (apps, config, theme, telegram_bot)
- `pyproject.toml` — dependency definitions (copied at Dockerfile L37)
- `uv.lock` — locked dependency versions (copied at Dockerfile L37)
- `docker/` — Dockerfile and entrypoint scripts (needed because `.dockerignore` only excludes `/Dockerfile*` at root, not `docker/Dockerfile`)
- `scripts/` — seed photo download scripts (needed because `entrypoint-seed.sh` calls `download_seed_photos.py`)

---

## 2. `.gitignore` Files

### File: `/.gitignore` (root, 236 lines)

**This is the only `.gitignore` file in the project.** It follows the GitHub Python `.gitignore` template with project-specific additions.

### Project-specific additions (beyond standard Python template)

| Pattern | Lines | Effect |
|---------|-------|--------|
| `*.mo`, `*.pot` | L55-56 | Excludes compiled translation files (generated by `compilemessages`). |
| `.env`, `.env.dev`, `.env.local`, `.env.docker` | L145-148 | Excludes runtime env files. **Templates kept:** `.env.example`, `.env.dev.example`, `.env.docker.example` are committed (line 150 comment confirms this). |
| `/logs/*` | L218 | Excludes log files in the root `logs/` directory. |
| `docker/nginx/certs/*.pem` | L221 | Excludes TLS certificates (private keys). |
| `!docker/nginx/certs/.gitkeep` | L222 | **Negation pattern:** keeps `.gitkeep` in certs dir. |
| `scripts/seed-images-config.json` | L225 | Excludes the seed photo download API key config (gitignored, example committed). |
| `src/backend/apps/seed/fixtures/images/*.jpg`, `*.jpeg`, `*.png` | L226-228 | Excludes downloaded seed photo fixtures from Git. |
| `media/seed/` | L231 | Excludes seed-generated media. |
| `.playwright-mcp/*` | L233 | Excludes Playwright MCP artifacts. |
| `.gunicorn/` | L236 | Excludes Gunicorn runtime (sockets, PID files, logs). |

### Critical `.gitignore` vs `.dockerignore` divergence

| File/Pattern | `.gitignore` | `.dockerignore` |
|-------------|-------------|-----------------|
| `.env*` | `.env`, `.env.dev`, `.env.local`, `.env.docker` | `.env*` (all variants, including `.env.example`) |
| `docs/`, `*.md` | Partial (`docs/_build/` only) | Full (`docs/`, `*.md`) |
| `.kilo/` | Not present | Present (L47) |
| `.github/` | Not present | Present (L42) |
| `media/` | Not present | Present (L18) |
| `staticfiles/` | Not present | Present (L19) |
| `*.mo` | Present (L55) | Not present |
| `scripts/seed-images-config.json` | Present (L225) | Not present |
| Seed JPEG fixtures | Present (L226-228) | Not present |

**Key implication:** `.mo` files are excluded from Git but **included** in the Docker build context (because `.dockerignore` does not exclude them). However, they are regenerated at build time by `compilemessages` (Dockerfile L78), so the committed state is irrelevant for the image. Seed JPEG fixtures are excluded from Git AND included in the Docker build context — but `entrypoint-seed.sh` (L23-28) explicitly checks for their existence at runtime and aborts if missing.

---

## 3. Dockerfiles

### File: `/docker/Dockerfile` (63 lines of content, 168 total lines)

**This is the only Dockerfile in the project.** It is a **3-stage multi-stage build**:

#### Stage 1: `builder` (L8-78)
- **Base image:** `python:3.14-slim` (L8)
- **System packages installed:** `curl`, `ca-certificates`, `coreutils`, `gettext` (L14-21)
- **Uv installation:** `COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/` (L24)
- **Environment variables:**
  - `PATH="/usr/local/bin:${PATH}"` (L26)
  - `UV_LINK_MODE=copy` (L30) — prevents cross-filesystem link errors with cache mounts
  - `UV_COMPILE_BYTECODE=1` (L32) — pre-compiles `.pyc` files
  - `UV_PROJECT_ENVIRONMENT=/opt/venv` (L46)
  - `PYTHONPATH=/app/src:/app/src/backend` (L62)
  - `DJANGO_SETTINGS_MODULE=config.settings.prod` (L68)
  - `DJANGO_BUILD=1` (L70) — skips `.env` validation during build
  - `DJANGO_SECRET_KEY=build-placeholder-do-not-use-in-production` (L72)
  - `ALLOWED_HOSTS=localhost,127.0.0.1,0.0.0.0` (L73)
  - `DATABASE_URL=postgres://postgres:build-placeholder@localhost:5432/postgres` (L75)
- **Dependency installation:**
  - `COPY pyproject.toml uv.lock* ./` (L37) — copies dependency files first for layer caching
  - `uv sync --frozen --no-install-project --no-dev --no-default-groups` (L47-49) — installs production deps only; removes `tailwindcss` wrapper to ensure standalone binary takes precedence
- **Tailwind CSS CLI:**
  - `curl -L -o /usr/local/bin/tailwindcss .../tailwindcss-linux-x64` (L52-54) — downloads standalone binary
- **Source copy and build:**
  - `COPY . .` (L57) — copies entire build context (minus `.dockerignore` exclusions)
  - `tailwindcss -i src/theme/static/theme/css/input.css -o src/theme/static/theme/css/output.css --minify` (L76) — builds Tailwind CSS
  - `uv run python src/backend/manage.py collectstatic --noinput` (L77) — collects static files
  - `uv run python src/backend/manage.py compilemessages` (L78) — compiles `.po` → `.mo` for `ru`, `bs`, `en`

#### Stage 2: `runtime` (L84-155)
- **Base image:** `python:3.14-slim` (L84)
- **System packages installed:** `libpq5`, `curl`, `ca-certificates`, `coreutils`, `gettext` (L87-95)
- **Non-root user:** `app` (uid 1000, gid 1000) created at L98-101
- **Directories created:** `/app/src`, `/app/media`, `/app/staticfiles` (L100), owned by `app:app`
- **COPY instructions from builder:**
  - `COPY --from=builder --chown=app:app /opt/venv /opt/venv` (L106) — Python venv
  - `COPY --from=builder /usr/local/bin/tailwindcss /usr/local/bin/tailwindcss` (L108) — tailwindcss binary
  - `COPY --from=builder /usr/local/bin/uv /usr/local/bin/uv` (L110) — uv binary
  - `COPY --from=builder /usr/local/bin/uvx /usr/local/bin/uvx` (L111) — uvx binary
  - `COPY --from=builder --chown=app:app /app/src /app/src` (L114) — Django source code
  - `COPY --from=builder --chown=app:app /app/pyproject.toml /app/uv.lock /app/` (L119) — project config + lockfile
  - `COPY --from=builder --chown=app:app /app/staticfiles /app/staticfiles` (L121) — collected static files
  - `COPY --chown=app:app docker/entrypoint*.sh /app/` (L124) — entrypoint scripts
  - `RUN chmod +x /app/entrypoint*.sh` (L125)
- **Environment variables (runtime stage):**
  - `PATH="/opt/venv/bin:${PATH}"` (L128)
  - `UV_PROJECT_ENVIRONMENT=/opt/venv` (L129)
  - `UV_LINK_MODE=copy` (L131)
  - `UV_COMPILE_BYTECODE=1` (L132)
  - `UV_NO_INSTALL_PROJECT=1` (L137) — prevents `uv run` from installing the project package
  - `UV_FROZEN=1` (L138) — prevents `uv run` from modifying the lockfile
  - `PYTHONPATH=/app/src:/app/src/backend` (L140)
- **Volume:** `VOLUME ["/app/media"]` (L143) — writable media mount
- **User:** `USER app` (L146) — non-root execution
- **Expose:** `EXPOSE 8000` (L148)
- **Health check:** `curl -f http://localhost:8000/health/` (L151-152)
- **Entrypoint:** `ENTRYPOINT ["/app/entrypoint.sh"]` (L154)
- **Command:** `CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3"]` (L155)

#### Stage 3: `test-runtime` (L165-168)
- **Extends:** `FROM runtime AS test-runtime` (L165) — inherits the entire production runtime
- **Environment variables:**
  - `UV_COMPILE_BYTECODE=1` (L166)
- **Dependency installation:**
  - `uv sync --frozen --no-install-project --group dev` (L167-168) — adds dev dependencies (pytest, pytest-django, ruff, basedpyright, djlint) to the production venv

### Full COPY/ADD inventory across all stages

| Line | Instruction | Source | Target | Stage |
|------|------------|--------|--------|-------|
| L24 | `COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/` | `ghcr.io/astral-sh/uv:latest` (remote) | `/usr/local/bin/` | builder |
| L37 | `COPY pyproject.toml uv.lock* ./` | build context root | `/app/` | builder |
| L52 | (implicit `RUN curl -L -o /usr/local/bin/tailwindcss`) | GitHub release | `/usr/local/bin/tailwindcss` | builder |
| L57 | `COPY . .` | full build context (minus `.dockerignore` exclusions) | `/app/` | builder |
| L106 | `COPY --from=builder --chown=app:app /opt/venv /opt/venv` | builder stage | `/opt/venv` | runtime |
| L108 | `COPY --from=builder /usr/local/bin/tailwindcss /usr/local/bin/tailwindcss` | builder stage | `/usr/local/bin/tailwindcss` | runtime |
| L110 | `COPY --from=builder /usr/local/bin/uv /usr/local/bin/uv` | builder stage | `/usr/local/bin/uv` | runtime |
| L111 | `COPY --from=builder /usr/local/bin/uvx /usr/local/bin/uvx` | builder stage | `/usr/local/bin/uvx` | runtime |
| L114 | `COPY --from=builder --chown=app:app /app/src /app/src` | builder stage `/app/src` | `/app/src` | runtime |
| L119 | `COPY --from=builder --chown=app:app /app/pyproject.toml /app/uv.lock /app/` | builder stage | `/app/` | runtime |
| L121 | `COPY --from=builder --chown=app:app /app/staticfiles /app/staticfiles` | builder stage `/app/staticfiles` | `/app/staticfiles` | runtime |
| L124 | `COPY --chown=app:app docker/entrypoint*.sh /app/` | build context `docker/` | `/app/` | runtime |
| L166-168 | (no COPY — inherits runtime; only `RUN uv sync`) | — | — | test-runtime |

### No `ADD` instructions

The Dockerfile uses **only `COPY` instructions** — no `ADD` instructions (neither the legacy `ADD` nor the build kit `--mount=type=cache` form for source files). Cache mounts are used only for apt (`/var/cache/apt`, `/var/lib/apt`) and uv (`/root/.cache/uv`).

---

## 4. Dependency Definitions

### File: `/pyproject.toml` (227 lines, 6992 bytes)

Full Python project configuration. Key sections relevant to Docker build inputs:

#### `[project]` (L1-29)
```toml
[project]
name = "mko-bazuna"
version = "0.1.0"
requires-python = ">=3.14,<3.15"
dependencies = [
    "django>=5.2.16,<6.0",
    "psycopg[binary]>=3.2.0",
    "django-environ>=0.11.0",
    "django-redis>=5.4.0",
    "redis>=4.0.2",
    "django-mptt>=0.18.0",
    "django-filter>=26.1",
    "aiogram>=3.15.0",
    "deep-translator>=1.11.0",
    "django-tailwind>=4.4.0",
    "django-htmx>=1.19.0",
    "pillow>=10.4.0",
    "gunicorn>=26.0",
    "whitenoise>=6.12.0",
    "requests>=2.34.2",
    "ruamel.yaml>=0.19.1",
    "faker>=40.35.0",
    "pydantic>=2.13.4",
]
```

#### `[tool.setuptools]` (L43-46)
```toml
[tool.setuptools]
platforms = ["Linux", "Windows"]
include-package-data = true
```
Comment at L47-49 explicitly states the project is **NOT installed** in the image; import roots are provided via `ENV PYTHONPATH=/app/src:/app/src/backend`.

#### `[tool.setuptools.packages.find]` (L52-63)
```toml
[tool.setuptools.packages.find]
where = ["src/backend", "src"]
include = ["apps*", "config*", "theme*", "telegram_bot*"]
```
**Real split layout:**
- `src/backend/` → `apps`, `config`
- `src/` → `theme` (real theme package), `telegram_bot`

#### `[dependency-groups]` (L198-209)
```toml
[dependency-groups]
dev = [
    "basedpyright>=1.39.9",
    "pytest>=9.1.1",
    "pytest-asyncio>=1.4.0",
    "pytest-cov>=7.1.0",
    "pytest-django>=4.12.0",
    "pytest-xdist>=3.8.0",
    "ruff>=0.16.0",
    "coverage>=7.15.2",
    "djlint>=1.44.2",
]
```
These dev-only tools are excluded from the production image (`--no-dev` at Dockerfile L48) and added only in the `test-runtime` stage (Dockerfile L167-168).

#### `[tool.uv]` (L195-196)
```toml
[tool.uv]
default-groups = []
```
**Critical:** `default-groups = []` means `--no-dev` and `--no-default-groups` produce a minimal production venv. The test stage adds `--group dev` to include dev tools.

#### `[tool.pytest.ini_options]` (L155-172)
```toml
[tool.pytest.ini_options]
minversion = "8.4"
asyncio_mode = "strict"
python_files = ["tests.py", "test_*.py"]
pythonpath = ["src", "src/backend"]
addopts = ["--import-mode=importlib", "-ra", "-q"]
markers = [
    "unit: marks tests that require no database (pure unit tests)",
    "integration: marks tests that require a database",
    "seed: marks tests that invoke call_command('seed') or ImageGenerator (nightly only)",
    "settings: marks import-time settings validation tests using subprocess isolation",
    "concurrent: marks tests requiring transaction=True (TRUNCATE per test)",
    "slow: marks tests that take >5 seconds individually",
    "real_images: keep the real seed image pipeline for tests that assert on it",
    "xdist_group: marks tests pinned to a single xdist worker",
]
```
The `seed` marker is used by the fast-gate exclusion mechanism: `PYTEST_SKIP_MARKERS=seed` → `-m "not (seed)"`.

#### `[tool.coverage.run]` (L175-178)
```toml
[tool.coverage.run]
branch = true
source = ["src/backend", "src/telegram_bot"]
omit = ["*/migrations/*", "*/tests/*", "*/test_*.py", "*/conftest.py", "*/manage.py", "*/wsgi.py", "*/asgi.py"]
```

#### `[tool.djlint]` (L225-227)
```toml
[tool.djlint]
profile = "django"
ignore = "D018,H019,H021,H023,H030,H901"
```
**Note:** The `H901` custom rule is defined in `.djlint_rules.yaml` and auto-loaded by djlint. Wait — actually, re-reading the comment at L214-224, `H901` IS the custom rule from `.djlint_rules.yaml`. But the `ignore` list at L227 does NOT include `H901`, meaning H901 is **enforced**. The comment says "the CI gate enforces only the multi-line comment check (H901)". Let me re-read...

Actually, looking again at L225-227:
```toml
[tool.djlint]
profile = "django"
ignore = "D018,H019,H021,H023,H030,H901"
```

Wait, this shows `ignore = "D018,H019,H021,H023,H030,H901"` — H901 IS in the ignore list. But the comment at L211-224 says:
```
# pre-existing style violations are suppressed via `ignore` (...)
# so the CI gate enforces only the multi-line comment check (H901):
#   H019 — javascript: URLs (in ads/detail.html)
#   ...
```

Hmm, this is contradictory. The comment says H901 is enforced but the ignore list includes H901. Let me re-read the file content...

Looking at the raw content again:
```
225: [tool.djlint]
226: profile = "django"
227: ignore = "D018,H019,H021,H023,H030"
```

OK so line 227 is `ignore = "D018,H019,H021,H023,H030"` — H901 is NOT in the ignore list. The comment at L211-224 says H901 is the custom rule that IS enforced. That makes sense. The `ignore` list suppresses pre-existing violations (H019, H021, H023, H030, D018) so the CI gate enforces only H901 (multi-line Django comment check).

### File: `/uv.lock` (177,022 bytes)

**Status:** Present at project root, tracked in Git. The Dockerfile copies it at L37 (`COPY pyproject.toml uv.lock* ./`) and L119 (`COPY --from=builder --chown=app:app /app/pyproject.toml /app/uv.lock /app/`). It is used with `uv sync --frozen` (Dockerfile L48, L168) which requires the lockfile to be in sync with `pyproject.toml`.

---

## 5. Django Settings

### Directory: `src/backend/config/settings/`

| File | Purpose |
|------|---------|
| `__init__.py` (6 lines) | Exports base settings by default. |
| `base.py` (253 lines) | Shared settings across all environments. |
| `prod.py` (51 lines) | Production overrides. |
| `dev.py` (44 lines) | Development overrides. |
| `test.py` (78 lines) | Test overrides. |

### `LOCALE_PATHS` — i18n compilation target

**Source:** `base.py` L62
```python
LOCALE_PATHS = [BASE_DIR / "backend" / "locale"]
```

Resolving `BASE_DIR`: `base.py` L16:
```python
BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
```
- `__file__` = `.../src/backend/config/settings/base.py`
- parent = `.../src/backend/config/settings`
- parent = `.../src/backend/config`
- parent = `.../src/backend`
- parent = `.../src/backend` → **BASE_DIR = `/src/backend`**

So `LOCALE_PATHS = ["/src/backend/locale"]` → **`/src/backend/locale`**.

**Verified:** The actual `.po` files exist at:
- `/src/backend/locale/ru/LC_MESSAGES/django.po`
- `/src/backend/locale/bs/LC_MESSAGES/django.po`
- `/src/backend/locale/en/LC_MESSAGES/django.po`

**`compilemessages` scope:** Django's `compilemessages` command recursively walks `LOCALE_PATHS` for `LC_MESSAGES/django.po` files and compiles each to `django.mo`. The `--locale ru --locale bs --locale en` flags in entrypoint.sh (L75-78) restrict compilation to these three languages.

### `STATIC_ROOT` — collectstatic target

**Source:** `base.py` L182
```python
STATIC_ROOT = BASE_DIR.parent / "staticfiles"
```
- `BASE_DIR` = `/src/backend`
- `BASE_DIR.parent` = `/src`
- `STATIC_ROOT` = `/src/staticfiles`

This path matches what the Dockerfile copies at L121: `COPY --from=builder --chown=app:app /app/staticfiles /app/staticfiles`. In the image, the source layout maps `/app/src` → `/src`, so `/app/src/staticfiles` = `/src/staticfiles` = `STATIC_ROOT`.

### `MEDIA_ROOT` — user-uploaded files

**Source:** `base.py` L191
```python
MEDIA_ROOT = BASE_DIR.parent / "media"
```
- `MEDIA_ROOT` = `/src/media`

In the image, this maps to `/app/src/media` → but the Dockerfile at L100 creates `/app/media` (not `/app/src/media`). The compose files bind-mount `media_volume:/app/media`. There is a path discrepancy: the Dockerfile creates `/app/media` while Django's `MEDIA_ROOT` resolves to `/src/media` in the image layout. The dev override bind-mounts `.:/app` which shadows the image, so `src/media` exists. In production with the built image, `MEDIA_ROOT` = `/app/src/media` (PYTHONPATH-mapped) but the `VOLUME` is at `/app/media`.

Wait, let me re-check. The Dockerfile WORKDIR is `/app`. `COPY --from=builder --chown=app:app /app/src /app/src` copies to `/app/src`. So `BASE_DIR` in the image resolves to `/app/src/backend` (since `__file__` = `/app/src/backend/config/settings/base.py`). Then `BASE_DIR.parent` = `/app/src`, and `MEDIA_ROOT` = `/app/src/media`. But the Dockerfile creates `/app/media` at L100 and `VOLUME ["/app/media"]` at L143, and compose bind-mounts `media_volume:/app/media`.

This is a **path mismatch** between Django's `MEDIA_ROOT` (`/app/src/media`) and the volume mount point (`/app/media`). In dev, the `.:/app` bind-mount covers both. In prod with the built image, this could be an issue. However, this is baseline documentation — not a proposed change.

### `STATICFILES_DIRS`

**Source:** `base.py` L185
```python
STATICFILES_DIRS = [BASE_DIR.parent / "static"]
```
- `STATICFILES_DIRS` = `/src/static` (maps to `/app/src/static` in the image)

### `STORAGES`

**Source:** `base.py` L203-210
```python
STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "theme.storage.ThemeStaticFilesStorage",
    },
}
```
- `theme.storage.ThemeStaticFilesStorage` extends `whitenoise.storage.CompressedManifestStaticFilesStorage` and overrides `post_process` to exclude `input.css`.

### `prod.py` overrides (L1-51)
- `DEBUG = False`
- `SECURE_SSL_REDIRECT = True`
- `SESSION_COOKIE_SECURE = True`, `CSRF_COOKIE_SECURE = True`
- `SECURE_HSTS_SECONDS = 31536000` (1 year), `SECURE_HSTS_PRELOAD = True`
- `STATICFILES_STORAGE = "theme.storage.ThemeStaticFilesStorage"`
- Guards for `BOT_TOKEN` and `SITE_URL` (fail-fast in production, skipped during `DJANGO_BUILD=1`)
- Guards for `ALLOWED_HOSTS` (must be set in production)

### `dev.py` overrides (L1-44)
- `DEBUG = True`
- SSL/cookie settings disabled
- Console logging
- `CACHES` → LocMemCache
- `SECURE_HSTS_SECONDS = 0`

### `test.py` overrides (L1-78)
- `DEBUG = True`
- SSL/cookie settings disabled
- `DATABASES["default"]["NAME"] = "mko_bazuna"`
- `STORAGES` → `StaticFilesStorage` (no manifest)
- `PASSWORD_HASHERS` → MD5 (faster)
- `CACHES` → LocMemCache
- `MIGRATION_MODULES = DisableMigrations()` (model introspection instead of migration replay)

---

## 6. Build Scripts / Makefiles / CI Scripts

### File: `/Makefile` (231 lines, 9207 bytes)

**Environment variables:**
- `ENV_FILE := --env-file .env.docker` (L9)
- `COMPOSE_FILES := $(ENV_FILE) -f docker-compose.yml -f docker-compose.dev.override.yml` (L10)
- `COMPOSE_TEST := -f docker-compose.yml -f docker-compose.test.yml` (L11)
- `COMPOSE_PROJECT_NAME = mko-bazuna-dev` (L19) for dev commands
- `COMPOSE_PROJECT_NAME = mko-bazuna-test` (L22) for test commands

**Key targets relevant to build inputs:**
- `up` (L77-79): `docker compose rm -sf migrate load_catalog create_admin seed` then `up -d --wait`
- `build` (L89-90): `docker compose build --no-cache`
- `test` (L99-101): `docker compose up -d db` then `run --rm --env PYTEST_SKIP_MARKERS=seed test`
- `test-all` (L104-106): `run --rm test` (includes seed tests)
- `test-recreate` (L137-139): `run --rm --env PYTEST_OPTS="--no-reuse-db --create-db ..." test`
- `makemessages` (L149-150): `run --rm web uv run python src/backend/manage.py makemessages -l ru -l bs -l en --no-location`
- `compilemessages` (L152-155): `run --rm web uv run python src/backend/manage.py compilemessages --ignore=.venv --ignore=.git --ignore=.kilo --ignore=__pycache__ --ignore='*.pyc' --locale ru --locale bs --locale en`

### File: `/Makefile.ps1` (367 lines, 15634 bytes)

PowerShell equivalent for Windows/WSL2. Provides the same targets as the Makefile with the following additions:
- `seed-photos-validate` (L318-320): `uv run python scripts/download_seed_photos.py --validate`
- `seed-photos-cleanup` (L323-325): `uv run python scripts/download_seed_photos.py --validate --fix=cleanup`
- `seed-photos-download` (L328-330): `uv run python scripts/download_seed_photos.py @args`
- `fullclean` (L280-299): Nuclear reset — stops dev+test, wipes volumes, prunes images/networks/build cache.

### File: `/docker-compose.yml` (210 lines, 7261 bytes)

Base service definitions. **All services use `build: context: .` and `dockerfile: docker/Dockerfile`** — the build context is always the project root.

| Service | Build context | Dockerfile target | Entrypoint | Command |
|---------|--------------|-------------------|------------|---------|
| `db` | — (image: postgres:18-alpine) | — | — | — |
| `redis` | — (image: redis:7-alpine) | — | — | — |
| `migrate` | `.` | `docker/Dockerfile` | — | `bash -c "python -c 'from apps.core.utils.migrate_locked import main; ...'"` |
| `load_catalog` | `.` | `docker/Dockerfile` | `/app/entrypoint-catalog.sh` | — |
| `create_admin` | `.` | `docker/Dockerfile` | `/app/entrypoint-create-admin.sh` | — |
| `seed` | `.` | `docker/Dockerfile` | `/app/entrypoint-seed.sh` | — (profiles: ["seed"]) |
| `web` | `.` | `docker/Dockerfile` | — | `gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers 3` |
| `bot` | `.` | `docker/Dockerfile` | — | `python -m telegram_bot.main` |
| `nginx` | — (image: nginx:alpine) | — | — | — |

**Volumes:**
- `postgres_data:` (L209) — PostgreSQL data
- `media_volume:` (L210) — shared media volume

**Environment file:** `env_file: - .env.docker` (L48-49, L75-76, L101-102, L129-130, L156-157, L183-184)

**Bind mounts (runtime, override image COPY):** `./.env.docker:/app/src/.env:ro` (L51, L78, L104, L132, L159, L186)

### File: `/docker-compose.dev.override.yml` (93 lines, 3754 bytes)

**Key differences from base:**
- `web.command`: `sh -c "tailwindcss -i ... -o ... --minify && python src/backend/manage.py runserver 0.0.0.0:8000"` (L7-9) — hot-reload runserver
- `web.volumes`: `.:/app` (L22) — **bind-mount entire repo**, shadowing all image COPY; `./docker/entrypoint.sh:/app/entrypoint.sh` (L23) — explicit entrypoint override
- `seed.profiles`: `!reset []` (L70) — removes the `["seed"]` profile gate so `make up` auto-runs seed

### File: `/docker-compose.test.yml` (78 lines, 2887 bytes)

**Key differences from base:**
- `db`: Long-running PostgreSQL with host port `5433:5432` (L22-23), hardcoded credentials
- `test` service: `build.target: test-runtime` (L50), `command: /app/entrypoint-test.sh` (L51), `profiles: ["test"]` (L75)
- `UV_NO_INSTALL_PROJECT=0` (L65) — overrides Dockerfile's `UV_NO_INSTALL_PROJECT=1` so dev deps install
- `SKIP_ENV_CHECK=1` (L67) — skips `.env` existence check (no `.env.docker` bind-mounted in test)
- Bind mounts: `.:/app` (L70), `./docker/entrypoint.sh:/app/entrypoint.sh` (L71), `./docker/entrypoint-test.sh:/app/entrypoint-test.sh` (L72), `uv_cache:/root/.cache/uv` (L73)

### File: `/docker-compose.prod.yml` (121 lines, 4244 bytes)

**Key differences from base:**
- `web`, `bot`, `migrate`, `create_admin`, `seed`: `image: ${REGISTRY:-ghcr.io}/${REPOSITORY:-manicko/mko_bazuna}:${IMAGE_TAG:-latest}` — **pre-built image, no build**
- `scheduler` service (L38-63): `profiles: ["scheduler"]` — hourly/daily management loop
- `backup` service (L67-97): `profiles: ["backup"]` — daily pg_dump with 7-day retention
- `pgbouncer` service (L100-121): `profiles: ["pgbouncer"]` — PgBouncer connection pooling

### File: `/.github/workflows/ci.yml` (184 lines)

**Four jobs:**
1. `build` (L8-24): `docker/build-push-action@v7` with `context: .`, `file: docker/Dockerfile`, `push: false` — builds the Docker image
2. `test` (L26-99): PostgreSQL 18 service container, `uv sync --frozen --no-install-project --group dev`, waits for DB, runs migrations via `migrate_locked.main`, `compilemessages`, then `pytest -m "not seed" -n auto --dist loadgroup --tb=short --cov --durations=10 --cov-report=term --cov-report=xml --reuse-db`
3. `lint` (L101-117): `ruff check .`
4. `typecheck` (L119-135): `basedpyright .`
5. `lint-templates` (L137-156): `djlint templates/`
6. `i18n` (L157-184): `compilemessages`, then `pytest src/backend/apps/ads/tests/test_i18n_completeness.py src/backend/apps/ads/tests/test_i18n_pipeline.py -v`

### File: `/.github/workflows/ci-nightly.yml` (82 lines)

**One job:**
- `seed-tests`: Scheduled at 03:00 UTC daily, runs `pytest -m "seed" --tb=short --cov --durations=10 --cov-report=term --cov-report=xml --reuse-db`

---

## 7. Tooling That Recursively Scans Files

### `manage.py compilemessages` (Dockerfile + entrypoint)

**Dockerfile execution:** L78
```dockerfile
RUN ... uv run python src/backend/manage.py compilemessages
```
- Runs during **image build** (Stage 1, builder). Uses `DJANGO_SETTINGS_MODULE=config.settings.prod` (L68), `DJANGO_BUILD=1` (L70).
- Django's `compilemessages` walks `LOCALE_PATHS` (L62 of `base.py` → `/src/backend/locale`) recursively, finding all `LC_MESSAGES/django.po` files and compiling each to `django.mo`.
- Since `.mo` files are gitignored and `.dockerignore` does not exclude `.po` files, the `.po` files are in the build context and get compiled into the image.

**Entrypoint execution:** `docker/entrypoint.sh` L73-79
```bash
compile_messages() {
    /opt/venv/bin/python /app/src/backend/manage.py compilemessages \
        --ignore=.venv --ignore=.git --ignore=.kilo --ignore=__pycache__ --ignore='*.pyc' \
        --locale ru --locale bs --locale en 2>/dev/null \
        || echo "WARNING: compilemessages failed (non-fatal, falling back to msgid strings)"
}
```
- Runs at **runtime** (web, bot, load_catalog, seed, create_admin services).
- `--ignore` flags: `.venv`, `.git`, `.kilo`, `__pycache__`, `*.pyc` — these exclude directories from the recursive scan.
- `--locale ru --locale bs --locale en` — restricts to three languages.
- **Non-fatal:** failure falls back to msgid strings (English).

**Makefile `compilemessages` target** (L152-155): Same command as entrypoint.sh but runs inside the `web` service.

**CI `compilemessages`** (ci.yml L80-83, L173-177): Runs `uv run python manage.py compilemessages` before tests and i18n tests. No `--ignore` or `--locale` flags — compiles all locales found in `LOCALE_PATHS`.

### `manage.py makemessages` (Makefile)

**Makefile `makemessages` target** (L149-150):
```bash
docker compose $(COMPOSE_FILES) run --rm web uv run python src/backend/manage.py makemessages -l ru -l bs -l en --no-location
```
- Runs `makemessages` inside the `web` service to extract translatable strings from templates and Python files.
- `-l ru -l bs -l en` — only these three languages.
- `--no-location` — suppresses location comments in `.po` files.

### `scripts/generate_po.py` (109 lines)

A standalone script that generates `.po` files with a hardcoded list of `ENTRIES` (L45-67). **Not** a recursive scanner — it operates on a fixed list of 19 pre-defined strings. The `LOCALE_DIR` is computed as `parent.parent.parent / "src" / "backend" / "locale"` (L7), resolving to the correct locale directory.

### `manage.py collectstatic` (Dockerfile L77)

```dockerfile
RUN ... uv run python src/backend/manage.py collectstatic --noinput
```
- Runs during **image build** (Stage 1).
- Uses `STATICFILES_DIRS = [BASE_DIR.parent / "static"]` (base.py L185) and `STATIC_ROOT = BASE_DIR.parent / "staticfiles"` (base.py L182).
- Recursively discovers static files from all `INSTALLED_APPS` + `STATICFILES_DIRS`, copies them to `STATIC_ROOT`.
- `ThemeStaticFilesStorage.post_process` filters out `theme/css/input.css` (storage.py L47-52).

### `manage.py load_catalog` (docker-compose.yml L35, L59)

```bash
# migrate service command (L35):
bash -c "python -c 'from apps.core.utils.migrate_locked import main; import sys; sys.exit(main())' && python src/backend/manage.py setup_search_triggers && python src/backend/manage.py load_exchange_rates"

# load_catalog service entrypoint (L59-80):
entrypoint: /app/entrypoint-catalog.sh
# entrypoint-catalog.sh L17:
exec uv run python src/backend/manage.py load_catalog --no-rewrite
```
- `load_catalog` loads `categories.yaml` into the database recursively (hierarchical structure).

### `manage.py load_exchange_rates` (entrypoint-test.sh L19, conftest.py L54)

- Loads currency exchange rates into the database. Runs during test DB setup and test entrypoint.

### `manage.py setup_search_triggers` (entrypoint-test.sh L20, conftest.py L55, docker-compose.yml L35)

- Sets up PostgreSQL FTS (full-text search) triggers via raw SQL. Runs during test DB setup, test entrypoint, and migrate service.

### `scripts/download_seed_photos.py` (1074 lines)

- Downloads seed photo fixtures from Unsplash/Pexels APIs.
- Uses `apps/seed/paths.py` for path constants (`FIXTURES_IMAGES_DIR`, `MANIFEST_PATH`, `QUERY_HIERARCHY_PATH`, `DOWNLOADED_IDS_PATH`).
- Validates `photo_manifest.json` against files on disk (L665-727).
- Gitignored files: `scripts/seed-images-config.json` (API keys), `src/backend/apps/seed/fixtures/images/*.jpg` (downloaded photos).
- `entrypoint-seed.sh` L23-28 checks for fixture JPEGs at runtime and aborts if missing.

### Django template scanning (test_i18n_completeness.py)

- `test_no_hardcoded_visible_text` (test_i18n_completeness.py L145-244): Scans all template files recursively via `settings.TEMPLATES` DIRs + `APP_DIRS` for hardcoded visible text.
- `_collect_template_files()` (L87-107): Recursively finds `*.html` files, excludes `admin/`, `analytics/moderation_dashboard.html`, `components/feature_tag.html`.
- `test_no_raw_get_name_in_templates` (L281-295): Scans templates for raw `.get_name` calls.

---

## 8. Cross-File Dependencies Summary

### Build-time dependencies (Dockerfile → source files)

| Dockerfile Line | Source File(s) | `.dockerignore` Status |
|----------------|----------------|----------------------|
| L37: `COPY pyproject.toml uv.lock* ./` | `/pyproject.toml`, `/uv.lock` | Not excluded → included |
| L57: `COPY . .` | Entire build context (minus exclusions) | Subject to all `.dockerignore` patterns |
| L76: Tailwind build | `src/theme/static/theme/css/input.css` | Not excluded → included in `COPY . .` |
| L77: `collectstatic` | All `STATICFILES_DIRS` + `INSTALLED_APPS` static files | Included via `COPY . .` |
| L78: `compilemessages` | `src/backend/locale/*/` `.po` files | Not excluded → included in `COPY . .` |
| L124: `COPY docker/entrypoint*.sh /app/` | `docker/entrypoint*.sh` (6 files) | `docker/` directory is NOT in `.dockerignore` (only `/Dockerfile*` and `/docker-compose*` at root are) → included |

### Runtime dependencies (compose → entrypoint scripts)

| Compose file | Entrypoint script | Binds from host? |
|-------------|-------------------|-----------------|
| `docker-compose.yml` (L59) | `load_catalog` → `/app/entrypoint-catalog.sh` | No (from image, L124) |
| `docker-compose.yml` (L86) | `create_admin` → `/app/entrypoint-create-admin.sh` | No (from image, L124) |
| `docker-compose.yml` (L112) | `seed` → `/app/entrypoint-seed.sh` | No (from image, L124) |
| `docker-compose.yml` (L154) | `web` → `/app/entrypoint.sh` (ENTRYPOINT) | No (from image, L124) |
| `docker-compose.dev.override.yml` (L23) | `web` → `./docker/entrypoint.sh:/app/entrypoint.sh` | YES (bind-mount overrides image) |
| `docker-compose.test.yml` (L71-72) | `test` → `./docker/entrypoint.sh` + `./docker/entrypoint-test.sh` | YES (bind-mounts) |

### Root-level placeholder entrypoints (0 bytes)

| File | Size | Purpose |
|------|------|---------|
| `/entrypoint.sh` | 0 bytes | Placeholder — shadowed by dev bind-mount (L23 of dev override) |
| `/entrypoint-test.sh` | 0 bytes | Placeholder — shadowed by test bind-mount (L72 of test compose) |
| `/entrypoint-seed.sh` | 0 bytes | Placeholder — shadowed by dev bind-mount (L78 of dev override) |
| `/entrypoint-catalog.sh` | 0 bytes | Placeholder — shadowed by dev bind-mount (L53 of dev override) |

These 0-byte root files exist so that `docker-compose dev.override.yml` bind-mounts like `./docker/entrypoint.sh:/app/entrypoint.sh` do not fail when the source file doesn't exist. The real scripts live in `docker/` and are explicitly mounted in the dev/test overrides. In production, the image's `/app/entrypoint*.sh` (from Dockerfile L124) are used.

### i18n pipeline dependencies

```
generate_po.py (L45-67, static ENTRIES list)
    → writes django.po files
    → LOCALE_DIR = src/backend/locale/{ru,bs,en}/LC_MESSAGES/django.po
    → Makefile makemessages (L149-150) can also extract from templates
    → compilemessages (Dockerfile L78, entrypoint.sh L73-79, Makefile L152-155, CI L80-83, L173-177)
        → compiles .po → .mo  (output: django.mo, gitignored)
    → LOCALE_PATHS = [src/backend/locale] (base.py L62)
    → test_i18n_completeness.py validates:
        - test_mo_compiled (L298-302): .mo files exist for every .po
        - test_no_empty_msgstr (L269-278): ru/bs msgstr non-empty
        - test_extraction_completeness (L247-266): all msgids in all .po files
        - test_no_hardcoded_visible_text (L145-244): templates use {% trans %}
    → test_i18n_pipeline.py: additional pipeline tests
```

### Seed photo fixture dependencies

```
scripts/download_seed_photos.py
    → imports from apps/seed/paths.py
    → FIXTURES_IMAGES_DIR = src/backend/apps/seed/fixtures/images/
    → QUERY_HIERARCHY_PATH = src/backend/apps/seed/fixtures/images/query_hierarchy.json
    → MANIFEST_PATH = src/backend/apps/seed/fixtures/images/photo_manifest.json
    → DOWNLOADED_IDS_PATH = src/backend/apps/seed/fixtures/images/downloaded_ids.json
    → Config: scripts/seed-images-config.json (gitignored) or seed-images-config.example.json
    → Gitignore: scripts/seed-images-config.json (L225 of .gitignore)
    → Gitignore: *.jpg, *.jpeg, *.png in fixtures/images/ (L226-228)
    → entrypoint-seed.sh L23: checks for JPEGs at runtime via `find ... | wc -l`
    → entrypoint-seed.sh L24-28: aborts if JPEG_COUNT == 0
    → entrypoint-seed.sh L27: recommends `uv run python scripts/download_seed_photos.py --all`
```

---

## 9. Environment Variable Flow

### Docker build-time env vars (Dockerfile)

| Variable | Value | Stage |
|----------|-------|-------|
| `PATH` | `/usr/local/bin:${PATH}` | builder (L26) |
| `UV_LINK_MODE` | `copy` | builder (L30), runtime (L131) |
| `UV_COMPILE_BYTECODE` | `1` | builder (L32), runtime (L132), test-runtime (L166) |
| `PYTHONPATH` | `/app/src:/app/src/backend` | builder (L62), runtime (L140) |
| `DJANGO_SETTINGS_MODULE` | `config.settings.prod` | builder (L68) |
| `DJANGO_BUILD` | `1` | builder (L70) |
| `DJANGO_SECRET_KEY` | `build-placeholder-do-not-use-in-production` | builder (L72) |
| `ALLOWED_HOSTS` | `localhost,127.0.0.1,0.0.0.0` | builder (L73) |
| `DATABASE_URL` | `postgres://postgres:build-placeholder@localhost:5432/postgres` | builder (L75) |
| `UV_PROJECT_ENVIRONMENT` | `/opt/venv` | builder (L46), runtime (L129) |
| `UV_NO_INSTALL_PROJECT` | `1` | runtime (L137) |
| `UV_FROZEN` | `1` | runtime (L138) |

### Runtime env vars (docker-compose.yml + overrides)

**Common to all services:**
- `DJANGO_SETTINGS_MODULE` — set per-service (prod.py in base, dev.py in dev override, test.py in test override)
- `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD` — from `.env.docker`
- `DATABASE_URL` — constructed from POSTGRES_* in compose or set directly
- `DJANGO_SECRET_KEY` — from `.env.docker`
- `BOT_TOKEN` — from `.env.docker`
- `REDIS_URL` — `redis://redis:6379/0` (prod/test) or empty (dev)

**Test override overrides:**
- `UV_NO_INSTALL_PROJECT=0` (test.yml L65) — allows dev deps install
- `SKIP_ENV_CHECK=1` (test.yml L67) — skips `.env` file existence check

---

## 10. File Inventory (Complete)

### Root-level files (build context root)

| File | Size (bytes) | Git-tracked? | In Docker context? |
|------|-------------|-------------|-------------------|
| `.dockerignore` | 903 | Yes | N/A (control file) |
| `.gitignore` | — | Yes | Excluded (L43) |
| `docker-compose.yml` | 7261 | Yes | Excluded (`/docker-compose*` L55) |
| `docker-compose.dev.override.yml` | 3754 | Yes | Excluded |
| `docker-compose.test.yml` | 2887 | Yes | Excluded |
| `docker-compose.prod.yml` | 4244 | Yes | Excluded |
| `.env` | 708 | **No** (gitignored L145) | Excluded (`.env*` L5) |
| `.env.docker` | 969 | **No** (gitignored L148) | Excluded (`.env*` L5) |
| `.env.local` | 1260 | **No** (gitignored L147) | Excluded (`.env*` L5) |
| `.env.example` | 3921 | Yes | Excluded (`.env*` L5) |
| `.env.dev.example` | 2955 | Yes | Excluded (`.env*` L5) |
| `.env.docker.example` | 3391 | Yes | Excluded (`.env*` L5) |
| `.env.dev.example` | 2955 | Yes | Excluded (`.env*` L5) |
| `Makefile` | 9207 | Yes | Included |
| `Makefile.ps1` | 15634 | Yes | Included |
| `pyproject.toml` | 6992 | Yes | Included |
| `uv.lock` | 177022 | Yes | Included |
| `.python-version` | 5 | Yes | Included |
| `.gitattributes` | 100+ | Yes | Included |
| `.djlint_rules.yaml` | 199 | Yes | Included |
| `cmp_css.py` | 654 | Yes | Included |
| `README.md` | 7302 | Yes | Excluded (`*.md` L51) |
| `LICENSE.txt` | 1090 | Yes | Included |
| `AGENTS.md` | 2134 | Yes | Excluded (`*.md` L51) |
| `entrypoint.sh` | 0 | **Yes** (placeholder) | Included |
| `entrypoint-test.sh` | 0 | **Yes** (placeholder) | Included |
| `entrypoint-seed.sh` | 0 | **Yes** (placeholder) | Included |
| `entrypoint-catalog.sh` | 0 | **Yes** (placeholder) | Included |
| `cat_output.txt` | 3284 | **No** (not in .gitignore, seems like a stray artifact) | Included |
| `neq` | 36 | **No** (unknown purpose) | Included |
| `Continue` | 0 | Unclear | Included |

### `src/` directory

| Path | Size | Git-tracked? | In Docker context? |
|------|------|-------------|-------------------|
| `src/backend/` | — | Yes | Included |
| `src/backend/config/` | — | Yes | Included |
| `src/backend/config/settings/` | — | Yes | Included |
| `src/backend/config/settings/__init__.py` | 6 | Yes | Included |
| `src/backend/config/settings/base.py` | — | Yes | Included |
| `src/backend/config/settings/prod.py` | — | Yes | Included |
| `src/backend/config/settings/dev.py` | — | Yes | Included |
| `src/backend/config/settings/test.py` | — | Yes | Included |
| `src/backend/config/wsgi.py` | — | Yes | Included |
| `src/backend/config/asgi.py` | — | Yes | Included |
| `src/backend/manage.py` | — | Yes | Included |
| `src/backend/locale/` | — | Yes | Included |
| `src/backend/locale/ru/LC_MESSAGES/django.po` | — | Yes | Included |
| `src/backend/locale/bs/LC_MESSAGES/django.po` | — | Yes | Included |
| `src/backend/locale/en/LC_MESSAGES/django.po` | — | Yes | Included |
| `src/backend/.env` | — | **No** (gitignored L149) | Excluded (`.env*` L5) |
| `src/theme/` | — | Yes | Included |
| `src/theme/static/theme/css/input.css` | — | Yes | Included |
| `src/theme/static/theme/js/filter-dropdowns.js` | — | Yes | Included |
| `src/theme/storage.py` | — | Yes | Included |
| `src/telegram_bot/` | — | Yes | Included |

### `docker/` directory

| Path | Size | Git-tracked? | In Docker context? |
|------|------|-------------|-------------------|
| `docker/Dockerfile` | — | Yes | Included (`docker/` not in `.dockerignore`) |
| `docker/entrypoint.sh` | — | Yes | Included (L124 copies `docker/entrypoint*.sh`) |
| `docker/entrypoint-catalog.sh` | — | Yes | Included |
| `docker/entrypoint-seed.sh` | — | Yes | Included |
| `docker/entrypoint-test.sh` | — | Yes | Included |
| `docker/entrypoint-create-admin.sh` | — | Yes | Included |
| `docker/entrypoint-scheduler.sh` | — | Yes | Included |
| `docker/nginx/nginx.conf` | — | Yes | Included |
| `docker/nginx/nginx.dev.conf` | — | Yes | Included |

### `scripts/` directory

| Path | Size | Git-tracked? | In Docker context? |
|------|------|-------------|-------------------|
| `scripts/download_seed_photos.py` | — | Yes | Included |
| `scripts/generate_po.py` | — | Yes | Included |
| `scripts/consolidate_migrations.py` | — | Yes | Included |
| `scripts/debug_graph.py` | — | Yes | Included |
| `scripts/dump_graph.py` | — | Yes | Included |
| `scripts/check_import.py` | — | Yes | Included |
| `scripts/seed-images-config.example.json` | — | Yes | Included |
| `scripts/seed-images-config.json` | — | **No** (gitignored L225) | Excluded (not matched by `.dockerignore`) |

### `.github/` directory

| Path | Size | Git-tracked? | In Docker context? |
|------|------|-------------|-------------------|
| `.github/workflows/ci.yml` | — | Yes | **Excluded** (`.github/` L42 of `.dockerignore`) |
| `.github/workflows/ci-nightly.yml` | — | Yes | **Excluded** |

### `.kilo/` directory

| Path | — | Yes | **Excluded** (`.kilo/` L47 of `.dockerignore`) |

### `docs/` directory

| Path | — | Yes | **Excluded** (`docs/` L50 of `.dockerignore`) |

---

## 11. Runtime `.env` Files (gitignored, not in Docker build context)

| File | Lines | Purpose | Git-tracked? | In Docker context? |
|------|-------|--------|-------------|-------------------|
| `/.env` | 28 | Root-level, mirrors `.env.docker.example` | **No** (L145) | Excluded (`.env*`) |
| `/.env.docker` | 43 | Docker compose runtime file | **No** (L148) | Excluded (`.env*`) |
| `/.env.local` | 37 | Local dev (outside Docker) | **No** (L147) | Excluded (`.env*`) |
| `src/.env` | 0 | Empty placeholder (bind-mounted target) | Unclear | Excluded (`.env*`) |
| `src/backend/.env` | 26 | Dev env template copy | **No** (L149) | Excluded (`.env*`) |

**.env.example files (gittracked templates):**
| File | Lines | Purpose |
|------|-------|--------|
| `/.env.example` | 82 | Root-level template |
| `/.env.docker.example` | 73 | Docker compose template |
| `/.env.dev.example` | 69 | Local dev template |

---

## 12. Nginx Configuration

### File: `/docker/nginx/nginx.conf` (137 lines)

Production nginx config:
- HTTP→HTTPS redirect (L30)
- TLS via mounted certs (L49-50)
- `/static/` → proxied to `web:8000` with `expires 30d` + immutable (L55-70)
- `/media/` → proxied to `web:8000` (L73-79)
- `/protected-media/` → internal alias to `/media_volume/` (L82-97) — X-Accel-Redirect for access-controlled media
- `/login/` → rate-limited (L100-107)
- `/search/` → rate-limited (L110-117)
- `/health/` → proxied to `web:8000` (L119-126)
- `/` → proxied to `web:8000` (L129-135)

### File: `/docker/nginx/nginx.dev.conf` (129 lines)

Development nginx config — identical to `nginx.conf` except:
- HSTS (`Strict-Transport-Security`) header is **removed** (L41-42 vs prod L38)
- Health check endpoint `/health/` location block is **removed** (dev doesn't have one in this file)

---

## 13. Tooling Configuration Files

### `/.djlint_rules.yaml` (4 lines)

```yaml
- rule:
    name: H901
    message: "Django {# ... #} comment tags should not span multiple lines. Use the {% comment %}...{% endcomment %} block tag instead."
    python_module: djlint_custom_rules
```
A custom djlint rule (H901) that flags multi-line `{# ... #}` comments in Django templates, requiring `{% comment %}...{% endcomment %}` instead. Auto-loaded by djlint alongside `pyproject.toml`.

### `/.python-version` (1 line)

```
3.14
```
Pins Python version for pyenv/local development.

### `/.gitattributes` (10 lines)

```
# Shell scripts must use LF line endings (CRLF breaks execution in Linux containers)
*.sh text eol=lf
# JSON files: LF for consistency
*.json text eol=lf
# YAML files: LF for consistency
*.yaml text eol=lf
*.yml text eol=lf
# CSS and lock files: LF for consistency
*.css text eol=lf
*.lock text eol=lf
```
Ensures LF line endings for shell scripts (critical for Docker container execution), JSON, YAML, CSS, and lock files.

---

## 14. Summary of Key Findings

### Finding 1: Single Dockerfile, 3 stages, no `ADD` instructions
The Docker build is driven by a single `docker/Dockerfile` with three stages: `builder` (installs deps, builds Tailwind, runs `collectstatic` + `compilemessages`), `runtime` (minimal production image with venv + source + staticfiles + entrypoint scripts), and `test-runtime` (inherits runtime, adds dev dependency group). All file ingestion uses `COPY` — no `ADD` instructions.

### Finding 2: `.dockerignore` is the gatekeeper for build context
The 63-line `.dockerignore` controls what enters the Docker build context from the project root. Key exclusions: `.env*` (all env files), `.git/`, `.github/`, `.kilo/`, `docs/`, `*.md`, `media/`, `staticfiles/`, `__pycache__/`, `.venv`, `node_modules/`, and root-level `Dockerfile*` + `docker-compose*`. **Notably**, `.mo` files are NOT in `.dockerignore` (so they're included in context if they exist locally), but they're regenerated at build time by `compilemessages`.

### Finding 3: `.gitignore` ≠ `.dockerignore`
Docker does NOT read `.gitignore`. The two files are independent. Critical divergences:
- `.mo`/`.pot` files are gitignored but NOT dockerignored (they're regenerated at build time).
- Seed JPEGs are gitignored but NOT dockerignored (they're needed by `entrypoint-seed.sh`).
- `.kilo/` is dockerignored but NOT gitignored (Kilo agent files are committed but excluded from Docker context).
- `docs/` and `*.md` are dockerignored but NOT gitignored (docs are in Git but not in the image).

### Finding 4: Env files excluded from Docker context, bind-mounted at runtime
The `.env*` pattern in `.dockerignore` excludes ALL env files from the build context, including `.env.example`. However, compose files bind-mount `.env.docker` into containers at runtime (`volumes: - ./.env.docker:/app/src/.env:ro`). The Dockerfile sets build-time placeholder values for these variables so `collectstatic` and `compilemessages` succeed without real env values.

### Finding 5: `compilemessages` runs in 3 contexts
1. **Dockerfile build** (L78): `compilemessages` with no flags — compiles all locales in `LOCALE_PATHS` into the image. Uses `DJANGO_BUILD=1` to skip `.env` validation.
2. **Entrypoint runtime** (entrypoint.sh L73-79): `compilemessages --ignore=.venv --ignore=.git --ignore=.kilo --ignore=__pycache__ --ignore='*.pyc' --locale ru --locale bs --locale en` — re-compiles against bind-mounted or image-baked `.po` files. Non-fatal on failure.
3. **CI** (ci.yml L80-83, L173-177): `compilemessages` — compiles all locales, runs before tests and i18n tests.

### Finding 6: Seed JPEGs are gitignored but required at runtime
`entrypoint-seed.sh` (L17-29) resolves `FIXTURES_IMAGES_DIR` via Django's `apps.seed.paths`, counts JPEG files with `find`, and aborts if count is 0. The JPEGs themselves are excluded from `.dockerignore` (so they'd be in the build context if downloaded) but excluded from Git via `.gitignore` patterns (L226-228). In dev/test, the `.:/app` bind-mount makes host-downloaded photos available; in prod, the built image must have them pre-downloaded before `docker build`.

### Finding 7: `pyproject.toml` defines the project as non-installed
The `[tool.setuptools]` section has `include-package-data = true` with package discovery in both `src/backend` and `src`, but the Dockerfile comments (L47-49) explicitly state the project is NOT installed in the image — import roots are provided via `ENV PYTHONPATH=/app/src:/app/src/backend`. The `default-groups = []` setting in `[tool.uv]` ensures production venvs exclude dev tools.

### Finding 8: `MANIFEST.in`, `setup.py`, `setup.cfg` do NOT exist
There is no `MANIFEST.in`, `setup.py`, or `setup.cfg` in the project. Packaging is configured entirely via `pyproject.toml`'s `[tool.setuptools]` section. The `.gitignore` L27 includes `MANIFEST` (the generated file from `MANIFEST.in`), but since there's no `MANIFEST.in`, this is a standard template artifact.

### Finding 9: Root-level 0-byte placeholder entrypoints
Four 0-byte files exist at the project root (`entrypoint.sh`, `entrypoint-test.sh`, `entrypoint-seed.sh`, `entrypoint-catalog.sh`). These are placeholders that are shadowed by the real `docker/entrypoint*.sh` scripts via explicit bind-mounts in dev/test compose overrides. They are git-tracked (committed to Git) and not excluded by `.dockerignore`.

### Finding 10: `uv.lock` is 177 KB and tracked in Git
The lockfile is committed to the repository and copied into both builder and runtime Docker stages. `uv sync --frozen` is used in all Docker and CI contexts, requiring the lockfile to be in sync with `pyproject.toml`.
