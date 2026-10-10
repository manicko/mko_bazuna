"""
Evidence verification for Problem P-003 — media_gate rate-limit blankout on HTMX sort.

Verifies each piece of reproduction evidence from the original bug reports against
the remediated source (commits aa0a08ba, cb798afa, f949d554, 410896fc).
Read-only: only the current source and the four remediation diffs were consulted.
"""

# =====================================================================
# EVIDENCE VERIFICATION — P-003
# =====================================================================
# Source of original evidence:
#   .ai/audit/problems/P-003-media-rate-limit-blankout.md        (the bug report)
#   .ai/audit/problems/tmp/researcher_1_curl.md                  (curl reproduction)
#   .ai/audit/problems/tmp/researcher_2_media_rate_limit.md      (code-path analysis)
#   .ai/audit/99-validation/code_context.md                    (plan-vs-code check)
# Remediation commits (newest → oldest): 410896fc, f949d554, cb798afa, aa0a08ba
# Current sources read for final state: enums.py, listings.py, cache.py,
#   rate_limit_response.py (+ tests: test_rate_limit_budget.py, test_media_security.py,
#   and docs/99-agent/nginx-rate-limit-attribution-record.md).


## TL;DR verbatim

> The original 60-request exhaustion is no longer possible with a 240-request
> budget; the empty-body 429 is replaced by a 140-byte SVG placeholder with
> `Retry-After`; client-side caching (`Cache-Control: public, max-age=86400`)
> prevents re-fetch on sort; therefore the original blankout scenario is NOT
> reproducible. (The `$body_bytes_sent == 0` attribution rule that the
> *measurement* gate relied on IS broken by the non-empty body — see §6.)


## 0. Remediation summary (what changed, where)

The four commits are additive and independent — each targets one symptom:

| Commit | Concern | Files touched (source) |
|---|---|---|
| `aa0a08ba` | Generic 429 builder gains `Retry-After` + `Cache-Control: no-store` + optional `body` | `core/utils/rate_limit_response.py` |
| `cb798afa` | `media_gate` 429 returns an SVG placeholder + `Retry-After` + `image/svg+xml` | `ads/views/listings.py` |
| `f949d554` | `media_gate` 200 responses gain `Cache-Control: public, max-age=86400` | `ads/views/listings.py` |
| `410896fc` | `RateLimitBudget.MEDIA_GATE` requests raised 60 → 240 | `core/enums.py` |

None of the four commits touches the **order** of operations inside `media_gate`
(the guard still runs first), nor the `bump_rate_limit_window` algorithm in
`cache.py`. The guard order is therefore structurally untouched; only the
budget magnitude, the 200 `Cache-Control`, and the 429 response shape changed.


## 1. Evidence Set A — Single-URL threshold test (60/61 boundary)

### 1.1 Original evidence (from P-003 §3 and researcher_1_curl §3)

Fetching `/media/seed/pedicure_01-small.jpg` 70×:
```
Requests 1–60:  HTTP 200
Request 61:     HTTP 429   ← first refused
Requests 62–70: HTTP 429
```
Root cause of the boundary: `bump_rate_limit_window` returns `current <= limit`
with `limit = 60` (enums.py:63 at the time), so the count reaches 61 on the
61st call and the guard returns `False` → 429.

### 1.2 Current source (post-remediation)

`src/backend/apps/core/enums.py`:
```python
class RateLimitBudget(StrEnum):
    """..."""
    MEDIA_GATE = "media_gate"                          # line 53

    @property
    def requests(self) -> int:                         # lines 55-64
        return {
            ...
            RateLimitBudget.MEDIA_GATE: 240,          # line 63  (was 60)
        }[self]

    @property
    def period(self) -> int:                          # lines 66-75
        return {
            ...
            RateLimitBudget.MEDIA_GATE: 60,           # line 74  (unchanged)
        }[self]
```
Docstring (enums.py:45-46) now reads:
> `MEDIA_GATE: 240 requests / 60 s. Anonymous DB-backed media serving; protects`

`src/backend/apps/ads/views/listings.py`:
```python
MEDIA_RATE_LIMIT_REQUESTS: int = RateLimitBudget.MEDIA_GATE.requests  # line 60 → 240
MEDIA_RATE_LIMIT_PERIOD: int = RateLimitBudget.MEDIA_GATE.period      # line 62 → 60
```

`src/backend/apps/core/utils/cache.py` (unchanged by remediation):
```python
def bump_rate_limit_window(key: str, limit: int, period: int) -> bool:  # line 60
    try:
        if cache.add(key, 1, timeout=period):        # line 80: first hit
            return True                              # line 81
        current = cache.incr(key)                    # line 82: subsequent hits
    except (ConnectionInterrupted, redis.RedisError):
        logger.warning("Cache write failed for %s; allowing request", key)
        return True                                  # line 85: fail-open
    except ValueError:
        cache.set(key, 1, timeout=period)            # line 88
        return True                                  # line 89
    return current <= limit                          # line 90  ← limit is now 240
```

### 1.3 Test pinning the new value

`src/backend/apps/core/tests/test_rate_limit_budget.py:82`:
```python
assert (RateLimitBudget.MEDIA_GATE.requests, RateLimitBudget.MEDIA_GATE.period) == (240, 60)
```
`src/backend/apps/ads/tests/test_media_security.py:1046-1048`:
```python
def test_period_constant_is_the_documented_window(self) -> None:
    """The window pair is the reviewed budget, not an inline literal."""
    assert (MEDIA_RATE_LIMIT_REQUESTS, MEDIA_RATE_LIMIT_PERIOD) == (240, 60)
```

### 1.4 New expected behavior

With `limit = 240` and `period = 60`, `bump_rate_limit_window`:
- `cache.add` creates the key with value 1 on hit #1 → returns `True`.
- `cache.incr` returns 2..240 for hits #2..#240 → all `True` (200).
- Hit #241 → `cache.incr` returns 241, `241 <= 240` is `False` → 429.
- TTL is still 60 s (enums.py:74); after the window the key resets via `cache.add`.

**New reproduction (same curl):**
```
Requests 1–240:   HTTP 200
Request 241:      HTTP 429   ← first refused
Requests 242–250: HTTP 429
```

### 1.5 Verdict: FIXED

The 60/61 boundary is gone. The boundary moved to **240 allowed, 241st refused**
— a 4× raise that covers ten 24-image page loads (10×24 = 240) before the first
429, matching the intent documented in the new test
`test_media_gate_budget_allows_ten_page_loads` (test_media_security.py:971-986).
The boundary mechanism (the `<= limit` comparison, the 60 s window reset) is
identical; only the limit operand changed from 60 to 240.


## 2. Evidence Set B — Round-by-round test (24 URLs/round) + client-side caching

### 2.1 Original evidence (researcher_1_curl §4; P-003 §3.2)

With `Cache-Control: no-cache` on every 200 and no `ETag`/`Last-Modified`, the
browser re-fetched all 24 thumbnails on every HTMX sort (a network request per
`<img>`), so the per-IP budget was consumed per round:
```
Round 1: 24 × 200, cumulative = 24
Round 2: 24 × 200, cumulative = 48
Round 3: 12 × 200, 12 × 429, cumulative = 72   ← budget exhausted at request #61
Round 4: 0 × 200, 24 × 429,  cumulative = 96
```

### 2.2 Current source — the Cache-Control change

`src/backend/apps/ads/views/listings.py`:
```python
# 200 responses on media_gate carry a 24h CDN/browser TTL. ``public`` lets nginx
# and shared caches store the response ... ``immutable`` is deliberately omitted:
# image keys are UUID v4 (uploads) or fixed ``seed/<filename>.jpg`` names, NOT
# content-addressed. Seed files are regenerated with WriteMode.REPLACE at the same
# URL, so a stale cached body would be served if ``immutable`` were present.
_MEDIA_CACHE_CONTROL_200: Final[str] = "public, max-age=86400"   # line 84
```
Applied to every 200 serving branch (listings.py):
```python
# Staff + DEBUG (line 252)            response["Cache-Control"] = _MEDIA_CACHE_CONTROL_200
# Staff + prod  (line 256)            response["Cache-Control"] = _MEDIA_CACHE_CONTROL_200
# Non-staff + DEBUG (line 275)         response["Cache-Control"] = _MEDIA_CACHE_200
# Non-staff + prod  (line 280)         response["Cache-Control"] = _MEDIA_CACHE_CONTROL_200
```

### 2.3 Why client-side caching defeats the reproduction

`max-age=86400` = 86,400 s = 24 h. After **Round 1** fetches the 24 thumbnails, a
real browser stores each in its HTTP cache for 24 h. An HTMX sort re-renders
`#ad-list` (filter_form.html:4-9, `<form hx-get hx-target="#ad-list">`, 24 `<img>`
in ad_list.html:125-131) — but the browser now resolves those 24 `<img src>`
URLs from the **disk/HTTP cache** (a cache hit, status 200 from cache, `Age`
counted down) and issues **zero** network requests to `media_gate`.

Therefore:
- **Round 1** consumes 24 of the 240 budget (the fresh fetch).
- **Rounds 2-4** consume **0** budget — the thumbnails are cache hits.

The original reproduction assumed each sort re-issued 24 fresh requests
(`Cache-Control: no-cache` guaranteed no cache reuse). That assumption is now
invalidated on both axes:

| Axis | Before fix | After fix |
|---|---|---|
| Budget magnitude | 60 req / 60 s | 240 req / 60 s |
| Per-sort network requests | 24 (forced re-fetch) | 0 (cached for 24 h) |

### 2.4 New expected behavior under each client

**Real browser (the actual reported scenario):**
```
Round 1: 24 network fetches → 24 × 200, cumulative budget = 24
Round 2: sort → 24 cache hits, 0 fetches (cached 24 h)
Round 3: sort → 24 cache hits, 0 fetches
Round 4: sort → 24 cache hits, 0 fetches
```
No amount of sorting within the 24 h cache lifetime exhausts the budget. The
blankout is not reproducible. Even with the dev `LocMemCache` rate-limit counter
shared across requests, the browser never sends the second-round requests that
would have been the trigger.

**curl with no cache (the controlled probe) — budget only:**
```
Rounds 1-10: 10 × 24 = 240 × 200  (exhaustion only at request #241)
Round 11: 24 × 429
```
So the curl probe still reproduces a 429 — but only on the **241st** request
(spread across 11 rounds), not the 61st. To observe it the tester must disable
curl's cache (`--no-cache`) and issue ≥241 requests; the original "Round 3
exhaustion" no longer occurs.

### 2.5 Verdict: FIXED

The round-by-round blankout (Rounds 1-4 with 429s appearing mid-Round 3) cannot
be reproduced after the fix. Client-side caching is the dominant change: with
`max-age=86400`, the browser does not re-fetch thumbnails on a re-sort, so the
rate-limit budget is no longer consumed per sort. The 4× budget raise is a
secondary defense-in-depth that only matters for non-cacheable clients (curl,
proxies that strip the TTL, or users who hard-reload/bust cache).


## 3. Evidence Set C — Response headers

### 3.1 Original evidence (researcher_1_curl §5-6; P-003 §3.3)

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
The 429 body was 0 bytes, matching `rate_limited_response(json=False)` →
`HttpResponse(status=429)`.

### 3.2 Current 200 headers (post-remediation)

`src/backend/apps/ads/views/listings.py`:
- Line 84: `_MEDIA_CACHE_CONTROL_200: Final[str] = "public, max-age=86400"`
- Lines 252, 256, 275, 280: every 200 serving branch now sets
  `response["Cache-Control"] = _MEDIA_CACHE_CONTROL_200` (was `"no-cache"` on
  the DEBUG branch and `"no-store"` on the production branch).

Confirmed by `TestMediaGateCacheControl` (test_media_security.py:719-925), e.g.
:740:
```python
assert response.headers.get("Cache-Control") == "public, max-age=86400"
assert "no-store" not in response.headers.get("Cache-Control", "")
assert "immutable" not in response.headers.get("Cache-Control", "")   # :924
```

**ETag / Last-Modified:** still absent — confirmed unchanged. No
`USE_ETAGS` anywhere (code_context.md §1.6 / "4. New relevant code … USE_ETAGS"),
no `ConditionalGetMiddleware`/`EtagMiddleware` in `MIDDLEWARE` (base.py:332-348),
and `_serve_image` returns a `FileResponse` with no `Last-Modified`
(listings.py:151-168). The fix chose `Cache-Control: max-age` instead of
conditional validation, so ETag/Last-Modified deliberately remain absent.

**Vary:** still `Cookie` (from `@vary_on_headers("Cookie")` at listings.py:171)
+ `Accept-Language` (from `LanguagePreMiddleware.process_response`,
language.py:159, applied to every response). Unchanged.

### 3.3 Current 429 headers (post-remediation)

`src/backend/apps/ads/views/listings.py` (lines 211-217):
```python
response = rate_limited_response(
    json=False,
    retry_after=MEDIA_RATE_LIMIT_PERIOD,     # listings.py:213 → 60
    body=_MEDIA_GATE_429_SVG,                # listings.py:214 → 140-byte SVG
)
response["Content-Type"] = "image/svg+xml"  # listings.py:216
return response                              # listings.py:217
```

`src/backend/apps/core/utils/rate_limit_response.py` (lines 53-62):
```python
def rate_limited_response(*, json: bool = True, retry_after=None, body=None):  # line 34
    if json:
        response: HttpResponse = JsonResponse({"error": RATE_LIMIT_ERROR}, status=429)  # line 54
    else:
        response = HttpResponse(status=429)        # line 56
    response["Cache-Control"] = "no-store"          # line 58  (NEW on every 429)
    if retry_after is not None:
        response[RETRY_AFTER_HEADER] = str(retry_after)  # lines 59-60
    if body is not None:
        response.content = body                     # lines 61-62  (NEW)
    return response
```

The SVG fallback constant (listings.py:70-75):
```python
_MEDIA_GATE_429_SVG: Final[str] = (
    '<svg xmlns="http://www.w3.org/2000/svg" '
    'width="240" height="180" viewBox="0 0 240 180">'
    '<rect width="240" height="180" fill="#e5e7eb"/>'
    "</svg>"
)
```
This concatenates to exactly **140 bytes** (verified by byte-counting the source
string: 40 + 47 + 47 + 6 = 140). The attribution record
(docs/99-agent/nginx-rate-limit-attribution-record.md:90) approximates this as
"~159 bytes"; the exact figure from the source is 140 — both are non-zero, which
is what matters for §6.

**Resulting 429 shape:**
- `Status: 429`
- `Content-Type: image/svg+xml`  (overridden at listings.py:216; was `text/html; charset=utf-8`)
- `Cache-Control: no-store`  (rate_limit_response.py:58)
- `Retry-After: 60`  (retry_after=MEDIA_RATE_LIMIT_PERIOD=60 → str)
- `Content-Length: 140`  (the SVG body)
- `Body: <svg .../> `  (non-empty; renders as a gray 240×180 rectangle in the `<img>` slot)

Confirmed by `TestMediaGateApplicationRateLimit` (test_media_security.py:950-969,
:988-1008) and the dedicated tests (cb798afa) :1050-1067:
```python
assert response.headers.get("Retry-After") == str(MEDIA_RATE_LIMIT_PERIOD)   # :966, :1005
assert "<svg" in response.content.decode()                                   # :967, :1006
assert response.headers.get("Content-Type") == "image/svg+xml"             # :968, :1007
assert response.headers.get("Cache-Control") == "no-store"                  # :969, :1008
assert _MEDIA_GATE_429_SVG in body                                           # :1066
```

### 3.4 Verdict: FIXED

- **200**: `Cache-Control` changed from `no-cache`/`no-store` → `public, max-age=86400`. ✓
- **200**: ETag/Last-Modified absent (unchanged, by design). ✓ (matches original)
- **200**: `Vary: Cookie, Accept-Language` unchanged. ✓
- **429**: `Content-Type` changed `text/html; charset=utf-8` → `image/svg+xml`. ✓
- **429**: `Content-Length: 0` → `Content-Length: 140` (non-empty body). ✓
- **429**: empty body → 140-byte SVG placeholder. ✓
- **429**: `Retry-After` absent → `Retry-After: 60` (NEW). ✓
- **429**: `Cache-Control` absent → `Cache-Control: no-store` (NEW). ✓

Every header in the original Evidence Set C is either materially improved (FIXED)
or intentionally preserved (UNCHANGED); none reproduces its pre-fix value.


## 4. Evidence Set D — Code path (rate-limit guard runs before DB/disk)

### 4.1 Original evidence (researcher_1_curl §Code confirmation; researcher_2 §3)

The rate-limit guard in `media_gate` runs **before** any DB lookup or disk
access, so an over-budget client never reaches the database or the filesystem.
The original reports placed the guard at "lines 186-191" (listings.py).

### 4.2 Current source (guard order, post-remediation)

`src/backend/apps/ads/views/listings.py`, `media_gate` (decorator at:171, def at:172):

```python
@vary_on_headers("Cookie")                                              # line 171
def media_gate(request: HttpRequest, image_key: str) -> HttpResponseBase:  # line 172
    ...
    media_key = _MEDIA_RATE_LIMIT_KEY_PATTERN.format(ip=get_client_ip(request))  # line 206
    if not bump_rate_limit_window(                                    # lines 207-209
        media_key, MEDIA_RATE_LIMIT_REQUESTS, MEDIA_RATE_LIMIT_PERIOD
    ):
        logger.warning("Media gate rate limit exceeded")              # line 210
        response = rate_limited_response(                             # lines 211-215
            json=False,                                               #
            retry_after=MEDIA_RATE_LIMIT_PERIOD,                       #
            body=_MEDIA_GATE_429_SVG,                                  #
        )                                                             #
        response["Content-Type"] = "image/svg+xml"                    # line 216
        return response                                               # line 217

    # --- NUL byte guard ---                                          # line 224
    if any(ord(ch) < 0x20 for ch in image_key):
        raise Http404("Image not found")

    # --- Path-traversal guard ---                                    # lines 230-233
    try:
        assert_storage_key_contained(image_key)
    except ValueError:
        raise Http404("Image not found") from None

    # --- AdImage lookup (DB) ---                                     # lines 241-246
    key_q = Q()
    for column in KEY_COLUMNS:
        key_q |= Q(**{column: image_key})
    if not AdImage.objects.filter(key_q).exists():   # ← DB hit
        raise Http404("Image not found")

    # --- STAFF branch ---                                            # lines 249-257
    if request.user.is_staff:
        ...
    # --- NON-STAFF authorization + serve ---                         # lines 266-281
    if not AdImage.objects.filter(
        account_state_q("ad__user__"), key_q, ad__status=AdStatus.PUBLISHED,
    ).exists():
        return HttpResponseForbidden(_("Access denied"))              # line 271
    ...                                                               # X-Accel / DEBUG serve
```

### 4.3 Line-number note (stale reference in the task)

The task's Evidence Set D text and `code_context.md` (written pre-remediation)
cite the guard at "lines 186-191". That was the **pre-remediation** line range
(code_context.md §1b also documents the decorator/def at 151/152 and body to
255 for that older revision). The remediation added two constant blocks
above the view — `_MEDIA_GATE_429_SVG` (listings.py:70-75) and the
`_MEDIA_CACHE_CONTROL_200` comment+constant (listings.py:77-84) — which shifted
the entire `media_gate` body **+20 lines**. The **current** guard is at
**listings.py:206-217** (key derivation at :206; the `if not bump...` check at
:207-209; the return at :211-217). The behavior is identical; only the line
numbers drifted.

### 4.4 Verdict: CONFIRMED (guard order unchanged)

The four remediation commits did **not** reorder the request-lifetime flow:
1. Rate-limit guard (cache.add/incr via `bump_rate_limit_window`) — listings.py:206-217
2. NUL-byte guard — listings.py:224
3. Path-traversal guard — listings.py:230-233
4. `AdImage.objects.filter(...).exists()` DB query — listings.py:245
5. Staff / non-staff auth + serving branches — listings.py:249-281

An over-budget client still returns a 429 **before** any DB lookup
(`AdImage.objects.filter`, :245/:266) or disk access (`_serve_image` /
`X-Accel-Redirect`). This is independently pinned by
`test_over_budget_is_refused_before_the_db_lookup` (test_media_security.py:988-1008),
which issues `MEDIA_RATE_LIMIT_REQUESTS` requests (exhausting the budget) against
a **valid PUBLISHED** ad key and still asserts `429`.

What the remediation *did* change about this guard:
- **Budget**: 60 → 240 (enums.py:63).
- **429 response shape**: now passes `retry_after=60` and `body=_MEDIA_GATE_429_SVG`
  and sets `Content-Type: image/svg+xml` (listings.py:211-217), instead of the old
  bare `rate_limited_response(json=False)` → empty `HttpResponse(status=429)`.
- **Generic builder**: `rate_limited_response` now also sets
  `Cache-Control: no-store` on every 429 and supports the `retry_after`/`body`
  kwargs (rate_limit_response.py:58-62).

But the **position and semantics** of the guard are unchanged: it still executes
first and still fails open on a cache outage (cache.py:83-85).


## 5. Verdict table

| # | Evidence set | Original finding | Post-remediation state | Verdict |
|---|---|---|---|---|
| A | Single-URL threshold (60/61 boundary) | 60 allowed, #61 → 429 | 240 allowed, #241 → 429 (enums.py:63; cache.py:90; test @ test_rate_limit_budget.py:82) | **FIXED** |
| B | Round-by-round (429 on round 3) | 24 imgs/round re-fetched, budget exhausted mid-round 3 | `Cache-Control: public, max-age=86400` (listings.py:84) — browser reuses cached thumbnails on re-sort; rounds 2-4 make 0 network requests; curl probe now needs ≥241 requests | **FIXED** |
| C | 200 headers | `Cache-Control: no-cache`, no ETag/Last-Modified | `Cache-Control: public, max-age=86400` (listings.py:252/256/275/280); ETag/Last-Modified still absent by design; Vary unchanged | **FIXED** |
| C | 429 headers | `Content-Type: text/html`, `Content-Length: 0`, empty body | `Content-Type: image/svg+xml` (listings.py:216); `Retry-After: 60` (rate_limit_response.py:59); `Cache-Control: no-store` (rate_limit_response.py:58); 140-byte SVG body (listings.py:70-75) | **FIXED** |
| D | Guard runs before DB/disk | Guard first, then lookup/serve | Guard still first: listings.py:206-217 precede NUL guard (:224), traversal guard (:230-233), DB `exists()` (:245), serving (:249-281) | **CONFIRMED** |


## 6. Remaining gaps — the `$body_bytes_sent == 0` attribution rule

### 6.1 The rule and why it mattered

The deployment measurement gate for the nginx rate-limit (B-02/B-05) attributes
each `/media/` `GET` 429 to one of two origins using a **one-sided** test on the
nginx access log:

> `Django-origin ⟺ $body_bytes_sent == 0`
> (docs/99-agent/nginx-rate-limit-attribution-record.md:85)

`log_format main` places `$body_bytes_sent` immediately after `$status`
(docker/nginx/nginx.conf:14-16):
```nginx
log_format main '$remote_addr - $remote_user [$time_local] "$request" '
                '$status $body_bytes_sent "$http_referer" '
                '"$http_user_agent" "$http_x_forwarded_for"';
```
The discriminator is free (no nginx config edit, no production-Python edit) and
was sound because the pre-fix `media_gate` 429 had an **empty body**
(`HttpResponse(status=429)` → `body_bytes_sent == 0`), while nginx's own 429 (from
`limit_req` on `location /media/`) carries a non-empty default error page.

### 6.2 Why the fix breaks the discriminator (not the bug, the measurement)

Commit `cb798afa` made `media_gate`'s 429 return a **140-byte SVG** body
(listings.py:70-75, :214). The attribution record documents this precisely as a
known, accepted regression of the measurement rule:

> "the Django 429 had an empty body before commit `cb798afa`; `media_gate` now
> returns a non-empty SVG fallback body (~159 bytes) on 429 (commit `cb798afa`),
> so `$body_bytes_sent > 0`; the one-sided `== 0` test mis-classifies
> Django-origin 429s as nginx-origin candidates"
> (docs/99-agent/nginx-rate-limit-attribution-record.md:90, Corrected fact #12 @ line 252)

> Corrected fact #13 (the exposure precondition) likewise re-derives the
> "first rejection at > 240" threshold from the new budget:
> `RateLimitBudget.MEDIA_GATE` is now 240/60s, so the precondition is
> `R > 240` per key per fixed 60 s window (attribution-record.md:105-112).

### 6.3 Impact on evidence verification

This gap affects the **nginx-vs-Django attribution measurement**, not the
P-003 reproduction itself. The two are independent:

- **P-003 reproduction** (the question asked here): the rate-limit blankout is NOT
  reproducible — covered by §1-5. The non-empty 429 body is exactly the FIX that
  prevents the blank `<img>`; that it happens to also break an *external* log
  parse is a side effect, not a regression of the user-facing behavior.
- **Attribution gate measurement**: the one-sided `$body_bytes_sent == 0` rule
  now produces a **false VOID** on a healthy stack, because a Django-origin 429
  no longer has `body_bytes_sent == 0`. When Django rejects (429 with the SVG
  body), the access channel buckets it as a "non-empty body → nginx-origin
  candidate" (`requests_media_429_nonempty_body`), so it is *not* counted as
  Django-origin, the error channel (nginx-only) does not corroborate, and
  `attribution_delta != 0` → C1 soundness failure → **VOID**. See
  attribution-record.md:92-96 and the worked "false VOID" path at :100-101.

### 6.4 Durable resolution (deferred, documented)

The record specifies the durable fix as a **deferred successor** (§6) that is
explicitly out of scope for P-003's remediation:

> "The durable fix is the Deferred successor (§6): add `$limit_req_status` to
> `log_format main` and attribute on `REJECTED`."
> (attribution-record.md:90, :252)

I.e., attribute nginx-origin 429s by `$limit_req_status = REJECTED` and treat
non-REJECTED 429s as Django-origin — a discriminator that no longer depends on
body length. This requires an nginx `log_format` change plus a parallel update to
the aggregator script `scripts/measure-nginx-rate-limit-keys.py` (which parses
`$status $body_bytes_sent` at line 67 and buckets on `body_bytes_sent == 0` at
line 270) and its unit test `test_measure_nginx_rate_limit_keys.py:9-18`.

### 6.5 Does this gap affect the present verification?

**No.** The evidence verification concerns whether P-003's blankout reproduces,
not whether the deployment log-attribution gate can still distinguish Django 429s
from nginx 429s. The two are deliberately decoupled in the record: the SVG body
is the *intended* user-facing fix (graceful degradation instead of a blank
`<img>`), and the attribution rule breakage is a *measurement* consequence that
the attribution record has already catalogued as CORRECTED with a deferred
successor. The only caveat worth flagging to a reader of this report: a future
re-attestation of the rate-limit gate must not rely on `$body_bytes_sent == 0`
to count Django-origin refusals on `/media/`; it must use the `$limit_req_status`
successor (or an equivalent non-body discriminator) to avoid a false VOID.


## 7. Final answer

**Is the original bug (P-003) reproducible after the fix? NO.**

The original reproduction hinged on three independent premises, all of which the
remediation breaks:

1. **A 60-request budget** (enums.py:63 → now 240) — the 60/61 boundary that
   produced the first 429 after ~2.5 sorts is gone; the boundary moved to
   240/241 (§1, Evidence Set A).
2. **No client-side caching of thumbnails** (listings.py:84 → `Cache-Control:
   public, max-age=86400`) — a browser re-sorting the listing now reuses cached
   thumbnails and issues zero new `media_gate` requests, so the per-sort budget
   burn that exhausted the limiter on round 3 no longer happens (§2, Evidence
   Set B).
3. **An empty-body 429** (listings.py:211-217; rate_limit_response.py:58-62) —
   even if a client did exhaust the 240 budget, the 429 no longer renders as a
   blank `<img>`: it carries a 140-byte `image/svg+xml` gray rectangle matching
   the 240×180 thumbnail slot, plus `Retry-After: 60` and `Cache-Control: no-store`,
   so failed thumbnails degrade gracefully instead of blanking out (§3,
   Evidence Set C).

The **rate-limit guard order** (Evidence Set D, §4) is confirmed unchanged:
the guard still runs first (listings.py:206-217, before the NUL guard :224,
traversal guard :230-233, and the `AdImage` DB query :245), and still fails open
on cache outage (cache.py:83-85). The fix does not reorder the guard — it widens
the budget, shapes the 429, and caches the 200.

The one residual, documented gap is **measurement-only**: the nginx attribution
record's one-sided `$body_bytes_sent == 0` rule (docs/99-agent/
nginx-rate-limit-attribution-record.md:85, corrected @:90 and :252) no longer
identifies Django-origin 429s because the body is now non-empty (140 bytes).
This is catalogued as CORRECTED with a deferred successor (`$limit_req_status`
on `log_format main`) and does not reintroduce the user-facing blankout.
