# Research Report: OLX-Style "Dropdown with Checkboxes" Filter Pattern for Mko Bazuna

**Date:** 2026-08-23  
**Scope:** Feasible implementation approaches for converting the catalog filter form (`filter_form.html`) to use collapsible dropdown-with-checkboxes panels for `listing_purpose` and `features`, matching the OLX pattern.  
**Stack constraints:** Django 5.2 LTS · HTMX 1.9.12 (no `hx-on`) · vanilla JS · Tailwind CSS v4 · PostgreSQL 18 · HTMX-driven MPA

---

## 1. Current State Analysis

### 1.1 The filter form (`filter_form.html`)

The form is a single `<form method="get">` that submits via HTMX:

```html
<form method="get"
      hx-get="{{ request.path }}"
      hx-target="#ad-list"
      hx-swap="innerHTML"
      hx-push-url="true"
      class="mb-6 p-4 bg-white rounded-lg shadow space-y-4">
```

**Key attributes:**
- `hx-get="{{ request.path }}"` — path-only URL (no inherited query string). This was fixed per `28_filter-reset-accumulation_spec.md` (previously `hx-get=""`).
- `hx-push-url="true"` — updates browser URL after swap.
- `hx-target="#ad-list"` — swaps the results container.

**Inside the form (in order):**
1. **Hidden inputs** preserve cross-navigation state: `q`, `category`, `city`, `min_price`, `max_price` (conditionally rendered only when present).
2. **`listing_purpose`** — a plain `<select name="listing_purpose">` with an `<option value="">` ("Any") default. Single-select, always submits a value.
3. **`features`** — inline checkboxes, `name="features"`, AND semantics on the server side. Checked state driven by `{% if f.slug in current_features %}checked{% endif %}`.
4. **`sort`** — a `<select name="sort">` shown only when `not query`. Values: `date_desc`, `date_asc`, `price_asc`, `price_desc` (from `AdSort` StrEnum).
5. **"Apply filters"** submit button.

The form renders horizontally in a `flex flex-wrap gap-4 items-end` layout.

### 1.2 The containing partial (`ad_list.html`)

`ad_list.html` is the HTMX-swappable fragment inside `#ad-list`. It includes `filter_form.html` conditionally (`{% if show_filters %}`). The comment at the top of `ad_list.html` explains the rationale:

> The filter form lives inside the HTMX-swappable region so that every navigation (form submit, "Clear all filters", chip removal, pagination) re-renders it server-side — preventing stale checkbox/select state from persisting and accumulating across filter sessions.

**Critical implication:** Every HTMX navigation **replaces the entire DOM of `#ad-list`**, including the form. Any client-side JS state (dropdown open/closed, scroll position within a panel) is **wiped** on every form submission, chip removal, or pagination click. This is by design — the server is the single source of truth for filter state.

### 1.3 Views (`listings.py` and `search.py`)

Both views share the same filter-parsing logic and pass the same context to the template:

| Context variable | Type | Source | Used for |
|---|---|---|---|
| `resolved_purposes` | queryset of `LookupItem` | `CategoryLookupResolver.get_resolved_purposes(category)` or all active items of group `listing_purpose` | Populating the purpose dropdown options |
| `resolved_features` | queryset of `LookupItem` | `CategoryLookupResolver.get_resolved_features(category)` or all active items of group `listing_feature` | Populating feature checkboxes |
| `current_listing_purpose` | `str \| None` (slug) | `request.GET.get("listing_purpose")` | Pre-selecting the purpose `<select>` |
| `current_features` | `list[str]` (slugs) | `request.GET.getlist("features")` | Pre-checking feature checkboxes |
| `current_sort` | `str` (AdSort value) | `request.GET.get("sort", AdSort.DATE_NEW)` | Pre-selecting the sort `<select>` |
| `query` | `str` | `request.GET.get("q", "")` | Hidden input; controls sort visibility |
| `current_category` | `str \| None` | `category_slug` (path param) | Hidden input |
| `current_city` | `str \| None` | `effective_city` | Hidden input |
| `min_price` / `max_price` | `str \| None` | query params | Hidden inputs |

**Filter semantics (both views):**
- `listing_purpose` — single-select exact slug match: `ads.filter(listing_purpose__slug=listing_purpose_slug)`
- `features` — multi-select AND: chained `.filter(features__slug=fslug)` for each slug
- Sort overrides to `-rank` when `q` is present; otherwise uses `AdSort` enum

**Lookup resolution:** `CategoryLookupResolver` walks the MPTT ancestor chain (nearest-ancestor-wins) with 300s cache. When no category is active, the full set of active `LookupItem` rows is shown.

### 1.4 Test contracts (critical constraints)

`src/backend/apps/ads/tests/test_catalog_filters.py` — `class TestFilterUrlReset`:

**Static template source checks (no DB):**
1. `test_form_uses_request_path_not_empty` — asserts `'hx-get="{{ request.path }}'` **is present** in `filter_form.html` source AND `'hx-get=""'` is **not** present.
2. `test_all_htmx_links_have_push_url` — asserts `ad_list.html` source has **exactly 8** `hx-get=` occurrences and **exactly 8** `hx-push-url="true"` occurrences.
3. `test_clear_all_filters_has_push_url` — asserts `'hx-push-url="true"'` and `'hx-get="?page=1'` in `ad_list.html` source.

**Rendered output checks (HTMX request):**
4. `test_form_renders_path_only_hx_get` — HTMX `GET /?features=delivery` renders the form with `hx-get="/"` (path only, no query params echoed in the form action).
5. `test_chip_link_has_push_url_in_rendered_output` — rendered chip removal links carry `hx-push-url="true"`.
6. `test_pagination_links_have_push_url_in_rendered_output` — rendered pagination links carry `hx-push-url="true"`.

**Behavioral:**
7. `test_form_submission_does_not_accumulate_params` — submitting `GET /?features=delivery` returns only ads with the `delivery` feature (AND semantics, no stale params).

### 1.5 Existing JS/dropdown patterns in the codebase

The codebase already implements collapsible dropdown patterns with vanilla JS (HTMX 1.9.12 has no `hx-on`). The **canonical pattern** is in `header_catalog.html` and `language_switcher.html`:

**Pattern structure (from `header_catalog.html` "All Categories" dropdown):**
```html
<div class="relative" data-categories-trigger>
    <button type="button" data-categories-toggle
            aria-haspopup="listbox" aria-expanded="false"
            aria-controls="menu-{{ cat.id }}"
            class="... min-h-[44px]">
        <span data-categories-label>...</span>
        <svg class="w-4 h-4 transition-transform duration-150"> <!-- caret -->
    </button>
    <div data-categories-panel
         class="absolute z-[90] mt-1 w-72 bg-white border border-gray-200 rounded-lg shadow-lg hidden">
        <!-- dropdown content -->
    </div>
</div>

<script>
(function () {
    'use strict';
    var catToggle = document.querySelector('[data-categories-toggle]');
    var catPanel = document.querySelector('[data-categories-panel]');
    function closeCategories() { /* add 'hidden', reset aria-expanded */ }
    if (catToggle && catPanel) {
        catToggle.addEventListener('click', function (e) {
            e.stopPropagation();
            var isOpen = !catPanel.classList.contains('hidden');
            if (isOpen) { closeCategories(); return; }
            catPanel.classList.remove('hidden');
            catToggle.setAttribute('aria-expanded', 'true');
        });
        document.addEventListener('click', function (e) { /* outside-click-to-close */ });
        document.addEventListener('keydown', function (e) {
            if (e.key === 'Escape') closeCategories();
        });
    }
    // Re-attach handlers after HTMX swaps
    window.addEventListener('htmx:afterSwap', function (e) {
        if (e.target) attachCategoryHandlers(e.target);
    });
})();
</script>
```

**Patterns observed across all components:**
- `data-*` attributes for selectors (no `hx-on`)
- `aria-expanded` toggles between `"true"`/`"false"`
- `aria-controls` linking toggle button to panel `id`
- `classList.add('hidden')` / `classList.remove('hidden')` for visibility
- `e.stopPropagation()` on the toggle to prevent outside-click from immediately closing
- `document.addEventListener('click', ...)` for outside-click-to-close
- `document.addEventListener('keydown', ...)` with `e.key === 'Escape'`
- `min-h-[44px]` enforced for all touch targets
- `htmx:afterSwap` listener to re-attach handlers after partial updates
- Caret SVG rotates 180° (`rotate-180` class) when expanded (see `header_catalog.html` lines 327-329, 390-393)

**No static JS files exist** — all JS is inline `<script>` blocks in templates. The CSS pipeline is Tailwind v4 standalone CLI; new utility classes require regenerating `output.css` via Docker.

### 1.6 PO intent (Problem_05)

`.ai/problems/Problem_05.md` (in Russian) documents the PO's explicit requirements:

> **Фильтры (Filters):**
> 1) Блок Features и Listing purpose нужно сделать выпадающим списком с чекбоксами, как на OLX.
> *(Make the Features and Listing purpose blocks into a dropdown with checkboxes, like OLX.)*
>
> **Сортировка (Sorting):**
> 1) Нужно отвязать сортировку от кнопки фильтров — сортировка должна применяться без кнопки фильтровать — просто при смене вида сортировки.
> *(Decouple sort from the filter button — sorting should apply on change, without clicking "Apply filters".)*
> 2) Блок сортировки нужно вынести визуально отдельно от блока фильтров и она должна отображаться всегда.
> *(Visually separate the sort block from the filter block, and it should always be visible.)*

These are referenced in `28_filter-reset-accumulation_spec.md` §9 (Non-Goals): *"Moving sort out of the filter form into a separate component (see Problem_05)"* and *"Converting filter selects to dropdowns-with-checkboxes (OLX pattern)"*.

---

## 2. The OLX "Dropdown with Checkboxes" Pattern

### 2.1 Live verification

A live fetch of `https://www.olx.pl/oferty/q-laptop/` (August 23, 2026) confirms the pattern. The filter sidebar on OLX consists of collapsible sections — **Filtry** (Filters) with groups like:

- **Kategoria** (Category) — button dropdown
- **Cena** (Price) — min/max inputs
- **Stan** (Condition) — "Wszystkie" (All) button dropdown

Each filter group label is clickable: it acts as a **toggle** that expands/collapses a panel containing the filter options. The options within are **checkboxes** (for multi-select) or **radio buttons** (for single-select). There is **no inline "Apply" per section** — the global filter application happens through the page's natural URL-based state management.

### 2.2 Pattern characteristics (from competitor research + live verification)

| Characteristic | OLX implementation | Industry consensus |
|---|---|---|
| **Expand/collapse** | Clicking the section header toggles visibility of the options panel | All platforms use collapsible sections (Forge, CFPB, FB Marketplace accordions) |
| **Multi-select control** | Checkboxes inside the panel | Checkboxes dominate for multi-select (3/4 platforms per competitor research §3.2) |
| **Single-select control** | Radio-style or single-checkbox grouping | Dropdown/radio for single-select, checkbox for multi |
| **Apply per section** | No per-section "Apply" — global apply or URL-state | Most platforms apply on change or via global button |
| **Outside-click-to-close** | Yes — clicking outside collapses all open panels | Standard across Avito, OLX, FB Marketplace, Craigslist overlay |
| **Escape-to-close** | Yes — keyboard Escape collapses open panel | WCAG-required for modal/dropdown interactions |
| **ARIA** | `aria-expanded`, `aria-controls`, `role="button"` | WCAG 2.1 AA — required for accessible disclosure widgets |
| **Active filter summary** | Chips above results with individual removal | 3/4 platforms show removable chips (Craigslist is the exception) |

### 2.3 OLX-specific behavioral details (from Forge & CFPB pattern libraries)

The Forge (LSEG) "Search Filters Extended" component and CFPB "Filterable List Control Panels" both implement the same OLX-aligned pattern:

1. **Section header** is an interactive toggle (button or button-like element). It shows:
   - Section label (e.g., "Features", "Listing purpose")
   - A chevron icon that rotates 180° when expanded
   - Optionally, a count badge showing how many options in that section are currently selected (e.g., "Features (2)")

2. **Expanded panel** contains the options as a vertical list, each with:
   - A checkbox (multi-select) or radio (single-select)
   - The option label
   - Sufficient vertical spacing for 44px+ touch targets

3. **Collapsed by default** — only the section that was interacted with is expanded.

4. **Progressive disclosure** — only one section is typically expanded at once (accordion behavior), reducing scroll depth.

### 2.4 How OLX handles the "Apply" question

From the competitor research §3.2 and §3.4:
- OLX does **not** have a per-section "Apply" button inside each dropdown.
- The global "Szukaj" (Search) button applies all filters at once.
- On desktop, the sort selector is rendered as **horizontal tabs above the results** (not inside the filter sidebar).
- On mobile, filters collapse into a full-screen drawer with a sticky "Apply" button at the bottom.

This directly aligns with Problem_05's requirement: sort should be decoupled from the filter form, applied on change, and visually separated.

---

## 3. Feasible Implementation Approaches

### Approach A: Collapsible checkbox panels + global "Apply filters" (form submit)

**Description:** Convert the `<select>` and inline checkboxes into collapsible `<button>` toggle + `<div>` panel with checkboxes/radios inside. The form still submits all at once via the "Apply filters" button.

**HTML structure (template-driven):**
```html
<form method="get" hx-get="{{ request.path }}" ...>
    <!-- Hidden inputs for cross-navigation state (unchanged) -->

    <!-- Listing purpose: collapsible checkbox dropdown -->
    <div class="relative" data-filter-dropdown data-filter-name="listing_purpose">
        <button type="button" data-filter-toggle
                aria-haspopup="listbox" aria-expanded="false"
                aria-controls="filter-panel-listing_purpose"
                class="flex items-center justify-between w-full px-3 py-2 border rounded-lg bg-white min-h-[44px] text-sm">
            <span>Listing purpose</span>
            <svg class="w-4 h-4 transition-transform duration-150"> ... </svg>
        </button>
        <div id="filter-panel-listing_purpose" data-filter-panel
             class="absolute z-10 mt-1 w-full bg-white border border-gray-200 rounded-lg shadow-lg hidden">
            {% for p in resolved_purposes %}
            <label class="flex items-center px-4 py-2.5 text-sm hover:bg-gray-50 min-h-[44px]">
                <input type="radio" name="listing_purpose" value="{{ p.slug }}"
                       {% if current_listing_purpose == p.slug %}checked{% endif %}>
                <span class="ml-2">{{ p|get_lookup_name:LANGUAGE_CODE }}</span>
            </label>
            {% endfor %}
        </div>
    </div>

    <!-- Features: collapsible checkbox dropdown (same pattern) -->
    <div class="relative" data-filter-dropdown data-filter-name="features">
        <button type="button" data-filter-toggle
                aria-haspopup="listbox" aria-expanded="false"
                aria-controls="filter-panel-features"
                class="...">
            <span>Features</span>
            <svg>...</svg>
        </button>
        <div id="filter-panel-features" data-filter-panel class="... hidden">
            {% for f in resolved_features %}
            <label class="flex items-center px-4 py-2.5 text-sm hover:bg-gray-50 min-h-[44px]">
                <input type="checkbox" name="features" value="{{ f.slug }}"
                       {% if f.slug in current_features %}checked{% endif %}>
                <span class="ml-2">{{ f|get_lookup_name:LANGUAGE_CODE }}</span>
            </label>
            {% endfor %}
        </div>
    </div>

    <!-- Apply button (unchanged) -->
    <button type="submit">Apply filters</button>
</form>
```

**JS:** A delegated-event IIFE (listeners on `document`, not on individual elements). ~40-50 lines of vanilla JS, following the existing `header_catalog.html` pattern but using event delegation so it survives HTMX DOM replacements.

**Pros:**
- **Minimal change to server-side logic** — views, URL params, filter semantics are completely unchanged. Checkboxes still submit via the form's normal GET serialization.
- **Preserves all test contracts** — the form still has `hx-get="{{ request.path }}"`, `hx-push-url="true"`, the "Apply filters" button. The test asserting no `hx-get=""` still passes. The 8 `hx-get=` / 8 `hx-push-url="true"` count in `ad_list.html` is unaffected (the dropdowns live in `filter_form.html`, not `ad_list.html`).
- **Follows existing codebase pattern** — the `data-*` + `aria-expanded` + vanilla JS pattern in `header_catalog.html` is already the established convention.
- **Progressive enhancement** — without JS, checkboxes are still visible (panel `hidden` class removed on init, or `<noscript>` fallback). Form submits normally.
- **No race conditions** — the user makes all selections, then submits once. No auto-submit-on-change.

**Cons:**
- Users must click "Apply filters" to submit — no instant feedback on checkbox toggle.
- Dropdown panels are absolutely positioned relative to the form container, which could cause layout issues if the form reflows on mobile (horizontal wrapping on narrow screens).
- Panel open/closed state is lost on every HTMX navigation (re-rendered from server) — this is by design but may feel slightly jarring if the user had a panel open and submits the form.

### Approach B: Collapsible checkbox panels + per-section auto-submit via `change` event (HTMX-enhanced)

**Description:** Same collapsible checkbox UI as Approach A, but checkboxes auto-submit the form on `change` — no "Apply filters" button needed for these sections. The sort selector is separated out (per Problem_05) and also auto-submits on change.

**Implementation:**
```javascript
// On checkbox/radio change, trigger form submission
document.addEventListener('change', function (e) {
    if (e.target.matches('[data-filter-submit]')) {
        var form = e.target.closest('form');
        if (form) {
            // HTMX 1.9.12: trigger the form's hx-get via htmx API
            htmx.trigger(form, 'submit');
        }
    }
});
```

Since the form already has `hx-get` and `hx-push-url`, `htmx.trigger(form, 'submit')` initiates the HTMX form submission. For the sort selector (outside the form), it gets its own `hx-get` + `hx-trigger="change"`:
```html
<select name="sort" id="sort"
        hx-get="{{ request.path }}"
        hx-target="#ad-list"
        hx-swap="innerHTML"
        hx-push-url="true"
        hx-trigger="change"
        class="... min-h-[44px]">
```

**Sort separation (Problem_05 Q1/Q2):** The `<select name="sort">` is moved out of `filter_form.html` into a separate component above the ad grid (rendered in `ad_list.html` directly, outside the form). It uses `hx-trigger="change"` to auto-submit on change.

**Pros:**
- Matches OLX's instant-apply UX (filters take effect immediately on checkbox toggle).
- Decouples sorting from the "Apply filters" button per Problem_05.
- Sort selector is always visible and separate from the filter panel.

**Cons:**
- **Race condition on multi-select:** If a user toggles two checkboxes in quick succession, the first HTMX request replaces the form DOM (re-rendering), wiping the second checkbox's `change` event before it fires or before the server response arrives. The second toggle may be lost or appear to uncheck visually. This is a fundamental limitation of the HTMX MPA "replace entire form" architecture.
- **The "Apply filters" button still needed for other controls** (price inputs are text fields, not checkboxes — auto-submit on keypress would be spammy). So the form can't be fully auto-submit; mixed behavior (auto for checkboxes, manual for price) is confusing.
- **Sort separation requires restructuring `ad_list.html`** — moving the sort select out of `filter_form.html` means it must be rendered in `ad_list.html` directly, which changes the test contract: `test_all_htmx_links_have_push_url` asserts **exactly 8** `hx-get=` and **exactly 8** `hx-push-url="true"` in `ad_list.html` source. Adding an HTMX-wired sort selector would make it 9 of each. The test must be updated, but per project rules ("Production code is king"), this requires updating the test to match the legitimate product decision (sort separation is explicitly requested by the PO).
- **More complex JS surface area** — managing auto-submit, debounced rapid toggles, and re-attachment after swaps.

### Approach C: `<details>`/`<summary>` native disclosure + checkboxes (progressive enhancement first)

**Description:** Use HTML5 `<details>` and `<summary>` elements for collapsible panels. The `<details>` element is natively keyboard-accessible, supports `aria-expanded` via the `open` attribute, and works without JavaScript. Checkboxes inside submit via the form normally.

```html
<details class="mb-3" data-filter-details>
    <summary class="flex items-center justify-between px-3 py-2 border rounded-lg bg-white min-h-[44px] cursor-pointer text-sm list-none">
        <span>Listing purpose</span>
        <svg class="w-4 h-4 transition-transform"> ... </svg>
    </summary>
    <div class="mt-1 space-y-1">
        {% for p in resolved_purposes %}
        <label class="flex items-center px-3 py-2 text-sm hover:bg-gray-50 min-h-[44px]">
            <input type="radio" name="listing_purpose" value="{{ p.slug }}" ...>
            <span>{{ p|get_lookup_name:LANGUAGE_CODE }}</span>
        </label>
        {% endfor %}
    </div>
</details>
```

**JS (optional enhancement):** Rotate the chevron SVG on `toggle` event, close other `<details>` (accordion behavior) on `toggle`, outside-click-to-close. Since `<details>` works natively, JS enhancement is minimal (~20 lines).

**Pros:**
- **Best progressive enhancement** — works without JavaScript. `<details>`/`<summary>` is the most accessible disclosure widget natively.
- **Keyboard accessible by default** — Space/Enter toggles, Tab navigation works, screen readers announce expanded/collapsed state automatically (no manual `aria-expanded` management needed).
- **Simple JS** — only needs chevron rotation and accordion behavior.
- **All test contracts preserved** — form structure and hx attributes are unchanged.
- **WCAG 2.5.5 AA** compliance is inherent.

**Cons:**
- `<details>`/`<summary>` is slightly harder to style consistently across browsers (default triangle marker must be suppressed with `list-style: none`).
- The panel opens **inline** (not as an absolutely-positioned floating dropdown), meaning expanding a panel pushes content downward. This matches OLX's **mobile** full-height accordion but differs from the desktop "floating dropdown" pattern.
- **Deviates from codebase convention** — all existing dropdowns (`header_catalog.html`, `language_switcher.html`) use `data-*` + `aria-expanded` + vanilla JS, NOT `<details>`. Introducing `<details>` adds a third pattern (project rule #7: "Follow existing patterns").
- The PO specifically asked for "выпадающий список с чекбоксами" (dropdown with checkboxes) — `<details>` produces an accordion, not a floating dropdown.

---

## 4. Recommendation

### Preferred: **Approach A** (Collapsible checkbox panels + global "Apply filters")

**Rationale (ranked by project constraints):**

1. **Lowest risk to existing tests.** The form's HTMX wiring (`hx-get="{{ request.path }}"`, `hx-push-url="true"`, `hx-target="#ad-list"`) remains untouched. The test contract `test_form_uses_request_path_not_empty` continues to pass. The `ad_list.html` test contract (8 `hx-get=` / 8 `hx-push-url="true"`) is unaffected since the dropdowns live in `filter_form.html`, not `ad_list.html`.

2. **Matches the established codebase pattern.** The `data-*` + `aria-expanded` + vanilla JS + `htmx:afterSwap` re-attachment pattern is already used in `header_catalog.html` (lines 180-546), `language_switcher.html` (lines 52-136), and the mega-submenu. New code follows the exact same structure — no new paradigms (project rule #7).

3. **Respects the HTMX MPA architecture.** The form is re-rendered server-side on every navigation (per the comment in `ad_list.html` lines 7-12). Approach A embraces this: dropdown open/closed state is ephemeral client-side state that correctly resets on server re-render. The **checkbox checked states** are preserved because they come from `current_listing_purpose` / `current_features` context variables — the server re-checks them based on URL params.

4. **Avoids the race condition of auto-submit (Approach B).** In an HTMX MPA where the form DOM is replaced on every response, auto-submit-on-change creates a race: toggling two checkboxes quickly causes the first request's response to replace the DOM before the second toggle registers. The "Apply filters" button sidesteps this: the user makes all selections, then submits once.

5. **Minimal JS surface area.** The JS is a straightforward adaptation of the existing `closeCategories()` pattern — ~45 lines, no new concepts.

6. **Progressive enhancement achievable.** The checkboxes can be rendered visible by default (no JS) and collapsed via JS on load. Without JS, the user sees all checkboxes inline (no toggle needed) and submits normally. With JS, the collapsible UX activates. This is strictly better than the current state (plain `<select>` which is also JS-independent).

7. **Sort separation (Problem_05) is a separate, incremental task.** Decoupling sort from the filter form is logically independent — it can be done before, after, or in parallel with the dropdown conversion.

**Why not B:** The race condition on auto-submit is a real problem in an HTMX MPA where the form is re-rendered on every response. The mixed auto-submit (checkboxes auto, price manual) creates confusing interaction model. The test count change (8→9) is also a concern, though it's a legitimate change.

**Why not C:** While `<details>` is more accessible out-of-the-box, it deviates from the established codebase convention (all existing dropdowns use `data-*` + `aria-expanded` + vanilla JS). The inline accordion expansion also differs from the OLX "floating dropdown" UX the PO referenced. Introducing a third pattern increases maintenance burden (project rule #7).

**Implementation approach for Approach A — event delegation (critical detail):**

Because the form is inside `#ad-list` (the HTMX swap target), any `<script>` block within `filter_form.html` is **destroyed and recreated** on every form submission. The existing `header_catalog.html` solves this by placing its `<script>` in the **header** (outside `#ad-list`) and using `htmx:afterSwap` to re-attach handlers. The filter dropdowns must use the **same strategy**:

- Place the dropdown initialization script in `list.html` (outside `#ad-list`), OR
- Use **event delegation** on `document` — attach listeners once that work for any current or future DOM elements via `e.target.closest('[data-filter-toggle]')`.

The event delegation approach is **strongly preferred** because:
- No `htmx:load` or `htmx:afterSwap` re-attachment needed.
- Single set of listeners on `document` handles all current + future dropdown instances.
- Consistent with `header_catalog.html`'s outside-click handler (`document.addEventListener('click', ...)`, line 415).

### Inline JS implementation (event delegation pattern)

```javascript
(function () {
    'use strict';

    function getPanelFromToggle(toggle) {
        var panelId = toggle.getAttribute('aria-controls');
        return panelId ? document.getElementById(panelId) : null;
    }

    function setExpanded(toggle, expanded) {
        toggle.setAttribute('aria-expanded', expanded ? 'true' : 'false');
        var svg = toggle.querySelector('svg');
        if (svg) {
            if (expanded) svg.classList.add('rotate-180');
            else svg.classList.remove('rotate-180');
        }
    }

    function closePanel(panel) {
        panel.classList.add('hidden');
        var toggle = document.querySelector('[aria-controls="' + panel.id + '"]');
        if (toggle) setExpanded(toggle, false);
    }

    function openPanel(panel) {
        panel.classList.remove('hidden');
        var toggle = document.querySelector('[aria-controls="' + panel.id + '"]');
        if (toggle) setExpanded(toggle, true);
    }

    function closeAllPanels() {
        document.querySelectorAll('[data-filter-panel]').forEach(closePanel);
    }

    // Click on toggle button: toggle panel, close siblings (accordion)
    document.addEventListener('click', function (e) {
        var toggle = e.target.closest('[data-filter-toggle]');
        if (!toggle) return;
        e.stopPropagation();

        var panel = getPanelFromToggle(toggle);
        if (!panel) return;

        var isOpen = !panel.classList.contains('hidden');
        // Close all other panels (accordion behavior)
        document.querySelectorAll('[data-filter-panel]').forEach(function (p) {
            if (p !== panel) closePanel(p);
        });
        if (isOpen) closePanel(panel);
        else openPanel(panel);
    });

    // Click outside the dropdown: close all panels
    document.addEventListener('click', function (e) {
        if (!e.target.closest('[data-filter-dropdown]')) {
            closeAllPanels();
        }
    });

    // Escape key: close all panels
    document.addEventListener('keydown', function (e) {
        if (e.key === 'Escape') closeAllPanels();
    });
})();
```

---

## 5. Sort Selector Separation (Problem_05 Q1/Q2)

The PO requires:
1. Sort decoupled from the "Apply filters" button — applied on **change**.
2. Sort visually separated from the filter block and **always visible**.

**Implementation plan (separate follow-up from dropdown work):**
- Move the `<select name="sort">` out of `filter_form.html` into `ad_list.html`, rendered above the ad grid (outside the form).
- Use HTMX 1.9.12's `hx-trigger` attribute for auto-submit on change:
  ```html
  <div class="mb-4 flex items-center gap-2">
      <label for="sort" class="text-sm text-gray-600">{% trans "Sort by" %}</label>
      <select name="sort" id="sort"
              class="px-3 py-2 border rounded-lg text-sm bg-white min-h-[44px]"
              hx-get="{{ request.path }}"
              hx-target="#ad-list"
              hx-swap="innerHTML"
              hx-push-url="true"
              hx-trigger="change">
          <option value="date_desc" {% if current_sort == 'date_desc' %}selected{% endif %}>{% trans "Newest first" %}</option>
          <option value="date_asc" {% if current_sort == 'date_asc' %}selected{% endif %}>{% trans "Oldest first" %}</option>
          <option value="price_asc" {% if current_sort == 'price_asc' %}selected{% endif %}>{% trans "Price: low to high" %}</option>
          <option value="price_desc" {% if current_sort == 'price_desc' %}selected{% endif %}>{% trans "Price: high to low" %}</option>
      </select>
  </div>
  ```

  `hx-trigger="change"` is fully supported in HTMX 1.9.12 — it triggers an AJAX request when the user changes the select's value, without requiring `onchange="this.form.submit()"` or `htmx.trigger()`.

**Impact on test contracts:**
- `test_all_htmx_links_have_push_url` asserts **exactly 8** `hx-get=` and **exactly 8** `hx-push-url="true"` in `ad_list.html` source. Moving sort into `ad_list.html` with `hx-get` + `hx-push-url="true"` would make it **9 of each**. The test must be updated to `9` — this is a legitimate test update matching a PO-requested product decision (sort separation). Per project rule #2 ("Production code is king: fix or remove the tests"), the test count assertion should be updated.
- The sort `<select>` also needs `hx-include` for hidden state (or relies on `hx-get` + the URL path approach). Since the sort selector is now outside the filter form, it won't include `q`, `category`, `city`, etc. unless we use `hx-include` to pull them from elsewhere, or we construct the URL manually. **This is a significant concern** — moving sort out of the filter form means it loses the hidden inputs that preserve `q`, `category`, `city`, `min_price`, `max_price`. The sort selector's `hx-get` would need to include those params. Options:
  - Add hidden `<input>` elements for each preserved param outside the form (duplicated).
  - Use `hx-include` to reference inputs elsewhere on the page (the search bar, etc.).
  - Render sort as a separate `<form>` with its own hidden inputs.

  Given this complexity, the sort separation is best handled as a **separate phase** after the dropdown conversion is complete and stable.

---

## 6. Best Practices Checklist

| Area | Recommendation | Confidence |
|---|---|---|
| **Touch targets** | `min-h-[44px]` on all toggle buttons and checkbox labels; 44×44px minimum per design system §Principles "Accessibility First" and mobile patterns §3.1 | HIGH |
| **Keyboard navigation** | Toggle buttons are `<button type="button">` (naturally focusable); Tab moves to first checkbox in panel; Escape closes; Space/Enter toggles (native button behavior) | HIGH |
| **ARIA compliance** | `aria-haspopup="listbox"` on toggle; `aria-expanded="false"/"true"` toggled dynamically; `aria-controls="filter-panel-<name>"` linking to panel `id` — matches existing `header_catalog.html` pattern exactly | HIGH |
| **Progressive enhancement** | Without JS, render panels visible by default (remove `hidden` class via a `<noscript>` fallback or a CSS `.no-js` class). Form still submits normally. | HIGH |
| **WCAG 2.5.5 AA** | 44px target size; 3:1 color contrast (use existing Tailwind text colors like `text-gray-700`); focus-visible ring (`focus:ring-2 focus:ring-blue-500`); no color-only indicators (always pair with text/icons) | HIGH |
| **HTMX swap safety** | Use **event delegation** on `document` (via `e.target.closest()`) — survives form re-render inside `#ad-list` without re-attachment | HIGH |
| **One-open-at-a-time (accordion)** | Opening one panel closes others — matches OLX/FB pattern; reduces scroll depth. Implement via closing siblings on toggle open. | MEDIUM |
| **Selected count badge** | Show "(N)" in toggle label when items are selected — provides immediate feedback before applying filters | MEDIUM |
| **Chevron rotation** | Rotate 180° when expanded (`rotate-180` Tailwind class) — matches existing `header_catalog.html` category expand pattern (lines 327-329) | HIGH |
| **Panel positioning** | Use `absolute z-10 mt-1 w-full` for floating dropdown (inside `relative` parent) — matches `header_catalog.html`'s `absolute z-[90]` pattern. On mobile, consider inline expansion (no `absolute`) to avoid viewport overflow issues. | MEDIUM |
| **State preservation** | Checked state comes from server (`current_listing_purpose`, `current_features`) — preserved across HTMX navs because the form is re-rendered server-side from URL params. Dropdown open/closed state is correctly ephemeral (resets on nav). | HIGH |

---

## 7. Summary of Changes Required (Approach A)

1. **`filter_form.html`** — Replace `<select name="listing_purpose">` with a `data-filter-dropdown` toggle + radio button panel (single-select, radio is semantically correct for listing purpose per spec §3.1 filter matrix). Replace inline features checkboxes with a `data-filter-dropdown` toggle + checkbox panel. Add toggle count badges.
2. **Dropdown JS** — Add a delegated-event `<script>` block. **Place it in `list.html`** (outside `#ad-list`) so it survives HTMX swaps, OR use document-level event delegation so no re-attachment is needed. ~45 lines following the existing `header_catalog.html` pattern.
3. **New CSS classes** — `rotate-180`, `focus:ring-2 focus:ring-blue-500`, `absolute z-10`, `shadow-lg`, etc. — must be verified present in `output.css`. The Tailwind v4 pipeline scans `@source` globs in `input.css`; if any class is missing, regenerate via `docker compose exec web tailwindcss -i src/theme/static/theme/css/input.css -o src/theme/static/theme/css/output.css --minify`.
4. **No view-layer changes.** The views already parse `listing_purpose` (single) and `features` (multi) correctly, resolve options via `CategoryLookupResolver`, and pass all context variables. The dropdowns are purely a template + JS change.
5. **Tests** — No existing test should break. The static assertions on `filter_form.html` (`hx-get="{{ request.path }}"`) and `ad_list.html` (8 counts) remain valid. New tests can assert: collapsible panel markup (`data-filter-toggle`, `aria-expanded`, `aria-controls`) is present in template source; checkbox states preserved after HTMX form submit.
6. **Sort separation (Problem_05)** — Deferred to a separate phase. It requires moving the sort `<select>` out of `filter_form.html`, adding `hx-trigger="change"`, and updating the `ad_list.html` test count from 8 to 9. This is a legitimate test update per project rule #2.
