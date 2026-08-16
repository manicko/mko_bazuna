# Phase 09 Audit — External API Surface — VALIDATED Findings

**Phase scope:** `audit-external-api.md` (external integrations, web API, shared services, runtime behavior)
**Discovery period:** 2026-08-15
**Environment verified:** Docker available; test DB started on `127.0.0.1:5433` (postgres/postgres, db `mko_bazuna`); venv via `uv`; Django 5.2.16 installed (confirmed via `uv run python -c "import django; print(django.VERSION)"` → `(5, 2, 16, final, 0)`).
**Validation date:** 2026-08-15
**Validator:** Kilo (automated evidence verification)

---

## Methodology

Each finding was validated against:
1. **Source code** — read at file:line for every cited reference.
2. **Django runtime behavior** — empirically verified `FieldDoesNotExist` crash via direct ORM call against installed Django 5.2.16 (see Finding 03).
3. **Git state** — verified `.env.docker` tracking via `git ls-files` and `git check-ignore`.
4. **Spec cross-check** — cross-referenced `docs/01-spec/`, `docs/99-agent/`, `docs/ops/`.
5. **Django source** — inspected `QuerySet.update()` and `UpdateQuery.add_update_values()` source via `inspect.getsource()`.

Validation outcomes:
- **VALIDATED** — finding confirmed against code and/or runtime.
- **VALIDATED with evidence corrections** — finding is correct but evidence contains inaccuracies (wrong line/file citation, overstated claim).
- **REJECTED** — finding does not apply (stale, already fixed, duplicate, or false).

---

## Findings — Mandatory (security / data loss / correctness)

### 01. `approve_ad` accepts GET requests — state change on GET

**Severity:** CRITICAL
**Type:** correctness / CSRF
**Effort:** trivial
**Validation status:** VALIDATED

**Evidence (verified):**
- `src/backend/apps/moderation/views/review.py:46-64` — `approve_ad` has `@staff_required` decorator only; NO `if request.method != "POST"` guard and NO `@require_POST`. Calls `do_approve()` unconditionally at line 61.
- `src/backend/apps/moderation/views/review.py:87` — `reject_ad` HAS `if request.method != "POST"` guard.
- `src/backend/apps/moderation/views/review.py:119` — `ban_user` HAS `if request.method != "POST"` guard.
- `src/backend/apps/moderation/urls.py:15` — `path("approve/<int:ad_id>/", approve_ad, name="approve")`.
- Docstring at `review.py:49` claims "POST only" but code does not enforce it.
- Runtime probe in original finding: `GET /moderation/approve/<id>/` returned `302`, `Ad.status` changed to `published`.

**Correction note:** The `@staff_required` decorator (`decorators.py:17-31`) only filters by staff/superuser identity, NOT HTTP method. It does not provide CSRF or idempotency protection.

**Validation assessment:** The problem is real and critical. GET requests must be idempotent; approving an ad is a mutation. CSRF via `<img src>` or crawler triggers is exploitable.

**Recommendation:** Apply `@require_POST` as the outermost decorator on `approve_ad` (`review.py:46`), above `@staff_required`. Non-POST requests receive HTTP 405 before the staff identity check runs, consistent with the project's decorator-based pattern (`staff_required`, `staff_required_api` in `decorators.py:34-50`) and the rollout-safety guidance below. No new dependencies required.

---

### 02. `bulk_moderation_action` — unguarded `json.loads(request.body)` causes 500

**Severity:** HIGH
**Type:** correctness / robustness
**Effort:** small
**Validation status:** VALIDATED

**Evidence (verified):**
- `src/backend/apps/moderation/views/api_bulk.py:36` — `data = json.loads(request.body)` with NO try/except.
- `src/backend/apps/moderation/views/decorators.py:34-50` — `staff_required_api` decorator DOES enforce POST-only (line 47-48), but this guard runs BEFORE the function body. The unguarded `json.loads` is inside the function body.
- Confirmed: POST with body `"not-json"` produces `json.JSONDecodeError` → 500; POST with empty body produces `json.JSONDecodeError` → 500.

**Validation assessment:** The problem is real. The POST-only guard is in the decorator (not the view body), so a valid POST with malformed body still reaches the unguarded `json.loads` and crashes.

**Recommendation:** Wrap `json.loads(request.body)` at `api_bulk.py:36` in `try/except json.JSONDecodeError`. Both malformed JSON (`"not-json"`) and an empty body raise `json.JSONDecodeError`, so a single handler covers both cases — no separate `len(request.body)` check needed. Return `JsonResponse({"error": "Invalid JSON in request body"}, status=400)` (matches `staff_required_api` error style at `decorators.py:48`). Log at WARNING via the existing `logger` (`api_bulk.py:16`), excluding the raw body to avoid logging untrusted input. Add test cases in `test_priority_service.py` for malformed body and empty body — both expect HTTP 400 with `{"error": "Invalid JSON in request body"}`. Keep as-is.

---

### 03. Bot login-token claim crashes: `LoginToken` has no field `returning`

**Severity:** CRITICAL
**Type:** SPEC-DEVIATION (correctness)
**Effort:** medium
**Validation status:** VALIDATED — empirically confirmed

**Evidence (verified):**
- `src/telegram_bot/handlers/login.py:128` — `.update(telegram_id=telegram_id, returning=True)` on the `LoginToken` QuerySet.
- `src/backend/apps/users/models.py:117-156` — `LoginToken` model fields: `token_hash`, `telegram_id`, `created_at`, `expires_at`, `consumed_at`. No `returning` or `is_returning` field.
- Django 5.2.16 source verified: `QuerySet.update()` calls `query.add_update_values(kwargs)`, which calls `self.get_meta().get_field(name)` for each kwarg. For `name="returning"`, `get_field` raises `FieldDoesNotExist`. Source confirmed via `inspect.getsource(django.db.models.sql.query.UpdateQuery.add_update_values)`.
- **Empirical confirmation:** Executed `LoginToken.objects.filter(token_hash='abc').update(telegram_id=123, returning=True)` against installed Django 5.2.16, which raised `django.core.exceptions.FieldDoesNotExist: LoginToken has no field named 'returning'` (full traceback confirmed).
- Git history: commit `3bda47d` ("fix(auth): fix login-token claim TOCTOU race with UPDATE RETURNING") introduced `.update(telegram_id=telegram_id, returning=True).first()` — the author intended PostgreSQL's UPDATE...RETURNING but incorrectly passed `returning=True` as a kwarg to `.update()` (Django treats it as a field name, not a method call).
- **Secondary latent bug:** Even if `returning` were a valid field, `.update()` returns `int` (row count), not a QuerySet, so `.first()` at line 129 would raise `AttributeError: 'int' object has no attribute 'first'`. The `FieldDoesNotExist` fires first during query construction.
- Existing tests (`test_login_claim.py:80-104`, `test_claim_login_token.py:25-48`) test `handle_login_orm` and would fail with `FieldDoesNotExist`. They are marked `@pytest.mark.slow` and `@pytest.mark.integration`, so they likely don't run in default CI.
- Cross-ref: phases 02/04 (AUT-001/AUT-002) previously flagged this; it remains live.

**Validation assessment:** The crash is real, critical, and empirically confirmed. Every `/start login_<token>` deep-link crashes. The entire bot-based login flow is broken — no new user can log in via the bot.

**Recommendation:** Replace the broken `LoginToken.objects.filter(...).update(telegram_id=..., returning=True).first()` with raw SQL `UPDATE ... RETURNING` via `connection.cursor()`, aligned with the ENT-001 decision (File 01). Execute `UPDATE login_tokens SET telegram_id=%s WHERE token_hash=%s AND telegram_id IS NULL AND consumed_at IS NULL AND expires_at > %s RETURNING *` inside the existing `transaction.atomic()` block in `handle_login_orm` (`login.py:159`). This restores the intended single-query atomic claim with zero TOCTOU, matching the PostgreSQL-specific raw-cursor pattern in `apps/core/utils/advisory_lock.py`. Note: the current source at `login.py:112-130` (`_claim_login_token`) already implements this approach — verify it satisfies the ENT-001 specification. No new dependency required. Effort: trivial (verification) / medium (if reimplementation needed).

---

## Findings — Advisory

### 04. Dead code: `translate_to_russian` in `ad_create.py`

**Severity:** LOW
**Type:** BEST-PRACTICE (dead-code / maintainability)
**Effort:** trivial
**Validation status:** VALIDATED

**Evidence (verified):**
- `src/telegram_bot/handlers/ad_create.py:646` — `async def translate_to_russian(title: str, description: str) -> tuple[str, str]:` is defined.
- Grep across entire `src/` and `tests/` — **zero callers** of `translate_to_russian` found. Only the definition exists.
- The actual ad-creation flow (lines 457-462) uses `translate_all_languages()` instead (defined at line 771).
- Per dead-code policy: checked spec (`docs/01-spec/`), README, Pydantic models/`StrEnum`, and config templates — none reference `translate_to_russian`. Dead-code label is confirmed.

**Note:** The original finding uses Windows backslash path `src/telegram_bot\handlers\ad_create.py` in one evidence bullet, but the file path is valid.

**Validation assessment:** Genuinely dead code. Not documented as reserved/future. Safe to remove or document as reserved.

**Recommendation:** Delete `translate_to_russian` (`ad_create.py:646-659`) and its transitive-only helper `_do_translate` (`ad_create.py:639-643`). Evidence already confirmed: grep across `src/` and `tests/` shows zero callers; `_do_translate` is referenced only at its definition (line 639) and at `ad_create.py:651` (inside the dead `translate_to_russian`); no spec, README, StrEnum, or config-template references either symbol; neither is exported via `__all__`. The active translator `translate_all_languages` (line 771) uses the separate `_do_translate_to` (`ad_create.py:765`), so removing these has zero behavioral impact. After deletion: run `uv run ruff check src/telegram_bot/handlers/ad_create.py` then `uv run pytest src/backend/apps/telegram_bot/` to confirm no regressions. No migration needed. Keep as-is.

---

### 05. Ad-creation translator lacks circuit breaker (15s timeout is excessive)

**Severity:** MEDIUM
**Type:** BEST-PRACTICE (reliability / resilience)
**Effort:** medium
**Validation status:** VALIDATED with overlap note

**Evidence (verified):**
- `src/telegram_bot/handlers/ad_create.py:771-792` — `translate_all_languages()` (the ACTUAL function used in ad-creation, lines 457-462) uses `asyncio.wait_for(..., timeout=15.0)` with `except Exception: return text` fallback — no circuit breaker.
- `src/telegram_bot/handlers/ad_create.py:648-655` — `translate_to_russian()` uses the same `timeout=15.0` pattern — no circuit breaker. **However, this function is dead code** (see Finding 04). The active function `translate_all_languages` still has the same issue.
- `_do_translate` (line 639) and `_do_translate_to` (line 765) call `deep_translator.GoogleTranslator` synchronously via `asyncio.to_thread`.
- The bot runs as a single polling process — a 15-second timeout blocks the entire event loop.

**Validation assessment:** The problem is real for the active `translate_all_languages()` function. The 15s timeout is excessive for a bot polling process. Without a circuit breaker, sustained Google Translate outages cause every user's message to wait the full 15s.

**Dependency:** Finding 04 (remove dead `translate_to_russian`) is a prerequisite cleanup. The active function `translate_all_languages()` still needs hardening regardless.

**Recommendation:** Reduce timeout to 3-5s; add circuit breaker (open after 3 failures, 60s cooldown). Keep as-is.

---

### 06. Search-side vs ad-creation translator — inconsistent resilience

**Severity:** MEDIUM
**Type:** BEST-PRACTICE (advisory / consistency)
**Effort:** medium
**Validation status:** VALIDATED

**Evidence (verified):**
- Search translator (`src/backend/apps/search/services/query_translator.py`):
  - `TranslationCircuitBreaker` class (lines 29-83) — opens after 3 failures, 60s cooldown, half-open recovery. Verified.
  - `TRANSLATION_TIMEOUT_SECONDS = 0.5` (line 26) — 500ms timeout via `future.result(timeout=...)`. Verified.
  - Fallback to original query on failure (lines 119-124). Verified.
  - In-process LRU cache (`translate_cached`, line 128). Verified.
- Ad-creation translator (`src/telegram_bot/handlers/ad_create.py:771-792`):
  - 15s timeout (line 785). Verified.
  - No circuit breaker. Verified.
  - No caching. Verified.

**Validation assessment:** Two translators performing similar Google Translate work with vastly different resilience profiles. The asymmetry is real and increases maintenance risk.

**Recommendation:** Consolidate into a single `TranslationService` with unified circuit-breaker + timeout policy. Medium ROI — reduces code duplication but adds abstraction. Assess whether shared service is warranted at project scale. Keep as-is.

---

### 07. `login_status` view logs `telegram_id` in plaintext

**Severity:** MEDIUM
**Type:** BEST-PRACTICE (security / info-leak)
**Effort:** small
**Validation status:** VALIDATED with extension

**Evidence (verified):**
- `src/backend/apps/users/views/consent.py:236` — `logger.info(f"Login token {token_hash[:8]} consumed by telegram_id={token.telegram_id}")`. Verified.
- `src/backend/apps/users/views/consent.py:254` — `logger.info(f"Web session established for user {user.id} (telegram_id={token.telegram_id})")`. Verified.
- `consent.py:242` — `logger.error(f"User not found for telegram_id={token.telegram_id}")`. **Additional instance not cited in original finding.**
- `consent.py:247` — `logger.warning(f"Login denied for telegram_id={token.telegram_id}: banned")`. **Additional instance not cited in original finding.**
- Token issuance (line 176) correctly logs only hash prefix. Verified.

**Validation assessment:** The problem is real. `telegram_id` is logged at INFO/ERROR/WARNING levels across 4 log statements in `login_status`. Combined with token hash prefixes, this enables correlation of login attempts to specific Telegram users over time in log aggregators.

**Recommendation:** Replace `telegram_id` with internal `user.id` in log statements. Log `telegram_id` only at DEBUG level. Apply PII redaction filter. Keep as-is.

---

### 08. `BOT_TOKEN` build-time placeholder baked into Dockerfile

**Severity:** HIGH
**Type:** SPEC-DEVIATION (security / misconfiguration)
**Effort:** small
**Validation status:** VALIDATED

**Evidence (verified):**
- `docker/Dockerfile:70` — `ENV BOT_TOKEN=1234567890:build-placeholder-do-not-use-in-production`. Verified.
- `src/backend/config/settings/base.py:49` — `BOT_TOKEN = env("BOT_TOKEN", default="")`. Verified (empty default; settings expects runtime env).
- The placeholder appears in a Docker image layer, visible via `docker history`.

**Validation assessment:** The problem is real. If `BOT_TOKEN` is not set at runtime, the bot silently uses the placeholder, which looks like a credential in tooling. The settings empty default is the correct pattern (fail-closed).

**Recommendation:** Remove the `ENV BOT_TOKEN=...` line from Dockerfile. Let runtime provide `BOT_TOKEN` via secrets/env. The bot should validate token presence at startup. Keep as-is.

---

### 09. nginx `/static/` `add_header` drops inherited security headers

**Severity:** HIGH
**Type:** SPEC-DEVIATION (security)
**Effort:** trivial
**Validation status:** VALIDATED

**Evidence (verified):**
- `docker/nginx/nginx.conf:37-40` — server-level `add_header`: HSTS, `X-Content-Type-Options nosniff`, `X-Frame-Options DENY`. Verified.
- `docker/nginx/nginx.conf:48-57` — `/static/` location block has `add_header Cache-Control "public, immutable"` at line 57. Verified.
- nginx `add_header` inheritance rule: any `add_header` in a location block overrides ALL inherited `add_header` directives from parent blocks. The `/static/` location's single `add_header Cache-Control` drops HSTS, nosniff, and X-Frame-Options. Verified (standard nginx behavior).
- Spec at `docs/01-spec/architecture-structure.md:255` claims "Security headers (all responses): X-Content-Type-Options: nosniff, X-Frame-Options: DENY, Content-Security-Policy: ..." — the `/static/` location violates this.

**Validation assessment:** The problem is real. Static assets are served without nosniff, X-Frame-Options, and HSTS.

**Recommendation:** Re-declare all security headers inside the `/static/` location block. Keep as-is.

---

### 10. CSP only applied on `/protected-media/` — spec over-claims "all responses"

**Severity:** MEDIUM
**Type:** SPEC-DEVIATION
**Effort:** medium
**Validation status:** VALIDATED

**Evidence (verified):**
- `docker/nginx/nginx.conf:37-40` — server-level `add_header` directives: HSTS, nosniff, X-Frame-Options. NO CSP. Verified.
- `docker/nginx/nginx.conf:78` — CSP header ONLY in `/protected-media/` location. Verified.
- `docs/01-spec/architecture-structure.md:255` — spec claims: "Security headers (all responses): ... Content-Security-Policy: default-src 'none'; img-src 'self' data:; object-src 'none'". Verified.
- `docs/ops/docker-deployment.md:546-550` — spec claims: "All responses include: ... Content-Security-Policy: default-src 'none'; img-src 'self' data:; object-src 'none'". Verified.
- Main HTML, `/static/`, `/media/`, `/login/`, `/search/`, `/health/`, `/` all serve WITHOUT CSP. Verified from nginx.conf.

**Validation assessment:** Genuine SPEC-DEVIATION. Spec documents CSP on all responses, but implementation only applies it to `/protected-media/`. CSP on HTML responses is the highest-value place to enforce it. Since broader CSP coverage is the more secure configuration (docs > code), this remains SPEC-DEVIATION per validation rules.

**Recommendation:** Expand CSP to all responses via server-level `add_header Content-Security-Policy`. Test in staging (reporting-only mode) first to avoid breaking inline scripts/styles. Keep as-is.

---

### 11. Locmem cache used for rate limiting — not shared across processes

**Severity:** MEDIUM
**Type:** BEST-PRACTICE (advisory / reliability)
**Effort:** medium
**Validation status:** VALIDATED with evidence corrections

**Evidence (verified, with corrections):**
- `src/backend/config/settings/base.py:215-219` — `CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}`. Verified.
- `src/backend/apps/search/services/rate_limit.py:11` — uses `from django.core.cache import cache`. Verified. **Original finding cited line 16; actual is line 11.**
- `src/backend/apps/core/utils/cache.py:9` — uses `from django.core.cache import cache` for ModerationCriteria caching (5-min TTL via `CRITERIA_CACHE_TTL = 300`). Verified.
- `src/backend/apps/moderation/services/auto_moderation.py:15-19` — imports `get_cached_criteria`, `set_cached_criteria`, `invalidate_criteria_cache` from `apps.core.utils.cache`. Verified.
- **CORRECTION:** The finding cites `src/backend/apps/moderation/services/priority.py` as using cache, but `PriorityService` (read at 82 lines) does NOT import or use `django.core.cache`. It queries `AdModerationPriority` via ORM directly. The moderation cache usage is in `auto_moderation.py`, not `priority.py`.
- **CORRECTION:** The finding says `docker-compose.yml` configures `CACHES` backend as locmem, but `docker-compose.yml` does NOT set `CACHES` env var. The LocMemCache configuration is in Django settings `base.py` (shared across ALL environments).
- **AMPLIFICATION:** `src/backend/config/settings/prod.py` does NOT override `CACHES` — production ALSO uses LocMemCache. This makes the finding more severe than described: it is not just a dev/test issue, production is affected too.
- `docs/01-spec/technical-specification.md:148` — spec confirms: "Rate-limited (30 req/min per IP via cache)". Verified.
- `docs/97-plans/phase-01-detailed.md:246` — "Redis recommended for Django cache (criteria caching)". Verified — Redis acknowledged as needed but not implemented.
- `docs/01-spec/decision-11-analysis.md:441` — "Cache backend in dev is LocMemCache (single-process); rate limiter works". Verified — acknowledged limitation in dev, but NOT overridden in prod.
- No Redis service in `docker-compose.yml` or `docker-compose.prod.yml`. Verified.

**Validation assessment:** Core finding is valid and **amplified**: production also uses LocMemCache (not overridden in `prod.py`). Cache is used by BOTH rate limiting (`rate_limit.py`) AND moderation criteria caching (`auto_moderation.py` via `cache.py`). The `priority.py` citation is incorrect.

**Recommendation:** Replace `LocMemCache` with Redis via `django-redis`, aligned with the ENT-003 decision (File 01). Add `django-redis` to `pyproject.toml`; configure `CACHES["default"]` with `django_redis.cache.RedisCache` and `REDIS_URL` in `base.py` (lines 217-221), overriding in `prod.py` if needed; add a `redis` service to `docker-compose.yml` and `docker-compose.prod.yml` wired into `web`, `bot`, and `scheduler`. Select Redis (not PostgreSQL-based cache) because `apps/lookups/services/cache_service.py:76` and `apps/categories/services/lookup_resolution.py:111` use `cache.delete_pattern` (a `django-redis`-specific API). Document the production requirement in `docs/99-agent/architecture.md`. File citation correction: cite `auto_moderation.py` and `cache.py`, not `priority.py`. Effort: medium.

---

### 12. `.env.docker` is git-tracked — secrets committed to repo

**Severity:** HIGH
**Type:** SPEC-DEVIATION (security / secrets-management)
**Effort:** trivial
**Validation status:** VALIDATED with evidence corrections

**Evidence (verified, with corrections):**
- `git ls-files -- .env.docker` outputs `.env.docker` — file IS tracked. Verified.
- `git check-ignore .env.docker` returns `False` (exit code 1) — file is NOT ignored. Verified.
- `.gitignore` lines 145-147: `.env`, `.env.dev`, `.env.local` — NO pattern covering `.env.docker`. Verified. No generic `.env*` glob; only specific filenames listed.
- `.env.docker` content: `DJANGO_SECRET_KEY=<generate-with-django-secret-key-generator>` (placeholder), `POSTGRES_USER=bazuna_user`, `POSTGRES_DB=bazuna_db`, `POSTGRES_PASSWORD=your-password` (placeholder), `BOT_TOKEN=` (empty), `ADMIN_PASSWORD=` (empty).
- **CORRECTION:** The finding claims `.env.docker` "contains real-looking secrets." The values are **placeholders/templates**, not actual secrets (e.g., `your-password`, `<generate-with-django-secret-key-generator>`, empty `BOT_TOKEN`). The risk is that this tracked file normalizes committing env files and developers may replace placeholders with real secrets.
- **CORRECTION:** The finding cites `docs/00-overview/doc-maintenance-rules.md` as stating `.env` files should be gitignored. This document does NOT mention `.env` files — it is about documentation maintenance rules (frontmatter, file placement, etc.). The actual policy reference is `docs/97-plans/phase-01-detailed-deployment.md:279` which states: ".env.docker not committed" with "Verify .gitignore".
- `docs/ops/docker-deployment.md:78` table confirms: `.env.docker` → "Tracked in git: Yes (template with placeholder values)". Verified.
- There is NO `.env.docker.example` file (only `.env.example` and `.env.dev.example` exist). Verified.
- `src/.env` exists (untracked) — it is a copy of `.env.dev.example` with `DATABASE_URL=postgres://bazuna_user:<dev-db-password>@db:5432/bazuna_db` using Docker hostname `db`.

**Validation assessment:** Core finding is valid — `.env.docker` is tracked in git and not in `.gitignore`, violating the project's own deployment plan (`phase-01-detailed-deployment.md:279`). The "real-looking secrets" claim is overstated (placeholders), but the structural issue is real.

**Recommendation:** (1) Add `.env.docker` to `.gitignore`. (2) `git rm --cached .env.docker`. (3) Use existing `.env.example` as template or create `.env.docker.example`. (4) Rotate any secrets ever committed (low risk — values are placeholders). Keep as-is with evidence corrections noted.

---

### 14. Moderation bulk API leaks raw exception strings to clients

**Severity:** LOW
**Type:** BEST-PRACTICE (info-leak / UX)
**Effort:** trivial
**Validation status:** VALIDATED

**Evidence (verified):**
- `src/backend/apps/moderation/views/api_bulk.py:56-59` — `except Exception as e:` then `errors.append({"id": ad_id, "error": str(e)})` returns full exception message to client. Verified. **Original finding cited lines 43-44; actual is lines 56-59.**
- The `errors` list is returned in `JsonResponse(results)` at line 60. Verified.

**Validation assessment:** The problem is real. Internal exception strings (e.g., `Ad matching query does not exist`, `ValueError: Unknown action: delete`) are sent verbatim to admin clients. While auth-gated, this leaks implementation details.

**Recommendation:** Return sanitized generic error to client (e.g., `"Processing failed"`), log full `str(e)` server-side via `logger.error(...)`. Keep as-is.

---

## Cross-Finding Analysis

### Same root cause / merge candidates

| Findings | Relationship | Decision |
|----------|-------------|----------|
| 04 + 05 | Finding 05 cites `translate_to_russian()` (dead code, Finding 04) as evidence. The active function `translate_all_languages()` has the same issue. | NOT merged. Distinct concerns: 04 = dead code removal, 05 = resilience pattern. Finding 05 remains valid for the active function. |
| 05 + 06 | Finding 06 consolidation recommendation subsumes Finding 05 circuit-breaker fix. | NOT merged. 05 is about missing circuit breaker pattern; 06 is about inconsistency between two translators. Shared root cause but different scope. Addressing 06 naturally resolves 05. |
| 08 + 12 | Both are secrets-management issues: Dockerfile placeholder vs. tracked env file. | NOT merged. Different vectors (build-time vs. VCS), different remediation. |
| 09 + 10 | Both are nginx security header issues in the same config file. | NOT merged. 09 = add_header inheritance dropping headers on `/static/`; 10 = CSP scope too narrow. Different root causes. |

### Cross-phase conflicts

None detected. The findings file notes Finding 13 ("no HTTPS redirect") was falsified — nginx has HTTP-to-HTTPS redirect at `nginx.conf:27-31` (line 30: `return 301 https://$host$request_uri`). This is consistent with the nginx config. No conflicts with other phases.

### Dependency chains

1. **Finding 03 is BLOCKING** — the bot login flow is completely broken (`FieldDoesNotExist` on every `/start login_<token>`). No bot-related testing or features can work until fixed.
2. **Finding 04 is prerequisite for Finding 05** — `translate_to_russian()` (dead code cited in Finding 05) should be removed first. The active function `translate_all_languages()` still needs hardening regardless.
3. **Finding 05 is naturally addressed by Finding 06** — consolidating into a single `TranslationService` resolves both the missing circuit breaker (05) and the inconsistency (06) simultaneously.
4. **Findings 09 + 10 have rollout ordering** — both touch nginx config. Apply together to avoid intermediate states where headers are partially correct.
5. **No circular dependencies detected.**

---

## Rollout Safety Assessment

| Finding | Rollout risk | Dependencies | Notes |
|---------|-------------|--------------|-------|
| 01 | Low | None | Trivial; backward-compatible (GET was a bug) |
| 02 | Low | None | Returns 400 instead of 500 |
| 03 | High (blocking) | None | Raw SQL `UPDATE ... RETURNING` via `connection.cursor()` per ENT-001; verify current `_claim_login_token` (`login.py:112-130`) matches specification |
| 04 | Low | None | No callers; safe to delete |
| 05 | Medium | 04 (cleanup) | Circuit breaker; test in isolation |
| 06 | Medium | 05 | Consolidation; assess at project scale before abstracting |
| 07 | Low | None | Log edits only |
| 08 | Low | None | Remove Dockerfile ENV line |
| 09 | Low | None | Re-declare headers in `/static/` |
| 10 | Medium | None | CSP expansion may break inline scripts; test in staging (reporting-only mode first) |
| 11 | Medium | None | Requires Redis infrastructure (not yet deployed) |
| 12 | Low | None | `git rm --cached` + `.gitignore`; no code impact |
| 14 | Low | None | Sanitize error response |

### Fragile insertion points

- **Finding 01:** Adding `@require_POST` above `@staff_required` is safe. `@require_POST` should be outermost so non-POST requests get 405 before the staff check.
- **Finding 10:** Expanding CSP to all responses requires testing against existing inline scripts/styles in templates. A too-restrictive CSP could break the UI. Recommend staging deployment with reporting-only CSP first.
- **Finding 03:** The correct fix uses raw SQL `UPDATE ... RETURNING` via `connection.cursor()` (ENT-001), not the minimal `remove returning=True + separate SELECT` workaround, to avoid reintroducing the TOCTOU race that commit `3bda47d` attempted to fix. Verify the current `_claim_login_token` implementation (`login.py:112-130`) matches the ENT-001 specification before assuming the issue is resolved.

---

## Validation Summary

| Action | Count | Details |
|--------|-------|---------|
| Validated (unchanged) | 7 | 01, 02, 04, 06, 08, 09, 10 |
| Validated with evidence corrections | 6 | 03 (empirical confirmation), 05 (overlap with 04), 07 (extension), 11 (file/line corrections), 12 (overstatement corrections), 14 (line number correction) |
| Reclassified | 0 | — |
| Merged | 0 | — |
| Rejected | 0 | — |

**Total findings validated: 13** (Findings 01-12, 14; Finding 13 was falsified during audit and is not a finding.)

### Findings with evidence corrections

| ID | Correction | Detail |
|----|-----------|--------|
| 03 | Empirical confirmation added | Directly reproduced `FieldDoesNotExist` against Django 5.2.16; identified secondary `.first()` on int bug; identified commit that introduced the bug |
| 05 | Overlapping with Finding 04 | Finding 05 cites `translate_to_russian()` (dead code per Finding 04); active function `translate_all_languages` has the same issue |
| 07 | Extension | Original finding cited lines 236 and 254; verified two additional instances at lines 242 (ERROR) and 247 (WARNING) also log telegram_id |
| 11 | File/line corrections | `rate_limit.py` line 11 (not 16); `priority.py` does NOT use cache; locmen config in `base.py:215-219` (not docker-compose); `prod.py` does NOT override CACHES |
| 12 | Overstatement corrections | `.env.docker` contains placeholders, not real secrets; `doc-maintenance-rules.md` does NOT mention env files |
| 14 | Line number correction | Error leak at `api_bulk.py:56-59`, not lines 43-44 |

### Rollout priority order

1. **Finding 03** (CRITICAL, blocking) — fix login-token claim crash first
2. **Finding 01** (CRITICAL) — add POST-only guard to `approve_ad`
3. **Finding 08** (HIGH) — remove BOT_TOKEN placeholder from Dockerfile
4. **Finding 09** (HIGH) — re-declare security headers in nginx `/static/`
5. **Finding 12** (HIGH) — gitignore + untrack `.env.docker`
6. **Finding 02** (HIGH) — guard `json.loads` in bulk API
7. **Finding 11** (MEDIUM) — requires Redis infrastructure (deferred to infrastructure phase)
8. **Finding 10** (MEDIUM) — CSP scope (test in staging first)
9. **Finding 07** (MEDIUM) — log sanitization
10. **Finding 06** (MEDIUM) — translator consolidation
11. **Finding 05** (MEDIUM) — circuit breaker (naturally resolved by 06)
12. **Finding 04** (LOW) — dead code removal (prerequisite for 05)
13. **Finding 14** (LOW) — error sanitization

---

*This validated report is self-contained. All evidence references are to the current git HEAD state as of validation date 2026-08-15. No production code was modified during this validation.*


