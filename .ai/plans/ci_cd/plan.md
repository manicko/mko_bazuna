# CI/CD Implementation Plan for Mko Bazuna

**Date:** 2026-07-27  
**Based on:** `.ai/plans/ci_cd/research.md`  
**Strategy:** Docker-based manual deploy with GitHub Actions

---

## 1. Overview

Implementation of Docker-based CI/CD pipeline with manual deployment to VPS via GitHub Actions. Architecture:
- **CI:** Parallel lint → typecheck → test jobs on push/PR
- **CD:** Manual workflow dispatch → build → push → deploy
- **Registry:** GitHub Container Registry (GHCR)
- **Target:** Single VPS (4 CPU, 8 GB RAM), no staging environment

---

## 2. Pre-implemented Components

| Component | Status | Notes |
|-----------|--------|-------|
| Non-root user (uid 1000) | ✅ Already in Dockerfile | See docker/Dockerfile |
| Coverage upload | ✅ Already configured | CI workflow |
| PostgreSQL 18 service | ✅ Already configured | CI workflow |
| Build cache (registry) | ✅ Partial | Currently uses registry cache; migrate to GHA cache |

---

## 3. Implementation Stages

### Stage A: Preparation & Setup (Priority: HIGH)

| ID | Task | Priority | Effort | Dependencies | Risks |
|----|------|----------|--------|--------------|-------|
| A1 | Create `production` environment in GitHub repository settings | HIGH | trivial | None | Deployment could run without proper approval |
| A2 | Add GitHub Secrets: SERVER_HOST, SERVER_USER, SERVER_SSH_KEY, SERVER_PORT | HIGH | trivial | A1 | Secret exposure if not properly configured |
| A3 | Add GitHub Secrets: DJANGO_SECRET_KEY, BOT_TOKEN, ADMIN_PASSWORD, POSTGRES_PASSWORD | HIGH | trivial | A1 | Secret exposure if not properly configured |
| A4 | Prepare VPS directory structure (`/opt/mko_bazuna/{backups,certs,media}`) | HIGH | small | None | Security misconfiguration, permission issues |
| A5 | Create deploy user on VPS with Docker group membership | HIGH | small | A4 | Security misconfiguration, permission issues |
| A6 | Clone repository to VPS and create `.env.docker` file | HIGH | small | A5 | Secret exposure if copied incorrectly |
| A7 | Set file permissions on VPS (600 for .env.docker, deploy ownership) | MEDIUM | trivial | A6 | Secret exposure in logs |

---

### Stage B: CI Pipeline (Enhancement)

| ID | Task | Priority | Effort | Dependencies | Risks |
|----|------|----------|--------|--------------|-------|
| B1 | Add concurrency control to existing `.github/workflows/ci.yml` | MEDIUM | trivial | None | Resource waste on multiple concurrent builds |
| B2 | Rename/move `ci.yml` to `ci-cd.yml` and add workflow_dispatch trigger | HIGH | small | B1 | Broken workflow if not done carefully |
| B3 | Add path filters to skip CI for docs-only changes | LOW | small | B1 | CI might run unnecessarily, consuming minutes |
| B4 | Verify existing PostgreSQL 18 service configuration | HIGH | trivial | None | — |
| B5 | Verify coverage artifact upload configuration | LOW | trivial | None | — |

---

### Stage C: CD Pipeline (Extend existing)

| ID | Task | Priority | Effort | Dependencies | Risks |
|----|------|----------|--------|--------------|-------|
| C1 | Add GHCR authentication to existing build job | HIGH | small | B1 | Authentication failures |
| C2 | Update build job to push images with SHA-based tags | HIGH | small | C1 | Failed image pushes |
| C3 | Add GHA layer caching to build step | MEDIUM | small | C2 | Slow builds without caching |
| C4 | Implement deploy job with SSH-based Docker Compose orchestration | HIGH | medium | A2, A3, C2 | Production outage, failed rollbacks |
| C5 | Add deploy health check with retry loop (30 attempts, 5s delay) | HIGH | trivial | C4 | Failed deployments going unnoticed |
| C6 | Add workflow_dispatch inputs for image tag selection (rollback support) | MEDIUM | small | C2 | Wrong image deployed |

---

### Stage D: Security & Hardening

| ID | Task | Priority | Effort | Dependencies | Risks |
|----|------|----------|--------|--------------|-------|
| D1 | Add Trivy security scan job (CRITICAL/HIGH severity, non-blocking) | MEDIUM | small | C2 | Unpatched vulnerabilities in production |
| D2 | Configure Trivy SARIF upload to GitHub Security tab | MEDIUM | trivial | D1 | No security visibility |
| D3 | Add dependency audit (pip-audit) for Python packages | MEDIUM | small | None | Outdated/vulnerable packages |
| D4 | Document rollback procedure in `docs/ops/deployment.md` | MEDIUM | small | C4 | Undocumented recovery procedures |

---

## 4. Execution Order (Topological Sort)

```
A1 → A2, A3 → A4, A5, A6, A7
              ↓
B1 → B2 → B3, B4, B5
          ↓
C1 → C2 → C3 → C4, C5, C6
          ↓
D1 → D2
D3 → (after C2)
D4 → (after C4)
```

**Critical Path:** A1 → A2/A3 → B1 → C1 → C4 (sequential, ~5-7 days calendar time with parallel execution)

---

## 5. Task Graph (Dependency DAG)

```
┌─────────────┐
│     A1      │ (GitHub Environment)
└──────┬──────┘
       │
       ▼
┌─────────────┐
│ A2, A3      │ (GitHub Secrets)
└──────┬──────┘
       │
       ▼
┌─────────────┐
│ A4, A5, A6 │ (VPS Setup)
└──────┬──────┘
       │
       ▼
┌─────────────────────────────┐
│  Stage B: CI Enhancements   │
├────────┬────────┬──────────┤
│   B1   │   B2   │ B3, B4, B5│
│Concurrency│ Rename  │ Verify   │
└────────┴────────┴──────────┘
                      │
                      ▼
┌──────────────────────────────────────────┐
│        Stage C: CD Pipeline               │
├────────┬────────┬──────────┬────────────┤
│   C1   │   C2   │    C3    │ C4, C5, C6 │
│  GHCR  │ Push   │ Caching  │ Deploy     │
└────────┴────────┴──────────┴────────────┘
                      │
                      ▼
┌─────────────────────────────┐
│ Stage D: Security Layer     │
├────────┬────────┬──────────┤
│   D1   │   D2   │   D3     │
│ Trivy  │ SARIF  │ Audit    │
└────────┴────────┴──────────┘
         │
         ▼
┌─────────────┐
│     D4      │
│  Documentation│
└─────────────┘
```

---

## 6. Risk Assessment & Mitigation

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| GitHub Actions time limit exceeded | MEDIUM | HIGH | Implement path filters; optimize test duration; consider public repo |
| SSH key compromise | LOW | HIGH | Use ED25519 keys; rotate quarterly; restrict deploy user permissions |
| Trivy scan blocks deploy | LOW | MEDIUM | Run as non-blocking job; use `ignore-unfixed: true` |
| Database migration failure | MEDIUM | HIGH | Advisory lock prevents concurrent runs; test migrations in CI; backup before deploy |
| Rollback procedure failure | LOW | MEDIUM | Document; test with known-good SHA tag |
| Secret leak in logs | LOW | CRITICAL | Mask secrets with `::add-mask::`; use GitHub Environments |

---

## 7. Verification Steps

After implementation:

1. **CI Verification:**
   - Push to `develop` branch → verify CI runs (no build/deploy)
   - Push to `main` branch → verify all jobs execute in parallel
   - Open PR → verify CI runs with same behavior as push

2. **CD Verification:**
   - Run workflow dispatch with empty tag → latest `main` image deploys
   - Verify health check passes after deployment (30 attempts × 5s)
   - Verify containers running: `docker compose ps` on VPS

3. **Rollback Verification:**
   - Trigger deploy with specific SHA tag
   - Verify old version is pulled and running

---

## 8. Files to Create/Modify

| Action | Path |
|--------|------|
| Rename & Modify | `.github/workflows/ci.yml` → `ci-cd.yml` (add workflow_dispatch, concurrency, CD jobs) |
| Create | `docs/ops/deployment.md` (rollback procedure, deployment guide) |

### 8.1 Deployment Commands Reference

The deploy job will execute on VPS:
```bash
cd /opt/mko_bazuna

# Pull latest images
docker compose -f docker-compose.yml -f docker-compose.prod.yml pull

# Stop old containers gracefully
docker compose -f docker-compose.yml -f docker-compose.prod.yml stop

# Remove old containers
docker compose -f docker-compose.yml -f docker-compose.prod.yml rm -f

# Start new containers
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d

# Clean up old images
docker image prune -f
```

### 8.2 Complete Workflow YAML (from research.md)

```yaml
name: CI/CD

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main, develop]
  workflow_dispatch:
    inputs:
      image_tag:
        description: 'Image tag to deploy (leave empty for main)'
        required: false
        default: ''

concurrency:
  group: ${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: true

env:
  REGISTRY: ghcr.io
  IMAGE_NAME: ${{ github.repository }}

jobs:
  # ============================================
  # LINT & TYPECHECK (parallel, fast-fail)
  # ============================================
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

  # ============================================
  # TEST (with PostgreSQL)
  # ============================================
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

  # ============================================
  # BUILD & PUSH (deploy only on main)
  # ============================================
  build:
    needs: [lint, typecheck, test]
    if: github.ref == 'refs/heads/main' || github.event_name == 'workflow_dispatch'
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
            type=ref,event=branch
            type=raw,value=latest,enable=${{ github.ref == 'refs/heads/main' }}
      - name: Build and push
        uses: docker/build-push-action@v6
        with:
          context: .
          push: true
          tags: ${{ inputs.image_tag != '' && format('{0}/{1}:{2}', env.REGISTRY, env.IMAGE_NAME, inputs.image_tag) || steps.meta.outputs.tags }}
          cache-from: type=gha
          cache-to: type=gha,mode=max

  # ============================================
  # SECURITY SCAN (optional, non-blocking)
  # ============================================
  security-scan:
    needs: build
    if: github.ref == 'refs/heads/main' && github.event_name != 'workflow_dispatch'
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

  # ============================================
  # DEPLOY (manual trigger only)
  # ============================================
  deploy:
    needs: [build]
    if: github.event_name == 'workflow_dispatch' && github.ref == 'refs/heads/main'
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
            cd /opt/mko_bazuna
            echo "Pulling latest images..."
            docker compose -f docker-compose.yml -f docker-compose.prod.yml pull
            echo "Stopping old containers..."
            docker compose -f docker-compose.yml -f docker-compose.prod.yml stop
            echo "Removing old containers..."
            docker compose -f docker-compose.yml -f docker-compose.prod.yml rm -f
            echo "Starting new containers..."
            docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
            docker image prune -f
            echo "Deployment complete"
      - name: Health check
        run: |
          sleep 10
          for i in {1..30}; do
            STATUS=$(curl -s -o /dev/null -w "%{http_code}" http://${{ secrets.SERVER_HOST }}/health/ || echo "000")
            if [ "$STATUS" = "200" ]; then
              echo "Health check passed"
              exit 0
            fi
            echo "Waiting for service (attempt $i)..."
            sleep 5
          done
          echo "Health check failed - check server logs"
          exit 1
```

### 8.3 VPS Preparation Script

```bash
# On VPS
mkdir -p /opt/mko_bazuna/{backups,certs,media}
cd /opt/mko_bazuna

# Create deploy user
useradd -m -s /bin/bash deploy
usermod -aG docker deploy

# Clone repository
git clone https://github.com/manicko/mko_bazuna .

# Create production environment file
cat > .env.docker << 'EOF'
DJANGO_SECRET_KEY=<from GitHub Secrets>
DEBUG=False
ALLOWED_HOSTS=localhost,your-domain.com

POSTGRES_USER=bazuna_user
POSTGRES_DB=bazuna_db
POSTGRES_PASSWORD=<from GitHub Secrets>

BOT_TOKEN=<from GitHub Secrets>
BOT_USERNAME=bazuna_bot
ADMIN_USERNAME=admin
ADMIN_PASSWORD=<from GitHub Secrets>
ADMIN_TELEGRAM_ID=<telegram-id>

TLS_CERT_PATH=/etc/nginx/certs
EOF

# Set permissions
chown -R deploy:deploy /opt/mko_bazuna
chmod 600 /opt/mko_bazuna/.env.docker

# Initial deployment
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

### 8.4 Branch Strategy

| Branch | Behavior |
|--------|----------|
| `main` | CI runs on push/PR; CD builds image; deploy via workflow dispatch |
| `develop` | CI only (tests, lint) - no image build |

### 8.5 Cost Estimation (GitHub Free Tier)

Estimated monthly usage for active development:

| Job | Duration (min) | Runs/day | Monthly (min) |
|-----|----------------|----------|---------------|
| Lint | 1 | 10 | 300 |
| Typecheck | 1 | 10 | 300 |
| Test | 3-5 | 10 | 1,500 |
| Build | 2-3 | 2 | 60 |
| **Total** | | | **~2,160 min** |

**Note:** For private repos, 2,000 minutes is the free limit. Consider making repo public or optimizing test duration.

---

## 9. Effort Summary

| Effort | Tasks Count |
|--------|-------------|
| trivial | A1, A2, A3, A7, B1, B4, B5, C5, C6, D2 |
| small | A4, A5, A6, B2, B3, C1, C2, C3, D1, D3, D4 |
| medium | C4 |

**Total: 22 tasks** — Estimated effort: **large** (~5-7 days with validation)

---

## 10. Estimated Timeline

| Stage | Tasks | Calendar Time |
|-------|-------|-------------|
| A: Preparation | A1-A7 | 1 day |
| B: CI Enhancement | B1-B5 | 1 day |
| C: CD Extension | C1-C6 | 2-3 days |
| D: Security | D1-D4 | 1 day |
| **Total** | **22 tasks** | **5-7 days** (with testing/validation) |

---

## 11. Rollback Procedure Reference

1. Go to **Actions** tab
2. Select **CI/CD** workflow
3. Click **Run workflow**
4. Enter `sha-{COMMIT_SHA}` of known-good version
5. Click **Run workflow**

---

## 12. Health Check Endpoint

The project includes health check at `/health/`:

```python
# apps/core/views.py
def health(request):
    return JsonResponse({"status": "ok"})
```