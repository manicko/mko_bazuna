---
name: audit-findings
description: Evidence-gathering (block 3) — established web-side per-IP rate-limiting idiom for mirroring into apps/core/services/contact_rate_limit.py
agent: auditor
phase: 11-bot-username-migration
block: 3
scope: "CURRENT web-side per-IP rate-limiting code ONLY — autocomplete + login. Bot process excluded (web-only)."
status: complete
validated: n/a
---

# Block 3 Audit Report — Web-Side Per-IP Deep-Link Render Rate Limiter

**Scope:** Verbatim study of the CURRENT web-side per-IP rate-limiting code only. No code was
written or modified. Output is verbatim quotes with `file:line` references, per the task brief,
mirrorable 1:1 into a new `apps/core/services/contact_rate_limit.py` (Problem 18, Task 7).

**Spec anchor:** `.ai/problems/18_contact-us_spec.md` CR-10 (Task 7):
> **Web-side:** Per-IP rate limiting on deep-link page renders, using the existing `cache.add` +
> `cache.incr` pattern from `apps/search/services/rate_limit.py` — key `telegram_dl_rl:{ip}`,
> limit 60 renders per 10 minutes per IP.
> Applied to pages that render contact links (detail, privacy, listings, login_issue).

The bot-side half (Task 6) is already implemented — see §4.

---

## 1. Search autocomplete rate limiter — FULL FILE

**File:** `src/backend/apps/search/services/rate_limit.py` (77 lines, verbatim)

```python
"""
Rate limiting utility for search autocomplete.

Uses Django's cache framework with atomic increment to enforce
a per-IP request limit within a sliding time window.
"""

import logging
from typing import Final

from django.core.cache import cache
from django.http import HttpRequest

logger = logging.getLogger(__name__)

# Maximum number of autocomplete requests per IP within the time window.
RATE_LIMIT_REQUESTS: Final[int] = 30

# Time window in seconds.
RATE_LIMIT_PERIOD: Final[int] = 60

# Cache key pattern — {ip} is replaced with the client's IP address.
_RATE_LIMIT_KEY_PATTERN: Final[str] = "autocomplete_rl:{ip}"


def rate_limit_check(request: HttpRequest) -> bool:
    """
    Check whether the given request is within the rate limit.

    Uses an atomic increment pattern via ``cache.add`` followed by
    ``cache.incr`` to initialise the counter at 1 and atomically
    increment on each subsequent request.  Returns ``True`` if the
    request is allowed, ``False`` if the caller has exceeded the limit.

    Args:
        request: The incoming HTTP request.

    Returns:
        ``True`` if the request may proceed, ``False`` if rate-limited.
    """
    ip = _get_client_ip(request)
    key = _RATE_LIMIT_KEY_PATTERN.format(ip=ip)

    try:
        # cache.add returns True if the key was created (first request).
        added = cache.add(key, 1, timeout=RATE_LIMIT_PERIOD)
        if added:
            current = 1
        else:
            # Atomic increment on existing key.
            current = cache.incr(key)

        return current <= RATE_LIMIT_REQUESTS

    except ValueError:
        # Key expired between the add/incr calls — treat as a fresh start.
        cache.set(key, 1, timeout=RATE_LIMIT_PERIOD)
        return True


def _get_client_ip(request: HttpRequest) -> str:
    """
    Extract the client IP address from the request.

    Checks ``HTTP_X_FORWARDED_FOR`` first (for reverse-proxy setups),
    then falls back to ``REMOTE_ADDR``.

    Args:
        request: The incoming HTTP request.

    Returns:
        The client IP address string, or ``"unknown"`` if not available.
    """
    x_forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded:
        return x_forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "unknown")
```

### Cache idiom — `file:line`

```
src/backend/apps/search/services/rate_limit.py:41    ip = _get_client_ip(request)
src/backend/apps/search/services/rate_limit.py:42    key = _RATE_LIMIT_KEY_PATTERN.format(ip=ip)
src/backend/apps/search/services/rate_limit.py:46    added = cache.add(key, 1, timeout=RATE_LIMIT_PERIOD)
src/backend/apps/search/services/rate_limit.py:47    if added:
src/backend/apps/search/services/rate_limit.py:48        current = 1
src/backend/apps/search/services/rate_limit.py:49    else:
src/backend/apps/search/services/rate_limit.py:51        current = cache.incr(key)
src/backend/apps/search/services/rate_limit.py:53    return current <= RATE_LIMIT_REQUESTS
```

- **Cache key pattern:** `autocomplete_rl:{ip}` — `rate_limit.py:23` `_RATE_LIMIT_KEY_PATTERN: Final[str] = "autocomplete_rl:{ip}"`
- **Limit:** `RATE_LIMIT_REQUESTS = 30` — `rate_limit.py:17`
- **Period:** `RATE_LIMIT_PERIOD = 60` (seconds) — `rate_limit.py:20`
- **`cache.add` + `cache.incr` idiom (lines 26–32 of the function — the exact range the spec cites):**
  `rate_limit.py:46` → `cache.add(key, 1, timeout=...)` returns `True` on first hit (creates counter at 1);
  on subsequent hits `cache.incr(key)` atomically bumps it; compare `current <= RATE_LIMIT_REQUESTS`.
- **Return semantics:** `True` = allowed, `False` = rate-limited — `rate_limit.py:39` docstring: "``True`` if the request may proceed, ``False`` if rate-limited."
- **`request.META["REMOTE_ADDR"]` usage:** NOT used directly. IP is resolved via `_get_client_ip(request)` →
  `rate_limit.py:74-77`:
  ```python
  74:     x_forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
  75:     if x_forwarded:
  76:         return x_forwarded.split(",")[0].strip()
  77:     return request.META.get("REMOTE_ADDR", "unknown")
  ```

---

## 2. Login token-issuance rate limiter — FULL FILE

**File:** `src/backend/apps/users/services/login_rate_limit.py` (79 lines, verbatim)

Function name, signature, and constants — verbatim:

```python
# login_rate_limit.py:18-25
RATE_LIMIT_REQUESTS: Final[int] = 10            # login_rate_limit.py:19
RATE_LIMIT_PERIOD: Final[int] = 60              # login_rate_limit.py:21
_RATE_LIMIT_KEY_PATTERN: Final[str] = "login_rl:{ip}"  # login_rate_limit.py:25

# login_rate_limit.py:28
def login_rate_limit_check(request: HttpRequest) -> bool:
```

The body is byte-for-byte identical to `rate_limit_check` except the key pattern (`login_rl:` vs
`autocomplete_rl:`), and the docstring line
`login_rate_limit.py:7` — "Mirrors the pattern in ``apps/search/services/rate_limit.py`` but with
tighter limits for the security-sensitive login endpoint." — confirms the established idiom is
deliberately duplicated.

### Call site / 429 response — `users/views/consent.py`

```
src/backend/apps/users/views/consent.py:46    from apps.users.services.login_rate_limit import login_rate_limit_check
src/backend/apps/users/views/consent.py:294    if not login_rate_limit_check(request):
src/backend/apps/users/views/consent.py:295        logger.warning("Rate limit exceeded for login_issue")
src/backend/apps/users/views/consent.py:296        return HttpResponse(status=429)
```

Verbatim (`consent.py:294-296`):
```python
294:     if not login_rate_limit_check(request):
295:         logger.warning("Rate limit exceeded for login_issue")
296:         return HttpResponse(status=429)
```

Note the login 429 has **no body** (bare `HttpResponse(status=429)`), whereas the autocomplete 429
returns JSON — see §3.

---

## 3. How `rate_limit_check` is wired into the search view — the 429 contract

**File:** `src/backend/apps/search/views/autocomplete.py`

```
src/backend/apps/search/views/autocomplete.py:17    from apps.search.services.rate_limit import rate_limit_check
src/backend/apps/search/views/autocomplete.py:57    if not rate_limit_check(request):
src/backend/apps/search/views/autocomplete.py:58        return JsonResponse({"error": "rate_limit"}, status=429)
```

Verbatim (`autocomplete.py:57-58`):
```python
57:     if not rate_limit_check(request):
58:         return JsonResponse({"error": "rate_limit"}, status=429)
```

Docstring contract (`autocomplete.py:44-45`):
```
44:     If the client exceeds the rate limit, an HTTP 429 response with
45:     ``{"error": "rate_limit"}`` is returned.
```

**Return-type contract summary:** `rate_limit_check` returns `bool`; the view negates it (`if not …`)
and produces the 429. The new contact limiter should follow the **same two conventions**:
- service signature `(request: HttpRequest) -> bool`, returning `True` when allowed.
- view-side 429. For the contact deep-link (a page render, not a JSON API), pick one of the two
  established 429 shapes — see §6.

---

## 4. Bot process — confirms web-only scope

**Bot is a separate process with its own source root.**

```
src/telegram_bot/                    # top-level package root (NOT under src/backend)
  ├── main.py                        # entrypoint
  ├── handlers/
  ├── middlewares/
  ├── services/rate_limit.py         # BOT-SIDE limiter (own package)
  └── tests/test_rate_limit_service.py
src/backend/                         # web process root
  └── apps/core/services/            # NEW contact_rate_limit.py lands here (web-only)
```

Bot entrypoint sets up Django before importing its own handlers — `src/telegram_bot/main.py:8-11`
(verbatim):
```python
 8: # Configure Django settings and initialize the app registry BEFORE importing any
 9: # module that pulls Django models (e.g. telegram_bot.middlewares).
10: os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.prod")
11: django.setup()
```
- Bot imports are from the `telegram_bot.*` package (`main.py:15`
  `from telegram_bot.middlewares import AccountStateMiddleware`), i.e. the bot root.
- The bot **does not** import or need `apps.search.services.rate_limit` / `apps.users.services.login_rate_limit`.
- Crucially, the bot already has its **own** bot-side contact rate limiter — Task 6 is DONE:
  `src/telegram_bot/services/rate_limit.py:74` `check_contact_start_rate_limit(user_id, limit=5, period=600)`
  with key `bot_contact_rl:{user_id}` (`telegram_bot/services/rate_limit.py:71`).
  The grep `check_contact_start_rate_limit` across `src/backend` returns **0 matches** — it is
  bot-process-local, confirming the two sides are intentionally separate.

**Conclusion for the new limiter:** A new `apps/core/services/contact_rate_limit.py` lives under
`src/backend/apps/core/services/` and is reachable from the **web process only** (gunicorn renders
the contact templates). The bot process is not a consumer. This matches the spec
(Problem 18 §1.4 / §3.3: web-side `telegram_dl_rl:{ip}` per IP vs. bot-side
`bot_contact_rl:{user_id}` per Telegram user).

`apps/core/services/` directory confirmed present with siblings:
```
apps/core/services/__init__.py
apps/core/services/contact.py     (existing contact bridge — R2 render conditions)
apps/core/services/site_config.py
apps/core/services/translation.py
```

---

## 5. Existing test idiom for web rate limits (mirror verbatim)

Two established patterns. Both live under `src/backend/` and use the in-repo test DB.

### 5a. Service-level unit test (direct, no HTTP client)

**File:** `src/backend/apps/search/tests/test_autocomplete.py`

- **Markers** (module-level, `test_autocomplete.py:35`):
  ```python
  35: pytestmark = [pytest.mark.django_db, pytest.mark.slow, pytest.mark.integration]
  ```
- **Cache clearing** — the `TestAutocompleteEndpoint` class uses an autouse fixture
  (`test_autocomplete.py:92-100`):
  ```python
  92:     @pytest.fixture(autouse=True)
  93:     def _reset_rate_limit(self) -> None:
  94:         """Clear the rate-limit cache before each test to prevent state bleed."""
  99:         cache.clear()
  ```
  and `test_autocomplete_rate_limit` (`test_autocomplete.py:160-177`) also calls `cache.clear()`
  explicitly at `test_autocomplete.py:165`.
- **`TestRateLimitService` class** (`test_autocomplete.py:625-644`) — the canonical mirror idiom:
  ```python
  625: class TestRateLimitService:
  626:     """Tests for the rate limit service."""
  627:
  628:     def test_rate_limit_blocks_after_threshold(self) -> None:
  629:         """Rate limit check returns False after exceeding threshold."""
  630:         from apps.search.services.rate_limit import rate_limit_check
  631:
  632:         cache.clear()
  633:         # Make a mock request
  634:         from django.http import HttpRequest
  635:
  636:         request = HttpRequest()
  637:         request.META["REMOTE_ADDR"] = "127.0.0.1"
  638:
  639:         # First 30 requests should be allowed
  640:         for i in range(30):
  641:             assert rate_limit_check(request), f"Request {i} should be allowed"
  642:
  643:         # 31st request should be blocked
  644:         assert not rate_limit_check(request), "Request 31 should be rate limited"
  ```
- **Import at top** (`test_autocomplete.py:13`): `from django.core.cache import cache`.
- **Endpoint-level 429 assertion** (`test_autocomplete_rate_limit`, `test_autocomplete.py:160-177`):
  uses `Client()` (`test_autocomplete.py:167`), loops 31 `client.get("/api/search/autocomplete", {"q": "тест"})`,
  asserts status 200 for 0–29 and 429 for the 31st, plus `assert response.json()["error"] == "rate_limit"`
  at `test_autocomplete.py:177`.

### 5b. HTTP-endpoint 429 test (login)

**File:** `src/backend/apps/users/tests/test_login.py`

- **Markers** (`test_login.py:19`):
  ```python
  19: pytestmark = [pytest.mark.django_db, pytest.mark.slow, pytest.mark.integration]
  ```
- **Module-level autouse cache fixture** (`test_login.py:22-29`) — the canonical cache-clear idiom:
  ```python
  22: @pytest.fixture(autouse=True)
  23: def _clear_cache():
  24:     """Clear Django cache between tests to prevent rate-limiter state bleed."""
  25:     from django.core.cache import cache
  26:
  27:     cache.clear()
  28:     yield
  29:     cache.clear()
  ```
- **Endpoint-level 429 assertion** (`test_login.py:75-83`):
  ```python
  75:     def test_login_issue_returns_429_on_rate_limit(self) -> None:
  76:         """Exceeding 10 requests/minute from the same IP returns 429."""
  77:         client = Client()
  78:         for _ in range(10):
  79:             response = client.get("/login/issue/")
  80:             assert response.status_code == 200
  81:
  82:         response = client.get("/login/issue/")
  83:         assert response.status_code == 429
  ```
  Note: the login test asserts only `status_code == 429` (no body check) — because `login_issue`
  returns a bare `HttpResponse(status=429)` (§2), unlike autocomplete which returns JSON.

### 5c. Parallel unit-test cache discipline (context only — not a rate-limit test)

Phase 11 Block-1 findings note the same cache-clear discipline in a sibling unit test
(`.ai/audit/11-bot-username-migration/findings.md:652`):
> `test_site_config.py` (unit/integration, `pytest.mark.django_db`) clears LocMemCache in an
> `autouse` fixture (L28-33) — new bot_username cache tests must use the same cache-clear discipline.

### Mirror checklist for the new limiter's test

To match the established idiom, the new `contact_rate_limit` test should:
1. Declare `pytestmark = [pytest.mark.django_db, pytest.mark.slow, pytest.mark.integration]`
   (matches both web rate-limit test modules — `test_autocomplete.py:35`, `test_login.py:19`).
   - Exception: a pure service-level unit test (no DB rows) can drop `django_db` if it only
     touches the cache; the `TestRateLimitService` class in `test_autocomplete.py` is on the
     `django_db` module but does not itself use the DB — it still passes because the cache backend
     (LocMemCache) is available without a DB table. Mirror whichever tier the new test targets.
2. Manage cache state with an autouse fixture:
   ```python
   @pytest.fixture(autouse=True)
   def _clear_cache():
       from django.core.cache import cache
       cache.clear()
       yield
       cache.clear()
   ```
3. Build the request with `request.META["REMOTE_ADDR"] = "127.0.0.1"` (matches `test_autocomplete.py:637`)
   and/or `request.META["HTTP_X_FORWARDED_FOR"] = "203.0.113.5"` to exercise the proxy branch
   (§6 confirms both branches exist).
4. Assert per-request `True`/`False` (`assert contact_rate_limit_check(request)` /
   `assert not contact_rate_limit_check(request)`) — the `TestRateLimitService` idiom
   (`test_autocomplete.py:641`/`644`).
5. For endpoint-level 429 tests, assert `response.status_code == 429` and (for JSON responses)
   `response.json()["error"] == "rate_limit"`; for HTML 429, assert only `status_code` (the login
   precedent, `test_login.py:83`).

---

## 6. IP extraction convention (verbatim) — the new limiter MUST mirror this

Both web rate-limiters use an identical `_get_client_ip` helper. Verbatim:

```python
# rate_limit.py:61-77 (search)  ==  login_rate_limit.py:63-79 (users)  — byte-identical
def _get_client_ip(request: HttpRequest) -> str:
    x_forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded:
        return x_forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "unknown")
```

```
rate_limit.py:74     x_forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
rate_limit.py:75     if x_forwarded:
rate_limit.py:76         return x_forwarded.split(",")[0].strip()
rate_limit.py:77     return request.META.get("REMOTE_ADDR", "unknown")
```

**Answer to "REMOTE_ADDR directly or HTTP_X_FORWARDED_FOR":** The project checks
`HTTP_X_FORWARDED_FOR` FIRST (`request.META.get("HTTP_X_FORWARDED_FOR")`), splits on comma, takes
`[0].strip()` (the leftmost un-trustworthy hop under nginx `proxy_set_header`), and only falls back
to `REMOTE_ADDR` when `X-Forwarded-For` is absent. The new limiter must match this convention
exactly (it is the established, nginx-aware IP-extraction contract). The spec research doc
explicitly relies on this:
`.ai/research/04_telegram-contact-antispam-research.md:301` —
> "The `X-Forwarded-For` IP extraction in `_get_client_ip()` (`search/services/rate_limit.py:61-77`)
> already handles the nginx reverse-proxy setup."

### Two-layer IP note (nginx vs. app)
- nginx `location /search/` and `/login/` carry `limit_req` (nginx-level) — see EXT-003
  (`.ai/audit/09-external-api/findings.md:62`). The ad-detail `location /` is **not** rate-limited
  at nginx, so the application-level per-IP limiter (this Block) is the relevant guard for the
  contact deep-link render path. The two layers are complementary.

---

## 7. Summary table — established idiom (verbatim constants)

| Limiter | File:Line (key pattern) | File:Line (limit / period) | 429 shape at call site |
|---|---|---|---|
| Autocomplete (search) | `autocomplete_rl:{ip}` — `rate_limit.py:23` | `30` / `60s` — `rate_limit.py:17,20` | `autocomplete.py:57-58` → `JsonResponse({"error":"rate_limit"}, status=429)` |
| Login token issuance | `login_rl:{ip}` — `login_rate_limit.py:25` | `10` / `60s` — `login_rate_limit.py:19,22` | `consent.py:294-296` → `HttpResponse(status=429)` (bare) |
| Upload (bot, per-user) | `bot_upload_rl:{user_id}` — `telegram_bot/services/rate_limit.py:23` | `10` / `60s` — `...rate_limit.py:17,20` | bot-internal (no HTTP 429) |
| Contact start (bot, per-user — DONE, Task 6) | `bot_contact_rl:{user_id}` — `telegram_bot/services/rate_limit.py:71` | `5` / `600s` — `...rate_limit.py:65,68` | bot-internal (cooldown message) |
| **Contact deep-link render (web, NEW — Task 7)** | `telegram_dl_rl:{ip}` (spec: Problem 18 CR-10) | `60` / `600s` (spec: Problem 18 CR-10) | **to be implemented** — mirror autocomplete (JSON, `detail`/`privacy`/`listings`) or login (bare HTTP, `login_issue`) depending on whether the page is HTMX/fragment or a full HTML render |

---

## 8. Advisory: the idiom is duplicated (DRY) — flag, not change

Each web rate-limit module defines its own private `_get_client_ip` (byte-identical, ~7 lines)
and its own copy of the `cache.add`/`cache.incr` try/except block. This was confirmed by grep:
`_get_client_ip` is defined in `rate_limit.py` (`rate_limit.py:61`) and `login_rate_limit.py`
(`login_rate_limit.py:63`) only — no shared `apps.core.utils.ip` / `apps.core.services.ip` helper
exists.

- **Verbatim:** `grep -rn "_get_client_ip" src/backend` → exactly 2 definitions (one per module),
  0 shared helpers. Same for the `cache.add`/`cache.incr` block (lines 44-58 of each file are
  structurally identical).
- **Recommendation (advisory, NOT in scope of this evidence-only block):** When creating
  `apps/core/services/contact_rate_limit.py`, the new module will be the **third** copy of the
  identical `_get_client_ip` + `cache.add/incr` body. The cleaner long-term fix is to extract a
  single `apps/core/utils/ip.py` (`def get_client_ip(request) -> str`) and/or a
  `apps/core/services/_cache_rate_limit.py` generic helper (`def _increment(key, limit, period)`).
  This is flagged here so the implementor can decide: (a) mirror the duplication exactly (lowest
  risk, matches existing convention 1:1), or (b) extract a shared helper and refactor the two
  existing modules to use it. Per the audit mandate this is classified **advisory** — no mandatory
  change. Effort to extract: small. Priority: recommended (maintainability; avoids a 4th copy).

---

## 9. Verbatim call-site map (grep confirmation)

`grep -rn "rate_limit_check" src/backend/apps/search` → exactly:
```
src/backend/apps/search/services/rate_limit.py:26   def rate_limit_check(request: HttpRequest) -> bool:
src/backend/apps/search/views/autocomplete.py:17   from apps.search.services.rate_limit import rate_limit_check
src/backend/apps/search/views/autocomplete.py:57       if not rate_limit_check(request):
src/backend/apps/search/tests/test_autocomplete.py:630   from apps.search.services.rate_limit import rate_limit_check
src/backend/apps/search/tests/test_autocomplete.py:641   assert rate_limit_check(request), ...
src/backend/apps/search/tests/test_autocomplete.py:644   assert not rate_limit_check(request), ...
```

`grep -rn "login_rate_limit_check" src/backend/apps/users` → exactly:
```
src/backend/apps/users/services/login_rate_limit.py:28   def login_rate_limit_check(request: HttpRequest) -> bool:
src/backend/apps/users/views/consent.py:46   from apps.users.services.login_rate_limit import login_rate_limit_check
src/backend/apps/users/views/consent.py:294   if not login_rate_limit_check(request):
```

Bot-side (web-process-irrelevant, confirmed separate):
`grep -rn "check_contact_start_rate_limit" src/backend` → 0 matches (bot-only); defined at
`src/telegram_bot/services/rate_limit.py:74`, tested at
`src/telegram_bot/tests/test_rate_limit_service.py:27` (`TestContactStartRateLimit`,
`pytestmark = [pytest.mark.django_db, pytest.mark.integration]`, `test_rate_limit_service.py:17`),
`cache.clear()` in autouse fixture `test_rate_limit_service.py:20-24`, assertions
`assert check_contact_start_rate_limit(123) is True` / `... is False` (`test_rate_limit_service.py:33,39`).

---

## 10. Files read in full for this block (audit trail)

| File | Purpose |
|---|---|
| `src/backend/apps/search/services/rate_limit.py` | Autocomplete rate limiter — idiom source (§1) |
| `src/backend/apps/search/views/autocomplete.py` | Call site + 429 contract (§3) |
| `src/backend/apps/users/services/login_rate_limit.py` | Login rate limiter — idiom twin (§2) |
| `src/backend/apps/users/views/consent.py` | Login 429 call site (§2) |
| `src/backend/apps/search/tests/test_autocomplete.py` | Service + endpoint rate-limit test idiom (§5a) |
| `src/backend/apps/users/tests/test_login.py` | Login 429 test idiom (§5b) |
| `src/telegram_bot/main.py` | Proof bot is a separate process via `django.setup()` (§4) |
| `src/telegram_bot/services/rate_limit.py` | Bot-side limiter (Task 6 already exists) (§4) |
| `src/telegram_bot/tests/test_rate_limit_service.py` | Bot-side test idiom (§9) |
| `src/backend/apps/core/services/contact.py` | Confirms `apps/core/services/` is the correct home dir |
| `.ai/problems/18_contact-us_spec.md` | Spec CR-10 / Task 7 — target constants (`telegram_dl_rl:{ip}`, 60/600s) |
| `.ai/research/04_telegram-contact-antispam-research.md` | §1.4 / §5.5 confirm mirror target + IP-extraction convention |
| `.ai/audit/11-bot-username-migration/findings.md` | Block-1 home + `test_site_config.py` cache-clear parallel (§5c) |
