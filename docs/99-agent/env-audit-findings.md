# Environment Configuration Audit Findings

## Scope

Audit of Docker image composition (`.dockerignore`), Docker Compose environment
variable resolution, and Makefile.ps1 invocation correctness across dev/test/prod
environments for the Mko Bazuna project.

---

## Finding 1: `.dockerignore` does not exclude `src/.env` from the Docker build context

### Severity: LOW (spec-deviation / hygiene)

### Evidence

- **`.dockerignore` line 5** (project root): pattern is `.env*`
- **`src/.env` exists** at project path `src/.env` (0 bytes) — confirmed via glob
- **`Dockerfile` line 57** (`COPY . .` in builder stage): copies the entire build context
- **`Dockerfile` line 117** (`COPY --from=builder --chown=app:app /app/src /app/src`): copies `src/` from builder to runtime stage
- No root-level `.env` file exists at the project root (confirmed via glob — only `.env.dev`, `.env.test`, etc. exist)

### Root Cause

The `.dockerignore` pattern `.env*` uses Go's `filepath.Match` semantics where `*`
does not cross path separators (`/`). When Docker walks the build context and
checks the full relative path against the pattern, `filepath.Match(".env*",
"src/.env")` returns `false` because:

1. The pattern `.env*` only matches strings that *start* with `.env`
2. The relative path `src/.env` starts with `s`, not `.env`
3. `*` in `filepath.Match` matches "any sequence of non-Separator characters" — it
   cannot match the `src/` prefix

**Result:** `.env*` correctly excludes root-level `.env*` files (`.env.dev`,
`.env.test`, `.env.prod`, `.env.example`) but **does NOT exclude**
`src/.env` in subdirectories.

### Impact

`src/.env` (0 bytes) is baked into Docker images. At runtime, docker-compose
bind-mounts `.env.dev` or `.env.test` to `/app/src/.env:ro` (overriding the baked
file), so the practical runtime impact is negligible. However:

- Unnecessary image bloat
- If secrets were ever placed in `src/.env`, they would be permanently baked into images
- Violates the principle of not including environment-specific files in build artifacts

### Required Fix

Add an explicit exclusion pattern for subdirectory `.env` files to `.dockerignore`:

```
# .dockerignore — add after line 5
src/.env
```

Or more broadly:
```
**/src/.env
```

---

## Finding 2: 7 Makefile.ps1 functions missing `--env-file .env.dev`

### Severity: MEDIUM (spec-deviation / correctness)

### Evidence

**Reference: `Makefile` (lines 9-11)** — correct implementation:
```makefile
ENV_FILE := --env-file .env.dev
COMPOSE_FILES := $(ENV_FILE) -f docker-compose.yml -f docker-compose.dev.override.yml
COMPOSE_TEST := --env-file .env.test -f docker-compose.yml -f docker-compose.test.yml
```

All dev Makefile targets use `$(COMPOSE_FILES)` which includes `--env-file .env.dev`.
All test Makefile targets use `$(COMPOSE_TEST)` which includes `--env-file .env.test`.

**Makefile.ps1 — functions missing `--env-file .env.dev` while specifying `-f` compose file flags:**

| Line | Function | Current Command (missing `--env-file`) |
|------|----------|------------------------------------------|
| 171 | `Invoke-Lint` | `docker compose -f docker-compose.yml -f docker-compose.dev.override.yml run --rm web uv run ruff check src/` |
| 177 | `Invoke-Typecheck` | `docker compose -f docker-compose.yml -f docker-compose.dev.override.yml run --rm web uv run basedpyright src/` |
| 183 | `Invoke-Format` | `docker compose -f docker-compose.yml -f docker-compose.dev.override.yml run --rm web uv run ruff check --fix src/` |
| 189 | `Invoke-Shell` | `docker compose -f docker-compose.yml -f docker-compose.dev.override.yml run --rm web /bin/bash` |
| 201 | `Invoke-Makemigrations` | `docker compose -f docker-compose.yml -f docker-compose.dev.override.yml run --rm web uv run python src/backend/manage.py makemigrations` |
| 207 | `Invoke-LoadCatalog` | `docker compose -f docker-compose.yml -f docker-compose.dev.override.yml run --rm load_catalog` |
| 225 | `Invoke-Logs` | `docker compose -f docker-compose.yml -f docker-compose.dev.override.yml logs -f` |

### Root Cause

The Makefile.ps1 dev functions were written with `-f docker-compose.yml -f docker-compose.dev.override.yml` flags but omitted the `--env-file .env.dev` flag. In contrast, all working functions in both Makefile.ps1 (`Invoke-Up`, `Invoke-Build`, `Invoke-Down`, `Invoke-CreateAdmin`, `Invoke-Clean`) and the equivalent Makefile targets include `--env-file .env.dev`.

### Impact

Without `--env-file .env.dev`, docker compose falls back to the default `.env` file
at the project root for `${VARIABLE}` substitution in the compose YAML. Since no
`.env` file exists at the project root, all `${VARIABLE}` references (such as
`${POSTGRES_DB}`, `${POSTGRES_USER}`, `${POSTGRES_PASSWORD}`,
`${DJANGO_SECRET_KEY}`) resolve to empty strings. Services with required-value
guards (`${POSTGRES_DB:?POSTGRES_DB must be set}`) will fail with validation
errors during service resolution. This affects:

- Running lint, typecheck, format, makemigrations, load-catalog, and logs in a
  dev environment
- Any debugging that relies on `make logs` or `make shell`

### Required Fix

Add `--env-file .env.dev` before the `-f` flags to all 7 functions, matching the
pattern used by `Invoke-Up` (line 79), `Invoke-Build` (line 90),
`Invoke-Down` (line 96), `Invoke-CreateAdmin` (line 216), and `Invoke-Clean`
(line 301):

```powershell
# Before:
docker compose -f docker-compose.yml -f docker-compose.dev.override.yml run --rm web uv run ruff check src/

# After:
docker compose --env-file .env.dev -f docker-compose.yml -f docker-compose.dev.override.yml run --rm web uv run ruff check src/
```

### Note on `Invoke-Migrate`

`Invoke-Migrate` (line 195) uses `docker compose --env-file .env.dev run --rm migrate`
— it already has `--env-file .env.dev` and deliberately omits the `-f` compose file
flags, matching the Makefile's `migrate` target (`docker compose $(ENV_FILE) run --rm migrate`).
This is **not a bug** — it is consistent with the Makefile reference implementation.
No fix is needed for `Invoke-Migrate`.

---

## Finding 3: `Invoke-FullClean` missing `--env-file .env.test` on test compose down

### Severity: LOW (spec-deviation / consistency)

### Evidence

**Makefile.ps1 line 318:**
```powershell
docker compose -f docker-compose.yml -f docker-compose.test.yml down -v --remove-orphans
```

**Makefile line 268 (reference):**
```makefile
COMPOSE_PROJECT_NAME=mko-bazuna-test docker compose $(COMPOSE_TEST) down -v --remove-orphans
```
Where `$(COMPOSE_TEST)` expands to `--env-file .env.test -f docker-compose.yml -f docker-compose.test.yml`.

### Root Cause

The test compose down command in `Invoke-FullClean` omits `--env-file .env.test`.

### Impact

For `down -v`, the `--env-file` flag is primarily needed for `${VARIABLE}`
substitution during compose file parsing. Since this is a teardown command that
removes containers and volumes, the impact is minimal — but it creates an
inconsistency with the Makefile and could cause issues if compose file validation
fails during the down operation.

### Required Fix

Add `--env-file .env.test`:
```powershell
docker compose --env-file .env.test -f docker-compose.yml -f docker-compose.test.yml down -v --remove-orphans
```

---

## Finding 4: `docs/ops/VERIFY_TESTS_INSTRUCTIONS.md` missing `--env-file .env.test` on manual test commands

### Severity: MEDIUM (spec-deviation / correctness)

### Evidence

**Lines 111-112** of `docs/ops/VERIFY_TESTS_INSTRUCTIONS.md`:
```pwsh
docker compose --project-name mko-bazuna-test -f docker-compose.yml -f docker-compose.test.yml up -d db
docker compose --project-name mko-bazuna-test -f docker-compose.yml -f docker-compose.test.yml run --rm --env PYTEST_SKIP_MARKERS=seed test
```

These commands are missing `--env-file .env.test`, while all other commands in the
same document correctly include `--env-file .env.dev` (lines 24, 47, 59, 65, 77, 89,
133, 139, 182, 194, 195).

**Makefile reference (lines 104-106):**
```makefile
test:
    docker compose $(COMPOSE_TEST) up -d db
    docker compose $(COMPOSE_TEST) run --rm --env PYTEST_SKIP_MARKERS=seed test
```
Where `$(COMPOSE_TEST)` expands to `--env-file .env.test -f docker-compose.yml -f docker-compose.test.yml`.

### Root Cause

The manual test commands in the docs omit `--env-file .env.test`. Without it,
docker compose uses the default `.env` file (which doesn't exist at the project
root) for `${VARIABLE}` substitution, causing compose validation to fail.

### Impact

Anyone following the manual commands in this guide will encounter `${VARIABLE}`
substitution failures (e.g., `${POSTGRES_DB:?POSTGRES_DB must be set}` errors).
The `make test` command itself works correctly because it uses `$(COMPOSE_TEST)`
which includes `--env-file .env.test`.

### Required Fix

Add `--env-file .env.test` to both commands:
```pwsh
docker compose --project-name mko-bazuna-test --env-file .env.test -f docker-compose.yml -f docker-compose.test.yml up -d db
docker compose --project-name mko-bazuna-test --env-file .env.test -f docker-compose.yml -f docker-compose.test.yml run --rm --env PYTEST_SKIP_MARKERS=seed test
```

---

## Summary of Required Fixes

| # | File | Line(s) | Fix | Effort |
|---|------|---------|-----|--------|
| 1 | `.dockerignore` | After line 5 | Add `src/.env` exclusion pattern | Trivial |
| 2 | `Makefile.ps1` | 171, 177, 183, 189, 201, 207, 225 | Add `--env-file .env.dev` to 7 dev functions | Small |
| 3 | `Makefile.ps1` | 318 | Add `--env-file .env.test` to test compose down in `Invoke-FullClean` | Trivial |
| 4 | `docs/ops/VERIFY_TESTS_INSTRUCTIONS.md` | 111-112 | Add `--env-file .env.test` to both manual test commands | Trivial |
