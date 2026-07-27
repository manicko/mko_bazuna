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
| Build cache | ⚠️ Optional | Currently uses registry cache; GHA cache is optional optimization |

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
| B3 | Add path filters to skip CI for docs-only changes | HIGH | small | B1 | CI might run unnecessarily, consuming minutes |
| B4 | Verify existing PostgreSQL 18 service configuration (no changes needed) | HIGH | trivial | None | — |
| B5 | Verify coverage artifact upload configuration | LOW | trivial | None | — |
| B6 | Integrate rollback documentation into `docs/ops/docker-deployment.md` | MEDIUM | small | None | Duplicate documentation if not merged |

---

### Stage C: CD Pipeline (Extend existing)

| ID | Task | Priority | Effort | Dependencies | Risks |
|----|------|----------|--------|--------------|-------|
| C1 | Add GHCR authentication to existing build job | HIGH | small | B1 | Authentication failures |
| C2 | Update build job to push images with SHA-based tags | HIGH | small | C1 | Failed image pushes |
| C3 | Remove ARM64 from platforms (keep only linux/amd64) | HIGH | trivial | C2 | None |
| C4 | Implement deploy job with SSH-based Docker Compose orchestration | HIGH | medium | A2, A3, C2 | Production outage, failed rollbacks |
| C5 | Add pre-deploy migrations via `docker compose run --rm migrate` | HIGH | small | C4 | Database drift on deploy |
| C6 | Add deploy health check with automatic rollback on failure | HIGH | medium | C4, C5 | Failed deployments left in broken state |
| C7 | Add workflow_dispatch inputs for image tag selection (rollback support) | MEDIUM | small | C2 | Wrong image deployed |

---

### Stage D: Security & Hardening

| ID | Task | Priority | Effort | Dependencies | Risks |
|----|------|----------|--------|--------------|-------|
| D1 | Add Trivy security scan job (CRITICAL/HIGH severity, non-blocking) | MEDIUM | small | C2 | Unpatched vulnerabilities in production |
| D2 | Configure Trivy SARIF upload to GitHub Security tab | MEDIUM | trivial | D1 | No security visibility |
| D3 | Add dependency audit (pip-audit) for Python packages | MEDIUM | small | None | Outdated/vulnerable packages |

---

## 4. Execution Order (Topological Sort)

```
A1 → A2, A3 → A4, A5, A6, A7
              ↓
B1 → B2 → B3, B4, B5 → B6 (docs integration)
           ↓
C1 → C2 → C3, C4, C5, C6, C7
           ↓
D1 → D2
D3 → (after C2)
```

**Critical Path:** A1 → A2/A3 → B1 → C1 → C4 → C5 → C6 (sequential, ~5-7 days calendar time with parallel execution)

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
│  Stage B: CI Enhancements    │
├────────┬────────┬──────────┤
│   B1   │   B2   │ B3, B4, B5, B6│
│Concurrency│ Rename  │ Verify/Docs │
└────────┴────────┴──────────┘
                   │
                   ▼
┌──────────────────────────────────────────┐
│        Stage C: CD Pipeline               │
├────────┬────────┬──────────┬────────────┤
│   C1   │   C2   │    C3    │ C4, C5, C6 │
│  GHCR  │ Push   │ Multi-arch│ Deploy & Rollback │
└────────┴────────┴──────────┴────────────┘
                   │
                   ▼
┌─────────────────────────────┐
│ Stage D: Security Layer     │
├────────┬────────┬──────────┤
│   D1   │   D2   │   D3     │
│ Trivy  │ SARIF  │ Audit    │
└────────┴────────┴──────────┘
```

---

## 6. Risk Assessment & Mitigation

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| GitHub Actions time limit exceeded | MEDIUM | HIGH | Implement path filters; optimize test duration; consider public repo for unlimited minutes |
| SSH key compromise | LOW | HIGH | Use ED25519 keys; rotate quarterly; restrict deploy user permissions |
| Trivy scan blocks deploy | LOW | MEDIUM | Run as non-blocking job; use `ignore-unfixed: true` |
| Database migration failure | MEDIUM | HIGH | Advisory lock prevents concurrent runs; test migrations in CI; backup before deploy |
| Rollback procedure failure | LOW | MEDIUM | Automated rollback on health check failure; test with known-good SHA tag |
| Secret leak in logs | LOW | CRITICAL | Mask `SERVER_HOST` with `::add-mask::`; use GitHub Environments |

### GitHub Free Tier Optimization Recommendations

1. **Path filters (B3):** Add `paths-ignore` for documentation-only changes to reduce CI runs
2. **Public repository:** Consider making the repo public to get unlimited GitHub Actions minutes
3. **GHA caching (C3):** Make optional - can be skipped if build times are acceptable

---

## 7. Verification Steps

After implementation:

1. **CI Verification:**
   - Push to `develop` branch → verify CI runs (no build/deploy)
   - Push to `main` branch → verify all jobs execute in parallel
   - Open PR → verify CI runs with same behavior as push
   - Modify only documentation → verify CI is skipped

2. **CD Verification:**
   - Run workflow dispatch with empty tag → latest `main` image deploys
   - Verify pre-deploy migrations execute before container start
   - Verify health check passes after deployment (30 attempts × 5s)
   - Verify containers running: `docker compose ps` on VPS

3. **Rollback Verification:**
   - Trigger deploy with specific SHA tag
   - Verify old version is pulled and running
   - Test automatic rollback by deploying a broken version

---

## 8. Files to Create/Modify

| Action | Path | Notes |
|--------|------|-------|
| Create | `.github/workflows/ci-cd.yml` | New unified workflow file (rename from ci.yml) |
| Modify | `docker/nginx/nginx.conf` | Add `/health/` location block |
| Modify | `docs/ops/docker-deployment.md` | Merge rollback procedure into existing deployment docs |

### 8.1 Deployment Commands Reference

The deploy job will execute on VPS:

```bash
cd /opt/mko_bazuna

# Pull latest images
docker compose -f docker-compose.yml -f docker-compose.prod.yml pull

# Run pre-deploy migrations (critical: must run before container restart)
docker compose -f docker-compose.yml -f docker-compose.prod.yml run --rm migrate

# Stop old containers gracefully
docker compose -f docker-compose.yml -f docker-compose.prod.yml stop

# Remove old containers
docker compose -f docker-compose.yml -f docker-compose.prod.yml rm -f

# Start new containers
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d

# Clean up old images
docker image prune -f

echo "Deployment complete"
```

### 8.2 Complete Workflow YAML

```yaml
name: CI/CD

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
          platforms: linux/amd64
          tags: ${{ steps.meta.outputs.tags }}
          cache-from: type=gha
          cache-to: type=gha,mode=max

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

  deploy:
    needs: [build]
    if: github.event_name == 'workflow_dispatch' && github.ref == 'refs/heads/main'
    runs-on: ubuntu-latest
    environment: production

    steps:
      - name: Mask secrets
        run: echo "::add-mask::${{ secrets.SERVER_HOST }}"

      - name: Deploy to VPS
        uses: appleboy/ssh-action@v1
        with:
          host: ${{ secrets.SERVER_HOST }}
          username: ${{ secrets.SERVER_USER }}
          key: ${{ secrets.SERVER_SSH_KEY }}
          port: ${{ secrets.SERVER_PORT }}
          script: |
            set -e
            DEPLOY_DIR="/opt/mko_bazuna"
            cd "$DEPLOY_DIR"

            echo "Pulling latest images..."
            docker compose -f docker-compose.yml -f docker-compose.prod.yml pull

            echo "Running pre-deploy migrations..."
            docker compose -f docker-compose.yml -f docker-compose.prod.yml run --rm migrate || { echo "Migration failed"; exit 1; }

            echo "Stopping old containers..."
            docker compose -f docker-compose.yml -f docker-compose.prod.yml stop || true

            echo "Removing old containers..."
            docker compose -f docker-compose.yml -f docker-compose.prod.yml rm -f || true

            echo "Starting new containers..."
            docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d

            echo "Cleaning old images..."
            docker image prune -f

            echo "Deployment complete"

      - name: Health check with automatic rollback
        run: |
          set -e
          echo "Waiting for services to stabilize..."
          sleep 10

          for i in {1..30}; do
            STATUS=$(curl -s -o /dev/null -w "%{http_code}" "https://${{ secrets.SERVER_HOST }}/health/" || echo "000")
            if [ "$STATUS" = "200" ]; then
              echo "Health check passed"
              exit 0
            fi
            echo "Waiting for service (attempt $i)..."
            sleep 5
          done

          echo "Health check failed - initiating automatic rollback..."
          # Rollback to previous known-good image
          ssh -o StrictHostKeyChecking=no ${{ secrets.SERVER_USER }}@${{ secrets.SERVER_HOST }} -p ${{ secrets.SERVER_PORT }} "
            cd /opt/mko_bazuna
            echo 'Rolling back to previous image...'
            docker compose -f docker-compose.yml -f docker-compose.prod.yml down
            docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --scale web=0
            docker image prune -f
          " || echo "Rollback attempt completed - check VPS manually"
          exit 1
```

### 8.3 Nginx Configuration Update

Add to `docker/nginx/nginx.conf` in the HTTPS server block (before the closing brace):

```nginx
        # Health check endpoint (no rate limiting, no auth)
        location /health/ {
            proxy_pass http://web:8000;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
        }
```

### 8.4 VPS Preparation Script

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

# Run initial migrations
docker compose -f docker-compose.yml -f docker-compose.prod.yml run --rm migrate
```

### 8.5 Branch Strategy

| Branch | Behavior |
|--------|----------|
| `main` | CI runs on push/PR; CD builds image; deploy via workflow dispatch |
| `develop` | CI only (tests, lint) - no image build |

### 8.6 Cost Estimation (GitHub Free Tier)

Estimated monthly usage for active development:

| Job | Duration (min) | Runs/day | Monthly (min) |
|-----|----------------|----------|---------------|
| Lint | 1 | ~10 | ~300 |
| Typecheck | 1 | ~10 | ~300 |
| Test | 3-5 | ~10 | ~1,500 |
| Build (multi-arch) | 2-3 | ~2 | ~60-90 |
| **Total** | | | **~2,160-2,460 min** |

**Note:** For private repos, 2,000 minutes is the free limit. Consider:
- Making repo public (unlimited minutes)
- Using path filters (B3) to skip CI for docs-only changes
- GHA caching (C3) to reduce build times

---

## 9. Effort Summary

| Effort | Tasks Count |
|--------|-------------|
| trivial | A1, A2, A3, A7, B1, B4, B5, C3, D2 |
| small | A4, A5, A6, B2, B3, B6, C1, C2, C5, C7, D1, D3 |
| medium | C4, C6 |

**Total: 19 tasks** — Estimated effort: **large** (~5-7 days with validation)

---

## 10. Estimated Timeline

| Stage | Tasks | Calendar Time |
|-------|-------|-------------|
| A: Preparation | A1-A7 | 1 day |
| B: CI Enhancement | B1-B6 | 1 day |
| C: CD Extension | C1-C7 | 2-3 days |
| D: Security | D1-D3 | 1 day |
| **Total** | **19 tasks** | **5-7 days** (with testing/validation) |

---

## 11. Rollback Procedure

### Automatic Rollback

The deploy job includes automatic rollback on health check failure. If health check fails after 30 attempts:
- The workflow automatically rolls back to the previously running image
- This happens transparently without manual intervention

### Manual Rollback

For manual rollback procedure, see `docs/ops/docker-deployment.md`:

1. Go to **Actions** tab
2. Select **CI/CD** workflow
3. Click **Run workflow**
4. Enter `sha-{COMMIT_SHA}` of known-good version
5. Click **Run workflow**

---

## 12. Health Check Endpoint

The project includes health check at `/health/`. The view is implemented in `apps/core/views.py`:

```python
# apps/core/views.py
def health(request):
    return JsonResponse({"status": "ok"})
```

**Required in nginx.conf:** Add explicit `/health/` location to proxy to web service without rate limiting.

**Security masking:** `SERVER_HOST` must be masked in GitHub Actions using `::add-mask::` to prevent log leakage.