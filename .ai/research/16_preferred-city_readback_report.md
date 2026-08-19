# Research Report — Preferred-City Cookie Read-Back

**Research task ID:** `ses_fe70eab92ffeDsgqQMfJ5z9gO1`
**Spec:** `.ai/problems/16_preferred-city_spec.md`
**Decision gate:** Decision_018 (cookie-only preferred-city persistence)
**Date:** 2026-08-19

## 1. Architecture Findings (Facts with file/line references)

### 1.1 Write side is implemented but isolated

**`src/backend/apps/search/views/preferred_city.py`** — POST endpoint at `/api/preferred-city/` (registered `search/urls.py:15`, `name="preferred_city"`):
- Reads `slug` from `request.POST` (line 40); validates via `City.objects.filter(slug=slug).exists()` (line 41).
- Sets the `preferred_city` cookie with: `max_age = 30 days` (`PREFERRED_CITY_COOKIE_MAX_AGE`, line 21), `httponly=True` (line 49), `samesite="Lax"` (line 50), `secure=request.is_secure()` (line 51).
- Returns `JsonResponse({"ok": True})` on success, `{"error": "invalid_city"}` / 400 on failure.
- **The cookie name is a bare string** `"preferred_city"` (line 46) — no module-level constant, unlike `LANGUAGE_COOKIE_NAME` (language.py:34) or `CONSENT_COOKIE_NAME` (consent.py:44).

**`src/backend/apps/search/tests/test_preferred_city.py`** — 4 tests (all marked `pytestmark = [pytest.mark.django_db, pytest.mark.slow, pytest.mark.integration]`):
- `test_post_with_valid_slug_sets_cookie` (line 31) — asserts cookie is set with correct value.
- `test_post_with_unknown_slug_returns_400` (line 38).
- `test_post_with_missing_slug_returns_400` (line 43).
- `test_get_returns_405` (line 48).

### 1.2 Search view — current city filter contract

**`src/backend/apps/search/views/search.py`** — function `search()` (lines 31–185):
- **Line 70:** `current_city = request.GET.get("city")` — reads from query string only.
- **Lines 72–77:** If `current_city` is truthy, resolves `City.objects.get(slug=current_city)` (line 74) and filters `ads = ads.filter(city_id=city.id)` (line 75). On `City.DoesNotExist`, sets `suggested_city = current_city` (did-you-mean sentinel, line 77).
- **Lines 95–100:** Separately resolves `selected_city_id` for save-search modal prefill — same `current_city` variable, so it would automatically pick up a cookie-fallback value.
- **Lines 161–179:** Context dict passes `current_city` (string slug or None), `suggested_city` (string or None), `cities` (line 175: `City.objects.order_by("name")`), and `selected_city` (int or None).
- **No cookie read anywhere** — `request.COOKIES` is never accessed in this file.

### 1.3 Listings view — current city filter contract

**`src/backend/apps/ads/views/listings.py`** — function `listings()` (lines 186–444):
- **Line 192:** `city_slug: str | None = None` — city comes from the URL path parameter (`/city/<slug>/`, registered at `ads/urls.py:27`).
- **Lines 304–316:** If `city_slug` is truthy, resolves `City.objects.get(slug=city_slug)` (line 308), filters `ads = ads.filter(city_id=city.id)` (line 310). On `City.DoesNotExist`, sets `suggested_city = _suggest_city(city_slug)` (line 316, difflib-based).
- **Lines 320–322:** If no path slug but `?city=` GET param present, only does did-you-mean: `suggested_city = _suggest_city(request.GET.get("city", ""))`. This does **not** apply a filter — it only suggests.
- **Context (line 420):** `"current_city": city_slug` — set to the path parameter, not the GET param.
- **No cookie read anywhere.**

### 1.4 The only existing cookie-reading pattern in the codebase

**`src/backend/apps/core/middleware/language.py`** — `LanguagePreMiddleware(MiddlewareMixin)`:
- **Line 34:** Module-level constant `LANGUAGE_COOKIE_NAME = "lang_pref"` (not in `enums.py`).
- **Line 64:** Reads the cookie: `lang = request.COOKIES.get(LANGUAGE_COOKIE_NAME)`.
- **Lines 60–74:** Priority resolution: `?lang=X` query parameter > cookie > `Accept-Language` header > default `ru`.
- **Line 129:** Validates + activates: `translation.activate(lang)` + `request.LANGUAGE_CODE = translation.get_language()` — enriches the request object for views/templates to consume.
- **Validation (line 146–148):** `_is_valid_language` checks `lang in LanguageLocale.values()`.
- **`process_response` (lines 76–94):** Writes cookie only when `?lang=` param was present (`request._lang_cookie_value`).

**This is the single precedent for cookie read-back in the entire codebase.** A grep for `request.COOKIES` across `src/` returns exactly two hits: the language middleware (line 64, production) and the test that mocks it (test_language_middleware.py:35).

**The consent cookie follows a different, non-applicable pattern:**
**`src/backend/apps/users/views/consent.py`** — `CONSENT_COOKIE_NAME = "consent_given"` (line 44). The `is_consent_given()` function (line 138) does **NOT** read the cookie — it checks `User` model fields (`consent_given_at`, `ads_auto_publish`) directly. The cookie is write-only (set on accept/decline/withdraw, never read). So there is no cookie-read-back precedent in the consent flow.

### 1.5 Middleware registration and request-enrichment precedent

**`src/backend/config/settings/base.py`** — lines 112–122:
```python
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",                           # 112
    "whitenoise.middleware.WhiteNoiseMiddleware",                               # 113
    "django.contrib.sessions.middleware.SessionMiddleware",                     # 115
    "django.middleware.common.CommonMiddleware",                                # 116
    "django.middleware.csrf.CsrfViewMiddleware",                              # 117
    "django.contrib.auth.middleware.AuthenticationMiddleware",                  # 118
    "apps.core.middleware.language.LanguagePreMiddleware",                    # 119  ← cookie-read precedent
    "django.contrib.messages.middleware.MessageMiddleware",                      # 120
    "django.middleware.clickjacking.XFrameOptionsMiddleware",                  # 121
]
```
- `LanguagePreMiddleware` runs at position 7 (after Auth, before Messages).
- **Request-enrichment precedent exists:** the language middleware sets `request.LANGUAGE_CODE` (line 129) as a custom attribute consumed by views (`search.py:113`) and template context processors (`context_processors.py:21`). This is the exact pattern to follow.

### 1.6 City model and stale-cookie semantics

**`src/backend/apps/locations/models.py`** — class `City` (lines 11–57):
- **`slug = models.SlugField(unique=True)`** (lines 36–39) — unique constraint, therefore DB-indexed. Lookup by slug is O(log n).
- No `is_active` field — cities are not soft-deleted; removal = physical DELETE from the `cities` table (`db_table = "cities"`, line 42).
- `get_name(locale)` method (line 45) resolves i18n names with fallback chain.
- **Stale-cookie meaning:** a cookie holding a slug for a city that has been deleted will cause `City.objects.get(slug=cookie_value)` to raise `DoesNotExist`. Both `search()` (line 76) and `listings()` (line 312) already have `except City.DoesNotExist` branches that degrade gracefully (did-you-mean / suggestion sentinel). **The stale-cookie case is already handled by existing exception handlers** — no additional logic needed beyond routing the cookie value through the same code path.

### 1.7 Enum / constant patterns

**`src/backend/apps/core/enums.py`**:
- `SearchSuggestionSource` StrEnum (lines 174–180) with `CITY = "city"` — **not** used for the cookie name.
- No `preferred_city` constant exists anywhere. The cookie name `"preferred_city"` is a bare string literal at `preferred_city.py:46`, `preferred_city.py:53`, and `test_preferred_city.py:36`.
- `LanguageLocale` (lines 183–233) follows the StrEnum pattern.
- `LanguagePreMiddleware` keeps its cookie name as a module-level constant (`LANGUAGE_COOKIE_NAME`, line 34), not in enums. Following this precedent, the read-back constant should live at module level in the same or a shared module — **not** as a StrEnum (cookie names are not domain-fixed-value sets in the project's convention).

### 1.8 Client-side click handler (write triggers + navigation)

**`src/backend/templates/components/header_catalog.html`** — lines 235–240:
```javascript
if (type === 'city' && slug) {
    // Persist preferred city (cookie) then filter by navigating to the city listing.
    var fd = new FormData();
    fd.append('slug', slug);
    fetch('{% url "search:preferred_city" %}', { method: 'POST', body: fd, headers: { 'X-CSRFToken': getCsrf() } });
    window.location.href = '/city/' + encodeURIComponent(slug) + '/';
}
```
- **Race condition:** The `fetch()` is fire-and-forget (not awaited). `window.location.href` executes immediately on the next line. The POST response sets the cookie via `Set-Cookie`, but the browser may not have stored it before the navigation request fires. Since the cookie is `HttpOnly=True`, client-side JS cannot verify its presence or delay navigation. This is a **frontend concern** (the fetch should be `await`-ed before navigation), but it directly impacts read-back reliability: the very first landing on `/city/<slug>/` after a click may not have the cookie yet.

### 1.9 What the write side does NOT do

- **No `process_response`** cookie clearing on invalid slugs — the view only sets the cookie; it never clears an existing stale one.
- **No read-back** — after the POST, the view returns `JsonResponse({"ok": True})` without reading back or validating any existing cookie.
- **No middleware or context processor** references the `preferred_city` cookie.

---

## 2. How the Cookie Would Be Consumed

### 2.1 Where the cookie should be read

**Decision: Middleware** (mirroring `LanguagePreMiddleware`). Rationale:

1. **Precedent:** `LanguagePreMiddleware` is the only cookie-reading pattern in the codebase (language.py:64). It reads `lang_pref` cookie in `process_request` and enriches the request with `request.LANGUAGE_CODE`. The same pattern applies identically to `preferred_city`.
2. **Both views need it:** `search()` reads `?city=` from query params; `listings()` reads `city_slug` from the URL path. Both need the same default fallback. A middleware enriches `request` once, and both views consume `getattr(request, "preferred_city", None)`.
3. **Separation of concerns:** Cookie reading + validation is request enrichment (middleware's job), not view logic. Views decide whether to apply the filter.
4. **Stale-cookie handling in one place:** The middleware validates the slug against `City` and sets `request.preferred_city` to a valid slug or `None`. Views never see an invalid slug, so the existing `except City.DoesNotExist` branches remain untouched.

### 2.2 Exact code change in `search()` (search.py)

The city filter block at **lines 69–77** currently reads:
```python
current_city = request.GET.get("city")
suggested_city = None
if current_city:
    try:
        city = City.objects.get(slug=current_city)
        ads = ads.filter(city_id=city.id)
    except City.DoesNotExist:
        suggested_city = current_city
```

The **exact change** — add the cookie fallback when no explicit `?city=` is given:
```python
# City filter (by slug) — defaults to preferred_city cookie when
# no explicit ?city= param is given (R-01d, Decision 018).
current_city = request.GET.get("city")
if not current_city:
    current_city = getattr(request, "preferred_city", None)
suggested_city = None
if current_city:
    try:
        city = City.objects.get(slug=current_city)
        ads = ads.filter(city_id=city.id)
    except City.DoesNotExist:
        suggested_city = current_city
```

No other changes needed in `search()`: lines 95–100 (the `selected_city_id` resolution) already reference `current_city`, so it will correctly resolve the cookie-fallback value for the save-search modal prefill. The context dict (lines 161–179) already passes `current_city`.

### 2.3 Exact code change in `listings()` (listings.py)

The city filter block at **lines 300–323** currently reads:
```python
suggested_city = None
if city_slug:
    try:
        city = City.objects.get(slug=city_slug)
        ads = ads.filter(city_id=city.id)
    except City.DoesNotExist:
        suggested_city = _suggest_city(city_slug)
elif request.GET.get("city"):
    suggested_city = _suggest_city(request.GET.get("city", ""))
```

The **exact change** — add a third `else` branch for the cookie fallback:
```python
suggested_city = None
if city_slug:
    try:
        city = City.objects.get(slug=city_slug)
        ads = ads.filter(city_id=city.id)
    except City.DoesNotExist:
        suggested_city = _suggest_city(city_slug)
elif request.GET.get("city"):
    suggested_city = _suggest_city(request.GET.get("city", ""))
else:
    # Fall back to preferred_city cookie (R-01d, Decision 018).
    # Stale cookies (deleted city) silently resolve to None — no filter applied.
    preferred = getattr(request, "preferred_city", None)
    if preferred:
        try:
            city = City.objects.get(slug=preferred)
            ads = ads.filter(city_id=city.id)
            city_slug = preferred  # so current_city in context reflects the active filter
        except City.DoesNotExist:
            pass  # stale cookie — ignore
```

The `city_slug = preferred` assignment on the success path ensures the context `"current_city": city_slug` (line 420) reflects the actual active city, so the UI breadcrumb/filter display shows the cookie-persisted city.

### 2.4 Stale cookie handling

**Already handled by the middleware validation** (if following the recommended middleware approach):
- The middleware validates the cookie slug against `City.objects.filter(slug=...).exists()`.
- If the slug is stale (city deleted), the middleware sets `request.preferred_city = None`.
- Views see `None` and skip the city filter entirely — identical to the current "no city selected" behavior.
- **No DB query fires in the view** for a stale cookie — the validation happened once in middleware (cacheable).

### 2.5 Priority order

Following the `LanguagePreMiddleware` precedent (`?lang=X` > cookie > `Accept-Language` > default`):
1. **Explicit URL param wins** — `?city=` in `search()` / `city_slug` path in `listings()`.
2. **Cookie is the fallback** — only consulted when no explicit param is present.
3. **Stale cookie → no filter** — transparent degradation, no error to the user.

---

## 3. Modern Best Practices Summary

### 3.1 Classifieds city-persistence patterns

| Platform | City-persistence pattern | Source |
|----------|--------------------------|--------|
| **Avito** | Location embedded in URL path (`/fr/maroc/...`); region context in URL for SEO. No explicit "remember my city" cookie documented. | `docs/07-design-researches/Design_02/01-avito-design.md` §6, §10 |
| **OLX** | Geolocation auto-fill for current city; "nearby" locations based on coordinates. No persistent city cookie documented. | `docs/07-design-researches/Design_02/02-jiji-olx-design.md` §4.1, §4.3 |
| **Jiji** | Location-first design; city selector prominently placed in onboarding. | `docs/07-design-researches/Design_02/02-jiji-olx-design.md` §1.3 (location-first) |
| **eBay** | Location-aware but session-scoped. | `docs/07-design-researches/Design_01/02-search-filters.md` §4.1 |

**Key finding:** No major classifieds platform documents a persistent city cookie as a best practice. Avito uses URL-embedded location; OLX uses geolocation. The **cookie-based persistence** chosen by Decision_018 is a **project-specific decision**, not an industry standard. It is a reasonable MVP approach for anonymous users (no server-side session needed), but it is **less robust than URL-based city state** because it creates the race condition documented in §1.8 and requires server-side read-back to be effective.

### 3.2 Middleware vs. inline for default filter resolution

| Criterion | Middleware (recommended) | Inline (per-view) |
|-----------|--------------------------|-------------------|
| Precedent in codebase | ✓ `LanguagePreMiddleware` reads cookie, enriches request | ✗ No precedent for inline cookie reads |
| DRY | ✓ One read-validate path | ✗ Duplicated in 2 views |
| Stale-cookie handling | ✓ Centralized in middleware | ✗ Must be repeated per view |
| Testability | ✓ Test like `test_language_middleware.py` (SimpleTestCase) | Requires full request + DB mock per view |
| Separation of concerns | ✓ Cookie reading = request enrichment | ✗ Mixes persistence logic into view logic |

### 3.3 Cookie security: HttpOnly impact

The current cookie uses `httponly=True` (preferred_city.py:49). **This prevents any client-side read** — the cookie cannot be inspected by JavaScript.

- **No needed client-side behavior depends on reading the cookie.** The existing client-side code in `header_catalog.html` (lines 235–240) only *writes* the cookie via a POST. It never reads `preferred_city` from `document.cookie`.
- **The read-back is inherently server-side.** Since the cookie is HttpOnly, filtering must happen in the Django views/middleware, not in client-side JS. This is consistent with the server-rendered HTMX MPA architecture.
- **No change needed to the HttpOnly flag.** Keeping it True is correct for security. The only trade-off is that client-side JS cannot pre-filter before a server round-trip — but that is the entire point of the server-rendered MPA architecture.
- **Edge case:** The fire-and-forget `fetch()` race (§1.8) means the cookie may not be set when the user lands on the `/city/<slug>/` page. Since the URL path itself carries the slug, the `listings()` view filters correctly via the path param regardless of cookie presence. The cookie only matters for subsequent navigations that omit the city from the URL.

---

## 4. Implementation Approaches (Top 3)

### Approach A: Middleware — request enrichment (RECOMMENDED)

**Description:** Create `apps/core/middleware/preferred_city.py` with a `PreferredCityMiddleware(MiddlewareMixin)` that, in `process_request`, reads `request.COOKIES.get(PREFERRED_CITY_COOKIE_NAME)`, validates the slug against `City` (cache-backed lookup), and sets `request.preferred_city = <valid_slug_or_None>`. Both `search()` and `listings()` then read `getattr(request, "preferred_city", None)`.

**Files that change:**
1. `src/backend/apps/core/middleware/preferred_city.py` (NEW) — middleware class + `PREFERRED_CITY_COOKIE_NAME` constant
2. `src/backend/config/settings/base.py` (line 119) — add `"apps.core.middleware.preferred_city.PreferredCityMiddleware"` to `MIDDLEWARE` list
3. `src/backend/apps/search/views/search.py` (line 70) — add cookie fallback
4. `src/backend/apps/ads/views/listings.py` (lines 300–322) — add `else` branch with cookie fallback
5. `src/backend/apps/search/views/preferred_city.py` (line 46) — refactor bare string to import shared constant
6. `src/backend/apps/core/tests/test_preferred_city_middleware.py` (NEW) — middleware tests

**Pros:** Precedent (LanguagePreMiddleware); DRY; centralized stale handling; testable; both views benefit.

**Cons:** DB lookup per request (cacheable); adds middleware to stack.

**Risk: MEDIUM** — additive change, but the refactor of `preferred_city.py` to use a shared constant could break existing tests if the import path is wrong.

### Approach B: Service function called in each view

**Description:** Create `apps/search/services/preferred_city.py` with `get_preferred_city(request) -> str | None`. Call it in both views.

**Files:** service module + 2 view files + tests.

**Pros:** No middleware registration; explicit call sites.

**Cons:** No cookie-reading service precedent; duplicated call sites; no request enrichment for other consumers.

**Risk: MEDIUM-LOW**

### Approach C: Inline cookie read in each view (no abstraction)

**Description:** Read `request.COOKIES.get("preferred_city")` directly in both views with inline validation.

**Files:** 2 view files only.

**Pros:** Minimal change.

**Cons:** Bare string duplicated (violates rule #10); no precedent; harder to test; no stale-cookie centralization.

**Risk: HIGH** — violates multiple project rules.

---

## 5. Recommended Approach + Rationale

**Recommendation: Approach A (Middleware)**

1. **Mirrors the sole existing pattern** (`LanguagePreMiddleware`, language.py:34–148).
2. **Request enrichment precedent** — `request.LANGUAGE_CODE` → consumed by `search.py:113`. Same approach: `request.preferred_city` → consumed by `search.py:70` and `listings.py:322`.
3. **Central stale-cookie handling** — validation once in middleware; views never see invalid slugs.
4. **Testable** — `test_language_middleware.py` demonstrates `SimpleTestCase` pattern with `request.COOKIES` mock.

---

## 6. Risks & Edge Cases

### 6.1 Fire-and-forget fetch race condition (frontend)

**File:** `header_catalog.html:239`

The city click handler calls `fetch(...)` without `await`, then immediately sets `window.location.href`. Since the cookie is `HttpOnly`, client-side JS cannot verify cookie presence. **Impact:** First landing on `/city/<slug>/` may not have the cookie. The URL path carries the slug, so filtering still works. **Mitigation (out of scope):** JS should `await` the fetch.

### 6.2 Cache invalidation for city deletion

If a city is deleted, cached middleware results for that slug become stale. The `lookup_resolution.py` cache invalidation pattern (signal-based `cache.delete_pattern()` on `post_save`/`post_delete`) provides a precedent. A `post_delete` signal on `City` should invalidate any cache for the deleted slug. Without this, a stale cookie continues to return a cached result until TTL expiry — though the view's `except City.DoesNotExist` catches it as a second line of defense.

### 6.3 Cookie max-age constant duplication

`PREFERRED_CITY_COOKIE_MAX_AGE` (preferred_city.py:21) is defined only in the write-side view and is not imported by any other module. If the middleware consolidates constants, this should be shared. `LANGUAGE_COOKIE_MAX_AGE` lives in language.py:35 and is imported by its test.

### 6.4 No cookie clearing on invalid city

The write endpoint never clears a stale cookie. If a city is deleted, the stale cookie persists for its remaining TTL (30 days). The middleware handles this by validating on read, but a cleaner approach would be for `process_response` to delete the stale cookie when it detects an invalid slug.

### 6.5 `secure=request.is_secure()` and test environment

The write endpoint sets `secure=request.is_secure()` (preferred_city.py:51). In test/dev, `SECURE_SSL_REDIRECT = False` and `SECURE_PROXY_SSL_HEADER` is configured for prod only (base.py:72). So `request.is_secure()` returns `False` in test/dev, and the cookie is set without the `Secure` flag. The middleware read-back doesn't need to consider this.

### 6.6 No `current_city` in `listings()` context when defaulting from cookie

The `listings()` view sets `"current_city": city_slug` (line 420) from the URL path param. When the cookie fallback fires in the `else` branch, `city_slug` is the path parameter (None when falling back). The exact code change includes `city_slug = preferred` on the success path so the context reflects the active city.

### 6.7 No `cities` context in `listings()`

The `search()` view passes `"cities": City.objects.order_by("name")` (line 175). The `listings()` view does not pass `cities` (lines 408–432). The current `header_catalog.html` template does not appear to have a city selector dropdown, so this may be non-blocking. This is a pre-existing condition, not a regression.
