# Implementation Plan: Catalog Menu & Breadcrumbs Fix

**Plan ID:** `20_catalog-menu-breadcrumb-fix_plan`
**Source Spec:** `.ai/problems/20_catalog-menu-breadcrumb-fix_spec.md` (Spec_020 — APPROVED)
**Date:** 2026-08-20
**Status:** Implementation-ready

---

## 1. Summary

Spec_020 applies two surgical fixes to the shared Avito-style catalog header
(`components/header_catalog.html`, built in Spec_014):

1. **Menu depth navigation is broken** — `mega_submenu.html` omits the `hidden`
   class on its lazy-loaded submenu container, causing the accordion's
   `collapseBranches()` to prematurely collapse the entire tree, and there is no
   back-navigation between levels.
2. **Breadcrumbs on ad-detail pages** render only "Главная" — the `ad_detail()`
   view never passes `breadcrumb_category` into the template context, and the
   breadcrumb trail lacks ellipsis truncation for long category chains.

All four implementation changes are template or view-context edits — **no schema
changes, no new endpoints, no build/deployment modifications, no public API
renames**. The HTMX `/categories/<slug>/submenu/` endpoint and the
`ad_detail` URL contract are unchanged.

---

## 2. Execution DAG

```
Phase 1 — Independent fixes (parallel, disjoint files/concerns):
├── tsk_01 ─ Fix ``hidden`` class on mega_submenu.html submenu container
└── tsk_02 ─ Pass ``breadcrumb_category`` in ad_detail() view context

Phase 2 — Dependent implementations (parallel):
├── tsk_03 ─ Redesign accordion JS in header_catalog.html  (depends on tsk_01)
└── tsk_04 ─ Implement breadcrumb ellipsis truncation in breadcrumb.html  (depends on tsk_02)

Phase 3 — Test assertions (parallel):
├── tsk_05 ─ Add test assertions for menu fix  (depends on tsk_01, tsk_03)
└── tsk_06 ─ Add test assertions for breadcrumb fix  (depends on tsk_02, tsk_04)

Phase 4 — Full verification:
└── tsk_07 ─ Run test suite + lint + typecheck + manual JS navigation trace
            (depends on tsk_05, tsk_06)
```

### Dependency rationale

| Dependency | Reason |
|---|---|
| `tsk_01 → tsk_03` | The redesigned accordion JS (`closeBranch` / `collapseSiblings`) reads `container.classList.contains('hidden')` to determine open/closed state. Without `hidden` on the `mega_submenu.html` container, `isOpen` is always `true` and `loadSubmenu()` never fires — level-3/4 are unreachable. |
| `tsk_02 → tsk_04` | The ellipsis truncation logic in `breadcrumb.html` can only be meaningfully verified on the ad-detail page once `breadcrumb_category` is passed by `ad_detail()`. Sequencing the context fix first ensures the template change is testable end-to-end. |
| `tsk_03 → tsk_05` | Menu test assertions include verifying the new JS function names (`closeBranch`, `collapseSiblings`) are present and the old `collapseBranches` is removed from `header_catalog.html` source. |
| `tsk_02, tsk_04 → tsk_06` | Breadcrumb tests assert both the context key presence (from `tsk_02`) and the ellipsis template logic (from `tsk_04`). |
| `tsk_05, tsk_06 → tsk_07` | The verification run executes the full test suite (existing + new) plus a manual 7-step navigation trace of the accordion JS (per spec §6.1, AC-01/02). |

---

## 3. Risk Assessment

| Task | Risk | Notes |
|---|---|---|
| `tsk_01` | **Low** | Single `class` attribute edit in a template partial. No config/schema/API impact. The `hidden` class is already used on the equivalent container in `header_catalog.html` (lines 104, 169), so this is a consistency fix. |
| `tsk_02` | **Low** | Additive context key in `ad_detail()`. `test_detail_context.py` uses `assertIn` — adding a key cannot break existing assertions. |
| `tsk_03` | **Medium** | Replaces client-side accordion behavior in `header_catalog.html`. **No** config/schema/build/API change. Fully specified replacement algorithm in spec §6.1 (7-step trace). Mitigation: template-source assertions + dedicated verification step with manual trace. |
| `tsk_04` | **Low** | Template-level conditional truncation using Django `slice`/length checks. No backend or view changes. |
| `tsk_05` | **Low** | New assertions in existing test files; no existing test modified. |
| `tsk_06` | **Low** | New assertions in existing test files; no existing test modified. |
| `tsk_07` | **N/A** | Verification only. |

**No research gates required.** No task modifies shared configuration, database
schema, build/deployment, startup behavior, test infrastructure, or renames/removes
public APIs. The single medium-risk item (tsk_03, JS behavior change) has a
complete, trace-verified algorithm from the spec — it is behavioral risk, not
architectural ambiguity.

---

## 4. Task Specifications

---

### tsk_01: Fix `hidden` class on mega_submenu.html submenu container

**Priority:** P0
**Type:** implementation
**Depends on:** none
**Risk:** low

**Affected files:**
- `src/backend/templates/categories/partials/mega_submenu.html`

**Affected targets:**
- The submenu container `<div>` inside the `{% for child in children %}` loop

**Semantic anchor:**
```
<div class="ml-4" data-category-submenu="{{ child.slug }}">
```
→
```
<div class="hidden ml-4" data-category-submenu="{{ child.slug }}">
```

**Changes:**
1. Add the `hidden` class to the submenu container `<div>` (the sibling of the
   `<button data-category-expand>` within each `<li>`), making it match the
   equivalent containers in `header_catalog.html` (lines 104, 169).

**Acceptance criteria:**
- The container `<div>` carries `class="hidden ml-4"`.
- No other markup in the partial is altered.

<details>
<summary>Implementation notes (from spec §3.1, R-01a)</summary>

<p>Without `hidden`, the accordion's toggle check (`!container.classList.contains('hidden')`)
evaluates to `true` on first interaction, causing `collapseBranches()` to fire and
`loadSubmenu()` to never execute. This single-class fix is the prerequisite for
the entire accordion redesign.</p>
</details>

---

### tsk_02: Pass `breadcrumb_category` in ad_detail() view context

**Priority:** P0
**Type:** implementation
**Depends on:** none (parallel with tsk_01)
**Risk:** low

**Affected files:**
- `src/backend/apps/ads/views/listings.py`

**Affected targets:**
- Function `ad_detail`, its `context` dict literal

**Semantic anchor:**
```python
context = {
    "ad": ad,
    "consent_shown": is_consent_given(request),
    "bot_username": settings.BOT_USERNAME,
    "is_favorited": (
        ad.favorites.filter(user_id=request.user.id).exists()
        if request.user.is_authenticated
        else False
    ),
}
```

**Changes:**
1. Add `"breadcrumb_category": ad.category` to the `context` dict (after `"ad": ad`).

**Acceptance criteria:**
- The context dict contains the key `breadcrumb_category` whose value is `ad.category`.
- All existing keys in the context dict remain unchanged.
- `test_detail_context.py` passes unchanged (new test in tsk_06 for the new key).

---

### tsk_03: Redesign accordion JS for back-navigation + sibling collapse

**Priority:** P0
**Type:** implementation
**Depends on:** tsk_01
**Risk:** medium — client-side behavior change (spec provides complete replacement algorithm in §6.1)

**Affected files:**
- `src/backend/templates/components/header_catalog.html`

**Affected targets (semantic):**
- `collapseBranches(panel)` function — **replace** with `closeBranch(container)` + `collapseSiblings(container)`
- The click-handler block inside `attachCategoryHandlers(panel)` — **replace** the `collapseBranches(panel); if (!isOpen && container) loadSubmenu(container);` branch

**Semantic replacement (from spec §6.1):**

Replace the `collapseBranches` function:
```javascript
function collapseBranches(panel) {
    panel.querySelectorAll('[data-category-submenu]').forEach(function (c) { c.classList.add('hidden'); });
    panel.querySelectorAll('[data-category-expand]').forEach(function (b) { b.setAttribute('aria-expanded', 'false'); });
}
```
with:
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
```

Replace the click-handler logic:
```javascript
collapseBranches(panel);
if (!isOpen && container) loadSubmenu(container);
```
with:
```javascript
if (isOpen) {
    closeBranch(container);
} else {
    collapseSiblings(container);
    loadSubmenu(container);
}
```

**Changes:**
1. Replace `collapseBranches(panel)` with `closeBranch(container)` + `collapseSiblings(container)`.
2. Update the click handler to use `closeBranch` (re-click → collapse own branch + descendants, keep ancestors) or `collapseSiblings` + `loadSubmenu` (expand → close only siblings at same level).
3. Update `closeCategories()` and `closeMobile()` to collapse branches correctly with the new function names — they currently call `collapseBranches(panel)`. Replace with a sibling-aware reset: hide all `[data-category-submenu]` containers and reset all `[data-category-expand]` buttons within the panel (this full-reset only happens on explicit panel close, so it's safe).

**Acceptance criteria:**
- `collapseBranches` function is removed from the template source.
- `closeBranch` and `collapseSiblings` functions are present.
- The 7-step navigation trace in spec §6.1 produces correct behavior (verified in tsk_07).

---

### tsk_04: Implement breadcrumb ellipsis truncation

**Priority:** P1
**Type:** implementation
**Depends on:** tsk_02
**Risk:** low — template-only conditional rendering

**Affected files:**
- `src/backend/templates/components/breadcrumb.html`

**Affected targets:**
- The `{% for cat in breadcrumb_category.get_ancestors %}` loop block

**Current template (lines 9–18):**
```django
{% if breadcrumb_category %}
    <a href="/">Главная</a>
    <span class="mx-1 text-gray-400">&rsaquo;</span>
    {% for cat in breadcrumb_category.get_ancestors %}
        <a href="{% url 'ads:listings_category' cat.slug %}" class="hover:text-blue-600">{{ cat.get_name }}</a>
        <span class="mx-1 text-gray-400">&rsaquo;</span>
    {% endfor %}
    <span class="font-medium text-gray-800">{{ breadcrumb_category.get_name }}</span>
{% endif %}
```

**Replacement logic (from spec §6.3, R-05a/b):**
```django
{% if breadcrumb_category %}
    <a href="/" class="hover:text-blue-600">Главная</a>
    <span class="mx-1 text-gray-400">&rsaquo;</span>
    {% with ancestors=breadcrumb_category.get_ancestors %}
        {% if ancestors|length > 2 %}
            <a href="{% url 'ads:listings_category' ancestors.0.slug %}" class="hover:text-blue-600">{{ ancestors.0.get_name }}</a>
            <span class="mx-1 text-gray-400">&rsaquo;</span>
            <span class="mx-1 text-gray-400">…</span>
            <span class="mx-1 text-gray-400">&rsaquo;</span>
            <a href="{% url 'ads:listings_category' ancestors.1.get_name }}" class="hover:text-blue-600">{{ ancestors|last }}</a>
            <span class="mx-1 text-gray-400">&rsaquo;</span>
            <span class="font-medium text-gray-800">{{ breadcrumb_category.get_name }}</span>
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

> **Correction to spec §6.3:** The example snippet `{{ ancestors|last:get_name }}` uses incorrect Django filter syntax. The ellipsis branch should render root (`ancestors.0`) → "…" → last ancestor (`{{ ancestors|last }}` with `.get_name`) → current category. The `last` filter is applied as `{{ ancestors|last }}` to get the object, then `.get_name` renders it.

**Changes:**
1. Wrap the ancestor loop in a `{% with ancestors=breadcrumb_category.get_ancestors %}` block.
2. Add a `{% if ancestors|length > 2 %}` branch that shows: root → "…" → last ancestor → current category (all as links except "…" and current).
3. Keep the `{% else %}` branch as the original full-chain rendering.

**Acceptance criteria:**
- When ancestor count ≤ 2 (including root and current): full chain renders as links.
- When ancestor count > 2: root + ellipsis + last ancestor + current, with the ellipsis as plain text.
- Breadcrumb separator `&rsaquo;` is preserved (PO decision Q4).
- Ad title is NOT in breadcrumbs (PO decision Q3).

---

### tsk_05: Add test assertions for menu fix

**Priority:** P1
**Type:** test
**Depends on:** tsk_01, tsk_03
**Risk:** low

**Affected files:**
- `src/backend/apps/categories/tests/test_submenu.py`
- `src/backend/apps/search/tests/test_autocomplete_template.py` (existing template source assertions)

**New test assertions (semantic targets):**

1. **In `test_submenu.py`** (or a new `SimpleTestCase`): Assert that the rendered `/categories/<slug>/submenu/` response contains `class="hidden ml-4"` with `data-category-submenu`. This verifies tsk_01.
   - Approach: read `mega_submenu.html` source directly (like `test_autocomplete_template.py`) and assert `class="hidden ml-4"` appears on a line containing `data-category-submenu`. No DB required.

2. **In a new template source test** (or extend `test_autocomplete_template.py`): Assert `header_catalog.html` contains `closeBranch` and `collapseSiblings` function definitions, and does **not** contain `collapseBranches`.

**Acceptance criteria:**
- At least one assertion verifies `hidden` class on the submenu container.
- At least one assertion verifies `closeBranch` / `collapseSiblings` are present and `collapseBranches` is absent.
- New assertions do not modify existing test methods.

---

### tsk_06: Add test assertions for breadcrumb fix

**Priority:** P1
**Type:** test
**Depends on:** tsk_02, tsk_04
**Risk:** low

**Affected files:**
- `src/backend/apps/ads/tests/test_detail_context.py`
- New test file or assertions for `breadcrumb.html` ellipsis (template source level)

**New test assertions (semantic targets):**

1. **In `test_detail_context.py`**: Add `test_detail_context_contains_breadcrumb_category` — assert `"breadcrumb_category"` is in the context dict returned by `ad_detail()`. Follows the existing `test_detail_context_contains_bot_username` pattern.

2. **Template source test for `breadcrumb.html`**: Assert the template contains the ellipsis branch (`ancestors|length`) and the `…` literal. Can be a `SimpleTestCase` that reads the file (like `test_autocomplete_template.py` pattern).

**Acceptance criteria:**
- `test_detail_context.py` includes an assertion for `breadcrumb_category` in the context.
- A template-level assertion verifies the ellipsis truncation logic is present in `breadcrumb.html`.
- Existing tests in both files continue to pass.

---

### tsk_07: Verification — full test suite + lint + manual JS trace

**Priority:** P0
**Type:** verification
**Depends on:** tsk_05, tsk_06
**Risk:** n/a

**Verification steps:**

1. **Lint:** `uv run ruff check src/backend`
2. **Typecheck:** `uv run basedpyright src/backend`
3. **Tests (Docker):** Start test DB if needed, then run:
   ```
   docker compose --project-name mko-bazuna-test -f docker-compose.yml -f docker-compose.test.yml run --rm test
   pytest \
     src/backend/apps/categories/tests/test_submenu.py \
     src/backend/apps/search/tests/test_autocomplete_template.py \
     src/backend/apps/ads/tests/test_listings_context.py \
     src/backend/apps/ads/tests/test_detail_context.py \
     -v
   ```
4. **Manual JS navigation trace** (spec §6.1, 7-step trace) — verified by the implementor:
   - Open dropdown → level-1 roots visible
   - Click expand on root A → siblings collapse; level-2 children load
   - Click expand on level-2 A1 → siblings collapse; level-3 children load; A stays open
   - Click expand on level-3 A1a → siblings collapse; level-4 children load; A, A1 stay open
   - Re-click expand on A1a → `closeBranch` closes A1a + descendants; A, A1 remain open
   - Re-click expand on A1 → `closeBranch` closes A1 + descendants; A remains open
   - Re-click expand on A → `closeBranch` closes A + descendants; level-1 roots visible

**Pass criteria:**
- All AC-01 through AC-05 from the spec are satisfied.
- `test_submenu.py` (4 tests), `test_autocomplete_template.py` (6 tests), `test_listings_context.py` (8 tests), `test_detail_context.py` (3 tests) all pass.
- New assertions from tsk_05 and tsk_06 pass.
- `ruff check` and `basedpyright` report no new issues.
- Manual JS trace confirms correct navigation at all 4 levels with back-navigation.

---

## 5. Acceptance Criteria Mapping

| AC | Verified by |
|---|---|
| AC-01: Menu depth navigation (4 levels) | tsk_01 + tsk_03 implementation; tsk_07 manual trace |
| AC-02: Back-navigation (collapse self+descendants, keep ancestors) | tsk_03 implementation; tsk_07 manual trace |
| AC-03: Breadcrumbs show full category path on ad detail | tsk_02 implementation; tsk_06 test assertion |
| AC-04: Breadcrumb ellipsis truncation | tsk_04 implementation; tsk_06 test assertion |
| AC-05: Existing tests pass (no regressions) | tsk_07 full test suite run |

---

## 6. Rollback Plan

No rollback task is required — all changes are small, isolated template/view-context edits with no database or configuration impact. Each task can be reverted independently:

- `tsk_01`: Remove `hidden` from the class on the `mega_submenu.html` container div.
- `tsk_02`: Remove the `breadcrumb_category` key from the `ad_detail()` context dict.
- `tsk_03`: Revert `header_catalog.html` JS to the `collapseBranches` function.
- `tsk_04`: Revert `breadcrumb.html` to the original `{% for %}` loop.
- `tsk_05`/`tsk_06`: Delete the new test assertions; existing tests are unmodified and unaffected.