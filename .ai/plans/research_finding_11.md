# Research: Finding 11 — LocMemCache Not Shared Across Processes

**Finding ID:** 11 (MEDIUM)
**Researcher:** task `ses_ff0118ee0ffeRO4MKcXYwqW16m`
**Date:** 2026-08-17

---

## Executive Summary

**Selected: Alternative A — django-redis + Redis Docker service.** The only alternative that fully resolves the finding AND activates existing code paths. The codebase already guards `cache.delete_pattern()` calls with `hasattr(cache, "delete_pattern")` at two sites, with inline comments stating "delete_pattern is only available on Redis cache backend." Django's built-in `RedisCache` (5.2) does NOT provide `delete_pattern` — only `django-redis` does.

---

## Full Cache Consumer Analysis

| Consumer | File:Line | Methods | TTL | Processes | Cross-process impact |
|----------|-----------|---------|-----|-----------|---------------------|
| Search autocomplete rate limit | `search/services/rate_limit.py:11` | `cache.add`, `cache.incr`, `cache.set` | 60s | 3 web workers | 30 req/min → effectively 90 req/min (per-worker counter) |
| Login rate limit | `users/services/login_rate_limit.py:13` | `cache.add`, `cache.incr`, `cache.set` | 60s | 3 web workers | 10 req/min → effectively 30 req/min |
| ModerationCriteria cache | `core/utils/cache.py:9` | `cache.get`, `cache.set`, `cache.delete` | 300s | Web + Bot | Bot reads stale criteria for up to 5 min after admin invalidation |
| Auto-moderation | `moderation/services/auto_moderation.py:15-19` | delegates to cache.py | 300s | Web (publish) + Bot (submit) | Same ModCriteria sync gap |
| Category lookup resolution | `categories/services/lookup_resolution.py:16` | `cache.get/set/delete` + guarded `delete_pattern` | 300s | 3 web workers | `delete_pattern` skipped (no hasattr) |
| Lookup cache service | `lookups/services/cache_service.py:11` | `cache.get/set/delete` + guarded `delete_pattern` | 3600s | 3 web workers + Bot | `delete_pattern` skipped; 1hr stale data |
| Seller dashboard stats | `analytics/services/seller_stats.py:42` | `cache.get`, `cache.set` | 300s | 3 web workers | Cache miss per worker; redundant DB queries |
| Bot upload rate limit | `telegram_bot/services/rate_limit.py:12` | `cache.add`, `cache.incr`, `cache.set` | 60s | Bot (single process) | Correct within bot, but bot cache invisible to web |

---

## Alternatives

| | A: django-redis + Docker Redis | B: Cloud Redis | C: PostgreSQL cache | D: Memcached | E: Django built-in RedisCache |
|---|---|---|---|---|---|
| Shared across processes | Yes | Yes | Yes | Yes | Yes |
| `delete_pattern` supported | Yes | Yes | No (guard→False) | No (guard→False) | No (guard→False) |
| Atomic `incr` (rate limit) | Yes | Yes | DB locks (poor) | Yes | Yes |
| No new dependency | No | No | Yes | Yes | Yes |
| No new Docker service | No | Yes (external) | Yes | No | No |
| Fits existing code (hasattr guards) | Yes | Yes | No | No | No |
| Fits project patterns (Docker Compose) | Yes | No | Yes | No | Yes |

## Rejected Alternatives
- **B (Cloud Redis):** Breaks "everything in Docker Compose" pattern; no benefit at this scale.
- **C (PostgreSQL cache):** Lacks `delete_pattern` — `hasattr` guard silently skips it, leaving two pattern-invalidation sites permanently dead.
- **D (Memcached):** Same `delete_pattern` gap. No existing infra pattern.
- **E (Django built-in `RedisCache`):** No new dependency, but confirmed: Django's built-in `RedisCache` does NOT expose `delete_pattern`. The existing code comments and guards were written for django-redis specifically. Would fix cross-process sharing but leave `delete_pattern` permanently dead — a false economy.

## Selected Solution: django-redis + Redis Docker Service

### Rationale
1. Unlocks already-guarded `cache.delete_pattern()` at `lookup_resolution.py:112` and `cache_service.py:77`.
2. Fixes rate-limit multiplication (30→90 req/min with 3 workers) via atomic Redis INCR.
3. Makes ModerationCriteria invalidation immediate across web+bot (not 5-min TTL fallback).
4. Consistent with existing `.gitignore` Redis patterns, `main.py:38` FSM-Redis comment, and `phase-02-detailed-plan-1.md:417-444`.
5. Matches two validated audit recommendations (ENT-003, Finding 11).

### Implementation Steps (12 files)
1. `pyproject.toml` — add `"django-redis>=5.4.0"`
2. `base.py` — `CACHES` → `django_redis.cache.RedisCache` with `REDIS_URL`
3. `dev.py` — override to `LocMemCache`
4. `test.py` — override to `LocMemCache`
5. `docker-compose.yml` — add `redis:7-alpine` service with healthcheck
6. `docker-compose.yml` — wire `REDIS_URL` + `depends_on: redis` into web/bot
7. `docker-compose.prod.yml` — add REDIS_URL + redis dependency to scheduler
8. `docker-compose.dev.override.yml` — set `REDIS_URL=` (empty) to skip Redis wait in dev
9. `.env.docker.example` — add `REDIS_URL=redis://redis:6379/0`
10. `.env.example` — add `REDIS_URL=redis://localhost:6379/0`
11. `docker/entrypoint.sh` — add `wait_for_redis()` function
12. `docs/99-agent/architecture.md` — add "Cache Backend" section

### Test Environment Considerations
- No Redis service needed in `docker-compose.test.yml` — `test.py` overrides to `LocMemCache`.
- All 4 test files with explicit `@override_settings(CACHES=LocMemCache)` become redundant but harmless.
- `cache.clear()` in tests remains safe with LocMem.
- Rate-limit tests stay deterministic (single process, sequential calls).
- `hasattr(cache, "delete_pattern")` correctly evaluates `False` in tests with LocMem.
- No migrations needed (django-redis has no models).
