# Docker Build Optimization - Final Validation & Prioritization Report

**Project:** Mko Bazuna  
**Date:** 2026-07-22  
**Source:** Research Report: `docker-build-optimization-research.md`

---

## Executive Summary

After thorough validation of all Docker build optimization recommendations, the following priorities are established:

| Priority | Recommendation | Implementation Scope | Effort |
|----------|----------------|---------------------|--------|
| **HIGH** | BuildKit cache mounts for apt-get | Dockerfile-only | Low |
| **HIGH** | Remove gcc/libpq-dev from builder | Dockerfile-only | Low |
| **HIGH** | uv cache mounts | Dockerfile-only | Low |
| **HIGH** | Health check endpoint | Django + Dockerfile | Medium |
| **MEDIUM** | Registry-level caching | CI/CD | Medium |
| **LOW** | Base image upgrade to slim-trixie | Dockerfile-only | Low |

---

## Detailed Validation Matrix

### 1. BuildKit Cache Mounts for apt-get ✅ VALIDATED - HIGH PRIORITY

**Research Report Reference:** Lines 31-49

**Implementation:**
```dockerfile
# syntax=docker/dockerfile:1
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && apt-get install -y --no-install-recommends gcc libpq-dev curl
```

**Scope:** Dockerfile-only change
**Effort:** Low
**Expected Impact:** 60-80% reduction in warm build times

---

### 2. Remove gcc/libpq-dev from Builder ✅ VALIDATED - HIGH PRIORITY

**Research Report Reference:** Lines 196-207

**Validation:**
- `psycopg[binary]` is **already implemented** in `pyproject.toml` (line 12)
- Binary wheels provide pre-compiled PostgreSQL driver
- `gcc` and `libpq-dev` are **unnecessary** for binary wheels

**Implementation:**
```dockerfile
# Remove from:
RUN apt-get install -y --no-install-recommends gcc libpq-dev curl

# Keep only:
RUN apt-get install -y --no-install-recommends curl
```

**Scope:** Dockerfile-only change
**Effort:** Low
**Expected Impact:** ~50MB smaller intermediate layer, faster apt operations

---

### 3. uv Cache Mounts ✅ VALIDATED - HIGH PRIORITY

**Research Report Reference:** Lines 137-144

**Implementation:**
```dockerfile
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project
```

**Scope:** Dockerfile-only change
**Effort:** Low
**Expected Impact:** 10-100x faster dependency installation

---

### 4. Health Check Endpoint ⚠️ VALIDATED - HIGH PRIORITY

**Research Report Reference:** Lines 217-245

**Requirements:**
1. Django view implementation
2. URL route configuration
3. Dockerfile HEALTHCHECK directive

**Django Implementation:**
```python
# apps/core/views.py
from django.http import JsonResponse
from django.db import connection

def health_check(request):
    db_healthy = True
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
    except Exception:
        db_healthy = False
    
    return JsonResponse({"status": "healthy" if db_healthy else "unhealthy"})
```

```python
# config/urls.py
from django.urls import path
from apps.core import views

urlpatterns = [
    # ... other routes
    path('health/', views.health_check, name='health'),
]
```

**Dockerfile Implementation:**
```dockerfile
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health/ || exit 1
```

**Scope:** Django code + Dockerfile change
**Effort:** Medium
**Security Note:** Consider returning generic "OK" without database details in production

---

### 5. Registry-Level Caching ⚠️ VALIDATED - MEDIUM PRIORITY

**Research Report Reference:** Lines 139-160, 343-348

**Implementation (GitHub Actions):**
```yaml
- name: Build
  uses: docker/build-push-action@v7
  with:
    context: .
    push: false
    tags: myapp:latest
    cache-from:
      - type: registry,ref: ghcr.io/org/mko-bazuna:buildcache
    cache-to:
      - type: registry,ref: ghcr.io/org/mko-bazuna:buildcache,mode=max
```

**Current CI Status:** Uses basic `docker build` without caching (line 17, ci.yml)

**Scope:** CI/CD configuration change
**Effort:** Medium
**Expected Impact:** Near-instant builds on subsequent runs (85-95% improvement)

---

### 6. Base Image Upgrade to slim-trixie ⚠️ VALIDATED - LOW PRIORITY

**Research Report Reference:** Lines 186-194

**Trade-off Analysis:**
| Aspect | Current (slim) | Recommended (slim-trixie) |
|--------|----------------|--------------------------|
| Size | ~130MB | ~130MB (optimized) |
| Stability | Debian stable | Debian testing |
| Package versions | Older | Newer |
| Security updates | Stable | Faster |

**Recommendation:** Keep `-slim` (bookworm) for production stability. Consider `-trixie` only if size is critical and testing is acceptable.

**Scope:** Dockerfile-only change
**Effort:** Low
**Risk:** Potential instability from newer base packages

---

## Already Implemented ✅

| Recommendation | Status | Evidence |
|----------------|--------|----------|
| psycopg[binary] | ✅ Implemented | `pyproject.toml` line 12 |
| uv package manager | ✅ Implemented | Dockerfile line 17, CI workflow |
| Multi-stage build | ✅ Implemented | Dockerfile lines 7, 56 |
| Non-root user | ✅ Implemented | Dockerfile lines 63-67, 93 |

---

## Implementation Rollout Sequence

### Phase 1: Dockerfile-Only Changes (Immediate)

1. Add `# syntax=docker/dockerfile:1` directive
2. Replace apt-get with BuildKit cache mounts
3. Remove `gcc` and `libpq-dev` from builder stage
4. Add uv cache mounts
5. Upgrade to `python:3.14-slim-trixie` (optional)

### Phase 2: Django Application Changes (Concurrent)

1. Create health check view in `apps/core/views.py`
2. Add URL route in `config/urls.py`
3. Add HEALTHCHECK directive to Dockerfile

### Phase 3: CI/CD Configuration (Follow-up)

1. Update `.github/workflows/ci.yml` to use registry caching
2. Configure build-push-action with cache-from/cache-to

---

## Expected Performance Improvements

| Optimization | Cold Build | Warm Build | Image Size |
|--------------|------------|------------|------------|
| BuildKit cache mounts | 10-20% faster | 60-80% faster | Same |
| Remove gcc/libpq-dev | 10-15% faster | Same | -50MB |
| uv cache mounts | Same | 10-30 seconds | Same |
| Registry caching | Near-instant | Near-instant | Same |
| **Combined Total** | 20-30% faster | 85-95% faster | -50MB |

---

## References

1. Docker BuildKit Cache Mounts: `docs.docker.com/build/cache/optimize`
2. BuildKit cache syntax: `docs.docker.com/reference/dockerfile/#run---mounttypecache`
3. Astral uv documentation: `docs.astral.sh/uv`
4. GitHub Actions build-push-action: `docker/build-push-action@v7`

---

## Conclusion

**7 recommendations** identified, **4 ready for immediate implementation**, **3 requiring additional changes**:

- **Immediate (Dockerfile-only):** BuildKit cache mounts, remove gcc/libpq-dev, uv cache mounts
- **Requires application changes:** Health check endpoint
- **Requires CI/CD changes:** Registry-level caching
- **Consideration:** Base image upgrade (stability trade-off)