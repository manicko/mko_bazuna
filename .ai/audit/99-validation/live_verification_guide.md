# Live Verification Guide — P-003 media_gate Rate-Limit Fix

Status: **FIX APPLIED AND LIVE-VERIFIED.** The remediation shipped across three
commits and is currently running on the dev site at `http://127.0.0.1:8000` (container
`mko-bazuna-dev-web`). This guide records how to start the environment, the exact
`curl` reproduction, the expected responses *now* (post-fix), and whether the
*original* reproduction still triggers the bug.

## What changed (the fix)

The original bug report (`.ai/audit/problems/P-003-media-rate-limit-blankout.md`)
described a `media_gate` budget of **60 requests / 60 s** whose **61st** request
returned an **empty-body HTTP 429** (`Content-Type: text/html`, 0 bytes, no
`Retry-After`), and whose 200 responses carried `Cache-Control: no-cache` with no
`ETag`/`Last-Modified` — so every HTMX sort re-fetched all 24 thumbnails and
exhausted the budget after ~2.5 page loads.

The fix is implemented in plan `.ai/plans/001-media-rate-limit-remediation.md`
(three independent blocks) and applied to source in:

| Block | Commit | Effect | Source |
|---|---|---|---|
| **A** | `f949d554` | 200 `Cache-Control`: `no-cache`/`no-store` → `public, max-age=86400` (no `immutable`) | `listings.py:84,252,256,275,280` |
| **B** | `410896fc` | `MEDIA_GATE` budget: **60 → 240** req / 60 s | `enums.py:63` (value), `enums.py:45-46` (docstring), `listings.py:60-62` |
| **C** | `cb798afa` | 429 returns **SVG placeholder + `Retry-After: 60` + `Cache-Control: no-store`** | `listings.py:66-75,206-217`, `rate_limit_response.py:21-63` |

The shared helper `rate_limited_response` (`apps/core/utils/rate_limit_response.py`)
gained two optional parameters — `retry_after: int | None = None` and
`body: str | None = None` (both `None` by default) and now sets
`Cache-Control: no-store` on every 429 it emits. This is backward-compatible with
all 8 callers (only `media_gate` passes the new args).

## 1. Environment setup — start the dev site with seeded data

The dev project is `mko-bazuna-dev`. The canonical entry point on Windows is
`Makefile.ps1` (PowerShell 7+); it sets `COMPOSE_PROJECT_NAME=mko-bazuna-dev` and
uses `--env-file .env.dev`.

```powershell
# 1. Ensure .env.dev exists (copy the template; required by compose interpolation).
if (!(Test-Path .env.dev)) { Copy-Item .env.dev.example .env.dev }

# 2. (First time only) build the image.
.\Makefile.ps1 build

# 3. Start the dev stack: db + redis + migrate + load_cities + load_catalog +
#    seed + web (runserver on :8000) + bot.
.\Makefile.ps1 up
```

Key facts that make verification possible:

- **`web` serves on host `:8000`** — `docker-compose.dev.override.yml:25-26` publishes
  `"8000:8000"`, and `web.command` runs `python src/backend/manage.py runserver 0.0.0.0:8000`
  (dev.override `:7-9`).
- **Seed data is populated before `web` starts.** The dev override declares
  `web.depends_on.seed.condition: service_completed_successfully`
  (dev.override.yml:29-31), and the `seed` one-shot writes the demo ads **and** the
  image files into the shared `media_volume` (seed images land at `/app/media/seed/...`
  inside the container, mapped from `media_volume`). The default seed counts are
  `SEED_USERS=10`, `SEED_ADS=600` (env.dev.example:98-99, dev.override.yml:147).
- **The dev cache is `LocMemCache`** — in-process, so the single `runserver`
  process shares the `media_gate_rl:127.0.0.1` counter across all requests, exactly
  reproducing the per-IP budget behaviour. (`dev.py:58-63` sets
  `CACHES["default"] = LocMemCache`.)
- **No nginx in the default dev stack** — nginx is gated behind the `use-nginx`
  profile (dev.override.yml:158-160) and is *off* by default. So the only limiter
  on `/media/` in the default dev site is the application-level `MEDIA_GATE` guard.
  (nginx's `limit_req zone=browse_limit burst=40 nodelay` on `location /media/` lives
  in `docker/nginx/nginx.dev.conf:107` and `docker/nginx/nginx.conf:112`, and is the
  "proxy half" referenced in `listings.py:52-53`.)

Seed media URLs are served through `media_gate` (`/ads/urls.py:25`:
`path("media/<path:image_key>", media_gate, ...)`); there is **no** `static()` media
fallback, so every `/media/...` request runs the view — including the rate-limit
guard.

### Pre-flight checks

```powershell
# Dev site running on :8000?
docker ps --filter "name=mko-bazuna-dev-web"
# (should show 0.0.0.0:8000->8000/tcp, Status "healthy")

# Seed images present at /media/seed/? (run inside the web container, or just curl)
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8000/media/seed/pedicure_01-small.jpg
# expect 200
```

## 2. Curl reference table (single URL, fresh 60 s window)

The target URL from the original repro — `/media/seed/pedicure_01-small.jpg` — is
still valid and fetchable (verified live: 200, `image/jpeg`, 9136 bytes).

`curl` does **not** consult the browser HTTP cache, so it hits the application
rate limiter on every request. With the budget now **240 req / 60 s**, the boundary
moves from **#61** (old) to **#241** (new).

| Request # | HTTP status | `Cache-Control` | `Retry-After` | `Content-Type` | Body | `Vary` |
|---|---|---|---|---|---|---|
| `#1` (first, under budget) | **200** | `public, max-age=86400` | — | `image/jpeg` | 9136-byte JPEG | `Cookie, Accept-Language` |
| `#240` (last allowed) | **200** | `public, max-age=86400` | — | `image/jpeg` | 9136-byte JPEG | `Cookie, Accept-Language` |
| `#241` (first over budget) | **429** | `no-store` | `60` | `image/svg+xml` | 140-byte SVG rect | `Cookie, Accept-Language` |
| `#300` (still over budget) | **429** | `no-store` | `60` | `image/svg+xml` | 140-byte SVG rect | `Cookie, Accept-Language` |

Notes:
- The 60 s window is keyed per client IP (`media_gate_rl:{ip}`, `listings.py:64`).
  After 60 s of no requests, `cache.add` resets the counter (`cache.py:80-81`).
- `Retry-After: 60` equals `MEDIA_RATE_LIMIT_PERIOD` (`enums.py:74` = `60`), passed
  as `retry_after=MEDIA_RATE_LIMIT_PERIOD` (`listings.py:213`).
- The 200 `Vary: Cookie, Accept-Language` comes from the `@vary_on_headers("Cookie")`
  decorator (`listings.py:171`) plus Django's `LocaleMiddleware` adding
  `Accept-Language` — present on both 200 and 429.
- The 429 body is exactly `_MEDIA_GATE_429_SVG` (`listings.py:70-75`), 140 bytes:
  `<svg xmlns="http://www.w3.org/2000/svg" width="240" height="180" viewBox="0 0 240 180"><rect width="240" height="180" fill="#e5e7eb"/></svg>`

## 3. Exact curl commands

### 3.1 Single-URL threshold test (replaces original 70× test)

```powershell
$url = "http://127.0.0.1:8000/media/seed/pedicure_01-small.jpg"
# Requests 1..250: expect 200 until #240, then 429 from #241 onward.
for ($i = 1; $i -le 250; $i++) {
    $code = curl -s -o /dev/null -w '%{http_code}' $url
    if ($i -in 1, 240, 241, 250) { Write-Host "req #$i -> $code" }
}
```

Expected output (fresh window):
```
req #1 -> 200
req #240 -> 200
req #241 -> 429
req #250 -> 429
```

### 3.2 Inspect the 429 response in detail

```powershell
# Exhaust the budget first, then examine the next 429.
$url = "http://127.0.0.1:8000/media/seed/pedicure_01-small.jpg"
1..240 | ForEach-Object { curl -s -o /dev/null $url } | Out-Null
curl -s -D - -o /dev/null $url          # request #241
curl -s $url                            # request #242, prints the SVG body
```

Expected: status `429`, headers `Cache-Control: no-store`, `Retry-After: 60`,
`Content-Type: image/svg+xml`, `Content-Length: 140`, body = the SVG rectangle.

### 3.3 Round-by-round test (mimics browser sorts, 24 URLs per round)

```powershell
$urls = (curl -s "http://127.0.0.1:8000/?sort=date_desc" |
    Select-String -Pattern 'src="(/media/[^"]+)"' -AllMatches).Matches |
    ForEach-Object { "http://127.0.0.1:8000$($_.Groups[1].Value)" }

for ($r = 1; $r -le 11; $r++) {
    $codes = foreach ($u in $urls) { curl -s -o /dev/null -w '%{http_code}' $u }
    $g = $codes | Group-Object -NoElement
    { "round {0}: {1}" -f $r, (($g | ForEach-Object { "$($_.Count)x$($_.Name)" }) -join ', ') } | Write-Host
}
```

Expected (curl, no client cache): rounds 1–10 all `24x200` (cumulative 240);
round 11 first request = `429`.

## 4. Header verification checklist

Assert these on the **200** response (`listings.py:245-281` → `_serve_image`
DEBUG branch or `X-Accel-Redirect` prod branch):

- [ ] `Cache-Control: public, max-age=86400` — exact (`listings.py:84`)
- [ ] `immutable` **absent** from `Cache-Control` — image keys are NOT
  content-addressed (UUID v4 / fixed seed names); see plan §13.
- [ ] `Vary` contains `Cookie` (and `Accept-Language`)
- [ ] `Content-Type: image/jpeg` (or the file's real type)
- [ ] `X-Content-Type-Options: nosniff` (`listings.py:167`/`_serve_image`)

Assert these on the **429** response (`listings.py:206-217` → `rate_limited_response`):

- [ ] Status **429**
- [ ] `Retry-After: 60` — equals `MEDIA_RATE_LIMIT_PERIOD` (`rate_limit_response.py:59-60`,
  `listings.py:213`)
- [ ] `Content-Type: image/svg+xml` (`listings.py:216` overrides the default)
- [ ] `Cache-Control: no-store` (every 429; `rate_limit_response.py:58`)
- [ ] Body is the 140-byte SVG rectangle starting with `<svg` and containing
  `fill="#e5e7eb"` (`listings.py:70-75`)
- [ ] `Vary` present (`Cookie, Accept-Language`)

Pinned by tests:
- `test_media_security.py:1046-1048` — `(MEDIA_RATE_LIMIT_REQUESTS, MEDIA_RATE_LIMIT_PERIOD) == (240, 60)`.
- `test_media_security.py:960-969` — 429 shape: `Retry-After == str(MEDIA_RATE_LIMIT_PERIOD)`,
  `<svg` in content, `Content-Type == image/svg+xml`, `Cache-Control == no-store`.
- `test_media_security.py:728-742` / `:811-832` — 200 `Cache-Control == "public, max-age=86400"`,
  no `immutable`, `cookie` in `Vary`.
- `test_rate_limit_budget.py:82` — `(240, 60)` reviewed budget.
- `test_media_security.py:971-986` — 240 requests all 200, 241st is 429
  (`test_media_gate_budget_allows_ten_page_loads`).

## 5. Live verification (executed against the running dev site)

The dev site was already running (`docker ps`: `mko-bazuna-dev-web`,
`0.0.0.0:8000->8000/tcp`, healthy). The probe below was run against it with a
fresh counter (the listing-page HTML fetch does not consume media budget).

### 5.1 Seed image is served by `media_gate` (24 `<img>` on the listing)

```
listing_status=200
--- 24 distinct media URLs extracted ---
/media/seed/apartment-cleaning_06-small.jpg
/media/seed/auto-equipment_09-small.jpg
... (24 total, all under <div id="ad-list">)
/media/seed/women-shoes_08-small.jpg
```

### 5.2 Request #1 — 200 with the NEW caching header

```
HTTP/1.1 200 OK
Content-Type: image/jpeg
Content-Length: 9136
Content-Disposition: inline; filename="pedicure_01-small.jpg"
Cache-Control: public, max-age=86400
Vary: Cookie, Accept-Language
```
✓ `Cache-Control` is `public, max-age=86400` (was `no-cache` before the fix).

### 5.3 Burst #2–#250 — boundary holds at 240/241

```
Burst summary (requests #2-#250, 249 requests):
  HTTP 200: 239
  HTTP 429: 10
  Total captured: 249
```
Including request #1: **240× HTTP 200** (requests #1–#240), then **HTTP 429** from
#241 onward. ✓ The first 429 lands exactly on request #241 — the 60/61 boundary
shifted to 240/241.

### 5.4 Request #241 — 429 with SVG + Retry-After

```
HTTP/1.1 429 Too Many Requests
Content-Type: image/svg+xml
Cache-Control: no-store
Retry-After: 60
Vary: Cookie, Accept-Language
Content-Length: 140

<svg xmlns="http://www.w3.org/2000/svg" width="240" height="180"
viewBox="0 0 240 180"><rect width="240" height="180" fill="#e5e7eb"/></svg>
```
✓ Status 429, `Retry-After: 60`, `Content-Type: image/svg+xml`,
`Cache-Control: no-store`, 140-byte SVG body. (No empty body, no `text/html`.)

## 6. Does the ORIGINAL reproduction still reproduce the bug?

**No — both original reproduction paths are neutralised by the fix.**

### 6.1 Original single-URL test (70× → was 429 at #61)

The original report fetched
`/media/seed/pedicure_01-small.jpg` 70 times and asserted `61: 429`. Under the fix
the budget is 240, so **all 70 requests return 200** — the "61st = 429" assertion
now **fails against the old expectation**, confirming the budget change. A curl
loop must run **240 successful + 1 refused** (= #241) to see the first 429.

| Original (pre-fix) | Post-fix |
|---|---|
| 60 req / 60 s | 240 req / 60 s |
| first 429 at **#61** | first 429 at **#241** |
| 70× curl → 10 returns 429 | 70× curl → **0** returns 429 (all 200) |

### 6.2 Original round-by-round test (4 rounds × 24 = 96 → was 429 in round 3)

The original report: round 1 = 24×200, round 2 = 24×200, round 3 = 12×200 + 12×429,
round 4 = 0×200 + 24×429 (budget exhausted at #61).

A naïve **curl** (which ignores `Cache-Control`) still reproduces an eventual 429,
but only after **round 10** (240 successes); round 11's first request is 429. The
original 4-round reproduction now yields **96×200, 0×429** — the blankout does not
occur.

### 6.3 Browser-level reproduction is eliminated entirely

This is the decisive change. With `Cache-Control: public, max-age=86400` on every
200 response, a real browser **does not re-fetch** thumbnails on a sort:

1. The first page load fetches 24 thumbnails (24 of the 240-request budget).
2. Each `<img>` response is stored in the browser HTTP cache, fresh for 24 h
   (`max-age=86400`).
3. On an HTMX `?sort=...` re-render, `#ad-list` is swapped with new `<img>` tags
   whose `src` URLs are **identical** to the just-cached ones (the same seed
   thumbnails per ad). The browser resolves each new `<img>` against its cache,
   and — because `max-age=86400` has not expired — serves the cached bytes
   **without a network request**. No `media_gate` call fires.
4. Repeat for every subsequent sort: 0 server requests, 0 budget consumed.

Before the fix, `Cache-Control: no-cache` (with no `ETag`/`Last-Modified`) forced
the browser to **revalidate** every image on every sort (a full GET, since there
was no validation token to make it a 304). That is what produced the "24
unconditional fetches per sort × ~2.5 sorts = budget exhausted" cascade. The
`max-age=86400` directive removes that cascade at the root.

Even if a user hard-refreshed (bypassing the cache) multiple times within 60 s,
the 240 budget absorbs **10 full 24-image page loads** before the limiter trips — vs.
the old 2.5 loads — and the SVG placeholder means that, at the limit, images
degrade to a visible gray rectangle rather than a broken-image icon / blank slot.

## 7. Summary — verify the fix in two commands

```powershell
.\Makefile.ps1 up
# then, in a fresh 60 s window:
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8000/media/seed/pedicure_01-small.jpg   # expect 200, Cache-Control: public, max-age=86400
# 240 succeeds then 1 refusal:
for ($i=1;$i-le-241;$i++) { $c=(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8000/media/seed/pedicure_01-small.jpg); if($i-in 240,241){"#$i -> $c"} }
# expect: #240 -> 200, #241 -> 429 (Cache-Control: no-store, Retry-After: 60, Content-Type: image/svg+xml)
```

A passing result matches the header checklist in §4 and the pinned tests in
`test_media_security.py` / `test_rate_limit_budget.py` — i.e. the (240, 60) budget,
the 24-hour public `max-age`, and the SVG+no-store+Retry-After 429 shape.
