---
id: block-1-implementation-requirements
source: "Block 1 specification handoff"
status: Ready for implementation
date: 2026-09-07
related:
  - docs/01-spec/url-state-preservation.md
  - .ai/plans/done/17_url-state-preservation_spec_DONE.md
---

# Block 1 — Concrete Implementation Requirements

## 1. Overview

**Goal:** When a buyer is on the search results page (`/search/?q=...`), clicking a
category in the header "All Categories" dropdown or the autocomplete suggestion
should navigate to `/search/?q=<existing>&category=<slug>&...` (refining the search
within that category) rather than to `/category/<slug>/` (leaving the search).

When no search query is active (listings pages), the current behavior is preserved:
category links route to `/category/<slug>/?...`.

**Discriminator:** the `query` template context variable.
- `listings.py:448` sets `"query": None` → falsy → listings mode.
- `search.py:274` sets `"query": query` where `query = (request.GET.get("q") or "").strip()`
  → truthy when a non-empty `q` is present → search mode.

**JavaScript mirror:** `URLSearchParams(window.location.search).get('q')` — truthy
when `q` is present and non-empty. This deliberately uses `get('q')` (not
`has('q')`) to match `{% if query %}`, which treats empty `q=` as falsy.

---

## 2. T1 — Template Conditional for Root Category Links

**File:** `src/backend/templates/components/header_catalog.html`

**Current state:**
- **L95 (desktop dropdown):**
  ```django
  <a href="{% url 'ads:listings_category' cat.slug %}?{% query_replace request page=1 city=request.current_city lang=LANGUAGE_CODE %}"
     data-category-link="{{ cat.slug }}" ...>
  ```
- **L178 (mobile panel):** identical pattern.

**Concrete change:** Wrap each `<a>` in a `{% if query %}...{% else %}...{% endif %}`
conditional:

| Branch | `href` template |
|--------|-----------------|
| `{% if query %}` (search page) | `{% url 'search:search' %}?{% query_replace request page=1 category=cat.slug city=request.current_city lang=LANGUAGE_CODE %}` |
| `{% else %}` (listings page)  | `{% url 'ads:listings_category' cat.slug %}?{% query_replace request page=1 city=request.current_city lang=LANGUAGE_CODE %}` (unchanged) |

**Semantic anchor:** The `<a>` tags bearing `data-category-link="{{ cat.slug }}"`
inside the `{% for cat in root_categories %}` loops on L92–120 (desktop) and
L175–203 (mobile).

**Acceptance criteria:**
1. Both L95 and L178 `<a>` tags are wrapped in `{% if query %}...{% else %}...{% endif %}`.
2. The `{% if query %}` branch uses `{% url 'search:search' %}?{% query_replace request page=1 category=cat.slug city=request.current_city lang=LANGUAGE_CODE %}`.
3. The `{% else %}` branch preserves the existing `{% url 'ads:listings_category' cat.slug %}?{% query_replace ... %}` pattern.
4. All other attributes (`data-category-link`, CSS classes, category name display)
   are duplicated identically in both branches.
5. `test_no_bare_category_path_in_dropdown` passes: every `listings_category' cat.slug %}`
   occurrence is followed by `?{% query_replace`.
6. `test_category_links_preserve_lang_and_city` passes: the string
   `query_replace request page=1 city=request.current_city lang=LANGUAGE_CODE`
   still appears in the file.

---

## 3. T4a — `htmx:afterSwap` Handler: Add `q`-Aware Branch

**File:** `src/backend/templates/components/header_catalog.html`, L639–659

**Current state:** The handler always rewrites `[data-category-link]` hrefs to
`/category/<slug>/?<rebuilt params>`:

```javascript
window.addEventListener('htmx:afterSwap', function (e) {
    if (e.target) attachCategoryHandlers(e.target);
    var categoryLinks = document.querySelectorAll('[data-category-link]');
    if (categoryLinks.length) {
        var catParams = new URLSearchParams(window.location.search);
        catParams.set('page', '1');
        var catBase = catParams.toString();
        categoryLinks.forEach(function (link) {
            var slug = link.getAttribute('data-category-link');
            var rebuilt = new URLSearchParams(catBase);
            link.setAttribute(
                'href',
                '/category/' + encodeURIComponent(slug) + '/?' + rebuilt.toString()
            );
        });
    }
});
```

**Concrete change:** Replace the inline link-recompute block with a call to the
shared helper `recomputeCategoryLinks()` (see T5). The `q` check lives inside
that helper. The `attachCategoryHandlers(e.target)` call on L641 is preserved.

**Acceptance criteria:**
1. `htmx:afterSwap` listener still exists at L639.
2. The inline `querySelectorAll('[data-category-link]')` loop is extracted into
   the shared `recomputeCategoryLinks()` helper (called from both `afterSwap`
   and `loadSubmenu`).
3. `recomputeCategoryLinks()` uses `URLSearchParams(window.location.search).get('q')`
   (truthy check, not `has('q')`).
4. When `q` is truthy, links are built as `/search/?<params>&category=<slug>`.
5. When `q` is falsy, links are built as `/category/<slug>/?<params>` (unchanged).
6. `test_after_swap_recomputes_category_links` passes: both `htmx:afterSwap` and
   `querySelectorAll('[data-category-link]')` strings are present in the file.

---

## 4. T4b — Autocomplete Category Click Handler: Add `q`-Aware Branch

**File:** `src/backend/templates/components/header_catalog.html`, L365–373

**Current state:**

```javascript
} else if (type === 'category' && slug) {
    var url = new URL(window.location.href);
    url.pathname = '/category/' + encodeURIComponent(slug) + '/';
    url.searchParams.set('page', '1');
    window.location.href = url.toString();
}
```

**Concrete change:** Add a `url.searchParams.get('q')` check after constructing
the `URL` object. If `q` is truthy, set `pathname = '/search/'` and
`searchParams.set('category', slug)`. Otherwise, keep the existing
`/category/<slug>/` behavior.

**New logic:**

```javascript
} else if (type === 'category' && slug) {
    var url = new URL(window.location.href);
    var q = url.searchParams.get('q');
    url.searchParams.set('page', '1');
    if (q) {
        url.pathname = '/search/';
        url.searchParams.set('category', slug);
    } else {
        url.pathname = '/category/' + encodeURIComponent(slug) + '/';
    }
    window.location.href = url.toString();
}
```

**Acceptance criteria:**
1. `url.searchParams.get('q')` appears in the handler.
2. When `q` is truthy: `url.pathname = '/search/'` and
   `url.searchParams.set('category', slug)` are executed.
3. When `q` is falsy: `url.pathname = '/category/' + encodeURIComponent(slug) + '/'`
   (current behavior preserved).
4. `url.searchParams.set('page', '1')` is always executed (set before the branch).
5. `test_autocomplete_category_preserves_url_params` passes:
   - `"window.location.href = '/category/' + encodeURIComponent(slug)"` NOT present.
   - `"new URL(window.location.href)"` present.
   - `"url.pathname"` present.
   - `"url.searchParams.set('page', '1')"` present.

---

## 5. T5 — Fix `loadSubmenu` Gap: Shared Link-Recompute Helper

### 5.1 Problem

`loadSubmenu()` (L414–432) injects submenu HTML via raw `fetch` + `container.innerHTML`,
bypassing HTMX's swap cycle. Therefore `htmx:afterSwap` does **not** fire, and the
injected links from `mega_submenu.html` are never recomputed.

`mega_submenu.html` is **read-only** for this block — its links are server-rendered
as bare hrefs (`{% url 'ads:listings_category' child.slug %}`, L11 — no
`?{% query_replace %}`). The server-side cache key
(`categories/views.py:46`: `category:submenu:{tree_version}:{slug}:{locale}`)
does **not** include the query string, so a server-side conditional in the
template would be unsafe (Risk R5). The fix must be client-side.

### 5.2 Implementation Options

#### Option A — Shared named helper function (RECOMMENDED)

Extract a named function `recomputeCategoryLinks()` containing:
1. `URLSearchParams(window.location.search)` → read `get('q')` (truthy check).
2. `document.querySelectorAll('[data-category-link]')`.
3. For each link, build the href based on `q` presence (search vs. category path).

Both `loadSubmenu` (after `container.innerHTML = html`) and `afterSwap` call it.

| Criterion | Assessment |
|-----------|-----------|
| DRY | ✅ Single source of truth for link-recompute logic |
| Spec directive | ✅ Explicitly requested: "Extract a shared helper function to avoid duplication" |
| Test compatibility | ✅ `querySelectorAll('[data-category-link]')` still in file (in helper); `htmx:afterSwap` still in file |
| Maintainability | ✅ `q`-check logic lives in one place; future changes to URL format need one edit |
| Refactor risk | ⚠️ Moves code from `afterSwap` handler body into a named function — minimal behavioral change |
| Self-documenting | ✅ Named function clearly communicates intent |

#### Option B — Inline duplicate

Copy the link-recompute block into both `loadSubmenu` and `afterSwap`.

| Criterion | Assessment |
|-----------|-----------|
| DRY | ❌ Logic duplicated in two locations |
| Spec directive | ❌ Explicitly contradicts: "Extract a shared helper function to avoid duplication" |
| Test compatibility | ✅ Tests pass (string assertions match) |
| Maintainability | ❌ `q`-check logic must be updated in two places; high risk of drift |
| Refactor risk | ✅ Minimal — no restructuring of `afterSwap` |
| Self-documenting | ⚠️ Inline code in both call sites |

#### Option C — Anonymous closure assigned to a variable

Same logic as Option A but assigned to `var recomputeCategoryLinks = function() { ... }`.

| Criterion | Assessment |
|-----------|-----------|
| Same benefits as A | ✅ |
| Self-documenting | ⚠️ Slightly less clear than a named function declaration |
| Hoisting | ⚠️ Function declarations are hoisted; variable-assigned closures are not (ordering matters) |

**Decision:** **Option A** — named function declaration. It directly follows the
spec directive, is hoisted (so ordering within the IIFE is flexible), and is the
most self-documenting. The `q`-check logic appears exactly once, satisfying the
mirror requirement between `{% if query %}` (T1) and `get('q')` (T4a/T4b/T5).

### 5.3 Concrete Change

**New helper function** (placed near the existing category logic, before
`loadSubmenu`):

```javascript
function recomputeCategoryLinks() {
    var categoryLinks = document.querySelectorAll('[data-category-link]');
    if (!categoryLinks.length) return;

    var urlParams = new URLSearchParams(window.location.search);
    var hasQuery = urlParams.get('q');  // truthy check, NOT has('q')
    urlParams.set('page', '1');
    var baseParams = urlParams.toString();

    categoryLinks.forEach(function (link) {
        var slug = link.getAttribute('data-category-link');
        if (hasQuery) {
            var searchParams = new URLSearchParams(baseParams);
            searchParams.set('category', slug);
            link.setAttribute('href', '/search/?' + searchParams.toString());
        } else {
            link.setAttribute(
                'href',
                '/category/' + encodeURIComponent(slug) + '/?' + baseParams
            );
        }
    });
}
```

**Modify `loadSubmenu`** (L414–432): after `container.innerHTML = html;`
(on L422), call `recomputeCategoryLinks()`.

**Modify `afterSwap` handler** (L639–659): replace the inline
`querySelectorAll('[data-category-link]')` loop with `recomputeCategoryLinks()`.

**mega_submenu.html** (read-only): Verify that child `<a>` tags carry
`data-category-link="{{ child.slug }}"` (L14) so the helper selects them. No
modification needed — the client-side recompute fixes up the bare hrefs after
injection.

**Acceptance criteria:**
1. `recomputeCategoryLinks()` is defined as a named function declaration.
2. `recomputeCategoryLinks()` is called inside `loadSubmenu`'s `.then()`
   callback, immediately after `container.innerHTML = html;` (L422).
3. The `afterSwap` handler calls `recomputeCategoryLinks()` instead of its
   inline `querySelectorAll` loop.
4. `recomputeCategoryLinks()` uses `get('q')` (truthy), not `has('q')`.
5. When `q` is truthy, links point to `/search/?...&category=<slug>`.
6. When `q` is falsy, links point to `/category/<slug>/?...`.
7. `loadSubmenu` continues to set `aria-expanded`, rotate SVG, and handle
   errors — the helper call is additive, not a replacement.
8. `test_after_swap_recomputes_category_links` passes.
9. `mega_submenu.html` is not modified (read-only verify).

---

## 6. Dependency Graph

```
T1 (template {% if query %})  ─┐
T4a (afterSwap → shared helper)├─ T5 (extract recomputeCategoryLinks)
T4b (autocomplete q-check)  ─┘
```

- **T5 is the foundation:** The shared helper must be extracted before (or
  alongside) T4a, because T4a delegates to it. T4b is independent (self-contained
  `q`-check inline).
- **T1 is independent** of the JS changes — it's a pure template conditional.
- **No database migrations** required — all changes are in templates and inline JS.
- **No view changes** required — `query` context var already exists in both
  `listings.py` and `search.py`.

**Recommended implementation order:** T5 (extract helper + wire into
`loadSubmenu`) → T4a (delegate `afterSwap` to helper) → T4b (add `q`-check to
autocomplete handler) → T1 (template conditional). All four can be done in a
single commit since they touch the same file and share the `q`-check discipline.

---

## 7. Researcher Assessment

**Researcher is NOT needed** for this block. Justification:

1. **No framework uncertainty:** Django 5.2 template tags (`{% if %}`, `{% url %}`,
   `{% query_replace %}`) and vanilla JavaScript (`URLSearchParams`, `URL` API,
   `fetch`, HTMX 2.0.10 events) are all already in use in this exact codebase.
2. **No API lookups required:** The `query_replace` tag, `htmx:configRequest`,
   `htmx:afterSwap` are all already present and documented in the spec
   (`dict_tags.py:47`, `url-state-preservation.md` §5.4).
3. **No multiple viable architectural approaches:** The discriminator (`query`
   context var / `get('q')`), the URL formats, and the cache key behavior are all
   dictated by the auditor handoff. The only real decision (shared helper vs.
   inline duplicate for T5) is resolved by the spec directive itself.
4. **Patterns are established:** The `{% if query %}` template conditional and the
   `URLSearchParams.get('q')` truthy check are already documented patterns in this
   codebase (e.g., `clearBtn` click handler L273 uses `params.has('q') && params.get('q')`
   for a similar q-vs-not distinction).

---

## 8. Test Verification Plan

All tests are in `src/backend/apps/ads/tests/test_catalog_filters.py`.
Run: `make test` (fast gate, skips seed suite).

| Test | Line | Type | Verifies |
|------|------|------|----------|
| `test_no_bare_category_path_in_dropdown` | 1090 | Static template source | T1: all `listings_category' cat.slug %}` occurrences are followed by `?{% query_replace` |
| `test_after_swap_recomputes_category_links` | 1155 | Static template source | T4a/T5: `htmx:afterSwap` and `querySelectorAll('[data-category-link]')` present |
| `test_autocomplete_category_preserves_url_params` | 1132 | Static template source | T4b: old `window.location.href = '/category/'` concat absent; `new URL()`, `url.pathname`, `url.searchParams.set('page', '1')` present |
| `test_category_links_preserve_lang_and_city` | 1080 | Static template source | T1: `query_replace request page=1 city=request.current_city lang=LANGUAGE_CODE` present |
| `test_category_links_render_with_state` | 1198 | Integration (DB) | Category URLs carry `city=` and `lang=` on listings pages |
| `test_clear_all_preserves_search_query` | 908 | Integration (DB) | `q=` preserved in clear-all URL on search page |

**Gap note:** No test currently renders the header template with `query` set to a
truthy value and asserts that category links point to `/search/?...&category=...`.
The T1 behavior is only covered by static source assertions (the `{% if query %}`
conditional exists). Adding a behavioral test is optional but recommended for
regression safety on the search-page routing.
