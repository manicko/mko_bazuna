# Verification Report: Catalog Filter/Sort UI

**Date:** 2026-08-23
**Scope:** Verification of the three PO-reported problems in the catalog filter/sort UI, and of the proposed remediation direction.
**Method:** Read-only source inspection of the **current working tree** (uncommitted changes on top of `git` HEAD). All conclusions are grounded in exact file paths and line numbers from the working tree.
**Stack:** Django 5.2 LTS · HTMX 1.9.12 · PostgreSQL 18 · Tailwind CSS v4 (standalone CLI) · vanilla JS only.

---

## 0. Baseline correction (precision note)

The task brief states the baseline commit is `ef26fc8`. Verified via `git log`:

```
dbdd974 fix(docker): resolve seed photos missing after Docker recreation   <- HEAD
6607ad9 doc test optmization
bbe35fc test(optimization): accelerate seed suite, fix marker hygiene, restore CI parity
2ff668c fix(ci): restore green lint/typecheck for static-defect audit O-03
ef26fc8 feat(catalog): add listing_purpose and features filters with sort improvements
```

`ef26fc8` **is an ancestor** of HEAD (`git merge-base --is-ancestor ef26fc8 HEAD` → true). HEAD has advanced 4 commits past `ef26fc8` to `dbdd974`. All `git diff HEAD` output below is therefore working-tree-vs-`dbdd974`. **This hash discrepancy has no effect on the analysis** — the working-tree state (sort extracted to `filter_sort.html`, features wrapped in `<details>`, `TestFilterUrlReset` added) is identical regardless of whether the baseline is `ef26fc8` or `dbdd974`, because neither intervening commit touched these templates.

---

## 1. Area 1 — Root-cause analysis: "Sorting resets filters"

### 1.1 Current working-tree structure (the bug)

The HTMX swap boundary is the decisive fact.

**`src/backend/templates/ads/list.html` (working tree, line 34–37):**

```
34:        {% include "ads/partials/filter_sort.html" %}
35:        <div id="ad-list">
36:            {% include "ads/partials/ad_list.html" %}
37:        </div>
```

Evidence:
- `filter_sort.html` is included on **line 34**, which is **BEFORE** `<div id="ad-list">` (line 35). It is therefore **OUTSIDE** the `#ad-list` swap target. (CONFIRMED — matches brief.)
- `ad_list.html` is included **inside** `#ad-list` (lines 36).

**`src/backend/templates/ads/partials/ad_list.html` (working tree, lines 7–15):**

```
7:  {% comment %} The filter form lives inside the HTMX-swappable region so that every
...
14: {% include "ads/partials/filter_form.html" %}
```

Evidence: `filter_form.html` is included at `ad_list.html:14`, **INSIDE** the `#ad-list` fragment (the partial that `listings()` returns for HTMX requests). (CONFIRMED — matches brief.)

**`src/backend/templates/ads/partials/filter_sort.html` (working tree, lines 14–44):**

```
14: <form method="get"
15:       hx-get="{{ request.path }}"
16:       hx-target="#ad-list"
17:       hx-push-url="true"
18:       hx-swap="innerHTML"
19:       class="mb-4">
...
24: {% if query %}<input type="hidden" name="q" value="{{ query }}">{% endif %}
25: {% if current_category %}<input type="hidden" name="category" value="{{ current_category }}">{% endif %}
26: {% if current_city %}<input type="hidden" name="city" value="{{ current_city }}">{% endif %}
27: {% if min_price %}<input type="hidden" name="min_price" value="{{ min_price }}">{% endif %}
28: {% if max_price %}<input type="hidden" name="max_price" value="{{ max_price }}">{% endif %}
29: {% if current_listing_purpose %}<input type="hidden" name="listing_purpose" value="{{ current_listing_purpose }}">{% endif %}
30: {% for fslug in current_features %}<input type="hidden" name="features" value="{{ fslug }}">{% endfor %}
31: <input type="hidden" name="page" value="1">
...
36: <select name="sort" id="sort"
...
38:            onchange="this.form.requestSubmit()">
```

Evidence: `filter_sort.html` is a **standalone form** that captures *all* filter state as **hidden `<input type="hidden">` elements** (q / category / city / min_price / max_price / listing_purpose / features), populated from view context at render time, and auto-submits via `onchange="this.form.requestSubmit()"` (line 38). (CONFIRMED — matches brief.)

### 1.2 The HTMX swap boundary is the root cause

The decisive evidence is in the view layer. On **every HTMX navigation** the server returns **only** the `#ad-list` fragment — never `list.html`:

**`src/backend/apps/ads/views/listings.py` (working tree, lines 510–512):**
```
510:    if request.headers.get("HX-Request"):
511:
512:        return render(request, "ads/partials/ad_list.html", context)
```

**`src/backend/apps/search/views/search.py` (working tree, lines 232–233):**
```
232:    if request.headers.get("HX-Request"):
233:        return render(request, "ads/partials/ad_list.html", context)
```

Both views render `ad_list.html` for HTMX requests. `ad_list.html` includes `filter_form.html` (line 14) but **does not** include `filter_sort.html`. The `filter_sort.html` fragment is included only in `list.html` (line 34) — the **full page** template returned on the initial non-HTMX load.

### 1.3 Step-by-step failure sequence

1. **Initial full page load** (`/`). `list.html` renders both `filter_sort.html` (outside `#ad-list`) and `ad_list.html`→`filter_form.html` (inside `#ad-list`). Both carry the current filter state.

2. **Buyer changes a feature checkbox** and clicks "Apply filters". The filter form (`filter_form.html`, *inside* `#ad-list`) submits via HTMX. The browser URL is updated (`hx-push-url="true"` on the form, `filter_form.html:9`) to include the new `features=…`. The server returns `ad_list.html` → `#ad-list` is swapped. The **filter form is re-rendered fresh** (line/visible fields reflect the new state). ✓

3. **But `filter_sort.html` is outside `#ad-list`**, so it is **NOT re-rendered** by this swap. Its hidden inputs are frozen at the values from the **last full page load** — i.e. the *pre-change* feature set.

4. **Buyer changes the sort.** `filter_sort.html`'s `<select onchange="this.form.requestSubmit()">` (line 38) submits the form. HTMX serializes **only this form's own data** (the stale hidden inputs from step 3 + the new `sort`). The freshly-changed `features` value (now in the URL) is **not** in the sort form's DOM, so it is **not** submitted.

5. **Server receives stale filter values + new sort.** The resulting URL drops the buyer's feature change. The sort is applied, but the filter state silently reverts. **→ Filter state is reset.** CONFIRMED.

### 1.4 Why `filter_form.html` does NOT have this problem

`filter_form.html` (working tree) carries filter state **two ways**, both of which are always-fresh because the form lives inside `#ad-list`:
- **Visible, live form fields** — `listing_purpose` `<select>` (lines 21–28), `min_price`/`max_price` number inputs (lines 32–43), `features` checkboxes (lines 55–61). These always reflect what the server rendered from the current URL.
- **Hidden inputs** for `q`/`category`/`city` (lines 11–13) — these are re-rendered on every HTMX swap (the form is inside the swap target), so they are never stale.

`filter_sort.html` introduced a **second, duplicate, stale copy** of all this state that could never be refreshed inside `#ad-list`.

### 1.5 Fix direction — CONFIRMED

**Moving the sort `<select>` INTO `filter_form.html` (inside `#ad-list`) eliminates the bug.** Verification:

- The sort `<select>` becomes a **form field** of `filter_form.html`. Because the entire form is re-rendered server-side on *every* HTMX submission (view context at `listings.py:486–498` supplies `current_sort`, `current_features`, `current_listing_purpose`, `min_price`, `max_price`, `query`, `current_category`, `current_city` — all derived from `request.GET`), the sort `selected` option is always correct for the current URL. No hidden-input duplication is needed.
- If the sort `<select>` carries `onchange="this.form.requestSubmit()"` (mirroring `filter_sort.html:38`), changing sort submits the **whole filter form** — sending all *current* field values plus the new sort. Filters do not change; only sort changes. This satisfies Decision_06.md requirement #3 ("two independent systems"). ✓
- The `#ad-list` swap count of `hx-get=` / `hx-push-url="true"` in `ad_list.html` is **untouched** (see §2.4 / Table 1) because the sort select is placed in `filter_form.html`, a *separate file referenced by `{% include %}`*, not an inline `hx-get` link in `ad_list.html`.

**Confidence: HIGH.** The root cause is a direct, provable consequence of the HTMX swap boundary (`listings.py:510-512` returns only `ad_list.html`, which includes `filter_form.html` but not `filter_sort.html`, while `list.html:34` includes `filter_sort.html` outside `#ad-list`).

---

## 2. Area 2 — Exhaustive test-contract impact analysis

### 2.1 Scope of the search

Searched the **entire** codebase (`src/`, `.kilo/`, `.github/`):
- `filter_sort.html` references in `*.py` → **0** (confirmed via repo-wide greps).
- `filter_sort.html` references in `*.html` → **1** (`list.html:34`).
- `<details>` / `<summary>` references in templates → **2** (`filter_form.html:47-48`, both inside the Features block).
- `name="sort"`, `onchange`, `requestSubmit` in any test → **0**.
- `filter_form.html` references in tests → **1** (`test_catalog_filters.py:309`, static source assertion).
- `sort` keyword in tests → only URL-param view-behavior tests (`test_listings_sort.py`, `test_listings_context.py`, `test_search_triggers.py`) and sort-related docstrings; **none** assert on sort *markup* or *position*.

Test files examined (all read in full):
| File | Relevant to proposed changes? |
|---|---|
| `apps/ads/tests/test_catalog_filters.py` | YES — `TestFilterUrlReset` (7 tests) + sort/param view tests |
| `apps/ads/tests/test_listings_sort.py` | sort ORDER via URL (no markup assertions) |
| `apps/ads/tests/test_listings_context.py` | context-dict keys (mocked render, no markup) |
| `apps/ads/tests/test_favorites.py` | shares `ad_list.html` but `show_filters` unset → form not rendered; asserts only heart/empty-state |
| `apps/ads/tests/test_gallery_markup.py` | ad-detail gallery; unrelated |
| `apps/ads/tests/test_script_gating.py` | ad-detail consent gating; unrelated |
| `apps/search/tests/test_search_view.py` | search view `page_obj`/status; no markup assertions |
| `apps/search/tests/test_autocomplete_template.py` | `header_catalog.html` only; unrelated |
| `apps/core/tests/test_templates.py` | consent-banner guard in `list.html` only |
| `apps/core/tests/test_create_admin_user.py` | unrelated ("shows details" word match) |
| `apps/moderation/tests/test_moderation_views.py` | unrelated ("details" word match) |
| `conftest.py` (backend) | fixtures only; no template assertions |
| `src/telegram_bot/tests/conftest.py` | bot tests; does not render catalog templates |

### 2.2 Proposed change set (what is being evaluated)

The three proposed changes (per the brief):
- **(a)** Move the sort `<select>` from `filter_sort.html` **into** `filter_form.html` (inside `#ad-list`), positioned to the right of the "Apply filters" button, auto-submitting the form on change.
- **(b)** Delete the `filter_sort.html` file; remove its `{% include %}` from `list.html:34`.
- **(c)** Replace the Features `<details>`/`<summary>` block (`filter_form.html:47-64`) with a floating dropdown (Approach A: `data-filter-dropdown` / `data-filter-toggle` / `data-filter-panel` + event-delegated vanilla JS).

**Implementation assumption:** sort is implemented as a *form field* with `onchange="this.form.requestSubmit()"` inside `filter_form.html` — i.e. it uses the form's existing `hx-get="{{ request.path }}"` and does **not** gain its own standalone `hx-get` attribute. This matches the PO's Decision_06.md ("in the same block as filters, to the right of Apply") and the fix verification in §1.5.

### 2.3 Affected-test analysis — PROPOSED approach (sort as form field)

**Table 1 — Full pass/fail + update matrix (proposed approach).**

| # | Test (file:line) | Exact assertion | After proposed change | Update required? |
|---|---|---|---|---|
| 1 | `TestFilterUrlReset::test_form_uses_request_path_not_empty` (`test_catalog_filters.py:307-312`) | `'hx-get="{{ request.path }}'` in `filter_form.html` source **and** `'hx-get=""'` not in source | **PASS** — the form tag (line 6) is untouched; sort `<select>` is an `onchange` field, adds no `hx-get` | None |
| 2 | `TestFilterUrlReset::test_all_htmx_links_have_push_url` (`test_catalog_filters.py:314-319`) | `ad_list.html` source has **exactly 8** `hx-get=` and **exactly 8** `hx-push-url="true"` | **PASS** — sort moves into `filter_form.html` (a separate file referenced by `{% include %}`); `ad_list.html` **source** is unchanged, so the count stays 8/8. See §2.5 caveat. | None |
| 3 | `TestFilterUrlReset::test_clear_all_filters_has_push_url` (`test_catalog_filters.py:321-326`) | `'hx-push-url="true"'` **and** `'hx-get="?page=1'` in `ad_list.html` | **PASS** — `ad_list.html` links untouched | None |
| 4 | `TestFilterUrlReset::test_form_renders_path_only_hx_get` (`test_catalog_filters.py:332-345`) | HTMX `GET /?features=delivery` renders `'hx-get="/"'` and does **not** render `'hx-get="/?features=delivery'` | **PASS** — form `hx-get` stays path-only (`/`). Sort `<select onchange>` adds no `hx-get`; no path-with-query `hx-get` is introduced | None |
| 5 | `TestFilterUrlReset::test_chip_link_has_push_url_in_rendered_output` (`test_catalog_filters.py:347-362`) | rendered HTMX output contains `'hx-push-url="true"'` | **PASS** — chip links (`ad_list.html:42,53`) unchanged | None |
| 6 | `TestFilterUrlReset::test_pagination_links_have_push_url_in_rendered_output` (`test_catalog_filters.py:364-377`) | rendered output contains `'hx-push-url="true"'` **and** `"Page navigation"` | **PASS** — pagination (`ad_list.html:128-159`) unchanged | None |
| 7 | `TestFilterUrlReset::test_form_submission_does_not_accumulate_params` (`test_catalog_filters.py:383-410`) | `GET /?features=delivery` returns only the delivery ad (AND semantics) | **PASS** — view filter logic (`listings.py:395-399`) unchanged; checkboxes still serialize `features=<slug>`; dropdown conversion preserves checkbox semantics | None |
| 8 | `TestListingPurposeFilter` (2 tests, `test_catalog_filters.py:74-128`) | `?listing_purpose=sell` narrows results | **PASS** — view logic (`listings.py:384-388`) unchanged | None |
| 9 | `TestFeaturesFilter` (2 tests, `test_catalog_filters.py:153-177`) | `?features=new&features=delivery` AND semantics | **PASS** — view logic unchanged; checkboxes still emit `features=` params regardless of dropdown chrome | None |
| 10 | `TestFilterAndSearchCombine::test_q_purpose_and_feature_combine` (`test_catalog_filters.py:183-213`) | `q+purpose+feature` combined AND | **PASS** — view + param parsing unchanged | None |
| 11 | `TestPriceNullSort` (2 tests, `test_catalog_filters.py:219-257`) | `price_asc`/`price_desc` nulls-last ordering | **PASS** — sort view logic (`listings.py:430-436`) unchanged | None |
| 12 | `TestRelevanceTiebreaker::test_rank_tie_breaks_by_published_at` (`test_catalog_filters.py:263-290`) | FTS `-rank,-published_at,-id` ordering | **PASS** — search view FTS branch unchanged | None |
| 13 | `TestListingsSortOrder` (4 tests, `test_listings_sort.py:53-109`) | `?sort=date_asc/date_desc` ordering in rendered HTML (ad-title positions) | **PASS** — sort value parsing (`listings.py:424-440`) unchanged; sort-select relocation does not alter ad-card positions | None |
| 14 | `TestListingsFilterContext` (6 tests, `test_listings_context.py:120-229`) | context keys/values incl. `current_sort` (mocked `render`, no markup) | **PASS** — context dict (`listings.py:472-504`) unchanged; `current_sort` still supplied | None |
| 15 | `TestSearchViewSorting` (3 tests, `test_search_triggers.py:190-253`) | `/search/?sort=` ordering (no-query branch) | **PASS** — search view sort branch (`search.py:185-192`) unchanged | None |
| 16 | `TestSearchViewPublishesFilter` / `Pagination` / `DescendantCategories` (`test_search_view.py`) | search status/pagination/category-expansion | **PASS** — no assertions on filter/sort markup; search renders `ad_list.html` too but no template-structure checks | None |
| 17 | `TestConsentBannerGuardInTemplates` (`test_templates.py:46-78`) | `ads/list.html` keeps consent-banner guard on the line before/after the include | **PASS** — removing `{% include filter_sort.html %}` (line 34) does not touch the guard at `list.html:40-42` | None |
| 18 | `TestAutocompleteTemplate` + `TestCatalogMenuAccordionTemplate` (`test_autocomplete_template.py`) | `header_catalog.html` autocomplete/accordion JS | **PASS** — `header_catalog.html` is not modified by the proposed changes | None |
| 19 | `TestFavoritesList` (`test_favorites.py:160-188`) | `/cabinet/favorites/` renders favorited ad titles / empty state | **PASS** — favorites view (`favorites.py:25-48`) does **not** set `show_filters`, so `ad_list.html:13` renders the form block as `False` → `filter_form.html` is never included in the favorites fragment | None |

**Result: 19/19 test groups PASS with NO updates required** under the proposed approach.

### 2.4 The critical distinction: sort as a *form field* vs. as a *separate `hx-get` element*

This is the most consequential finding. The existing research report (`01_olx-checkbox-dropdown-research.md`, §5 & §6) considered **moving the sort `<select>` OUT of `filter_form.html` into `ad_list.html` as a standalone HTMX element** with `hx-get` + `hx-trigger="change"`. That alternative approach has a **different** test impact:

- Placing a sort `<select>` with `hx-get="{{ request.path }}" hx-push-url="true" hx-target="#ad-list"` **inline in `ad_list.html`** would add **1** `hx-get=` and **1** `hx-push-url="true"` to `ad_list.html`'s source, changing `test_all_htmx_links_have_push_url` from **8 → 9** (both counts). That test would then **FAIL** and require updating both `8` → `9` (report §6 line 507).

The **proposed approach (sort as a form field inside `filter_form.html`)** does **not** add any `hx-get`/`hx-push-url` to `ad_list.html` source (the sort lives in the *included* `filter_form.html`, whose `hx-get` is the form's own). Therefore `ad_list.html`'s source count is unchanged and `test_all_htmx_links_have_push_url` is unaffected.

| Approach | Where sort lives | `ad_list.html` source count | `test_all_htmx_links_have_push_url` |
|---|---|---|---|
| Research-report §5/§6 (separate `hx-get` element in `ad_list.html`) | inline `ad_list.html`, standalone | 9 / 9 | **FAILS 8→9** — requires test edit |
| **Proposed (form field in `filter_form.html`)** | inside `filter_form.html` (via `{% include %}`), `onchange` submits form | **8 / 8** | **PASSES** — no test change |

**Confidence: HIGH** that the proposed approach keeps the count at 8/8 (verified by counting the 8 `hx-get=`/`hx-push-url="true"` pairs in `ad_list.html` working-tree source at lines 42, 53, 60, 131, 135, 145, 153, 157).

### 2.5 Gap: no regression test for the sort-reset bug

A codebase-wide search confirms **no existing test** covers the "sort preserves filters" invariant:

- No test submits the **sort** form and then asserts the **filter** values remain.
- `test_form_submission_does_not_accumulate_params` (`test_catalog_filters.py:383-410`) tests *filter* → *filter* accumulation only (not sort → filter).
- `test_listings_sort.py` tests sort **ordering** but never asserts filter-state preservation across a sort change.

**Recommendation:** add a regression test (HTMX-scoped) that:
1. `GET /?features=delivery` with `HX-Request: true`;
2. captures the rendered form's *current* `features`/sort state;
3. changes `sort` and re-requests;
4. asserts the filter field values are preserved in the re-rendered `#ad-list` fragment.

Such a test would have **caught the current `filter_sort.html` bug** and would validate the fix.

---

## 3. Area 3 — Features floating-dropdown approach: recommendation

### 3.1 `header_catalog.html` canonical pattern — VERIFIED

`src/backend/templates/components/header_catalog.html` is the established dropdown pattern (read in full, 546 lines). Confirmed structure:

- **Trigger button** (`header_catalog.html:76-84`): `<button type="button" data-categories-toggle aria-haspopup="listbox" aria-expanded="false" ...>` (also `data-preferred-city-toggle` at :43, `data-header-auth-toggle` at :499-501).
- **Floating panel** (`header_catalog.html:85`): `<div data-categories-panel class="absolute left-0 z-[90] mt-1 w-72 bg-white border border-gray-200 rounded-lg shadow-lg hidden">`.
- **Vanilla JS** (`header_catalog.html:180-545`) inside an IIFE:
  - `classList.add('hidden')` / `classList.remove('hidden')` for visibility (`closeCategories` line 400, etc.).
  - `setAttribute('aria-expanded', 'true'/'false')` toggling (lines 327, 413, 468, 514).
  - `aria-controls` links toggle button → panel id (e.g. line 97 → 106).
  - `e.stopPropagation()` on the toggle (line 409).
  - `document.addEventListener('click', …)` for **outside-click-to-close** (lines 415, 470, 516).
  - `document.addEventListener('keydown', …)` with `e.key === 'Escape'` (lines 419, 474, 519).
  - Caret SVG rotates via `rotate-180`: `svg.classList.add('rotate-180')` (line 329) / `classList.remove('rotate-180')` (line 392, 445).
  - **`htmx:afterSwap` re-attachment**: `window.addEventListener('htmx:afterSwap', …)` (lines 541-544) re-runs `attachCategoryHandlers(e.target)`.
- **Touch targets**: `min-h-[44px]` / `min-w-[44px]` on all toggles (lines 44, 58, 65, 77, 98, 120, 159, 165, 232).

The `filter_form.html` dropdown must replicate this **exactly** (project rule #7: "Follow existing patterns").

### 3.2 Tailwind CSS pipeline — VERIFIED

- **Input:** `src/theme/static/theme/css/input.css` (working tree, 3 lines):
  ```
  /* Tailwind input stylesheet */
  @import "tailwindcss";
  @source "src/backend/templates/**/*.html";
  ```
  The `@source` glob **already covers all template dirs**, so any new utility class added to a scanned template is picked up on the next build.
- **Output:** `src/theme/static/theme/css/output.css` exists (34 KB, last written 2026-08-23). It is referenced by `list.html:12` (`<link rel="stylesheet" href="{% static 'theme/css/output.css' %}">`).
- **Class availability** (verified present via literal substring search of `output.css`):

  | Class | Present in `output.css`? | Used in `header_catalog.html`? |
  |---|---|---|
  | `rotate-180` | ✅ Yes (CONFIRMED — resolves report §1.5's open question) | ✅ lines 329, 392, 445 |
  | `z-10` / `z-[10]` | ✅ Yes | — (report §3 spec used `z-10`) |
  | `z-[90]` | ✅ Yes | ✅ lines 54, 85, 144, 178 |
  | `shadow-lg` | ✅ Yes | ✅ lines 54, 85, 128, 144 |
  | `absolute` | ✅ Yes | ✅ lines 42, 53, 75, 85, 116, 128, 143 |
  | `hidden` | ✅ Yes (trivial) | ✅ everywhere |
  | `focus:ring-2` / `focus:ring-blue-500` | ✅ Yes | ✅ lines 120, 232 |
  | `min-h-[44px]` | ✅ Yes (`44px` + `min-h-` confirmed; earlier regex miss was a CSS-escaping artifact) | ✅ 9 sites |
  | `min-w-[44px]` | ✅ Yes | ✅ lines 98, 165, 232 |
  | `transition-transform` | ✅ Yes | ✅ lines 100, 167, 328, 389, 421 |

  **Conclusion: every utility class required by Approach A is already generated in `output.css`.** Because the classes already exist in templates scanned by `@source`, **no Tailwind regeneration is strictly required** for the *chrome* classes. *(Caveat: only if the dropdown markup reuses exactly the classes above. Any brand-new arbitrary value — e.g. a pixel value not already used — would still need a Docker rebuild, per the report §1.5.)*
- The earlier "No files found" result for `min-h-\[44px\]` was a **regex-escaping false negative**: CSS escapes the brackets as `min-h-\[44px\]` (backslash + bracket), so the regex `min-h-\[44px\]` (which looks for `min-h-[44px]` *without* backslash) could not match. A literal search for `44px` and `min-h-` confirms presence.

### 3.3 No Alpine.js — VERIFIED

Repo-wide grep for `alpine|x-data|x-on:|x-bind|x-show|@click|@change` across all `*.html` templates → **No matches** (the only apparent hits in the broad `x-` scan were false positives from Tailwind `px-` classes). The project is **vanilla-JS + HTMX-only** (HTMX 1.9.12 has no `hx-on`). Approach A (native `data-*` + vanilla JS) is the only sanctioned interop style.

### 3.4 Approach A confirmed as the recommended direction

Against the three candidate approaches from `01_olx-checkbox-dropdown-research.md`:

| Criterion | Approach A (collapsible checkbox panels + global "Apply") | Approach B (per-section auto-submit) | Approach C (`<details>`/`<summary>`) |
|---|---|---|---|
| Eliminates "stretches everything" (PO complaint #2) | ✅ `absolute` floating panel | ✅ floating panel | ❌ **inline expansion** — the exact bug PO complained about |
| Follows codebase convention (rule #7) | ✅ matches `header_catalog.html` `data-*`+`aria-expanded`+vanilla JS | ⚠️ introduces `htmx.trigger` API surface | ❌ third pattern; no existing `<details>` in codebase |
| Survives HTMX re-render of `#ad-list` | ✅ event delegation on `document` (matches `header_catalog.html` outside-click handler) | ⚠️ race: rapid toggles lose pending toggle during form re-render | ⚠️ panel state lost on re-render |
| Test impact | ✅ zero (dropdowns live in `filter_form.html`, not `ad_list.html`) | ⚠️ would need 8→9 if sort separated | ✅ no test references `<details>` |
| PO Decision_06 #2 ("dropdown like listing_purpose, but checkboxes") | ✅ floating dropdown + checkboxes | — | ❌ accordion, not "dropdown" |
| PO #3 ("sort must not reset filters") | ✅ sort stays a form field inside `#ad-list` | — | — |

**Recommendation: Approach A.** It is the only option that (a) fixes the "stretches everything" complaint by using `absolute`-positioned floating panels — directly addressing the PO's `<details>` objection, (b) follows the exact `header_catalog.html` convention (project rule #7), (c) needs zero test updates, and (d) is compatible with the sort-into-`filter_form.html` fix (§1.5) because the dropdown checkboxes remain *form fields* that submit via the single "Apply filters" button — no auto-submit race condition.

**Implementation note (from report §4, lines 395-405):** because `filter_form.html` is inside `#ad-list` (destroyed + recreated on every swap), the dropdown JS **must not** live inline in `filter_form.html`. Use **document-level event delegation** (`e.target.closest('[data-filter-toggle]')`) so a single listener set on `document` handles all current and future instances — no `htmx:afterSwap` re-attachment needed. This mirrors `header_catalog.html`'s own outside-click handler (`document.addEventListener('click', …)`, line 415).

**Confidence: HIGH.**

---

## 4. Tailwind class availability summary

Already present in `output.css` (no regeneration needed for Approach A chrome):
`rotate-180`, `absolute`, `z-10`/`z-[10]`/`z-[90]`, `shadow-lg`, `hidden`, `focus:ring-2`, `focus:ring-blue-500`, `min-h-[44px]`, `min-w-[44px]`, `transition-transform`, `border`, `border-gray-200`, `bg-white`, `rounded-lg`, `z-10`, `mt-1`, `w-full`/`w-72`, `py-2.5`, `px-4`, `text-sm`, `text-gray-700`, `hover:bg-gray-50`.

**Only needs a one-time clarification:** the count-badge text color (`text-gray-500`) and `text-xs` already exist in `ad_list.html` (`current_features|length` badge at `filter_form.html:51`). No novel arbitrary values are required if the dropdown mirrors `header_catalog.html`'s exact class set.

**Verification method caveat:** `output.css` is a single ~34 KB minified line (line 2). Class *presence* was verified by literal substring match. Per the design-system pipeline (`input.css` `@source "src/backend/templates/**/*.html"`), adding any *new* arbitrary value to a scanned template requires a rebuild (`docker compose exec web tailwindcss -i …/input.css -o …/output.css --minify`) — but Approach A reuses only already-scanned classes, so this is not triggered.

---

## 5. Blockers & risks

1. **Conflicting sort-separation guidance (MEDIUM risk).** `01_olx-checkbox-dropdown-research.md` §5–§6 recommends **deferring** sort separation and moving the sort selector *out* of `filter_form.html` into `ad_list.html` as a standalone `hx-get` element (which would trip `test_all_htmx_links_have_push_url` 8→9). **Decision_06.md** (lines 1, 3) requires sort *inside* the filter block, to the right of "Apply filters", applied on change without resetting filters. The **proposed approach here (sort as a form field in `filter_form.html` with `onchange` auto-submit) aligns with Decision_06** and **avoids** the 8→9 test break — but an implementer following the research report's §5 literally would reintroduce a count-breaking change. **Action:** decide whether sort auto-submits the whole form (`onchange`, recommended, 8/8 holds) or becomes a standalone `hx-get` link (9/9, needs test edit). Only the former is test-safe.

2. **No regression test for sort/filter independence (HIGH value, low risk).** Identified in §2.5. The current working tree introduced `filter_sort.html` with `onchange="this.form.requestSubmit()"` but added **no** behavioral test asserting that a sort change preserves `features`/`listing_purpose`/price. This is precisely the defect that slipped through. **Action:** add the HTMX regression test described in §2.5 before/while implementing the fix.

3. **`filter_sort.html` is unreferenced by tests (LOW risk, good news).** Removing `filter_sort.html` and its include (`list.html:34`) touches no test contract — no path/href/lex test asserts its existence. Safe to delete.

4. **`filter_form.html` shared by `listings()` and `search()` (MEDIUM caution).** Both views render `ad_list.html`→`filter_form.html` for HTMX (`listings.py:512`, `search.py:233`). On the search page `query` is truthy, so a sort `<select {% if not query %}>` guard keeps it hidden there (matching current `filter_sort.html:13` behavior). **The moved sort must keep the `{% if not query %}` guard** or it will wrongly appear on `/search/?q=`. No current test asserts this, so it won't fail tests — but it is a behavioral regression risk.

5. **Stale `output.css` timestamp vs. template churn (LOW).** `output.css` last wrote 2026-08-23 00:20, same day as the working-tree template edits. Because Approach A reuses only classes already emitted by scanned templates, the committed `output.css` is sufficient. If the implementer adds *any* class value not already used project-wide (e.g. `z-[50]` instead of `z-10`), a Tailwind rebuild is required or the dropdown panel will not be positioned — and there is no CI step flagged in `.github/workflows/ci.yml` that rebuilds/regenerates `output.css` from source (verified: CI only runs lint/typecheck/test per `.kilo/commands/plan/plan-spec.md` conventions). **Action:** reuse `header_catalog.html`'s exact class set; if new values are needed, rebuild `output.css` via Docker before merge.

6. **Working-tree churn already modified `TestFilterUrlReset` (LOW — informational).** The `TestFilterUrlReset` class (`test_catalog_filters.py:293-410`) is **untracked-vs-HEAD**: it did **not** exist at HEAD (`dbdd974`); it was added in the working tree alongside the `filter_form.html`/`ad_list.html` template work (confirmed via `git diff HEAD -- test_catalog_filters.py`: the entire `TestFilterUrlReset` class is an addition). These tests currently **PASS** on the working tree and remain green under the proposed changes (§2.3). No action needed, but note these tests are themselves part of the uncommitted change set and have not yet been committed/validated through CI.

---

## 6. Evidence appendix — working-tree file/line map

| Artifact | Path | Key lines |
|---|---|---|
| Sort form (outside `#ad-list`) | `src/backend/templates/ads/list.html` | 34 (include `filter_sort.html`); 35-37 (`#ad-list` boundary) |
| Filter form (inside `#ad-list`) | `src/backend/templates/ads/partials/ad_list.html` | 7-15 (comment + `{% include filter_form.html %}` under `show_filters`) |
| Sort fragment (stale hidden inputs) | `src/backend/templates/ads/partials/filter_sort.html` | 13 (`{% if not query %}`); 14-19 (form hx attrs); 24-31 (hidden inputs); 36-43 (`<select name="sort" onchange>`) |
| Filter fragment (live form fields) | `src/backend/templates/ads/partials/filter_form.html` | 5-10 (form hx attrs); 11-13 (hidden q/category/city); 21-28 (`listing_purpose` select); 32-43 (price inputs); 45-65 (Features `<details>`); 67-73 (Apply button) |
| HTMX partial branch (renders `ad_list.html` only) | `src/backend/apps/ads/views/listings.py` | 510-512; context `current_sort`/`current_features` at 486-498; sort parsing 424-440; feature parse 395-399 |
| Search view HTMX partial branch | `src/backend/apps/search/views/search.py` | 232-233; `show_filters=True` at 228 |
| Sort enum | `src/backend/apps/core/enums.py` | 11-17 (`AdSort`: DATE_NEW/DATE_OLD/PRICE_LOW/PRICE_HIGH) |
| Test contracts | `src/backend/apps/ads/tests/test_catalog_filters.py` | 307 (`hx-get` assertion); 314 (`8/8` count); 321 (clear-all); 332 (path-only render); 347 (chip push-url); 364 (pagination); 383 (no-accumulation) |
| Sort-order behavioral tests | `src/backend/apps/ads/tests/test_listings_sort.py` | 56-109 (URL-param ordering only) |
| Canonical dropdown pattern | `src/backend/templates/components/header_catalog.html` | 76-84 (toggle); 85 (floating panel); 415 (document click); 419 (Escape); 541-544 (`htmx:afterSwap`); 329/392 (`rotate-180`) |
| Tailwind entry (scans templates) | `src/theme/static/theme/css/input.css` | 3 (`@source "src/backend/templates/**/*.html"`) |
| Tailwind output (built artifact) | `src/theme/static/theme/css/output.css` | 2 (minified; all classes present) |
| PO decision | `.ai/problems/Decision_06.md` | 1 (sort in filter block, right of Apply); 2 (Features → floating dropdown w/ checkboxes); 3 (sort must not reset filters) |
| Prior research (conflicting sort-separation rec.) | `.ai/reports/01_olx-checkbox-dropdown-research.md` | §5 (move sort to `ad_list.html`, separate `hx-get`); §6 (deferred); §7 (Approach A) |
| `src/templates/` (separate dir) | `src/templates/` | **Empty** (`[]` — not a symlink; an empty directory) |
| Alpine.js usage | all `*.html` templates | **Absent** (grep for `alpine|x-data|@click|@change|x-bind|x-show` → 0 matches) |

---

## 7. Verdict

1. **Root cause (Area 1): CONFIRMED.** The sort selector was extracted into `filter_sort.html`, included in `list.html` **outside** `#ad-list` (line 34), and wired with stale hidden inputs (lines 24-31). Because HTMX requests return only `ad_list.html` (which includes `filter_form.html` but **not** `filter_sort.html` — `listings.py:510-512`), the sort form's hidden inputs are never refreshed after a filter change. Changing sort then submits the stale inputs, dropping the buyer's filters. The fix direction (move sort **into** `filter_form.html`, inside `#ad-list`) is **verified correct**: the sort becomes a live form field re-rendered server-side with every submission, carrying current state natively — no stale hidden inputs, and `ad_list.html`'s `hx-get`/`hx-push-url` count stays at 8/8.

2. **Test contracts (Area 2):** All 19 test groups examined **PASS** under the proposed approach with **zero test updates required**. The only test that *would* break is `test_all_htmx_links_have_push_url` (8→9) — but **only** if an implementer follows the research report's §5 alternative (sort as a standalone `hx-get` element in `ad_list.html`), **not** the proposed form-field approach. **Action:** implement sort as an `onchange` form field in `filter_form.html`, and add the missing sort-persistence regression test (§2.5).

3. **Floating dropdown (Area 3):** **Approach A** (`data-filter-dropdown` / `data-filter-toggle` / `data-filter-panel` + event-delegated vanilla JS, mirroring `header_catalog.html`) is **confirmed recommended**. It is the only approach that fixes the PO's "stretches everything" `<details>` complaint (via `absolute` floating panels), follows the established codebase convention (rule #7), needs no test changes, and is compatible with the sort-into-form fix. All required Tailwind classes already exist in `output.css` (no rebuild needed). **Do not** use Approach C (`<details>`): it is the inline-expansion pattern the PO explicitly rejected, and it introduces a third dropdown pattern.
