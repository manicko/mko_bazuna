# Docker Environment Phase — Prioritized Decision (Synthesis)

**Status:** Proposed decision, pending validator approval.
**Scope:** Introduce a NEW development phase that makes the entire `mko_bazuna` application
run and be developed fully inside Docker containers (PostgreSQL + Django web + aiogram bot + nginx),
with three environment profiles: **Prod**, **Dev**, **Test**.
**Inputs synthesized:**
- `docker_env_research_01_build_orchestration.md` (build, image, orchestration)
- `docker_env_research_02_dev_test_ci.md` (dev workflow, test env, CI)
- `docker_env_research_03_prod_security_ops.md` (prod deploy, security, ops)

**Source of truth:** `docs/wiki/01..04*.md`. Current actual repo state:
`docker-compose.yml` (db+web only, `runserver`, bind-mount `.:/app`, port 8000 published),
`docker/Dockerfile` (single-stage, no non-root, no collectstatic), `pyproject.toml`
(Django>=6.0.1, psycopg2-binary, requires-python>=3.14).

---

## 1. Executive summary of the decision

Adopt a **three-profile Docker environment** built from a single multi-stage image and a
**base + per-environment override** compose layout:

- **Base** `docker-compose.yml`: `db` (postgres:18, ICU locale) + `web` + `bot` + `nginx` + shared volumes.
- **Dev** `docker-compose.dev.override.yml`: bind-mount source for hot reload, `runserver`, `DEBUG=True`, host port for direct access, no TLS.
- **Test** `docker-compose.test.yml`: ephemeral **real PostgreSQL 18** (no persistent volume), a `test` runner service that migrates + runs `pytest` (never SQLite — Russian FTS + plpgsql triggers require real Postgres).
- **Prod** `docker-compose.prod.yml`: immutable image, `gunicorn` sync WSGI, nginx TLS + `/media/` hardening (zone R8), `restart: unless-stopped`, secrets via `env_file` now (Docker secrets later), optional PgBouncer, scheduled-jobs runner.

One **entrypoint** enforces a DB-wait + **run-once migration guard** before `web` and `bot` start.
The bot (async aiogram) and web (sync WSGI) share the image but run as **separate containers**,
each with `CONN_MAX_AGE=0`, ORM calls wrapped in `sync_to_async` in the bot.

This is intentionally **MVP-sized** (~300 users/day, ≤500k ads, <2s response) — no Kubernetes,
no Celery/Redis, no observability stack in phase 1.

---

## 2. Cross-researcher agreement (high confidence — adopt as-is)

All three researchers independently agreed on the following. These are **decided**:

| # | Decision | Rationale / source |
|---|----------|--------------------|
| A1 | **Multi-stage Dockerfile** (builder with gcc/libpq-dev + `uv sync`; slim runtime) | R1 §3.1; smaller, safer prod image |
| A2 | **Non-root user** in runtime stage + `collectstatic` at build | R1 §3.1, R3 P0; `03_structure.md:96` |
| A3 | **`uv` for deps**, `UV_PROJECT_ENVIRONMENT=/opt/venv`, `UV_LINK_MODE=copy`, `uv sync --frozen` | `02_packages.md`; existing Dockerfile |
| A4 | **Base + override compose layout** for prod/dev/test | R1 §3.3, R2 §3.1, R3 §2.1 |
| A5 | **Dev = bind-mount + hot reload; Prod = immutable image (no mount)** | R1, R2 §3.1 |
| A6 | **Test uses real PostgreSQL 18, ephemeral; SQLite rejected** | R1 §3.3, R2 §3.2 — FTS `to_tsvector('russian',…)` + plpgsql triggers are PG-only |
| A7 | **Entrypoint: DB-wait + run-once migration guard** before web+bot | `03_structure.md:105`; R1 §3.2, R3 P1 |
| A8 | **nginx mandatory**: TLS terminator + `/static/` + `/media/`; web not published externally | `03_structure.md:88,94`; R1 §3.5, R3 §2.2 |
| A9 | **`/media/` hardening (zone R8)**: block script exec, `X-Content-Type-Options: nosniff`, image MIME whitelist, `Content-Disposition: inline` | `03_structure.md:99-103`; R3 §2.2 |
| A10 | **`CONN_MAX_AGE=0`** per process; bot ORM in `sync_to_async` | `02_packages.md:9`; R1 §3.6, R3 §2.5 |
| A11 | **Three named volumes**: `postgres_data`, `media_volume`, `static_volume` | `03_structure.md:91`; all three |
| A12 | **Secrets via `env_file` now; Docker secrets deferred**; `API_ID/API_HASH` NOT present | `03_structure.md:106`; R3 §2.3 |
| A13 | **`bot` = same image, `python -m telegram_bot.main`; `restart: unless-stopped`** | `03_structure.md:87`; R1, R3 |
| A14 | **Scheduled jobs = Django management commands (no Celery in phase 1)** | `02_packages.md:53-55`; R3 §2.6 |
| A15 | **CI: build image + run pytest against real Postgres 17**; ruff + basedpyright | R2 §3.4 |
| A16 | **Makefile / compose shortcuts** for in-container dev ergonomics | R2 §3.3 |

---

## 3. Conflicts resolved (with authority)

### C1 — Python base image version (HIGHEST PRIORITY — spec defect)

**Conflict:** Researcher #1 recommended downgrading to `python:3.12-slim` claiming "3.14 is
pre-release." The spec (`03_structure.md:96`) and `pyproject.toml` say `python:3.14`. `pyproject.toml`
also declares `django>=6.0.1` while `02_packages.md:14` pins `django==5.1.2`.

**Authoritative facts (verified against Django docs, 2026):**
- Django **5.1** supports Python **3.10–3.13 only** (NOT 3.14). Django 5.1 series reached EOL **2025-12-01**; mainstream support ended April 2026.
- Python **3.14** is stable (final Oct 2025) and requires **Django 5.2 (added in 5.2.8) or Django 6.0**.
- Django **6.0** supports Python **3.12–3.14**.
- => The spec's own combination `python:3.14` + `Django 5.1.2` is **internally contradictory and cannot be built**. Researcher #1's "3.14 is pre-release" claim is **stale/incorrect**, but its conclusion (do not pair 3.14 with Django 5.1) is directionally right.

**Decision (RESOLVED — updated per owner directive + `docker_env_research_04_pg18_py314_versions.md`, APPROVED):**
Standardize on **Django 5.2.x LTS (`>=5.2.8,<6.0`) + Python 3.14 + psycopg3**, database **PostgreSQL 18**.
- The owner directs using the LATEST stable versions: **Python 3.14** (GA Oct 2025) and **PostgreSQL 18** (GA Sep 2025). This is verified correct and coherent.
- Python 3.14 requires **Django ≥5.2.8** (support added in 5.2.8) — Django **5.1 is incompatible with 3.14** and is already EOL. We pin the **Django 5.2.x LTS series** (`>=5.2.8,<6.0`, extended support to **April 2028**) — NOT a single patch, NOT Django 6.0 (6.0 supports 3.14 but is not LTS). Django 5.2 LTS keeps every spec-relied 5.1 feature (native psycopg pool via `"pool"`, `LoginRequiredMiddleware`, `STORAGES`, `{% querystring %}`).
- Base image: **`python:3.14-slim`**. psycopg[binary]>=3.2 ships cp314 wheels.
- **Database: `postgres:18` (Debian-based, NOT alpine)** with ICU locale for correct Russian collation — see decision **C1b** below.

> **Superseded note:** An earlier revision of this decision recommended Python 3.13 + PostgreSQL 17
> (out of caution re: 3.14 maturity). That caution is now obsolete — 3.14 and PG18 are GA and
> production-ready in 2026. Researcher #1's "3.14 is pre-release" claim was stale and is rejected.

### C1b — PostgreSQL 18 + Russian locale/collation (NEW, owner directive)

**Owner rationale:** earlier PostgreSQL versions have problems with Russian locale/collation.
**Verified nuance (`research_04`, APPROVED):** partially correct —
- `to_tsvector('russian', …)` **FTS stemming is locale-INDEPENDENT** (built-in snowball dictionary), so it is not the thing that breaks.
- But **sorting (`ORDER BY`), `pg_trgm` similarity, and `LIKE` character-classes ARE collation-dependent** and genuinely benefit from PG18 + a proper ICU locale, avoiding glibc `ru_RU.UTF-8` collation-version-mismatch warnings.

**Decision (RESOLVED):**
- DB image **`postgres:18`** (Debian; avoid `postgres:18-alpine` — musl libc has weaker non-C locale support even though PG15+ alpine ships ICU).
- initdb with **ICU**: `POSTGRES_INITDB_ARGS: "--locale-provider=icu --icu-locale=ru-RU"`.
- PG18 enables **data page checksums by default** — fine for a greenfield MVP cluster; note it for any future cross-cluster upgrade/restore.
- PG18 changes FTS/collation-dependent processing to use the cluster's default collation provider; a fresh cluster needs no reindex, but document `REINDEX` for future collation-provider changes.

### C2 — psycopg driver

**Conflict:** `pyproject.toml` has `psycopg2-binary`; spec + all researchers say psycopg3.
**Decision (RESOLVED):** Use **`psycopg[binary]>=3.2.0`**, remove `psycopg2-binary`.
Django 5.1+/5.2 auto-detects psycopg3 on the same `django.db.backends.postgresql` engine; native
pool needs `psycopg[pool]`/`psycopg-pool`. psycopg2 is feature-frozen. (`02_packages.md:17`.)

### C3 — PgBouncer: mandatory vs optional

**Conflict:** R3 lists PgBouncer as **P0/mandatory**; R1 marks it **P2/defer**. Spec says
"рекомендуется" (recommended), not required (`03_structure.md:104`, `02_packages.md:9`).
**Decision (RESOLVED):** **P1, structurally ready but off by default in phase 1.**
- Provide a PgBouncer service in an **opt-in compose profile** (`--profile pgbouncer`) wired for transaction mode; keep `CONN_MAX_AGE=0` regardless. For ~300 users/day with 3 gunicorn workers + 1 bot, direct psycopg3 connections are sufficient. Enable PgBouncer only when connection pressure is observed. This satisfies the spec ("recommended") without over-provisioning the MVP.

### C4 — Scheduled jobs: host cron vs cron-in-container vs loop container

**Conflict:** R3 recommended a **dedicated scheduler container** (a `while true; sleep 3600` loop
or cron); spec text mentions "systemd timer / cron" (host-oriented). R1 didn't cover it.
**Decision (RESOLVED):** **Dedicated `scheduler` container running Django management commands**, one per job, triggered by an in-container cron (e.g. `supercronic` for a non-root, log-friendly cron) OR a simple guarded loop.
- Keeps everything in Docker (matches "everything in containers" goal), config co-located in compose, and portable across Windows-dev/Linux-prod. Host `systemd`/`cron` rejected as primary because it breaks the "fully containerized" requirement (host cron only as a documented fallback).
- Jobs (all as management commands): `archive_ads` (2mo), `delete_archived_ads` (4mo), `purge_failed_moderation` (7d, `moderation_failed_at`), `purge_rejected_ads` (90d, `rejected_at`, zone D4 — **add: R3 omitted this**), `hard_delete_erased_users` (30d after `consent_revoked_at`, zone R1), `sweep_drafts` (30min), `cleanup_login_tokens` (expired/consumed tokens, zone C1 — **add: all three researchers omitted this**).
- Each job MUST be **idempotent** and take a per-job lock (advisory lock or DB lock table) to survive container restarts mid-run.

### C5 — Migration guard robustness

**Conflict:** R1's file-lock (`/app/.migrations_done`) is per-container-filesystem and does NOT
coordinate two separate containers (web + bot) — it only prevents re-run within one container.
**Decision (RESOLVED):** Use a **dedicated one-shot `migrate` service** (or a compose start-order guard) that runs `manage.py migrate --noinput` to completion; `web` and `bot` `depends_on: migrate (service_completed_successfully)`. Django migrations are already transactional/idempotent, and PostgreSQL advisory lock around the migrate step prevents concurrent apply. The file-lock is rejected as the sole mechanism (cross-container race). (`03_structure.md:105`, zone C5/D7.)

### C6 — Windows dev file-mount performance

**Agreement/refinement:** R2 flagged WSL2 + `:cached`. **Decision:** Require Docker Desktop **WSL2 backend**; keep the repo inside the WSL2 filesystem for acceptable bind-mount I/O; `:cached`/`:delegated` hints are legacy no-ops on modern Docker but harmless. Document in README.

### C7 — `compose` `version:` key

R1's snippets include `version: "3.9"`. **Decision:** OMIT the obsolete top-level `version:` key (Compose v2 ignores/deprecates it). Minor but include in plan to avoid warnings.

---

## 4. Corrections to research (must be reflected in the plan)

The plan MUST incorporate these fixes over the raw research:

1. **Base image = `python:3.14-slim`** with **Django 5.2.x LTS (`>=5.2.8,<6.0`) + psycopg3** (decision C1/C1b/C2).
2. **Migration guard = dedicated one-shot `migrate` service** with advisory lock, not a per-container file lock (C5).
3. **Add two missing scheduled jobs**: `purge_rejected_ads` (90d, zone D4) and `cleanup_login_tokens` (zone C1) — omitted by all researchers (C4).
4. **PgBouncer = opt-in compose profile**, not mandatory and not fully deferred (C3).
5. **nginx MIME whitelist for `/media/` = `image/jpeg` only** as the strict default per zone R8/E; png/webp from R3 exceed spec (Telegram delivers JPEG). Keep `image/jpeg` whitelist + `application/octet-stream` default; do not broaden.
6. **Drop obsolete `version:` key** from all compose files (C7).
7. **`pyproject.toml` reconciliation is a prerequisite task** (Django, psycopg, requires-python) — must be Task 0 of the plan, before any image build.
8. **`config/settings` should be split** (base/dev/prod/test) OR env-flag driven; researchers referenced `config.settings.test`/`config.settings` inconsistently. Choose **env-flag single settings module** (matches existing `config/settings.py` in `03_structure.md`) OR a `settings/` package — plan must pick one and be consistent. Recommend a **`settings/` package** (`base.py`, `dev.py`, `prod.py`, `test.py`) selected by `DJANGO_SETTINGS_MODULE`.
9. **Certbot/TLS**: for a single-host MVP, prefer **host-terminated TLS or a certbot sidecar with webroot**; keep it simple. Plan should treat cert issuance as an ops runbook step, not block first deploy (can start with self-signed/staging).

---

## 5. Final prioritized recommendation (P0 → P2)

### P0 — Must-have (a correct, buildable, 3-profile Docker environment)
1. **Task 0 — Reconcile `pyproject.toml`**: `django>=5.2.8,<6.0` (5.2.x LTS), `psycopg[binary]>=3.2.0` (+ `psycopg[pool]` if native pool used), `requires-python=">=3.14"`; add spec deps (django-environ, django-mptt, django-filter, aiogram, deep-translator, django-tailwind, django-htmx, django-storages, pillow). Remove psycopg2-binary. Regenerate `uv.lock`.
2. **Multi-stage `docker/Dockerfile`** — `python:3.14-slim`, builder (gcc/libpq-dev + `uv sync --frozen`), runtime (non-root `app`, venv copy, `collectstatic` output, `libpq5`).
3. **`docker/entrypoint.sh`** — DB-wait; delegate migration to one-shot `migrate` service.
4. **Base `docker-compose.yml`** — `db` (postgres:18 + ICU initdb + healthcheck + optional `initdb.d` for extensions), one-shot `migrate`, `web`, `bot`, `nginx`; volumes `postgres_data`/`media_volume`/`static_volume`; web NOT published.
5. **`docker-compose.dev.override.yml`** — bind-mount, `runserver`, `DEBUG=True`, host port, whitenoise ok.
6. **`docker-compose.test.yml`** — ephemeral postgres:18, `test` runner (migrate + `pytest` on real PG), no host ports, `--rm`.
7. **`docker-compose.prod.yml`** — gunicorn sync WSGI, immutable image, `restart: unless-stopped`, nginx TLS + R8 `/media/` hardening, `scheduler` service.
8. **`docker/nginx/` config** — reverse proxy to `web:8000`, `/static/` + `/media/` with zone R8 rules (block script exec, nosniff, `image/jpeg` whitelist, inline disposition), forwarded headers.
9. **`config/settings/` package** — base/dev/prod/test; TLS-ready prod (`SECURE_SSL_REDIRECT`, `SECURE_PROXY_SSL_HEADER`, `USE_X_FORWARDED_HOST`, secure cookies), `CONN_MAX_AGE=0`, `STORAGES`/django-storages.
10. **`.env.example`** (+ `.env.dev`) — `DJANGO_SECRET_KEY`, `DEBUG`, `ALLOWED_HOSTS`, DB vars, `BOT_TOKEN`; NO `API_ID/API_HASH`.
11. **Scheduled-jobs `scheduler` service** + management commands incl. the two additions (`purge_rejected_ads`, `cleanup_login_tokens`); idempotent + locked.

### P1 — Should-have (operability + DX)
12. **Makefile / PowerShell shortcuts**: `up`, `down`, `test`, `lint`, `typecheck`, `shell`, `migrate`, `makemigrations`, `logs`.
13. **CI pipeline** (GitHub Actions): build image, run pytest vs postgres:18 service, ruff, basedpyright; uv cache.
14. **PgBouncer opt-in compose profile** (transaction mode) — ready but off.
15. **DB backup**: daily `pg_dump` sidecar/cron + 7-day rotation + documented restore runbook.
16. **Healthchecks** on db, web, pgbouncer; `depends_on` conditions (`service_healthy`, `service_completed_successfully`).
17. **Docker `json-file` log rotation** (`max-size`, `max-file`) on long-running services.
18. **README/runbook**: Windows WSL2 setup, profile usage, TLS issuance, backup/restore.

### P2 — Nice-to-have (post-MVP)
19. Docker secrets (Swarm/K8s), BuildKit cache mounts, multi-arch build.
20. Self-hosted Plausible/Umami via Docker (analytics fallback, decision L).
21. Log aggregation (Loki/Promtail), metrics (Prometheus/Grafana), resource limits.
22. Point-in-time recovery (WAL archiving); testcontainers.
23. Phase-2 `scraping_service` (Telethon) compose wiring (out of scope, decision B).

---

## 6. Environment matrix (authoritative)

| Aspect | **Dev** | **Test** | **Prod** |
|--------|---------|----------|----------|
| Compose files | base + `dev.override` | `test` | base + `prod` |
| Source | bind-mount (hot reload) | bind-mount or baked | baked in image (immutable) |
| Server | `runserver` | pytest runner | `gunicorn` sync WSGI |
| DB | `db` (persistent volume) | ephemeral postgres:18 (no volume) | `db` (persistent volume) |
| Migrations | on-demand / `migrate` svc | in test entrypoint | one-shot `migrate` svc (locked) |
| nginx | optional | none | mandatory, TLS + R8 |
| DEBUG | True | True (test settings) | False |
| Secrets | `.env.dev` | CI env vars / generated | `env_file` (secrets later) |
| PgBouncer | off | off | opt-in profile |
| Scheduler | off (manual invoke) | off | on |
| Host ports | web published | none | 80/443 only |

---

## 7. Risks & open questions carried to the planner

- **R-1 (HIGH):** `pyproject.toml`/wiki version contradiction must be fixed first (C1/C2); otherwise nothing builds. Resolved baseline: Django 5.2.x LTS (`>=5.2.8,<6.0`) + Python 3.14 + PostgreSQL 18 (ICU).
- **R-2 (MED):** Non-root user write access to `media_volume` on Windows/WSL2 — ensure volume ownership (`chown` in entrypoint or matching UID).
- **R-3 (MED):** Native Django pool vs PgBouncer vs neither — plan should default to **neither** (direct psycopg3, `CONN_MAX_AGE=0`) and keep PgBouncer opt-in.
- **R-4 (LOW):** django-tailwind CSS build — use standalone CLI mode (no Node runtime) or build CSS in the builder stage; confirm in plan.
- **R-5 (LOW):** TLS cert issuance flow on first deploy — treat as runbook, start with staging/self-signed.
- **OQ-1:** Single settings module (env-flag) vs `settings/` package? → Decision C/§4.8 recommends **`settings/` package**; planner to confirm and keep imports consistent.
- **OQ-2:** Seed data (categories/cities) at DB init (SQL) vs Django migration/`loaddata`? → Recommend **Django data migration/`loaddata`** (app-owned), SQL `initdb.d` only for extensions (`pg_trgm`) if not created by a migration.

---

## 8. Traceability to spec zones

- Media hardening: **R8** (`03_structure.md:99-103`, `04_db_structure.md:163`).
- Connection pooling / `CONN_MAX_AGE=0` / PgBouncer: **C5** (`02_packages.md:9`, `03_structure.md:104`).
- Migration-once: **C5/D7** (`03_structure.md:105`).
- Consent hard-delete job: **F / R1** (`01_..:102-107`, `04_..:247`).
- Rejected purge job (90d): **D4** (`04_..:84,104,239`).
- Login-token cleanup: **C1** (`04_..:42-58`).
- Draft sweep (30min): **I** (`01_..:137`).
- Archive/delete timers (2mo/4mo, `published_at`): **J** (`01_..:139-144`).
- Anonymity of media URLs (UUID keys): **R6** (`04_..:155`).
- Analytics (Plausible / self-host fallback): **L** (`01_..:154-158`).

---

*Synthesized 2026-07-18 from three researcher outputs; conflicts resolved with verified
Django/Python/psycopg compatibility facts. Ready for validator review.*
