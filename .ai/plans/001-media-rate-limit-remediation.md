# Execution Plan — P-003: media_gate rate-limit blankout on HTMX sort

## 1. Overview

### Problem
`media_gate` (listings.py:151) serves ad thumbnails with `Cache-Control: no-cache` / `no-store` (lines 226, 230, 249, 254). Each HTMX sort re-fetches all 24 thumbnails (ad_list.html:125-131, `PER_PAGE=24`) because the browser revalidates every image. The `MEDIA_GATE` rate-limit budget is 60 requests / 60s, which is exhausted after ~2.5 page loads, after which all subsequent image requests return **429 with an empty body** (no `Retry-After`, no SVG fallback) — breaking the ad list visually.

### Root Cause (confirmed via code_context.md)
1. **Images are not cacheable across navigations** — `no-cache`/`no-store` forces revalidation on every thumbnail fetch, and each revalidation counts against the rate-limit budget.
2. **Budget is too low** — 60/60s is insufficient for 24-image page loads × multiple sorts.
3. **429 response is non-graceful** — empty body, no `Retry-After` header (RFC 9110 §15.4.5 violation), no visual fallback content.

### Research Finding — Image keys are NOT content-addressed
The `immutable` Cache-Control directive is **UNSAFE** and MUST NOT be used. Investigation of four image-key sources confirms no content hash is embedded in the URL:

| Source | File:Line | Key format | Content hash? |
|---|---|---|---|
| User upload | `media/services/filesystem.py:260-262` | `{uuid4}.jpg` | No — UUID v4 is random, not derived from content |
| Ad thumbnail | `ads/models.py:643-649` | `AdImage.thumbnail_small_url` = `MEDIA_URL + {uuid-stem}-{size}.jpg` | No |
| Thumbnail file | `media/services/thumbnails.py:115` | `{stem}-{size}.jpg` | No |
| Seed image | `seed/generators/images.py:112,261` | `seed/{filename}.jpg` | No — fixed filename, content can change via `WriteMode.REPLACE` |
| SHA-256 field | `ads/models.py:643-649` | `AdImage.sha256` column | Stored but NOT in URL — used only for upload-time dedup |

**Implication**: If `immutable` were set, a seed image regeneration (`_preprocess_one` using `WriteMode.REPLACE`, `seed/generators/images.py:333`) would overwrite the file bytes at the same URL, but browsers would serve the stale cached version until the cache is manually cleared. The correct directive is `Cache-Control: public, max-age=86400` (NO `immutable`), allowing natural revalidation after the TTL expires.

### Three Work Blocks
- **Block A (primary fix)**: Enable safe browser caching of media responses (`max-age=86400`, no `immutable`).
- **Block B (defense-in-depth)**: Raise the `MEDIA_GATE` rate-limit budget to accommodate legitimate page-load traffic.
- **Block C (defense-in-depth)**: Make 429 responses RFC-compliant and visually graceful (Retry-After header + SVG fallback body + `no-store` Cache-Control).

```
Dependency graph:
  Block C → Block A  (both touch the 429 path in media_gate; C changes the call signature)
  Block B → (independent)
```

Recommended implementation order: **C first, then A, then B** — because Block C modifies the shared `rate_limited_response` function signature and the 429 call site in `media_gate`; Block A then modifies the 200-response paths; Block B is fully isolated in `enums.py`.

---

## 2. Work Block A — Enable safe client-side caching of media responses

### Goal
Reduce 429 frequency by making image requests cacheable. This is the **primary fix**: with `max-age=86400`, a user browsing the listing, sorting, and paginating will reuse cached thumbnails instead of revalidating 24 images per navigation.

### Targets
| File | Symbol / Region | Change |
|---|---|---|
| `apps/ads/views/listings.py:226` | `media_gate` 200-path, small thumbnail `Cache-Control` | `"no-cache"` → `"public, max-age=86400"` |
| `apps/ads/views/listings.py:230` | `media_gate` 200-path, medium thumbnail `Cache-Control` | `"no-cache"` → `"public, max-age=86400"` |
| `apps/ads/views/listings.py:249` | `media_gate` 200-path, original image `Cache-Control` | `"no-store"` → `"public, max-age=86400"` |
| `apps/ads/views/listings.py:254` | `media_gate` 200-path, fallback image `Cache-Control` | `"no-store"` → `"public, max-age=86400"` |

### Design Decisions
- **No `immutable`**: As documented in the research finding above.
- **`public`** (not `private`): media files are served via nginx (`/media/` location, `nginx.conf:107`) with no user auth context; `public` allows intermediary caches (CDN, nginx) to cache too.
- **`max-age=86400`** (24h): matches typical ad-image TTL. The listing HTML is not cached (no `Cache-Control` on `ad_list.html` page), so users always see a fresh ad list; only image bytes are cached. 24h is long enough to amortize the revalidation cost across many HTMX sorts, short enough that stale images are refreshed.
- **No ETag added**: the existing UUID-based keys change when an image is replaced (new UUID → new URL), so stale-cache risk is minimal. ETag would add complexity without addressing the core issue.

### Risk Assessment
- **Shared config / public API impact: none**. `media_gate` is only called by `<img src="...">` tags in templates; no API consumer depends on `no-cache`.
- **Data staleness**: A seller editing an ad generates a new image UUID (so the URL changes), so the browser fetches the new image. The old UUID URL remains on disk but is unreferenced. No stale-content risk.
- **Seed images**: `seed/{filename}.jpg` is served from the same `media_gate` path. If seed fixtures are updated (e.g., during development), old cached versions persist for up to 24h. This is acceptable for dev (`max-age=86400` is short; seed images are static fixtures that rarely change). To force-refresh during seed runs, the Implementor may append a query param to the URL (not required for this plan).

### Test Strategy
Update existing tests in `test_media_security.py`:

| Test class | File location | Current assertion | New assertion |
|---|---|---|---|
| `TestMediaGateCacheControl` | `tests/test_media_security.py:718-852` | `"no-store"` (prod), `"no-cache"` (dev) on 200 responses | `"max-age=86400"` (prod), `"max-age=86400"` (dev) on 200 responses |

Add a new test (in a new `TestMediaGateCacheControl` method, same file):
- `test_200_response_has_cache_control_max_age` — asserts `Cache-Control` contains `max-age=86400` and does NOT contain `immutable`.

### Verification
- Run: `.\Makefile.ps1 test` (or `$dc run --rm -e PYTEST_OPTS="src/backend/apps/ads/tests/test_media_security.py" test`)
- Assert: all `TestMediaGateCacheControl` tests pass; no `immutable` in any Cache-Control header.

---

## 3. Work Block B — Raise MEDIA_GATE rate-limit budget

### Goal
Increase the rate-limit budget from 60 req / 60s to 240 req / 60s (4× the current value), providing headroom for 24-image page loads + HTMX sorts. This is defense-in-depth: Block A reduces requests via caching, Block B ensures the remaining uncached requests (e.g., first page load, cold cache, new users) don't hit the budget.

### Target
| File | Symbol / Region | Current | Proposed |
|---|---|---|---|
| `apps/core/enums.py:63` | `RateLimitBudget.MEDIA_GATE` requests | `60` | `240` |
| `apps/core/enums.py:74` | `RateLimitBudget.MEDIA_GATE` period | `60` | `60` (unchanged) |
| `apps/core/enums.py:45-46` | `RateLimitBudget.MEDIA_GATE` docstring | references 60/60 | update to reference 240/60 |

### Design Decisions
- **Only change requests (60 → 240), not period**: The budget window (60s) is the reviewed, documented value. 4× the request count provides headroom for 10 page loads (24 images each) within the 60s window.
- **`240` is exact**: it allows 10 × 24-image page loads before rate-limiting, which is well above the expected HTMX sort traffic (1-3 sorts = 24-72 images, mostly cached).
- **Do NOT change `RateLimitBudget` structure**: the enum's dict-lookup pattern (`requests()` / `period()` / `budget_seconds()` properties via `RateLimitSettings`) remains unchanged; only the dictionary value is updated.

### Risk Assessment
- **Rate-limiting is permissive**: 240 req / 60s = 4 req/s. A single bot client would need to fetch 240 thumbnails in 60s to trigger the limit — this is aggressive scraping behavior, not legitimate browsing. The existing `limit_req zone=browse_limit burst=40 nodelay` in nginx (`nginx.conf:107`) provides complementary protection at the nginx layer.
- **Memory/cache pressure**: `cache.py:60-90` (`bump_rate_limit_window`) uses a single Redis key with TTL per IP per budget. Raising the budget value increases the key's TTL ceiling but does not change the storage pattern (one key per active IP). Negligible memory impact.

### Test Strategy
Update tests that assert the reviewed budget values:

| File:Line | Test | Current assertion | New assertion |
|---|---|---|---|
| `tests/test_rate_limit_budget.py:76` | `test_budgets_are_the_reviewed_values` | `requests == 60` for MEDIA_GATE | `requests == 240` |
| `tests/test_rate_limit_budget.py:82` | `test_budgets_are_the_reviewed_values` | `requests == 60` for MEDIA_GATE | `requests == 240` |
| `tests/test_media_security.py:994-996` | `TestMediaGateApplicationRateLimit.test_period_constant_is_the_documented_window` | `budget == 60` | `budget == 240` |

Add a new test:
- `test_media_gate_budget_allows_ten_page_loads` — asserts 240 requests within the 60s window are allowed (10 × PER_PAGE=24).

### Verification
- Run: `.\Makefile.ps1 test` (or `$dc run --rm -e PYTEST_OPTS="src/backend/apps/ads/tests/test_rate_limit_budget.py src/backend/apps/ads/tests/test_media_security.py" test`)
- Assert: all budget-related tests pass with 240.

---

## 4. Work Block C — RFC-compliant 429 with graceful degradation

### Goal
When the rate-limit budget IS exceeded, return a proper 429 response with:
1. A `Retry-After` header (RFC 9110 §15.4.5 — currently absent).
2. A minimal SVG placeholder body (instead of empty body) so `<img>` tags render a visible fallback.
3. `Cache-Control: no-store` on the 429 response (so browsers don't cache the error).

### Targets

#### 4.1 — `rate_limited_response` function (shared helper)
| File | Symbol / Region | Change |
|---|---|---|
| `apps/core/utils/rate_limit_response.py:27` | `rate_limited_response` function signature | Add `retry_after: int | None = None` and `body: str | None = None` parameters (defaults preserve existing behavior for all 19 callers) |
| `apps/core/utils/rate_limit_response.py:49` | HTML branch (JSONResponse with status 429) | Add `Retry-After` header if `retry_after` is provided; set `<Retry-After>` value from param |
| `apps/core/utils/rate_limit_response.py:53` | JSON branch (HttpResponse with status 429) | Same `Retry-After` header logic for JSON 429 responses |
| `apps/core/utils/rate_limit_response.py` (new constant) | module-level | `RETRY_AFTER_HEADER = "Retry-After"` as `Final[str]` |

**Backward compatibility**: All 19 existing callers call `rate_limited_response(json=False)` or `rate_limited_response()` without `retry_after` or `body`. Since both new params default to `None`, existing callers get identical behavior (no `Retry-After` header, no body) — except:
- The HTML branch gains `Cache-Control: no-store` unconditionally (see 4.2).

#### 4.2 — `Cache-Control: no-store` on 429 responses
This directive belongs in Block C (429 handling) for implementation independence from Block A (200-path caching). Setting `no-store` on 429 ensures browsers never cache a rate-limit error — if a user is rate-limited, a subsequent request after the window should re-check, not reuse a cached 429.

| File | Symbol / Region | Change |
|---|---|---|
| `apps/core/utils/rate_limit_response.py` (HTML branch) | `rate_limited_response` function | Add `response["Cache-Control"] = "no-store"` |
| `apps/core/utils/rate_limit_response.py` (JSON branch) | `rate_limited_response` function | Add `response["Cache-Control"] = "no-store"` |

**Existing callers**: 6 HTML callers (`core/views.py:84`, `users/consent.py:342`, `users/consent.py:346`, `listings.py:83`, `listings.py:191`, `listings.py:271`) and 2 JSON callers (`autocomplete.py:59`, `search.py:89`). The `no-store` addition is safe for all — 429 errors should never be cached regardless of caller.

#### 4.3 — `media_gate` 429 call site
| File | Symbol / Region | Change |
|---|---|---|
| `apps/ads/views/listings.py:191` | `media_gate` 429 return | Change from `return rate_limited_response(json=False)` to pass `retry_after=MEDIA_RATE_LIMIT_PERIOD` and `body=_MEDIA_GATE_429_SVG` |

**New module constant** in `listings.py:64` (adjacent to the existing `_MEDIA_RATE_LIMIT_KEY_PATTERN`):

```python
# SVG placeholder for rate-limited media requests. Renders a 240×180 gray
# rectangle matching the thumbnail fallback state in ad_list.html. No text
# content (avoids i18n extraction concerns); the <img> alt attribute provides
# the semantic label.
_MEDIA_GATE_429_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="240" height="180" '
    'viewBox="0 0 240 180" role="img" aria-label="Image unavailable">'
    '<rect width="240" height="180" rx="8" fill="#e5e7eb"/></svg>'
)
```

This SVG:
- Matches the `<img>` dimensions in `ad_list.html:134` (`width="240" height="180"`).
- Uses `bg-gray-200` equivalent (`#e5e7eb`) matching `ad_list.html:139` fallback color.
- Uses `rx="8"` (rounded corners) matching `rounded-t-lg` in the template.
- Contains no user-visible text → no i18n extraction needed.
- Is ~150 bytes — negligible bandwidth.

### Design Decisions
- **Retry-After value**: Use `MEDIA_RATE_LIMIT_PERIOD` (which resolves to 60, the period in seconds). This follows the precedent of `db_lock_timeout.py:36,68` which uses `_RETRY_AFTER_SECONDS = 30` for its 503 responses. The Implementor should derive this from the same constant to avoid drift.
- **SVG as `body` param (not hardcoded)**: The `body` parameter is generic — any caller can pass an HTML or SVG body. `media_gate` passes the SVG; other callers (privacy page, login form, etc.) leave it as `None` (empty body, backward-compatible).
- **SVG content-type**: The `Content-Type` header must be set to `image/svg+xml` when serving the SVG body. This is set at the call site (`media_gate` line 191) on the response object, OR — better — the `body` parameter implicitly sets the content type when it detects SVG content. The Implementor should decide: simplest is to set `response.content_type = "image/svg+xml"` at the `media_gate` call site before returning.

### Risk Assessment
- **Shared function change**: `rate_limited_response` is called from 8 locations across 5 files. Adding two optional params with `None` defaults is backward-compatible. The `no-store` Cache-Control addition on all 429 responses is safe — caching an error response is never desirable.
- **429 callers in non-media contexts**: The 5 non-media 429 callers (`core/views.py:84` privacy, `users/consent.py:342,346` login, `autocomplete.py:59`, `search.py:89`) get `no-store` on their 429 responses but no `Retry-After` (param defaults to `None`). This is acceptable — those callers can adopt `retry_after` later if needed; the param is available.
- **SVG accessibility**: `<img>` alt text from `ad_list.html:132` (`alt="{{ ad|get_title:LANGUAGE_CODE }}"`) provides the semantic label; the SVG's `aria-label="Image unavailable"` is a fallback for screen readers.

### Test Strategy
Update in `test_media_security.py`:

| File:Line | Test | Change |
|---|---|---|
| `tests/test_media_security.py` (new test in `TestMediaGateApplicationRateLimit`) | `test_429_has_retry_after_header` | Assert `Retry-After` header is set on 429 responses from `media_gate` |
| `tests/test_media_security.py` (new test) | `test_429_returns_svg_placeholder` | Assert 429 body contains `<svg` and `Content-Type` is `image/svg+xml` |
| `tests/test_media_security.py` (new test) | `test_429_has_no_store_cache_control` | Assert `Cache-Control` is `no-store` on 429 responses |
| `tests/test_media_security.py:923-938` | `TestMediaGateApplicationRateLimit` burst tests | Update if they assert response body is empty (now SVG) |
| `tests/test_media_security.py:122-128` | `TestOneResponseShape.test_rate_limited_response` | Update if asserting empty body or missing headers |
| `tests/test_media_security.py:718-852` | `TestMediaGateCacheControl` | No changes needed (tests 200 responses; 429 path is separate) |

Also update in `test_rate_limit_budget.py`:
| File:Line | Test | Change |
|---|---|---|
| `tests/test_rate_limit_budget.py:122` | `TestOneResponseShape.test_rate_limited_json_body` | Assert `Cache-Control` is `no-store` on 429 responses |

Add new cross-cutting test:
- `test_rate_limited_response_preserves_backward_compatibility` — assert that callers passing no new params get the same response as before (no `Retry-After` header, empty body) — except for the new `no-store` Cache-Control which is an intentional improvement for all 429 responses.

### Verification
- Run: `.\Makefile.ps1 test` (or `$dc run --rm -e PYTEST_OPTS="src/backend/apps/ads/tests/test_media_security.py src/backend/apps/core/tests/test_rate_limit_budget.py src/backend/apps/core/tests/test_rate_limit_response.py" test`)
- Assert: all 429-response tests pass; `Retry-After` header present on media_gate 429; SVG body has correct content-type; `no-store` on all 429s.

---

## 5. Implementation Sequence

| Step | Block | Commit boundary | Depends on |
|---|---|---|---|
| 1 | C | `chore: 429 responses carry Retry-After + no-store Cache-Control` | none |
| 2 | C | `feat(media_gate): return SVG placeholder on 429 rate-limit` | Step 1 (same block) |
| 3 | A | `feat(media): enable safe max-age=86400 caching on image responses` | Step 2 (avoids 429-path code conflict) |
| 4 | B | `chore: raise MEDIA_GATE budget to 240/60s` | none (independent) |

**Rationale for C→A ordering**: Blocks C and A both modify `media_gate` (lines 186-191 for 429, lines 226-254 for 200). Implementing C first (429 path) then A (200 paths) avoids merge conflicts in the same function. Block B is a one-line enum change, fully independent.

**Commits must be atomic**: each block = one commit, each passing the fast test gate (`.\Makefile.ps1 test`).

---

## 6. Per-Block Task Specifications

### Task C-1: Add Retry-After and no-store to rate_limited_response
**File**: `apps/core/utils/rate_limit_response.py`
**Actions**:
- Add module constant `RETRY_AFTER_HEADER = "Retry-After"` (Final[str])
- Add parameters `retry_after: int | None = None` and `body: str | None = None` to `rate_limited_response` signature (line 27)
- In HTML branch (line 49): set `response["Cache-Control"] = "no-store"` unconditionally; if `retry_after` is not None, set `response["Retry-After"] = str(retry_after)`; if `body` is not None, set `response.content = body`
- In JSON branch (line 53): set `response["Cache-Control"] = "no-store"` unconditionally; if `retry_after` is not None, set `response["Retry-After"] = str(retry_after)`
**Verification**: `test_rate_limit_response.py` or inline test — 429 response has `no-store`, `Retry-After` when param provided, backward-compatible when params omitted
**blocked_by**: none

### Task C-2: media_gate passes SVG placeholder + retry_after on 429
**File**: `apps/ads/views/listings.py`
**Actions**:
- Add module constant `_MEDIA_GATE_429_SVG` (Final[str]) near line 64
- Change line 191: `return rate_limited_response(json=False)` → build response, pass `retry_after=MEDIA_RATE_LIMIT_PERIOD` and `body=_MEDIA_GATE_429_SVG`, set `Content-Type` to `image/svg+xml`
**Verification**: `test_media_security.py` — 429 from media_gate returns SVG with correct content-type and Retry-After
**blocked_by**: C-1

### Task A: Enable max-age=86400 caching on 200 media responses
**File**: `apps/ads/views/listings.py`
**Actions**:
- Line 226: `"no-cache"` → `"public, max-age=86400"`
- Line 230: `"no-cache"` → `"public, max-age=86400"`
- Line 249: `"no-store"` → `"public, max-age=86400"`
- Line 254: `"no-store"` → `"public, max-age=86400"`
- Add a module constant `_MEDIA_CACHE_CONTROL_200 = "public, max-age=86400"` (Final[str]) at line 64, use it in all 4 places
**Verification**: `test_media_security.py::TestMediaGateCacheControl` — 200 responses assert `max-age=86400`, no `immutable`
**blocked_by**: C-2 (same function; avoid conflict)

### Task B: Raise MEDIA_GATE budget to 240/60s
**File**: `apps/core/enums.py`
**Actions**:
- Line 63: change budget dictionary value from `60` to `240`
- Lines 45-46: update docstring comment
**Verification**: `test_rate_limit_budget.py`, `test_media_security.py::TestMediaGateApplicationRateLimit` — assert budget is 240
**blocked_by**: none

---

## 7. Acceptance Criteria

| # | Criterion | Block | Test |
|---|---|---|---|
| A1 | 200 responses from media_gate have `Cache-Control: public, max-age=86400` (no `immutable`) | A | `test_media_security.py::TestMediaGateCacheControl` |
| B1 | MEDIA_GATE budget is 240 requests / 60s | B | `test_rate_limit_budget.py`, `test_media_security.py::TestMediaGateApplicationRateLimit` |
| C1 | 429 responses carry `Retry-After` header (media_gate: 60s) | C | `test_media_security.py` (new) |
| C2 | 429 responses from media_gate return SVG placeholder with `Content-Type: image/svg+xml` | C | `test_media_security.py` (new) |
| C3 | All 429 responses have `Cache-Control: no-store` | C | `test_media_security.py`, `test_rate_limit_budget.py` |
| C4 | `rate_limited_response` is backward-compatible (existing callers unaffected) | C | `test_rate_limited_response.py` (new) |

---

## 8. Rollout & Compatibility

### Backward compatibility
- Block A: Cache-Control change only affects browser caching behavior. No API contract change. The `public` directive is safe for anonymous media.
- Block B: Budget increase is strictly more permissive. No breaking change.
- Block C: New parameters default to `None`. `no-store` on all 429s is strictly an improvement (prevents error caching). No caller is broken.

### nginx considerations
`nginx.conf:107` (`location /media/`) does NOT add its own `Cache-Control` — it proxies to Django. Django's response headers pass through. No nginx config change required. The `limit_req zone=browse_limit burst=40 nodelay` at `nginx.conf:107` provides complementary nginx-level rate limiting (20r/s + burst 40) that protects Django from flood traffic; the `MEDIA_GATE` budget protects against sustained per-IP abuse.

### Data / schema migrations
None required. No model or schema changes.

### i18n
The SVG placeholder (`_MEDIA_GATE_429_SVG`) contains no translatable text (no gettext calls, no Django template tags). The i18n completeness gate (`test_i18n_completeness.py`) scans templates and Telegram bot source only — Python constants under `apps/` are not extracted. No `.po` update needed. The `aria-label="Image unavailable"` is a fixed English string acceptable for a fallback SVG (matching the existing `{% trans "No image" %}` pattern at `ad_list.html:139`).

### Seeds / fixtures
No seed changes required. Seed images (`seed/{filename}.jpg`) serve through `media_gate` and will benefit from the `max-age=86400` caching like all images.

---

## 9. Verification Commands

```powershell
# Fast test gate (all affected test files)
$dc run --rm test  # uses defaults: PYTEST_OPTS overrides applied per-file below

# Block A tests
$dc.run --rm -e PYTEST_OPTS="src/backend/apps/ads/tests/test_media_security.py::TestMediaGateCacheControl" test

# Block B tests
$dc.run --rm -e PYTEST_OPTS="src/backend/apps/core/tests/test_rate_limit_budget.py src/backend/apps/ads/tests/test_media_security.py::TestMediaGateApplicationRateLimit" test

# Block C tests
$dc.run --rm -e PYTEST_OPTS="src/backend/apps/ads/tests/test_media_security.py src/backend/apps/core/tests/test_rate_limit_response.py" test

# Full i18n gate (must pass after any string changes — SVG has no strings, so expected to pass unchanged)
$dc.run --rm -e PYTEST_OPTS="src/backend/apps/core/tests/test_i18n_completeness.py" test
```

### Prerequisites
- Test DB running: `docker compose --project-name mko-bazuna-test up -d db`
- Use `mko-bazuna-test` project name (NOT `mko-bazuna-dev`)
- `.env.test` file must exist (copy `.env.test.example`)

---

## 10. Out of Scope

- Adding ETag / Last-Modified headers (UUID-based keys already provide uniqueness; ETag would add complexity without solving the core issue).
- Per-user cache invalidation (no login on the buyer side; anonymous browsing only).
- CDN-level caching configuration (nginx passes headers through; no config change needed).
- Localizing the SVG `aria-label` (fixed English fallback; the `<img>` alt text provides the primary label).
- Changing the `rate_limited_response` callers to use `retry_after` (other than media_gate) — out of scope for P-003; available as a future improvement via the new parameter.
