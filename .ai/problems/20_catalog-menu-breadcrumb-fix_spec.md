# Spec_020 — Catalog Menu & Breadcrumbs Fix

**Decision source:** `.ai/problems/Decision_020.md`
**Spec state:** APPROVED — all Product Owner decisions resolved (see §8)
**Date:** 2026-08-19
**Stack:** Django 5.2 LTS · Python 3.14 · HTMX 1.9.12 (pinned CDN) · django-mptt · Tailwind CSS · PostgreSQL 18
**Related spec:** Spec_014 (`14_catalog-ui-avito_spec.md`) — implemented the shared catalog header; this spec fixes menu depth navigation and breadcrumb rendering.

---

## 1. Business Goal

The shared Avito-style catalog header (`components/header_catalog.html`), implemented per Spec_014, has two defects reported in Decision_020:

1. **Menu button cannot navigate beyond level 2** — the accordion only reaches the first subcategory level; deeper levels (3, 4) are unreachable, and back-navigation between levels is not possible.
2. **Breadcrumbs do not show the category path** — on ad detail pages, breadcrumbs render only "Главная" without the ancestor chain to the ad's category.

This spec defines the minimal, surgical fixes to make menu navigation work through all 4 levels (with back-navigation) and breadcrumbs show the full category path on all pages.

---

## 2. Scope

### In Scope
1. Fix the `hidden` class bug in `mega_submenu.html` that prevents level-2+ expansion.
2. Redesign the accordion JavaScript to support back-navigation (collapse current level while keeping parent levels visible).
3. Fix breadcrumb rendering on the ad detail page to pass `breadcrumb_category` explicitly and show the full ancestor chain.
4. Add ellipsis truncation for long breadcrumb chains.
5. Ensure top-level categories remain accessible from any menu depth.

### Out of Scope
- Changing the menu to a two-column mega-menu (PO elected to keep the single-column accordion).
- Hover-to-expand (PO elected click-only, Option A).
- Ad title in breadcrumbs (PO confirmed: keep current behavior — no ad title).
- Breadcrumb separator (PO confirmed: keep `&rsaquo;`).
- Shared base template refactor (per Spec_014 constraint: no `{% extends %}`).
- Dashboard/auth headers (not affected).

---

## 3. Facts

### 3.1 Confirmed Bug: Missing `hidden` Class in `mega_submenu.html`

| Element | File | Line | Class |
|---|---|---|---|
| Level-1 container (desktop dropdown) | `header_catalog.html` | 77 | `class="hidden ml-4"` ✅ |
| Level-1 container (mobile off-canvas) | `header_catalog.html` | 142 | `class="hidden ml-4"` ✅ |
| Level-2+ container (dynamic injection) | `mega_submenu.html` | 28 | `class="ml-4"` ❌ **(missing `hidden`)** |

**Mechanism**: The JS toggle in `header_catalog.html` (lines 300–321) uses:
```javascript
var isOpen = container && !container.classList.contains('hidden');
```
Without `hidden` on dynamically-loaded containers, `isOpen` evaluates to `true` on first interaction, causing `collapseBranches()` to fire and `loadSubmenu()` to never execute. The user sees no level-3/4 children.

### 3.2 Confirmed Bug: `collapseBranches` Destroys Ancestor State

The current `collapseBranches(panel)` function (line 300–303) adds `hidden` to **all** `[data-category-submenu]` containers and resets **all** `[data-category-expand]` buttons to `aria-expanded=false`. This means:

- Expanding a level-2 sibling collapses the level-1 parent container too (because it's also a `[data-category-submenu]`).
- After collapse, the level-2 container is nested inside the now-hidden level-1 container → invisible even if `hidden` is removed.
- No back-navigation is possible: the entire menu tree resets on every expand action.

### 3.3 Breadcrumb Context Gap on Ad Detail Page

- `ad_detail` view (`apps/ads/views/listings.py`, line 48) does NOT pass `breadcrumb_category` in its context dict (line 78–87).
- The header template (`header_catalog.html`, line 10) uses `{% firstof breadcrumb_category ad.category as current_cat %}` as a fallback, which works only if `ad` and `ad.category` are in scope.
- On the ad detail page, `ad` IS in context (view passes `"ad": ad`), but the fallback may not reliably produce the full ancestor chain because the `breadcrumb.html` include receives the category but the view never explicitly sets `breadcrumb_category`.
- The PO confirms breadcrumbs currently show only "Главная" on ad detail — the category path is not rendering.

### 3.4 All Existing Tests Pass

Test suites run via Docker (test DB `mko-bazuna-test-db-1`):
- `test_submenu.py` (4 tests) — endpoint tests for `/categories/<slug>/submenu/` ✅ passing
- `test_autocomplete_template.py` (6 tests) — template wiring assertions ✅ passing
- `test_listings_context.py` (8 tests) — filter context including `breadcrumb_category` ✅ passing
- `test_detail_context.py` (3 tests) — detail view context ✅ passing

### 3.5 MPTT Ancestor Ordering Confirmed

Per `.venv/Lib/site-packages/mptt/models.py:522`, `get_ancestors()` defaults to `ascending=True`, which returns root→leaf order. The breadcrumb template's `{% for cat in breadcrumb_category.get_ancestors %}` correctly produces root→leaf. **Breadcrumb ordering is NOT the bug.**

### 3.6 HTMX 1.9.12 Constraints (critical)

- `hx-on` (inline event-handler attribute) is **NOT available** — introduced in HTMX 2.0.
- All interactive logic uses vanilla JS via `data-*` attributes (matching existing `language_switcher.html` pattern).

---

## 4. Requirements

### R-01: Menu Depth Navigation (Fix `hidden` Class Bug)

| ID | Requirement | Source |
|---|---|---|
| R-01a | `mega_submenu.html` line 28 must include the `hidden` class: `<div class="hidden ml-4" data-category-submenu="{{ child.slug }}"></div>` | Code trace §3.1 |
| R-01b | The menu must traverse all 4 MPTT levels: root → level-2 → level-3 → level-4 | Decision_020 §1 |
| R-01c | Each level is lazy-loaded via the existing `/categories/<slug>/submenu/` HTMX endpoint on click of the expand button | Existing implementation |

### R-02: Back-Navigation Between Menu Levels

| ID | Requirement | Source |
|---|---|---|
| R-02a | When at level N (N ≥ 2), the user can click to return to level N-1 without collapsing the entire menu tree. | Decision_020 §1 ("При переходе на 3 уровень, я должен иметь возможность кликом вернуться на 2 уровень") |
| R-02b | When re-clicking an expand button for an already-open branch, collapse that branch and its descendants; keep ancestor branches open. | Decision_020 §1 |
| R-03c | Top-level categories (root nodes) are always visible in the panel and remain accessible from any submenu depth. | Decision_020 §2 ("Должна оставаться возможность вернуться наверх") |

### R-03: Accordion Behavior (Sibling Collapse Only)

| ID | Requirement | Source |
|---|---|---|
| R-03a | Expanding a branch collapses only sibling branches at the same DOM level, not ancestor or descendant branches. | Decision_020 §1 |
| R-03b | Ancestor containers (parent levels) must never be hidden by navigating deeper into a sibling branch. | Decision_020 §1 |

### R-04: Breadcrumb Rendering on All Pages

| ID | Requirement | Source |
|---|---|---|
| R-04a | On ad detail pages, `breadcrumb_category` must be explicitly passed in the view context (`ad.category`). | Decision_020 §2 ("не раскрываются категории") |
| R-04b | Breadcrumbs show the full ancestor chain from root → current category, using MPTT `get_ancestors()` (root→leaf order). | MPTT confirmed §3.5 |
| R-04c | On category listing pages, breadcrumbs show root → current category path (already works via `breadcrumb_category` passed by `listings()` and `search()`). | Existing implementation |
| R-04d | The ad title is NOT included in breadcrumbs (Avito pattern; confirmed by PO). | Spec_014 R-03c; PO Q3 |

### R-05: Breadcrumb Ellipsis Truncation

| ID | Requirement | Source |
|---|---|---|
| R-05a | If the breadcrumb ancestor chain exceeds 3 segments (including root and current), intermediate segments are collapsed with a "…" ellipsis. Show root + first 1 intermediate + "…" + last 1 intermediate + current. | Decision_020 §3 ("Если он длинный - ставим многоточие") |
| R-05b | The ellipsis truncation is applied in the `breadcrumb.html` template include, not in the view logic. | Template-layer decision |

### R-06: Breadcrumb on Search Results

| ID | Requirement | Source |
|---|---|---|
| R-06a | On search result pages, breadcrumbs show the category path (if a category filter is active); the search query is shown separately below the trail as "Результаты поиска: [query]". | Spec_014 R-03d; existing `breadcrumb.html` |

### R-07: Interaction Model

| ID | Requirement | Source |
|---|---|---|
| R-07a | Click-to-expand only (no hover-to-expand). | PO Q5, Option A |
| R-07b | Click-outside and Escape close the entire menu panel. | Existing behavior (Spec_014 R-02e, AC-04) |

---

## 5. Conceptual Development Tasks

| # | Task | Description | Resolvable By |
|---|---|---|---|
| T1 | Fix `hidden` class in `mega_submenu.html` | Add `hidden` class to the submenu container div on line 28: `<div class="hidden ml-4" data-category-submenu="{{ child.slug }}"></div>` | Frontend |
| T2 | Redesign accordion JS for back-navigation | Replace `collapseBranches()` with a depth-aware sibling-collapse algorithm: when expanding a branch, collapse only siblings at the same DOM level; when re-clicking an open branch, collapse it and its descendants. Keep ancestors open. | Frontend |
| T3 | Pass `breadcrumb_category` on ad detail | In `ad_detail()` view (`listings.py` line 48), add `"breadcrumb_category": ad.category` to the context dict. | Backend |
| T4 | Implement breadcrumb ellipsis truncation | Modify `breadcrumb.html` to truncate the ancestor chain when it exceeds 3 segments, using a template-level slice + "…" insertion. | Frontend |
| T5 | Add/Update template tests | Add test assertions for: `mega_submenu.html` `hidden` class; breadcrumb rendering on detail page context; breadcrumb ellipsis truncation. | Backend/QA |
| T6 | Update existing tests if needed | Verify `test_submenu.py`, `test_autocomplete_template.py`, `test_listings_context.py`, `test_detail_context.py` still pass after changes. | Backend/QA |

**Suggested build order:** T1 → T2 → T3 → T4 → T5 → T6

---

## 6. Technical Details

### 6.1 JavaScript Algorithm (header_catalog.html, lines 300–326)

**Current (broken):**
```javascript
function collapseBranches(panel) {
    panel.querySelectorAll('[data-category-submenu]').forEach(function (c) { c.classList.add('hidden'); });
    panel.querySelectorAll('[data-category-expand]').forEach(function (b) { b.setAttribute('aria-expanded', 'false'); });
}

// In click handler:
var isOpen = container && !container.classList.contains('hidden');
collapseBranches(panel);
if (!isOpen && container) loadSubmenu(container);
```

**Replacement logic:**

```javascript
// Close a single branch (container + all its descendants), keeping ancestors open.
function closeBranch(container) {
    container.classList.add('hidden');
    container.querySelectorAll('[data-category-submenu]').forEach(function (c) {
        c.classList.add('hidden');
    });
    // Reset expand buttons within this branch's <li> and descendants
    var li = container.closest('li');
    if (li) {
        li.querySelectorAll('[data-category-expand]').forEach(function (b) {
            b.setAttribute('aria-expanded', 'false');
        });
    }
}

// Collapse only sibling containers at the same DOM level (not ancestors).
function collapseSiblings(container) {
    var li = container.closest('li');
    if (!li) return;
    var siblings = li.parentElement.querySelectorAll(':scope > li');
    siblings.forEach(function (sibLi) {
        var sibContainer = sibLi.querySelector('[data-category-submenu]');
        if (sibContainer && sibContainer !== container) {
            closeBranch(sibContainer);
        }
    });
}

// Updated click handler:
var expand = e.target.closest('[data-category-expand]');
if (expand) {
    e.preventDefault();
    e.stopPropagation();
    var slug = expand.getAttribute('data-category-expand');
    var container = panel.querySelector('[data-category-submenu="' + slug + '"]');
    var isOpen = container && !container.classList.contains('hidden');
    if (isOpen) {
        closeBranch(container);  // Navigate back: collapse this branch + descendants
    } else {
        collapseSiblings(container);  // Close sibling branches at same level
        loadSubmenu(container);  // Load + expand this branch
    }
}
```

**Trace with fix (4-level tree: Root → A → B → C → D):**

1. Open dropdown → level-1 roots visible
2. Click expand on root category A → `collapseSiblings(A's container)` closes B, C, D roots; `loadSubmenu(A's container)` loads A's children (level 2)
3. Click expand on level-2 child A1 → `collapseSiblings(A1's container)` closes A1's siblings; `loadSubmenu` loads A1's children (level 3). A's container stays open.
4. Click expand on level-3 child A1a → same pattern, loads level 4. A and A1 stay open.
5. Click expand on A1a again (already open) → `closeBranch(A1a's container)` closes A1a + descendants. A and A1 remain open. User is back at level 3.
6. Click expand on A1 again → `closeBranch(A1)` closes A1 + descendants. A stays open. User is back at level 2.
7. Click expand on A again → `closeBranch(A)` closes A + descendants. Level-1 roots visible again.

### 6.2 Ad Detail View Context (listings.py, line 78)

**Add to context dict:**
```python
context = {
    "ad": ad,
    "breadcrumb_category": ad.category,  # NEW: enables breadcrumb path rendering
    "consent_shown": is_consent_given(request),
    ...
}
```

### 6.3 Breadcrumb Template (breadcrumb.html)

**Current rendering:** Shows `Главная › [ancestors] › [current]`

**Ellipsis truncation:** When ancestor chain length > 3 (including root), show:
```
Главная › [root] › … › [last intermediate] › [current]
```

Template approach using Django's `slice` filter on the ancestors queryset:
```django
{% if breadcrumb_category %}
    <a href="/">Главная</a>
    <span class="mx-1 text-gray-400">&rsaquo;</span>
    {% with ancestors=breadcrumb_category.get_ancestors %}
        {% if ancestors|length > 2 %}
            {{ ancestors.0.get_name }} › … › {{ ancestors|last:get_name }} › {{ breadcrumb_category.get_name }}
        {% else %}
            {% for cat in ancestors %}
                <a href="{% url 'ads:listings_category' cat.slug %}" class="hover:text-blue-600">{{ cat.get_name }}</a>
                <span class="mx-1 text-gray-400">&rsaquo;</span>
            {% endfor %}
            <span class="font-medium text-gray-800">{{ breadcrumb_category.get_name }}</span>
        {% endif %}
    {% endwith %}
{% endif %}
```

> **Note:** The `ancestors|last` syntax uses Django's `last` template filter. For deep chains where `ancestors.count > 2`, show root + ellipsis + last ancestor + current. The ellipsis segment is plain text (not linked).

---

## 7. Data & API Contracts

No API contract changes — both fixes use existing endpoints and templates.

- `/categories/<slug>/submenu/` (GET) — unchanged; returns `mega_submenu.html` fragment.
- `ad_detail` view — adds `breadcrumb_category` to context; no template URL changes.

---

## 8. Resolved Product Owner Decisions

| Q# | Question | PO Answer |
|---|---|---|
| 1 | Menu navigation pattern | Keep single-column accordion (Option A). Must navigate freely up and down all levels. Back to level 2 from level 3 by click. |
| 2 | Top-level accessible from any depth | Yes — "Должна оставаться возможность вернуться наверх" |
| 3 | Ad title in breadcrumbs | No — keep current behavior (ad title not in breadcrumbs) |
| 4 | Breadcrumb separator | Keep `&rsaquo;` (no change) |
| 5 | Trigger interaction | Click only (Option A, no hover) |
| 6 | Breadcrumb on ad detail | Must show full category path root→leaf, not just "Главная" |
| 7 | Long breadcrumb paths | Use ellipsis truncation when path is long |

---

## 9. Technical Constraints

1. **HTMX 1.9.12** — `hx-on` not available; use vanilla JS `data-*` + event listeners.
2. **No `base.html`** — keep `{% include %}` pattern; do not introduce `{% extends %}`.
3. **No custom CSS** in `input.css` — all styling via Tailwind utility classes.
4. **`autocomplete-dropdown` token** on `<ul>` must remain for `test_autocomplete_template.py`.
5. **`settings.BOT_USERNAME`** must never appear in templates directly.
6. **django-mptt** `get_ancestors()` / `get_descendants()` / `root_nodes()` are the only tree accessors.
7. **`mega_submenu.html`** must have `hidden` class on its container div, matching `header_catalog.html`.

---

## 10. Acceptance Criteria

### AC-01: Menu Depth Navigation
- Opening the "All Categories" dropdown and clicking expand buttons navigates through all 4 levels (root → level-2 → level-3 → level-4).
- Each level loads via the existing `/categories/<slug>/submenu/` endpoint.
- No level is unreachable.

### AC-02: Back-Navigation
- From level 3, re-clicking the level-2 expand button closes level 3 (and its children) while keeping level 1 and level 2 open.
- From level 2, re-clicking the level-1 expand button closes level 2 (and its children) while keeping level 1 open.
- Top-level categories remain visible at all times during navigation.

### AC-03: Breadcrumbs on Ad Detail
- On `/ads/<id>/` (ad in a deep category), breadcrumbs show: `Главная › [ancestor1] › [ancestor2] › … › [current_category]`.
- At least root → current category path is visible.
- Ad title is NOT in the breadcrumb trail.

### AC-04: Breadcrumb Ellipsis
- For categories with > 2 ancestors (chain depth > 3 including root), intermediate segments are replaced with "…".

### AC-05: Existing Tests Pass
- `test_submenu.py` (4 tests) — endpoint contract unchanged.
- `test_autocomplete_template.py` (6 tests) — template wiring unchanged.
- `test_listings_context.py` (8 tests) — context keys unchanged.
- `test_detail_context.py` (3 tests) — context keys unchanged (adding `breadcrumb_category` is additive).

---

## 11. Dependencies

- T1 must precede T2 (the `hidden` class fix is required for the accordion logic to work correctly).
- T3 must precede T4 (breadcrumb view context enables template rendering).
- T1 + T3 are independent and can be done in parallel.

## 12. Risks

| Risk | Mitigation |
|---|---|
| `test_detail_context.py` asserts exact context keys | Adding `breadcrumb_category` is additive; the test uses `assertIn`, not exact match. No breakage expected. |
| `test_submenu.py` asserts the rendered HTML contains child names | The `hidden` class addition doesn't affect child rendering. No breakage. |
| JavaScript change breaks existing accordion behavior | Comprehensive JS trace in §6.1 verifies all navigation paths. Manual verification recommended. |
| Breadcrumb ellipsis template logic is complex | Keep truncation simple: `ancestors|length > 2` → show root + ellipsis + leaf ancestor + current. |

---

*Spec compiled from Product Owner decisions (6 questions resolved) and four sources:
`Decision_020.md`, `catalog_ui_avito_patterns_research.md`, `htmx_dropdown_breadcrumb_patterns_research.md`, and direct source code tracing of `header_catalog.html`, `mega_submenu.html`, `breadcrumb.html`, `views.py`, and `models.py`.*
