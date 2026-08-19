---
id: 16_preferred-city
domain: spec
tags:
  - preferred-city
  - cookie
  - search
  - catalog-ui
  - plan-15
  - t-700
related:
  - technical-specification
  - search-patterns
  - 14_catalog-ui-avito_spec
  - Decision_018
  - db-schema
  - architecture-structure
---

# Spec_016 — Preferred-City Cookie Persistence & Read-Back

**Decision source:** `.ai/problems/Decision_018.md` (Approved: cookie-only MVP)
**Spec state:** IMPLEMENTATION-READY — PO Q1–Q4 resolved (all = option A, with clarification Q1 = keyword searches only)
**Date:** 2026-08-19
**Stack:** Django 5.2 LTS · Python 3.14 · HTMX 1.9.12 · PostgreSQL 18 · django-mptt
**Plan:** 15 (catalog-ui-avito) — gates/unblocks task T-700

---

## 1. Problem Statement

The catalog header (Spec_014) lets a buyer click a **city** suggestion in the autocomplete
dropdown, which should remember the choice and filter results. Spec_014 §8.3 stated the
registered-user path uses `UserProfile.preferred_city`, but no `UserProfile` model exists
in `apps/users` (the app has a single custom `User` model extending `AbstractUser` and a
`LoginToken` model; the `User` model has no `preferred_city` field).

**Decision_018** resolved this by selecting **option (c): cookie-only** — a
`preferred_city` cookie (city slug, 30-day expiry) set client-side on city-suggestion click,
working uniformly for both guests and registered buyers. Registered-user server-side profile
persistence (`User.preferred_city` FK) is deferred.

The **remaining gap**: the cookie write path is already implemented (`preferred_city.py`
view + `header_catalog.html` click handler), but the cookie is **never read back**. Spec R-01d
says "subsequent searches use the preferred city" — no view currently reads
`request.COOKIES["preferred_city"]` to apply it as a default city filter when no explicit
city is in the URL/query. This spec completes T-700 by specifying and implementing the
cookie read-back.

### Preferred City Resolution (PO-Confirmed Hybrid Model)

The PO confirmed a hybrid precedence chain (Q1–Q4, all = A). The resolution applies
to **keyword search only** (`/search/?q=`) per Q1:

```
1. Explicit city filter     (?city=<slug>  |  /city/<slug>/)     ← always wins; does NOT mutate preference
2. Authenticated user       (User.preferred_city)                ← deferred per Decision_018; field does not exist yet
3. Anonymous user           (preferred_city cookie)                ← current MVP implementation
4. No preferred city        → no city filter applied
```

> **Explicit city selection affects only the current search/browsing context and does not
> automatically change the persistent preferred city.** Opening `/search/?q=квартира&city=budva`
> temporarily filters to Budva but leaves the saved preference unchanged. The persistent
> preference is changed only by selecting a city (or "All cities") in the header/city selector,
> which overwrites or clears the cookie.

---

## 2. Scope

### In Scope

1. **Cookie read-back middleware** — read and validate the `preferred_city` cookie, enrich
   the request with a validated city slug (or `None`), mirroring the existing
   `LanguagePreMiddleware` cookie-reading pattern.
2. **`/search/` keyword-search default (Q1 = A, keyword-only)** — when a buyer visits
   `/search/?q=<query>` with no `?city=` param, the system reads the `preferred_city` cookie
   and applies it as a default city filter if the slug is valid (R-101d: "subsequent searches
   use the preferred city").
3. **Stale-cookie handling (Q4 = A)** — silently ignore and clear the cookie if the city slug
   no longer exists in the database.
4. **Cookie clearing (Q3 = A)** — selecting a city in the header/city selector overwrites the
   cookie; selecting "All cities" clears it (cookie deleted). Opening a temporary `?city=<slug>`
   URL does **not** clear or change the cookie (explicit selection is non-mutating).
5. **Explicit filter precedence (Q2 = A)** — `?city=<slug>` always overrides the cookie.
   Explicit selection does **not** mutate the persistent preference.
6. **Tests** — read-back coverage (cookie → default filter, precedence, stale handling,
   non-mutation on explicit `?city=`).
7. **No schema changes** — consistent with Decision_018 (cookie-only, no migration).
8. **Cookie name as constant (T-800)** — consolidate the bare string into a module-level
   constant following the `LANGUAGE_COOKIE_NAME` precedent.

### Out of Scope

1. **`/city/<slug>/` and root catalog `/` and category listings read-back** — per Q1, the
   preferred-city cookie is applied to **keyword search only** (`/search/?q=`). The root
   catalog and category listings ignore the cookie (so browsing "Недвижимость" shows all
   cities, not just the preferred one). T-600 (`listings()` integration) is deferred.
2. **Registered-user server-side profile persistence** (`User.preferred_city` FK) —
   explicitly deferred to a dedicated buyer-profile task (Decision_018 §5). The `User` model
   does not yet have a `preferred_city` field. The hybrid resolution model (Section 1)
   documents where this tier will slot in when implemented.
3. **Geo-IP auto-detection** — not part of MVP; no automatic city detection from IP.
4. **Session-based city storage** — US-B7 says "selected city saved in session"; the cookie
   supersedes this for the preferred-city feature (Decision_018). Session history remains
   separate (search history, not city preference).
5. **Frontend fetch race fix** — the fire-and-forget `fetch()` in `header_catalog.html:239`
   is a separate frontend concern (documented as a risk, not in this spec's scope).
6. **Frontend `await` for cookie write** — the client cannot verify HttpOnly cookie presence;
   a future fix may `await` the fetch in `header_catalog.html:239` to guarantee the cookie is
   set before navigation. Frontend change, out of scope here.
7. **`bot_username` in templates** — unrelated to this feature; already handled by context
   processor (T-200 in Spec_014).
8. **Migration workflow** — no migrations needed (cookie-only; Decision_018).

---

## 3. Facts

### 3.1 Current Implementation State

| Component | Status | Location |
|---|---|---|
| Cookie write endpoint (`POST /api/preferred-city/`) | ✅ Implemented | `apps/search/views/preferred_city.py:24-53` |
| Cookie write tests | ✅ Implemented (4 tests) | `apps/search/tests/test_preferred_city.py` |
| URL registration | ✅ Registered | `apps/search/urls.py:15` |
| City-suggestion click handler (POST + navigate) | ✅ Implemented | `templates/components/header_catalog.html:235-240` |
| `/city/<slug>/` route | ✅ Exists | `apps/ads/urls.py:27` → `listings()` |
| `?city=` filter in `search()` | ✅ Exists | `apps/search/views/search.py:70` |
| `city_slug` filter in `listings()` | ✅ Exists | `apps/ads/views/listings.py:304-316` |
| **Cookie read-back / default application** | ❌ **Missing** | No code reads `request.COOKIES["preferred_city"]` |
| **Stale-cookie handling** | ❌ Missing | |
| **Cookie clearing/reset** | ❌ Missing | |

### 3.2 Codebase Evidence

- **Cookie write** (`preferred_city.py:40-53`): Reads `slug` from `request.POST`, validates via
  `City.objects.filter(slug=slug).exists()`, sets cookie with `max_age=30 days`,
  `httponly=True`, `samesite="Lax"`, `secure=request.is_secure()`. Cookie name is a bare string
  `"preferred_city"` (line 46) — no module-level constant.
- **Cookie read — the gap**: A repository-wide grep for `request.COOKIES` returns exactly one
  production hit: `apps/core/middleware/language.py:64` (reads `lang_pref` cookie). The
  `preferred_city` cookie is never read anywhere.
- **Existing cookie-reading precedent** (`language.py:34-94`): `LanguagePreMiddleware`
  reads `lang_pref` in `process_request` via `request.COOKIES.get(LANGUAGE_COOKIE_NAME)`,
  validates against `LanguageLocale.values()`, and enriches the request with
  `request.LANGUAGE_CODE` (line 129). This is the **only** cookie-read-back pattern in the
  codebase and the direct architectural precedent.
- **Request-enrichment consumer pattern**: `request.LANGUAGE_CODE` (set by middleware) is
  consumed by `search.py:113` (`LanguageLocale.from_code(request.LANGUAGE_CODE)`). The same
  approach applies: middleware sets `request.preferred_city`, views consume it.
- **Middleware registration** (`base.py:112-122`): `LanguagePreMiddleware` is at position 7
  in the `MIDDLEWARE` list (after Auth, before Messages). New middleware should be inserted
  immediately after it.
- **City model** (`locations/models.py:36-39`): `slug = models.SlugField(unique=True)` —
  DB-indexed, O(log n) lookup. No `is_active` field — cities are hard-deleted, so a stale
  cookie refers to a row that no longer exists.
- **Stale-cookie handling in views**: Both `search()` (line 76) and `listings()` (line 312)
  already have `except City.DoesNotExist` branches that degrade gracefully (did-you-mean
  sentinel). The read-back can route through the same code path.
- **Client-side click handler** (`header_catalog.html:235-240`): On city click, POSTs to
  `search:preferred_city` via `fetch()`, then immediately sets `window.location.href` to
  `/city/<slug>/`. The `fetch()` is fire-and-forget (not awaited). Since the cookie is
  `HttpOnly=True`, client-side JS cannot verify cookie presence.
- **Search view city filter** (`search.py:69-77`): `current_city = request.GET.get("city")`.
  If truthy, resolves `City.objects.get(slug=current_city)` and filters `ads.filter(city_id=...)`.
  On `DoesNotExist`, sets `suggested_city` (did-you-mean). `selected_city_id` (line 95-100)
  reuses `current_city` for save-search modal prefill.
- **Listings view city filter** (`listings.py:300-323`): `city_slug` comes from URL path.
  If truthy, resolves + filters. If path slug is empty but `?city=` GET param present,
  only does did-you-mean (does **not** filter). Context `"current_city": city_slug` (line 420)
  is set from the path param only.
- **Cookie name convention**: `LANGUAGE_COOKIE_NAME` (line 34) and `CONSENT_COOKIE_NAME`
  (`consent.py:44`) are module-level constants, not in `enums.py` or as StrEnum. The bare
  string `"preferred_city"` should be consolidated into a constant.
- **`header_catalog.html`** context (`header_catalog.html:6-7`): Uses `bot_username`,
  `root_categories` (context processor), `query`, `breadcrumb_category` (or `ad.category`).
  The `current_cat` fallback (line 10) derives from `breadcrumb_category` / `ad.category` —
  not from the preferred-city cookie. No change needed to the template's city display.

### 3.3 HTMX 1.9.12 Constraints

- `hx-on` is NOT available (introduced in HTMX 2.0). Outside-click and Escape-to-close must
  use vanilla JS (see `header_catalog.html` lines 149-384 for the existing pattern).
- The cookie read-back is server-side only (HttpOnly cookie), so no HTMX/JS changes are needed.

---

## 4. Requirements

### R-101: Cookie Read-Back on Keyword Search

When a buyer visits `/search/?q=<query>` (keyword search with no `?city=` param), the system
must read the `preferred_city` cookie and apply it as a default city filter if the slug is valid.

### R-102: Cookie Read-Back on Catalog Browsing — DEFERRED (Q1)

Per Q1 (PO confirmed), the preferred-city cookie is applied to **keyword search only**.
The root catalog `/`, category listings `/category/<slug>/`, and `/city/<slug>/` listings
do **not** read the cookie. This requirement is deferred to a future task. T-600
(`listings()` integration) is removed from this spec's scope.

### R-103: Explicit Filter Precedence (Non-Mutating)

An explicit `?city=` param in `search()` or `city_slug` path param in `/city/<slug>/`
**always overrides** the cookie for the current request. The cookie is consulted only as a
fallback when no explicit city is specified. Explicitly: opening `/search/?q=квартира&city=budva`
temporarily filters to Budva but does **not** overwrite or clear the `preferred_city` cookie.
The persistent preference is changed only via the header/city selector (city click or
"All cities" selection).

### R-103b: Explicit Filter is Non-Mutating

Opening a temporary URL with `?city=<slug>` (e.g., `/search/?q=квартира&city=budva`) or
navigating to `/city/<slug>/` applies the city filter for that request only. It does **not**
overwrite or clear the `preferred_city` cookie. This prevents a user's temporary exploration
from changing their saved preference.

### R-104: Stale Cookie Handling

If the `preferred_city` cookie references a city slug that no longer exists in the `cities`
table, the system must silently ignore the cookie (no city filter applied) and delete the stale
cookie from the response so it does not persist.

### R-105: Cookie Clearing on City Change

- **Selecting a city** in the header/city selector overwrites the `preferred_city` cookie
  (new value, 30-day expiry).
- **Selecting "All cities"** in the header/city selector deletes the `preferred_city` cookie
  (permanent preference cleared).
- **Opening a temporary `?city=<slug>` URL or `/city/<slug>/`** does **not** clear or overwrite
  the cookie (non-mutating, per R-103b).
- The write endpoint (`preferred_city.py`) already handles the set; the "All cities" clear
  requires either a `POST` to `/api/preferred-city/` with an empty `slug`, or a dedicated
  clear response. See Data & API Contract §9.5.

### R-106: No Schema Changes

The read-back must not introduce any database migration. The cookie is the sole persistence
mechanism (consistent with Decision_018).

### R-107: Cookie Name as Constant

The `preferred_city` cookie name must be a module-level constant (following the
`LANGUAGE_COOKIE_NAME` precedent at `language.py:34`), not a bare string literal.

### R-108: HttpOnly Preserved

The cookie remains `HttpOnly=True` (already set in `preferred_city.py:49`). Read-back is
inherently server-side. No change to the cookie's security attributes.

---

## 5. Conceptual Development Tasks

| # | Task | Purpose | Depends On | Resolvable By |
|---|---|---|---|---|
| **T-100** | Decision gate (DONE) | Resolved storage strategy: cookie-only via Decision_018 | — | PO |
| **T-200** | Cookie write endpoint (DONE) | POST `/api/preferred-city/` sets cookie (30-day, HttpOnly) | Decision_018 | Backend |
| **T-300** | Click handler (DONE) | JS in header: POST to set cookie + navigate to `/city/<slug>/` | T-200 | Frontend |
| **T-400** | Preferred-city middleware | Read + validate cookie; enrich `request.preferred_city` (slug or `None`) | Decision_018 | Backend |
| **T-500** | `search()` read-back integration (keyword-only, Q1) | Default `?city=` from `request.preferred_city` when absent | T-400 | Backend |
| ~~T-600~~ | ~~`listings()` read-back integration~~ | **DEFERRED** — Q1 scopes cookie read-back to keyword search only; root catalog `/` and category listings excluded | — | — |
| **T-700** | Stale-cookie clearing + non-mutation | `process_response` deletes invalid/stale cookie; explicit `?city=` never overwrites | T-400 | Backend |
| **T-701** | "All cities" cookie clear | Extend write endpoint (`preferred_city.py`) to accept empty `slug` and delete the cookie | Decision_018 | Backend |
| **T-800** | Refactor cookie constants | Move `preferred_city` + `PREFERRED_CITY_COOKIE_MAX_AGE` into shared constant | T-400 | Backend |
| **T-900** | Tests for read-back | Middleware unit + view integration (cookie→filter, precedence, stale, non-mutation) | T-500, T-700, T-701 | Backend/QA |

**Suggested build order:** T-400 → T-800 → T-500 → T-701 → T-700 → T-900

**Note:** T-200, T-300 are already implemented. T-400, T-500, T-700, T-701, T-800, and T-900 are the
remaining work specified by this document. T-600 is deferred (Q1: keyword search only).

---

## 6. Product Owner Decisions

| # | Question | PO Decision | Source |
|---|---|---|---|
| D1 | Storage strategy for preferred-city | **Cookie-only (option c)** — no schema change; registered-user `User.preferred_city` persistence deferred | Decision_018 §4 |
| D2 | MVP scope | "preferred-city storage without complex personalization" — cookie is sufficient uniform mechanism for guests + registered | Decision_018 §4 |
| D3 | Cookie attributes | 30-day expiry, city slug value, HttpOnly, SameSite=Lax, Secure when HTTPS | Decision_018 §3; `preferred_city.py:45-51` |
| **Q1** | Cookie read-back scope | **A (keyword search only)** — apply `preferred_city` cookie to `/search/?q=`. **NOT** applied to `/`, `/category/<slug>/`, or `/city/<slug>/`. | PO answered 2026-08-19 |
| **Q2** | Precedence | **A** — explicit `?city=` / `/city/<slug>/` **always overrides** the cookie. | PO answered 2026-08-19 |
| **Q3** | Cookie clearing | **A (clarified)** — selecting a city overwrites; selecting "All cities" clears; opening a temporary `?city=` URL does **not** mutate the cookie. | PO answered 2026-08-19 |
| **Q4** | Stale cookie | **A** — silently ignore + delete stale cookie. | PO answered 2026-08-19 |

### Hybrid Resolution Model (PO-Confirmed)

```
1. Explicit city filter     (?city=<slug>  |  /city/<slug>/)     ← always wins; does NOT mutate preference
2. Authenticated user       (User.preferred_city)                ← deferred; field does not exist yet
3. Anonymous user           (preferred_city cookie)             ← current MVP
4. No preferred city        → no city filter applied
```

---

## 7. Resolved Questions

All four questions are now **resolved** by the Product Owner (answered 2026-08-19).

### Q1 (RESOLVED): Cookie read-back scope — keyword searches only

**PO decision: A (keyword search only).** The `preferred_city` cookie is applied as a default
city filter on `/search/?q=` **only**. It is **not** applied to the root catalog `/`, category
listings `/category/<slug>/`, or `/city/<slug>/`.

| Option | Behavior | PO Decision |
|---|---|---|
| **A** ✅ | Apply to keyword searches only | **SELECTED** — avoids surprising users browsing a category who don't want their preferred city auto-applied |
| B | Apply to keyword searches + catalog root | ⚠️ Rejected — PO wants category/catalog browsing to show all cities |
| C | Apply to keyword search + catalog root only | ⚠️ Rejected — same reasoning |
| D | No read-back — cookie is write-only | ⚠️ Rejected — cookie would serve no purpose |

**Rationale:** "Иначе пользователь может открыть, например, «Недвижимость» и внезапно получить
только Подгорицу, хотя он просто хотел посмотреть весь каталог." (PO)

**Impact on tasks:** T-600 (`listings()` integration) is **deferred**. T-400, T-500, T-700,
T-701, T-800, T-900 remain in scope.

### Q2 (RESOLVED): Explicit filter precedence

**PO decision: A** — `?city=<slug>` or `/city/<slug>/` **always overrides** the cookie for
the current request. Explicit selection is **non-mutating** — it does not change the saved
preferred city.

### Q3 (RESOLVED): Cookie clearing mechanism

**PO decision: A (clarified)** — Three behaviors:
1. Selecting a city in the **header/city selector** overwrites the cookie.
2. Selecting **"All cities"** in the header/city selector clears (deletes) the cookie.
3. Opening a **temporary** `?city=<slug>` URL or `/city/<slug>/` does **not** overwrite or clear
   the cookie (non-mutating, per Q2).

### Q4 (RESOLVED): Stale cookie behavior

**PO decision: A** — Silently ignore + delete the stale cookie. No errors shown to the user.

---

## 8. Technical Constraints

1. **No schema changes** — Decision_018 mandates cookie-only; `makemigrations --check` must remain clean.
2. **HttpOnly cookie** — `preferred_city.py:49` sets `httponly=True`; read-back must be server-side only. Client-side JS cannot read or clear the cookie.
3. **Middleware pattern precedent** — `LanguagePreMiddleware` (language.py:34-148) is the only cookie-reading pattern; the read-back must follow it.
4. **Middleware ordering** — new middleware inserted after `LanguagePreMiddleware` in `base.py:112-122` (`process_request` enriches request before views execute).
5. **City.slug uniqueness** — `unique=True` (locations/models.py:36); stale-cookie validation via `City.objects.filter(slug=...).exists()` is an indexed lookup.
6. **No custom CSS** — `input.css` is Tailwind-only (no new `.css` rules); all styling via utility classes.
7. **StrEnum for domain constants** — follow project rule #10; cookie name follows the module-level-constant convention (`LANGUAGE_COOKIE_NAME`, `CONSENT_COOKIE_NAME`), not StrEnum.
8. **HTMX 1.9.12** — no `hx-on`; read-back is server-side so no JS changes needed.
9. **`settings.BOT_USERNAME` never in templates** — must arrive via context variable (R-05f, spec_014 §7); the preferred-city feature does not touch this.

---

## 9. Data & API Contracts

### 9.1 Cookie Write (existing, unchanged)

```
POST /api/preferred-city/
Body: slug=<city_slug>
Headers: X-CSRFToken (from csrfmiddlewaretoken input)

Response 200: {"ok": true}
  Set-Cookie: preferred_city=<city_slug>; Max-Age=2592000; HttpOnly; SameSite=Lax; Secure (in prod)

Response 400: {"error": "invalid_city"}
  (unknown or missing slug)
```

### 9.2 Cookie Read — Preferred City Resolution (new — T-400 middleware)

```
GET /search/?q=<query>          (keyword search, no ?city= param)
Cookies: preferred_city=<city_slug>

→ Middleware sets: request.preferred_city = <valid_slug | None>
→ search(): if not request.GET.get("city"):
        current_city = getattr(request, "preferred_city", None)
→ Results filtered by city_id (if current_city is truthy)
```

**Resolution precedence** (keyword search only; Q1):

```
1. Explicit city filter     ?city=<slug>            → used directly; cookie NOT consulted
2. Authenticated user       User.preferred_city     → (deferred — field does not exist; not implemented)
3. Anonymous user           preferred_city cookie   → applied as default city filter
4. None                     → no city filter applied
```

**Scope note (Q1):** Root catalog `/`, category listings, and `/city/<slug>/` do **not** read
the cookie. The read-back is specific to `/search/?q=` keyword search.

### 9.3 Non-Mutation on Explicit Filter (new — T-700)

```
GET /search/?q=квартира&city=budva    (explicit ?city=)
Cookies: preferred_city=podgorica

→ search(): current_city = request.GET.get("city") → "budva"
→ Results filtered to Budva
→ Cookie is NOT read, NOT overwritten, NOT cleared
→ preferred_city cookie remains = "podgorica"
```

Opening a temporary `?city=` URL or `/city/<slug>/` does **not** mutate the persistent
preferred city (per Q2+Q3).

### 9.4 Stale Cookie (new — T-700)

```
GET /search/?q=<query>
Cookies: preferred_city=<deleted_city_slug>

→ Middleware: City.objects.filter(slug=<deleted_city_slug>).exists() → False
→ request.preferred_city = None
→ process_response: response.delete_cookie("preferred_city")
→ View: no city filter applied (default "all cities")
```

### 9.5 "All Cities" Cookie Clear (new — T-701)

```
POST /api/preferred-city/
Body: slug=                        (empty — signals clear)
Headers: X-CSRFToken

Response 200: {"ok": true}
  Set-Cookie: preferred_city=; Max-Age=0; HttpOnly; SameSite=Lax; Secure (in prod)
```

Triggered by selecting "Все города" in the header/city selector. Deletes the cookie entirely
(per Q3).

### 9.6 Cookie Filter Contract (unchanged, existing)

### 9.4 City Filter Contract (unchanged, existing)

Both `search()` and `listings()` use `City.objects.get(slug=city).filter(city_id=city.id)` —
the read-back routes the cookie value through this exact existing code path. No new query
pattern; no new index.

---

## 10. Acceptance Criteria

### AC-1: Keyword search respects preferred city
- Given a buyer with `preferred_city=Подгорица` cookie
- When they search `/search/?q=велосипед` (no `?city=`)
- Then results are filtered to Подгорица ads only
- And `current_city` in the template context reflects the cookie value

### AC-2: Explicit city overrides cookie (non-mutating)
- Given a buyer with `preferred_city=Подгорица` cookie
- When they search `/search/?q=велосипед&city=dubrovnik`
- Then results are filtered to Дубровник (not Подгорица)
- And the `preferred_city` cookie **remains** `Подгорица` (not overwritten by explicit `?city=`)

### AC-3: Catalog root does NOT respect preferred city (Q1)
- Given a buyer with `preferred_city=Подгорица` cookie
- When they visit `/` (homepage) or `/category/electronics/`
- Then **all** cities' ads are shown (cookie is not applied to catalog browsing)

### AC-4: Stale cookie is ignored and cleared
- Given a buyer with `preferred_city=old-city` cookie (city deleted from DB)
- When they visit `/search/?q=велосипед`
- Then no city filter is applied (all cities shown)
- And the `preferred_city` cookie is deleted from the response

### AC-5: Selecting a city overwrites the cookie
- Given a buyer with `preferred_city=Подгорица` cookie
- When they select "Дубровник" in the **header/city selector** (not a temp `?city=` URL)
- Then the cookie is overwritten to `preferred_city=Дубровник`
- And results show Дубровник ads

### AC-6: "All cities" clears the cookie
- Given a buyer with `preferred_city=Подгорица` cookie
- When they select "Все города" in the header/city selector
- Then the `preferred_city` cookie is deleted (cleared)
- And subsequent searches show all cities by default

### AC-7: No schema changes
- `makemigrations --check` passes with no new migrations required

### AC-8: Tests pass
- `test_preferred_city.py` (existing 4 write-side tests) still passes
- New middleware tests mirror `test_language_middleware.py` pattern
- New read-back integration tests in `test_search.py` / `test_listings_context.py`
- `rm test_autocomplete_template.py` assertions still pass (no template changes)
- `makemigrations --check` passes (no migrations expected — cookie-only)

---

## 11. Risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| **Fire-and-forget fetch race** | High | Low | `header_catalog.html:239` — POST fires but navigation starts immediately; cookie may not be set on first `/city/<slug>/` landing. **Not blocking**: URL path carries the slug, so `listings()` filters correctly without the cookie. Cookie read-back is for *subsequent* navigations. Frontend can `await` the fetch later (out of scope). |
| **Stale cookie serves deleted city** | Low | Medium | Middleware validates `City.objects.filter(slug=...).exists()` on every read; invalid slugs → `None` + cookie deletion in `process_response`. |
| **DB lookup per request** | Medium | Low | One indexed `City.objects.filter(slug=...)` exists-check per request when cookie present. Cacheable via Django cache framework if profiling shows cost. |
| **Cookie name as bare string** | Low | Low | T-800 consolidates `"preferred_city"` into a module-level constant, following `LANGUAGE_COOKIE_NAME` precedent. |
| **Middleware ordering** | Low | Medium | Insert after `LanguagePreMiddleware` (base.py:119) so request enrichment is available to all views. Verified via test that `request.preferred_city` is set before `search()` runs. |
| **City deleted after cookie set** | Low | Low | Covered by AC-4 / R-104 — stale-cookie clearing. Pre-existing `except City.DoesNotExist` in views provides second line of defense. |
| **Breaking existing tests** | Low | Medium | The read-back adds a fallback (`if not current_city: current_city = getattr(request, "preferred_city", None)`) — when no cookie is present (all existing test requests), behavior is unchanged. |

---

## 12. Assumptions

1. **Q1 = A (keyword search only)**: The cookie read-back applies to `/search/?q=` only.
   Root catalog `/` and category listings `/category/<slug>/` do **not** read the cookie
   (PO-confirmed, not an assumption).
2. **Q2 = A**: Explicit `?city=` / `/city/<slug>/` always overrides the cookie for the
   current request and does **not** mutate it.
3. **Q3 = A (clarified)**: Selecting a city in the header/city selector overwrites; "All cities"
   clears. Opening a temporary `?city=` URL does not mutate the cookie.
4. **Q4 = A**: Stale cookies are silently ignored and cleared via `process_response`.
5. **`User.preferred_city` is deferred**: The `User` model (extends `AbstractUser`) does not
   currently have a `preferred_city` field. The hybrid resolution model documents where this
   tier will slot in. For now, all users (guests + registered) use the cookie.
6. **Both guests and registered users** use the same cookie (Decision_018 consequence).
   No server-side profile storage.
7. **The cookie write path** (`preferred_city.py`, `header_catalog.html` click handler) is
   stable for the write side; T-701 extends it to accept an empty `slug` for the "All cities"
   clear.
8. **The `/city/<slug>/` route** and `?city=` query param contract remain unchanged — explicit
   selection is non-mutating per Q2/Q3.
9. **Test environment** uses Docker PostgreSQL (`mko-bazuna-test-db-*`), not local `uv run pytest`.

---

## 13. Out of Scope

- **Catalog root `/`, category listings, and `/city/<slug>/` cookie read-back** — Q1 restricts the
  cookie to keyword searches only (`/search/?q=`). T-600 (`listings()` integration) is deferred.
- **Registered-user `User.preferred_city` persistence** — the `User` model does not yet have this
  field; server-side profile persistence is deferred to a dedicated buyer-profile subsystem (D1).
- **Geo-IP auto-detection** — not in MVP scope.
- **Session-based city preference** — session history remains separate (search history, not city
  preference).
- **Frontend fetch await** — the `header_catalog.html:239` fire-and-forget `fetch()` race is a
  frontend fix (out of scope; documented as a risk).
- **Frontend `await` for cookie write** — client cannot verify HttpOnly cookie presence; a future
  fix may `await` the fetch to guarantee the cookie is set before navigation.
- **Cookie-based UI indicator** — the header does not show which city is "preferred" (HttpOnly
  cookie cannot be read by JS; no UI badge needed for MVP).
- **`bot_username` in templates** — unrelated to this feature; already handled by context processor.
- **Migration workflow** — no migrations needed (cookie-only; D1).

---

## 14. Dependencies

| Dependency | Rationale |
|---|---|
| `apps/locations/models.py` (`City`) | Validation of cookie slug via `City.objects.filter(slug=...)` |
| `apps/core/middleware/language.py` | Architectural precedent for cookie reading + request enrichment |
| `apps/search/views/search.py` (lines 69-77, 95-100) | City filter block to extend with cookie fallback (keyword search only) |
| `apps/search/views/preferred_city.py` | Write endpoint to extend for T-701 ("All cities" = empty slug → delete cookie); consolidate cookie constant |
| `apps/core/middleware/` package | Directory to host the new `PreferredCityMiddleware` |
| `config/settings/base.py` (line 112-122) | `MIDDLEWARE` list to register the new middleware |
| `apps/users/models.py` (`User`) | Reference for deferred `User.preferred_city` tier (field does not exist yet) |
| `templates/components/header_catalog.html` | Consumer of `current_city` context; "All cities" selector triggers T-701 POST |

---

## 15. Research Summary

A Researcher agent investigated the architecture and best practices
(full report: `.ai/research/16_preferred-city_readback_report.md`).

### Key Findings

1. **The read-back gap is confirmed** — grep for `request.COOKIES` across `src/` returns only
   `language.py:64` (the `lang_pref` cookie). No code reads `preferred_city`.

2. **Middleware is the recommended approach** — mirrors the sole existing cookie-reading
   pattern (`LanguagePreMiddleware`). The language middleware reads a cookie in
   `process_request`, validates it, and enriches the request (`request.LANGUAGE_CODE`),
   which is then consumed by `search.py:113`. The preferred-city read-back is structurally
   identical.

3. **Exact code changes identified** (with file/line references):
   - `search.py:70`: add `if not current_city: current_city = getattr(request, "preferred_city", None)`
     — **only** in `search()`, per Q1 (keyword search only)
   - `listings.py`: read-back deferred (Q1); no `listings()` changes for cookie fallback
   - New `apps/core/middleware/preferred_city.py` with `PreferredCityMiddleware`
   - Register at `base.py:120` (after `LanguagePreMiddleware`)
   - `preferred_city.py`: add T-701 support for empty `slug` → `delete_cookie`

4. **Stale-cookie handling** — middleware validates slug on every read; invalid → `None`
   + `delete_cookie()` in `process_response`. Existing `except City.DoesNotExist` branches
   in views provide a second line of defense.

5. **No industry standard for persistent city cookies** — Avito uses URL-embedded location,
   OLX uses geolocation. The cookie approach is project-specific (MVP simplicity for
   anonymous users). The middleware approach keeps it server-side and HttpOnly-safe.

### Rejected Approaches

- **Service function per view** (Approach B) — breaks the codebase precedent; duplicates the
  read path across two views; no request-enrichment for other consumers.
- **Inline cookie read in each view** (Approach C) — violates project rules (#10 constants,
  #4 single responsibility, DRY); no precedent; harder to test.

### Risks Not Covered by Research

- **Frontend fetch race** (`header_catalog.html:239`) — the `fetch()` to set the cookie is
  fire-and-forget; navigation starts immediately. Since the URL path carries the slug, the
  first landing filters correctly via path param; the cookie only matters for *subsequent*
  navigations. A frontend `await` fix is recommended separately.

---

## 16. Definition of Ready

This specification is implementation-ready. All PO questions are resolved:

1. **Q1 = A (keyword search only)** ✅ — confirmed by PO; T-700 includes cookie read-back on
   `/search/?q=` only. T-600 (`listings()` read-back) is deferred.
2. **Q2 = A** ✅ — explicit `?city=` / `/city/<slug>/` always overrides the cookie; non-mutating.
3. **Q3 = A (clarified)** ✅ — city selector overwrites; "All cities" clears; temp `?city=` is
   non-mutating. T-701 extends the write endpoint for the "All cities" clear.
4. **Q4 = A** ✅ — stale cookies silently ignored + cleared via `process_response`.
5. **All assumptions confirmed or accepted as PO defaults** (Section 12).
6. The implementation team has access to:
   - This spec (`16_preferred-city_spec.md`)
   - Decision_018 (approved decision)
   - Spec_014 (R-01d, §8.3 — preferred city storage contract)
   - The Researcher report (`16_preferred-city_readback_report.md`)
7. The test environment is available: `docker compose --project-name mko-bazuna-test -f docker-compose.yml -f docker-compose.test.yml up -d db`.
8. `makemigrations --check` is clean (no migrations expected — cookie-only).

---

*Spec compiled from Decision_018 (approved decision), Spec_014 (R-01d, §8.3), codebase analysis
(preferred_city.py, header_catalog.html, search.py, listings.py, language.py), and the
Researcher report (preferred-city read-back investigation). All findings read directly from
the repository.*
