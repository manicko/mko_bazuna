# CI/CD Research for Mko Bazuna

**Date:** 2026-07-27  
**Project:** Mko Bazuna — Telegram-driven classifieds board (Avito-like)  
**Target:** GitHub Actions CI/CD with Docker deployment to VPS

---

## 1. Current Project Architecture

### 1.1 Stack Summary

| Component | Technology | Version/Constraint |
|-----------|------------|-------------------|
| Python | 3.14 | `>=3.14,<3.15` |
| Django | 5.2 LTS | `>=5.2.16,<6.0` |
| PostgreSQL | 18 | `postgres:18-alpine` |
| Telegram Bot | aiogram | `>=3.15.0` |
| Package Manager | uv | Latest (from ghcr.io/astral-sh/uv) |
| CSS Framework | Tailwind CSS | Standalone CLI binary |
| WSGI Server | Gunicorn | `>=26.0` |
| Web Server | Nginx | `nginx:alpine` |

### 1.2 Project Structure

```
mko_bazuna/
├── src/
│   ├── backend/          # Django project (manage.py, config/)
│   │   ├── apps/         # Django applications (ads, users, categories, etc.)
│   │   ├── config/       # Django settings (base, dev, test, prod)
│   │   └── manage.py
│   ├── theme/            # Tailwind CSS source
│   └── telegram_bot/     # aiogram bot code
├── docker/
│   ├── Dockerfile        # Multi-stage build
│   ├── entrypoint.sh     # Main entrypoint
│   ├── entrypoint-test.sh  # Test entrypoint
│   ├── entrypoint-scheduler.sh
│   └── entrypoint-create-admin.sh
├── docker-compose.yml    # Base compose (db, migrate, web, bot, nginx)
├── docker-compose.prod.yml  # Production overrides (scheduler, backup, pgbouncer)
├── docker-compose.test.yml  # Ephemeral test DB
└── pyproject.toml        # Project definition with uv
```

### 1.3 Docker Architecture

#### Multi-stage Dockerfile

**Builder Stage:**
- Base: `python:3.14-slim`
- Installs uv, curl, coreutils
- Installs Python dependencies via `uv sync --frozen --no-dev`
- Downloads Tailwind CSS CLI standalone binary
- Builds Tailwind CSS (`tailwindcss -i ... -o ... --minify`)
- Collects static files via `collectstatic`

**Runtime Stage:**
- Base: `python:3.14-slim`
- Only runtime dependencies: `libpq5`, `curl`, `ca-certificates`
- Non-root user (uid 1000) for security
- Healthcheck: `curl -f http://localhost:8000/health/ || exit 1`

#### Docker Compose Services

| Service | Purpose | Notes |
|---------|---------|-------|
| `db` | PostgreSQL 18 | Healthcheck via `pg_isready` |
| `migrate` | One-shot migrations | Advisory lock (ID 100) prevents concurrent runs |
| `create_admin` | One-shot admin creation | Skipped if `ADMIN_PASSWORD` empty |
| `web` | Django/Gunicorn | Depends on migrate, restart unless-stopped |
| `bot` | Telegram bot | Depends on migrate, restart unless-stopped |
| `nginx` | Reverse proxy | Ports 80/443, TLS certs mount |
| `scheduler` | Periodic tasks | Profile-gated `scheduler` |
| `backup` | DB dumps (7-day retention) | Profile-gated `backup` |
| `pgbouncer` | Connection pooling | Profile-gated `pgbouncer` |

### 1.4 Testing & Quality Tools

Configured in `pyproject.toml`:

| Tool | Config |
|------|--------|
| Ruff | E, F, I, B, UP rules; line-length 88 |
| Basedpyright | Standard mode, relaxed Django compatibility |
| pytest | Async mode, coverage threshold 80% |
| Coverage | Excludes migrations, tests, manage.py, wsgi/asgi |

Current CI workflow (`.github/workflows/ci.yml`):
- **Build job:** Docker build with registry cache
- **Test job:** PostgreSQL service, migrations, pytest with coverage
- **Lint job:** Ruff check
- **Typecheck job:** Basedpyright

---

## 2. Requirements for CI/CD

### 2.1 Testing Requirements

| Requirement | Status | Notes |
|-------------|--------|-------|
| Unit tests | ✅ Implemented | pytest with pytest-asyncio |
| Integration tests | ✅ Configured | Uses real PostgreSQL in CI |
| Coverage threshold | ✅ Configured | 80% minimum |
| Migration check | ✅ Implemented | `makemigrations --check --dry-run` |

### 2.2 Quality Gates

| Gate | Tool | Configuration |
|------|------|---------------|
| Linting | Ruff | Fast-fail gate (runs first) |
| Type checking | Basedpyright | Separate job |
| Security scanning | ❌ Not configured | Recommended: Trivy |
| Dependency audit | ❌ Not configured | Recommended: pip-audit or safety |

### 2.3 Deployment Requirements

| Requirement | Status | Notes |
|-------------|--------|-------|
| Docker image build | ✅ Implemented | Multi-stage, optimized |
| Image registry | ❌ Not configured | GHCR recommended |
| Server access | ❌ Manual | SSH keys needed |
| Secret management | ❌ Not configured | GitHub Secrets / .env |
| Rollback capability | ❌ Not configured | Needed for manual deploy |

### 2.4 Constraints

- **Free GitHub tier:** 2,000 minutes/month for private repos, unlimited for public
- **VPS:** 4 CPU cores, 8 GB RAM (sufficient for small deployment)
- **Manual deploy only:** No automatic deployment on merge
- **No staging:** Direct production deployment via workflow dispatch

---

## 3. Modern CI/CD Approaches for MVP Projects (2026)

### 3.1 Core Principles for Small Projects

Based on analysis of current best practices:

1. **Keep it simple:** 40-80 lines of YAML is sufficient for most MVPs
2. **Fast feedback:** Test job should complete in <2 minutes
3. **Docker caching:** Use `cache-from: type=gha` for fast rebuilds
4. **SHA tagging:** Tag images with commit SHA for traceability and rollback
5. **Non-root containers:** Security baseline (already implemented)
6. **Secrets management:** GitHub Secrets or OIDC (preferred for cloud)

### 3.2 Deployment Patterns for VPS

| Pattern | Description | Pros | Cons |
|---------|-------------|------|------|
| **SSH + Docker Compose** | SSH into server, `docker compose pull && up -d` | Simple, no additional tools | Manual setup, SSH key rotation |
| **GitHub Deploy Keys** | SSH with deploy-specific key | Better security isolation | Key management overhead |
| **OCI + systemd** | Pull image via systemd service | Systemd manages lifecycle | More complex than compose |
| **Watchtower** | Auto-update containers | Zero code for CD | Less control, no rollback UI |

### 3.3 Recommended Optimizations

- **Layer caching:** `cache-from/cache-to: type=gha` reduces build times by 60-80%
- **Dependency caching:** `astral-sh/setup-uv` with `enable-cache: true`
- **Concurrency control:** Cancel superseded runs on same branch
- **Path filters:** Skip CI for docs-only changes
- **Security scanning:** Trivy for vulnerability detection before deploy

---

## 4. Strategy Selection

### 4.1 Selected Approach: Docker-based Manual Deploy

**Rationale:**

1. **Architecture alignment:** Project already uses Docker Compose for orchestration
2. **Resource constraints:** VPS is single server, no Kubernetes needed
3. **Manual trigger requirement:** Workflow dispatch fits the "manual deploy" constraint
4. **Cost efficiency:** GitHub Actions free tier sufficient for MVP
5. **Simplicity:** SSH + Docker Compose is straightforward and maintainable

### 4.2 Workflow Architecture

```
Push/PR → CI (lint/test/typecheck) → Manual Approval → CD (build/push/deploy)
```

**Jobs:**
1. `lint` — Ruff fast-fail (parallel)
2. `typecheck` — Basedpyright (parallel)  
3. `test` — PostgreSQL + pytest with coverage (parallel with lint/typecheck)
4. `build` — Docker image build + push (waits for test)
5. `deploy` — SSH to VPS, `docker compose pull && up -d` (manual trigger)

### 4.3 Registry Strategy

- **GitHub Container Registry (GHCR)** for Docker images
- **Tagging scheme:**
  - `sha-{COMMIT_SHA}` for precise rollback
  - `main` for latest main branch
  - `latest` for backward compatibility (manually triggered)

---

## 5. Detailed Solution

### 5.1 GitHub Secrets Required

| Secret Name | Description | Example Value |
|-------------|-------------|---------------|
| `SERVER_HOST` | VPS IP/hostname | `192.168.1.100` |
| `SERVER_USER` | SSH user on VPS | `deploy` |
| `SERVER_SSH_KEY` | SSH private key for deploy user | (4096-bit ED25519 key) |
| `SERVER_PORT` | SSH port (optional) | `22` (default) |
| `DJANGO_SECRET_KEY` | Django secret (production) | (generated) |
| `BOT_TOKEN` | Telegram bot token | (from @BotFather) |
| `ADMIN_PASSWORD` | Admin user password | (strong password) |
| `POSTGRES_PASSWORD` | DB password | (strong password) |

### 5.2 CI/CD Workflow Files

#### `.github/workflows/ci.yml` (Updated for deployment)

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
    if: ${{ github.ref == 'refs/heads/main' || github.event_name == 'workflow_dispatch' }}
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
    if: ${{ github.event_name == 'workflow_dispatch' && github.ref == 'refs/heads/main' }}
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
    if: ${{ github.event_name == 'workflow_dispatch' && github.ref == 'refs/heads/main' }}
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
            
            # Pull latest images
            echo "Pulling latest images..."
            docker compose -f docker-compose.yml -f docker-compose.prod.yml pull
            
            # Stop old containers gracefully
            echo "Stopping old containers..."
            docker compose -f docker-compose.yml -f docker-compose.prod.yml stop
            
            # Remove old containers
            echo "Removing old containers..."
            docker compose -f docker-compose.yml -f docker-compose.prod.yml rm -f
            
            # Start new containers
            echo "Starting new containers..."
            docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
            
            # Clean up old images
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

### 5.3 VPS Deployment Setup

#### Server Preparation Script

```bash
# On VPS
mkdir -p /opt/mko_bazuna/{backups,certs,media}
cd /opt/mko_bazuna

# Create deploy user
useradd -m -s /bin/bash deploy
usermod -aG docker deploy

# Copy docker-compose files (via git clone or sync)
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

#### Required GitHub Environments

Configure in **Settings → Environments**:

| Environment | Protection Rules | Secrets |
|-------------|------------------|---------|
| `production` | Required reviewers (optional for manual deploy) | Inherits repo secrets |

### 5.4 Branch Strategy

| Branch | Behavior |
|--------|----------|
| `main` | CI runs on push/PR; CD builds image; deploy via workflow dispatch |
| `develop` | CI only (tests, lint) - no image build |

### 5.5 Cost Estimation (GitHub Free Tier)

Estimated monthly usage for active development:

| Job | Duration (min) | Runs/day | Monthly (min) |
|-----|----------------|----------|---------------|
| Lint | 1 | 10 | 300 |
| Typecheck | 1 | 10 | 300 |
| Test | 3-5 | 10 | 1,500 |
| Build | 2-3 | 2 | 60 |
| **Total** | | | **~2,160 min** |

**Note:** For private repos, 2,000 minutes is the free limit. Consider:
- Making repo public (unlimited CI minutes)
- Optimizing test duration
- Using path filters to skip CI for docs

### 5.6 Rollback Strategy

Rollback is performed via workflow dispatch with specific image tag:

1. Go to **Actions** tab
2. Select **CI/CD** workflow
3. Click **Run workflow**
4. Enter `sha-{COMMIT_SHA}` of known-good version
5. Click **Run workflow**

Alternatively, SSH to VPS and:

```bash
cd /opt/mko_bazuna
docker compose -f docker-compose.yml -f docker-compose.prod.yml down
# Edit .env.docker to specify OLD image tag if needed
docker compose -f docker-compose.yml -f docker-compose.prod.yml pull
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

### 5.7 Health Check Endpoint

The project includes health check at `/health/` (per Dockerfile). Ensure this endpoint is verified after deployment:

```python
# apps/core/views.py
def health(request):
    return JsonResponse({"status": "ok"})
```

### 5.8 Security Considerations

1. **Container security:** Image runs as non-root (uid 1000)
2. **Base images:** Pinned to `python:3.14-slim` and `postgres:18-alpine`
3. **Secrets:** All secrets stored in GitHub Secrets, never in repo
4. **SSH access:** Use dedicated deploy user, not root
5. **Image scanning:** Trivy catches CRITICAL/HIGH vulnerabilities
6. **Advisory locks:** Migrations and admin creation use locking to prevent races

---

## 6. Implementation Checklist

- [ ] Add GitHub Secrets to repository
- [ ] Configure `production` environment in GitHub
- [ ] Prepare VPS with Docker, docker-compose, deploy user
- [ ] Copy workflow file to `.github/workflows/ci-cd.yml`
- [ ] Test workflow with PR
- [ ] Perform first manual deployment
- [ ] Verify health check endpoint
- [ ] Document rollback procedure

---

## 7. References

- [GitHub Actions Documentation](https://docs.github.com/en/actions)
- [Docker Build Push Action](https://github.com/docker/build-push-action)
- [GHCR Documentation](https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry)
- Current implementation: `.github/workflows/ci.yml`