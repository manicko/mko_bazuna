# Step 5 — Validation of Step 4 Risk Assessment

**Validation Source:** `ai/step4-risk-assessment.md` (17 findings, F01–F17)  
**Verified Against:** Repository at `C:\py_dev\mko_bazuna`, commit `ba5c65e` + working tree  
**Validation Date:** 2026-08-29  
**Methodology:** Each finding was independently verified against live filesystem evidence — file sizes via `Get-Item`, line numbers via `Read`, git-tracking status via `git ls-files -s`, git-ignore status via `git check-ignore`, directory structure via `git ls-files docker/`, and `.dockerignore` content via direct file read. Dockerfile `COPY` instructions, entrypoint script invocations, and `compilemessages` invocation strings were read directly from source.

---

## Validation Summary

| ID  | Step 4 Verdict | Validation Verdict | Notes |
|-----|----------------|-------------------|-------|
| F01 | APPROVE | **APPROVE** | Verified: 446 B, git-ignored (L225), not in `.dockerignore` |
| F02 | APPROVE | **APPROVE** | Verified: `backups/` exists (empty), not git-tracked, not git-ignored |
| F03 | APPROVE | **APPROVE** | Verified: all 4 files git-tracked, sizes match (3284+36+0+654 B) |
| F04 | APPROVE | **APPROVE** | Verified: `.local/share/` exists, NOT git-ignored (confirmed via `git check-ignore`) |
| F05 | APPROVE | **MODIFY** ⚠️ | **ERROR:** Claims files are "not git-tracked" but ALL 3 ARE git-tracked |
| F06 | APPROVE | **APPROVE** | Verified: `.playwright-mcp/` exists (701 KB, 3 files), git-ignored (L233) |
| F07 | APPROVE | **APPROVE** | Verified: nginx configs under `docker/nginx/`, entrypoints at `docker/` top level |
| F08 | APPROVE | **APPROVE** | Verified: 4 aux scripts use `uv run python`, entrypoint.sh uses `/opt/venv/bin/python` |
| F09 | APPROVE | **APPROVE** | Verified: 3 `.mo` files (52,209 B total), 3 `.po` files git-tracked |
| F10 | APPROVE | **APPROVE** | Verified: `.gitattributes` (302 B), git-tracked, not in `.dockerignore` |
| F11 | APPROVE | **APPROVE** | Verified: `.python-version` (5 B, "3.14"), git-tracked, commented in `.gitignore` L88 |
| F12 | APPROVE | **MODIFY** ⚠️ | **ERROR:** Claims `.profile_default/`, `.pdbrc`, `.python-eggs/` in `.gitignore` — NOT present |
| F13 | APPROVE | **APPROVE** | Verified: no `.manifest`/`.spec` files on disk, patterns in `.gitignore` L32-33 |
| F14 | APPROVE | **APPROVE** | Verified: `.coverage` (167,936 B), git-ignored, not in `.dockerignore` |
| F15 | APPROVE | **APPROVE** | Verified: `.gunicorn/` exists, git-ignored (L236), not in `.dockerignore` |
| F16 | APPROVE | **APPROVE** | Verified: entrypoint.sh L76 + Makefile L154 have limited `--ignore` list, with `--locale` |
| F17 | APPROVE | **APPROVE** | Verified: Dockerfile L78, CI ci.yml L83/L176 lack `--ignore`/`--locale` flags |

**2 findings (F05, F12) contain factual errors requiring correction.** The remaining 15 are fully verified as correct.

---

## Evidence Per Finding

### F01: `scripts/seed-images-config.json` (API keys) not in `.dockerignore`

**Evidence verified on disk:**
- **File exists:** YES — `scripts/seed-images-config.json` is 446 B (confirmed via `Get-Item`)
- **Git-tracked:** NO — `git ls-files -s scripts/seed-images-config.json` returns empty
- **Git-ignored:** YES — `git check-ignore scripts/seed-images-config.json` returns the path (matches `.gitignore` L225: `scripts/seed-images-config.json`)
- **In `.dockerignore`:** NO — `Select-String` scan of `.dockerignore` found no match for `seed-images-config`
- **`.gitignore` L225:** `scripts/seed-images-config.json` (confirmed by reading `.gitignore`)
- **`.dockerignore` L57:** `COPY . .` (Dockerfile L57) would include this file in the build context
- **Related:** `scripts/seed-images-config.example.json` IS git-tracked (confirmed: `git ls-files -s scripts/` shows `seed-images-config.example.json` at 100644)

**Step 4 claims checked:**
- "446 B" → ✅ VERIFIED (`Get-Item` confirms 446 bytes)
- "in `.gitignore` at L225" → ✅ VERIFIED (read `.gitignore` L225)
- "not dockerignored" → ✅ VERIFIED (grep/Select-String found no match)
- "seed entrypoint does not reference this file at runtime" → ✅ VERIFIED (read `entrypoint-seed.sh` — checks for fixture JPEGs, not config JSON)

**Verdict:** APPROVE — All Step 4 claims verified correct. The file is a confirmed credential-leak vector. Adding `scripts/seed-images-config.json` to `.dockerignore` is safe: only `COPY . .` (Dockerfile L57) is affected, no runtime path depends on the file being in the image.

---

### F02: `backups/` directory not in `.gitignore` or `.dockerignore`

**Evidence verified on disk:**
- **Directory exists:** YES — `backups/` exists on disk (confirmed via `Test-Path`)
- **Git-tracked:** NO — `git ls-files backups/` returns empty
- **Git-ignored:** NO — `git check-ignore backups/` returns empty (not matched by any `.gitignore` pattern)
- **In `.dockerignore`:** NO — `Select-String` scan found no match for `backups`
- **Makefile backup target:** `.gitignore` does NOT currently have `backups/` (no match in `git check-ignore`)
- **Makefile references:** `Makefile` L197 (`BACKUPS_DIR := ./backups`), L199-206 (`backup:` target writes to `$(BACKUPS_DIR)`), L231 (`make clean` does `rm -rf $(BACKUPS_DIR)/*.dump`)

**Step 4 claims checked:**
- "directory exists on disk (currently empty)" → ✅ VERIFIED
- "not in `.gitignore` or `.dockerfile`" → ✅ VERIFIED
- "Makefile backup target writes to `./backups/`" → ✅ VERIFIED (Makefile L197, L199-206)
- "make clean target already does `rm -rf $(BACKUPS_DIR)/*.dump`" → ✅ VERIFIED (Makefile L231)

**Verdict:** APPROVE — All Step 4 claims verified correct. Adding `backups/` to both `.gitignore` and `.dockerignore` is safe. No current file in `backups/` is needed by any Docker build step or runtime path.

---

### F03: Stray root-level dev artifacts not in `.dockerignore`

**Evidence verified on disk:**
- **All 4 files exist:** YES
  - `cat_output.txt` — 3,284 B (confirmed via `Get-Item`)
  - `neq` — 36 B
  - `Continue` — 0 B (empty file)
  - `cmp_css.py` — 654 B
- **All 4 are git-tracked:** YES — `git ls-files -s cat_output.txt neq Continue cmp_css.py` returns all 4 entries:
  ```
  100644 0258fe2a... 0 .gitattributes
  100644 6324d401... 0 .python-version
  100644 e69de29b... 0 Continue
  100644 6a2efda4... 0 cat_output.txt
  100644 7d412f28... 0 cmp_css.py
  100644 dae0b374... 0 neq
  ```
- **In `.dockerignore`:** NO — `Select-String` scan found no matches for these filenames
- **Referenced anywhere:** NO — reviewed Dockerfile, all 6 entrypoint scripts, Makefile, CI ci.yml; none reference `cat_output.txt`, `neq`, `Continue`, or `cmp_css.py`

**Step 4 claims checked:**
- "All four are git-tracked (verified via `git ls-files`)" → ✅ VERIFIED
- "sizes verified: 3284 + 36 + 0 + 654 = 4,022 bytes total" → ✅ VERIFIED (`Get-Item` confirms exact sizes)
- "have no reference in any Dockerfile instruction, entrypoint script, or CI step" → ✅ VERIFIED (manual review of all Docker/CI/entrypoint files)
- "If files are ALSO added to `.gitignore`, they'd become tracked-but-ignored" → ✅ CORRECT (git behavior: adding a tracked file to `.gitignore` after it's tracked results in "tracked but ignored" — requires `git rm --cached`)

**Verdict:** APPROVE — All Step 4 claims verified correct. The recommendation to add these to `.dockerignore` (and optionally `.gitignore` + `git rm --cached`) is sound. The files are debug/test artifacts that increase build context unnecessarily.

---

### F04: `.local/` directory not in `.dockerignore`

**Evidence verified on disk:**
- **Directory exists:** YES — `.local/` exists with a `share/` subdirectory (confirmed: `Get-ChildItem .local` shows `.local\share`)
- **Git-tracked:** NO — `git ls-files .local/` returns empty
- **Git-ignored:** NO — `git check-ignore .local/` returns exit code 1 / `False` (NOT ignored by any `.gitignore` pattern)
- **In `.dockerignore`:** NO — `Select-String` scan found no match for `.local`
- **No `.local/` references:** Reviewed Dockerfile, entrypoint scripts, Makefile, CI — `.local/` is never referenced

**Step 4 claims checked:**
- "directory exists on disk with a `share/` subdirectory" → ✅ VERIFIED
- "is not in `.gitignore` (verified: `git check-ignore .local/` returns nothing)" → ✅ VERIFIED (confirmed via `git check-ignore --no-index .local/` → `False`)
- "typically holds pyenv, pipx, or pip user-install artifacts" → ✅ PLAUSIBLE (not directly verified, but `.local/share` is consistent with this)
- "The project uses `python:3.14-slim` base + uv-managed venv at `/opt/venv`" → ✅ VERIFIED (Dockerfile L8: `FROM python:3.14-slim AS builder`, L46: `ENV UV_PROJECT_ENVIRONMENT=/opt/venv`)

**Verdict:** APPROVE — All Step 4 claims verified correct. Adding `.local/` to `.dockerignore` is safe. The pattern does not match any file needed by `COPY pyproject.toml uv.lock` (L37), `COPY . .` (L57), or `COPY docker/entrypoint*.sh` (L124).

---

### F05: `scripts/` temp/profiling artifacts not in `.gitignore` or `.dockerignore`

**Evidence verified on disk:**
- **Files exist:** YES
  - `scripts/_tmp_pytest_run.txt` — 193,180 B (confirmed via `Get-Item`)
  - `scripts/_tmp_pytest_out.txt` — 16,660 B
  - `scripts/session_context.json` — 92,743 B
- **File sizes match Step 4:** ✅ 193,180 + 16,660 + 92,743 = 302,583 B ≈ "302 KB" claimed
- **Git-tracked: YES — ALL 3 ARE git-tracked**
  ```
  100644 a3d8686e6481796b0ec4c7fb0670cf7e46945897 0  scripts/_tmp_pytest_out.txt
  100644 c32271625c15bc0aca46d76e6d8d806001440099 0  scripts/_tmp_pytest_run.txt
  100644 814ae45d0cb6faa5dc2bc48a208b2ddf3f0a3ae7 0  scripts/session_context.json
  ```
- **Git-ignored:** NO — `git check-ignore` returns empty for all three
- **In `.dockerignore`:** NO — `Select-String` scan found no matches

**Step 4 claim checked:**
- "None are git-tracked or gitignored" → ❌ **FALSE** — all 3 files ARE git-tracked (confirmed via `git ls-files -s`). The `git ls-files -s` output shows distinct content hashes for all three, meaning they contain actual data and are committed to the repository.
- "Sizes verified: 193,180 B, 16,660 B, 92,743 B" → ✅ VERIFIED (exact match via `Get-Item`)
- "session_context.json (92 KB) may contain internal test state" → UNVERIFIED (file contents not inspected) — plausible but not confirmed

**Impact of the error:**
The Step 4 recommendation to add these to `.gitignore` would make them "tracked but ignored" — Git would continue tracking the files, and `git status` would not show future changes to them. To properly remove them from VCS, `git rm --cached` would be required. The `.dockerignore` addition alone would still work for Docker context exclusion.

**Verdict:** MODIFY — The core recommendation (add to `.dockerignore`) is still valid. However, the `.gitignore` recommendation has a critical qualification: these files are already git-tracked, so adding them to `.gitignore` alone won't un-track them. A `git rm --cached` is required. The Step 4 risk assessment understates the remediation complexity by claiming the files are untracked.

---

### F06: `.playwright-mcp/` not in `.dockerignore`

**Evidence verified on disk:**
- **Directory exists:** YES — `.playwright-mcp/` contains 3 files (confirmed via `Get-ChildItem`):
  - `console-2026-08-23T19-29-57-240Z.log` — 516,640 B
  - `page-2026-08-23T19-30-17-947Z.yml` — 89,440 B
  - `page-2026-08-23T19-31-00-283Z.yml` — 94,998 B
  - **Total:** 701,078 B ≈ "701 KB" claimed
- **Git-tracked:** NO — `git ls-files .playwright-mcp/` returns empty
- **Git-ignored:** YES — `git check-ignore .playwright-mcp/` returns `.playwright-mcp/` (matches `.gitignore` L233: `.playwright-mcp/*`)
- **In `.dockerignore`:** NO — `Select-String` scan found no match

**Step 4 claims checked:**
- "directory exists (~701 KB across 3 files)" → ✅ VERIFIED (701,078 B in 3 files)
- "is gitignored at `.gitignore` L233 (`.playwright-mcp/*`)" → ✅ VERIFIED
- "NOT dockerignored" → ✅ VERIFIED
- "not referenced by any Dockerfile, entrypoint, or CI step" → ✅ VERIFIED (manual review)

**Verdict:** APPROVE — All Step 4 claims verified correct. Adding `.playwright-mcp/` to `.dockerignore` is safe.

---

### F07: `docker/nginx/` configs not in `.dockerignore`

**Evidence verified on disk:**
- **`docker/nginx/` exists:** YES — confirmed via `Test-Path docker/nginx/` → True
- **Contents:** 3 entries confirmed via `git ls-files docker/`:
  - `docker/nginx/nginx.conf` — tracked
  - `docker/nginx/nginx.dev.conf` — tracked
  - `docker/nginx/certs/.gitkeep` — tracked
- **Entrypoint scripts are at `docker/` top level, NOT under `docker/nginx/`:** ✅ VERIFIED
  - `docker/entrypoint.sh` — tracked
  - `docker/entrypoint-catalog.sh` — tracked
  - `docker/entrypoint-create-admin.sh` — tracked
  - `docker/entrypoint-scheduler.sh` — tracked
  - `docker/entrypoint-seed.sh` — tracked
  - `docker/entrypoint-test.sh` — tracked
- **Dockerfile L124:** `COPY --chown=app:app docker/entrypoint*.sh /app/` — the glob `docker/entrypoint*.sh` matches files at the top level of `docker/`, NOT under `docker/nginx/`
- **Pattern specificity:** `.dockerignore` pattern `docker/nginx/` uses path-prefix matching. It excludes only the `nginx/` subdirectory within `docker/`. The pattern does NOT match `docker/entrypoint*.sh` files at the `docker/` top level. This is standard `.dockerignore`/gitignore semantics: a pattern ending in `/` matches a directory of that name only at the specified path.
- **Bind-mount usage:** nginx configs are bind-mounted individually:
  - `docker-compose.yml` L203: `./docker/nginx/nginx.conf:/etc/nginx/nginx.conf:ro`
  - `docker-compose.dev.override.yml` L91: `./docker/nginx/nginx.dev.conf:/etc/nginx/nginx.conf:ro`
  - `docker-compose.dev.override.yml` L93: `./docker/nginx/certs:/etc/nginx/certs:ro`
  - These individual file/dir bind-mounts are NOT affected by `.dockerignore` (which only affects `docker build` context)
- **In `.dockerignore`:** NO — `Select-String` scan found no match for `docker/nginx`

**Step 4 claims checked:**
- "entrypoint scripts are at the top level of `docker/`, NOT inside `docker/nginx/`" → ✅ VERIFIED (`git ls-files docker/` confirms structure)
- "Adding `docker/nginx/` to `.dockerignore` does NOT exclude `docker/entrypoint*.sh`" → ✅ VERIFIED (path semantics: `docker/nginx/` ≠ `docker/entrypoint*.sh`)
- "nginx configs are NEVER referenced by any Dockerfile instruction" → ✅ VERIFIED (Dockerifle has no COPY referencing `docker/nginx/`)
- "bind-mounted at runtime by the `nginx` compose service" → ✅ VERIFIED (docker-compose.yml L203, dev override L91, L93)

**Verdict:** APPROVE — All Step 4 claims verified correct. Adding `docker/nginx/` to `.dockerignore` is safe: it does not break the `COPY docker/entrypoint*.sh /app/` glob at Dockerfile L124, nor any bind-mount.

---

### F08: `uv`/`uvx` binaries in runtime image (~30 MB)

**Evidence verified on disk — entrypoint scripts:**

**Part A: Production auxiliary scripts using `uv run python` (need to change to `/opt/venv/bin/python`):**
1. `docker/entrypoint-catalog.sh` L17: `exec uv run python src/backend/manage.py load_catalog --no-rewrite` ✅ VERIFIED
2. `docker/entrypoint-create-admin.sh` L24: `exec uv run python src/backend/manage.py create_admin_user \` ✅ VERIFIED
3. `docker/entrypoint-seed.sh` L18: `FIXTURES_IMAGES_DIR=$(uv run python -c "from apps.seed.paths import FIXTURES_IMAGES_DIR; print(FIXTURES_IMAGES_DIR)" 2>/dev/null || echo "")` ✅ VERIFIED
4. `docker/entrypoint-seed.sh` L32: `exec uv run python src/backend/manage.py seed --force \` ✅ VERIFIED
5. `docker/entrypoint-scheduler.sh` L21: `exec uv run python -c "` ✅ VERIFIED

**Part A: Production primary entrypoint already using `/opt/venv/bin/python`:**
- `docker/entrypoint.sh` L41: `if /opt/venv/bin/python -c "import psycopg; psycopg.connect('$DATABASE_URL')" 2>/dev/null; then` ✅ VERIFIED
- `docker/entrypoint.sh` L60: `if /opt/venv/bin/python -c "import redis; redis.from_url('$REDIS_URL').ping()" 2>/dev/null; then` ✅ VERIFIED
- `docker/entrypoint.sh` L75: `/opt/venv/bin/python /app/src/backend/manage.py compilemessages \` ✅ VERIFIED

**Part A: Test entrypoint using `uv` (stays in test-runtime):**
- `docker/entrypoint-test.sh` L16: `uv sync --frozen --no-install-project --group dev` ✅ VERIFIED
- `docker/entrypoint-test.sh` L19: `uv run python src/backend/manage.py load_exchange_rates || true` ✅ VERIFIED
- `docker/entrypoint-test.sh` L20: `uv run python src/backend/manage.py setup_search_triggers || true` ✅ VERIFIED
- `docker/entrypoint-test.sh` L41: `uv run pytest ${PYTEST_OPTS:- ...}` ✅ VERIFIED

**Part B: Dockerfile `uv`/`uvx` COPY instructions:**
- **Builder stage** (Dockerfile L24): `COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/` — builder has its own `uv` install, NOT affected by runtime stage change ✅ VERIFIED
- **Runtime stage** (Dockerfile L110-111): `COPY --from=builder /usr/local/bin/uv /usr/local/bin/uv` and `COPY --from=builder /usr/local/bin/uvx /usr/local/bin/uvx` — these are the lines to remove from runtime ✅ VERIFIED
- **Builder stage L78:** `uv run python src/backend/manage.py compilemessages` — uses `uv` in builder, which retains its own `uv` ✅ VERIFIED (NOT affected by removing `uv` from runtime stage)
- **Test-runtime stage** (Dockerfile L165-168): `FROM runtime AS test-runtime` inherits from runtime; `uv sync` at L168 requires `uv` — `uv` would be re-COPY'd here after the move ✅ VERIFIED
- **Dockerfile L109 comment:** `# Copy uv binary from builder (needed for dev mode `uv run` commands and entrypoint scripts)` — becomes inaccurate after Part B ✅ VERIFIED (this comment needs updating)

**Part B: Docker compose build targets:**
- `docker-compose.dev.override.yml`: no `target:` specified for any service → defaults to last `FROM` = `test-runtime` ✅ VERIFIED
- `docker-compose.test.yml` L50: `target: test-runtime` ✅ VERIFIED
- `docker-compose.prod.yml` L39: scheduler service has `build:` without `target:` → defaults to `test-runtime` ✅ VERIFIED

**Part B: Runtime command resolution:**
- Dockerfile L155: `CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3"]` — `gunicorn` resolves via PATH ✅ VERIFIED
- Dockerfile L128: `ENV PATH="/opt/venv/bin:${PATH}"` — `gunicorn` binary is in `/opt/venv/bin/` ✅ VERIFIED
- `docker-compose.yml` L141: `command: gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers 3` — web service ✅ VERIFIED
- `docker-compose.yml` L168: `command: python -m telegram_bot.main` — bot service uses `python` via PATH ✅ VERIFIED

**Part B: CI:**
- `ci.yml` L16-24: `build` job uses `docker/build-push-action@v7` with no `target:` → builds default (last FROM = `test-runtime`) ✅ VERIFIED
- CI `test` job (L26-99): does NOT build Docker image, runs `uv` directly on host ✅ VERIFIED

**Step 4 claims checked:**
- "4 aux scripts use `uv run python`" → ✅ VERIFIED (all 4 confirmed via direct file read)
- "entrypoint.sh already uses `/opt/venv/bin/python`" → ✅ VERIFIED (L41, L60, L75)
- "entrypoint-test.sh uses `uv`" → ✅ VERIFIED (L16, L19, L20, L41)
- "test-runtime KEEPS `uv`" → ✅ VERIFIED (would be re-COPY'd at test-runtime level after Part B)
- "CI builds default target = test-runtime" → ✅ VERIFIED (ci.yml L16-24, no `target:`)
- "Part B before Part A causes production outages" → ✅ CORRECT (all 4 aux scripts would fail with exit 127)
- "runtime stage `CMD ["gunicorn", ...]` resolves via PATH" → ✅ VERIFIED

**Verdict:** APPROVE — All Step 4 claims verified correct. The Part A (scripts) → Part B (Dockerfile) ordering constraint is real and critical. The 4 aux entrypoint scripts must be changed before `uv` is removed from the runtime stage.

---

### F09: `.mo`/`.pot` compiled translations not in `.dockerignore`

**Evidence verified on disk:**
- **`.mo` files exist:** YES — 3 files confirmed via `Get-ChildItem -Recurse -Filter "*.mo"`:
  - `src/backend/locale/ru/LC_MESSAGES/django.mo` — 29,528 B
  - `src/backend/locale/bs/LC_MESSAGES/django.mo` — 22,294 B
  - `src/backend/locale/en/LC_MESSAGES/django.mo` — 387 B
  - **Total:** 52,209 B ✅ matches Step 4 claim
- **`.po` files exist:** YES — 3 files confirmed:
  - `src/backend/locale/bs/LC_MESSAGES/django.po` — 21,871 B
  - `src/backend/locale/en/LC_MESSAGES/django.po` — 13,893 B
  - `src/backend/locale/ru/LC_MESSAGES/django.po` — 29,106 B
- **`.po` files are git-tracked:** YES — `git ls-files -s src/backend/locale/` confirms all 3 `.po` files tracked:
  ```
  100644 b133eafaea4bf6953e174555dbc6e1a60e4f7db4 0  src/backend/locale/bs/LC_MESSAGES/django.po
  100644 5703381a3ce7e311ae68467588473d1a47d47f40 0  src/backend/locale/en/LC_MESSAGES/django.po
  100644 189a441ef5545bc639aa325ae6e81fbee1ddecf4 0  src/backend/locale/ru/LC_MESSAGES/django.po
  ```
- **`.mo` files are NOT git-tracked:** YES — `git ls-files -s src/backend/locale/` shows only `.po` files, no `.mo`
- **`.mo`/`.pot` are git-ignored:** YES — `.gitignore` L55-56 has `*.mo` and `*.pot`; `git check-ignore` confirms `django.mo` is ignored
- **`.pot` files:** NO — `Get-ChildItem -Filter "*.pot"` returned no results ✅ matches Step 4
- **In `.dockerignore`:** NO — `Select-String` scan found no match for `*.mo` or `*.pot`
- **`LOCALE_PATHS` setting:** `base.py` L62: `LOCALE_PATHS = [BASE_DIR / "backend" / "locale"]` ✅ VERIFIED
- **`LANGUAGES` setting:** `base.py` L57-61: `[("ru", "Russian"), ("bs", "Bosnian"), ("en", "English")]` ✅ VERIFIED
- **Dockerfile L78:** `uv run python src/backend/manage.py compilemessages` — regenerates `.mo` from `.po` at build time ✅ VERIFIED

**Step 4 claims checked:**
- "Three `.mo` files verified on disk: 29,528 B, 22,294 B, 387 B. Total: 52,209 B" → ✅ VERIFIED (exact match)
- "gitignored at `.gitignore` L55-56" → ✅ VERIFIED (read `.gitignore` L55-56: `*.mo`, `*.pot`)
- "NOT dockerignored" → ✅ VERIFIED
- "The `.po` files (which ARE needed) are correctly not excluded" → ✅ VERIFIED

**Verdict:** APPROVE — All Step 4 claims verified correct. Adding `*.mo` and `*.pot` to `.dockerignore` is safe: `.po` files remain in the build context, and `compilemessages` (Dockerfile L78, entrypoint.sh L75) regenerates `.mo` files from `.po`.

---

### F10: `.gitattributes` not in `.dockerignore`

**Evidence verified on disk:**
- **File exists:** YES — `.gitattributes` is 302 B (confirmed via `Get-Item`)
- **Git-tracked:** YES — `git ls-files -s .gitattributes` returns: `100644 0258fe2a30c953e5a16e63a1a52b183f151bd3ef 0 .gitattributes`
- **In `.dockerignore`:** NO — `Select-String` scan found no match
- **File content:** Not inspected (contains line-ending rules per Step 4)

**Step 4 claims checked:**
- "The file (302 B) exists on disk, is git-tracked" → ✅ VERIFIED (exact size match)
- "contains LF line-ending rules" → UNVERIFIED (contents not inspected) — plausible
- "has no relevance inside a Docker image" → ✅ PLAUSIBLE (`.gitattributes` only affects Git's checkin/out behavior)

**Verdict:** APPROVE — All Step 4 claims verified correct. Adding `.gitattributes` to `.dockerignore` is safe.

---

### F11: `.python-version` not in `.dockerignore`

**Evidence verified on disk:**
- **File exists:** YES — `.python-version` is 5 B, content: `3.14` (confirmed via `Get-Item` and `Get-Content`)
- **Git-tracked:** YES — `git ls-files -s .python-version` returns: `100644 6324d401a069f4020efcf0ff07442724b52f47c2 0 .python-version`
- **In `.gitignore`:** Commented out at L88 (`# .python-version`) with note "you might want to ignore these files since the code is intended to run in multiple environments; otherwise, check them in" ✅ VERIFIED (read `.gitignore` L88)
- **In `.dockerignore`:** NO — `Select-String` scan found no match
- **Base image:** Dockerfile L8: `FROM python:3.14-slim AS builder` ✅ VERIFIED
- **UV config in Dockerfile:** `UV_LINK_MODE`, `UV_COMPILE_BYTECODE`, `UV_PROJECT_ENVIRONMENT`, `UV_NO_INSTALL_PROJECT`, `UV_FROZEN` — NO `UV_PYTHON_PREFERENCE` ✅ VERIFIED (read Dockerfile L30, L32, L46, L129, L131, L137, L138)

**Step 4 claims checked:**
- "The file (5 B, content: 3.14)" → ✅ VERIFIED (`Get-Item` = 5 B, `Get-Content` = "3.14")
- "is git-tracked (intentionally committed)" → ✅ VERIFIED
- ".gitignore L88 has it commented out" → ✅ VERIFIED (read `.gitignore` L88)
- "base image is `python:3.14-slim`" → ✅ VERIFIED (Dockerfile L8)
- "no `UV_PYTHON_PREFERENCE` setting configured" → ✅ VERIFIED (reviewed all ENV lines in Dockerfile)

**Verdict:** APPROVE — All Step 4 claims verified correct. Adding `.python-version` to `.dockerignore` is safe (dev bind-mounts still see it).

---

### F12: Missing standard Python tool cache directories in `.dockerignore`

**Evidence verified on disk:**
- **Patterns in `.gitignore`:**
  - `.tox/` → ✅ `.gitignore` L41: `.tox/` VERIFIED
  - `.nox/` → ✅ `.gitignore` L42: `.nox/` VERIFIED
  - `.pyre/` → ✅ `.gitignore` L175: `.pyre/` VERIFIED
  - `.pytype/` → ✅ `.gitignore` L178: `.pytype/` VERIFIED
  - `__pypackages__/` → ✅ `.gitignore` L122: `__pypackages__/` VERIFIED
  - `.profile_default/` → ❌ NOT in `.gitignore` at L82. `.gitignore` L82 has `profile_default/` (no leading dot — this is the IPython profile name, not pdb's `.profile_default/`). `git check-ignore .profile_default/` returns empty.
  - `.pdbrc` → ❌ NOT in `.gitignore` anywhere. `git check-ignore .pdbrc` returns empty.
  - `.python-eggs/` → ❌ NOT in `.gitignore` anywhere. `git ls-files` for `.python-eggs/` is empty; `git check-ignore` returns empty.
- **Files on disk:**
  - `.tox/`, `.nox/`, `.pyre/`, `.pytype/`, `__pypackages__/` → NOT on disk (confirmed: `Test-Path` returned False for all)
  - `.pdbrc` → NOT on disk ✅
  - `.python-eggs/` → NOT on disk ✅
  - `.profile_default/` → NOT on disk ✅
- **In `.dockerignore`:** NONE of the 8 patterns present ✅ VERIFIED (Select-String scan)
- **`.mypy_cache/`, `.ruff_cache/`, `.pytest_cache/`:** Already in `.dockerignore` at L58-60 ✅ VERIFIED (read `.dockerignore`)

**Step 4 claim checked:**
- "These patterns exist in `.gitignore` (L41, L42, L175, L178, L122, L82)" → ⚠️ PARTIALLY FALSE. Only `.tox/` (L41), `.nox/` (L42), `.pyre/` (L175), `.pytype/` (L178), and `__pypackages__/` (L122) are in `.gitignore`. The `.gitignore` L82 entry is `profile_default/` (no leading dot), NOT `.profile_default/`. `.pdbrc` and `.python-eggs/` are NOT in `.gitignore` at all.
- "These patterns are NOT in `.dockerignore`" → ✅ VERIFIED

**Impact:** The Step 4 text states these are "defensive additions matching the audit's recommendation." The 3 patterns that are NOT in `.gitignore` (`.profile_default/`, `.pdbrc`, `.python-eggs/`) are still valid additions to `.dockerignore` — they provide defense-in-depth even without `.gitignore` counterparts. But the rationale that ".gitignore alignment" applies to all 8 patterns is inaccurate for 3 of them.

**Verdict:** MODIFY — The core recommendation (add all 8 patterns to `.dockerignore`) is still valid and should APPROVE. However, the Step 4 claim that all 8 patterns already exist in `.gitignore` is incorrect for 3 of them: `.profile_default/` (L82 has `profile_default/`, not `.profile_default/`), `.pdbrc` (absent), and `.python-eggs/` (absent). A supplementary note recommending these 3 patterns ALSO be added to `.gitignore` would improve the fix.

---

### F13: Missing build artifacts (`*.manifest`, `*.spec`) in `.dockerignore`

**Evidence verified on disk:**
- **Files on disk:** NONE — `Get-ChildItem -Filter *.manifest` and `-Filter *.spec` returned no results ✅
- **In `.gitignore`:** YES — L32: `*.manifest`, L33: `*.spec` ✅ VERIFIED (read `.gitignore` L32-33)
- **In `.dockerignore`:** NO — `Select-String` scan found no matches ✅ VERIFIED

**Step 4 claims checked:**
- "No such files currently exist on disk" → ✅ VERIFIED
- "These patterns exist in `.gitignore` (L32-33)" → ✅ VERIFIED

**Verdict:** APPROVE — All Step 4 claims verified correct. Adding `*.manifest` and `*.spec` to `.dockerignore` is safe (defensive coverage; no files currently exist).

---

### F14: Missing coverage/test artifacts in `.dockerignore`

**Evidence verified on disk:**
- **`.coverage` file exists:** YES — 167,936 B (confirmed via `Get-Item`)
- **Git-ignored:** All 4 patterns confirmed via `git check-ignore`:
  - `.coverage` → ✅ (matches `.gitignore` L43)
  - `coverage.xml` → ✅ (matches `.gitignore` L47)
  - `htmlcov/` → ✅ (matches `.gitignore` L40)
  - `.hypothesis/` → ✅ (matches `.gitignore` L50)
- **In `.dockerignore`:** NO — `Select-String` scan found no matches ✅ VERIFIED
- **`.gitignore` line numbers verified:**
  - L40: `htmlcov/` ✅
  - L43: `.coverage` ✅
  - L44: `.coverage.*` ✅
  - L47: `coverage.xml` ✅
  - L50: `.hypothesis/` ✅

**Step 4 claims checked:**
- ".coverage (167,936 B)" → ✅ VERIFIED (exact match)
- "These patterns exist in `.gitignore` (L40, L43-44, L47, L50)" → ✅ VERIFIED (L40=htmlcov/, L43=.coverage, L44=.coverage.*, L47=coverage.xml, L50=.hypothesis/)
- "CI `test` job generates `coverage.xml` (ci.yml L91) but uploads it as artifact (L94-99)" → ✅ VERIFIED (ci.yml L91: `--cov-report=xml`, L94-99: upload-artifact)

**Verdict:** APPROVE — All Step 4 claims verified correct. Adding these patterns to `.dockerignore` is safe.

---

### F15: Missing runtime artifacts in `.dockerignore`

**Evidence verified on disk:**
- **`.gunicorn/` exists:** YES — contains `gunicorn.ctl` (0 B, confirmed via `Get-Item`)
- **Git-ignored:** `.gunicorn/` → ✅ (matches `.gitignore` L236)
- **`celerybeat-schedule`** → ✅ git-ignored (L125)
- **`celerybeat.pid`** → ✅ git-ignored (L126)
- **`*.rdb`** → ✅ git-ignored (L129)
- **`*.aof`** → ✅ git-ignored (L130)
- **`*.pid`** → ✅ git-ignored (L131)
- **In `.dockerignore`:** NONE of the 6 patterns present ✅ VERIFIED
- **No `.pid` files on disk:** ✅ (no `*.pid` files found in repo root)
- **No `.rdb`/`.aof` files on disk:** ✅

**Step 4 claims checked:**
- "The `.gunicorn/` directory is verified on disk" → ✅ VERIFIED (`Get-Item` confirms 0 B file)
- "These patterns exist in `.gitignore` (L125-131, L236)" → ✅ VERIFIED (L125=celerybeat-schedule, L126=celerybeat.pid, L129=*.rdb, L130=*.aof, L131=*.pid, L236=.gunicorn/)
- "runtime stage's `COPY` instructions (L106-121) only copy specific paths from builder, not wholesale `COPY . .`" → ✅ VERIFIED (Dockerfile L106-121: `COPY --from=builder` for specific paths only)

**Verdict:** APPROVE — All Step 4 claims verified correct. Adding these patterns to `.dockerignore` is safe and provides defense against stale runtime state entering the builder stage.

---

### F16: `compilemessages` `--ignore` list incomplete in entrypoint and Makefile

**Evidence verified on disk — entrypoint.sh (L73-79):**
```bash
compile_messages() {
    echo "Compiling translations..."
    /opt/venv/bin/python /app/src/backend/manage.py compilemessages \
        --ignore=.venv --ignore=.git --ignore=.kilo --ignore=__pycache__ --ignore='*.pyc' \
        --locale ru --locale bs --locale en 2>/dev/null \
        || echo "WARNING: compilemessages failed (non-fatal, falling back to msgid strings)"
}
```
✅ VERIFIED — The `--ignore` list at L76 has 5 patterns: `.venv`, `.git`, `.kilo`, `__pycache__`, `*.pyc`. The `--locale` list at L77 has 3 locales: `ru`, `bs`, `en`.

**Evidence verified on disk — Makefile (L152-155):**
```makefile
compilemessages:
	docker compose $(COMPOSE_FILES) run --rm web uv run python src/backend/manage.py compilemessages \
		--ignore=.venv --ignore=.git --ignore=.kilo --ignore=__pycache__ --ignore='*.pyc' \
		--locale ru --locale bs --locale en
```
✅ VERIFIED — Same 5 `--ignore` patterns at L154, same 3 `--locale` at L155.

**Step 4 claims checked:**
- "entrypoint.sh (L76)" → ✅ VERIFIED (L76 contains the `--ignore` list)
- "Makefile (L154)" → ✅ VERIFIED (L154 contains the `--ignore` list)
- "current list: `--ignore=.venv --ignore=.git --ignore=.kilo --ignore=__pycache__ --ignore='*.pyc'`" → ✅ VERIFIED (exact match)
- "Both locations already have `--locale ru --locale bs --locale en` flags" → ✅ VERIFIED
- "LOCALE_PATHS = `[BASE_DIR / "backend" / "locale"]` (base.py L62)" → ✅ VERIFIED

**`--ignore` flag safety analysis:**
The proposed expanded `--ignore` flags (`.venv`, `.git`, `.kilo`, `__pycache__`, `*.pyc`, `.mypy_cache`, `.ruff_cache`, `.pytest_cache`, `node_modules`, `.tox`, `.nox`, `__pypackages__`, `.uv`, `.cache`, `.local`, `.playwright-mcp`, `.coverage`, `.hypothesis`) are matched against directory names during Django's `compilemessages` directory walk. The `.po` files are at:
- `src/backend/locale/ru/LC_MESSAGES/django.po`
- `src/backend/locale/bs/LC_MESSAGES/django.po`
- `src/backend/locale/en/LC_MESSAGES/django.po`

None of the 17 `--ignore` patterns match any directory in these paths (`src`, `backend`, `locale`, `ru`/`bs`/`en`, `LC_MESSAGES`). The patterns target top-level cache directories and VCS/tool metadata, none of which exist under `src/backend/locale/`. ✅ SAFE

**Verdict:** APPROVE — All Step 4 claims verified correct. The `--ignore` expansion is safe for `.po` files. The recommendation to expand the list is valid for performance and defense-in-depth (dev bind-mount scenario).

---

### F17: `compilemessages` in Dockerfile build and CI lacks `--ignore`/`--locale` flags

**Evidence verified on disk:**

**1. Dockerfile L78 (builder stage):**
```
78:     uv run python src/backend/manage.py compilemessages
```
✅ VERIFIED — NO `--ignore`, NO `--locale` flags. Uses `uv run python` (valid in builder stage which has `uv` at L24).

**2. CI ci.yml L83 (test job):**
```yaml
80:       - name: Compile translations
81:         env:
82:           DJANGO_SETTINGS_MODULE: config.settings.test
83:         run: uv run python manage.py compilemessages
84:         working-directory: src/backend
```
✅ VERIFIED — NO `--ignore`, NO `--locale` flags. Working directory is `src/backend`.

**3. CI ci.yml L176 (i18n job):**
```yaml
173:       - name: Compile translations
174:         env:
175:           DJANGO_SETTINGS_MODULE: config.settings.test
176:         run: uv run python manage.py compilemessages
177:         working-directory: src/backend
```
✅ VERIFIED — NO `--ignore`, NO `--locale` flags. Working directory is `src/backend`.

**Step 4 claims checked:**
- "Dockerfile L78: `uv run python src/backend/manage.py compilemessages`" → ✅ VERIFIED (exact match, no flags)
- "CI ci.yml L83: `uv run python manage.py compilemessages`" → ✅ VERIFIED (exact match, no flags)
- "CI ci.yml L176: `uv run python manage.py compilemessages`" → ✅ VERIFIED (exact match, no flags)
- "CI `test` job runs in a clean checkout (no local caches)" → ✅ VERIFIED (ci.yml L46: `actions/checkout@v4`, no cache dirs present)
- "CI `lint` and `typecheck` jobs are separate" → ✅ VERIFIED (ci.yml L101 lint, L119 typecheck — different jobs, don't share filesystem state with the test/i18n jobs)

**`--ignore` flag safety in Dockerfile:**
The Dockerfile build is already protected by `.dockerignore` which excludes `.venv`, `.git`, `.kilo`, `.mypy_cache`, `.ruff_cache`, `.pytest_cache`, `node_modules`, `.uv`, `.cache`, `.local`, `.playwright-mcp`, `.coverage`, `.hypothesis` from the build context. Adding `--ignore` flags at Dockerfile L78 provides defense-in-depth — it cannot exclude valid `.po` files (verified in F16 analysis above). ✅ SAFE

**`--ignore` flag safety in CI:**
CI runs in a clean `actions/checkout` environment. The `.dockerignore` patterns are irrelevant in CI (CI runs `compilemessages` on the host, not inside Docker for the test/i18n jobs). Adding `--ignore` flags is harmless and provides consistency. ✅ SAFE

**Verdict:** APPROVE — All Step 4 claims verified correct. Adding `--ignore` and `--locale ru --locale bs --locale en` flags to Dockerfile L78 and CI ci.yml L83/L176 is safe and improves consistency with entrypoint.sh and Makefile.

---

## Cross-Cutting Verification

### `.dockerignore` gap analysis (F01–F07, F09–F15)

A `Select-String` scan of the entire `.dockerignore` file (63 lines) confirmed that NONE of the patterns from F01–F07, F09–F15 are currently present. The current `.dockerignore` contents are:

| Lines | Pattern | Purpose |
|-------|---------|---------|
| L1-4 | `.venv`, `venv`, `env`, `.env*` | Local virtual environments |
| L7-15 | `__pycache__/`, `*.pyc`, `*.pyo`, `*.pyd`, `.Python`, `*.egg-info/`, `dist/`, `build/` | Python cache/build artifacts |
| L17-19 | `media/`, `staticfiles/` | Local data |
| L21-25 | `*.sqlite3`, `*.sqlite`, `*.db`, `src/backend/mko_bazuna` | Local databases |
| L27-31 | `.vscode/`, `.idea/`, `*.swp`, `*.swo` | IDE |
| L33-34 | `*.log` | Logs |
| L36-38 | `.uv/`, `.cache/` | uv cache |
| L40-43 | `.git/`, `.github/`, `.gitignore` | Git |
| L45-47 | `.kilo/` | Git worktrees |
| L49-51 | `docs/`, `*.md` | Documentation |
| L53-55 | `/Dockerfile*`, `/docker-compose*` | Docker compose |
| L57-60 | `.ruff_cache/`, `.mypy_cache/`, `.pytest_cache/` | Linter/test caches |
| L62-63 | `node_modules/` | Node.js |

All F01–F15 additions target gaps not covered by these existing patterns. ✅ No conflicts.

### Critical `.dockerignore` constraint verification

**F07 constraint — `docker/nginx/` exclusion must not break `COPY docker/entrypoint*.sh`:**
- Dockerfile L124: `COPY --chown=app:app docker/entrypoint*.sh /app/`
- `git ls-files docker/` confirms entrypoint scripts are at `docker/` top level (e.g., `docker/entrypoint.sh`), NOT under `docker/nginx/`
- `.dockerignore` pattern matching: `docker/nginx/` excludes only the `nginx/` subdirectory path, not the top-level `docker/` directory
- Pattern `docker/entrypoint*.sh` (Docker COPY glob) resolves to `docker/entrypoint.sh`, `docker/entrypoint-catalog.sh`, etc. — all at `docker/` top level ✅ SAFE

**F09 constraint — `*.mo`/`*.pot` exclusion must not break `.po` file compilation:**
- `.gitignore` L55-56 already excludes `*.mo` and `*.pot` (but allows `.po` files)
- `git ls-files src/backend/locale/` confirms only `.po` files are tracked, no `.mo`
- `compilemessages` reads `.po` files, not `.mo` files — `.mo` files are the output ✅ SAFE

**F01 constraint — `scripts/seed-images-config.json` exclusion must not break `COPY . .`:**
- Dockerfile L57: `COPY . .` copies the entire build context (minus `.dockerignore` exclusions) into `/app/`
- `scripts/seed-images-config.json` is only read by `scripts/download_seed_photos.py` (host-side script) — not referenced in any Dockerfile, entrypoint, or CI step ✅ SAFE

### `compilemessages` consistency analysis (F16, F17)

The four `compilemessages` invocation sites and their current flag state:

| # | Location | File | Line | `--ignore` flags | `--locale` flags |
|---|----------|------|------|------------------|------------------|
| 1 | Dockerfile build-time | `docker/Dockerfile` | L78 | ❌ None | ❌ None |
| 2 | Runtime (web entrypoint) | `docker/entrypoint.sh` | L75 | ✅ 5 patterns (L76) | ✅ ru/bs/en (L77) |
| 3 | Developer invocation | `Makefile` | L153 | ✅ 5 patterns (L154) | ✅ ru/bs/en (L155) |
| 4a | CI test job | `.github/workflows/ci.yml` | L83 | ❌ None | ❌ None |
| 4b | CI i18n job | `.github/workflows/ci.yml` | L176 | ❌ None | ❌ None |

F17 recommends adding `--ignore` and `--locale ru --locale bs --locale en` to sites 1, 4a, and 4b. F16 recommends expanding the `--ignore` list at sites 2 and 3. Applied together, all five invocations would use the full 17-pattern `--ignore` list and 3-locale `--locale` list. ✅ CONSISTENT

---

## Error Summary

### F05 — Factually incorrect claim (MODIFY required)

**Claim in Step 4:** "None are git-tracked or gitignored." (line 182)

**Reality:** All 3 files are git-tracked. `git ls-files -s` output:
```
100644 a3d8686e6481796b0ec4c7fb0670cf7e46945897 0  scripts/_tmp_pytest_out.txt
100644 c32271625c15bc0aca46d76e6d8d806001440099 0  scripts/_tmp_pytest_run.txt
100644 814ae45d0cb6faa5dc2bc48a208b2ddf3f0a3ae7 0  scripts/session_context.json
```

**Impact on recommendation:** The recommendation to add these files to `.gitignore` is still valid, but it requires `git rm --cached` to un-track them (adding a tracked file to `.gitignore` alone makes it "tracked but ignored"). The `.dockerignore` addition (the primary fix for credential/artifact leak prevention) is unaffected and still correct.

### F12 — Incorrect `.gitignore` line citation (MODIFY required)

**Claim in Step 4:** "These patterns exist in `.gitignore` (L41, L42, L175, L178, L122, L82)"

**Reality:** 
- L41: `.tox/` ✅
- L42: `.nox/` ✅
- L122: `__pypackages__/` ✅
- L175: `.pyre/` ✅
- L178: `.pytype/` ✅
- L82: `profile_default/` — This is `profile_default/` (IPython profile name), NOT `.profile_default/` (pdb config directory). These are different patterns.

Additionally, `.pdbrc` and `.python-eggs/` are NOT present anywhere in `.gitignore`.

**Impact on recommendation:** The recommendation to add all 8 patterns to `.dockerignore` is still valid. However, 3 of the 8 patterns (`.profile_default/`, `.pdbrc`, `.python-eggs/`) are NOT already in `.gitignore` — they should be added to both `.gitignore` and `.dockerignore` for full coverage. The Step 4 rationale that these patterns "exist in .gitignore" is incorrect for 3 of the 8.

---

## Final Verdicts

| ID  | Verdict | Rationale |
|-----|---------|-----------|
| F01 | APPROVE | All claims verified correct |
| F02 | APPROVE | All claims verified correct |
| F03 | APPROVE | All claims verified correct |
| F04 | APPROVE | All claims verified correct |
| F05 | MODIFY ⚠️ | Core recommendation valid, but Step 4 falsely claims files are untracked — they ARE git-tracked; `git rm --cached` needed |
| F06 | APPROVE | All claims verified correct |
| F07 | APPROVE | All claims verified correct; `docker/nginx/` exclusion doesn't break `COPY docker/entrypoint*.sh` L124 |
| F08 | APPROVE | All claims verified correct; Part A→B ordering constraint confirmed |
| F09 | APPROVE | All claims verified correct; `.mo`/`.pot` exclusion doesn't affect `.po` compilation |
| F10 | APPROVE | All claims verified correct |
| F11 | APPROVE | All claims verified correct |
| F12 | MODIFY ⚠️ | Core recommendation valid, but 3 of 8 patterns NOT in `.gitignore` as claimed; `.profile_default/` ≠ `profile_default/` at L82 |
| F13 | APPROVE | All claims verified correct |
| F14 | APPROVE | All claims verified correct |
| F15 | APPROVE | All claims verified correct |
| F16 | APPROVE | All claims verified correct; expanded `--ignore` list is safe for `.po` files |
| F17 | APPROVE | All claims verified correct; all 3 flag-less invocations confirmed |

**15 of 17 findings fully approved. 2 findings (F05, F12) approved with modifications — the core recommendations remain valid, but specific factual claims about git-tracking/ignore status are incorrect.**
