# CI/CD Preparation Guide — Mko Bazuna

**Date:** 2026-07-28  
**Based on:** `.ai/plans/ci_cd/plan.md`  
**Core principle:** Separate **one-time server preparation** (Stage A) from the **daily release process** (Stage G). One-time work is done once after buying a VPS; the daily process is repeated on every release.

---

## Table of Contents

0. [Stage 0 — Local Development Machine (Windows)](#stage-0--local-development-machine-windows)
1. [Repository Structure](#repository-structure)
2. [What Lives Where](#what-lives-where)
3. [Stage A — One-time Server Preparation](#stage-a--one-time-server-preparation)
4. [Stage B — GitHub Configuration](#stage-b--github-configuration)
5. [Stage C — GitHub Actions Workflow](#stage-c--github-actions-workflow)
6. [Stage E — Rollback Procedure](#stage-e--rollback-procedure)
7. [Stage F — Verification Checklist](#stage-f--verification-checklist)
8. [Stage G — Daily Release Process](#stage-g--daily-release-process)
9. [Forward-looking Recommendations](#forward-looking-recommendations)

---

## Stage 0 — Local Development Machine (Windows)

**When:** Execute once on your Windows development machine. This is the starting point — everything else builds on this.

**Goal:** A Windows machine with Git, Docker Desktop, Python, and the repository cloned locally.

### 0.1 Install Git

1. Download from [git-scm.com](https://git-scm.com/download/win).
2. Run the installer with default settings.
3. Verify:
   ```powershell
   git --version
   ```

### 0.2 Install Docker Desktop

1. Download from [docker.com](https://www.docker.com/products/docker-desktop/).
2. Run the installer.
3. Start Docker Desktop and wait for it to be ready (whale icon in system tray).
4. Verify:
   ```powershell
   docker --version
   docker compose version
   ```

### 0.3 Install Python

1. Download Python 3.14 from [python.org](https://www.python.org/downloads/).
2. During install, check **"Add Python to PATH"**.
3. Verify:
   ```powershell
   python --version
   pip --version
   ```

### 0.4 Install uv (package manager)

```powershell
pip install uv
```

Verify:
```powershell
uv --version
```

### 0.5 Configure SSH for GitHub

Generate an SSH key for GitHub authentication (this is **different** from the deploy key — see [SSH Key Pairs](#ssh-key-pairs)):

```powershell
ssh-keygen -t ed25519 -f ~/.ssh/github_bazuna -C "your-email@example.com"
```

Add the public key to GitHub:
1. Go to **GitHub → Settings → SSH and GPG keys → New SSH key**.
2. Title: `Windows Dev Machine`
3. Key: contents of `~/.ssh/github_bazuna.pub`
4. Click **Add SSH key**.

### 0.6 Clone the repository

```powershell
git clone git@github.com:manicko/mko_bazuna.git
cd mko_bazuna
```

### 0.7 Configure VSCode (optional)

Install recommended extensions:
- Python
- Ruff (linting)
- Docker
- GitLens

### 0.8 First local build

```powershell
cd mko_bazuna
docker compose -f compose.yaml -f compose.test.yaml up -d
```

Verify:
```powershell
curl http://localhost:8000/health/
```

Expected: `{"status": "ok"}`

---

## Repository Structure

Before setting up CI/CD, understand what lives in the Git repository:

```
mko_bazuna/
├── .github/
│   └── workflows/
│       ├── ci.yml           # Code quality: lint, typecheck, test
│       └── deploy.yml       # Deployment: build, push, deploy
├── docker/
│   ├── Dockerfile           # Multi-stage build
│   ├── entrypoint.sh        # Main entrypoint
│   ├── entrypoint-test.sh
│   ├── entrypoint-scheduler.sh
│   ├── entrypoint-create-admin.sh
│   └── nginx/
│       └── nginx.conf       # Reverse proxy config
├── src/
│   ├── backend/             # Django project (manage.py, config/, apps/)
│   ├── theme/               # Tailwind CSS source
│   └── telegram_bot/        # aiogram bot code
├── compose.yaml             # Base compose (db, migrate, web, bot, nginx)
├── compose.dev.yaml         # Dev overrides
├── compose.prod.yaml        # Production overrides (scheduler, backup, image tags)
├── compose.test.yaml        # Ephemeral test DB
├── pyproject.toml           # Project definition with uv
├── .env.docker              # Production env (NOT committed)
├── .env.example             # Template (committed)
└── README.md
```

**Key files used by CI/CD:**
- `.github/workflows/ci.yml` — CI pipeline
- `.github/workflows/deploy.yml` — CD pipeline
- `compose.yaml` + `compose.prod.yaml` — Used on VPS for deployment
- `docker/Dockerfile` — Builds the application image
- `docker/nginx/nginx.conf` — Reverse proxy configuration

---

## What Lives Where

### In Git Repository (committed)

```
compose.yaml
compose.dev.yaml
compose.prod.yaml
compose.test.yaml
docker/Dockerfile
docker/entrypoint*.sh
docker/nginx/nginx.conf
src/
.github/workflows/
.env.example
.env.dev.example
README.md
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
.env                  # Local development env
.env.local
src/.env
src/backend/.env
~/.ssh/github_bazuna  # SSH key for GitHub
~/.ssh/deploy_bazuna  # SSH key for VPS (deploy)
```

---

## SSH Key Pairs

There are **two separate SSH key pairs** — do not confuse them:

| Key Pair | Purpose | Used By |
|----------|---------|---------|
| `~/.ssh/github_bazuna` | Authenticate to GitHub (clone, push) | Your Windows machine → GitHub |
| `~/.ssh/deploy_bazuna` | Authenticate to VPS for deployment | GitHub Actions → VPS |

**Key 1 — GitHub access (Windows → GitHub):**
- Generated in [0.5](#05-configure-ssh-for-github)
- Public key added to GitHub **Settings → SSH and GPG keys**
- Private key stays on your Windows machine

**Key 2 — VPS deploy access (GitHub Actions → VPS):**
- Generated in [A4](#a4-set-up-ssh-key-authentication-for-the-deploy-user)
- Public key copied to VPS `~/.ssh/authorized_keys`
- Private key stored as `SERVER_SSH_KEY` GitHub Secret
- Used by `appleboy/ssh-action` in the deploy workflow

---

## Stage A — One-time Server Preparation

**When:** Execute once, immediately after purchasing the VPS. Never repeat unless the server is destroyed.

**Goal:** A hardened Linux server with Docker, a deploy user, directory structure, and an initial `.env.docker` file. After this stage, the server is ready to receive images from GHCR.

### A0. Prerequisites Checklist (before touching the server)

| Item | What you need | How to obtain |
|------|--------------|---------------|
| **VPS** | 4 CPU, 8 GB RAM, Ubuntu 22.04 LTS (or 24.04) | Any provider (DigitalOcean, Hetzner, AWS EC2, etc.) |
| **Root access** | Password or SSH key for `root` | Provided by VPS provider |
| **Domain name** (optional but recommended) | e.g., `bazuna.com` | Domain registrar |
| **GitHub account** | With admin access to the `mko_bazuna` repo | Existing or create new |
| **Telegram BotFather token** | Bot token string | Message `@BotFather` → `/newbot` → copy token |
| **Your Telegram user ID** | Numeric ID | Message `@userinfobot` → copy ID |

### A1. Provision the VPS

1. Create a VPS instance (Ubuntu 22.04 LTS recommended).
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
passwd deploy
```

### A4. Set up SSH key authentication for the deploy user

On your **local machine** (not the VPS), generate an SSH key pair:

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
├── backups/       # Database dumps (7-day retention)
├── certs/         # TLS certificates (fullchain.pem, privkey.pem)
├── media/         # User-uploaded images (Telegram ad photos)
├── compose.yaml         # Copied from repo
├── compose.prod.yaml    # Copied from repo
├── docker/
│   └── nginx/
│       └── nginx.conf        # Copied from repo
└── .env.docker                # Created in A6
```

### A6. Copy compose files and create `.env.docker`

**The source code is NOT needed on the VPS** — it is already baked into the Docker images pulled from GHCR. Only the Docker Compose files and nginx config are required to define service orchestration.

From your local machine:

```bash
# Create the nginx config directory on the VPS if it doesn't exist
ssh -i ~/.ssh/deploy_bazuna deploy@<YOUR_VPS_IP> "mkdir -p /opt/mko_bazuna/docker/nginx"

# Copy compose files and nginx config to the VPS
scp -i ~/.ssh/deploy_bazuna \
  compose.yaml \
  compose.prod.yaml \
  docker/nginx/nginx.conf \
  deploy@<YOUR_VPS_IP>:/opt/mko_bazuna/
```

> **Why not `git clone`?** If the server uses GHCR images, git is not needed at all. The source code is never referenced at runtime — only the compose files are used by `docker compose`.

Create the `.env.docker` file on the VPS:

```bash
cat > .env.docker << 'ENVEOF'
# .env.docker — Production environment for Docker deployment
# DO NOT set DATABASE_URL — Docker Compose constructs it from POSTGRES_* variables

# Django
DJANGO_SECRET_KEY=<GENERATE-A-LONG-RANDOM-STRING>
DEBUG=False
ALLOWED_HOSTS=<your-domain.com>,localhost,127.0.0.1

# PostgreSQL
POSTGRES_USER=bazuna_user
POSTGRES_DB=bazuna_db
POSTGRES_PASSWORD=<GENERATE-A-STRONG-PASSWORD>

# Telegram Bot
BOT_USERNAME=<your-bot-username>
BOT_TOKEN=<YOUR-BOT-TOKEN-FROM-BOTFATHER>

# TLS Certificates
TLS_CERT_PATH=/opt/mko_bazuna/certs

# Analytics (optional)
PLAUSIBLE_HOST=

# Admin
ADMIN_USERNAME=admin
ADMIN_PASSWORD=<GENERATE-A-STRONG-PASSWORD>
ADMIN_TELEGRAM_ID=<YOUR-TELEGRAM-USER-ID>
ENVEOF
```

#### Generating secure values

```bash
# Django secret key
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"

# PostgreSQL password
openssl rand -base64 32

# Admin password
openssl rand -base64 24
```

### A7. Set file permissions

On the VPS:

```bash
chmod 600 .env.docker
chown -R deploy:deploy /opt/mko_bazuna
chown -R deploy:deploy /opt/mko_bazuna/certs
chmod 700 /opt/mko_bazuna/certs
```

### A8. (Optional) Set up TLS certificates

If you have a domain and want HTTPS:

```bash
sudo apt-get install -y certbot
sudo certbot certonly --standalone -d your-domain.com
sudo cp /etc/letsencrypt/live/your-domain.com/fullchain.pem /opt/mko_bazuna/certs/
sudo cp /etc/letsencrypt/live/your-domain.com/privkey.pem /opt/mko_bazuna/certs/
sudo chown deploy:deploy /opt/mko_bazuna/certs/*
sudo chmod 600 /opt/mko_bazuna/certs/privkey.pem
```

### A9. (Optional) Initial manual deployment

Before CI/CD is fully wired (i.e., before GHCR images exist), you can do a manual test deploy that builds images locally:

```bash
cd /opt/mko_bazuna
docker compose -f compose.yaml -f compose.prod.yaml up -d --build
```

The `--build` flag forces a local build since no GHCR image exists yet. Once CI/CD is ready, future deploys will use `docker compose pull` to fetch pre-built images from GHCR instead.

---

## Stage B — GitHub Configuration

**When:** One-time setup in GitHub. Done alongside Stage A.

### B1. Create the `production` environment

1. Go to your GitHub repository → **Settings** → **Environments**.
2. Click **New environment**.
3. Name: `production`.
4. (Optional) Add required reviewers if you want approval gates.
5. Click **Configure environment**.

### B2. Add GitHub Secrets — Server Access Only

**Critical design decision:** Only server-access secrets go in GitHub Secrets. All application secrets (DJANGO_SECRET_KEY, BOT_TOKEN, POSTGRES_PASSWORD, ADMIN_PASSWORD) exist **only** in `.env.docker` on the VPS. This eliminates the risk of secret drift between two locations.

Go to **Settings** → **Secrets and variables** → **Actions** → **New repository secret**.

Add **only 4 secrets**:

| Secret Name | Value | How to obtain |
|-------------|-------|---------------|
| `SERVER_HOST` | VPS public IP or hostname | From VPS provider dashboard |
| `SERVER_USER` | `deploy` | The deploy user created in A3 |
| `SERVER_SSH_KEY` | Contents of `~/.ssh/deploy_bazuna` (private key) | Generated in A4 — **the private key, not the .pub file** |
| `SERVER_PORT` | `22` (or your custom SSH port) | Default is 22 unless you changed it |

#### Important: SERVER_SSH_KEY format

The `SERVER_SSH_KEY` must be the **entire private key file contents**, including the `-----BEGIN OPENSSH PRIVATE KEY-----` and `-----END OPENSSH PRIVATE KEY-----` lines.

```bash
# On your local machine, to copy to clipboard:
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

## Stage C — GitHub Actions Workflow

**When:** One-time file creation. After this, CI/CD runs automatically.

### C1. Split into two workflow files

**Do not** create a single `ci-cd.yml`. Instead, create two separate files for clear separation of concerns:

```
.github/workflows/
├── ci.yml        # Code quality: lint, typecheck, test, coverage
└── deploy.yml    # Deployment: build, push to GHCR, deploy to VPS
```

**Why split?**

- `ci.yml` runs on every push/PR and never touches the server. It validates code quality.
- `deploy.yml` runs only on manual `workflow_dispatch` and handles deployment only.
- Through years, when staging, multiple environments, or additional checks are added, this separation makes maintenance trivial.

### C2. `ci.yml` — Code Quality Workflow

Create `.github/workflows/ci.yml`:

```yaml
name: CI

on:
  push:
    branches: [main, develop]
    paths-ignore:
      - 'docs/**'
      - '*.md'
  pull_request:
    branches: [main, develop]
    paths-ignore:
      - 'docs/**'
      - '*.md'

concurrency:
  group: ${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: true

env:
  REGISTRY: ghcr.io
  IMAGE_NAME: ${{ github.repository }}

jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Setup uv
        uses: astral-sh/setup-uv@v5
        with:
          enable-cache: true
      - name: Install dependencies
        run: uv sync --frozen --no-install-project
        working-directory: src/backend
      - name: Run ruff
        run: uv run ruff check .
        working-directory: src/backend

  typecheck:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Setup uv
        uses: astral-sh/setup-uv@v5
        with:
          enable-cache: true
      - name: Install dependencies
        run: uv sync --frozen --no-install-project
        working-directory: src/backend
      - name: Run basedpyright
        run: uv run basedpyright .
        working-directory: src/backend

  test:
    runs-on: ubuntu-latest
    services:
      db:
        image: postgres:18-alpine
        env:
          POSTGRES_DB: mko_bazuna
          POSTGRES_USER: postgres
          POSTGRES_PASSWORD: postgres
        options: >-
          --health-cmd pg_isready
          --health-interval 5s
          --health-timeout 5s
          --health-retries 5
        ports:
          - 5432:5432
    steps:
      - uses: actions/checkout@v4
      - name: Setup uv
        uses: astral-sh/setup-uv@v5
        with:
          enable-cache: true
      - name: Install dependencies
        run: uv sync --frozen --no-install-project
        working-directory: src/backend
      - name: Wait for database
        run: |
          for i in $(seq 1 30); do
            if uv run python -c "import psycopg; psycopg.connect('postgres://postgres:postgres@localhost:5432/mko_bazuna')" 2>/dev/null; then
              echo "Database ready"
              exit 0
            fi
            sleep 1
          done
          echo "ERROR: Database unavailable" >&2
          exit 1
        working-directory: src/backend
      - name: Run migrations
        env:
          DJANGO_SETTINGS_MODULE: config.settings.test
          DATABASE_URL: postgres://postgres:postgres@localhost:5432/mko_bazuna
          DJANGO_SECRET_KEY: test-secret-key-for-testing-only
        run: uv run python -c 'from apps.core.utils.migrate_locked import main; import sys; sys.exit(main())'
        working-directory: src/backend
      - name: Check no pending migrations
        env:
          DJANGO_SETTINGS_MODULE: config.settings.test
          DATABASE_URL: postgres://postgres:postgres@localhost:5432/mko_bazuna
          DJANGO_SECRET_KEY: test-secret-key-for-testing-only
        run: uv run python -m django makemigrations --check --dry-run
        working-directory: src/backend
      - name: Run pytest with coverage
        env:
          DJANGO_SETTINGS_MODULE: config.settings.test
          DATABASE_URL: postgres://postgres:postgres@localhost:5432/mko_bazuna
          DJANGO_SECRET_KEY: test-secret-key-for-testing-only
        run: uv run pytest --tb=short --cov --cov-report=term --cov-report=xml -q
        working-directory: src/backend
      - name: Upload coverage report
        uses: actions/upload-artifact@v4
        with:
          name: coverage-report
          path: src/backend/coverage.xml
          retention-days: 30
```

### C3. `deploy.yml` — Deployment Workflow

Create `.github/workflows/deploy.yml`:

```yaml
name: Deploy

on:
  workflow_dispatch:
    inputs:
      image_tag:
        description: 'Image tag to deploy (e.g., sha-a913bc2 or v0.3.1)'
        required: true
        default: ''

concurrency:
  group: deploy-${{ github.ref }}
  cancel-in-progress: false

env:
  REGISTRY: ghcr.io
  IMAGE_NAME: ${{ github.repository }}

jobs:
  build:
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
          registry: ${{ env.REGISTRY }}
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}
      - name: Extract metadata
        id: meta
        uses: docker/metadata-action@v5
        with:
          images: ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}
          tags: |
            type=sha
            type=raw,value=${{ github.event.inputs.image_tag }}
      - name: Build and push
        uses: docker/build-push-action@v6
        with:
          context: .
          push: true
          platforms: linux/amd64
          tags: ${{ steps.meta.outputs.tags }}
          cache-from: type=gha
          cache-to: type=gha,mode=max

  security-scan:
    needs: build
    runs-on: ubuntu-latest
    steps:
      - name: Run Trivy vulnerability scanner
        uses: aquasecurity/trivy-action@master
        with:
          image-ref: ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}:sha-${{ github.sha }}
          format: 'sarif'
          output: 'trivy-results.sarif'
          ignore-unfixed: true
          severity: 'CRITICAL,HIGH'
      - name: Upload Trivy results to GitHub Security
        uses: github/codeql-action/upload-sarif@v3
        with:
          sarif_file: 'trivy-results.sarif'
          category: 'trivy'

  deploy:
    needs: [build]
    runs-on: ubuntu-latest
    environment: production
    steps:
      - name: Deploy to VPS
        uses: appleboy/ssh-action@v1
        with:
          host: ${{ secrets.SERVER_HOST }}
          username: ${{ secrets.SERVER_USER }}
          key: ${{ secrets.SERVER_SSH_KEY }}
          port: ${{ secrets.SERVER_PORT || '22' }}
          script: |
            set -e
            DEPLOY_DIR="/opt/mko_bazuna"
            cd "$DEPLOY_DIR"

            # Determine image tag
            IMAGE_TAG="${{ github.event.inputs.image_tag }}"
            export REGISTRY="ghcr.io"
            export REPOSITORY="${{ github.repository }}"
            export IMAGE_TAG="$IMAGE_TAG"

            # Save current tag for potential rollback
            CURRENT_IMAGE=$(docker inspect web 2>/dev/null | jq -r '.[0].Image' || echo "")
            if [ -n "$CURRENT_IMAGE" ]; then
              PREVIOUS_TAG=$(echo "$CURRENT_IMAGE" | sed 's/.*://')
            else
              PREVIOUS_TAG=""
            fi
            echo "$PREVIOUS_TAG" > /tmp/previous_tag.txt
            echo "Previous tag saved: $PREVIOUS_TAG"

            # Pull latest images from GHCR
            echo "Pulling images from GHCR..."
            docker compose -f compose.yaml -f compose.prod.yaml pull

            # Backup database before migrations (safety net)
            echo "Backing up database..."
            BACKUP_FILE="/opt/mko_bazuna/backups/pre_deploy_$(date +%Y%m%d_%H%M%S).dump"
            docker compose -f compose.yaml -f compose.prod.yaml run --rm \
              db pg_dump -U ${POSTGRES_USER:-postgres} -d ${POSTGRES_DB:-postgres} -F c -f /backups/pre_deploy_$(date +%Y%m%d_%H%M%S).dump || echo "WARNING: Backup failed, continuing..."

            # Run pre-deploy migrations
            echo "Running pre-deploy migrations..."
            docker compose -f compose.yaml -f compose.prod.yaml run --rm migrate

            # Start new containers
            echo "Starting new containers..."
            docker compose -f compose.yaml -f compose.prod.yaml up -d

            # Clean up old images
            docker image prune -f

            echo "Deployment complete"

      - name: Health check with automatic rollback
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

            # Health check via internal Docker network
            for i in {1..30}; do
              STATUS=$(curl -s -o /dev/null -w "%{http_code}" "http://web:8000/health/" 2>/dev/null || echo "000")
              if [ "$STATUS" = "200" ]; then
                echo "Health check passed"
                exit 0
              fi
              echo "Waiting for service (attempt $i)..."
              sleep 5
            done

            echo "Health check failed - initiating automatic rollback..."
            PREVIOUS_TAG=$(cat /tmp/previous_tag.txt 2>/dev/null || echo "")
            if [ -n "$PREVIOUS_TAG" ]; then
              echo "Rolling back to previous tag: $PREVIOUS_TAG"
              docker pull ghcr.io/${{ github.repository }}:$PREVIOUS_TAG
              docker compose -f compose.yaml -f compose.prod.yaml up -d --no-deps web
              echo "Rollback completed - verify manually"
            else
              echo "No previous tag available for rollback - check VPS manually"
            fi
            exit 1
```

### C4. Verify the workflow triggers

| Event | Branches | Paths | Behavior |
|-------|----------|-------|----------|
| `push` | `main`, `develop` | All except `docs/**` and `*.md` | CI only (lint, typecheck, test) |
| `pull_request` | `main`, `develop` | All except `docs/**` and `*.md` | CI only |
| `workflow_dispatch` | `main` only | N/A | Full CD (build → push → deploy) |

### C5. Verify `compose.prod.yaml` image overrides

The existing `compose.prod.yaml` already has `image:` overrides for `web`, `bot`, `migrate`, and `create_admin` services. These ensure Docker Compose pulls from GHCR instead of building locally. No changes needed.

### C6. Verify the `.env.docker` is NOT committed

```bash
git check-ignore .env.docker
# Should output: .env.docker
```

If not ignored, add it:

```bash
echo ".env.docker" >> .gitignore
```

### C7. Health endpoint

The project already has a `/health/` endpoint (per Dockerfile `HEALTHCHECK`). The deploy workflow verifies it via `curl http://web:8000/health/`. Expected response:

```json
{"status": "ok"}
```

---

## Stage E — Rollback Procedure

**When:** Used when a deployment breaks the production site.

### E1. Automatic rollback

The deploy workflow includes automatic rollback. If the health check fails after 30 attempts (150 seconds):

1. The workflow reads the previous tag from `/tmp/previous_tag.txt` on the VPS.
2. It pulls the previous image from GHCR.
3. It restarts the `web` container with the previous image.
4. The workflow exits with an error — you must verify manually.

### E2. Manual rollback via GitHub Actions

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
docker compose -f compose.yaml -f compose.prod.yaml down

# Set the image tag to the known-good version
export IMAGE_TAG="sha-<COMMIT_SHA>"

# Pull and start
docker compose -f compose.yaml -f compose.prod.yaml pull
docker compose -f compose.yaml -f compose.prod.yaml up -d
```

---

## Stage F — Verification Checklist

**When:** Run after initial setup (once) and after each major change.

### F1. CI Verification

| Test | Expected Result |
|------|----------------|
| Push to `develop` branch | CI runs (lint, typecheck, test) — no build/deploy |
| Push to `main` branch | All CI jobs run in parallel |
| Open PR to `main` | CI runs with same behavior as push |
| Modify only `docs/**` | CI is **skipped** (path filter) |
| Modify only `*.md` | CI is **skipped** (path filter) |

### F2. CD Verification

| Test | Expected Result |
|------|----------------|
| Run workflow dispatch with `sha-{SHA}` | Specific commit image deploys |
| Verify `docker compose pull` runs | Images fetched from GHCR (check logs) |
| Verify pre-deploy backup runs | `.dump` file created in `/opt/mko_bazuna/backups/` |
| Verify migrations run before restart | `migrate` container runs, exits successfully |
| Verify health check passes | `curl http://web:8000/health/` returns 200 |
| Verify containers running | `docker compose ps` shows all services `Up` |
| Verify no local build | No `build` step in deploy logs |
| Verify Docker cleanup runs | `docker image prune -f` executed |

### F3. Rollback Verification

| Test | Expected Result |
|------|----------------|
| Deploy with specific SHA tag | Old version is pulled and running |
| Deploy a broken version | Automatic rollback to previous tag |
| Manual rollback via Actions | Known-good version deploys successfully |

### F4. Server Health Verification

On the VPS:

```bash
# Check all containers
docker compose -f compose.yaml -f compose.prod.yaml ps

# Check web health
curl -s http://localhost:8000/health/

# Check logs
docker compose -f compose.yaml -f compose.prod.yaml logs web --tail 20
docker compose -f compose.yaml -f compose.prod.yaml logs bot --tail 20

# Check disk space
df -h

# Check backups
ls -la /opt/mko_bazuna/backups/
```

---

## Stage G — Daily Release Process

**When:** Every time you want to deploy a new version to production. This is the **only** stage you repeat regularly.

### G1. Prerequisites (verified daily)

Before each release, confirm:

1. **CI is green** on `main` branch (all jobs pass).
2. **Your VPS is running** and accessible.
3. **You have the commit SHA** you want to deploy.

### G2. The release flow (5 minutes, no SSH needed)

#### Step 1. Merge to `main`

Ensure your changes are merged to the `main` branch:

```bash
git checkout main
git pull origin main
```

CI will automatically run on the push. Wait for all jobs to pass.

#### Step 2. Trigger the deployment

1. Go to the **Actions** tab in GitHub.
2. Select the **Deploy** workflow.
3. Click the **Run workflow** dropdown → **Run workflow**.
4. In the `image_tag` input, enter the tag to deploy:
   - **For a specific commit:** `sha-{COMMIT_SHA}` (e.g., `sha-a913bc2`)
   - **For a release:** `v0.3.1`
5. Click **Run workflow**.

> **Important:** The `image_tag` input is **required** — you must always specify a tag. Never leave it empty. This ensures every deployment is traceable to a specific image.

The workflow will:
- Build the Docker image with the specified tag.
- Push to GHCR.
- SSH into the VPS.
- Pull the new image.
- **Backup the database** (pre-migration safety net).
- Run migrations.
- Restart containers.
- Clean up old Docker images.
- Run health check.

#### Step 3. Monitor the deployment

Watch the workflow run in the GitHub Actions UI. It takes 2–5 minutes.

**Success indicators:**
- All steps show green checkmarks.
- Health check step shows "Health check passed".
- Deploy step shows "Deployment complete".

**Failure indicators:**
- Any step shows a red X.
- Health check step shows "Health check failed".
- The workflow may attempt automatic rollback.

#### Step 4. Verify on the server (optional but recommended)

```bash
ssh -i ~/.ssh/deploy_bazuna deploy@<YOUR_VPS_IP>

cd /opt/mko_bazuna
docker compose -f compose.yaml -f compose.prod.yaml ps
curl -s http://localhost:8000/health/
```

### G3. Rollback (if something goes wrong)

If the deployment fails or the site is broken:

1. Go to **Actions** → **Deploy** workflow.
2. Click **Run workflow** dropdown.
3. In `image_tag`, enter `sha-{KNOWN_GOOD_COMMIT_SHA}`.
4. Click **Run workflow**.

The previous version will be deployed.

### G4. What NOT to do during release

- **Do not** SSH into the VPS and run `docker compose up -d` manually — the workflow handles this.
- **Do not** edit `.env.docker` on the VPS during deploy — the workflow doesn't touch it, but manual edits can cause confusion.
- **Do not** merge to `main` without CI passing.
- **Do not** use `workflow_dispatch` on the `develop` branch — deploy only from `main`.
- **Do not** leave `image_tag` empty — always specify a tag.

---

## Forward-looking Recommendations

These are **advisory** improvements that can be implemented later as the project grows.

### 1. Use GitHub Releases for deployment triggers

Instead of manually entering a tag in `workflow_dispatch`, create a GitHub Release:

```
GitHub Release v0.3.1
  ↓
Triggers deploy.yml automatically
  ↓
Deploys to production
```

This creates a clear audit trail of all releases in the GitHub UI.

### 2. Add a staging environment

Even with one VPS, you can run a staging instance using a separate compose project:

```bash
# Staging
docker compose -p stage -f compose.yaml -f compose.prod.yaml up -d

# Production
docker compose -p prod -f compose.yaml -f compose.prod.yaml up -d
```

This allows testing deployments before they hit production.

### 3. Rename compose files to Docker's recommended convention

Docker now recommends `compose.yaml` and `compose.dev.yaml` instead of `docker-compose.yml`. The plan already uses the modern naming. If the existing project files still use the old naming, rename them:

```
compose.yaml         (was docker-compose.yml)
compose.prod.yaml    (was docker-compose.prod.yml)
compose.test.yaml    (was docker-compose.test.yml)
```

### 4. Add dependency audit (pip-audit)

Add a job to `ci.yml` that scans Python dependencies for known vulnerabilities:

```yaml
dependency-audit:
  runs-on: ubuntu-latest
  steps:
    - uses: actions/checkout@v4
    - name: Setup uv
      uses: astral-sh/setup-uv@v5
    - name: Run pip-audit
      run: uv run pip-audit --requirement src/backend/uv.lock
```

---

## Summary: One-time vs. Daily

| | One-time (Stages A–F) | Daily (Stage G) |
|---|---|---|
| **VPS setup** | ✅ Done once | — |
| **Docker install** | ✅ Done once | — |
| **Deploy user** | ✅ Created once | — |
| **SSH keys** | ✅ Generated once | — |
| **GitHub Secrets** (4 server-only) | ✅ Added once | — |
| **GitHub Environment** | ✅ Created once | — |
| **Workflow files** (`ci.yml` + `deploy.yml`) | ✅ Created once | — |
| **`.env.docker`** on VPS | ✅ Created once | — |
| **Build & push image** | — | ✅ Every release |
| **Deploy to VPS** | — | ✅ Every release |
| **Database backup** | — | ✅ Before every migration |
| **Run migrations** | — | ✅ Every release |
| **Health check** | — | ✅ Every release |
| **Docker cleanup** | — | ✅ After every deploy |
| **Rollback if needed** | — | ✅ When broken |
| **Monitor logs** | — | ✅ After deploy |

---

## Quick Reference: All Secrets and Values

### GitHub Secrets (4 secrets — server access only)

| Name | Source |
|------|--------|
| `SERVER_HOST` | VPS IP address |
| `SERVER_USER` | `deploy` |
| `SERVER_SSH_KEY` | Private key from `~/.ssh/deploy_bazuna` |
| `SERVER_PORT` | `22` |

### VPS `.env.docker` variables (10 variables — app secrets live here only)

| Variable | Source |
|----------|--------|
| `DJANGO_SECRET_KEY` | `python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"` |
| `DEBUG` | `False` |
| `ALLOWED_HOSTS` | Your domain + localhost |
| `POSTGRES_USER` | `bazuna_user` |
| `POSTGRES_DB` | `bazuna_db` |
| `POSTGRES_PASSWORD` | `openssl rand -base64 32` |
| `BOT_USERNAME` | Your bot's username (without @) |
| `BOT_TOKEN` | From `@BotFather` |
| `ADMIN_PASSWORD` | `openssl rand -base64 24` |
| `ADMIN_TELEGRAM_ID` | Your numeric Telegram ID |

### SSH key pair

| File | Location | Purpose |
|------|----------|---------|
| Private key | `~/.ssh/deploy_bazuna` (local) | Becomes `SERVER_SSH_KEY` GitHub Secret |
| Public key | `~/.ssh/deploy_bazuna.pub` (local) | Copied to VPS `~/.ssh/authorized_keys` |

### Directory structure on VPS

```
/opt/mko_bazuna/
├── backups/           # DB dumps (7-day retention + pre-deploy backups)
├── certs/             # TLS: fullchain.pem, privkey.pem
├── media/             # User-uploaded images
├── compose.yaml         # Copied from repo
├── compose.prod.yaml    # Copied from repo
├── docker/
│   └── nginx/
│       └── nginx.conf        # Copied from repo
└── .env.docker                # Created in A6 (chmod 600)
```

**Note:** Source code is NOT on the VPS. Only compose files and nginx config are needed — the application code lives inside the Docker images pulled from GHCR.
