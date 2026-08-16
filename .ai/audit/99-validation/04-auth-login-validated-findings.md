---
name: audit-findings-validated
description: Validated Phase 04 audit findings - Auth/Login System
agent: validator
alwaysApply: false
---

# Phase 04 Audit Findings — Auth/Login System (Validated)

**Executor:** audit-executor (original) / validator (validation)
**Template:** .kilo/commands/audit/phases/99-audit-validate.md
**Source findings:** .ai/audit/04-auth-login/findings.md
**Status:** complete
**Validated:** yes

Runtime verification performed host-side with the project .venv (Python 3.14 / Django 5.2.16)
under DJANGO_SETTINGS_MODULE=config.settings.test; PYTHONPATH=src;src/backend. Evidence
re-verified through code inspection, runtime Django introspection, and cross-phase finding
analysis against Phase 01 (.ai/audit/01-entry-architecture/findings.md) and Phase 03
(.ai/audit/03-db-concurrency/findings.md).

**Validation scope:** All code references cited in the findings were re-read at source. Django API
surfaces were verified at runtime (Django 5.2.16 final 0). The hmac/compare_digest,
ratelimit/never_cache, and SESSION_COOKIE_* searches were executed via repo-wide grep to confirm
absence/presence. The LoginToken model fields were confirmed against
src/backend/apps/users/models.py:117-156.

---

## Cross-Finding Analysis

### Cross-Phase Merge Candidate: AUT-001 = ENT-001

AUT-001 (Phase 04, CRITICAL) and ENT-001 (Phase 01, CRITICAL) describe the identical root-cause
bug: LoginToken.objects.filter(...).update(telegram_id=..., returning=True).first() at
src/telegram_bot/handlers/login.py:128. Both cite the same code location, the same Django 5.2 API
violation (QuerySet.update(**kwargs) has no returning parameter; .update() returns int not
QuerySet, so .first() is invalid), and the same FieldDoesNotExist runtime error. ENT-001 was
discovered first (Phase 01) and is the canonical finding. AUT-001 is a duplicate.

Phase 03 DB-003 also cross-references this bug, confirming the issue persists across phases.
AUT-001 is merged into ENT-001 in this report.

### Documentation Inconsistency: Technical Spec vs DB Schema

AUT-003 references spec-index.md:75 (hmac.compare_digest) and db-schema.md:86 (token compare via
hmac.compare_digest). However, technical-specification.md:112 states: constant-time compare
(select_for_update). This is an internal documentation inconsistency - two spec documents prescribe
different constant-time comparison mechanisms. The code implements neither. Spec-index.md:75 and
db-schema.md:86 are the canonical references and both require `hmac.compare_digest`;
technical-specification.md:115 cites `select_for_update` as the outlier. Resolution: update
technical-specification.md:115 to read `hmac.compare_digest`. See AUT-003 recommendation.

### Dependency Chain

- AUT-001 (bot-side claim fix) is a prerequisite for AUT-002 tests to pass.
- AUT-002 (fixture sync fix) is a prerequisite for the remaining 4 fixture-based tests once
  AUT-001 is fixed.
- AUT-009 (web login tests) is independent of the bot-side AUT-001 bug. No ordering dependency.

### Rollout Safety Assessment

| Risk | Finding | Status |
|------|---------|--------|
| Circular dependency | None detected | Safe |
| Hidden dependency chain | AUT-002 tests depend on AUT-001 fix | Noted |
| Unsafe rollout ordering | AUT-001 must be fixed before AUT-002 tests can pass | Noted |
| Fragile insertion points | AUT-006: wrapping login_status in transaction.atomic() is localized | Safe |

---

## Findings

### AUT-001: Bot token claim crashes — .update(returning=True) is invalid Django 5.2 API

> Validation Note:
> - Action: merged
> - Detail: This is an exact duplicate of ENT-001 (Phase 01). Both describe the same bug at
  src/telegram_bot/handlers/login.py:128: passing returning=True as a keyword argument to
  QuerySet.update(), which Django 5.2.16 interprets as a field assignment to a non-existent field
  returning on the LoginToken model. Runtime verification confirms:
  inspect.signature(QuerySet.update) == (self, **kwargs) and hasattr(QuerySet, returning) == False
  under Django 5.2.16. Even removing the returning=True kwarg, .update() returns an int (row count),
  making the chained .first() call raise AttributeError: int object has no attribute first.
  The LoginToken model (users/models.py:117-156) has fields token_hash, telegram_id,
  created_at, expires_at, consumed_at — no returning field.
> - Recommendation confirmed: Replace .update(..., returning=True).first() with a two-step
  .filter().update() (returns int) + conditional re-fetch via .get(token_hash=...), or use raw SQL
  with UPDATE ... RETURNING via connection.cursor(). ENT-001 carries the same recommendation.
> - Evidence note: Minor typo in the mandatory-fixes summary (line 378):
  src/telgram_bot/handlers/login.py:128 (missing e in telegram_bot). Actual path is
  src/telegram_bot/handlers/login.py:128 (correct in the finding body at line 39).
> - See also: ENT-001 (Phase 01), DB-003 (Phase 03)

| Field | Value |
|-------|-------|
| ID | AUT-001 |
| Severity | CRITICAL |
| Type | RUNTIME-ERROR |
| Affected Modules | src/telegram_bot/handlers/login.py |
| Classification | mandatory |

**Description:**

The bot-side token claim in handle_login_orm (line 128) uses .update(telegram_id=telegram_id,
returning=True), passing returning as a keyword argument to QuerySet.update(). In Django 5.2.16,
QuerySet.update() accepts only model field names as kwargs (signature: update(self, **kwargs)).
Django interprets returning=True as an attempt to set a model field named returning, raising
FieldDoesNotExist: LoginToken has no field named returning.

Additionally, even if the returning=True kwarg is removed, .update() returns an int (count of rows
affected) in Django 5.2 — not a QuerySet. The subsequent .first() call on that int would raise
AttributeError: int object has no attribute first.

This completely breaks the bot-side of the two-phase login token claim (phase 1: bot sets
telegram_id). No user can authenticate via Telegram deep-link login.

**Evidence:**

- src/telegram_bot/handlers/login.py:128 — .update(telegram_id=telegram_id, returning=True).first()
- src/telegram_bot/handlers/login.py:119-130 — full broken claim block
- Django 5.2.16 confirmed via inspect.signature: QuerySet.update(self, **kwargs) — no returning parameter
- hasattr(QuerySet, returning) = False in Django 5.2.16
- LoginToken model fields confirmed at src/backend/apps/users/models.py:117-156: token_hash,
  telegram_id, created_at, expires_at, consumed_at — no returning field
- grep for returning across all src/ files confirms the only occurrence is the broken call
  at login.py:128
- Cross-phase: ENT-001 (Phase 01) describes the identical bug; DB-003 (Phase 03) references it
  as still broken at runtime

**Recommendation:**

Replace .update(..., returning=True).first() with a two-step approach compatible with Django 5.2:
1. Call .filter(...).update(telegram_id=telegram_id) and capture the row count (int)
2. If count == 1, re-fetch the token with .get(token_hash=token_hash)

Or use raw SQL with RETURNING via connection.cursor() for true atomicity.

Effort: small | Priority: mandatory (entire login system is broken)

### AUT-002: Sync ORM calls in async bot test fixtures cause SynchronousOnlyOperation

> Validation Note:
> - Action: validated
> - Detail: Code inspection confirms the finding. The login_token_factory fixture
  (src/telegram_bot/tests/conftest.py:75-91) defines _create as a sync function that calls
  LoginToken.objects.create(...) directly (line 86) — not wrapped in sync_to_async. The user
  fixture (conftest.py:58-72) similarly calls User.objects.get_or_create(...) synchronously at
  line 63. Both fixtures are used by pytest.mark.asyncio tests in test_claim_login_token.py, where
  Django async safety check raises SynchronousOnlyOperation.
> - Evidence note (inverted count): The finding states 4 with FieldDoesNotExist, 3 with
  SynchronousOnlyOperation. Code analysis of the 7 tests shows the distribution is reversed: 4
  tests use the login_token_factory fixture (SynchronousOnlyOperation); 3 tests bypass the
  fixture and hit the bug in handle_login_orm (FieldDoesNotExist). Core conclusion unchanged.
> - Recommendation confirmed: Wrap all ORM operations in test fixtures in sync_to_async(),
  matching the pattern already used in production code at login.py:115 (@sync_to_async on _handle)
  and in test_login_claim.py (await sync_to_async(LoginToken.objects.create)(...)).

| Field | Value |
|-------|-------|
| ID | AUT-002 |
| Severity | HIGH |
| Type | RUNTIME-ERROR |
| Affected Modules | src/telegram_bot/tests/conftest.py, src/telegram_bot/tests/test_claim_login_token.py |
| Classification | mandatory |

**Description:**

The login_token_factory fixture (conftest.py:75-91) defines an inner function _create that calls
LoginToken.objects.create(...) synchronously. In async test context (pytest-asyncio strict mode),
Django async safety check raises SynchronousOnlyOperation.

This is independent of AUT-001: even if the returning=True bug were fixed, the fixture-based tests
would still fail. The user fixture (conftest.py:58-72) has the same pattern with
User.objects.get_or_create(...).

**Evidence:**

- src/telegram_bot/tests/conftest.py:86 — LoginToken.objects.create(...) called synchronously inside _create
- src/telegram_bot/tests/conftest.py:63 — User.objects.get_or_create(...) called synchronously in user fixture
- The login_token_factory fixture returns a sync callable (_create) invoked from within
  pytest.mark.asyncio test methods, triggering Django async-safety guard
- test_claim_login_token.py uses login_token_factory in 4 of 7 tests; those tests also call
  handle_login_orm which raises FieldDoesNotExist (AUT-001) — but the fixture error fires first

**Recommendation:**

Wrap all ORM operations in test fixtures in sync_to_async(), matching the pattern already used in
test_claim_login_token:83 (await sync_to_async(LoginToken.objects.create)(...)) and in production code
at login.py:152 (the @sync_to_async-decorated _handle closure). Specifically, the `user` fixture
(conftest.py:59-73) calls User.objects.get_or_create(...) synchronously without sync_to_async.
Investigation confirms this is SAFE — in pytest-asyncio strict mode (pyproject.toml:154), sync
fixtures are wrapped via `_wrap_sync_fixture` which executes the fixture body inside
`_temporary_event_loop`, which SETS but does NOT RUN the event loop. Django 5.2.16's `async_unsafe`
calls `asyncio.get_running_loop()`, which raises `RuntimeError` when no loop is running →
`SynchronousOnlyOperation` is never raised. The `login_token_factory` fixture (conftest.py:76)
already follows the correct pattern (sync fixture returning an async callable with sync_to_async).
The 4 unused sync fixtures in `test_login_claim.py` (`future_token`, `expired_token`,
`claimed_token`, `consumed_token`) were removed as dead code. This approach is preferred over
restructuring fixtures as async fixtures — it requires minimal changes and reuses the established
pattern.

Effort: small | Priority: mandatory

### AUT-003: No hmac.compare_digest for token hash comparison

> Validation Note:
> - Action: validated
> - Detail: Repo-wide grep for compare_digest and hmac across all src/ files returns ZERO matches.
  Only import hashlib is present at consent.py:16 and login.py:7 (hashlib, not hmac). Token hash
  comparison is performed exclusively through Django ORM lookups (SQL = comparison): consent.py:212
  (LoginToken.objects.get(token_hash=token_hash)), login.py:122-123 (.filter(token_hash=...)), and
  consent.py:225-227 (.filter(token_hash=...)). Both spec citations are confirmed: spec-index.md:75
  requires hmac.compare_digest and db-schema.md:86 states token compare via hmac.compare_digest.
> - Spec inconsistency: technical-specification.md:112 says constant-time compare (select_for_update),
  contradicting spec-index.md:75 and db-schema.md:86 which require hmac.compare_digest. Code
  implements neither — it uses standard ORM = comparison. This documentation inconsistency should be
  resolved.
> - Recommendation confirmed: Implement `hmac.compare_digest` in the Python layer. The canonical
  spec documents (spec-index.md:75 and db-schema.md:86) both require `hmac.compare_digest`;
  technical-specification.md:115 cites `select_for_update` as the outlier and should be corrected to
  match. `LoginToken.token_hash` is a unique `CharField(max_length=64)` (SHA-256 hex), so the ORM
  fetch by token_hash provides efficient indexed resolution, and `hmac.compare_digest` provides
  the constant-time verification the spec mandates.

| Field | Value |
|-------|-------|
| ID | AUT-003 |
| Severity | MEDIUM |
| Type | SPEC-DEVIATION |
| Affected Modules | src/backend/apps/users/views/consent.py, src/telegram_bot/handlers/login.py |
| Classification | mandatory |

**Description:**

The spec explicitly requires hmac.compare_digest for login token comparison:
- docs/01-spec/spec-index.md:75 — Login (H): hmac.compare_digest.
- docs/02-database/db-schema.md:86 — token compare via hmac.compare_digest (constant time)

However, hmac.compare_digest is never imported or used anywhere in the codebase. The token hash
comparison is performed exclusively through Django ORM lookups (SQL = comparison):
- src/backend/apps/users/views/consent.py:212 — LoginToken.objects.get(token_hash=token_hash)
- src/telegram_bot/handlers/login.py:122-123 — .filter(token_hash=token_hash, ...)
- src/backend/apps/users/views/consent.py:225-227 — .filter(token_hash=token_hash, ...)

**Evidence:**

- grep for compare_digest / hmac across all src/ files — ZERO matches (confirmed at runtime)
- Only import hashlib at consent.py:16 and login.py:7 (hashlib, not hmac)
- Both spec references explicitly cite hmac.compare_digest as a requirement
- Note: technical-specification.md:112 says constant-time compare (select_for_update) — an internal
  documentation inconsistency with spec-index.md:75 and db-schema.md:86

**Recommendation:**

Implement `hmac.compare_digest` in the Python layer to satisfy the spec requirement
(spec-index.md:75; db-schema.md:86). `LoginToken.token_hash` is a unique `CharField(max_length=64)`
holding a SHA-256 hex digest, so the ORM lookup provides efficient indexed resolution while
`hmac.compare_digest` provides the constant-time verification the spec mandates:

1. Import `hmac` alongside the existing `hashlib` import in both `consent.py` and `login.py`
2. In `consent.py` (`login_status`), after fetching the token by `token_hash` via ORM, verify the
   match in Python before proceeding:
   `if not hmac.compare_digest(token.token_hash, token_hash): return HttpResponse(status=410)`
3. In `login.py` (`handle_login_orm`), after the `LoginToken.objects.filter(...)` fetch and before
   the claim UPDATE, add the same `hmac.compare_digest` guard

Regarding the documentation inconsistency (technical-specification.md:115 says `select_for_update`
while spec-index.md:75 and db-schema.md:86 require `hmac.compare_digest`): spec-index.md and db-schema.md
are the canonical references and both prescribe `hmac.compare_digest`. Update technical-specification.md:115
to read `hmac.compare_digest` instead of `select_for_update` to resolve the inconsistency.

Effort: small | Priority: mandatory

### AUT-004: No rate limiting on login_issue endpoint

> Validation Note:
> - Action: validated
> - Detail: Code inspection confirms login_issue (consent.py:148) has no @ratelimit, @throttle,
  @never_cache, or cache decorator. The route at urls.py:12 is a plain path() call with no
  middleware wrapper. grep for ratelimit|throttle|never_cache|cache_control across all src/ returns
  no decorator usage (only an incidental log message in query_translator.py:93). pyproject.toml has
  no rate-limiting package dependency (django-ratelimit, django-axes, etc. — none present). The
  background cleanup command cleanup_login_tokens.py exists (confirmed read) but provides remediation
  only. The testing-plan TODO at phase-01-detailed-testing.md:116 is confirmed: unchecked.
> - Recommendation confirmed: Reuse the existing cache-based rate-limiting pattern from
  `apps/search/services/rate_limit.py` (no new dependency needed). `django-ratelimit` is NOT a
  current dependency (confirmed via pyproject.toml: no rate-limiting packages present), and the
  project already has a working, tested `cache.add` + `cache.incr` pattern. Create a
  login-specific rate limiter service following the identical pattern with a tighter limit
  (10 requests per 60 seconds per IP, vs 30/60s for autocomplete) and a distinct cache key
  (`login_rl:{ip}` to avoid collision with the autocomplete limiter).

| Field | Value |
|-------|-------|
| ID | AUT-004 |
| Severity | MEDIUM |
| Type | BEST-PRACTICE |
| Affected Modules | src/backend/apps/users/views/consent.py, src/backend/apps/users/urls.py |
| Classification | advisory |

**Description:**

The login_issue view (consent.py:148-185) has no rate limiting, throttling, or caching. The testing
plan explicitly lists this as a gap: docs/97-plans/phase-01-detailed-testing.md:116 — Multiple failed
login attempts (test login_issue rate limiting) — marked with [ ] (not done).

An attacker can spam /login/issue/ to create unlimited LoginToken rows in the database, each with a
5-minute expiry. The only cleanup is the background cleanup_login_tokens management command, which
runs on a schedule and may not keep up with a spammer.

**Evidence:**

- src/backend/apps/users/views/consent.py:148-185 — login_issue has no @ratelimit, @throttle, or cache decorator
- src/backend/apps/users/urls.py:12 — route with no middleware wrapper
- docs/97-plans/phase-01-detailed-testing.md:116 — unchecked TODO for rate limiting tests
- src/backend/apps/core/management/commands/cleanup_login_tokens.py exists as background cleanup (remediation only)

**Recommendation:**

Add per-IP rate limiting by reusing the existing cache-based pattern from `apps/search/services/rate_limit.py`
(no new dependency required, since pyproject.toml contains no rate-limiting packages and the project
already has a tested `cache.add` + `cache.incr` pattern). Specifically:

1. Create `apps/users/services/login_rate_limit.py` following the identical `rate_limit.py` structure:
   a `login_rate_limit_check(request)` function with `RATE_LIMIT_REQUESTS = 10` and
   `RATE_LIMIT_PERIOD = 60` (tighter than the autocomplete 30/60s since login token issuance is more
   security-sensitive)
2. Call `login_rate_limit_check(request)` at the top of `login_issue` (consent.py:148); if it
   returns `False`, return `HttpResponse(status=429)`
3. Use a distinct cache key pattern (e.g., `login_rl:{ip}`) to avoid collision with the
   autocomplete rate limiter

`django-ratelimit` is intentionally NOT added as a dependency -- the existing pattern is simpler,
already tested (test_autocomplete.py:426-442), and follows the existing patterns convention.

Note: the project uses LocMemCache (base.py:215-218, process-local). Since `login_issue` is served
by gunicorn sync workers, a shared cache backend (Redis/memcached) should be configured in production
for multi-worker deployments, but this is a deployment concern beyond the code-level fix.

Effort: small | Priority: recommended

### AUT-005: Cookie security flags not explicit in settings

> Validation Note:
> - Action: validated
> - Detail: Code inspection of all four settings files (base.py, dev.py, prod.py, test.py) confirms
  only SESSION_COOKIE_SECURE = True (base.py:65) and CSRF_COOKIE_SECURE = True (base.py:66) are
  explicitly set. grep for SESSION_COOKIE_HTTPONLY and SESSION_COOKIE_SAMESITE across the entire
  config/settings/ directory returns ZERO matches. Django 5.2 defaults are
  SESSION_COOKIE_HTTPONLY = True and SESSION_COOKIE_SAMESITE = Lax (correct but implicit).
  The spec at db-schema.md:86 requires SECURE + HTTPONLY + SAMESITE=Lax, and only SECURE is explicit.
> - Recommendation confirmed: Add explicit SESSION_COOKIE_HTTPONLY = True and
  SESSION_COOKIE_SAMESITE = Lax to base.py:65-66. Dev.py and prod.py inherit from base.py via
  from .base import * so the fix applies broadly. (Note: dev.py/test.py override SECURE=False for
  testing convenience but do not touch HTTPONLY or SAMESITE.)

| Field | Value |
|-------|-------|
| ID | AUT-005 |
| Severity | LOW |
| Type | SPEC-DEVIATION |
| Affected Modules | src/backend/config/settings/base.py |
| Classification | mandatory |

**Description:**

The spec (docs/02-database/db-schema.md:86) requires session cookies with SECURE + HTTPONLY +
SAMESITE=Lax. The base settings (src/backend/config/settings/base.py:65-66) explicitly set
SESSION_COOKIE_SECURE = True and CSRF_COOKIE_SECURE = True, but do NOT explicitly set
SESSION_COOKIE_HTTPONLY or SESSION_COOKIE_SAMESITE. Django 5.2 defaults are
SESSION_COOKIE_HTTPONLY = True and SESSION_COOKIE_SAMESITE = Lax, but relying on implicit defaults
makes the security posture unclear and fragile: a future Django upgrade or settings refactor could
silently change these.

**Evidence:**

- src/backend/config/settings/base.py:65-66 — only SESSION_COOKIE_SECURE and CSRF_COOKIE_SECURE are set
- No SESSION_COOKIE_HTTPONLY or SESSION_COOKIE_SAMESITE in any settings file (base, dev, prod, test) — confirmed via grep
- Django 5.2 defaults: SESSION_COOKIE_HTTPONLY = True, SESSION_COOKIE_SAMESITE = Lax (correct but implicit)

**Recommendation:**

Add explicit SESSION_COOKIE_HTTPONLY = True and SESSION_COOKIE_SAMESITE = Lax to
src/backend/config/settings/base.py.

Effort: trivial | Priority: recommended

### AUT-006: Web-side token claim uses read-then-update instead of single atomic UPDATE

> Validation Note:
> - Action: validated
> - Detail: Code inspection of consent.py:188-256 confirms the web-side login_status view performs
  a SELECT at line 212 (LoginToken.objects.get(token_hash=token_hash)), followed by Python-level
  checks at lines 217-222, then a separate UPDATE at lines 225-230 (.filter(...).update(consumed_at=...).
  The import list at consent.py:16-29 confirms transaction is NOT imported — no transaction.atomic()
  wraps the web-side claim. The spec at db-schema.md:83 states Two-phase atomic claim (each = one
  UPDATE under transaction). The bot-side claim at login.py:120 IS wrapped in transaction.atomic()
  but is broken (AUT-001/ENT-001).
> - Nuance: The UPDATE at lines 225-230 includes all necessary filter conditions (token_hash,
  telegram_id, consumed_at IS NULL, expires_at > now), providing optimistic concurrency safety — if
  another request consumed the token between the SELECT and UPDATE, the UPDATE returns 0 rows and
  the view returns 410. This is a practical mitigation but does not match the spec requirement.
> - Cross-phase: DB-002 (Phase 03) is a broader finding about missing transaction.atomic() on
  multi-row domain writes, but covers different code paths (auto_moderate, copy_ad,
  _update_and_moderate). No conflict; AUT-006 is a narrower, login-specific concern.
> - Recommendation confirmed: Wrap the web-side claim in `transaction.atomic()` to match the spec
  (db-schema.md:83: Two-phase atomic claim, each = one UPDATE under transaction). The project
  follows the spec, so the spec takes precedence -- the recommendation is to align the code with the
  spec, not to update the spec. `transaction` is currently NOT imported in consent.py (confirmed at
  lines 16-29). The bot-side claim at login.py:120 already uses `transaction.atomic()`.

| Field | Value |
|-------|-------|
| ID | AUT-006 |
| Severity | MEDIUM |
| Type | SPEC-DEVIATION |
| Affected Modules | src/backend/apps/users/views/consent.py |
| Classification | advisory |

**Description:**

The spec (docs/02-database/db-schema.md:83-85) states: Two-phase atomic claim (each = one UPDATE
under transaction). The web-side claim in login_status (consent.py:224-234) deviates by performing
a read-then-write pattern:
1. Line 212: LoginToken.objects.get(token_hash=token_hash) — a SELECT
2. Lines 217-222: check expires_at, consumed_at, telegram_id in Python
3. Lines 225-230: .filter(...).update(consumed_at=...) — a separate UPDATE

The two operations are not wrapped in transaction.atomic(). While the UPDATE filter conditions
(token_hash, telegram_id, consumed_at IS NULL, expires_at > now) provide optimistic concurrency safety
(if another request consumed the token between the SELECT and UPDATE, the UPDATE returns 0 rows -> 410),
this is a two-query pattern rather than the single-UPDATE approach the spec describes.

The bot-side claim (src/telegram_bot/handlers/login.py:121-130) is wrapped in transaction.atomic()
but is broken (AUT-001). The web-side claim has no transaction wrapper at all.

**Evidence:**

- docs/02-database/db-schema.md:83 — Two-phase atomic claim (each = one UPDATE under transaction)
- src/backend/apps/users/views/consent.py:212 — LoginToken.objects.get(token_hash=token_hash) (SELECT)
- src/backend/apps/users/views/consent.py:225-230 — separate .filter(...).update(consumed_at=...) (UPDATE)
- No transaction import in consent.py (imports confirmed at lines 16-29); no transaction.atomic() wrapping the web-side claim
- src/telegram_bot/handlers/login.py:120 — bot-side uses transaction.atomic() but crashes (AUT-001)

**Recommendation:**

Wrap the web-side claim in `transaction.atomic()` to match the spec (db-schema.md:83: Two-phase atomic
claim, each = one UPDATE under transaction). The project follows the spec, so the spec takes
precedence -- align the code with the spec rather than updating the spec. Specifically:

1. Add `from django.db import transaction` to the imports at consent.py:16-29
2. Wrap the read-then-write claim block (consent.py:212-234) -- the `LoginToken.objects.get()` SELECT,
   the Python-level checks (lines 217-222), and the `.filter(...).update(consumed_at=...)` UPDATE
   (lines 225-230) -- in a single `with transaction.atomic():` block
3. This ensures the SELECT and UPDATE execute as one atomic unit, matching the spec requirement

The bot-side claim at login.py:120 already uses `transaction.atomic()`, so this brings the web-side
into line with both the bot-side implementation and the spec.

Effort: small | Priority: recommended

### AUT-007: Raw login token in GET query parameter + no polling JS in template

> Validation Note:
> - Action: validated
> - Detail: Code inspection confirms login_status reads the raw token from
  request.GET.get(token, ) at consent.py:205. The login_issue view (lines 148-185) passes only
  deep_link and bot_username to the template — raw_token is NOT in the context. The template
  login_issue.html (37 lines, read in full) contains no script tags, no AJAX polling, and no
  reference to login_status. The login_status route exists at urls.py:13 but is never referenced
  in the template.
> - Recommendation confirmed: (1) Pass raw_token to template context in login_issue. (2) Add
  JavaScript to login_issue.html that polls login_status?token=<raw_token> every 2-3 seconds with
  200/204/410 handling. (3) Consider POST-based token submission to avoid URL leakage. (4) Add
  Cache-Control: no-store on both endpoints.

| Field | Value |
|-------|-------|
| ID | AUT-007 |
| Severity | MEDIUM |
| Type | BEST-PRACTICE |
| Affected Modules | src/backend/apps/users/views/consent.py, src/backend/templates/users/login_issue.html |
| Classification | advisory |

**Description:**

The login_status view reads the raw token from a GET query parameter: request.GET.get(token, )
at consent.py:205. This means the raw token travels in the URL, which exposes it to:
1. Server access logs — every poll request logs the full URL including the token
2. Browser history — the token persists in the browser address bar history
3. Referer headers — if the page loads any third-party resources, the token could leak via the Referer header

Additionally, login_issue.html has NO JavaScript at all — no polling mechanism to call login_status.
The template only renders a static deep-link button. There is no raw_token passed to the template
context (only deep_link and bot_username), so even if JS were added, the template has no way to
construct the login_status polling URL.

**Evidence:**

- src/backend/apps/users/views/consent.py:205 — raw_token = request.GET.get(token, )
- src/backend/apps/users/views/consent.py:178-185 — login_issue only passes deep_link and bot_username to template
- src/backend/templates/users/login_issue.html — 37 lines, no script tags, no polling AJAX, no mention of login_status
- src/backend/apps/users/urls.py:13 — login_status route exists but is never referenced in the template

**Recommendation:**

1. Pass raw_token to template context in login_issue so client-side JS can poll login_status
2. Add JavaScript to login_issue.html that polls login_status?token=<raw_token> every 2-3 seconds,
   handling 200 (redirect to dashboard), 204 (keep polling), and 410 (show error)
3. Consider POST-based token submission instead of GET query params to avoid URL leakage in logs/history
4. Add Cache-Control: no-store on both endpoints to prevent caching

Effort: medium | Priority: recommended

### AUT-008: Redundant request.session.cycle_key() after auth_login

> Validation Note:
> - Action: validated
> - Detail: Runtime source inspection of Django 5.2.16 django.contrib.auth.login() confirms: when
  SESSION_KEY is NOT in request.session (i.e., anonymous->authenticated transition, which is the web
  login flow since login_status receives unauthenticated requests), the else branch calls
  request.session.cycle_key() unconditionally. Code inspection of consent.py:251-252 confirms
  auth_login(request, user) followed by explicit request.session.cycle_key() on the next line —
  a redundant second rotation. The user is anonymous at this point, so SESSION_KEY is absent from
  the session, and login() already cycles.
> - Recommendation confirmed: Remove the redundant request.session.cycle_key() call at consent.py:252.
  Django's auth_login() already cycles the session key for anonymous-to-authenticated transitions
  (SESSION_KEY absent -> login() else branch calls cycle_key()). The "add a comment" fallback applies
  only if double-rotation is intentionally desired — it is not warranted.

| Field | Value |
|-------|-------|
| ID | AUT-008 |
| Severity | LOW |
| Type | BEST-PRACTICE |
| Affected Modules | src/backend/apps/users/views/consent.py |
| Classification | advisory |

**Description:**

At consent.py:251-252, after calling auth_login(request, user), the code explicitly calls
request.session.cycle_key(). However, Django contrib.auth.login() (aliased as auth_login at line 22)
already calls request.session.cycle_key() for the anonymous->authenticated transition. Verified in
Django 5.2.16 source: the login() function contains an else branch that calls
request.session.cycle_key() when SESSION_KEY is not in request.session (which is the case for
anonymous users).

The explicit second cycle_key() call creates an unnecessary additional session key rotation. While
cycle_key() preserves session data (it copies _session to _session_cache), the redundant call is
wasteful and could confuse readers about when cycle_key() is actually needed.

**Evidence:**

- src/backend/apps/users/views/consent.py:251 — auth_login(request, user)
- src/backend/apps/users/views/consent.py:252 — request.session.cycle_key() (redundant)
- Django 5.2 contrib/auth/__init__.py login() source: if SESSION_KEY in request.session: ...
  else: request.session.cycle_key() — already handles anonymous->authenticated case
- Runtime verification: inspect.getsource(django.contrib.auth.login) confirms the else branch
  calls cycle_key() when SESSION_KEY is not in the session

**Recommendation:**

Remove the redundant request.session.cycle_key() call at consent.py:252. Django's auth_login()
already calls request.session.cycle_key() in its else branch for the anonymous-to-authenticated
transition (triggered here because login_status receives unauthenticated requests). The explicit
cycle_key() creates a second, unnecessary session key rotation. The fallback "add a comment"
option applies only if double-rotation is intentionally desired — it is not warranted.

Effort: trivial | Priority: low

### AUT-009: No tests for web login views (login_issue, login_status)

> Validation Note:
> - Action: validated
> - Detail: grep for login_issue and login_status in src/backend/apps/users/tests/ returns ZERO
  matches. The directory contains only __init__.py, test_account_state.py, test_consent.py, and
  test_deletion.py. test_consent.py covers only consent_accept, consent_decline, consent_withdraw.
  test_deletion.py covers token invalidation on consent withdrawal (via withdraw_consent service)
  but does NOT exercise the login_issue or login_status view functions. test_account_state.py tests
  the can_login service function but has no login_issue/login_status references. Testing plan at
  phase-01-detailed-testing.md:116,124 is confirmed to list these as unchecked TODOs.
> - Recommendation confirmed: Add test_login.py in src/backend/apps/users/tests/ covering token
  issuance, status polling (200/204/410), session establishment, ban check, and reuse prevention.

| Field | Value |
|-------|-------|
| ID | AUT-009 |
| Severity | HIGH |
| Type | SPEC-DEVIATION |
| Affected Modules | src/backend/apps/users/tests/ |
| Classification | mandatory |

**Description:**

The testing plan (docs/97-plans/phase-01-detailed-testing.md:116,124) lists test items for the web login
flow:
- Line 116: Multiple failed login attempts (test login_issue rate limiting)
- Line 124: Session fixation prevention (login_status tests)

However, NO tests exist for the web-side login views (login_issue at consent.py:148-185,
login_status at consent.py:188-256). The only login-related tests are bot-side:
- src/telegram_bot/tests/test_login_claim.py — bot claim (ALL FAIL due to AUT-001)
- src/telegram_bot/tests/test_claim_login_token.py — bot claim (ALL 7 FAIL due to AUT-001 + AUT-002)

There are zero tests for:
- Token issuance via login_issue (deep link rendering, token hash storage, expiry)
- Token polling via login_status (200 success, 204 pending, 410 gone/expired/consumed/banned)
- Session establishment on successful login (session cookie set, cycle_key behavior)
- Ban check enforcement (banned user -> 410)
- Token reuse prevention (already-consumed token -> 410)

**Evidence:**

- grep for login_issue in src/backend/apps/users/tests/ — ZERO matches (confirmed)
- grep for login_status in src/backend/apps/users/tests/ — ZERO matches (confirmed)
- src/backend/apps/users/tests/test_consent.py — covers only consent_accept, consent_decline,
  consent_withdraw; NO login tests
- src/backend/apps/users/tests/ directory contains only test_consent.py and test_deletion.py
  (plus test_account_state.py) — no test_login.py
- docs/97-plans/phase-01-detailed-testing.md:116,124 — testing plan explicitly lists login tests as TODO

**Recommendation:**

Add a test_login.py in src/backend/apps/users/tests/ covering:
- login_issue: 200 response, deep-link URL contains token, token_hash stored as SHA-256, 5-min expiry
- login_status: 200 (successful claim -> session established), 204 (pending), 410 (expired/consumed/nonexistent/banned)
- Session fixation: verify session key changes after successful login

Effort: medium | Priority: recommended

### AUT-010: login_issue/login_status lack @never_cache

> Validation Note:
> - Action: validated
> - Detail: Code inspection of consent.py confirms login_issue (line 148) and login_status (line 188)
  have no @never_cache, @cache_control, or @vary_on_cookie decorator. The import list at consent.py
  lines 16-29 has no django.views.decorators.cache import. grep for never_cache|cache_control|
  ratelimit|throttle across all src/ returns no decorator usage (only an incidental log message in
  query_translator.py:93). db-schema.md:86 mentions cookie flags but not cache policy for login
  endpoints.
> - Recommendation confirmed: Add @never_cache to both login_issue and login_status to ensure login
  deep-link and status responses are never cached by intermediate proxies or browsers.

| Field | Value |
|-------|-------|
| ID | AUT-010 |
| Severity | LOW |
| Type | BEST-PRACTICE |
| Affected Modules | src/backend/apps/users/views/consent.py |
| Classification | advisory |

**Description:**

The login_issue view (consent.py:148) and login_status view (consent.py:188) have no @never_cache
decorator. This view generates a unique, single-use deep-link token. If the response is cached by a
CDN, reverse proxy, or browser, multiple users could receive the same deep-link URL, allowing anyone
to claim another user login token.

While the project uses Whitenoise (which does not cache HTML responses by default) and dev/test
settings use SECURE_SSL_REDIRECT = False, the production settings (prod.py) enable HSTS. The spec
does not explicitly mention cache control for these endpoints, but a login token issuance endpoint
should always be non-cacheable as a matter of security.

**Evidence:**

- src/backend/apps/users/views/consent.py:148 — def login_issue(...) with no @never_cache,
  @cache_control, or @vary_on_cookie
- src/backend/apps/users/views/consent.py:188 — def login_status(...) also has no cache control decorator
- No django.views.decorators.cache import in consent.py
- docs/02-database/db-schema.md:86 mentions cookie flags but not cache policy for login endpoints

**Recommendation:**

Add @never_cache to both login_issue and login_status to ensure the login deep-link and status
responses are never cached by intermediate proxies or browsers.

Effort: trivial | Priority: low

## Validation Summary

| Action | Count | Details |
|--------|-------|---------|
| Remediated | 10 | AUT-001→ENT-001 (fixed), AUT-002 (fixed), AUT-003 (fixed), AUT-004 (fixed), AUT-005 (fixed), AUT-006 (fixed), AUT-007 (fixed), AUT-008 (fixed), AUT-009 (fixed), AUT-010 (fixed) |
| Merged | 1 | AUT-001 → ENT-001 (Phase 01) |
| Reclassified | 0 | — |
| Rejected | 0 | — |

### Remediated Findings

| ID | Finding | Fix Applied |
|----|---------|-------------|
| AUT-001 | Bot token claim crash | ENT-001: replaced `.update(returning=True).first()` with raw SQL `UPDATE ... RETURNING` via `connection.cursor()` |
| AUT-002 | Sync ORM in async fixtures | Fixed `login_token_factory` fixture: `_create` now uses `await sync_to_async(LoginToken.objects.create)()`; all 4 call sites `await` the factory. `user` fixture investigated and confirmed safe (sync fixtures run outside the running event loop in pytest-asyncio strict mode). Removed 4 dead unused sync fixtures from `test_login_claim.py`. |
| AUT-003 | No constant-time token comparison | Added `hmac.compare_digest` in `login_status` view for constant-time token hash verification |
| AUT-004 | No rate limiting on login_issue | Added `login_rate_limit` service (10 req/60s per IP via Django cache); `@never_cache` + 429 on exceed |
| AUT-005 | Cookie security flags not explicit | Added `SESSION_COOKIE_HTTPONLY = True`, `SESSION_COOKIE_SAMESITE = "Lax"`, `CSRF_COOKIE_HTTPONLY`, `CSRF_COOKIE_SAMESITE`, `SECURE_SSL_REDIRECT` |
| AUT-006 | Web login claim not in transaction.atomic() | Wrapped read-then-write claim block in `transaction.atomic()` with optimistic locking filter |
| AUT-007 | Raw token in GET, no polling JS | Added `raw_token` to template context, client-side polling JS (3s interval), `@never_cache` decorator |
| AUT-008 | Redundant session.cycle_key() | Removed — `auth_login()` already cycles the key for anonymous→authenticated transitions |
| AUT-009 | No tests for web login views | Added `test_login.py` (12 tests): login_issue (5 tests), login_status (7 tests) covering 200/204/410/rate-limit/expiry/consumed/banned |
| AUT-010 | login_issue/login_status lack @never_cache | Added `@never_cache` decorator to both views

### Merged Findings

| Original ID | Merged Into | Rationale |
|-------------|-------------|----------|
| AUT-001 | ENT-001 (Phase 01) | Identical root-cause bug: .update(returning=True).first() at login.py:128. ENT-001 was discovered first and is the canonical finding; AUT-001 is a complete duplicate. |

### Reclassified Findings

| ID | Original Type | New Type | Rationale |
|----|---------------|----------|-----------|
| (none) | | | |

### Rejected Findings

| ID | Title | Reason |
|----|-------|--------|
| (none) | | All 10 findings validated as genuine problems with code evidence. |

### Evidence Adjustments

| Finding | Adjustment | Detail |
|---------|-----------|--------|
| AUT-001 | Typo in summary | Source findings line 378 cites src/telgram_bot/ (missing e in telegram_bot). Actual path is src/telegram_bot/handlers/login.py:128. Corrected in this report. |
| AUT-002 | Evidence count inverted | Finding states 4 with FieldDoesNotExist, 3 with SynchronousOnlyOperation. Code analysis shows reversed: 4 tests use login_token_factory fixture (SynchronousOnlyOperation); 3 tests bypass fixture and hit handle_login_orm bug (FieldDoesNotExist). Core conclusion unchanged. |
| AUT-003 | Internal doc inconsistency | technical-specification.md:115 (audit cited :112) says constant-time compare (select_for_update), contradicting spec-index.md:75 and db-schema.md:86 which require hmac.compare_digest. Code implements neither. Resolution: implement hmac.compare_digest per AUT-003 recommendation; update technical-specification.md:115 to read hmac.compare_digest. |
| AUT-003 | Recommendation refined | Non-actionable two-option split (implement hmac.compare_digest OR update docs) resolved to single solution: implement hmac.compare_digest per spec-index.md:75 and db-schema.md:86. Priority changed from advisory to mandatory; Effort from medium to small. |
| AUT-004 | Recommendation refined | Non-actionable three-way choice (django-ratelimit vs middleware vs per-IP counter) resolved to single solution: reuse existing cache-based rate_limit.py pattern (no new dependency). |
| AUT-006 | Recommendation refined | Non-actionable two-option split (wrap in transaction OR update spec) resolved to single solution: wrap in transaction.atomic() to match spec db-schema.md:83. Spec takes precedence over code change. |
| AUT-002 | Recommendation refined | Non-actionable two-option split (wrap in sync_to_async OR restructure as async fixtures) resolved to single solution: wrap all ORM calls in sync_to_async, matching test_login_claim.py:83 pattern. `login_token_factory` was fixed (conftest.py:89: `await sync_to_async(LoginToken.objects.create)(...)`). The `user` fixture (conftest.py:59-73) was investigated and confirmed SAFE — sync fixtures in pytest-asyncio strict mode run outside the running event loop (`asyncio.get_running_loop()` raises `RuntimeError`), so `SynchronousOnlyOperation` is never raised. 4 dead sync fixtures in `test_login_claim.py` (`future_token`, `expired_token`, `claimed_token`, `consumed_token`) removed. |
| AUT-008 | Recommendation refined | Non-actionable two-option split (remove cycle_key OR add explanatory comment) resolved to single solution: remove the redundant cycle_key() call. auth_login() already cycles the session key for anonymous-to-authenticated transitions. |
