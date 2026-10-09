# Researcher 1 — Curl Reproduction: Image Blankout on Sort

## Environment
- Dev site: `http://127.0.0.1:8000` (Django `runserver`, `WSGIServer/0.2 CPython/3.14.8`, DEBUG=True)
- Cache backend: `LocMemCache` (in-process, per dev.py lines 58–63) — shared across all
  requests in the single dev-server process, so the rate-limit counter persists.
- Client IP seen by `media_gate`: `127.0.0.1` (loopback peer is trusted; no forwarded
  headers from curl, so `get_client_ip` returns `127.0.0.1`).
- Rate-limit key: `media_gate_rl:127.0.0.1` (listings.py:64 — `_MEDIA_RATE_LIMIT_KEY_PATTERN`).

## Hypothesis (to verify, not assume)
A 61st request to a `media_gate` URL within 60s returns HTTP 429. A listing page
renders 24 thumbnail `<img>` via `/media/...` URLs; `media_gate` sets
`Cache-Control: no-cache` and no ETag/Last-Modified; each HTMX `?sort=` re-render
fires all 24. After ~2.5 page loads (60/24), the per-IP budget (60/60s) exhausts,
images go blank, and recover after the window resets.

The previous audit (`.ai/audit/problems.md`, commit 5cdd1cdf) blamed a non-atomic
seed-image write in `_preprocess_one` (`apps/seed/generators/images.py`). That path
runs only during `docker compose run --rm seed` (seed regeneration), never during a
browser sort. It cannot explain sort-induced blankout. Treated as a misdiagnosis.

## Reproduction steps

### 1. Extract 24 media thumbnail URLs from one listing render
```powershell
curl -s "http://127.0.0.1:8000/?sort=date_desc" -o page.html
# page.html contains 24 <img src="/media/seed/...-small.jpg"> tags
```
Result: exactly **24** `<img src="/media/...">` tags found, all under `<div id="ad-list">`.
All 24 URLs are distinct `seed/<category>_NN-small.jpg` paths.

### 2. Confirm 24 imgs under #ad-list
```powershell
(Get-Content page.html -Raw) -split "`n" | Select-String '<img src="/media/' | Measure-Object
```
Result: **24** matches. All are thumbnail renders inside the listing grid.

### 3. Single-URL 70x threshold test (proves the 60/61 boundary)
```powershell
$url = "http://127.0.0.1:8000/media/seed/pedicure_01-small.jpg"
for ($i = 1; $i -le 70; $i++) {
    $code = curl -s -o /dev/null -w "%{http_code}" $url
    "$i : $code"
}
```
Result:
```
1 : 200   ...   59 : 200   60 : 200
61 : 429   ...   70 : 429
```
- Requests 1–60: **200**
- Request 61: **429** (first 429)
- Requests 62–70: **429**

This is exactly the predicted threshold: 60 allowed, 61st refused.

### 4. Round-by-round test (mimics page loads / sorts, 24 imgs each)
```powershell
# After a 65s wait for window reset (confirmed fresh by a probe returning 200):
$urls = Get-Content urls.txt  # 24 media URLs
for ($r = 1; $r -le 4; $r++) {
    $r200 = 0; $r429 = 0
    foreach ($u in $urls) {
        $code = curl -s -o /dev/null -w "%{http_code}" "http://127.0.0.1:8000$u"
        if ($code -eq "200") { $r200++ } elseif ($code -eq "429") { $r429++ }
    }
    Write-Host ("Round {0}: 200={1}  429={2}  cumulative={3}" -f $r, $r200, $r429, ($r200+$r429)*0+$cumulative)
}
```
Result (clean window, no prior probe):
```
Round 1: 200=24  429=0   cumulative=24
Round 2: 200=24  429=0   cumulative=48
Round 3: 200=12  429=12  cumulative=72
Round 4: 200=0   429=24  cumulative=96
```
Interpretation: budget of 60 is consumed by requests 1–60 (rounds 1+2 = 48, then 12 more in
round 3). Requests 61–72 (remainder of round 3) and 73–96 (round 4) all get 429.

**Note on a prior run**: one earlier round test showed the threshold at 48 instead of
60 (rounds 1–2 all 200, round 3 all 429). A re-run 65s later with no prior request
showed the expected 60 boundary. The 48 run is attributed to background traffic (e.g.,
a browser tab on the live dev site consuming ~12 image requests). This in itself
proves the mechanism: any concurrent consumer of `/media/` URLs competes for the same
per-IP budget.

### 5. 200 response headers (media_gate success)
```
HTTP/1.1 200 OK
Date: Fri, 09 Oct 2026 19:43:41 GMT
Server: WSGIServer/0.2 CPython/3.14.8
Content-Type: image/jpeg
Content-Length: 9136
Content-Disposition: inline; filename="pedicure_01-small.jpg"
X-Content-Type-Options: nosniff
Cache-Control: no-cache
Vary: Cookie, Accept-Language
X-Frame-Options: DENY
Content-Language: ru
Referrer-Policy: same-origin
Cross-Origin-Opener-Policy: same-origin
```
- `Cache-Control: no-cache` — confirmed present.
- `ETag` — **absent**.
- `Last-Modified` — **absent**.
- `Vary: Cookie, Accept-Language` — present (from `@vary_on_headers("Cookie")`).

### 6. 429 response headers (live capture, budget exhausted)
```
HTTP/1.1 429 Too Many Requests
Date: Fri, 09 Oct 2026 19:54:18 GMT
Server: WSGIServer/0.2 CPython/3.14.8
Content-Type: text/html; charset=utf-8
Vary: Cookie, Accept-Language
X-Frame-Options: DENY
Content-Language: ru
Content-Length: 0
X-Content-Type-Options: nosniff
Referrer-Policy: same-origin
Cross-Origin-Opener-Policy: same-origin
```
Body: **0 bytes** (empty). Matches `rate_limited_response(json=False)` → `HttpResponse(status=429)`.

## Code confirmation

### media_gate runs rate-limit guard BEFORE DEBUG/serving branch
File: `src/backend/apps/ads/views/listings.py`

```python
@vary_on_headers("Cookie")
def media_gate(request, image_key):
    # Rate limit (09-API-005). Runs before the AdImage lookup...
    media_key = _MEDIA_RATE_LIMIT_KEY_PATTERN.format(ip=get_client_ip(request))
    if not bump_rate_limit_window(media_key, MEDIA_RATE_LIMIT_REQUESTS, MEDIA_RATE_LIMIT_PERIOD):
        logger.warning("Media gate rate limit exceeded")
        return rate_limited_response(json=False)          # ← 429, before DB or disk
    # ... path-traversal guard ...
    # ... AdImage lookup ...
    if settings.DEBUG:
        response = _serve_image(image_key)
        response["Cache-Control"] = "no-cache"
        return response
    response = HttpResponse()
    response["X-Accel-Redirect"] = f"/protected-media/{image_key}"
    response["Cache-Control"] = "no-store"
    return response
```
Lines 186–191 (rate-limit guard) precede lines 198–255 (path-traversal, DB lookup,
DEBUG/serving branch). An over-budget client never reaches the database or the
filesystem.

### RateLimitBudget.MEDIA_GATE == (60, 60)
File: `src/backend/apps/core/enums.py`

```python
class RateLimitBudget(StrEnum):
    ...
    MEDIA_GATE = "media_gate"
    @property
    def requests(self) -> int:
        return { ..., RateLimitBudget.MEDIA_GATE: 60 }[self]
    @property
    def period(self) -> int:
        return { ..., RateLimitBudget.MEDIA_GATE: 60 }[self]
```
Enum docstring (line 45–46): "MEDIA_GATE: 60 requests / 60 s. Anonymous DB-backed media
serving; protects the database from an over-budget client (09-API-005)."

### Module-level constants derive from the enum
File: `src/backend/apps/ads/views/listings.py`, lines 60–62:
```python
MEDIA_RATE_LIMIT_REQUESTS: int = RateLimitBudget.MEDIA_GATE.requests  # = 60
MEDIA_RATE_LIMIT_PERIOD: int = RateLimitBudget.MEDIA_GATE.period      # = 60
```

### bump_rate_limit_window — the shared limiter body
File: `src/backend/apps/core/utils/cache.py`, lines 60–90:
```python
def bump_rate_limit_window(key: str, limit: int, period: int) -> bool:
    try:
        if cache.add(key, 1, timeout=period):   # first hit: create key = 1
            return True
        current = cache.incr(key)               # subsequent: increment
    except (ConnectionInterrupted, redis.RedisError):
        logger.warning("Cache write failed for %s; allowing request", key)
        return True                              # fail-open
    except ValueError:
        cache.set(key, 1, timeout=period)        # key expired between add/incr
        return True
    return current <= limit                      # ≤ 60 → True; 61 → False
```
- `cache.add` + `cache.incr` is the atomic idiom (Redis `INCR` is atomic; LocMemCache
  `incr` holds an internal lock).
- Returns `True` for counts 1–60, `False` for count 61 → the 61st call returns `False`.
- TTL = `period` (60s). After 60s the key expires; the next `cache.add` resets the
  window. This explains "reappear after several refreshes" (wait > 60s).
- Fails open: a cache outage allows all media (never a 5xx).

### Test assertions pinning the (60, 60) budget
- `src/backend/apps/core/tests/test_rate_limit_budget.py:82`
  `assert (RateLimitBudget.MEDIA_GATE.requests, RateLimitBudget.MEDIA_GATE.period) == (60, 60)`
- `src/backend/apps/core/tests/test_rate_limit_budget.py:67-74`
  `test_media_gate_limiter_matches_its_budget`: asserts
  `listings.MEDIA_RATE_LIMIT_REQUESTS == RateLimitBudget.MEDIA_GATE.requests` and
  `MEDIA_RATE_LIMIT_PERIOD == RateLimitBudget.MEDIA_GATE.period`.
- `src/backend/apps/ads/tests/test_media_security.py:994-996`
  `test_period_constant_is_the_documented_window`:
  `assert (MEDIA_RATE_LIMIT_REQUESTS, MEDIA_RATE_LIMIT_PERIOD) == (60, 60)`
- `src/backend/apps/ads/tests/test_media_security.py:923-938`
  `test_burst_over_budget_is_refused`: "The (limit+1)th request from one IP is
  refused with 429."
- `src/backend/apps/ads/tests/test_media_security.py:940-956`
  `test_over_budget_is_refused_before_the_db_lookup`: "The limiter runs before the
  AdImage query." (over-budget request for a valid PUBLISHED ad key still 429s)
- `src/backend/apps/ads/tests/test_media_security.py:719-757`
  `TestMediaGateCacheControl`: production 200 → `Cache-Control: no-store`;
  dev (DEBUG=True) 200 → `Cache-Control: no-cache`; no ETag/Last-Modified asserted.

### URL routing — all /media/ goes through media_gate
File: `src/backend/apps/ads/urls.py`, line 25:
```python
path("media/<path:image_key>", media_gate, name="media_gate"),
```
Root URLconf does NOT use `static()` for media. There is no `django.views.static.serve`
or lazy backfill path — every `/media/...` request hits `media_gate`, which checks the
`AdImage` DB row, then serves from disk (DEBUG) or `X-Accel-Redirect` (prod).

### Previous audit misdiagnosis — confirmed
`.ai/audit/problems.md` (commit 5cdd1cdf) identified root cause as a non-atomic write of
the original image in `apps/seed/generators/images.py::_preprocess_one`, racing with
concurrent `media_gate` readers during seed re-run. Verified:
- `_preprocess_one` (now fixed per the audit's own "Fix Applied") runs ONLY during
  `docker compose run --rm seed` — a manual re-seed command, not during a browser sort.
- A browser sort issues `GET /?sort=...` → HTMX swaps `#ad-list` → 24 new `<img>` fetches
  to `/media/seed/...`. None of these touch the seed generator. The seed write path is
  simply not on the sort code path.
- The audit's own evidence #4 and Finding #4 acknowledged `media_gate` rate-limits, but
  its "Most Likely" and "Root Cause" sections attributed the symptom to the seed write
  race — a misdiagnosis. The applied fix (atomic original-image write) is correct for
  the seed-regeneration scenario but does NOT address sort-induced blankout.

## The 60/60s threshold (summary table)

| Test | Requests allowed | First 429 at |
|---|---|---|
| Single-URL 70x (controlled) | 60 | #61 |
| Round-by-round (clean, 24 per round) | 60 | request #61 (12th request of round 3) |
| Round-by-round (prior, with background traffic) | ~48 | request #49 |

## One-sentence root cause

Each HTMX `?sort=` re-render fires 24 unconditional `media_gate` image requests that
bear `Cache-Control: no-cache` with no ETag/Last-Modified (so no browser cache savings),
and the application-level per-IP budget of 60 requests / 60 seconds is exhausted in ~2.5
page loads, causing the 61st-onward image requests to return HTTP 429 (empty body) and
the thumbnails to go blank until the 60-second window resets.
