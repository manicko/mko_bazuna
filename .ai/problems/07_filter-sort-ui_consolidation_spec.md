# Problem 07 — Filter/Sort UI Consolidation

## Metadata

| Field | Value |
|---|---|
| **ID** | `07` |
| **Title** | Catalog filter/sort UI consolidation — sort relocation, features dropdown, state independence |
| **Source** | `Decision_06.md` (PO, Russian) |
| **Type** | UI defect + enhancement |
| **Related artifacts** | `Problem_05.md` (sort always visible; features dropdown), `.ai/reports/01_olx-checkbox-dropdown-research.md`, `.ai/plans/30_filter-sort-i18n_plan.md`, `docs/01-spec/filter-ui.md` |
| **Stack** | Django 5.2 LTS · HTMX 1.9.12 · PostgreSQL 18 · vanilla JS · Tailwind CSS v4 |
| **Working-tree state** | Commit `dbdd974` base; `filter_sort.html` (new, untracked), `filter_form.html` (modified), `list.html` (modified) |

---

## 1. Problem Statement

The Product Owner identified three issues in the buyer-facing catalog filter/sort interface (`Decision_06.md`):

1. **Sort placement:** The sort selector currently renders as a separate form block *above* `#ad-list`. The PO wants it positioned visually in the same block as the filters, to the right of the "Apply filters" button.
2. **Features filter rendering:** The Features filter currently uses `<details>/<summary>` which expands inline and stretches the layout. The PO wants a clean floating dropdown with checkboxes (matching the Listing purpose dropdown behavior, but with checkboxes instead of plain options).
3. **Sort ↔ filter interaction:** Changing the sort currently resets all active filters (and vice versa). Sort and filters must be two independent systems — changing one must not alter the other's state.

### Verified business outcome

After this change, a buyer can:
- See the sort selector inline with the filter form (to the right of "Apply filters").
- Expand the Features filter as a floating dropdown (not an inline stretch) containing checkboxes.
- Switch sort order while keeping all active feature/listing-purpose/price filters intact.
- Change filters while keeping the current sort order intact.

---

## 2. Root Cause Analysis

### 2.1 Sort resets filters — stale hidden inputs (CONFIRMED)

**The stale-hidden-inputs bug is the root cause of Issue #3.** It is also the reason the sort form was placed outside `#ad-list`.

**Mechanism:**

1. `list.html:34` includes `filter_sort.html` **as a standalone `<form>` rendered outside `<div id="ad-list">`** (line 35).
2. HTMX requests from the filter form (inside `#ad-list`) cause the server to re-render and return **only `ad_list.html`** (the swap target is `innerHTML` of `#ad-list`).
3. `listings.py:510-512` and `search.py:232-233` both confirm: HTMX requests return only `ad_list.html`, which does **not** include `filter_sort.html`.
4. Because `filter_sort.html` is never re-rendered during HTMX navigation, its **hidden inputs** (lines 24–31 of the current file) carry **stale** filter values from the last full-page load.
5. When the buyer changes the sort, the sort form (with stale hidden inputs + new `sort` value) is submitted. The server receives the stale filter params, **silently reverting** the buyer's changes.

**Key insight:** The *same mechanism* that fixes the layout (Issue #1) fixes the staleness (Issue #3). If the sort control is moved **inside** `filter_form.html` (which lives inside `#ad-list` at `ad_list.html:14` and is re-rendered on every HTMX swap), its selected value is always fresh — no hidden inputs needed.

### 2.3 Features dropdown — `<details>` causes layout stretch (CONFIRMED)

`filter_form.html:47-63` currently uses:

```django
<details class="w-full">
    <summary class="flex items-center justify-between px-3 py-2 border border-gray-300 rounded-lg ...">
        <span>{% trans "Features" %}</span>
        ...
    </summary>
    <div class="mt-2 max-h-60 overflow-y-auto">
        {% for f in resolved_features %}
            <label class="flex items-center gap-1 ...">
                <input type="checkbox" name="features" value="{{ f.slug }}" ...>
                {{ f|get_lookup_name:LANGUAGE_CODE }}
            </label>
        {% endfor %}
    </div>
</details>
```

**Problem:** `<details>` is a block-level expand/collapse that renders its content inline, pushing all sibling elements (including the price inputs and Apply button) downward. On each expand, the form height grows, stretching the entire filter block. This is the "все растягивает" (stretches everything) complaint.

### 2.4 Reference pattern — OLX "Состояние" (verified via Playwright render)

The PO provided `https://www.olx.kz/elektronika/foto-video/` as the reference for the desired Features behavior. The OLX UI was rendered and the accessibility snapshot captured (see `.playwright-mcp/page-2026-08-23T19-31-00-283Z.yml`). The structure is:

```
Container:
  └─ label/caption: "Состояние" (paragraph, always visible above the control)
  └─ trigger button: "toggle flyout" [aria-haspopup="listbox"] [aria-expanded]
      └─ shows current selection: "Все объявления"
  └─ floating panel [listbox role]:
      ├─ option → checkbox "Все объявления" [checked] + label paragraph
      ├─ option → checkbox "Б/у" + label paragraph
      └─ option → checkbox "Новый" + label paragraph
```

**Key UX characteristics:**
- The dropdown **panel floats** (overlay), it does not push siblings.
- A single **trigger button** shows the current selection.
- **Checkboxes** allow multi-select.
- Clicking outside or pressing Escape closes the panel.

### 2.5 Existing dropdown pattern in this codebase

`header_catalog.html` already implements the exact floating-dropdown pattern (`data-{name}-toggle` + `data-{name}-panel` + `relative`/`absolute` + `hidden` toggle + document-level event delegation). This is the established convention and should be reused for Features rather than inventing a new component.

---

## 3. Requirements

### 3.1 Functional Requirements

| ID | Requirement | Priority | Source issue |
|---|---|---|---|
| FR-1 | The sort `<select>` must be inside `filter_form.html`, within the form that is re-rendered inside `#ad-list` on every HTMX navigation. | P0 (blocker) | #3 |
| FR-2 | The sort `<select>` must render visually to the right of the "Apply filters" button, in the same horizontal row. | P1 | #1 |
| FR-3 | The sort `<select>` must auto-submit the form on change (`onchange="this.form.requestSubmit()"`). | P1 | #1, #3 |
| FR-4 | The sort `<select>` must only render when there is no active search query (`{% if not query %}`). | P1 | #1 |
| FR-5 | The Features filter must render as a floating dropdown: trigger button showing the current selection count, expanding a floating panel containing checkboxes. | P0 | #2 |
| FR-6 | The Features dropdown must not push/stretch sibling form elements when expanded. | P0 | #2 |
| FR-7 | Each feature checkbox must be independently toggleable with server-rendered `checked` state reflecting the current URL params. | P1 | #2 |
| FR-8 | The Features dropdown must close when clicking outside its panel or pressing Escape. | P1 | UX consistency |
| FR-9 | Changing the sort must not alter any filter state (listing_purpose, features, price). | P0 | #3 |
| FR-10 | Changing any filter must not alter the sort order — the current sort value must be preserved in the URL and reflected in the re-rendered sort control. | P0 | #3 |
| FR-11 | The "Clear all filters" link must preserve the current sort value in the resulting URL. | P1 | #3 |

### 3.2 Non-Functional Requirements

| ID | Requirement |
|---|---|
| NFR-1 | No new third-party JS libraries. Use vanilla JS consistent with `header_catalog.html`. |
| NFR-2 | The dropdown JS must use **document-level event delegation** (not element-specific `addEventListener`), because `filter_form.html` is destroyed and recreated on every HTMX swap. Inline `addEventListener` would be lost. (This mirrors `header_catalog.html:415` pattern, but generalized via `e.target.closest('[data-filter-toggle]')`.) |
| NFR-3 | The sort control must reuse the form's existing `hx-get="{{ request.path }}"` action — it must **not** introduce a new `hx-get` attribute. |
| NFR-4 | All new translatable strings must use `{% trans %}` / `{% blocktrans %}` (no hardcoded text). |
| NFR-5 | Touch targets must meet 44×44px minimum (consistent with `header_catalog.html`). |

---

## 4. Design Decisions

### D-1: Move sort INTO `filter_form.html` (inside the HTMX swap boundary)

**Decision:** The sort `<select>` is moved from the standalone `filter_sort.html` form into `filter_form.html`, as a field within the existing form.

**Rationale:** This is the single change that resolves Issue #3 (stale hidden inputs). `filter_form.html` (line 14 of `ad_list.html`) is inside `#ad-list`, which is the HTMX swap target (`hx-target="#ad-list"`). It is re-rendered server-side on every form submission, chip removal, and pagination click. The `<select>` element's `selected` state is set server-side via `{% if current_sort == X %}selected{% endif %}` (same pattern already used for `listing_purpose` at `filter_form.html:24`). No client-side state synchronization is needed.

**Implementation sketch (within `filter_form.html`, after the Apply button):**

```django
{% if not query %}
    <div class="flex items-end gap-2">
        <label for="sort" class="block text-sm font-medium text-gray-700 mb-1">
            {% trans "Sort" %}
        </label>
        <select name="sort" id="sort"
                class="px-3 py-2 border rounded-lg text-sm bg-white"
                onchange="this.form.requestSubmit()">
            <option value="date_desc" {% if current_sort == 'date_desc' or not current_sort %}selected{% endif %}>
                {% trans "Newest first" %}
            </option>
            <option value="date_asc" {% if current_sort == 'date_asc' %}selected{% endif %}>
                {% trans "Oldest first" %}
            </option>
            <option value="price_asc" {% if current_sort == 'price_asc' %}selected{% endif %}>
                {% trans "Price: low to high" %}
            </option>
            <option value="price_desc" {% if current_sort == 'price_desc' %}selected{% endif %}>
                {% trans "Price: high to low" %}
            </option>
        </select>
    </div>
{% endif %}
```

**Positioning:** The sort field is placed inside the same `<div class="flex flex-wrap gap-4 items-end">` row (line 15 of `filter_form.html`), after the "Apply filters" button block (line 67-73). It uses `items-end` alignment so the label and select align with the button. Sort auto-submits on change via `onchange="this.form.requestSubmit()"` (PO CONFIRMED — see D-3/Q-3).

**Sort values:** The four `option` values (`date_desc`, `date_asc`, `price_asc`, `price_desc`) correspond to the `AdSort` StrEnum (`apps/core/enums.py:11-17`). The `name="sort"` attribute is already expected by both views (`listings.py:486`, `search.py:140`).

### D-2: Sort visibility — hide during search (PO CONFIRMED)

**Decision:** Wrap the sort control in `{% if not query %}`.

**Rationale:** When a buyer submits a search (`q` param present), the search view (`search.py:142-192`) **always** orders by FTS relevance (`-rank`), regardless of the `sort` parameter. The `current_sort` context variable is still passed to the template (`search.py:213` for completeness of URL preservation), but it is **not** applied during search. Rendering a sort selector during search would show a control that is silently ignored by the server — a misleading UX.

> **Fact (not assumption):** `search.py:142` checks `if query:` and enters the relevance-ordering branch. The `else` branch (lines 182–192) applies the sort. There is no path where both `query` and a non-relevance sort are simultaneously active.

**Implication for `filter_sort.html`:** The current file already implements this guard at line 13 (`{% if not query %}`). The new implementation preserves it.

### D-3: Replace Features `<details>` with floating checkbox dropdown

**Decision:** Replace the `<details>/<summary>` (lines 47–63 of `filter_form.html`) with a floating dropdown using the `header_catalog.html` pattern, adapted for checkboxes.

**Structure (matching OLX "Состояние"):**

```django
{% if resolved_features %}
    <div data-filter-trigger class="relative">
        {# Trigger button — shows "Features" label + count #}
        <button type="button"
                data-filter-toggle
                aria-haspopup="listbox"
                aria-expanded="false"
                class="flex items-center justify-between px-3 py-2 border border-gray-200 rounded-lg text-sm font-medium text-gray-700 bg-white hover:bg-gray-50 min-h-[44px]">
            <span>{% trans "Features" %}</span>
            {% if current_features %}
                <span class="text-xs text-gray-500">({{ current_features|length }})</span>
                <svg class="w-4 h-4 transition-transform duration-150" ...>
                    <path .../>
                </svg>
            {% else %}
                <svg class="w-4 h-4 transition-transform duration-150" ...>
                    <path .../>
                </svg>
            {% endif %}
        </button>
        {# Floating panel — checkboxes, server-rendered checked state #}
        <div data-filter-panel
             role="listbox"
             class="absolute left-0 z-[90] mt-1 w-64 bg-white border border-gray-200 rounded-lg shadow-lg hidden">
            <div class="py-1 max-h-60 overflow-y-auto">
                {% for f in resolved_features %}
                    <label class="flex items-center gap-2 px-3 py-2 text-sm text-gray-700 hover:bg-blue-50 cursor-pointer min-h-[44px]">
                        <input type="checkbox"
                               name="features"
                               value="{{ f.slug }}"
                               {% if f.slug in current_features %}checked{% endif %}
                               class="h-4 w-4 text-blue-600 focus:ring-blue-500">
                        {{ f|get_lookup_name:LANGUAGE_CODE }}
                    </label>
                {% endfor %}
            </div>
        </div>
    </div>
{% endif %}
```

**CSS justification (Tailwind v4 — already in `output.css`):**
- `absolute`, `z-[90]`, `shadow-lg`, `hidden`, `rotate-180`, `transition-transform`, `duration-150`, `min-h-[44px]`, `focus:ring-blue-500` — all present in the committed Tailwind output (per existing usage in `header_catalog.html`).

### D-4: Dropdown JS — document-level delegation

**Decision:** Implement the Features dropdown toggle/close logic as a **module-level IIFE** using **document-level event delegation** (`e.target.closest('[data-filter-toggle]')`), not per-element `addEventListener`.

**Rationale:** `filter_form.html` is destroyed and recreated on every HTMX swap inside `#ad-list`. Inline `addEventListener` calls would execute on page load but would be lost when the form is replaced. Document-level delegation survives re-renders because the listener lives on `document`, not on the form element.

**Behavior spec:**
- Clicking `data-filter-toggle` toggles `aria-expanded` (`true`/`false`) and the `hidden` class on the sibling `data-filter-panel`.
- Clicking outside the `[data-filter-trigger]` wrapper closes the panel.
- Pressing Escape closes any open panel.
- The caret SVG rotates 180° when open (`rotate-180`).

This mirrors the existing `closeCity()` / `closeCategories()` pattern in `header_catalog.html:415-421` but generalized via `e.target.closest()`.

### D-5: Listing purpose — keep native `<select>` (PO CONFIRMED)

**Decision:** Leave `listing_purpose` as a native `<select>` (`filter_form.html:21`). Do NOT convert it to the custom dropdown component.

**Rationale:** The PO's complaint (Issue #2) was **only** about Features stretching the layout. The native `<select>` does not have this problem — it has a fixed, compact rendered size. Converting it would add complexity with no PO-requested benefit. The OLX reference shows both Condition and Subcategory using the same custom dropdown, but the PO explicitly scoped the change to Features ("поле Features").

> This is an **assumption** (see §5.4, Q-2). If visual consistency with Features is desired, `listing_purpose` can be converted in a follow-up.

### D-6: Delete `filter_sort.html`

**Decision:** Delete `src/backend/templates/ads/partials/filter_sort.html` and remove its `{% include %}` from `list.html:34`.

**Rationale:** Its functionality (sort control) is now in `filter_form.html`, which is inside the HTMX swap boundary. Keeping it would create a redundant, stale-prone duplicate.

---

## 5. Ambiguities, Assumptions, and Open Questions — RESOLVED

All open questions were presented to the Product Owner and **confirmed as "Option А"** on 2026-08-23.

### 5.1 Resolved by evidence (facts)

| # | Item | Evidence | Decision |
|---|---|---|---|
| F-1 | Sort is stale because `filter_sort.html` is outside `#ad-list` | `list.html:34` (include before `#ad-list`), `listings.py:510-512` / `search.py:232-233` (HTMX returns only `ad_list.html`), `filter_sort.html:24-31` (stale hidden inputs) | Move sort into `filter_form.html` |
| F-2 | Sort must be hidden during search | `search.py:142` enters relevance branch `if query:`; sort is ignored | `{% if not query %}` guard around sort |
| F-3 | Features `<details>` causes layout stretch | `filter_form.html:47` `<details class="w-full">` is block-level, inline expansion | Replace with floating dropdown |
| F-4 | `header_catalog.html` has a reusable dropdown pattern | `header_catalog.html:76-110` (structure), `:407-422` (JS), `:539-544` (HTMX survival via delegation) | Reuse pattern for Features |
| F-5 | All 8 `hx-get=` in `ad_list.html` are accounted for | Static source: lines 42, 53, 60, 131, 135, 145, 153, 157 | Contract preserved (see §6) |
| F-6 | `test_listings_sort.py` has no markup assertions on sort control | `test_listings_sort.py:56-109` — tests assert on ad-title positions + URL params only | No test break risk |

### 5.2 Confirmed decisions (PO approved — Option A)

| ID | Decision (PO CONFIRMED: "Для всех вопросов — А") | Rationale |
|---|---|---|
| D-1 | **Hide sort during search.** Wrap the sort `<select>` in `{% if not query %}`. | When `q` is present, `search.py:142` always orders by FTS relevance (`-rank`), ignoring the `sort` parameter. Showing a control that is silently ignored is misleading. |
| D-2 | **Listing purpose stays as native `<select>`.** No conversion to custom dropdown. | PO's complaint was only about Features stretching. Native `<select>` has a fixed, non-stretching size. `listing_purpose` is single-select (radio, not checkboxes), so converting adds complexity with no PO benefit. |
| D-3 | **Sort auto-submits on change** (`onchange="this.form.requestSubmit()"`). Filters still use the "Apply filters" button. | Sort is a fast UX switch (OLX pattern: "Сортировать по:" → immediate reordering). With sort inside `filter_form.html`, `requestSubmit()` serializes all live form fields (checkboxes, selects), so filters are preserved — exactly the Issue #3 fix. |

### 5.3 Previously-open questions — now resolved

| Q | Answer (PO CONFIRMED) |
|---|---|
| Q-1: Hide sort during search? | **Yes** — `{% if not query %}` guard. |
| Q-2: Convert `listing_purpose` to custom dropdown? | **No** — keep native `<select>`. |
| Q-3: Auto-submit sort or require "Apply filters"? | **Auto-submit** via `onchange="this.form.requestSubmit()"`. |

---

## 6. Test Contract Impact

**Source:** Research report verified all test files at `src/backend/apps/ads/tests/`.

### 6.1 Static source tests (`test_catalog_filters.py`)

| Test | File:line | Assertion | Impact of change |
|---|---|---|---|
| `test_form_uses_request_path_not_empty` | `test_catalog_filters.py:307-312` | `filter_form.html` contains `hx-get="{{ request.path }}"` and NOT `hx-get=""` | ✅ **No impact.** The sort `<select>` reuses the form's existing `hx-get`. The `filter_form.html` already has this. |
| `test_all_htmx_links_have_push_url` | `test_catalog_filters.py:314-319` | `ad_list.html` source has exactly **8** `hx-get=` and **8** `hx-push-url="true"` | ✅ **No impact.** The sort `<select>` with `onchange` adds **0** `hx-get` to `ad_list.html` (it's in `filter_form.html`, a separate included file). `filter_sort.html` currently contributes 0 to `ad_list.html`'s count. ⚠️ **Breaks to 9/9 ONLY** if sort is implemented as a standalone `hx-get` element inline in `ad_list.html` (explicitly avoided by D-1). |
| `test_clear_all_filters_has_push_url` | `test_catalog_filters.py:321-326` | `ad_list.html` has `hx-push-url="true"` and `hx-get="?page=1` | ✅ **No impact.** Unchanged. |

### 6.2 Integration tests (rendered output)

| Test | File:line | Assertion | Impact of change |
|---|---|---|---|
| `test_form_renders_path_only_hx_get` | `test_catalog_filters.py:332-345` | HTMX `GET /` renders `hx-get="/"` in output | ✅ **No impact.** Sort is a form field, not an `hx-get` link. |
| `test_chip_link_has_push_url_in_rendered_output` | `test_catalog_filters.py:347-362` | Feature chip removal links have `hx-push-url="true"` | ✅ **No impact.** Chip removal uses `current_sort` (line 42, 53) — unchanged. |
| `test_pagination_links_have_push_url_in_rendered_output` | `test_catalog_filters.py:364-377` | Pagination links have `hx-push-url="true"` and "Page navigation" | ✅ **No impact.** Paginated URLs already preserve `current_sort` (line 42). |
| `test_form_submission_does_not_accumulate_params` | `test_catalog_filters.py:383-410` | `?features=delivery` returns only delivery ads (AND semantics) | ✅ **No impact.** Features checkbox logic unchanged. |

### 6.3 Sort ordering tests (`test_listings_sort.py`)

| Test | File:line | Assertion | Impact |
|---|---|---|---|
| `test_date_old_orders_oldest_first` | `test_listings_sort.py:56-71` | `?sort=date_asc` → ads ordered oldest-first by title position | ✅ **No impact.** Tests URL param + ad positions, not sort control markup. |
| `test_date_new_orders_newest_first` | `test_listings_sort.py:73-85` | `?sort=date_desc` → newest-first | ✅ **No impact.** |
| `test_default_sort_is_date_new` | `test_listings_sort.py:87-97` | No param → `date_desc` default | ✅ **No impact.** |
| `test_date_asc_and_desc_are_reversed` | `test_listings_sort.py:99-109` | Asc and desc produce opposite orderings | ✅ **No impact.** |

### 6.4 Test suite to run

- `make test` (fast gate, includes `test_catalog_filters.py` and `test_listings_sort.py`)
- Test DB: Docker container `mko-bazuna-test-db-*` on port 5433; run via `make test` (auto-starts DB).

---

## 7. Files Affected (Change List)

| File | Action | Description |
|---|---|---|
| `src/backend/templates/ads/partials/filter_form.html` | **Modify** | (1) Add sort `<select>` with `onchange="this.form.requestSubmit()"` after "Apply filters" button, guarded by `{% if not query %}`. (2) Replace Features `<details>/<summary>` (lines 47-63) with floating checkbox dropdown (`data-filter-*` pattern). |
| `src/backend/templates/ads/list.html` | **Modify** | Remove `{% include "ads/partials/filter_sort.html" %}` at line 34. |
| `src/backend/templates/ads/partials/filter_sort.html` | **Delete** | No longer needed; functionality moved to `filter_form.html`. |
| **JS file** (new, TBD) | **Create** | Document-level delegated dropdown toggle + outside-click + Escape-close JS module. See §4.4 for placement decision. |
| No view changes | — | `listings.py` and `search.py` already pass all required context (`current_sort`, `current_features`, `resolved_features`, `current_listing_purpose`, `resolved_purposes`, `min_price`, `max_price`, `query`). |
| No model/enum changes | — | `AdSort` enum (`enums.py:11-17`) and sort values (`date_desc`, `date_asc`, `price_asc`, `price_desc`) are already correct and match existing `option` values. |

### 7.1 JS file placement (open)

The dropdown JS needs a home. Options:
- **(A)** Inline `<script>` at the bottom of `filter_form.html` — **rejected** (D-4 requires `htmx:afterSwap` re-attachment since `filter_form.html` is inside the HTMX swap boundary and is destroyed/recreated).
- **(B)** Inline `<script>` at the bottom of `ad_list.html` — works (same file as `filter_form.html` include), but still needs delegation.
- **(C)** New static JS file (e.g. `src/theme/static/theme/js/filter-dropdowns.js`) included in `list.html` — cleanest separation; the IIFE runs once on `DOMContentLoaded`, uses document-level delegation. **Recommended.**

---

## 8. Edge Cases & Constraints

| EC # | Scenario | Handling |
|---|---|---|
| EC-1 | Search results (`q` present) | Sort selector hidden. Features dropdown still available. |
| EC-2 | Favorites page | `ad_list.html:13` guards `{% if show_filters %}` — filter form is not rendered there, so no impact. |
| EC-3 | No features available (`resolved_features` empty) | Features dropdown block guarded by `{% if resolved_features %}` — not rendered. |
| EC-4 | No listing purposes (`resolved_purposes` empty) | Native `<select>` guarded by `{% if resolved_purposes %}` — not rendered. |
| EC-5 | Multiple features selected, then user changes sort | Sort submits the entire form via `requestSubmit()` — all checked checkboxes are serialized from the live DOM (not stale hidden inputs). Filters preserved. |
| EC-6 | Mobile viewport | Touch targets use `min-h-[44px]`; dropdown panel uses `absolute` positioning which works on mobile (panel flows within viewport). |
| EC-7 | HTMX re-render after sort change | `#ad-list` is swapped; `filter_form.html` re-renders with `current_sort` reflecting the new value — the `<select>` shows the correct `selected` option. |

---

## 9. Acceptance Criteria

| AC # | Given | When | Then |
|---|---|---|---|
| AC-1 | Buyer is on a category page (no search query) | They look at the filter form | Sort `<select>` is visible to the right of "Apply filters", inside the filter form block |
| AC-2 | Buyer is on search results | They look at the filter form | Sort `<select>` is **not** rendered |
| AC-3 | Buyer has features checked | They change the sort dropdown | All checked features remain checked; URL preserves `features=` params; results reorder |
| AC-4 | Buyer changes a feature checkbox | They click "Apply filters" | Sort value is preserved in the URL; selected sort option remains correct in the re-rendered control |
| AC-5 | Buyer expands the Features dropdown | — | The floating panel appears (overlay, not inline stretch); checkboxes are visible |
| AC-6 | Buyer clicks outside the Features dropdown | — | The panel closes |
| AC-7 | Buyer presses Escape while Features dropdown is open | — | The panel closes |
| AC-8 | Buyer has features selected | They look at the Features trigger button | The count of selected features is shown `(N)` |
| AC-9 | Test suite | `make test` | `test_catalog_filters.py` and `test_listings_sort.py` all pass; `ad_list.html` source still has exactly 8 `hx-get=` and 8 `hx-push-url="true"` |

---

## 10. Internationalization

The following `{% trans %}` strings are **already present** in the committed `.po` files (verified at `src/backend/locale/ru/LC_MESSAGES/django.po`):
- `"Sort"` (line 103)
- `"Features"` (line 115)
- `"Apply filters"` (line 121)
- `"Listing purpose"` (line 125)
- `"Newest first"` / `"Oldest first"` / `"Price: low to high"` / `"Price: high to low"` — verify these existing strings exist (same values from current `filter_sort.html:39-42`.

**No new translatable strings** need to be added for this change, assuming the sort option labels in `filter_form.html` match the existing labels from `filter_sort.html` (lines 39–42). The existing `{% trans "selected" %}` (`filter_form.html:51`) is reused.

---

## 11. Sequence of Rendering (post-change)

```text
list.html (full page load)
├─ header_catalog.html
├─ (filter_sort.html include REMOVED)
├─ #ad-list
│   ├─ ad_list.html
│   │   ├─ {% if show_filters %}
│   │   │   └─ filter_form.html  ← NOW CONTAINS SORT SELECT
│   │   │       ├─ hidden inputs: q, category, city
│   │   │       ├─ listing_purpose (native <select>)
│   │   │       ├─ min_price / max_price (number inputs)
│   │   │       ├─ Features (floating checkbox dropdown with data-filter-toggle/panel)
│   │   │       ├─ "Apply filters" button
│   │   │       └─ sort <select> onchange=requestSubmit (if not query) ← MOVED HERE
│   │   ├─ ad cards grid (or empty state)
│   │   └─ pagination (if >1 page)
│   └─ (active filter chips — preserve current_sort in their URLs)
└─ footer

HTMX navigation (filter submit, chip remove, pagination, sort change):
├─ Request → ad_list.html (partial)
├─ Server re-renders filter_form.html (inside #ad-list) → all controls fresh
├─ #ad-list swapped via innerHTML
└─ Sort value preserved via current_sort in context + URL params
```

---

## 12. Summary of Changes

This specification resolves all three issues from `Decision_06.md` with a **single core architectural fix**: move the sort control from the stale, outside-`#ad-list` `filter_sort.html` into the HTMX-swap-boundary inside `filter_form.html`. This fixes Issue #3 directly (no stale hidden inputs — all controls are live DOM re-rendered on every swap). It simultaneously fixes Issue #1 (sort is now in the same visual block as filters, positioned right of "Apply filters"). Issue #2 (Features `<details>` stretch) is fixed by replacing `<details>/<summary>` with the existing floating-checkbox-dropdown pattern from `header_catalog.html`, matching the OLX "Состояние" reference the PO provided.
