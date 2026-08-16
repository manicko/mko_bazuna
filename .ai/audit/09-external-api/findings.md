# Phase 09 Audit — External API Surface

**Phase scope:** `audit-external-api.md` (external integrations, web API, shared services, runtime behavior)
**Discovery period:** 2026-08-15
**Environment verified:** Docker available; test DB started on `127.0.0.1:5433` (postgres/postgres, db `mko_bazuna`); venv via `uv`.
**Status:** Complete — findings finalized.

---

## Methodology

- **Static discovery** across bot runtime (`src/telegram_bot/`), Django web API (`src/backend/apps/`), nginx TLS/headers, translation client, and shared services.
- **Runtime verification** via throwaway Django test probes against the test DB (probes deleted after capture; no production code modified).
- **Spec cross-check** against `docs/01-spec/`, `docs/99-agent/architecture.md`, and runtime `.env` files.
- Findings are grouped by risk: Mandatory (security / data loss / correctness) first, then Advisory. Each finding has severity, evidence (file/line), explanation, and effort estimate.

---

## Summary Table

| ID  | Title | Severity | Type | Effort |
|-----|-------|----------|------|--------|
| 01  | `approve_ad` and `reject_ad` accept GET requests — CSRF/state-change on GET | CRITICAL | correctness | trivial |
| 02  | `bulk_moderation_action` performs unguarded `json.loads(request.body)` — 500 on malformed/empty body | HIGH | correctness | small |
| 03  | Bot login-token claim crashes: `LoginToken` has no field `returning` (FieldDoesNotExist) | CRITICAL | correctness | medium |
| 04  | Dead code: `translate_to_russian` in `ad_create.py` is defined but never called | LOW | advisory | trivial |
| 05  | Ad-creation translator lacks circuit breaker (15s timeout is excessive, no short-circuit) | MEDIUM | reliability | medium |
| 06  | Search-side translator has circuit breaker + 500ms timeout; ad-creation has neither — inconsistency | MEDIUM | advisory | medium |
| 07  | `login_status` view logs `telegram_id` in plaintext to server logs | MEDIUM | security | small |
| 08  | `BOT_TOKEN` build-time placeholder baked into Dockerfile | HIGH | security | small |
| 09  | nginx `/static/` `add_header` drops inherited HSTS / nosniff / X-Frame-Options | HIGH | security | trivial |
| 10  | CSP only applied on `/protected-media/` — spec over-claims "all responses" | MEDIUM | spec-deviation | medium |
| 11  | Locmem cache used for rate limiting — not shared across gunicorn workers / bot | MEDIUM | advisory | medium |
| 12  | `.env.docker` is git-tracked — secrets committed to repo | HIGH | security | trivial |
| 14  | Moderation bulk API returns raw exception strings to clients | LOW | info-leak | trivial |

> Note: Finding 13 ("no HTTPS redirect") was investigated and **falsified** — nginx config has an HTTP?HTTPS redirect at `docker/nginx/nginx.conf:27-31`.

---

## Findings — Mandatory (security / data loss / correctness)

### 01. `approve_ad` accepts GET requests — state change on GET

**Severity:** CRITICAL
**Type:** correctness / CSRF
**Effort:** trivial

**Evidence:**
- `src/backend/apps/moderation/views/review.py:46-64` — `def approve_ad(request: HttpRequest, ad_id: int)`: calls `do_approve()` at line 61 unconditionally. No `if request.method != "POST"` guard or `@require_POST` decorator.
- `src/backend/apps/moderation/urls.py:15` — `path("approve/<int:ad_id>/", approve_ad, name="approve")`.
- Runtime probe confirmed: `GET /moderation/approve/<id>/` returned `302`, and `Ad.status` changed from its prior state to `published` immediately. Output: `APPROVE_GET_STATUS= 302`, `AD_STATUS_AFTER_GET= published`.
- Contrast: `reject_ad` (`review.py:87`) and `ban_user` (`review.py:119`) BOTH have `if request.method != POST` guards; only `approve_ad` is missing one.
- The docstring on `approve_ad` (line 49) claims "POST only" — a spec deviation with the code.

**Explanation:**
GET requests must be idempotent and side-effect-free. Approving an ad is a state-changing mutation. A GET-based approve path can be triggered by:
- Crawlers/scanners hitting `/moderation/approve/1`.
- CSRF via `<img src="https://site/moderation/approve/1">` embedded anywhere (Django's `CsrfViewMiddleware` does not protect GET).

**Recommendation (fix code):**
Add `@require_POST` (or `if request.method != "POST": return HttpResponseNotAllowed(["POST"])`) to `approve_ad`. `reject_ad` and `ban_user` already have equivalent guards. This is trivial and mandatory.

---

### 02. `bulk_moderation_action` — unguarded `json.loads(request.body)` causes 500

**Severity:** HIGH
**Type:** correctness / robustness
**Effort:** small

**Evidence:**
- `src/backend/apps/moderation/views/api_bulk.py:36` — `data = json.loads(request.body)` with no try/except.
- Runtime probe confirmed:
  - `test_malformed_json_500`: `POST` with body `"not-json"` ? `500` (`JSONDecodeError: Expecting value: line 1 column 1 (char 0)`).
  - `test_empty_body_500`: `POST` with empty body ? `500` (`JSONDecodeError: Expecting value: line 1 column 1 (char 0)`).
- Stacktrace shows uncaught `json.decoder.JSONDecodeError` propagating through `api_bulk.py:36` ? Django's error handler ? 500.

**Explanation:**
The endpoint returns 500 on malformed input. While auth-gated (`staff_required_api`), this still produces noisy 500s in logs/Sentry and degrades UX for legitimate admin tooling. It should return a 400 Bad Request.

**Recommendation (fix code):**
Guard the parse and return a 400:
```python
try:
    data = json.loads(request.body)
    if not isinstance(data, dict):
        raise ValueError("Request body must be a JSON object")
except (json.JSONDecodeError, ValueError) as e:
    return JsonResponse({"error": f"Invalid JSON: {e}"}, status=400)
```

---

### 03. Bot login-token claim crashes: `LoginToken` has no field `returning`

**Severity:** CRITICAL
**Type:** correctness (previously logged in phases 02/04, still unfixed)
**Effort:** medium

**Evidence:**
- `src/telegram_bot/handlers/login.py:128` — `.update(telegram_id=telegram_id, returning=True)` on the `LoginToken` QuerySet.
- `src/backend/apps/users/models.py:117-156` — `LoginToken` model fields are: `token_hash`, `telegram_id`, `created_at`, `expires_at`, `consumed_at`. There is **no** `returning` or `is_returning` field.
- The `returning=True` argument to `.update()` causes Django to raise `FieldDoesNotExist: LoginToken has no field named 'returning'` because `.update()` validates field names against the model schema.
- This crash occurs inside `handle_login_orm() -> _handle()` (sync_to_async wrapper), triggered by the bot's `/start login_<token>` command handler.
- Cross-ref: phases 02/04 (AUT-001/AUT-002) previously flagged this; it remains live.

**Explanation:**
Every new user who clicks a login token claim in Telegram triggers this crash. The entire bot-based login flow is broken — no new user can ever log in via the bot. This is a total login-flow failure.

**Recommendation (fix code):**
Either:
- (Minimal) Remove `returning=True` from the `.update()` call at `login.py:128` if the field is not needed, OR
- (Correct) Add an `is_returning = models.BooleanField(default=False)` field to `LoginToken` via migration and change the `.update()` to `is_returning=True`, then use it for analytics.

Since the `returning` flag appears to be analytics (not functional), removing the erroneous kwarg is the lowest-risk fix.

---

## Findings — Advisory

### 04. Dead code: `translate_to_russian` in `ad_create.py`

**Severity:** LOW
**Type:** dead-code / maintainability
**Effort:** trivial

**Evidence:**
- `src/telegram_bot\handlers\ad_create.py:646` — `async def translate_to_russian(title: str, description: str) -> tuple[str, str]:` is defined.
- Grep search found **zero** callers of `translate_to_russian` anywhere in `src/` or `tests/`.
- The actual ad-creation flow (lines 457–472) uses `translate_all_languages()` instead (defined at line 771).
- `translate_to_russian` is a standalone async function that wraps `_do_translate` with a 15s timeout and `asyncio.to_thread`, but is never invoked.

**Explanation:**
Unreachable dead code. It is not documented elsewhere as reserved/future, so it is genuinely dead. It confuses readers and adds maintenance surface.

**Recommendation (investigate):**
Per dead-code policy, do not delete outright. Confirm `translate_to_russian` is not referenced by tests or external callers (grep confirmed zero references). If truly unused, remove it; if intended for a future ad-creation path, document it as reserved.

---

### 05. Ad-creation translator lacks circuit breaker (15s timeout is excessive)

**Severity:** MEDIUM
**Type:** reliability / resilience
**Effort:** medium

**Evidence:**
- `src/telegram_bot/handlers/ad_create.py:648-655` — `translate_to_russian()` uses `asyncio.wait_for(asyncio.to_thread(_do_translate, text), timeout=15.0)` with `except Exception: return text` fallback. It has a timeout and fallback, but **no circuit breaker**.
- `src/telegram_bot/handlers/ad_create.py:771-792` — `translate_all_languages()` (the actual function used) also uses `timeout=15.0` with `except Exception: return text` — same pattern, no circuit breaker.
- The bot runs as a single polling process. A 15-second timeout per translation call blocks the entire event loop. If Google Translate is slow/throttled, every user's message queues behind it.
- `_do_translate` (line 639) and `_do_translate_to` (line 765) call `deep_translator.GoogleTranslator` synchronously, offloaded to a thread via `asyncio.to_thread`.

**Explanation:**
A 15s timeout is very long for a bot polling process. Without a circuit breaker, a sustained Google Translate outage means every user's ad-creation request still waits the full 15s before falling back, rather than short-circuiting after the first few failures.

**Recommendation (best-practice):**
- Reduce the timeout from 15s to 3-5s (matching typical external API latency budgets).
- Add a circuit breaker (open after 3 consecutive failures, 60s cooldown) — see the search-side translator as a reference pattern.
- Consider moving translation to a background task with async user notification, rather than blocking the FSM dialog.

---

### 06. Search-side vs ad-creation translator — inconsistent resilience

**Severity:** MEDIUM
**Type:** advisory / consistency
**Effort:** medium

**Evidence:**
- Search translator (`src/backend/apps/search/services/query_translator.py`):
  - `TranslationCircuitBreaker` class (lines 29-83) — opens after 3 consecutive failures, 60s cooldown, half-open recovery.
  - `TRANSLATION_TIMEOUT_SECONDS = 0.5` (line 26) — 500ms timeout via `future.result(timeout=0.5)`.
  - Fallback to original query on failure (`except` block, lines 119-124).
  - In-process LRU cache for repeated queries (`translate_cached`, line 129).
- Ad-creation translator (`ad_create.py:648-655`, `771-792`):
  - 15s timeout (30× longer than search).
  - No circuit breaker.
  - No caching.

**Explanation:**
Two translators performing similar Google Translate work with vastly different resilience profiles. This asymmetry increases the risk of future bugs and makes the system's failure modes unpredictable.

**Recommendation (best-practice):**
Consolidate into a single `TranslationService` class with a unified circuit-breaker + timeout policy, shared by both search and ad-creation paths. This reduces code duplication and ensures consistent failure behavior.

---

### 07. `login_status` view logs `telegram_id` in plaintext

**Severity:** MEDIUM
**Type:** security / info-leak
**Effort:** small

**Evidence:**
- `src/backend/apps/users/views/consent.py:236` — `logger.info(f"Login token {token_hash[:8]} consumed by telegram_id={token.telegram_id}")`.
- `src/backend/apps/users/views/consent.py:254` — `logger.info(f"Web session established for user {user.id} (telegram_id={token.telegram_id})")`.
- Note: token issuance (line 176) correctly logs only the hash prefix — `"Issued login token hash={token_hash[:8]}..."` — which is good practice.

**Explanation:**
`telegram_id` is a personally-identifying value in Telegram's context. Logging it at INFO level exposes it in all log aggregators and persisted log stores. Combined with token hash prefixes, this could enable correlation of login attempts to specific Telegram users over time.

**Recommendation (best-practice):**
Replace `telegram_id` with the internal `user.id` (or `User.pk`) in log statements. Log `telegram_id` only at DEBUG level (if needed for debugging), never at INFO. Apply a logging redaction filter for PII fields.

---

### 08. `BOT_TOKEN` build-time placeholder baked into Dockerfile

**Severity:** HIGH
**Type:** security / misconfiguration
**Effort:** small

**Evidence:**
- `docker/Dockerfile:70` — `ENV BOT_TOKEN=1234567890:build-placeholder-do-not-use-in-production`
- Settings reads: `src/backend/config/settings/base.py:49` — `BOT_TOKEN = env("BOT_TOKEN", default="")` (empty default).

**Explanation:**
A fake-but-realistic-looking token (`1234567890:...`) is baked into the Docker image layer. If a developer deploys without setting `BOT_TOKEN` at runtime, the bot will use the placeholder, which looks like a credential in tooling/inspection. It appears in `docker history` layer inspection and Dockerfile parsing tools.

**Recommendation (fix):**
Remove the `ENV BOT_TOKEN=...` line from the Dockerfile. Let the runtime provide `BOT_TOKEN` via secrets/env. The settings default of `""` (empty) is safer — the bot should refuse to start if no token is provided, not silently use a fake one.

---

### 09. nginx `/static/` `add_header` drops inherited security headers

**Severity:** HIGH
**Type:** security
**Effort:** trivial

**Evidence:**
- `docker/nginx/nginx.conf:37-40` — Server-level `add_header` directives: HSTS, `nosniff`, `X-Frame-Options: DENY` (comment at line 37 claims "applied to all responses").
- `docker/nginx/nginx.conf:48-57` — `/static/` location block uses `add_header Cache-Control "public, immutable";` at line 57.
- In nginx, any `add_header` directive in a location block **overrides all** `add_header` directives from parent blocks. So the `/static/` location's single `add_header Cache-Control` drops HSTS, nosniff, and X-Frame-Options for all static asset responses.

**Explanation:**
Static assets (CSS, JS) are served without `nosniff`, `X-Frame-Options: DENY`, and HSTS. This is a security regression — an attacker who can influence static content loses the protective headers.

**Recommendation (fix):**
Re-declare the security headers inside the `/static/` location block, or restructure so `add_header` is only set at the server level and `/static/` uses `expires` + `add_header` with all needed headers re-listed. The simplest fix: repeat the three security `add_header` lines inside the `/static/` location.

---

### 10. CSP only on `/protected-media/` — spec over-claims "all responses"

**Severity:** MEDIUM
**Type:** spec-deviation
**Effort:** medium

**Evidence:**
- `docker/nginx/nginx.conf:78` — CSP header only in the `/protected-media/` location block: `add_header Content-Security-Policy "default-src 'none'; img-src 'self' data:; object-src 'none'" always;`
- `docker/nginx/nginx.conf:37` — Comment says "Security headers (applied to all responses)" but CSP is NOT among the server-level headers (only HSTS, nosniff, X-Frame-Options are server-level).
- The main HTML responses, `/static/`, `/media/`, `/login/`, `/search/`, `/health/`, and `/` locations all serve content WITHOUT any CSP header.

**Explanation:**
Documentation claims broader CSP coverage than is actually deployed. CSP on HTML responses is the highest-value place to enforce it (to prevent XSS on user-facing pages). Restricting it to `/protected-media/` only protects a narrow internal path.

**Recommendation:**
Either (a) expand CSP to all responses per the spec by adding a server-level `add_header Content-Security-Policy` directive, or (b) update the comment/docs to accurately state CSP scope is limited to `/protected-media/`. Recommend (a) with a sane default CSP (e.g., `default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data: https:; object-src 'none'`).

---

### 11. Locmem cache used for rate limiting — not shared across processes

**Severity:** MEDIUM
**Type:** advisory / reliability
**Effort:** medium

**Evidence:**
- `src/backend/apps/search/services/rate_limit.py:16` — uses Django's `django.core.cache` for rate-limit counters.
- `src/backend/apps/moderation/services/priority.py` — also uses cache keys for moderation priority caching.
- `docker-compose.yml` (dev/test) configures `CACHES` backend as `locmem`.
- Architecture: gunicorn (sync, multi-worker) + bot process share one DB but **not** locmem cache. Each gunicorn worker and the bot process has its own in-memory cache.

**Explanation:**
Locmem cache is per-process. Rate-limit counters and cached moderation priorities are invisible across workers and the bot process. This means:
- Rate limits are effectively bypassed when a request hits a different worker (the counter starts fresh).
- Moderation priority cache is duplicated/inconsistent across workers, leading to stale priority calculations.

**Recommendation (best-practice):**
Use Redis (or the shared PostgreSQL cache) for rate limiting in production. Locmem is acceptable for dev-only. Document this limitation in `docs/99-agent/architecture.md` and ensure production `docker-compose.prod.yml` uses Redis.

---

### 12. `.env.docker` is git-tracked — secrets committed to repo

**Severity:** HIGH
**Type:** security / secrets-management
**Effort:** trivial

**Evidence:**
- `git ls-files -- .env.docker` ? outputs `.env.docker` (file IS tracked).
- `git check-ignore .env.docker` ? returns `False` (file is NOT ignored).
- `.gitignore` lists `.env`, `.env.dev`, `.env.local` but has NO pattern covering `.env.docker` — the generic `.env*` pattern is not present; only specific filenames are listed.
- `.env.docker` contains real-looking secrets: DB credentials, `SECRET_KEY`, `BOT_TOKEN`, etc.

**Explanation:**
Secrets committed to version control are a critical exposure vector. Even if rotated, git history retains them indefinitely. This violates the project's own documented rules (`docs/00-overview/doc-maintenance-rules.md` states `.env` files should be gitignored).

**Recommendation (fix):**
1. Add `.env.docker` to `.gitignore`.
2. Remove it from git tracking: `git rm --cached .env.docker`.
3. Add a `.env.docker.example` template file instead.
4. Rotate any secrets that were ever committed.

---

### 14. Moderation bulk API leaks raw exception strings to clients

**Severity:** LOW
**Type:** info-leak / UX
**Effort:** trivial

**Evidence:**
- `src/backend/apps/moderation/views/api_bulk.py:43-44` — `errors.append({"id": ad_id, "error": str(e)})` returns the full exception message to the client.

**Explanation:**
Internal exception strings (e.g., `Ad matching query does not exist`, `ValueError: Unknown action: delete`, or database error text) are sent verbatim to admin clients. While auth-gated, this leaks implementation details that could aid an attacker in understanding system internals if an admin account is compromised.

**Recommendation (best-practice):**
Return a sanitized, generic error message to the client (e.g., `{"id": ad_id, "error": "Processing failed"}`) and log the full `str(e)` server-side only via `logger.error(...)`.

---

## Doc Updates Needed

The following documentation should be updated to reflect reality:

1. **CSP scope** (`docs/01-spec/` security section): CSP is only applied to `/protected-media/`, NOT to all responses as currently documented. Either expand implementation to match docs, or update docs to state the actual scope.
2. **nginx security header inheritance** (`docs/99-agent/architecture.md`): Document that `/static/` `add_header Cache-Control` overrides server-level security headers — recommend re-declaring them in the location block.
3. **Rate-limiting backend** (`docs/99-agent/architecture.md`): Document that locmem cache is used and is not shared across gunicorn workers / bot process; Redis is required for production consistency.
4. **`.env` file policy** (`docs/00-overview/doc-maintenance-rules.md`): Clarify that `.env.docker` must NOT be git-tracked; only `.env.example` templates should be committed. Add `.env*` glob or explicit `.env.docker` to `.gitignore`.
5. **HTTP method constraints** (`docs/01-spec/` moderation API): Document that `approve_ad`, `reject_ad`, `ban_user` are POST-only endpoints.

---

## Cross-Phase References

- **Finding 03** (login token claim crash): Cross-references phases 02 and 04 (AUT-001/AUT-002). This is the same `returning` field crash, still open.
- **Finding 12** (`.env.docker` tracked): Cross-references CFG-003 (secrets in version control) from earlier phases.

---

*Findings file generated per Phase 09 task. No production code was modified during this audit.*
