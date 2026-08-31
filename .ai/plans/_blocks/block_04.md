# Block 4: Category Browsing & Context Scoping

## 1. Block Summary

Verifies that category-based browsing preserves category context across the URL path, applies a descendant-subtree filter on ads, constrains filter option sets via `CategoryLookupResolver`, and renders breadcrumbs reflecting the active category ancestor chain — while documenting the context-drop behavior on header search and the absence of category control on `/search/?q=`.

---

## 2. Findings Table

| # | Variation | Implementation Location | Test Coverage | Existing Test File:Line | Test-Engineer Task | Risk |
|---|-----------|------------------------|---------------|------------------------|--------------------|------|
| V1 | Category entry via `/category/<slug>/` path — category preserved, `get_descendants(include_self=True)` subtree filter applied to ad queryset. Invalid slug → did-you-mean banner. | `ads/urls.py:26` (route); `listings.py:262-274` (lookup + filter); `listings.py:276-279` (invalid → suggest) | GAP | `test_listings_context.py:176-196` (unit-level, mocked ORM — verifies `current_category` mirrors path slug and `breadcrumb_category` in context, but does NOT test actual subtree queryset filtering); `test_breadcrumbs_render.py:98-108` (integration on `/category/business/` — checks breadcrumb HTML only, not filtered results) | Integration test: create ads in a parent category and a non-descendant sibling category; GET `/category/<parent>/` with real Django Client; assert only ads whose `category` is in the parent's subtree appear in `page_obj`; assert invalid slug returns 200 with `suggested_category` set and no filter applied. | Medium |
| V2 | Category-constrained filter option sets — `resolved_purposes`/`resolved_features`/`resolved_conditions` resolved via `CategoryLookupResolver` ancestor-walk (nearest-explicit-ancestor-wins, 300s cache) when `breadcrumb_category` is active; full active lookup set fallback when no category. | `listings.py:365-386`; `search.py:119-140` | GAP | `test_catalog_filters.py:96-603` (tests filter application with purpose/feature/condition lookups, but does NOT create `CategoryListingPurpose`/`CategoryListingFeature`/`CategoryListingCondition` through-table bindings — resolver returns empty sets); `test_listings_context.py:120-164` (unit-level, mocked — does not exercise resolver) | Integration test: create a parent category with `CategoryListingPurpose`/`CategoryListingFeature` through-table bindings and a child category with no direct bindings; GET `/category/<child>/` and assert `context['resolved_purposes']` equals the parent's resolved set (ancestor-walk inheritance), NOT the full lookup set; verify cache key `lookup:resolved_*:<child_id>` is populated. Also test that without a category path, `resolved_*` returns the full active `LookupItem` set. | High |
| V3 | Breadcrumb rendering reflects active category ancestor chain — root-first `get_ancestors`, last segment as plain text, `›` separators, ellipsis truncation for chains >2. `breadcrumb_category` passed from listings, search, and ad_detail. | `breadcrumb.html:11-34`; `listings.py:260,266,431`; `search.py:59,63,240`; `ad_detail` at `listings.py:88` | EXISTS | `test_breadcrumbs_render.py:95-156` (root category → "Главная > Бизнес"; child category → ancestor chain; ad detail → full path; home → empty nav); `test_detail_context.py:121-130` (`breadcrumb_category` context key == `ad.category`); `test_autocomplete_template.py:148-153` (template-source: no `get_ancestors\|last` crash on empty; `slice:"::-1"\|first` safe access); `test_detail_context.py:154-179` (template-source: ellipsis `>…<`, `&rsaquo;` separator, `{% if ancestors\|length > 2 %}`) | No new test needed — existing coverage is sufficient. Optional: add a test for a 3-level-deep ancestor chain (e.g., root → child → grandchild) verifying the full chain renders without truncation, building on the catalog-loaded fixture in `test_breadcrumbs_render.py`. | Low |
| V4 | Context-drop (shared with Block 3) — header search form (`header_catalog.html:114-132`) submits only `q` + `csrfmiddlewaretoken`; no hidden `category`/`city`/`feature` inputs. Submitting from a category page yields `/search/?q=<t>` with no category context. Only re-scoping mechanisms are autocomplete category suggestion or single-word fuzzy match. | `header_catalog.html:114-132`; `filter_form.html:11-12` | GAP | `test_autocomplete_template.py:55-64` (verifies `name="q"` and htmx attrs but does NOT assert absence of hidden category/city inputs); `test_autocomplete_template.py:145` asserts `{% with current_cat=breadcrumb_category %}` in header, but no behavioral test of the context-drop | Template-source assertion: read `header_catalog.html` lines 114-132, assert no `<input type="hidden" name="category"` or `<input type="hidden" name="city"` within the search form. Optionally: Django Client test on `/category/<slug>/` rendering the full page and asserting the header search form contains only `name="q"` and `csrfmiddlewaretoken` inputs (no hidden category/city). | Medium |
| V5 | Gap — no category control in `filter_form.html` on `/search/?q=`: hidden `category` input is gated on `{% if current_category %}`; on the search page without `?category=`, `current_category` is `None`, so no category control is offered. Category scoping on `/search/` is only possible via URL or autocomplete. | `filter_form.html:11-12`; `search.py:57-69` | GAP | `test_catalog_filters.py:492-528` (template-source assertions for `filter_form.html` — checks `hx-get` and `current_category` hidden input presence, but does NOT test the absence on `/search/?q=`); `test_search_view.py:643-651` (asserts `breadcrumb_category` is set when `?category=transport` is passed, but does not test the filter form rendering) | Integration test: create a published ad in category `transport`; GET `/search/?q=<term>` (no `?category=`); assert response renders `filter_form.html` without a hidden `category` input (since `current_category` is `None`); assert `/search/?category=transport&q=<term>` renders the hidden `category` input. Uses Django Client + HTML content assertion. | Medium |
| V6 | Fuzzy match narrows results but doesn't update filter options or breadcrumb — single-word query matching a category via `_fuzzy_category_match` (`search.py:167-174`) narrows the queryset to the category subtree but does NOT set `breadcrumb_category`, `current_category`, or constrain `resolved_*` — those remain at the full-set fallback. | `search.py:167-174` (`_fuzzy_category_match` call + subtree filter); `search.py:57-69` (explicit `?category=` — separate mechanism); `search.py:119-140` (resolved sets fallback to full lookup when `breadcrumb_category` is None) | GAP | `test_search_view.py:182-248` (`TestSearchViewDescendantCategories` — `test_category_match_expands_to_descendants` verifies the queryset narrows to descendants and excludes non-descendants, but does NOT assert `context['resolved_*']` or `context['breadcrumb_category']` remain unconstrained) | Assert behavior of `/search/?q=Транспорт` (single-word query matching category name): (1) results narrow to the matched category subtree via `page_obj`; (2) `context['breadcrumb_category']` is `None` (no path category); (3) `context['resolved_purposes']`/`resolved_features`/`resolved_conditions` are the full active lookup sets (fallback), NOT the category-constraint set — proving the fuzzy match constrains results but leaves filter options at the unconstrained default. | Medium |
| V7 | Deviation — `?category=` on root `/` does NOT filter (`listings.py:281-284` only calls `_suggest_category`; no queryset filter, no `breadcrumb_category`). This differs from `/search/?category=` (`search.py:57-69`) which does filter. | `listings.py:281-284` (root `?category=` → suggest only, no filter); `listings.py:262-274` (path `category_slug` → filter) | GAP | `test_listings_context.py:176-196` (tests `category_slug` path param, not `?category=` query param); `test_listings_sort.py:26-109` (uses `/` without `?category=`) | Assert that GET `/?category=transport` (root with query param, not path) does NOT filter: create ads in category `transport` and a different category; GET `/?category=transport`; assert both ads appear in results (no filtering applied) AND `context['current_category']` is `None` (path slug is None) AND `context['breadcrumb_category']` is `None` AND `context['suggested_category']` is `None` (valid slug = no suggestion). Also test `/?category=invalid-slug` → `suggested_category` is set. | Medium |

---

## 3. Priority

**Medium** — Block 4 covers the core category browsing UX (entry, subtree filter, breadcrumbs). V2 (constrained filter sets) is **High** risk because it gates the buyer's ability to see category-appropriate filter options; V1, V6, V7 are **Medium**; V3 is **Low** (already covered); V4, V5 are **Medium**.

---

## 4. Dependencies

| Depends On | Block/Surface | Rationale |
|------------|---------------|-----------|
| Block 3 (FTS results rendering) | `.ai/plans/_blocks/block_03.md` | Block 4 shares the FTS result rendering pipeline (`ads/partials/ad_list.html`); the fuzzy-match gap (V6) sits at the intersection of FTS search (`search.py:167-182`) and category scoping. |
| Block 5 (filter controls) | `.ai/plans/_blocks/block_05.md` | The category-constrained filter option sets (V2) feed directly into the filter form (`filter_form.html:16-93`) whose controls are tested in Block 5. V5 (no category control on `/search/?q=`) is a filter-form concern. |
| Block 3 context-drop (shared) | `.ai/plans/_blocks/block_03.md` | The context-drop behavior (V4) is jointly owned by Block 3 and Block 4 per the top plan (`01_search_patterns_test_verification_top_plan.md:99`). |
| Test DB catalog loading | `conftest.py` (root), `categories/catalog/builder.py:load_catalog` | Tests for V1/V2/V3/V6 that use the real catalog need the class-scoped `_load_catalog` fixture pattern from `test_breadcrumbs_render.py:49-92` to avoid slug collisions with `test_submenu.py`'s `tree` fixture. |

---

## 5. Validator Recommendations

> **HTMX 2.0 migration scope:** HTMX 2.0 migration does not require renaming `addEventListener` event handlers (both `htmx:afterRequest` and `htmx:after-request` fire). HTML attributes (`hx-get`, `hx-target`, `hx-swap`, `hx-push-url`) are unchanged. B6 (`htmx.get` at `header_catalog.html:536`) is NOT resolved by migration — see Block 1 for the explicit code fix required. Block 4's test assertions (V1–V7) depend on HTML attributes and Django context, both unaffected by HTMX 2.0.

### 5.1 Category Subtree Assertion Approach (V1, V7)

- **Real Django Client (integration):** Create ads in a 3-level category tree (root → child → grandchild) and a separate non-descendant root category. Assert via `response.context["page_obj"]` that:
  - `/category/<root>/` returns ads from root + all descendants, excludes non-descendants.
  - `/?category=<root>` (query-param deviation) returns ALL published ads unfiltered.
- **Use `create_test_ad`** from `conftest.py` with `status=AdStatus.PUBLISHED` and explicit `published_at` to satisfy DB check constraints.
- **Slug collision avoidance:** Use simple, non-catalog slugs (e.g., `cat-root`, `cat-child`, `cat-unrelated`) or load via `load_catalog` + class-scoped atomic fixture as in `test_breadcrumbs_render.py` to match production categories.

### 5.2 Category-Constrained Filter Set Assertion (V2)

- **Ancestor-walk inheritance:** Create `CategoryListingPurpose`/`CategoryListingFeature`/`CategoryListingCondition` through-table rows for a **parent** category only. Create a **child** category with no direct bindings. GET `/category/<child>/` and assert `context["resolved_purposes"]` contains only the parent's bound items (not the full `LookupItem` set) — proving the resolver walks up to the nearest ancestor.
- **Cache key verification:** After resolution, assert the LocMemCache key `lookup:resolved_purposes:<child_id>` is populated (mirrors `lookup_resolution.py:155`).
- **Fallback path:** GET `/` (no category) and assert `context["resolved_purposes"]` equals `LookupItem.objects.filter(group__code=LookupGroupCode.LISTING_PURPOSE, is_active=True)`.

### 5.3 Breadcrumb HTML Assertions (V3)

- **Rendered HTML:** Use regex to extract `<nav aria-label="Breadcrumb">` inner HTML (as in `test_breadcrumbs_render.py:39-46`). Assert ancestor names appear in root→leaf order and the current category is rendered as plain text (not a link).
- **Ellipsis truncation:** For 3+ ancestor chains, assert `>…<` appears and only the first + last ancestor links render. For ≤2 ancestors, assert no `>…<` truncation.
- **Template-source guard:** Assert `{% if ancestors|length > 2 %}` gates the truncation branch (`test_detail_context.py:154-157`).
- **Note — HTMX 2.0 `addEventListener` scope (out of assertion scope):** `header_catalog.html:244` (`htmx:afterRequest`) and `header_catalog.html:544` (`htmx:afterSwap`) are `addEventListener` calls, not inline `hx-on:` attributes. HTMX 2.0 dispatches both camelCase and kebab-case event forms for every event, so these listeners fire unchanged. They are out of Block 4's test-assertion scope — Block 4 verifies category browsing via URL path and Django Client context, not JS event listeners.

### 5.4 Context-Drop & Filter Form Assertions (V4, V5)

- **Template-source (no DB):** Read `header_catalog.html` and `filter_form.html`; assert no `<input type="hidden" name="category"` or `<input type="hidden" name="city"` inside the header search form (V4). Assert `filter_form.html` line 12 is `{% if current_category %}` — gating the hidden category input (V5).
- **Rendered output (integration):** GET `/category/<slug>/` and assert the rendered HTML header search form contains only `name="q"` + `csrfmiddlewaretoken` inputs within `data-search-form`.

### 5.5 Fuzzy Match Gap Assertion (V6)

- **Integration:** GET `/search/?q=Транспорт` (single-word matching a category name). Assert `response.context["page_obj"]` narrows to the subtree (ads in non-matching categories excluded). Assert `response.context["breadcrumb_category"]` is `None` and `response.context["current_category"]` is `None`. Assert `response.context["resolved_purposes"]` is the full active set (fallback), not the category-constrained set.
- **Cache isolation:** Clear LocMemCache between tests (`cache.clear()`) to avoid stale resolver results from sibling test classes.
