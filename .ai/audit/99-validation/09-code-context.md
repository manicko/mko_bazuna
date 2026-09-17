# Code Context — External API Findings (Phase 09 Audit)

## Scope
Validated audit report: `.ai/audit/99-validation/09-external-api-validated-findings.md` (7 findings, EXT-001–EXT-007).

## Project Architecture
- **Two processes, one DB**: web (gunicorn sync WSGI, Django 5.2) + bot (aiogram 3.x, `django.setup()` + shared ORM).
- `src/backend/` — Django project (web process). `src/telegram_bot/` — bot process.
- Shared ORM models across both processes.
- Management commands inherit `django.core.management.base.BaseCommand`.

## Finding Status (verified against current code + git log)

| ID | Type | Priority | Action | Current State |
|----|------|----------|--------|---------------|
| EXT-001 | DOC-UPDATE | P1 | Update consent.py docstring | **ALREADY RESOLVED** — commit `140f21a` updated docstring; current `consent.py:8-14` already says "Buyer search queries are NOT sent to any translation service" |
| EXT-002 | SPEC-DEVIATION | P1 | send_alerts.py resilience fix | **NEEDS ACTION** — confirmed vulnerability present |
| EXT-003 | SPEC-DEVIATION | P2 (optional) | moderation API 400→422 | **NEEDS ACTION** — confirmed; 5 tests assert 400 |
| EXT-004 | BEST-PRACTICE | P2 | Remove dead translate_cached | **ALREADY RESOLVED** — commit `65cb355` removed `translate_cached`; test fixture updated |
| EXT-005 | BEST-PRACTICE | P2 | Remove redundant hmac.compare_digest | **NEEDS ACTION** — confirmed at `consent.py:390-392` |
| EXT-006 | BEST-PRACTICE | P2 | .gitignore for .tmp/ | **PARTIAL** — `.tmp/` files removed from git (commit `2b018a9`), but `.gitignore` has no `.tmp/` exclusion (line 220 only covers `docker/nginx/certs/*.pem`) |
| EXT-007 | BEST-PRACTICE | P2 | Bot login rate limiting | **NEEDS ACTION** — confirmed: no rate limit in `handle_login_deep_link` |

**Actionable findings: EXT-002, EXT-003 (optional), EXT-005, EXT-006, EXT-007.**

---

## EXT-002 — send_alerts.py Resilience (P1)

**File:** `src/backend/apps/search/management/commands/send_alerts.py`

**Current state (confirmed):**
- Line 13: `from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError` — only permanent-failure imports
- Line 61: `asyncio.run(self._send_user_digests(settings.BOT_TOKEN, user_ads))` — no outer try/except
- Lines 149-176: per-user loop catches only `(TelegramBadRequest, TelegramForbiddenError)` — permanent failures only; `TelegramRetryAfter` (429), `TelegramServerError` (5xx), `TelegramNetworkError` (connection) propagate and crash the entire batch

**Reference pattern:** `src/backend/apps/search/services/immediate_alerts.py`

Key patterns to mirror:
- Lines 22-29: full exception import set: `AiogramError, TelegramBadRequest, TelegramForbiddenError, TelegramNetworkError, TelegramRetryAfter, TelegramServerError`
- Lines 180-186: `_run_send` wraps `asyncio.run()` in try/except `AiogramError`
- Lines 207-237: `_send` inner handler with permanent dead-letter + transient retry-once with backoff (respects `exc.retry_after` for 429, capped `_BACKOFF_BASE=0.5` for others)
- Lines 239-242: `asyncio.gather` with `return_exceptions=True`
- Constants: `_SEND_CONCURRENCY = 10`, `_BACKOFF_BASE = 0.5`

**Key structural difference:** `send_alerts.py` iterates users sequentially in a for-loop (not asyncio.gather), so the pattern adaptation is: add transient exception handling within the per-user try block, with retry-once + backoff.

**No existing test file** for send_alerts.py. Need to create one.
**Test marker conventions:** `pytestmark = [pytest.mark.django_db, pytest.mark.slow, pytest.mark.integration]`

---

## EXT-003 — Moderation API 400→422 (P2, optional)

**File:** `src/backend/apps/moderation/views/api_bulk.py` (lines 42-46)

**Current state (confirmed):**
- Line 42-46: catches `ValidationError`, returns `JsonResponse({"error": "Invalid request body"}, status=400)`
- Lines 52-61: `MAX_BULK_ACTIONS` rejection also returns 400 (should stay 400 — it's a semantic limit, not a schema violation)
- `schemas.py:24`: `model_config = ConfigDict(extra="forbid")`

**Tests:** `src/backend/apps/moderation/tests/test_priority_service.py` (lines 611-758):
- `test_unknown_action_returns_400` (line 611) — `{"action": "unknown"}` → asserts 400
- `test_malformed_json_body_returns_400` (line 642) — `data="not-json"` → asserts 400
- `test_empty_body_returns_400` (line 656) — `data=""` → asserts 400
- `test_extra_key_returns_400` (line 670) — `{"rogue": "x"}` → asserts 400
- `test_selected_items_type_mismatch_returns_400` (line 690) — `"selected_items": "not-a-list"` → asserts 400
- `test_bulk_exceeds_max_actions_returns_400` (line 736) — should KEEP 400 (MAX_BULK_ACTIONS limit, not schema violation)

**Action:** Change ValidationError handler to return 422 + `ValidationError.errors()` as JSON body. Update 5 test assertions (rename 400→422, update docstrings). Keep MAX_BULK_ACTIONS at 400.

**Test class structure:** Tests are in a class with `self.staff_user`, `self.bulk_url`, `pytestmark = [pytest.mark.django_db, pytest.mark.slow, pytest.mark.integration]`

---

## EXT-005 — Redundant hmac.compare_digest (P2)

**File:** `src/backend/apps/users/views/consent.py` (lines 384-392)

**Current state (confirmed):**
- Line 387: `token = LoginToken.objects.get(token_hash=token_hash)` — exact-match on `unique=True, db_index=True` field
- Lines 390-392: comment + `if not hmac.compare_digest(token.token_hash, token_hash): return HttpResponse(status=410)` — no-op (values are identical after a successful get())
- `LoginToken` model (`models.py:162-167`): `token_hash = CharField(max_length=64, unique=True, db_index=True)`
- Token entropy: `secrets.token_urlsafe(24)` = ~192 bits (`consent.py:304`)
- Real protection: atomic `UPDATE ... RETURNING` with `WHERE consumed_at IS NULL` (`consent.py:406-411`)

**Action:** Remove lines 390-392 (comment + compare_digest call). The `import hmac` should be checked for other uses.

**Tests:** `src/backend/apps/users/tests/test_login.py` — `TestLoginTokenSecurity` class has `test_token_hash_mismatch_returns_410` (line 238) which should still pass after removal (hash mismatch → DoesNotExist → 410). `pytestmark = [pytest.mark.django_db, pytest.mark.slow, pytest.mark.integration]`.

---

## EXT-006 — .gitignore for .tmp/ (P2)

**Current state (confirmed):**
- `git ls-files .tmp/` returns nothing — files already removed from git (commit `2b018a9`)
- `.tmp/` directory does not exist on disk
- `.gitignore` line 219-221 covers only `docker/nginx/certs/*.pem`, NOT `.tmp/`
- No `.tmp/` exclusion exists anywhere in `.gitignore` (252 lines, verified)

**Action:** Add `.tmp/` exclusion to `.gitignore` at line 220 area (after the docker/nginx/certs section).

---

## EXT-007 — Bot Login Rate Limiting (P2)

**File:** `src/telegram_bot/handlers/login.py` (lines 34-101)

**Current state (confirmed):**
- `handle_login_deep_link` (line 35) — no rate-limiting call before `handle_login_orm` (line 95)
- `LOGIN_PATTERN = re.compile(r"^login_([A-Za-z0-9_-]{32})$")` — matches `/start login_<token>`

**Rate limit patterns to follow:** `src/telegram_bot/services/rate_limit.py`
- `check_upload_rate_limit` (lines 31-65): uses `cache.add(key, 1, timeout=period)` + `cache.incr(key)` idiom, returns `bool`
- `check_contact_start_rate_limit` (lines 83-119): same pattern, different limits (5/600s)
- Constants: `RATE_LIMIT_REQUESTS=10`, `RATE_LIMIT_PERIOD=60`, `CONTACT_RATE_LIMIT_REQUESTS=5`, `CONTACT_RATE_LIMIT_PERIOD=600`
- Decorators: `@sync_to_async`
- Cache keys: `bot_upload_rl:{user_id}`, `bot_contact_rl:{user_id}`

**Action:**
1. Add `check_login_rate_limit` to `rate_limit.py` using the `check_upload_rate_limit` idiom (10 claims/min per `message.from_user.id`, cache key `bot_login_rl:{user_id}`)
2. Call `check_login_rate_limit` at the top of `handle_login_deep_link` before token claim

**Tests:** `src/telegram_bot/tests/test_login.py` — existing bot login tests use `pytest.mark.xdist_group("bot_concurrent")`. Tests mock `message` with `MagicMock`, `handle_login_deep_link` is called directly with `message=message, bot=MagicMock(), state=state`.

**Bot middleware:** `src/telegram_bot/main.py:57-63` — middleware stack has `AccountStateMiddleware` (checks banned/deleted/etc.) but no rate limiting middleware. `permissions.py` confirms `AccountStateMiddleware` does not rate-limit.

---

## Discrepancies vs. Audit Findings Doc

1. **EXT-004 finding**: Claims `translate_cached` exists at `translation.py:107-121`. **Already removed** (commit `65cb355`). The current code has `translate_cached_generic` at line 107-108, which IS actively used (called at line 176 by `translate_text`, imported by `backfill_translations.py:39`). The dead function `translate_cached` is gone — finding is obsolete.

2. **EXT-002 finding**: References `immediate_alerts.py:22-29` in `management/commands/`. **Actual location:** `src/backend/apps/search/services/immediate_alerts.py` (not in `management/commands/`). The reference code patterns all match.

3. **EXT-001 finding**: Claims `consent.py:8-13` docstring. **Already updated** (commit `140f21a`). Current docstring (lines 8-14) already disclaims search query egress. Finding is obsolete.

4. **EXT-006 finding**: Claims `.tmp/nginx-test-certs/*.pem` are tracked in git. **Already removed** (commit `2b018a9`). Only the `.gitignore` gap remains.
