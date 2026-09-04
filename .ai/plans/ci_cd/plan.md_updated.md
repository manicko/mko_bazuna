# CI/CD Implementation Plan for Mko Bazuna (Updated)

**Date:** 2026-09-01  
**Author:** Kilo (Planner Agent)  
**Status:** Draft  
**Based on:** `.ai/plans/ci_cd/audit-report.md` (2026-09-01), `.ai/plans/ci_cd/research.md`, `.ai/plans/ci_cd/preparation-guide.md`  
**Companion:** [`preparation-guide.md_updated.md`](./preparation-guide.md_updated.md)  
**Architecture reference:** [`docs/99-agent/architecture.md`](../../docs/99-agent/architecture.md)  
**CI contract:** [`src/backend/tests/test_docs_ci_parity.py`](../../src/backend/tests/test_docs_ci_parity.py)  

---

## Table of Contents

1. [Overview](#0-overview)
2. [Repository Structure](#1-repository-structure)
3. [What Lives Where](#2-what-lives-where)
4. [SSH Key Pairs](#3-ssh-key-pairs)
5. [Pre-implemented Components (Already in Place)](#4-pre-implemented-components-already-in-place)
6. [Implementation Stages](#5-implementation-stages)
7. [Execution Order / DAG](#6-execution-order--dag)
8. [Risk Assessment](#7-risk-assessment)
9. [Verification Steps](#8-verification-steps)
10. [Files to Create/Modify](#9-files-to-createmodify)
11. [Deployment Commands Reference](#10-deployment-commands-reference)
12. [Branch Strategy](#11-branch-strategy)
13. [Architecture Constraints](#12-architecture-constraints)
14. [Modern Best-Practice Integration (Advisory)](#13-modern-best-practice-integration-advisory)

---

## 0. Overview

**CI is LIVE.** Continuous Integration runs on every push and pull request via two workflow files:

- `.github/workflows/ci.yml` — 6 parallel jobs: **build**, **test**, **lint**, **typecheck**, **lint-templates**, **i18n**.
- `.github/workflows/ci-nightly.yml` — serial seed test suite (daily cron at 03:00 UTC + manual `workflow_dispatch`).

The CI build job constructs a Docker image with `push: false` (cache-only against a GHCR registry cache) — it validates that the image builds but **never publishes** for deployment.

**CD is NOT BUILT.** There is no `.github/workflows/deploy.yml`. The entire manual-deploy pipeline (SHA-tagged image push to GHCR, SSH-based deployment to a single VPS, pre-deploy backup, pre-deploy migrations, health-check, automatic rollback, image prune) is **to be implemented from scratch** per Stage C below.

**Target architecture (unchanged):**

- **Registry:** GitHub Container Registry (GHCR) — `ghcr.io/manicko/mko_bazuna`
- **Deploy target:** Single VPS (4 CPU, 8 GB RAM), no staging environment
- **Deploy trigger:** Manual `workflow_dispatch` with a **required** `image_tag` input (SHA-based or version — never `latest`)
- **Process model:** Two processes (web gunicorn WSGI + Telegram bot) sharing one Django project and one PostgreSQL 18 database; migrations run exactly once before both start via an advisory-locked one-shot service
- **UI:** HTMX MPA (no SPA framework)

---

## 1. Repository Structure

```
mko_bazuna/
├── .github/
│   └── workflows/
│       ├── ci.yml                # CI: 6 parallel jobs (build, test, lint, typecheck, lint-templates, i18n)
│       ├── ci-nightly.yml        # Nightly: serial seed suite (cron + manual trigger)
│       └── deploy.yml            # CD: to be created (build → push → deploy to VPS)
├── docker/
│   ├── Dockerfile                # 3-stage: builder / runtime / test-runtime
│   ├── entrypoint.sh             # Main entrypoint (shared setup functions)
│   ├── entrypoint-test.sh        # Test runner (pytest)
│   ├── entrypoint-catalog.sh     # One-shot: load categories
│   ├── entrypoint-scheduler.sh   # Periodic task loop
│   ├── entrypoint-create-admin.sh  # One-shot: create admin user
│   ├── entrypoint-seed.sh        # One-shot: seed demo data
│   └── nginx/
│       └── nginx.conf            # Reverse proxy (TLS, rate limits, health)
├── src/
│   ├── backend/                  # Django project (manage.py, config/, apps/)
│   ├── theme/                    # Tailwind CSS source
│   └── telegram_bot/             # aiogram bot code
├── docker-compose.yml            # Base compose (db, redis, migrate, load_catalog, create_admin, seed, web, bot, nginx)
├── docker-compose.dev.override.yml  # Dev overrides (hot-reload, bind mounts, seed auto-run)
├── docker-compose.prod.yml       # Prod overrides (GHCR image overrides, scheduler/backup/pgbouncer profiles)
├── docker-compose.test.yml       # Ephemeral test DB (port 5433)
├── pyproject.toml                # Project definition with uv
├── Makefile                      # GNU Make targets (Linux/macOS)
├── Makefile.ps1                  # PowerShell equivalent (Windows)
├── .env.docker.example           # Production env template (committed)
├── .env.example                  # Local dev env template (committed)
├── .env.dev.example              # Dev env template (committed)
├── .gitignore
└── README.md
```

**Naming convention:** All compose files use the legacy `docker-compose.*.yml` naming. **Do NOT rename** — every Makefile target, compose override, CI workflow, and operational doc depends on these names (`Makefile:10-11`, `docker-compose.dev.override.yml`, `docker-deployment.md`).

**Dead files (pending cleanup):** Four **0-byte stubs** at the repository root shadow the real scripts in `docker/` and serve no purpose. They are not referenced by any compose file or tool:

| File (repo root) | Size | Real counterpart |
|---|---|---|
| `entrypoint.sh` | 0 bytes | `docker/entrypoint.sh` (3,472 bytes) |
| `entrypoint-test.sh` | 0 bytes | `docker/entrypoint-test.sh` (2,702 bytes) |
| `entrypoint-catalog.sh` | 0 bytes | `docker/entrypoint-catalog.sh` (493 bytes) |
| `entrypoint-seed.sh` | 0 bytes | `docker/entrypoint-seed.sh` (1,376 bytes) |

Per the audit dead-code policy, investigate purpose before removal. Do **not** delete `docker/entrypoint*.sh`.

---

## 2. What Lives Where

### In Git Repository (committed)

```
.github/workflows/ci.yml            # CI pipeline (6 jobs)
.github/workflows/ci-nightly.yml    # Nightly seed suite
docker/Dockerfile                   # 3-stage build
docker/entrypoint*.sh               # 6 entrypoint scripts (sh)
docker/nginx/nginx.conf             # Reverse proxy config
docker-compose.yml                  # Base services
docker-compose.dev.override.yml     # Dev overrides
docker-compose.prod.yml             # Production overrides + profiles
docker-compose.test.yml             # Test override
src/                                # Django + theme + bot source
.env.example                        # Local development template
.env.dev.example                    # Development env template
.env.docker.example                 # Production env template
pyproject.toml                      # uv project + pytest config
Makefile                            # GNU Make targets
Makefile.ps1                        # Windows PowerShell equivalent
.gitignore
```

### Only on VPS (never committed)

```
.env.docker          # Production secrets (DJANGO_SECRET_KEY, BOT_TOKEN, etc.)
media/               # User-uploaded images (Telegram ad photos)
backups/             # Database dumps (7-day retention + pre-deploy backups)
certs/               # TLS certificates (fullchain.pem, privkey.pem)
```

### Never committed (local only)

```
~/.ssh/github_bazuna  # SSH key for GitHub (Windows → GitHub)
~/.ssh/deploy_bazuna  # SSH key for VPS (GitHub Actions → VPS)
```

### Reconciliation note

`research.md` §5.1 lists 8 GitHub Secrets including app secrets (`DJANGO_SECRET_KEY`, `BOT_TOKEN`, `POSTGRES_PASSWORD`, `ADMIN_PASSWORD`). **This is stale and contradicts both the code and the other plan files.** Current reality: only **4 server-access secrets** live in GitHub; all application secrets exist **only** in `.env.docker` on the VPS. This is enforced by code:

- `config/settings/prod.py:18-22` — fails fast if `BOT_TOKEN` is empty (non-build mode)
- `config/settings/prod.py:26-30` — fails fast if `SITE_URL` is unset
- `config/settings/prod.py:50-51` — fails fast if `ALLOWED_HOSTS` is empty
- `config/settings/base.py:52` — `DJANGO_SECRET_KEY = env("DJANGO_SECRET_KEY")` (required, no default)
- `.gitignore:148` — `.env.docker` is ignored; `.env.docker.example` is the tracked template

**GitHub Secrets (4 only):** `SERVER_HOST`, `SERVER_USER`, `SERVER_SSH_KEY`, `SERVER_PORT`. No workflow reads app secrets from GitHub Actions secrets.

---

## 3. SSH Key Pairs

There are **two separate SSH key pairs** — do not confuse them:

| Key Pair | Purpose | Used By |
|---|---|---|
| `~/.ssh/github_bazuna` | Authenticate to GitHub | Windows machine → GitHub |
| `~/.ssh/deploy_bazuna` | Authenticate to VPS | GitHub Actions → VPS |

**Key 1 — GitHub access:** Generated on the developer's Windows machine. Public key added to GitHub Settings → SSH and GPG keys. Private key stays local.

**Key 2 — VPS deploy access:** Generated on the developer's Windows machine. Public key copied to VPS `~/.ssh/authorized_keys`. Private key stored as the `SERVER_SSH_KEY` GitHub Secret. Used by `appleboy/ssh-action` in the deploy workflow.

---

## 4. Pre-implemented Components (Already in Place)

The following components are **live in the repository** and form the baseline. The updated plan documents them rather than re-implementing:

| Component | Status | Evidence |
|---|---|---|
| Dockerfile 3-stage (builder / runtime / test-runtime) | ✅ Done | `docker/Dockerfile:8` (`builder`), `:89` (`runtime`), `:168` (`test-runtime`) |
| Non-root user (uid 1000) | ✅ Done | `docker/Dockerfile:102-106` creates `app` group/user; `USER app` at `:149` |
| Standalone Tailwind CLI | ✅ Done | `docker/Dockerfile:52-54` downloads standalone binary; `:76-83` builds CSS + collectstatic + compilemessages |
| HEALTHCHECK | ✅ Done | `docker/Dockerfile:154-155` — `curl -f http://localhost:8000/health/` |
| CI: 6 jobs | ✅ Done | `ci.yml` — build, test, lint, typecheck, lint-templates, i18n |
| CI: nightly seed suite | ✅ Done | `ci-nightly.yml` — `seed-tests` job, daily cron at 03:00 UTC + manual |
| CI: GHCR registry build cache (`push: false`) | ✅ Done | `ci.yml:30` `push: false`; `ci.yml:32-33` `cache-from/cache-to: type=registry,ref=ghcr.io/manicko/mko-bazuna:buildcache` **⚠️ note:** ci.yml:32-33 uses hyphen `mko-bazuna` but the repo/name in ci.yml:31 and `pyproject.toml:39` uses underscore `mko_bazuna`. This is a ci.yml bug — the cache ref should be `mko_bazuna` (underscore) to match the repository. Recommended fix: update ci.yml:32-33 to use `mko_bazuna` (underscore). |
| CI: PostgreSQL 18 service | ✅ Done | `ci.yml:41` `postgres:18-alpine`; `docker-compose.test.yml:12` |
| CI: test command contract | ✅ Done | `ci.yml:111` — `-m "not seed" -n auto --dist loadgroup --tb=short --cov --durations=10 --cov-report=term --cov-report=xml --reuse-db` |
| CI: nightly seed command | ✅ Done | `ci-nightly.yml:73` — `-m "seed"` (serial, no xdist) |
| CI: lint-templates (djlint) | ✅ Done | `ci.yml:157-173` — `uv run djlint templates/` |
| CI: i18n (compilemessages + completeness) | ✅ Done | `ci.yml:177-253` — `--locale ru --locale bs --locale en`; runs `test_i18n_completeness.py` |
| CI: coverage artifact upload | ✅ Done | `ci.yml:114-119` — uploads `coverage.xml` |
| `docker-compose.prod.yml` image overrides | ✅ Done | `docker-compose.prod.yml:7-26` — web/bot/migrate/create_admin/seed → GHCR `${REGISTRY}/${REPOSITORY}:${IMAGE_TAG}` |
| Prod profiles: scheduler / backup / pgbouncer | ✅ Done | `docker-compose.prod.yml:38-63` (scheduler), `:67-97` (backup), `:100-121` (pgbouncer) |
| `.env.docker` gitignored | ✅ Done | `.gitignore:148`; 3 tracked templates: `.env.docker.example`, `.env.example`, `.env.dev.example` |
| Fail-fast prod settings guards | ✅ Done | `prod.py:18-22,26-30,50-51` (BOT_TOKEN, SITE_URL, ALLOWED_HOSTS); `base.py:52` (DJANGO_SECRET_KEY) |
| Languages: ru/bs/en (Bosnian, not Montenegrin) | ✅ Done | `base.py:69-73` `LANGUAGES`; `enums.py:187-192` `LanguageLocale.RUSSIAN/BOSNIAN/ENGLISH`; `Dockerfile:83` `--locale ru --locale bs --locale en` |
| `test_docs_ci_parity.py` CI contract | ✅ Done | `tests/test_docs_ci_parity.py:45-175` — enforces loadgroup/not-seed/reuse-db/importlib on ci.yml/entrypoint/Makefile |
| Rollback procedure documented in §Stage E | ✅ Done | `plan.md` §Stage E (lines 497–562) documents manual + automatic rollback; procedures live in this plan and the preparation-guide §Stage E. `docs/ops/docker-deployment.md` does **not** contain a rollback section — do not reference it for rollback. |
| pytest `--import-mode=importlib` in addopts | ✅ Done | `pyproject.toml:168` `addopts = ["--import-mode=importlib", "-ra", "-q"]` |
| pytest-xdist ≥ 3.8 (worksteal available) | ✅ Done | `pyproject.toml:213` — `pytest-xdist>=3.8.0` |
| Migrate-locked advisory lock (ID 100) | ✅ Done | `docker-compose.yml:35` migrate command uses `migrate_locked.main()`; one-shot service with `depends_on: db: service_healthy` |
| `docker/entrypoint.sh` shared functions | ✅ Done | 6 entrypoint scripts in `docker/`; sourced by catalog/seed/scheduler/create-admin scripts |

**⚠️ Build cache note:** The CI build job uses a GHCR registry cache (`ci.yml:32-33`) — this is live, not optional. Recommended next hardening: add GitHub Actions cache (`cache-from: type=gha`) and `docker/metadata-action@v5` to the CI build job alongside the existing registry cache.

---

## 5. Implementation Stages

### Stage 0 — Local Dev Machine (Windows)

**When:** Execute once on the developer's Windows machine. Starting point.

| ID | Task | Priority | Effort | Dependencies |
|----|------|----------|--------|--------------|
| 0.1 | Install Git, Docker Desktop, Python 3.14, uv | HIGH | trivial | None |
| 0.2 | Generate SSH key for GitHub (`~/.ssh/github_bazuna`) | HIGH | trivial | 0.1 |
| 0.3 | Clone repository and verify local build | HIGH | trivial | 0.2 |

**Commands (PowerShell + Makefile.ps1 or GNU Make):**

```powershell
# 0.1
winget install Git.Git
winget install Docker.DockerDesktop
winget install Python.Python.3.14
pip install uv

# 0.2
ssh-keygen -t ed25519 -f ~/.ssh/github_bazuna -C "your-email@example.com"
# Add public key to GitHub → Settings → SSH and GPG keys

# 0.3
git clone git@github.com:manicko/mko_bazuna.git
cd mko_bazuna
make up          # starts dev env with hot-reload on port 8000
# Or on Windows: .\Makefile.ps1 up
curl http://localhost:8000/health/
```

**Expected:** `{"status": "ok"}`

> **Note:** Local tests require a PostgreSQL test database in Docker on port 5433 (`docker-compose.test.yml:23`). Always start it first: `make test-db` (or `.\Makefile.ps1 test-db`). Never run `uv run pytest` locally without the Docker test DB — it will fail (DB unreachable on localhost:5432).

### Stage A — VPS Preparation (Priority: HIGH)

**When:** Execute once, immediately after purchasing the VPS.

**Goal:** A hardened Linux server with Docker, a deploy user, directory structure, and an initial `.env.docker` file.

| ID | Task | Priority | Effort | Dependencies |
|----|------|----------|--------|--------------|
| A1 | Create `production` environment in GitHub repository settings | HIGH | trivial | None |
| A2 | Add 4 GitHub Secrets: `SERVER_HOST`, `SERVER_USER`, `SERVER_SSH_KEY`, `SERVER_PORT` | HIGH | trivial | A1 |
| A3 | Generate deploy SSH key (`~/.ssh/deploy_bazuna`) and copy public key to VPS | HIGH | trivial | None |
| A4 | Install Docker and Docker Compose on VPS | HIGH | small | None |
| A5 | Create deploy user on VPS with Docker group membership | HIGH | small | A4 |
| A6 | Prepare VPS directory structure (`/opt/mko_bazuna/{backups,certs,media}`) | HIGH | small | A5 |
| A7 | Copy compose files + nginx config to VPS (source code NOT needed — baked into GHCR images) | HIGH | trivial | A5 |
| A8 | Create `.env.docker` on VPS with production secrets (23 variables from `.env.docker.example`) | HIGH | small | A7 |
| A9 | Set file permissions on VPS (`chmod 600 .env.docker`, ownership) | MEDIUM | trivial | A8 |

**A8 — `.env.docker` (app secrets live here ONLY):**

```bash
# On VPS, as deploy user:
cat > /opt/mko_bazuna/.env.docker << 'ENVEOF'
DJANGO_SECRET_KEY=<generate-with-django-secret-key-generator>
DEBUG=False
ALLOWED_HOSTS=<your-domain.com>,localhost,127.0.0.1

POSTGRES_USER=bazuna_user
POSTGRES_DB=bazuna_db
POSTGRES_PASSWORD=<generate-with-openssl-rand-base64-32>

REDIS_URL=redis://redis:6379/0

BOT_USERNAME=<your-bot-username>
BOT_TOKEN=<your-bot-token-from-botfather>

SITE_URL=https://your-domain.com
IMMEDIATE_ALERTS_ENABLED=false

TLS_CERT_PATH=/opt/mko_bazuna/certs

PLAUSIBLE_HOST=

ADMIN_USERNAME=admin
ADMIN_PASSWORD=<generate-with-openssl-rand-base64-24>
ADMIN_TELEGRAM_ID=<your-telegram-user-id>

SEED_USERS=10
SEED_ADS=600

# GHCR image override (used by docker-compose.prod.yml)
REGISTRY=ghcr.io
REPOSITORY=manicko/mko_bazuna
IMAGE_TAG=latest

FIX_PERMISSIONS=0
SKIP_ENV_CHECK=
ENVEOF

chmod 600 .env.docker
```

**Generating secure values:**

```bash
# Django secret key
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
# PostgreSQL / admin passwords
openssl rand -base64 32
openssl rand -base64 24
```

### Stage B — CI Enhancement (Priority: MEDIUM)

**Status:** CI is **already implemented** as a 6-job parallel gate in `ci.yml` + a nightly `seed-tests` job in `ci-nightly.yml`. This stage documents the current baseline and adds two small modernizations.

| ID | Task | Priority | Effort | Dependencies | Status |
|----|------|----------|--------|--------------|--------|
| B1 | Add `concurrency:` group to `ci.yml` to cancel superseded runs | MEDIUM | trivial | None | ⬜ To do |
| B2 | Document existing 6-job CI + nightly split (`ci.yml` + `ci-nightly.yml`) | HIGH | trivial | — | ✅ Done |
| B3 | Add `paths-ignore` to `ci.yml` to skip docs-only changes | HIGH | trivial | B1 | ⬜ To do |
| B4 | Verify PostgreSQL 18 service configuration | HIGH | trivial | None | ✅ Done |
| B5 | Verify coverage artifact upload configuration | LOW | trivial | None | ✅ Done |
| B6 | Rollback docs merged into `docs/ops/docker-deployment.md` | MEDIUM | — | — | ✅ Done |

**Current `ci.yml` structure (baseline — do not alter existing jobs):**

```yaml
# .github/workflows/ci.yml — 6 parallel jobs
name: CI
on:
  push:
    branches: [main, develop]
  # ⬜ B1: add concurrency group here
  # ⬜ B3: add paths-ignore for docs-only changes here
jobs:
  build:       # Docker build, push: false, GHCR registry cache
  test:        # Postgres 18 service + pytest (loadgroup, not seed, reuse-db, cov)
  lint:        # ruff check
  typecheck:   # basedpyright
  lint-templates:  # djlint
  i18n:        # compilemessages + test_i18n_completeness.py
```

**B1 — Concurrency (to add):**

```yaml
concurrency:
  group: ${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: true
```

**B3 — Path filters (to add):**

```yaml
on:
  push:
    branches: [main, develop]
    paths-ignore:
      - 'docs/**'
      - '*.md'
      - '.ai/**'
  pull_request:
    branches: [main, develop]
    paths-ignore:
      - 'docs/**'
      - '*.md'
      - '.ai/**'
```

**Contract enforcement:** `test_docs_ci_parity.py` asserts that `ci.yml` uses `--dist loadgroup`, `-m "not seed"`, `--reuse-db`, and that `pyproject.toml` addopts include `--import-mode=importlib`. Do NOT change `--dist loadgroup` to `--dist worksteal` without also updating the parity test — `loadgroup` is intentional for FSM-pinned bot tests (see [Modern Best-Practice Integration §13](#13-modern-best-practice-integration-advisory)).

### Stage C — CD Pipeline (Priority: HIGH)

**Status:** NOT STARTED. No `deploy.yml` exists. Build job runs `push: false`. The following 10 tasks build the entire CD pipeline from scratch.

| ID | Task | Priority | Effort | Dependencies | Status |
|----|------|----------|--------|--------------|--------|
| C1 | Create `.github/workflows/deploy.yml` with `workflow_dispatch` + required `image_tag` input | HIGH | small | B2 | ⬜ To build |
| C2 | Build job: OIDC login to GHCR → metadata-action tags → build-push with `push: true`, linux/amd64 | HIGH | small | C1 | ⬜ To build |
| C3 | (Security scan integrated as D1 below) | — | — | — | Moved to Stage D |
| C4 | Deploy job: SSH-based Docker Compose orchestration | HIGH | medium | C2, A2 | ⬜ To build |
| C5 | `docker compose pull` before `up -d` to fetch images from GHCR | HIGH | trivial | C4 | ⬜ To build |
| C6 | Pre-deploy `pg_dump` database backup before migrations | HIGH | small | C4, C5 | ⬜ To build |
| C7 | Pre-deploy migrations via `docker compose run --rm migrate` | HIGH | small | C4, C5, C6 | ⬜ To build |
| C8 | `docker-compose.prod.yml` image override for GHCR (prevents build-vs-pull conflict) | HIGH | — | C4 | ✅ Done |
| C9 | Health check with automatic rollback on failure (30 attempts × 5s) | HIGH | medium | C4, C5, C6, C7, C8 | ⬜ To build |
| C10 | `docker image prune -f` after successful deployment | HIGH | trivial | C4 | ⬜ To build |

**C1 — Workflow trigger (required SHA-based `image_tag`):**

```yaml
name: Deploy

on:
  workflow_dispatch:
    inputs:
      image_tag:
        description: 'Image tag to deploy (e.g., sha-a913bc2 or v0.3.1)'
        required: true
        default: ''
  push:
    branches: [main]
    # Only build+push on main; actual deploy is always manual via workflow_dispatch
```

**C2 — Build & Push Job (GHCR, `workflow_dispatch`-driven):**

The build job authenticates to GHCR using the built-in `GITHUB_TOKEN` (OIDC-backed, no PAT stored as a secret). It uses `docker/metadata-action@v5` to generate SHA-based + raw-input tags, then `docker/build-push-action@v7` with `push: true`:

```yaml
  build-and-push:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      packages: write
    steps:
      - uses: actions/checkout@v4

      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v3

      - name: Log in to GHCR
        uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          token: ${{ secrets.GITHUB_TOKEN }}   # built-in OIDC-backed token; no PAT

      - name: Extract metadata (tags, labels)
        id: meta
        uses: docker/metadata-action@v5
        with:
          images: ghcr.io/${{ github.repository }}
          tags: |
            type=sha
            type=raw,value=${{ github.event.inputs.image_tag }}

      - name: Build and push image
        uses: docker/build-push-action@v7
        with:
          context: .
          file: docker/Dockerfile
          push: true
          platforms: linux/amd64
          tags: ${{ steps.meta.outputs.tags }}
          cache-from: type=gha
          cache-to: type=gha,mode=max
```

**C4–C10 — Deploy job (full sequence: pull → backup → migrate → up → prune → health → rollback):**

```yaml
  deploy:
    needs: [build]
    runs-on: ubuntu-latest
    environment: production
    permissions:
      contents: read
    concurrency:
      group: deploy-${{ github.ref }}
      cancel-in-progress: false
    steps:
      - name: Deploy to VPS
        uses: appleboy/ssh-action@v1
        with:
          host: ${{ secrets.SERVER_HOST }}
          username: ${{ secrets.SERVER_USER }}
          key: ${{ secrets.SERVER_SSH_KEY }}
          port: ${{ secrets.SERVER_PORT || '22' }}
          envs: |
            IMAGE_TAG=${{ github.event.inputs.image_tag }}
            REPOSITORY=${{ github.repository }}
          script: |
            set -e
            DEPLOY_DIR="/opt/mko_bazuna"
            cd "$DEPLOY_DIR"

            export REGISTRY="ghcr.io"
            export REPOSITORY="${REPOSITORY}"
            export IMAGE_TAG="${IMAGE_TAG}"

            # Save current image tag for potential rollback (C9)
            CURRENT_IMAGE=$(docker compose -f docker-compose.yml -f docker-compose.prod.yml \
              ps --format "{{.Image}}" web 2>/dev/null || echo "")
            PREVIOUS_TAG=$(echo "$CURRENT_IMAGE" | rev | cut -d: -f1 | rev)
            echo "$PREVIOUS_TAG" > /opt/mko_bazuna/.previous_tag
            echo "Previous tag saved: $PREVIOUS_TAG"

            # Pull latest images from GHCR (C5)
            echo "Pulling images from GHCR..."
            docker compose -f docker-compose.yml -f docker-compose.prod.yml pull

            # Pre-deploy database backup (C6)
            echo "Backing up database..."
            docker compose -f docker-compose.yml -f docker-compose.prod.yml run --rm \
              db pg_dump -U ${POSTGRES_USER:-postgres} -d ${POSTGRES_DB:-postgres} -F c \
              -f /backups/pre_deploy_$(date +%Y%m%d_%H%M%S).dump || echo "WARNING: Backup failed, continuing..."

            # Pre-deploy migrations via one-shot service (C7)
            echo "Running pre-deploy migrations..."
            docker compose -f docker-compose.yml -f docker-compose.prod.yml run --rm migrate

            # Start new containers using GHCR images (C8 image override is already in docker-compose.prod.yml)
            echo "Starting new containers..."
            docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d

            # Clean up old images (C10)
            docker image prune -f

            echo "Deployment complete"

      - name: Health check with automatic rollback (C9)
        if: always() && !cancelled()
        uses: appleboy/ssh-action@v1
        with:
          host: ${{ secrets.SERVER_HOST }}
          username: ${{ secrets.SERVER_USER }}
          key: ${{ secrets.SERVER_SSH_KEY }}
          port: ${{ secrets.SERVER_PORT || '22' }}
          script: |
            DEPLOY_DIR="/opt/mko_bazuna"
            cd "$DEPLOY_DIR"

            echo "Waiting for services to stabilize..."
            sleep 10

            # Health check: run curl inside the web container via docker compose exec
            # (web:8000 is not published on the host; "web" DNS only resolves inside
            #  the compose network, so curl must execute within docker compose)
            for i in $(seq 1 30); do
              STATUS=$(docker compose -f docker-compose.yml -f docker-compose.prod.yml \
                exec -T web curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/health/ 2>/dev/null || echo "000")
              if [ "$STATUS" = "200" ]; then
                echo "Health check passed"
                exit 0
              fi
              echo "Waiting for service (attempt $i)..."
              sleep 5
            done

            echo "Health check failed - initiating automatic rollback..."
            PREVIOUS_TAG=$(cat /opt/mko_bazuna/.previous_tag 2>/dev/null || echo "")
            if [ -n "$PREVIOUS_TAG" ]; then
              echo "Rolling back to previous tag: $PREVIOUS_TAG"
              # Tag the GHCR image with the previous tag and redeploy
            REGISTRY="ghcr.io" REPOSITORY="${REPOSITORY}" IMAGE_TAG="$PREVIOUS_TAG" \
              docker compose -f docker-compose.yml -f docker-compose.prod.yml pull web
              docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --no-deps web
              echo "Rollback completed - verify manually"
            else
              echo "No previous tag available for rollback - check VPS manually"
            fi
            exit 1
```

> **C9 advisory:** For production-grade rollback, consider image-digest pinning (`--detach` via `docker image inspect --format '{{.RepoDigests}}`) instead of tag-based rollback. Tags can be mutated; digests cannot.

### Stage D — Security & Hardening (Priority: MEDIUM)

**Status:** NOT IMPLEMENTED. No security scanning exists in any workflow.

| ID | Task | Priority | Effort | Dependencies | Status |
|----|------|----------|--------|--------------|--------|
| D1 | Trivy fs-mode vulnerability scan (non-blocking CRITICAL/HIGH) + SARIF upload | MEDIUM | small | — | ⬜ To build |
| D2 | SARIF upload to GitHub Security tab | MEDIUM | trivial | D1 | ⬜ To build |
| D3 | pip-audit for Python dependency vulnerabilities (verify Py3.14 support) | MEDIUM | small | — | ⬜ To build |
| D4 | Dependabot (`github-actions` + `docker/docker` ecosystems, weekly) | LOW | trivial | — | ⬜ To build |
| D5 | gitleaks + `.gitleaks.toml` (secret scanning in CI) | MEDIUM | small | — | ⬜ To build |
| D6 | zizmor workflow linting (CI security best-practice) | LOW | trivial | — | ⬜ To build |

**D1 — Trivy (fs-mode, non-blocking):**

Added as a job in `ci.yml` (scans source tree, not the built image — simpler and faster):

```yaml
  security-scan:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Run Trivy vulnerability scanner
        uses: aquasecurity/trivy-action@master
        with:
          scan-type: fs
          format: 'sarif'
          output: 'trivy-results.sarif'
          ignore-unfixed: true
          severity: 'CRITICAL,HIGH'
          exit-code: '0'   # non-blocking — report but do not fail the build
      - name: Upload Trivy results to GitHub Security
        if: always()
        uses: github/codeql-action/upload-sarif@v3
        with:
          sarif_file: 'trivy-results.sarif'
          category: 'trivy'
```

**D3 — pip-audit (CI job, Python deps only):**

```yaml
  dependency-audit:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Set up uv
        uses: astral-sh/setup-uv@v5
        with:
          enable-cache: true
      - name: Run pip-audit
        run: uv run pip-audit --requirement src/backend/uv.lock
        working-directory: src/backend
```

> **D3 note:** Verify `pip-audit` supports Python 3.14 before adopting. If unsupported, use `uv audit` or `pip-audit` with a compat layer.

---

## 6. Execution Order / DAG

```
Stage 0 (local dev) ──→ Stage A (VPS prep + 4 secrets)
                              │
                              ▼
                    ┌─────────────────────┐
                    │  Stage B: CI Baseline│
                    │  (already live)     │
                    │  + B1 concurrency    │  ← can do in parallel
                    │  + B3 paths-ignore   │  ← can do in parallel
                    └──────────┬──────────┘
                               │
                               ▼
                    ┌─────────────────────┐
                    │  Stage C: CD Build   │
                    │  C1 → C2 → C4 → C5 → │
                    │  C6 → C7 → C9 → C10  │
                    │  (C8 already done)   │
                    └──────────┬──────────┘
                               │
                               ▼
                    ┌─────────────────────┐
                    │  Stage D: Security   │
                    │  D1 (Trivy)          │  ← depends on C2 (built image)
                    │  D2 (SARIF upload)   │  ← depends on D1
                    │  D3 (pip-audit)      │  ← independent
                    │  D4 (Dependabot)     │  ← config only
                    │  D5 (gitleaks)       │  ← config only
                    │  D6 (zizmor)         │  ← config only
                    └──────────────────────┘

Nightly (ci-nightly.yml) ── separate (cron + manual, runs seed suite)
```

**Critical path:** Stage 0 → Stage A → Stage B (B1 + B3) → Stage C (C1→C2→C4→C5→C6→C7→C9→C10) → Stage D (D1→D2).  
D3/D4/D5/D6 can run in parallel with CD since they are independent (config-only or source-tree scans).

**Independently executable tasks (no dependencies):**
- D3 (pip-audit) — scans `uv.lock`, no CD dependency
- D4 (Dependabot config) — `.github/dependabot.yml`, no runtime dependency
- D5 (gitleaks + `.gitleaks.toml`) — config + CI job, no CD dependency
- D6 (zizmor) — workflow linting, no CD dependency

---

## 7. Risk Assessment

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| GitHub Actions time limit (2,000 min free tier) | MEDIUM | MEDIUM | B3 path filters skip docs-only CI; concurrency (B1) cancels stale runs; consider public repo for unlimited minutes |
| SSH key compromise (deploy key) | LOW | HIGH | ED25519 keys; rotate quarterly; deploy user with minimal permissions; separate GitHub + VPS keys |
| Trivy scan blocks deploy | LOW | MEDIUM | D1 uses `exit-code: '0'` (non-blocking); report-only SARIF |
| GHCR auth misconfiguration | LOW | HIGH | Use built-in `GITHUB_TOKEN` (OIDC-backed); no PAT stored in secrets |
| Secret leak in logs | LOW | CRITICAL | Mask `SERVER_HOST` with `::add-mask::`; app secrets NOT in GitHub Secrets (only in `.env.docker`) |
| Database migration failure | MEDIUM | HIGH | Advisory lock (ID 100) prevents concurrent runs; test migrations in CI; **backup before deploy (C6)** |
| Database backup failure | LOW | MEDIUM | Non-blocking backup (`|| echo WARNING`); log warning and continue |
| Rollback procedure failure | LOW | MEDIUM | C9 automated rollback on health-check failure; test with known-good SHA tag; manual SSH fallback (prep-guide §Stage E) |
| Build vs pull conflict | LOW | HIGH | C8 image override in `docker-compose.prod.yml` (✅ already implemented) forces pull from GHCR |
| Stale image deployment | MEDIUM | HIGH | C5 `docker compose pull` before `up -d` |
| Disk bloat from old images | MEDIUM | MEDIUM | C10 `docker image prune -f` after successful deploy |
| `latest` tag ambiguity | HIGH | MEDIUM | C1 requires `image_tag` input (`required: true`, `default: ''`); never default to `latest` |
| Deploy workflow never triggered (human error) | LOW | HIGH | GitHub Environment `production` can add required reviewers for deploy job |

---

## 8. Verification Steps

### Already Verified (CI baseline live)

| Check | How to Verify | Status |
|-------|---------------|--------|
| 6-job CI passes on push | `git push` to `develop` or `main`; check Actions tab | ✅ Implemented |
| Nightly seed suite runs | Check `ci-nightly.yml` cron at 03:00 UTC, or trigger manually | ✅ Implemented |
| Parity test enforces CI contract | `test_docs_ci_parity.py` runs in `test` job | ✅ Enforced |
| Lint templates (djlint) | `ci.yml:157-173` runs `uv run djlint templates/` | ✅ Implemented |
| i18n completeness | `ci.yml:177-253` compiles `ru/bs/en` + runs completeness tests | ✅ Implemented |
| Test DB port 5433 | `docker-compose.test.yml:23` maps `"5433:5432"`; `Makefile:121` `make test-db` | ✅ Verified |
| `.env.docker` not committed | `.gitignore:148`; `git check-ignore .env.docker` | ✅ Verified |
| Fail-fast prod guards | `prod.py:18-22,26-30,50-51`; `base.py:52` | ✅ Implemented |
| Image override in prod | `docker-compose.prod.yml:7-26` | ✅ Implemented |

### To Verify After CD Built (Stage C complete)

| Check | How to Verify | Status |
|-------|---------------|--------|
| Deploy workflow dispatches with SHA tag | Run `workflow_dispatch` with `sha-{COMMIT_SHA}` | ⬜ To verify |
| GHCR image pushed with SHA tag | Check `ghcr.io/manicko/mko_bazuna` package, tag `sha-<sha>` | ⬜ To verify |
| Pull before up | Check deploy logs for `docker compose pull` step | ⬜ To verify |
| Pre-deploy backup created | Check `/opt/mko_bazuna/backups/` for `pre_deploy_*.dump` | ⬜ To verify |
| Pre-deploy migrations run | Check deploy logs for `migrate` service success | ⬜ To verify |
| Health check passes | `docker compose exec -T web curl -sf http://localhost:8000/health/` returns 200 | ⬜ To verify |
| Containers running | `docker compose ps` on VPS | ⬜ To verify |
| Image prune runs | Check deploy logs for `docker image prune -f` | ⬜ To verify |
| Rollback on failure | Deploy broken image; verify automatic rollback to previous tag | ⬜ To verify |
| Trivy scan non-blocking | Verify `security-scan` job reports but doesn't fail CD | ⬜ To verify (D1) |

---

## 9. Files to Create/Modify

| Action | Path | Status | Notes |
|--------|------|--------|-------|
| Create | `.github/workflows/deploy.yml` | ⬜ To build | CD: OIDC → GHCR → deploy → health → rollback |
| Create | `.github/dependabot.yml` | ⬜ To build (D4) | Weekly: `github-actions` + `docker` ecosystem |
| Create | `.gitleaks.toml` | ⬜ To build (D5) | Allowlist for build placeholders (e.g., `test-secret-key-for-testing-only`) |
| Add job | `.github/workflows/ci.yml` | ⬜ To build (B1, B3, D3) | Add `concurrency:`, `paths-ignore:`, `dependency-audit` + `security-scan` jobs |
| Rename | `docker-compose.yml` → `compose.yaml` etc. | 🚫 Do NOT | All tooling uses legacy names; renaming breaks Makefile, overrides, CI, and docs |
| Modify | `docker-compose.prod.yml` | ✅ Done | Image overrides already present |
| Create | `docs/ops/docker-deployment.md` rollback section | 🚫 Do NOT recreate | Already documented in `preparation-guide.md` §Stage E and `docker-deployment.md` |
| Verify | `.gitignore` | ✅ Done | `.gitignore:148` ignores `.env.docker` |

> **Do NOT rename compose files.** Do NOT recreate rollback docs. Do NOT delete `docker/entrypoint*.sh`. The 4 root-level 0-byte stubs are dead files pending cleanup investigation.

---

## 10. Deployment Commands Reference

The deploy job executes the following on the VPS (corrected to use real `docker-compose.*.yml` names):

```bash
set -e
DEPLOY_DIR="/opt/mko_bazuna"
cd "$DEPLOY_DIR"

# Required image tag (no default to latest) — provided via workflow_dispatch
export IMAGE_TAG="${IMAGE_TAG}"            # e.g., sha-a913bc2 or v0.3.1
export REGISTRY="ghcr.io"
export REPOSITORY="${REPOSITORY}"          # e.g., manicko/mko_bazuna

# Save current image for rollback (C9)
CURRENT_IMAGE=$(docker compose -f docker-compose.yml -f docker-compose.prod.yml \
  ps --format "{{.Image}}" web 2>/dev/null || echo "")
PREVIOUS_TAG=$(echo "$CURRENT_IMAGE" | rev | cut -d: -f1 | rev)
echo "$PREVIOUS_TAG" > /opt/mko_bazuna/.previous_tag

# Pull latest images from GHCR (C5)
docker compose -f docker-compose.yml -f docker-compose.prod.yml pull

# Backup database before migrations (C6)
docker compose -f docker-compose.yml -f docker-compose.prod.yml run --rm \
  db pg_dump -U "${POSTGRES_USER:-postgres}" -d "${POSTGRES_DB:-postgres}" -F c \
  -f /backups/pre_deploy_$(date +%Y%m%d_%H%M%S).dump || echo "WARNING: Backup failed, continuing..."

# Run pre-deploy migrations (C7) — one-shot migrate service with advisory lock
docker compose -f docker-compose.yml -f docker-compose.prod.yml run --rm migrate

# Start new containers (uses GHCR images via C8 image override)
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d

# Clean up old images (C10)
docker image prune -f

echo "Deployment complete"
```

**Inspecting the running tag:**

```bash
# Show which image tag is currently running for the web service
docker compose -f docker-compose.yml -f docker-compose.prod.yml ps --format "table {{.Name}}\t{{.Image}}\t{{.Status}}"
```

---

## 11. Branch Strategy

| Branch | CI Behavior | CD Behavior |
|--------|-------------|-------------|
| `main` | All 6 CI jobs run on push/PR | `workflow_dispatch` deploy enabled (manual, required `image_tag`) |
| `develop` | All 6 CI jobs run on push/PR | No deploy — CI only |
| `nightly` (ci-nightly.yml) | N/A (separate workflow) | Serial seed suite, daily cron at 03:00 UTC + manual `workflow_dispatch` |

**Deploy rule:** Only `main` can trigger `workflow_dispatch` deployment. The `image_tag` input is **required** (never defaults to `latest`). Deploy via `sha-{COMMIT_SHA}` for precise traceability and rollback.

---

## 12. Architecture Constraints

### 12.1 Build vs Pull Resolution (image override)

**Status:** ✅ Done.

The base `docker-compose.yml` defines `web`, `bot`, `migrate`, `create_admin`, and `seed` services with `build:` directives. The production override `docker-compose.prod.yml` overrides these with `image:` keys pointing to GHCR:

```yaml
# docker-compose.prod.yml:7-26
services:
  web:
    image: ${REGISTRY:-ghcr.io}/${REPOSITORY:-manicko/mko_bazuna}:${IMAGE_TAG:-latest}
  bot:
    image: ${REGISTRY:-ghcr.io}/${REPOSITORY:-manicko/mko_bazuna}:${IMAGE_TAG:-latest}
  migrate:
    image: ${REGISTRY:-ghcr.io}/${REPOSITORY:-manicko/mko_bazuna}:${IMAGE_TAG:-latest}
  create_admin:
    image: ${REGISTRY:-ghcr.io}/${REPOSITORY:-manicko/mko_bazuna}:${IMAGE_TAG:-latest}
  seed:
    image: ${REGISTRY:-ghcr.io}/${REPOSITORY:-manicko/mko_bazuna}:${IMAGE_TAG:-latest}
```

When an `image:` key is present in an override, Docker Compose uses it and ignores the `build:` directive — this ensures the deploy workflow pulls from GHCR instead of building locally.

### 12.2 Deploy Workflow Sequence

The correct sequence ensures image freshness and database consistency (preserved verbatim from the original plan):

```
1. docker compose pull     → Fetch latest images from GHCR
2. pg_dump backup          → Backup database before migrations
3. docker compose run migrate → Run migrations with pulled image
4. docker compose up -d    → Start containers (uses pulled images)
5. docker image prune -f   → Clean up old images
```

### 12.3 Secrets Strategy

**Design decision:** Application secrets live ONLY in `.env.docker` on the VPS. GitHub Secrets contain ONLY server-access credentials (`SERVER_HOST`, `SERVER_USER`, `SERVER_SSH_KEY`, `SERVER_PORT`). This eliminates secret drift between two locations.

- `.env.docker` is gitignored (`.gitignore:148`)
- `.env.docker.example` is the tracked template (23 variables)
- `prod.py` fail-fast guards enforce `BOT_TOKEN`, `SITE_URL`, `ALLOWED_HOSTS` at startup
- `base.py` requires `DJANGO_SECRET_KEY` (no default)
- GHCR auth uses built-in `GITHUB_TOKEN` (OIDC-backed) — no PAT stored as a GitHub Secret

### 12.4 Compose File Naming

The project uses legacy `docker-compose.*.yml` naming. **Do not rename.** All tooling depends on these names:

- `docker-compose.yml` — base services
- `docker-compose.dev.override.yml` — dev overrides (hot-reload, bind mounts)
- `docker-compose.prod.yml` — production overrides (image overrides + profiles)
- `docker-compose.test.yml` — ephemeral test DB (port 5433)

---

## 13. Modern Best-Practice Integration (Advisory)

These recommendations are **advisory** — recommended but not mandatory. They harden an already-correct architecture without changing the Docker + GHCR + manual-deploy-to-VPS model.

| # | Recommendation | File/Effort | Priority | Status |
|---|---|---|---|---|
| 1 | **Built-in GITHUB_TOKEN (OIDC-backed)** — The deploy template uses the built-in `GITHUB_TOKEN` for GHCR auth (already OIDC-backed, no PAT required). For stricter OIDC, the `docker/login-action` can use an OIDC token exchange via `registry-type: oidc` — but the current `token: ${{ secrets.GITHUB_TOKEN }}` pattern is sufficient and correct. | `deploy.yml` build job | HIGH | ✅ Adopted (built-in GITHUB_TOKEN) |
| 2 | **Dependabot** — Weekly auto-updates for `github-actions` + `docker` ecosystems | `.github/dependabot.yml` (NEW) | LOW | ⬜ To adopt |
| 3 | **Concurrency control** — Cancel superseded CI runs on same branch | `ci.yml` (add `concurrency:`) | MEDIUM | ⬜ To adopt (B1) |
| 4 | **Trivy fs-mode** — Source-tree vulnerability scan, non-blocking CRITICAL/HIGH | `ci.yml` (add `security-scan` job) | MEDIUM | ⬜ To adopt (D1) |
| 5 | **gitleaks + `.gitleaks.toml`** — Secret detection in CI; allowlist build placeholders | `.gitleaks.toml` + `ci.yml` gitleaks job | MEDIUM | ⬜ To adopt (D5) |
| 6 | **zizmor** — GitHub Actions workflow security linting | `ci.yml`/`deploy.yml` + `zizmor` job | LOW | ⬜ To adopt (D6) |
| 7 | **`--dist worksteal`** (if xdist ≥ 3.8) — Better test distribution | `ci.yml` test command — ⚠️ REQUIRES updating `test_docs_ci_parity.py` (which enforces `--dist loadgroup`) | ADVISORY | ⚠️ Do NOT adopt blindly — `loadgroup` is intentional for FSM-pinned bot tests |
| 8 | **`setup-uv@v5` with `enable-cache: true`** — Already used; verify for latest | `ci.yml` (already present) | LOW | ✅ Already adopted |
| 9 | **metadata-action** — Tag/label generation from git metadata | `ci.yml` build job + `deploy.yml` build job | LOW | ⬜ To adopt (CI build hardening) |
| 10 | **Codecov** — Upload coverage to codecov.io for richer reporting | `ci.yml` + `ci-nightly.yml` | LOW | ⬜ Optional — current artifact upload works |
| 11 | **DJLint + i18n jobs** — Already in CI | `ci.yml:157-215` | — | ✅ Already implemented |

> **Note on #7 (`--dist worksteal`):** The best-practice recommendation to switch from `--dist loadgroup` to `--dist worksteal` is **advisory only**. `loadgroup` is intentionally used because bot tests share FSM state and must pin to the same worker (`xdist_group` markers, `pyproject.toml:179`). `test_docs_ci_parity.py:48` enforces `--dist loadgroup` as a CI contract. Switching to `worksteal` would require updating the parity test. Since `pytest-xdist>=3.8.0` is already declared (`pyproject.toml:213`), `worksteal` is technically available, but the trade-off is reduced FSM isolation guarantees for slightly better load balancing.

---

*End of `plan.md_updated.md`. This is a planning document — it does not modify any production code, workflows, or configuration.*
