# Problem P-003 — media_gate Rate Limit Causes Thumbnail Blankout on Sort

## Summary
When a user sorts the listing page (HTMX re-render), 24 `media_gate` image
requests fire unconditionally. Each `media_gate` response carries
`Cache-Control: no-cache` with no `ETag`/`Last-Modified`, so the browser
re-fetches on every render. The per-IP budget of **60 requests / 60 seconds**
(defined by `RateLimitBudget.MEDIA_GATE`) is exhausted after ~2.5 page loads,
after which every image request returns **HTTP 429** (empty body) and thumbnails
go blank until the window resets.

## Key Distinction from P-001 (Seed Write Race, commit 5cdd1cdf)
The previous audit (`.ai/audit/problems.md`) identified a **non-atomic seed-image
write** in `_preprocess_one` (`apps/seed/generators/images.py`). That defect only
manifests during `docker compose run --rm seed` (seed regeneration) and is **not
on the sort code path**. A browser sort issues:
1. `GET /?sort=...` → HTMX swaps `#ad-list`
2. 24 new `<img>` fetches to `/media/seed/...`
None of these touch the seed generator. The 429 reproduction proves a **separate,
independent** root cause: HTTP 429 responses with empty bodies are returned by
`media_gate`'s rate-limit guard, which executes **before** any disk or DB access.

## Environment
- Dev site: `http://127.0.0.1:8000` (Django `runserver`)
- Cache backend: `LocMemCache` (shared across all requests in the single dev-server process)
- Client IP: `127.0.0.1` (rate-limit key: `media_gate_rl:127.0.0.1`)
- Rate limit: `RateLimitBudget.MEDIA_GATE` = (60 requests, 60 seconds)

## Reproduction (verified)

### 1. Single-URL threshold test
Fetching `/media/seed/pedicure_01-small.jpg` 70 times:
```
Requests 1–60:  HTTP 200
Request 61:     HTTP 429   ← first refused
Requests 62–70: HTTP 429
```
This pinpoints the exact 60/61 boundary.

### 2. Round-by-round test (24 URLs per round, mimicking page sorts)
```
Round 1: 24 × 200, cumulative = 24
Round 2: 24 × 200, cumulative = 48
Round 3: 12 × 200, 12 × 429, cumulative = 72  ← budget exhausted at request #61
Round 4: 0 × 200, 24 × 429, cumulative = 96
```

### 3. Response headers

**HTTP 200 (success):**
```
Cache-Control: no-cache
Vary: Cookie, Accept-Language
ETag: — (absent)
Last-Modified: — (absent)
```

**HTTP 429 (rate-limited):**
```
Content-Type: text/html; charset=utf-8
Content-Length: 0
Body: (empty)
```
The 429 body is 0 bytes, matching `rate_limited_response(json=False)` →
`HttpResponse(status=429)`.

## Code Path

### `media_gate` (ads/views/listings.py)
```python
@vary_on_headers("Cookie")
def media_gate(request, image_key):
    # Rate limit guard runs BEFORE any DB lookup or disk access
    media_key = _MEDIA_RATE_LIMIT_KEY_PATTERN.format(ip=get_client_ip(request))
    if not bump_rate_limit_window(media_key, MEDIA_RATE_LIMIT_REQUESTS, MEDIA_RATE_LIMIT_PERIOD):
        logger.warning("Media gate rate limit exceeded")
        return rate_limited_response(json=False)  # ← 429, empty body
    # ... path-traversal guard, AdImage lookup, X-Accel-Redirect / DEBUG serve ...
```

### `RateLimitBudget.MEDIA_GATE` (apps/core/enums.py)
```python
MEDIA_GATE = "media_gate"  # doc: 60 requests / 60 s

@property
def requests(self) -> int:
    return {..., RateLimitBudget.MEDIA_GATE: 60}[self]

@property
def period(self) -> int:
    return {..., RateLimitBudget.MEDIA_GATE: 60}[self]
```

### Module-level constants (ads/views/listings.py)
```python
MEDIA_RATE_LIMIT_REQUESTS = RateLimitBudget.MEDIA_GATE.requests  # 60
MEDIA_RATE_LIMIT_PERIOD = RateLimitBudget.MEDIA_GATE.period      # 60
```

### `bump_rate_limit_window` (apps/core/utils/cache.py)
```python
def bump_rate_limit_window(key, limit, period) -> bool:
    if cache.add(key, 1, timeout=period):  # first hit
        return True
    current = cache.incr(key)              # subsequent hits
    # ...
    return current <= limit  # True for 1–60, False for 61
```
TTL = 60 seconds. After the window expires, `cache.add` resets the counter — this
is why images "reappear after a few refreshes" (wait > 60s).

## Why This Is a Problem
1. **60 requests/60s is too low for anonymous browsing.** A listing page with 24
   thumbnails consumes 24 budget per page view; 2.5 sorts exhaust it.
2. **No client-side caching.** `Cache-Control: no-cache` + no `ETag`/`Last-Modified`
   means the browser cannot avoid re-requesting thumbnails the user has already seen.
3. **429 returns empty body.** The browser shows a broken image icon / blank space
   with no fallback messaging.
4. **In production (gunicorn + nginx), the budget is shared per real client IP**
   (behind a proxy), so a single user can block themselves — and on shared IPs
   (NAT/proxy), one user can exhaust another's budget.

## Affected Files
- `src/backend/apps/core/enums.py` — `RateLimitBudget.MEDIA_GATE` definition
- `src/backend/apps/ads/views/listings.py` — `media_gate`, rate-limit constants
- `src/backend/apps/core/utils/cache.py` — `bump_rate_limit_window`
- `src/backend/apps/core/tests/test_rate_limit_budget.py` — pins (60, 60)
- `src/backend/apps/ads/tests/test_media_security.py` — rate-limit behavior tests

## Suggested Remediation Direction (for planning)
- [ ] Evaluate whether 60 req/60s is the intended budget for anonymous media serving.
- [ ] Add `ETag`/`Last-Modified` or `Cache-Control: max-age` so repeat views don't
      consume budget (thumbnails are immutable per seed version).
- [ ] Consider exempting seed images (immutable, disk-served) from the rate limit
      or applying a higher budget to them specifically.
- [ ] Return a minimal placeholder body on 429 so broken images degrade gracefully.

## Investigator Reports
- **Researcher 1** (curl reproduction): `.ai/audit/problems/tmp/researcher_1_curl.md`
  — controlled 70× single-URL test confirming the 60/61 boundary; 24-URL round-by-round
  test (rounds 1–4: 24/24/12+12/0 HTTP 200, rest 429); response headers for both 200 and 429.
- **Researcher 2** (code path analysis): `.ai/audit/problems/tmp/researcher_2_media_rate_limit.md`
  — template analysis (ad_list.html line 126–131, 24 imgs), HTMX sort form, URL routing,
  rate-limit config, cache backend (LocMemCache in dev), IP resolution (`get_client_ip`),
  and complete localization file/line table.

## Open for Root-Cause Auditor
- Confirm whether 60 req/60s is the **intended** budget for anonymous media serving (per
  `09-API-005` ticket referenced in commit `5ffad37e`), or whether it is too tight for a
  24-thumbnail listing that re-fetches on every HTMX sort.
- Evaluate remediation options (see "Suggested Remediation Direction" above).

## Status
- **Confirmed.** Rate-limit blankout is a distinct root cause from the seed-write
  race (P-001). Reproduction pinned to the 60/61 boundary via controlled curl; code path
  fully localized. Awaiting root-cause auditor review for remediation direction.
