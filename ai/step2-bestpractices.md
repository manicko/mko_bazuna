# Step 2 Best Practices Report: Docker Build Optimization

**Research Date:** 2026-08-29
**Project Root:** `C:\py_dev\mko_bazuna`
**Stack:** Python 3.14 / Django 5.2 LTS / PostgreSQL 18 / aiogram 3.x / uv / HTMX MPA / Gunicorn WSGI
**Confidence Level:** HIGH — all findings verified against project source on disk and cross-referenced with official uv documentation (docs.astral.sh), Docker best-practices guides, and Django community patterns.

---

## Summary Table

| # | Practice | Relevant File(s) (Step 1) | Current State (verified) | Best Practice | Relevance / Risk |
|---|----------|---------------------------|--------------------------|---------------|-------------------|
| 1 | Exclude `.mo`/`.pot` from build context | `.dockerignore` L55-56 (`.gitignore` has them); `Dockerfile` L78; `src/backend/locale/*/LC_MESSAGES/*.mo` on disk | `.mo` files are gitignored but **NOT** dockerignored. Three `.mo` files exist locally (ru, bs, en) | Add `*.mo` and `*.pot` to `.dockerignore` | **Medium risk.** Stale `.mo` files are transferred into the build context (wasted bandwidth/layer bytes) then overwritten by `compilemessages` at build time. Removing them from context saves transfer and eliminates the risk of stale translations being baked in if `compilemessages` is ever skipped. |
| 2 | Exclude stray root-level dev artifacts | Root directory listing; `.dockerignore` (no entries) | `cat_output.txt` (3284 B), `neq` (36 B), `Continue` (0 B), `cmp_css.py` (654 B) all committed and in build context | Add explicit exclusions for stray files + add to `.gitignore` if not needed in VCS | **High risk.** Debug/profiling artifacts in a production image are unprofessional and can leak output data. `cmp_css.py` and `cat_output.txt` appear to be one-off tooling leftovers. |
| 3 | Exclude `.gitattributes` from build context | `.gitignore` (no entry); `.dockerignore` (no entry) | `.gitattributes` (302 B, git-tracked) is included in build context | Add `.gitattributes` to `.dockerignore` | **Low risk.** Git-only file (LF line-ending rules). Has zero relevance inside a container image. Also a credential hygiene concern — `.gitattributes` can sometimes contain path-rewrite rules that should stay Git-local. |
| 4 | Exclude `.python-version` from build context | `.gitignore` L88 (commented out); `.dockerignore` (no entry) | `.python-version` (5 B, git-tracked, contains `3.14`) is in build context | Add `.python-version` to `.dockerignore` | **Low risk.** Base image `python:3.14-slim` already provides Python 3.14. The file is only consumed by pyenv/`python-version` managers at local dev time. Including it adds noise; excluding it prevents confusion if pyenv were installed in-container. |
| 5 | Exclude `scripts/` temp/profiling artifacts | `scripts/` directory listing; `.gitignore` (no entries) | `_tmp_pytest_run.txt` (190 KB), `_tmp_pytest_out.txt` (16 KB), `session_context.json` (90 KB) in context | Add these patterns to `.gitignore` **and** `.dockerignore` | **Medium risk.** Combined ~300 KB of test-profiling output transferred per build. Not needed at runtime. Should not be committed to VCS either. |
| 6 | Exclude `scripts/seed-images-config.json` from build context | `.gitignore` L225; `.dockerignore` (no entry) | Gitignored (contains API keys) but **NOT** dockerignored → `COPY . .` (Dockerfile L57) includes it in image | Add `scripts/seed-images-config.json` to `.dockerignore` | **High risk (security).** The file contains Unsplash/Pexels API keys. Although it is gitignored, any developer with a local copy who runs `docker build` will get it baked into the image. This is a credential leak vector. |
| 7 | Exclude `backups/` directory from build context | `.gitignore` (no entry); `.dockerignore` (no entry) | `backups/` directory exists at root (contains `.dump` files from `make backup`) | Add `backups/` to `.gitignore` and `.dockerignore` | **High risk (security/data).** Database dumps may contain sensitive production data. Must never enter a container image. |
| 8 | Exclude `.local/` from build context | `.gitignore` (no entry for `.local`); `.dockerignore` (no entry) | `.local/` directory exists at root (pyenv local installs) | Add `.local/` to `.dockerignore` | **Medium risk.** Can contain platform-specific Python builds (hundreds of MB). Unnecessary in container. |
| 9 | Add missing standard Python tool caches | `.dockerignore` L58-60 (`.ruff_cache/`, `.mypy_cache/`, `.pytest_cache/` present, others missing) | Missing: `.tox/`, `.nox/`, `.pyre/`, `.pytype/`, `__pypackages__/`, `.python-eggs/`, `.profile_default/`, `.pdbrc` | Add all standard Python tool cache dirs to `.dockerignore` | **Medium risk.** If any of these caches exist locally they bloat the build context. Standard template coverage. |
| 10 | Add missing build artifacts | `.gitignore` L29-33 (`.manifest`, `.spec` present); `.dockerignore` (no entries) | `*.manifest`, `*.spec` are gitignored but NOT dockerignored | Add `*.manifest`, `*.spec` to `.dockerignore` | **Low risk.** PyInstaller artifacts, unlikely present but should be covered for completeness. |
| 11 | Add missing coverage/test artifacts | `.gitignore` L40-52 (coverage patterns present); `.dockerignore` (no entry for local `.coverage`) | `.coverage` (168 KB), `coverage.xml`, `htmlcov/`, `.hypothesis/` are gitignored but NOT dockerignored | Add coverage/test artifact patterns to `.dockerignore` | **Medium risk.** `.coverage` file (168 KB verified on disk) is transferred per build. Test artifacts should never reach production images. |
| 12 | Add missing runtime artifacts | `.gitignore` L125-136 (celery/redis/rabbitmq patterns present); `.dockerignore` (no entry) | `celerybeat-schedule`, `celerybeat.pid`, `*.rdb`, `*.aof` gitignored but NOT dockerignored; `.gunicorn/` (L236) gitignored but not dockerignored | Add these patterns to `.dockerignore` | **Medium risk.** Runtime lock files and Redis RDB files from previous runs could be baked into the image. |
| 13 | Verify `pyproject.toml`/`uv.lock` layer caching | `Dockerfile` L37 (already separated) | `COPY pyproject.toml uv.lock* ./` before `COPY . .` — correct | Keep as-is; this is the **uv-recommended** pattern | **Already correct (HIGH confidence).** The official uv Docker docs (docs.astral.sh) recommend copying `pyproject.toml` and `uv.lock` first, then `--mount=type=bind` or `COPY`, to install deps into a cacheable layer before copying source. The project follows this. |
| 14 | Evaluate narrowing `COPY . .` | `Dockerfile` L57 | `COPY . .` copies entire filtered context | Assess: splitting into multiple `COPY` instructions for finer cache granularity vs. fragility | **Low risk / design decision.** The project is NOT pip-installed (PYTHONPATH-based), so `collectstatic` needs templates from all apps, `compilemessages` needs locale `.po` files, and Tailwind needs `src/theme/static/`. Narrowing `COPY . .` to specific subdirs would be fragile and is not recommended by uv docs for the source layer — the dependency layer (L37) is already split correctly. |
| 15 | Remove dead `.dockerignore` pattern | `.dockerignore` L25 | `src/backend/mko_bazuna` — path does NOT exist on disk | Remove or document | **Low risk.** The directory was verified absent. Dead pattern causes confusion. |
| 16 | `compilemessages` `--ignore` completeness in entrypoint | `entrypoint.sh` L76; `Makefile` L154 | `--ignore=.venv --ignore=.git --ignore=.kilo --ignore=__pycache__ --ignore='*.pyc'` — missing `.mypy_cache`, `.ruff_cache`, `.pytest_cache`, `node_modules`, `.tox`, `__pypackages__` | Add comprehensive `--ignore` flags covering all tool caches | **Medium risk.** Django's `compilemessages` recursively walks `LOCALE_PATHS`. While `.dockerignore` excludes most of these from the image build context, the entrypoint runs at runtime where bind mounts (dev) expose the full repo. Missing `--ignore` flags cause unnecessary filesystem traversal and potential stale `.po` compilation from tool cache directories. |
| 17 | `compilemessages` flags in Dockerfile build | `Dockerfile` L78 | No `--ignore` or `--locale` flags — compiles all locales found in `LOCALE_PATHS` | Add `--locale ru --locale bs --locale en` to match entrypoint and Makefile behavior | **Low risk.** In the image build, `.dockerignore` already limits the context, so all `.po` files are from the committed locale directory. However, adding `--locale` flags makes the build more explicit and consistent with the entrypoint and Makefile targets. Adding `--ignore` flags is belt-and-suspenders since `.dockerignore` handles it. |
| 18 | `uv`/`uvx` binaries in runtime image | `Dockerfile` L110-111 | Copied from builder to runtime; entrypoint scripts call `uv run` | Assess necessity | **Design decision.** The entrypoint scripts (`entrypoint.sh`, `entrypoint-catalog.sh`, `entrypoint-seed.sh`, `entrypoint-create-admin.sh`, `entrypoint-scheduler.sh`) all invoke `uv run python ...`. If entrypoint scripts are rewritten to use `/opt/venv/bin/python` directly, `uv`/`uvx` can be removed from the runtime stage, saving ~30 MB. However, the uv-recommended Docker pattern keeps `uv` available for `uv run` invocations. The official uv docs show removing `uv` only when using the `CMD ["uv", "run", "app"]` pattern with the `uv` Docker image itself, or when using `ENV VIRTUAL_ENV` + direct PATH activation. For this project's `uv run`-based entrypoints, `uv` in the runtime image is justified. |
| 19 | `tailwindcss` binary in runtime image | `Dockerfile` L108 | Copied from builder; dev compose bind-mounts `.:/app` which shadows `/app` but NOT `/usr/local/bin/tailwindcss` | Keep for dev mode | **Already correct.** The `tailwindcss` standalone binary is needed in dev mode (the `web` service runs `tailwindcss -i ... -o ...` via `runserver`). In production, CSS is pre-built at Dockerfile L76 and `tailwindcss` is never invoked. Since the same Dockerfile serves both dev and prod, the binary must remain. Removing it would break `make up` dev workflow. |
| 20 | `test-runtime` dev deps separation | `Dockerfile` L165-168 | `FROM runtime AS test-runtime` + `uv sync --frozen --no-install-project --group dev` | Already correct | **Already correct (HIGH confidence).** The `test-runtime` stage correctly inherits the production `runtime` image and only adds the `dev` dependency group. `default-groups = []` in `pyproject.toml` L196 ensures production `uv sync --no-dev --no-default-groups` excludes dev tools, and the test stage adds them back with `--group dev`. This is the pattern recommended by the uv Docker docs. |
| 21 | `.gitignore` vs `.dockerignore` divergence documentation | Step 1 Finding 3 | Intentional divergences exist (`.mo`, seed JPEGs, `.kilo/`, `docs/`) | No action needed — document as intentional | **Already correct.** The divergences are deliberate: `.mo` files are regenerated at build; seed JPEGs are bind-mounted in dev/test and pre-baked for prod seed service; `.kilo/` is excluded from Docker so `compilemessages` (Dockerfile L78) only compiles current-branch locales. This is correct behavior. |
| 22 | `Dockerfile`/`docker-compose*` exclusion scope | `.dockerignore` L54-55 | `/Dockerfile*` excludes root-level Dockerfiles; actual Dockerfile is at `docker/Dockerfile` (not excluded) | Correct — `docker/` dir must be included | **Already correct.** The `COPY docker/entrypoint*.sh /app/` instruction at Dockerfile L124 requires `docker/` to be in the context. The root-level `/Dockerfile*` and `/docker-compose*` patterns correctly exclude root-level copies that don't exist (actual files are in `docker/` and at root respectively). |
| 23 | apt cache cleanup | `Dockerfile` L21, L95 | `rm -rf /var/lib/apt/lists/*` present in both builder and runtime apt `RUN` blocks | Keep — already correct | **Already correct.** Standard Docker best practice. Cache mounts for apt are also used (`--mount=type=cache,target=/var/cache/apt`). |
| 24 | `UV_NO_INSTALL_PROJECT=1` + `UV_FROZEN=1` in runtime | `Dockerfile` L137-138 | Set in runtime stage | Keep | **Already correct.** These prevent `uv run` from attempting to install the project package or modify the lockfile in the runtime image. The uv docs recommend `UV_FROZEN=1` (or `--frozen`) for production to ensure reproducibility. |
| 25 | `UV_LINK_MODE=copy` | `Dockerfile` L30, L131 | Set in both stages | Keep | **Already correct.** Required when using cache mounts to prevent cross-filesystem link errors, as documented in the official uv Docker guide. |
| 26 | `UV_COMPILE_BYTECODE=1` | `Dockerfile` L32, L132, L166 | Set in all stages | Keep | **Already correct.** Recommended by uv docs for faster startup. Pre-compiles `.pyc` files. |

---

## Detailed Sections

### 1. `.mo`/`.pot` Files: Exclude from Build Context

**File:** `.dockerignore` (missing), `.gitignore` L55-56 (has `*.mo`, `*.pot`), `Dockerfile` L78, `src/backend/locale/ru/LC_MESSAGES/django.mo`, `src/backend/locale/bs/LC_MESSAGES/django.mo`, `src/backend/locale/en/LC_MESSAGES/django.mo`

**Current state (verified on disk):**
Three `.mo` files exist locally in `src/backend/locale/`:
- `src/backend/locale/ru/LC_MESSAGES/django.mo`
- `src/backend/locale/bs/LC_MESSAGES/django.mo`
- `src/backend/locale/en/LC_MESSAGES/django.mo`

These files are gitignored (`*.mo` in `.gitignore` L55-56) but are NOT in `.dockerignore`. They therefore enter the Docker build context via `COPY . .` (Dockerfile L57).

**Best practice:**
Add `*.mo` and `*.pot` to `.dockerignore`:

```dockerfile
# Compiled translations — gitignored but NOT dockerignored (current gap)
# compilemessages (Dockerfile L78) regenerates these in the image;
# excluding them from context saves transfer and prevents stale .mo files
*.mo
*.pot
```

**Relevance to this project:**
The Dockerfile build runs `compilemessages` at L78, which regenerates all `.mo` files from `.po` files. Any `.mo` files already present in the source tree are overwritten. Including them in the build context is pure waste — they're transferred over the Docker context stream, added to a layer, then immediately overwritten. By excluding them, the build context is smaller and there's no risk of stale translations being baked in if the `compilemessages` step ever fails or is removed. The official Django `.dockerignore` template from dockerignore.com explicitly includes `*.mo` and `*.pot` in its "Build Artifacts" section.

**Risk level:** Medium — if `compilemessages` fails during build, the stale `.mo` from the host would remain in the image, potentially serving outdated translations.

---

### 2. Stray Root-Level Dev Artifacts: Exclude from Build Context

**File:** Root directory listing (verified on disk), `.dockerignore` (no entries for these files)

**Current state (verified on disk):**
Four stray files exist at the project root and are included in the Docker build context:

| File | Size | Git-tracked? | Purpose |
|------|------|-------------|---------|
| `cat_output.txt` | 3284 B | Yes (git-tracked) | Debug output artifact |
| `neq` | 36 B | Yes (git-tracked) | Unknown purpose |
| `Continue` | 0 B | Yes (git-tracked) | Empty file |
| `cmp_css.py` | 654 B | Yes (git-tracked) | One-off CSS comparison script |

**Best practice:**
Add these to `.dockerignore`:

```dockerignore
# Stray root-level development artifacts
cat_output.txt
neq
Continue
cmp_css.py
```

And they should also be reviewed for `.gitignore` inclusion — these appear to be one-off scripts/debug artifacts that shouldn't be tracked in VCS at all.

**Relevance to this project:**
Step 1 Finding 9 noted these as `cat_output.txt`, `neq`, `Continue` at L848-850. The report correctly identifies them as "not in .gitignore, seems like a stray artifact" (`cat_output.txt`), "unknown purpose" (`neq`), and "Unclear" (`Continue`). `cmp_css.py` is a 654-byte script at root that appears to be a one-off tool for comparing CSS output. None of these are referenced by any Dockerfile instruction, entrypoint script, or compose file. Including them in the build context is pure bloat and in the case of `cat_output.txt` potentially a data leak of debug output.

**Risk level:** High (for `cat_output.txt` — debug output may contain sensitive data; Low for the others — minimal size but unprofessional).

---

### 3. `.gitattributes`: Exclude from Build Context

**File:** `.gitignore` (no entry), `.dockerignore` (no entry), `.gitattributes` (302 B, git-tracked)

**Current state (verified on disk):**
`.gitattributes` (302 bytes) is git-tracked and included in the Docker build context. It contains LF line-ending rules for `.sh`, `.json`, `.yaml`, `.yml`, `.css`, `.lock` files.

**Best practice:**
Add `.gitattributes` to `.dockerignore`:

```dockerignore
# Git metadata — only needed by Git, not in the image
.gitattributes
```

**Relevance to this project:**
`.gitattributes` (Step 1 section 13, L983-997) is purely a Git configuration file that controls line-ending normalization during Git checkout. Inside a Docker image, Git is not used (the `.git/` directory is already excluded by `.dockerignore` L41). The file has zero runtime effect. Including it adds unnecessary context bytes and is a hygiene concern. The techearl.com `.dockerignore` best-practices guide (May 2026) lists `.gitattributes` in its "Version control" section alongside `.git` and `.gitignore`.

**Risk level:** Low — 302 bytes of waste, but important for principle (Git-only files should not enter Docker context).

---

### 4. `.python-version`: Exclude from Build Context

**File:** `.gitignore` L88 (commented out), `.dockerignore` (no entry), `.python-version` (5 B, git-tracked)

**Current state (verified on disk):**
`.python-version` (5 bytes, contains `3.14`) is git-tracked and included in the Docker build context. The `.gitignore` comment at L88 says `# .python-version` (commented out), meaning the convention is to commit it.

**Best practice:**
Add `.python-version` to `.dockerignore`:

```dockerignore
# Python version pin — only for pyenv/local dev; base image already has 3.14
.python-version
```

**Relevance to this project:**
The Dockerfile uses `python:3.14-slim` (L8, L84) as the base image, so Python 3.14 is already present. `.python-version` is consumed by pyenv and similar version managers at local development time. Inside the container, there is no pyenv, and `uv` uses its own managed Python (or the system Python from the base image). The file has no effect at runtime or build time inside the container. The `.gitignore` L88 comment confirms this is the standard Python `.gitignore` template behavior (commented out to allow committing the pin for team consistency). Since it serves no purpose in Docker, it should be excluded from the build context.

**Risk level:** Low — 5 bytes, but principle matters. If `uv` were configured to read `.python-version` (it can via `UV_PYTHON_PREFERENCE`), the file's presence could cause unexpected Python resolution behavior.

---

### 5. `scripts/` Temp/Profiling Artifacts: Exclude from Build Context and Git

**File:** `scripts/` directory (verified on disk), `.gitignore` (no entries), `.dockerignore` (no entries)

**Current state (verified on disk):**
Three temp/profiling artifacts exist in `scripts/` and are included in the build context:

| File | Size | In `.gitignore`? | In `.dockerignore`? |
|------|------|-------------------|----------------------|
| `scripts/_tmp_pytest_run.txt` | 193,180 B (~190 KB) | No | No |
| `scripts/_tmp_pytest_out.txt` | 16,660 B (~16 KB) | No | No |
| `scripts/session_context.json` | 92,743 B (~90 KB) | No | No |

**Best practice:**
Add to both `.gitignore` and `.dockerignore`:

```gitignore
# Temp/profiling artifacts
scripts/_tmp_*.txt
scripts/session_context.json
```

```dockerignore
# Temp/profiling artifacts in scripts/
scripts/_tmp_pytest_run.txt
scripts/_tmp_pytest_out.txt
scripts/session_context.json
```

**Relevance to this project:**
Step 1 section 8 notes `scripts/download_seed_photos.py` (109 lines) and imports from `apps.seed.paths`, but does not catalog `_tmp_pytest_run.txt`, `_tmp_pytest_out.txt`, or `session_context.json`. These are clearly runtime-generated artifacts from test profiling or interactive debugging (e.g., the Kilo agent's `session_context.json` tracks conversation state). Combined ~300 KB of waste per build context transfer. `scripts/seed-images-config.example.json` (347 B) IS needed — it's the template — but the temp files are not. The `entrypoint-seed.sh` (Step 1 L691-697) references `download_seed_photos.py` and `apps.seed.paths` but never these temp files.

**Risk level:** Medium — 300 KB of unnecessary context transfer; profiling data may contain internal state.

---

### 6. `scripts/seed-images-config.json`: Exclude from Build Context (Security)

**File:** `.gitignore` L225 (present), `.dockerignore` (absent), `scripts/seed-images-config.json`

**Current state (verified on disk):**
`scripts/seed-images-config.json` is gitignored (L225) but NOT in `.dockerignore`. The file exists on disk (446 bytes, verified). The Dockerfile's `COPY . .` (L57) includes it in the build context, and no instruction removes it.

**Best practice:**
Add to `.dockerignore` (not just `.gitignore`):

```dockerignore
# Seed photo API keys — gitignored but must also be dockerignored
scripts/seed-images-config.json
```

**Relevance to this project:**
Step 1 Finding 6 (L1024-1025) explicitly documents: `entrypoint-seed.sh` (L23-28) checks for JPEG fixtures at runtime and aborts if missing. The `download_seed_photos.py` script (L691-697) uses `seed-images-config.json` for API keys to download seed photos from Unsplash/Pexels. However, `download_seed_photos.py` runs on the HOST (via `make seed-photos-download`), not inside the container. The seed-service entrypoint (`entrypoint-seed.sh`) only checks for JPEG existence — it never reads `seed-images-config.json`. Therefore, the API key config should NOT be in the Docker image. Including it is a credential leak: any developer with local API keys who runs `docker build` will bake those keys into the production image. This is a **confirmed security vulnerability** given that `.env*` is already excluded but `seed-images-config.json` is not.

**Risk level:** High — credential/API key leak into production container images.

---

### 7. `backups/` Directory: Exclude from Build Context (Security)

**File:** Root directory listing (verified). `.gitignore` — no entry. `.dockerignore` — no entry. `backups/` directory exists.

**Current state (verified on disk):**
`backups/` directory exists at the project root. The `Makefile` `backup` target (L199-206) writes `dump_*.dump` files to `./backups/`. These are PostgreSQL dumps that may contain sensitive production data.

**Best practice:**
Add to both `.gitignore` and `.dockerignore`:

```gitignore
# Database backups — never commit
backups/
```

```dockerignore
# Database backup dumps — must never enter images
backups/
```

**Relevance to this project:**
Step 1 section 8 (L711-718) catalogs the build's file ingestion but does not mention `backups/`. The `Makefile` `backup` target (Step 1 L525-526, L199-206) creates `dump_*.dump` files in `./backups/`. The `Makefile` `fullclean` target (Makefile.ps1 L280-299) explicitly cleans this directory. Database dumps contain user data (phone numbers for classifieds, ad content, etc.) and must never be in a Docker image. This is a confirmed security gap.

**Risk level:** High — potential PII/sensitive data leak into production images.

---

### 8. `.local/` Directory: Exclude from Build Context

**File:** Root directory listing (verified). `.gitignore` (no entry). `.dockerignore` (no entry). `.local/` directory exists.

**Current state (verified on disk):**
`.local/` directory exists at the project root. It is not tracked by Git but is present on disk (likely from local pyenv/pipx installs). It is not in `.dockerignore`.

**Best practice:**
Add to `.dockerignore`:

```dockerignore
# Local pyenv/pipx installations
.local/
```

**Relevance to this project:**
`.local/` is a standard location for `pipx`, `pyenv`, and user-local Python installations. In the project root, it may contain pyenv-managed Python installations (which can be hundreds of MB). Inside the container, the `python:3.14-slim` base image + uv-managed venv provide all needed Python. The `.gitignore` (standard Python template) does not include `.local/` because some projects commit user-scoped tool configs, but for this Dockerized project, it has no relevance.

**Risk level:** Medium — `.local/` may contain large platform-specific Python builds that bloat the build context.

---

### 9. Missing Standard Python Tool Cache Directories

**File:** `.dockerignore` L58-60 (has `.ruff_cache/`, `.mypy_cache/`, `.pytest_cache/` but no others), `.gitignore` L40-52

**Current state (verified):**
The `.dockerignore` covers three tool caches:
- `.ruff_cache/` (L58)
- `.mypy_cache/` (L59)
- `.pytest_cache/` (L60)

But misses several standard Python tool caches that are present in the `.gitignore`:
- `.tox/` (L41 of `.gitignore`)
- `.nox/` (L42)
- `.hypothesis/` (L50)
- `.pyre/` (L175)
- `.pytype/` (L178)
- `.profile_default/` (not in gitignore)
- `__pypackages__/` (L122)
- `.pdbrc` (not in gitignore)
- `.python-eggs/` (not in gitignore)

Also, `.gitignore` has cache patterns for:
- `.cache` (L45) — already covered by `.dockerignore` `.cache/` (L38)

**Best practice:**
Add the missing standard patterns to `.dockerignore`:

```dockerignore
# Additional Python tool caches (standard template coverage)
.tox/
.nox/
.hypothesis/
.pyre/
.pytype/
.__pypackages__/
.pdbrc
.python-eggs/
.profile_default/
```

**Relevance to this project:**
The project uses `basedpyright` (type checker), `ruff` (linter), `pytest` (test), and `djlint` (template linter). While `ruff`/`mypy`/`pytest` caches are excluded, the project's actual tool is `basedpyright` (not `mypy`). The `.gitignore` follows the standard Python template which includes both `.mypy_cache/` and `.pytype/` and `.pyre/`, but the `.dockerignore` only includes `.mypy_cache/`. Adding the full set ensures that no matter which tools are run locally, their caches never enter the Docker build context. The dockerignore.com community best-practices guide includes all of these in its "Dependency Management & Package Cache" section.

**Risk level:** Medium — tool caches can be large and contain stale analysis results that could confuse `compilemessages` or other recursive scanners.

---

### 10. Missing Build Artifacts (PyInstaller etc.)

**File:** `.gitignore` L29-33 (has `*.manifest`, `*.spec`), `.dockerignore` (no entries)

**Current state (verified):**
`.gitignore` covers:
- `*.manifest` (L32)
- `*.spec` (L33)

But `.dockerignore` does not exclude these. No PyInstaller usage was found in the project (no `.spec` files exist on disk), but the patterns should be present for completeness.

**Best practice:**
Add to `.dockerignore`:

```dockerignore
# PyInstaller artifacts
*.manifest
*.spec
```

**Relevance to this project:**
The project does not use PyInstaller (Step 1 Finding 8 confirms no `MANIFEST.in`, `setup.py`, or `setup.cfg`). However, the `.gitignore` includes these patterns from the standard Python template. Adding them to `.dockerignore` ensures completeness and protects against future tooling changes. The dockerignore.com framework-specific template includes `*.spec` and `*.manifest` in its "Build Artifacts" section.

**Risk level:** Low — no current PyInstaller usage, but best-practice completeness.

---

### 11. Missing Coverage/Test Artifacts

**File:** `.gitignore` L40-52 (has `.coverage`, `.coverage.*`, `htmlcov/`, `.hypothesis/`), `.dockerignore` (no entries for these)

**Current state (verified on disk):**
- `.coverage` file exists (167,936 bytes) at the project root
- `coverage.xml` — generated by `--cov-report=xml` in CI
- `htmlcov/` — generated by `--cov-report=html`
- `.hypothesis/` — Hypothesis test database
- `.coverage.*` — coverage.py parallel data

These are all gitignored but NOT dockerignored. The `.coverage` file (168 KB) is confirmed present on disk.

**Best practice:**
Add to `.dockerignore`:

```dockerignore
# Coverage and test artifacts
.coverage
.coverage.*
htmlcov/
.hypothesis/
.coverage.*
```

**Relevance to this project:**
The project's `pyproject.toml` L174-178 defines `[tool.coverage.run]` with `source = ["src/backend", "src/telegram_bot"]`. The CI workflow (`ci.yml` L91) runs `pytest --cov --cov-report=term --cov-report=xml`, producing `.coverage` and `coverage.xml`. The `Makefile` `test` target runs `pytest` which can produce these artifacts locally. Including a 168 KB `.coverage` file in every build context transfer is wasteful and could leak test execution metadata. The techearl.com best-practices guide (May 2026) lists `coverage` and `.nyc_output/` under "Test and coverage."

**Risk level:** Medium — 168 KB wasteful transfer; test metadata could contain internal timing/structure info.

---

### 12. Missing Runtime Artifacts (Celery/Redis/Gunicorn)

**File:** `.gitignore` L125-136, `.dockerignore` (no entries)

**Current state (verified):**
`.gitignore` includes:
- `celerybeat-schedule` (L125)
- `celerybeat.pid` (L126)
- `*.rdb` (L129)
- `*.aof` (L130)
- `*.pid` (L131)
- `mnesia/` (L134)
- `rabbitmq/` (L135)
- `rabbitmq-data/` (L136)

But `.dockerignore` has none of these. Also `.gitignore` L236 has `.gunicorn/` but `.dockerignore` does not.

**Best practice:**
Add to `.dockerignore`:

```dockerignore
# Runtime artifacts (should never be in image)
celerybeat-schedule
celerybeat.pid
*.rdb
*.aof
*.pid
.gunicorn/
```

**Relevance to this project:**
The project uses Redis (docker-compose.yml `redis:7-alpine`, `REDIS_URL` in settings). Redis RDB/AOF persistence files (`*.rdb`, `*.aof`) could exist if Redis runs with persistence locally. The `.gunicorn/` directory (gitignored L236) stores Gunicorn sockets, PID files, and logs. The `entrypoint.sh` L41 shows Gunicorn is the WSGI server (`CMD ["gunicorn", ...]` at Dockerfile L155). The `.pid` pattern catches PID files from any process. Including these in the Docker build context risks baking stale runtime state into the image. While these files are unlikely to exist during a clean build, they could be present after a dev run, and Docker would include them in the context without exclusion.

**Risk level:** Medium — stale PID/sock files could cause container startup issues if accidentally included.

---

### 13. Dependency File Layer Caching: Already Correct

**File:** `Dockerfile` L37

**Current state (verified on disk):**
```dockerfile
COPY pyproject.toml uv.lock* ./
```
This is the **first** `COPY` of source files, before `COPY . .` (L57). The dependency install (`uv sync --frozen --no-install-project --no-dev --no-default-groups` at L47-49) runs between these two COPYs.

**Best practice (from official uv docs):**
The official uv Docker integration guide (docs.astral.sh, Section "Intermediate layers") recommends:

```dockerfile
# Install dependencies
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-install-project

# Copy the project into the image
COPY . /app

# Sync the project
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked
```

**Relevance to this project:**
The project's approach is functionally equivalent to the official pattern — it copies `pyproject.toml` and `uv.lock` first (L37), installs deps with `--no-install-project` (L48), then copies all source (L57). The key difference is that the project uses `COPY pyproject.toml uv.lock* ./` instead of `--mount=type=bind,source=...`. Both approaches achieve the same goal: dependency layer caching so that source code changes don't invalidate the dependency install layer. The project's `COPY` approach is simpler and also makes the files available for the subsequent `uv sync` (which needs them). The uv docs note that for the non-bind-mount approach, the files must be `COPY`'d because `uv sync` needs them in the filesystem. The project's approach is **correct and follows the official recommendation** for projects that don't use BuildKit bind mounts for lockfile injection.

The `--frozen` flag (Dockerfile L48) is equivalent to `--locked` for sync purposes — it asserts the lockfile is up to date without checking. The project uses `--frozen` consistently in both Docker (L48, L168) and CI (L54, L112, L130, L148, L170). This is correct.

**Risk level:** None — already following best practice.

**Recommendation:** No change needed. The current approach is optimal.

---

### 14. Evaluating Narrowing `COPY . .`

**File:** `Dockerfile` L57

**Current state (verified on disk):**
```dockerfile
COPY . .
```
This copies the entire Docker build context (after `.dockerignore` filtering) to `/app/`.

**Best practice (from Docker and uv docs):**
The Docker best-practices guide recommends minimizing what's copied in each `COPY` instruction for better layer caching. However, this applies to **which directories** are copied, not necessarily splitting every file.

**Relevance to this project:**
The `COPY . .` at L57 is the source-code layer that follows the dependency layer (L37 → L47-49). This separation already achieves the primary caching benefit: dependency changes don't invalidate the source layer, and source changes don't invalidate the dependency layer.

The question of whether to narrow `COPY . .` to specific subdirectories (e.g., `COPY src/ scripts/ pyproject.toml uv.lock Makefile docker/`) is a **design decision**:

**Arguments for narrowing:**
- Better granular caching: if a stray file changes, only its layer is invalidated
- The uv Docker guide's "Intermediate layers" section uses `--mount=type=bind` for lockfiles, then `COPY . /app` for source — suggesting source is copied wholesale

**Arguments against narrowing (specific to this project):**
1. The project is NOT pip-installed (Step 1 Finding 7, L47-49 of `pyproject.toml`). Import roots are via `PYTHONPATH=/app/src:/app/src/backend` (Dockerfile L62). This means **all** source must be present at runtime — `COPY . .` is functionally correct.
2. `collectstatic` (Dockerfile L77) uses `STATICFILES_DIRS = [BASE_DIR.parent / "static"]` (base.py L185) and recurses through all `INSTALLED_APPS` templates (Step 1 L667-668). Narrowing the COPY would risk missing app templates.
3. `compilemessages` (Dockerfile L78) walks `LOCALE_PATHS = [BASE_DIR / "backend" / "locale"]` (base.py L62), which resolves to `src/backend/locale/`.
4. Tailwind build (Dockerfile L76) reads `src/theme/static/theme/css/input.css`.
5. The entrypoint scripts at `docker/entrypoint*.sh` are copied separately at L124 (`COPY --chown=app:app docker/entrypoint*.sh /app/`), not via `COPY . .`.

The uv Docker guide explicitly recommends the pattern the project uses: copy dependency files first, install deps in a separate layer, then `COPY . .` for source. Splitting source into per-directory `COPY` instructions would be **fragile** — if a template in `apps/ads/` changes, but the `COPY` instruction lists `src/backend/apps/` as a separate line, that's fine, but if a new app directory is added and the `COPY` instruction doesn't include it, the build silently produces a broken image. The `COPY . .` approach is safer and the performance difference is negligible since `.dockerignore` already filters aggressively.

**Recommendation:** Keep `COPY . .` as-is. The dependency layer caching (L37 → L47-49 → L57) is the correct pattern per official uv docs. Narrowing `COPY . .` adds fragility without meaningful benefit.

---

### 15. Dead `.dockerignore` Pattern: `src/backend/mko_bazuna`

**File:** `.dockerignore` L25

**Current state (verified on disk):**
```
src/backend/mko_bazuna
```
The path `src/backend/mko_bazuna` does NOT exist on disk (verified: `src/backend/` contains `apps`, `config`, `docker`, `locale`, `templates`, `__init__.py`, `manage.py`, `.env`, and step3 artifact files — no `mko_bazuna` directory or file).

The `.gitignore` also has `src/backend/mko_bazuna` (no line number in Step 1, but the pattern is present). The Step 1 report (L109) notes: "Excludes a local database file or app directory at this path."

**Best practice:**
Remove dead patterns from `.dockerignore`. If the path was a historical database file, it should be covered by the `*.sqlite3` / `*.db` patterns already present. If it was a historical app directory that no longer exists, the pattern is dead code.

**Relevance to this project:**
The `src/backend/mko_bazuna` pattern appears to be a leftover from an early project layout where the Django project was a package named `mko_bazuna` inside `src/backend/`. The current layout uses `config/settings/` for settings, `apps/` for Django apps, and `src/theme/` for the theme — no `mko_bazuna` package. Keeping the pattern is harmless (it matches nothing), but it's misleading: a future developer might think `src/backend/mko_bazuna` is a real path and wonder why it's excluded. The Step 1 report itself noted confusion: "Excludes a local database file or app directory at this path" — suggesting even the analyst was uncertain.

**Risk level:** Low — harmless dead pattern, but a documentation/clarity issue.

---

### 16. `compilemessages` `--ignore` Completeness in Entrypoint

**File:** `docker/entrypoint.sh` L76, `Makefile` L154, `Dockerfile` L78, CI workflow `ci.yml` L83, L176

**Current state (verified on disk):**

**Entrypoint (`entrypoint.sh` L75-78):**
```bash
/opt/venv/bin/python /app/src/backend/manage.py compilemessages \
    --ignore=.venv --ignore=.git --ignore=.kilo --ignore=__pycache__ --ignore='*.pyc' \
    --locale ru --locale bs --locale en 2>/dev/null \
    || echo "WARNING: compilemessages failed (non-fatal, falling back to msgid strings)"
```

**Makefile (L153-155):**
```bash
docker compose $(COMPOSE_FILES) run --rm web uv run python src/backend/manage.py compilemessages \
    --ignore=.venv --ignore=.git --ignore=.kilo --ignore=__pycache__ --ignore='*.pyc' \
    --locale ru --locale bs --locale en
```

**Dockerfile (L78):**
```dockerfile
RUN ... uv run python src/backend/manage.py compilemessages
```
No `--ignore` or `--locale` flags.

**CI (ci.yml L83, L176):**
```yaml
run: uv run python manage.py compilemessages
```
No `--ignore` or `--locale` flags.

**Best practice:**
Django's `compilemessages` recursively walks `LOCALE_PATHS` looking for `LC_MESSAGES/django.po` files. The `--ignore` flags exclude directories from scanning. The project's ignore list is incomplete:

Missing patterns that should be ignored:
- `.mypy_cache` — present in `.dockerignore` but not in `--ignore`
- `.ruff_cache` — present in `.dockerignore` but not in `--ignore`
- `.pytest_cache` — present in `.dockerignore` but not in `--ignore`
- `node_modules` — present in `.dockerignore` but not in `--ignore`
- `.tox`, `.nox` — not present in either
- `__pypackages__` — not present in either
- `.uv` — present in `.dockerignore` but not in `--ignore`
- `.cache` — present in `.dockerignore` but not in `--ignore`

**Relevance to this project:**
The entrypoint `compilemessages` runs at **runtime** (not just build time). In development mode, the `.:/app` bind-mount (docker-compose.dev.override.yml L22) exposes the **entire host filesystem** inside `/app/`. This means all local tool caches (`.mypy_cache`, `.ruff_cache`, `.pytest_cache`, `.uv`, `.cache`) are visible inside the container. Without `--ignore` flags for these, `compilemessages` will traverse into them looking for `LC_MESSAGES/django.po` files — wasted filesystem I/O and potential confusion if stale `.po` files exist in cache directories. The `--ignore` flags currently cover only `.venv`, `.git`, `.kilo`, `__pycache__`, `*.pyc` — missing the project's own tool caches.

The Makefile `compilemessages` target (L152-155) runs inside the `web` service with the `.:/app` bind-mount, so it has the same vulnerability.

For the **Dockerfile build** (L78) and **CI** (L83, L176), the `.dockerignore` already filters most of these, so the `--ignore` flags are less critical. However, CI runs on a fresh checkout without `.dockerignore` enforcement — the CI `compilemessages` at ci.yml L83 uses `working-directory: src/backend`, which means `LOCALE_PATHS` resolves to `src/backend/locale` relative to `src/backend/`, and the recursive walk would start from `src/backend/` and look for `LC_MESSAGES/django.po` in all subdirectories including `.mypy_cache`, `.pytest_cache`, etc. if they exist in `src/backend/`.

**Recommendation:**
1. Add comprehensive `--ignore` flags to the entrypoint and Makefile `compilemessages`:
   ```bash
   --ignore=.venv --ignore=.git --ignore=.kilo --ignore=__pycache__ --ignore='*.pyc' \
   --ignore=.mypy_cache --ignore=.ruff_cache --ignore=.pytest_cache --ignore=node_modules \
   --ignore=.tox --ignore=.nox --ignore=__pypackages__ --ignore=.uv --ignore=.cache
   ```
2. Add `--ignore` and `--locale` flags to the Dockerfile build step (L78) and CI steps for consistency.
3. Consider tracking this as a Django upstream enhancement — there is a Django ticket (#37188) requesting a `--gitignore` flag for `compilemessages` to automatically respect `.gitignore` patterns.

**Risk level:** Medium — unnecessary filesystem traversal at every container startup in dev mode; potential stale `.po` compilation from cache dirs.

---

### 17. `compilemessages` in Dockerfile Build: Missing `--locale` Restriction

**File:** `Dockerfile` L78

**Current state (verified on disk):**
```dockerfile
RUN ... uv run python src/backend/manage.py compilemessages
```
No `--locale` flags. The entrypoint (L76-77) uses `--locale ru --locale bs --locale en`.

**Best practice:**
The `compilemessages` command, with no `--locale` restriction, compiles ALL `django.po` files found in `LOCALE_PATHS`. Since the project only supports three languages (`ru`, `bs`, `en` per base.py L57-61), adding `--locale` flags makes the build explicit and prevents accidental compilation of `.po` files that might exist in other locale directories (e.g., from a stale branch or partial checkout).

**Relevance to this project:**
Step 1 section 7 (L624) notes: "Django's `compilemessages` command recursively walks `LOCALE_PATHS` for `LC_MESSAGES/django.po` files and compiles each to `django.mo`." The `.po` files are committed to Git (Step 1 L868-870). In the Docker build context, `.dockerignore` already excludes `.kilo/` (preventing stale worktree locales), but without `--locale` flags, if any stray `.po` file existed in an unexpected locale directory, it would be compiled. Adding `--locale ru --locale bs --locale en` to the Dockerfile build step makes the build deterministic and consistent with the entrypoint (L77) and Makefile (L155).

**Risk level:** Low — the current setup works correctly because only three locale directories exist. The `--locale` flags add defensive explicitness.

---

### 18. `uv`/`uvx` Binaries in Runtime Image: Necessity Assessment

**File:** `Dockerfile` L110-111

**Current state (verified on disk):**
```dockerfile
COPY --from=builder /usr/local/bin/uv /usr/local/bin/uv
COPY --from=builder /usr/local/bin/uvx /usr/local/bin/uvx
```
Comment (L109): "Copy uv binary from builder (needed for dev mode `uv run` commands and entrypoint scripts)"

**Best practice (from official uv docs):**
The uv Docker guide recommends removing `uv` from the final image when it's not needed, using either:
1. `--mount=from=ghcr.io/astral-sh/uv` (temporary mount for build-time commands)
2. `ENV VIRTUAL_ENV=/opt/venv` + `ENV PATH="/opt/venv/bin:$PATH"` (direct PATH activation, no `uv run` needed)

**Relevance to this project:**
All five entrypoint scripts invoke `uv run`:
- `entrypoint.sh` L75: `uv run python .../manage.py compilemessages`
- `entrypoint-catalog.sh` L17: `uv run python .../manage.py load_catalog`
- `entrypoint-seed.sh` L32: `uv run python .../manage.py seed`
- `entrypoint-create-admin.sh` L24: `uv run python .../manage.py create_admin_user`
- `entrypoint-scheduler.sh` L21: `uv run python -c "..."`
- `cmd` at Dockerfile L155: `gunicorn` (direct, no `uv run`)

The `UV_NO_INSTALL_PROJECT=1` and `UV_FROZEN=1` (Dockerfile L137-138) make `uv run` a fast no-op sync (deps already in venv, no network). However, this still requires the `uv` binary to be present.

**Options to remove `uv` from runtime:**
1. **Replace `uv run` with direct venv activation:** Change entrypoint scripts to use `/opt/venv/bin/python` instead of `uv run python`. This eliminates the `uv` dependency entirely from the runtime image.
2. **Use `VIRTUAL_ENV` env var:** Set `ENV VIRTUAL_ENV=/opt/venv` so that `python` resolves to the venv without `uv run`. This is the pattern shown in the uv docs (Section "Using the environment").

However, the entrypoint scripts are **shared** between the production image (from Dockerfile L124) and the dev/test bind-mounts. In dev/test, the `.:/app` bind-mount shadows the image's `/app` directory, so the scripts come from the host. If the scripts are changed to `/opt/venv/bin/python`, they'd work in both prod (venv exists in image) and dev (venv exists via bind-mount shadowing).

But there's a subtlety: in dev mode, the bind-mount `.:/app` shadows `/app`, but `/opt/venv` is NOT shadowed. So `/opt/venv/bin/python` would work in both dev and prod. The only concern is whether `uv run` does anything beyond activating the venv — with `UV_NO_INSTALL_PROJECT=1` and `UV_FROZEN=1`, it should just be `python` with the venv activated.

**Risk level:** Medium design decision — removing `uv` saves ~30 MB (the `uv` binary is 20-30 MB depending on architecture) and reduces attack surface, but requires modifying 5 entrypoint scripts. The project's current approach (keeping `uv`) is the safer choice for now, as it preserves the `uv run` pattern that ensures correct venv activation.

---

### 19. `tailwindcss` Binary in Runtime Image: Correct for Dev

**File:** `Dockerfile` L108

**Current state (verified on disk):**
```dockerfile
COPY --from=builder /usr/local/bin/tailwindcss /usr/local/bin/tailwindcss
```
Comment (L107): "Copy tailwindcss binary from builder (needed for dev mode CSS generation)"

**Best practice:**
The `tailwindcss` standalone binary (~20 MB) is only needed in development (the `web` service runs `tailwindcss -i ... -o ...` via `runserver` in docker-compose.dev.override.yml L7-9). In production, CSS is pre-built at Dockerfile L76 and the binary is never invoked.

**Relevance to this project:**
The dev compose override (docker-compose.dev.override.yml L22) bind-mounts `.:/app`, which shadows the `/app` directory but does NOT shadow `/usr/local/bin/tailwindcss`. So the binary from the image IS used in dev mode. Without it, `make up` would fail with "tailwindcss: command not found" in the `web` service's dev command. Removing it would break dev workflow.

However, there's a subtlety: the `migrate`, `load_catalog`, `create_admin`, `seed`, and `scheduler` services also use the same image. None of these services need `tailwindcss`. But since they use the same Dockerfile, the binary is present in all. This is a minor inefficiency — the binary could be copied only for the `web` service by using a target-specific `COPY` in a separate stage, but this adds complexity without meaningful benefit.

**Recommendation:** Keep as-is. The binary is needed for dev mode and the cost of removing it (separate build stage or conditional copy) outweighs the ~20 MB saved.

---

### 20. `.env*` Pattern in `.dockerignore`: Correct Scope

**File:** `.dockerignore` L5 (`.env*`)

**Current state (verified on disk):**
The `.env*` pattern matches ALL files starting with `.env` at any directory level:
- Root: `.env`, `.env.docker`, `.env.local`, `.env.example`, `.env.dev.example`, `.env.docker.example`
- `src/`: `src/.env` (0-byte placeholder, Step 1 L929)
- `src/backend/`: `src/backend/.env` (1034 bytes, gitignored L149)

**Best practice:**
The techearl.com best-practices guide (May 2026) recommends `.env*` in `.dockerignore` to prevent all environment files from entering the image, even example templates. This is correct.

**Relevance to this project:**
Step 1 Finding 4 (L1016-1017) confirms: env files are excluded from the Docker build context and bind-mounted at runtime via `volumes: - ./.env.docker:/app/src/.env:ro` in compose. The `.env.example` templates (git-tracked, for developer reference) are correctly excluded — they have no value inside a container image. The `SKIP_ENV_CHECK=1` env var (docker-compose.test.yml L67) allows the test environment to skip the `.env` existence check when `.env.docker` is not bind-mounted. This is a correct and intentional design.

**Risk level:** None — correct practice. No change needed.

**Note on `.gitignore` divergence:**
The `.gitignore` (L145-148) explicitly excludes `.env`, `.env.dev`, `.env.local`, `.env.docker` (specific patterns) while keeping `.env.example`, `.env.dev.example`, `.env.docker.example` (templates). The `.dockerignore` `.env*` pattern is broader (excludes templates too). This divergence is intentional and correct — `.gitignore` keeps templates for developer onboarding, `.dockerignore` keeps all env files (including templates) out of the image.

---

### 21. Multi-Stage Build Architecture: Already Correct

**File:** `Dockerfile` (3 stages: builder → runtime → test-runtime)

**Current state (verified on disk):**
- **Stage 1 (`builder`):** `python:3.14-slim` + uv + production deps + Tailwind build + collectstatic + compilemessages
- **Stage 2 (`runtime`):** `python:3.14-slim` + venv + source + staticfiles + entrypoint scripts (NO gcc, NO libpq-dev, NO curl download tools)
- **Stage 3 (`test-runtime`):** inherits `runtime`, adds `--group dev` (pytest, ruff, basedpyright, djlint)

**Best practice (from uv docs and general Docker guidance):**
Multi-stage builds are the recommended approach for production images. The builder stage contains build tools; the runtime stage contains only what's needed to run.

**Relevance to this project:**
The architecture is correct per all sources:
1. The builder stage installs `gcc`-equivalent tools implicitly via uv (psycopg[binary] is pre-compiled, so no `gcc`/`libpq-dev` needed — confirmed by Dockerfile comment L11-12).
2. The `gettext` package is installed in BOTH stages (L20 in builder, L94 in runtime) — the runtime needs it for `compilemessages` at container startup (entrypoint.sh L75). This is correct: `compilemessages` requires the `msgfmt` binary from `gettext`.
3. The runtime stage installs `libpq5` (L90) — the shared library for psycopg3 (binary), but NOT `libpq-dev` (the development headers). This is correct.
4. `curl` in the runtime stage (L91) is used for the health check (L151-152). This is a tradeoff — `curl` could be replaced by a pure-Python health check, but `curl` is small on `slim` images and the pattern is standard.
5. The `test-runtime` stage correctly only adds dev deps, inheriting all production artifacts. Step 1 Finding 1 (L1003-1004) correctly notes this.

**Risk level:** None — already follows best practices.

---

### 22. apt Cache Cleanup: Already Correct

**File:** `Dockerfile` L21, L95

**Current state (verified on disk):**
Both apt `RUN` blocks use:
```dockerfile
--mount=type=cache,target=/var/cache/apt,sharing=locked \
--mount=type=cache,target=/var/lib/apt,sharing=locked \
apt-get update && apt-get install -y --no-install-recommends \
... \
&& rm -rf /var/lib/apt/lists/*
```

**Best practice:**
The Dockerfile best-practices guide recommends:
1. `--no-install-recommends` to avoid unnecessary packages
2. `rm -rf /var/lib/apt/lists/*` to clean apt cache after install
3. `--mount=type=cache` for `/var/cache/apt` and `/var/lib/apt` to improve build caching

**Relevance to this project:**
The project already implements all three. The `sharing=locked` mount option (L15) ensures cache mounts are not shared between stages, preventing cross-stage contamination. This is correct and follows Docker BuildKit best practices.

**Risk level:** None — already correct.

---

### 23. `compilemessages` `--ignore=*.mo` Consideration

**File:** `Dockerfile` L78, `entrypoint.sh` L76, `Makefile` L154

**Best practice:**
Since `.mo` files are gitignored (and the recommendation in Practice 1 is to add them to `.dockerignore`), `compilemessages` should also be instructed to `--ignore=*.mo` to prevent it from trying to parse `.mo` files as if they were `.po` files (though in practice, Django's `compilemessages` only processes `.po` files and ignores `.mo` files automatically).

**Relevance to this project:**
Django's `compilemessages` command uses `gettext` tools (`msgfmt`) and only processes `*.po` files — it does not traverse or read `*.mo` files. So `--ignore=*.mo` is not strictly needed. However, if `.mo` files exist in the build context (as they do locally), they would be copied into the image via `COPY . .` and then overwritten by `compilemessages`. Excluding them from `.dockerignore` (Practice 1) is the better solution.

---

### 24. `Makefile` `compilemessages` Target: Align `--ignore` Flags

**File:** `Makefile` L152-155

**Current state (verified on disk):**
```makefile
compilemessages:
	docker compose $(COMPOSE_FILES) run --rm web uv run python src/backend/manage.py compilemessages \
		--ignore=.venv --ignore=.git --ignore=.kilo --ignore=__pycache__ --ignore='*.pyc' \
		--locale ru --locale bs --locale en
```

The `Makefile` `compilemessages` target shares the same incomplete `--ignore` list as the entrypoint. This is the same issue as Practice 16 — the `--ignore` list should be expanded to cover all tool cache directories.

**Recommendation:**
Update both the `Makefile` and `entrypoint.sh` `--ignore` flags to be consistent and comprehensive.

---

## Cross-Reference: Key Architecture-Specific Observations

### Build-time vs. Runtime Separation (Step 1 Finding 1)

The project's 3-stage Dockerfile correctly separates build-time tools from runtime:
- **Builder stage** has: `gcc`-equivalent (via uv), `gettext`, `curl` (for Tailwind download). These are NOT in the runtime stage.
- **Runtime stage** has: `gettext` (needed for runtime `compilemessages` in entrypoint.sh), `libpq5` (psycopg3 shared lib), `curl` (health check). No compilers.
- This is the standard pattern recommended by the Docker best-practices guide and the uv Docker integration guide.

### The "Project Not Installed" Design (Step 1 Finding 7)

The project uses `PYTHONPATH=/app/src:/app/src/backend` (Dockerfile L62, L140) instead of `pip install -e .` or `uv sync` (which installs the project). This means `COPY . .` must include the full source tree — there's no way to narrow it without risking missing app templates or locale files. The `default-groups = []` setting (pyproject.toml L196) correctly excludes dev deps from production sync. `UV_NO_INSTALL_PROJECT=1` (Dockerfile L137) prevents `uv` from trying to install the project package at runtime.

### CI vs Docker Context Differences

The CI workflow (ci.yml) runs `compilemessages` without `--ignore` flags (L83, L176) and without `--locale` flags. This is less critical in CI because:
1. CI uses `actions/checkout@v4` which checks out a clean repo (no local tool caches like `.mypy_cache` unless generated by prior CI steps)
2. But the CI `compilemessages` runs at `working-directory: src/backend` (L84), so `LOCALE_PATHS` resolves relative to `src/backend/` — and `.mypy_cache`, `.pytest_cache` etc. could exist there if `basedpyright` or `pytest` ran in earlier steps in the same job (they do — `basedpyright` runs in the `typecheck` job, but the `i18n` job is separate and has no prior cache-generating steps). The risk is low but non-zero.

---

## Action Priority Matrix

| Priority | Practices |
|----------|-----------|
| **P0 — Immediate (Security/Risk)** | #6 (`seed-images-config.json` API keys), #7 (`backups/` directory), #2 (stray root files), #1 (`.mo` files) |
| **P1 — Short-term (Best Practice Gaps)** | #9 (missing tool caches), #11 (coverage artifacts), #12 (runtime artifacts), #16 (`compilemessages` ignore completeness), #3 (`.gitattributes`), #4 (`.python-version`), #5 (scripts temp artifacts), #8 (`.local/`) |
| **P2 — Design Evaluation** | #18 (uv/uvx in runtime), #19 (tailwindcss in runtime), #14 (narrowing `COPY . .`) |
| **P3 — Already Correct (Verify)** | #13 (dependency layer caching), #15 (dead pattern), #17 (locale restriction), #20 (`.env*` scope), #21 (multi-stage), #22 (apt cleanup), #23 (.mo ignore in compilemessages) |

---

## References

1. **Official uv Docker Guide:** https://docs.astral.sh/uv/guides/integration/docker/ (accessed 2026-08-29)
   - Cache mount for uv: `--mount=type=cache,target=/root/.cache/uv`
   - `UV_LINK_MODE=copy` for cross-filesystem cache compatibility
   - `UV_COMPILE_BYTECODE=1` for faster startup
   - Intermediate layers: `--no-install-project` for dependency layer caching
   - Multi-stage: remove `uv` from final image when using `VIRTUAL_ENV` pattern
   - Pin uv version (e.g., `ghcr.io/astral-sh/uv:0.12.7`)
   - `.venv` in `.dockerignore` to prevent local platform venv contamination

2. **Docker `.dockerignore` Best Practices:** https://techearl.com/blog/dockerignore-best-practices/ (May 2026)
   - `.env*` to exclude all env files including templates
   - `.gitattributes` exclusion
   - Pattern syntax differences from `.gitignore`
   - Negation patterns and ordering

3. **Django `.dockerignore` Template:** https://dockerignore.com/dockerignores/frameworks-django
   - Excludes `*.mo`, `*.pot` (build artifacts)
   - Excludes `**/.venv/`, `**/.tox/`, `**/.mypy_cache/`, etc.
   - Excludes `**/.env*` and secrets

4. **Django Docker Best Practices:** https://betterstack.com/community/guides/scaling-python/django-docker-best-practices/ (Feb 2025)
   - Multi-stage builds, non-root user, `.dockerignore`, pinned versions

5. **Django Ticket #37188:** `compilemessages` should ignore common environment and dependency directories by default — https://code.djangoproject.com/ticket/37188

6. **Project source files verified:**
   - `.dockerignore` (63 lines, on disk)
   - `docker/Dockerfile` (168 lines, on disk)
   - `pyproject.toml` (227 lines, on disk)
   - `Makefile` (231 lines, on disk)
   - `docker/entrypoint.sh` (92 lines, on disk)
   - `docker/entrypoint-test.sh` (41 lines, on disk)
   - `docker/entrypoint-seed.sh` (34 lines, on disk)
   - `docker/entrypoint-catalog.sh` (17 lines, on disk)
   - `docker/entrypoint-create-admin.sh` (28 lines, on disk)
   - `docker/entrypoint-scheduler.sh` (66 lines, on disk)
   - `src/backend/config/settings/base.py` (253 lines, on disk)
   - `src/backend/config/settings/prod.py` (51 lines, on disk)
   - `src/backend/config/settings/dev.py` (44 lines, on disk)
   - `src/backend/config/settings/test.py` (78 lines, on disk)
   - `.gitignore` (236 lines, on disk)
   - `docker-compose.yml` (210 lines, on disk)
   - `docker-compose.dev.override.yml` (93 lines, on disk)
   - `docker-compose.test.yml` (78 lines, on disk)
   - `docker-compose.prod.yml` (121 lines, on disk)
   - `.github/workflows/ci.yml` (184 lines, on disk)
   - `.github/workflows/ci-nightly.yml` (82 lines, on disk)
   - Root directory listing (verified: `cat_output.txt`, `neq`, `Continue`, `cmp_css.py`, `.coverage`, `backups/`, `.local/`, etc.)
   - `scripts/` directory (verified: `_tmp_pytest_run.txt`, `_tmp_pytest_out.txt`, `session_context.json`, `seed-images-config.json`)
   - `src/backend/locale/` directory (verified: `.mo` files exist for ru, bs, en)
