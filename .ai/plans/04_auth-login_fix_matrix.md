# Phase 04 — Auth/Login Fix Matrix

**Audit Report:** `.ai/audit/99-validation/04-auth-login-validated-findings.md`
**Source Findings:** `.ai/audit/99-validation/04-auth-login-findings.json`
**Classification:** `.ai/audit/99-validation/04-classification-output.json` (from researcher)
**Status:** Gap in AUT-005 identified — CSRF cookie flags missing from settings
**Phase 01 Cross-reference:** ENT-001 (AUT-001 merged into)

---

## Summary

| ID | Severity | Title | Code Fix Present? | Classification | Gap |
|----|----------|-------|--------------------|-----------------|-----|
| AUT-001 | CRITICAL | Bot token claim uses invalid `.update(returning=True)` | YES | Multiple viable routes | None |
| AUT-002 | HIGH | Sync ORM in async bot test fixtures | YES | Multiple viable routes | None |
| AUT-003 | MEDIUM | No `hmac.compare_digest` for token hash | YES | Simple / Low-risk | None |
| AUT-004 | MEDIUM | No rate limiting on login_issue | YES | Multiple viable routes | None |
| AUT-005 | LOW | Cookie security flags not explicit | **NO — gap** | Simple / Low-risk | CSRF_COOKIE_HTTPONLY, CSRF_COOKIE_SAMESITE missing |
| AUT-006 | MEDIUM | No `transaction.atomic()` around web claim | YES | Simple / Low-risk | None |
| AUT-007 | MEDIUM | Raw token in GET + no polling JS | YES | Simple / Low-risk | None |
| AUT-008 | LOW | Redundant `cycle_key()` after `auth_login` | YES | Simple / Low-risk | None |
| AUT-009 | HIGH | No tests for web login views | YES | Simple / Low-risk | None |
| AUT-010 | LOW | Missing `@never_cache` on login views | YES | Simple / Low-risk | None |

---

## Finding Details

### AUT-001 (CRITICAL) — Bot token claim crash
- **Root cause:** `.update(returning=True).first()` raises `FieldDoesNotExist` then `AttributeError` under Django 5.2.
- **Merge:** Merged into ENT-001 (Phase 01) — identical root cause at `login.py:128`.
- **Fix applied (code verified):** Raw SQL `UPDATE ... RETURNING` via `connection.cursor()` with `transaction.atomic()` in `src/telegram_bot/handlers/login.py` `_claim_login_token()`.
- **Classification:** Multiple viable routes (raw SQL vs two-step ORM fetch+update).
- **Risk:** Low — contained to one function, tests cover all paths.

### AUT-002 (HIGH) — Sync ORM in async fixtures
- **Root cause:** `login_token_factory` in `conftest.py` calls sync ORM directly, triggering `SynchronousOnlyOperation`.
- **Fix applied (code verified):** Wrapped in `sync_to_async()` — `src/telegram_bot/tests/conftest.py`.
- **Classification:** Multiple viable routes (sync_to_async vs async fixture creation).
- **Tests:** `test_login_claim.py` (5 tests), `test_claim_login_token.py` (7 tests).

### AUT-003 (MEDIUM) — Missing `hmac.compare_digest`
- **Root cause:** Token hash comparison uses plain `==` operator (timing-attack vulnerable).
- **Fix applied (code verified):** `hmac.compare_digest` used in `src/backend/apps/users/views/consent.py` and `src/telegram_bot/handlers/login.py`.
- **Doc fix:** `docs/01-spec/technical-specification.md:115` corrected from `select_for_update` to `hmac.compare_digest`.
- **Classification:** Simple / Low-risk.

### AUT-004 (MEDIUM) — No rate limiting on login_issue
- **Root cause:** `login_issue` endpoint accepts unlimited POST requests — brute-force token guessing possible.
- **Fix applied (code verified):** `login_rate_limit_check()` imported from `src/backend/apps/users/services/login_rate_limit.py` in `consent.py`; uses existing cache pattern (10 requests / 60s per IP).
- **Classification:** Multiple viable routes (django-ratelimit vs middleware vs custom cache pattern).

### AUT-005 (LOW) — Cookie security flags not explicit
- **Root cause:** `SESSION_COOKIE_SECURE`, `SESSION_COOKIE_HTTPONLY`, `SESSION_COOKIE_SAMESITE`, `CSRF_COOKIE_SECURE` are present in `base.py`, but `CSRF_COOKIE_HTTPONLY` and `CSRF_COOKIE_SAMESITE` are **missing**.
- **Audit report gap:** "Fix Applied" column claims CSRF_COOKIE_HTTPONLY and CSRF_COOKIE_SAMESITE were added — **NOT present in code**.
- **Fix to apply:** Add to `src/backend/config/settings/base.py`:
  ```python
  CSRF_COOKIE_HTTPONLY = True
  CSRF_COOKIE_SAMESITE = "Lax"
  ```
- **Classification:** Simple / Low-risk.

### AUT-006 (MEDIUM) — Web-side claim not in transaction
- **Root cause:** `login_status` view performs read-then-update of login token without `transaction.atomic()`.
- **Fix applied (code verified):** Wrapped in `transaction.atomic()` in `src/backend/apps/users/views/consent.py`.
- **Classification:** Simple / Low-risk.

### AUT-007 (MEDIUM) — Raw token in GET + no polling JS
- **Root cause:** Login token passed in GET query parameter; template has no JS polling for status check.
- **Fix applied (code verified):** `raw_token` passed to template context; polling JS added in `src/backend/templates/users/login_issue.html`.
- **Classification:** Simple / Low-risk.

### AUT-008 (LOW) — Redundant cycle_key
- **Root cause:** `request.session.cycle_key()` called after `auth_login()`, which is redundant — Django handles session cycle internally during login.
- **Fix applied (code verified):** Removed from `src/backend/apps/users/views/consent.py`.
- **Classification:** Simple / Low-risk.

### AUT-009 (HIGH) — No tests for web login views
- **Root cause:** `login_issue` and `login_status` views had no test coverage.
- **Fix applied (code verified):** 12 tests added in `src/backend/apps/users/tests/test_login.py`.
- **Classification:** Simple / Low-risk.

### AUT-010 (LOW) — Missing @never_cache
- **Root cause:** `login_issue` and `login_status` views lack `@never_cache` — responses could be cached by proxies, leaking tokens.
- **Fix applied (code verified):** `@never_cache` decorator applied to both views in `consent.py`.
- **Classification:** Simple / Low-risk.

---

## Dependency Graph

```
AUT-001 → AUT-002 (tests for claim need AUT-001 fix)
AUT-001 → AUT-003 (bot-side hmac comparison in login.py)
AUT-001 → AUT-006 (web-side atomic claim follows same pattern)
AUT-004 → AUT-009 (rate-limited login_issue needs test coverage)
AUT-005 → AUT-010 (both are response hardening for login views)
```

All dependencies satisfied — fixes applied in correct order.

---

## Rollout Safety

- No data migrations required (all fixes are code-level)
- All fixes localized to known insertion points
- No backward-compatibility concerns (new settings flags are additive; removed cycle_key is redundant)
- Tests cover all critical paths (AUT-001: 12 tests across 2 files; AUT-009: 12 tests)
- No circular dependencies

---

## Action Items

| # | Task | File(s) | Status |
|---|------|---------|--------|
| 1 | Add CSRF_COOKIE_HTTPONLY and CSRF_COOKIE_SAMESITE to settings | `config/settings/base.py` | **TODO** |
| 2 | Update audit report — correct AUT-005 "Fix Applied" to "Gap" | `04-auth-login-validated-findings.md` | **TODO** |
| 3 | Run quality gates | ruff, mypy, basedpyright, pytest | **TODO** |
| 4 | Update documentation | `docs/02-database/db-schema.md` if needed | **TODO** |
| 5 | Commit changes | git | **TODO** |
