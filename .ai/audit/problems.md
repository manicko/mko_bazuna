---
id: audit-problems
domain: audit
tags:
  - audit
  - env
  - env-files
  - outdated
  - proposals
related:
  - doc-maintenance-rules
  - docker-deployment
  - technical-specification
  - spec-index
  - architecture-structure
---

# Audit Problems Report — Environment Files

> Status: `problems.md` is a **documentation-only** audit file (Markdown). It records
> env-file gaps, stale references, and proposed content that **cannot be applied**
> because `.env*` files are denied to the agent (per user instruction:
> "ты не должен править env файлы"). Each finding below includes the exact
> proposed addition and a rationale.

---

## 1. Context

A prior study session evaluated specs **12 / 15** and plans **14 / 16** (plus
`doc-maintenance-rules.md`) for any configuration, init, migration, or deployment
impact. That initial report concluded "no env changes needed" — which was
**incomplete**. A thorough code+Docker+docs audit reveals several env-file
gaps that pre-date but are **not addressed by** the new features.

**What the specs/plans themselves require:** nothing new. All settings used by
spec12/plan14 (moderation priority), spec15 (filter UI / alerts), and plan16
(category/lookup architecture) are **already present** in `base.py` and
**already documented** in the env example files. See [§4 Spec-by-spec
analysis](#4-spec-by-spec-analysis) below.

**What IS outdated:** the env example files omit variables that `base.py`
actually reads, the `docker-deployment.md` env-variable table is incomplete,
and one documented variable (`ADMIN_EMAIL`) is referenced but never
implemented. Details and proposed fixes follow.

---

## 2. Complete env-variable inventory

### 2.1 Variables read by Python code (`config/settings/base.py`)

| Variable | Required? | Default | In `.env.docker.example`? | In `.env.example`? | In `.env.dev.example`? |
|---|---|---|---|---|---|
| `DJANGO_SECRET_KEY` | Yes | — | ✅ | ✅ | ✅ |
| `DEBUG` | No | `False` | ✅ | ✅ | ✅ |
| `BOT_TOKEN` | No | `""` | ✅ | ✅ | ✅ |
| `ALLOWED_HOSTS` | No | `""` | ✅ | ✅ | ❌ |
| `DATABASE_URL` | No | `None` | ❌¹ | ❌¹ | ✅ |
| `POSTGRES_DB` | fallback | `"mko_bazuna"` | ✅ | ✅ | ✅ |
| `POSTGRES_USER` | fallback | `"postgres"` | ✅ | ✅ | ✅ |
| `POSTGRES_PASSWORD` | fallback | — | ✅ | ✅ | ✅ |
| `POSTGRES_HOST` | fallback | `"localhost"` | ❌ | ❌ | ❌ |
| `POSTGRES_PORT` | fallback | `"5432"` | ❌ | ❌ | ❌ |
| `BOT_USERNAME` | No | `""` | ✅ | ✅ | ✅ |
| `SITE_URL` | No (prod guard) | `"http://localhost:8000"` | ✅ | ✅ | ✅ |
| `IMMEDIATE_ALERTS_ENABLED` | No | `"false"` | ✅ | ✅ | ✅ |
| `PLAUSIBLE_HOST` | No | `""` | ✅ | ✅ | ✅ |
| `REDIS_URL` | No | `"redis://localhost:6379/0"` | ✅ | ✅ | ✅ |

¹ `DATABASE_URL` is intentionally omitted from `.env.docker.example` and
`.env.example` with a comment ("Docker Compose constructs it from POSTGRES_*").
It IS present in `.env.dev.example` for local non-Docker development.

### 2.2 Variables used in Docker / entrypoint scripts (not Python)

| Variable | Where used | In env example files? |
|---|---|---|
| `ADMIN_USERNAME` | `entrypoint-create-admin.sh`, `docker-compose.yml` | ✅ |
| `ADMIN_PASSWORD` | `entrypoint-create-admin.sh`, `docker-compose.yml` | ✅ |
| `ADMIN_TELEGRAM_ID` | `entrypoint-create-admin.sh`, `docker-compose.yml` | ✅ |
| `SEED_USERS` | `entrypoint-seed.sh`, `docker-compose.yml` | ✅ |
| `SEED_ADS` | `entrypoint-seed.sh`, `docker-compose.yml` | ✅ |
| `REGISTRY` | `docker-compose.prod.yml` | ✅ (`.env.docker.example`, `.env.example`) |
| `REPOSITORY` | `docker-compose.prod.yml` | ✅ (`.env.docker.example`, `.env.example`) |
| `IMAGE_TAG` | `docker-compose.prod.yml` | ✅ (`.env.docker.example`, `.env.example`) |
| `TLS_CERT_PATH` | `docker-compose.prod.yml` | ✅ |
| `FIX_PERMISSIONS` | `docker/entrypoint.sh` | ✅ |
| `SKIP_ENV_CHECK` | `docker/entrypoint.sh`, `entrypoint-scheduler.sh`, `docker-compose.test.yml` | ✅ |

### 2.3 Internal build/runtime flags (not for operators)

| Variable | Where used | Should be in env examples? |
|---|---|---|
| `DJANGO_BUILD` | `base.py`, `prod.py`, `Dockerfile` | ❌ No — internal only |
| `DJANGO_SETTINGS_MODULE` | `manage.py`, `asgi.py`, `wsgi.py`, compose `environment:` | ❌ No — set inline per service |
| `UV_PROJECT_ENVIRONMENT` | `Dockerfile`, compose `environment:` | ❌ No — internal |

---

## 3. Findings — what is outdated and what SHOULD be in the env files

### 3.1 `POSTGRES_HOST` and `POSTGRES_PORT` are undocumented

**Severity:** Medium — functional gap for local non-Docker development.

**Code evidence** (`base.py` lines 158–166):
```python
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": os.getenv("POSTGRES_DB", "mko_bazuna"),
            "USER": os.getenv("POSTGRES_USER", "postgres"),
            "PASSWORD": env("POSTGRES_PASSWORD"),
            "HOST": os.getenv("POSTGRES_HOST", "localhost"),   # ← read but not documented
            "PORT": os.getenv("POSTGRES_PORT", "5432"),         # ← read but not documented
            ...
        }
    }
```

These two variables are read by Django's `DATABASES` fallback path — the code
branch taken when `DATABASE_URL` is **not** set. In Docker, `DATABASE_URL` is
always constructed inline by `docker-compose.yml` (e.g. line 45:
`DATABASE_URL: postgres://${POSTGRES_USER}:${POSTGRES_PASSWORD}@db:5432/${POSTGRES_DB}`),
so the fallback is never reached in containers. However:

1. **Local non-Docker development** (`python src/backend/manage.py runserver`)
   does NOT set `DATABASE_URL`. It relies on `.env` at `src/backend/.env`.
   A developer whose local PostgreSQL runs on a non-default port (e.g. 5433 to
   avoid conflicting with the test DB on 5433) has **no documented way** to
   tell Django the port — they must discover `POSTGRES_PORT` by reading
   `base.py` source.

2. The env example files present a "PostgreSQL discrete variables" section
   listing only `POSTGRES_USER`, `POSTGRES_DB`, `POSTGRES_PASSWORD`. This implies
   those three are the complete set, which is incorrect.

3. `POSTGRES_HOST=db` is set inline in `docker-compose.yml` for all services
   (web, bot, migrate, load_catalog, create_admin, seed) and in
   `docker-compose.dev.override.yml`. While this works for Docker (the hostname
   is always `db`), the env files should still document the variable as
   available for local overrides.

**Proposed addition to `.env.docker.example`** (under the existing PostgreSQL
section, after `POSTGRES_PASSWORD`):

```
# PostgreSQL host and port (Docker-internal hostname is always "db", set inline
# in docker-compose.yml; these vars are read by Django's DATABASES fallback when
# DATABASE_URL is not set — used for local non-Docker development).
# In Docker, leave at "db"/"5432" (compose constructs DATABASE_URL inline).
POSTGRES_HOST=db
POSTGRES_PORT=5432
```

**Proposed addition to `.env.example`** (same section):

```
# PostgreSQL host/port for local non-Docker development (Django DATABASES fallback).
# In Docker, compose sets POSTGRES_HOST=db inline; DATABASE_URL is built automatically.
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
```

**Proposed addition to `.env.dev.example`** (after the existing
`POSTGRES_PASSWORD` line, since this file already uses `DATABASE_URL`):

```
# PostgreSQL discrete vars (alternative to DATABASE_URL above; used for pg_dump
# and as Django DATABASES fallback when DATABASE_URL is omitted).
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
```

### 3.2 `ADMIN_EMAIL` is referenced in docs but not implemented

**Severity:** Low — documentation inconsistency.

**Evidence:**
- `docs/ops/docker-deployment.md` line 623:
  ```
  | Email | (empty) | Optional; can be set via `ADMIN_EMAIL` |
  ```
- `docker/entrypoint-create-admin.sh` (the actual admin-creation entrypoint)
  only passes three flags to `create_admin_user`:
  ```bash
  exec uv run python src/backend/manage.py create_admin_user \
      --username "${ADMIN_USERNAME:-admin}" \
      --password "${ADMIN_PASSWORD}" \
      --telegram-id "${ADMIN_TELEGRAM_ID:--1}"
  ```
  No `--email` flag is passed. No `ADMIN_EMAIL` env var is read anywhere in
  the Python codebase (grep confirms zero matches for `ADMIN_EMAIL` in `*.py`).

**Conclusion:** `ADMIN_EMAIL` is a stale documentation reference. The variable
does not exist in the code or in any env file. Either:
- (a) Remove the `ADMIN_EMAIL` row from `docker-deployment.md`, or
- (b) If email support is desired in the future, add `ADMIN_EMAIL` to
  `entrypoint-create-admin.sh` and to all env example files.

**Proposed action:** Document the removal in `problems.md` and note it as a
stale reference in `docker-deployment.md`.

### 3.3 `docker-deployment.md` Environment Variables table is incomplete

**Severity:** Medium — operators rely on this table as the canonical env-var
reference.

**Evidence:** The table at `docs/ops/docker-deployment.md` lines 305–321 lists
14 variables but omits:

| Missing variable | Used where? | Why it should be in the table |
|---|---|---|
| `DEBUG` | `base.py` L45; set inline in `docker-compose.dev.override.yml` | Operators need to know the flag exists and defaults to `False` in production |
| `ALLOWED_HOSTS` | `base.py` L52; `prod.py` L50 guard raises if empty | Production guard will fail without it — operators need this warning |
| `REDIS_URL` | `base.py` L242, 250; set inline in compose for prod services | Mentioned in prose (line 37) but absent from the table; the table should include it |
| `POSTGRES_HOST` | `base.py` L165; set inline in compose | Part of the PostgreSQL discrete-variable set |
| `POSTGRES_PORT` | `base.py` L166; used in prod backup service (line 71) | Same as above |

**Proposed action:** Expand the table in `docker-deployment.md` (lines 305–321)
to include the five missing rows above, with the same "Required?" / "Description"
columns used for existing entries.

### 3.4 `.env.dev.example` omits `ALLOWED_HOSTS`

**Severity:** Low — acceptable for development.

**Evidence:** `.env.dev.example` does not list `ALLOWED_HOSTS`. In dev settings
(`config/settings/dev.py`), `DEBUG = True` is hardcoded, and Django allows all
hosts when `DEBUG=True`. The dev compose override does not set `ALLOWED_HOSTS`
either — it's only present in `.env.docker` (loaded via `env_file`) and used by
the base compose's `web` service when running with `config.settings.prod`.

**Conclusion:** Not truly missing for dev. No change needed, but a comment
could clarify why it's absent.

---

## 4. Spec-by-spec analysis (12 / 15 / 14 / 16)

### spec12 / plan14 — Enhanced Moderation

| Component | Env var needed? | Status |
|---|---|---|
| `AdModerationPriority` model | No | DB-backed; one-to-one with `Ad` |
| `PriorityCalculator` service | No | Hardcoded thresholds: `score >= 80 → HIGH`, `score >= 50 → MEDIUM`; banned-words sourced from `ModerationCriteria` singleton model (admin-edited, not env) |
| `ModerationAnalytics` service | No | DB queries, no config |
| `IMMEDIATE_ALERTS_ENABLED` guard in `moderation/signals.py` | No | Already in all three env example files (added for US-B11 alerts feature) |

**Conclusion:** No new env vars. `IMMEDIATE_ALERTS_ENABLED` was already added
and documented.

### spec15 — Filter UI

| Component | Env var needed? | Status |
|---|---|---|
| `CategoryFilterForm` | No | Form logic, no config |
| Filter query params (`category`/`city`/`price_min`/`price_max`) | No | HTTP query params, not env |
| `AlertQueryService` | No | Uses `settings.BOT_TOKEN`, `settings.SITE_URL` (both already in env files) |
| `IMMEDIATE_ALERTS_ENABLED` | No | Already in all three env example files |

**Conclusion:** No new env vars. All required settings are already present.

### plan16 — Category & Lookup Architecture

| Component | Env var needed? | Status |
|---|---|---|
| `CategoryLookupResolver` | No | Hardcoded `CACHE_TTL = 300` (not env-configurable); walks MPTT ancestors |
| `LookupCacheService` | No | Hardcoded `CACHE_TTL = 3600` (not env-configurable); uses Django cache framework |
| `CategoryPath` model | No | DB-backed model |
| `LookupGroup` / `LookupItem` models | No | DB-backed models |
| `CategoryListingPurpose` / `CategoryListingFeature` | No | DB-backed through tables |
| `FileHashService` | No | Pure SHA-256 computation, stateless |
| `categories.yaml` + `builder.py` | No | File path is hardcoded (`Path(__file__).resolve().parents[2] / "catalog" / "categories.yaml"` in `load_catalog.py` L9); not env-configurable |
| `load_catalog` management command `--config` arg | No | Has a `--config` CLI flag for override; not an env var |

**Conclusion:** No new env vars. The cache TTL constants (`300` and `3600`
seconds) are hardcoded in the service modules. If production tuning of these
values is desired, they **could** be promoted to env-configurable settings
(e.g. `CATEGORY_RESOLUTION_CACHE_TTL_SECONDS`, `LOOKUP_CACHE_TTL_SECONDS`),
but this is not required by the specs and would be a new design decision
rather than a documentation fix.

---

## 5. Summary of proposed env-file changes

| File | Change | Status |
|---|---|---|
| `.env.docker.example` | Add `POSTGRES_HOST=db` + `POSTGRES_PORT=5432` to PostgreSQL section | Proposed — blocked by env-file deny rule |
| `.env.example` | Add `POSTGRES_HOST=localhost` + `POSTGRES_PORT=5432` to PostgreSQL section | Proposed — blocked by env-file deny rule |
| `.env.dev.example` | Add `POSTGRES_HOST=localhost` + `POSTGRES_PORT=5432` after `POSTGRES_PASSWORD` | Proposed — blocked by env-file deny rule |
| `docs/ops/docker-deployment.md` | Removed stale `ADMIN_EMAIL` row from admin user table | ✅ FIXED |
| `docs/ops/docker-deployment.md` | Expanded Environment Variables table (added `DEBUG`, `ALLOWED_HOSTS`, `REDIS_URL`, `POSTGRES_HOST`, `POSTGRES_PORT`) | ✅ FIXED |
| `docs/01-spec/technical-specification.md` | Removed broken `> Source:` citations and `spec12/15/plan14/16` from `related:` | ✅ FIXED |
| `docs/01-spec/spec-index.md` | Removed `spec12/15/plan14/16` from `related:` | ✅ FIXED |
| `docs/01-spec/filter-ui.md` | Removed `spec15` from `related:` | ✅ FIXED |

---

## 6. Files referenced

- `.env.docker.example` (not modified — env file, per user instruction)
- `.env.example` (not modified — env file, per user instruction)
- `.env.dev.example` (not modified — env file, per user instruction)
- `src/backend/config/settings/base.py` (lines 158–166 — reads `POSTGRES_HOST`/`POSTGRES_PORT`)
- `src/backend/config/settings/prod.py` (guard checks for `BOT_TOKEN`, `SITE_URL`, `ALLOWED_HOSTS`)
- `docker-compose.yml` (sets `POSTGRES_HOST=db` inline for all services)
- `docker-compose.dev.override.yml` (sets `POSTGRES_HOST=db`, `DATABASE_URL=...`)
- `docker-compose.prod.yml` (backup service sets `POSTGRES_PORT=5432`)
- `docker/entrypoint.sh` (uses `DEBUG`, `FIX_PERMISSIONS`, `SKIP_ENV_CHECK`, `DATABASE_URL`)
- `docker/entrypoint-create-admin.sh` (uses `ADMIN_USERNAME`, `ADMIN_PASSWORD`, `ADMIN_TELEGRAM_ID`)
- `docker/entrypoint-seed.sh` (uses `SEED_USERS`, `SEED_ADS`)
- `docs/ops/docker-deployment.md` (env vars table §3.3; `ADMIN_EMAIL` stale reference §3.2)
- All Markdown documentation files referencing specs/plans that do not exist as files on disk (§7)

---

## 7. Broken cross-references to spec/plan files

**Severity:** Medium — broken links in documentation.

The following references pointed to files (`spec12.md`, `spec15.md`,
`plan14.md`, `plan16.md`) that **do not exist** on disk:

| Referencing file | Reference | Target (missing) |
|---|---|---|
| `docs/01-spec/technical-specification.md` frontmatter | `related: spec12, spec15, plan14, plan16` | not found |
| `docs/01-spec/technical-specification.md` L170 | `> Source: [spec12.md](spec12.md), [plan14.md](plan14.md)` | not found |
| `docs/01-spec/technical-specification.md` L200 | `> Source: [plan16.md](plan16.md)` | not found |
| `docs/01-spec/spec-index.md` frontmatter | `related: spec12, spec15, plan14, plan16` | not found |
| `docs/01-spec/filter-ui.md` frontmatter | `related: spec15` | not found |

**Root cause:** A prior session added `related:` entries and `> Source:`
citations referencing `spec12.md`/`spec15.md`/`plan14.md`/`plan16.md` as
if those files existed. They were never created. The content that these
files were meant to describe is **already inline** in
`technical-specification.md` sections Q (Enhanced moderation tooling) and
S (Category & lookup architecture), plus the Filter UI section in
`spec-index.md`.

**FIX APPLIED (Markdown, writable):**
- Removed `spec12`, `spec15`, `plan14`, `plan16` from the `related:`
  frontmatter of `technical-specification.md` and `spec-index.md`.
- Removed `spec15` from the `related:` frontmatter of `filter-ui.md`.
- Removed both `> Source: [spec12.md](...)` / `> Source: [plan14.md](...)`
  citation lines from section Q and `> Source: [plan16.md](...)` from
  section S in `technical-specification.md`. The section content itself
  (which already describes everything those specs would have covered) is
  retained.
- Removed the stale `ADMIN_EMAIL` row from the pre-configured admin user
  table in `docker-deployment.md` (line 623). `ADMIN_EMAIL` is referenced
  in documentation but is not read by any entrypoint script or Python code.
- Expanded the Environment Variables table in `docker-deployment.md`
  (formerly lines 305–321) from 14 to 19 rows, adding the five previously
  missing variables: `DEBUG`, `ALLOWED_HOSTS`, `REDIS_URL`,
  `POSTGRES_HOST`, `POSTGRES_PORT`.

**Unfixed items (require env-file writes — blocked):**
- `POSTGRES_HOST` / `POSTGRES_PORT` still not added to `.env.docker.example`,
  `.env.example`, `.env.dev.example` (see §3.1).
- A comment should be added to `docker-deployment.md` §3.4 noting why
  `.env.dev.example` omits `ALLOWED_HOSTS` (acceptable for `DEBUG=True`).

---

## 8. Edit history

| Date | Action |
|---|---|
| 2026-08-19 | Created `problems.md`; initial version documented the blocked `.env.docker.example` edit but incorrectly concluded "no env changes needed" |
| 2026-08-19 | Rewritten with full env-variable inventory (§2), four concrete findings with proposed content (§3), spec-by-spec analysis confirming no new env vars needed (§4), and broken cross-reference audit (§7) |
| 2026-08-19 | Applied Markdown fixes: removed broken `spec12/15/plan14/16` cross-references from frontmatter + `> Source:` citations in `technical-specification.md`, `spec-index.md`, `filter-ui.md`; removed stale `ADMIN_EMAIL` from `docker-deployment.md`; expanded env vars table in `docker-deployment.md` from 14 to 19 rows |
