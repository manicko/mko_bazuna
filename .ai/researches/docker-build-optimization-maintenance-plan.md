# Docker Build Optimization Maintenance Plan

**Project:** Mko Bazuna  
**Date:** 2026-07-22  
**Based on:** `docker-build-optimization-final-report.md`  
**Stack:** Python 3.14 · Django 5.2 LTS · PostgreSQL 18 · uv package manager

---

## Executive Summary

This maintenance plan details the implementation of Docker build optimizations validated in the final report. The optimizations are organized into three phases with clear dependencies, expected outcomes, and risk assessments.

**Total Tasks:** 9  
**Estimated Total Effort:** ~2-3 hours  
**Expected Build Time Improvement:** 85-95% (warm builds), 20-30% (cold builds)  
**Expected Image Size Reduction:** ~50MB

---

## Phase 1: Dockerfile-Only Optimizations (Immediate)

These tasks can be executed independently and in parallel.

### Task 1.1: Add BuildKit Syntax Directive

**File:** `docker/Dockerfile`  
**Location:** Line 1 (immediately after the comment block header)  
**Type:** Add top-level directive

| Attribute | Value |
|-----------|-------|
| Priority | HIGH |
| Effort | Low |
| Dependencies | None |
| Risk | Low |

**Expected Outcome:**
- Enables BuildKit cache mount features
- Required for all cache mount optimizations
- No functional impact on image

**Implementation:**
```dockerfile
# syntax=docker/dockerfile:1
# Multi-stage Dockerfile for Mko Bazuna
```

**Risk Assessment:**
- **Low Risk:** This is a no-op comment directive that only affects advanced Docker features
- **Mitigation:** Standard Dockerfile parsing remains compatible
- **Verification:** Build should succeed identically or faster

---

### Task 1.2: Implement BuildKit Cache Mounts for apt-get

**File:** `docker/Dockerfile`  
**Location:** Lines 9-14 (apt-get install in builder stage)  
**Type:** Modify existing RUN command

| Attribute | Value |
|-----------|-------|
| Priority | HIGH |
| Effort | Low |
| Dependencies | Task 1.1 (BuildKit syntax directive) |
| Risk | Low |

**Expected Outcome:**
- 60-80% reduction in warm build times for apt-get operations
- `/var/cache/apt` and `/var/lib/apt` cached between builds
- Faster dependency installation in CI/CD

**Implementation:**
```dockerfile
# CURRENT (lines 9-14):
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# PROPOSED:
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*
```

**Risk Assessment:**
- **Low Risk:** Standard BuildKit feature, widely used
- **Mitigation:** Ensure Docker Buildx is enabled in CI (already configured in ci.yml line 13-14)
- **Verification:** Compare build times before/after; cache directory should persist

---

### Task 1.3: Remove gcc and libpq-dev from Builder Stage

**File:** `docker/Dockerfile`  
**Location:** Lines 9-14 (same block as Task 1.2)  
**Type:** Modify existing RUN command

| Attribute | Value |
|-----------|-------|
| Priority | HIGH |
| Effort | Low |
| Dependencies | Task 1.1 (BuildKit syntax directive) |
| Risk | Low |

**Expected Outcome:**
- ~50MB reduction in intermediate layer size
- Faster apt-get operations (fewer packages)
- No functional change (psycopg[binary] provides pre-compiled driver)

**Implementation:**
```dockerfile
# CURRENT (lines 9-14):
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# PROPOSED:
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*
```

**Risk Assessment:**
- **Low Risk:** `psycopg[binary]` in `pyproject.toml` line 12 provides pre-compiled PostgreSQL driver
- **Mitigation:** Verify psycopg binary wheel is compatible with target platform
- **Verification:** Run tests after build; database connectivity should work

---

### Task 1.4: Add uv Cache Mounts

**File:** `docker/Dockerfile`  
**Location:** Line 31 (uv sync command)  
**Type:** Modify existing RUN command

| Attribute | Value |
|-----------|-------|
| Priority | HIGH |
| Effort | Low |
| Dependencies | None (can be done independently) |
| Risk | Low |

**Expected Outcome:**
- 10-100x faster dependency installation
- uv cache persists between builds
- Reduced network calls for package downloads

**Implementation:**
```dockerfile
# CURRENT (line 31):
RUN /uv sync --frozen --no-install-project

# PROPOSED:
RUN --mount=type=cache,target=/root/.cache/uv \
    /uv sync --frozen --no-install-project
```

**Risk Assessment:**
- **Low Risk:** Standard BuildKit cache mount pattern
- **Mitigation:** Ensure uv version compatibility across builds
- **Verification:** Cache directory should be reused; first build slower, subsequent builds faster

---

## Phase 2: Django Application Changes (Concurrent with Phase 1)

### Task 2.1: Create Health Check View

**File:** `src/backend/apps/core/views.py`  
**Location:** Create new file (doesn't exist yet)  
**Type:** Create new file

| Attribute | Value |
|-----------|-------|
| Priority | HIGH |
| Effort | Medium |
| Dependencies | None |
| Risk | Low |

**Expected Outcome:**
- HTTP endpoint at `/health/` returning JSON status
- Database connectivity check included
- Enables container orchestration health monitoring

**Implementation:**
```python
"""Core application views."""
from django.http import JsonResponse
from django.db import connection


def health_check(request):
    """Health check endpoint for container orchestration.

    Returns HTTP 200 with status if healthy, HTTP 503 if unhealthy.
    Includes database connectivity check.
    """
    db_healthy = True
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
    except Exception:
        db_healthy = False

    if db_healthy:
        return JsonResponse({"status": "healthy"})
    return JsonResponse({"status": "unhealthy"}, status=503)
```

**Risk Assessment:**
- **Low Risk:** Simple view with no side effects
- **Mitigation:** Use generic response without exposing database details
- **Verification:** Access `/health/` endpoint; should return `{"status": "healthy"}`

---

### Task 2.2: Register Health Check URL Route

**File:** `src/backend/config/urls.py`  
**Location:** Line 17 (after existing includes)  
**Type:** Add new path to urlpatterns

| Attribute | Value |
|-----------|-------|
| Priority | HIGH |
| Effort | Low |
| Dependencies | Task 2.1 (health check view) |
| Risk | Low |

**Expected Outcome:**
- URL route `/health/` maps to health_check view
- Endpoint accessible without authentication

**Implementation:**
```python
"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
"""
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("moderation/", include("apps.moderation.urls")),
    path("", include("apps.users.urls")),
    path("", include("apps.ads.urls")),
    path("", include("apps.categories.urls")),
    path("", include("apps.locations.urls")),
    path("", include("apps.search.urls")),
    path("health/", include("apps.core.urls")),  # NEW
]
```

**Alternative Implementation (if apps.core.urls doesn't exist):**
```python
# Direct import approach:
from apps.core import views

urlpatterns = [
    # ... existing routes
    path("health/", views.health_check, name="health"),
]
```

**Risk Assessment:**
- **Low Risk:** Simple URL routing addition
- **Mitigation:** Use `include()` pattern consistent with other apps
- **Verification:** Run `python manage.py show_urls` or test endpoint access

---

### Task 2.3: Add HEALTHCHECK Directive to Dockerfile

**File:** `docker/Dockerfile`  
**Location:** After line 95 (after EXPOSE directive, before ENTRYPOINT)  
**Type:** Add new directive

| Attribute | Value |
|-----------|-------|
| Priority | HIGH |
| Effort | Low |
| Dependencies | Task 2.1, Task 2.2 (health check endpoint) |
| Risk | Low |

**Expected Outcome:**
- Docker can monitor container health
- Container restarts unhealthy instances
- Integration with container orchestration (K8s, swarm, etc.)

**Implementation:**
```dockerfile
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health/ || exit 1

ENTRYPOINT ["/app/entrypoint.sh"]
```

**Risk Assessment:**
- **Low Risk:** Standard Docker health check pattern
- **Mitigation:** Ensure curl is available in runtime image (add if needed)
- **Verification:** Run `docker inspect` on container; health status should show

---

## Phase 3: CI/CD Configuration (Follow-up)

### Task 3.1: Update CI Build Step with Registry Caching

**File:** `.github/workflows/ci.yml`  
**Location:** Lines 16-17 (Build Docker image step)  
**Type:** Modify existing step

| Attribute | Value |
|-----------|-------|
| Priority | MEDIUM |
| Effort | Medium |
| Dependencies | None |
| Risk | Medium |

**Expected Outcome:**
- Near-instant builds on subsequent runs (85-95% improvement)
- Build cache stored in GitHub Container Registry
- Reduced CI minutes and faster feedback

**Implementation:**
```yaml
# CURRENT (lines 16-17):
- name: Build Docker image
  run: docker build -t mko-bazuna:ci -f docker/Dockerfile .

# PROPOSED:
- name: Build Docker image
  uses: docker/build-push-action@v7
  with:
    context: .
    push: false
    tags: mko-bazuna:ci
    cache-from:
      - type: registry,ref: ghcr.io/manicko/mko-bazuna:buildcache
    cache-to:
      - type: registry,ref: ghcr.io/manicko/mko-bazuna:buildcache,mode=max
```

**Risk Assessment:**
- **Medium Risk:** Requires GHCR write permissions; introduces external dependency
- **Mitigation:** Use separate cache repository; test with `push: false` first
- **Verification:** Compare build times; check that cache layer is reused

---

## Dependency Graph

```
┌─────────────────────────────────────────────────────────────┐
│                     Phase 1: Dockerfile Changes              │
└─────────────────────────────────────────────────────────────┘
                                │
        ┌───────────────────────┼───────────────────────┐
        ▼                       ▼                       ▼
┌───────────────┐     ┌─────────────────┐     ┌──────────────────┐
│ Task 1.1      │     │ Task 1.2        │     │ Task 1.4         │
│ BuildKit      │     │ apt-get cache   │     │ uv cache         │
│ Directive     │     │ mounts          │     │ mounts           │
└───────────────┘     └─────────────────┘     └──────────────────┘
                                │
        ┌───────────────────────┼───────────────────────┐
        ▼                       ▼                           (independent)
┌───────────────┐     ┌─────────────────┐
│ Task 1.3      │     │                 │
│ Remove gcc/   │     │                 │
│ libpq-dev     │     │                 │
└───────────────┘     └─────────────────┘

┌─────────────────────────────────────────────────────────────┐
│                     Phase 2: Django Changes                 │
└─────────────────────────────────────────────────────────────┘
                                │
        ┌───────────────────────┼───────────────────────┐
        ▼                       ▼                       ▼
┌───────────────┐     ┌─────────────────┐     ┌──────────────────┐
│ Task 2.1      │     │ Task 2.2        │     │ Task 2.3         │
│ Health View   │────▶│ URL Route       │────▶│ HEALTHCHECK      │
└───────────────┘     └─────────────────┘     └──────────────────┘

┌─────────────────────────────────────────────────────────────┐
│                     Phase 3: CI/CD Changes                  │
└─────────────────────────────────────────────────────────────┘
                                │
        ┌───────────────────────┼───────────────────────┐
        ▼                       ▼
┌───────────────┐     ┌─────────────────┐
│ Task 3.1      │     │                 │
│ Registry      │     │                 │
│ Caching       │     │                 │
└───────────────┘     └─────────────────┘
```

---

## Task Execution Order

### Recommended Execution Sequence:

1. **Task 1.1** → Add BuildKit syntax directive (prerequisite for Task 1.2)
2. **Task 1.2** → Implement apt-get cache mounts
3. **Task 1.3** → Remove gcc/libpq-dev (can be done with Task 1.2)
4. **Task 1.4** → Add uv cache mounts (independent)
5. **Task 2.1** → Create health check view
6. **Task 2.2** → Register health check URL
7. **Task 2.3** → Add HEALTHCHECK directive
8. **Task 3.1** → Update CI with registry caching (can be done last)

---

## Verification Checklist

After implementing all tasks, verify:

- [ ] Docker builds complete successfully
- [ ] Health check endpoint returns `{"status": "healthy"}`
- [ ] Database connectivity check works correctly
- [ ] Container health status shows "healthy" in `docker inspect`
- [ ] Cold build completes without errors
- [ ] Warm build is significantly faster (cache working)
- [ ] Image size reduced by ~50MB
- [ ] CI builds use cache (if Task 3.1 implemented)

---

## Rollback Plan

If issues arise:

1. **Task 1.1-1.4 (Dockerfile):** Revert to original Dockerfile
2. **Task 2.1-2.3 (Health Check):** Remove health check from URLs and Dockerfile
3. **Task 3.1 (CI):** Revert to `docker build` command

All changes are isolated and reversible.

---

## Notes

- `psycopg[binary]` is already implemented in `pyproject.toml` line 12
- uv package manager is already in use (Dockerfile line 17, CI workflow)
- Multi-stage build and non-root user are already implemented
- Base image upgrade to `-slim-trixie` is **not recommended** due to stability trade-offs (keep `-slim`)

---

## References

1. Docker BuildKit Cache Mounts: https://docs.docker.com/build/cache/optimize
2. BuildKit cache syntax: https://docs.docker.com/reference/dockerfile/#run---mounttypecache
3. Astral uv documentation: https://docs.astral.sh/uv
4. GitHub Actions build-push-action: https://github.com/docker/build-push-action