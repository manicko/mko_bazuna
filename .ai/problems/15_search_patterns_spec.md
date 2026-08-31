---
id: search-patterns-spec
domain: search
tags:
  - search
  - bugs
  - fts
  - htmx
  - specification
related:
  - search-patterns
  - filter-ui
  - buyer-stories
  - technical-specification
---

# Spec 15 — Search Patterns: Bug Fixes & Context Preservation

| Field | Value |
|---|---|
| **Spec ID** | 15 |
| **Title** | Search functionality: fix 7 verified bugs + autocomplete regression + header context preservation |
| **Status** | Draft — PO-1–PO-5 confirmed. PO-5=B (HTMX 2.x upgrade performed by team's separate audit task before T6) |
| **Source problem input** | `.ai/problems/Problem_01.md` (Russian: "autocomplete works on first search but not on second; clear-X does nothing") |
| **Live verification report** | `.ai/problems/01_search_patterns_verification.md` (7 bugs confirmed via Playwright live testing on `localhost:8000`) |
| **Architecture research** | `.ai/research/search-journeys-our-architecture.md`, `.ai/research/search-journeys-spec.md`, `.ai/research/search-journeys-validation.md`, `.ai/research/olx-vs-avito-comparison.md` |
| **Test plan** | `.ai/problems/01_search_patterns_test_verification_top_plan.md` (11 test blocks, 14 journey groups) |
| **Source of truth (live impl)** | `src/backend/apps/search/views/search.py:33-253`, `src/backend/templates/components/header_catalog.html:113-549`, `src/backend/templates/ads/partials/filter_form.html:5-127`, `src/backend/templates/ads/partials/ad_list.html:1-193` |
| **Stack context** | Django 5.2 LTS (HTMX MPA, sync WSGI gunicorn) + aiogram bot · HTMX 1.9.12 · PostgreSQL 18 (native per-language FTS) · Tailwind CSS v4 |

---

## 1. Problem statement

The Mko Bazuna website search functionality has multiple bugs and UX gaps that cause
unexpected behavior for **buyer users** (unauthenticated visitors who browse, search,
and filter ads without login). These were identified in `Problem_01.md` and verified
through live testing on `http://localhost:8000/`.

**Original problems (Problem_01.md, 2026-08-29):**
1. **Autocomplete regression:** "On first search, autocomplete suggestions work. On
   repeat search, only history is shown and no suggestions."
2. **Clear-X button does nothing:** "If after first search you click the clear
   cross — nothing happens. The site should return to the pre-search state."

**Verified through live testing (01_search_patterns_verification.md):** 7 bugs
confirmed across 6 user-journey scenarios and 9 cross-cutting behaviors:

| Bug | Description | Severity |
|-----|-------------|----------|
| **B1** | CSRF token (`csrfmiddlewaretoken`) leaks into URL query string when the header GET search form submits | Medium |
| **B2** | Native browser clear-X on `<input type="search">` clears the text but does nothing (no wired handler, no navigation) | Medium |
| **B3** | Header search form submits only `q` — drops the active category, city, and all filter context | Medium |
| **B4** | Sort dropdown hidden when `q` is present (`{% if not query %}`); `sort=` param silently ignored on FTS results | Medium |
| **B5** | Min/max price inputs render with `value="None"` (Python `None` stringified) | Low |
| **B6** | `htmx.get()` called in `header_catalog.html` — but HTMX 1.9.12 has no `htmx.get()` API (it was introduced in HTMX 2.0); favorites badge refresh silently fails | Medium |
| **B7** | `lang=ru` dropped from URL on HTMX pagination (pagination links omit the `lang` query param) | Low |

**Autocomplete regression root-cause status:** Static analysis shows the autocomplete
endpoint (`search:autocomplete`) returns all suggestion sources (history + categories +
cities + popular) unconditionally. The `render()` client-side function renders all four
sections. The most likely cause on the dev instance is that `PopularSearch` suggestions
are gated by `hit_count >= 10` (`popular_search.py:19`), so on a low-traffic instance
the popular section is always empty, and if the query also doesn't match any category
or city names, the dropdown appears to show "only history." This is expected behavior
on low-traffic environments, not a code defect — but it creates a poor perception for
buyers on production if popular queries are sparse.

---

## 2. Confirmed requirements

### R1 — CSRF token must not appear in GET search URL (B1)
The header search `<form method="get" action="{% url 'search:search' %}">` at
`header_catalog.html:114-115` includes `{% csrf_token %}`, which renders
`<input type="hidden" name="csrfmiddlewaretoken">`. When the form submits via GET,
the token appears in the URL query string. The CSRF token is needed for AJAX POST
requests (favorites toggle, preferred-city) via the `X-CSRFToken` header mechanism
(already used in `ads/list.html:19`, `cabinet/favorites.html:19`), **not** inside the
GET search form.

**Fix:** Remove `{% csrf_token %}` from the GET search form. Keep the CSRF token
available via the `csrf_token` template variable for existing `hx-headers`
declarations on parent templates (e.g., `<body hx-headers='{"X-CSRFToken": "{{ csrf_token }}"}'>
in `ads/list.html:19`, `ads/detail.html:23`).

**Evidence:** Verified live — URL becomes `/search/?csrfmiddlewaretoken=...&q=term`.
Source: `header_catalog.html:115`.

### R2 — Clear button must return to pre-search state (B2)
The search input is `<input type="search">` (`header_catalog.html:117`). Browsers
render a native clear-X (×) that only clears the input field without triggering
navigation or form submission. No custom clear button exists in the markup.

**Fix:** Add an explicit clear control (button) wired to navigate the user back to
the pre-search browsing state. The target behavior is a **Product Owner decision**
(see PO-1).

**Evidence:** Verified live — clicking × clears the input text but URL still
contains `q=term`. Source: `header_catalog.html:117,130`.

### R3 — Header search must preserve category and city context (B3)
The header search form (`header_catalog.html:114-132`) contains only
`<input name="q">` and `{% csrf_token %}`. There are no hidden inputs for
`category`, `city`, or any filter parameters. Submitting the header search from a
`/category/<slug>/` or `/city/<slug>/` page drops the current context and lands on
`/search/?q=<term>` with no category or city.

**Fix:** When the user is on a category or city page, populate hidden `category`
and/or `city` inputs in the header form so they are carried into the `/search/` URL.
This is a **Product Owner decision** (see PO-3).

**Evidence:** Verified live — searching "мото" from `/category/transport/` yields
`/search/?q=мото` with no `category=transport`. Source: `header_catalog.html:114-132`.

### R4 — Sort must be available on FTS search results (B4)
The sort dropdown in `filter_form.html:103` is gated by `{% if not query %}` —
hidden entirely when `q` is present. In `search.py:156-208`, when `query` is truthy,
the sort parameter is parsed into context (`current_sort`) but the results are always
ordered by `-rank, -published_at, -id` (FTS relevance). The `sort=` query parameter
has no effect on FTS results.

**Fix:** Remove the `{% if not query %}` gate in `filter_form.html` so the sort
dropdown is always visible, and add a sort branch in `search.py` for FTS results
that respects the `sort=` parameter (with relevance-first as an option). This is a
**Product Owner decision** (see PO-2).

**Evidence:** Verified live — no sort dropdown on `/search/?q=бар`; adding
`&sort=price_asc` to URL produces relevance-ordered results, not price-ordered.
Source: `filter_form.html:103`, `search.py:156-208`.

### R5 — Price inputs must not display "None" (B5)
The price inputs at `filter_form.html:50-51` and `filter_form.html:56-57` render
`value="{{ min_price }}"` and `value="{{ max_price }}"`. When no price filter is set,
`min_price` and `max_price` are Python `None`, which Django stringifies to the literal
text "None" in the rendered `value` attribute.

**Fix:** Use `{{ min_price|default:'' }}` (or `{{ min_price|default_if_none:'' }}`)
so the `value` attribute is an empty string when no price is set.

**Evidence:** Verified live — `value="None"` on min/max price inputs. Source:
`filter_form.html:50-51,56-57`.

### R6 — Favorites badge must refresh after favorite toggle (B6, PO-5=B)
The header catalog JavaScript at `header_catalog.html:532-540` listens for the
`favorite:toggled` event and calls `htmx.get('/cabinet/favorites/count/', { target:
badge, swap: 'outerHTML' })`. However, the site loads HTMX 1.9.12 (from
`unpkg.com/htmx.org@1.9.12`), which does **not** expose the `htmx.get()` method.
HTMX 1.9.x only provides `htmx.ajax()`, `htmx.on()`, `htmx.trigger()`, `htmx.onLoad()`.

**Fix (per PO-5=B):** Upgrade HTMX to 2.x across all templates. After upgrade,
`htmx.get()` becomes available and the existing `header_catalog.html:536` call works
without modification. The HTMX 2.x upgrade is performed by the team's separate
audit task (`audit_task_htmx.md`) before T6.
(HTMX compatibility check across all templates and JS API calls).

**Evidence:** Verified live — `TypeError: htmx.get is not a function` in console
(two errors per favorite toggle). `Object.keys(htmx)` in browser console returns
`["onLoad", "on", "trigger", "ajax"]` (no `get`/`post`/`put`/`delete`). Source:
`header_catalog.html:532-540`, HTMX loaded at 5 template files via `unpkg.com/htmx.org@1.9.12`.

### R7 — Language parameter must be preserved across HTMX pagination (B7)
The pagination links in `ad_list.html:142-171` encode the URL as
`?page=N&q=<term>&category=<slug>&sort=<value>&...` but do **not** include the
`lang=<code>` query parameter. When HTMX fires `hx-get` and pushes the URL via
`hx-push-url="true"`, the new URL omits `lang`. The page content still renders
correctly in the last-selected language (via `lang_pref` cookie / session), but
the `lang` param is lost from the canonical URL.

**Fix:** Append `lang={{ LANGUAGE_CODE }}` to pagination link URLs in
`ad_list.html` (and chip-removal clear-all links).

**Evidence:** Verified live — navigating to `/category/transport/?lang=ru` then
clicking page 2 yields URL `?page=2&category=transport&sort=date_desc` (no `lang=ru`).
Source: `ad_list.html:142-171`.

### R8 — Autocomplete must show all suggestion sources on every keystroke
The autocomplete endpoint (`search/views/autocomplete.py:26-92`) correctly merges
and returns all suggestion sources: `user_history`, `category`, `city`, and
`popular_search`. The client-side `render()` function (`header_catalog.html:210-242`)
renders all four sections. The issue on low-traffic instances is that the
`popular_search` source is gated by `hit_count >= 10` (`popular_search.py:19`), so
it returns empty results, making the dropdown appear to show "only history."

**Fix (technical):** Seed popular search queries in dev/test environments so the
dropdown demonstrates all sections. **Fix (product):** The `min_hit_count=10`
threshold is confirmed as intended production behavior (see PO-4 — Confirmed: A).

**Evidence:** Live verification — autocomplete API returns all sources; popular
section empty due to `hit_count >= 10` gate. Source: `autocomplete.py:77-78`,
`popular_search.py:19,68-71`.

---

## 3. Conceptual development tasks

Each task is independent and can be owned/planned separately.

### T1 — Remove CSRF token from GET search form (B1, R1)

- **Purpose:** Eliminate CSRF token leakage in the GET search URL query string.
- **Concrete change:** Remove `{% csrf_token %}` from the header search `<form>` at
  `header_catalog.html:115`. The CSRF token remains available via the `csrf_token`
  template variable for existing `hx-headers='{"X-CSRFToken": "{{ csrf_token }}"}'`
  declarations in parent templates (`ads/list.html:19`, `ads/detail.html:23`), which
  protect AJAX POST requests (favorites, preferred-city) via the `X-CSRFToken` header.
- **Expected outcome:** Header search form submits to `/search/?q=<term>` with no
  `csrfmiddlewaretoken` parameter. AJAX POST requests (favorites toggle, preferred
  city) continue to work via `X-CSRFToken` header.
- **Dependencies:** None.
- **Test impact:** Update any tests asserting on the presence of
  `csrfmiddlewaretoken` in the header search form. Tests asserting on
  `X-CSRFToken` header usage or AJAX POST behavior remain valid.
- **Priority:** P1

### T2 — Implement wired clear button for search input (B2, R2)

- **Purpose:** Provide a functional clear control that returns the user to the
  pre-search browsing state.
- **Concrete change:** Add a visible clear button (×) next to the search input in
  `header_catalog.html:117-130`, wired with JavaScript to navigate based on PO-1:
  - If PO-1 = `history.back()`: `onclick="window.history.back()"` or clear-and-reset.
  - If PO-1 = `/`: `onclick="window.location.href='/'"`.
  Also handle the case where the user is on the `/search/` page itself (clearing
  `q` while retaining context if PO-3 is accepted).
- **Expected outcome:** Clicking the clear button removes the search query and
  navigates to the pre-search state (last browsing page via `history.back()`, or
  homepage if PO-1 defaults to `/`).
- **Dependencies:** PO-1 decision.
- **Test impact:** New Playwright e2e test for clear button navigation; existing
  template-source assertions (`test_autocomplete_template.py`) may need updating if
  the input element ID/class changes.
- **Priority:** P1

### T3 — Preserve category/city context in header search form (B3, R3)

- **Purpose:** Carry the active category and city into the `/search/` URL when the
  user searches from a scoped page (`/category/<slug>/` or `/city/<slug>/`).
- **Concrete change:** In the header search form (`header_catalog.html:114-132`),
  add conditional hidden inputs:
  - `{% if breadcrumb_category %}<input type="hidden" name="category" value="{{ current_cat.slug }}">{% endif %}`
  - `{% if current_city %}<input type="hidden" name="city" value="{{ current_city }}">{% endif %}`
  - Also carry `listing_purpose`, `features`, `min_price`, `max_price`, `condition`
    if PO-3 extends to full filter preservation (default: category + city only).
  Update `search.py:57-74` to honor the carried `category` param (already does —
  reads `request.GET.get("category")`).
- **Expected outcome:** Searching from `/category/transport/` yields
  `/search/?q=<term>&category=transport` (instead of `/search/?q=<term>`). The search
  results are scoped to the transport subtree. City is similarly preserved.
- **Dependencies:** PO-3 decision. Depends on understanding which context params to
  carry.
- **Test impact:** Existing tests asserting context-drop behavior
  (`test_search_view.py`, `test_autocomplete_template.py`) must be updated to assert
  context **preservation** instead.
- **Priority:** P2

### T4 — Enable sort on FTS search results (B4, R4)

- **Purpose:** Allow buyers to sort search results by date or price, with
  relevance as the default.
- **Concrete change:**
  1. In `filter_form.html:103`, remove the `{% if not query %}` gate so the sort
     dropdown is always visible.
  2. In `search.py:156-208`, add a sort branch within the FTS `if query:` block that
     respects `current_sort`:
     - `price_asc`: `order_by(F("price_normalized_eur").asc(nulls_last=True), "-rank", "-published_at", "-id")`
     - `price_desc`: `order_by(F("price_normalized_eur").desc(nulls_last=True), "-rank", "-published_at", "-id")`
     - `date_asc`: `order_by("published_at", "-rank", "-id")`
     - `date_desc` (default): `order_by("-rank", "-published_at", "-id")` (current behavior)
     This preserves the relevance-first approach by keeping `-rank` as a secondary
     sort key when the buyer explicitly chooses date or price.
- **Expected outcome:** Sort dropdown appears on `/search/?q=<term>`. Selecting
  "Price: low to high" re-orders results by price (NULLs last), with relevance as a
  tiebreaker.
- **Dependencies:** PO-2 decision.
- **Test impact:** Update tests asserting sort is hidden on search results
  (`test_search_view.py`, `test_catalog_filters.py`). Add tests for FTS + sort
  combination.
- **Priority:** P2

### T5 — Fix `value="None"` on price inputs (B5, R5)

- **Purpose:** Prevent the literal string "None" from rendering in the min/max price
  input fields.
- **Concrete change:** In `filter_form.html:51,57`, change
  `value="{{ min_price }}"` → `value="{{ min_price|default:'' }}"` and
  `value="{{ max_price }}"` → `value="{{ max_price|default:'' }}"`.
  The `default_if_none` filter is also acceptable.
- **Expected outcome:** Empty price input when no price filter is set; the `value`
  attribute is an empty string (or omitted), not "None".
- **Dependencies:** None.
- **Test impact:** None expected — tests likely don't assert on `value="None"`.
- **Priority:** P3

### T6 — Fix favorites badge refresh for HTMX 2.x (B6, R6, PO-5=B)

- **Purpose:** Ensure the favorites count badge refreshes after a favorite is toggled,
  now running on HTMX 2.x (upgraded separately via `audit_task_htmx.md`).
- **Concrete change:**
  1. HTMX 1.9.12 → 2.x upgrade is performed by the team as a separate audit task
     (`audit_task_htmx.md`). By T6 implementation time, HTMX 2.x is already loaded.
  2. In `header_catalog.html:536`, the `htmx.get()` call is now valid under HTMX 2.x —
     verify it works and produces no console errors.
  3. Audit all other HTMX JS API calls (`htmx.ajax`, `htmx.on`, `htmx.trigger`,
     `htmx.onLoad`) and HTMX attributes (`hx-get`, `hx-post`, `hx-target`, `hx-swap`,
     `hx-swap-oob`, etc.) across all 5 templates for HTMX 2.x compatibility:
     - If `htmx.ajax()` is removed/deprecated in 2.x, replace with `htmx.ajax()` equivalent
       or the new API.
     - If `hx-swap-oob` is deprecated, update to the 2.x syntax.
     - Ensure all event handlers (`htmx:afterRequest`, `htmx:afterOnLoad`, etc.) use
       correct 2.x event names.
  4. Update the HTMX CDN `<script>` tag from `@1.9.12` to `@2.x` if not already done
     by the upgrade audit task.
- **Expected outcome:** After toggling a favorite (heart icon), the favorites count
  badge in the header refreshes without console errors. All HTMX features across the
  site continue to function correctly on HTMX 2.x.
- **Dependencies:** PO-5=B (confirmed). HTMX 2.x upgrade pre-installed by
  `audit_task_htmx.md` before T6 begins.
- **Test impact:** Existing `test_favorites_badge.py` tests cover the server-side
  endpoint. Add Playwright e2e for client-side favorites toggle + badge refresh.
  Add regression tests for all HTMX-powered interactions (favorites, saved searches,
  preferred city, autocomplete) on HTMX 2.x.
- **Priority:** P1

### T7 — Preserve `lang` parameter in pagination and chip-removal URLs (B7, R7)

- **Purpose:** Keep the `lang=<code>` query parameter in URL when navigating via
  HTMX pagination links and chip-removal links.
- **Concrete change:** In `ad_list.html:142-171` (pagination links) and
  `ad_list.html:35-69` (chip removal links), append
  `{% if LANGUAGE_CODE %}&lang={{ LANGUAGE_CODE }}{% endif %}` to each URL.
  Alternatively, introduce a template tag or shared fragment for URL parameter
  assembly to avoid repetition across the 9+ pagination link definitions.
- **Expected outcome:** Navigating to page 2 from `/category/transport/?lang=ru`
  yields URL `?page=2&category=transport&sort=date_desc&lang=ru` (with `lang=ru`
  preserved).
- **Dependencies:** None.
- **Test impact:** Update tests asserting on pagination URL format
  (`test_catalog_filters.py::test_pagination_links_have_push_url_in_rendered_output`
  asserts `content.count("hx-push-url=\"true\"") == 9` — adding `lang` param does not
  change this count).
- **Priority:** P4

### T8 — Investigate and fix autocomplete "only history" on low-traffic instances (Bug #1, R8)

- **Purpose:** Ensure the autocomplete dropdown always shows all suggestion sources
  (categories, cities, popular) and does not appear to show "only history."
- **Concrete change:**
  - **Dev/test:** Seed `PopularSearch` rows with `hit_count >= 10` for common
    queries so the popular section is non-empty in dev/test environments. This can
    be done in the seed module (`apps/seed/`) or a test fixture.
  - **Production:** Document that the `hit_count >= 10` gate (`popular_search.py:19`)
    is the intended behavior; popular suggestions appear once queries reach 10+
    searches.
  - **Client-side:** Verify that the `htmx:afterRequest` handler in
    `header_catalog.html:244-254` correctly re-renders all four sections on every
    autocomplete XHR response (not just on first load). Add a defensive check:
    always call `render()` regardless of previous state.
- **Expected outcome:** On any instance (dev/test/prod), the autocomplete dropdown
  shows all four sections (Cities, Categories, Popular, History) whenever there are
  matching suggestions in each. The dropdown never appears to show "only history"
  unless all other sections genuinely have no matches.
   - **Dependencies:** PO-4 decision (threshold) — confirmed: A (keep threshold,
     seed dev/test). Requires runtime investigation (see Researcher Task 1) to
     confirm root cause.
- **Test impact:** `test_autocomplete.py` assertions on popular suggestions
  (`hit_count >= 10`) remain valid. New seed/popular_search fixtures needed for
  dev/test.
- **Priority:** P2

---

## 4. Product Owner decisions

The following decisions have been made by the Product Owner. Defaults were assumed
and are now **Confirmed**.

| # | Decision | Options | Status | Rationale |
|---|---|---|---|---|
| **PO-1** | Clear-X button behavior | A: `history.back()` · B: Navigate to `/` | **Confirmed: A** | OLX clears query but preserves path state. `history.back()` returns to the pre-search browsing position. |
| **PO-2** | Sort on FTS results | A: Honor `?sort=` with relevance-first default · B: Keep rank-only | **Confirmed: A** | Buyers on Avito/OLX can sort by price/date. Technical approach: keep `-rank` as secondary sort key. |
| **PO-3** | Header-search context preservation | A: Wire hidden `category`/`city` inputs · B: Keep context drop | **Confirmed: A** | Avito preserves region+category when searching from scoped pages. Scope: `category` + `city` only. |
| **PO-4** | Popular suggestions threshold | A: Keep `hit_count >= 10` + seed dev/test · B: Lower to 1 · C: Remove | **Confirmed: A** | Threshold prevents noise. "Only history" issue is perception on low-traffic instances — seed dev/test data. |
| **PO-5** | HTMX version | A: Patch `htmx.get()` → `htmx.ajax('GET', ...)` · B: Upgrade to HTMX 2.x | **Confirmed: B** (upgrade performed by team's separate audit task before T6) | PO commits to HTMX 2.x upgrade. B6 resolved by upgrading (not patching). T6 adapts existing code to 2.x. |

---

## 5. Research summary

### 5.1 Existing research (comprehensive, HIGH confidence)

The research phase (conducted by prior Researcher agents) produced four documents:

1. **`search-journeys-our-architecture.md`** — Maps the 6 search user journeys to the
   actual implementation (Django 5.2 HTMX MPA + PostgreSQL FTS). Source of truth is
   the implementation code, not the spec docs. Documents architectural realities:
   - Header search bar submits only `q` (line 79)
   - Sort on search page is relevance, not the `sort` param (line 80)
   - Price filtering is EUR-normalized (line 81)
   - Anonymous history in Django session, not a cookie (line 45)

2. **`search-journeys-spec.md`** — Final journey specification with validation
   criteria for all 6 scenarios + 4 cross-cutting behaviors. Includes 4 open product
   decisions.

3. **`search-journeys-validation.md`** — Concrete validation criteria per scenario,
   referencing existing test files and test data setup requirements.

4. **`olx-vs-avito-comparison.md`** — Competitor UX comparison + unified flow
   recommendation for Mko Bazuna.

5. **`01_search_patterns_verification.md`** — Live verification report from
   Playwright testing on `localhost:8000`, confirming 7 bugs (B1–B7) and verifying
   that the original Problem_01.md bug #1 (autocomplete regression) is likely
   expected behavior on low-traffic instances.

### 5.2 Source code verified (read-only)

| Component | Key files | Key finding |
|---|---|---|
| Header search form | `header_catalog.html:114-132` | `{% csrf_token %}` on GET form; only `name="q"` input; no hidden category/city |
| Search view (FTS) | `search/views/search.py:33-253` | `query` truthy → FTS rank order; sort param parsed but ignored when `q` present (line 156-208) |
| Autocomplete API | `search/views/autocomplete.py:26-92` | Returns all sources (history, category+city, popular); popular gated by `hit_count >= 10` |
| Popular search gate | `search/services/popular_search.py:19` | `_MIN_HIT_COUNT = 10` constant |
| Filter form | `ads/partials/filter_form.html:5-127` | `{% if not query %}` gates sort dropdown (line 103); `value="{{ min_price }}"` renders `None` (lines 51, 57) |
| Pagination links | `ads/partials/ad_list.html:142-171` | URLs omit `lang=` param |
| Favorites badge JS | `header_catalog.html:532-540` | Calls `htmx.get()` (HTMX 2.x API); site loads HTMX 1.9.12 |
| Favorites (correct usage) | `cabinet/favorites.html:47` | Uses `htmx.ajax('GET', ...)` — HTMX 1.9.x compatible |
| HTMX version | 5 template files | All load `htmx.org@1.9.12` from unpkg |

### 5.3 Approaches evaluated

**B6 (HTMX API mismatch) — PO-5=B:**
| Approach | No library upgrade? | Risk | Effort |
|---|---|---|---|
| A — Replace `htmx.get()` → `htmx.ajax('GET', ...)` (stay on HTMX 1.9.12) | Yes | Low (1-line change, already used in favorites.html:47) | 1-line change |
| B — Upgrade to HTMX 2.x + use `htmx.get()` | No (upgrade required) | High (audit all `hx-*` attributes + JS API across 5 templates for breaking changes) | Multi-file, multi-test |

**Decision (PO-5=B):** Upgrade to HTMX 2.x (performed by the team's separate audit task,
`audit_task_htmx.md`). B6 is resolved by the upgrade — `htmx.get()` becomes available
after HTMX 2.x is installed. T6 code changes must also verify all other HTMX JS API calls
and attributes are 2.x-compatible (audit done by the team, adaptation in T6).
Approach A (patch) is rejected by PO decision.

**B2 (clear button):**
| Approach | Navigates to pre-search state | Complexity |
|---|---|---|
| A — `history.back()` | Yes (native back stack) | Simple, 1 line of JS |
| B — Track pre-search URL in JS, navigate to it | Yes (more reliable than back()) | Moderate (need to capture referer on first search) |
| C — Navigate to `/` | No (loses category context) | Simple but less ideal |

**Decision (PO-1=A):** `history.back()` — confirmed by PO. The header search is a
full-page `<form method="get">` submit (not HTMX), so it pushes a standard history
entry — `history.back()` reliably returns to the pre-search page.

**Bug #1 (autocomplete perception):**
| Hypothesis | Evidence | Confidence |
|---|---|---|
| Popular section empty due to `hit_count >= 10` gate | `popular_search.py:19` — `_MIN_HIT_COUNT = 10`; verified via live API: Popular section empty | HIGH |
| Client-side `htmx:afterRequest` handler fails to re-render | `header_catalog.html:244-254` — handler filters on `detail.target !== dropdown` (correct for `hx-swap="none"`); `render()` always called on valid response | HIGH (code is correct) |
| Staleness from signed-cookie session | Anonymous history in Django session (DB row, not cookie); sessionid cookie keeps session alive | MEDIUM (possible stale session in dev) |
| Missing category/city matches | Depends on query text; verified that `render()` always renders all 4 sections | HIGH |

**Conclusion:** Root cause is the `hit_count >= 10` gate on low-traffic instances.
No code fix needed for production; seed dev/test data instead.

---

## 6. Assumptions

| # | Assumption | Justification |
|---|---|---|
| A1 | The "carousel" (gallery) bug (Spec 13) and the search bugs (this spec) are independent — no overlap in affected files or templates. | Spec 13 targets `detail.html` gallery; this spec targets `header_catalog.html` search form, `filter_form.html`, `ad_list.html` pagination. |
| A2 | The `X-CSRFToken` header mechanism already protects AJAX POST requests (favorites, preferred-city) on parent templates (`ads/list.html:19`, `ads/detail.html:23`, `cabinet/favorites.html:19`), so removing `{% csrf_token %}` from the GET search form does not break CSRF protection. | Verified in source: parent `<body>` has `hx-headers='{"X-CSRFToken": "{{ csrf_token }}"}'`. |
| A3 | The `category` and `city` query params on `/search/?q=…` are already read by `search.py:57,73` — so adding hidden inputs to the header form is a template-only change; no view-level changes needed for context preservation. | Verified: `search.py:57` reads `request.GET.get("category")`, `search.py:73` reads explicit_city. |
| A4 | The favorites badge count endpoint (`/cabinet/favorites/count/`) is already correct and returns the proper HTML fragment — only the client-side JavaScript call is broken. | Verified: `cabinet/views/favorites.py:51-68` renders `header_favorites_badge.html` with `favorites_count`. |
| A5 | The `lang` parameter preservation (B7) is a URL-canonicality issue, not a functional break — the `lang_pref` cookie re-establishes language on next full-page load. | Verified in live testing: content renders correctly in the selected language even when `lang` param is dropped from the URL. |
| A6 | The autocomplete "only history" issue (Bug #1) is a perception problem on low-traffic instances, not a code defect — the endpoint and client-side rendering are both correct. | Verified: `autocomplete.py` returns all sources; `header_catalog.html:210-242` renders all 4 sections; popular section empty due to `hit_count >= 10` gate. |
| A7 | HTMX 1.9.12 is loaded from a pinned CDN URL (`unpkg.com/htmx.org@1.9.12`) across all 5 templates — no package manager dependency to update. | Verified via grep: all 5 templates load `htmx.org@1.9.12`. |

---

## 7. Constraints

| # | Constraint | Source |
|---|---|---|
| C1 | CSRF protection for AJAX POSTs must use the `X-CSRFToken` header, not hidden inputs in GET forms. | Django security best practice; AGENTS.md rule 12 (logging, no print) |
| C2 | The site currently uses HTMX 1.9.12 (loaded from `unpkg.com/htmx.org@1.9.12` across 5 templates) — `htmx.get()` is NOT available. Per PO-5=B, HTMX will be upgraded to 2.x by the team's separate audit task (`audit_task_htmx.md`) before T6. By T6 implementation time, HTMX 2.x is loaded and `htmx.get()` becomes valid. T6 code changes must verify all HTMX JS API calls and attributes are 2.x-compatible. | `header_catalog.html:4` comment notes HTMX 1.9.12; verified via browser console `Object.keys(htmx)` returns `["onLoad", "on", "trigger", "ajax"]` (no `get`) |
| C3 | StrEnum must be used for all fixed values (sort options, etc.) — no plain strings. | AGENTS.md rule 10 |
| C4 | All user-visible strings must be wrapped in `{% trans %}`/`{% blocktrans %}` (templates) or `gettext`/`gettext_lazy` (Python). i18n completeness test must pass. | AGENTS.md rule 16; languages: ru (primary), en, bs |
| C5 | Production code > tests — if tests conflict with business logic, fix the tests. | AGENTS.md rule 2 |
| C6 | Avoid overengineering — prefer simple, obvious solutions. | AGENTS.md rule 5 |
| C7 | Search runs on PostgreSQL native FTS (per-language vectors). No external search engine. | `spec-index.md:48` |
| C8 | Buyers browse/search without login. Favorites, search history, and saved searches are the only authenticated features. | `buyer-stories.md` US-B1 |

---

## 8. Risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| **R1:** Removing `{% csrf_token %}` from the GET search form breaks CSRF protection for the header search submit itself. | Low | High (security) | The search form is GET (idempotent, not state-changing) — CSRF protection is not needed for GET. AJAX POSTs (favorites, preferred-city) use the `X-CSRFToken` header on `<body hx-headers>`, which is unaffected. Verify with a CSP/CSRF audit. |
| **R2:** Adding hidden `category`/`city` inputs to the header form (PO-3=A) could interfere with the on-page filter form's own hidden inputs, causing duplicate params. | Medium | Medium | The header form and filter form are separate `<form>` elements with different actions. Hidden inputs in the header form only apply to the header form submission. No conflict. |
| **R3:** Enabling sort on FTS results (PO-2=A) changes the relevance ordering — buyers may see less relevant results when sorting by price. | Medium | Low | Keep `-rank` as a secondary sort key so relevance still influences the order within the chosen sort. Default remains relevance-first (`date_desc` = `-rank, -published_at, -id`). |
| **R4:** Adding `lang` param to pagination URLs (T7) changes the URL structure, potentially breaking existing tests that assert on exact URL format. | Low | Low | Update affected tests (`test_catalog_filters.py::test_pagination_links_have_push_url_in_rendered_output` asserts on count of `hx-push-url="true"` — not affected by param addition). |
| **R5:** HTMX 2.x upgrade risks breaking existing HTMX-powered interactions across 5 templates due to API/attribute changes (`htmx.ajax`, `hx-swap-oob`, event names). | Medium | High | The HTMX 1.9.12 → 2.x upgrade is performed by the team's separate audit task (`audit_task_htmx.md`). T6 must verify and adapt all HTMX JS API calls and attributes for 2.x compatibility. Regression tests for all HTMX interactions (favorites, saved searches, preferred city, autocomplete) added. |
| **R6:** Seeding popular search queries in dev/test (T8) could mask a real issue if the production instance also has sparse popular queries. | Low | Medium | The threshold gate is a product decision (PO-4 confirmed: keep `10`). If production popular suggestions are sparse, that's a data-growth issue, not a code bug. |
| R7: Adding a wired clear button (T2) introduces new JavaScript that may conflict with existing event handlers in the IIFE at `header_catalog.html:180-548`. | Low | Low | The clear button can be a simple `<button onclick="window.history.back()">` — no additional event listener needed. Verify with Playwright e2e. |

---

## 9. Open questions

| # | Question | Status |
|---|---|---|
| Q1 | PO-1: Clear-X → `history.back()` or `/` (homepage)? | **Confirmed: A** (`history.back()`) |
| Q2 | PO-2: Enable sort dropdown + honor `sort=` on FTS results, relevance-first default? | **Confirmed: A** (honor sort) |
| Q3 | PO-3: Preserve `category` + `city` only, or full filter set in header search form? | **Confirmed: A** (category + city only) |
| Q4 | PO-4: Keep `min_hit_count=10` for production popular suggestions? | **Confirmed: A** (keep threshold, seed dev/test) |
| Q5 | PO-5: Patch `htmx.get()` → `htmx.ajax('GET', ...)` vs. upgrade to HTMX 2.x? | **Confirmed: B** (upgrade to HTMX 2.x) |
| Q6 | (Runtime investigation) Is the autocomplete "only history" issue (Bug #1) solely caused by the `hit_count >= 10` gate, or is there an additional client-side re-render issue on repeat XHRs? | Pending Researcher Task 1. |
| Q7 | Does the clear button need to preserve the `lang=` parameter in its navigation target? | If navigating via `history.back()` or `/`, the `lang_pref` cookie re-establishes language. **Assumed: no explicit `lang` preservation needed.** |

---

## 10. Researcher tasks

One Researcher investigation is needed: Task 1 to close Bug #1 uncertainty.

> **Note on HTMX 2.x upgrade (PO-5=B):** The HTMX 1.9.12 → 2.x upgrade is performed as
> a **separate architectural audit** (`audit_task_htmx.md`, conducted independently by
> the team). By the time T6 development begins, HTMX will already be upgraded to 2.x
> on the runtime. However, **the codebase will still contain HTMX 1.9.x-era code**
> (e.g., `htmx.ajax()` calls in templates) that may require adaptation to the HTMX 2.x
> API. T6's concrete change includes verifying and updating all HTMX JS API calls
> for 2.x compatibility as part of the favorites badge refresh fix.

### Researcher Task 1 — Bug #1 root-cause investigation (low-traffic autocomplete)

**Context:** Static analysis shows the autocomplete endpoint and client-side rendering
are correct (all 4 sections always render). But on low-traffic instances, the
"Popular" section is always empty (due to `hit_count >= 10` gate), and if the query
also doesn't match any category/city names, the dropdown appears to show "only
history." This matches the original Problem_01.md report: "first search works,
repeat search only shows history."

**Instructions for the Researcher:**
1. Investigate the current autocomplete architecture on the **running dev server**
   (`http://localhost:8000/`):
   - Call `GET /api/search/autocomplete?q=<term>` for queries that match categories,
     queries that match cities, and queries that match neither (to confirm popular
     section is empty).
   - Compare first vs. repeat search behavior — check if the `htmx:afterRequest`
     handler in `header_catalog.html:244-254` fires correctly on repeat XHRs.
   - Check if anonymous session state (`sessionid` cookie + Django session table)
     could cause stale results.
2. Investigate modern best practices for autocomplete suggestion rendering on
   low-traffic instances:
   - Should popular suggestions degrade gracefully when none have 10+ hits?
   - Should the dropdown show a "No popular suggestions" message, or hide the
     section header entirely?
3. Identify feasible approaches and recommend the preferred one:
   - **Approach A:** Seed popular queries in dev/test (no production change).
   - **Approach B:** Lower `min_hit_count` to 1 for production (shows all queries).
   - **Approach C:** Add a fallback "recent site-wide searches" section.
   - **Approach D:** Add client-side logic to show "Show all results for '<term>'"
     more prominently when only history is available.

**Expected output:** Confirmation that the root cause is the `hit_count >= 10` gate
(or discovery of an additional client-side issue), plus a recommendation for the
preferred approach.

---

## 11. Out of scope

- Adopting a JavaScript search library (Algolia, Elasticsearch) — the project uses
  native PostgreSQL FTS (`spec-index.md:48`).
- Adding a filter sidebar to the search results page — the on-page filter form
  (`filter_form.html`) already exists and is functional; only the sort dropdown
  gating and price input display need fixing.
- Changing the `hit_count >= 10` threshold for **production** — this is a product
   decision (PO-4 confirmed: keep threshold), not a code change. The threshold stays
  as-is.
- Back-end search relevance algorithm improvements (e.g., boosting, field weights)
  — the current FTS implementation (`-rank, -published_at, -id`) is out of scope.
- Mobile-specific search UI changes — the header search bar is responsive and shared
  across desktop and mobile; bugs are not viewport-specific.
- The "Saved search alerts" feature (US-B11) — this is a separate concern from the
  search bugs documented here. It is covered by `01_search_patterns_test_verification_top_plan.md`
  Block 11 but is not affected by the bugs in this spec.
- The filter form on the **listings** pages (`/`, `/category/`, `/city/`) is already
  correct — the bugs are specific to the **search** page (`/search/?q=…`) and the
  shared header.

---

## 12. Definition of Ready

The following must be true before an engineering task for any individual bug fix can
start:

1. **PO-1 confirmed** — Clear-X behavior decided (`history.back()` or `/`). ✅ Done.
2. **PO-2 confirmed** — Sort on FTS results decided (honor sort or rank-only). ✅ Done.
3. **PO-3 confirmed** — Header-search context preservation decided (carry category/city
   or accept context drop). ✅ Done.
4. **PO-4 confirmed** — Popular suggestions threshold confirmed (keep 10, lower, or
   remove). ✅ Done.
5. **PO-5 confirmed** — HTMX fix approach decided (patch API or upgrade to 2.x). ✅ Done
   — **B** (upgrade to HTMX 2.x, performed by the team's separate audit task).
6. **Researcher Task 1 completed** — Root cause of Bug #1 confirmed (likely the
   `hit_count >= 10` gate; possibly additional client-side issue).
7. **HTMX 2.x upgrade installed** — The HTMX 1.9.12 → 2.x upgrade has been applied
   to the runtime (via `audit_task_htmx.md`). T6 code changes are scoped to adapting
   existing HTMX 1.9.x-era code to the 2.x API.
8. **Test baseline green** — `make test` passes on `main` (fast gate, skips `seed`).
9. **Affected test files identified** — Test files that assert on the current (buggy)
   behavior are listed in each task's "Test impact" section above.
10. **i18n checked** — Any new user-visible strings introduced by fixes are wrapped in
    `{% trans %}` / `{% blocktrans %}` (templates) or `gettext`/`gettext_lazy` (Python).
    `make makemessages` + `make compilemessages` run before commit.
    `test_i18n_completeness.py` passes.
11. **Acceptance criteria defined** — Each task's expected outcome is documented above
    and a test assertion is specified.

### Acceptance criteria summary (per task)

| Task | Acceptance criteria |
|---|---|
| T1 (CSRF) | `GET /search/?q=term` URL contains no `csrfmiddlewaretoken` param. AJAX POSTs (favorites, preferred-city) still include valid `X-CSRFToken` header. |
| T2 (Clear-X) | Clicking clear button navigates to pre-search state (`history.back()` or per PO-1). `q` param removed from URL. |
| T3 (Context) | Searching from `/category/transport/` yields `/search/?q=<term>&category=transport`. Searching from `/city/podgorica/` yields `&city=podgorica`. Results scoped to the correct subtree/city. |
| T4 (Sort on FTS) | Sort dropdown visible on `/search/?q=<term>`. Selecting "Price: low to high" re-orders results by `price_normalized_eur` ASC (NULLs last). `?q=term&sort=price_asc` produces price-ordered, not rank-ordered, results. |
| T5 (value="None") | Price inputs render `value=""` (empty) when no price filter is set. No literal "None" string in any input `value` attribute. |
| T6 (HTMX fix) | Toggling a favorite does not produce `TypeError: htmx.get is not a function` in console. Favorites count badge updates after toggle. |
| T7 (lang param) | Page 2 URL from `/category/transport/?lang=ru` is `?page=2&category=transport&sort=date_desc&lang=ru` (includes `lang=ru`). |
| T8 (Autocomplete) | Autocomplete dropdown renders all 4 sections (Cities, Categories, Popular, History) whenever matches exist. On dev/test, Popular section is non-empty for seeded queries. |

---

## 13. References

- **Original problem:** `.ai/problems/Problem_01.md`
- **Live verification report:** `.ai/problems/01_search_patterns_verification.md`
- **Architecture mapping:** `.ai/research/search-journeys-our-architecture.md`
- **Journey specification:** `.ai/research/search-journeys-spec.md`
- **Validation criteria:** `.ai/research/search-journeys-validation.md`
- **Competitor comparison:** `.ai/research/olx-vs-avito-comparison.md`
- **Test plan:** `.ai/problems/01_search_patterns_test_verification_top_plan.md`
- **Product spec (search patterns):** `docs/01-spec/search-patterns.md`
- **Product spec (filter UI):** `docs/01-spec/filter-ui.md`
- **Technical specification:** `docs/01-spec/technical-specification.md`
- **Spec index:** `docs/01-spec/spec-index.md`
- **Buyer stories:** `docs/04-user-stories/buyer-stories.md`
- **Owner decisions:** `docs/05-owner-decisions/index.md`
- **HTMX 2.x upgrade audit:** `.ai/problems/audit_task_htmx.md` (team audit, performed before T6)

### Source code (read-only)

| Component | File:lines |
|---|---|
| Search view (FTS) | `src/backend/apps/search/views/search.py:33-253` |
| Autocomplete view | `src/backend/apps/search/views/autocomplete.py:26-92` |
| Popular search service | `src/backend/apps/search/services/popular_search.py:1-80` |
| Header catalog template | `src/backend/templates/components/header_catalog.html:113-549` |
| Filter form template | `src/backend/templates/ads/partials/filter_form.html:5-127` |
| Ad list partial (chips + pagination) | `src/backend/templates/ads/partials/ad_list.html:1-193` |
| Favorites count badge view | `src/backend/apps/cabinet/views/favorites.py:51-68` |
| Favorite heart component | `src/backend/templates/components/favorite_heart.html:1-38` |
| HTMX script tags | 5 templates: `ads/list.html:16`, `ads/detail.html:20`, `cabinet/hub.html:14`, `cabinet/favorites.html:16`, `cabinet/saved_searches.html:15` |

### Test files (existing)

| Test file | Coverage |
|---|---|
| `src/backend/apps/search/tests/test_search_view.py` | Search view behavior, FTS ordering, history recording |
| `src/backend/apps/search/tests/test_autocomplete.py` | Autocomplete endpoint, suggestions, rate limiting |
| `src/backend/apps/search/tests/test_autocomplete_template.py` | Template-source assertions for autocomplete attributes |
| `src/backend/apps/cabinet/tests/test_favorites_badge.py` | Favorites count badge fragment endpoint |
| `src/backend/apps/ads/tests/test_catalog_filters.py` | Filter application, chip removal, clear-all, HTMX contract |
| `src/backend/apps/ads/tests/test_listings_sort.py` | Sort behavior on listings pages |
| `src/backend/apps/ads/tests/test_detail_context.py` | Ad detail page context and rendered HTML |

---

*End of specification. Status: Draft — PO-1–PO-5 confirmed. PO-5=B (HTMX 2.x
upgrade) is performed by the team's separate audit task (`audit_task_htmx.md`)
before T6 implementation begins. T6 code changes are scoped to adapting existing
HTMX 1.9.x-era code to the 2.x API. Once Researcher Task 1 completes (Bug #1
root-cause confirmation), all DoR items are satisfied and implementation
(T1–T8) can begin.*
