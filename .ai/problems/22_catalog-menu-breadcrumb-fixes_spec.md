# Spec_022 — Catalog Menu & Breadcrumbs Fix (Corrective)

**Decision source:** `.ai/problems/Decision_021.md`
**Spec state:** APPROVED — three root causes identified, fixes specified
**Date:** 2026-08-20
**Stack:** Django 5.2.16 LTS · Python 3.14 · HTMX 1.9.12 · django-mptt · PostgreSQL 18

**Predecessor:** Spec_020 (`20_catalog-menu-breadcrumb-fix_spec.md`) — implementation attempted in commit
`2a72514`; the menu JS accordion redesign was correct but never activated because no expand buttons
render (RC-A). Breadcrumbs render but show no category path because `{% firstof %}` converts the
Category object to a string (RC-B), compounded by `|last` failing on empty querysets (RC-C).

---

## 1. Business Goal

Fix the two runtime defects reported in Decision_021:

1. **Breadcrumbs show "???????" only** — no category path on category listing pages, ad detail pages,
   or the search results page.
2. **Menu accordion cannot navigate beyond level 1** — no expand buttons appear, so sub-levels 2–4
   are unreachable and back-navigation between levels does not work.

The Spec_020 JS redesign (`closeBranch` / `collapseSiblings`) is correct and remains in place. The
fixes here are purely: restore expand-button rendering and correct the breadcrumb variable chain.

---

## 2. Scope

### In Scope

1. Replace the non-existent `get_children_count` check with `get_children.exists` in
   `header_catalog.html` and `mega_submenu.html` so expand buttons render for categories that
   have children.
2. Replace `{% firstof breadcrumb_category ad.category as current_cat %}` with
   `{% with current_cat=breadcrumb_category %}` to preserve the Category object reference.
3. Replace `breadcrumb_category.get_ancestors|last` in the `{% with %}` tag with a safe pattern
   that does not raise on empty querysets.
4. Keep the ellipsis truncation logic and separator decisions from Spec_020.

### Out of Scope

- No DB schema changes (no new fields/methods on `Category`; no migrations).
- No new endpoints (existing `/categories/<slug>/submenu/` HTMX endpoint is unchanged).
- No JS changes (the accordion was correctly redesigned in commit `2a72514`).
- No new API or URL contracts.
- No CSS changes or new assets.
- No `base.html` / extends introduction.

---

## 3. Root Cause Analysis

### RC-A: `get_children_count` does not exist on `Category`

| Attribute | Value |
|---|---|
| Template locations | `header_catalog.html` line 94, line 159; `mega_submenu.html` line 16 |
| Check expression | `{% if cat.get_children_count %}` |
| Django resolution | `get_children_count` is not a defined method or property on `Category` or `MPTTModel`. Django template variable resolution returns `TEMPLATE_STRING_IF_INVALID` (empty string) for non-existent attributes. Empty string is falsy. |
| Observed result | `{% if cat.get_children_count %}` is always False -> no expand buttons render. |
| Verified | `hasattr(Category, 'get_children_count')` returns False. `cat.get_children.count()` returns the correct count. |

MPTT model inspection:

| Available accessor | Description | Returns |
|---|---|---|
| `cat.get_children()` | Direct children queryset | QuerySet[Category] |
| `cat.get_descendant_count()` | Count of ALL descendants (tree) | int |
| `cat.get_ancestors()` | Ancestor chain (root -> parent) | QuerySet[Category] |
| ~~cat.get_children_count~~ | Does not exist | — |

Impact: The entire accordion is dead code — `attachCategoryHandlers()` attaches a click handler
to `[data-categories-panel]`, but the handler listens for clicks on `[data-category-expand]`,
which never exist in the DOM.

### RC-B: `{% firstof ... as %}` stringifies the object

| Attribute | Value |
|---|---|
| Location | `header_catalog.html` line 10 |
| Check expression | `{% firstof breadcrumb_category ad.category as current_cat %}` |
| Django internals | `FirstOfNode.render()` calls `render_value_in_context(value, context)` which calls `str(value)` before storing in the context variable. |
| Observed result | `current_cat` is the string "??????", not a Category instance. |
| Verified | Shell test: `{{ cc.get_name }}` with `cc` set via `firstof` returns empty; direct `{{ c.get_name }}` on same Category returns "??????". |

Downstream effects:
1. Line 78: `{{ current_cat.get_name }}` renders empty (strings lack `get_name`).
2. Line 135: Breadcrumb include receives a string as `breadcrumb_category`.
3. Inside `breadcrumb.html`: `breadcrumb_category.get_ancestors` and `.get_name` fail silently.

### RC-C: `|last` filter raises on empty queryset

| Attribute | Value |
|---|---|
| Location | `breadcrumb.html` line 13 |
| Check expression | `{% with ancestors=...get_ancestors last_ancestor=...get_ancestors\|last %}` |
| Django internals | `last` filter does `value[-1]`. QuerySet `__getitem__` with negative index raises `ValueError`. |
| Observed result | Root categories (0 ancestors) crash the `with` tag. |
| Verified | Direct render raises `ValueError: Negative indexing is not supported.` |

Impact: Even if RC-B is fixed, root-level categories would still crash the breadcrumb template.

---

## 4. Requirements

### R-01: Expand Buttons Must Render for Categories with Children
- R-01a: Any category with direct children must show an expand button.
- R-01b: Any category with no children must not show an expand button.
- R-01c: Each category triggers at most one DB query for children count.
- R-01d: All 4 MPTT levels must have functional expand buttons where children exist.

### R-02: `current_cat` Must Be a Category Object
- R-02a: `current_cat` must be a Category instance (not a string).
- R-02b: On listing/search pages, `current_cat` = `breadcrumb_category` from view.
- R-02c: On ad detail, `current_cat` = `breadcrumb_category` (already passed by view).
- R-02d: On home page, `current_cat` = None.

### R-03: Breadcrumb Template Must Not Crash on Empty Ancestors
- R-03a: Root-level categories (0 ancestors) render: "??????? > [name]".
- R-03b: Child categories render full ancestor chain.
- R-03c: No Python exceptions during template rendering.

### R-04: Existing Behavior Preserved
- R-04a: Accordion JS (closeBranch/collapseSiblings) unchanged.
- R-04b: hidden class on mega_submenu.html container unchanged.
- R-04c: Breadcrumb ellipsis truncation unchanged.
- R-04d: Separator &rsaquo; unchanged.
- R-04e: No ad title in breadcrumbs.

---

## 5. Conceptual Development Tasks

| # | Task | Description | Resolvable By |
|---|---|---|---|
| T1 | Fix get_children_count | Replace {% if cat.get_children_count %} with {% if cat.get_children.exists %} in header_catalog.html (2 places) and mega_submenu.html (1 place). | Frontend |
| T2 | Fix firstof stringification | Replace {% firstof ... as current_cat %} with {% with current_cat=breadcrumb_category %}. | Frontend |
| T3 | Fix |last on empty queryset | Remove last_ancestor from with-tag; use ancestors|slice:"-1:"|first in ellipsis branch. | Frontend |
| T4 | Update tests | Extend test_autocomplete_template.py and test_detail_context.py; add runtime breadcrumb tests. | Backend/QA |
| T5 | Verification | Full test suite + lint + typecheck + manual browser verification. | All |

---

## 6. Technical Details

### 6.1 Fix RC-A: Expand Button Condition

**Files:** `header_catalog.html` (lines 94, 159), `mega_submenu.html` (line 16)

Replace `{% if cat.get_children_count %}` with `{% if cat.get_children.exists %}`.

Template variable resolution chain: `cat.get_children` (method, no args) -> QuerySet; `.exists`
(method, no args) -> bool. Verified in shell: True for categories with children, False for leaves.

### 6.2 Fix RC-B: Object-Preserving Variable

**File:** `header_catalog.html` line 10

Replace:
```
{% firstof breadcrumb_category ad.category as current_cat %}
```
With:
```
{% with current_cat=breadcrumb_category %}
```

Both `listings()` and `ad_detail()` views already pass `breadcrumb_category` in their context
(commit `2a72514`). The `ad.category` fallback is no longer needed. The `{% with %}` block must
wrap the header content that uses `current_cat` (lines 78 and 135).

### 6.3 Fix RC-C: Safe Ancestor Last-Element Access

**File:** `breadcrumb.html` line 13

Remove `last_ancestor` from the `{% with %}` tag:

Before:
```
{% with ancestors=breadcrumb_category.get_ancestors last_ancestor=breadcrumb_category.get_ancestors|last %}
```

After:
```
{% with ancestors=breadcrumb_category.get_ancestors %}
```

In the ellipsis branch (lines 15-22), replace `last_ancestor` references with
`ancestors|slice:"-1:"|first`:

```
<a href="{% url 'ads:listings_category' ancestors|slice:"-1:"|first.slug %}" ...>
{{ ancestors|slice:"-1:"|first.get_name }}</a>
```

`slice:"-1:"` returns a queryset with only the last element; `first` returns it (or None).
This is safe because the `{% if ancestors|length > 2 %}` guard ensures 3+ ancestors exist.

---

## 7. API & Data Contracts

No changes — all fixes are template-level.

---

## 8. Test Strategy

### Template source assertions (no DB)
- `test_autocomplete_template.py`: assert `get_children.exists` present, `get_children_count` absent, `firstof` absent, `ancestors` with `slice` present, `get_ancestors|last` absent.
- `test_detail_context.py`: assert safe breadcrumb patterns in `breadcrumb.html`.

### Runtime rendering tests (Docker test DB)
- `test_breadcrumbs_render.py`: GET category page, assert "???????" + category name in breadcrumb.
  GET ad detail, assert category path. GET home, assert no error.
- `test_submenu.py`: assert expand button present for categories with children, absent for leaf.

---

## 9. Acceptance Criteria

| AC | Verification |
|---|---|
| AC-01: Expand buttons render for categories with children | test + manual |
| AC-02: No expand buttons for leaf categories | test + manual |
| AC-03: Breadcrumb shows path on root category pages | test |
| AC-04: Breadcrumb shows full ancestor chain on child pages | test |
| AC-05: Breadcrumb shows category path on ad detail | test |
| AC-06: Breadcrumb renders empty (no crash) on home | test |
| AC-07: No template exceptions on any page | HTTP 200 + log check |
| AC-08: Existing tests pass | full suite + lint + typecheck |

---

## 10. Dependencies

T1 (RC-A) first. T2 and T3 in parallel. T4 after all fixes. T5 after T4.
