# Implementation Plan: Catalog Menu & Breadcrumbs Fix (Corrective)

**Plan ID:** `22_catalog-menu-breadcrumb-fixes_plan`
**Source Spec:** `.ai/problems/22_catalog-menu-breadcrumb-fixes_spec.md` (Spec_022 — APPROVED)
**Source Problem:** `.ai/problems/Decision_021.md`
**Date:** 2026-08-20
**Status:** Ready for implementation

---

## 1. Summary

Three template-level root causes prevent breadcrumbs and menu expansion from working,
despite commit `2a72514` implementing the correct accordion JS:

1. **RC-A:** `{% if cat.get_children_count %}` — method doesn't exist; always False;
   no expand buttons render anywhere.
2. **RC-B:** `{% firstof breadcrumb_category ad.category as current_cat %}` — Django's
   `FirstOfNode` calls `str()` before storing; `current_cat` is a string, not a Category.
3. **RC-C:** `...get_ancestors|last` in `{% with %}` — `|last` raises `ValueError` on
   empty queryset (root categories).

All fixes are template-only — no schema changes, no new endpoints, no JS changes.

---

## 2. Execution DAG

```
Phase 1 — Independent template fixes (parallel):
+-- tsk_01 - Fix get_children_count ? get_children.exists (RC-A)
+-- tsk_02 - Fix firstof ? with (RC-B)
+-- tsk_03 - Fix |last on empty queryset (RC-C)

Phase 2 — Tests (parallel):
+-- tsk_04 - Template source assertions (no DB)
+-- tsk_05 - Runtime rendering tests (Docker test DB)

Phase 3 — Verification:
+-- tsk_06 - Run full test suite + lint + typecheck + manual browser check
```

Dependency rationale:
- T1, T2, T3 are independent (disjoint template lines/sections).
- T4/T5 depend on all template fixes being in place.
- T6 depends on T4, T5.

---

## 3. Risk Assessment

| Task | Risk | Notes |
|---|---|---|
| tsk_01 | Low | Single string replacement in template condition. `get_children.exists` verified working in shell. |
| tsk_02 | Medium | Wrapping template content in {% with %} changes template structure. Must ensure all usages of current_cat are inside the block. Mitigation: template source test for firstof absence. |
| tsk_03 | Low | Removing last_ancestor from with-tag; using slice:"-1:"|first in guarded branch. Safe because {% if ancestors|length > 2 %} ensures non-empty. |
| tsk_04 | Low | New assertions in existing test files; no existing tests modified. |
| tsk_05 | Medium | Requires Docker test DB with seeded categories. Uses existing test DB on port 5433. |
| tsk_06 | N/A | Verification only. |

No schema changes, no config changes, no endpoint changes — every fix is template-source only.

---

## 4. Task Specifications

### tsk_01: Fix get_children_count -> get_children.exists (RC-A)

**Priority:** P0
**Type:** implementation
**Depends on:** none
**Risk:** low

**Affected files:**
- `src/backend/templates/components/header_catalog.html` (lines 94, 159)
- `src/backend/templates/categories/partials/mega_submenu.html` (line 16)

**Changes:**

1. `header_catalog.html` line 94:
   ```
   {% if cat.get_children_count %}
   ```
   ?
   ```
   {% if cat.get_children.exists %}
   ```

2. `header_catalog.html` line 159:
   ```
   {% if cat.get_children_count %}
   ```
   ?
   ```
   {% if cat.get_children.exists %}
   ```

3. `mega_submenu.html` line 16:
   ```
   {% if child.get_children_count %}
   ```
   ?
   ```
   {% if child.get_children.exists %}
   ```

**Acceptance criteria:**
- No occurrence of `get_children_count` in any template file.
- `get_children.exists` appears exactly 3 times (2 in header_catalog.html, 1 in mega_submenu.html).
- Shell-verified: returns True for categories with children, False for leaf categories.

---

### tsk_02: Fix firstof stringification (RC-B)

**Priority:** P0
**Type:** implementation
**Depends on:** none (parallel with tsk_01)
**Risk:** medium

**Affected file:** `src/backend/templates/components/header_catalog.html`

**Current (line 10):**
```django
{% firstof breadcrumb_category ad.category as current_cat %}
```

**Replacement:**
```django
{% with current_cat=breadcrumb_category %}
```

**Implementation steps:**
1. Replace line 10 with the `{% with %}` tag.
2. The `{% with %}` block must wrap all content that references `current_cat`.
   Currently `current_cat` is used on line 78 (dropdown label) and line 135
   (breadcrumb include). The `{% with %}` must open at line 10 and close after
   line 136 (after the header content).

   The header content structure is:
   ```
   Line 10: {% firstof ... %}
   Line 11: <header ...>
   ...
   Line 135:     {% include "components/breadcrumb.html" with breadcrumb_category=current_cat %}
   Line 136: </header>
   ```

   The fix wraps lines 11-136 inside the `{% with %}` block:
   ```
   {% with current_cat=breadcrumb_category %}
       <header ...>
           ... (all existing content) ...
       </header>
   {% endwith %}
   ```

3. Both `listings()` and `ad_detail()` views already pass `breadcrumb_category`
   in their context (verified via source code trace and commit `2a72514`).

**Acceptance criteria:**
- No occurrence of `firstof` in `header_catalog.html`.
- `{% with current_cat=breadcrumb_category %}` appears at the top of the header section.
- `current_cat` is available where used (line 78, 135).
- `ad_detail` context passes `breadcrumb_category` (already done in commit `2a72514`).

---

### tsk_03: Fix |last on empty queryset (RC-C)

**Priority:** P0
**Type:** implementation
**Depends on:** none (parallel with tsk_01)
**Risk:** low

**Affected file:** `src/backend/templates/components/breadcrumb.html`

**Change 1 — Remove `last_ancestor` from with-tag (line 13):**

Before:
```django
{% with ancestors=breadcrumb_category.get_ancestors last_ancestor=breadcrumb_category.get_ancestors|last %}
```

After:
```django
{% with ancestors=breadcrumb_category.get_ancestors %}
```

**Change 2 — Replace `last_ancestor` references in the ellipsis branch (line 19):**

Before:
```django
<a href="{% url 'ads:listings_category' last_ancestor.slug %}" class="hover:text-blue-600">{{ last_ancestor.get_name }}</a>
```

After (bind the last ancestor safely inside the length-guarded branch):
```django
{% with last_ancestor=ancestors|slice:"::-1"|first %}
<a href="{% url 'ads:listings_category' last_ancestor.slug %}" class="hover:text-blue-600">{{ last_ancestor.get_name }}</a>
{% endwith %}
```

**Why this is safe:**
- The `{% if ancestors|length > 2 %}` guard on line 14 ensures we only reach the
  ellipsis branch when there are 3+ ancestors.
- `ancestors|slice:"::-1"` returns a reversed queryset; `|first` selects the
  original last element (the immediate ancestor of the current category).
- `|first` returns that element (or None for empty, but the guard prevents empty).
- `ancestors|length` calls `len()` on the queryset, which works for both empty and
  non-empty querysets (unlike `|last`).

> **Implementation note (deviation from literal plan):** The plan's original text used
> `ancestors|slice:"-1:"|first.slug`. This is **not valid** Django template syntax:
> (1) a filter chain cannot be followed by an attribute access (`|first.slug` raises
> `TemplateSyntaxError`), and (2) `slice:"-1:"` on a QuerySet does **not** select the
> last element — a negative lower bound is treated as the whole queryset. Both points
> were verified empirically at runtime. The corrected pattern binds the last element
> via a nested `{% with last_ancestor=ancestors|slice:"::-1"|first %}` inside the
> length-guarded branch, then accesses `.slug` / `.get_name` normally.

**Acceptance criteria:**
- No occurrence of `get_ancestors|last` in `breadcrumb.html`.
- `slice:"::-1"|first` appears in the ellipsis branch (bound via `{% with %}`).
- Root categories (0 ancestors): `{% with ancestors=...get_ancestors %}` resolves to
  empty queryset; `{% if ancestors|length > 2 %}` is False; `{% else %}` branch runs;
  no crash.

---

### tsk_04: Template source assertions

**Priority:** P1
**Type:** test
**Depends on:** tsk_01, tsk_02, tsk_03
**Risk:** low

**Affected files:**
- `src/backend/apps/search/tests/test_autocomplete_template.py` — extend
  `TestCatalogMenuAccordionTemplate`
- `src/backend/apps/ads/tests/test_detail_context.py` — extend
  `TestBreadcrumbEllipsisTemplate`

**New assertions in `test_autocomplete_template.py`:**

1. `test_children_exists_replaces_get_children_count_in_header`:
   Assert `get_children.exists` present in `header_catalog.html`.
   Assert `get_children_count` NOT present in `header_catalog.html`.

2. `test_children_exists_replaces_get_children_count_in_submenu`:
   Assert `get_children.exists` present in `mega_submenu.html`.
   Assert `get_children_count` NOT present in `mega_submenu.html`.

3. `test_firstof_replaced_with_with_tag`:
   Assert `firstof` NOT present in `header_catalog.html`.
   Assert `with current_cat=breadcrumb_category` present.

4. `test_breadcrumb_uses_safe_last_element_access`:
   Assert `get_ancestors|last` NOT present in `breadcrumb.html`.
   Assert `slice:"::-1"|first` present in `breadcrumb.html`.

**New assertions in `test_detail_context.py`:**

5. `test_breadcrumb_with_tag_no_last_ancestor`:
   Assert `last_ancestor=breadcrumb_category` NOT present in `breadcrumb.html`.

**Acceptance criteria:**
- All 5 new assertions pass.
- Existing tests in both files still pass unchanged.

---

### tsk_05: Runtime rendering tests

**Priority:** P1
**Type:** test
**Depends on:** tsk_01, tsk_02, tsk_03
**Risk:** medium

**New file:** `src/backend/apps/ads/tests/test_breadcrumbs_render.py`

**Tests (pytest with django_db, requires test DB on port 5433):**

1. `test_breadcrumb_shows_root_category`:
   GET `/category/business/` — assert response contains "???????" and "??????"
   in the breadcrumb nav. Assert HTTP 200.

2. `test_breadcrumb_shows_ancestor_chain`:
   GET `/category/business-commercial-real-estate/` — assert response contains
   "???????", "??????" (ancestor), and "???????????? ????????????" (current)
   in the breadcrumb nav. Assert HTTP 200.

3. `test_breadcrumb_on_ad_detail`:
   GET `/13/` (ad in a deep category) — assert breadcrumb nav contains
   "???????" and the ad's category name. Assert HTTP 200.

4. `test_breadcrumb_empty_on_home`:
   GET `/` — assert breadcrumb nav is empty or absent. Assert HTTP 200.

**New tests in `test_submenu.py` (extension):**

5. `test_expand_button_present_for_category_with_children`:
   GET `/categories/business/submenu/` — assert response contains
   `data-category-expand` button.

6. `test_expand_button_absent_for_leaf_category`:
   GET `/categories/ready-business/submenu/` (leaf node) — assert response
   does NOT contain `data-category-expand` button.

**Acceptance criteria:**
- All 6 tests pass with the Docker test DB.
- Test DB container name: `mko-bazuna-test-db-*` (port 5433).

---

### tsk_06: Full verification

**Priority:** P0
**Type:** verification
**Depends on:** tsk_04, tsk_05

**Verification steps:**

1. **Lint:** `uv run ruff check src/backend`

2. **Typecheck:** `uv run basedpyright src/backend`

3. **Tests (Docker):**
   ```bash
   docker compose --project-name mko-bazuna-test -f docker-compose.yml -f docker-compose.test.yml run --rm test
   ```

4. **Manual browser verification:**
   - Open `http://localhost:8000/` — empty nav, no crash
   - Open `http://localhost:8000/category/business/` — breadcrumb: "??????? > ??????"
   - Open `http://localhost:8000/category/business-commercial-real-estate/` —
     breadcrumb: "??????? > ?????? > ???????????? ????????????"
   - Click "??? ?????????" dropdown — expand buttons visible on root categories with children
   - Click expand on "??????" — level-2 submenu loads via HTMX
   - Click expand on a level-2 category with children — level-3 submenu loads
   - Navigate back by re-clicking expand buttons — ancestors stay open

**Pass criteria:**
- All AC-01 through AC-08 from Spec_022 are satisfied.
- `ruff check` and `basedpyright` report no new issues.
- All existing tests + new tests pass.
- No `ValueError` or template exceptions in server logs.

---

## 5. Rollback Plan

Each task is a template-only change with no DB or config impact:

- tsk_01: Change `get_children.exists` back to `get_children_count`.
- tsk_02: Remove `{% with %}` wrapper, restore `{% firstof %}` line.
- tsk_03: Restore `last_ancestor` in `{% with %}`, restore `|last` usage.
- tsk_04/tsk_05: Delete new test assertions/files.

No migrations, no restarts, no data changes required for rollback.
