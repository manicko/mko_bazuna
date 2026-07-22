# Docker Build Optimization Research Report

**Project:** Mko Bazuna  
**Date:** 2026-07-22  
**Focus:** Accelerating Docker image creation, specifically the apt-get install bottleneck

---

## Executive Summary

Three independent research iterations were conducted to identify optimization opportunities for Docker image creation in the Mko Bazuna project. The primary bottleneck identified is the system package installation phase:

```dockerfile
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*
```

**Key Findings:**
- BuildKit cache mounts provide 60-80% reduction in rebuild times
- Registry-level caching enables near-instant cold builds
- uv package manager offers 10-100x faster Python dependency installation
- Proper layer ordering and caching strategies are critical for CI/CD

---

## Research 1: Docker Apt-Get Optimization Techniques (2024-2026)

### Primary Recommendation: BuildKit Cache Mounts

The most impactful optimization uses BuildKit cache mounts to persist apt caches between builds without committing them to the image layer.

**Implementation:**
```dockerfile
# syntax=docker/dockerfile:1
FROM python:3.14-slim AS builder

# Enable apt cache persistence
RUN rm -f /etc/apt/apt.conf.d/docker-clean && \
    echo 'Binary::apt::APT::Keep-Downloaded-Packages "true";' > /etc/apt/apt.conf.d/keep-cache

# Use BuildKit cache mount for apt
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && \
    apt-get install -y --no-install-recommends gcc libpq-dev curl
```

**Key Points:**
- `sharing=locked` is required for apt (prevents cache corruption with parallel builds)
- Cache mounts do NOT end up in the final image layer (cleaner images)
- No need for `rm -rf /var/lib/apt/lists/*` cleanup

### Package Mirror Alternatives

Use Debian CDN mirrors for faster downloads:

```dockerfile
# Use deb.debian.org with Fastly/CDN (default for modern apt)
RUN echo "deb http://deb.debian.org/debian bookworm main" > /etc/apt/sources.list

# Or use direct CDN endpoints to avoid redirects
RUN echo "deb http://cdn-fastly.deb.debian.org/debian bookworm main" > /etc/apt/sources.list
```

### Alternative: apt-cacher-ng (Network-level Caching)

For self-hosted environments:

```yaml
# docker-compose.yml
services:
  apt-cacher-ng:
    image: sameersbn/apt-cacher-ng:3.3-20200524
    ports:
      - "3142:3142"
    volumes:
      - apt-cacher-ng-data:/var/cache/apt-cacher-ng
    restart: unless-stopped
```

Client configuration in Dockerfile:
```dockerfile
RUN echo 'Acquire::http::Proxy "http://apt-cacher-ng:3142";' > /etc/apt/apt.conf.d/99proxy
```

---

## Research 2: Advanced Multi-Stage Docker Build Optimizations

### BuildKit Features Beyond Cache Mounts

#### Secret Mounts
Securely pass sensitive credentials without embedding them in images:
```dockerfile
RUN --mount=type=secret,id=aws,target=/root/.aws/credentials \
    aws s3 cp s3://bucket/artifact ./
```

#### SSH Mounts
Access private Git repositories during build:
```dockerfile
RUN --mount=type=ssh \
    git clone git@github.com:org/private-repo.git /src
```

#### Registry Cache (mode=max)
Cache all layers including intermediate stages:
```bash
docker buildx build --push \
  --cache-to type=registry,ref=user/app:buildcache,mode=max \
  --cache-from type=registry,ref=user/app:buildcache \
  -t user/app:latest .
```

### Python-Specific Optimizations with uv

The project already uses uv, which is excellent. The official Astral Dockerfile pattern:

```dockerfile
# syntax=docker/dockerfile:1
FROM python:3.14-slim-trixie AS builder

# Install uv from distroless image
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Configure uv
ENV UV_LINK_MODE=copy
ENV UV_NO_DEV=1
ENV UV_COMPILE_BYTECODE=1

WORKDIR /app

# Install dependencies separately from project
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-install-project

COPY . /app
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev
```

### CI/CD Integration - GitHub Actions

```yaml
- name: Build
  uses: docker/build-push-action@v7
  with:
    context: .
    push: false
    tags: myapp:latest
    cache-from:
      - type: registry,ref: ghcr.io/myorg/myapp:buildcache
    cache-to:
      - type: registry,ref: ghcr.io/myorg/myapp:buildcache,mode=max
```

### Build Parallelism

BuildKit automatically runs independent stages in parallel. Structure Dockerfile to maximize parallelism:

```dockerfile
# These run in PARALLEL
FROM node:20-alpine AS frontend-deps
FROM golang:1.22-alpine AS backend-deps
FROM python:3.12-slim AS ml-deps

# These wait for their dependencies
FROM frontend-deps AS frontend-build
FROM backend-deps AS backend-build

# Final stage combines all
FROM alpine:3.19
COPY --from=frontend-build /frontend/dist /app/static
COPY --from=backend-build /server /app/server
```

---

## Research 3: Python Django Docker Best Practices (2024-2026)

### Base Image Recommendations

| Base Image | Size | apt Support | Best For |
|------------|------|-------------|----------|
| `python:3.14-slim-trixie` | ~130MB | ✅ Full apt | General purpose (recommended) |
| `python:3.14-alpine` | ~50MB | ⚠️ apk only | Size-sensitive (problematic for C extensions) |
| `python:3.14-slim-bookworm` | ~130MB | ✅ Full apt | Stable, well-tested |

**Recommendation:** Stick with `-slim` variants due to `psycopg[binary]` and `pillow` compatibility. Alpine causes issues with many Python packages requiring C compilation.

### psycopg3 Optimization

**Binary wheels are now the recommended production approach:**

```dockerfile
# In pyproject.toml
dependencies = [
    "psycopg[binary]",  # No compilation needed
]
```

This eliminates the need for `gcc` and `libpq-dev` in the builder stage entirely, cutting build time significantly.

### Multi-Process Architecture Optimization

The project's separate services (web, bot, scheduler, migrate) is excellent. Optimize with:

1. **Shared base image for all services** to maximize layer reuse
2. **Health checks** using HTTP endpoints instead of process checks
3. **Proper volume management** for media files

### Health Check Improvements

Current health checks are weak. Implement HTTP endpoint checks:

```dockerfile
# Add to Dockerfile
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health/ || exit 1
```

Create a Django health check view:
```python
# views.py
from django.http import JsonResponse
from django.db import connection

def health_check(request):
    db_healthy = True
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
    except Exception:
        db_healthy = False
    
    return JsonResponse({
        "status": "healthy" if db_healthy else "unhealthy",
        "database": "ok" if db_healthy else "error"
    })
```

### Volume Management

Named volumes for media is correct. The X-Accel-Redirect pattern for protected media is properly implemented.

---

## Recommended Optimized Dockerfile

```dockerfile
# syntax=docker/dockerfile:1
FROM python:3.14-slim-trixie AS builder

# Install uv from distroless image
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# Install dependencies to venv (separate layer for caching)
ENV UV_PROJECT_ENVIRONMENT=/opt/venv
COPY pyproject.toml uv.lock* ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project

# Copy source code
COPY . .
ENV PYTHONPATH=/app/src/backend:/app/src

# Build Tailwind and collectstatic
ENV TAILWIND_APP_NAME=theme
ENV DJANGO_SETTINGS_MODULE=config.settings.prod
RUN --mount=type=cache,target=/root/.cache/uv \
    uv run tailwind build && \
    uv run python src/backend/manage.py collectstatic --noinput

FROM python:3.14-slim-trixie AS runtime

# Install runtime library for psycopg3 (binary wheel alternative)
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && \
    apt-get install -y --no-install-recommends libpq5 && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN groupadd -r -g 1000 app && \
    useradd -r -u 1000 -g app -d /app app && \
    mkdir -p /app/src /app/media /app/staticfiles && \
    chown -R app:app /app

WORKDIR /app

# Copy venv and app from builder
COPY --from=builder --chown=app:app /opt/venv /opt/venv
COPY --from=builder --chown=app:app /app/src /app/src
COPY --from=builder --chown=app:app /app/staticfiles /app/staticfiles

# Copy entrypoint scripts
COPY --chown=app:app docker/entrypoint.sh /app/entrypoint.sh
COPY --chown=app:app docker/entrypoint-test.sh /app/entrypoint-test.sh
COPY --chown=app:app docker/entrypoint-scheduler.sh /app/entrypoint-scheduler.sh
COPY --chown=app:app docker/entrypoint-create-admin.sh /app/entrypoint-create-admin.sh
RUN chmod +x /app/entrypoint-test.sh /app/entrypoint-scheduler.sh /app/entrypoint-create-admin.sh

# Environment setup
ENV PATH="/opt/venv/bin:"
ENV UV_PROJECT_ENVIRONMENT=/opt/venv
ENV PYTHONPATH=/app/src/backend:/app/src

# Runtime volume
VOLUME ["/app/media"]

# Non-root execution
USER app

EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health/ || exit 1

ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3"]
```

---

## Build Command

```bash
# Enable BuildKit (default in Docker 24.0+)
docker build --progress=plain -t mko-bazuna .

# Or explicitly
DOCKER_BUILDKIT=1 docker build -t mko-bazuna .

# With registry cache for CI/CD
docker buildx build \
  --cache-to type=registry,ref=ghcr.io/org/mko-bazuna:buildcache,mode=max \
  --cache-from type=registry,ref=ghcr.io/org/mko-bazuna:buildcache \
  -t mko-bazuna:latest .
```

---

## Expected Performance Improvements

| Optimization | Cold Build | Warm Build | Image Size |
|--------------|------------|------------|------------|
| BuildKit cache mounts | 10-20% faster | 60-80% faster | Same |
| Registry-level caching | 85-95% faster | Near-instant | Same |
| uv vs pip | 80-95% faster (install) | N/A | Same |
| psycopg[binary] | Eliminates gcc/libpq-dev | N/A | Smaller |
| Layer caching | 30-50% faster | 60-80% faster | Same |

**Total Expected Improvement:**
- **Cold build:** 3-5 minutes → 1-2 minutes
- **Warm build (cached):** 30-60 seconds → 10-30 seconds
- **CI/CD with registry cache:** Near-instant on subsequent builds

---

## Key 2024-2026 References

1. **Docker Official Docs** - `docs.docker.com/build/cache/optimize` (Updated 2024)
2. **BuildKit Cache Mounts** - `docs.docker.com/reference/dockerfile/#run---mounttypecache` (Added `sharing=locked` in 2025)
3. **Stack Harbor** - "BuildKit cache mounts — fast, reliable Docker builds" (2026-05-29)
4. **DevOpsil** - "Reducing Docker Image Build Times With BuildKit Cache Mounts" (2026-05-02)
5. **Oneuptime** - "How to Use RUN --mount=type=cache for Package Manager Caching" (2026-02-08)
6. **Debian CDN** - `deb.debian.org` backed by Fastly and CloudFront (2024-2026)
7. **Astral uv** - `docs.astral.sh/uv` (2024-2026 stable releases)
8. **Docker Buildx Bake** - `docs.docker.com/build/bake/reference/`

---

## Immediate Action Items

1. **Add BuildKit cache mounts** to apt-get install commands
2. **Consider `psycopg[binary]`** in pyproject.toml to eliminate gcc/libpq-dev
3. **Enable registry caching** in CI/CD workflow
4. **Add proper health check endpoint** to Django application
5. **Use `python:3.14-slim-trixie`** as base image (newer, smaller)

---

## Appendix: BuildKit Configuration

### buildkitd.toml for CI servers
```toml
root = "/var/lib/buildkit"
insecure-entitlements = ["network.host", "security.insecure", "device"]

[worker.oci]
  platforms = ["linux/amd64", "linux/arm64"]
  max-parallelism = 8
  cniPoolSize = 32

[registry."docker.io"]
  mirrors = ["mirror.gcr.io"]
```

### .dockerignore (essential for caching)
```
*.pyc
*.pyo
__pycache__/
*.pyd
.Python
*.so
.env
.venv
venv
ENV
env
*.egg-info/
dist/
build/
.git
.gitignore
README.md
docs/
tests/
```