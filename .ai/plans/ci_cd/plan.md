# CI/CD Implementation Plan for Mko Bazuna

**Date:** 2026-07-28  
**Based on:** `.ai/plans/ci_cd/research.md`  
**Strategy:** Docker-based manual deploy with GitHub Actions

---

## 0. Overview

Implementation of Docker-based CI/CD pipeline with manual deployment to VPS via GitHub Actions. Architecture:
- **CI:** Parallel lint → typecheck → test jobs on push/PR
- **CD:** Manual workflow dispatch → build → push → deploy
- **Registry:** GitHub Container Registry (GHCR)
- **Target:** Single VPS (4 CPU, 8 GB RAM), no staging environment
- **Workflow files:** Split into `ci.yml` (code quality) + `deploy.yml` (deployment)

---

## 1. Repository Structure

```
mko_bazuna/
├── .github/
│   └── workflows/
│       ├── ci.yml           # Code quality: lint, typecheck, test
│       └── deploy.yml       # Deployment: build, push, deploy
├── docker/
│   ├── Dockerfile           # Multi-stage build
│   ├── entrypoint*.sh       # Entrypoint scripts
│   └── nginx/
│       └── nginx.conf       # Reverse proxy config
├── src/
│   ├── backend/             # Django project
│   ├── theme/               # Tailwind CSS source
│   └── telegram_bot/        # aiogram bot code
├── compose.yaml             # Base compose (db, migrate, web, bot, nginx)
├── compose.prod.yaml        # Production overrides (scheduler, backup, image tags)
├── compose.test.yaml        # Ephemeral test DB
├── pyproject.toml           # Project definition with uv
├── .env.docker              # Production env (NOT committed)
├── .env.example             # Template (committed)
└── README.md
```

**Note:** The plan uses modern Docker Compose V2 naming (`compose.yaml` instead of `docker-compose.yml`). The existing project files use the old naming — rename during implementation.

---

## 2. What Lives Where

### In Git Repository (committed)

```
compose.yaml
compose.prod.yaml
compose.test.yaml
docker/Dockerfile
docker/entrypoint*.sh
docker/nginx/nginx.conf
src/
.github/workflows/
.env.example
README.md
```

### Only on VPS (never committed)

```
.env.docker          # Production secrets
media/               # User-uploaded images
backups/             # Database dumps
certs/               # TLS certificates
```

### Never committed (local only)

```
~/.ssh/github_bazuna  # SSH key for GitHub (Windows → GitHub)
~/.ssh/deploy_bazuna  # SSH key for VPS (GitHub Actions → VPS)
```

---

## 3. SSH Key Pairs

There are **two separate SSH key pairs** — do not confuse them:

| Key Pair | Purpose | Used By |
|----------|---------|---------|
| `~/.ssh/github_bazuna` | Authenticate to GitHub | Windows machine → GitHub |
| `~/.ssh/deploy_bazuna` | Authenticate to VPS | GitHub Actions → VPS |

**Key 1 — GitHub access:** Generated on the developer's Windows machine. Public key added to GitHub Settings → SSH and GPG keys. Private key stays local.

**Key 2 — VPS deploy access:** Generated on the developer's Windows machine. Public key copied to VPS `~/.ssh/authorized_keys`. Private key stored as `SERVER_SSH_KEY` GitHub Secret.

---

## 4. Pre-implemented Components

| Component | Status | Notes |
|-----------|--------|-------|
| Non-root user (uid 1000) | ✅ Already in Dockerfile | See docker/Dockerfile |
| Coverage upload | ✅ Already configured | CI workflow |
| PostgreSQL 18 service | ✅ Already configured | CI workflow |
| Build cache | ⚠️ Optional | Currently uses registry cache; GHA cache is optional optimization |
| Health endpoint | ✅ Already in Dockerfile | `curl -f http://localhost:8000/health/` |
| Docker image prune | ✅ Already in plan | Runs after deploy |

---

## 5. Implementation Stages

### Stage 0: Local Development Machine (Windows)

**When:** Execute once on the developer's Windows machine. This is the starting point.

| ID | Task | Priority | Effort | Dependencies |
|----|------|----------|--------|--------------|
| 0.1 | Install Git, Docker Desktop, Python 3.14, uv | HIGH | trivial | None |
| 0.2 | Generate SSH key for GitHub (`~/.ssh/github_bazuna`) | HIGH | trivial | 0.1 |
| 0.3 | Clone repository and verify local build | HIGH | trivial | 0.2 |

**Commands:**
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
docker compose -f compose.yaml -f compose.test.yaml up -d
curl http://localhost:8000/health/
```

---

### Stage A: Preparation & Setup (Priority: HIGH)

**When:** Execute once, immediately after purchasing the VPS.

**Goal:** A hardened Linux server with Docker, a deploy user, directory structure, and an initial `.env.docker` file.

| ID | Task | Priority | Effort | Dependencies | Risks |
|----|------|----------|--------|--------------|-------|
| A1 | Create `production` environment in GitHub repository settings | HIGH | trivial | None | Deployment could run without proper approval |
| A2 | Add GitHub Secrets: SERVER_HOST, SERVER_USER, SERVER_SSH_KEY, SERVER_PORT | HIGH | trivial | A1 | Secret exposure if not properly configured |
| A3 | Generate deploy SSH key (`~/.ssh/deploy_bazuna`) and copy public key to VPS | HIGH | trivial | None | SSH key compromise |
| A4 | Install Docker and Docker Compose on VPS | HIGH | small | None | — |
| A5 | Create deploy user on VPS with Docker group membership | HIGH | small | A4 | Security misconfiguration |
| A6 | Prepare VPS directory structure (`/opt/mko_bazuna/{backups,certs,media}`) | HIGH | small | A5 | Security misconfiguration, permission issues |
| A7 | Copy compose files + nginx config to VPS (NOT source code) | HIGH | trivial | A5 | Missing files |
| A8 | Create `.env.docker` file on VPS with production secrets | HIGH | small | A7 | Secret exposure if copied incorrectly |
| A9 | Set file permissions on VPS (600 for .env.docker, deploy ownership) | MEDIUM | trivial | A8 | Secret exposure in logs |

#### A6 — Step-by-step VPS preparation

The VPS preparation must be done step-by-step with verification at each step:

```bash
# 1. SSH as root
ssh root@SERVER_IP

# 2. Create deploy user
adduser deploy
usermod -aG docker deploy

# 3. Create directory structure
mkdir -p /opt/mko_bazuna/{backups,certs,media,docker/nginx}
chown -R deploy:deploy /opt/mko_bazuna

# 4. Exit and verify as deploy user
exit
ssh deploy@SERVER_IP

# 5. Verify working directory
pwd
# Expected: /home/deploy

# 6. Verify directory structure
ls -la /opt/mko_bazuna/
# Expected: backups/  certs/  media/  docker/
```

#### A8 — `.env.docker` (app secrets live here ONLY)

**Critical design decision:** Application secrets (DJANGO_SECRET_KEY, BOT_TOKEN, POSTGRES_PASSWORD, ADMIN_PASSWORD) exist **only** in `.env.docker` on the VPS. They are **NOT** stored as GitHub Secrets. This eliminates the risk of secret drift between two locations.

```bash
# On VPS, as deploy user:
cat > /opt/mko_bazuna/.env.docker << 'ENVEOF'
DJANGO_SECRET_KEY=<generate-with-django-secret-key-generator>
DEBUG=False
ALLOWED_HOSTS=<your-domain.com>,localhost,127.0.0.1

POSTGRES_USER=bazuna_user
POSTGRES_DB=bazuna_db
POSTGRES_PASSWORD=<generate-with-openssl-rand-base64-32>

BOT_USERNAME=<your-bot-username>
BOT_TOKEN=<your-bot-token-from-botfather>

TLS_CERT_PATH=/opt/mko_bazuna/certs

ADMIN_USERNAME=admin
ADMIN_PASSWORD=<generate-with-openssl-rand-base64-24>
ADMIN_TELEGRAM_ID=<your-telegram-user-id>
ENVEOF

chmod 600 .env.docker
```

---

### Stage B: CI Pipeline (Enhancement)

| ID | Task | Priority | Effort | Dependencies | Risks |
|----|------|----------|--------|--------------|-------|
| B1 | Add concurrency control to existing `.github/workflows/ci.yml` | MEDIUM | trivial | None | Resource waste on multiple concurrent builds |
| B2 | Split `ci.yml` into `ci.yml` + `deploy.yml`; add `workflow_dispatch` with **required** `image_tag` input | HIGH | small | B1 | Broken workflow if not done carefully |
| B3 | Add path filters to skip CI for docs-only changes | HIGH | small | B1 | CI might run unnecessarily, consuming minutes |
| B4 | Verify existing PostgreSQL 18 service configuration (no changes needed) | HIGH | trivial | None | — |
| B5 | Verify coverage artifact upload configuration | LOW | trivial | None | — |
| B6 | Integrate rollback documentation into `docs/ops/docker-deployment.md` | MEDIUM | small | None | Duplicate documentation if not merged |

**Key change in B2:** The `image_tag` input is **required** — never allow empty/default `latest`. Always deploy a specific tag (`sha-{COMMIT_SHA}` or `v0.3.1`).

---

### Stage C: CD Pipeline (Extend existing)

| ID | Task | Priority | Effort | Dependencies | Risks |
|----|------|----------|--------|--------------|-------|
| C1 | Add GHCR authentication to existing build job | HIGH | small | B1 | Authentication failures |
| C2 | Update build job to push images with SHA-based tags | HIGH | small | C1 | Failed image pushes |
| C3 | Remove ARM64 from platforms (keep only linux/amd64) | HIGH | trivial | C2 | None |
| C4 | Implement deploy job with SSH-based Docker Compose orchestration | HIGH | medium | A2, C2 | Production outage, failed rollbacks |
| C5 | Add `docker compose pull` before up -d to fetch images from GHCR | HIGH | trivial | C4 | Stale images deployed |
| C6 | Add pre-deploy **database backup** (`pg_dump`) before migrations | HIGH | small | C4, C5 | Data loss on migration failure |
| C7 | Add pre-deploy migrations via `docker compose run --rm migrate` | HIGH | small | C4, C5, C6 | Database drift on deploy |
| C8 | Override image in compose.prod.yaml for GHCR registry (prevents build vs pull conflict) | HIGH | small | C4 | Build vs pull conflict |
| C9 | Add deploy health check with automatic rollback on failure | HIGH | medium | C4, C5, C6, C7, C8 | Failed deployments left in broken state |
| C10 | Add `docker image prune -f` after successful deployment | HIGH | trivial | C4 | Disk bloat over time |

---

### Stage D: Security & Hardening

| ID | Task | Priority | Effort | Dependencies | Risks |
|----|------|----------|--------|--------------|-------|
| D1 | Add Trivy security scan job (CRITICAL/HIGH severity, non-blocking) | MEDIUM | small | C2 | Unpatched vulnerabilities in production |
| D2 | Configure Trivy SARIF upload to GitHub Security tab | MEDIUM | trivial | D1 | No security visibility |
| D3 | Add dependency audit (pip-audit) for Python packages | MEDIUM | small | None | Outdated/vulnerable packages |

---

## 6. Execution Order (Topological Sort)

```
0.1 → 0.2 → 0.3

A1 → A2, A3 → A4, A5 → A6, A7 → A8, A9
                ↓
B1 → B2 → B3, B4, B5 → B6 (docs integration)
              ↓
C1 → C2 → C3 → C4 → C5 → C6 → C7 → C8 → C9 → C10
               ↓
             C10 (can run in parallel with C9)
             ↓
D1 → D2
D3 → (after C2)
```

**Critical Path:** 0.1 → A1 → A2/A3 → B1 → C1 → C2 → C3 → C4 → C5 → C6 → C7 → C8 → C9 (sequential, ~5-7 days calendar time with parallel execution)

---

## 7. Task Graph (Dependency DAG)

```
┌─────────────┐
│    0.1      │ (Local dev setup)
└──────┬──────┘
       │
       ▼
┌─────────────┐
│    A1      │ (GitHub Environment)
└──────┬──────┘
       │
       ▼
┌─────────────┐
│ A2, A3      │ (GitHub Secrets + SSH keys)
└──────┬──────┘
       │
       ▼
┌─────────────┐
│ A4, A5, A6, A7, A8, A9 │ (VPS Setup)
└──────┬──────┘
       │
       ▼
┌─────────────────────────────┐
│  Stage B: CI Enhancements    │
├────────┬────────┬──────────┤
│   B1   │   B2   │ B3, B4, B5, B6│
│Concurrency│ Split  │ Verify/Docs │
│          │ Workflow│             │
└────────┴────────┴──────────┘
                       │
                       ▼
┌────────────────────────────────────────────────────────────────┐
│                  Stage C: CD Pipeline                             │
├────────┬────────┬────────┬────────┬────────┬────────┬──────────┤
│   C1   │   C2   │   C3   │   C4   │   C5   │  C6   │  C7, C8, C9, C10 │
│  GHCR  │ Push   │ Single │ Deploy │ Pull   │ Backup│ Image, Health,  │
│ Auth   │ SHA    │ Arch   │ Job    │ Images │ & Migr│ Prune           │
└────────┴────────┴────────┴────────┴────────┴────────┴──────────┘
                             │
                             ▼
┌──────────────────────────────────────────┐
│        Stage D: Security & Hardening       │
├────────┬────────────────────────────────┤
│   D1   │ D2, D3                         │
│Trivy   │ Security & Audit                 │
└────────┴────────────────────────────────┘
```

---

## 8. Risk Assessment & Mitigation

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| GitHub Actions time limit exceeded | MEDIUM | HIGH | Implement path filters; optimize test duration; consider public repo for unlimited minutes |
| SSH key compromise | LOW | HIGH | Use ED25519 keys; rotate quarterly; restrict deploy user permissions; separate GitHub and VPS keys |
| Trivy scan blocks deploy | LOW | MEDIUM | Run as non-blocking job; use `ignore-unfixed: true` |
| Database migration failure | MEDIUM | HIGH | Advisory lock prevents concurrent runs; test migrations in CI; **backup before deploy** (C6) |
| Database backup failure | LOW | MEDIUM | Non-blocking backup; log warning and continue |
| Rollback procedure failure | LOW | MEDIUM | Automated rollback on health check failure; test with known-good SHA tag |
| Secret leak in logs | LOW | CRITICAL | Mask `SERVER_HOST` with `::add-mask::`; use GitHub Environments; app secrets NOT in GitHub Secrets |
| Build vs pull conflict | MEDIUM | HIGH | Add `image:` override in compose.prod.yaml for web/bot services |
| Stale image deployment | MEDIUM | HIGH | Add `docker compose pull` before `up -d` in deploy workflow |
| Disk bloat from old images | MEDIUM | MEDIUM | Add `docker image prune -f` after successful deploy (C10) |
| `latest` tag ambiguity | HIGH | MEDIUM | Make `image_tag` required in workflow_dispatch; never use `latest` |

---

## 9. Verification Steps

After implementation:

1. **CI Verification:**
   - Push to `develop` branch → verify CI runs (no build/deploy)
   - Push to `main` branch → verify all jobs execute in parallel
   - Open PR → verify CI runs with same behavior as push
   - Modify only documentation → verify CI is skipped

2. **CD Verification:**
   - Run workflow dispatch with `sha-{SHA}` → specific commit image deploys
   - Verify `docker compose pull` executes before container start
   - Verify pre-deploy **database backup** executes before migrations
   - Verify pre-deploy migrations execute after pull, before container restart
   - Verify health check passes after deployment (30 attempts × 5s)
   - Verify containers running: `docker compose ps` on VPS
   - Verify no build occurs (containers use GHCR images)
   - Verify `docker image prune -f` executes after successful deploy

3. **Rollback Verification:**
   - Trigger deploy with specific SHA tag
   - Verify old version is pulled and running
   - Test automatic rollback by deploying a broken version

---

## 10. Files to Create/Modify

| Action | Path | Notes |
|--------|------|-------|
| Create | `.github/workflows/ci.yml` | CI pipeline: lint, typecheck, test, coverage |
| Create | `.github/workflows/deploy.yml` | CD pipeline: build, push to GHCR, deploy to VPS |
| Rename | `docker-compose.yml` → `compose.yaml` | Modern Docker Compose V2 naming |
| Rename | `docker-compose.prod.yml` → `compose.prod.yaml` | Modern Docker Compose V2 naming |
| Rename | `docker-compose.test.yml` → `compose.test.yaml` | Modern Docker Compose V2 naming |
| Modify | `compose.prod.yaml` | Add `image:` override for web/bot services to use GHCR images |
| Modify | `docs/ops/docker-deployment.md` | Merge rollback procedure into existing deployment docs |
| Modify | `.gitignore` | Ensure `.env.docker` is ignored |

### 10.1 Deployment Commands Reference

The deploy job will execute on VPS:

```bash
cd /opt/mko_bazuna

# Determine image tag (REQUIRED — no default to latest)
IMAGE_TAG="${{ github.event.inputs.image_tag }}"

# Export environment variables for compose (image override)
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

# Backup database before migrations (safety net for data corruption)
echo "Backing up database..."
docker compose -f compose.yaml -f compose.prod.yaml run --rm \
  db pg_dump -U ${POSTGRES_USER:-postgres} -d ${POSTGRES_DB:-postgres} -F c \
  -f /backups/pre_deploy_$(date +%Y%m%d_%H%M%S).dump || echo "WARNING: Backup failed, continuing..."

# Run pre-deploy migrations (critical: must run before container restart)
echo "Running pre-deploy migrations..."
docker compose -f compose.yaml -f compose.prod.yaml run --rm migrate

# Start new containers (uses pulled images due to image: override in prod override)
echo "Starting new containers..."
docker compose -f compose.yaml -f compose.prod.yaml up -d

# Clean up old images
docker image prune -f

echo "Deployment complete"
```

### 10.2 compose.prod.yaml Image Override

The production override file must specify `image:` for web and bot services to prevent `docker compose` from using the `build:` directive. This ensures the workflow pulls from GHCR.

```yaml
# Production override for compose.yaml
# Immutable image deployment with TLS hardening, scheduler, and image overrides for GHCR

services:
  # Override web for production: use pre-built image from GHCR
  web:
    image: ${REGISTRY:-ghcr.io}/${REPOSITORY:-manicko/mko_bazuna}:${IMAGE_TAG:-latest}

  # Override bot for production: use pre-built image from GHCR
  bot:
    image: ${REGISTRY:-ghcr.io}/${REPOSITORY:-manicko/mko_bazuna}:${IMAGE_TAG:-latest}

  # ... rest of the file unchanged
```

### 10.3 Complete Workflow YAML — Split into ci.yml + deploy.yml

#### `.github/workflows/ci.yml` — Code Quality

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

#### `.github/workflows/deploy.yml` — Deployment

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

            # Determine image tag (REQUIRED — no default to latest)
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

            # Backup database before migrations (safety net for data corruption)
            echo "Backing up database..."
            docker compose -f compose.yaml -f compose.prod.yaml run --rm \
              db pg_dump -U ${POSTGRES_USER:-postgres} -d ${POSTGRES_DB:-postgres} -F c \
              -f /backups/pre_deploy_$(date +%Y%m%d_%H%M%S).dump || echo "WARNING: Backup failed, continuing..."

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

### 10.4 Branch Strategy

| Branch | Behavior |
|--------|----------|
| `main` | CI runs on push/PR; CD builds image; deploy via workflow dispatch |
| `develop` | CI only (tests, lint) - no image build |

---

## 11. Effort Summary

| Effort | Tasks Count |
|--------|-------------|
| trivial | 0.1, A1, A2, A3, A9, B1, B4, B5, C3, C5, C10, D2 |
| small | 0.2, 0.3, A4, A5, A6, A7, A8, B2, B3, B6, C1, C2, C6, C7, D1, D3 |
| medium | C4, C9 |

**Total: 24 tasks** — Estimated effort: **large** (~5-7 days with validation)

---

## 12. Estimated Timeline

| Stage | Tasks | Calendar Time |
|-------|-------|-------------|
| 0: Local Dev | 0.1-0.3 | 1 hour |
| A: Preparation | A1-A9 | 1 day |
| B: CI Enhancement | B1-B6 | 1 day |
| C: CD Extension | C1-C10 | 2-3 days |
| D: Security | D1-D3 | 1 day |
| **Total** | **24 tasks** | **5-7 days** (with testing/validation) |

---

## 13. Rollback Procedure

### Automatic Rollback

The deploy job includes automatic rollback on health check failure. If health check fails after 30 attempts:
1. The workflow reads the previously saved tag from `/tmp/previous_tag.txt`
2. It pulls the image with that tag: `ghcr.io/<repo>:<tag>`
3. It restarts the web container with the previous image
4. This happens transparently without manual intervention

### Manual Rollback

1. Go to **Actions** tab
2. Select **Deploy** workflow
3. Click **Run workflow**
4. Enter `sha-{COMMIT_SHA}` of known-good version (required)
5. Click **Run workflow**

---

## 14. Notes on GitHub Actions Expression Syntax

GitHub Actions `if` conditions use JavaScript expression syntax with specific operators:
- All `if` conditions must be wrapped in `${{ }}`
- `&&` for AND, `||` for OR (both are valid within the expression)
- String comparisons use `==` operator

Correct syntax examples:
- `if: ${{ github.ref == 'refs/heads/main' || github.event_name == 'workflow_dispatch' }}`
- `if: ${{ github.ref == 'refs/heads/main' && github.event_name != 'workflow_dispatch' }}`
- `if: ${{ github.event_name == 'workflow_dispatch' && github.ref == 'refs/heads/main' }}`

---

## 15. Architecture Constraints Summary

### 15.1 Build vs Pull Resolution

**Problem:** The base `compose.yaml` defines `web` and `bot` services with `build:` directive. When deploying to VPS, `docker compose up -d` would attempt to build locally instead of pulling pre-built images from GHCR.

**Solution:** Override `image:` in `compose.prod.yaml` for `web` and `bot` services. When an `image:` key is present in an override file, Docker Compose uses it and ignores the `build:` directive - this ensures the workflow pulls from GHCR.

### 15.2 Deploy Workflow Sequence

The correct sequence ensures image freshness and database consistency:

```
1. docker compose pull     → Fetch latest images from GHCR
2. pg_dump backup          → Backup database before migrations
3. docker compose run migrate → Run migrations with pulled image
4. docker compose up -d    → Start containers (uses pulled images)
5. docker image prune -f   → Clean up old images
```

This sequence prevents:
- Stale image deployment
- Build vs pull conflicts
- Database schema drift
- Data loss on migration failure
- Disk bloat from old images

### 15.3 Secrets Strategy

**Design decision:** Application secrets live ONLY in `.env.docker` on the VPS. GitHub Secrets contain ONLY server-access credentials (SERVER_HOST, SERVER_USER, SERVER_SSH_KEY, SERVER_PORT). This eliminates secret drift between two locations.

### 15.4 Compose File Naming

The plan uses modern Docker Compose V2 naming (`compose.yaml` instead of `docker-compose.yml`). The existing project files use the old naming — rename during implementation as part of Stage B.