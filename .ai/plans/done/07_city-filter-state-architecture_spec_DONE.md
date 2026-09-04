---
id: 07-city-filter-state-architecture
domain: spec
tags:
  - city-filter
  - badge
  - state-management
  - htmx
  - cookie
  - architecture
source_problem: .ai/problems/Problem_04.md
replaces: commit c3fa2ae (masking fix)
related:
  - search-patterns
  - filter-ui
  - technical-specification
  - architecture-structure
---

# Specification: City-Filter State Architecture (Badge Off-By-One on "Entire Country")

**Status:** Draft (analytical, implementation-ready)
**Version:** 1.0
**Date:** 2026-09-04
**Source problem:** `.ai/problems/Problem_04.md` (RU: *«Смена города работает не корректно при возврате к значению вся страна — url меняется, но в самой кнопке/выпадающем списке остается предыдущее значение»*)

> **TL;DR.** The header city badge lags one selection. A prior fix (commit `c3fa2ae`) made the badge read `request.current_city` on two views, which only masks the real defects: (1) the preferred-city persistence is a **fire-and-forget `fetch` followed by an immediate full-page navigation**, so the `Set-Cookie`/`delete-Cookie` header is routinely aborted before it lands; (2) `delete_cookie()` is called **without matching attributes**, so a `Secure` cookie is never actually removed on this HTTPS site; (3) effective-URL-city is resolved **per-view in only 2 of 3 header-rendering views**, so `ad_detail` degrades to the lagging preference. The proper architecture: **centralize URL-city resolution in middleware**, **synchronize persistence (`await`) with navigation**, and **mirror cookie-delete attributes to the set attributes**.

---

## 1. Problem Statement

When a buyer interacts with the catalog header city dropdown:

1. **Land on `/`** → badge shows **«Вся страна»** (Entire country). ✔ correct.
2. **Select «Бар»** → URL becomes `/city/bar/`, badge shows **«Бар»**. ✔ correct.
3. **Select «Entire country»** → URL becomes `/`, but the badge **still shows «Бар»** (the previous selection). ✘ *bug.*

The badge shows the **previous** selection: it is off-by-one relative to the URL. The user reports: *«url меняется, но в самой кнопке/выпадающем списке остается предыдущее значение»* (the URL changes, but the button/dropdown keeps the previous value).

**Scope of impact.** The bug is the city *badge* on the catalog header (`components/header_catalog.html`, `data-preferred-city-label`). The header (with the badge) is rendered on exactly two pages (verified): the listings/search page (`ads/list.html` L23 → `listings`/`search` views) and the ad-detail page (`ads/detail.html` L28 → `ad_detail` view). All other pages use `components/header.html`, which has no city badge.

---

## 2. Facts (Verified Against Code & Runtime)

### 2.1 The masking fix and why it is insufficient

Commit `c3fa2ae` applied three changes:

| Change | Location | Effect |
|---|---|---|
| `listings.py` L325 | `request.current_city = effective_city` | Exposes URL-city on the catalog page |
| `search.py` L94 | `request.current_city = current_city` | Exposes URL-city on the search page |
| `context_processors.py` L63-74 | `header_context` iterates `(request.current_city, request.preferred_city)` | Badge prefers the URL-city over the preference |

This fixes *selecting* a specific city (step 2) because `/city/bar/` sets `current_city="bar"` and the URL is ahead of the cookie. **It does not fix step 3 (clear→`/`)** because:

- On `/`, no city is in the URL, so `effective_city` falls back to `request.preferred_city` (the cookie). The badge therefore still reads the **cookie**, and the cookie is stale (see 2.2/2.3).
- `ad_detail` (the other header-rendering view) **never sets `request.current_city`** (`ads/views/listings.py` L45-99), so its badge falls straight through to the lagging `request.preferred_city`.

### 2.2 Root cause #1 — fire-and-forget persistence race

`header_catalog.html` city handlers perform a bare, non-awaited `fetch(POST)` and then immediately assign `window.location.href`:

- Autocomplete city suggestion — `header_catalog.html` L362-367: `fetch(POST preferred_city)` then `applyCityFilter(slug)`.
- City dropdown option — `header_catalog.html` L583-589: `fetch(POST preferred_city)` then `applyCityFilter(slug)`.
- "Entire country" clear — `header_catalog.html` L573-581: `fetch(POST preferred_city, action=clear)` then `applyCityFilter(null)`.

`applyCityFilter()` (`header_catalog.html` L229-248) ends with **`window.location.href = url.toString()`** — a *synchronous, full-page* navigation (NOT an HTMX `htmx.ajax` call; the only `htmx.ajax` in the file is the favorites badge at L628). A synchronous `window.location.href` **aborts in-flight fetches**, so the browser frequently discards the `Set-Cookie` / deletion `Set-Cookie` header before it is applied. `PreferredCityMiddleware` then reads the **stale** preference on the next page.

> Researcher-report note (corrected): the report described `applyCityFilter` as calling `htmx.ajax('GET', …)` — this is inaccurate. The city flow uses `window.location.href` (full navigation); `htmx` is not involved in city selection. The race mechanism (un-awaited `fetch` + immediate navigation) is nonetheless real and is the dominant cause.

### 2.3 Root cause #2 — `delete_cookie` attribute mismatch

`apps/search/views/preferred_city.py`:

- **Set** (consent-gated), `src/backend/apps/search/views/preferred_city.py` L77-85:
  `response.set_cookie(..., samesite="Lax", httponly=True, secure=request.is_secure())`
- **Delete** (unconditional), `src/backend/apps/search/views/preferred_city.py` L51:
  `response.delete_cookie(PREFERRED_CITY_COOKIE_NAME)` — **no `samesite`, no `secure`, no `httponly`**.

Verified against the project's pinned Django 5.2: `django/http/response.py` L292-308 — `delete_cookie` only sets `secure=True` for `__Host-`/`__Secure-` prefixed names. `preferred_city` is **not** prefixed, so on this HTTPS deployment (nginx TLS termination per `architecture-structure.md` §Deployment; `SECURE_SSL_REDIRECT=True`, `base.py`) the deletion `Set-Cookie` is emitted **without `Secure`**, and browsers will **not** delete a `Secure` cookie via a non-`Secure` `Set-Cookie`. The "Entire country" clear therefore frequently fails to remove the cookie, so `request.preferred_city` keeps the stale city on `/`.

### 2.4 Root cause #3 — scattered, incomplete effective-city resolution

`request.current_city` is assigned in only two views (`listings.py` L325, `search.py` L94). The effective-URL-city logic itself is also **duplicated** — `listings.py` parses it from `city_slug` (path) / `request.GET["city"]` (L293-303); `search.py` parses it from `request.GET.get("city")` (L81-82). There is no single place that says "what the URL says the city is," so every view that renders the badge must remember to set it. `ad_detail` does not → badge reverts to the cookie.

### 2.5 Why "returning to Вся страна" specifically reproduces

Trace of the user's step 3 under the masking fix:

1. Click «Entire country» → `fetch(POST action=clear)` (un-awaited) → `applyCityFilter(null)` → navigates to `/`.
2. The `fetch` is aborted by the navigation; the deletion `Set-Cookie` does not land (race §2.2), and even if it did, its attributes don't match (§2.3), so the `preferred_city` cookie **persists** as `"bar"`.
3. On `/`, `listings()` finds no city in the URL → `effective_city = request.preferred_city = "bar"` → `request.current_city = "bar"`.
4. `header_context` → badge = «Бар». ✘

---

## 3. Confirmed Requirements

These are **confirmed by existing specification** (not invented) and define correct behavior:

| ID | Requirement | Source |
|---|---|---|
| CR-1 | The header city badge always reflects the **effective** city the ads are currently filtered by: explicit URL city (`/city/<slug>/` or `?city=`) → the buyer's persisted preferred city (default) → «Entire country». | `search-patterns.md` L157 «The header city button shows `preferred_city_display`…»; `filter-ui.md` L340-346 (explicit URL overrides default) |
| CR-2 | The badge must be in lock-step with the URL and the ad filter (no off-by-one after selecting *or* clearing a city). | Problem statement (this document) |
| CR-3 | The persisted preferred city is the **default filter** on listings/search only when the URL carries **no** explicit city. Authenticated buyers use `User.preferred_city` (DB FK); anonymous buyers use the consent-gated `preferred_city` cookie; otherwise country-wide. | `technical-specification.md` G L126-133; `architecture-structure.md` Middleware table |
| CR-4 | Selecting «Entire country» clears the persisted preferred city (cookie for guests, `User.preferred_city` FK for authenticated) so the next country-wide page shows «Entire country» and country-wide ads. | `preferred_city.py` L49-58 (clear = delete cookie + clear FK) — must be made *reliable* |
| CR-5 | Cookie write/delete must be **synchronous** with the resulting navigation so preference state is correct on the page the buyer lands on. | Derived from root cause §2.2/§2.3 (the bug class) |
| CR-6 | `request.current_city` must resolve consistently on **every** page that renders the catalog header (listings/search *and* ad-detail). | Derived from root cause §2.4 |
| CR-7 | An unknown/invalid city slug (`?city=x` or `/city/x/`) yields no filter + a did-you-mean suggestion; the badge falls through to the preferred default / «Entire country». | `listings.py` L298-320; `search.py` L84-89; `filter-ui.md` F-5/F-6 |
| CR-8 | No new i18n strings; the «Entire country» label is already `gettext("Entire country")` and city names via `City.get_name(locale)`. | `context_processors.py` L63; `header_catalog.html` L64 |

### Acceptance (behavioral, end-to-end)

| # | Given | When | Then |
|---|---|---|---|
| A1 | Buyer on `/` (no cookie) | observes badge | «Entire country», ads country-wide |
| A2 | Buyer selects «Бар» | lands on `/city/bar/` | badge «Бар», ads filtered to Bar |
| A3 | Buyer on `/city/bar/`, picks «Entire country» | lands on `/` | badge «Entire country», ads country-wide |
| A4 | Buyer (consented guest) selects «Бар» then immediately «Беране» | lands on `/city/berane/` | badge «Беране» (not «Бар») |
| A5 | Buyer on an ad detail `/<id>/` (no explicit URL city) | badge shows preferred default or «Entire country» (consistent with homepage, not a stale selection) | |
| A6 | Anonymous buyer with no `consent_preferences` | selects a city then clears | no cookie is ever written/read; badge still follows the URL city |
| A7 | Authenticated buyer | selects «Бар» then clears | badge «Entire country» after clear; DB FK cleared |

---

## 4. Conceptual Development Tasks

### Task T1 — Centralize effective-URL-city resolution (request layer)

- **Purpose:** Resolve *once per request*, before any view or context processor runs, the city the URL explicitly encodes (`/city/<slug>/` path or `?city=` query param). Expose it as `request.current_city` so every header-rendering page — listings, search, and `ad_detail` — has a single, race-free source of truth for the *explicit* URL city.
- **Expected outcome:** A new `CityResolutionMiddleware` (inserted in `base.py` MIDDLEWARE at L132-133, before `PreferredCityMiddleware`) that sets `request.current_city = <slug> | None` from `request.path` + `request.GET`, on every request. The listings/search views no longer parse the URL city themselves and no longer assign `request.current_city`. `ad_detail` needs no change (gets it from middleware).
- **Dependencies:** None.
- **Evidence:** `base.py` L125-136 (insertion point); `PreferredCityMiddleware` (`middleware/preferred_city.py`) is the established pattern for attaching `request` attributes.

### Task T2 — Refactor listings/search to read URL-city from the request layer

- **Purpose:** Replace the duplicated URL-city parsing in `listings()` (L293-303) and `search()` (L81-82) with a read of `request.current_city` (now set by middleware). Preserve the **preferred-city fallback for the ad queryset** (the filter default) — only the *explicit* URL-city source moves to middleware; the `preferred_city` fallback for filtering is unchanged.
- **Expected outcome:** `effective_city = request.current_city or getattr(request, "preferred_city", None)` in both views; `request.current_city` is no longer reassigned in the views (it comes from middleware). The badge (context processor) reads the same chain.
- **Dependencies:** T1.
- **Files:** `ads/views/listings.py` L287-325; `search/views/search.py` L79-94.

### Task T3 — Synchronize persistence with navigation

- **Purpose:** Eliminate the fire-and-forget race by **awaiting** the `preferred_city` POST before navigating, and by making cookie *deletion* use attributes that actually remove the cookie.
- **Expected outcome (two sub-changes):**
  - `header_catalog.html`: wrap the three `fetch(POST …)` call sites (L366, L578, L588) so navigation runs **after** the response is received (`await fetch(...).catch(...)`), then `window.location.href`. The `Set-Cookie`/`Set-Cookie(deletion)` header is applied before the browser issues the navigation request. (Try/catch preserves navigation on network error — the URL city still drives the badge.)
  - `preferred_city.py` L51: `response.delete_cookie(PREFERRED_CITY_COOKIE_NAME, samesite="Lax", secure=request.is_secure(), httponly=True)` — mirror the `set_cookie` attributes (L77-85) so a `Secure` cookie is actually deleted on HTTPS.
- **Dependencies:** None (independent of T1/T2).
- **Files:** `components/header_catalog.html` (script block ~L544-592); `search/views/preferred_city.py` L49-58.

### Task T4 — Guard badge read when current_city is absent (defense in depth)

- **Purpose:** Ensure the context processor's badge chain is robust even if a future view forgets to be covered — keep `header_context`' iterating `request.current_city` → `request.preferred_city` → «Entire country», but make the *clear* flow unambiguous.
- **Expected outcome:** `context_processors.py` `header_context` (L63-74) is retained as-is (it already prefers `current_city`); the fix is that `current_city` is now *always* correct (T1) and `preferred_city` is now *always* up to date (T3). No behavior change; add a unit test asserting the fallback order with explicit `current_city=None`.
- **Dependencies:** T1.
- **Files:** `core/context_processors.py`; `core/tests/test_context_processors.py`.

### Task T5 — Tests

- **Purpose:** Lock in the corrected behavior and prevent regression of the masking-vs-architecture regression pattern.
- **Expected outcome (new/updated tests):**
  - `CityResolutionMiddleware` unit test: `/city/budva/` → `current_city="budva"`; `/?city=budva` → `current_city="budva"`; `/` → `None`; stale `preferred_city` cookie does **not** appear in `current_city`.
  - `ad_detail` integration: badge reflects URL/preferred state consistently with the homepage (regression guard for the T1 gap).
  - End-to-end-style readback tests for A3 (clear→`/` shows «Entire country» + country-wide) and A4 (Bar→Беране, badge «Беране»).
  - `preferred_city` view test: `delete_cookie` is invoked with `samesite="Lax", secure=True` (assertion on response cookie attributes) when the request is secure.
  - Update the existing `TestCityBadgeReadback` (`apps/search/tests/test_preferred_city_readback.py`) if its assertions assume the view-set `current_city` (they should still pass under the middleware model).
- **Dependencies:** T1, T3.
- **Files:** new `core/tests/test_city_resolution_middleware.py`; `apps/search/tests/test_preferred_city.py`; possibly `apps/ads/tests/test_detail_context.py`.

### Task T6 — Documentation

- **Purpose:** Reflect the authoritative city-resolution flow so future agents do not reintroduce per-view `current_city` assignments.
- **Expected outcome:** Update `architecture-structure.md` (Middleware table, §"Middleware & context processors") and `search-patterns.md` (§"Preferred City") to state: effective-URL-city is resolved in `CityResolutionMiddleware` → `request.current_city`; the preferred city is a *filter default only*, exposed as `request.preferred_city`; the badge is `current_city` → `preferred_city` → «Entire country»; persistence is awaited and `delete_cookie` mirrors `set_cookie`.
- **Dependencies:** T1, T3.
- **Files:** `docs/01-spec/architecture-structure.md`, `docs/01-spec/search-patterns.md`.

### Task dependency graph

```
T1 (middleware) ──► T2 (views read from request layer) ──► T5 (tests)
                └─► T4 (context-processor guard) ───────► T5
T3 (sync persistence + delete_cookie) ────────────────► T5
T1,T3 ───────────────────────────────────────────────► T6 (docs)
```

---

## 5. Product Owner Decisions

All decisions below are **confirmed by existing specification / product intent** (not invented here). The rejected alternative is documented to justify the chosen architecture.

| Q | Decision | Confirmed by | Rationale / rejected alternative |
|---|---|---|---|
| D1 | The badge is **coupled** to the effective city: explicit URL city → preferred default → «Entire city». It is **not** decoupled to "URL-only". | `search-patterns.md` L157; `filter-ui.md` L340-346 | Decoupling the badge to "URL-only" would make the badge say «Entire country» on the homepage of a buyer whose preferred city is still applied as the ad filter — a badge/filter mismatch that is *more* confusing than the current bug. Fixing reliability (T3) makes the coupled behavior correct. |
| D2 | The homepage / category pages keep the **preferred city as the default ad filter** when the URL has no explicit city. | `search-journeys.md` L76 «City = preferred (or country-wide)»; `search-patterns.md` L128-141; `technical-specification.md` G L126-130 | This is the spec-intent ("Preferences survive context loss"). The user's *«по умолчанию — вся страна»* describes the no-preference (fresh) state, which is consistent. |
| D3 | Selecting «Entire country» **permanently clears** the preferred city (cookie for guests, `User.preferred_city` FK for authenticated). | `preferred_city.py` L49-58 (existing clear behavior) | Matches the explicit-intent of the «Entire country» button and makes A3/A6 hold. Transient clear (keep preference) would re-show the previous city on `/` — the very bug being fixed. |
| D4 | Cookie write/delete is **synchronized with navigation** (await `fetch` before `window.location.href`). | N/A (new — architectural requirement) | Without this the race (§2.2) cannot be closed; it is the core of "make it work correctly." |
| D5 | `delete_cookie` **mirrors `set_cookie` attributes** (`samesite="Lax", secure=request.is_secure(), httponly=True`). | Django `response.py` L292-308 + site is HTTPS | Without this a `Secure` cookie cannot be deleted on HTTPS (§2.3) — empirically breaks D3. |

### Gray area (no decision required — recorded as a constraint)

The user phrasing *«по умолиманию — вся страна»* could be read as a desire to **drop the preferred-city default on the homepage** entirely (always country-wide). Per D2 this is **not** adopted — it would contradict `search-journeys.md` L76 and US-B7 ("selected city saved in session"). If the Product Owner later decides to remove the homepage preferred-default, that is a **product** change to be specified separately; it is out of scope here.

---

## 6. Research Summary

A Researcher agent was tasked with investigating the architecture and modern best practices. Findings were **verified against the code** where they concerned the live behavior; one inaccuracy was corrected.

### 6.1 Verified findings

| # | Finding | Verdict | Evidence |
|---|---|---|---|
| R1 | Effective-URL-city is set in only `listings()` (L325) and `search()` (L94); `ad_detail` does not. | **Correct, scope narrowed:** only `ad_detail` is the gap — `header_catalog.html` (the only template with the badge) is included solely by `ads/list.html` L23 and `ads/detail.html` L28. Dashboards/cabinet/etc. use `header.html` (no badge). | `grep` for `header_catalog` includes + `request.current_city` assignments |
| R2 | The clear flow calls `response.delete_cookie(...)` **without** `samesite`/`secure`/`httponly`, while `set_cookie` (L77-85) has them. | **Confirmed + strengthened:** on HTTPS, the deletion `Set-Cookie` is non-`Secure`, so it cannot remove the `Secure` cookie. Verified Django `response.py` L292-308 (only `__Host-`/`__Secure-` names auto-set `secure`). | `preferred_city.py` L51 vs L77-85; Django source L292-308 |
| R3 | City navigation uses `window.location.href` (full navigation), **not** `htmx.ajax`. | **Corrected:** the report said `applyCityFilter` calls `htmx.ajax('GET', …)`; it actually calls `window.location.href` (header_catalog.html L247). The only `htmx.ajax` is the favorites badge (L628). | `header_catalog.html` grep: `htmx.ajax` only at L628 |
| R4 | The persistence `fetch` is fire-and-forget (no `await`) before navigation. | **Confirmed.** `fetch(POST…)` at L366/578/588 with no `await`/`.then`, immediately followed by `applyCityFilter()` → `window.location.href`. | `header_catalog.html` L366, L578, L588 |
| R5 | `django-htmx` is a dependency and `django_htmx` is in MIDDLEWARE; HTMX headers (`HX-Redirect`, `HX-Location`, `HX-Push-Url`) are available for server-driven navigation. | Confirmed (use as context for alternative approaches, not adopted). | `base.py` L103, L132 (LanguagePre uses it); `pyproject.toml` |

### 6.2 Best-practice alignment

- **"URL is the source of truth for UI/display state"** (django-htmx / django-htmx-nav): the display label should be derivable from the URL without depending on async side-effect writes. The chosen architecture honors this by (a) centralizing URL-city parsing in middleware (T1) so the badge never needs the cookie, and (b) making the cookie a *filter default* (not a display source) and *synchronizing* its writes (T3) so the homepage default is reliable.
- **Server sets state then redirects in one atomic response** (HTMX `HX-Redirect`): considered (researcher Approach B) but **not adopted** because the city flow is plain-vanilla `fetch` + `window.location.href`, not HTMX-initiated; converting it to a full HTMX POST would be a larger, riskier surface change (touches the dropdown interaction model + `test_catalog_filters.py` link-count guards) for no behavioral gain over awaiting the existing fetch. Awaiting the fetch is the minimal, equivalent fix.
- **`delete_cookie` must mirror `set_cookie`** (Django docs): adopted directly (T3).

### 6.3 Approaches considered (ranked)

| Approach | What | Adopt | Why not the others |
|---|---|---|---|
| **A. Middleware resolution + synchronized persistence** (recommended) | `CityResolutionMiddleware` sets `request.current_city` from the URL on every request; views read it for the explicit city and keep `preferred_city` only as the filter fallback; badge = `current_city` → `preferred_city` → «Entire country»; `await fetch` + mirroring `delete_cookie`. | ✅ | Fixes all three root causes with minimal, spec-aligned surface. |
| B. Server-driven redirect (`HX-Redirect` on the POST) | Convert the city `fetch` to an HTMX POST whose response sets the cookie and carries `HX-Redirect` to the filtered URL. | ❌ consider later | Larger refactor of the dropdown JS; the existing cookie-attribute bug (§2.3) must be fixed regardless; higher test-guard churn. |
| C. Decouple badge from preference (badge = URL-only) | Badge shows URL city or «Entire country»; preferred city influences only the queryset. | ❌ rejected (D1) | Introduces badge/filter mismatch on the homepage default (D2); contradicts spec intent. |

---

## 7. Assumptions

1. The site is served over HTTPS with `Secure` cookies (nginx TLS per `architecture-structure.md`; `SECURE_SSL_RECORRECT=True`, `base.py`). This is why the `delete_cookie` attribute mismatch (§2.3) is a real defect.
2. Only `ads/list.html` (L23) and `ads/detail.html` (L28) include `components/header_catalog.html`; every other page uses `components/header.html` (no city badge). So the behavioral fix must cover `listings`, `search`, and `ad_detail`.
3. `/search/?city=<slug>` and `/?city=<slug>` and `/city/<slug>/` are all valid inputs; the middleware regex must match the path form (`/city/<slug>/`) and the query form (`?city=`), and must not match category paths (`/category/city-foo/`).
4. The `preferred_city` POST endpoint (`search:preferred_city`) may return non-2xx on CSRF/network failure; the awaited `fetch` must not block navigation on such failure (best-effort persistence, URL always drives the result).
5. No schema/migration changes are required — all changes are middleware, view, template-JS, and the cookie-setting view.
6. i18n strings are unchanged (the «Entire country» label and city names are already localized).

---

## 8. Constraints

| # | Constraint | How satisfied |
|---|---|---|
| C1 | `StrEnum` for fixed values; no plain-string constants | No new constants introduced; reuse `PREFERRED_CITY_COOKIE_NAME` module constant |
| C2 | No `print()`; proper logging | Any new middleware uses `logger = logging.getLogger(__name__)` |
| C3 | Vanilla JS only (no new frontend framework) | T3 uses `await fetch(…)` + `window.location.href` — existing pattern |
| C4 | i18n: `trans`/`blocktrans` in templates, `gettext` in Python; `ru`+`bs` non-empty | No new strings; run `makemessages`+`compilemessages`; `test_i18n_completeness.py` must pass |
| C5 | `djlint`-clean templates | Template edits pass `uv run djlint src/backend/templates/` |
| C6 | Lint + type-check clean on changed files | `uv run ruff check` + `uv run basedpyright` on touched files |
| C7 | Tests must not be distorted for the fix; tests encode correct behavior | T5 asserts A1–A7 (correct behavior); updated/added only |
| C8 | No DB schema/migration changes | Confirmed — all changes are app-layer |
| C9 | Tests run in Docker against PostgreSQL on port 5433; `make test` is the fast gate | All new tests placed under existing test paths and marked appropriately |
| C10 | Two-process deployment (web WSGI + bot aiogram), shared DB, migrations run once | No migration changes (C8); middleware JS runs client-side (no process concern) |

---

## 9. Risks

| # | Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|---|
| R1 | Middleware parses `request.path`/`request.GET["city"]` for a URL the router doesn't map to `listings` (e.g. a future `/city/`-prefixed non-listings route). | Low | Low | Regex `^/city/(?P<slug>[^/]+)/?$` only; `?city=` only affects the badge, not data, on non-catalog pages |
| R2 | Awaiting `fetch` blocks navigation for one network round-trip (~tens of ms local; variable remotely). | Low | Low | `await fetch(...).catch(=>undefined)` so navigation proceeds even on network/CSS/CSRF failure; URL city always wins the badge |
| R3 | `delete_cookie` attributes drift again from `set_cookie`. | Low | High | T3 mirrors attributes; T5 asserts the response cookie carries `secure`/`samesite=Lax`; consider a shared helper in T2/T3 follow-up |
| R4 | `CityResolutionMiddleware` ordering — if placed after `PreferredCityMiddleware`, `current_city` is unavailable to it (it isn't, but future readers may move it). | Low | Medium | Document insertion point (before `PreferredCityMiddleware`); T5 unit test asserts attribute presence |
| R5 | Badge on `ad_detail` now shows the URL city only when the URL has one; detail URLs (`/<id>/`) never do, so the badge shows the preferred default — behavior change from "stale cookie" to "preferred default". | Low | Low | This is the *correct* behavior (A5); document in changelog |
| R6 | Existing `TestCityBadgeReadback` (current session) asserts the view-set `current_city`; moving to middleware must not break them. | Medium | Medium | T5 re-runs `test_preferred_city_readback.py`; assertions target `response.context` and rendered badge, both preserved |

---

## 10. Open Questions

1. **(Resolved by D2 — not blocked.)** Whether the homepage preferred-default should ever be removed. Decision: keep (out of scope to change).
2. **Server-driven vs. awaited client redirect.** D4 chooses awaited `fetch`. If the team later migrates the city selector to a proper HTMX POST, `HX-Redirect` (researcher Approach B) becomes the cleaner path — but that is a separate enhancement, not required to fix the bug.
3. **Shared cookie-attribute helper.** Should `set_cookie`/`delete_cookie` for `preferred_city` be wrapped in one helper to prevent attribute drift (R3)? Recommended as a small follow-up in T3; not required for the fix.

---

## 11. Out of Scope

- **Decoupling the badge from the preferred-city default** (rejected approach C; see D1).
- **Changing the homepage/`/category/<slug>/` preferred-city default filter semantics** (D2 — preserved).
- **The category+city URL coexistence / header-JS navigation rewrite** — this is already specified and tracked separately in `.ai/problems/05_filter-regression_spec.md` (T5) and `.ai/problems/06_url-architecture-audit_report.md`. The city-badge bug is orthogonal to whether `/city/<slug>/` is used vs `?city=` (both set `current_city` identically under T1).
- **Language-switcher staleness / clear-all visibility / price-chip rendering** — separate problems (filter regression), out of scope.
- **Bot-side or DB schema changes.**
- **Replacing the closed city list or the did-you-mean (`difflib`) behavior.**

---

## 12. Definition of Ready

This specification is ready for implementation planning when:

1. ✅ The badge semantics decision is recorded (D1: coupled — confirmed by `search-patterns.md` L157).
2. ✅ All three root causes are traced to exact code with `file:line` (§2.2/§2.3/§2.4).
3. ✅ Each root cause is reproduced end-to-end against the codebase (§2.5) and confirmed the masking fix does not close it.
4. ✅ The architectural approach (centralize in middleware; synchronize persistence; mirror delete attributes) is chosen with rationale and rejected alternatives documented (§6.3).
5. ✅ Conceptual tasks are decomposed with purpose / expected outcome / dependencies and a dependency graph (§4).
6. ✅ Acceptance criteria (§3, A1–A7) are concrete and testable.
7. ✅ Constraints (no schema change, vanilla JS, i18n, two-process deploy, test-in-Docker) are documented (§8).
8. ✅ Risks and mitigations are documented (§9).
9. ✅ Out-of-scope items are explicit to prevent scope creep (§11).
10. ✅ The prior masking fix (`c3fa2ae`) is understood and superseded — the new design replaces per-view `request.current_city` assignment (T1) rather than extending it.

---

## 13. Affected-Artifact Index

| Artifact | Role |
|---|---|
| `config/settings/base.py` L125-136 | MIDDLEWARE insertion point (before `PreferredCityMiddleware`) |
| `src/backend/apps/core/middleware/` (new `city_resolution.py`) | T1: new `CityResolutionMiddleware` |
| `src/backend/apps/core/middleware/preferred_city.py` | Precedent for request-attribute attachment; unchanged in logic |
| `src/backend/apps/ads/views/listings.py` L287-325 | T2: read URL-city from `request.current_city`; drop L325 assignment |
| `src/backend/apps/search/views/search.py` L79-94 | T2: read URL-city from `request.current_city`; drop L94 assignment |
| `src/backend/apps/core/context_processors.py` L63-74 | T4: unchanged logic (verified correct once T1/T3 are in) |
| `src/backend/apps/search/views/preferred_city.py` L49-58, L77-85 | T3: fix `delete_cookie` attributes (L51) |
| `src/backend/templates/components/header_catalog.html` L362-367, L573-581, L578-588, L229-248 | T3: `await fetch` before `window.location.href` |
| `src/backend/apps/ads/urls.py` L24-27 | URL patterns for `/city/<slug>/` (no change needed) |
| `src/backend/apps/core/tests/test_context_processors.py` | T4/T5: coverage for fallback order |
| `src/backend/apps/search/tests/test_preferred_city_readback.py` | T5: regression guards A3/A4; keep passing under new design |
| `docs/01-spec/architecture-structure.md`, `docs/01-spec/search-patterns.md` | T6: document the authoritative resolution flow |
