---
phase: "09"
phase_name: "External Integrations & API"
date: "2026-09-12"
auditor: "Executor (subagent)"
mode: "problems-only"
id_prefix: "EXT"
report_status: "draft"
severity_taxonomy: ".kilo/commands/audit/phases/09-audit-external-api.md#severity-taxonomy"
---

# Audit Findings — External Integrations & API

## Executive Summary

Seven findings were identified across the bot runtime, translation client, login-token flow, moderation API, and secrets hygiene. Two are MEDIUM severity (a stale docstring misrepresenting data-flow to a third-party translator, and a missing transient-error handler in the daily alert digest command), five are LOW severity. No CRITICAL or HIGH issues were found.

## Scope & Methodology

**Scope:** External integration boundaries — the async bot process (polling runtime, update-dedup + DB-connection middleware, login deep-link handler), the Google Cloud Translation client (timeout/retry/circuit-breaker/cache), the login-token issuance→claim→polling lifecycle (web + bot), the moderation bulk-action JSON API endpoint, the nginx reverse proxy (TLS, headers, rate-limit zones), and secrets sourcing (`.env.docker` bind-mount, env guards). Bot uses long-polling (`dp.run_polling`), not webhooks — no webhook secret to verify. The only REST-like endpoint is `POST /moderation/api/v1/bulk-action/` (staff-only).

### Runtime Verification

| R# | Check | Method | Result |
|----|-------|--------|--------|
| R-01 | Bot token never logged in production code | grep `settings.BOT_TOKEN` usages + read `main.py:36-41` | PASS |
| R-02 | GOOGLE_TRANSLATE_API_KEY never logged | grep `GOOGLE_TRANSLATE_API_KEY` + read `translation.py:149-157` | PASS |
| R-03 | Translation client has timeout/retry/circuit-breaker/fallback | read `translation.py` lines 34–104, 160–254 | PASS |
| R-04 | Login token: SHA-256 hash stored, raw token not persisted | read `consent.py:303-309` + `LoginToken` model | PASS |
| R-05 | Login token: atomic claim via UPDATE...RETURNING | read `handlers/login.py:122-155`, `consent.py:405-410` | PASS |
| R-06 | Login token: 5-min expiry enforced | read `consent.py:309` + `LoginToken` model | PASS |
| R-07 | `translate_cached` (bs→ru) dead code — only test references | grep `translate_cached` across `src/` | PASS (confirmed dead code) |
| R-08 | `send_alerts.py` missing transient exception handling | read `send_alerts.py:167-173` + compare `immediate_alerts.py:207-237` | PASS (confirmed gap) |
| R-09 | Stale docstring in `consent.py` vs `translation.py` / spec | cross-reference docstrings + `technical-specification.md:119` | PASS (confirmed discrepancy) |
| R-10 | Test cert private keys committed to repo | `git ls-files` + read `.gitignore` | PASS (confirmed tracked) |
| R-11 | Login rate limit on web side | read `login_rate_limit.py` + `contact_rate_limit.py` | PASS (10/min, 60/10min) |
| R-12 | Bot-side login handler rate limit | read `handlers/login.py:34-119` + `services/rate_limit.py` | PASS (confirmed absent) |
| R-13 | Moderation API auth + validation | read `api_bulk.py` + `decorators.py` + `schemas.py` | PASS (staff-only, Pydantic-validated) |
| R-14 | No hardcoded secrets in repo | grep for token/API-key patterns | PASS |
| R-15 | No REST/DRF API surface beyond moderation bulk endpoint | read `config/urls.py` | PASS |

**Tools used:** `git ls-files`, `grep` (semantic), Docker test suite (`docker compose ... run --rm test`), `ruff` (not needed — no code changes), file inspection.

**Assumptions:** Production uses Redis-backed cache (LocMemCache only in dev/test); PostgreSQL 18; Django 5.2; bot runs under CPython; `.env.docker` bind-mounted read-only at container runtime; test certs in `.tmp/nginx-test-certs/` are local mkcert-generated.

## Findings Summary

| ID | Title | Severity | Status | Category |
|----|-------|----------|--------|----------|
| EXT-001 | Stale consent.py docstring falsely claims search queries are sent to Google Translate | MEDIUM | Open | Documentation / Data-flow accuracy |
| EXT-002 | send_alerts daily digest command crashes on transient Telegram API errors | MEDIUM | Open | Resilience / Error handling |
| EXT-003 | Moderation API returns 400 for schema validation instead of 422 | LOW | Open | API validation |
| EXT-004 | Dead code: translate_cached (bs→ru specific function) unused in production | LOW | Open | Code quality / Maintenance |
| EXT-005 | Redundant hmac.compare_digest in login_status is a no-op | LOW | Open | Security correctness |
| EXT-006 | Test certificate private keys committed to repository | LOW | Open | Secrets hygiene |
| EXT-007 | Bot-side login deep-link handler lacks rate limiting | LOW | Open | Defense-in-depth |

## Distribution

**Severity counts**

| MEDIUM | 2 |
| LOW | 5 |

**Status counts**

| Status | Count |
|--------|-------|
| Open | 7 |

## Findings by Severity

### MEDIUM

#### EXT-001: [MEDIUM] — Stale consent.py docstring falsely claims search queries are sent to Google Translate

| Field | Value |
|---|---|
| **ID** | EXT-001 |
| **Title** | Stale consent.py docstring falsely claims search queries are sent to Google Translate |
| **Severity** | MEDIUM |
| **Category** | Documentation / Data-flow accuracy |
| **File(s)** | `src/backend/apps/users/views/consent.py:8-13` |
| **Status** | Open |
| **Problem** | The module docstring for `consent.py` states: "Ad title/description (on creation) and search queries (on lookup) are sent to Google Translate via the Google Cloud Translation API (direct httpx call) for language normalization." In reality, search-query-to-translator egress was removed — the search path now uses per-language FTS vectors with no external call. The docstring overstates data sent to a third party. |
| **Impact** | If this docstring is surfaced in privacy/consent disclosures or documentation consumed by users/stakeholders, it misrepresents what data flows to Google. The actual code does NOT send search queries, so the discrepancy overstates external PII/content egress — a regulatory and trust concern. |
| **Root Cause** | The `consent.py` module docstring was written when search-query translation existed. The translation service (`translation.py:9-11`) and technical specification (`technical-specification.md:119`) were updated to reflect the removal, but `consent.py` was not updated in the same change. |
| **Recommendation** | Update the `consent.py` docstring to match the actual behavior: remove "search queries (on lookup)" from the list of data sent to Google Translate. Only ad title/description (on creation) is translated externally. |
| **Effort** | S |
| **Priority** | P1 |
| **CWE** | CWE-706 (Misleading Documentation) |
| **Likelihood** | MEDIUM |

**Evidence — `src/backend/apps/users/views/consent.py:8-13`** *(supports: "consent.py docstring claims search queries are sent to Google Translate")*:
```python
# Data flow disclosure — translation egress:
# Ad title/description (on creation) and search queries (on lookup) are
# sent to Google Translate via the Google Cloud Translation API (direct httpx call)
# for language normalization. This is a best-effort, non-identifying content transfer;
# no user PII (telegram_id, username, IP) is included in the request.
# See also section G in docs/01-spec/technical-specification.md.
```

**Evidence — `src/backend/apps/core/services/translation.py:8-11`** *(supports: "actual code states search-query translation was removed")*:
```python
# Used at publication time by the bot's ad-creation translator
# (``telegram_bot.handlers.ad_create``). Search/alert query translation was
# removed — the search path now uses language-aware per-language FTS vectors
# with no external translation.
```

**Evidence — `docs/01-spec/technical-specification.md:119`** *(supports: "spec confirms no query-time translation; no search queries sent to translator")*:
```text
The query is searched in its original language — no query-time translation.
Category names are indexed per language via name_i18n->>'bs' / ->>'en' ...
No search queries are sent to any translation service — search runs per-language
on pre-translated vectors.
```

---

#### EXT-002: [MEDIUM] — send_alerts daily digest command crashes on transient Telegram API errors

| Field | Value |
|---|---|
| **ID** | EXT-002 |
| **Title** | send_alerts daily digest command crashes on transient Telegram API errors |
| **Severity** | MEDIUM |
| **Category** | Resilience / Error handling |
| **File(s)** | `src/backend/apps/search/management/commands/send_alerts.py:139-183` |
| **Status** | Open |
| **Problem** | The daily `send_alerts` management command's `_send_user_digests` coroutine only catches `TelegramBadRequest` and `TelegramForbiddenError` (permanent failures) inside the per-user send loop. It does NOT catch `TelegramRetryAfter` (HTTP 429), `TelegramServerError` (HTTP 5xx), or `TelegramNetworkError` (connection issues). A single transient error propagates out of the for-loop, past the `finally` block (which closes the bot session), and crashes the entire management command via `asyncio.run(self._send_user_digests(...))` at line 60 — which has no outer try/except. |
| **Impact** | When the Telegram API returns a transient error (rate limit, 5xx, or network blips) for any single user during the daily digest batch, the entire command aborts. All remaining users miss their daily alert digest for that cycle. The notifications for matching ads were already persisted before the send phase, so re-running the command would re-send to users who already received their digest (duplicate messages) while users after the failure still miss theirs. |
| **Root Cause** | The immediate-alerts path (`immediate_alerts.py:207-237`) was hardened with comprehensive exception handling (permanent failures dead-lettered, transient failures retried once with capped backoff). The `send_alerts.py` daily command was written first and was not updated to match the same resilient pattern when the immediate-alert path was built. |
| **Recommendation** | Align `_send_user_digests` with the immediate-alerts exception handling pattern: catch `TelegramRetryAfter` (respect `retry_after`), `TelegramServerError`, and `TelegramNetworkError` as transient (retry once with backoff, then dead-letter on persistent failure); keep `TelegramBadRequest`/`TelegramForbiddenError` as permanent dead-letter. Wrap the entire `_send_user_digests` call in `handle()` with a try/except for `AiogramError` so a single user's transient error never aborts the entire batch. |
| **Effort** | S |
| **Priority** | P1 |
| **CWE** | CWE-754 (Improper Check for Unusual or Exceptional Conditions) |
| **Likelihood** | MEDIUM |

**Evidence — `src/backend/apps/search/management/commands/send_alerts.py:167-183`** *(supports: "only catches BadRequest/ForbiddenError; no transient handling")*:
```python
            try:
                await bot.send_message(
                    chat_id=user.chat_id,
                    text=message,
                    parse_mode="HTML",
                )
            except (TelegramBadRequest, TelegramForbiddenError) as e:
                logger.warning("Failed to send alert to user %d: %s", user_id, e)
```

**Evidence — `src/backend/apps/search/management/commands/send_alerts.py:60`** *(supports: "asyncio.run called without outer try/except")*:
```python
        # Send messages outside the transaction (network I/O)
        asyncio.run(self._send_user_digests(settings.BOT_TOKEN, user_ads))
```

**Evidence — `src/backend/apps/search/services/immediate_alerts.py:207-237`** *(supports: "immediate-alerts path handles all transient exceptions")*:
```python
                except (TelegramBadRequest, TelegramForbiddenError) as exc:
                    # Permanent failures — dead-letter (no retry).
                    ...
                except (
                    TelegramRetryAfter,
                    TelegramNetworkError,
                    TelegramServerError,
                ) as exc:
                    # Transient failures — retry once with capped backoff.
                    ...
```

---

### LOW

#### EXT-003: [LOW] — Moderation API returns 400 for schema validation instead of 422

| Field | Value |
|---|---|
| **ID** | EXT-003 |
| **Title** | Moderation API returns 400 for schema validation instead of 422 |
| **Severity** | LOW |
| **Category** | API validation |
| **File(s)** | `src/backend/apps/moderation/views/api_bulk.py:42-46` |
| **Status** | Open |
| **Problem** | The moderation bulk-action API endpoint catches `pydantic.ValidationError` and returns HTTP 400 ("Invalid request body"). The audit phase rubric (§5e) expects malformed input to return 422 (Unprocessable Entity), not 500. While 400 is a valid client-error code, 422 is the semantically correct status for schema validation failures (the request was well-formed HTTP but contained semantically invalid data). |
| **Impact** | API clients cannot distinguish between malformed syntax (400) and schema validation failures (422), reducing error-handling precision. Low direct risk — the endpoint is staff-only and behind nginx rate limiting. |
| **Root Cause** | The Pydantic `ValidationError` is caught in the same handler as the `MAX_BULK_ACTIONS` rejection, returning 400 for both cases. No separate status code for semantic validation failure. |
| **Recommendation** | Return 422 (with `pydantic.ValidationError.errors()` as the JSON body) for schema validation failures, retain 400 for the `MAX_BULK_ACTIONS` count rejection or also return 422 for consistency. |
| **Effort** | T |
| **Priority** | P2 |
| **CWE** | CWE-693 (Protection Mechanism Failure) |
| **Likelihood** | LOW |

**Evidence — `src/backend/apps/moderation/views/api_bulk.py:42-46`** *(supports: "ValidationError returns 400, not 422")*:
```python
    try:
        payload = BulkModerationRequest.model_validate_json(request.body)
    except ValidationError:
        logger.warning("Invalid bulk moderation request body")
        return JsonResponse({"error": "Invalid request body"}, status=400)
```

---

#### EXT-004: [LOW] — Dead code: translate_cached (bs→ru specific function) unused in production

| Field | Value |
|---|---|
| **ID** | EXT-004 |
| **Title** | Dead code: translate_cached (bs→ru specific function) unused in production |
| **Severity** | LOW |
| **Category** | Code quality / Maintenance |
| **File(s)** | `src/backend/apps/core/services/translation.py:107-121` |
| **Status** | Open |
| **Problem** | The function `translate_cached(query: str)` at line 108 is a bs→ru-specific wrapper that calls `_translate_via_api(query, "bs", "ru")`. No production code calls this function — the only references are in `test_multi_lang_translation.py:53` (for cache clearing in test fixtures). Production code uses `translate_cached_generic` (which supports any language pair) via `translate_text`. Per audit policy, dead code that IS documented as intended should be investigated before removal — the docstring claims it's "for search queries" which is no longer accurate. |
| **Impact** | Confusing dead code that could mislead future maintainers into using the wrong (hardcoded bs→ru) function. The docstring (line 116: "The search query to translate") references a use case that no longer exists. |
| **Root Cause** | The bs→ru-specific `translate_cached` was the original implementation for search-query translation. When the search path was refactored to per-language FTS, the generic `translate_cached_generic` replaced it, but the old function was not removed. |
| **Recommendation** | Investigate whether `translate_cached` serves any documented purpose. If not (it doesn't — search translation was removed), remove the function and its cache-clearing reference in the test fixture. Update the test to only clear `translate_cached_generic`. |
| **Effort** | S |
| **Priority** | P2 |
| **CWE** | CWE-563 (Dead Code) |
| **Likelihood** | LOW |

**Evidence — `src/backend/apps/core/services/translation.py:107-121`** *(supports: "translate_cached hardcodes bs→ru and is never called in production")*:
```python
@lru_cache(maxsize=128)
def translate_cached(query: str) -> str:
    """Cached translation function.
    ...
    Args:
        query: The search query to translate
    Returns:
        Translated query in Russian
    """
    return _translate_via_api(query, "bs", "ru")
```

**Evidence — `src/backend/apps/core/services/translation.py:9-11`** *(supports: "search translation was removed; translate_cached_generic is the replacement")*:
```python
# Used at publication time by the bot's ad-creation translator
# (``telegram_bot.handlers.ad_create``). Search/alert query translation was
# removed — the search path now uses language-aware per-language FTS vectors
```

---

#### EXT-005: [LOW] — Redundant hmac.compare_digest in login_status is a no-op

| Field | Value |
|---|---|
| **ID** | EXT-005 |
| **Title** | Redundant hmac.compare_digest in login_status is a no-op |
| **Severity** | LOW |
| **Category** | Security correctness |
| **File(s)** | `src/backend/apps/users/views/consent.py:386-392` |
| **Status** | Open |
| **Problem** | In `login_status`, the token is retrieved via `LoginToken.objects.get(token_hash=token_hash)` (line 386) — an ORM exact-match lookup on the unique hash column. If the lookup succeeds, `token.token_hash` is by definition equal to `token_hash` (they are the same value: the lookup key). The subsequent `hmac.compare_digest(token.token_hash, token_hash)` at line 391 therefore always returns `True`, making it a no-op. The comment (line 390) claims "Constant-time comparison (spec: spec-index.md:75, db-schema.md:86)" but the `compare_digest` is applied AFTER the comparison that already occurred in the DB lookup — it does not protect against timing attacks. |
| **Impact** | The `compare_digest` provides illusion of constant-time token verification without actually achieving it. The real comparison (DB indexed lookup) is not constant-time, but the practical risk is negligible because the token has 192 bits of entropy (`secrets.token_urlsafe(24)`), making brute-force infeasible. The misleading comment may cause future maintainers to believe the timing-attack protection is effective when it is not. |
| **Root Cause** | The spec (spec-index.md:75, db-schema.md:93) calls for `hmac.compare_digest`, and the developer applied it, but placed it after the ORM lookup instead of using it to compare the user-supplied hash against a fetched stored hash in a way that would be meaningful. The spec did not specify the exact placement. |
| **Recommendation** | Either: (a) Remove the redundant `compare_digest` call and its misleading comment, acknowledging that the SHA-256 hash + 192-bit entropy + atomic UPDATE...RETURNING claim is the actual protection; or (b) If the intent is to defend against DB-timing oracle attacks, restructure so the hash is compared in Python (not via DB get) with `compare_digest` before any DB write. Option (a) is simpler and sufficient given the entropy. |
| **Effort** | T |
| **Priority** | P2 |
| **CWE** | CWE-208 (Observable Timing Discrepancy / ineffective control) |
| **Likelihood** | LOW |

**Evidence — `src/backend/apps/users/views/consent.py:384-392`** *(supports: "compare_digest called after ORM exact-match lookup that already succeeded")*:
```python
    with transaction.atomic():
        try:
            token = LoginToken.objects.get(token_hash=token_hash)
        except LoginToken.DoesNotExist:
            return HttpResponse(status=410)

        # Constant-time comparison (spec: spec-index.md:75, db-schema.md:86)
        if not hmac.compare_digest(token.token_hash, token_hash):
            return HttpResponse(status=410)
```

**Evidence — `docs/01-spec/spec-index.md:75`** *(supports: "spec references hmac.compare_digest")*:
```text
- **Login (H):** QR deep-link login_<token> (32-char URL-safe token (~192-bit CSPRNG, rate-limited 5-min TTL),
  LoginToken two-phase atomic claim, hmac.compare_digest; consumption via POST body + CSRF (not URL query).
```

---

#### EXT-006: [LOW] — Test certificate private keys committed to repository

| Field | Value |
|---|---|
| **ID** | EXT-006 |
| **Title** | Test certificate private keys committed to repository |
| **Severity** | LOW |
| **Category** | Secrets hygiene |
| **File(s)** | `C:\py_dev\mko_bazuna/.tmp/nginx-test-certs/fullchain.pem`, `.tmp/nginx-test-certs/privkey.pem` (tracked via `git ls-files`) |
| **Status** | Open |
| **Problem** | The files `.tmp/nginx-test-certs/fullchain.pem` and `.tmp/nginx-test-certs/privkey.pem` are tracked in the Git repository (confirmed via `git ls-files`). These appear to be mkcert-generated local development certificates. The `.gitignore` only excludes `docker/nginx/certs/*.pem` (line 221), not the `.tmp/nginx-test-certs/*.pem` path, so the private key (`privkey.pem`) was committed alongside the certificate. |
| **Impact** | While these are localhost development certificates (not production TLS certs), committing private keys to version control violates security hygiene. If the mkcert root CA or the private key is ever reused outside the original dev environment, it could enable MITM attacks. The `.gitignore` gap also means any future test certs in `.tmp/` would silently be committed. |
| **Root Cause** | The `.gitignore` pattern `docker/nginx/certs/*.pem` was written for the production cert mount path but does not cover the `.tmp/nginx-test-certs/` path used for local HTTPS testing. No `.tmp/` exclusion exists. |
| **Recommendation** | Add `.tmp/` to `.gitignore` (or at minimum `.tmp/nginx-test-certs/`), and remove the tracked `privkey.pem` and `fullchain.pem` from Git history via `git rm --cached`. Verify no other `.tmp/` test artifacts are tracked. |
| **Effort** | T |
| **Priority** | P2 |
| **CWE** | CWE-312 (Cleartext Storage of Sensitive Information) |
| **Likelihood** | LOW |

**Evidence — `git ls-files` output** *(supports: "test cert private keys are tracked in git")*:
```text
.tmp/nginx-test-certs/fullchain.pem
.tmp/nginx-test-certs/privkey.pem
```

**Evidence — `.gitignore:220-222`** *(supports: ".gitignore only covers docker/nginx/certs/, not .tmp/")*:
```text
# mkcert development certificates (never commit private keys)
docker/nginx/certs/*.pem
!docker/nginx/certs/.gitkeep
```

---

#### EXT-007: [LOW] — Bot-side login deep-link handler lacks rate limiting

| Field | Value |
|---|---|
| **ID** | EXT-007 |
| **Title** | Bot-side login deep-link handler lacks rate limiting |
| **Severity** | LOW |
| **Category** | Defense-in-depth |
| **File(s)** | `src/telegram_bot/handlers/login.py:34-119` |
| **Status** | Open |
| **Problem** | The `handle_login_deep_link` handler (responding to `/start login_<token>`) performs no rate limiting before executing the token claim. The web side rate-limits token ISSUANCE (`login_rate_limit_check` — 10/min per IP, `check_deep_link_render_rate_limit` — 60/10min), but the bot side — which actually claims the token via `UPDATE ... RETURNING` — has no per-chat or per-token rate limiting. Other bot endpoints (file uploads, contact-start) are rate-limited via `telegram_bot/services/rate_limit.py`, but login is not. |
| **Impact** | An attacker who knows or guesses a valid `login_<token>` deep-link format could spam `/start login_<token>` messages to the bot, causing a stream of DB UPDATE queries on the `login_tokens` table. The 192-bit token entropy makes brute-force guessing infeasible, and the atomic claim (`UPDATE ... RETURNING` with `consumed_at IS NULL` filter) ensures only the first valid claim succeeds — but a flood of login deep-links still consumes bot event-loop time and DB connections. |
| **Root Cause** | The login handler was implemented as part of the two-phase auth flow without applying the same `TelegramRateLimitMiddleware` / `rate_limit_check` pattern used by `ad_create` and `contact` handlers. The web-side rate limits were assumed sufficient as a proxy for bot-side protection. |
| **Recommendation** | Add a lightweight per-chat rate limit to `handle_login_deep_link` (e.g., 10 login claims per minute per Telegram chat_id) using the existing `telegram_bot.services.rate_limit` pattern. Also note: aiogram's built-in `TelegramRetryArea` handling during `getUpdates` polling provides backpressure at the gateway level, but application-level per-chat limiting is recommended for defense-in-depth. |
| **Effort** | S |
| **Priority** | P2 |
| **CWE** | CWE-770 (Allocation of Resources Without Limits) |
| **Likelihood** | LOW |

**Evidence — `src/telegram_bot/handlers/login.py:34-43`** *(supports: "handle_login_deep_link has no rate-limiting check before token claim")*:
```python
@router.message(Command("start"))
async def handle_login_deep_link(
    message: types.Message, bot: Bot, state: FSMContext
) -> None:
    ...
    args = message.text.split(maxsplit=1)
    ...
    raw_token = match.group(1)
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    login_token, user, created = await handle_login_orm(
        token_hash=token_hash,
        ...
    )
```

**Evidence — `src/telegram_bot/services/rate_limit.py:20-24,70-75`** *(supports: "existing per-chat rate-limit patterns for uploads and contact-start, but none for login")*:
```python
RATE_LIMIT_REQUESTS: Final[int] = 10     # uploads: 10/60s per user
RATE_LIMIT_PERIOD: Final[int] = 60
CONTACT_RATE_LIMIT_REQUESTS: Final[int] = 5  # contact-start: 5/600s per user
CONTACT_RATE_LIMIT_PERIOD: Final[int] = 600
```
No `check_login_rate_limit` function exists in this module — login deep-link claims are unthrottled at the bot layer.

**Evidence — `src/backend/apps/users/services/login_rate_limit.py:18-19,47-55`** *(supports: "web-side login issuance IS rate-limited, creating an asymmetry")*:
```python
RATE_LIMIT_REQUESTS: Final[int] = 10
RATE_LIMIT_PERIOD: Final[int] = 60

def login_rate_limit_check(request: HttpRequest) -> bool:
    ...
    added = cache.add(key, 1, timeout=RATE_LIMIT_PERIOD)
    if added:
        current = 1
    else:
        current = cache.incr(key)
    return current <= RATE_LIMIT_REQUESTS
```
This limiter guards `login_issue` (token ISSUANCE at `consent.py:299`); no equivalent guards the bot-side CLAIM in `handlers/login.py`.

---

## Cross-Finding Analysis

- **Merge candidates:** None — all seven findings have distinct root causes (documentation drift, error handling gap, status code, dead code, redundant comparison, committed secrets, missing rate limit).
- **Conflicting evidence:** None.
- **Dependency chains:** None. The findings are independent.

## Remediation Roadmap

| Order | ID | Severity | Effort | Priority | Recommendation (summary) |
|-------|----|----------|--------|----------|--------------------------|
| 1 | EXT-001 | MEDIUM | S | P1 | Update consent.py docstring to remove "search queries (on lookup)" from translation egress description |
| 2 | EXT-002 | MEDIUM | S | P1 | Align send_alerts.py exception handling with immediate_alerts.py: catch TelegramRetryAfter/ServerError/NetworkError with retry+backoff, wrap asyncio.run in try/except AiogramError |
| 3 | EXT-003 | LOW | T | P2 | Return 422 (with ValidationError.errors()) for Pydantic schema validation failures in bulk_moderation_action |
| 4 | EXT-004 | LOW | S | P2 | Remove dead `translate_cached` function (bs→ru) and its test-fixture cache_clear reference |
| 5 | EXT-005 | LOW | T | P2 | Remove redundant `hmac.compare_digest` call + misleading comment in login_status |
| 6 | EXT-006 | LOW | T | P2 | Add `.tmp/` to .gitignore, remove tracked test certs from git history |
| 7 | EXT-007 | LOW | S | P2 | Add per-chat rate limit to bot-side login deep-link handler using existing rate_limit pattern |

## Rollout Safety

| ID | Risk | Backward-compatible? | Test gap (must cover) |
|----|------|----------------------|-----------------------|
| EXT-001 | Low | Yes | N/A (doc change only) |
| EXT-002 | Med | Yes | Test: transient Telegram errors in _send_user_digests do not abort entire batch; test: retry+backoff engages |
| EXT-003 | Low | Yes | Test: 422 returned for invalid JSON body / schema violation |
| EXT-004 | Low | Yes | Test: remove translate_cached references from test fixtures; ensure translate_cached_generic still used |
| EXT-005 | Low | Yes | Test: login_status still returns 410 for invalid/expired tokens |
| EXT-006 | Low | Yes | Test: CI verifies no .tmp/ files are tracked |
| EXT-007 | Low | Yes | Test: per-chat login rate limit returns appropriate response after threshold |

## Appendices

### Appendix A — git tracked test certificates

*(supports the claim: ".tmp/nginx-test-certs/*.pem are tracked in git despite .gitignore not covering that path")*
```text
$ git ls-files -- '.tmp/'
.tmp/nginx-test-certs/fullchain.pem
.tmp/nginx-test-certs/privkey.pem
```

### Appendix B — send_alerts.py exception imports vs. caught exceptions

*(supports the claim: "send_alerts.py imports fewer aiogram exceptions than it should, and catches only permanent failures")*
```text
# send_alerts.py imports (line 13):
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError

# immediate_alerts.py imports (lines 22-29):
from aiogram.exceptions import (
    AiogramError,
    TelegramBadRequest,
    TelegramForbiddenError,
    TelegramNetworkError,
    TelegramRetryAfter,
    TelegramServerError,
)
# immediate_alerts catches RetryAfter/ServerError/NetworkError; send_alerts does NOT
```
