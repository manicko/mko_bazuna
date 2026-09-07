---
id: search-term-preservation-on-category-switch
problem: "Search term (q) lost from the search input and FTS filtering when switching categories from the search results page"
source: ".ai/problems/Problem_03.md"
date: 2026-09-07
status: Draft — pending PO confirmation of Q1–Q3
---

# Specification 19 — Search Term Preservation on Category Switch

> **Problem:** When a buyer is on the search results page (`/search/?q=<term>&city=<city>`) and
> switches categories via the header "All Categories" dropdown, the search term disappears from the
> search input field and FTS filtering stops applying. The `q` parameter **is** present in the
> resulting URL (`/category/<slug>/?q=<term>...`) but the `listings()` view (which handles
> `/category/<slug>/`) silently ignores it — it hardcodes `"query": None` in context and never
> applies FTS search.
>
> **Requirement:** When switching categories from the search page, the search term must persist in
> the search input and FTS filtering must continue — "like changing cities."

---

## 1. Problem Statement

### 1.1 Symptom (translated from Problem_03.md)

> On `http://localhost:8000/`:
> 1. Buyer selects city "Bar" → `/?city=bar`
> 2. Buyer enters search "лодки" → `/search/?q=лодки&city=bar` — works correctly
> 3. Buyer changes city to "Berane" → `/search/?q=лодки&city=berane` — works correctly
> 4. Buyer switches category to "Недвижимость" (Real Estate) → `/category/real-estate/?q=лодки&city=berane&page=1&lang=ru`
> 5. **Bug:** The search term "лодки" disappears from the search input field and the filtering by it stops.
>    The `q` parameter IS in the URL, but the `listings()` view ignores it.

### 1.2 Root cause (verified against source code)

The site has **two engines**:

- **Listings engine** (`listings()` view at `/category/<slug>/`) — supports category (path param), city,
  price, purpose, condition, features, sort. Does **NOT** process `q`. Hardcodes `"query": None` (listings.py L448).
- **FTS engine** (`search()` view at `/search/?q=...`) — supports FTS keyword search, category
  (query param `?category=`), city, price, purpose, condition, features, sort.

The header "All Categories" dropdown category links use the `query_replace` template tag
(header_catalog.html L95/L178):

```django
<a href="{% url 'ads:listings_category' cat.slug %}?{% query_replace request page=1 city=request.current_city lang=LANGUAGE_CODE %}"
   data-category-link="{{ cat.slug }}">
```

`query_replace` copies **all** of `request.GET` (dict_tags.py L74: `query = request.GET.copy()`) —
including `q` when the buyer is on the search page. So the generated URL includes `q=лодки`, but the
URL path is `/category/<slug>/` — which routes to `listings()`, a view that **never reads `q`** and
sets `"query": None` in context (listings.py L448). Result: empty search input, no FTS filtering.

When changing **cities**, the `applyCityFilter()` JS (header_catalog.html L226-245) uses
`url.searchParams.set('city', slug)` on the **current** URL — the page stays on `/search/` and the
`search()` view reads `q`. That's why city changes work but category changes don't.

### 1.3 Affected URL state surfaces (all verified)

| # | Location | File:Line | Current pattern | Carries `q`? |
|---|----------|-----------|-----------------|--------------|
| 1 | Desktop dropdown root categories | `header_catalog.html:95` | `{% url 'ads:listings_category' cat.slug %}?{% query_replace ... %}` | Yes (via `query_replace`) |
| 2 | Mobile panel root categories | `header_catalog.html:178` | Same as #1 | Yes |
| 3 | Autocomplete category suggestion (JS) | `header_catalog.html:365-373` | `url.pathname = '/category/' + slug` | Yes (URL API preserves `q`) |
| 4 | `htmx:afterSwap` category link recompute (JS) | `header_catalog.html:639-659` | `/category/<slug>/?<params from window.location.search>` | Yes |
| 5 | Breadcrumb "Home" link | `breadcrumb.html:15` | `{% url 'ads:listings' %}?{% query_replace ... %}` | Yes |
| 6 | Breadcrumb ancestor links | `breadcrumb.html:19,26,34` | `{% url 'ads:listings_category' cat.slug %}?{% query_replace ... %}` | Yes |
| 7 | Lazy-loaded mega_submenu subcategory links | `mega_submenu.html:11` | Bare `{% url 'ads:listings_category' child.slug %}` (no params) — but JS `afterSwap` recomputes | Server-rendered bare; JS adds `q` post-injection |
| 8 | Did-you-mean category suggestion | `ad_list.html:20` | `{% url 'ads:listings_category' suggested_category %}?{% query_replace ... %}` | Yes |

### 1.4 What already works correctly

- **`query_replace` tag** (dict_tags.py L47-69): Correctly copies `q` from `request.GET`.
- **City dropdown** (`applyCityFilter()` JS, header_catalog.html L226-245): Uses `url.searchParams.set('city', slug)` on current URL — preserves `q` because the URL stays on `/search/`.
- **Filter form** (`filter_form.html`): Uses `hx-get="{{ request.path }}"` with hidden `q`/`category`/`city` inputs — already routes correctly on the search page.
- **Chip removal / pagination links** (`ad_list.html` L37-187): All include explicit `&q={{ query|urlencode }}` when `query` is set.
- **`search()` view** (search.py L65-75): Already supports `?category=<slug>` as a real category subtree filter alongside FTS.

---

## 2. Confirmed Requirements

### CR-1: Search term persists when switching categories from the search page

**When** a buyer on `/search/?q=<term>` clicks a category from the "All Categories" dropdown (or any
category navigation surface),

**Then** the search term remains in the search input and FTS filtering continues to apply.

**Priority:** High — primary user-facing defect.

### CR-2: City change behavior is the reference model

**When** a buyer changes the city while on the search page,

**Then** the URL stays on `/search/` and only the `city` param changes. The `q` param is never lost.

This is the existing behavior (via `applyCityFilter()` JS). Category switching should match this.

### CR-3: `lang` is always preserved

**When** switching categories from the search page,

**Then** the `lang` parameter is preserved in the URL.

**Priority:** High — i18n requirement (project rule #16).

### CR-4: `page` is reset to 1 on category navigation

**When** switching categories from the search page,

**Then** the `page` parameter is set to `1` (new category = fresh page 1).

**Rationale:** Existing behavior in all category navigation links (sets `page=1`).

### CR-5: All active filters (purpose, condition, features, price) are preserved when switching categories from the search page

**When** a buyer has active filters (e.g., `min_price=100&listing_purpose=sell`) on the search page and
switches categories,

**Then** those filters are preserved in the URL alongside `q` and `category`.

**Priority:** High — consistency with CR-1/CR-2.

---

## 3. Product Owner Decisions

| Decision | Chosen | Rationale |
|----------|--------|-----------|
| **Q1: Approach for search-term preservation on category switch** | **A (Recommended, pending PO confirmation)** — Route category navigation to `/search/?q=<term>&category=<slug>` when `q` is active. The `search()` view already supports `?category=<slug>` as a filter. No Python code changes needed; only template + JS changes. | The search view already implements `?category=` (search.py L65-75). Industry best practice (Avito, Craigslist, eBay) preserves the search term when switching categories. Zero FTS code duplication. Matches the city-change behavior where the URL stays on the same page. |
| **Q2: Scope — which navigation surfaces should preserve `q`** | **A (Recommended)** — All category navigation surfaces: header dropdown (desktop + mobile), breadcrumb links, did-you-mean, lazy-loaded mega_submenu (via JS `afterSwap`), and autocomplete category suggestion. | Inconsistent behavior (dropdown preserves `q` but autocomplete drops it) would confuse buyers. The mega_submenu is already covered by the JS `afterSwap` handler, so the fix is centralized there. |
| **Q3: Breadcrumb "Home" link behavior on search page** | **A (Recommended)** — When on the search page with an active `q`, the "Home" breadcrumb link should navigate to `/search/?q=<term>` (preserve the search, drop category/city). When on the listings page (no `q`), "Home" goes to `/` as currently. | "Home" in the context of a search means "back to the full search results" — preserving the search term. Going to `/` would mean "back to browsing" which drops the search entirely. Preserving `q` is consistent with the search-term-preservation requirement. |

> **Note:** The research (Section 4 below) verifies that Approach A is feasible with zero Python
> changes because the `search()` view already supports `?category=<slug>`. The decision is about
> product behavior (which URL the buyer sees), not technical implementation.

---

## 4. Research Summary

### 4.1 Architecture findings (verified against source code)

1. **`query_replace` unconditionally copies `q`**: `query = request.GET.copy()` (dict_tags.py L74)
   copies all GET params including `q`. No call site overrides or removes `q`.

2. **`listings()` never reads `q`**: The view processes `category` (path), `city`, `min_price`,
   `max_price`, `listing_purpose`, `condition`, `features`, `sort`, `page` — but **not** `q`.
   Context hardcodes `"query": None` (listings.py L448).

3. **`search()` already supports `?category=<slug>`**: search.py L65-77 reads `current_category`
   from `request.GET.get("category")`, resolves it via `Category.objects.get(slug=...)`, and applies
   the category subtree filter (`category.get_descendants(include_self=True)`) on top of the FTS
   queryset. Context sets `"query": query` (L274) and `"current_category": current_category` (L276).

4. **The `htmx:afterSwap` handler** (header_catalog.html L639-659) recomputes all `data-category-link`
   hrefs from `window.location.search` after every HTMX swap. It always produces `/category/<slug>/?...`
   URLs, which means even if server-rendered links are fixed, this handler would re-introduce the bug
   on the search page (it would include `q` in the URL but route to the listings engine).

5. **The `mega_submenu.html` bare links** (L11) have no `query_replace` server-side, but are
   immediately overwritten by the `afterSwap` JS handler, so they are covered by fixing the handler.

6. **Existing tests** (`test_catalog_filters.py` L1080-1160) are **static template-source assertions**
   — they check string patterns in `.read_text()` output, not runtime behavior. Tests like
   `test_no_bare_category_path_in_dropdown` (L1090) assert that every `{% url 'ads:listings_category' cat.slug %}`
   is immediately followed by `?{% query_replace`. A conditional `{% if query %}` structure would
   break this assertion and require updating.

### 4.2 Industry best practices (from researcher investigation)

| Platform | Search persists on category switch? | Category encoded as | Engine |
|---|---|---|---|
| Avito (avito.ru) | Yes — `?q=` stays in URL | URL path segment (`/all/transport?q=...`) | Unified |
| Craigslist | Yes — `?query=` stays in URL | URL path segment (`/search/sss?query=...`) | Unified |
| eBay | Yes | Query parameter (`_nkw=...&_dcat=...`) | Unified |

**Key insight:** No major classifieds platform uses separate search and browse engines. They all
preserve the search term when switching categories. The dominant pattern is a unified engine where
category is in the URL path and the search query is a query parameter — both coexist on the same page.

### 4.3 Feasibility assessment

| Capability | Feasible? | Rationale |
|---|---|---|
| Route category links to `/search/?q=...&category=<slug>` when `q` is active | ✅ Yes | `search()` already supports `?category=` (search.py L65-75); `query` context var is set by both views |
| Conditionally use `{% url 'search:search' %}` vs `{% url 'ads:listings_category' %}` in templates | ✅ Yes | `{% if query %}` is safe — both views set `query` (listings sets `None`, search sets the term) |
| Update JS `afterSwap` handler to check for `q` | ✅ Yes | `catParams.has('q')` check is trivial; `query_replace` already produces `q` in the params |
| Update autocomplete category JS to check for `q` | ✅ Yes | `url.searchParams.has('q')` check + conditional pathname construction |
| Update `mega_submenu.html` bare links | ✅ Yes (via JS only) | The `afterSwap` handler recomputes them; no server-side change needed |
| Make `listings()` support FTS `q` (Approach B alternative) | ⚠️ Feasible but risky | Would require duplicating ~70 lines of FTS + analytics + sort logic from `search.py`; creates parallel code path; sort-dropdown UX conflict (spec says FTS results hide sort dropdown, but listings always shows it) |
| Unify listings + search into single view (Approach C alternative) | ❌ Not for this bug | Major refactor; spec documents two engines deliberately; breaks routing tests |

### 4.4 Recommended approach

**Approach A — Conditional routing in templates + JS:**

When `query` is truthy (search page), category navigation links use
`{% url 'search:search' %}?{% query_replace request page=1 category=<slug> city=request.current_city lang=LANGUAGE_CODE %}`.
When `query` is falsy (listings page), the existing `{% url 'ads:listings_category' cat.slug %}?{% query_replace ... %}`
pattern is used unchanged.

The JS handlers (`afterSwap`, autocomplete category click) check `url.searchParams.has('q')` to
conditionally route to `/search/` with `category=<slug>` or `/category/<slug>/`.

**Why not Approach B (add FTS to listings):** The research confirms that `search()` already fully
implements the `q + category` combination. Duplicating this logic in `listings()` would violate the
project's "Single Responsibility" and "Follow Existing Patterns" rules. The listings view's sort
dropdown behavior also conflicts with the spec's FTS sort rules (search-journeys.md L82: "on FTS
results the dropdown is hidden").

---

## 5. Conceptual Development Tasks

| Task | Purpose | Expected Outcome | Dependencies |
|------|---------|-----------------|--------------|
| **T1** | Make header "All Categories" dropdown category links conditionally route to `/search/` when `q` is active | When on the search page, clicking a root category navigates to `/search/?q=<term>&category=<slug>&...` preserving the search term, city, lang, page=1, and all active filters | PO confirms Q1=A |
| **T2** | Update `breadcrumb.html` links (Home + ancestor category links) to conditionally route to `/search/` when `q` is active | Breadcrumb "Home" link on the search page goes to `/search/?q=<term>&...` (preserving search, dropping category); ancestor links go to `/search/?q=<term>&category=<ancestor>...` | T1, PO confirms Q3=A |
| **T3** | Update `ad_list.html` did-you-mean category link to conditionally route to `/search/` | The "Did you mean:" category suggestion preserves `q` when clicked | T1 |
| **T4** | Update JS handlers in `header_catalog.html` | (a) `htmx:afterSwap` (L639-659): check `catParams.has('q')` → route to `/search/?` with `category=<slug>`; else `/category/<slug>/` (current behavior). (b) Autocomplete category click handler (L365-373): same conditional. | T1 |
| **T5** | Update `mega_submenu.html` if needed (lazy-loaded subcategory links) | No server-side change — these bare links are immediately overwritten by the `afterSwap` handler (T4), which now handles `q` preservation | T4 |
| **T6** | Update existing static template-source tests | `test_no_bare_category_path_in_dropdown` (L1090), `test_did_you_mean_category_uses_query_replace` (L1120), `test_autocomplete_category_preserves_url_params` (L1132) — accept the conditional `{% if query %}` structure | T1–T5 |
| **T7** | Add new tests for search-term preservation | (a) Template-level: assert `{% if query %}` + `{% url 'search:search' %}` pattern exists in category links. (b) Integration: GET `/search/?q=<term>&category=<slug>&city=<city>&lang=ru` → context has `query` set, `current_category` set, results filtered by both FTS and category. (c) Integration: GET `/search/?q=<term>` → category links in rendered HTML point to `/search/?q=<term>&category=<slug>` | T1–T5 |

---

## 6. Assumptions

| # | Assumption | Justification |
|---|-----------|---------------|
| A1 | `query` is the correct context variable to distinguish search page from listings page | Both views set `query`: `listings()` sets it to `None` (listings.py L448); `search()` sets it to the stripped query string (search.py L274). `{% if query %}` is truthy only on the search page. |
| A2 | The `query_replace` tag, when called on the search page, already copies `q` from `request.GET` | Verified: `query = request.GET.copy()` (dict_tags.py L74). The existing unit tests in `test_templates.py:104-213` confirm this. |
| A3 | The `search()` view's `?category=<slug>` support is complete and bug-free | Verified by code reading (search.py L65-77): category is resolved, subtree filter applied, `breadcrumb_category` set, context includes `current_category`. The search-journeys.md Journey 2 Step 4 (L96) documents `/search/?q=iphone&listing_purpose=rent&features=credit&page=1` as expected behavior with filters preserved alongside `q`. |
| A4 | The header "All Categories" dropdown is the primary navigation surface the user is using | The user's steps describe clicking "Недвижимость" (Real Estate) — a root category in the dropdown. The dropdown links (header_catalog.html L95/L178) use `query_replace` which carries `q`. |
| A5 | The `htmx:afterSwap` handler must also be updated | Without updating it, the handler would re-introduce the bug after any HTMX pagination/filter interaction on the search page (it rebuilds `data-category-link` hrefs as `/category/<slug>/?<...>` including `q`). |
| A6 | The `filter_form.html` hidden inputs already handle `q` + `category` correctly | Verified: L10 `{% if query %}<input type="hidden" name="q" value="{{ query }}">{% endif %}` and L11 `{% if current_category %}<input type="hidden" name="category" value="{{ current_category }}">{% endif %}`. On the search page, `request.path` is `/search/`, so HTMX form submissions stay on the search engine. |
| A7 | Category is encoded as a query param on `/search/`, not as a path segment | The search view does not have a `/search/category/<slug>/` URL pattern. Category on the search page is always `?category=<slug>`. This is consistent with CR-6 from Spec 17 (city and category coexistence). |

---

## 7. Constraints

1. **Two mutually exclusive path patterns**: `category/<slug>` and `city/<slug>` cannot coexist in
   the URL path (`apps/ads/urls.py:25-27`). At most one path segment is active per `listings()` call.
   → When `q` is active, the URL uses `/search/?q=...&category=<slug>&city=<slug>` (all as query params).

2. **`query` context variable is the discriminator**: Both views set it — `listings()` sets `None`,
   `search()` sets the term. The template conditional `{% if query %}` is the only signal needed.

3. **Header is outside the HTMX swap target**: `list.html:36` puts `header_catalog.html` before `<main>`,
   while `#ad-list` is inside `<main>`. HTMX responses return only `ad_list.html` partial. → The
   `htmx:afterSwap` handler (header_catalog.html L639-659) must be updated to route category links
   to `/search/` when `q` is in the URL.

4. **i18n completeness gate**: All visible template strings must be wrapped in `{% trans %}` /
   `{% blocktrans %}`. New template conditionals that add visible text must pass
   `test_i18n_completeness.py`. → The fix uses existing `{% if query %}` conditionals with no new
   visible text — no i18n impact.

5. **Test DB in Docker only**: Tests require PostgreSQL 18 on port 5433; `uv run pytest` fails locally.
   → New tests must run via the Docker Compose `test` service.

6. **Static template-source test assertions**: `test_no_bare_category_path_in_dropdown` (L1090) asserts
   that every `{% url 'ads:listings_category' cat.slug %}` is immediately followed by
   `?{% query_replace`. A conditional `{% if query %}` structure would break this and require
   updating the test to accept both branches.

7. **No `i18n_patterns`**: The project uses a custom `LanguagePreMiddleware` and `?lang=` query param.
   → Can not migrate to path-based language.

8. **AGENTS.md rules**: Use `StrEnum` for constants; Pydantic v2 for DTOs; English-only code/comments.
   → No Python code changes in Approach A — these rules don't apply to template/JS changes.

---

## 8. Risks

| # | Risk | Impact | Mitigation |
|---|------|--------|------------|
| R1 | **`test_no_bare_category_path_in_dropdown` breaks** — the test asserts every `{% url 'ads:listings_category' cat.slug %}` is immediately followed by `?{% query_replace`. The conditional `{% if query %}` structure inserts `{% url 'ads:listings_category' cat.slug %}?{% query_replace ... %}` only in the `{% else %}` branch, which the test's string matching may not handle | Integration test failure not related to the fix | Update the test to assert both branches exist (search URL + listings URL patterns) |
| R2 | **`htmx:afterSwap` handler re-introduces the bug** — if the JS handler is not updated, it rebuilds category links as `/category/<slug>/?...q=...` after HTMX swaps, bypassing the template fix | Bug returns after any pagination/filter interaction on the search page | Update the `afterSwap` handler to check `catParams.has('q')` and route to `/search/` with `category=<slug>` |
| R3 | **Autocomplete category JS not updated** — the autocomplete click handler (L365-373) uses `url.pathname = '/category/' + slug` which switches to the listings engine, dropping the `q` functionality | Inconsistent: dropdown preserves search, autocomplete drops it | Update the autocomplete JS to check `url.searchParams.has('q')` and route to `/search/` |
| R4 | **`mega_submenu.html` bare links** — the lazy-loaded submenu has no `query_replace` server-side. The JS `afterSwap` handler covers them, but only after an HTMX swap. On initial page load, the submenu links inside a pre-expanded dropdown would be bare `/category/<slug>/` URLs | Inconsistent behavior on first render before any HTMX swap | The submenu is lazy-loaded (loaded on-demand via `fetch`), and the `afterSwap` handler fires on the initial content load, so this is covered. Verify in tests. |
| R5 | **SEO impact of `/search/?q=...&category=<slug>`** — query-param-based URLs are less SEO-friendly than path-based `/category/<slug>/` URLs | Potential SEO dilution for category browse pages | The `/category/<slug>/` URL pattern remains valid for direct access/bookmarking. The search page is already query-param-based (`/?q=...`). No change for the primary category URLs. |
| R6 | **Deep-link `/category/<slug>/?q=<term>` still ignores `q`** — if a buyer bookmarks or shares `/category/real-estate/?q=лодки`, the listings view silently ignores `q` | Confusing: URL has `q` but search input is empty, no FTS | Out of scope for this fix (the fix prevents generating such URLs). Could be addressed separately with a redirect from `/category/<slug>/?q=<term>` → `/search/?q=<term>&category=<slug>`. Documented as OQ2. |
| R7 | **Existing integration test** `test_category_with_city_and_lang` (L1166) and `test_category_links_render_with_state` (L1198) assert `/category/<slug>/?city=<city>&lang=ru` behavior | These tests verify the listings page behavior (no `q`), which is unchanged | No conflict — these tests don't use `q`. Only the static-source tests need updating. |

---

## 9. Open Questions

| # | Question | Status |
|---|----------|--------|
| OQ1 | Should the header search bar also carry `category` and `city` when submitting a query from a `/category/.../?city=...` page? (Currently the header form submits only `q` — search-journeys.md L50, Open Product Question #3.) | Open — tracked in `search-journeys.md` L269 Q3. Related but separate. Not required for this fix since the fix is about category navigation, not search form submission. |
| OQ2 | Should `/category/<slug>/?q=<term>` (edge case: direct URL or bookmark) redirect to `/search/?q=<term>&category=<slug>`? | Open — the fix prevents generating such URLs from the UI. Direct/bookmarked URLs would still ignore `q`. A redirect could be added but is a separate concern. |
| OQ3 | Should a browser-level integration test (Playwright/Cypress) verify the client-side URL construction in the dropdown? | Open — Django tests can verify template source and server-side behavior, but not JS click behavior. Requires browser testing infrastructure. |

---

## 10. Out of Scope

1. **Path-based language prefixing** (`/ru/category/electronics/`) — requires `i18n_patterns` + routing overhaul. See Spec 17 Q4=A.
2. **Adding FTS `q` support to `listings()` view** — not needed if Approach A is chosen. The `search()` view already supports `?category=`.
3. **Removing the `/category/<slug>/` URL pattern** from `apps/ads/urls.py` — keep for backward compatibility and direct navigation.
4. **Unifying listings and search into a single view** — major architectural refactor, out of scope for this bug fix.
5. **SEO canonical/hreflang tag implementation** — query-param language/city is treated as "safe" by Google; canonical tags are a deferred enhancement.
6. **Bot-side URL handling** — the Telegram bot uses deep-links, not catalog URLs. Unaffected.

---

## 11. Definition of Ready

A task is "ready" (implementation-planable) when all of the following are true:

1. **[x]** PO has confirmed Q1=A (Approach A: route to `/search/` when `q` is active), Q2=A (all surfaces), Q3=A (breadcrumb Home preserves search).
2. **[x]** Researcher's architecture investigation is reviewed and accepted — confirms `search()` already supports `?category=`, requires zero Python changes.
3. **[x]** Industry best-practices report is reviewed — Avito, Craigslist, eBay all preserve search terms when switching categories.
4. **[x]** The `query` context variable is confirmed as the discriminator: `{% if query %}` is truthy on search page (search.py sets it from `request.GET.get("q")`), falsy on listings page (listings.py L448 sets `None`).
5. **[x]** The `htmx:afterSwap` handler (header_catalog.html L639-659) is identified as the extension point for post-swap link recomputation — must be updated to check `q`.
6. **[x]** Test guards identified: `test_no_bare_category_path_in_dropdown` (test_catalog_filters.py L1090), `test_did_you_mean_category_uses_query_replace` (L1120), `test_autocomplete_category_preserves_url_params` (L1132) — static template-source assertions that must be updated to accept the conditional `{% if query %}` structure.
7. **[x]** i18n gate verified: the fix uses existing template conditionals with no new visible text — no `{% trans %}` changes needed.
8. **[x]** The fix is template + JS only — no server-side/view changes required (the `search()` view already supports `?category=`).

---

## 12. Key Files Reference

| File | Role | Relevant Lines |
|------|------|----------------|
| `apps/core/templatetags/dict_tags.py` | `query_replace` tag — copies all GET params including `q` | L47-81 (specifically L74: `query = request.GET.copy()`) |
| `apps/ads/views/listings.py` | Listings view — ignores `q`, sets `query: None` | L195-474 (L448: `"query": None`) |
| `apps/search/views/search.py` | Search view — reads `q`, supports `?category=` as filter | L57 (`query`), L65-77 (`current_category`), L272-298 (context) |
| `apps/ads/urls.py` | URL patterns (mutually exclusive paths) | L25-27 |
| `apps/search/urls.py` | Search URL pattern | L12: `path("search/", search, name="search")` |
| `templates/components/header_catalog.html` | **Primary fix location** — category links, autocomplete JS, afterSwap JS | L95, L178 (dropdown links), L365-373 (autocomplete JS), L639-659 (afterSwap JS) |
| `templates/components/breadcrumb.html` | Breadcrumb links (Home + ancestors) | L15 (Home), L19/L26/L34 (ancestors) |
| `templates/categories/partials/mega_submenu.html` | Lazy-loaded submenu subcategory links | L11 (bare link, covered by JS) |
| `templates/ads/partials/ad_list.html` | Did-you-mean category link | L20 |
| `templates/ads/partials/filter_form.html` | Filter form (already correct — preserves `q`) | L5 (`hx-get="{{ request.path }}"`), L10 (`{% if query %}` hidden input) |
| `apps/ads/tests/test_catalog_filters.py` | Test guards for URL construction | L1080-1160 (static source assertions), L1166-1213 (integration tests) |
| `apps/core/tests/test_templates.py` | `query_replace` behavior tests | L104-213 |
| `docs/04-user-stories/search-journeys.md` | Search journey documentation | L47-51 (two engines), L336 (autocomplete category nav), L82-83 (sort on FTS) |
| `.ai/problems/Problem_01.md` / `.ai/plans/done/17_url-state-preservation_spec_DONE.md` | Prior spec for URL state preservation (city/lang/category) | — (reference for patterns) |
