---
id: 18_preferred-city
domain: spec
tags:
  - preferred-city
  - hybrid-persistence
  - catalog-ui
  - search
  - cookie
  - user-model
related:
  - technical-specification
  - search-patterns
  - filter-ui
  - ui-patterns
  - db-schema
  - architecture-structure
  - 14_catalog-ui-avito_spec
  - 16_preferred-city_spec
  - Decision_018
  - owner-decisions-index
---

# Spec_018 — Preferred-City: Hybrid Persistence & Catalog City Selector

**Decision source:** `.ai/problems/Decision_018.md` (approved direction: hybrid `User.preferred_city` FK + cookie)
**Spec state:** IMPLEMENTATION-READY — Product Owner questions resolved with recommended defaults (see §6)
**Date:** 2026-08-19
**Stack:** Django 5.2 LTS · Python 3.14 · HTMX 1.9.12 · PostgreSQL 18 · aiogram 3.x · Tailwind CSS · django-mptt
**Plan:** 15 (catalog-ui-avito) — subsumes task T-700 from Spec_016
**Supersedes:** `16_preferred-city_spec.md` (cookie-only read-back) and `14_catalog-ui-avito_spec.md` §8.3/T6 (`UserProfile.preferred_city`)

---

## 1. Problem Statement

The catalog header lets a buyer choose a city (via the autocomplete "city" suggestion or — per this decision — a dedicated header city button). The chosen city must **(a)** persist across sessions for both guests and registered buyers, and **(b)** act as the **default catalog/search filter** on subsequent visits — without becoming a hard constraint that prevents browsing another city.

The existing codebase (Decision_018 cookie-only MVP, Spec_016) implements only the **write** side: `POST /api/preferred-city/` sets a 30-day `preferred_city` cookie, but **no code reads it back**, so a returning visitor re-selects their city every time.

**Decision_018 (revised)** upgrades the storage strategy to a **hybrid model** — mirroring Avito.ru's proven pattern (cookie+localStorage for anonymous, account-stored for authenticated):

| Role | Storage | Resolution |
|---|---|---|
| Authenticated buyer | `User.preferred_city` FK → `City` | Server-side, cross-device |
| Anonymous buyer | `preferred_city` cookie (city slug) | Browser-local |

The two layers are reconciled at read time: for authenticated users the **database value wins**; the cookie is a **fallback** only when the DB value is empty (e.g., guest→login migration) and continues to serve anonymous visitors.

### Authoritative city-resolution priority

**Authenticated user:**
1. Explicit city in the current URL path (`/city/<slug>/`) or `?city=` param
2. `User.preferred_city` (account preference)
3. `preferred_city` cookie (guest fallback)
4. Default — **all cities** (no filter → country-wide)

**Anonymous buyer:**
1. Explicit city in URL path or `?city=` param
2. `preferred_city` cookie
3. Default — **all cities** (no filter → country-wide)

`preferred_city` is a **default filter, not a hard constraint** (Decision_018 §"город не должен автоматически ломать поиск"): an explicit city in the request always overrides it, and the user can always navigate to `/city/<other>/`.

`preferred_city` is **independent of `SavedSearch.city`** (Decision_018 §"И ещё один момент"): the saved-search city is a per-search explicit filter condition; `preferred_city` is a global quick-context ("usually search here"). Alert queries are scoped to `SavedSearch.city`, never to `preferred_city`.

---

## 2. Confirmed Requirements

### R-01: User model carries preferred_city

`User` (Django `AbstractUser`, `apps/users/models.py`) gains a nullable FK to `locations.City`. **No separate `UserProfile` model** — the author explicitly rejected the 1:1 profile table as overengineering for a single field (Decision_018 §"Но `UserProfile` действительно не нужен"). `related_name="+"` (no reverse accessor needed).

| Field | Type | Attributes |
|---|---|---|
| `preferred_city` | `ForeignKey("locations.City")` | `null=True, blank=True, on_delete=SET_NULL, related_name="+"` |

`on_delete=SET_NULL` (not PROTECT) is deliberate: the existing `Ad.city` uses PROTECT (an ad must keep its posting city), but a *user preference* should never block a city from being removed from the catalog. A deleted city → `NULL` (graceful downgrade to "all cities"), matching the author's "not a hard constraint" principle.

### R-02: One migration

A single new migration `apps/users/migrations/0003_user_preferred_city.py` adds the nullable FK. Nullable = no default value needed; existing rows are unaffected. (Resolves Superseded Spec_016 AC-6/R-106 "no schema changes".)

### R-03: Cookie attributes (updated from cookie-only)

| Property | Value | Notes |
|---|---|---|
| Name | `preferred_city` | Module-level constant `PREFERRED_CITY_COOKIE_NAME` (see §7) |
| Value | City slug (e.g. `podgorica`) | |
| `max_age` | **1 year** (`31536000`s) | Changes Spec_016's 30 days → per Decision_018 §"А cookie всё равно оставляем" |
| `httponly` | `True` | Read-back is server-side only |
| `samesite` | `Lax` | |
| `secure` | `request.is_secure()` | Prod-only via SECURE_PROXY_SSL_HEADER |
| `path` | `/` | Site-wide |

Cookie name is a **module-level constant** following `LANGUAGE_COOKIE_NAME` (`apps/core/middleware/language.py:34`) and `CONSENT_COOKIE_NAME` (`apps/users/views/consent.py:44`). It is **not** a `StrEnum` — the codebase investigation confirmed cookie names are not domain-fixed-value sets in this project's convention (they are transport-layer identifiers, not business enums). See §7.3 for the rejected StrEnum alternative.

### R-04: Middleware resolves the effective preferred city

A new `PreferredCityMiddleware` (mirroring `LanguagePreMiddleware`) runs in `process_request`, enriches `request` with the **effective preferred city** (DB-first for authenticated, cookie fallback for anonymous), validates the slug, and deletes stale cookies in `process_response`. Registered after `LanguagePreMiddleware` in `MIDDLEWARE` (base.py:119).

### R-05: Search view defaults to the preferred city

`search()` applies the resolved preferred city as the **default** `city` filter when no explicit `?city=` param is present (R-01d intent from Spec_014). Explicit `?city=<slug>` always wins.

### R-06: Listings view defaults to the preferred city

`listings()` applies the resolved preferred city as the default filter when the URL path has no `city_slug` and no `?city=` param. The context `current_city` reflects the active city so the header badge/filter display is correct.

### R-07: City button in the catalog header

The header gains a persistent **city button** (`📍 <CityName> ▾`), per Decision_018 §"Как это будет выглядеть в интерфейсе" and the OLX/Avito research (Avito Pattern A header button is the most discoverable). Clicking opens a dropdown of the Montenegro city list; selecting a city writes the preference (cookie + DB for auth) and navigates to `/city/<slug>/`.

### R-08: Login migrates guest preference to account

On successful login (`login_status` → `auth_login`, consent.py:285), if the authenticated user has **no** `User.preferred_city`, the cookie value (if valid) is written to `User.preferred_city`. If the user **already has** a DB preference, the cookie is overwritten to match (keeps them in sync). This is the guest→registered migration the author requires.

### R-09: Logout keeps the cookie

`POST /logout/` flakes the Django **session** only; the `preferred_city` cookie is **intentionally retained** (Decision_018 §"При logout можно охранить cookie — это не секрет"). The retained cookie serves as the fallback for the user's next anonymous session. Cookie is **not** user-identifying/PII (it is a city slug), so retaining it is safe and improves re-engagement UX.

### R-10: Stale-cookie tolerance

If the cookie (or `User.preferred_city`) references a city slug no longer in `cities`, the middleware treats it as `None` (no filter applied) and the response deletes the stale cookie. The existing `except City.DoesNotExist` branches in `search()` and `listings()` are a second line of defense.

### R-11: Cookie write persists DB preference for authenticated users

`POST /api/preferred-city/` writes **both** the cookie (for all visitors) and `User.preferred_city` (for authenticated users) on a valid city selection. Guests get the cookie only.

---

## 3. Conceptual Development Tasks

| # | Task | Purpose | Expected Outcome | Depends On |
|---|---|---|---|---|
| T-01 | Add `preferred_city` FK to `User` | Persist the buyer's preferred city server-side (account-scoped) per the hybrid model | `User.preferred_city` nullable FK → `cities`, `SET_NULL`, `related_name="+"`; migration `0003_user_preferred_city` | Decision_018 |
| T-02 | Add `PreferredCityMiddleware` | Resolve the *effective* preferred city once per request and enrich it for views (DB for authenticated, cookie for anonymous); validate + clear stale cookies — mirrors `LanguagePreMiddleware` | Middleware sets `request.preferred_city = <slug\|None>`; registered after `LanguagePreMiddleware` (base.py:119); `process_response` deletes stale cookie | T-01 |
| T-03 | Extend cookie write endpoint | Write cookie (1-year) + `User.preferred_city` (auth) on city selection; consolidate cookie name/mAX_AGE into shared constants | `preferred_city.py` extended; `PREFERRED_CITY_COOKIE_NAME` + `PREFERRED_CITY_COOKIE_MAX_AGE = 1yr` shared; auth → `User.preferred_city` save | T-01 |
| T-04 | Search-view read-back | Apply the effective preferred city as the default `?city=` filter (cookie/DB fallback) when no explicit city in the query | `search.py`: `current_city = explicit OR request.preferred_city` | T-02 |
| T-05 | Listings-view read-back | Apply the effective preferred city as the default filter when the URL path and query carry no city; set `current_city` in context | `listings.py`: `else` branch falls back to `request.preferred_city`; context `current_city` updated | T-02 |
| T-06 | Login sync hook | Migrate a guest's cookie preference into `User.preferred_city` on first login; re-sync on subsequent logins | Login hook (consent.py:285) backfills DB from cookie (if DB null) / overwrites cookie from DB (if set) | T-01, T-03 |
| T-07 | Header city button | Add a persistent `📍 <City> ▾` button to `header_catalog.html` with a city dropdown; show the effective preferred city (or default label) | Header renders city badge; dropdown lists Montenegro cities; click → persist + navigate to `/city/<slug>/` | T-02 |
| T-08 | Tests | Cover middleware (unit), view read-back (integration), login sync, header rendering, precedence, stale-cookie clearing | Mirrors `test_language_middleware.py` (SimpleTestCase) + `test_preferred_city.py` (Client) patterns | T-02…T-07 |

**Suggested build order:** T-01 → T-02 → T-03 → (T-04 ∥ T-05 ∥ T-07) → T-06 → T-08

**Note:** T-02/T-08 build on the existing write side (Spec_016 T-200/T-300). T-03 revises the existing 30-day cookie to 1-year and adds the DB write. T-06 is new (login sync). T-07 is new (header badge).

---

## 4. Product Owner Decisions

These are the gray areas in `Decision_018.md` resolved with a recommended default. The author's intent is strong throughout; defaults match Decision_018's reasoning and the Avito/OLX research unless marked **needs confirmation**.

| # | Decision | Resolved Value | Source / Rationale |
|---|---|---|---|
| D-1 | Storage strategy (cookie vs. profile vs. hybrid) | **Hybrid** — `User.preferred_city` FK (auth) + cookie (guest) | Decision_018 §"Я бы сделал гибрид"; Avito.ru persistence pattern (§5) |
| D-2 | FK on `User` vs `UserProfile` | **Directly on `User`** — no profile table | Decision_018 §"Но `UserProfile` действительно не нужен"; replaces Spec_014 §8.3/T6 |
| D-3 | `on_delete` on `User.preferred_city` | **SET_NULL** (graceful downgrade) | Preference must not block city removal; "not a hard constraint" principle; contrasts with `Ad.city`=PROTECT |
| D-4 | Authenticated priority order | explicit URL/param > `User.preferred_city` > cookie > default | Decision_018 §"Приоритет" |
| D-5 | Anonymous priority order | explicit URL/param > cookie > default | Consistent with D-4 (DB layer absent) |
| D-6 | Default city when no preference | **All cities (no filter)** — country-wide | Matches existing behavior (no regression); Avito/Geo-IP and OLX/Mobile "All" both use country-wide default; the author never named a specific default city; see Q-1 |
| D-7 | Cookie `max_age` | **1 year** (`31536000`s) | Decision_018 §"А cookie всё равно оставляем" (`Max-Age = 1 year`); replaces Spec_016's 30 days |
| D-8 | Cookie persists across logout | **Yes — retained** | Decision_018 §"При logout можно охранить cookie" |
| D-9 | Header city button | **Add persistent `📍 <City> ▾` button** | Decision_018 §"Как это будет выглядеть в интерфейсе"; Avito Pattern A (most discoverable); research §3.2.5/12.2 |
| D-10 | `preferred_city` vs `SavedSearch.city` | **Fully independent** — alert queries scope to `SavedSearch.city` only | Decision_018 §"не надо путать"; SavedSearch already has its own `city` FK (search/models.py:63) |
| D-11 | Query-text city extraction | **No** — "explicit city" = URL path `/city/<slug>/` or `?city=` param only (see Q-3) | Matches existing architecture (FTS is title/desc only); Avito/OLX use URL/param-driven city, not free-text parsing |
| D-12 | Profile-management surface | **Header button is the primary setter**; dedicated cabinet profile page deferred | Decision_018 only describes the header; "не усложнять без необходимости"; Spec_017 (User Cabinet) may extend later |
| D-13 | Login sync direction | **Bidirectional reconcile**: if DB null → backfill from cookie; if DB set → overwrite cookie from DB | Decision_018 §"После сравнения с OLX" + §"После логина синхронизировать cookie с User.preferred_city" |

---

## 5. Research Summary

Two evidence-backed investigations were delegated to the Researcher agent and are fully documented in:

- **Competitive UX:** `docs/07-design-researches/Design_03/city-selection-report.md` (524 lines, live DOM via Playwright on 2026-08-19) and `.ai/research/16_preferred-city_readback_report.md` §3.1
- **Codebase:** `.ai/research/16_preferred-city_readback_report.md` §1–§6, plus direct source reads in this analysis

### 5.1 Competitive UX findings (key takeaways)

| Platform | Header city indicator? | Persistence | Precedence | Cross-device (auth) |
|---|---|---|---|---|
| **Avito.ru** ✅ reference | Yes — `<button>` "Пермь" right of search | Cookie + localStorage + account | URL path > cookie > Geo-IP > default | Yes |
| **OLX.ua** | No — city combobox *inside* hero search form | Unknown (likely HttpOnly cookie) | Country-wide default ("All Ukraine") | Likely yes |
| **Mobile.bg** | No — region `<select>` in filter sidebar | URL params (likely) | "All" default | Unknown |
| Otomoto.pl / SS.com | None | — | — | — |

**Key takeaways for Mko Bazuna:**
- Avito.ru **validates** cookie+account hybrid persistence — Decision_018's chosen direction is industry-proven.
- **Persistent header city indicator matters**: only Avito provides one; Mko Bazuna currently has none (city is hidden inside autocomplete). Confirms D-9.
- For a ~30-city market (Montenegro), an inline combobox/dropdown suffices — no Avito-scale modal picker needed (report §13.3).
- **Default fallback = country-wide** is the norm for smaller markets (OLX "All Ukraine", Mobile.bg "All"). Confirms D-6.
- **Precedence = URL/param wins** is universal. Confirms D-4/D-5/D-11 (no free-text city parsing; Avito itself reads city from the URL path, not the query text).

### 5.2 Codebase findings (key takeaways)

- **Read-back gap confirmed** — `request.COOKIES` appears in production only at `language.py:64` (the `lang_pref` cookie). `preferred_city` is written at `preferred_city.py:44-52` + `header_catalog.html:235-240` but **never read**.
- **User model** (`apps/users/models.py`) has no `preferred_city`; latest migration is `0002_alter_user_telegram_id_null`; a new `0003_user_preferred_city` is required.
- **`City` model** has `slug = SlugField(unique=True)` and **no `is_active`** — cities are hard-deleted. `SET_NULL` on the FK + middleware validation handle staleness.
- **`LanguagePreMiddleware`** (`language.py:34-148`, registered `base.py:119`) is the **structural precedent**: module-level cookie constant, `process_request` read+validate+enrich, `process_response` write/delete, `SimpleTestCase` tests in `test_language_middleware.py`.
- **Precedence today:** `listings()` reads city from URL path (`/city/<slug>/`); `search()` reads `?city=` param; `request.GET.get("city")` (search.py:70) does not consult the cookie. The `?city=` GET param in `listings()` currently triggers only did-you-mean (no filter) — a latent inconsistency to preserve (not regress) or fix separately.
- **Login hook** lands at `login_status` → `auth_login(request, user)` (consent.py:285); **logout** at `logout_view` → `django.contrib.auth.logout` (logout.py:23). The login hook is the natural sync point.
- **No persistent city button** exists in `header_catalog.html`; the city interaction is exclusively the autocomplete dropdown click handler (lines 235-240). `cities` queryset is passed to `list.html` by `search.py:175` but **not** by `listings()` (pre-existing gap — T-07 should pass `cities` if the header dropdown needs it).
- **Test patterns:** middleware = `SimpleTestCase` with `req = HttpRequest(); req.COOKIES[...]` + `getattr(request, ...)` assertions; view = `pytest.mark.django_db` + `Client` POST/GET; `test_preferred_city.py` already covers the write side (4 tests).

### 5.3 Implementation approaches evaluated

| Approach | Description | Verdict |
|---|---|---|
| **A. Middleware enrichment (RECOMMENDED)** | `PreferredCityMiddleware` mirrors `LanguagePreMiddleware`: reads cookie + (auth) DB in `process_request`, sets `request.preferred_city`; views fall back to it. Central stale handling + one test surface. | ✅ Adopt |
| B. Per-view service function | `get_preferred_city(request)` called in both views. | Rejected — no codebase precedent; duplicates read path; no request enrichment for the header badge (T-07). |
| C. Inline cookie read in each view | `request.COOKIES.get("preferred_city")` directly in both views. | Rejected — violates project rule #10 (bare string), rule #4 (DRY); no stale-cookies centralization. |

The middleware approach resolves **both** the read-back gap (Spec_016) **and** the authenticated-vs-guest priority (DB wins for auth) in one pass.

---

## 6. Key Assumptions (recommended defaults — pending PO confirmation on Q-1/Q-3)

1. **"Default city" = all cities (no filter)** when no preference exists (D-6). The author lists "Город по умолм по умолчанию" as priority #4 but never names a specific city; existing behavior is country-wide, and Avito/OLX/Mobile all default to country-wide for small markets.
2. **Read-time resolution is source of truth:** the middleware resolves the effective preferred city (DB-first for auth, cookie fallback). The login-time write-back (T-06) keeps the cookie consistent for the post-logout anonymous session but is not strictly required for correctness.
3. **City button shows** the *effective* preferred city (resolved by middleware); when none, shows a neutral label (e.g. "Вся страна" / country-wide) — **confirmed default label pending PO** (see Q-2 for the exact wording/locale).
4. **City click flow** is unchanged at the transport level: `POST /api/preferred-city/` (sets cookie + DB) then navigate to `/city/<slug>/`. Only the server-side persistence widens (DB write for auth) and the max_age changes (30d → 1yr).
5. **Fire-and-forget fetch race** (`header_catalog.html:239`) remains a known frontend risk (cookie may not be set on the *first* `/city/<slug>/` landing) — the URL path still filters correctly, so it is not blocking. A future `await fetch(...)` is out of scope here.
6. **Guests and registered users share the same header city button** and the same `/api/preferred-city/` endpoint.

---

## 7. Technical Constraints

1. **One migration only** — `User.preferred_city` nullable FK; `makemigrations` produces a single `0003_user_preferred_city`. (Overrides Spec_016 AC-6/R-106 "no schema changes".)
2. **HttpOnly cookie** — read-back is server-side only; no client-side JS reads `preferred_city`. (Preferred_city.py:49; report §3.3)
3. **Middleware pattern precedent** — must mirror `LanguagePreMiddleware` (language.py:34-148): module-level cookie constant, `process_request` enrichment, `process_response` cleanup; `SimpleTestCase`-style tests.
4. **Middleware ordering** — insert `PreferredCityMiddleware` **immediately after** `LanguagePreMiddleware` (base.py:119) so `request.preferred_city` is available before views execute.
5. **`City.slug` uniqueness** — `unique=True` (locations/models.py:36); stale validation via `City.objects.filter(slug=...).exists()` is an indexed lookup.
6. **No custom CSS** — `input.css` is Tailwind-only (Spec_007); all styling via Tailwind utility classes.
7. **StrEnum for domain constants; cookie name follows module-level-constant convention** — `LANGUAGE_COOKIE_NAME`/`CONSENT_COOKIE_NAME` precedent; cookie names are transport identifiers, not domain enums. A `StrEnum` for the cookie name is **rejected** (would diverge from the only two existing cookie constants and the `LanguagePreMiddleware` structural twin).
8. **HTMX 1.9.12** — no `hx-on` (introduced in 2.0); read-back is server-side so no JS changes are needed for the filter logic. (Any dropdown-toggle JS for the city button must use vanilla `data-*` per Spec_014 §7.1.)
9. **`settings.BOT_USERNAME` never in templates** — must arrive via the `bot_username` context variable (header_context context processor). The city button does not change this.
10. **City button only on public catalog pages** — `header_catalog.html` is included on `list.html` + `detail.html` (Spec_014 R-05b); **not** on dashboard/cabinet pages (separate `header.html`). The city badge belongs in `header_catalog.html` only.
11. **Two processes, one DB** — the bot also runs `django.setup()` and shares the ORM. The `User.preferred_city` write path is web-only (buyers set the city on the site); the bot does not need to read/write it. No bot-side change required.

---

## 8. Data & API Contracts

### 8.1 Cookie write (evolved — T-03)

```
POST /api/preferred-city/   (name="search:preferred_city")
Body: slug=<city_slug>  (+ X-CSRFToken)
Headers: X-CSRFToken

Response 200: {"ok": true}
  Set-Cookie: preferred_city=<city_slug>; Max-Age=31536000; HttpOnly; SameSite=Lax; Secure (prod); Path=/
  If authenticated: User.preferred_city = <City(slug)> is saved (200 still returned)

Response 400: {"error": "invalid_city"}
  (unknown or missing slug)
Response 405: (GET not allowed)
```

### 8.2 Cookie/DB read (new — T-02 + T-04/T-05)

```
GET /search/?q=<query>          (no ?city=)
GET /                           (root catalog)
GET /category/<slug>/           (category listing, no city)
Cookies: preferred_city=<city_slug>

→ PreferredCityMiddleware:
   if request.user.is_authenticated and request.user.preferred_city_id:
       request.preferred_city = request.user.preferred_city.slug   # DB wins
   else:
       request.preferred_city = <cookie slug if City exists else None>
→ search()/listings(): current_city = explicit_param or request.preferred_city or None
→ results filtered by city_id; stale → None (no filter) + cookie deleted in process_response
```

### 8.3 Login sync (new — T-06)

```
POST /login_status?token=<raw_token>   → auth_login(request, user) (consent.py:285)

→ After auth_login, for the JUST-authenticated user:
   cookie_slug = request.COOKIES.get("preferred_city")  (validated against City)
   if user.preferred_city_id is None and cookie_slug is valid:
       user.preferred_city = City(slug=cookie_slug); user.save(update_fields=["preferred_city"])
   elif user.preferred_city_id is set:
       (cookie already = user.preferred_city.slug from last click; no overwrite needed)
   # Cookie is NOT deleted — it remains the anonymous-session fallback (D-8/D-9).
```

### 8.4 Logout (unchanged behavior, clarified — R-09)

```
POST /logout/   → django.contrib.auth.logout(request) (logout.py:23)
   - Session flushed (anonymous thereafter)
   - preferred_city cookie RETAINED (not cleared) — serves next anonymous session
```

### 8.5 Header city button (new — T-07)

```
GET /, /category/<slug>/, /city/<slug>/, /search/?q=...   (any page rendering header_catalog.html)

→ Context gains: preferred_city_display (localized name or "Вся страна"), cities (queryset)
→ Header renders: 📍 <preferred_city_display> ▾
→ Dropdown: Montenegro cities (ordered by name); click → POST /api/preferred-city/ + navigate /city/<slug>/
```

### 8.6 Stale cookie (new — R-10 / T-08)

```
GET /search/?q=...
Cookies: preferred_city=deleted-city-slug

→ Middleware: City.objects.filter(slug=deleted-city-slug).exists() → False
   request.preferred_city = None
   process_response: response.delete_cookie("preferred_city")
→ View: no city filter (all cities)
```

---

## 9. Acceptance Criteria

### AC-1: Authenticated priority — DB wins over cookie
- Given a registered buyer with `User.preferred_city = Podgorica` and `preferred_city` cookie = `budva`
- When they visit `/search/?q=велосипед` (no `?city=`)
- Then results are filtered to **Подгорица** (DB wins), not Будва

### AC-2: Guest priority — cookie is the default
- Given an anonymous buyer with `preferred_city` cookie = `podgorica`
- When they visit `/` (root catalog)
- Then results are filtered to Подгорица

### AC-3: Explicit city always overrides
- Given a buyer (auth or anon) with preferred city = `podgorica`
- When they visit `/city/budva/` or `/search/?q=x&city=budva`
- Then results are filtered to **Будва**, and `User.preferred_city` / cookie are **not** overwritten by the visit (only an explicit city-selection action writes)

### AC-4: Stale cookie ignored and cleared
- Given a buyer with `preferred_city` cookie = `old-city` (city deleted from DB)
- When they visit any catalog page
- Then no city filter is applied (all cities) and the `preferred_city` cookie is deleted in the response

### AC-5: Selecting a city persists for auth + guest
- Given an authenticated buyer
- When they click city "Будва" in the header dropdown (or autocomplete)
- Then `User.preferred_city = Будва`, cookie = `budva` (1-year), and results show Будва

### AC-6: Login migrates guest preference
- Given an anonymous buyer with cookie = `podgorica` who logs in with a `User.preferred_city = NULL`
- When login completes
- Then `User.preferred_city` is backfilled to Подгорица (cookie retained)

### AC-7: Logout retains cookie as anonymous fallback
- Given a registered buyer with `User.preferred_city = Podgorica` and cookie = `podgorica`
- When they log out
- Then the cookie is retained; a subsequent anonymous visit to `/` still defaults to Подгорица

### AC-8: Header city button renders
- Given any catalog/detail page
- Then the header shows `📍 <city> ▾` (the effective preferred city, localized) or a country-wide label when unset
- And the dropdown lists Montenegro cities

### AC-9: No `UserProfile` model created
- `apps/users/` contains only `User` + `LoginToken` (no `UserProfile`). `makemigrations --check` produces exactly one migration (`0003_user_preferred_city`).

### AC-10: `preferred_city` ≠ `SavedSearch.city`
- A `SavedSearch` saved with `city = Будва` keeps alerting on Будва ads even if the buyer's `User.preferred_city` is Подгорица (and vice-versa). They are independent fields.

---

## 10. Risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| **Header city button adds UI surface** (Spec_014 didn't specify a header badge) | Medium | Medium | Follow Avito Pattern A (small badge, dropdown); reuse existing city queryset; keep Spec_014's shared-header include intact |
| **Fire-and-forget fetch race** (`header_catalog.html:239`) | High | Low | URL path carries the slug so first landing filters correctly without the cookie; cookie read-back is for *subsequent* navigations. Future `await` fix (out of scope) |
| **Spec_016 conflict** (it mandates "no schema changes, `makemigrations --check` clean") | Resolved | High | This spec explicitly supersedes Spec_016 AC-6/R-106 — one nullable FK migration is introduced; `makemigrations --check` will show exactly one new migration |
| **Spec_014 conflict** (§8.3/T6 specify `UserProfile.preferred_city`) | Resolved | High | This spec supersedes Spec_014 §8.3 and T-06 — FK goes on `User` directly, no `UserProfile` |
| **Stale cookie serves a deleted city** | Low | Low | Middleware validates on every read; `SET_NULL` + `except City.DoesNotExist` are second/third lines of defense |
| **DB lookup per request** (cookie + optional `User.preferred_city` access) | Medium | Low | `User.preferred_city` is a `select_related`-able FK loaded with the auth user; cookie slug validation is one indexed `City` lookup, cacheable if profiling shows cost |
| **Cookie name StrEnum vs. constant** rule tension | Low | Low | Follow proven precedent (`LANGUAGE_COOKIE_NAME`/`CONSENT_COOKIE_NAME` — module constants, not StrEnum); rejected StrEnum per §7.3 |
| **Cross-browser divergence** (cookie on one browser, DB from another) | Low | Low | Resolved by priority: DB wins for authenticated — the DB value is always authoritative when present, so cross-browser is consistent |
| **`listings()` doesn't pass `cities` to template** (pre-existing) | Low | Medium | T-07 must add `cities` queryset to `listings()` context so the header dropdown renders. (Currently only `search.py:175` passes it.) |

---

## 11. Open Questions (pending PO confirmation)

> Recommended defaults are assumed in this spec so it is implementation-ready. Confirm or override before final sign-off.

- **Q-1 (DEFAULT CITY):** When no preference exists (new visitor, no cookie, not registered), what is the fallback? *(Decision_018 §"Город по умолчанию")*
  - **A (assumed):** All cities / country-wide (no filter) — matches existing behavior and Avito/OLX/Mobile small-market defaults.
  - **B:** A specific seeded default city (e.g., Подгорица). Requires a seed/catalog data decision + a fallback when that city is removed.
  - Recommended default: **A**.

- **Q-2 (DEFAULT-LABEL WORDING):** When the city button has no preference, what text/localization is shown? *(Decision_018 never named it.)*
  - **A (assumed):** "Вся страна" (Russian) / "Це цело" (Montenegrin, per research §13.4) — country-wide.
  - **B:** Leave the button label empty / show only the dropdown arrow.
  - Recommended default: **A**, localized via existing `get_name` i18n.

- **Q-3 (QUERY-TEXT CITY EXTRACTION):** When a buyer searches free text containing a city name (e.g. "квартира Будва") with `preferred_city = Подгорица` and no explicit `?city=`/`/city/` param, should the system extract "Будва" from the query and override the preferred-city default? *(Decision_018 §"город не должен автоматически ломать поиск".)*
  - **A (assumed):** No — "explicit city" means URL path `/city/<slug>/` or `?city=` param only. Free-text queries still receive the preferred-city default filter. (Matches existing FTS architecture and Avito/OLX URL-driven city selection.)
  - **B:** Parse city names out of the search query (new query-text analysis feature). Higher effort; risks false positives.
  - Recommended default: **A** — keeps `preferred_city` a *default* while still letting an explicit URL/param override; query-text parsing is a separate future enhancement if the author finds A too aggressive.

- **Q-4 (PROFILE SURFACE):** Is the header city button the **only** way to set `User.preferred_city`, or is it also editable in a dedicated profile/cabinet page? *(Spec_017 "User Cabinet" is in flight.)*
  - **A (assumed):** Header city button only for this spec; a dedicated profile setting can be added later under Spec_017.
  - **B:** Add a "Preferred city" field to the user cabinet profile page.
  - Recommended default: **A** (avoids scope creep; the button is the Avito-style single-tap setter).

---

## 12. Out of Scope

- **Geo-IP auto-detection** — not in MVP scope (Decision_018 §6; report §13). If a default city is ever wanted, a future geo-IP task would own it.
- **Free-text city parsing in queries** — per Q-3/A (no query-text extraction). The FTS query (`search.py`) keeps searching title/description only.
- **Full Avito-modal city picker** — Montenegro has ~30 cities; an inline dropdown/combobox (Pattern A minimal badge) suffices. No modal.
- **Saved-search city coupling** — `preferred_city` and `SavedSearch.city` are explicitly independent (D-10); saved-search alert re-scoping is a separate task.
- **Frontend fetch `await` fix** — the `header_catalog.html:239` race is a separate frontend concern (documented in §5.2 / Spec_016 risk).
- **Cookie-based UI badge read in JS** — the cookie is HttpOnly; the header badge is populated **server-side** from the middleware-resolved value, not from `document.cookie`.
- **Bot-side changes** — the bot does not read/write `preferred_city`; buyers set it on the web. No aiogram work.

---

## 13. Dependencies (cross-reference)

| Dependency | Role | Location |
|---|---|---|
| `apps/users/models.py` (`User`) | Add `preferred_city` FK | T-01 |
| `apps/locations/models.py` (`City`) | Validate cookie/D-B slug; `slug` unique | T-02, T-04, T-05 |
| `apps/core/middleware/language.py` | Structural precedent for middleware + tests | T-02 |
| `config/settings/base.py` (MIDDLEWARE + TEMPLATES context processors) | Register middleware; context for header | T-02, T-07 |
| `apps/search/views/preferred_city.py` | Extend write side (1yr + DB write) + shared constants | T-03 |
| `apps/search/views/search.py` (line 70, 95-100, 161-179) | Cookie/DB default fallback | T-04 |
| `apps/ads/views/listings.py` (lines 300-323, 420) | Cookie/DB default fallback + context | T-05 |
| `apps/users/views/consent.py` (line 285 `auth_login`) | Login sync hook | T-06 |
| `apps/users/views/logout.py` | Confirm cookie retained on logout | T-06 |
| `templates/components/header_catalog.html` | Add city button + pass `cities`/`preferred_city_display` | T-07 |
| `apps/core/context_processors.py` (`header_context`) | Optionally expose resolved preferred city to header | T-07 |
| `apps/search/models.py` (`SavedSearch.city`) | Confirm independence | D-10 (no change) |
| `templates/components/language_switcher.html` | UI pattern precedent for `data-*` vanilla JS toggles | T-07 |

---

## 14. Definition of Ready

This specification is implementation-ready when:

1. **Q-1 through Q-4 are resolved** (recommended defaults marked above are accepted, or PO overrides).
2. The implementation team has:
   - This spec (`18_preferred-city_spec.md`)
   - `.ai/problems/Decision_018.md` (the approved hybrid decision)
   - `.ai/research/16_preferred-city_readback_report.md` §1–§6 (codebase findings)
   - `docs/07-design-researches/Design_03/city-selection-report.md` (OLX/Avito patterns)
   - The superseded specs `16_preferred-city_spec.md` and `14_catalog-ui-avito_spec.md` §8.3/T6 for context on what is superseded.
3. The test environment is available: `docker compose --project-name mko-bazuna-test -f docker-compose.yml -f docker-compose.test.yml up -d db` (PostgreSQL 18 on port 5433).
4. `makemigrations --check` baseline is clean (one new migration `users.0003_user_preferred_city` is *expected* from T-01).
5. The build order (§3) is agreed: T-01 → T-02 → T-03 → (T-04 ∥ T-05 ∥ T-07) → T-06 → T-08.

---

*Spec compiled from `.ai/problems/Decision_018.md` (revised hybrid decision), the existing codebase (`preferred_city.py`, `header_catalog.html`, `search.py:70`, `listings.py:304-323`, `apps/users/models.py`, `apps/locations/models.py`, `core/middleware/language.py`, `consent.py:285`, `logout.py:23`), the two Researcher reports (`.ai/research/16_preferred-city_readback_report.md` and `docs/07-design-researches/Design_03/city-selection-report.md`), and the superseded `16_preferred-city_spec.md` / `14_catalog-ui-avito_spec.md`. All findings read directly from the repository or live DOM inspection.*
