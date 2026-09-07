---
id: block-2-implementation-requirements
source: "Block 2 specification handoff — Spec 19 (search-term-preservation-on-category-switch), T2 + T3"
status: Ready for implementation
date: 2026-09-07
related:
  - docs/01-spec/url-state-preservation.md
  - .ai/problems/19_search-term-preservation-on-category-switch_spec.md
  - .ai/plans/block-1-implementation-requirements.md
  - src/backend/apps/core/templatetags/dict_tags.py
---

# Block 2 — Concrete Implementation Requirements

## 1. Overview

**Goal:** When a buyer is on the search results page (`/search/?q=...`), clicking a
breadcrumb link (Home or ancestor category) or the "Did you mean:" category
suggestion must navigate to `/search/?q=<existing>&category=<slug>&...`
(refining the search within that category) rather than to `/category/<slug>/`
(which routes to the `listings()` view, which ignores `q`).

When no search query is active (listings / ad-detail pages), the current behavior
is preserved: links route to `/category/<slug>/` (or `/` for Home).

**Scope:** This block covers **T2** (`breadcrumb.html`) and **T3** (`ad_list.html`
did-you-mean). Block 1 already covered T1 (`header_catalog.html` dropdown + JS
handlers) and T5 (`recomputeCategoryLinks()` shared helper).

**Discriminator:** the `query` template context variable.
- `listings.py:448` sets `"query": None` → falsy → listings mode.
- `search.py:274` sets `"query": query` (stripped `q` from GET) → truthy → search mode.
- On ad-detail pages, `query` is undefined → Django treats it as falsy → `{% else %}` branch.

**`query_replace` behavior (key constraint from Auditor):**
- Copies **all** of `request.GET` (dict_tags.py:74: `query = request.GET.copy()`) —
  including `q` when present.
- A `None` kwarg **removes** the param (dict_tags.py:76-78). So
  `category=None` drops the `category` key; `city=None` drops the `city` key.

**Q3=A discrepancy resolution:** Q3=A (§3 of the spec) is authoritative. The
Breadcrumb "Home" link drops **both** `category` and `city` (uses
`category=None city=None`), despite §5 T2 summary saying "drop category" only.
This is consistent with "Home = back to full search results."

---

## 2. T2 — `breadcrumb.html`: Conditional Search Routing

**File:** `src/backend/templates/components/breadcrumb.html`

**Context source:** `query` flows into this template via the include at
`header_catalog.html:164`:
```django
{% include "components/breadcrumb.html" with breadcrumb_category=current_cat %}
```
The `{% include %}` does **not** use `only`, so the full template context
(including `query` from `listings.py`/`search.py`) is available. No explicit
context pass is needed.

**Pattern:** Follow the exact same `{% if query %}...{% else %}...{% endif %}`
discriminator pattern already established in Block 1 (`header_catalog.html:95`,
`header_catalog.html:178`).

### 2.1 Home link (L15)

**Current code:**
```django
        <a href="{% url 'ads:listings' %}?{% query_replace request city=request.current_city lang=LANGUAGE_CODE %}" class="hover:text-blue-600">{% trans "Home" %}</a>
```

**Required change — wrap in `{% if query %}...{% else %}...{% endif %}`:**

| Branch | `href` template |
|--------|-----------------|
| `{% if query %}` (search page) | `{% url 'search:search' %}?{% query_replace request page=1 category=None city=None lang=LANGUAGE_CODE %}` |
| `{% else %}` (listings / detail) | `{% url 'ads:listings' %}?{% query_replace request city=request.current_city lang=LANGUAGE_CODE %}` (unchanged) |

**Exact replacement:**
```django
        {% if query %}
        <a href="{% url 'search:search' %}?{% query_replace request page=1 category=None city=None lang=LANGUAGE_CODE %}" class="hover:text-blue-600">{% trans "Home" %}</a>
        {% else %}
        <a href="{% url 'ads:listings' %}?{% query_replace request city=request.current_city lang=LANGUAGE_CODE %}" class="hover:text-blue-600">{% trans "Home" %}</a>
        {% endif %}
```

**Key details for the Home link:**
- `category=None` → removes `category` from the query string (Home = "back to full search").
- `city=None` → removes `city` from the query string (per Q3=A, Home drops both).
- `page=1` → resets pagination (the buyer might be on page 2+ of search results).
- `q` → auto-preserved by `request.GET.copy()` — no explicit `q` reference needed.
- `lang=LANGUAGE_CODE` → always injected (i18n gate, project rule #16).
- The `{% else %}` branch is **unchanged** — no `page=1` (matches current behavior for listings home).

### 2.2 Ancestor link — `ancestors.0.slug` (L19-21)

**Current code:**
```django
                <a href="{% url 'ads:listings_category' ancestors.0.slug %}?{% query_replace request page=1 city=request.current_city lang=LANGUAGE_CODE %}"
                   data-category-link="{{ ancestors.0.slug }}"
                   class="hover:text-blue-600">{{ ancestors.0|get_category_name:LANGUAGE_CODE }}</a>
```

**Required change — wrap in `{% if query %}...{% else %}...{% endif %}`:**

| Branch | `href` template |
|--------|-----------------|
| `{% if query %}` (search page) | `{% url 'search:search' %}?{% query_replace request page=1 category=ancestors.0.slug city=request.current_city lang=LANGUAGE_CODE %}` |
| `{% else %}` (listings / detail) | `{% url 'ads:listings_category' ancestors.0.slug %}?{% query_replace request page=1 city=request.current_city lang=LANGUAGE_CODE %}` (unchanged) |

**Exact replacement:**
```django
                {% if query %}
                <a href="{% url 'search:search' %}?{% query_replace request page=1 category=ancestors.0.slug city=request.current_city lang=LANGUAGE_CODE %}"
                   data-category-link="{{ ancestors.0.slug }}"
                   class="hover:text-blue-600">{{ ancestors.0|get_category_name:LANGUAGE_CODE }}</a>
                {% else %}
                <a href="{% url 'ads:listings_category' ancestors.0.slug %}?{% query_replace request page=1 city=request.current_city lang=LANGUAGE_CODE %}"
                   data-category-link="{{ ancestors.0.slug }}"
                   class="hover:text-blue-600">{{ ancestors.0|get_category_name:LANGUAGE_CODE }}</a>
                {% endif %}
```

**Key details for ancestor links:**
- `category=ancestors.0.slug` → **sets** the category to the ancestor (replaces current category in the search).
- `city=request.current_city` → **preserves** the city (per Q3=A, ancestor links preserve `q+city`).
- `q` → auto-preserved by `request.GET.copy()`.
- All non-href attributes (`data-category-link`, CSS classes, text content) are **duplicated identically** in both branches.

### 2.3 Last ancestor link — `last_ancestor.slug` (L26-28)

**Current code:**
```django
                    <a href="{% url 'ads:listings_category' last_ancestor.slug %}?{% query_replace request page=1 city=request.current_city lang=LANGUAGE_CODE %}"
                       data-category-link="{{ last_ancestor.slug }}"
                       class="hover:text-blue-600">{{ last_ancestor|get_category_name:LANGUAGE_CODE }}</a>
```

**Required change — wrap in `{% if query %}...{% else %}...{% endif %}`:**

| Branch | `href` template |
|--------|-----------------|
| `{% if query %}` (search page) | `{% url 'search:search' %}?{% query_replace request page=1 category=last_ancestor.slug city=request.current_city lang=LANGUAGE_CODE %}` |
| `{% else %}` (listings / detail) | `{% url 'ads:listings_category' last_ancestor.slug %}?{% query_replace request page=1 city=request.current_city lang=LANGUAGE_CODE %}` (unchanged) |

**Exact replacement:**
```django
                    {% if query %}
                    <a href="{% url 'search:search' %}?{% query_replace request page=1 category=last_ancestor.slug city=request.current_city lang=LANGUAGE_CODE %}"
                       data-category-link="{{ last_ancestor.slug }}"
                       class="hover:text-blue-600">{{ last_ancestor|get_category_name:LANGUAGE_CODE }}</a>
                    {% else %}
                    <a href="{% url 'ads:listings_category' last_ancestor.slug %}?{% query_replace request page=1 city=request.current_city lang=LANGUAGE_CODE %}"
                       data-category-link="{{ last_ancestor.slug }}"
                       class="hover:text-blue-600">{{ last_ancestor|get_category_name:LANGUAGE_CODE }}</a>
                    {% endif %}
```

### 2.4 Cat-loop ancestor link — `cat.slug` (L34-36)

**Current code:**
```django
                    <a href="{% url 'ads:listings_category' cat.slug %}?{% query_replace request page=1 city=request.current_city lang=LANGUAGE_CODE %}"
                       data-category-link="{{ cat.slug }}"
                       class="hover:text-blue-600">{{ cat|get_category_name:LANGUAGE_CODE }}</a>
```

**Required change — wrap in `{% if query %}...{% else %}...{% endif %}`:**

| Branch | `href` template |
|--------|-----------------|
| `{% if query %}` (search page) | `{% url 'search:search' %}?{% query_replace request page=1 category=cat.slug city=request.current_city lang=LANGUAGE_CODE %}` |
| `{% else %}` (listings / detail) | `{% url 'ads:listings_category' cat.slug %}?{% query_replace request page=1 city=request.current_city lang=LANGUAGE_CODE %}` (unchanged) |

**Exact replacement:**
```django
                    {% if query %}
                    <a href="{% url 'search:search' %}?{% query_replace request page=1 category=cat.slug city=request.current_city lang=LANGUAGE_CODE %}"
                       data-category-link="{{ cat.slug }}"
                       class="hover:text-blue-600">{{ cat|get_category_name:LANGUAGE_CODE }}</a>
                    {% else %}
                    <a href="{% url 'ads:listings_category' cat.slug %}?{% query_replace request page=1 city=request.current_city lang=LANGUAGE_CODE %}"
                       data-category-link="{{ cat.slug }}"
                       class="hover:text-blue-600">{{ cat|get_category_name:LANGUAGE_CODE }}</a>
                    {% endif %}
```

### 2.5 `breadcrumb.html` — Full Resulting Template

After all four changes, `breadcrumb.html` should look like:

```django
{% comment %} Breadcrumb trail for the shared catalog header.
   Renders the category ancestor chain (root -> leaf) with the last segment as
   plain text, using "›" separators. On search queries the query text is shown
   separately below the trail. On the home page (no category, no query) nothing
   is rendered.

   Expects ``breadcrumb_category`` (a Category or None) and ``query`` in the
include context. {% endcomment %}
{% load i18n %}
{% load localized_content %}
{% load dict_tags %}
<nav aria-label="{% trans "Breadcrumb" %}"
     class="mt-3 flex flex-wrap items-center text-sm text-gray-500">
    {% if breadcrumb_category %}
        {% if query %}
        <a href="{% url 'search:search' %}?{% query_replace request page=1 category=None city=None lang=LANGUAGE_CODE %}" class="hover:text-blue-600">{% trans "Home" %}</a>
        {% else %}
        <a href="{% url 'ads:listings' %}?{% query_replace request city=request.current_city lang=LANGUAGE_CODE %}" class="hover:text-blue-600">{% trans "Home" %}</a>
        {% endif %}
        <span class="mx-1 text-gray-400">&rsaquo;</span>
        {% with ancestors=breadcrumb_category.get_ancestors %}
            {% if ancestors|length > 2 %}
                {% if query %}
                <a href="{% url 'search:search' %}?{% query_replace request page=1 category=ancestors.0.slug city=request.current_city lang=LANGUAGE_CODE %}"
                   data-category-link="{{ ancestors.0.slug }}"
                   class="hover:text-blue-600">{{ ancestors.0|get_category_name:LANGUAGE_CODE }}</a>
                {% else %}
                <a href="{% url 'ads:listings_category' ancestors.0.slug %}?{% query_replace request page=1 city=request.current_city lang=LANGUAGE_CODE %}"
                   data-category-link="{{ ancestors.0.slug }}"
                   class="hover:text-blue-600">{{ ancestors.0|get_category_name:LANGUAGE_CODE }}</a>
                {% endif %}
                <span class="mx-1 text-gray-400">&rsaquo;</span>
                <span class="mx-1 text-gray-400">…</span>
                <span class="mx-1 text-gray-400">&rsaquo;</span>
                {% with last_ancestor=ancestors|slice:"::-1"|first %}
                    {% if query %}
                    <a href="{% url 'search:search' %}?{% query_replace request page=1 category=last_ancestor.slug city=request.current_city lang=LANGUAGE_CODE %}"
                       data-category-link="{{ last_ancestor.slug }}"
                       class="hover:text-blue-600">{{ last_ancestor|get_category_name:LANGUAGE_CODE }}</a>
                    {% else %}
                    <a href="{% url 'ads:listings_category' last_ancestor.slug %}?{% query_replace request page=1 city=request.current_city lang=LANGUAGE_CODE %}"
                       data-category-link="{{ last_ancestor.slug }}"
                       class="hover:text-blue-600">{{ last_ancestor|get_category_name:LANGUAGE_CODE }}</a>
                    {% endif %}
                {% endwith %}
                <span class="mx-1 text-gray-400">&rsaquo;</span>
                <span class="font-medium text-gray-800">{{ breadcrumb_category|get_category_name:LANGUAGE_CODE }}</span>
            {% else %}
                {% for cat in ancestors %}
                    {% if query %}
                    <a href="{% url 'search:search' %}?{% query_replace request page=1 category=cat.slug city=request.current_city lang=LANGUAGE_CODE %}"
                       data-category-link="{{ cat.slug }}"
                       class="hover:text-blue-600">{{ cat|get_category_name:LANGUAGE_CODE }}</a>
                    {% else %}
                    <a href="{% url 'ads:listings_category' cat.slug %}?{% query_replace request page=1 city=request.current_city lang=LANGUAGE_CODE %}"
                       data-category-link="{{ cat.slug }}"
                       class="hover:text-blue-600">{{ cat|get_category_name:LANGUAGE_CODE }}</a>
                    {% endif %}
                    <span class="mx-1 text-gray-400">&rsaquo;</span>
                {% endfor %}
                <span class="font-medium text-gray-800">{{ breadcrumb_category|get_category_name:LANGUAGE_CODE }}</span>
            {% endif %}
        {% endwith %}
    {% endif %}
</nav>
{% if query %}
    <p class="mt-1 text-sm text-gray-600">
        {% trans "Search results:" %} <span class="font-medium text-gray-800">{{ query }}</span>
    </p>
{% endif %}
```

---

## 3. T3 — `ad_list.html`: Conditional Search Routing for Did-You-Mean

**File:** `src/backend/templates/ads/partials/ad_list.html`

**Context source:** `query` is in the context for both `listings()` (L448: `None`)
and `search()` (L274: the query string). The did-you-mean block is gated by
`{% if suggested_category %}` (L17), which is only set when `search()` detects
a fuzzy category match.

### 3.1 Did-you-mean category link (L20-21)

**Current code:**
```django
            {% trans "Did you mean:" %} <a href="{% url 'ads:listings_category' suggested_category %}?{% query_replace request page=1 city=request.current_city lang=LANGUAGE_CODE %}"
class="underline font-medium">{{ suggested_category }}</a>?
```

**Required change — wrap the `<a>` element in `{% if query %}...{% else %}...{% endif %}`.**
The `{% trans "Did you mean:" %}` prefix and the `?` suffix stay **outside** the
conditional in both branches.

| Branch | `href` template |
|--------|-----------------|
| `{% if query %}` (search page) | `{% url 'search:search' %}?{% query_replace request page=1 category=suggested_category city=request.current_city lang=LANGUAGE_CODE %}` |
| `{% else %}` (listings page) | `{% url 'ads:listings_category' suggested_category %}?{% query_replace request page=1 city=request.current_city lang=LANGUAGE_CODE %}` (unchanged) |

**Exact replacement** (replace L20-21):
```django
            {% trans "Did you mean:" %} {% if query %}<a href="{% url 'search:search' %}?{% query_replace request page=1 category=suggested_category city=request.current_city lang=LANGUAGE_CODE %}"
class="underline font-medium">{{ suggested_category }}</a>{% else %}<a href="{% url 'ads:listings_category' suggested_category %}?{% query_replace request page=1 city=request.current_city lang=LANGUAGE_CODE %}"
class="underline font-medium">{{ suggested_category }}</a>{% endif %}?
```

**Key details for the did-you-mean link:**
- `category=suggested_category` → sets the category to the fuzzy-match suggestion.
- `city=request.current_city` → preserves the city (same as existing pattern).
- `q` → auto-preserved by `request.GET.copy()`.
- `page=1` → resets pagination.
- The `{% trans "Did you mean:" %}` text and `{{ suggested_category }}` variable
  are the same in both branches — no new visible text (i18n gate unaffected,
  project rule #16).

### 3.2 `ad_list.html` — Full Resulting Did-You-Mean Block

After the change, the block at L17–24 should look like:

```django
{% if suggested_category %}
    <div class="mb-4 p-3 bg-blue-50 rounded-lg">
        <p class="text-sm text-blue-800">
            {% trans "Did you mean:" %} {% if query %}<a href="{% url 'search:search' %}?{% query_replace request page=1 category=suggested_category city=request.current_city lang=LANGUAGE_CODE %}"
class="underline font-medium">{{ suggested_category }}</a>{% else %}<a href="{% url 'ads:listings_category' suggested_category %}?{% query_replace request page=1 city=request.current_city lang=LANGUAGE_CODE %}"
class="underline font-medium">{{ suggested_category }}</a>{% endif %}?
        </p>
    </div>
{% endif %}
```

**Note on formatting:** The `<a>` tag's `href` spans two lines (matching the original
L20–21 format). Both the `{% if query %}` and `{% else %}` branches reproduce this
two-line format identically. The `{% if query %}`, `{% else %}`, and `{% endif %}`
tags are inline (between the text prefix and the `<a>` tag) to preserve the rendered
whitespace: the space between "Did you mean:" and the link, and the `?` after the
link, are unaffected.

---

## 4. mega_submenu.html — Read Only (NOT Modified)

**File:** `src/backend/templates/categories/partials/mega_submenu.html`

No changes. The lazy-loaded submenu's bare `<a>` links (L11:
`{% url 'ads:listings_category' child.slug %}`) are already covered by the
`recomputeCategoryLinks()` JS helper (Block 1, T5), which was wired into
`loadSubmenu()` (header_catalog.html L476) and `htmx:afterSwap` (L701).

**Verification required (static):** `mega_submenu.html` child `<a>` tags must
still carry `data-category-link="{{ child.slug }}"` (L14) so the JS helper
can select and recompute them. No modification — just verify the attribute is
present.

---

## 5. Existing Test Compatibility Analysis

All tests are in `src/backend/apps/ads/tests/test_catalog_filters.py` and
`src/backend/apps/ads/tests/test_detail_context.py`. Run: `make test` (fast gate,
skips seed suite).

| Test | File:Line | Type | Why it passes unchanged |
|------|-----------|------|------------------------|
| `test_breadcrumb_links_preserve_lang_and_city` | test_catalog_filters.py:1107 | Static template source | Asserts `query_replace request page=1 city=request.current_city lang=LANGUAGE_CODE` is in `breadcrumb.html` source — still present in all `{% else %}` branches. Also asserts `data-category-link` — still present. |
| `test_no_bare_category_path_in_dropdown` | test_catalog_filters.py:1090 | Static template source | Tests `header_catalog.html` only, not `breadcrumb.html` or `ad_list.html`. Unaffected. |
| `test_did_you_mean_category_uses_query_replace` | test_catalog_filters.py:1120 | Static template source | Asserts `suggested_category %}?{% query_replace request page=1 city=request.current_city lang=LANGUAGE_CODE` is in `ad_list.html` source — still present in the `{% else %}` branch. |
| `test_ellipsis_truncation_branch_present` | test_detail_context.py:153 | Static template source | Asserts `{% if ancestors|length > 2 %}` and `{% endwith %}` in `breadcrumb.html` — not removed by Block 2 changes. |
| `test_ellipsis_literal_present` | test_detail_context.py:159 | Static template source | Asserts `>…<` in `breadcrumb.html` — unchanged. |
| `test_separator_preserved` | test_detail_context.py:164 | Static template source | Asserts `&rsaquo;` in `breadcrumb.html` — unchanged. |
| `test_breadcrumb_with_tag_no_last_ancestor` | test_detail_context.py:169 | Static template source | Asserts `last_ancestor=breadcrumb_category` and `get_ancestors|last` are **not** in `breadcrumb.html` — not introduced by Block 2. |
| `test_breadcrumb_empty_on_home` | test_breadcrumbs_render.py:144 | Integration (DB) | Home page has no `breadcrumb_category` → `{% if breadcrumb_category %}` is falsy → entire nav block skipped. The new `{% if query %}` wrappers are inside the `{% if breadcrumb_category %}` block, so they don't execute. |
| `test_breadcrumb_shows_root_category` | test_breadcrumbs_render.py:97 | Integration (DB) | `/category/business/?lang=ru` — `query` is `None` (listings view) → `{% else %}` branches execute → same output as before. |
| `test_breadcrumb_shows_ancestor_chain` | test_breadcrumbs_render.py:107 | Integration (DB) | `/category/business-commercial-real-estate/?lang=ru` — `query` is `None` → `{% else %}` branches → same output. |
| `test_breadcrumb_on_ad_detail` | test_breadcrumbs_render.py:116 | Integration (DB) | Ad detail — `query` undefined → falsy → `{% else %}` branches → same output. |
| `test_category_links_preserve_lang_and_city` | test_catalog_filters.py:1080 | Static template source | Tests `header_catalog.html` only — unaffected by Block 2. |
| `test_autocomplete_category_preserves_url_params` | test_catalog_filters.py:1132 | Static template source | Tests `header_catalog.html` JS only — unaffected. |
| `test_config_request_hook_injects_lang` | test_catalog_filters.py:1147 | Static template source | Tests `header_catalog.html` only — unaffected. |
| `test_category_with_city_and_lang` | test_catalog_filters.py:1166 | Integration (DB) | `/category/<slug>/?city=<city>&lang=ru` — listings view, `query=None` → `{% else %}` branch → same URLs. |
| `test_category_links_render_with_state` | test_catalog_filters.py:1198 | Integration (DB) | `/category/<slug>/?city=<city>&lang=ru` — listings view, `query=None` → `{% else %}` branches → `city=` and `lang=` preserved as before. |
| `test_sort_dropdown_visible_on_search_results` | test_catalog_filters.py:1219 | Integration (DB) | `/search/?q=транспорт&lang=ru` with XHR — renders `ad_list.html` partial. `query` is truthy → `{% if query %}` branch for did-you-mean renders `{% url 'search:search' %}` href. The `{% else %}` branch href string still exists in the source (for the assertion). Sort dropdown still renders. |

**Conclusion:** All existing tests pass as-is. No test modifications required.

---

## 6. Acceptance Criteria

1. ✅ **breadcrumb.html T2 — Home link (L15):** Wrapped in `{% if query %}...{% else %}...{% endif %}`. Search branch uses `{% url 'search:search' %}?{% query_replace request page=1 category=None city=None lang=LANGUAGE_CODE %}`.
2. ✅ **breadcrumb.html T2 — Ancestor links (L19, L26, L34):** All three ancestor links wrapped in `{% if query %}...{% else %}...{% endif %}`. Search branches use `{% url 'search:search' %}?{% query_replace request page=1 category=<respective-slug> city=request.current_city lang=LANGUAGE_CODE %}`.
3. ✅ **ad_list.html T3 — Did-you-mean link (L20-21):** Wrapped in `{% if query %}...{% else %}...{% endif %}`. Search branch uses `{% url 'search:search' %}?{% query_replace request page=1 category=suggested_category city=request.current_city lang=LANGUAGE_CODE %}`.
4. ✅ **All `{% else %}` branches are byte-identical to current code:** The `href` template tags, attributes, and text content in each `{% else %}` branch match the current source exactly.
5. ✅ **`mega_submenu.html` NOT modified** — read-only verification only.
6. ✅ **No new visible text** — all `{% trans %}` / variable content is duplicated identically in both branches. i18n gate unaffected.
7. ✅ **All existing tests pass** without modification (see §5).
8. ✅ **No new dependencies** — uses only the existing `query_replace` tag and the existing `query` context variable.

---

## 7. Dependency Graph

```
T2 (breadcrumb.html conditionals)  ───┐
T3 (ad_list.html conditional)     ────┤
Block 1 (T1, T4a, T4b, T5)         ───┘  ← already complete in header_catalog.html
```

- **T2 and T3 are independent** — they touch different files and share no code-level
  dependency. They can be implemented and reviewed independently.
- **Both depend on Block 1** (T5: `recomputeCategoryLinks()` JS helper) being in place
  — this is already done. The JS helper handles `mega_submenu.html` and
  `header_catalog.html` link recompute after HTMX swaps; T2 and T3 only add the
  server-side template conditionals.
- **No database migrations** required.
- **No view changes** required — `query` context variable already exists in both
  `listings.py` (set to `None`) and `search.py` (set to the query string).

**Recommended implementation order:** T2 → T3 (or in parallel, since they are
independent). Both can be done in a single commit.

---

## 8. Implementation Checklist

### T2 — `breadcrumb.html` (4 links)

- [ ] L15: Home link — add `{% if query %}...{% else %}...{% endif %}` wrapper
  - `{% if query %}` branch: `{% url 'search:search' %}?{% query_replace request page=1 category=None city=None lang=LANGUAGE_CODE %}`
  - `{% else %}` branch: unchanged (`{% url 'ads:listings' %}?{% query_replace request city=request.current_city lang=LANGUAGE_CODE %}`)
- [ ] L19-21: `ancestors.0.slug` link — add conditional wrapper
  - `{% if query %}` branch: `{% url 'search:search' %}?{% query_replace request page=1 category=ancestors.0.slug city=request.current_city lang=LANGUAGE_CODE %}`
  - `{% else %}` branch: unchanged
- [ ] L26-28: `last_ancestor.slug` link — add conditional wrapper
  - `{% if query %}` branch: `{% url 'search:search' %}?{% query_replace request page=1 category=last_ancestor.slug city=request.current_city lang=LANGUAGE_CODE %}`
  - `{% else %}` branch: unchanged
- [ ] L34-36: `cat.slug` link (in for-loop) — add conditional wrapper
  - `{% if query %}` branch: `{% url 'search:search' %}?{% query_replace request page=1 category=cat.slug city=request.current_city lang=LANGUAGE_CODE %}`
  - `{% else %}` branch: unchanged

### T3 — `ad_list.html` (1 link)

- [ ] L20-21: Did-you-mean category link — add `{% if query %}...{% else %}...{% endif %}` wrapper around the `<a>` element only
  - `{% trans "Did you mean:" %}` prefix and `?` suffix stay outside the conditional
  - `{% if query %}` branch: `{% url 'search:search' %}?{% query_replace request page=1 category=suggested_category city=request.current_city lang=LANGUAGE_CODE %}`
  - `{% else %}` branch: unchanged
  - `{{ suggested_category }}` variable text identical in both branches

### Verification

- [ ] Run fast gate: `$dc run --rm --env PYTEST_SKIP_MARKERS=seed test`
- [ ] Static template-source assertions pass:
  - `test_breadcrumb_links_preserve_lang_and_city`
  - `test_did_you_mean_category_uses_query_replace`
  - `test_no_bare_category_path_in_dropdown`
  - `test_ellipsis_truncation_branch_present`
  - `test_ellipsis_literal_present`
  - `test_separator_preserved`
  - `test_breadcrumb_with_tag_no_last_ancestor`
- [ ] Integration tests pass:
  - `test_breadcrumb_shows_root_category`
  - `test_breadcrumb_shows_ancestor_chain`
  - `test_breadcrumb_on_ad_detail`
  - `test_breadcrumb_empty_on_home`
  - `test_category_with_city_and_lang`
  - `test_category_links_render_with_state`
  - `test_sort_dropdown_visible_on_search_results`
- [ ] Verify `mega_submenu.html` is **not** modified (git diff check)
- [ ] Run lint: `uv run ruff check src/backend/templates/` (djlint for templates)
- [ ] No i18n extraction needed (no new `{% trans %}` strings)

---

## 9. Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| **Django `None` kwarg in `query_replace`** — `category=None` in a Django template `{% query_replace %}` call: the template engine passes `None` as a Python `None` value, and `dict_tags.py:76` checks `if value is None`. This is correct and tested (`test_query_replace_none_value_removes_param`). | Search branch Home link may not drop `category`/`city` if the tag doesn't handle `None` | Already tested in `test_templates.py:181-196`. The `{% if query %}` only renders when `q` is active (search view), so `None` is only passed in the search context where it works correctly. |
| **Ad-detail page has no `query` in context** — `breadcrumb.html` is included from `header_catalog.html` on `detail.html`, but `ad_detail()` doesn't set `query` in its context. | `{% if query %}` would be falsy → `{% else %}` branch → correct (listings behavior) | This is the **desired** behavior: breadcrumb on a detail page should go to `/category/<slug>/`, not `/search/`. Django treats undefined template variables as falsy in `{% if %}`. |
| **`q` not in `query_replace` output** — buyer on `/search/?q=лодки` clicks Home in breadcrumb; the search branch uses `category=None city=None` but doesn't explicitly set `q`. | Search term could be lost | `query_replace` copies `request.GET` (which includes `q` on the search page). The `q` param is auto-preserved. Confirmed by `test_query_replace_preserves_existing_params` and `test_query_replace_none_value_removes_param`. |
| **Favorites view renders `ad_list.html` without `query`** — `favorites_list()` doesn't set `query` in context. | `{% if query %}` falsy → did-you-mean uses `{% else %}` branch → correct (listings URL) | On favorites page, `suggested_category` is also not set, so the `{% if suggested_category %}` block doesn't render at all. No issue. |

---

## 10. Reference: Block 1 Pattern (Already Implemented)

The exact pattern to follow is in `header_catalog.html:95-107` (desktop dropdown):

```django
{% if query %}
<a href="{% url 'search:search' %}?{% query_replace request page=1 category=cat.slug city=request.current_city lang=LANGUAGE_CODE %}"
   data-category-link="{{ cat.slug }}"
   class="block flex-1 px-4 py-2.5 text-sm text-gray-700 hover:bg-blue-50 hover:text-blue-700">
    {{ cat|get_category_name:LANGUAGE_CODE }}
</a>
{% else %}
<a href="{% url 'ads:listings_category' cat.slug %}?{% query_replace request page=1 city=request.current_city lang=LANGUAGE_CODE %}"
   data-category-link="{{ cat.slug }}"
   class="block flex-1 px-4 py-2.5 text-sm text-gray-700 hover:bg-blue-50 hover:text-blue-700">
    {{ cat|get_category_name:LANGUAGE_CODE }}
</a>
{% endif %}
```

**Key principle:** The `{% if query %}` branch uses `{% url 'search:search' %}`
with `category=<slug>` in `query_replace`. The `{% else %}` branch preserves the
original `{% url 'ads:listings_category' <slug> %}` URL. All non-href attributes
are duplicated identically in both branches.
