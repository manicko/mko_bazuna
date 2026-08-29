# Step 3 Audit Report: Docker Build Optimization Findings

**Audit Date:** 2026-08-29  
**Project Root:** `C:\py_dev\mko_bazuna`  
**Stack:** Python 3.14 / Django 5.2 LTS / PostgreSQL 18 / aiogram 3.x / uv / HTMX MPA  
**Source Reports:** `ai/step1-baseline.md` (verified on-disk evidence), `ai/step2-bestpractices.md` (best-practice benchmarks)  
**Confidence Level:** HIGH — all file paths, sizes, and line numbers verified against source files on disk.

---

## Scope and Methodology

This audit classifies each Docker-build-optimization practice as **correctly implemented**, **missing**, or **suboptimal**, based on the Step 2 best-practices report cross-referenced with live filesystem verification. P3 ("Already Correct") practices from Step 2 are excluded per task instructions.

### Excluded as P3 (Already Correct, verified on disk)
| Step 2 Practice | Reason for exclusion |
|---|---|
| #13 Dependency file layer caching (`COPY pyproject.toml uv.lock* ./` before `COPY . .`) | Follows official uv docs; correct pattern |
| #14 Narrowing `COPY . .` | Correctly assessed as unnecessary — project is PYTHONPATH-based, not pip-installed; narrowing adds fragility |
| #15 Dead `.dockerignore` pattern `src/backend/mko_bazuna` | P3 low-priority; harmless dead pattern |
| #17 Dockerfile `compilemessages` missing `--locale` | P3 — low risk; only 3 locale dirs exist, build is deterministic |
| #19 `tailwindcss` binary in runtime | Correctly required for dev mode `runserver` CSS rebuild |
| #20 `.env*` scope in `.dockerignore` | Correct — broad `.env*` prevents all env files entering context |
| #21 Multi-stage build architecture (builder → runtime → test-runtime) | Correct separation; dev tools excluded from runtime |
| #22 apt cache cleanup (`rm -rf /var/lib/apt/lists/*` + cache mounts) | Already correct |
| #23 `compilemessages --ignore=*.mo` | Django only processes `.po` files; `.mo` exclusion handled at `.dockerignore` level |

### New findings discovered through on-disk verification (beyond Step 2)
- `.playwright-mcp/` (~701 KB on disk) is gitignored but NOT dockerignored
- `docker/nginx/` configs (~12 KB) are not consumed by the Docker build but enter the context because `docker/` must be included for `COPY docker/entrypoint*.sh`

---

## Summary

| ID | Title | Classification | Impact Category |
|----|-------|---------------|-----------------|
| F01 | `scripts/seed-images-config.json` (API keys) not in `.dockerignore` | missing | security |
| F02 | `backups/` directory not in `.gitignore` or `.dockerignore` | missing | security |
| F03 | Stray root-level dev artifacts not in `.dockerignore` | missing | build context |
| F04 | `.local/` directory not in `.dockerignore` | missing | build context |
| F05 | `scripts/` temp/profiling artifacts not in VCS or `.dockerignore` | missing | build context |
| F06 | `.playwright-mcp/` not in `.dockerignore` | missing | build context |
| F07 | `docker/nginx/` configs not in `.dockerignore` | missing | build context |
| F08 | `uv`/`uvx` binaries in runtime image (~30 MB) | suboptimal | image contents |
| F09 | `.mo`/`.pot` compiled translations not in `.dockerignore` | missing | build artifacts |
| F10 | `.gitattributes` not in `.dockerignore` | missing | build artifacts |
| F11 | `.python-version` not in `.dockerignore` | missing | build artifacts |
| F12 | Missing standard Python tool cache dirs in `.dockerignore` | missing | caches |
| F13 | Missing build artifacts (`*.manifest`, `*.spec`) in `.dockerignore` | missing | build artifacts |
| F14 | Missing coverage/test artifacts in `.dockerignore` | missing | build artifacts |
| F15 | Missing runtime artifacts in `.dockerignore` | missing | build artifacts |
| F16 | `compilemessages` `--ignore` list incomplete in entrypoint + Makefile | suboptimal | tooling efficiency |
| F17 | `compilemessages` in Dockerfile + CI lacks `--ignore`/`--locale` flags | suboptimal | tooling efficiency |

---

## Category 1: Docker Build Context (exclude files before they reach build context)

### F01: `scripts/seed-images-config.json` (API keys) not in `.dockerignore`

| Field | Detail |
|---|---|
| **Classification** | missing |
| **File(s) affected** | `.dockerignore` (no entry); `scripts/seed-images-config.json` (446 B, verified on disk) |
| **Current state** | Gitignored at `.gitignore` L225 but NOT in `.dockerignore`. `COPY . .` (Dockerfile L57) includes it in the build context. |
| **Best practice** | `.dockerignore` must mirror `.gitignore` for all files containing secrets/credentials. The Docker build context is independent of Git — gitignored files still enter the context. |
| **Gap** | Unsplash/Pexels API keys in `seed-images-config.json` are baked into every container image built by any developer who has a local copy. This is a confirmed credential leak vector. |
| **Actionable improvement** | Add `scripts/seed-images-config.json` to `.dockerignore`. |
| **Impact category** | security |
| **Step 2 reference** | Practice #6 (P0 — Immediate) |

### F02: `backups/` directory not in `.gitignore` or `.dockerignore`

| Field | Detail |
|---|---|
| **Classification** | missing |
| **File(s) affected** | `.gitignore` (no entry); `.dockerignore` (no entry); `backups/` directory (exists on disk, currently empty) |
| **Current state** | The `Makefile` `backup` target (Makefile L199-206) writes `dump_*.dump` PostgreSQL dump files to `./backups/`. Neither `.gitignore` nor `.dockerignore` excludes this directory. |
| **Best practice** | Database dump directories must be excluded from both VCS and Docker build context — dumps may contain PII (phone numbers, ad content). |
| **Gap** | If `make backup` has been run locally, dump files containing production data would enter the Docker build context via `COPY . .` (Dockerfile L57) and be baked into the image. |
| **Actionable improvement** | Add `backups/` to both `.gitignore` and `.dockerignore`. |
| **Impact category** | security |
| **Step 2 reference** | Practice #7 (P0 — Immediate) |

### F03: Stray root-level dev artifacts not in `.dockerignore`

| Field | Detail |
|---|---|
| **Classification** | missing |
| **File(s) affected** | `.dockerignore` (no entries for these files); root files: `cat_output.txt` (3284 B), `neq` (36 B), `Continue` (0 B), `cmp_css.py` (654 B) — all verified on disk, all git-tracked |
| **Current state** | None of these files are excluded by `.dockerignore`. All are included in the build context via `COPY . .` (Dockerfile L57). |
| **Best practice** | One-off debug scripts, debug output files, and unidentified files should not enter production container images. |
| **Gap** | `cat_output.txt` (debug output, 3284 B) and `neq` (unknown purpose, 36 B) are git-tracked and baked into every image. `cmp_css.py` (654 B) is a one-off CSS comparison script not referenced by any Dockerfile instruction or entrypoint script. |
| **Actionable improvement** | Add `cat_output.txt`, `neq`, `Continue`, `cmp_css.py` to `.dockerignore`. Additionally, review these files for `.gitignore` inclusion — they should likely not be tracked in VCS at all. |
| **Impact category** | build context |
| **Step 2 reference** | Practice #2 (P0 — Immediate) |

### F04: `.local/` directory not in `.dockerignore`

| Field | Detail |
|---|---|
| **Classification** | missing |
| **File(s) affected** | `.gitignore` (no entry); `.dockerignore` (no entry); `.local/` directory (exists on disk, contains `share/` subdirectory) |
| **Current state** | `.local/` is not excluded from the Docker build context. |
| **Best practice** | User-local Python installations (pyenv, pipx, pip user installs) should not enter container images. The base image `python:3.14-slim` + uv-managed venv provide all needed Python. |
| **Gap** | `.local/` may contain large platform-specific Python builds (hundreds of MB if pyenv is used), unnecessarily bloating build context transfer. |
| **Actionable improvement** | Add `.local/` to `.dockerignore`. |
| **Impact category** | build context / build time |
| **Step 2 reference** | Practice #8 (P1 — Short-term) |

### F05: `scripts/` temp/profiling artifacts not in `.gitignore` or `.dockerignore`

| Field | Detail |
|---|---|
| **Classification** | missing |
| **File(s) affected** | `.gitignore` (no entries); `.dockerignore` (no entries); `scripts/_tmp_pytest_run.txt` (193,180 B), `scripts/_tmp_pytest_out.txt` (16,660 B), `scripts/session_context.json` (92,743 B) — all verified on disk |
| **Current state** | Not excluded from build context or VCS. ~302 KB of profiling/debug output enters the build context on every `COPY . .` (Dockerfile L57). |
| **Best practice** | Temp/profiling artifacts should be in both `.gitignore` and `.dockerignore`. Neither file currently excludes them. |
| **Gap** | 300 KB of unnecessary context transfer per build; profiling data may contain internal test state or conversation metadata. |
| **Actionable improvement** | Add `scripts/_tmp_*.txt` and `scripts/session_context.json` to both `.gitignore` and `.dockerignore`. |
| **Impact category** | build context / build time |
| **Step 2 reference** | Practice #5 (P1 — Short-term) |

### F06: `.playwright-mcp/` not in `.dockerignore`

| Field | Detail |
|---|---|
| **Classification** | missing |
| **File(s) affected** | `.gitignore` L233 (`.playwright-mcp/*`); `.dockerignore` (no entry); `.playwright-mcp/` directory (exists on disk, ~701 KB across 3 files) |
| **Current state** | Gitignored but NOT dockerignored. Contents (~684 KB) enter the Docker build context via `COPY . .` (Dockerfile L57). |
| **Best practice** | Tool output/caches that are gitignored must also be dockerignored — Docker does not read `.gitignore`. |
| **Gap** | ~701 KB of Playwright MCP browser/runtime artifacts transferred per build; not needed in the image. |
| **Actionable improvement** | Add `.playwright-mcp/` to `.dockerignore`. |
| **Impact category** | build context / build time |
| **Step 2 reference** | Not explicitly listed in Step 2 (discovered through on-disk verification); aligns with Practice #9 category (missing tool caches) |

### F07: `docker/nginx/` configs not in `.dockerignore`

| Field | Detail |
|---|---|
| **Classification** | missing |
| **File(s) affected** | `.dockerignore` (no entry for `docker/nginx/`); `docker/nginx/nginx.conf` (6273 B), `docker/nginx/nginx.dev.conf` (5860 B) — verified on disk |
| **Current state** | The `docker/` directory must be in the build context for `COPY docker/entrypoint*.sh /app/` (Dockerfile L124). But `docker/nginx/` subdirectory contains nginx configs that are NOT consumed by any Dockerfile instruction. They are only bind-mounted at runtime by the `nginx` compose service (`docker-compose.yml` L203: `./docker/nginx/nginx.conf:/etc/nginx/nginx.conf:ro`). |
| **Best practice** | Exclude files from the build context that are not consumed by any Docker build instruction. |
| **Gap** | ~12 KB of nginx config files enter the build context unnecessarily on every build. While small, the principle matters — these files are purely runtime bind-mounts, never baked into the image. |
| **Actionable improvement** | Add `docker/nginx/` to `.dockerignore`. The `docker/entrypoint*.sh` files will still be included because `COPY docker/entrypoint*.sh` requires the `docker/` directory. |
| **Impact category** | build context |
| **Step 2 reference** | Falls under Practice #14 category (Dockerfile input precision) |

---

## Category 2: Dockerfile Inputs (narrow broad `COPY`/`ADD`)

**No findings.** The Dockerfile's `COPY` instructions are already optimally scoped:

- `COPY pyproject.toml uv.lock* ./` (L37) — correct split for dependency layer caching; first `COPY` of source files.
- `COPY . .` (L57) — correct for a PYTHONPATH-based (non-pip-installed) project; narrowing adds fragility without benefit per official uv docs.
- `COPY --chown=app:app docker/entrypoint*.sh /app/` (L124) — already narrowed to only entrypoint scripts.
- `COPY --from=builder` instructions in runtime stage (L106, L108, L110-111, L114, L119, L121) — each copies a specific artifact from the builder; no overly broad `COPY`.
- No `ADD` instructions exist (only `COPY`).

The `COPY . .` at L57 is the single broad instruction, but it is the correct pattern: `.dockerignore` handles the filtering, and the project's PYTHONPATH-based layout requires all source files. The dependency layer (L37 → L47-49) is correctly separated for cache invalidation isolation.

---

## Category 3: Runtime Dependencies (prevent dev/test/build-only packages in production images)

### F08: `uv`/`uvx` binaries in runtime image (~30 MB unnecessary)

| Field | Detail |
|---|---|
| **Classification** | suboptimal |
| **File(s) affected** | `docker/Dockerfile` L110-111 (copies `uv` and `uvx` from builder to runtime stage); all entrypoint scripts |
| **Current state** | The runtime stage copies `uv` (~20–30 MB) and `uvx` binaries from the builder (Dockerfile L110-111, comment at L109: "needed for dev mode `uv run` commands and entrypoint scripts"). Five entrypoint scripts invoke `uv run python ...`: `entrypoint-catalog.sh` L17, `entrypoint-create-admin.sh` L24, `entrypoint-seed.sh` L18/L32, `entrypoint-scheduler.sh` L21, `entrypoint-test.sh` L16/L19-20/L41. The main `CMD` (L155) invokes `gunicorn` directly via `PATH="/opt/venv/bin:${PATH}"` (L128). `entrypoint.sh` itself already uses `/opt/venv/bin/python` directly (L41, L60, L75). |
| **Best practice** | Only include binaries needed at runtime. The `uv` binary can be removed from the production runtime stage if entrypoint scripts use direct venv invocation instead of `uv run`. |
| **Gap** | Inconsistency: `entrypoint.sh` (the primary web entrypoint) already uses `/opt/venv/bin/python` directly, but four auxiliary entrypoint scripts still use `uv run python`. This forces `uv`/`uvx` to be copied into the production runtime image (~30 MB), increasing attack surface. The `test-runtime` stage legitimately needs `uv` for `uv sync --group dev` (entrypoint-test.sh L16), but that could be a separate `COPY` only in the test stage. |
| **Actionable improvement** | Either (a) replace `uv run python` with `/opt/venv/bin/python` in `entrypoint-catalog.sh`, `entrypoint-create-admin.sh`, `entrypoint-seed.sh`, and `entrypoint-scheduler.sh`, then move the `uv`/`uvx` `COPY` from the `runtime` stage to only the `test-runtime` stage; or (b) set `ENV VIRTUAL_ENV=/opt/venv` so `python` resolves to the venv without `uv run`. The existing pattern in `entrypoint.sh` (direct venv path) proves this is feasible. |
| **Impact category** | image contents |
| **Step 2 reference** | Practice #18 (P2 — Design Evaluation) |

---

## Category 4: Build Artifacts and Caches (prevent/remove caches, temp files, generated artifacts)

### F09: `.mo`/`.pot` compiled translations not in `.dockerignore`

| Field | Detail |
|---|---|
| **Classification** | missing |
| **File(s) affected** | `.gitignore` L55-56 (has `*.mo`, `*.pot`); `.dockerignore` (no entry); three `.mo` files verified on disk: `src/backend/locale/ru/LC_MESSAGES/django.mo` (29,528 B), `src/backend/locale/bs/LC_MESSAGES/django.mo` (22,294 B), `src/backend/locale/en/LC_MESSAGES/django.mo` (387 B) |
| **Current state** | `.mo` files are gitignored but NOT dockerignored. They enter the build context via `COPY . .` (Dockerfile L57) and are then overwritten by `compilemessages` at Dockerfile L78. `.po` files (which ARE needed) are correctly not excluded. |
| **Best practice** | Compiled translation files should be excluded from the Docker build context — they are regenerated at build time and their presence risks stale translations being baked in if `compilemessages` fails. |
| **Gap** | ~51 KB of stale `.mo` files transferred per build; if `compilemessages` were ever skipped or failed, stale host translations would be served in the image. |
| **Actionable improvement** | Add `*.mo` and `*.pot` to `.dockerignore`. |
| **Impact category** | build artifacts / security (stale data) |
| **Step 2 reference** | Practice #1 (P0 — Immediate) |

### F10: `.gitattributes` not in `.dockerignore`

| Field | Detail |
|---|---|
| **Classification** | missing |
| **File(s) affected** | `.gitignore` (no entry); `.dockerignore` (no entry); `.gitattributes` (302 B, verified on disk, git-tracked) |
| **Current state** | `.gitattributes` contains LF line-ending rules for `.sh`, `.json`, `.yaml`, `.css`, `.lock` files. It is included in the Docker build context via `COPY . .` (Dockerfile L57). |
| **Best practice** | Git-only configuration files (line-ending normalization, path-rewrite rules) have no relevance inside a Docker image and should be excluded. |
| **Gap** | 302 bytes of Git-only configuration needlessly transferred into every build context. Also a credential hygiene concern — `.gitattributes` can contain path-rewrite rules that should remain Git-local. |
| **Actionable improvement** | Add `.gitattributes` to `.dockerignore`. |
| **Impact category** | build artifacts |
| **Step 2 reference** | Practice #3 (P1 — Short-term) |

### F11: `.python-version` not in `.dockerignore`

| Field | Detail |
|---|---|
| **Classification** | missing |
| **File(s) affected** | `.gitignore` L88 (commented out — convention is to commit it); `.dockerignore` (no entry); `.python-version` (5 B, content: `3.14`, verified on disk, git-tracked) |
| **Current state** | `.python-version` is git-tracked and enters the Docker build context via `COPY . .` (Dockerfile L57). The base image `python:3.14-slim` (Dockerfile L8, L84) already provides Python 3.14. |
| **Best practice** | The Python version pin file is only consumed by pyenv/version managers at local dev time. Inside the container, there is no pyenv, and uv uses its own managed Python or the system Python from the base image. |
| **Gap** | 5 bytes of irrelevant metadata in the build context. If `uv` were ever configured to read `.python-version` (via `UV_PYTHON_PREFERENCE`), the file's presence could cause unexpected Python resolution behavior. |
| **Actionable improvement** | Add `.python-version` to `.dockerignore`. |
| **Impact category** | build artifacts |
| **Step 2 reference** | Practice #4 (P1 — Short-term) |

### F12: Missing standard Python tool cache directories in `.dockerignore`

| Field | Detail |
|---|---|
| **Classification** | missing |
| **File(s) affected** | `.gitignore` (has patterns at L41, L42, L50, L122, L170, L175, L178, L181); `.dockerignore` (has only `.ruff_cache/`, `.mypy_cache/`, `.pytest_cache/` at L58-60); missing: `.tox/`, `.nox/`, `.pyre/`, `.pytype/`, `__pypackages__/`, `.profile_default/` |
| **Current state** | `.gitignore` includes `.tox/` (L41), `.nox/` (L42), `.pyre/` (L175), `.pytype/` (L178), `__pypackages__/` (L122), `profile_default/` (L82). None of these are in `.dockerignore`. Only `.ruff_cache/`, `.mypy_cache/`, `.pytest_cache/` are dockerignored (L58-60). `.cache` is dockerignored (L38) and gitignored (L45). |
| **Best practice** | `.dockerignore` should cover the full set of standard Python tool cache directories to prevent them from ever entering the build context, regardless of which tools are run locally. |
| **Gap** | If a developer runs `tox`, `nox`, `pyre`, `pytype`, or pip with `__pypackages__`, the resulting cache directories (which can be large and platform-specific) would be included in the Docker build context via `COPY . .` (Dockerfile L57). The project uses `basedpyright` (not `mypy`), but `.mypy_cache` is still dockerignored — the project should align with its actual tooling and standard templates. |
| **Actionable improvement** | Add `.tox/`, `.nox/`, `.pyre/`, `.pytype/`, `__pypackages__/`, `.profile_default/`, `.pdbrc`, `.python-eggs/` to `.dockerignore`. |
| **Impact category** | caches |
| **Step 2 reference** | Practice #9 (P1 — Short-term) |

### F13: Missing build artifacts (`*.manifest`, `*.spec`) in `.dockerignore`

| Field | Detail |
|---|---|
| **Classification** | missing |
| **File(s) affected** | `.gitignore` L32-33 (has `*.manifest`, `*.spec`); `.dockerignore` (no entries); no `.manifest` or `.spec` files verified on disk |
| **Current state** | PyInstaller artifact patterns are gitignored but NOT dockerignored. No such files currently exist on disk. |
| **Best practice** | `.dockerignore` should cover all build artifact patterns from the standard Python `.gitignore` template for completeness and defensive coverage. |
| **Gap** | If PyInstaller or similar tooling is ever introduced, the resulting `*.manifest` and `*.spec` files would enter the build context. Currently no risk since no such files exist. |
| **Actionable improvement** | Add `*.manifest` and `*.spec` to `.dockerignore` for completeness. |
| **Impact category** | build artifacts |
| **Step 2 reference** | Practice #10 (P1 — Short-term) |

### F14: Missing coverage/test artifacts in `.dockerignore`

| Field | Detail |
|---|---|
| **Classification** | missing |
| **File(s) affected** | `.gitignore` L40-50 (has `htmlcov/`, `.coverage`, `.coverage.*`, `coverage.xml`, `.hypothesis/`); `.dockerignore` (no entries); `.coverage` file verified on disk (167,936 B) |
| **Current state** | Coverage and test artifacts are gitignored but NOT dockerignored. The `.coverage` file (168 KB) is confirmed present on disk and enters the build context via `COPY . .` (Dockerfile L57). |
| **Best practice** | Test/coverage artifacts should never enter container images — they contain test execution metadata (timing, internal paths, code structure) and waste context transfer bandwidth. |
| **Gap** | 168 KB of `.coverage` data transferred per build. If `coverage.xml`, `htmlcov/`, or `.hypothesis/` are generated locally before a build, they would also enter the context. |
| **Actionable improvement** | Add `.coverage`, `.coverage.*`, `coverage.xml`, `htmlcov/`, `.hypothesis/` to `.dockerignore`. |
| **Impact category** | build artifacts |
| **Step 2 reference** | Practice #11 (P1 — Short-term) |

### F15: Missing runtime artifacts in `.dockerignore`

| Field | Detail |
|---|---|
| **Classification** | missing |
| **File(s) affected** | `.gitignore` L125-136, L236 (has `celerybeat-schedule`, `celerybeat.pid`, `*.rdb`, `*.aof`, `*.pid`, `.gunicorn/`); `.dockerignore` (no entries for these); `.gunicorn/` directory verified on disk |
| **Current state** | Runtime lock files, PID files, and Redis persistence files are gitignored but NOT dockerignored. The `redis:7-alpine` service may produce `*.rdb`/`*.aof` files locally. The `.gunicorn/` directory (sockets, PID files, logs) exists on disk. |
| **Best practice** | Runtime artifacts (locks, PID files, sockets, database dumps from local services) must never be baked into container images — stale runtime state can cause startup failures. |
| **Gap** | If Redis or Gunicorn has been run locally prior to `docker build`, stale PID/sock/RDB files could enter the build context via `COPY . .` (Dockerfile L57) and be copied into the builder stage's `/app/` directory. While the runtime stage selectively copies only needed paths, the builder stage still carries this dead weight in an intermediate layer. |
| **Actionable improvement** | Add `celerybeat-schedule`, `celerybeat.pid`, `*.rdb`, `*.aof`, `*.pid`, `.gunicorn/` to `.dockerignore`. |
| **Impact category** | build artifacts |
| **Step 2 reference** | Practice #12 (P1 — Short-term) |

---

## Category 5: Related Tooling (prevent recursive processing of irrelevant directories)

### F16: `compilemessages` `--ignore` list incomplete in entrypoint and Makefile

| Field | Detail |
|---|---|
| **Classification** | suboptimal |
| **File(s) affected** | `docker/entrypoint.sh` L75-77; `Makefile` L152-155 |
| **Current state** | Both use identical, incomplete `--ignore` list: `--ignore=.venv --ignore=.git --ignore=.kilo --ignore=__pycache__ --ignore='*.pyc'`. Missing patterns that exist in `.gitignore`/`.dockerignore` and on disk: `.mypy_cache`, `.ruff_cache`, `.pytest_cache`, `node_modules`, `.tox`, `.nox`, `__pypackages__`, `.uv`, `.cache`, `.local`, `.playwright-mcp`, `.coverage`, `.hypothesis`. |
| **Best practice** | Django's `compilemessages` recursively walks `LOCALE_PATHS` (`src/backend/locale/` per `base.py` L62) looking for `LC_MESSAGES/django.po` files. The `--ignore` flags exclude directories from the recursive scan. The list should be comprehensive to prevent unnecessary filesystem I/O and potential stale `.po` compilation from cache directories. |
| **Gap** | In dev mode, the `.:/app` bind-mount (docker-compose.dev.override.yml L22) exposes the full repo inside the container. While `compilemessages` only walks `LOCALE_PATHS`, the incomplete `--ignore` list means that if any tool cache directory happens to contain a `LC_MESSAGES/django.po` subdirectory (e.g., from a stale branch or vendored dependency), it would be compiled. The list also diverges from `.dockerignore` coverage — tool caches that `.dockerignore` excludes from the image build are not excluded from the runtime `compilemessages` walk. The Makefile target runs in the same bind-mount environment, so it has the same vulnerability. |
| **Actionable improvement** | Expand the `--ignore` list in both `entrypoint.sh` (L76) and `Makefile` (L153-155) to cover all tool cache directories: `.mypy_cache`, `.ruff_cache`, `.pytest_cache`, `node_modules`, `.tox`, `.nox`, `__pypackages__`, `.uv`, `.cache`, `.local`, `.playwright-mcp`. Consider extracting the command into a shared script to ensure consistency. |
| **Impact category** | tooling efficiency |
| **Step 2 reference** | Practice #16 (P1 — Short-term); Practice #24 (Makefile same issue) |

### F17: `compilemessages` in Dockerfile build and CI lacks `--ignore`/`--locale` flags

| Field | Detail |
|---|---|
| **Classification** | suboptimal |
| **File(s) affected** | `docker/Dockerfile` L78; `.github/workflows/ci.yml` L83, L176 |
| **Current state** | Dockerfile L78: `uv run python src/backend/manage.py compilemessages` — no `--ignore` or `--locale` flags. CI ci.yml L83 and L176: `uv run python manage.py compilemessages` — no `--ignore` or `--locale` flags. The entrypoint (L76) and Makefile (L153-155) use `--ignore=... --locale ru --locale bs --locale en`. |
| **Best practice** | All `compilemessages` invocations should use consistent `--ignore` and `--locale` flags. The `--locale ru --locale bs --locale en` flags match the project's `LANGUAGES` setting (`base.py` L57-61) and prevent accidental compilation of `.po` files in unexpected locale directories. The `--ignore` flags provide defense-in-depth even when `.dockerignore` handles context filtering. |
| **Gap** | Inconsistency across execution contexts: the entrypoint and Makefile restrict to 3 locales with ignore flags, but the Dockerfile build and CI compile all locales without any ignore filtering. In CI, `compilemessages` runs at `working-directory: src/backend` (ci.yml L84, L177) — a clean checkout means no local caches, so the risk is low. But CI runs `basedpyright` and `pytest` in separate jobs, and if a future refactor runs cache-generating tools in the same job before `compilemessages`, stale `.po` files could be compiled. The Dockerfile build is protected by `.dockerignore`, so the risk is also low — but consistency matters for maintainability and future-proofing. |
| **Actionable improvement** | Add `--ignore` and `--locale ru --locale bs --locale en` flags to the Dockerfile `compilemessages` (L78) and CI `compilemessages` (ci.yml L83, L176) to match the entrypoint and Makefile. This makes all four execution contexts consistent and defensively explicit. |
| **Impact category** | tooling efficiency |
| **Step 2 reference** | Practice #16 (P1 — Short-term, CI context); Practice #17 (P3 — Dockerfile `--locale`, included here for consistency) |

---

## Cross-Cutting Observations

1. **`.dockerignore` vs `.gitignore` divergence is systematic.** Files gitignored for security (`.env*`, `*.mo`, `*.coverage`, `celerybeat.pid`, `*.rdb`) are inconsistently dockerignored. The `.env*` pattern is correctly dockerignored (L5), but `.mo`, `.coverage`, `celerybeat-schedule`, `*.rdb`, `.gunicorn/` are not. The root cause: `.dockerignore` was built from a partial template (only `.ruff_cache`, `.mypy_cache`, `.pytest_cache` from the tool-cache family) rather than mirroring the full `.gitignore`.

2. **`compilemessages` is the single most inconsistent tooling touchpoint.** It runs in four locations (Dockerfile L78, entrypoint.sh L75, Makefile L152, CI ci.yml L83/L176) with three different flag configurations (no flags, incomplete `--ignore` + `--locale`, and CI with no flags). This creates a maintenance hazard — changes to supported languages or ignore patterns require updates in multiple places.

3. **`uv`/`uvx` in the runtime image is justified but inconsistent.** `entrypoint.sh` already uses `/opt/venv/bin/python` directly (L41, L60, L75), proving the runtime venv is sufficient for at least the primary entrypoint. The four auxiliary scripts still use `uv run python`, creating the sole dependency on `uv` in the production image.

4. **Stray and untracked files are git-tracked and in the build context.** `cat_output.txt`, `neq`, `Continue`, and `cmp_css.py` are committed to Git (not ignored) and included in the Docker build context. Unlike `.playwright-mcp/` and `backups/` (which are untracked), these tracked files will always be present in any checkout and thus always in the build context.

---

## Impact Summary by Category

| Category | Findings | Risk Profile |
|---|---|---|
| Docker Build Context | F01, F02, F03, F04, F05, F06, F07 | 2 security (credential dump), 5 build-context/waste |
| Dockerfile Inputs | (none) | All COPY instructions correctly scoped |
| Runtime Dependencies | F08 | ~30 MB image bloat, unnecessary attack surface |
| Build Artifacts and Caches | F09, F10, F11, F12, F13, F14, F15 | ~240 KB on-disk waste, security gaps, cache pollution |
| Related Tooling | F16, F17 | Tooling inconsistency, defensive gaps in recursive scanning |

**Total actionable findings: 17** (15 missing, 2 suboptimal; 0 correctly implemented since P3 practices were excluded per task instructions)
