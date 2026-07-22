# Research 2: uv Package Manager Cache Optimization

**Date:** 2026-07-22
**Focus:** Accelerating Python dependency installation with uv cache mounts

## Problem Statement

The current Dockerfile uses uv for dependency management:
```dockerfile
RUN uv sync --frozen --no-install-project
```

While uv is fast, it still downloads packages on each build when dependencies haven't changed.

## Key Findings

### 1. uv Cache Mounts (2025-2026 Official Documentation)

Source: [Astral - Using uv in Docker](https://docs.astral.sh/uv/guides/integration/docker)
Source: [Astral - uv GitHub docs](https://github.com/astral-sh/uv/blob/main/docs/guides/integration/docker.md)

uv supports BuildKit cache mounts for persistent dependency caching:

```dockerfile
ENV UV_LINK_MODE=copy

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync
```

### 2. uv Cache Directory Location

uv stores cache at:
- Unix: `$XDG_CACHE_HOME/uv` or `$HOME/.cache/uv`
- Windows: `%LOCALAPPDATA%\uv\cache`

Can be overridden:
```dockerfile
ENV UV_CACHE_DIR=/root/.cache/uv
ENV UV_PYTHON_CACHE_DIR=/root/.cache/uv/python
```

### 3. Bytecode Compilation

Enable for production images:
```dockerfile
ENV UV_COMPILE_BYTECODE=1
# or
RUN uv sync --compile-bytecode
```

### 4. Intermediate Layers Pattern

Separate dependency installation from project code:
```dockerfile
# Install dependencies to venv
COPY pyproject.toml uv.lock* ./
RUN uv sync --frozen --no-install-project

# Copy source code last
COPY . .
```

## Specific Recommendations for Mko Bazuna

### Change 1: Add uv Cache Mount to Builder Stage

Current:
```dockerfile
RUN uv sync --frozen --no-install-project
```

Recommended:
```dockerfile
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project
```

### Change 2: Add Bytecode Compilation (Production Image)

In the runtime stage, add:
```dockerfile
ENV UV_COMPILE_BYTECODE=1
```

Or set during sync:
```dockerfile
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --compile-bytecode
```

### Change 3: Configure Link Mode for Cache Compatibility

When using cache mounts:
```dockerfile
ENV UV_LINK_MODE=copy
```

This prevents warnings about linking across file systems.

## Complete Optimized Builder Stage

```dockerfile
# syntax=docker/dockerfile:1.4
FROM python:3.14-slim AS builder

# Configure apt cache
RUN rm -f /etc/apt/apt.conf.d/docker-clean && \
    echo 'Binary::apt::APT::Keep-Downloaded-Packages "true";' > /etc/apt/apt.conf.d/keep-cache

# Install build dependencies with cache mount
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
  --mount=type=cache,target=/var/lib/apt,sharing=locked \
  apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    curl \
  && rm -rf /var/lib/apt/lists/*

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /

WORKDIR /app

# Configure uv for caching
ENV UV_LINK_MODE=copy
ENV UV_COMPILE_BYTECODE=1

# Copy dependency files first for better caching
COPY pyproject.toml uv.lock* ./

# Install dependencies with uv cache mount
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project

# Copy source code last
COPY . .

ENV PYTHONPATH=/app/src/backend:/app/src

# Build Tailwind CSS and collect static files
ENV TAILWIND_APP_NAME=theme
ENV DJANGO_SETTINGS_MODULE=config.settings.prod
RUN uv run tailwind build && \
    uv run python src/backend/manage.py collectstatic --noinput
```

## Expected Impact

| Metric | Before | After |
|--------|--------|-------|
| Dependency install (first build) | ~30-60s | ~30-60s |
| Dependency install (no changes) | ~30-60s | ~2-5s |
| Image size | ~500MB | ~500MB (same) |
| Startup time | Normal | Slightly faster (bytecode) |

## Trade-offs

- **Pro:** Dramatically faster dependency installation on rebuilds
- **Pro:** No image size increase
- **Con:** Requires BuildKit
- **Con:** Cache mount location must be consistent across builds

## Additional Optimizations

1. **Pin uv version** instead of using `latest`:
   ```dockerfile
   COPY --from=ghcr.io/astral-sh/uv:0.4.0 /uv /uvx /
   ```

2. **Use dependency groups** for better separation:
   ```dockerfile
   RUN uv sync --frozen --no-install-project --group dev
   ```

3. **Consider uv export** for even faster installs:
   ```dockerfile
   RUN uv export --frozen --output requirements.txt && \
       pip install -r requirements.txt
   ```