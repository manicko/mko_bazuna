# Specification: Filter Regression — Clear-All Visibility, Price Chip, City/Category Preservation, Language-Switch Consistency

**Status:** Draft — incorporates Researcher findings, Auditor review, and **confirmed PO decisions** (Q1=C+price-as-chip, Q2=A, Q3=A)  
**Version:** 1.0  
**Date:** 2026-09-03  
**Source Problem:** `.ai/problems/Problem_04.md` (RU)  

---

## 1. Problem Statement

After implementing Plans 17 (`search-clear-ux`) and 18 (`price-enforcement_and-filter-reset`), the catalog filter functionality has fully regressed on the website. The site exhibits five user-facing defects in the filter UI:

| # | Problem (translated from RU) | Correct Behavior |
|---|---|---|
| 1 | The "Clear all filters" button is **always visible**, even when no filters are active. It should only appear when at least one filter chip is active, and disappear after clearing. | Button visible only when chips-block condition is true |
| 2 | After selecting a price range and applying the filter, a **plain text** "Price: {min}–{max}" appears instead of a **clickable chip** that can be individually dismissed — unlike the purpose/condition/features chips. | Price range should render as a removable chip, identical in pattern to other filter chips |
| 3 | *(Not numbered in problem statement — skipped)* | — |
| 4 | When changing the city (via header dropdown or autocomplete suggestion), the **category filter is reset** — lost from the URL. | Both category and city should be preserved simultaneously |
| 5 | When changing language, **all filters may or may not be reset** — inconsistent/unpredictable behavior. | Language switching should consistently preserve all active filters |

The root causes were introduced by commits `da1b33d` (Plan 17: search clear button consolidation) and the chain of commits implementing Plan 18 (T5–T17: price enforcement, filter-reset, and price-range summary), culminating in commit `41ac009` which moved the clear-all link out of all conditionals without adding a visibility guard.

---

## 2. Facts (Verified by Code Analysis)

### 2.1 Clear-all button always visible (Problem 1)

**File:** `src/backend/templates/ads/partials/ad_list.html` (L77–83), `src/backend/apps/ads/views/listings.py` (L447–467), `src/backend/apps/search/views/search.py` (L274–300)

- `ad_list.html` L77–83 renders the clear-all `<a>` link with **no conditional guard whatsoever**. It is always present in the template output.
- The `filter-ui.md` spec (L396) calls for `{% if has_active_filters %}` wrapping the link, but this was **never implemented**. The existing chips-block condition `{% if current_listing_purpose or current_features or current_condition %}` (L39) does not include price range, and the clear-all link (L77–83) is rendered **outside** that condition entirely with no guard.
- **Regression point**: Commit `41ac009` ("fix(T10+T11)") moved the clear-all link from inside the `{% if current_listing_purpose or current_features or current_condition %}` block (L39, which conditionally showed it when purpose/feature/condition chips were present) to **outside** that block with no replacement guard. Before this commit, the button was at least conditionally shown when purpose/features/condition chips were present.

### 2.2 Price range as plain text (Problem 2)

**File:** `src/backend/templates/ads/partials/ad_list.html` (L32–37), `src/backend/apps/ads/views/listings.py` (L347–359 + L457–458), `src/backend/apps/search/views/search.py` (L110–122 + L283–284)

- `ad_list.html` L32–37 renders the price range as a plain `<div class="filter-summary">` containing only `{% blocktrans %}` text — **no `&times;` removal link**, no chip styling (`inline-flex ... rounded-full`), not inside the chips container.
- The sibling filter chips (purpose L41–53, condition L54–66, features L67–74) are `<span class="inline-flex items-center px-3 py-1 ... rounded-full">` elements with `&times;` `<a>` removal links.
- The price summary block is **outside** the `{% if current_listing_purpose or current_features or current_condition %}` conditional at L39 — so even if price is set, the chip container doesn't activate.
- The context variables `active_price_min` / `active_price_max` (parsed `Decimal` or `None`) are correctly exposed by both views (listings.py L457–458, search.py L283–284), confirming the views were updated by Plan 18 but the template was not fully fixed.

### 2.3 City change resets category (Problem 4)

**File:** `src/backend/apps/ads/urls.py` (L24–27), `src/backend/templates/components/header_catalog.html` (L340, L562), `src/backend/apps/ads/views/listings.py` (L263–285, L293–320)

- **URL architecture defect**: `ads/urls.py` defines mutually exclusive path patterns — `category/<slug:category_slug>/` and `city/<slug:city_slug>/` — only one can be active in the URL path at a time. There is no pattern that supports both simultaneously.
- `listings.py` L263–285: `category_slug` comes from the URL **path** parameter; `request.GET.get("category")` is used only for did-you-mean suggestions (the `elif` branch at L282), NOT for actual category filtering.
- `listings.py` L293–320: `city` CAN come from either the URL path OR `request.GET.get("city")` — both work as real filters. This asymmetry (city as query param works, category as query param doesn't) is the root of the regression.
- `header_catalog.html` L340 (autocomplete suggestion click) and L562 (city dropdown click): the JS navigates via `window.location.href = '/city/' + encodeURIComponent(slug) + '/'` — a full-page navigation to a city-only path that **discards the category path param entirely**.
- The `filter_form.html` hidden inputs (L11–12) send `category` and `city` as query params, but on the listings page, `?category=` is ignored for filtering (only the path works). On the search page, `?category=` IS used for filtering.
- **Pre-existing**: This URL architecture limitation existed before Plans 17/18. The header_catalog.html L340/L562 city navigation to `/city/<slug>/` has always existed. However, the regression context implies it became noticeable after the filter changes (users now expect both to persist).

### 2.4 Language switching inconsistency (Problem 5)

**File:** `src/backend/templates/ads/list.html` (L23, L36), `src/backend/templates/components/language_switcher.html` (L35), `src/backend/apps/core/templatetags/dict_tags.py` (L47–69), `src/backend/apps/core/middleware/language.py`

- `list.html` L23 includes `components/header_catalog.html` (which contains the language switcher) **outside** the `#ad-list` HTMX swap target (L36).
- When a buyer applies a filter via HTMX `hx-get` with `hx-push-url="true"` (chip removal, pagination, filter form submit, clear-all), the `#ad-list` div is swapped but the header (including all language switcher links) is **not re-rendered**.
- The language switcher links are built using `query_replace` (dict_tags.py L47–69), which calls `request.GET.copy()` at **render time** — capturing the query params from the last **full page load**, not the current browser URL state.
- After an HTMX filter change, the browser URL shows the updated params (e.g., `?features=delivery&min_price=100`), but the language switcher links still contain the stale params from the previous full page load (e.g., just `?min_price=100`). Clicking a language link navigates to the stale URL, **dropping the HTMX-applied filters**.
- When filters are applied via full page reload (e.g., sort dropdown `onchange="this.form.requestSubmit()"`, or form submit without HTMX), the header IS re-rendered with the correct params, so language switching preserves everything.
- This **asymmetry** (HTMX changes → stale header; form submissions → fresh header) produces the "may or may not reset" inconsistent behavior.
- Additionally, `query_replace` preserves the `page` param, so switching language on page 3 keeps `page=3` — which in the new language may not exist (different result count/sort), causing further confusion.
- The `query_replace` function correctly handles multi-value params (e.g., `features=a&features=b`) and preserves all `request.GET` keys not in kwargs — the function itself is not buggy. The bug is in the **staleness** of its render-time snapshot.

### 2.5 Existing test gaps

**File:** `src/backend/apps/ads/tests/test_catalog_filters.py`

- `test_clear_all_filters_has_push_url` (L665–687): asserts the clear-all `hx-get` URL drops `q` and `sort`, and has `hx-push-url="true"`. **Does NOT assert visibility condition** — it doesn't check that the link is wrapped in the chips-block conditional.
- `test_all_htmx_links_have_push_url` (L647–654): hard-counts `9` `hx-get=` and `9` `hx-push-url="true"` in `ad_list.html`. Adding a price-chip removal link would change this to 10.
- `test_lang_param_in_all_htmx_urls` (L656–663): asserts ≥18 `LANGUAGE_CODE` occurrences (9 links × 2 attrs). A new price-chip link would add 2 more.
- No test verifies that the clear-all link is hidden when no chips (including price) are active.
- No test covers language switching after HTMX navigation (the staleness scenario).
- No test covers city selection preserving category on the listings page.
- `test_query_replace` tests (test_templates.py L104–131) do NOT test multi-value params preservation or `page` param preservation.

---

## 3. Confirmed Requirements

| ID | Requirement | Source |
|---|---|---|
| CR-1 | The "Clear all filters" button must only render when at least one filter chip is active (purpose, condition, features, or price range). It must disappear after all filters are cleared. | Problem 1, PO-Q1=C |
| CR-2 | "Active chips" condition: `current_listing_purpose` OR `current_condition` OR any `current_features` OR (`active_price_min` OR `active_price_max`). The `sort` parameter is **not** part of the visibility condition. `page` and `lang` alone do NOT trigger visibility. | Problem 1, PO-Q1=C |
| CR-3 | When active chips exist, the clear-all button resets ALL query params (`q`, `sort`, `min_price`, `max_price`, `listing_purpose`, `listing_condition`, `features`, `page`) via HTMX `hx-get` with `hx-push-url="true"`. | Problem 1, R-FR-01, R-FR-04 |
| CR-4 | On the search results page (`/search/?q=...`), clear-all preserves the search query `q` but resets all other filter params. On the listings/catalog page, clear-all resets all params including `q` (though `q` is absent on listings). | Problem 1, filter-ui.md L414–416, PO-Q3=A |
| CR-5 | Category and city are path parameters and are naturally preserved by clear-all (not in the query string). | Problem 1, R-FR-03 |
| CR-6 | The price-range display must be a **clickable chip** (not plain text) with a `&times;` removal link, matching the pattern of the purpose/condition/features chips. | Problem 2 |
| CR-7 | The price-range chip removal link must drop only `min_price` and `max_price` from the URL, preserving all other active filters (q, category, city, purpose, condition, features, sort). | Problem 2, pattern of existing chips |
| CR-8 | Selecting a city while a category is active must preserve the category filter. Both filters must coexist. | Problem 4 |
| CR-9 | When changing language, ALL active filters must be consistently preserved, regardless of whether they were applied via HTMX partial updates or full page reloads. | Problem 5 |
| CR-10 | The language switcher links must reflect the current browser URL state (all active query params) at all times, including after HTMX navigation. | Problem 5 |

---

## 4. Conceptual Development Tasks

### Task T1: Add price to chips-block visibility condition

**Purpose:** Extend the existing chips-block conditional to include price range, so the chip container (and clear-all button) activate when a price filter is set.
**Expected outcome:** The clear-all button and chip container appear when any of: purpose, condition, features, OR price range is active.
**Changes:** In `ad_list.html` L39, change the condition from `{% if current_listing_purpose or current_features or current_condition %}` to also include `{% if ... or active_price_min or active_price_max %}`. No new context variable needed — `active_price_min`/`active_price_max` are already exposed by both views.
**Dependencies:** None (foundational).
**Affected files:** `ad_list.html`, `listings.py` (verify `active_price_min`/`active_price_max` context), `search.py` (verify same).
**Test impact:** Add test that chip container appears when only price is active; clear-all button hidden when no chips active (including no price).

### Task T2: Wrap clear-all link in visibility conditional

**Purpose:** Make the "Clear all filters" button conditionally render based on the chips-block condition.
**Expected outcome:** Button only appears when at least one chip (purpose, condition, features, or price) is active; disappears after clearing.
**Changes:** Move the clear-all `<a>` link (ad_list.html L77–83) **inside** the chips-block `{% if %}` condition (L39). Currently it's outside the conditional at L77–83 (unguarded). It should only render when the chips block is visible.
**Dependencies:** T1.
**Affected files:** `ad_list.html`.
**Test impact:** Assert clear-all link is hidden when no chips active; assert it appears when any chip is active. `test_clear_all_filters_has_push_url` should verify the link is wrapped in the chips conditional.

### Task T3: Convert price range to a removable chip

**Purpose:** Render the price-range summary as a clickable chip with a removal `&times;` link, matching the pattern of other filter chips. Also activates the chip container when price is set.
**Expected outcome:** Price range appears as an `inline-flex ... rounded-full` chip with a removal link that drops only `min_price`/`max_price`.
**Changes:** Replace the `<div class="filter-summary">` (L32–37) with a `<span>` chip inside the chips container (L39–76 block). The price chip must be placed **inside** the `{% if ... or active_price_min or active_price_max %}` conditional so it appears when price is set. The removal link should preserve all other filters and reset `page` to 1.
**Dependencies:** T1 (the condition extension must be in place).
**Affected files:** `ad_list.html`.
**Test impact:** `test_all_htmx_links_have_push_url` count changes from 9 to 10; `test_lang_param_in_all_htmx_urls` minimum changes from 18 to 20. Add test verifying price chip appears as a removable chip.

### Task T4: Add search-page clear-all `q` preservation

**Purpose:** On the search results page, clear-all should preserve the search query `q` while resetting all other filter params.
**Expected outcome:** Search page clear-all URL includes `?q=<query>` but not other filter params.
**Changes:** Make the clear-all `hx-get` URL conditional on whether the current view is a search (detectable via `{% if query %}` — the `query` context variable is set by `search()` but not by `listings()`).
**Dependencies:** T2 (same template area).
**Affected files:** `ad_list.html`, `listings.py` (export `query=None` for context consistency), `search.py`.
**Test impact:** `test_clear_all_filters_has_push_url` must be split or parameterized for search vs. listings; the current assertion that `q` is absent from the reset URL is wrong for the search page.

### Task T5: Fix city+category URL coexistence (header navigation)

**Purpose:** When selecting a city from the header dropdown or autocomplete, preserve the category path param and all existing query params.
**Expected outcome:** City selection navigates to the current path + `?city=<slug>` (preserving category, q, sort, features, etc.) instead of `/city/<slug>/` (which discards everything).
**Changes:** Modify `header_catalog.html` JS (L340 autocomplete click handler, L562 city dropdown click handler) to use `URLSearchParams` to set/replace the `city` param on the current URL, rather than hard-navigating to `/city/<slug>/`.
**Recommended approach:** Option A from Q2 — city as query param alongside the category path. The `listings()` view already supports `?city=` as a filter (L302–309), and `current_city` is correctly populated from it (L303, L325). The `search()` view also supports `?city=` (L81–89).
**Dependencies:** None (independent JS change).
**Affected files:** `header_catalog.html`.
**Test impact:** Add tests verifying that selecting a city from the header preserves the category path and other query params.

### Task T6: Fix language-switcher staleness after HTMX navigation

**Purpose:** Ensure the language switcher links always reflect the current browser URL state, including after HTMX partial updates.
**Expected outcome:** Switching language after any filter change (HTMX or full reload) consistently preserves all active filters.
**Changes:** Two approaches:
- **Approach A (recommended):** Move `language_switcher.html` inside the `#ad-list` HTMX swap target so it re-renders on every partial swap with the current `request.GET`.
- **Approach B:** Add an `htmx:afterSwap` JS listener that rewrites the language link `href`s from `window.location.search`.
- **Approach C:** Change `query_replace` to also strip the `page` param (since page > 1 shouldn't be carried across language switches when filters change).
**Recommended approach:** A — structural fix (move header component inside swap target). If that causes rendering issues (the header is used on multiple pages), use Approach B.
**Dependencies:** None (independent JS/template change).
**Affected files:** `list.html`, `header_catalog.html`, `language_switcher.html`, `ad_list.html` (if A).
**Test impact:** Add integration test verifying language switcher links reflect current URL params after HTMX navigation.

### Task T7: Update tests for all fixes

**Purpose:** Update existing tests that encode wrong behavior and add new tests for the fixed behaviors.
**Expected outcome:** All tests pass and cover the corrected behaviors.
**Changes:**
	- Strengthen `test_clear_all_filters_has_push_url` to verify the clear-all link is wrapped in the chips conditional (not unconditionally rendered)
- Update `test_all_htmx_links_have_push_url` from count 9 → 10 (after T3 adds a price-chip link)
- Update `test_lang_param_in_all_htmx_urls` from ≥18 → ≥20
- Split clear-all test for search page (`q` preserved) vs. listings page (`q` absent)
- Add tests for: clear-all hidden when no filters active, price chip removal, city+category coexistence, language switcher after HTMX
**Dependencies:** T1–T6.
**Affected files:** `test_catalog_filters.py`, `test_templates.py`, new test files.

### Task T8: i18n verification

**Purpose:** Ensure all modified/added template strings are wrapped in `{% trans %}`/`{% blocktrans %}` and `.mo` files are compiled.
**Expected outcome:** `test_i18n_completeness.py` passes with no new violations.
**Dependencies:** T2, T3, T4.
**Affected files:** `ad_list.html`, locale `.po`/`.mo` files.

---

## 5. Product Owner Decisions

| Q | Question | Options | Resolved Choice | Rationale |
|---|---|---|---|---|
| **Q1** | What triggers "Clear all filters" button visibility? | A: Any filter/q/sort active (excl. page/lang) · B: Only q/price/purpose/condition/features (excl. sort) · C: Only chips-visible params (purpose/condition/features) **and price must be added as a chip** | **C + price as chip** (confirmed by PO) | PO specifies: button should render when chips are visible. The current condition `{% if current_listing_purpose or current_features or current_condition %}` is correct in principle but incomplete — price range must be added to this condition so that it also counts as a "chip". No separate `has_active_filters` variable needed; extend the existing chips condition to include `active_price_min` and `active_price_max`. |
| **Q2** | When city is selected while category is active, what URL? | A: `/category/<cat>/?city=<slug>` (city as query param) · B: `/city/<slug>/?category=<cat>` (category as query param) · C: New combined path `/category/<cat>/city/<city_slug>/` | **A** (confirmed by PO) | Minimal change: `listings.py` already supports `?city=` as a filter (L302–309). Option B fails because `?category=` is suggestion-only on listings. Option C requires new URL patterns + view refactoring (highest risk). |
| **Q3** | On search page, does clear-all preserve `q`? | A: Yes, preserve `q` (per spec) · B: No, clear everything | **A** (confirmed by PO) | Spec filter-ui.md L414–416 explicitly says search page clear-all "preserves q." The search query is the primary content of the page; clearing it takes the user to the unfiltered catalog, which is not the intent of a "filter reset." |

---

## 6. Research Summary

### Researcher findings (verified)

1. **Clear-all button (Problem 1):** Root cause confirmed — `ad_list.html` L77–83 renders the clear-all `<a>` link with **no conditional guard whatsoever**. The link is outside the chips-block condition `{% if current_listing_purpose or current_features or current_condition %}` (L39). Per PO-Q1=C, the fix is to extend this condition to also include `active_price_min or active_price_max` and move the clear-all link **inside** that extended condition. No new `has_active_filters` context variable is needed.

2. **Price chip (Problem 2):** Root cause confirmed — price summary (L32–37) is a plain `<div>` with `{% blocktrans %}`, no removal link, not styled as a chip, and outside the chips container. The `active_price_min`/`active_price_max` context vars are correctly exposed by both views. Fix: convert to chip with removal link, add price to the chips-block condition. Adding a removal `hx-get` link increments the `ad_list.html` link count from 9 to 10.

3. **City+category (Problem 4):** Root cause confirmed — `ads/urls.py` defines mutually exclusive path patterns for category and city. The header JS navigates to `/city/<slug>/` discarding the category path. The `listings()` view treats `?category=` as suggestion-only (L282–285) but `?city=` as a real filter (L302–309). Fix: change header JS to use `?city=<slug>` query param alongside the current path.

4. **Language switching (Problem 5):** Root cause confirmed — `list.html` L23 includes the header (with language switcher) outside the `#ad-list` HTMX target (L36). After HTMX filter changes, the language switcher links retain stale `request.GET` params from the last full page load. The `query_replace` tag itself is not buggy — the issue is the staleness of its render-time snapshot. Fix: restructure so the language switcher is inside the swap target, or use JS to update links on `htmx:afterSwap`.

5. **`query_replace` correctness:** Verified — `request.GET.copy()` preserves multi-value params (e.g., `features=a&features=b`), and `query.urlencode()` preserves them in the output. The function correctly handles the `page` param preservation (which is itself a minor secondary issue).

### Audit findings

- **Test `test_clear_all_filters_has_push_url` (test_catalog_filters.py L665–687)** encodes wrong behavior for the search page — it asserts `q` is absent from the reset URL, but the spec says `q` should be preserved on search pages.
- **Test `test_all_htmx_links_have_push_url` (L647–654)** hard-counts 9 links; adding a price-chip removal link requires updating this to 10.
- **No test** exists that verifies the clear-all link is hidden when no chips (including price) are active, or that it appears when only price is active.
- The 18 inline URL constructions in `ad_list.html` (chip/pagination links) are repetitive but flagged as "No structural change" by the spec (filter-ui.md §"Pagination URL Preservation"). This is a maintainability concern but not in scope for this regression fix.

---

## 7. Assumptions

1. The fix scope is limited to template, view, and JS changes — no database schema or migration changes are needed.
2. The listings/search views already expose all necessary context variables (`active_price_min`, `active_price_max`, `query`, `current_sort`, `min_price`, `max_price`, `current_listing_purpose`, `current_features`, `current_condition`). No new context variable needed — the fix extends the existing chips-block condition to include price range.
3. The price chip removal link follows the same URL pattern as other chip removal links (preserving all other params, resetting `page` to 1).
4. The `listings()` view's support for `?city=` as a query parameter (L302–309) is the intended mechanism for city filtering when city is used as a query param alongside a category path.
5. The header is shared across `list.html`, `detail.html`, and other templates — any move of the language switcher into the HTMX swap target must be evaluated for side effects on non-catalog pages.
6. The `query_replace` template tag correctly preserves all GET params including multi-value params — the language-switch bug is purely about render-time staleness, not the tag's logic.

---

## 8. Constraints

| Constraint | How Satisfied |
|---|---|
| C1: All filter chips must be removable with a single `×` link | Price chip (T3) follows the same pattern |
| C2: Clear-all must use HTMX `hx-get` with `hx-push-url="true"` | Existing pattern preserved (T2, T4) |
| C3: No new frontend framework (vanilla JS only) | All JS changes use existing inline `<script>` patterns (T5, T6) |
| C4: i18n: all new visible strings wrapped in `{% trans %}`/`{% blocktrans %}` | T8 verifies `test_i18n_completeness.py` passes |
| C5: `StrEnum` for all constants | `AdSort` StrEnum used elsewhere in views for sort handling |
| C6: djlint-clean templates | All template changes pass `uv run djlint` |
| C7: Tests must not be distorted to match broken behavior | Per AGENTS.md rule #2 — tests updated to assert correct behavior (T7) |
| C8: City as query param must be supported by both views | `listings.py` L302–309 and `search.py` L81–89 already support `?city=` |

---

## 9. Risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Moving language_switcher inside `#ad-list` swap target breaks non-catalog pages (detail, dashboard) that also include the header | Medium | High | Evaluate scope of `{% include %}` — detail.html L23 also includes `header_catalog.html`. Use Approach B (JS rewrite) if structural change is too risky. |
| Adding price-chip removal link breaks `test_all_htmx_links_have_push_url` hard-count (9→10) | High | Low | Update the test explicitly in T7 |
| City navigation JS change may break autocomplete city selection on search page | Medium | Medium | Test both `/search/?q=...` and `/category/<slug>/` flows after JS change |
| `has_active_filters` variable not needed (PO chose C: extend existing chips-block condition instead) | Low | Low | N/A — PO explicitly chose option C over A/B |
| Search-page clear-all preserving `q` may surprise users who expect full reset | Low | Low | Spec explicitly defines this behavior; document in user-facing text |
| Price chip removal link URL construction must match the pattern of other chips (18 inline URLs) | High | Low | Follow the exact same `hx-get`?page=1&<preserve-other-params>` pattern |
| HTMX `htmx:afterSwap` handler may not fire for full page loads (breaking header update) | Low | Low | The `htmx:afterSwap` handler only runs for HTMX swaps; for full loads the header is already correct |

---

## 10. Open Questions

1. **Language switcher inside swap target (T6):** Moving `language_switcher.html` (inside `header_catalog.html`) into the `#ad-list` div would require rendering the header twice (once in `list.html` for full loads, once in the HTMX partial). This is architecturally awkward. Is Approach B (JS rewrite of `href`s on `htmx:afterSwap`) acceptable? **Deferred to implementation** — the PO should confirm preference between structural fix and JS fix.

2. **City navigation on search page:** The search page uses `/search/` as the path. When changing city from the header on the search page, should the URL become `/search/?q=...&city=<slug>`? The recommended JS fix (`URLSearchParams` on current path) handles this naturally, but needs confirmation.

3. **Price chip vs. summary distinction:** The current code has both a `<div class="filter-summary">` (L32–37) and chips (L39–76). Should the price summary be converted INTO a chip (merging the two), or should the summary remain as a text label AND a chip be added? **Recommended: convert the summary div into a chip** — having both a text summary and a chip for the same filter is redundant.

4. **Mobile city drawer:** Problem 4 references the header city dropdown. Is there also a mobile city drawer that needs the same JS fix? (The `header_catalog.html` has a mobile categories panel but city selection is in the header dropdown for all viewport sizes.)

---

## 11. Out of Scope

- **Full filter architecture refactor** (e.g., adopting `django-filter` or consolidating the 18 inline URL constructions in `ad_list.html`): The spec (spec 02 §10, filter-ui.md) explicitly states "No structural change" to the filter architecture. This regression fix addresses the specific bugs, not the underlying URL duplication.
- **Search history or autocomplete changes**: Not affected by any of the 5 problems.
- **Price enforcement (Plan 18 core)**: Already implemented; price=0, "Free" label, bot Free button, non-null field — all completed in commits `ce93157` through `4fab99e`.
- **Search-clear button in header (Plan 17)**: Already implemented; the `data-search-clear` button in `header_catalog.html` L145–148 is correct and not part of this regression.
- **Backend search/sort logic**: PostgreSQL FTS, relevance ranking, price sorting — all working correctly.
- **Category and city name i18n (spec 09)**: Separate bug, already resolved.

---

## 12. Definition of Ready

This specification is ready for implementation planning when:

1. ✅ PO decisions Q1–Q3 are **confirmed** by the Product Owner (Q1=C+price-as-chip, Q2=A, Q3=A)
2. ✅ All 5 problems are traced to specific code locations with file:line citations.
3. ✅ Root causes are verified against the actual codebase (not assumptions).
4. ✅ Test gaps are identified (which tests encode wrong behavior, which tests are missing).
5. ✅ Fix approaches are identified with recommended options and rationale.
6. ✅ Dependencies between tasks are mapped (T1→T2, T3→T7, etc.).
7. ✅ Constraints (no new framework, i18n, StrEnum, djlint) are documented.
8. ✅ Risks and mitigation strategies are documented.
9. ✅ Out-of-scope items are explicitly listed to prevent scope creep.
10. ✅ Conceptual tasks have clear purpose, expected outcome, and dependencies.

---

## 13. Problem-to-Task Mapping

| Problem # | Tasks that address it | Root cause |
|---|---|---|
| 1 (clear-all always visible) | T1, T2, T7, T8 | Clear-all link unguarded; price not in chips-block condition |
| 2 (price range plain text) | T3, T7, T8 | Price summary is `<div>`, not a `<span>` chip with removal link |
| 4 (city resets category) | T5, T7 | Header JS navigates to `/city/<slug>/` instead of preserving path |
| 5 (language switch inconsistency) | T6, T7 | Language switcher outside HTMX swap target; links go stale |
| (interconnected) | T1, T4 | T1: Add price to chips visibility condition; T4: Search-page clear-all `q` preservation (CR-4) |
