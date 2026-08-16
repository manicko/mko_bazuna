# Phase 02 Audit Findings — Configuration & Secrets Management

**Executor:** audit-executor
**Template:** `.kilo/commands/audit/phases/02-audit-config-secrets.md`
**Status:** complete
**Validated:** no

Runtime verification performed host-side with the project `.venv` (Python 3.14 / Django 5.2.16 /
django-environ 0.14) and `docker compose config` (no running services required). Evidence:
`git ls-files`, `git check-ignore`, `docker compose config`, and direct settings imports under
`DJANGO_SETTINGS_MODULE` = dev/prod/test with env vars set and unset.

## Findings

### CFG-001: BOT_TOKEN silently defaults to empty in production; bot silently skips startup
| Field | Value |
|-------|-------|
| **ID** | CFG-001 |
| **Severity** | HIGH |
| **Type** | SPEC-DEVIATION / BEST-PRACTICE |
| **Affected Modules** | `src/backend/config/settings/base.py`, `src/telegram_bot/main.py`, `src/backend/apps/search/management/commands/send_alerts.py` |
| **Classification** | mandatory |

**Description:** `base.py:49` reads `BOT_TOKEN = env("BOT_TOKEN", default="")`. In `main.py:25-30` an
empty token is treated as "development mode": it logs a WARNING and returns (container exits 0)
instead of failing. `send_alerts.py:70-73` repeats the silent skip for alert delivery. The
`main.py:23-24` comment falsely documents that "missing/invalid token raises ImproperlyConfigured
at django.setup()".

**Evidence:** Importing `config.settings.prod` with `BOT_TOKEN` unset returns `BOT_TOKEN = ''`
(no error). `docker compose config` resolves `BOT_TOKEN: ""` in the `bot` service. Both
required-secret siblings fail fast (`DJANGO_SECRET_KEY`, `POSTGRES_PASSWORD` raise
`ImproperlyConfigured`), but `BOT_TOKEN` does not.

**Recommendation:** In production, require a non-empty `BOT_TOKEN` (drop the `default=""`, or add an
explicit `if not BOT_TOKEN and not DEBUG: raise ImproperlyConfigured(...)` guard) and make the bot
process exit non-zero on a missing token. Correct the misleading comment. Effort: small.

---

### CFG-002: Compose silently falls back to literal weak placeholders for required secrets
| Field | Value |
|-------|-------|
| **ID** | CFG-002 |
| **Severity** | HIGH |
| **Type** | BEST-PRACTICE |
| **Affected Modules** | `docker-compose.yml:36,60`, `docker-compose.prod.yml:50`, `docker-compose.yml:10-12` |
| **Classification** | mandatory |

**Description:** Required secret vars use `:-` defaults instead of fail-fast `:?`:
`DJANGO_SECRET_KEY: ${DJANGO_SECRET_KEY:-placeholder}` (yml:36,60; prod.yml:50) and
`POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-postgres}` / `POSTGRES_USER: ${POSTGRES_USER:-postgres}`
(yml:10-12, repeated in prod). When the var is absent the service boots with the literal string
`placeholder` as `SECRET_KEY` (known/weak, leading to session and CSRF forgery) or `postgres` as the
DB password.

**Evidence:** grep shows `:-placeholder` and `:-postgres` defaults. `docker compose config`
(empty env) resolves `DJANGO_SECRET_KEY: <generate-with-django-secret-key-generator>` and
`BOT_TOKEN: ""` — i.e. the shipped default config carries a placeholder signing key, not a real one,
with no boot failure.

**Recommendation:** Replace `:-placeholder`/`:-postgres` with fail-fast `:?` syntax
(e.g. `${DJANGO_SECRET_KEY:?DJANGO_SECRET_KEY must be set}`) so a missing required secret fails the
service boot with a clear error. Never default secret-bearing vars. Effort: trivial.

---

### CFG-003: Runtime secret source `.env.docker` is git-tracked, not gitignored, and docs instruct filling real values into it
| Field | Value |
|-------|-------|
| **ID** | CFG-003 |
| **Severity** | HIGH |
| **Type** | SPEC-DEVIATION |
| **Affected Modules** | `.env.docker`, `.gitignore:145-149`, `docker-compose.yml` (all services `env_file: .env.docker` + `./.env.docker:/app/src/.env:ro`), `docs/ops/docker-deployment.md:165,267` |
| **Classification** | mandatory |

**Description:** `.env.docker` is BOTH the only runtime secret source (loaded by every service via
`env_file:` and bind-mounted as `src/.env`) AND a git-tracked file. `.gitignore` ignores `.env`,
`.env.dev`, `.env.local` but explicitly does NOT list `.env.docker`. The ops docs instruct operators
to "Configure `.env.docker` with your real values" (dev + prod). Any `git add .env.docker` after
filling real `DJANGO_SECRET_KEY`/`BOT_TOKEN`/`POSTGRES_PASSWORD` commits production secrets to VCS.

**Evidence:** `git ls-files .env.docker` shows it is tracked. `git check-ignore .env.docker` exits
1 (not ignored). Current content is placeholders only (no active leak), but the documented
deployment flow writes real secrets into this tracked file. `.dockerignore` correctly excludes
`.env*` from images (line 5), so the leak vector is VCS, not the image.

**Recommendation:** Decouple the tracked template from the runtime secret file: keep `.env.docker`
as a tracked template only, and inject real secrets via a gitignored runtime file (e.g. copy to a
gitignored `.env`) or via the orchestration environment. Add `.env.docker`-secrets-handling
guidance to `.gitignore`/`.dockerignore`. Effort: small.

---

### CFG-004: Scheduler entrypoint checks the wrong `.env` path; hourly sweeps never start
| Field | Value |
|-------|-------|
| **ID** | CFG-004 |
| **Severity** | HIGH |
| **Type** | SPEC-DEVIATION |
| **Affected Modules** | `docker/entrypoint-scheduler.sh:8`, `docker/entrypoint.sh:10-14`, `docker-compose.prod.yml:42,53-54` |
| **Classification** | mandatory |

**Description:** `docker/entrypoint.sh` (used by `web`/`bot` ENTRYPOINT) checks `/app/src/.env`
first, then `/app/.env`. The scheduler uses a different script, `docker/entrypoint-scheduler.sh:8`,
which checks ONLY `/app/.env` — a path that is never created. The bind-mount
`volumes: ./.env.docker:/app/src/.env:ro` (prod.yml:54) lands the secret file at `/app/src/.env`,
not `/app/.env`. The `scheduler` service sets no `SKIP_ENV_CHECK`.

**Evidence:** `docker compose config` for the scheduler shows `volumes:
./.env.docker:/app/src/.env:ro` and `entrypoint: /app/entrypoint-scheduler.sh`. Reading
`entrypoint-scheduler.sh` shows `if [ -z "$SKIP_ENV_CHECK" ] && [ ! -f "/app/.env" ]` evaluates to
true (because `/app/.env` is absent), prints "ERROR: /app/.env file not found", then `exit 1`. With
`restart: unless-stopped` (prod.yml:58) this is a crash loop.

**Consequence:** When deployed with `--profile scheduler`, the hourly sweeps (`archive_sweep`,
`delete_sweep`, `consent_hard_delete`, `sweep_drafts`, `cleanup_login_tokens`,
`purge_failed_ads`, `purge_rejected_ads`) never execute until the path check is fixed.

**Recommendation:** Fix `entrypoint-scheduler.sh` to check `/app/src/.env` (match the bind-mount)
or source the shared check from `entrypoint.sh`. Effort: trivial.

---

### CFG-005: No config/secret-loading tests; missing-secret rejection behavior is untested
| Field | Value |
|-------|-------|
| **ID** | CFG-005 |
| **Severity** | MEDIUM |
| **Type** | BEST-PRACTICE |
| **Affected Modules** | `conftest.py:10-15` (sets defaults instead of asserting), no settings/config test module |
| **Classification** | advisory |

**Description:** `conftest.py` unconditionally stamps placeholder `DJANGO_SECRET_KEY`/`BOT_TOKEN`
defaults so the suite can boot; no test asserts that a missing required secret raises
`ImproperlyConfigured`, nor that `BOT_TOKEN` empty handling is intentional per-environment. The
rejection behavior verified manually in R2 (CFG-001/002) has no CI guard.

**Evidence:** `pytest --collect-only -q` lists app-level test modules only; grep for
`SECRET_KEY|BOT_TOKEN|ImproperlyConfigured` across `**/tests/**` returns matches in `conftest.py`
only. `test_context_processors.py` passes (4/4) — it does not cover settings.

**Recommendation:** Add a `SimpleTestCase` asserting `ImproperlyConfigured` is raised when
`DJANGO_SECRET_KEY` is absent, and a test pinning the per-environment `BOT_TOKEN` policy.
Effort: small.

---

### CFG-006: Docs claim test DEBUG=False; code sets DEBUG=True (and test HSTS still differs from dev)
| Field | Value |
|-------|-------|
| **ID** | CFG-006 |
| **Severity** | LOW |
| **Type** | DOC-UPDATE / SPEC-DEVIATION |
| **Affected Modules** | `docs/ops/docker-deployment.md:396`, `src/backend/config/settings/test.py:9` |
| **Classification** | advisory |

**Description:** The ops architecture-comparison table states Test `DEBUG = False`, but
`test.py:9` sets `DEBUG = True` (intentional per the adjacent comment: "test settings must behave
like dev, not prod"). Test also retains base's `SECURE_HSTS_SECONDS = 3600` and
`SECURE_HSTS_INCLUDE_SUBDOMAINS = True`, whereas `dev.py` sets HSTS to `0` / `False`. The code
choice is reasonable (richer test failures); the documentation is stale.

**Evidence:** Import `config.settings.test` -> `DEBUG=True`, `SECURE_HSTS_SECONDS=3600`,
`SECURE_HSTS_INCLUDE_SUBDOMAINS=True`. Doc table row: `DEBUG | True | False`.

**Recommendation:** Update the docs table to `DEBUG = True` for Test. If "behave like dev" is the
goal, also align test HSTS to `0`. Effort: trivial.

---

### CFG-007: Dead zero-byte root entrypoint stubs are git-tracked and unused
| Field | Value |
|-------|-------|
| **ID** | CFG-007 |
| **Severity** | LOW |
| **Type** | BEST-PRACTICE |
| **Affected Modules** | `./entrypoint.sh`, `./entrypoint-catalog.sh`, `./entrypoint-seed.sh`, `./entrypoint-test.sh` (all 0 bytes), `docker/entrypoint*.sh` (real) |
| **Classification** | advisory |

**Description:** The repository root contains four 0-byte `entrypoint*.sh` stubs that are
git-tracked but never referenced — `docker-compose.yml` resolves entrypoints to `/app/entrypoint*.sh`
(copied from `docker/entrypoint*.sh` by the Dockerfile L121, optionally overridden by
`./docker/entrypoint*.sh` bind-mounts in the dev override). The real scripts live in `docker/`.

**Evidence:** `git ls-files entrypoint*.sh` -> 4 root stubs tracked; `Get-Item` -> 0 bytes each;
`grep entrypoint` in `docker-compose.yml` -> matches are `/app/entrypoint-catalog.sh` (line 49) etc.

**Recommendation:** Delete the root stubs (or clarify they are intentionally empty) to avoid
confusion about which entrypoint actually runs. Effort: trivial.

---

## Summary

| Severity | Count |
|----------|-------|
| CRITICAL | 0 |
| HIGH | 4 |
| MEDIUM | 1 |
| LOW | 2 |

## Mandatory Fixes
- CFG-001 - Require non-empty `BOT_TOKEN` in production; fail boot instead of silently skipping.
- CFG-002 - Replace `:-placeholder` / `:-postgres` Compose defaults with fail-fast `:?`.
- CFG-003 - Stop tracking the runtime secret file; gitignore `.env.docker` and source secrets
  from a gitignored runtime file or orchestration env.
- CFG-004 - Fix `entrypoint-scheduler.sh` to check `/app/src/.env` so the scheduler (and its
  hourly sweeps) actually start.

## Advisory Recommendations
- CFG-005 - Add config/secret-loading tests (missing-key rejection, BOT_TOKEN policy).
- CFG-006 - Update docs (test `DEBUG` is `True`).
- CFG-007 - Remove dead 0-byte root entrypoint stubs.

## Doc Updates Needed
- CFG-006 - `docs/ops/docker-deployment.md:396` DEBUG column for Test.
- CFG-003 - `docs/ops/docker-deployment.md:165,267` secret-file handling guidance.
