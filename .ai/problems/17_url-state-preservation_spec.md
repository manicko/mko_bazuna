---
id: url-state-preservation
problem: "URL state (city, language) lost when navigating between categories; city dropdown and language dropdown not consistently linked to URL state"
source: ".ai/problems/Problem_01.md"
date: 2026-09-05
status: Signed-off (PO confirmed Q1=A, Q2=A, Q3=A, Q4=A)
---

# Specification 17 — URL State Preservation: City / Language / Category Navigation

> **Problem:** When a buyer navigates to a different category (via the header "All
> Categories" dropdown or autocomplete suggestion), the `lang` and `city` parameters
> disappear from the URL. Likewise, selecting a city via the header dropdown
> navigates to `/city/<slug>/`, discarding the active category path. The language
> and city dropdowns do not maintain a consistent, bidirectional link with the URL
> state.
>
> **Question posed:** *"Study modern practices and tell me, is this normal behavior?"*
> **Answer:** **No.** Modern classifieds (Avito, OLX, eBay) preserve all active filter
> state (language, city, category, sort, price, purpose, condition, features) across
> navigation. The URL is the source of truth — it must be shareable, bookmarkable,
> and back-button friendly. Losing state on category navigation is a UX defect.

---

## 1. Problem Statement

### 1.1 Symptom (translated from Problem_01.md)

> "We don't have correct linking between the URL and switching cities in the
> dropdown list and language in the dropdown list. When we navigate through
> different categories, the city and language from the URL disappear."

### 1.2 Three concrete failure modes

| # | Action | Expected URL | Actual URL (broken) | Root cause |
|---|--------|-------------|---------------------|------------|
| A | Buyer on `/category/electronics/?city=budva&lang=ru`, clicks "Transport" in the category dropdown | `/category/transport/?city=budva&lang=ru` | `/category/transport/` | `header_catalog.html` L97: `<a href="{% url 'ads:listings_category' cat.slug %}">` generates a bare path URL — no query params |
| B | Buyer on `/category/electronics/`, selects "Budva" in the city dropdown | `/category/electronics/?city=budva&lang=ru` | `/city/budva/` | `header_catalog.html` L562: `window.location.href = '/city/' + slug + '/'` — full-page navigation to a city-only path |
| C | Buyer on `/category/electronics/?city=budva&lang=ru`, switches language to Bosnian | `/category/electronics/?city=budva&lang=bs` | `/category/electronics/?lang=bs` | Category navigation (A) already dropped `city`; language switcher preserves what `request.GET` had at render time, but `request.GET` no longer has `city` because it was in the path (dropped by action A) |

### 1.3 Affected UI surfaces

All three are in the shared catalog header (`components/header_catalog.html`) and
breadcrumbs (`components/breadcrumb.html`), rendered on every catalog and detail page:

| Location | File:Line | Element | URL generated | Params dropped |
|----------|-----------|---------|---------------|----------------|
| Category dropdown (desktop) | `header_catalog.html:97` | `<a href="{% url 'ads:listings_category' cat.slug %}">` | `/category/<slug>/` | `lang`, `city`, `sort`, all filters |
| Category dropdown (mobile) | `header_catalog.html:180` | same | `/category/<slug>/` | `lang`, `city`, `sort`, all filters |
| Autocomplete city suggestion | `header_catalog.html:340` | `window.location.href = '/city/' + slug + '/'` | `/city/<slug>/` | category path, `lang`, all filters |
| Autocomplete category suggestion | `header_catalog.html:343` | `window.location.href = '/category/' + slug + '/'` | `/category/<slug>/` | `lang`, `city`, all filters |
| City dropdown selection | `header_catalog.html:562` | `window.location.href = '/city/' + slug + '/'` | `/city/<slug>/` | category path, `lang`, all filters |
| "Entire country" clear | `header_catalog.html:552` | `window.location.href = '/'` | `/` | **Bug:** Drops `lang` along with everything else. Should clear only `city`, preserving `lang` and other params. On root `/`, URL becomes `/?lang=ru`. |
| Breadcrumb ancestor link | `breadcrumb.html:18,31` | `<a href="{% url 'ads:listings_category' cat.slug %}">` | `/category/<slug>/` | `lang`, `city`, all filters |
| Did-you-mean city suggestion | `ad_list.html:27-28` | `{% url 'ads:listings_city' suggested_city %}` | `/city/<slug>/` | category path, `lang` |

### 1.4 What already works correctly

- **Language switcher links** (`language_switcher.html:35`): Uses `query_replace`
  which copies `request.GET` and overrides `lang`. Preserves all query params
  including `city`.
- **Language switcher post-swap staleness**: An `htmx:afterSwap` listener
  (`language_switcher.html:131-142`) already recomputes switcher hrefs from the
  live browser URL after HTMX partial updates, and drops `page`.
- **City dropdown via `applyCityFilter()`** (`header_catalog.html:229-248`): Uses
  `new URL(window.location.href)` and `url.searchParams.set('city', slug)` —
  correctly preserves the current path and all query params.
- **HTMX filter form** (`filter_form.html:5`): Submits via `hx-get="{{ request.path }}"`
  with hidden inputs for `q`, `category`, and `city` — preserves all state within
  the same path.
- **Chip removal / pagination links** (`ad_list.html`): All include explicit
  `&lang={{ LANGUAGE_CODE }}` and `&city={{ current_city }}` in both `href` and
  `hx-get` attributes, with `hx-push-url="true"`.
- **Clear-all link** (`ad_list.html:37-46`): Preserves `q` and `lang`, drops
  other filters (on listings page).

### 1.5 Why it is NOT normal behavior

Per the Researcher's analysis of leading classifieds platforms:

- **Avito** (`avito.ru`): URL hierarchy `/<city>/<category>/<subcategory>/` — city and
  category are always present together in the path. Navigating between categories
  preserves the city.
- **OLX** (`olx.pl` etc.): Country TLD carries geography; category in path; all
  filters (including language via separate domains) persist across navigation.
- **eBay**: Path for the primary resource, query params for all secondary filters
  (price, location, sort). Navigation between categories preserves all active
  filters.
- **Craigslist**: City is a subdomain; category is a path code; filters are query
  params. State is never lost on navigation.

No major classifieds platform drops language or city when a buyer switches categories.
The URL is the source of truth (search-journeys.md L53: *"URL state is the source of
truth"*).

---

## 2. Confirmed Requirements

### CR-1: Category navigation preserves all active URL state

**When** a buyer navigates to a new category via any UI path (header dropdown,
mobile menu, breadcrumb, autocomplete suggestion, did-you-mean link),

**Then** the language (`lang`), city (`city`), sort, and all active filter params
(purpose, condition, features, price range, page) are preserved in the URL.

**Priority:** High — primary user-facing defect.

### CR-2: City selection preserves the active category path

**When** a buyer selects a city via the header city dropdown or autocomplete
suggestion,

**Then** the category (if active in the path) is preserved and the city is applied
as `?city=<slug>` alongside the category path. The URL becomes
`/category/<slug>/?<existing params>&city=<slug>`.

**Priority:** High — same root cause as CR-1, bidirectional consistency.

### CR-3: "Entire country" clear preserves `lang` and all non-city filters on all pages

**When** a buyer clicks "Entire country" (clear city) on any page (category page,
filtered listings, or root `/`),

**Then** only the `city` parameter is removed; `lang`, and all other params are
preserved. On root `/`, the URL becomes `/?lang=ru` (city removed, language preserved).

**Priority:** Medium — consistency with CR-2.

### CR-4: Breadcrumb category links preserve URL state

**When** a buyer clicks a breadcrumb ancestor category link

**Then** `lang`, `city`, and all active filter params are preserved.

**Priority:** Medium — same class of bug as CR-1.

### CR-5: `lang` remains a query parameter

Language is represented as `?lang=<code>` in the URL (not path-based `/ru/`).

**Rationale:** `?lang=` is priority #1 in `LanguagePreMiddleware`; it is already
implemented, tested, and working. Path-based language prefixing would require
`i18n_patterns` and a full routing overhaul — out of scope.

**Priority:** High (confirmed constraint).

### CR-6: City can coexist with category as a query parameter

City is expressible as `?city=<slug>` alongside `/category/<slug>/` in the path.
The `?city=` form is a real filter on both listings and search pages (verified in
`listings.py:293-309` and `search.py:79-92`).

**Priority:** High (architectural prerequisite for CR-1/CR-2).

### CR-7: HTMX-driven partial updates never drop URL state silently

**When** a buyer applies filters, changes sort, paginates, or removes chips via HTMX,

**Then** the pushed URL (`hx-push-url="true"`) contains `lang` and `city` and all
other active params.

**Priority:** High — partially already works (chips/pagination in `ad_list.html`
include `lang`/`city`), but the header is outside the swap target.

### CR-8: Language switching drops `page`

**When** a buyer switches language,

**Then** the `page` parameter is not carried to the new language view (avoids landing
on an empty/nonexistent page). This is already implemented in
`language_switcher.html:135` (`params.delete('page')`).

**Priority:** Low (already implemented; included for completeness).

---

## 3. Conceptual Development Tasks

### Task 1 — Server-side URL construction for category navigation links

- **Purpose:** Make every category-link navigation (header dropdown, mobile menu,
  breadcrumbs, did-you-mean) emit a URL that includes the current `lang`, `city`,
  and all active filter params alongside the category path.
- **Expected outcome:** Category links render as `/category/<slug>/?<lang=...&city=...&...>`.
  No URL state is lost on category navigation.
- **Files:** `header_catalog.html` (L97, L180), `breadcrumb.html` (L18, L31),
  `ad_list.html` (L27-28 did-you-mean).
- **Approach:** Use the existing `query_replace` template tag (or explicit
  `{% if LANGUAGE_CODE %}` blocks matching the pattern in `ad_list.html`) to build
  `?lang=X&city=Y` suffixes onto the reversed category URL.
- **Dependencies:** None — `query_replace` already exists (`dict_tags.py:47`).

### Task 2 — Replace hardcoded `/city/<slug>/` navigation with `?city=` on current URL; fix root clear behavior

- **Purpose:** Make city selection (dropdown + autocomplete) preserve the category
  path and all query params by using `URLSearchParams` to set `?city=<slug>` on the
  current URL, instead of hardcoding `window.location.href = '/city/' + slug + '/'`.
  Also fix the "Entire country" clear link (L552) to remove only the `city` query
  param while preserving `lang` and all other state on ALL pages (including root `/`,
  where the URL becomes `/?lang=ru`).
- **Expected outcome:** City selection keeps the category path intact; city is applied
  as a query param. "Entire country" clears only `city` on all pages (preserving `lang`
  and all other params).
- **Files:** `header_catalog.html` (L340 autocomplete city, L552 "Entire country"
  clear, L562 city dropdown, L229-248 `applyCityFilter`).
- **Approach:** Replace the three hardcoded path navigations with
  `url.searchParams.set('city', slug)` / `url.searchParams.delete('city')` on
  `new URL(window.location.href)`. Handle the edge case where the current path is
  already `/city/<old_slug>/` (replace the path segment rather than appending a
  query param that would be ignored). Update the "Entire country" clear to conditionally
  delete only `city` (or clear all if on root path `/`).
- **Dependencies:** Task 1 must be complete so category links carry `city` forward.

### Task 3 — Autocomplete category suggestion preserves URL state

- **Purpose:** Make the autocomplete category suggestion (in the JS `dropdown`
  handler) preserve `lang`, `city`, and all active params.
- **Expected outcome:** Clicking a category autocomplete suggestion navigates to
  `/category/<slug>/?<preserved params>` instead of `/category/<slug>/`.
- **Files:** `header_catalog.html` (L343).
- **Approach:** Replace the hardcoded `window.location.href = '/category/' + slug + '/'`
  with URL construction that appends existing query params.
- **Dependencies:** Task 1.

### Task 4 — Client-side HTMX safety net (global `htmx:configRequest` hook)

- **Purpose:** Guarantee that every HTMX-driven request carries `lang` from the
  current URL, as a safety net for any future HTMX navigations that might bypass
  the explicit server-side param construction.
- **Expected outcome:** All HTMX GET/XHR requests inherit `lang` from
  `window.location.search` automatically.
- **Files:** A shared JS file or inline script in `header_catalog.html` /
  `list.html` / `detail.html`.
- **Approach:** Add a `document.body.addEventListener('htmx:configRequest', ...)`
  handler that reads `lang` from `window.location.search` and injects it into
  `event.detail.parameters` if not already present.
- **Dependencies:** None — additive safety net.

### Task 5 — Client-side HTMX safety net for category/city links post-swap

- **Purpose:** After an HTMX swap updates the URL (e.g., pagination changes
  `?city=` or `?lang=`), the header category/breadcrumb links (rendered at initial
  page load) become stale. Add an `htmx:afterSwap` handler to recompute them from
  the live URL.
- **Expected outcome:** Category and breadcrumb links in the header always reflect
  the current URL query params, not the snapshot from initial page load.
- **Files:** `language_switcher.html` (extend existing `htmx:afterSwap` handler)
  or `header_catalog.html`.
- **Approach:** Extend the existing `htmx:afterSwap` handler (L131-142) to also
  recompute `[data-category-link]` hrefs from `window.location.search`.
- **Dependencies:** Task 4 (or can be combined).

### Task 6 — Test coverage for URL state preservation

- **Purpose:** Add regression tests for the URL state preservation behavior.
- **Expected outcome:** Tests asserting that category links, city selection, and
  language switching preserve each other's state.
- **Files:** `test_catalog_filters.py`, new integration test module.
- **Approach:**
  - **Template-level tests** (no DB): Assert that category/breadcrumb link
    `href` attributes in `header_catalog.html` / `breadcrumb.html` include
    `?lang=` and `&city=` when `LANGUAGE_CODE` / `current_city` are in context.
  - **View-level tests** (with DB): Assert that `/category/<slug>/?city=<city>&lang=ru`
    returns both filters applied.
  - **Browser-level test** (if Playwright available): Assert that clicking a
    category in the dropdown preserves `lang` and `city` in the URL.
- **Dependencies:** Tasks 1–3 must be complete for view-level assertions.

---

## 4. Product Owner Decisions

| Decision | Chosen | Rationale |
|----------|--------|-----------|
| **Q1: Scope of URL preservation on category navigation** | **A** — Preserve all active filters (lang, city, sort, price, purpose, condition, features) | Modern classifieds preserve full state; URL is source of truth. Matches `search-journeys.md` J5: "category is in the path, not a param" — the path carries category, query params carry everything else. |
| **Q2: City representation for coexistence** | **A** — Use `?city=<slug>` query param (not `/city/<slug>/` path) | `listings()` already supports `?city=` as a real filter; allows coexistence with `/category/<slug>/` in the URL. Matches `search-journeys.md` L184: "Clicking a city sets `?city=<slug>` on the current URL (preserving the category path)." |
| **Q3: "Entire country" clear on all pages** | **A** — Remove only `city`, preserve `lang` and all other params on ALL pages (including root `/`) | PO clarified: "Entire country" clears only the `city` parameter everywhere. On root `/`, the URL becomes `/?lang=ru` (city removed, language preserved). Language is never cleared by "Entire country." |
| **Q4: Language URL representation** | **A** — Keep `?lang=` query param (no path-based `/ru/` migration) | Already implemented and working via `LanguagePreMiddleware` priority #1. Path-based language would require `i18n_patterns` + routing overhaul — disproportionate effort. Google treats `?lang=` as a "safe" parameter (acceptable for a regional site). |

> **Note:** The `search-journeys.md` L184-187 already documents the *intended* behavior
> ("Clicking a city sets `?city=<slug>` on the current URL (preserving the category
> path)") — the bug is that the **implementation** in `header_catalog.html` still
> navigates to `/city/<slug>/`. This spec confirms that the documented intent is the
> correct behavior and closes the gap.

---

## 5. Research Summary

### 5.1 Modern practices for URL state in classifieds

Leading classifieds platforms (Avito, OLX, eBay, Craigslist) follow a
**"primary-resource-in-path, secondary-filters-in-query"** URL architecture:

| Site | Geography | Category | Language | Filters |
|------|-----------|----------|----------|---------|
| Avito | Path (`/<city>/`) | Path (`/category/`) | Separate TLD | Query params |
| OLX | Country TLD | Path | Country TLD | Query params |
| Craigslist | Subdomain | Path code | Monolingual | Query params |
| eBay | Path or query | Path | Subdirectory/TLD | Query params |

**Key insight:** No major classifieds site drops language or city when switching
categories. The URL is always a complete, shareable representation of the current
view state.

### 5.2 Query param vs. path segment

- **Path segments** (`/category/electronics/`): SEO-friendly, stable, hierarchical.
  Best for primary resources that should be indexed.
- **Query parameters** (`?city=budva&lang=ru`): composable, preservable, easy to
  add/remove individually. Best for transient, combinable filter state.

The project's constraint (mutually exclusive `category/<slug>` and `city/<slug>`
path patterns) forces city to be a query param when a category is active. This
aligns with the eBay/Avito hybrid approach.

### 5.3 Language representation

- **Google discourages** `?lang=` query params for international SEO in favor of
  subdirectories (`/de/`) or ccTLDs. However, `?lang=` is treated as a "safe"
  parameter and is acceptable for small regional sites.
- **No major classifieds** uses query-param language — they use separate TLDs or
  subdomains. But the project's `LanguagePreMiddleware` already uses `?lang=` as
  priority #1; migrating to path-based language would require `i18n_patterns` and
  a full routing overhaul — disproportionate for the scope.
- **Recommendation confirmed:** Keep `?lang=` as query param.

### 5.4 HTMX-specific URL state management

**HTMX 2.0.10 behaviors (verified from htmx.org docs + GitHub issues):**

1. `hx-push-url="true"` pushes the **full request URL** to browser history — the
   project already uses this correctly in `ad_list.html`.
2. `htmx:configRequest` event fires before each AJAX request — can inject `lang`
   into `event.detail.parameters` (recommended by HTMX maintainers for "URL params
   you know are safe").
3. `htmx:beforeHistoryUpdate` fires before history is updated — can modify the
   pushed URL.
4. **HTMX does NOT auto-carry URL params** to new requests (GitHub issue #3199) —
   they must be explicitly preserved via hidden inputs, `htmx:configRequest`, or
   server-side template construction.
5. Elements **outside** the swap target (`#ad-list`) are never re-rendered on
   partial swap — the header (with category links, language switcher) is frozen
   between full page loads.

**The bug in HTMX terms:** Category links are plain `<a>` tags that cause full-page
navigations to bare `/category/<slug>/` URLs. Unlike the HTMX-powered chip/pagination
links (which are constructed server-side with explicit `lang`/`city` params), these
header links are rendered once at page load and never updated.

**Recommended fix pattern (from Researcher):**
- **Server-side template construction** using `query_replace` for header/breadcrumb
  links (matches existing pattern in `language_switcher.html` and `ad_list.html`).
- **Client-side `htmx:configRequest` hook** as a safety net for future HTMX navigations.
- **Extend the existing `htmx:afterSwap` handler** to also recompute category/breadcrumb
  links after swaps (mirroring the language switcher pattern).

### 5.5 Feasibility assessment

| Capability | Feasible? | Rationale |
|-----------|-----------|-----------|
| Category links preserve `lang` + `city` + filters | ✅ Yes | Use `query_replace` template tag (exists at `dict_tags.py:47`) |
| Breadcrumb links preserve state | ✅ Yes | Same `query_replace` approach in `breadcrumb.html` |
| City dropdown preserves category path | ✅ Yes | `applyCityFilter()` already uses `new URL()` — just switch from path form to `?city=` form |
| Autocomplete category suggestion preserves state | ✅ Yes | Modify the JS to append current query params |
| Global `htmx:configRequest` hook | ✅ Yes | Small JS snippet, HTMX 2.0.10 compatible |
| Path-based city + path-based category coexistence | ❌ No (by design) | Mutually exclusive URL patterns. Use `?city=` query param. |
| Path-prefix language (`/ru/`, `/bs/`) | ❌ No (by design) | `?lang=` is priority #1 in `LanguagePreMiddleware` |

---

## 6. Assumptions

| # | Assumption | Justification |
|---|-----------|---------------|
| A1 | `lang` and `city` as query params is the desired URL design | `?lang=` is priority #1 in `LanguagePreMiddleware`; `?city=` is a real filter on both views. The existing spec docs (`search-journeys.md` L184-187) describe this as the intended behavior. |
| A2 | The `/city/<slug>/` path form can be deprecated for header navigation (not removed from URL config) | The URL pattern `listings_city` remains valid for direct navigation/bookmarking; only the header JS stops using it. |
| A3 | Full-page navigation is the correct behavior for category/city/language switching (not HTMX partial) | Category changes are primary navigation (like a new page load), not filter refinements. The header is outside `#ad-list` and would need re-rendering for partial updates. |
| A4 | "Entire country" clear removes only `city` param on ALL pages (including root `/`); `lang` and all other params are always preserved | PO clarified: language must never be cleared by "Entire country" — the URL becomes `/?lang=ru` on root after clearing city |
| A5 | `URLSearchParams` is the correct client-side tool for URL construction | The codebase already uses it (`language_switcher.html:134`, `header_catalog.html:275-280`). It correctly handles multi-value params and URL encoding. `QuerySet.urlencode()` produces identical encoding. |

---

## 7. Constraints

1. **Two mutually exclusive path patterns**: `category/<slug>` and `city/<slug>`
   cannot coexist in the URL path (`ads/urls.py:25-27`). At most one is active
   per `listings()` call. → City must be a query param when category is in the path.

2. **Category is path-only on listings**: `?category=` query param is
   suggestion-only on the listings page (`listings.py:282-285`); it's a real
   filter only on the search page (`search.py:64-75`). → Category cannot be
   preserved as a query param on listings; it must stay in the path.

3. **Header is outside the HTMX swap target**: `list.html:23` includes
   `header_catalog.html` before `<main>`, while `#ad-list` is at `list.html:36`
   inside `<main>`. HTMX responses return only `ad_list.html` partial. → Header
   links go stale after swaps; need `htmx:afterSwap` to recompute.

4. **No `i18n_patterns`**: The project uses a custom `LanguagePreMiddleware`
   (not `LocaleMiddleware`) and `?lang=` query param. → Cannot migrate to
   path-based language without a routing overhaul.

5. **Django 5.2 LTS, HTMX 2.0.10**: `htmx:configRequest` and
   `htmx:beforeHistoryUpdate` are available in HTMX 2.x but
   `htmx.pushURL()` / `htmx.replaceURL()` are not exposed (internal functions).
   → Must use event listeners, not direct API calls.

6. **Test DB in Docker only**: Tests require PostgreSQL 18 on port 5433;
   `uv run pytest` fails locally. → Any new tests must run via the Docker
   Compose `test` service.

7. **i18n completeness gate**: All visible template strings must be wrapped in
   `{% trans %}` / `{% blocktrans %}`. New template changes that add visible
   text must pass `test_i18n_completeness.py`. → No new hardcoded visible text
   in templates.

8. **AGENTS.md rule**: Use `StrEnum` for constants; Pydantic v2 for DTOs;
   English-only code/comments.

---

## 8. Risks

| # | Risk | Impact | Mitigation |
|---|------|--------|------------|
| R1 | **Category links without `lang`/`city`** if `query_replace` context is missing | Buyer loses language/city after category navigation | Assert in template tests that `language_switcher.html:35` pattern (using `query_replace`) produces correct output; add template-level test for category links |
| R2 | **Stale header links after HTMX swap** — category/breadcrumb links rendered at initial load become stale after pagination/filter HTMX updates change `lang`/`city` in the URL | Buyer switches category and goes to a wrong URL | Extend the existing `htmx:afterSwap` handler (`language_switcher.html:131`) to also recompute `[data-category-link]` hrefs |
| R3 | **"Entire country" clear drops `lang`** — currently navigates to `/` (drops all state including `lang`); after fix, must clear only `city` on ALL pages, preserving `lang` | Update the clear link (L552) to use `url.searchParams.delete('city')` on `new URL(window.location.href)` — preserves `lang` and all other params. On root `/`, URL becomes `/?lang=ru`. |
| R4 | **`page` parameter carried to language switch** — already handled by `language_switcher.html:135` (`params.delete('page')`); new category links should also drop `page` | Buyer lands on nonexistent page after switching category | Category navigation should set `page=1` (new category = fresh page 1) |
| R5 | **Duplicate `city` param** — if both `/city/<slug>/` path and `?city=` query are present, the view handles it (path wins), but URL is confusing | Confusing URL for the buyer | The fix replaces `/city/` navigation with `?city=` for new navigations; the path form remains only for direct/bookmarked URLs |
| R6 | **Test count assertions** — `test_all_htmx_links_have_push_url` (`test_catalog_filters.py:648`) hard-counts `hx-get=` and `hx-push-url="true"` in `ad_list.html`. Changes to `ad_list.html` (did-you-mean links, L27-28) could break this count | Test failures not related to the fix | Scope changes carefully; update test counts only if `ad_list.html` link count changes |
| R7 | **SEO: `?city=` and `?lang=` as non-canonical params** — Google may index filtered pages as duplicate content | Potential SEO dilution | Add `rel="canonical"` to base category page and/or `noindex` on heavily-filtered variations (deferred — out of scope for this fix) |
| R8 | **`applyCityFilter()` on root path `/`** — currently navigates to `/city/<slug>/`; after fix, should go to `/?city=<slug>` (or `/category/<current>/` if on a category page) | Same bug as L562 — just different entry point | The fix in Task 2 modifies `applyCityFilter` itself, covering all callers |

---

## 9. Open Questions

| # | Question | Status |
|---|----------|--------|
| OQ1 | Should the header search bar also preserve `category` and `city` when submitting a query from a `/category/.../?city=...` page? Currently (per `search-journeys.md` L95, L126) the header search submits only `q`, dropping category and city. | Open — tracked in `search-journeys.md` L269 Q3. Related but separate from this spec. Could be addressed in Task 1 by adding `category`/`city` hidden inputs to the header search form (already partially present at `header_catalog.html:131-132`, but `current_category` is `None` on the search page). |
| OQ2 | Should the `/city/<slug>/` path form be removed from `urls.py`? | Open — deprecation path not decided. Keeping it for backward compat (direct navigation/bookmarks). May cause confusion if both `?city=` and `/city/` exist simultaneously. |
| OQ3 | Should "Entire country" clear on a non-category page (e.g., `/?city=budva`) navigate to `/` or `/?lang=ru`? | **Resolved by PO clarification:** "Entire country" clears only the `city` parameter on ALL pages (including root `/`), preserving `lang` and all other params. On root `/`, the URL becomes `/?lang=ru`. **Closed.** |
| OQ4 | Should a browser-level integration test (Playwright/Cypress) be added to verify client-side URL construction in the header dropdowns? | Open — the JS navigation behavior is not exercised by Django tests. Requires browser testing infrastructure. |

---

## 10. Out of Scope

1. **Path-based language prefixing** (`/ru/category/electronics/`) — would require
   `i18n_patterns` + routing overhaul. See PO decision Q4=A.
2. **Removing the `/city/<slug>/` URL pattern** from `ads/urls.py` — keep for backward
   compatibility / direct navigation. See Open Question OQ2.
3. **Header search bar context preservation** (carrying category+city to `/search/`) —
   tracked separately in `search-journeys.md` L269 Q3. See Open Question OQ1.
4. **SEO canonical/hreflang tag implementation** — query-param language/city is treated
   as "safe" by Google; canonical tags are a deferred enhancement. See Risk R7.
5. **New frontend framework / React / SPA** — the project is HTMX MPA only.
   See constraint C5.
6. **Bot-side URL handling** — the Telegram bot uses deep-links, not catalog URLs.
   Unaffected.

---

## 11. Definition of Ready

A task is "ready" (implementation-planable) when all of the following are true:

1. **[x]** PO has confirmed decisions Q1–Q4 (all confirmed: Q1=A, Q2=A, Q3=A hybrid, Q4=A).
2. **[ ]** Researcher's modern-practices report is reviewed and accepted (delegated and completed).
3. **[ ]** The `query_replace` template tag is confirmed as the URL construction mechanism
       (exists at `dict_tags.py:47`; used by `language_switcher.html:35`).
4. **[ ]** The `applyCityFilter()` and `selectCity()` JS patterns are confirmed as the
       client-side URL construction mechanism (`header_catalog.html:229-248`).
5. **[ ]** The existing `htmx:afterSwap` handler (`language_switcher.html:131-142`) is
       confirmed as the extension point for post-swap link recomputation.
6. **[ ]** Test guards identified: `test_all_htmx_links_have_push_url`
       (`test_catalog_filters.py:648`) and `test_lang_param_in_all_htmx_urls`
       (`test_catalog_filters.py:659`) — template-level assertions that must not regress.
7. **[ ]** i18n gate verified: any new visible template text wrapped in `{% trans %}`;
       existing `test_i18n_completeness.py` tests pass.
8. **[ ]** The fix does not require server-side/view changes (all changes are in
       templates + client-side JS) — confirmed by `listings()` URL architecture analysis.

---

## 12. Key Files Reference

| File | Role | Relevant Lines |
|------|------|----------------|
| `apps/ads/urls.py` | URL patterns (mutually exclusive paths) | L25-27 |
| `apps/ads/views/listings.py` | Listings view (city/cat filter logic) | L263-285 (cat), L293-325 (city), L435-456 (context) |
| `apps/search/views/search.py` | Search view (both are real filters) | L64-75 (cat), L79-92 (city) |
| `apps/core/middleware/language.py` | Language resolution `?lang=` > cookie > header | L59-66 |
| `apps/core/middleware/city_resolution.py` | City resolution (path > `?city=` > None) | L50-64 |
| `apps/core/middleware/preferred_city.py` | Preferred city fallback | L47-66 |
| `apps/core/context_processors.py` | Header context (cities, categories, badge) | L28-107 |
| `apps/core/templatetags/dict_tags.py` | `query_replace` template tag | L47-69 |
| `templates/components/header_catalog.html` | **Primary fix location** (category links, city JS, autocomplete JS) | L97, L180, L340, L343, L552, L562 |
| `templates/components/language_switcher.html` | Language switcher (already fixed for swap staleness) | L35, L131-142 |
| `templates/components/breadcrumb.html` | Breadcrumb category links | L18, L31 |
| `templates/ads/partials/ad_list.html` | Ad list partial (did-you-mean links, chip/pagination URLs) | L27-28, L37-46, L45-182 |
| `templates/ads/list.html` | Full listings template (header + `#ad-list`) | L23, L36 |
| `apps/ads/tests/test_catalog_filters.py` | Test guards for URL construction | L648, L659, L665 |
| `apps/core/tests/test_templates.py` | `query_replace` behavior tests | L104-130 |

---

## 13. Related Documents

- **Input problem:** `.ai/problems/Problem_01.md` (RU)
- **Search journeys:** `docs/04-user-stories/search-journeys.md` (L184-187, L269 Q3)
- **Filter UI spec:** `docs/01-spec/filter-ui.md` (L410-411, L444-447)
- **i18n spec:** `docs/01-spec/i18n-spec.md` (§G, runtime language resolution)
- **Technical specification:** `docs/01-spec/technical-specification.md` (§G)
- **Deleted prior analysis:** `.ai/problems/06_url-architecture-audit_report.md`,
  `.ai/problems/05_filter-regression_spec.md` (Problem 04 #4),
  `.ai/problems/07_test-language-standardization_DONE.md`
- **Deleted prior research:** `.ai/findings/07_city-category-url-coexistence-research.md`
- **Language switcher fix:** `docs/99-agent/htmx-language-switcher-fix-evaluation.md`,
  `docs/99-agent/htmx-swap-language-switcher-audit.md`
