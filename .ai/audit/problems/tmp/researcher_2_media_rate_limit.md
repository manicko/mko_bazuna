# Intermediate Report — Researcher: Media Gate Rate-Limit Blankout

## Task
Find the exact reproduction criteria and localize the code path for the user-reported
regression: "after sorting the listing page, some photos don't display; after several
browser refreshes they appear." URL: `http://localhost:8000/?listing_purpose=&condition=new&min_price=&max_price=&sort=date_desc`

## Investigation Steps Completed

### 1. Git History Review
- Latest commit: `5cdd1cfc` "fix(ads): generate seed images atomically and clean up the seed image test set" (Oct 7, 2026)
- A prior AI session concluded the root cause was a **non-atomic seed-image write** in
  `_preprocess_one` (`apps/seed/generators/images.py`), creating `.ai/audit/problems.md`.
- This is a **misdiagnosis**: the seed writer only runs during
  `docker compose run --rm seed`, not during a browser sort. A sort triggers HTMX to
  re-render `#ad-list` (24 `<img>` fetches to `/media/seed/...`), which never touches
  the seed generator.

### 2. Template Analysis
- `src/backend/templates/ads/partials/ad_list.html` lines 126–131:
  ```django
  <img src="{{ ad.images.first.thumbnail_small_url|default:ad.images.first.image_url }}"
       loading="lazy" width="240" height="180">
  ```
  24 images per page.
- `src/backend/templates/ads/partials/filter_form.html`: the sort selector lives in a
  form with
  ```django
  <form hx-get hx-target="#ad-list" hx-swap="innerHTML" hx-push-url="true">
  ```
  and `<select name="sort" onchange="this.form.requestSubmit()">`.
  Sorting = a full HTMX re-request that swaps `#ad-list`, issuing 24 new image fetches.

### 3. View / Route Analysis
- `src/backend/apps/ads/urls.py` line 25:
  ```python
  path("media/<path:image_key>", media_gate, name="media_gate")
  ```
  Root URLconf (`config/urls.py`) does **not** call `static()` for media — every
  `/media/...` request routes through `media_gate`.
- `src/backend/apps/ads/views/listings.py` `media_gate`:
  - Rate-limit guard runs **first** (before AdImage lookup or disk access).
  - `Cache-Control: no-cache` is set on both DEBUG (inline serve) and non-DEBUG paths.
  - No ETag / Last-Modified is set; `USE_ETAGS` defaults to False.

### 4. Rate-Limit Configuration
- `src/backend/apps/core/enums.py`:
  ```python
  class RateLimitBudget(StrEnum):
      MEDIA_GATE = "media_gate"
      # 60 requests / 60 seconds (see docstring on line 45–46)
  ```
  `.requests` → 60, `.period` → 60.
- `src/backend/apps/ads/views/listings.py` lines 60–62:
  ```python
  MEDIA_RATE_LIMIT_REQUESTS: int = RateLimitBudget.MEDIA_GATE.requests  # = 60
  MEDIA_RATE_LIMIT_PERIOD: int = RateLimitBudget.MEDIA_GATE.period      # = 60
  ```
- `src/backend/apps/core/utils/cache.py` `bump_rate_limit_window`:
  - Uses `cache.add(key, 1, timeout=period)` then `cache.incr(key)`.
  - Returns `True` for counts 1–60, `False` for 61.
  - TTL = 60s; after expiry, `cache.add` resets the window.

### 5. Cache Backend Confirmation
- Dev settings (`config/settings/dev.py` lines 58–63):
  ```python
  CACHES = {
      "default": {
          "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
      }
  }
  ```
  `LocMemCache` — in-process, shared across all requests within the single dev-server
  process. This means the rate-limit counter is process-global, not per-worker.
- Base settings note (`base.py` lines 622–630): in dev/test, `REDIS_URL=""` (empty);
  `CACHES` is overridden to `LocMemCache` (no Redis dependency). In production, Redis
  would be used.

### 6. IP Resolution Confirmation
- `src/backend/apps/core/utils/client_ip.py` `get_client_ip`:
  - Reads `REMOTE_ADDR` first; if it is loopback/private/trusted-proxy, consults
    `X-Real-IP` then `X-Forwarded-For` (right-to-left).
  - In dev: browser and curl both connect to `127.0.0.1` (loopback) → same bucket
    `media_gate_rl:127.0.0.1`.
- This confirms the browser and the curl reproduction share the same rate-limit budget.

### 7. Response Header Confirmation (curl)
**HTTP 200 (success):**
```
Cache-Control: no-cache
Vary: Cookie, Accept-Language
ETag — (absent)
Last-Modified — (absent)
```

**HTTP 429 (rate-limited):**
```
Content-Type: text/html; charset=utf-8
Content-Length: 0
Body: (empty)
```
Matches `rate_limited_response(json=False)` → `HttpResponse(status=429)`.

## Exact Reproduction Criteria

### Controlled (curl) — single URL 70×
```powershell
$url = "http://127.0.0.1:8000/media/seed/pedicure_01-small.jpg"
for ($i = 1; $i -le 70; $i++) {
    $code = curl -s -o /dev/null -w "%{http_code}" $url
    "$i : $code"
}
```
**Expected result:**
- Requests 1–60: HTTP 200
- Request 61: HTTP 429 (first refusal)
- Requests 62–70: HTTP 429

### Page-sort simulation — 24 URLs × 4 rounds
```powershell
# repro_media_429.ps1 (saved in this directory)
$url = 'http://127.0.0.1:8000/?sort=date_desc'
$html = curl -s $url
$urls = [regex]::Matches($html, 'src="(/media/[^"]+)"').Groups[1].Value  # 24 URLs

for ($round = 0; $round -lt 4; $round++) {
    $codes = @()
    foreach ($u in $urls) {
        $c = (curl -s -o nul -w '%{http_code}' "http://127.0.0.1:8000$u")
        $codes += $c
    }
    $g = $codes | Group-Object -NoElement
    $summary = ($g | ForEach-Object { "$($_.Count) x HTTP $($_.Name)" }) -join ', '
    Write-Host "round $($round+1): $summary"
}
```
**Expected output:**
```
round 1: 24 x HTTP 200
round 2: 24 x HTTP 200
round 3: 12 x HTTP 200, 12 x HTTP 429
round 4: 24 x HTTP 429
```

### Browser reproduction
1. Load `http://localhost:8000/?sort=date_desc` (page 1) — all images load (24 requests).
2. Sort again (page 2) — all images load (48 cumulative requests).
3. Sort again (page 3) — ~12 images fail with 429 (60th request is the cutoff).
4. Wait 60 seconds, refresh — all images load again (window reset).

## Localization

| Concern | File | Lines |
|---------|------|-------|
| Rate budget enum | `src/backend/apps/core/enums.py` | `RateLimitBudget.MEDIA_GATE` = (60, 60) |
| Rate-limit constants | `src/backend/apps/ads/views/listings.py` | 60–62 |
| `media_gate` view | `src/backend/apps/ads/views/listings.py` | 131–147 |
| `bump_rate_limit_window` | `src/backend/apps/core/utils/cache.py` | 60–90 |
| `rate_limited_response` | `src/backend/apps/core/utils/rate_limit_response.py` | 27–41 |
| URL route | `src/backend/apps/ads/urls.py` | 25 |
| Client IP resolution | `src/backend/apps/core/utils/client_ip.py` | 61–94 |
| Test assertions (budget = 60/60) | `src/backend/apps/core/tests/test_rate_limit_budget.py` | 67–82 |
| Test assertions (429 behavior) | `src/backend/apps/ads/tests/test_media_security.py` | 923–956 |
| Dev cache backend | `config/settings/dev.py` | 58–63 |
| Template (24 imgs) | `src/backend/templates/ads/partials/ad_list.html` | 126–131 |
| Template (HTMX sort) | `src/backend/templates/ads/partials/filter_form.html` | `<form hx-get hx-target="#ad-list">` |

## Root Cause (preliminary)
The application-level `media_gate` rate limiter (`RateLimitBudget.MEDIA_GATE` = 60
requests/60s per IP) is too tight for the listing page: each sort re-render fetches 24
thumbnails, and responses carry `Cache-Control: no-cache` with no `ETag`/`Last-Modified`,
so the browser cannot cache or revalidate them. After ~2–3 page sorts within 60s, the
60-request budget is exhausted; subsequent image requests get HTTP 429 with an empty
body, so `<img>` tags render blank. Images reappear after the 60-second window resets —
matching the user's "appear after several refreshes" symptom.

## Status
- **Investigation complete.** All code paths, config, and headers confirmed via curl.
- **Exact reproduction** achieved (60/61 boundary, 24-URL round test).
- **Localization** complete (see file/line table above).
- **Open question for root-cause auditor:** whether 60 req/60s is intentional for
  anonymous media serving or a regression from commit `5ffad37e`
  ("fix(ads): add the application-level limiter to the media gate (09-API-005)").
