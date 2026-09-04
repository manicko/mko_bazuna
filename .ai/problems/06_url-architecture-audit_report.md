# URL Architecture Audit: City/Category Filtering and URL Construction

**Audit Phase:** URL architecture, filter parameter flow, and header navigation behavior
**Date:** 2026-09-03
**Status:** Complete — findings verified against code and spec

---

## 1. Executive Summary

The catalog URL architecture uses **two mutually exclusive path-based filters** —
`category/<slug>/` and `city/<slug>/` — that cannot coexist in the URL path
simultaneously. Critically, the code treats these two filters **asymmetrically**:

| Filter | URL path param | Query param (`?param=`) |
|--------|---------------|------------------------|
| **Category** | ✅ Real filter (subtree via MPTT) | ⚠️ Suggestion-only (did-you-mean), **NOT** a filter |
| **City** | ✅ Real filter (exact match) | ✅ Real filter (exact match) — same code path |

This asymmetry means the only viable fix for "city selection preserves category"
is **Option A** (PO-confirmed): navigate to the current path + `?city=<slug>` as a
query parameter alongside the category in the path. Category cannot be preserved
as a query param on listings because `?category=` is suggestion-only there.

The header catalog JS (`header_catalog.html` L340 and L562) currently hard-navigates
to `/city/<slug>/`, discarding the category path entirely. This is the root cause of
Problem 04 (#4): "When changing the city, the category filter is reset."

---

## 2. URL Pattern Architecture

### 2.1 Path patterns (`src/backend/apps/ads/urls.py`, L24–27)

```python
urlpatterns = [
    path("", listings, name="listings"),                              # /            — root catalog
    path("category/<slug:category_slug>/", listings, name="listings_category"),  # /category/<slug>/
    path("city/<slug:city_slug>/", listings, name="listings_city"),  # /city/<slug>/
    ...
]
```

**Confirmed: The `category/<slug>` and `city/<slug>` path segments are mutually
exclusive.** Django's URL resolver matches the first segment after the app prefix:
it is either `category`, `city`, an `int:ad_id`, `dashboard`, `media`, etc. There
is no pattern like `category/<cat>/city/<city>/` or `city/<city>/category/<cat>/`.
At most one of `category_slug` or `city_slug` is non-`None` in a single `listings()`
call. There is also no combined query-param-based path that accepts both in the URL
path.

### 2.2 The `listings()` view signature (`listings.py`, L190–194)

```python
def listings(
    request: HttpRequest,
    category_slug: str | None = None,
    city_slug: str | None = None,
) -> HttpResponse:
```

Both slugs arrive from **URL path parameters** only — Django fills them from the
`<slug:category_slug>` / `<slug:city_slug>` converters. Query params (`?category=`,
`?city=`) are handled entirely inside the function body via `request.GET`.

---

## 3. Category Filter: Path-Only

### 3.1 Category from URL path — real filter (`listings.py`, L263–275)

```python
if category_slug:
    try:
        category = Category.objects.get(slug=category_slug, is_active=True)
        breadcrumb_category = category
        descendant_ids = category.get_descendants(include_self=True).values_list("id", flat=True)
        ads = ads.filter(category_id__in=descendant_ids)   # ← REAL filter (MPTT subtree)
    except Category.DoesNotExist:
        suggested_category = _suggest_category(category_slug)
```

The `category_slug` path parameter triggers a genuine filter: it resolves the
`Category` by slug, walks the MPTT subtree via `get_descendants(include_self=True)`,
and filters ads by `category_id__in=descendant_ids`. An invalid slug yields a
did-you-mean suggestion.

### 3.2 Category from query param — suggestion ONLY (`listings.py`, L282–285)

```python
elif request.GET.get("category"):
    # Try to suggest category for invalid slug
    suggested_category = _suggest_category(request.GET.get("category", ""))
```

This `elif` branch fires **only when `category_slug` is falsy** (i.e., no category
in the URL path). It calls `_suggest_category()` — which runs `difflib.get_close_matches`
against active category slugs — and sets `suggested_category` for the did-you-mean
banner. **It does NOT filter ads.** The `?category=` query parameter on a listings
page is purely advisory.

**Contrast with `search.py`, L64–67:** On the search page, `?category=` IS a real
filter:

```python
current_category = request.GET.get("category")
if current_category:
    category = Category.objects.get(slug=current_category, is_active=True)
    ads = ads.filter(category_id__in=descendant_ids)   # ← REAL filter
```

This means `?category=` preserves category on the **search** page (both as filter
and in the hidden input of the header search form) but **not** on the **listings**
page. The listings page relies entirely on the URL path for category filtering.

### 3.3 Context: `current_category` (`listings.py`, L452)

```python
"current_category": category_slug,
```

`current_category` is set to the **path parameter** slug (or `None`). It is consumed
by:
- `filter_form.html` L11 — hidden input `name="category"` (used by the header search
  form to carry category to `/search/`, and by the HTMX filter form to re-emit on
  `request.path`).
- `header_catalog.html` L131 — hidden input in the search form.

---

## 4. City Filter: Path OR Query Param

### 4.1 City from URL path — real filter (`listings.py`, L293–300)

```python
if city_slug:
    effective_city = city_slug
    try:
        city = City.objects.get(slug=city_slug)
        ads = ads.filter(city_id=city.id)               # ← REAL filter (path)
    except City.DoesNotExist:
        suggested_city = suggest_city(city_slug)
```

### 4.2 City from query param — ALSO a real filter (`listings.py`, L302–309)

```python
elif request.GET.get("city"):
    effective_city = request.GET["city"]
    try:
        city = City.objects.get(slug=effective_city)
        ads = ads.filter(city_id=city.id)               # ← REAL filter (query param)
    except City.DoesNotExist:
        suggested_city = suggest_city(effective_city)
```

### 4.3 Default fallback — preferred city (`listings.py`, L310–320)

```python
else:
    preferred_city = getattr(request, "preferred_city", None)
    if preferred_city:
        effective_city = preferred_city
        try:
            city = City.objects.get(slug=preferred_city)
            ads = ads.filter(city_id=city.id)
        except City.DoesNotExist:
            pass
```

### 4.4 Effective city exposed (`listings.py`, L325)

```python
request.current_city = effective_city
```

Both views set `request.current_city` to the **effective** city — whether it came
from the path param, the query param, or the preferred-city fallback. The
`header_context` processor (L64–66 of `context_processors.py`) reads this to display
the active city badge, preventing the Problem-04 off-by-one where the badge would
otherwise show the stale cookie preference.

### 4.5 Priority chain

1. `city_slug` (URL path `/city/<slug>/`) — wins, real filter
2. `?city=<slug>` (query param) — real filter
3. `request.preferred_city` (middleware: DB FK for auth users, validated cookie
   for anonymous) — default filter

---

## 5. Header JS Navigation Behavior

### 5.1 Autocomplete suggestion click (`header_catalog.html`, L328–349)

The `dropdown.addEventListener('click', ...)` handler at L328 intercepts clicks on
`<a data-suggestion-text>` elements rendered by the `render()` function (L278–310).
It branches on `data-suggestion-type`:

#### City suggestion (L335–340):

```javascript
if (type === 'city' && slug) {
    // Persist preferred city (cookie) then filter by navigating to the city listing.
    var fd = new FormData();
    fd.append('slug', slug);
    fetch('{% url "search:preferred_city" %}', { method: 'POST', body: fd, headers: { 'X-CSRFToken': getCsrf() } });
    window.location.href = '/city/' + encodeURIComponent(slug) + '/';   // ← L340: HARDCODED path
}
```

**Behavior**: Persists the city preference via a fire-and-forget `fetch` POST, then
performs a **full-page navigation** to `/city/<slug>/`. The current URL (including
any `/category/<slug>/` path segment and any query params like `?sort=price_asc`)
is **completely discarded** — only the city slug survives, in the URL path.

#### Category suggestion (L341–344):

```javascript
} else if (type === 'category' && slug) {
    // Filter by category.
    window.location.href = '/category/' + encodeURIComponent(slug) + '/';  // ← L343: HARDCODED path
}
```

**Behavior**: Full-page navigation to `/category/<slug>/`. This discards any city
filter (path or query param) the user had active. Since this navigates to a listings
path, `?city=` would be lost (though `?category=` is path-only, so this particular
navigation is correct for category).

#### Text suggestion (L344–348):

```javascript
} else {
    // Text suggestion (popular search / user history): populate + submit.
    searchInput.value = text;
    if (searchForm) searchForm.submit();  // ← submits to search:search (/search/)
}
```

**Behavior**: Populates the search input and submits the header search form, which
navigates to `/search/?q=<text>`. The form's hidden inputs (L131–132) carry
`current_category` and `current_city` as query params — which **do work** on the
search page (both are real filters there).

### 5.2 City dropdown click handler (`header_catalog.html`, L545–564)

Two sub-handlers inside `cityPanel.addEventListener('click', ...)`:

#### "Entire country" (clear) (L546–554):

```javascript
var clearItem = e.target.closest('[data-city-clear]');
if (clearItem) {
    e.preventDefault();
    var fd = new FormData();
    fd.append('action', 'clear');
    fetch('{% url "search:preferred_city" %}', { method: 'POST', body: fd, headers: { 'X-CSRFToken': cityGetCsrf() } });
    window.location.href = '/';    // ← L552: HARDCODED root — discards category + city
    return;
}
```

**Behavior**: Clears the city preference via POST, then navigates to `/`. Discards
both the category path and any city filter.

#### City option selection (L555–563):

```javascript
var link = e.target.closest('[data-city-option]');
if (link) {
    e.preventDefault();
    var slug = link.getAttribute('data-city-option');
    var fd = new FormData();
    fd.append('slug', slug);
    fetch('{% url "search:preferred_city" %}', { method: 'POST', body: fd, headers: { 'X-CSRFToken': cityGetCsrf() } });
    window.location.href = '/city/' + encodeURIComponent(slug) + '/';   // ← L562: HARDCODED path
}
```

**Behavior**: Identical to the autocomplete city handler (L340) — persists the city
preference via POST, then navigates to `/city/<slug>/`, discarding the current path.

### 5.3 Category dropdown links (`header_catalog.html`, L97 and L180)

```html
<a href="{% url 'ads:listings_category' cat.slug %}" data-category-link="{{ cat.slug }}" ...>
```

These are plain `<a>` tags with Django-reversed URLs (`/category/<slug>/`). The
`attachCategoryHandlers` function (L431–453) intercepts clicks but only calls
`closeCategories()` and `return`s — it does **not** modify the href. Default
navigation proceeds to the hardcoded `/category/<slug>/` path, **discarding any
`?city=` query param** the user may have had.

This is the **reverse asymmetry**: city selection breaks category (L340, L562),
and category selection breaks city (L97, L180). The category links don't use JS to
append the current city query param to the URL.

---

## 6. The Asymmetry Summarized

```
                    URL Path                    Query Param (?param=)
Category:           ✅ REAL filter              ⚠️ Suggestion-only on listings
                                          (REAL filter on search page — different view)
City:               ✅ REAL filter              ✅ REAL filter (same code path)
```

### Why this asymmetry exists

The `listings()` view was designed with category as the **primary path-based navigator**
and city as a **secondary modifier**. The URL structure mirrors Avito's:
`/<category_slug>/` and `/city/<city_slug>/`. City was given the extra flexibility of
a query param because:

1. The preferred-city middleware needs a way to apply a default city without changing
   the URL path (the `else` fallback at L310–320).
2. The `filter_form.html` HTMX form sends `city` as a hidden query param, so when
   you're on `/category/electronics/` and apply a price filter, the form needs to
   round-trip the city without losing it — the hidden input at L132
   (`<input type="hidden" name="city" value="{{ current_city }}">`) handles this.

Category was NOT given the same query-param treatment on listings because:
- The category is always in the path when active (the URL pattern enforces it).
- The `?category=` query param was intentionally relegated to "suggestion-only"
  (L282–285), likely to avoid ambiguity: if both `?category=` and the path param
  existed, which wins?

However, this means the `?category=` hidden input in `filter_form.html` (L11) and
`header_catalog.html` (L131) is **redundant but harmless** on listings pages — the
path already carries the category, and the query param is ignored for filtering.
On the search page, it becomes a real filter.

---

## 7. Exact Changes Needed to Preserve Category When Selecting a City

### 7.1 City selection must append `?city=` to the current URL (not navigate to `/city/<slug>/`)

**File:** `src/backend/templates/components/header_catalog.html`

#### Change 1 — Autocomplete city suggestion click (L340)

**Current:**
```javascript
window.location.href = '/city/' + encodeURIComponent(slug) + '/';
```

**Required:**
```javascript
var url = new URL(window.location.href);
url.searchParams.set('city', slug);
window.location.href = url.toString();
```

This preserves:
- The current path (e.g., `/category/electronics/` — the category stays in the path)
- All existing query params (e.g., `?sort=price_asc&min_price=100`)
- The `lang` parameter if present

The `?city=budva` query param is then picked up by `listings()` L302–309 as a **real
filter**, coexisting with the category path param.

#### Change 2 — City dropdown selection (L562)

Same change as L340:
```javascript
var url = new URL(window.location.href);
url.searchParams.set('city', slug);
window.location.href = url.toString();
```

#### Change 3 — "Entire country" clear button (L552)

**Current:**
```javascript
window.location.href = '/';
```

**Required:**
```javascript
var url = new URL(window.location.href);
url.searchParams.delete('city');
window.location.href = url.toString();
```

This removes the city filter but preserves the category path and other params.

### 7.2 Why `?category=` query param cannot be used for city selection's reciprocal

If, instead, the fix tried to preserve city via path and category via query param
(Option B from the regression spec: `/city/<slug>/?category=<cat>`), it would **fail**
because `listings()` treats `?category=` as suggestion-only (L282–285). The category
would not be filtered. This is why the PO chose Option A (`?city=` alongside the
category path).

### 7.3 Category selection must preserve `?city=` (reverse asymmetry)

**File:** `src/backend/templates/components/header_catalog.html`, category links
at L97 and L180

The category dropdown links currently hardcode `href="{% url 'ads:listings_category' cat.slug %}"`
which generates `/category/<slug>/`, discarding any `?city=` param. To preserve city
when selecting a category, the JS in `attachCategoryHandlers` (L431–438) should
intercept category-link clicks and append the current `city` query param:

```javascript
if (e.target.closest('a[data-category-link]')) {
    // Allow default navigation but preserve current city param
    var link = e.target.closest('a[data-category-link]');
    var url = new URL(link.href);
    var currentParams = new URLSearchParams(window.location.search);
    if (currentParams.has('city')) {
        url.search = currentParams.toString();
    }
    window.location.href = url.toString();
    closeCategories();
    return;
}
```

**Note:** The regression spec (`05_filter-regression_spec.md` T5) scopes the fix to
L340 and L562 only. The reverse case (category links discarding city at L97, L180)
is a **related but unaddressed** asymmetry. It should be included in the same fix or
tracked as a follow-up.

### 7.4 Did-you-mean suggestion links also discard context

**File:** `src/backend/templates/ads/partials/ad_list.html`, L27–29

```html
<a href="{% url 'ads:listings_city' suggested_city %}" ...>{{ suggested_city }}</a>?
```

The did-you-mean city suggestion navigates to `/city/<suggested>/`, also discarding
any category path. If the user is on `/category/electronics/?city=kyivv` (typo), the
did-you-mean suggestion should preserve the category:

```html
<a href="?city={{ suggested_city }}{% if current_category %}&amp;...{% endif %}" ...>
```

Or use `URLSearchParams` construction. Currently this is hardcoded to
`/city/<slug>/` via URL reversing.

---

## 8. Spec Alignment

### 8.1 Spec says "Category and city are path parameters"

`filter-ui.md` (L410–411):
> "Category and city are **path parameters** (in the URL path, not query string)
> and are naturally preserved."

This statement is **partially accurate for city** (which is also a query param
filter) but **inaccurate for category** (which has no query-param filter on listings).
The spec's claim that path params are "naturally preserved" during city selection is
**false** — selecting a city navigates to `/city/<slug>/`, which replaces the
`category/<slug>/` path segment entirely.

### 8.2 Spec journey matrix acknowledges the loss

`search-journeys.md` (L236–241):
| Journey | Category kept via header search? | City kept via header search? |
|---------|----------------------------------|------------------------------|
| Home → category+filter → query → results | No — lost on header submit | Preferred-city default re-applied; category path dropped |
| Category → query → results | No — lost | Preferred-city default re-applied; category path dropped |

Journeys 2 and 4 explicitly document that the category path is **dropped** when
submitting the header search. Since the header search form has hidden `category`
and `city` inputs (header_catalog.html L131–132), these are sent as query params to
`/search/?q=...&category=...&city=...`. On the **search page**, both are real filters,
so the category IS preserved there — but the journey says "lost" because the user
moved from a listings page (where category is in the path) to the search page (where
category is a query param). The "loss" is the **engine transition** (listings → FTS
search), not a filter loss per se.

### 8.3 Open product question

`search-journeys.md` (L268–270):
> **Q3. Header-search context preservation. Should the header bar carry the active
> category (path → `?category=`) and city when submitting from a `/category/…` or
> `/city/…` page, matching OLX/Avito? Currently dropped in journeys 2, 4, and 6.**

This is acknowledged as an open question in the spec. The header search form already
carries both via hidden inputs (L131–132), so this is partially implemented — the
gaps are:
1. City selection via dropdown/autocomplete (full-page nav to `/city/<slug>/`) — **not**
   carried as `?category=`.
2. The "Entire country" clear (full-page nav to `/`) — **not** carried.

The confirmed PO decision (regression spec `05_filter-regression_spec.md` Q2=A)
resolves Q3 for the city-selection case: use `?city=` alongside the existing
category path.

---

## 9. Test Coverage Gaps

### 9.1 No test for city selection preserving category on listings

`test_preferred_city_readback.py` tests `?city=` as a filter and `/city/<slug>/` as
a path filter, but does **not** test the scenario:
> "User is on `/category/electronics/`, selects a city → category is preserved"

This is because the JS behavior (full-page navigation to `/city/<slug>/`) is not
exercised by Django tests — it's client-side JS. A browser/integration test
(Playwright) would be needed.

### 9.2 `test_listings_context.py` does not cover the city+path-param coexistence

The unit test at L176 (`test_path_slugs_populate_current_category_and_city`) tests
both path slugs simultaneously, but Django's URL resolver would never route both
to the same view call. It tests the mock directly. No test verifies:
> `/category/electronics/?city=budva` → both filters applied

The `test_listings_context.py` `_SPEC_QUERY` (L35–37) uses
`category=electronics&city=kyiv` as raw query params, but since `category_slug`
is `None` in that test, `?category=` falls through to the suggestion-only branch
(L264). The test asserts `current_category is None` (L158) — confirming that
`?category=` does NOT set `current_category` on the listings page.

### 9.3 `test_preferred_city_readback.py` L159 — `?city=budva` on root path

```python
response = client.get("/?city=budva")
assert _result_ids(response) == [budva_ad.id]
```

This confirms `?city=` works as a filter on the root path. But there's **no test**
for `?city=` on `/category/<slug>/` — the exact scenario that the fix targets.

---

## 10. Risk Assessment

### 10.1 Low-risk changes (header JS only)

The fix requires changes **only** in `header_catalog.html` JS (L340, L552, L562),
plus optionally L97/L180 for the reverse case. No backend/view changes are needed:
`listings()` already supports `?city=` as a real filter (L302–309), and
`current_city` context is already populated from it.

### 10.2 SEO/canonical concern

Currently `/city/budva/` and `/?city=budva` are **different URLs** that filter to
the same ads but render different paths. With the fix, city selection from
`/category/electronics/` produces `/category/electronics/?city=budva`. There is no
canonical tag to unify these, but this is a pre-existing condition — the fix does
not worsen it.

### 10.3 The `/city/<slug>/` path becomes vestigial

After the fix, no header interaction navigates to `/city/<slug>/` anymore.
The URL pattern `listings_city` (L27) remains valid and functional (the view
still handles `city_slug` path param), but it is no longer reachable from the
header UI. Users can still type it directly or bookmark it. The did-you-mean
suggestion at `ad_list.html` L27 still links to `/city/<slug>/`. This should be
updated to also use `?city=` on the current path for consistency.

---

## 11. Complete Evidence Summary

### File: `src/backend/apps/ads/urls.py`

| Line | Pattern | URL Name | View Args |
|------|---------|----------|-----------|
| L25 | `""` | `ads:listings` | — |
| L26 | `"category/<slug:category_slug>/"` | `ads:listings_category` | `category_slug` |
| L27 | `"city/<slug:city_slug>/"` | `ads:listings_city` | `city_slug` |

**Mutually exclusive**: Only one `<slug:>` segment can appear in the path.

### File: `src/backend/apps/ads/views/listings.py`

| Lines | Behavior |
|-------|----------|
| L263–275 | `category_slug` (path) → real filter (MPTT subtree) |
| L282–285 | `request.GET.get("category")` → suggestion only, NOT a filter |
| L293–300 | `city_slug` (path) → real filter |
| L302–309 | `request.GET.get("city")` → real filter (same code path) |
| L310–320 | `request.preferred_city` fallback → real filter |
| L325 | `request.current_city = effective_city` (exposed to header badge) |
| L452 | `context["current_category"] = category_slug` (path slug, not query) |
| L453 | `context["current_city"] = effective_city` (path, query, or preferred) |

### File: `src/backend/templates/components/header_catalog.html`

| Line | Code | Problem |
|------|------|---------|
| L131 | `{% if current_category %}<input type="hidden" name="category">` | Correct for search page; redundant on listings (path-only) |
| L132 | `{% if current_city %}<input type="hidden" name="city">` | Correct — carries city as query param to search |
| L340 | `window.location.href = '/city/' + slug + '/'` | **Discards category path** — city suggestion click |
| L343 | `window.location.href = '/category/' + slug + '/'` | Discards city param — category suggestion click |
| L552 | `window.location.href = '/'` | Discards category + city — "Entire country" clear |
| L562 | `window.location.href = '/city/' + slug + '/'` | **Discards category path** — city dropdown selection |
| L97 | `<a href="{% url 'ads:listings_category' cat.slug %}">` | Discards `?city=` param — desktop category link |
| L180 | `<a href="{% url 'ads:listings_category' cat.slug %}">` | Discards `?city=` param — mobile category link |

### File: `src/backend/apps/search/views/search.py`

| Lines | Behavior |
|-------|----------|
| L65 | `current_category = request.GET.get("category")` |
| L68–75 | `?category=` → real filter (search page only) |
| L81–89 | `?city=` → real filter (same as listings) |
| L94 | `request.current_city = current_city` |

### File: `src/backend/templates/ads/partials/filter_form.html`

| Line | Code | Effect |
|------|------|--------|
| L5 | `hx-get="{{ request.path }}"` | HTMX submits to current path (preserves category path) |
| L11 | `{% if current_category %}<input type="hidden" name="category" value="{{ current_category }}">` | Sent as query param; ignored on listings (path-only), used on search |
| L12 | `{% if current_city %}<input type="hidden" name="city" value="{{ current_city }}">` | Sent as query param; works on both listings and search |

### File: `src/backend/templates/ads/partials/ad_list.html`

| Line | Code | Effect |
|------|------|--------|
| L45–46 | Chip removal links include `&category={{ current_category }}&city={{ current_city }}` | Preserves both as query params via HTMX (relative `?page=1...`) |
| L78–79 | Clear-all `hx-get="?page=1..."` | Uses relative URL — preserves the path (category) and all query params |
| L27–28 | Did-you-mean city suggestion links to `{% url 'ads:listings_city' suggested_city %}` | **Discards category path** — should use `?city=` on current path |

---

## 12. Recommendations

### Recommendation 1 (Mandatory for Problem-04 fix): Replace hardcoded `/city/<slug>/` navigation with `?city=` on current URL

**What:** In `header_catalog.html`, replace the three full-page `window.location.href = '/city/' + ... + '/'`
assignments (L340, L562) and the clear assignment (L552) with `URLSearchParams`-based
URL construction that preserves the current path and query parameters.

**Why:** The `listings()` view already supports `?city=` as a real filter (L302–309).
The category is already in the path. Appending `?city=<slug>` keeps both filters active
without any backend change. This is the PO-confirmed Option A.

**Effort:** Trivial (3 lines of inline JS, ~5 minutes).

**Priority:** Recommended (fixes Problem 04 #4).

### Recommendation 2 (Advisory): Extend city preservation to category links and did-you-mean

**What:** Update the category dropdown links (L97, L180) to preserve `?city=` via JS
interception, and update the did-you-mean city suggestion (ad_list.html L27) to use
`?city=` on the current path instead of `/city/<slug>/`.

**Why:** The reverse asymmetry (selecting a category discards the active city) is the
same root cause. Leaving it unfixed creates an inconsistent user experience: city
preserves category, but category does not preserve city.

**Effort:** Small (JS interception in `attachCategoryHandlers`, template link change).

**Priority:** Recommended (completes the bidirectional preservation).

### Recommendation 3 (Advisory): Update spec docs to reflect the asymmetry

**What:** Update `filter-ui.md` (L410–411) to clarify that while both category and city
are "path parameters," city is also a query-param filter whereas category is path-only
on listings. Update `search-patterns.md` (L316–318) to note that the autocomplete city
recommendation should preserve the current path.

**Why:** The current spec text ("Category and city are path parameters and are
naturally preserved") is misleading — they are NOT naturally preserved when the user
selects a different filter via the header.

**Effort:** Trivial (doc text update).

**Priority:** Recommended (prevents future confusion).

### Recommendation 4 (Advisory): Add integration test for city selection preserving category

**What:** Add a Playwright/browser integration test that:
1. Navigates to `/category/electronics/`
2. Clicks a city in the header dropdown
3. Asserts the URL is `/category/electronics/?city=<slug>` (not `/city/<slug>/`)
4. Asserts the category breadcrumb is still visible

**Why:** The JS navigation behavior is not currently tested by any Django test
(the unit tests mock the view directly). A browser test would catch regressions in
the header JS URL construction.

**Effort:** Medium (requires Playwright setup if not already present).

**Priority:** Recommended (prevents regression).
