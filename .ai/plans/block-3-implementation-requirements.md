---
id: block-3-implementation-requirements
source: "Block 3 specification handoff"
status: Ready for implementation
date: 2026-09-07
related:
  - .ai/problems/19_search-term-preservation-on-category-switch_spec.md
---

# Block 3 — Test Updates for Search-Term Preservation (T6 + T7)

## Overview

Enhance existing static-source tests (T6) and add new tests (T7) to cover the
search-term preservation feature implemented in Blocks 1–2.

## T6 — Enhance Existing Static-Source Tests (test_catalog_filters.py)

All enhancements add assertions to existing methods in `TestFilterUrlReset`:

| Test | Line | Add assertions |
|------|------|----------------|
| `test_category_links_preserve_lang_and_city` | L1080 | `{% url 'search:search' %}` in header_catalog.html |
| `test_no_bare_category_path_in_dropdown` | L1090 | `{% if query %}` + `{% url 'search:search' %}` in header_catalog.html |
| `test_breadcrumb_links_preserve_lang_and_city` | L1107 | `{% url 'search:search' %}` + `{% if query %}` in breadcrumb.html |
| `test_did_you_mean_category_uses_query_replace` | L1120 | `{% if query %}` + `{% url 'search:search' %}` in ad_list.html |
| `test_autocomplete_category_preserves_url_params` | L1132 | `url.searchParams.get('q')` + `url.searchParams.set('category', slug)` in header_catalog.html |
| `test_after_swap_recomputes_category_links` | L1155 | `recomputeCategoryLinks` + `get('q')` in header_catalog.html |

## T7 — Add New Tests

### T7a — Template-level static assertions (test_catalog_filters.py, TestFilterUrlReset)

New method `test_search_page_routes_category_links_to_search_engine`:
- Reads header_catalog.html, breadcrumb.html, ad_list.html
- Asserts each has `{% if query %}` + `{% url 'search:search' %}?{% query_replace`

### T7b — Integration: FTS + category coexistence (test_search_view.py, TestSearchViewDescendantCategories)

New method `test_q_and_category_coexist`:
- Uses fixtures: `seller`, `root_category`, `child_category`, `other_category`, `city`
- Creates ads with matching title in root_category, child_category, other_category
- Creates one ad in root_category with non-matching title
- GET `/search/?q=красный телевизор&category={root_category.slug}&lang=ru` (two-word q avoids fuzzy category match)
- Asserts: `context["query"]`, `context["current_category"]`, results = only root + child ads (2 total)

### T7c — Integration: rendered category links on search page (test_catalog_filters.py, TestFilterUrlReset)

New method `test_search_page_category_links_preserve_q`:
- Uses fixtures: `seller`, `category`, `city` (conftest root category fixture)
- GET `/search/?q=boats&city={city.slug}&lang=ru` (non-HTMX full page)
- Parses HTML for `href` values adjacent to `data-category-link`
- Asserts: each href starts with `/search/?q=boats`, contains `category=`, does NOT start with `/category/`

## Constraints
- `pytestmark` in test_catalog_filters.py: `[django_db, integration]` — integration tests are fine
- test_search_view.py: `pytestmark = [django_db, slow, integration]` — included in fast gate (only `seed` is skipped)
- Use `Accept-Language: en` where asserting on English UI strings
- `query_replace` returns `urlencode()` output; HTML auto-escaping converts `&` → `&amp;` in href attributes
- Two-word query (`красный телевизор`) avoids the single-word fuzzy category match path in search.py L192-199
