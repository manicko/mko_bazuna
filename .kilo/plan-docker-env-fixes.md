# Docker Compose Environment Variable Fixes — Implementation Plan

## Overview

Decomposition of 13 accepted findings (ENV-001 through ENV-013, plus 3 ENV-files-audit findings) into atomic, implementation-ready tasks. All changes preserve the production contract (`docker-compose.yml` is not modified for ENV-002). Each task is independently verifiable via `docker compose config` or `grep`.

Priority ordering: **Critical → High → Medium → Low**, with dependency-aware sequencing for same-file edits.

---

## Dependency & File-Collision Graph

All tasks touching `docker-compose.test.yml` are **sequential** (one Implementor at a time, same file). Tasks touching `Makefile.ps1` are likewise sequential. All other tasks touch distinct files and can proceed in any order between them.

```
docker-compose.test.yml (sequential):
  ENV-013 (db cleanup) → ENV-003 (migrate/create_admin volumes) → ENV-002 (5 service overrides)
    → ENV-004 (env_file doc comment) → ENV-007 (update inaccurate comments)

Makefile.ps1 (sequential):
  ENV-files-audit Finding 2 (7 functions) → ENV-files-audit Finding 3 (Invoke-FullClean)

Cross-file (parallel-safe, one Implementor):
  ENV-001, ENV-005, ENV-006, ENV-009, ENV-010, ENV-012, Finding 4
```

---

## Tasks

### Task 1 — ENV-001/ENV-011: Add `.env` exclusion patterns to `.dockerignore`
- **Priority:** CRITICAL
- **Description:** Add `src/.env` and `**/.env*` patterns to `.dockerignore`. The current `.env*` pattern only matches dotfiles at the repo root; `src/.env` (the bind-mount path) and nested `.env*` files are not excluded from the Docker build context. This covers both ENV-001 and ENV-011 (same root cause).
- **Files:** `.dockerignore`
- **Acceptance criteria:**
  - `grep -n 'src/.env' .dockerignore` returns the new `src/.env` line
  - `grep -n '**/.env*' .dockerignore` returns the new `**/.env*` pattern
  - `src/.env` is not present in `docker build` context (verified by `docker build --no-cache --target builder .` context listing or `COPY --from=0 /app/src/.env` failing — context test)
- **Dependencies:** none

---

### Task 2 — ENV-005: Add 6 missing variables to `.env.test` and `.env.test.example`
- **Priority:** HIGH
- **Description:** Add the following 6 variables to both `.env.test` and `.env.test.example` with test-appropriate values (empty strings, `false`, etc.), matching the sections already present in `.env.dev.example`:
  - `GOOGLE_TRANSLATE_API_KEY` → empty string (translations fall back to original text)
  - `SITE_URL` → `http://localhost:8000`
  - `IMMEDIATE_ALERTS_ENABLED` → `false`
  - `TLS_CERT_PATH` → `/etc/nginx/certs`
  - `PLAUSIBLE_HOST` → empty string
  - `FIX_PERMISSIONS` → `0`
- **Files:** `.env.test`, `.env.test.example`
- **Acceptance criteria:**
  - All 6 variables present in both files
  - Values are test-appropriate (no production secrets)
  - No existing variables are modified (only additions)
- **Dependencies:** none
- **Note:** This is a prerequisite for Task 5 (ENV-002) — the overridden services reference `.env.test` which must contain all needed variables.

---

### Task 3 — ENV-013: Clean up `db` service in test compose
- **Priority:** MEDIUM
- **Description:** In `docker-compose.test.yml`, remove `env_file: .env.test`, the `.env.test:/app/src/.env` volume bind-mount, and `DJANGO_SETTINGS_MODULE` from the test `db` service. PostgreSQL doesn't read Django env vars; these are unnecessary noise. Keep `DATABASE_URL`, PostgreSQL runtime vars (from base compose), ports (`5433:5432`), and the healthcheck. The `POSTGRES_*` vars are resolved via `--env-file .env.test` at the `docker compose` command level.
- **Files:** `docker-compose.test.yml`
- **Acceptance criteria:**
  - `docker compose --env-file .env.test -f docker-compose.yml -f docker-compose.test.yml config db` shows no `env_file` key, no `.env.test` volume, no `DJANGO_SETTINGS_MODULE` on the `db` service
  - `DATABASE_URL`, `ports`, and `healthcheck` are still present
- **Dependencies:** none
- **Note:** Must be applied before other `docker-compose.test.yml` edits (sequential ordering — this service block is first in the file).

---

### Task 4 — ENV-003: Fix volumes for `migrate` and `create_admin` in test compose using `!override`
- **Priority:** HIGH
- **Description:** In `docker-compose.test.yml`, the current `migrate` and `create_admin` test overrides do not specify `volumes`, so Docker Compose **concatenates** them with the base compose's volumes (which include `.env.dev:/app/src/.env:ro`). Fix by adding `volumes: !override ["./.env.test:/app/src/.env:ro"]` to both service overrides. The `!override` tag is the Compose-spec way to replace (not append) the volume list.
- **Files:** `docker-compose.test.yml`
- **Acceptance criteria:**
  - `docker compose --env-file .env.test -f docker-compose.yml -f docker-compose.test.yml config migrate` shows only `.env.test:/app/src/.env:ro` volume — NO `.env.dev` volume
  - Same for `create_admin`
  - No `!override` tag leaks in `docker compose config` output (it's resolved at parse time)
- **Dependencies:** Task 3 (ENV-013) — same file, must be applied after db service cleanup

---

### Task 5 — ENV-002: Add comprehensive overrides for `bot`, `web`, `load_cities`, `load_catalog`, `seed`
- **Priority:** CRITICAL
- **Description:** In `docker-compose.test.yml`, add full service overrides for the 5 services that currently lack test overrides. Each gets:
  - `env_file: [.env.test]`
  - `volumes: !override ["./.env.test:/app/src/.env:ro"]` + `media_volume:/app/media` (for `web`, `bot`, `seed`)
  - `environment:` with `DJANGO_SETTINGS_MODULE=config.settings.test`
  - Do NOT modify `docker-compose.yml` (production contract preserved).
- **Files:** `docker-compose.test.yml`
- **Acceptance criteria:**
  - `docker compose --env-file .env.test -f docker-compose.yml -f docker-compose.test.yml config` shows all 5 services with `env_file: .env.test`, `DJANGO_SETTINGS_MODULE=config.settings.test`, and `!override` volumes (only `.env.test` bind-mount, no `.env.dev`)
  - `web`, `bot`, and `seed` also show `media_volume:/app/media`
  - No service inherits `config.settings.prod` or `.env.dev` volume
- **Dependencies:** Task 2 (ENV-005 — `.env.test` must have all variables), Task 4 (ENV-003 — same file ordering)

---

### Task 6 — ENV-004: Document `env_file` invisibility in test compose
- **Priority:** HIGH
- **Description:** Add a documentation comment to `docker-compose.test.yml` explaining that `env_file` is resolved and consumed by Docker Compose before `docker compose config` renders its output — the key does not appear in `config` output but is still applied at container start. Place the comment near the top of the file or above the first `env_file:` usage.
- **Files:** `docker-compose.test.yml`
- **Acceptance criteria:**
  - Comment present and explains: (a) `env_file` vars are applied at runtime, (b) they don't appear in `docker compose config` output, (c) use `--env-file` on the command line for interpolation context
  - Comment is in English and follows the existing comment style
- **Dependencies:** Task 5 (ENV-002) — the comment explains the pattern used by the new service overrides

---

### Task 7 — ENV-007: Update inaccurate comments in test compose
- **Priority:** MEDIUM
- **Description:** After all structural changes (ENV-013, ENV-003, ENV-002), audit and update all comments in `docker-compose.test.yml` to accurately reflect the final configuration. Specifically: (a) the `db` service comment about volumes, (b) the `migrate` comment, (c) the `create_admin` comment, and (d) any stale references to `.env.dev` in test compose.
- **Files:** `docker-compose.test.yml`
- **Acceptance criteria:**
  - No comment references `.env.dev` in the test compose file
  - All comments accurately describe the current configuration
  - `docker compose config` output matches what the comments describe
- **Dependencies:** Tasks 3, 4, 5, 6 (ENV-013, ENV-003, ENV-002, ENV-004) — all structural changes must be done first

---

### Task 8 — ENV-006: Add env-sourcing preamble to Makefile shell-var targets
- **Priority:** HIGH
- **Description:** In the bash `Makefile`, add `set -a; . .env.dev; set +a` preamble to the `db-shell`, `backup`, `restore`, and `create-admin` targets. These targets use `$${POSTGRES_USER}` / `$${POSTGRES_DB}` shell expansion, which requires the `.env.dev` variables to be in the shell's environment. Other targets (lint, format, typecheck, etc.) use `$(COMPOSE_FILES)` which handles Docker Compose interpolation — they do NOT need this preamble.
- **Files:** `Makefile`
- **Acceptance criteria:**
  - `grep -n "set -a; . .env.dev; set +a" Makefile` returns 4 matches (db-shell, backup, restore, create-admin)
  - `make -n db-shell` (dry run) shows the sourcing preamble before the `docker compose exec` line
  - Targets `lint`, `format`, `typecheck`, `makemessages`, `compilemessages` do NOT have the preamble (not needed)
- **Dependencies:** none

---

### Task 9 — ENV-012: Add `POSTGRES_HOST` to `.env.dev.example` and `.env.prod.example`
- **Priority:** LOW
- **Description:** Add `POSTGRES_HOST=db` to both `.env.dev.example` and `.env.prod.example` for template consistency. `.env.test.example` already has it; dev and prod examples are missing it.
- **Files:** `.env.dev.example`, `.env.prod.example`
- **Acceptance criteria:**
  - `grep -n POSTGRES_HOST .env.dev.example .env.prod.example .env.test.example` returns a match in all 3 files
  - Values are `db` (matching inter-container hostname convention)
- **Dependencies:** none

---

### Task 10 — ENV-files-audit Finding 2: Add `--env-file .env.dev` to 7 Makefile.ps1 dev functions
- **Priority:** MEDIUM
- **Description:** Add `--env-file .env.dev` to all 7 dev compose commands in `Makefile.ps1` that are currently missing it:
  - `Invoke-Lint` (line 171)
  - `Invoke-Typecheck` (line 177)
  - `Invoke-Format` (line 183)
  - `Invoke-Shell` (line 189)
  - `Invoke-Makemigrations` (line 201)
  - `Invoke-LoadCatalog` (line 207)
  - `Invoke-Logs` (line 225)

  These functions run `docker compose -f docker-compose.yml -f docker-compose.dev.override.yml` without `--env-file .env.dev`, so Docker Compose cannot interpolate `${POSTGRES_USER}`, `${POSTGRES_DB}`, `${DJANGO_SECRET_KEY}`, etc. The script-level `.env.dev` load (lines 18-33) populates `$env:` for the PowerShell-side variables (`$pgUser`, `$pgDb`) but does NOT pass them to Docker Compose's interpolation engine.
- **Files:** `Makefile.ps1`
- **Acceptance criteria:**
  - `grep -c "env-file .env.dev" Makefile.ps1` returns at least 9 (the 2 existing + 7 new)
  - All 7 functions now include `--env-file .env.dev` in their `docker compose` invocations
- **Dependencies:** none

---

### Task 11 — ENV-files-audit Finding 3: Add `--env-file .env.test` to `Invoke-FullClean` test down
- **Priority:** LOW
- **Description:** In `Makefile.ps1`, add `--env-file .env.test` to the test compose `down` command in `Invoke-FullClean` (line 318).
- **Files:** `Makefile.ps1`
- **Acceptance criteria:**
  - `grep -n "docker compose -f docker-compose.yml -f docker-compose.test.yml down" Makefile.ps1` shows `--env-file .env.test` in the `Invoke-FullClean` function
- **Dependencies:** Task 10 (Finding 2) — same file, sequential

---

### Task 12 — ENV-files-audit Finding 4: Add `--env-file .env.test` to VERIFY_TESTS_INSTRUCTIONS.md
- **Priority:** MEDIUM
- **Description:** Add `--env-file .env.test` to both Docker compose commands on lines 111-112 of `docs/ops/VERIFY_TESTS_INSTRUCTIONS.md` (the manual `make test` equivalent commands).
- **Files:** `docs/ops/VERIFY_TESTS_INSTRUCTIONS.md`
- **Acceptance criteria:**
  - Both commands on lines 111-112 include `--env-file .env.test`
  - Commands are valid: `docker compose --env-file .env.test --project-name mko-bazuna-test -f docker-compose.yml -f docker-compose.test.yml ...`
- **Dependencies:** none

---

### Task 13 — ENV-009: Document env var resolution & CI/Docker Compose divergence
- **Priority:** MEDIUM
- **Description:** Add a new section to `docs/99-agent/architecture.md` documenting:
  1. How environment variables are resolved (Docker Compose interpolation via `--env-file`, `env_file:` directive vs `environment:`, shell var expansion in Makefile)
  2. The divergence between CI and Docker Compose (Docker Compose uses `--env-file .env.*` for interpolation; CI may set vars differently)
  3. The precedence: `environment:` > `env_file:` > Docker Compose `--env-file` > Dockerfile `ENV`
- **Files:** `docs/99-agent/architecture.md`
- **Acceptance criteria:**
  - New "Environment Variable Resolution" section present under the appropriate heading
  - Documents the precedence chain and CI/compose divergence
  - Content is accurate based on actual usage in the compose files
- **Dependencies:** none (informational; benefits from being written after compose changes are finalized, but no hard dependency)

---

### Task 14 — ENV-010: Remove root-level empty entrypoint stubs
- **Priority:** LOW
- **Description:** Delete the 0-byte root-level `entrypoint.sh` and `entrypoint-test.sh` stubs. The real scripts live in `docker/entrypoint*.sh` and are `COPY --chown=app:app docker/entrypoint*.sh /app/` into the image at build time (Dockerfile line 129). The root stubs are gitignored via `.gitignore` line 251 (`/entrypoint*.sh`) and serve no purpose — they get overwritten by the Docker COPY in any case.
- **Files:** `entrypoint.sh` (repo root), `entrypoint-test.sh` (repo root)
- **Acceptance criteria:**
  - Both root-level stub files are deleted (`git rm` if tracked, or `rm` if untracked)
  - `docker/entrypoint.sh` and `docker/entrypoint-test.sh` still exist and are non-empty
  - `git status` shows no unexpected changes
- **Dependencies:** none

---

## Verification Strategy

All changes are verifiable without running the full test suite:

| Task | Verification Command |
|------|---------------------|
| ENV-001/011 | `grep 'src/.env' .dockerignore` + `grep '**/.env*' .dockerignore` |
| ENV-002 | `docker compose --env-file .env.test -f docker-compose.yml -f docker-compose.test.yml config` (check 5 services) |
| ENV-003 | `docker compose --env-file .env.test -f docker-compose.yml -f docker-compose.test.yml config migrate create_admin` (no `.env.dev` volume) |
| ENV-004 | `grep -c "env_file" docker-compose.test.yml` + manual comment read |
| ENV-005 | `grep -v '^#' .env.test \| grep -c '='` (count vars in both files) |
| ENV-006 | `make -n db-shell` (dry run shows sourcing preamble) |
| ENV-007 | `grep -n '.env.dev' docker-compose.test.yml` (should return nothing in comments) |
| ENV-009 | Read architecture.md section |
| ENV-010 | `Test-Path entrypoint.sh` / `Test-Path entrypoint-test.sh` (should fail) |
| ENV-012 | `grep POSTGRES_HOST .env.*.example` |
| Finding 2 | `grep -c 'env-file .env.dev' Makefile.ps1` (should be >= 9) |
| Finding 3 | `grep 'env-file .env.test.*down' Makefile.ps1` |
| Finding 4 | Read lines 111-112 of VERIFY_TESTS_INSTRUCTIONS.md |
