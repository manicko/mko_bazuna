# Phase 09 Audit Fix Matrix — External API Surface

**Source:** `.ai/audit/99-validation/09-external-api-validated-findings.md`
**Created:** 2026-08-17
**Status:** COMPLETE — all 13 findings processed, 10 implemented, 3 already fixed before workflow

---

## 1. Findings Summary by Severity

### CRITICAL
| ID | Title | Status | Classification |
|----|-------|--------|----------------|
| 01 | `approve_ad` accepts GET requests | NEEDS FIX | Simple / low-risk |
| 03 | Bot login-token claim crashes (`returning=True`) | **ALREADY FIXED** | N/A — verified current code uses raw SQL UPDATE...RETURNING |

### HIGH
| ID | Title | Status | Classification |
|----|-------|--------|----------------|
| 02 | `bulk_moderation_action` — unguarded `json.loads` | NEEDS FIX | Simple / low-risk |
| 08 | `BOT_TOKEN` placeholder baked into Dockerfile | NEEDS FIX | Simple / low-risk |
| 09 | nginx `/static/` drops inherited security headers | NEEDS FIX | Simple / low-risk |
| 12 | `.env.docker` git-tracked | **PARTIALLY FIXED** | Manual git op (git rm forbidden) |

### MEDIUM
| ID | Title | Status | Classification |
|----|-------|--------|----------------|
| 05 | Ad-creation translator lacks circuit breaker | NEEDS FIX | Complex — resolved by Finding 06 |
| 06 | Search vs ad-creation translator inconsistency | NEEDS FIX | Complex / Multiple-routes |
| 07 | `login_status` logs `telegram_id` in plaintext | **ALREADY FIXED** | N/A — uses `mask_telegram_id()` |
| 10 | CSP only applied on `/protected-media/` | NEEDS FIX | Multiple-routes (staged rollout) |
| 11 | LocMem cache for rate limiting | NEEDS FIX | Complex / infra change |

### LOW
| ID | Title | Status | Classification |
|----|-------|--------|----------------|
| 04 | Dead code: `translate_to_russian` | NEEDS FIX | Simple / low-risk |
| 14 | Moderation bulk API leaks raw exception strings | NEEDS FIX | Simple / low-risk |

---

## 2. Finding Details

### Finding 01 — `approve_ad` accepts GET requests (CRITICAL)

**Current state:** `src/backend/apps/moderation/views/review.py:46-64` — `approve_ad` has only `@staff_required`, no `@require_POST`, no method guard. `reject_ad` and `ban_user` both have `if request.method != "POST"` guards.

**Root cause:** `@staff_required` checks identity only, not HTTP method.

**Selected solution:** Apply `@require_POST` as the outermost decorator on `approve_ad` (above `@staff_required`). Non-POST requests get HTTP 405 before the staff check. Matches the project's existing decorator pattern.

**Files to change:**
- `src/backend/apps/moderation/views/review.py` — add `from django.views.decorators.http import require_POST` + `@require_POST` decorator
- `src/backend/apps/moderation/tests/test_priority_service.py` — add test: GET to approve URL returns 405

**Tests required:**
- GET `/moderation/approve/<id>/` → 405 (was 302 before fix)
- POST `/moderation/approve/<id>/` with staff user → 302 redirect (existing behavior preserved)
- Non-staff GET → 404 (existing `staff_required` behavior preserved)

**Docs required:**
- `docs/01-spec/architecture-structure.md` — update Zone R8 section to note POST enforcement on approve endpoint
- None otherwise (code comment on docstring already says "POST only")

**Status:** PENDING

---

### Finding 02 — `bulk_moderation_action` unguarded `json.loads` (HIGH)

**Current state:** `src/backend/apps/moderation/views/api_bulk.py:36` — `data = json.loads(request.body)` with NO try/except. POST with malformed body → JSONDecodeError → 500.

**Root cause:** `json.loads` raises `json.JSONDecodeError` on malformed/empty body. The `staff_required_api` decorator only guards HTTP method, not body parsing.

**Selected solution:** Wrap `json.loads(request.body)` in `try/except json.JSONDecodeError`. Return `JsonResponse({"error": "Invalid JSON in request body"}, status=400)`. Log at WARNING via existing `logger` (exclude raw body).

**Files to change:**
- `src/backend/apps/moderation/views/api_bulk.py` — add try/except around json.loads
- `src/backend/apps/moderation/tests/test_priority_service.py` — add tests for malformed body + empty body

**Tests required:**
- POST with body `"not-json"` → 400 with `{"error": "Invalid JSON in request body"}`
- POST with empty body → 400 with same error
- Existing happy-path tests still pass

**Docs required:** None

**Status:** PENDING

---

### Finding 03 — Bot login-token claim crash (CRITICAL) — ALREADY FIXED

**Current state:** `src/telegram_bot/handlers/login.py:97-130` — `_claim_login_token()` already uses raw SQL `UPDATE login_tokens SET telegram_id = %s WHERE ... RETURNING ...` via `connection.cursor()`, exactly as the audit recommended. Called within `transaction.atomic()` at line 159-160. The `FieldDoesNotExist` crash (from the audit's evidence of `.update(telegram_id=..., returning=True)`) is no longer present.

**Verification:**
- `_claim_login_token` uses `connection.cursor()` with parameterized `UPDATE ... RETURNING` (lines 112-130)
- `WHERE` clause ensures only unclaimed (`telegram_id IS NULL`), unconsumed (`consumed_at IS NULL`), and unexpired (`expires_at > now`) tokens are touched
- Single-statement atomic claim — zero TOCTOU
- `LoginToken` model fields (`token_hash`, `telegram_id`, `created_at`, `expires_at`, `consumed_at`) all exist — no `returning` field referenced

**Tests:** Existing tests at `src/telegram_bot/tests/test_claim_login_token.py` (7 tests, marked `@pytest.mark.slow` + `@pytest.mark.integration`) test `handle_login_orm` and pass against the current implementation.

**Action:** No code change needed. Mark as verified/resolved.

**Status:** RESOLVED (already fixed before this workflow)

---

### Finding 04 — Dead code: `translate_to_russian` (LOW)

**Current state:** `src/telegram_bot/handlers/ad_create.py:645-665` — `translate_to_russian()` (line 652) and `_do_translate()` (line 645) are defined but have ZERO callers. The active translator is `translate_all_languages()` (line 798+) which uses `_do_translate_to()` (line 792).

**Root cause:** Dead code left from a refactor to multi-language support.

**Selected solution:** Delete `translate_to_russian` (line 652-665) and `_do_translate` (line 645-649). Finding 05/06 consolidation will also delete `_do_translate_to` (line 792-796).

**Files to change:**
- `src/telegram_bot/handlers/ad_create.py` — delete dead functions

**Tests required:**
- `uv run pytest src/telegram_bot/tests/` — confirm no regressions
- Grep for any remaining references (already verified zero callers)

**Docs required:** None

**Status:** PENDING

---

### Finding 05 — Ad-creation translator lacks circuit breaker (MEDIUM)

**Current state:** `src/telegram_bot/handlers/ad_create.py:798-820` — `translate_all_languages()` uses `asyncio.wait_for(..., timeout=15.0)` with bare `except Exception: return text`. No circuit breaker, no caching.

**Root cause:** The bot-side translator was never hardened, unlike the search-side translator which has a circuit breaker + 500ms timeout + LRU cache.

**Selected solution:** Resolved by Finding 06's consolidation. After creating the shared `TranslationService` module, `translate_all_languages` will inherit the circuit breaker, 500ms timeout, and LRU cache.

**Dependency:** Finding 04 (dead code removal) is a prerequisite cleanup.

**Tests required:**
- After consolidation: test circuit-breaker open state, timeout fallback, exception fallback, LRU cache hit
- Add to `src/telegram_bot/tests/test_multi_lang_translation.py`

**Docs required:** None (covered by Finding 06 docs)

**Status:** PENDING (blocked on Finding 06)

---

### Finding 06 — Search vs ad-creation translator inconsistency (MEDIUM)

**Current state:** Search-side translator (`query_translator.py`) has `TranslationCircuitBreaker`, 500ms timeout, LRU cache. Bot-side (`ad_create.py`) has 15s timeout, no breaker, no cache.

**Root cause:** Two independent translator implementations with divergent resilience patterns.

**Selected solution:** **Alternative (c)** — Create shared `apps/core/services/translation.py` module containing `TranslationCircuitBreaker`, `_EXECUTOR`, timeout constant, LRU-cached translators, and generic `translate_text()` function. Rewrite bot's `translate_all_languages` to use it via `asyncio.gather` + `asyncio.to_thread`. Convert search-side `query_translator.py` into a thin re-export shim (preserving all names for existing callers/tests).

**Research reference:** See `.ai/plans/research_finding_06.md` for full analysis.

**Files to change (new):**
- `src/backend/apps/core/services/translation.py` — new shared module

**Files to change (edit):**
- `src/backend/apps/search/services/query_translator.py` — convert to re-export shim
- `src/telegram_bot/handlers/ad_create.py` — rewrite `translate_all_languages`, delete 3 dead translators
- `src/telegram_bot/tests/test_multi_lang_translation.py` — update patch target, add parity tests

**Files unchanged at runtime:**
- `src/backend/apps/search/views/search.py`
- `src/backend/apps/search/services/alert_query.py`
- `src/backend/apps/search/tests/test_query_translator.py`

**Tests required:**
- Search-side: existing `test_query_translator.py` stays green (7 tests, unchanged)
- Bot-side: update `test_multi_lang_translation.py` patch target from `ad_create._do_translate_to` → shared module; add circuit-breaker open-state short-circuit test, timeout→fallback test, exception→fallback test
- Integration: `test_ad_create.py` patches whole `translate_all_languages` → unchanged

**Docs required:**
- `docs/01-spec/search-patterns.md` — note bot now reuses shared translator
- `docs/01-spec/technical-specification.md:106` — still holds (deep-translator + parallel gather)
- `docs/03-packages/dependency-collisions.md` — note 500ms timeout now governs bot ad-creation too

**Status:** PENDING

---

### Finding 07 — `login_status` logs `telegram_id` in plaintext (MEDIUM) — ALREADY FIXED

**Current state:** `src/backend/apps/users/views/consent.py:262-289` — all 4 log statements already use `mask_telegram_id(token.telegram_id)`. The `mask_telegram_id` function is defined at `src/backend/apps/core/utils/sanitize.py:46-62`.

**Verification:**
- Line 263: `f"Login token {token_hash[:8]} consumed by telegram_id={mask_telegram_id(token.telegram_id)}"`
- Line 271: `f"User not found for telegram_id={mask_telegram_id(token.telegram_id)}"`
- Line 278: `f"Login denied for telegram_id={mask_telegram_id(token.telegram_id)}: banned"`
- Line 288: `f"Web session established for user {user.id} (telegram_id={mask_telegram_id(token.telegram_id)})"`

**Tests:** Existing tests at `src/backend/apps/core/tests/test_sanitize.py` (5 tests) cover `mask_telegram_id`.

**Action:** No code change needed. Mark as verified/resolved.

**Status:** RESOLVED (already fixed before this workflow)

---

### Finding 08 — `BOT_TOKEN` placeholder in Dockerfile (HIGH)

**Current state:** `docker/Dockerfile:70` — `ENV BOT_TOKEN=1234567890:build-placeholder-do-not-use-in-production`

**Root cause:** Build-time placeholder baked into Docker image layer.

**Selected solution:** Remove the `ENV BOT_TOKEN=...` line. Production `prod.py:14` already validates `BOT_TOKEN` presence at startup (raises `ImproperlyConfigured` if empty). The `.env.docker.example` template correctly has `BOT_TOKEN=` (empty, for dev).

**Files to change:**
- `docker/Dockerfile` — remove line 70

**Tests required:**
- Dockerfile lint / build verification (no test suite impact)

**Docs required:** None (the comment on line 68-73 already documents placeholder pattern)

**Status:** PENDING

---

### Finding 09 — nginx `/static/` drops inherited security headers (HIGH)

**Current state:** `docker/nginx/nginx.conf:48-57` — `/static/` location has `add_header Cache-Control "public, immutable"` (line 57). Due to nginx `add_header` inheritance, this DROPS all inherited server-level headers (HSTS, nosniff, X-Frame-Options). Same issue in `docker/nginx/nginx.dev.conf:59`.

**Root cause:** nginx `add_header` inheritance rule: any `add_header` in a location block overrides ALL inherited `add_header` directives from parent blocks.

**Selected solution:** Re-declare all security headers inside the `/static/` location block. Use `expires 30d;` (which doesn't trigger the inheritance override) for Cache-Control instead of `add_header Cache-Control`.

**Files to change:**
- `docker/nginx/nginx.conf` — fix `/static/` location block
- `docker/nginx/nginx.dev.conf` — fix `/static/` location block (same fix)

**Tests required:**
- nginx config syntax check: `nginx -t -c nginx.conf` (can be done in container)
- Verify response headers on `/static/` path (manual or curl)

**Docs required:**
- `docs/01-spec/architecture-structure.md` — update Zone R8 section to document `/static/` header redeclaration

**Status:** PENDING

---

### Finding 10 — CSP only applied on `/protected-media/` (MEDIUM)

**Current state:** CSP `add_header` only in `/protected-media/` location (`nginx.conf:78`). Spec at `architecture-structure.md:255` claims CSP on "all responses." Main HTML, `/static/`, `/media/`, `/login/`, `/search/`, `/health/`, `/` all serve WITHOUT CSP.

**Root cause:** CSP was only added to the restricted media location; server-level CSP was never implemented.

**Selected solution:** **Alternative D** — Server-level `Content-Security-Policy-Report-Only` with a content-appropriate relaxed policy (accommodates inline scripts, external CDN scripts, `onclick` handlers that exist in templates). Report-Only means zero rollout risk. Remove per-location CSP from `/protected-media/` (server-level Report-Only covers it). Phase 2 (deferred): refactor templates to eliminate `'unsafe-inline'`, then switch to enforcing CSP.

**Research reference:** See `.ai/plans/research_finding_10.md` for full analysis including template audit.

**Dependency:** Must be applied concurrently with Finding 09 (both touch nginx config; `/static/` needs Finding 09 fix to receive server-level CSP).

**Files to change:**
- `docker/nginx/nginx.conf` — add server-level CSP-Report-Only, remove per-location CSP from `/protected-media/`, fix `/static/` headers (Finding 09)
- `docker/nginx/nginx.dev.conf` — same changes
- NEW: `src/backend/apps/core/views.py` — CSP report endpoint at `/csp-report/`
- `src/backend/config/urls.py` — wire URL

**Tests required:**
- nginx config syntax check
- Verify CSP-Report-Only header on `/`, `/static/`, `/protected-media/`
- Endpoint receives POST reports (unit test on view)

**Docs required:**
- `docs/01-spec/architecture-structure.md:255` — update to describe staged rollout (Report-Only → enforcement)
- `docs/ops/docker-deployment.md:546-550` — update security header claim

**Status:** PENDING (Wave 2 — after Finding 09)

---

### Finding 11 — LocMem cache not shared across processes (MEDIUM)

**Current state:** `src/backend/config/settings/base.py:219-223` — `CACHES` uses `LocMemCache`. `prod.py` does NOT override. Cache consumers: `rate_limit.py`, `cache.py`, `auto_moderation.py`, `lookup_resolution.py`, `cache_service.py`. Production runs 3 gunicorn workers + bot process — LocMem is per-process, not shared.

**Root cause:** LocMemCache is in-process only; rate-limit counters multiply by worker count, cache invalidation doesn't propagate across processes.

**Selected solution:** **Alternative A** — django-redis + Redis Docker service. Add `django-redis` to `pyproject.toml` dependencies. Configure `CACHES["default"]` with `django_redis.cache.RedisCache` and `REDIS_URL` in `base.py`. Override to `LocMemCache` in `dev.py` and `test.py` (no Redis needed locally). Add `redis:7-alpine` service to `docker-compose.yml` and `docker-compose.prod.yml`. Wire `REDIS_URL` into all service environments. Add `wait_for_redis()` to `docker/entrypoint.sh`.

**Research reference:** See `.ai/plans/research_finding_11.md` for full analysis.

**Files to change:**
- `pyproject.toml` — add `"django-redis>=5.4.0"` to dependencies
- `src/backend/config/settings/base.py` — replace LocMemCache → RedisCache with REDIS_URL
- `src/backend/config/settings/dev.py` — override CACHES → LocMemCache
- `src/backend/config/settings/test.py` — override CACHES → LocMemCache
- `docker-compose.yml` — add Redis service, add REDIS_URL to all service envs
- `docker-compose.prod.yml` — add REDIS_URL to scheduler env
- `docker-compose.dev.override.yml` — add REDIS_URL to web/bot envs (if needed)
- `.env.docker.example` — add `REDIS_URL=redis://redis:6379/0`
- `.env.example` — add `REDIS_URL=redis://localhost:6379/0`
- `docker/entrypoint.sh` — add `wait_for_redis()` function + call
- `docs/99-agent/architecture.md` — add Cache Backend section

**Tests required:**
- `uv run pytest src/backend/apps/search/tests/test_query_translator.py` — cache-related tests still pass (test.py uses LocMem)
- `uv run pytest src/backend/apps/moderation/tests/` — auto_moderation cache tests still pass
- `uv run pytest src/backend/apps/categories/tests/` — lookup cache tests still pass
- `uv run pytest src/backend/apps/core/tests/test_sanitize.py` — unchanged
- Verify `hasattr(cache, "delete_pattern")` still works correctly with Redis at runtime

**Docs required:**
- `docs/99-agent/architecture.md` — document Redis requirement as cache backend
- `docs/01-spec/technical-specification.md:152` — note Redis is now the shared cache
- `.ai/plans/research_finding_11.md` — reference to research

**Status:** PENDING (large infra change)

---

### Finding 12 — `.env.docker` git-tracked (HIGH) — PARTIALLY FIXED

**Current state:** `.gitignore` line 148 already has `.env.docker`. `.env.docker.example` exists as a template. However, the file is still tracked by git (committed before the `.gitignore` update).

**Root cause:** `.gitignore` only prevents future tracking; it doesn't untrack already-committed files.

**Selected solution:** The `.gitignore` fix is already done. The remaining step is `git rm --cached .env.docker` to untrack the file. **However, `git rm` is explicitly forbidden by the project's git rules.** This is a one-time manual git operation that cannot be performed programmatically. The file contains only placeholder values (no real secrets).

**Action:** Document the manual step. The `.gitignore` fix prevents future tracking. The file contains only placeholders.

**Files to change:**
- None (gitignore already fixed; untracking is a manual git operation)

**Tests required:** None

**Docs required:**
- `docs/ops/docker-deployment.md:78` — update table entry for `.env.docker` to reflect "Tracked in git: No"

**Status:** RESOLVED (gitignore already fixed; untracking is manual)

---

### Finding 14 — Moderation bulk API leaks raw exception strings (LOW)

**Current state:** `src/backend/apps/moderation/views/api_bulk.py:56-59` — `errors.append({"id": ad_id, "error": str(e)})` returns full exception message to client.

**Root cause:** Internal exception strings (e.g., "Ad matching query does not exist") sent verbatim to admin clients.

**Selected solution:** Return sanitized generic error to client (e.g., "Processing failed"), log full `str(e)` server-side via `logger.error(...)`. This is paired with Finding 02 in the same file.

**Files to change:**
- `src/backend/apps/moderation/views/api_bulk.py` — sanitize error message, add logger.error

**Tests required:**
- POST with unknown action → error message is sanitized (not raw `ValueError`)
- POST with non-existent ad → error message is sanitized (not raw DoesNotExist)
- Existing test `test_unknown_action_returns_error` (line 537) checks `assertIn("unknown", ...)` — needs update

**Docs required:** None

**Status:** PENDING (paired with Finding 02)

---

## 3. Implementation Wave Plan

### Wave 1 — Simple, independent fixes (parallel)
| Finding | File(s) | Agent |
|---------|---------|-------|
| 01 | `review.py` + `test_priority_service.py` | implementor |
| 08 | `Dockerfile` | implementor |
| 09 | `nginx.conf` + `nginx.dev.conf` | implementor |

### Wave 2 — `api_bulk.py` combined fixes (single file)
| Finding | File(s) | Agent |
|---------|---------|-------|
| 02 + 14 | `api_bulk.py` + `test_priority_service.py` | implementor |

### Wave 3 — Dead code removal
| Finding | File(s) | Agent |
|---------|---------|-------|
| 04 | `ad_create.py` | implementor |

### Wave 4 — Complex infrastructure changes
| Finding | Files | Agent |
|---------|-------|-------|
| 06 + 05 | `core/services/translation.py` (new) + `query_translator.py` + `ad_create.py` + `test_multi_lang_translation.py` | implementor |
| 10 | `nginx.conf` + `nginx.dev.conf` + `core/views.py` + `urls.py` | implementor |
| 11 | `pyproject.toml` + `base.py` + `dev.py` + `test.py` + docker-compose files + entrypoint.sh + env templates | implementor |

### Wave 5 — Documentation updates
All findings' doc requirements consolidated.

---

## 4. Quality Gates

**Python (`*.py`):**
- `uv run ruff check <affected>`
- `uv run basedpyright <affected>`
- `uv run pytest <relevant_path>`

**Docker/nginx:**
- `nginx -t` config syntax validation
- Docker image build verification

**Git:**
- Conventional commits per finding
- No forbidden git commands

---

## 5. Status Tracking

| Finding | Severity | Researcher Status | Implementation Status | Docs Status | Tests Status | Commit |
|---------|----------|-------------------|----------------------|-------------|--------------|--------|
| 01 | CRITICAL | Simple | **DONE** | **DONE** | **DONE** | `a567c38` |
| 02 | HIGH | Simple | **DONE** | None | **DONE** | `a567c38` |
| 03 | CRITICAL | Already fixed | **RESOLVED** (verified) | None | Verified | None |
| 04 | LOW | Simple | **DONE** | None | **DONE** | `832c049` |
| 05 | MEDIUM | Complex (merged) | **DONE** (via 06) | **DONE** | **DONE** | `7d6aac7` |
| 06 | MEDIUM | Complex | **DONE** | **DONE** | **DONE** | `7d6aac7` |
| 07 | MEDIUM | Already fixed | **RESOLVED** (verified) | None | Verified | None |
| 08 | HIGH | Simple | **DONE** | None | N/A (Docker build) | `c583f2b` |
| 09 | HIGH | Simple | **DONE** | **DONE** (covered by 10 docs) | N/A (nginx -t) | `16342e9` |
| 10 | MEDIUM | Multiple-routes | **DONE** | **DONE** | **DONE** | `39d4757` |
| 11 | MEDIUM | Complex | **DONE** | **DONE** | **DONE** | `560a214` |
| 12 | HIGH | Partially fixed | **RESOLVED** (gitignore already done; untrack = manual) | **DONE** (already correct) | None | None |
| 14 | LOW | Simple | **DONE** | None | **DONE** | `a567c38` |

### Commit Summary
| Commit | Findings | Message |
|--------|----------|---------|
| `a567c38` | 01, 02, 14 | `fix(moderation): enforce POST on approve_ad, guard bulk JSON parse, sanitize bulk errors` |
| `832c049` | 04 | `fix(telegram_bot): remove dead translate_to_russian and _do_translate` |
| `c583f2b` | 08 | `fix(docker): remove BOT_TOKEN build-time placeholder from Dockerfile` |
| `16342e9` | 09 | `fix(nginx): re-declare security headers in /static/ location` |
| `7d6aac7` | 05, 06 | `refactor(translations): consolidate translators into shared core service` |
| `39d4757` | 10 | `fix(security): expand CSP to all responses via Report-Only mode` |
| `560a214` | 11 | `fix(cache): replace LocMemCache with Redis via django-redis` |

### Already-Fixed Findings (no action needed)
| Finding | Verification |
|---------|-------------|
| 03 | `login.py:_claim_login_token` already uses raw SQL `UPDATE ... RETURNING` via `connection.cursor()` — matches ENT-001 spec recommendation |
| 07 | `consent.py` log statements already use `mask_telegram_id()` — `mask_telegram_id` function exists at `sanitize.py:46-62` |
| 12 | `.gitignore` already has `.env.docker` (line 148); `.env.docker.example` exists as template; `docs/ops/docker-deployment.md:78` already reflects "No (gitignored)". Note: `git rm --cached .env.docker` is a manual one-time operation (git rm is forbidden by project rules). |
