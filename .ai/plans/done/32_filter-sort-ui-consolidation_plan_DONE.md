---
id: 32_filter-sort-ui-consolidation
spec: .ai/problems/07_filter-sort-ui_consolidation_spec.md
domain: implementation-plan
spec_status: APPROVED
priority: High
status: DONE
date: 2026-08-23
stack: Python 3.14 · Django 5.2 LTS · PostgreSQL 18 · HTMX 1.9.12 · vanilla JS · Tailwind CSS v4
---

# Plan 32 — Filter/Sort UI Consolidation — DONE

Transformation of **Spec 07** (`.ai/problems/07_filter-sort-ui_consolidation_spec.md`, APPROVED) into a
dependency-aware implementation DAG.

> **Root cause (confirmed):** `list.html` includes `filter_sort.html` as a **standalone `<form>`
> outside `#ad-list`** (before the `<div id="ad-list">` block). HTMX navigation re-renders only the
> `innerHTML` of `#ad-list` (i.e. `ad_list.html`, which includes `filter_form.html`), so the sort
> form — with its stale hidden inputs — is never refreshed. Changing the sort submits stale filter
> values, silently reverting the buyer's filters.
>
> **Single core fix:** Move the sort `<select>` from the standalone `filter_sort.html` form **into
> `filter_form.html`** (inside `#ad-list`, re-rendered on every HTMX swap). This makes the sort
> control part of the live form — its `selected` state is always fresh (server-rendered from
> `current_sort`), and `onchange="this.form.requestSubmit()"` serializes all live form fields,
> preserving every filter. Same fix resolves Issue #1 (sort placement) and Issue #3 (stale
> interaction). Issue #2 (Features `<details>` stretch) is fixed by replacing `<details>` with
> the floating-checkbox-dropdown pattern already established in `header_catalog.html`.
>
> **Note on FR-11 ("Clear all filters" preserves sort):** The spec's §7 "Files Affected" does not
> list `ad_list.html`, but FR-11 explicitly requires the "Clear all filters" link (in `ad_list.html`,
> lines 59–60) to preserve `current_sort`. The current link only preserves `q`; the sort value is
> dropped, defaulting to `date_desc` on clear. This is a required gap-fill surfaced from the spec's
> own functional requirements.

The spec's three conceptual issues are reorganized below into seven implementation-sequenced tasks
optimized for file-edit isolation, dependency safety, and independent reviewability.

---

## 1. Statement of Scope

Seven tasks (6 implementation + 1 verification), touching:

- `src/backend/templates/ads/partials/filter_form.html` — add sort `<select>` inside the HTMX
  form (after "Apply filters" button, in the same flex row, guarded by `{% if not query %}`);
  replace Features `<details>/<summary>` with a floating checkbox dropdown using the
  `data-filter-*` convention.
- `src/backend/templates/ads/list.html` — remove the `{% include "ads/partials/filter_sort.html" %}`
  (currently outside `#ad-list`); add a `<script>` tag for the new dropdown JS.
- `src/backend/templates/ads/partials/filter_sort.html` — **delete** (replaced by the sort
  `<select>` inside `filter_form.html`).
- `src/backend/templates/ads/partials/ad_list.html` — add `{% if current_sort %}&sort={{ current_sort }}{% endif %}`
  to the "Clear all filters" link's `href` and `hx-get` (FR-11).
- `src/theme/static/theme/js/filter-dropdowns.js` — **new** vanilla-JS IIFE with document-level
  event delegation for dropdown toggle / outside-click-close / Escape-close.

**No view, model, enum, or schema changes.** Both `listings()` and `search()` already pass all
required context (`current_sort`, `current_features`, `resolved_features`, `min_price`,
`max_price`, `query`, `show_filters`, etc.). The four `AdSort` enum values (`date_desc`,
`date_asc`, `price_asc`, `price_desc`) match the existing sort `<option>` values.

**In scope (files):**
- `src/backend/templates/ads/partials/filter_form.html`
- `src/backend/templates/ads/list.html`
- `src/backend/templates/ads/partials/filter_sort.html` (delete)
- `src/backend/templates/ads/partials/ad_list.html`
- `src/theme/static/theme/js/filter-dropdowns.js` (new)

**Out of scope:** price inputs (already visible in current `filter_form.html`), feature tags on
list/detail cards (already implemented via `components/feature_tag.html` from Plan 30),
`listing_purpose` conversion (PO confirmed: keep native `<select>`), any view or model changes.

---

## 2. Execution DAG

```
G1:  [T-01] Add sort <select> to filter_form.html     [T-04] Create filter-dropdowns.js
        │                                                     │
        │                                                     │
        ├──→ [T-02] Remove filter_sort.html include + delete  │
        │           file from list.html                       │
        │                                                     │
        ├──→ [T-03] Replace Features <details>                │     [T-06] Preserve current_sort in
        │           with floating dropdown  (same file)       │          "Clear all filters" link
        │           in filter_form.html                        │          (ad_list.html)
        │                                                     │
        └──→ [T-05] Include filter-dropdowns.js in list.html│
                        (depends on T-02 + T-04)
                                │
                                ▼
                        [T-07] Verification — make test + lint + static assertions
                        (depends on T-01, T-02, T-03, T-04, T-05, T-06)
```

**Critical path:** T-01 → {T-02, T-03} → T-05 → T-07
**Parallel groups:**
- **G1:** `{T-01, T-04, T-06}` — three different files (`filter_form.html`, new JS file, `ad_list.html`), no dependencies between them.
- **G2:** `{T-02, T-03}` — T-02 edits `list.html`, T-03 edits `filter_form.html`; both depend on T-01 (T-02 needs sort inside the form before deleting `filter_sort.html`; T-03 shares `filter_form.html` with T-01 and must sequence to avoid concurrent edits).
- **G3:** `{T-05}` — edits `list.html` (same file as T-02, sequence after), depends on T-04 (JS file must exist).
- **G4:** `{T-07}` — final verification gate, depends on all implementation tasks.

---

## 3. Task Index

| ID | Title | Stage | Priority | Risk | Blocked by |
|----|-------|-------|----------|------|-----------|
| T-01 | Add sort `<select>` to `filter_form.html` (inside HTMX form, after Apply button) | 1 | High | Low | — |
| T-04 | Create `filter-dropdowns.js` (document-level delegation) | 1 | Medium | Low | — |
| T-06 | Preserve `current_sort` in "Clear all filters" link in `ad_list.html` | 1 | Medium | Low | — |
| T-02 | Remove `filter_sort.html` include from `list.html`; delete `filter_sort.html` | 2 | High | Low | T-01 |
| T-03 | Replace Features `<details>` with floating checkbox dropdown in `filter_form.html` | 2 | Medium | Low | T-01 |
| T-05 | Include `filter-dropdowns.js` in `list.html` | 3 | Medium | Low | T-02, T-04 |
| T-07 | Verification: `make test` + lint + static assertions | 4 | High | Low | all |

---

## 4. Current State (verified from source)

| Concern | Current state | Evidence |
|---------|--------------|----------|
| Sort `<select>` location | **Outside `#ad-list`** — standalone form in `filter_sort.html`, included by `list.html` before `<div id="ad-list">` | `list.html` includes `filter_sort.html` as a separate `<form>` with its own `hx-get`; not re-rendered on HTMX swaps → stale hidden inputs |
| Sort hidden inputs | **Stale** — `filter_sort.html` carries hidden inputs for `q`, `category`, `city`, `min_price`, `max_price`, `listing_purpose`, `features`, `page` | `filter_sort.html` lines 24–31 (standalone form outside swap boundary) |
| Sort auto-submit | `onchange="this.form.requestSubmit()"` on standalone form | `filter_sort.html` line 38 — already works with HTMX form interception |
| Sort guard | `{% if not query %}` | `filter_sort.html` line 13; `listings()` view does NOT set `query` (undefined → falsy → sort shows); `search()` sets `"query"` (line 209) |
| Sort option values | `date_desc`, `date_asc`, `price_asc`, `price_desc` | `filter_sort.html` lines 39–42; match `AdSort` enum (`core/enums.py:14-17`) |
| Sort in `filter_form.html` | **Absent** — sort is only in the standalone `filter_sort.html` | `filter_form.html` has no `<select name="sort"` element |
| Features rendering | `<details class="w-full">/<summary>` — inline block-level expansion stretches layout | `filter_form.html` lines 45–65 |
| Features checked state | Server-rendered via `{% if f.slug in current_features %}checked{% endif %}` | `filter_form.html` line 58 |
| Features count display | `({{ current_features|length }} {% trans "selected" %})` inside `<summary>` | `filter_form.html` line 51 |
| `current_sort` in context | Yes — passed by both views | `listings.py` line 486 (`"current_sort": sort`); `search.py` line 213 (`"current_sort": current_sort`) |
| `query` in context | `search()`: `"query": query` (line 209). `listings()`: not set (undefined → falsy) | Verified via grep |
| "Clear all filters" sort preservation | **NOT preserved** — link only includes `?page=1&q=...` | `ad_list.html` lines 59–60 (no `&sort=`) |
| Chip removal sort preservation | **Preserved** — includes `{% if current_sort %}&sort={{ current_sort }}{% endif %}` | `ad_list.html` lines 42, 53 |
| Pagination sort preservation | **Preserved** — includes `{% if current_sort %}&sort={{ current_sort }}{% endif %}` | `ad_list.html` lines 131, 135, 145, 153, 157 |
| `ad_list.html` `hx-get=` count | Exactly **8** `hx-get=` and **8** `hx-push-url="true"` (raw file text) | `test_catalog_filters.py:314-319` (`test_all_htmx_links_have_push_url`) — chip removal (2), clear-all (1), pagination first/prev/page/next/last (5) |
| `filter_form.html` `hx-get` | `hx-get="{{ request.path }}"` on the `<form>` — path-only, no empty `hx-get=""` | `test_catalog_filters.py:307-312` (`test_form_uses_request_path_not_empty`) |
| `feature_tag.html` | Already exists — used on list cards (`ad_list.html:103`) | `components/feature_tag.html` |
| JS dropdown pattern | `header_catalog.html` uses inline `<script>` with per-element `addEventListener` (outside swap boundary) | `header_catalog.html` lines 180–545 |
| HTMX swap boundary | `#ad-list` innerHTML — includes `ad_list.html` → `filter_form.html` (line 14, inside `{% if show_filters %}`) | `list.html` lines 35–37; `ad_list.html` line 14 |
| Static JS directory | `src/theme/static/theme/` exists (has `css/` only); `theme` app in `INSTALLED_APPS` | `base.py` line 95; `STATICFILES_DIRS` uses `AppDirectoriesFinder` for theme |
| `list.html` script loads | htmx CDN in `<head>` (line 16); `header_catalog.html` inline script in body | `list.html` lines 2, 12, 16, 20 |
| Tests referencing sort markup | **None** — `test_listings_sort.py` asserts on URL param + ad-title positions only | `test_listings_sort.py:56-109` |
| Tests referencing `filter_sort.html` | **None** — no test reads or asserts on `filter_sort.html` | grep returns zero |

---

## 5. Risk & Rollout Notes

- **Stale-hidden-inputs bug (Issue #3) is the core risk and its own fix.** Moving the sort `<select>`
  into `filter_form.html` eliminates the standalone form entirely. The `onchange="this.form.requestSubmit()"`
  handler now submits the **main filter form** (not a separate form), so `requestSubmit()` serializes
  all live DOM fields — checkboxes, selects, inputs — with no stale hidden inputs. The server re-renders
  `filter_form.html` on every swap with fresh `current_sort` / `current_features` state. No client-side
  state synchronization needed.
- **`filter_form.html` edit contention (T-01 → T-03).** Both tasks edit the same partial. T-01 inserts
  after the "Apply filters" button block; T-03 replaces the `<details>` block (an earlier region). Sequencing
  T-01 before T-03 prevents merge conflicts and ensures the implementor sees the final file layout.
- **`list.html` edit contention (T-02 → T-05).** T-02 removes the `filter_sort.html` include (before
  `<div id="ad-list">`); T-05 adds a `<script>` tag (before `</body>`). Different regions, but same file —
  sequenced for safe concurrent editing.
- **Test contract is preserved (verified).** The new sort `<select>` uses `onchange` (not `hx-get`), so
  `ad_list.html`'s `hx-get=` count stays at 8 (the sort lives in `filter_form.html`, a separate file
  included via `{% include %}` whose raw text is not counted). The `filter_form.html` `hx-get` is
  unchanged. Modifying the "Clear all filters" link's URL (T-06) adds `&sort=...` to an existing `hx-get`
  attribute — no new `hx-get=` is added, so the count stays at 8.
- **HTMX `requestSubmit()` compatibility.** `this.form.requestSubmit()` triggers a native submit event;
  HTMX 1.9.12 intercepts the form's `hx-get` and serializes all form fields. This pattern is already
  proven in the current `filter_sort.html` (line 38). Moving it into the main filter form preserves
  the same behavior — now with live (not stale) fields.
- **HTMX re-render survival (NFR-2).** The Features dropdown JS uses **document-level event
  delegation** (`e.target.closest('[data-filter-toggle]')`) because `filter_form.html` is destroyed and
  recreated on every `innerHTML` swap of `#ad-list`. Per-element `addEventListener` would be lost.
  The delegate listener lives on `document` (not on the form element) and survives re-renders.
  The inline `onchange="this.form.requestSubmit()"` on the sort `<select>` is an HTML attribute (not a JS
  listener), so it is re-parsed by the browser on every `innerHTML` insert — no JS listener to lose.
- **JS file placement (option C, spec-confirmed).** A new static JS file is cleaner than an inline
  script in `filter_form.html` (option A, rejected — would need `htmx:afterSwap` re-attachment) or
  `ad_list.html` (option B — works but mixes concerns). The `theme` app is in `INSTALLED_APPS`, so
  `src/theme/static/theme/js/filter-dropdowns.js` is discoverable via `AppDirectoriesFinder` and
  referenceable as `{% static 'theme/js/filter-dropdowns.js' %}` (same convention as `output.css`).
- **No rollback needed.** All changes are additive or corrective (template edits + one file deletion
  of an untracked file). If reverted, the sort simply returns to the standalone `filter_sort.html` form.

---

## 6. Overall Acceptance Criteria

1. **AC-1** — On a category page (no search query), the sort `<select>` is visible to the right of the
   "Apply filters" button, inside the filter form block (within `#ad-list`).
2. **AC-2** — On search results (`q` present), the sort `<select>` is **not** rendered (`{% if not query %}`).
3. **AC-3** — With features checked, changing the sort dropdown preserves all checked features; the URL
   retains `features=` params; results reorder.
4. **AC-4** — With a sort selected, changing a feature checkbox and clicking "Apply filters" preserves
   the sort value in the URL; the re-rendered sort `<select>` shows the correct `selected` option.
5. **AC-5** — Expanding the Features dropdown renders a floating panel (overlay, not inline stretch);
   checkboxes are visible.
6. **AC-6** — Clicking outside the Features dropdown panel closes it.
7. **AC-7** — Pressing Escape while the Features dropdown is open closes it.
8. **AC-8** — With features selected, the Features trigger button shows the count `(N)`.
9. **AC-9** — `make test` passes; `test_catalog_filters.py` and `test_listings_sort.py` all green;
   `ad_list.html` source still has exactly 8 `hx-get=` and 8 `hx-push-url="true"`.
10. **AC-10** — Clicking "Clear all filters" preserves the current `sort` value in the resulting URL
    (FR-11).

---

## 7. Task Specifications

---

## T-01 — Add sort `<select>` to `filter_form.html` (inside HTMX form)

| Field | Value |
|-------|-------|
| **ID** | T-01 |
| **Title** | Add sort `<select>` to `filter_form.html` inside the HTMX swap boundary |
| **Type** | Template edit |
| **Priority** | High |
| **Risk** | Low |
| **Blocked by** | — |
| **source_reference** | Spec §D-1 (move sort into `filter_form.html`); §FR-1, FR-2, FR-3, FR-4 |

**description**

The sort `<select>` currently lives in the standalone `filter_sort.html` form, which is included by
`list.html` *outside* `#ad-list` and therefore never re-rendered during HTMX swaps — causing stale
hidden-input state (Issue #3) and separate-form layout (Issue #1). Move the sort control into
`filter_form.html` as a field within the existing `<form>` (which has `hx-get="{{ request.path }}"`,
`hx-target="#ad-list"`, `hx-swap="innerHTML"`, `hx-push-url="true"`). Because `filter_form.html`
is included inside `ad_list.html` (line 14, inside `{% if show_filters %}`), it is re-rendered on
every HTMX swap, making all form controls live — no hidden inputs needed.

Insert the sort `<select>` **after the "Apply filters" button block** and **before the closing
`</div>`** of the flex row (`<div class="flex flex-wrap gap-4 items-end">`), so it renders visually
to the right of the button in the same horizontal row. Guard with `{% if not query %}` (sort is
irrelevant during FTS relevance search — see spec D-2/F-2). Use `onchange="this.form.requestSubmit()"`
for auto-submit (PO-confirmed — see D-3/Q-3). Use `{% trans %}` for all labels. Option values match
`AdSort` StrEnum: `date_desc`, `date_asc`, `price_asc`, `price_desc`. Server-side `selected` state
via `{% if current_sort == 'X' or not current_sort %}selected{% endif %}` (same pattern already used
for `listing_purpose` native `<select>` in this same file).

**goals**
- Sort control is inside the HTMX swap boundary (`#ad-list` → `ad_list.html` → `filter_form.html`).
- Sort auto-submits the entire live form on change, preserving all filter state.
- Sort hidden during search (`{% if not query %}`).
- Sort option values match `AdSort` enum; labels use `{% trans %}`.

**files**
- path: `src/backend/templates/ads/partials/filter_form.html`

**semantic_anchors**
- Target region: the `<div class="flex flex-wrap gap-4 items-end">` flex row
- Insert after: the `{% if resolved_purposes or resolved_features %} ... </div>` block (Apply filters button)
- Insert before: the closing `</div>` of the flex row, followed by `</form>`

**changes**
- action: insert_in_body — add a `<div class="flex items-end gap-2">` containing the sort `<select>`
  (with `{% if not query %}` guard, `<label>`, 4 `<option>` elements keyed to `AdSort` values,
  `onchange="this.form.requestSubmit()"`) after the Apply filters button block and before the flex
  row's closing `</div>`.

**acceptance_criteria**
- `filter_form.html` contains a `<select name="sort" id="sort"` with `onchange="this.form.requestSubmit()"`,
  guarded by `{% if not query %}`.
- Sort options are `date_desc`, `date_asc`, `price_asc`, `price_desc` with `{% trans %}` labels.
- `current_sort` from context drives the `selected` attribute server-side.
- No new `hx-get=` is added to `filter_form.html` (sort uses `onchange`, not `hx-get`) — the form's
  existing `hx-get="{{ request.path }}"` is reused.
- The sort `<select>` renders inside the same flex row as the "Apply filters" button, after it.

---

## T-04 — Create `filter-dropdowns.js` (document-level event delegation)

| Field | Value |
|-------|-------|
| **ID** | T-04 |
| **Title** | Create `filter-dropdowns.js` with document-level dropdown toggle/close JS |
| **Type** | Template asset (new file) |
| **Priority** | Medium |
| **Risk** | Low |
| **Blocked by** | — |
| **source_reference** | Spec §D-3 (dropdown structure), §D-4 (JS behavior spec), §NFR-1, NFR-2 |

**description**

Create a new vanilla-JS module at `src/theme/static/theme/js/filter-dropdowns.js`. The `theme` app is
in `INSTALLED_APPS` (base.py line 95), and its static dir `src/theme/static/` is discovered by
`AppDirectoriesFinder` — same convention as `output.css` (referenced as `{% static 'theme/css/output.css' %}`).

The module is an IIFE (`(function () { 'use strict'; ... })()` — mirroring `header_catalog.html`
convention) that uses **document-level event delegation** per NFR-2:
`document.addEventListener('click', fn)` with `e.target.closest('[data-filter-toggle]')`. This is
required because `filter_form.html` is destroyed and recreated on every HTMX `innerHTML` swap of
`#ad-list` — per-element listeners would be lost. Document-level delegation survives re-renders because
the listener lives on `document`, not on the form element.

Behavior:
- **Click on `[data-filter-toggle]`:** toggle `aria-expanded` (`true`/`false`) on the button and toggle
  the `hidden` class on the sibling `[data-filter-panel]` within the same `[data-filter-trigger]` wrapper.
  Rotate the caret SVG 180° (`rotate-180` class) when open. Close any other open panel first.
- **Click outside `[data-filter-trigger]`:** close all open panels (reset `aria-expanded` to `false`,
  add `hidden`, remove `rotate-180`).
- **Press Escape:** close all open panels.

This mirrors the `closeCategories()` / `closeCity()` pattern in `header_catalog.html:398-476` but
generalized via `e.target.closest()` for the generic `data-filter-*` selectors, so it works for any
dropdown using this convention. No third-party libraries. The IIFE runs once on `DOMContentLoaded`;
no `htmx:afterSwap` re-initialization needed (delegation handles re-injected elements automatically).

**goals**
- Features dropdown toggles open/closed via trigger button click.
- Clicking outside the dropdown closes it.
- Pressing Escape closes any open dropdown.
- Caret SVG rotates 180° when open.
- Survives HTMX re-renders via document-level delegation (no per-element listeners).
- No third-party dependencies (vanilla JS only).

**files**
- path: `src/theme/static/theme/js/filter-dropdowns.js` (new)

**semantic_anchors**
- Target: new file — IIFE module with `document.addEventListener('click', ...)` and
  `document.addEventListener('keydown', ...)` using `e.target.closest('[data-filter-toggle]')`

**changes**
- action: add_file — `filter-dropdowns.js` containing the IIFE with click delegation (toggle),
  outside-click close, and Escape close, targeting `[data-filter-toggle]`, `[data-filter-panel]`,
  and `[data-filter-trigger]` selectors.

**acceptance_criteria**
- File `src/theme/static/theme/js/filter-dropdowns.js` exists.
- Uses `document.addEventListener` (not per-element `addEventListener`).
- Clicking `[data-filter-toggle]` toggles `aria-expanded` + `hidden` class on sibling `[data-filter-panel]`.
- Outside-click and Escape both close open panels.
- Caret SVG gets `rotate-180` class when open, removed when closed.
- No `addEventListener` calls on elements queried at init time (all delegation via `document`).

---

## T-06 — Preserve `current_sort` in "Clear all filters" link

| Field | Value |
|-------|-------|
| **ID** | T-06 |
| **Title** | Add `current_sort` to "Clear all filters" link URL in `ad_list.html` |
| **Type** | Template edit |
| **Priority** | Medium |
| **Risk** | Low |
| **Blocked by** | — |
| **source_reference** | Spec §FR-11 ("Clear all filters" must preserve sort); §6.3 (`test_clear_all_filters_has_push_url` — no test impact) |

**description**

The "Clear all filters" link in `ad_list.html` (lines 59–60) currently constructs a URL with only
`?page=1&q={{ query }}` — it does **not** preserve `current_sort`. When the buyer clicks "Clear all
filters", the server receives no `sort` param and defaults to `date_desc`, silently resetting the
sort order. This violates FR-11.

All sibling links in `ad_list.html` (chip removal at lines 42/53, pagination at lines 131–157) already
include `{% if current_sort %}&sort={{ current_sort }}{% endif %}` in both their `href` and `hx-get`
attributes. This task adds the same `&sort={{ current_sort }}` preservation to the "Clear all filters"
link's `href` and `hx-get` attributes, making it consistent.

The `current_sort` context variable is already passed by both `listings()` and `search()` views
(listings.py line 486, search.py line 213). No view changes required.

**Test impact:** `test_clear_all_filters_has_push_url` (test_catalog_filters.py:321-326) only
asserts `hx-get="?page=1` is a substring — adding `&sort=...` after `page=1` does not break this.
`test_all_htmx_links_have_push_url` counts 8 `hx-get=` — modifying an existing link's `hx-get` value
(not adding a new `hx-get` attribute) keeps the count at 8.

**goals**
- "Clear all filters" link preserves `current_sort` in both `href` and `hx-get`.
- Test `test_clear_all_filters_has_push_url` still passes.
- `hx-get=` count in `ad_list.html` remains 8.

**files**
- path: `src/backend/templates/ads/partials/ad_list.html`

**semantic_anchors**
- Target: the "Clear all filters" `<a>` element (the one containing `{% trans "Clear all filters" %}`)
- The `href` and `hx-get` attributes of that specific `<a>` element

**changes**
- action: replace_in_body — in the "Clear all filters" `<a>` element, append
  `{% if current_sort %}&sort={{ current_sort }}{% endif %}` to both the `href` and `hx-get`
  attribute values, after the existing `{% if query %}&q={{ query|urlencode }}{% endif %}`.

**acceptance_criteria**
- The "Clear all filters" `<a>` in `ad_list.html` includes `{% if current_sort %}&sort={{ current_sort }}{% endif %}`
  in both `href` and `hx-get`.
- `test_clear_all_filters_has_push_url` passes (still finds `hx-get="?page=1` substring).
- `test_all_htmx_links_have_push_url` passes (count still 8).

---

## T-02 — Remove `filter_sort.html` include from `list.html`; delete `filter_sort.html`

| Field | Value |
|-------|-------|
| **ID** | T-02 |
| **Title** | Remove `filter_sort.html` include from `list.html`; delete the file |
| **Type** | Template edit + file deletion |
| **Priority** | High |
| **Risk** | Low |
| **Blocked by** | T-01 |
| **source_reference** | Spec §D-6 (delete `filter_sort.html`), §FR-1 |

**description**

Remove the `{% include "ads/partials/filter_sort.html" %}` line from `list.html` (currently inserted
before `<div id="ad-list">`, at 4-space indentation inside `<main>`). This include places the sort
form *outside* the HTMX swap boundary — the root cause of the stale-hidden-inputs bug. After T-01
moves the sort `<select>` into `filter_form.html` (inside `#ad-list`), the standalone form is redundant
and stale-prone. Delete `src/backend/templates/ads/partials/filter_sort.html` entirely.

**T-02 depends on T-01:** The sort `<select>` must exist inside `filter_form.html` before the standalone
`filter_sort.html` form is removed, ensuring no gap where the sort control is absent.

**goals**
- No sort control renders outside `#ad-list`.
- No stale hidden inputs remain.
- `filter_sort.html` file no longer exists.

**files**
- path: `src/backend/templates/ads/list.html`
  - action: delete_in_body — remove `{% include "ads/partials/filter_sort.html" %}` (currently
    between the save-search modal block and `<div id="ad-list">`).
- path: `src/backend/templates/ads/partials/filter_sort.html`
  - action: delete_file — entire file.

**acceptance_criteria**
- `list.html` contains no reference to `filter_sort.html` (grep returns zero).
- `filter_sort.html` no longer exists on disk.
- `list.html` renders `<div id="ad-list">` directly after the `#main` content opening (no sort form
  before it).

---

## T-03 — Replace Features `<details>` with floating checkbox dropdown in `filter_form.html`

| Field | Value |
|-------|-------|
| **ID** | T-03 |
| **Title** | Replace Features `<details>/<summary>` with floating checkbox dropdown |
| **Type** | Template edit |
| **Priority** | Medium |
| **Risk** | Low |
| **Blocked by** | T-01 |
| **source_reference** | Spec §D-3 (dropdown structure), §FR-5, FR-6, FR-7, FR-8, §NFR-1 |

**description**

Replace the `<details class="w-full"> ... </details>` block (inside `{% if resolved_features %}`
in `filter_form.html`) with a floating dropdown using the `data-filter-*` convention established in
`header_catalog.html`. The `<details>` element is block-level — its inline expansion pushes all sibling
form elements downward (the "stretches everything" complaint). The replacement uses `position: absolute`
(`absolute` + `z-[90]` + `shadow-lg`) so the panel floats as an overlay and does not displace siblings.

Structure to replace the existing `<details>` block:

```django
<div data-filter-trigger class="relative">
    <button type="button"
            data-filter-toggle
            aria-haspopup="listbox"
            aria-expanded="false"
            class="flex items-center justify-between px-3 py-2 border border-gray-200 rounded-lg text-sm font-medium text-gray-700 bg-white hover:bg-gray-50 min-h-[44px]">
        <span>{% trans "Features" %}</span>
        {% if current_features %}
            <span class="text-xs text-gray-500">({{ current_features|length }})</span>
        {% endif %}
        <svg class="w-4 h-4 transition-transform duration-150" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7"></path>
        </svg>
    </button>
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
```

Key points:
- The `name="features"` and `value="{{ f.slug }}"` attributes on checkboxes are unchanged — server-side
  form submission behavior is identical.
- The `checked` state is still server-rendered via `{% if f.slug in current_features %}checked{% endif %}`
  — no client-side state.
- The count display `({{ current_features|length }})` reuses `current_features` from context (same
  variable the current `<details>` `<summary>` uses at line 51). Per the OLX reference, simplified to
  just the count (no "selected" text).
- All new translatable strings use `{% trans %}`. (`"Features"` is already in the `.po` files per
  spec §10.)
- Tailwind classes (`absolute`, `z-[90]`, `shadow-lg`, `hidden`, `rotate-180`, `min-h-[44px]`,
  `focus:ring-blue-500`) are all present in the committed `output.css` (confirmed via existing
  `header_catalog.html` usage).
- The caret SVG path (`d="M19 9l-7 7-7-7"`) matches the chevron-down used in `header_catalog.html`
  (lines 50, 82, 101, 168).

**T-03 depends on T-01** (same file — sequence after the sort insertion to avoid concurrent edits in
`filter_form.html`).

**goals**
- Features renders as a floating dropdown (overlay, not inline stretch).
- Checkboxes are independently toggleable with server-rendered `checked` state.
- Form submission of `name="features"` is unchanged.
- Dropdown closes on outside-click and Escape (via T-04 JS).
- Count `(N)` shown on trigger button when features selected.

**files**
- path: `src/backend/templates/ads/partials/filter_form.html`

**semantic_anchors**
- Target: the `<details class="w-full">` element and its contents (the `<summary>` and inner `<div>`),
  within the `{% if resolved_features %}` block
- The surrounding `<div>` wrapper is preserved; only the `<details>` element is replaced with the
  `data-filter-trigger` / `data-filter-toggle` / `data-filter-panel` structure

**changes**
- action: replace_in_body — replace the `<details class="w-full">` element (and its `<summary>` and
  inner `<div>`) with the floating dropdown structure above, preserving the
  `{% for f in resolved_features %}` loop and checkbox attributes.

**acceptance_criteria**
- `filter_form.html` contains no `<details>` or `<summary>` element.
- `filter_form.html` contains `data-filter-trigger`, `data-filter-toggle`, `data-filter-panel` attributes.
- All feature checkboxes retain `name="features"`, `value="{{ f.slug }}"`, and
  `{% if f.slug in current_features %}checked{% endif %}`.
- The dropdown panel has `absolute z-[90] ... hidden` class (floating, initially hidden).
- No sibling form elements (price inputs, Apply button, sort select) are pushed/stretched by the panel.

---

## T-05 — Include `filter-dropdowns.js` in `list.html`

| Field | Value |
|-------|-------|
| **ID** | T-05 |
| **Title** | Add `<script>` tag for `filter-dropdowns.js` in `list.html` |
| **Type** | Template edit |
| **Priority** | Medium |
| **Risk** | Low |
| **Blocked by** | T-02, T-04 |
| **source_reference** | Spec §7.1 (option C: separate static JS file included in `list.html`) |

**description**

Add a `<script src="{% static 'theme/js/filter-dropdowns.js' %}"></script>` tag to `list.html`, placed
at the end of `<body>` (after `{% include "components/footer.html" %}`, before `</body>`). This is the
full-page template rendered by both `listings()` and `search()` for non-HTMX requests. On initial page
load, the script's IIFE attaches document-level listeners that survive all subsequent HTMX swaps of
`#ad-list` (the form is re-rendered inside the swap boundary, but `document`-level delegation catches
the new `data-filter-*` elements automatically).

`list.html` already has `{% load static %}` (line 2), so the `{% static %}` tag resolves correctly.
The `theme` app's `AppDirectoriesFinder` discovers `src/theme/static/theme/js/` (same as the existing
`{% static 'theme/css/output.css' %}` reference on line 12). The IIFE uses `DOMContentLoaded` so it
can be placed anywhere in the document.

**T-05 depends on T-02** (both edit `list.html` — T-02 removes the include, T-05 adds the script tag;
sequence for safe concurrent editing) and **T-04** (the referenced JS file must exist before the
`<script>` tag is valid).

**goals**
- `filter-dropdowns.js` is loaded once on full page load.
- Document-level delegation listeners are active.
- No duplicate script tags or per-element listener loss on HTMX re-renders.

**files**
- path: `src/backend/templates/ads/list.html`

**semantic_anchors**
- Insert after: `{% include "components/footer.html" %}` (the last include before `</body>`)
- Insert before: `</body>` (the closing body tag of `list.html`)

**changes**
- action: insert_in_body — add `<script src="{% static 'theme/js/filter-dropdowns.js' %}"></script>`
  after the footer include and before `</body>`.

**acceptance_criteria**
- `list.html` contains `<script src="{% static 'theme/js/filter-dropdowns.js' %}"></script>`.
- The script tag is placed at the end of `<body>` (after footer, before `</body>`).
- `{% load static %}` is present in `list.html` (already loaded at line 2).

---

## T-07 — Verification

| Field | Value |
|-------|-------|
| **ID** | T-07 |
| **Title** | Verify: `make test` + lint + static assertions |
| **Type** | Verification |
| **Priority** | High |
| **Risk** | Low |
| **Blocked by** | T-01, T-02, T-03, T-04, T-05, T-06 |
| **source_reference** | Spec §6 (Test Contract Impact), §9 (Acceptance Criteria), §FR-11 |

**description**

Final verification gate for all implementation tasks. Run the fast test suite (which includes both
affected test modules) plus lint and static assertions that guard the HTMX contract and the new
dropdown/behavior.

**verification_steps**
- test: `make test` — fast gate including `test_catalog_filters.py` and `test_listings_sort.py`
  (auto-starts the Docker test DB on port 5433).
- lint: `uv run ruff check src/backend` (ruff is Python-only; the JS file is not linted by ruff —
  verify JS syntax manually or via `node --check` if available in the environment).
- static_assertions:
  1. `ad_list.html` raw text still has exactly 8 `hx-get=` and 8 `hx-push-url="true"`
     (asserted by `test_catalog_filters.py::test_all_htmx_links_have_push_url`).
  2. `filter_form.html` contains `hx-get="{{ request.path }}"` and NOT `hx-get=""`
     (asserted by `test_catalog_filters.py::test_form_uses_request_path_not_empty`).
  3. `list.html` contains no reference to `filter_sort.html` (grep returns zero).
  4. `filter_sort.html` no longer exists on disk.
  5. `filter_form.html` contains `<select name="sort"` with `onchange="this.form.requestSubmit()"`,
     guarded by `{% if not query %}`.
  6. `filter_form.html` contains no `<details>` or `<summary>` element.
  7. `filter_form.html` contains `data-filter-toggle` and `data-filter-panel`.
  8. `ad_list.html` "Clear all filters" link includes `&sort={{ current_sort }}` (FR-11).
  9. `list.html` contains `<script src="{% static 'theme/js/filter-dropdowns.js' %}">`.
  10. `src/theme/static/theme/js/filter-dropdowns.js` exists and uses
      `document.addEventListener` (not per-element listeners).

**pass_criteria**
- `make test` passes (0 failures in `test_catalog_filters.py` and `test_listings_sort.py`).
- All 10 static assertions above hold.
- `uv run ruff check src/backend` is clean (no new issues).

**files**
- path: (no code files — verification step)

---

## 8. Execution DAG (summary)

```
        G1 (parallel, different files)              G2 (parallel, different files)
       ┌────────────┐ ┌────────────┐ ┌──────────┐    ┌──────────────┐ ┌──────────────┐
       │  T-01      │ │  T-04      │ │  T-06    │    │  T-02        │ │  T-03        │
       │ sort into  │ │ create JS  │ │ clear-  │    │ remove incl  │ │ features     │
       │ form       │ │ file       │ │ all sort│    │ + delete file│ │ dropdown     │
       └────┬───────┘ └──────┬─────┘ └────┬─────┘    └──────┬───────┘ └──────┬───────┘
            │              │              │                 │                  │
            │              └──────────────┼─────────────────┘                  │
            │                             │ (depend on T-01)                    │
            │              ┌──────────────┴─────────────────┐                 │
            └──────────────┤  T-05 (include JS in list.html) ├─────────────────┘
                           │        (depends on T-02, T-04) │
                           └──────────────┬─────────────────┘
                                          │
                                          ▼
                              G4: T-07 (verification — make test + lint)
                              (depends on T-01, T-02, T-03, T-04, T-05, T-06)
```

**G1:** `{T-01, T-04, T-06}` — parallel (different files: `filter_form.html`, new JS file, `ad_list.html`)
**G2:** `{T-02, T-03}` — parallel (different files: `list.html`, `filter_form.html`; both depend on T-01)
**G3:** `{T-05}` — depends on T-02 (same file `list.html`) and T-04 (JS file must exist)
**G4:** `{T-07}` — depends on all implementation tasks
