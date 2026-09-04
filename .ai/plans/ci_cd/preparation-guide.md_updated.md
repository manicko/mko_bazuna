# CI/CD Preparation Guide — Mko Bazuna (Updated)

**Date:** 2026-09-01
**Author:** Kilo (Planner Agent)
**Status:** Draft
**Based on:** `.ai/plans/ci_cd/audit-report.md` (2026-09-01), `.ai/plans/ci_cd/research.md`, `.ai/plans/ci_cd/preparation-guide.md` (2026-07-28)
**Companion:** [`plan.md_updated.md`](./plan.md_updated.md)
**Architecture reference:** [`docs/99-agent/architecture.md`](../../docs/99-agent/architecture.md)
**CI contract:** [`src/backend/tests/test_docs_ci_parity.py`](../../src/backend/tests/test_docs_ci_parity.py)
**Operations runbook:** [`docs/ops/docker-deployment.md`](../../docs/ops/docker-deployment.md)

---

## Table of Contents

0. [Stage 0 — Local Development Machine (Windows)](#0-stage-0--local-development-machine-windows)
1. [Repository Structure](#1-repository-structure)
2. [What Lives Where](#2-what-lives-where)
3. [SSH Key Pairs](#3-ssh-key-pairs)
4. [Stage A — One-time Server Preparation](#4-stage-a--one-time-server-preparation)
5. [Stage B — GitHub Configuration](#5-stage-b--github-configuration)
6. [Stage C — GitHub Actions Workflow](#6-stage-c--github-actions-workflow)
7. [Stage E — Rollback Procedure](#7-stage-e--rollback-procedure)
8. [Stage F — Verification Checklist](#8-stage-f--verification-checklist)
9. [Stage G — Daily Release Process](#9-stage-g--daily-release-process)
10. [Forward-looking Recommendations](#10-forward-looking-recommendations)
11. [Quick Reference](#11-quick-reference)

---

> **Core principle:** Separate one-time server preparation (Stage A) from the daily release process (Stage G). One-time work is done once after buying a VPS; the daily process is repeated on every release.

---

## 0. Stage 0 — Local Development Machine (Windows)

**When:** Execute once on your Windows development machine. This is the starting point — everything else builds on this.

**Goal:** A Windows machine with Git, Docker Desktop, Python 3.14, uv, and the repository cloned locally.

### 0.1 Install Git, Docker Desktop, Python, uv

```powershell
winget install Git.Git
winget install Docker.DockerDesktop
winget install Python.Python.3.14
pip install uv
```

Verify:
```powershell
git --version
docker --version
docker compose version
python --version
uv --version
```

### 0.2 Configure SSH for GitHub

Generate an SSH key for GitHub authentication (this is **different** from the deploy key — see [SSH Key Pairs](#3-ssh-key-pairs)):

```powershell
ssh-keygen -t ed25519 -f ~/.ssh/github_bazuna -C "your-email@example.com"
```

Add the public key to GitHub:
1. Go to **GitHub → Settings → SSH and GPG keys → New SSH key**.
2. Title: `Windows Dev Machine`
3. Key: contents of `~/.ssh/github_bazuna.pub`
4. Click **Add SSH key**.

### 0.3 Clone the repository

```powershell
git clone git@github.com:manicko/mko_bazuna.git
cd mko_bazuna
```

### 0.4 First local build

**Local development** uses the dev override (`docker-compose.dev.override.yml`) with hot-reload on port 8000. Run via the Makefile (or `Makefile.ps1` on Windows):

```powershell
make up            # Linux / macOS (uses docker-compose.yml + docker-compose.dev.override.yml)
# Or on Windows:
.\Makefile.ps1 up
```

Verify:
```powershell
curl http://localhost:8000/health/
```

Expected: `{"status": "ok"}`

**Running tests** requires a separate PostgreSQL test database in Docker on port 5433 (mapped by `docker-compose.test.yml:23`). Start it first, then run the fast gate:

```powershell
make test-db          # starts test PostgreSQL (port 5433), idempotent
make test             # fast gate: skips nightly seed suite, reuses DB
# Or on Windows:
.\Makefile.ps1 test-db
.\Makefile.ps1 test
```

> **Never run `uv run pytest` locally** without the Docker test DB — it will fail (DB unreachable on `localhost:5432`). The test infra lives in Docker, not in the local Python environment.

---

## 1. Repository Structure

Before setting up CI/CD, understand what lives in the Git repository:

```
mko_bazuna/
├── .github/
│   └── workflows/
│       ├── ci.yml                    # CI: 6 parallel jobs + coverage upload
│       ├── ci-nightly.yml            # Nightly: serial seed suite (cron + manual)
│       └── deploy.yml                # CD: to be created (build → push → deploy)
├── docker/
│   ├── Dockerfile                    # 3-stage: builder / runtime / test-runtime
│   ├── entrypoint.sh                 # Main entrypoint (shared functions, 3,472 bytes)
│   ├── entrypoint-test.sh            # Test runner (2,702 bytes)
│   ├── entrypoint-catalog.sh         # One-shot: load categories (493 bytes)
│   ├── entrypoint-create-admin.sh    # One-shot: create admin user (838 bytes)
│   ├── entrypoint-seed.sh            # One-shot: seed demo data (1,376 bytes)
│   ├── entrypoint-scheduler.sh       # Periodic task loop (2,066 bytes)
│   └── nginx/
│       └── nginx.conf                # Reverse proxy (TLS, rate limits, health)
├── src/
│   ├── backend/                      # Django project (manage.py, config/, apps/)
│   ├── theme/                        # Tailwind CSS source
│   └── telegram_bot/                 # aiogram bot code
├── docker-compose.yml                # Base: db, redis, migrate, load_catalog, web, bot, nginx
├── docker-compose.dev.override.yml   # Dev overrides (hot-reload, bind mounts, seed auto-run)
├── docker-compose.prod.yml           # Prod overrides (GHCR image overrides + scheduler/backup/pgbouncer profiles)
├── docker-compose.test.yml           # Ephemeral test DB (port 5433)
├── pyproject.toml                    # uv project + pytest config (--import-mode=importlib, xdist>=3.8)
├── Makefile                          # GNU Make targets (Linux/macOS)
├── Makefile.ps1                      # PowerShell equivalent (Windows)
├── .env.docker.example               # Production env template (23 variables, committed)
├── .env.example                      # Local dev env template (committed)
├── .env.dev.example                  # Dev env template (committed)
├── .gitignore                        # .env.docker at line 148
└── README.md

⚠️ Dead files (pending cleanup): Four 0-byte stubs at the repo root shadow the real
   scripts in docker/ and serve no purpose. They are NOT referenced by any compose
   file (which mounts docker/entrypoint*.sh) and should be investigated before removal.
   Do NOT delete docker/entrypoint*.sh.

   ├── entrypoint.sh          (0 bytes, shadows docker/entrypoint.sh: 3,472 bytes)
   ├── entrypoint-test.sh     (0 bytes, shadows docker/entrypoint-test.sh: 2,702 bytes)
   ├── entrypoint-catalog.sh  (0 bytes, shadows docker/entrypoint-catalog.sh: 493 bytes)
   └── entrypoint-seed.sh     (0 bytes, shadows docker/entrypoint-seed.sh: 1,376 bytes)
```

**Naming convention:** All compose files use the legacy `docker-compose.*.yml` naming. **Do NOT rename** — every Makefile target, compose override, CI workflow, and operational doc depends on these names (`Makefile:10-11`, `docker-compose.dev.override.yml`, `docs/ops/docker-deployment.md`, `.kilo/rules/commands.md`).

**Key files used by CI/CD:**
- `.github/workflows/ci.yml` — CI pipeline (6 jobs)
- `.github/workflows/ci-nightly.yml` — Nightly seed suite (serial)
- `.github/workflows/deploy.yml` — CD pipeline (**to be created**, §C4 below)
- `docker-compose.yml` + `docker-compose.prod.yml` — Used on VPS for deployment
- `docker/Dockerfile` — 3-stage build (builder / runtime / test-runtime)
- `docker/nginx/nginx.conf` — Reverse proxy configuration

---

## 2. What Lives Where

### In Git Repository (committed)

```
.github/workflows/ci.yml            # CI: 6 parallel jobs
.github/workflows/ci-nightly.yml    # Nightly seed suite
.github/workflows/deploy.yml         # CD: to be created
docker/Dockerfile                   # 3-stage build
docker/entrypoint*.sh               # 6 entrypoint scripts (all >0 bytes)
docker/nginx/nginx.conf             # Reverse proxy config
docker-compose.yml                  # Base services
docker-compose.dev.override.yml     # Dev overrides (hot-reload, bind mounts)
docker-compose.prod.yml             # Production overrides + profiles
docker-compose.test.yml             # Test override (port 5433)
.env.example                        # Local dev template
.env.dev.example                    # Dev env template
.env.docker.example                 # Production env template (23 variables)
pyproject.toml                      # uv + pytest config
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
.env                  # Local development env (gitignored via .gitignore:145)
.env.dev
.env.local
~/.ssh/github_bazuna  # SSH key for GitHub (Windows → GitHub)
~/.ssh/deploy_bazuna  # SSH key for VPS (GitHub Actions → VPS)
```

### Reconciliation note — secrets strategy

`research.md` §5.1 lists 8 GitHub Secrets including app secrets (`DJANGO_SECRET_KEY`, `BOT_TOKEN`, `POSTGRES_PASSWORD`, `ADMIN_PASSWORD`). **This is stale and contradicts both the code and the audit.** Current reality: only **4 server-access secrets** live in GitHub; all application secrets exist **only** in `.env.docker` on the VPS. This is enforced by code:

- `config/settings/prod.py:18-22` — fails fast if `BOT_TOKEN` is empty (non-build mode)
- `config/settings/prod.py:26-30` — fails fast if `SITE_URL` is unset
- `config/settings/prod.py:50-51` — fails fast if `ALLOWED_HOSTS` is empty
- `config/settings/base.py:52` — `DJANGO_SECRET_KEY = env("DJANGO_SECRET_KEY")` (required, no default)
- `.gitignore:148` — `.env.docker` is ignored

**GitHub Secrets (4 only):** `SERVER_HOST`, `SERVER_USER`, `SERVER_SSH_KEY`, `SERVER_PORT`. No workflow reads app secrets from GitHub Actions secrets. App secrets come solely from `.env.docker` on the VPS.

---

## 3. SSH Key Pairs

There are **two separate SSH key pairs** — do not confuse them:

| Key Pair | Purpose | Used By |
|----------|---------|---------|
| `~/.ssh/github_bazuna` | Authenticate to GitHub (clone, push) | Your Windows machine → GitHub |
| `~/.ssh/deploy_bazuna` | Authenticate to VPS for deployment | GitHub Actions → VPS |

**Key 1 — GitHub access (Windows → GitHub):**
- Generated in [0.2](#02-configure-ssh-for-github)
- Public key added to GitHub **Settings → SSH and GPG keys**
- Private key stays on your Windows machine

**Key 2 — VPS deploy access (GitHub Actions → VPS):**
- Generated in [A4](#a4-generate-deploy-ssh-key)
- Public key copied to VPS `~/.ssh/authorized_keys`
- Private key stored as the `SERVER_SSH_KEY` GitHub Secret
- Used by `appleboy/ssh-action` in the deploy workflow

---

## 4. Stage A — One-time Server Preparation

**When:** Execute once, immediately after purchasing the VPS. Never repeat unless the server is destroyed.

**Goal:** A hardened Linux server with Docker, a deploy user, directory structure, and an initial `.env.docker` file. After this stage, the server is ready to receive images from GHCR.

### A0. Prerequisites Checklist

| Item | What you need | How to obtain |
|------|--------------|---------------|
| **VPS** | 4 CPU, 8 GB RAM, Ubuntu 24.04 LTS | DigitalOcean, Hetzner, AWS EC2, etc. |
| **Root access** | Password or SSH key for `root` | Provided by VPS provider |
| **Domain name** (recommended) | e.g., `bazuna.com` | Domain registrar |
| **GitHub account** | Admin access to `mko_bazuna` repo | Existing or create new |
| **Telegram BotFather token** | Bot token string | Message `@BotFather` → `/newbot` → copy token |
| **Your Telegram user ID** | Numeric ID | Message `@userinfobot` → copy ID |

### A1. Provision the VPS

1. Create a VPS instance (Ubuntu 24.04 LTS recommended).
2. Note the **public IP address** — you will need it for `SERVER_HOST`.
3. SSH into the server as root:
   ```bash
   ssh root@<YOUR_VPS_IP>
   ```

### A2. Install Docker and Docker Compose

On the VPS, as root:

```bash
apt-get update
apt-get install -y ca-certificates curl gnupg

install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
  -o /etc/apt/keyrings/docker.asc
chmod a+r /etc/apt/keyrings/docker.asc

echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] \
  https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
  tee /etc/apt/sources.list.d/docker.list > /dev/null

apt-get update
apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

docker --version
docker compose version
```

### A3. Create the deploy user

```bash
useradd -m -s /bin/bash deploy
usermod -aG docker deploy
```

### A4. Generate deploy SSH key (GitHub Actions → VPS)

On your **local Windows machine**, generate an SSH key pair:

```bash
ssh-keygen -t ed25519 -f ~/.ssh/deploy_bazuna -C "deploy@bazuna-vps"
```

Copy the public key to the VPS:

```bash
ssh-copy-id -i ~/.ssh/deploy_bazuna.pub deploy@<YOUR_VPS_IP>
```

Verify the key works:

```bash
ssh -i ~/.ssh/deploy_bazuna deploy@<YOUR_VPS_IP>
```

The **private key** (`~/.ssh/deploy_bazuna`) becomes the `SERVER_SSH_KEY` GitHub Secret. Keep it secure — never commit it to the repo.

### A5. Create directory structure

On the VPS, as the deploy user:

```bash
sudo mkdir -p /opt/mko_bazuna/{backups,certs,media}
sudo chown -R deploy:deploy /opt/mko_bazuna
```

Directory layout after this step:

```
/opt/mko_bazuna/
├── backups/           # Database dumps (7-day retention + pre-deploy backups)
├── certs/             # TLS: fullchain.pem, privkey.pem
├── media/             # User-uploaded images (Telegram ad photos)
├── docker-compose.yml         # Copied from repo (§A6)
├── docker-compose.prod.yml    # Copied from repo (§A6)
├── docker/
│   └── nginx/
│       └── nginx.conf        # Copied from repo (§A6)
└── .env.docker                # Created in A6
```

### A6. Copy compose files and nginx config to VPS

**The source code is NOT needed on the VPS** — it is already baked into the Docker images pulled from GHCR. Only the Docker Compose files and nginx config are required to define service orchestration.

From your local machine, copy the files using the full real names:

```bash
scp -i ~/.ssh/deploy_bazuna \
  docker-compose.yml \
  docker-compose.prod.yml \
  docker/nginx/nginx.conf \
  deploy@<YOUR_VPS_IP>:/opt/mko_bazuna/

ssh -i ~/.ssh/deploy_bazuna deploy@<YOUR_VPS_IP> \
  "mkdir -p /opt/mko_bazuna/docker/nginx"

scp -i ~/.ssh/deploy_bazuna \
  docker/nginx/nginx.conf \
  deploy@<YOUR_VPS_IP>:/opt/mko_bazuna/docker/nginx/
```

### A7. Create `.env.docker` on the VPS

Create `.env.docker` on the VPS using all 23 variables from the real `.env.docker.example` template:

```bash
ssh -i ~/.ssh/deploy_bazuna deploy@<YOUR_VPS_IP>
cd /opt/mko_bazuna

cat > .env.docker << 'ENVEOF'
# ====================== Django ======================
DJANGO_SECRET_KEY=<generate-with-django-secret-key-generator>
DEBUG=False
ALLOWED_HOSTS=<your-domain.com>,localhost,127.0.0.1

# ====================== PostgreSQL Database ======================
POSTGRES_USER=bazuna_user
POSTGRES_DB=bazuna_db
POSTGRES_PASSWORD=<generate-with-openssl-rand-base64-32>

# ====================== Redis ======================
REDIS_URL=redis://redis:6379/0

# ====================== Telegram Bot ======================
BOT_USERNAME=<your-bot-username>
BOT_TOKEN=<YOUR-BOT-TOKEN-FROM-BOTFATHER>

# ====================== Public site ======================
SITE_URL=https://your-domain.com
IMMEDIATE_ALERTS_ENABLED=false

# ====================== TLS Certificates ======================
TLS_CERT_PATH=/etc/nginx/certs

# ====================== Analytics ======================
PLAUSIBLE_HOST=

# ====================== Admin ======================
ADMIN_USERNAME=admin
ADMIN_PASSWORD=<generate-with-openssl-rand-base64-24>
ADMIN_TELEGRAM_ID=<your-telegram-user-id>

# ====================== Seed (demo data) ======================
SEED_USERS=10
SEED_ADS=600

# ====================== Production image / registry ======================
REGISTRY=ghcr.io
REPOSITORY=manicko/mko_bazuna
IMAGE_TAG=<your-sha-tag-or-version>

# ====================== Container runtime ======================
FIX_PERMISSIONS=0
SKIP_ENV_CHECK=
ENVEOF
```

**Generating secure values:**

```bash
# Django secret key
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"

# PostgreSQL / admin passwords
openssl rand -base64 32
openssl rand -base64 24
```

### A8. Set file permissions

On the VPS:

```bash
chmod 600 .env.docker
chown -R deploy:deploy /opt/mko_bazuna
chmod 700 /opt/mko_bazuna/certs
```

### A9. (Optional) Set up TLS certificates

If you have a domain and want HTTPS:

```bash
sudo apt-get install -y certbot
sudo certbot certonly --standalone -d your-domain.com
sudo cp /etc/letsencrypt/live/your-domain.com/fullchain.pem /opt/mko_bazuna/certs/
sudo cp /etc/letsencrypt/live/your-domain.com/privkey.pem /opt/mko_bazuna/certs/
sudo chown deploy:deploy /opt/mko_bazuna/certs/*
sudo chmod 600 /opt/mko_bazuna/certs/privkey.pem
```

### A10. (Optional) Initial manual deployment

Before GHCR images exist (i.e., before the deploy workflow is built), you can do a manual test deploy that builds images locally:

```bash
cd /opt/mko_bazuna
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```

The `--build` flag forces a local build since no GHCR image exists yet. Once the deploy workflow is operational (§C4), future deploys will use `docker compose pull` to fetch pre-built images from GHCR instead.

---

## 5. Stage B — GitHub Configuration

**When:** One-time setup in GitHub. Done alongside Stage A.

### B1. Create the `production` environment

1. Go to your GitHub repository → **Settings → Environments**.
2. Click **New environment**.
3. Name: `production`.
4. (Optional) Add required reviewers for manual approval gates.
5. Click **Configure environment**.

### B2. Add GitHub Secrets — Server Access Only (4 secrets)

**Critical design decision:** Only server-access secrets go in GitHub Secrets. All application secrets (DJANGO_SECRET_KEY, BOT_TOKEN, POSTGRES_PASSWORD, ADMIN_PASSWORD, etc.) exist **only** in `.env.docker` on the VPS. This eliminates the risk of secret drift between two locations.

Go to **Settings → Secrets and variables → Actions → New repository secret**.

Add **only 4 secrets**:

| Secret Name | Value | How to obtain |
|-------------|-------|---------------|
| `SERVER_HOST` | VPS public IP or hostname | From VPS provider dashboard |
| `SERVER_USER` | `deploy` | The deploy user created in A3 |
| `SERVER_SSH_KEY` | Contents of `~/.ssh/deploy_bazuna` (private key) | Generated in A4 — **the private key, not the .pub file** |
| `SERVER_PORT` | `22` (or your custom SSH port) | Default is 22 unless you changed it |

#### SERVER_SSH_KEY format

The `SERVER_SSH_KEY` must be the **entire private key file contents**, including the `-----BEGIN OPENSSH PRIVATE KEY-----` and `-----END OPENSSH PRIVATE KEY-----` lines.

```bash
# On your local machine:
cat ~/.ssh/deploy_bazuna | clip    # Windows
cat ~/.ssh/deploy_bazuna | pbcopy  # macOS
```

### B3. Verify secrets are set

After adding all secrets, verify they appear in the list (values are hidden):

```
SERVER_HOST    ••••••••••
SERVER_USER    ••••••••••
SERVER_SSH_KEY ••••••••••
SERVER_PORT    ••••••••••
```

---

## 6. Stage C — GitHub Actions Workflow

**When:** One-time file creation / verification. After this, CI runs automatically on every push/PR; CD runs on manual `workflow_dispatch`.

> **⚠️ Correction:** The original prep-guide §C1 proposed creating a **single** `ci-cd.yml`. This is stale. CI was already split into **`ci.yml`** (6-job parallel gate) + **`ci-nightly.yml`** (serial seed suite). The only file still to be created is **`deploy.yml`** (CD). See §C4 below.

### C1. CI workflow split — already implemented ✅

The repository currently contains two CI workflow files:

```
.github/workflows/
├── ci.yml            # 6 parallel jobs (build, test, lint, typecheck, lint-templates, i18n)
├── ci-nightly.yml    # Serial seed suite (cron 03:00 UTC + manual workflow_dispatch)
└── deploy.yml        # CD pipeline — TO BE CREATED (§C4)
```

### C2. `ci.yml` — CI baseline (6 jobs, already live ✅)

The current `ci.yml` runs on every push to `main` / `develop` and on pull requests. It has **6 parallel jobs**:

| Job | Purpose | Status |
|-----|---------|--------|
| `build` | Docker build with GHCR registry cache (`push: false`); validates image builds | ✅ Live (`ci.yml:8-33`) |
| `test` | PostgreSQL 18 service + pytest with coverage | ✅ Live (`ci.yml:35-119`) |
| `lint` | Ruff check | ✅ Live |
| `typecheck` | Basedpyright | ✅ Live |
| `lint-templates` | Djlint on Django templates | ✅ Live (`ci.yml:157-173`) |
| `i18n` | compilemessages `--locale ru --locale bs --locale en` + `test_i18n_completeness.py` | ✅ Live (`ci.yml:177-253`) |

**Important — CI contract enforced by `test_docs_ci_parity.py`:** The test job uses the following exact flags (`ci.yml:111`):

```
uv run pytest -m "not seed" -n auto --dist loadgroup --tb=short --cov --durations=10 --cov-report=term --cov-report=xml --reuse-db
```

This contract is **enforced** by `src/backend/tests/test_docs_ci_parity.py:45-175`, which asserts that `ci.yml`, the `Makefile`/`Makefile.ps1`, and `pyproject.toml` all agree on:
- `--dist loadgroup` (intentional — bot FSM tests share state and must pin to the same xdist worker)
- `-m "not seed"` (fast gate — nightly seed suite runs separately)
- `--reuse-db` (test DB schema persists between runs)
- `--import-mode=importlib` in `pyproject.toml:168` addopts

**Nightly seed suite (`ci-nightly.yml:73`)** runs the slow tests serially:

```
uv run pytest -m "seed" --tb=short --cov --durations=10 --cov-report=term --cov-report=xml --reuse-db
```

> **⚠️ Advisory only:** `pytest-xdist>=3.8.0` (`pyproject.toml:213`) technically supports `--dist worksteal` for better load balancing. However, `loadgroup` is intentionally used because bot tests share FSM-pinned state. Switching to `worksteal` would require updating `test_docs_ci_parity.py` to enforce the new flag. Do NOT adopt blindly.

**Two small CI hardening tasks remain (Stage B in plan.md_updated.md §B1/B3):**
- **B1:** Add a `concurrency:` group to `ci.yml` to cancel superseded runs.
- **B3:** Add `paths-ignore` to `ci.yml` to skip docs-only changes.

These do **not** change the test command contract and do not require updating the parity test.

### C3. `ci-nightly.yml` — nightly seed suite (already live ✅)

```yaml
# .github/workflows/ci-nightly.yml — daily at 03:00 UTC + manual trigger
name: Nightly Seed Tests

on:
  schedule:
    - cron: "0 3 * * *"
  workflow_dispatch:

concurrency:
  group: nightly-seed-tests
  cancel-in-progress: false  # do not cancel — seed tests must complete

jobs:
  seed-tests:
    runs-on: ubuntu-latest
    env:
      PYTHONPATH: ${{ github.workspace }}/src:${{ github.workspace }}/src/backend
    services:
      db:
        image: postgres:18-alpine
        # ...env + healthcheck identical to ci.yml test job...
    steps:
      - uses: actions/checkout@v4
      - name: Setup uv
        uses: astral-sh/setup-uv@v5
        with:
          enable-cache: true
      - name: Install dependencies
        run: uv sync --frozen --no-install-project --group dev
        working-directory: src/backend
      # ...wait-for-db, migrate...
      - name: Run seed tests with coverage
        run: uv run pytest -m "seed" --tb=short --cov --durations=10 --cov-report=term --cov-report=xml --reuse-db
        working-directory: src/backend
      - name: Upload coverage report
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: nightly-coverage-report
          path: src/backend/coverage.xml
          retention-days: 7
```

### C4. `deploy.yml` — CD pipeline (TO BE CREATED)

**Status:** Not started. No `deploy.yml` exists. The CI build job uses `push: false`, so no image is ever published.

Create `.github/workflows/deploy.yml` with:
- `workflow_dispatch` trigger with a **required** `image_tag` input (SHA-based or version — never `latest`)
- GHCR auth using the built-in `GITHUB_TOKEN` (OIDC-backed, no PAT stored as a secret) — replaces the `GITHUB_TOKEN`-as-password pattern from the original prep guide
- `docker/metadata-action@v5` for SHA + raw-input tags
- `docker/build-push-action@v7` with `push: true`
- Deploy job: SSH via `appleboy/ssh-action@v1` using the 4 GitHub Secrets → VPS

**Full YAML template (corrected — uses `docker-compose.*.yml` names, OIDC, `docker compose ps` for rollback):**

```yaml
name: Deploy

on:
  workflow_dispatch:
    inputs:
      image_tag:
        description: 'Image tag to deploy (e.g., sha-a913bc2 or v0.3.1)'
        required: true
        default: ''

env:
  REGISTRY: ghcr.io

jobs:
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

  deploy:
    needs: [build-and-push]
    runs-on: ubuntu-latest
    environment: production
    concurrency:
      group: deploy-${{ github.ref }}
      cancel-in-progress: false
    steps:
      - name: Deploy to VPS (pull → backup → migrate → up → prune → health → rollback)
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
            export REPOSITORY="$REPOSITORY"
            export IMAGE_TAG="$IMAGE_TAG"

            # Save current image tag for rollback (C9)
            CURRENT_IMAGE=$(docker compose -f docker-compose.yml -f docker-compose.prod.yml \
              ps --format "{{.Image}}" web 2>/dev/null || echo "")
            PREVIOUS_TAG=$(echo "$CURRENT_IMAGE" | rev | cut -d: -f1 | rev || echo "")
            echo "$PREVIOUS_TAG" > /opt/mko_bazuna/.previous_tag
            echo "Previous tag saved: $PREVIOUS_TAG"

            # Pull latest images from GHCR
            echo "Pulling images from GHCR..."
            docker compose -f docker-compose.yml -f docker-compose.prod.yml pull

            # Pre-deploy database backup (C6)
            echo "Backing up database..."
            docker compose -f docker-compose.yml -f docker-compose.prod.yml run --rm \
              db pg_dump -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" -F c \
              -f /backups/pre_deploy_$(date +%Y%m%d_%H%M%S).dump || \
              echo "WARNING: Backup failed, continuing..."

            # Pre-deploy migrations via one-shot service (C7)
            echo "Running pre-deploy migrations..."
            docker compose -f docker-compose.yml -f docker-compose.prod.yml run --rm migrate

            # Start new containers (C8: image override already in docker-compose.prod.yml:7-26)
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

            echo "Health check failed — initiating automatic rollback..."
            PREVIOUS_TAG=$(cat /opt/mko_bazuna/.previous_tag 2>/dev/null || echo "")
            if [ -n "$PREVIOUS_TAG" ]; then
              echo "Rolling back to previous tag: $PREVIOUS_TAG"
              export REGISTRY="ghcr.io"
              export REPOSITORY="${REPOSITORY}"
              export IMAGE_TAG="$PREVIOUS_TAG"
              docker compose -f docker-compose.yml -f docker-compose.prod.yml pull web
              docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --no-deps web
              echo "Rollback completed — verify manually"
            else
              echo "No previous tag available for rollback — check VPS manually"
            fi
            exit 1
```

> **C9 advisory:** For production-grade rollback, consider image-digest pinning (immutable digests) instead of tag-based rollback. Tags can be mutated; digests cannot. See `plan.md_updated.md` §13 for the full Stage C breakdown (C1–C10).

### C5. Compose file name corrections

**⚠️ All compose references must use the real legacy names.** The original prep guide used `compose.yaml` / `compose.prod.yaml` / `compose.dev.yaml` / `compose.test.yaml` — these are **stale and do not exist**:

| Stale name (DO NOT USE) | Correct name (use this) |
|------|------|
| `compose.yaml` | `docker-compose.yml` |
| `compose.dev.yaml` | `docker-compose.dev.override.yml` |
| `compose.prod.yaml` | `docker-compose.prod.yml` |
| `compose.test.yaml` | `docker-compose.test.yml` |

Every Makefile target, VPS deploy command, and verification step in this guide uses the corrected `docker-compose.*.yml` names. **Do not rename the files** — all tooling depends on the legacy names.

### C6. Verify `.env.docker` is NOT committed ✅ Done

```bash
git check-ignore .env.docker
# Should output: .env.docker
```

`.env.docker` is gitignored at `.gitignore:148`. The tracked template is `.env.docker.example` (23 variables). Three tracked templates exist: `.env.example`, `.env.dev.example`, `.env.docker.example`.

### C7. Health endpoint

The project includes a `/health/` endpoint (`docker/Dockerfile:154-155` HEALTHCHECK). The deploy workflow verifies it via `docker compose exec` (the host cannot resolve the compose-internal `web` hostname or reach port 8000, which is not published):

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml exec -T web curl -sf http://localhost:8000/health/
```

Expected response:
```json
{"status": "ok"}
```

---

## 7. Stage E — Rollback Procedure

**When:** Used when a deployment breaks the production site.

> **Note:** Automatic rollback is **part of the unbuilt `deploy.yml`** (§C4, step C9). It is not yet live. Manual rollback via SSH is always available.

### E1. Automatic rollback (TO BE IMPLEMENTED)

Once `deploy.yml` is created, the health-check step (30 attempts × 5s = 150s) will automatically roll back on failure:

1. The workflow reads the previous tag from `/opt/mko_bazuna/.previous_tag` (captured via `docker compose ps` before deploy).
2. It pulls the previous image from GHCR.
3. It restarts the `web` container with the previous image (`up -d --no-deps web`).
4. The workflow exits with an error — you must verify manually.

### E2. Manual rollback via GitHub Actions

Once `deploy.yml` exists:

1. Go to **Actions** tab in GitHub.
2. Select the **Deploy** workflow.
3. Click **Run workflow** (dropdown).
4. In the `image_tag` input, enter `sha-{COMMIT_SHA}` of the known-good version.
   - Find the SHA on the **Commits** tab or in the **Actions** run history.
5. Click **Run workflow**.

The workflow will:
- Build the image for that commit (if not cached).
- Push it to GHCR.
- Deploy it to the VPS.

### E3. Manual rollback via SSH

If GitHub Actions is unavailable:

```bash
ssh -i ~/.ssh/deploy_bazuna deploy@<YOUR_VPS_IP>

cd /opt/mko_bazuna

# List available images
docker images | grep ghcr.io

# Down current containers
docker compose -f docker-compose.yml -f docker-compose.prod.yml down

# Set the image tag to the known-good version
export IMAGE_TAG="sha-<COMMIT_SHA>"

# Pull and start
docker compose -f docker-compose.yml -f docker-compose.prod.yml pull
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

> The rollback procedure is documented in this guide (§Stage E above). `docs/ops/docker-deployment.md` does **not** contain a rollback section — do not reference it for rollback; all rollback steps live here.

---

## 8. Stage F — Verification Checklist

**When:** Run after initial setup (once) and after each major change.

### F1. CI Verification

| Test | Expected Result | Status |
|------|----------------|--------|
| Push to `develop` branch | CI runs (6 jobs): build, test, lint, typecheck, lint-templates, i18n — no deploy | ✅ Live |
| Push to `main` branch | All 6 CI jobs run in parallel | ✅ Live |
| Open PR to `main` | CI runs with same behavior as push | ✅ Live |
| CI test command | `-m "not seed" -n auto --dist loadgroup --reuse-db --cov` (enforced by parity test) | ✅ Enforced |
| `ci-nightly.yml` runs | Daily at 03:00 UTC serial seed suite (`-m "seed"`) | ✅ Live |
| Parity test passes | `test_docs_ci_parity.py` asserts CI contract on `ci.yml` / `Makefile` / `pyproject.toml` | ✅ Enforced |

### F2. CD Verification (after `deploy.yml` is created)

| Test | Expected Result | Status |
|------|----------------|--------|
| Run `workflow_dispatch` with `sha-{SHA}` | Specific commit image deploys | ⬜ To verify |
| GHCR image pushed with SHA tag | Check `ghcr.io/manicko/mko_bazuna` package, tag `sha-<sha>` | ⬜ To verify |
| `docker compose pull` runs | Images fetched from GHCR (check deploy logs) | ⬜ To verify |
| Pre-deploy backup created | `.dump` file in `/opt/mko_bazuna/backups/` | ⬜ To verify |
| Pre-deploy migrations run | `migrate` one-shot service runs, exits 0 | ⬜ To verify |
| Health check passes | `docker compose exec -T web curl -sf http://localhost:8000/health/` returns 200 | ⬜ To verify |
| Containers running | `docker compose ps` shows all services `Up` | ⬜ To verify |
| Docker cleanup runs | `docker image prune -f` executed | ⬜ To verify |
| Rollback on failure | Deploy broken image → automatic rollback to previous tag | ⬜ To verify |

### F3. Server Health Verification (on VPS)

```bash
ssh -i ~/.ssh/deploy_bazuna deploy@<YOUR_VPS_IP>
cd /opt/mko_bazuna

# Check all containers
docker compose -f docker-compose.yml -f docker-compose.prod.yml ps

# Check web health
curl -s http://localhost:8000/health/

# Check logs
docker compose -f docker-compose.yml -f docker-compose.prod.yml logs web --tail 20
docker compose -f docker-compose.yml -f docker-compose.prod.yml logs bot --tail 20

# Check disk space
df -h

# Check backups
ls -la /opt/mko_bazuna/backups/
```

### F4. Local test verification (before deploying)

```powershell
# Start test DB (port 5433)
make test-db
# Or: .\Makefile.ps1 test-db

# Run fast gate (skips nightly seed suite)
make test
# Or: .\Makefile.ps1 test
```

> Local tests require the Docker test DB — never run `uv run pytest` directly without it.

---

## 9. Stage G — Daily Release Process

**When:** Every time you want to deploy a new version to production. This is the **only** stage you repeat regularly.

> **⚠️ Prerequisite:** `deploy.yml` must be created (§C4) before this process works. CI is already live and runs on every push/PR.

### G1. Prerequisites (verified daily)

Before each release, confirm:

1. **CI is green** on `main` branch (all 6 jobs pass in `ci.yml`).
2. **Your VPS is running** and accessible via SSH.
3. **You have the commit SHA** you want to deploy.

### G2. The release flow (5 minutes, no SSH needed)

#### Step 1. Merge to `main`

Ensure your changes are merged to the `main` branch:

```bash
git checkout main
git pull origin main
```

CI will automatically run on the push. Wait for all 6 jobs to pass.

#### Step 2. Trigger the deployment

1. Go to the **Actions** tab in GitHub.
2. Select the **Deploy** workflow (requires `deploy.yml` to exist — §C4).
3. Click the **Run workflow** dropdown → **Run workflow**.
4. In the `image_tag` input, enter the tag to deploy:
   - **For a specific commit:** `sha-{COMMIT_SHA}` (e.g., `sha-a913bc2`)
5. Click **Run workflow**.

> **Important:** The `image_tag` input is **required** (never defaults to `latest`). This ensures every deployment is traceable to a specific image and enables precise rollback.

The workflow will:
- Build the Docker image with the specified tag (OIDC to GHCR).
- Push to GHCR.
- SSH into the VPS.
- Pull the new image.
- **Backup the database** (pre-migration safety net).
- Run migrations (advisory lock, ID 100).
- Restart containers.
- Clean up old Docker images.
- Run health check (30 attempts × 5s).
- Rollback automatically if health check fails.

#### Step 3. Monitor the deployment

Watch the workflow run in the GitHub Actions UI. It takes 2–5 minutes.

**Success indicators:**
- All steps show green checkmarks.
- Health check step shows "Health check passed".
- Deploy step shows "Deployment complete".

**Failure indicators:**
- Any step shows a red X.
- Health check step shows "Health check failed — initiating automatic rollback".
- The workflow attempts automatic rollback to the previous tag.

#### Step 4. Verify on the server (recommended)

```bash
ssh -i ~/.ssh/deploy_bazuna deploy@<YOUR_VPS_IP>
cd /opt/mko_bazuna
docker compose -f docker-compose.yml -f docker-compose.prod.yml ps
curl -s http://localhost:8000/health/
```

### G3. Rollback (if something goes wrong)

If the deployment fails or the site is broken:

1. **Automatic:** If the health check fails, `deploy.yml`'s rollback step (§E1) automatically redeploys the previous tag.
2. **Manual via Actions:** Go to **Actions** → **Deploy** workflow → **Run workflow** dropdown → enter `sha-{KNOWN_GOOD_COMMIT_SHA}`.
3. **Manual via SSH:** See [§E3](#e3-manual-rollback-via-ssh).

### G4. What NOT to do during release

- **Do not** SSH into the VPS and run `docker compose up -d` manually (use the workflow) — the workflow handles the full sequence (pull → backup → migrate → up → prune → health).
- **Do not** edit `.env.docker` on the VPS during deploy — the workflow doesn't touch it, but manual edits can cause confusion.
- **Do not** merge to `main` without CI passing.
- **Do not** use `workflow_dispatch` on the `develop` branch — deploy only from `main`.
- **Do not** leave `image_tag` empty — always specify a SHA-based or version tag.

---

## 10. Forward-looking Recommendations

These are **advisory** improvements that can be implemented later. None change the core Docker + GHCR + manual-`workflow_dispatch` + single-VPS model.

1. **GitHub Releases for deployment triggers** — Instead of manually entering a tag in `workflow_dispatch`, create a GitHub Release → automatically triggers deploy. Creates a clear audit trail of all releases.

2. **Add a staging environment** — Even with one VPS, run a staging instance using a separate compose project name:
   ```bash
   # Staging
   docker compose -p stage -f docker-compose.yml -f docker-compose.prod.yml up -d
   # Production
   docker compose -p prod -f docker-compose.yml -f docker-compose.prod.yml up -d
   ```

3. **Trivy fs-mode vulnerability scan** — Add as a non-blocking CI job (scan source tree, report CRITICAL/HIGH as SARIF). See `plan.md_updated.md` §Stage D (D1).

4. **pip-audit for Python dependency vulnerabilities** — Add as a CI job scanning `uv.lock`. Verify Python 3.14 support first. See `plan.md_updated.md` §Stage D (D3).

5. **gitleaks + `.gitleaks.toml`** — Secret detection in CI to catch accidental commits. See `plan.md_updated.md` §Stage D (D5).

6. **zizmor workflow linting** — GitHub Actions workflow security linting. See `plan.md_updated.md` §Stage D (D6).

7. **Dependabot** — Weekly auto-updates for `github-actions` + `docker` ecosystems. See `plan.md_updated.md` §Stage D (D4).

8. **`--dist worksteal` (if xdist ≥ 3.8)** — Better test load balancing. ⚠️ **Requires updating `test_docs_ci_parity.py`** — `loadgroup` is intentional for FSM-pinned bot tests. See `plan.md_updated.md` §13 (Modern Best Practices #7).

9. **GitHub Actions build cache** — Add `cache-from: type=gha` alongside the existing GHCR registry cache in the CI build job. See `plan.md_updated.md` §Stage B (B1).

> **Do NOT rename compose files.** The original prep-guide §Forward-looking §3 proposed renaming `docker-compose.*.yml` → `compose.*.yaml`. This is **stale and should not be done** — all existing tooling (Makefile, overrides, CI, docs) depends on the legacy names. See `plan.md_updated.md` §12.4 (Architecture Constraints) and the [Compose Name Corrections](#c5-compose-file-name-corrections) section above.

---

## 11. Quick Reference

### GitHub Secrets (4 secrets — server access only)

| Name | Source |
|------|--------|
| `SERVER_HOST` | VPS IP address |
| `SERVER_USER` | `deploy` |
| `SERVER_SSH_KEY` | Private key from `~/.ssh/deploy_bazuna` |
| `SERVER_PORT` | `22` |

### VPS `.env.docker` variables (23 variables — app secrets live here only)

| Variable | Source |
|----------|--------|
| `DJANGO_SECRET_KEY` | `python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"` |
| `DEBUG` | `False` |
| `ALLOWED_HOSTS` | Your domain + localhost |
| `POSTGRES_USER` | `bazuna_user` |
| `POSTGRES_DB` | `bazuna_db` |
| `POSTGRES_PASSWORD` | `openssl rand -base64 32` |
| `REDIS_URL` | `redis://redis:6379/0` (Docker internal) |
| `BOT_USERNAME` | Your bot's username (without @) |
| `BOT_TOKEN` | From `@BotFather` |
| `SITE_URL` | Your production URL (no trailing slash) |
| `IMMEDIATE_ALERTS_ENABLED` | `false` |
| `TLS_CERT_PATH` | `/etc/nginx/certs` (or `/opt/mko_bazuna/certs`) |
| `PLAUSIBLE_HOST` | Empty to disable, or your Plausible instance |
| `ADMIN_USERNAME` | `admin` |
| `ADMIN_PASSWORD` | `openssl rand -base64 24` |
| `ADMIN_TELEGRAM_ID` | Your numeric Telegram ID |
| `SEED_USERS` | `10` (demo data) |
| `SEED_ADS` | `600` (demo data) |
| `REGISTRY` | `ghcr.io` |
| `REPOSITORY` | `manicko/mko_bazuna` |
| `IMAGE_TAG` | SHA tag or version (e.g., `sha-a913bc2`) |
| `FIX_PERMISSIONS` | `0` (auto-on when `DEBUG=True`) |
| `SKIP_ENV_CHECK` | Empty (skip env-file validation) |

### SSH key pairs

| File | Location | Purpose |
|------|----------|---------|
| Private key | `~/.ssh/github_bazuna` (local) | GitHub authentication (clone, push) |
| Public key | `~/.ssh/github_bazuna.pub` (local) | GitHub → Settings → SSH and GPG keys |
| Private key | `~/.ssh/deploy_bazuna` (local) | Becomes `SERVER_SSH_KEY` GitHub Secret |
| Public key | `~/.ssh/deploy_bazuna.pub` (local) | Copied to VPS `~/.ssh/authorized_keys` |

### Directory structure on VPS

```
/opt/mko_bazuna/
├── backups/                       # DB dumps (7-day retention + pre-deploy backups)
├── certs/                         # TLS: fullchain.pem, privkey.pem
├── media/                         # User-uploaded images
├── docker-compose.yml             # Copied from repo
├── docker-compose.prod.yml        # Copied from repo
├── docker/
│   └── nginx/
│       └── nginx.conf            # Copied from repo
└── .env.docker                    # Created in A7 (chmod 600)
```

### Local development commands

| Command | Purpose |
|---------|---------|
| `make up` (or `.\Makefile.ps1 up`) | Start dev environment (hot-reload, port 8000) |
| `make test-db` (or `.\Makefile.ps1 test-db`) | Start test PostgreSQL (port 5433) |
| `make test` (or `.\Makefile.ps1 test`) | Run fast gate (skips nightly seed suite) |
| `make test-all` | Run full suite (includes seed, ~35 min) |
| `make test-recreate` | Fresh schema (`--create-db`) |
| `make lint` | Ruff check |
| `make typecheck` | Basedpyright |

### Deploy commands (run on VPS by deploy.yml)

```bash
set -e
DEPLOY_DIR="/opt/mko_bazuna"
cd "$DEPLOY_DIR"

export REGISTRY="ghcr.io"
export REPOSITORY="${REPOSITORY}"
export IMAGE_TAG="${IMAGE_TAG}"   # e.g., sha-a913bc2 or v0.3.1

# Save current tag for rollback
CURRENT_IMAGE=$(docker compose -f docker-compose.yml -f docker-compose.prod.yml ps --format "{{.Image}}" web 2>/dev/null || echo "")
PREVIOUS_TAG=$(echo "$CURRENT_IMAGE" | rev | cut -d: -f1 | rev || echo "")
echo "$PREVIOUS_TAG" > /opt/mko_bazuna/.previous_tag

# Pull latest images from GHCR
docker compose -f docker-compose.yml -f docker-compose.prod.yml pull

# Backup database before migrations
docker compose -f docker-compose.yml -f docker-compose.prod.yml run --rm \
  db pg_dump -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" -F c \
  -f /backups/pre_deploy_$(date +%Y%m%d_%H%M%S).dump || echo "WARNING: Backup failed, continuing..."

# Run pre-deploy migrations (advisory lock, ID 100)
docker compose -f docker-compose.yml -f docker-compose.prod.yml run --rm migrate

# Start new containers (uses GHCR images via docker-compose.prod.yml:7-26 image overrides)
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d

# Clean up old images
docker image prune -f

echo "Deployment complete"
```

### Language support

The project supports three languages — **Russian / Bosnian / English** (Bosnian, not Montenegrin):

| StrEnum name | Locale code | Evidence |
|--------------|-------------|----------|
| `RUSSIAN` | `ru` | `base.py:69-73`; `Dockerfile:83` |
| `BOSNIAN` | `bs` | `enums.py:187-192`; `Dockerfile:83` |
| `ENGLISH` | `en` | `base.py:69-73`; `Dockerfile:83` |

The launch **geography** is Montenegro, but the UI **language code** is Bosnian (`bs`). Updated docs use `ru`/`bs`/`en` consistently.

---

*End of `preparation-guide.md_updated.md`. This is a planning document — it does not modify any production code, workflows, or configuration. The only file to be created is `.github/workflows/deploy.yml` (§C4). All already-implemented items are marked ✅ Done.*
