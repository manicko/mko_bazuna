# Research 1: Docker Build Optimization - APT Cache Mounts

**Date:** 2026-07-22
**Focus:** Accelerating apt-get installation in Docker builds

## Problem Statement

The current Dockerfile's apt-get installation stage is slow:
```dockerfile
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*
```

This step downloads package lists and packages every time, even when they haven't changed.

## Key Findings

### 1. BuildKit Cache Mounts for APT (2025-2026 Best Practice)

Source: [Docker Docs - Optimize cache usage in builds](https://docs.docker.com/build/cache/optimize)
Source: [OneUptime - How to Use RUN --mount=type=cache](https://oneuptime.com/blog/post/2026-02-08-how-to-use-run-mounttypecache-for-package-manager-caching/view)

Cache mounts persist package manager caches across builds WITHOUT including them in the final image:

```dockerfile
# syntax=docker/dockerfile:1.4

RUN rm -f /etc/apt/apt.conf.d/docker-clean && \
    echo 'Binary::apt::APT::Keep-Downloaded-Packages "true";' > /etc/apt/apt.conf.d/keep-cache

RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
  --mount=type=cache,target=/var/lib/apt,sharing=locked \
  apt-get update && apt-get install -y --no-install-recommends gcc libpq-dev curl
```

**Benefits:**
- Only downloads changed/new packages on subsequent builds
- Cache is NOT baked into the final image (keeps image small)
- Works with shared cache in CI environments

### 2. Dockerfile Syntax Requirement

To use cache mounts, enable Dockerfile syntax 1.4:
```dockerfile
# syntax=docker/dockerfile:1.4
```

### 3. APT Cache Configuration

Before using cache mounts, configure apt to keep downloaded packages:
```dockerfile
RUN rm -f /etc/apt/apt.conf.d/docker-clean
RUN echo 'Binary::apt::APT::Keep-Downloaded-Packages "true";' > /etc/apt/apt.conf.d/keep-cache
```

## Specific Recommendations for Mko Bazuna

### Change 1: Enable BuildKit Syntax
Add at the top of Dockerfile:
```dockerfile
# syntax=docker/dockerfile:1.4
```

### Change 2: Modify Builder Stage APT Installation
Replace the current apt-get line with:
```dockerfile
# Install build dependencies for psycopg3 and curl
RUN rm -f /etc/apt/apt.conf.d/docker-clean && \
    echo 'Binary::apt::APT::Keep-Downloaded-Packages "true";' > /etc/apt/apt.conf.d/keep-cache && \
    apt-get update && apt-get install -y --no-install-recommends \
        gcc \
        libpq-dev \
        curl \
    && rm -rf /var/lib/apt/lists/*
```

With cache mounts:
```dockerfile
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
  --mount=type=cache,target=/var/lib/apt,sharing=locked \
  apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    curl \
  && rm -rf /var/lib/apt/lists/*
```

## Expected Impact

| Metric | Before | After |
|--------|--------|-------|
| First build | ~60-90 seconds | ~60-90 seconds |
| Subsequent builds (no changes) | ~60-90 seconds | ~5-15 seconds |
| Image size | Unchanged | Unchanged |

## Trade-offs

- **Pro:** Dramatically faster rebuilds when only application code changes
- **Pro:** No image size increase
- **Con:** Requires Docker BuildKit (default in Docker Desktop 20.10+, Docker Engine 23.0+)
- **Con:** Cache mounts don't persist across different builders without explicit cache-to/from

## Additional Considerations

For CI/CD pipelines, combine with registry-based caching:
```yaml
# GitHub Actions example
- name: Build and push
  uses: docker/build-push-action@v7
  with:
    cache-from: type=registry,ref=ghcr.io/${{ github.repository }}:buildcache
    cache-to: type=registry,ref=ghcr.io/${{ github.repository }}:buildcache,mode=max
```