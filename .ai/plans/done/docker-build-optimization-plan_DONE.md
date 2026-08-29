# Docker Build Optimization — Implementation Plan

**Status:** FINAL
**Date:** 2026-08-29
**Scope:** 17 findings (F01–F17) across 5 categories, delivered as 5 dependency-ordered commits (CG4+CG5 combined as default; 6 if F08 is split).

---

## 1. Overview

The Mko Bazuna project uses a 3-stage Dockerfile (`docker/Dockerfile`: builder → runtime → test-runtime) with `.dockerignore` controlling build-context membership. This plan addresses all 17 findings (F01–F17) organized into 5 categories and 6 commit groups (CG4+CG5 combined as default → 5 commits). Modified findings (F05, F12) and the F08 Part A→B ordering constraint are reflected throughout.

**Scope distinction:** This plan clearly separates four concerns:
- **Build-context exclusions** (CG1–CG3): `.dockerignore`/`.gitignore` additions that prevent files from entering `docker build` context. These reduce context-transfer size and prevent credential/PII leakage into intermediate layers; they do not affect bind-mount workflows.
- **Image-layer exclusions** (F09): patterns that prevent stale artifacts (`.mo` files) from being baked into image layers during `COPY . .`.
- **Build-time tooling** (builder stage): `uv`/`uvx` used by the builder stage to install dependencies — not modified by this plan.
- **Runtime dependencies** (CG4, CG5): `uv`/`uvx` COPY in the `runtime` stage — removed in CG5, moved to `test-runtime` only; all production entrypoints switch to `/opt/venv/bin/python`.

**Content-anchored edits note:** All modifications below are anchored on content patterns (e.g., `COPY --from=builder /usr/local/bin/uv`, `exec uv run python`, `uv run python src/backend/manage.py compilemessages`) rather than bare line numbers, to avoid drift sensitivity. Line numbers in parentheses are provided as supplementary context only and may become stale; the content pattern is the authoritative reference for implementation.

**Bind-mount invariance principle (critical):** `.dockerignore` only affects `docker build` — it does NOT affect compose bind-mounts. Dev (`.:/app`) and test bind-mounts always see the full host repo. Every `.dockerignore`/`.gitignore` change below is safe for bind-mount workflows.

**No changes needed for:** `COPY pyproject.toml uv.lock* ./` — already optimal per uv docs (layer caching). `COPY . .` — correctly broad for PYTHONPATH-based layout (narrowing rejected — fragile, no meaningful benefit). `COPY docker/entrypoint*.sh /app/` — already narrowed to entrypoint scripts only. apt cache cleanup — already correct. Multi-stage architecture — already correct. Layer caching — already correct. P3 practices (layer caching, COPY narrowing, dead `.dockerignore` patterns, tailwindcss retention, `.env*` scope, apt cleanup, UV runtime env vars, bytecode compilation) are excluded as already-implemented; see Section 12 for the full list.

---

## 2. Overview Table

| ID | Category | File(s) Modified | Commit Group | Risk |
|----|----------|------------------|--------------|------|
| F01 | 1 (Build Context) | `.dockerignore` | CG1 | High |
| F02 | 1 (Build Context) | `.dockerignore`, `.gitignore` | CG1 | High |
| F03 | 1 (Build Context) | `.dockerignore` | CG2 | Medium |
| F04 | 1 (Build Context) | `.dockerignore` | CG2 | Medium |
| F05 ⚠️ | 1 (Build Context) | `.dockerignore`, `.gitignore` + `git rm --cached` | CG2 | Low |
| F06 | 1 (Build Context) | `.dockerignore` | CG2 | Low |
| F07 | 1 (Build Context) | `.dockerignore` | CG2 | Low |
| — | 2 (Dockerfile Inputs) | (no changes) | — | — |
| F08 ⚠️ | 3 (Runtime Deps) | 4 entrypoint scripts + `docker/Dockerfile` | CG4+CG5 | High |
| F09 | 4 (Artifacts/Caches) | `.dockerignore` | CG3 | Medium |
| F10 | 4 (Artifacts/Caches) | `.dockerignore` | CG3 | Low |
| F11 | 4 (Artifacts/Caches) | `.dockerignore` | CG3 | Low |
| F12 ⚠️ | 4 (Artifacts/Caches) | `.dockerignore`, `.gitignore` | CG3 | Low |
| F13 | 4 (Artifacts/Caches) | `.dockerignore` | CG3 | Low |
| F14 | 4 (Artifacts/Caches) | `.dockerignore` | CG3 | Medium |
| F15 | 4 (Artifacts/Caches) | `.dockerignore` | CG3 | Medium |
| F16 | 5 (Tooling) | `docker/entrypoint.sh`, `Makefile` | CG6 | Low |
| F17 | 5 (Tooling) | `docker/Dockerfile`, `.github/workflows/ci.yml` | CG6 | Low |

**⚠️ Modified findings:** F05 (git-tracked files — requires `git rm --cached`), F12 (3 patterns NOT in `.gitignore` — must add to both).

---

## 3. Commit Group Summary

| CG | Findings | Files | Core change |
|----|----------|-------|-------------|
| CG1 | F01, F02 | `.dockerignore`, `.gitignore` | Exclude API keys + DB dump dir from build context |
| CG2 | F03, F04, F05, F06, F07 | `.dockerignore`, `.gitignore`, `git` | Exclude stray files, `.local/`, tool caches, Playwright MCP, nginx configs |
| CG3 | F09–F15 | `.dockerignore`, `.gitignore`, `git` | Exclude compiled translations, build/test artifacts, runtime state |
| CG4+CG5 (default: combined commit) | F08 Part A+B | 4 entrypoint scripts + `docker/Dockerfile` | Replace `uv run python` → `/opt/venv/bin/python`; move `uv`/`uvx` COPY from `runtime` to `test-runtime` stage |
| CG6 | F16, F17 | `docker/entrypoint.sh`, `Makefile`, `docker/Dockerfile`, `.github/workflows/ci.yml` | Expand `compilemessages --ignore` list; add `--locale` to Docker+CI (18 patterns + 3 locales) |

---

## 4. Category 1: Docker Build Context

### CG1 — F01: `scripts/seed-images-config.json` not in `.dockerignore`

**File:** `.dockerignore`
**Modification:** Append `scripts/seed-images-config.json` to `.dockerignore` (after the existing uv cache section or any location — new section: `# Seed photo API keys — gitignored but must also be dockerignored` followed by `scripts/seed-images-config.json`).
**Rationale:** This file contains Unsplash/Pexels API keys (446 B, verified on disk); `.dockerignore` is independent of `.gitignore`, so any developer with a local copy bakes credentials into every image via `COPY . .` (Dockerfile L57).
**Dependencies/order:** Standalone.
**Risk considerations:** High severity credential leak. After fix, `entrypoint-seed.sh` (L18) checks for fixture JPEGs, not this config file — no runtime path depends on it being in `/app`. Seed photo downloads run host-side via `scripts/download_seed_photos.py` (Makefile `seed-photos-download`), not inside the container.
**Validation criteria:** Run `docker build --no-cache` and verify `find /app -name seed-images-config.json` returns nothing in the image. Confirm `entrypoint-seed.sh` still functions by checking it only inspects `FIXTURES_IMAGES_DIR` for JPEGs.

### CG1 — F02: `backups/` directory not in `.gitignore` or `.dockerignore`

**File:** `.dockerignore`, `.gitignore`
**Modification:** Append `backups/` to both files.
**Rationale:** `make backup` writes `dump_*.dump` PostgreSQL dumps (potentially containing PII) to `./backups/`; the directory exists on disk and is excluded from neither VCS nor Docker build context.
**Dependencies/order:** Standalone.
**Risk considerations:** High severity — database dumps may contain user phone numbers and ad content. The `make clean` target (Makefile L231) already does `rm -rf $(BACKUPS_DIR)/*.dump`, confirming this is a local-only artifact dir.
**Validation criteria:** Run `make backup` locally, then `docker build --no-cache` and verify `backups/` is not in the image (`find /app -path '*/backups/*'` returns nothing). Confirm `git status` no longer shows `backups/` contents.

### CG2 — F03: Stray root-level dev artifacts not in `.dockerignore`

**File:** `.dockerignore`
**Modification:** Append `cat_output.txt`, `neq`, `Continue`, `cmp_css.py` to `.dockerignore`.
**Rationale:** Four git-tracked files (3,284 + 36 + 0 + 654 B) are debug/profiling artifacts with no reference in any Dockerfile instruction, entrypoint script, or CI step.
**Dependencies/order:** Standalone.
**Risk considerations:** Medium — debug output (`cat_output.txt`) in a production image is unprofessional and may leak internal data. Adding to `.gitignore` + `git rm --cached` is a recommended follow-up but NOT required for the Docker fix.
**Validation criteria:** `docker build --no-cache` and verify none of the 4 files appear in the image root (`ls /app/ | grep -E '^(cat_output|neq|Continue|cmp_css)'`).

### CG2 — F04: `.local/` directory not in `.dockerignore`

**File:** `.dockerignore`
**Modification:** Append `.local/` to `.dockerignore`.
**Rationale:** `.local/` (with `share/` subdirectory) holds pyenv/pipx/pip user-local installs that can be hundreds of MB; the container has `python:3.14-slim` base + `/opt/venv` and needs neither.
**Dependencies/order:** Standalone.
**Risk considerations:** Medium — build context bloat if pyenv is used locally. Does NOT affect bind-mounts.
**Validation criteria:** Create a test file in `.local/` before build, run `docker build --no-cache`, verify `.local/` is absent from the image.

### CG2 — F05 ⚠️ MODIFIED: `scripts/` temp/profiling artifacts

**MODIFICATION NOTE:** An earlier audit pass claimed these files are "not git-tracked" — this is **FALSE**. All 3 files ARE git-tracked (confirmed via `git ls-files -s`). Adding them to `.gitignore` alone makes them "tracked but ignored"; `git rm --cached` is required to un-track them. The `.dockerignore` addition is still valid and safe.

**File:** `.dockerignore`, `.gitignore`
**Modification:**
1. Append `scripts/_tmp_pytest_run.txt`, `scripts/_tmp_pytest_out.txt`, `scripts/session_context.json` to `.dockerignore`.
2. Append `scripts/_tmp_pytest_run.txt`, `scripts/_tmp_pytest_out.txt`, `scripts/session_context.json` to `.gitignore`.
3. Run `git rm --cached scripts/_tmp_pytest_run.txt scripts/_tmp_pytest_out.txt scripts/session_context.json` to un-track from VCS.
**Rationale:** ~302 KB of test-profiling output (including 92 KB `session_context.json` that may contain internal state) enters the build context on every `COPY . .` (Dockerfile L57).
**Dependencies/order:** `.dockerignore` change is independent. `.gitignore` change + `git rm --cached` should be done in the same commit so the files are un-tracked atomically with the ignore rule.
**Risk considerations:** Low — no build or runtime path references these files. The `git rm --cached` step is critical: without it, future `git add` operations would re-add the files despite the `.gitignore` entry.
**Validation criteria:** After commit, `git ls-files scripts/_tmp_pytest_run.txt` returns empty. `docker build --no-cache` excludes these files. `entrypoint-seed.sh` (which calls `download_seed_photos.py`) is unaffected — it never references these temp files.

### CG2 — F06: `.playwright-mcp/` not in `.dockerignore`

**File:** `.dockerignore`
**Modification:** Append `.playwright-mcp/` to `.dockerignore`.
**Rationale:** Gitignored (`.gitignore`) but not dockerignored; ~701 KB of Playwright MCP browser/runtime artifacts (3 files: console log + 2 page snapshots) enter the build context.
**Dependencies/order:** Standalone.
**Risk considerations:** Low — not referenced by any Dockerfile, entrypoint, or CI step.
**Validation criteria:** `docker build --no-cache` and verify `.playwright-mcp/` is not in the image.

### CG2 — F07: `docker/nginx/` configs not in `.dockerignore`

**File:** `.dockerignore`
**Modification:** Append `docker/nginx/` to `.dockerignore`.
**Rationale:** The `docker/` directory must be in the build context for `COPY docker/entrypoint*.sh /app/` (Dockerfile L124), but `docker/nginx/` (nginx.conf 6,273 B + nginx.dev.conf 5,860 B + `.gitkeep`) is NEVER referenced by any Dockerfile instruction — only bind-mounted at runtime by the nginx compose service.
**Dependencies/order:** Standalone.
**Risk considerations:** Low — verified that `docker/nginx/` pattern does NOT exclude `docker/entrypoint*.sh` (entrypoint scripts are at `docker/` top level, not under `docker/nginx/`). Bind-mounts are unaffected by `.dockerignore`.
**Validation criteria:** `docker build --no-cache` and verify `COPY docker/entrypoint*.sh /app/` still succeeds (entrypoint scripts present in image). Verify `docker/nginx/` directory is absent from the image.

### Category 2 — Dockerfile Inputs (no changes)

No findings in Category 2. The Dockerfile's `COPY` instructions are already correctly scoped: `COPY pyproject.toml uv.lock* ./` provides dependency-layer caching; `COPY . .` is the correct pattern for a PYTHONPATH-based (non-pip-installed) project (narrowing rejected — fragile, no meaningful benefit); `COPY --chown=app:app docker/entrypoint*.sh /app/` is already narrowed to only entrypoint scripts. No `ADD` instructions exist.

---

## 5. Category 3: Runtime Dependencies

### CG4 — F08 Part A: Replace `uv run python` → `/opt/venv/bin/python` in 4 aux entrypoint scripts

**Files:** `docker/entrypoint-catalog.sh`, `docker/entrypoint-create-admin.sh`, `docker/entrypoint-seed.sh`, `docker/entrypoint-scheduler.sh`
**Modification:** Replace each `exec uv run python` and `uv run python -c` invocation with `/opt/venv/bin/python`:

| Script | Line | Before | After |
|--------|------|--------|-------|
| `entrypoint-catalog.sh` | L17 | `exec uv run python src/backend/manage.py load_catalog --no-rewrite` | `exec /opt/venv/bin/python src/backend/manage.py load_catalog --no-rewrite` |
| `entrypoint-create-admin.sh` | L24 | `exec uv run python src/backend/manage.py create_admin_user \` | `exec /opt/venv/bin/python src/backend/manage.py create_admin_user \` |
| `entrypoint-seed.sh` | L18 | `FIXTURES_IMAGES_DIR=$(uv run python -c "...")` | `FIXTURES_IMAGES_DIR=$(/opt/venv/bin/python -c "...")` |
| `entrypoint-seed.sh` | L32 | `exec uv run python src/backend/manage.py seed --force \` | `exec /opt/venv/bin/python src/backend/manage.py seed --force \` |
| `entrypoint-scheduler.sh` | L21 | `exec uv run python -c "` | `exec /opt/venv/bin/python -c "` |

**Rationale:** `entrypoint.sh` (the primary web entrypoint) already uses `/opt/venv/bin/python` directly (L41, L60, L75) — this pattern is proven and the runtime venv exists in all stages. Removing `uv`/`uvx` from the runtime image requires this change.
**Dependencies/order:** **MUST** be committed before or simultaneously with CG5 (Part B). If Part B lands first without Part A, all 4 aux services (catalog, create_admin, seed, scheduler) crash-loop with "command not found: uv" (exit 127). **Default approach: combined CG4+CG5 commit** to eliminate the crash-loop window entirely. A split is acceptable if targeted rollback of Part B is preferred, but CG4 must still precede CG5. `entrypoint-test.sh` stays unchanged — it runs only in the `test-runtime` stage which retains `uv`.
**Risk considerations:** High ordering risk. `Dockerfile` L109 comment says "needed for dev mode `uv run` commands and entrypoint scripts" — becomes inaccurate after CG5 and must be updated. The `UV_NO_INSTALL_PROJECT=1` and `UV_FROZEN=1` env vars (Dockerfile L137-138) make `uv run` a no-op sync; `/opt/venv/bin/python` bypasses uv entirely — same result.
**Validation criteria:** Rebuild the `runtime` image (after CG5) and verify `load_catalog`, `seed`, `create_admin`, and `scheduler` services start without "uv: command not found" errors. Confirm `entrypoint-test.sh` still works in `test-runtime` (it retains `uv`).

### CG5 — F08 Part B: Move `uv`/`uvx` COPY from `runtime` to `test-runtime` stage

**File:** `docker/Dockerfile`
**Modification:**
1. **Remove** from the `runtime` stage (the `uv`/`uvx` comment + two `COPY --from=builder` lines):
   - Comment `# Copy uv binary from builder (needed for dev mode \`uv run\` commands and entrypoint scripts)` → delete or update to `# uv/uvx only needed in test-runtime for \`uv sync\`; runtime entrypoints use /opt/venv/bin/python directly`
   - `COPY --from=builder /usr/local/bin/uv /usr/local/bin/uv` → remove
   - `COPY --from=builder /usr/local/bin/uvx /usr/local/bin/uvx` → remove
2. **Add** to the `test-runtime` stage (after `FROM runtime AS test-runtime`, before the `uv sync` RUN):
   - Add `COPY --from=builder /usr/local/bin/uv /usr/local/bin/uv` and `COPY --from=builder /usr/local/bin/uvx /usr/local/bin/uvx`
   - Also need env vars `PATH`, `UV_PROJECT_ENVIRONMENT`, `UV_NO_INSTALL_PROJECT`, `UV_FROZEN` in test-runtime for `uv sync` and `uv run` to work (inherited from `runtime` via `FROM runtime AS test-runtime`, so they're already present — verified).
**Rationale:** The `uv` binary (~20–30 MB) is only needed at runtime by `entrypoint-test.sh` (which does `uv sync --group dev` + `uv run pytest`). All production entrypoints now use `/opt/venv/bin/python` directly (after Part A). This reduces the production runtime image size and attack surface.
**Dependencies/order:** Must be committed AT or AFTER CG4 (Part A). **Default approach: combined CG4+CG5 commit** to eliminate the crash-loop window entirely. A split into separate CG4 and CG5 commits is acceptable if targeted rollback of Part B is preferred, but CG4 must still land before (or with) CG5.
**Risk considerations:** 
- CI `build` job (ci.yml L16-24) builds the default target = last `FROM` = `test-runtime` (no `target:` specified) — still has `uv` ✅
- Production image (`--target runtime`) no longer has `uv` — all entrypoints use `/opt/venv/bin/python` or resolve `python` via `PATH="/opt/venv/bin:${PATH}"` ✅
- `CMD ["gunicorn", ...]` (L155) resolves via PATH in `/opt/venv/bin/` ✅
- Bot service (`docker-compose.yml` L168: `command: python -m telegram_bot.main`) resolves via PATH ✅
- `entrypoint-test.sh` uses `uv` (L16, L19, L20, L41) — it's in `test-runtime` which retains `uv` ✅
- Dev compose (docker-compose.dev.override.yml) has no `target:` → defaults to `test-runtime` (has `uv`) ✅
**Validation criteria:** `docker build --target runtime --no-cache` produces an image without `uv`/`uvx` binaries (verify `which uv` fails in the image). `docker build --target test-runtime --no-cache` still has `uv` (verify `which uv` succeeds). CI build job still passes. Production services (web, bot, catalog, seed, create_admin, scheduler) start without errors.

---

## 6. Category 4: Build Artifacts and Caches

### CG3 — F09: `.mo`/`.pot` compiled translations not in `.dockerignore`

**File:** `.dockerignore`
**Modification:** Append `*.mo` and `*.pot` to `.dockerignore`.
**Rationale:** Three `.mo` files (~52 KB total) are gitignored but not dockerignored; they enter the build context via `COPY . .` (Dockerfile L57) and are immediately overwritten by `compilemessages` (Dockerfile L78). Excludes prevents stale translations from being baked in if `compilemessages` fails.
**Dependencies/order:** Standalone.
**Risk considerations:** Medium — if `compilemessages` (Dockerfile L78) were skipped or failed, stale host `.mo` files would be served. `.po` files (the input) remain in the build context — they are git-tracked and not matched by `*.mo`/`*.pot`.
**Validation criteria:** `docker build --no-cache` and verify no `.mo` files exist before `compilemessages` runs (add `RUN find /app -name "*.mo"` before L78 temporarily, or check the final image only has freshly compiled `.mo` from build). Confirm `compilemessages` succeeds (image has `.mo` files at `src/backend/locale/*/LC_MESSAGES/django.mo`).

### CG3 — F10: `.gitattributes` not in `.dockerignore`

**File:** `.dockerignore`
**Modification:** Append `.gitattributes` to `.dockerignore`.
**Rationale:** Git-only configuration file (302 B, LF line-ending rules) with zero relevance inside a container image. Credential hygiene concern — `.gitattributes` can contain path-rewrite rules.
**Dependencies/order:** Standalone.
**Risk considerations:** Low — not referenced by any Dockerfile, entrypoint, or CI step. Should NOT be added to `.gitignore` — it is intentionally git-tracked for team consistency.
**Validation criteria:** `docker build --no-cache` and verify `.gitattributes` is absent from the image root.

### CG3 — F11: `.python-version` not in `.dockerignore`

**File:** `.dockerignore`
**Modification:** Append `.python-version` to `.dockerignore`.
**Rationale:** 5-byte file containing `3.14`; the base image `python:3.14-slim` already provides Python 3.14. Only consumed by pyenv at local dev time. No `UV_PYTHON_PREFERENCE` is configured (verified: Dockerfile env vars are `UV_LINK_MODE`, `UV_COMPILE_BYTECODE`, `UV_PROJECT_ENVIRONMENT`, `UV_NO_INSTALL_PROJECT`, `UV_FROZEN` only).
**Dependencies/order:** Standalone.
**Risk considerations:** Low — not referenced by any Dockerfile, entrypoint, or CI step. Should NOT be added to `.gitignore` — the project intentionally tracks it (`.gitignore` L88 is commented out).
**Validation criteria:** `docker build --no-cache` and verify `.python-version` is absent from the image. Dev bind-mount still sees it (host-side `uv` uses it).

### CG3 — F12 ⚠️ MODIFIED: Missing standard Python tool cache dirs in `.dockerignore`

**MODIFICATION NOTE:** An earlier audit pass claimed all 8 patterns exist in `.gitignore`. Verification found that only 5 of 8 are in `.gitignore`:
- ✅ Already in `.gitignore`: `.tox/` (L41), `.nox/` (L42), `.pyre/` (L175), `.pytype/` (L178), `__pypackages__/` (L122)
- ❌ NOT in `.gitignore`: `.profile_default/` (L82 has `profile_default/` — no leading dot, different pattern), `.pdbrc` (absent), `.python-eggs/` (absent)

The 3 missing patterns must be added to **both** `.gitignore` and `.dockerignore` for full coverage.

**File:** `.dockerignore`, `.gitignore`
**Modification:**
1. Append to `.dockerignore`: `.tox/`, `.nox/`, `.pyre/`, `.pytype/`, `__pypackages__/`, `.profile_default/`, `.pdbrc`, `.python-eggs/`
2. Append to `.gitignore` (the 3 patterns not already present): `.profile_default/`, `.pdbrc`, `.python-eggs/`
**Rationale:** Defense-in-depth — if a developer runs `tox`, `nox`, `pyre`, `pytype`, `__pip` packages, pdb, or egg-based installs locally, the resulting caches could bloat the build context and potentially confuse recursive `compilemessages` scans.
**Dependencies/order:** Standalone.
**Risk considerations:** Low — none of these directories/files are needed inside the container. The `.gitignore` additions are required for F12's MODIFICATION: the 3 patterns not already in `.gitignore` must be added there too (not just `.dockerignore`) so `git check-ignore` behavior is consistent.
**Validation criteria:** `git check-ignore .profile_default/ .pdbrc .python-eggs/` returns all 3 paths. `docker build --no-cache` excludes all 8 patterns. Verify `.tox/`, `.nox/` etc. don't appear in the image (create a test dir, build, verify absence).

### CG3 — F13: Missing build artifacts (`*.manifest`, `*.spec`) in `.dockerignore`

**File:** `.dockerignore`
**Modification:** Append `*.manifest` and `*.spec` to `.dockerignore`.
**Rationale:** PyInstaller artifact patterns from the standard Python `.gitignore` template (L29-33); currently gitignored but not dockerignored. No files currently exist on disk — purely defensive.
**Dependencies/order:** Standalone.
**Risk considerations:** Low — no `.manifest`/`.spec` files exist; defensive coverage only.
**Validation criteria:** `docker build --no-cache` with a dummy `test.spec` file in root — verify it's excluded from context.

### CG3 — F14: Missing coverage/test artifacts in `.dockerignore`

**File:** `.dockerignore`
**Modification:** Append `.coverage`, `.coverage.*`, `coverage.xml`, `htmlcov/`, `.hypothesis/` to `.dockerignore`.
**Rationale:** The `.coverage` file (167,936 B) is verified on disk and enters the build context via `COPY . .` (Dockerfile L57). Test execution metadata (timing, internal paths, code structure) should not be in production images.
**Dependencies/order:** Standalone.
**Risk considerations:** Medium — 168 KB wasteful transfer; test metadata exposure. These patterns are already in `.gitignore` (L40-50).
**Validation criteria:** `docker build --no-cache` and verify no `.coverage` or `coverage.xml` in the image. Run `pytest --cov` locally, rebuild, verify exclusion.

### CG3 — F15: Missing runtime artifacts in `.dockerignore`

**File:** `.dockerignore`
**Modification:** Append `celerybeat-schedule`, `celerybeat.pid`, `*.rdb`, `*.aof`, `*.pid`, `.gunicorn/` to `.dockerignore`.
**Rationale:** Runtime lock files, PID files, Redis persistence files, and Gunicorn runtime state (`/.gunicorn/` verified on disk containing `gunicorn.ctl`) could be baked into the builder stage's `/app/` via `COPY . .` (Dockerfile L57) if Redis/Gunicorn were run locally before building.
**Dependencies/order:** Standalone.
**Risk considerations:** Medium — stale PID/sock files in the builder layer are dead weight; the runtime stage only copies specific paths (`COPY --from=builder /app/src /app/src` L114), so final image is unaffected. These patterns are already in `.gitignore`.
**Validation criteria:** `docker build --no-cache` and verify `.gunicorn/` is absent from the image. No existing file dependency.

---

## 7. Category 5: Related Tooling

### CG6 — F16: Expand `compilemessages` `--ignore` list in entrypoint and Makefile

**Files:** `docker/entrypoint.sh` (`compile_messages()` function's `--ignore` list), `Makefile` (`compilemessages` target's `--ignore` list)
**Modification:** Expand both `--ignore` lists from the current 5 patterns to 18:

```
--ignore=.venv --ignore=.git --ignore=.kilo --ignore=__pycache__ --ignore='*.pyc' \
--ignore=.mypy_cache --ignore=.ruff_cache --ignore=.pytest_cache --ignore=node_modules \
--ignore=.tox --ignore=.nox --ignore=__pypackages__ --ignore=.uv --ignore=.cache \
--ignore=.local --ignore=.playwright-mcp --ignore=.coverage --ignore=.hypothesis
```

Both locations already have `--locale ru --locale bs --locale en` (entrypoint.sh L77, Makefile L155) — those are retained unchanged.
**Rationale:** In dev/test, the `.:/app` bind-mount exposes the full host repo. Without comprehensive `--ignore` flags, `compilemessages` traverses cache directories (wasted I/O, potential stale `.po` compilation). The expanded list mirrors `.dockerignore` coverage.
**Dependencies/order:** Apply together with F17 (same commit group CG6) for consistency across all 4 invocation sites.
**Risk considerations:** Low — the `--ignore` patterns target top-level cache/VCS directories; none are in the path `src/backend/locale/{ru,bs,en}/LC_MESSAGES/` where `.po` files live. Non-fatal fallback (`entrypoint.sh` L78: `|| echo WARNING`) protects against any edge case. Django's `compilemessages` uses `action="append"` for `--ignore` (Django 5.2.16), so each `--ignore` flag is independent.
**Validation criteria:** Run `make compilemessages` and verify it completes without errors. In dev mode, `entrypoint.sh`'s `compile_messages()` runs at container startup — verify no warnings. Confirm `.mo` files regenerated for `ru`/`bs`/`en` only.

### CG6 — F17: Add `--ignore`/`--locale` flags to Dockerfile build and CI `compilemessages`

**Files:** `docker/Dockerfile` (bare `compilemessages` invocation), `.github/workflows/ci.yml` (test job + i18n job `compilemessages` invocations)
**Modification:** Append the same 13 additional `--ignore` flags (plus existing 5) and `--locale ru --locale bs --locale en` to the three flag-less invocations:

- **Dockerfile (bare `compilemessages` invocation):** `uv run python src/backend/manage.py compilemessages` → `uv run python src/backend/manage.py compilemessages --ignore=.venv --ignore=.git --ignore=.kilo --ignore=__pycache__ --ignore='*.pyc' --ignore=.mypy_cache --ignore=.ruff_cache --ignore=.pytest_cache --ignore=node_modules --ignore=.tox --ignore=.nox --ignore=__pypackages__ --ignore=.uv --ignore=.cache --ignore=.local --ignore=.playwright-mcp --ignore=.coverage --ignore=.hypothesis --locale ru --locale bs --locale en`
- **CI ci.yml (test job `compilemessages` invocation):** `uv run python manage.py compilemessages` → same flags appended
- **CI ci.yml (i18n job `compilemessages` invocation):** `uv run python manage.py compilemessages` → same flags appended

**Rationale:** Makes all 4 `compilemessages` invocation sites (Dockerfile, entrypoint.sh, Makefile, CI ×2) consistent. The `--locale ru --locale bs --locale en` flags match `LANGUAGES` in `base.py` (L57-61) and prevent accidental compilation of `.po` files in unexpected locale directories.
**Dependencies/order:** Apply together with F16 (same commit group CG6).
**Risk considerations:** Low — Dockerfile build is already protected by `.dockerignore` (which excludes most cache dirs from context); the `--ignore` flags are defense-in-depth. CI runs on a clean `actions/checkout` environment — the flags are harmless and provide consistency. All 5 `.po` files (ru, bs, en) remain in the build context/CI checkout.
**Validation criteria:** CI `test` job and `i18n` job pass. `docker build --no-cache` succeeds with `compilemessages` producing `.mo` files for exactly `ru`/`bs`/`en`. Verify no other locale directories produce `.mo`.

**Maintainability advisory (future improvement, not required for this plan):** The 18 `--ignore` patterns + 3 `--locale` flags are now duplicated across 4 invocation sites (Dockerfile, entrypoint.sh, Makefile, ci.yml ×2). A shared helper script (e.g., `docker/_compilemessages_flags.sh` sourced by entrypoint.sh and Makefile, inlined into Dockerfile/CI) would eliminate this duplication risk — if a future pattern is added, all 4 sites must be updated in lockstep. Deferred to future work; the inline approach is correct and functional for this plan.

---

## 8. Dependency-Aware Execution Order

```
CG1 (F01, F02) → CG2 (F03–F07) → CG3 (F09–F15) → CG4+CG5 (F08 Part A+B, combined commit) → CG6 (F16, F17)
```

**Rationale for ordering:**

1. **CG1 before everything:** Security fixes (credential leak in `seed-images-config.json`, PII exposure in `backups/`) land first. These are zero-risk additions; no other finding depends on them.

2. **CG2 before CG3:** Both are `.dockerignore` expansion clusters, but CG2 handles files/directories (stray artifacts, `.local/`, temp files, Playwright MCP, nginx configs) while CG3 handles pattern-based artifacts (compiled translations, tool caches, coverage data, runtime state). Ordering them separately allows smaller, reviewable commits. CG2 is independent of CG3.

3. **CG3 before CG4:** The `.dockerignore` expansions (CG1–CG3) are all independent of runtime dependency changes (CG4–CG5). Getting all context exclusions done first ensures the build context is clean before the more impactful `uv` removal work begins. This is the "narrow the funnel" principle — secure the build inputs, then optimize the runtime.

4. **CG4→CG5 (F08 ordering constraint):** This is the **critical path constraint**. Part A (replace `uv run python` → `/opt/venv/bin/python` in 4 entrypoint scripts) MUST be committed before or simultaneously with Part B (remove `uv`/`uvx` from the runtime stage). If Part B lands first, all 4 production aux services (catalog, create_admin, seed, scheduler) fail with `exit 127` (command not found). **Default approach: combined CG4+CG5 commit** to eliminate the crash-loop window entirely. A split into separate CG4 and CG5 commits is available if targeted rollback of Part B is preferred, but CG4 must still land before (or with) CG5.

5. **CG4/CG5 before CG6:** The `compilemessages` flag expansion (F16/F17) is purely additive — more `--ignore` patterns and `--locale` flags. It does not interact with the `uv` removal. Applying it last ensures all prior changes are validated before the final consistency fix. CG6 could theoretically be applied in parallel with CG4/CG5, but sequential is safer for reviewability.

**No circular dependencies exist.** All `.dockerignore` additions (CG1–CG3) are fully independent. CG4+CG5 (F08) has a hard ordering constraint (Part A before Part B). CG6 is independent of F08 but applied last for reviewability.

---

## 9. Rollback Procedures

### Rollback CG1 (F01, F02)
```powershell
git revert <CG1-commit-hash> --no-edit
```
No runtime services depend on `backups/` or `seed-images-config.json` being excluded. Reverting restores the prior `.dockerignore`/`.gitignore`.

### Rollback CG2 (F03–F07)
```powershell
git revert <CG2-commit-hash> --no-edit
```
Files return to build context. F05's `git rm --cached` reverts (files re-appear in VCS tracking). Verify with `git ls-files scripts/_tmp_pytest_run.txt` after revert.

### Rollback CG3 (F09–F15)
```powershell
git revert <CG3-commit-hash> --no-edit
```
`.mo`/`.pot` files, coverage data, runtime artifacts, and tool caches return to the build context. No functional impact — `compilemessages` overwrites `.mo`; runtime stage only copies specific paths.

### Rollback CG4+CG5 (F08 Part A+B, combined commit — default approach)
```powershell
git revert <CG4+CG5-commit-hash> --no-edit
```
Single revert restores both entrypoint scripts to `uv run python` and `uv`/`uvx` COPY in the runtime stage. No crash-loop window because both changes are reverted atomically. Use this when CG4+CG5 was applied as a combined commit.

### Rollback CG4 (F08 Part A) — split-commit approach
```powershell
git revert <CG4-commit-hash> --no-edit
```
Reverts entrypoint scripts to `uv run python`. Safe only if CG5 (Part B) has NOT been applied. If CG5 IS applied, reverting CG4 without reverting CG5 causes the production aux services to fail (they'd call `uv run` but `uv` is absent from runtime image).

### Rollback CG5 (F08 Part B) — split-commit approach
```powershell
git revert <CG5-commit-hash> --no-edit
```
Restores `uv`/`uvx` COPY in the runtime stage. After this revert, CG4 (Part A) is still in effect (scripts use `/opt/venv/bin/python`), so `uv` is present but unused in production — harmless but wasteful. Full rollback = revert CG5 then CG4.

### Rollback CG6 (F16, F17)
```powershell
git revert <CG6-commit-hash> --no-edit
```
Reverts to original incomplete `--ignore` lists and missing `--locale` flags. `compilemessages` still works (fewer ignored dirs, all locales compiled instead of just ru/bs/en). Functional but less defensive.

---

## 10. Validation Matrix

| Group | Command | Success criteria |
|-------|---------|-----------------|
| CG1 | `docker build --no-cache -t test:cg1 .` | Image has no `seed-images-config.json`, no `backups/` |
| CG2 | `docker build --no-cache -t test:cg2 .` | Image excludes 4 stray files, `.local/`, 3 temp files, `.playwright-mcp/`, `docker/nginx/` |
| CG3 | `docker build --no-cache -t test:cg3 .` | Image excludes `.mo`/`.pot` before compilemessages, no `.gitattributes`, `.python-version`, coverage data, runtime artifacts |
| CG4+CG5 | `docker build --target runtime --no-cache` + `docker build --target test-runtime --no-cache` | `which uv` fails in runtime image; succeeds in test-runtime; all 4 aux entrypoint scripts use `/opt/venv/bin/python` (grep confirms no `uv run` in 4 aux scripts) |
| CG6 | `make compilemessages` + `docker build --no-cache -t test:cg6 .` | compilemessages succeeds with full ignore flags; CI i18n job passes |
| Full | `make test` | Fast gate (non-seed tests) passes — confirms no regression from all changes |
| Full | `docker compose -f docker-compose.yml -f docker-compose.test.yml build` | Test-runtime image builds with `uv` retained; `entrypoint-test.sh` works |

---

## 11. Files Modified Summary

| File | CG | Changes |
|------|-----|---------|
| `.dockerignore` | CG1, CG2, CG3 | Append: F01 (1 pattern), F02 (1), F03 (4), F04 (1), F05 (3), F06 (1), F07 (1), F09 (2), F10 (1), F11 (1), F12 (8), F13 (2), F14 (5), F15 (6) |
| `.gitignore` | CG1, CG2, CG3 | Append: F02 (`backups/`), F05 (3 patterns), F12 (3 patterns: `.profile_default/`, `.pdbrc`, `.python-eggs/`) |
| `docker/entrypoint-catalog.sh` | CG4 (combined w/ CG5) | At `exec uv run python src/backend/manage.py load_catalog`: `uv run python` → `/opt/venv/bin/python` |
| `docker/entrypoint-create-admin.sh` | CG4 (combined w/ CG5) | At `exec uv run python src/backend/manage.py create_admin_user`: `uv run python` → `/opt/venv/bin/python` |
| `docker/entrypoint-seed.sh` | CG4 (combined w/ CG5) | At `FIXTURES_IMAGES_DIR=$(uv run python -c` and `exec uv run python src/backend/manage.py seed`: `uv run python` → `/opt/venv/bin/python` |
| `docker/entrypoint-scheduler.sh` | CG4 (combined w/ CG5) | At `exec uv run python -c`: `uv run python` → `/opt/venv/bin/python` |
| `docker/Dockerfile` | CG5 (combined w/ CG4), CG6 | Remove `COPY --from=builder /usr/local/bin/uv` + `COPY --from=builder /usr/local/bin/uvx` + comment from `runtime` stage; add to `test-runtime` stage; expand bare `compilemessages` invocation with `--ignore` + `--locale` flags |
| `Makefile` | CG6 (F16) | At `compilemessages` target: expand `--ignore` list to 18 patterns |
| `.github/workflows/ci.yml` | CG6 (F17) | At test job + i18n job `compilemessages` invocations: add `--ignore` + `--locale` flags |
| Git index | CG2 (F05) | `git rm --cached` for 3 tracked temp files |
| Git index | CG3 (F12) | No `git rm` needed — 3 patterns are NOT tracked |

---

## 12. Excluded from Plan (P3 / Already Correct)

| Practice | Reason |
|----------|--------|
| `COPY pyproject.toml uv.lock* ./` (L37) | Correct uv-recommended layer caching pattern |
| `COPY . .` (L57) narrowing | Rejected — PYTHONPATH-based project, narrowing is fragile |
| Dead `src/backend/mko_bazuna` pattern | P3 — harmless dead pattern, low priority |
| `tailwindcss` in runtime | P3 — needed for dev-mode `runserver` CSS rebuild |
| `.env*` scope | P3 — correctly broad, prevents all env files entering context |
| Multi-stage build architecture | P3 — correct 3-stage separation |
| apt cache cleanup | P3 — already present (cache mounts + `rm -rf /var/lib/apt/lists/*`) |
| `UV_NO_INSTALL_PROJECT=1` + `UV_FROZEN=1` | P3 — correct runtime hardening |
| `UV_LINK_MODE=copy` | P3 — required for cache mount compatibility |
| `UV_COMPILE_BYTECODE=1` | P3 — correct for faster startup |
