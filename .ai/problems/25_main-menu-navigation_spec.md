# Spec_025 — Main Menu Navigation Expand Button Redesign

**Decision source:** `.ai/problems/Decision_024.md`
**Research:** `.ai/research/25_main-menu-navigation_research.md`
**Spec state:** APPROVED — PO decisions resolved
**Date:** 2026-08-21
**Stack:** Django 5.2.16 LTS · Python 3.14 · HTMX 1.9.12 · django-mptt · Tailwind CSS · PostgreSQL 18

**Predecessor:** Spec_022 (`22_catalog-menu-breadcrumb-fixes_spec.md`) — Spec_022 restored expand-button rendering and breadcrumb path rendering. The accordion JS (`closeBranch`/`collapseSiblings`) is correct and in place. This spec addresses the **remaining UX gaps**: un-intuitive right-chevron icon, sub-44px touch target, no visual state cue on expand, missing `aria-controls`, and inconsistency between `mega_submenu.html` and `header_catalog.html` button classes.

---

## 1. Business Goal

The "All Categories" dropdown menu (Avito-style) renders and functions (expand buttons appear, submenus load lazily via `/categories/<slug>/submenu/`, breadcrumbs show the category path). However, the expand buttons have two UX defects:

1. **Wrong icon signifier** — a right-pointing chevron `▶` (`d="M9 5l7 7-7 7"`) is used for an in-place expand/collapse action. Per NN/g empirical A/B research, the right-arrow is the worst-performing icon for in-place accordions — it is not statistically distinguishable from a no-icon control and should not be used for accordion disclosure.
2. **Sub-44px touch target** — the expand button is 32×32px (`px-2 py-2` + `w-4 h-4` SVG), violating the project's own `ui-patterns.md` §Touch Target Guidelines (44px minimum), WCAG 2.5.5 Target Size (Enhanced), and Apple HIG (44pt). Additionally, the chevron never rotates or changes on expand, so there is **no visual state cue** — openness is signalled only by `aria-expanded` and the submenu appearing, which is insufficient for users who rely on visual feedback.

The original Problem_03 requested replacing `>` with `+`/`−`. Research found that while plus/minus is acceptable, the downward-facing **caret that rotates** is the recommended signifier (NN/g: "the safest icon choice for accordions that expand in place"). The PO decision (Decision_024) is to use the **rotating downward caret** instead of plus/minus, with the reason documented.

---

## 2. Scope

### In Scope

1. Replace the right-chevron `▶` SVG path with a downward-facing caret `▼` in all three template locations.
2. Add a 180° CSS rotation transform on the caret when the branch is expanded (`aria-expanded="true"`).
3. Enlarge the expand button hit area to ≥44×44px while keeping the 16px icon centered.
4. Add `aria-controls` to the expand button, linking it to the submenu container's `id`.
5. Add the matching `id` to the submenu container div (currently has no `id`).
6. Fix the `mega_submenu.html` expand button class inconsistency — it currently lacks `min-h-[44px]` present in `header_catalog.html`.
7. Make the pattern consistent across desktop dropdown, mobile off-canvas panel, and lazy-loaded `mega_submenu.html`.

### Out of Scope

- **Changing to `+`/− icon** — rejected (research-backed; see §8 Decision Rationale). The PO's original suggestion is documented but not implemented.
- **Whole-header disclosure (Approach B)** — merging the category label `<a>` and expand button into a single disclosure toggle. This removes the split-action anti-pattern but changes the row structure that tests assert on. Documented as a follow-up spec (Spec_026-B).
- **WAI-ARIA `role="tree"` / `treeitem` / `group`** — full tree semantics require a larger JS rewrite and test updates. Documented as Approach C follow-up.
- **Keyboard arrow navigation** — the existing Escape / click-outside close is sufficient for this ticket; full arrow-key tree navigation is deferred to Approach B/C.
- No DB schema changes, no new endpoints, no new models, no migrations.

---

## 3. Facts

### 3.1 Three Expand-Button Locations

| # | Context | File | Button Line | SVG Path | Container Line | Container Has `id`? | Button Has `min-h-[44px]`? |
|---|---|---|---|---|---|---|---|
| 1 | Desktop "All Categories" dropdown (level 1) | `header_catalog.html` | line 96–102 | `d="M9 5l7 7-7 7"` (▶) | line 105 | No | Yes |
| 2 | Mobile off-canvas panel (level 1) | `header_catalog.html` | line 162–168 | `d="M9 5l7 7-7 7"` (▶) | line 171 | No | Yes |
| 3 | Lazy-loaded submenu partial (level 2+) | `mega_submenu.html` | line 17–25 | `d="M9 5l7 7-7 7"` (▶) | line 28 | No | **No** (inconsistency) |

### 3.2 Current Button Markup (all three locations are structurally identical)

`header_catalog.html` line 95–105 (desktop):
```html
{% if cat.get_children.exists %}
<button type="button" data-category-expand="{{ cat.slug }}"
        class="px-2 py-2 text-gray-400 hover:text-blue-600 min-h-[44px]"
        aria-expanded="false" aria-label="{% trans "Expand" %} {{ cat.get_name }}">
    <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7"></path>
    </svg>
</button>
{% endif %}
...
<div class="hidden ml-4" data-category-submenu="{{ cat.slug }}"></div>
```

### 3.3 Current Hit-Area Calculation

Button classes `px-2 py-2` = 0.5rem horizontal padding (8px × 2 = 16px) + `w-4` SVG (16px) = **32px wide**. Height: 0.5rem vertical padding (8px × 2) + `h-4` SVG (16px) = **32px tall**. This passes WCAG 2.5.8 (24px) but fails the project's 44px standard and Apple HIG.

### 3.4 Current State Handling

The JS (`header_catalog.html` lines 313–377) already correctly toggles `aria-expanded="true/false"` on the button and adds/removes `hidden` on the submenu container via `loadSubmenu`/`closeBranch`. **The chevron never rotates** — no CSS transform or class toggle exists. The only visual change is the submenu appearing/disappearing and `aria-expanded` changing (which is invisible to non-screen-reader users).

### 3.5 Existing Tests

- `test_submenu.py` — `TestExpandButtons` asserts `data-category-expand` present for categories with children, absent for leaves. **Unaffected** by icon/rotation/size changes (attribute name and condition unchanged).
- `test_autocomplete_template.py` — `TestCatalogMenuAccordionTemplate` asserts: `hidden ml-4` class on container, `closeBranch`/`collapseSiblings` functions present, `collapseBranches` absent, `get_children.exists` present, `firstof` absent. **Unaffected** — we preserve all these strings.

### 3.6 Research Findings (HIGH confidence)

- **NN/g "Accordion Icons" (Laubheimer & Budiu, 2020):** Caret (chevron) is the safest icon for in-place accordions. The right-facing arrow is explicitly "not recommended" — not statistically different from no-icon control. Chevrons should **rotate** to communicate state.
- **WCAG 2.2 SC 2.5.5:** 44×44px target size (Enhanced AA). The project already mandates this in `ui-patterns.md`.
- **Apple HIG / Material Design:** 44pt / 48dp minimum.
- **Plus/minus:** Acceptable but "slower to scan" and risks confusion with add/remove actions.

### 3.7 Spec_022 Already Applied

Spec_022 (Applied 2026-08-20, commit `a6b7e11`) already fixed:
- `get_children_count` → `get_children.exists` (expand buttons now render)
- `firstof` → `{% with current_cat=breadcrumb_category %}` (breadcrumbs show category path)
- `breadcrumb.html` `|last` → `slice:"::-1"|first` (no crash on empty ancestors)

These are **confirmed working** in the current codebase. This spec builds on top of them for the remaining icon/size/ARIA gaps.

---

## 4. Requirements

| ID | Requirement | Source |
|---|---|---|
| R-01 | The expand button must use a downward-facing caret `▼` SVG (path `M5 9l7 7 7-7`), not the right-chevron `▶` (path `M9 5l7 7-7 7`). | NN/g §3.1; Decision_024 Q1 |
| R-02 | The caret must rotate 180° when the branch is expanded (`aria-expanded="true"`), and return to 0° when collapsed. | NN/g §3.1; Decision_024 Q2 |
| R-03 | The expand button hit area must be ≥44×44px in both dimensions (project standard + WCAG 2.5.5 + Apple HIG 44pt). | `ui-patterns.md` §Touch Target; NN/g §3.2 |
| R-04 | The caret SVG icon itself remains 16×16px (`w-4 h-4`) — only the padding/hit-area grows. | UX Planet §3.1 (compact icon, large hit area) |
| R-05 | The expand button must have `aria-controls` attribute matching the `id` of its associated submenu container. | WAI-ARIA Disclosure pattern §3.1 |
| R-06 | The submenu container must have a unique `id` attribute (e.g. `menu-{{ cat.id }}` or `submenu-{{ cat.slug }}`) that the button's `aria-controls` references. | WAI-ARIA Disclosure pattern §3.1 |
| R-07 | The pattern must be identical across all three locations: desktop dropdown, mobile off-canvas, and `mega_submenu.html`. | Decision_024 Q5 |
| R-08 | No existing JS behavior changes — the accordion toggle, sibling-collapse, and close-on-outside-click must work identically. Only the rotation class toggle is added. | Spec_022 R-04a (behavior preserved) |

---

## 5. Conceptual Development Tasks

| # | Task | Description | Resolvable By |
|---|---|---|---|
| T1 | Replace chevron icon in `mega_submenu.html` | Change SVG path from `d="M9 5l7 7-7 7"` to `d="M5 9l7 7 7-7"` (downward caret). Add `aria-controls` and ensure 44px hit area. | Frontend |
| T2 | Replace chevron icon in `header_catalog.html` — desktop | Same change on the desktop dropdown expand button (line 96–102). | Frontend |
| T3 | Replace chevron icon in `header_catalog.html` — mobile | Same change on the mobile off-canvas expand button (line 162–168). | Frontend |
| T4 | Add submenu container `id` + `aria-controls` | Add `id="menu-{{ cat.id }}"` to each `data-category-submenu` container div; add `aria-controls="menu-{{ cat.id }}"` to the expand button. All three locations. | Frontend |
| T5 | Enlarge touch targets to 44×44px | Replace `px-2 py-2` with `p-3` and add `min-w-11 min-h-11` (Tailwind: 44px). Fix `mega_submenu.html` missing `min-h-[44px]`. | Frontend |
| T6 | Add rotation toggle in JS | In `header_catalog.html` inline `<script>`, when a branch opens, add `rotate-180` (or `transform rotate-180`) class to the button's SVG; remove it when closing. Scope to the clicked branch's SVG. | Frontend |
| T7 | Update tests | Extend `test_autocomplete_template.py` to assert: downward caret path present, right-chevron path absent, `aria-controls` present, `min-w-11` or `p-3` present, rotation class toggle in JS. | QA |
| T8 | Verification | Full test suite + lint + typecheck + manual browser verification (desktop + mobile). | All |

**Suggested build order:** T1 → T2 → T3 (parallelizable, same template changes) → T4 (id + aria-controls) → T5 (sizing) → T6 (JS rotation) → T7 (tests) → T8 (verification). T1–T5 can be done together as one template-edit pass per file.

---

## 6. Technical Details

### 6.1 Icon Replacement

**Current SVG path (right-chevron ▶):**
```
d="M9 5l7 7-7 7"
```
This draws: start at (9,5) → line to (16,12) → line to (9,19) → a right-pointing triangle.

**New SVG path (downward caret ▼):**
```
d="M5 9l7 7 7-7"
```
This draws: start at (5,9) → line to (12,16) → line to (19,9) → a downward-pointing triangle.

**Why this path:** The downward caret is the standard disclosure icon. When rotated 180°, it points upward (▲), signalling "expanded / visible below." This matches NN/g's recommendation and the WAI-ARIA Disclosure pattern.

### 6.2 Button Class Changes

**Current (all three locations):**
```html
class="px-2 py-2 text-gray-400 hover:text-blue-600 min-h-[44px]"
```
*(Note: `mega_submenu.html` is missing `min-h-[44px]` — inconsistency.)*

**New:**
```html
class="p-3 text-gray-400 hover:text-blue-600 min-w-11 min-h-11 min-w-[44px] min-h-[44px] transition-transform duration-150"
```

- `p-3` = 0.75rem (12px) padding on all sides → 16px icon + 12px + 12px = 40px. To reach 44px, add `min-w-11 min-h-11` (Tailwind: `min-width: 2.75rem` = 44px, `min-height: 2.75rem` = 44px).

Actually, for precision: `min-w-11` = 2.75rem = 44px, `min-h-11` = 2.75rem = 44px. With `p-3` (12px) + 16px icon, the natural size is 40px, but `min-w-11 min-h-11` forces it to 44px. This is the cleanest way to guarantee the 44px floor.

**Simpler and clearer:**
```html
class="p-3 text-gray-400 hover:text-blue-600 min-w-[44px] min-h-[44px] flex items-center justify-center transition-transform duration-150"
```

Wait — using `min-w-[44px] min-h-[44px]` with arbitrary values might not work if the Tailwind config doesn't support arbitrary values. Let me check the Tailwind config... Actually, Tailwind CSS v3+ supports arbitrary values by default. But the project uses `django-tailwind`. Let me use the `min-w-11 min-h-11` approach which uses theme-based values (2.75rem = 44px) which is more standard.

Let me settle on:
```html
class="p-3 text-gray-400 hover:text-blue-600 min-w-11 min-h-11 flex items-center justify-center transition-transform duration-150"
```

Actually, looking at the existing code, `min-h-[44px]` is already used (line 97 of header_catalog.html). So arbitrary values ARE supported. Let me use:

```html
class="p-3 text-gray-400 hover:text-blue-600 min-w-[44px] min-h-[44px] flex items-center justify-center transition-transform duration-150"
```

Hmm, but actually there's a subtlety. The current button has `px-2 py-2 min-h-[44px]`. The `px-2` gives horizontal padding of 8px, and `w-4` gives a 16px icon. Total width = 16 + 16 = 32px. The `min-h-[44px]` on height makes height 44px, but width is still 32px.

For the new button, we want both dimensions ≥44px. The cleanest approach:
```html
class="p-3 text-gray-400 hover:text-blue-600 min-w-[44px] min-h-[44px] flex items-center justify-center transition-transform duration-150"
```

This gives:
- `p-3` = 12px padding → icon area = 16 + 12 + 12 = 40px, but `min-w-[44px]` forces width to 44px
- `min-h-[44px]` forces height to 44px
- `flex items-center justify-center` centers the SVG within the expanded hit area
- `transition-transform duration-150` for smooth rotation

Wait, but `flex items-center justify-center` would change the layout slightly. The button is inside a `<div class="flex items-center justify-between">`. The button being `flex` itself is fine — it's already a button. Let me keep it simple:

```html
class="p-3 text-gray-400 hover:text-blue-600 min-w-[44px] min-h-[44px] transition-transform duration-150"
```

The SVG `w-4 h-4` stays. With `p-3`, the button becomes 40×40px, and `min-w-[44px] min-h-[44px]` bumps it to 44×44px. The icon stays centered because button has default `flex` behavior... actually no, `<button>` is `display: inline-block` by default. The SVG inside would be positioned based on text alignment. Let me use `flex items-center justify-center` to ensure centering:

```html
class="p-3 text-gray-400 hover:text-blue-600 min-w-[44px] min-h-[44px] flex items-center justify-center transition-transform duration-150"
```

This is clean and correct.

### 6.3 aria-controls + Container id

**Button (before):**
```html
<button type="button" data-category-expand="{{ child.slug }}"
        class="px-2 py-2 text-gray-400 hover:text-blue-600"
        aria-expanded="false" aria-label="{% trans "Expand" %} {{ child.get_name }}">
```

**Button (after):**
```html
<button type="button" data-category-expand="{{ child.slug }}"
        aria-controls="menu-{{ child.id }}"
        class="p-3 text-gray-400 hover:text-blue-600 min-w-[44px] min-h-[44px] flex items-center justify-center transition-transform duration-150"
        aria-expanded="false" aria-label="{% trans "Expand" %} {{ child.get_name }}">
```

**Container (before):**
```html
<div class="hidden ml-4" data-category-submenu="{{ child.slug }}"></div>
```

**Container (after):**
```html
<div id="menu-{{ child.id }}" class="hidden ml-4" data-category-submenu="{{ child.slug }}"></div>
```

Using `child.id` (the MPTT model's primary key) for the `id` attribute is stable and unique. The `aria-controls` value must match exactly.

### 6.4 JS Rotation Toggle

In the existing inline `<script>`, the `loadSubmenu` function (line 313–327) currently sets `aria-expanded="true"` on the expand button:

```javascript
function loadSubmenu(container) {
    var li = container.closest('li');
    if (!li) return;
    var slug = (container.getAttribute('data-category-submenu') || '').replace(/"/g, '');
    if (!slug) return;
    fetch('/categories/' + encodeURIComponent(slug) + '/submenu/')
        .then(function (r) { if (!r.ok) throw new Error(); return r.text(); })
        .then(function (html) {
            container.innerHTML = html;
            container.classList.remove('hidden');
            var expand = li.querySelector('[data-category-expand]');
            if (expand) expand.setAttribute('aria-expanded', 'true');
        })
        .catch(function () { /* ignore load errors */ });
}
```

**Change needed:** After setting `aria-expanded="true"`, also add a rotation class to the SVG inside the expand button. And in `closeBranch`, remove the rotation class when closing.

**Updated `loadSubmenu` (line 324):**
```javascript
            var expand = li.querySelector('[data-category-expand]');
            if (expand) {
                expand.setAttribute('aria-expanded', 'true');
                var svg = expand.querySelector('svg');
                if (svg) svg.classList.add('rotate-180');
            }
```

**Updated `closeBranch` (line 329–340):** The function currently resets `aria-expanded="false"` on all expand buttons within the branch's `<li>`:
```javascript
function closeBranch(container) {
    container.classList.add('hidden');
    container.querySelectorAll('[data-category-submenu]').forEach(function (c) {
        c.classList.add('hidden');
    });
    var li = container.closest('li');
    if (li) {
        li.querySelectorAll('[data-category-expand]').forEach(function (b) {
            b.setAttribute('aria-expanded', 'false');
        });
    }
}
```

**Add rotation reset:**
```javascript
function closeBranch(container) {
    container.classList.add('hidden');
    container.querySelectorAll('[data-category-submenu]').forEach(function (c) {
        c.classList.add('hidden');
    });
    var li = container.closest('li');
    if (li) {
        li.querySelectorAll('[data-category-expand]').forEach(function (b) {
            b.setAttribute('aria-expanded', 'false');
            var svg = b.querySelector('svg');
            if (svg) svg.classList.remove('rotate-180');
        });
    }
}
```

Also update `collapsePanel` (line 379–382) which resets all expand buttons when closing the entire panel:
```javascript
function collapsePanel(panel) {
    panel.querySelectorAll('[data-category-submenu]').forEach(function (c) { c.classList.add('hidden'); });
    panel.querySelectorAll('[data-category-expand]').forEach(function (b) {
        b.setAttribute('aria-expanded', 'false');
        var svg = b.querySelector('svg');
        if (svg) svg.classList.remove('rotate-180');
    });
}
```

Note: The `rotate-180` class is a Tailwind utility that applies `transform: rotate(180deg)`. For it to work, the SVG needs `transition-transform duration-150` (already added via the button class in §6.2).

**Important:** The SVG itself doesn't need the `transition-transform` — the button class applies it, and since SVG is a child of the button, the transform class on the SVG will animate. Actually, Tailwind's `rotate-180` applies to the element it's on (the SVG), and `transition-transform` on the button will apply to all children. Let me be precise: Tailwind's `transition-*` utilities go on the element that should animate. Since we're adding `rotate-180` to the SVG, the `transition-transform` should be on the SVG too, or we put both on the SVG.

Let me revise: put `transition-transform duration-150` on the SVG in the template, and toggle `rotate-180` on the SVG in JS:

**SVG:**
```html
<svg class="w-4 h-4 transition-transform duration-150" fill="none" stroke="currentColor" viewBox="0 0 24 24">
    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 9l7 7 7-7"></path>
</svg>
```

**JS toggle (add `rotate-180` to SVG classList).**

This is cleaner. The button class handles hit-area sizing; the SVG class handles animation.

### 6.5 Consistency Between `mega_submenu.html` and `header_catalog.html`

The `mega_submenu.html` expand button (line 18) currently has:
```html
class="px-2 py-2 text-gray-400 hover:text-blue-600"
```
(No `min-h-[44px]`, no `flex`, no `transition`.)

It must be updated to match the same pattern as `header_catalog.html`:
```html
class="p-3 text-gray-400 hover:text-blue-600 min-w-[44px] min-h-[44px] flex items-center justify-center transition-transform duration-150"
```

And its SVG must get `transition-transform duration-150`:
```html
<svg class="w-4 h-4 transition-transform duration-150" ...>
```

---

## 7. Data & API Contracts

**No changes.** Both the lazy-load endpoint and the view context are unchanged:
- `/categories/<slug>/submenu/` (GET) — unchanged; returns `mega_submenu.html` fragment.
- `category_submenu` view — unchanged.
- Context processor `header_context` — unchanged.

---

## 8. Resolved Product Owner Decisions

| Q# | Question | PO Decision | Rationale |
|---|---|---|---|
| 1 | Icon: `+`/− vs rotating caret? | **Rotating downward caret ▼** (not `+`) | NN/g empirical study: caret is "safest icon choice" for in-place accordions; right-arrow "should not be used." Plus/minus "acceptable but slower to scan." Rotation provides visual state cue. |
| 2 | Toggle behavior on expand? | **Rotate 180° in place** (CSS `rotate-180` class on SVG) | Standard pattern; low effort; clearly communicates state. |
| 3 | Button size? | **44×44px minimum** | Project's `ui-patterns.md` mandates 44px; WCAG 2.5.5 AA; Apple HIG 44pt. Current 32×32px fails. |
| 4 | Scope? | **Approach A only** (icon + size + aria-controls + rotation) | Zero test breakage; ships in one ticket. Approach B (whole-header disclosure + tree semantics) deferred to follow-up. |
| 5 | Mobile vs desktop? | **Same pattern everywhere** | Consistency; 44px applies to both touch targets. |
| 6 | Button-link integration (split action)? | **Keep split action for now**; document as follow-up | Unifying changes row structure tests assert on; deferred to Approach B. |

**Rejected with reason:** The PO's original `+`/`−` suggestion from Problem_03 is **not adopted**. Research (NN/g, HIGH confidence) found that plus/minus is slower to scan and risks confusion with add/remove actions. The rotating caret is empirically superior for accordion disclosure. This is documented here so future maintainers understand why the icon deviates from the original request.

---

## 9. Technical Constraints

1. **HTMX 1.9.12** — `hx-on` not available; all JS via vanilla `data-*` + inline `<script>`.
2. **No custom CSS** — all styling via Tailwind utility classes (matching existing `header_catalog.html` pattern).
3. **`data-category-expand` and `data-category-submenu` attribute names** must remain unchanged (JS depends on them; tests assert presence).
4. **`hidden` class** on submenu container must remain unchanged (tests assert `class="hidden ml-4"`).
5. **`test_autocomplete_template.py`** substring assertions must still pass — `get_children.exists`, `closeBranch`, `collapseSiblings`, `collapseBranches` absent, `hidden ml-4`, `data-category-submenu`.
6. **`test_submenu.py`** endpoint tests unchanged — `/categories/<slug>/submenu/` still returns 200/404 with child names.
7. **`child.id` used for `id` attribute** — MPTT Category model has an auto-increment PK `id`. Safe to use in `id="menu-{{ child.id }}"`.
8. **`aria-controls` references must match `id` exactly** — `aria-controls="menu-{{ child.id }}"` → `id="menu-{{ child.id }}"`.

---

## 10. Acceptance Criteria

| AC | Verification |
|---|---|
| AC-01: Downward caret icon in all 3 locations | Template source: `d="M5 9l7 7 7-7"` present; `d="M9 5l7 7-7 7"` absent |
| AC-02: Chevron rotates 180° on expand | Manual + JS: `rotate-180` class added on open, removed on close |
| AC-03: Hit area ≥44×44px | CSS: `min-w-[44px] min-h-[44px]` on all 3 buttons; `mega_submenu.html` fixed to match |
| AC-04: `aria-controls` + container `id` | `aria-controls="menu-{{ child.id }}"` on button; `id="menu-{{ child.id }}"` on container |
| AC-05: SVG rotation transition | `transition-transform duration-150` on SVG in all 3 locations |
| AC-06: Existing tests pass | `test_submenu.py` (6 tests), `test_autocomplete_template.py` (9 tests) — all green |
| AC-07: No template exceptions | 200 OK on category listing, ad detail, search, home |
| AC-08: Consistent icons across mobile + desktop | Same SVG path + classes in desktop dropdown, mobile panel, and mega_submenu |
| AC-09: No `+`/− icon | `d="M9 5l7 7-7 7"` (right-chevron) absent from all templates; no plus-minus toggle |

---

## 11. Dependencies

- T1–T3 can be done in one pass per file (icon + class + aria-controls + id changes are all in the same template blocks).
- T4 (JS rotation toggle) depends on the SVG path change (T1–T3) being in place, since `querySelector('svg')` targets the SVG we're modifying.
- T7 (tests) must run after all changes.
- No dependency on Spec_022 — it's already applied.

---

## 12. Follow-up: Approach B (Whole-Header Disclosure + Tree Semantics)

Documented as a future spec. After Approach A ships and is verified:

1. **Unify row action:** Merge the category label `<a>` and the expand button into a single disclosure `<button>` for branches. Leaf nodes remain plain `<a>` navigation. This eliminates the split-action anti-pattern (Smashing Magazine "Tivoli example").
2. **ARIA tree semantics:** Add `role="tree"`, `role="treeitem"`, `role="group"` + `aria-owns` to the menu structure.
3. **Keyboard navigation:** Wire Right/Down arrow keys per WAI-ARIA APG Tree View keyboard matrix.
4. **Nesting depth guard:** Cap desktop to 3 levels; beyond that, render a routing-page link instead of another lazy submenu (matches Avito/eBay ceiling).
5. **Test updates:** `test_autocomplete_template.py` and `test_submenu.py` will need updated substring assertions for the new `role="tree"` structure.

---

## 13. Risks

| Risk | Mitigation |
|---|---|
| Rotating caret might not animate smoothly if `transition-transform` is missing | Add `transition-transform duration-150` to the SVG class in all 3 templates; verify in browser |
| `mega_submenu.html` lazy-loaded content won't have the new JS class-toggle behavior | The `htmx:afterSwap` listener (line 529–532) calls `attachCategoryHandlers(e.target)` on newly injected panels, re-attaching click handlers. New content will get the rotation behavior because `closeBranch`/`collapsePanel`/`loadSubmenu` are in the original `<script>`, not re-injected. Verify with lazy-loaded level 2+ |
| `child.id` might not be available in some contexts | MPTT Category model has `id` (auto PK) in all querysets used by `root_categories` and `children`. Safe. |
| `aria-controls` ID mismatch across lazy-loaded content | Each `mega_submenu.html` render uses the same `child.id` → `menu-{{ child.id }}` pattern, so the button's `aria-controls` and the container's `id` match within the same rendered fragment |
| `min-w-[44px]` arbitrary value not purged by Tailwind | The project already uses `min-h-[44px]` extensively (header_catalog.html lines 44, 58, 65, 77, 163; autocomplete template assertions don't check this). Arbitrary values are supported by the Tailwind config. |
