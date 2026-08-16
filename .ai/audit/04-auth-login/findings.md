---
name: audit-findings
description: Phase 04 Auth/Login system audit findings
agent: audit-executor
alwaysApply: false
---

# Phase 04 Audit Findings — Auth/Login System

**Executor:** audit-executor
**Template:** .ai/audit/templates/audit-findings.md
**Status:** complete
**Validated:** yes

---

## Findings

### AUT-001 (CRITICAL/MANDATORY/RUNTIME-ERROR): Bot token claim crashes — `.update(returning=True)` is invalid Django 5.2 API

| Field | Value |
|-------|-------|
| **ID** | AUT-001 |
| **Severity** | CRITICAL |
| **Type** | RUNTIME-ERROR |
| **Affected Modules** | src/telegram_bot/handlers/login.py |
| **Classification** | mandatory |

**Description:**

The bot-side token claim in `handle_login_orm` (line 128) uses `.update(telegram_id=telegram_id, returning=True)`, passing `returning` as a keyword argument to `QuerySet.update()`. In Django 5.2.16, `QuerySet.update()` accepts only model field names as kwargs (signature: `update(self, **kwargs)`). Django interprets `returning=True` as an attempt to set a model field named `returning`, raising `FieldDoesNotExist: LoginToken has no field named 'returning'`.

Additionally, even if the `returning=True` kwarg is removed, `.update()` returns an `int` (count of rows affected) in Django 5.2 — not a QuerySet. The subsequent `.first()` call on that int would raise `AttributeError: 'int' object has no attribute 'first'`.

This completely breaks the bot-side of the two-phase login token claim (phase 1: bot sets `telegram_id`). No user can authenticate via Telegram deep-link login.

**Evidence:**

- `src/telegram_bot/handlers/login.py:128` — `.update(telegram_id=telegram_id, returning=True).first()`
- `src/telegram_bot/handlers/login.py:119-130` — full broken claim block
- Django 5.2.16 confirmed via `inspect.signature`: `QuerySet.update(self, **kwargs)` — no `returning` parameter
- `hasattr(QuerySet, 'returning')` = `False` in Django 5.2.16
- Runtime: `test_login_claim.py::TestClaimLoginToken::test_fresh_unclaimed_token` → `FieldDoesNotExist: LoginToken has no field named 'returning'`
- Runtime: `test_claim_login_token.py` — all 7 tests FAIL (4 with `FieldDoesNotExist`, 3 with `SynchronousOnlyOperation`)

**Recommendation:**

Replace `.update(..., returning=True).first()` with a two-step approach compatible with Django 5.2:
1. Call `.filter(...).update(telegram_id=telegram_id)` and capture the row count (int)
2. If count == 1, re-fetch the token with `.get(token_hash=token_hash)`

Or use raw SQL with `RETURNING` via `connection.cursor()` for true atomicity.

Effort: small | Priority: mandatory (entire login system is broken)

---

### AUT-002 (HIGH/MANDATORY/RUNTIME-ERROR): Sync ORM calls in async bot test fixtures cause `SynchronousOnlyOperation`

| Field | Value |
|-------|-------|
| **ID** | AUT-002 |
| **Severity** | HIGH |
| **Type** | RUNTIME-ERROR |
| **Affected Modules** | src/telegram_bot/tests/conftest.py, src/telegram_bot/tests/test_claim_login_token.py |
| **Classification** | mandatory |

**Description:**

The `login_token_factory` fixture (`conftest.py:75-91`) defines an inner function `_create` that calls `LoginToken.objects.create(...)` synchronously. In async test context (pytest-asyncio strict mode), Django's async safety check raises `SynchronousOnlyOperation: You cannot call this from an async context - use a thread or sync_to_async.`

This is independent of AUT-001: even if the `returning=True` bug were fixed, 3 of 7 tests in `test_claim_login_token.py` would still fail. The `user` fixture (`conftest.py:58-72`) has the same pattern with `User.objects.get_or_create(...)`.

**Evidence:**

- `src/telegram_bot/tests/conftest.py:84-89` — `_create` calls `LoginToken.objects.create(...)` synchronously
- `src/telegram_bot/tests/conftest.py:63-71` — `user` fixture calls `User.objects.get_or_create(...)` synchronously
- Runtime: `test_claim_login_token.py::TestClaimLoginToken::test_claim_valid_token` → `SynchronousOnlyOperation`
- Runtime: `test_claim_login_token.py::TestClaimLoginToken::test_creates_user_on_first_claim` → same `SynchronousOnlyOperation`
- Runtime: `test_claim_login_token.py::TestClaimLoginToken::test_returns_existing_user_on_second_login` → same `SynchronousOnlyOperation`

**Recommendation:**

Wrap all ORM operations in test fixtures in `sync_to_async()` (matching the pattern already used in production code at `login.py:115`), or restructure fixtures as async fixtures with `async def` and `await sync_to_async(...)`.

Effort: small | Priority: mandatory

---

### AUT-003 (MEDIUM/MANDATORY/SPEC-DEVIATION): No `hmac.compare_digest` for token hash comparison

| Field | Value |
|-------|-------|
| **ID** | AUT-003 |
| **Severity** | MEDIUM |
| **Type** | SPEC-DEVIATION |
| **Affected Modules** | src/backend/apps/users/views/consent.py, src/telegram_bot/handlers/login.py |
| **Classification** | mandatory |

**Description:**

The spec explicitly requires `hmac.compare_digest` for login token comparison:
- `docs/01-spec/spec-index.md:75` — "Login (H): QR deep-link `login_<token>` (32-char), `LoginToken` two-phase atomic claim, `hmac.compare_digest`."
- `docs/02-database/db-schema.md:86` — "token compare via `hmac.compare_digest` (constant time)"

However, `hmac.compare_digest` is never imported or used anywhere in the codebase. The token hash comparison is performed exclusively through Django ORM lookups (SQL `=` comparison):
- `src/backend/apps/users/views/consent.py:212` — `LoginToken.objects.get(token_hash=token_hash)` (SELECT with `=`)
- `src/telegram_bot/handlers/login.py:122-123` — `.filter(token_hash=token_hash, ...)` (SQL `=` comparison)
- `src/backend/apps/users/views/consent.py:225-227` — `.filter(token_hash=token_hash, ...)` (SQL `=` comparison)

**Evidence:**

- `grep` for `compare_digest` / `hmac` across all `src/` files — ZERO matches
- Only `import hashlib` at `consent.py:16` and `login.py:7` (hashlib, not hmac)
- Both spec references explicitly cite `hmac.compare_digest` as a requirement

**Recommendation:**

Either implement `hmac.compare_digest` in the Python layer (fetch candidate tokens and compare in Python), or update the spec docs to clarify that the database-level `=` comparison on a SHA-256 hash is the accepted approach (since the hash is already a one-way derivation and timing attacks on SQL `=` over a 64-char hex hash are impractical).

Effort: medium | Priority: advisory

---

### AUT-004 (MEDIUM/ADVISORY/BEST-PRACTICE): No rate limiting on `login_issue` endpoint

| Field | Value |
|-------|-------|
| **ID** | AUT-004 |
| **Severity** | MEDIUM |
| **Type** | BEST-PRACTICE |
| **Affected Modules** | src/backend/apps/users/views/consent.py, src/backend/apps/users/urls.py |
| **Classification** | advisory |

**Description:**

The `login_issue` view (`consent.py:148-185`) has no rate limiting, throttling, or caching. The testing plan explicitly lists this as a gap: `docs/97-plans/phase-01-detailed-testing.md:116` — "Multiple failed login attempts (test login_issue rate limiting)" — marked with `- [ ]` (not done).

An attacker can spam `/login/issue/` to create unlimited `LoginToken` rows in the database, each with a 5-minute expiry. The only cleanup is the background `cleanup_login_tokens` management command, which runs on a schedule and may not keep up with a spammer.

**Evidence:**

- `src/backend/apps/users/views/consent.py:148-185` — `login_issue` has no `@ratelimit`, `@throttle`, or cache decorator
- `src/backend/apps/users/urls.py:12` — route with no middleware wrapper
- `docs/97-plans/phase-01-detailed-testing.md:116` — unchecked TODO for rate limiting tests
- `src/backend/apps/core/management/commands/cleanup_login_tokens.py` exists as background cleanup (remediation only)

**Recommendation:**

Add rate limiting using django-ratelimit, a custom throttling middleware, or a simple per-IP counter (e.g., max 10 tokens per minute per IP).

Effort: small | Priority: recommended

---

### AUT-005 (LOW/MANDATORY/SPEC-DEVIATION): Cookie security flags not explicit in settings

| Field | Value |
|-------|-------|
| **ID** | AUT-005 |
| **Severity** | LOW |
| **Type** | SPEC-DEVIATION |
| **Affected Modules** | src/backend/config/settings/base.py |
| **Classification** | mandatory |

**Description:**

The spec (`docs/02-database/db-schema.md:86`) requires session cookies with `SECURE` + `HTTPONLY` + `SAMESITE=Lax`. The base settings (`src/backend/config/settings/base.py:65-66`) explicitly set `SESSION_COOKIE_SECURE = True` and `CSRF_COOKIE_SECURE = True`, but do NOT explicitly set `SESSION_COOKIE_HTTPONLY` or `SESSION_COOKIE_SAMESITE`. Django 5.2's defaults are `SESSION_COOKIE_HTTPONLY = True` and `SESSION_COOKIE_SAMESITE = "Lax"`, but relying on implicit defaults makes the security posture unclear and fragile: a future Django upgrade or settings refactor could silently change these.

**Evidence:**

- `src/backend/config/settings/base.py:65-66` — only `SESSION_COOKIE_SECURE` and `CSRF_COOKIE_SECURE` are set
- No `SESSION_COOKIE_HTTPONLY` or `SESSION_COOKIE_SAMESITE` in any settings file (base, dev, prod, test)
- Django 5.2 defaults: `SESSION_COOKIE_HTTPONLY = True`, `SESSION_COOKIE_SAMESITE = "Lax"` (correct but implicit)

**Recommendation:**

Add explicit `SESSION_COOKIE_HTTPONLY = True` and `SESSION_COOKIE_SAMESITE = "Lax"` to `src/backend/config/settings/base.py`.

Effort: trivial | Priority: recommended

---

### AUT-006 (MEDIUM/ADVISORY/SPEC-DEVIATION): Web-side token claim uses read-then-update instead of single atomic UPDATE

| Field | Value |
|-------|-------|
| **ID** | AUT-006 |
| **Severity** | MEDIUM |
| **Type** | SPEC-DEVIATION |
| **Affected Modules** | src/backend/apps/users/views/consent.py |
| **Classification** | advisory |

**Description:**

The spec (`docs/02-database/db-schema.md:83-85`) states: "Two-phase atomic claim (each = one UPDATE under transaction)". The web-side claim in `login_status` (`consent.py:224-234`) deviates from this by performing a read-then-write pattern:
1. Line 212: `LoginToken.objects.get(token_hash=token_hash)` — a SELECT
2. Lines 217-222: check `expires_at`, `consumed_at`, `telegram_id` in Python
3. Lines 225-230: `.filter(...).update(consumed_at=...)` — a separate UPDATE

The two operations are not wrapped in `transaction.atomic()`. While the UPDATE's filter conditions (token_hash, telegram_id, consumed_at IS NULL, expires_at > now) provide optimistic concurrency safety (if another request consumed the token between the SELECT and UPDATE, the UPDATE returns 0 rows → 410), this is a two-query pattern rather than the single-UPDATE approach the spec describes.

The bot-side claim (`src/telegram_bot/handlers/login.py:121-130`) is wrapped in `transaction.atomic()` but is broken (AUT-001). The web-side claim has no transaction wrapper at all.

**Evidence:**

- `docs/02-database/db-schema.md:83` — "Two-phase atomic claim (each = one UPDATE under transaction)"
- `src/backend/apps/users/views/consent.py:212` — `LoginToken.objects.get(token_hash=token_hash)` (SELECT)
- `src/backend/apps/users/views/consent.py:225-230` — separate `.filter(...).update(consumed_at=...)` (UPDATE)
- No `transaction.atomic()` wrapping the web-side claim
- `src/telegram_bot/handlers/login.py:120` — bot-side uses `transaction.atomic()` but crashes (AUT-001)

**Recommendation:**

Wrap the web-side claim in `transaction.atomic()` for consistency, or update the spec to clarify that the read-then-write with optimistic concurrency pattern is an acceptable alternative.

Effort: small | Priority: recommended

---

### AUT-007 (MEDIUM/ADVISORY/BEST-PRACTICE): Raw login token in GET query parameter + no polling JS in template

| Field | Value |
|-------|-------|
| **ID** | AUT-007 |
| **Severity** | MEDIUM |
| **Type** | BEST-PRACTICE |
| **Affected Modules** | src/backend/apps/users/views/consent.py, src/backend/templates/users/login_issue.html |
| **Classification** | advisory |

**Description:**

The `login_status` view reads the raw token from a GET query parameter: `request.GET.get("token", "")` at `consent.py:205`. This means the raw token travels in the URL, which exposes it to:
1. **Server access logs** — every poll request logs the full URL including the token
2. **Browser history** — the token persists in the browser's address bar history
3. **Referer headers** — if the page loads any third-party resources, the token could leak via the Referer header

Additionally, `login_issue.html` has NO JavaScript at all — no polling mechanism to call `login_status`. The template only renders a static deep-link button. There is no `raw_token` passed to the template context (only `deep_link` and `bot_username`), so even if JS were added, the template has no way to construct the `login_status` polling URL.

**Evidence:**

- `src/backend/apps/users/views/consent.py:205` — `raw_token = request.GET.get("token", "")`
- `src/backend/apps/users/views/consent.py:178-185` — `login_issue` only passes `deep_link` and `bot_username` to template
- `src/backend/templates/users/login_issue.html` — 37 lines, no `<script>` tags, no polling AJAX, no mention of `login_status`
- `src/backend/apps/users/urls.py:13` — `login_status` route exists but is never referenced in the template

**Recommendation:**

1. Pass `raw_token` to template context in `login_issue` so client-side JS can poll `login_status`
2. Add JavaScript to `login_issue.html` that polls `login_status?token=<raw_token>` every 2-3 seconds, handling 200 (redirect to dashboard), 204 (keep polling), and 410 (show error)
3. Consider POST-based token submission instead of GET query params to avoid URL leakage in logs/history
4. Add `Cache-Control: no-store` on both endpoints to prevent caching

Effort: medium | Priority: recommended

---

### AUT-008 (LOW/ADVISORY/BEST-PRACTICE): Redundant `request.session.cycle_key()` after `auth_login`

| Field | Value |
|-------|-------|
| **ID** | AUT-008 |
| **Severity** | LOW |
| **Type** | BEST-PRACTICE |
| **Affected Modules** | src/backend/apps/users/views/consent.py |
| **Classification** | advisory |

**Description:**

At `consent.py:251-252`, after calling `auth_login(request, user)`, the code explicitly calls `request.session.cycle_key()`. However, Django's `contrib.auth.login()` (aliased as `auth_login` at line 22) already calls `request.session.cycle_key()` for the anonymous→authenticated transition. Verified in Django 5.2.16 source: the `login()` function contains an `else` branch that calls `request.session.cycle_key()` when `SESSION_KEY` is not in `request.session` (which is the case for anonymous users).

The explicit second `cycle_key()` call creates an unnecessary additional session key rotation. While `cycle_key()` preserves session data (it copies `_session` to `_session_cache`), the redundant call is wasteful and could confuse readers about when `cycle_key()` is actually needed.

**Evidence:**

- `src/backend/apps/users/views/consent.py:251` — `auth_login(request, user)`
- `src/backend/apps/users/views/consent.py:252` — `request.session.cycle_key()` (redundant)
- Django 5.2 `contrib/auth/__init__.py` `login()` source: `if SESSION_KEY in request.session: ... else: request.session.cycle_key()` — already handles anonymous→authenticated case

**Recommendation:**

Remove the redundant `request.session.cycle_key()` call at line 252, since Django's `login()` already cycles the session key for anonymous-to-authenticated transitions. If defense-in-depth is the intent, add a comment explaining why it is kept despite being redundant.

Effort: trivial | Priority: low

---

### AUT-009 (HIGH/MANDATORY/SPEC-DEVIATION): No tests for web login views (`login_issue`, `login_status`)

| Field | Value |
|-------|-------|
| **ID** | AUT-009 |
| **Severity** | HIGH |
| **Type** | SPEC-DEVIATION |
| **Affected Modules** | src/backend/apps/users/tests/ |
| **Classification** | mandatory |

**Description:**

The testing plan (`docs/97-plans/phase-01-detailed-testing.md:116,124`) lists test items for the web login flow:
- Line 116: "Multiple failed login attempts (test login_issue rate limiting)"
- Line 124: "Session fixation prevention (login_status tests)"

However, NO tests exist for the web-side login views (`login_issue` at `consent.py:148-185`, `login_status` at `consent.py:188-256`). The only login-related tests are bot-side:
- `src/telegram_bot/tests/test_login_claim.py` — bot claim (ALL FAIL due to AUT-001)
- `src/telegram_bot/tests/test_claim_login_token.py` — bot claim (ALL 7 FAIL due to AUT-001 + AUT-002)

There are zero tests for:
- Token issuance via `login_issue` (deep link rendering, token hash storage, expiry)
- Token polling via `login_status` (200 success, 204 pending, 410 gone/expired/consumed/banned)
- Session establishment on successful login (session cookie set, cycle_key behavior)
- Ban check enforcement (banned user → 410)
- Token reuse prevention (already-consumed token → 410)

**Evidence:**

- `grep` for `login_status` in `src/backend/apps/users/tests/` — no matches
- `grep` for `login_issue` in `src/backend/apps/users/tests/` — no matches
- `src/backend/apps/users/tests/test_consent.py` — covers only `consent_accept`, `consent_decline`, `consent_withdraw`; NO login tests
- `src/backend/apps/users/tests/` directory contains only `test_consent.py` and `test_deletion.py` — no `test_login.py`
- `docs/97-plans/phase-01-detailed-testing.md:116,124` — testing plan explicitly lists login tests as TODO

**Recommendation:**

Add a `test_login.py` in `src/backend/apps/users/tests/` covering:
- `login_issue`: 200 response, deep-link URL contains token, token_hash stored as SHA-256, 5-min expiry
- `login_status`: 200 (successful claim → session established), 204 (pending), 410 (expired/consumed/nonexistent/banned)
- Session fixation: verify session key changes after successful login

Effort: medium | Priority: recommended

---

### AUT-010 (LOW/ADVISORY/BEST-PRACTICE): `login_issue`/`login_status` lack `@never_cache`

| Field | Value |
|-------|-------|
| **ID** | AUT-010 |
| **Severity** | LOW |
| **Type** | BEST-PRACTICE |
| **Affected Modules** | src/backend/apps/users/views/consent.py |
| **Classification** | advisory |

**Description:**

The `login_issue` view (`consent.py:148`) and `login_status` view (`consent.py:188`) have no `@never_cache` decorator. This view generates a unique, single-use deep-link token. If the response is cached by a CDN, reverse proxy, or browser, multiple users could receive the same deep-link URL, allowing anyone to claim another user's login token.

While the project uses Whitenoise (which doesn't cache HTML responses by default) and dev/test settings use `SECURE_SSL_REDIRECT = False`, the production settings (`prod.py`) enable HSTS. The spec does not explicitly mention cache control for these endpoints, but a login token issuance endpoint should always be non-cacheable as a matter of security.

**Evidence:**

- `src/backend/apps/users/views/consent.py:148` — `def login_issue(...)` with no `@never_cache`, `@cache_control`, or `@vary_on_cookie`
- `src/backend/apps/users/views/consent.py:188` — `def login_status(...)` also has no cache control decorator
- No `django.views.decorators.cache` import in `consent.py`
- `docs/02-database/db-schema.md:86` mentions cookie flags but not cache policy for login endpoints

**Recommendation:**

Add `@never_cache` to both `login_issue` and `login_status` to ensure the login deep-link and status responses are never cached by intermediate proxies or browsers.

Effort: trivial | Priority: low

---

## Summary

| Severity | Count |
|----------|-------|
| CRITICAL | 1 |
| HIGH | 2 |
| MEDIUM | 3 |
| LOW | 3 |

---

## Mandatory Fixes

1. **AUT-001 (CRITICAL)**: Rewrite bot-side token claim at `src/telgram_bot/handlers/login.py:128` — `.update(returning=True).first()` is broken in Django 5.2. Replace with `.filter().update()` (returns int) + conditional re-fetch, or raw SQL with RETURNING.
2. **AUT-002 (HIGH)**: Fix sync ORM calls in test fixtures (`conftest.py:84-89`) — wrap in `sync_to_async()`.
3. **AUT-003 (MEDIUM)**: Implement `hmac.compare_digest` for token comparison or update spec docs (`spec-index.md:75`, `db-schema.md:86`).
4. **AUT-005 (LOW)**: Add explicit `SESSION_COOKIE_HTTPONLY = True` and `SESSION_COOKIE_SAMESITE = "Lax"` to `base.py`.
5. **AUT-009 (HIGH)**: Add test coverage for web login views (`login_issue`, `login_status`) — currently completely untested.

---

## Advisory Recommendations

1. **AUT-004 (MEDIUM)**: Add rate limiting to `login_issue` endpoint.
2. **AUT-006 (MEDIUM)**: Wrap web-side claim in `transaction.atomic()` or update spec to accept optimistic concurrency.
3. **AUT-007 (MEDIUM)**: Pass `raw_token` to template context, add JS polling to `login_issue.html`, add `Cache-Control: no-store`.
4. **AUT-008 (LOW)**: Remove redundant `request.session.cycle_key()` at `consent.py:252`.
5. **AUT-010 (LOW)**: Add `@never_cache` to `login_issue` and `login_status` views.

---

## Doc Updates Needed

- **AUT-003**: Update `docs/01-spec/spec-index.md:75` and `docs/02-database/db-schema.md:86` if accepting DB-level `=` comparison instead of `hmac.compare_digest`.
- **AUT-006**: Clarify `docs/02-database/db-schema.md:83-85` — accept read-then-write with optimistic concurrency or require true single-UPDATE.
- **AUT-009**: Implement the test items listed in `docs/97-plans/phase-01-detailed-testing.md:116,124` (rate limiting tests, session fixation tests for `login_status`).

---

## Template Field Reference

### Mandatory Fields Per Finding

| Field | Type | Values/Format |
|-------|------|---------------|
| `id` | string | Unique identifier within phase (e.g., AUT-001) |
| `title` | string | Human-readable one-line summary |
| `type` | enum | `SPEC-DEVIATION`, `BEST-PRACTICE`, `DOC-UPDATE`, `RUNTIME-ERROR` |
| `severity` | enum | `CRITICAL`, `HIGH`, `MEDIUM`, `LOW` |
| `description` | string | Detailed problem description with context |
| `evidence` | string | File paths, line references, log excerpts, code snippets |
| `affected_modules` | list | Affected module paths |
| `recommendation` | string | Concrete fix direction: what to change and why |
| `classification` | enum | `mandatory` or `advisory` |

### Classification Guide

- **mandatory**: Security vulnerabilities, data loss risks, correctness issues, spec deviations requiring immediate fix
- **advisory**: Code quality improvements, refactoring suggestions, best practice enhancements
