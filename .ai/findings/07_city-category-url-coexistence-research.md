# Research Recommendation: City+Category URL Coexistence Fix

**Date:** 2026-09-03
**Input:** `06_url-architecture-audit_report.md` (audit findings)
**Spec reference:** `.ai/problems/05_filter-regression_spec.md` (T5, Q2=A)
**Status:** Option A confirmed as correct — with one edge-case refinement

---

## 1. Recommendation (TL;DR)

**The spec's proposed approach (Option A) is confirmed as the correct fix.** Change
the header city-selection JS in `header_catalog.html` to use `URLSearchParams` to
set/replace the `city` param on the **current URL**, then navigate via
`window.location.href`. This preserves the category path segment and all existing
query parameters, and requires **no server-side changes** because `listings()` already
supports `?city=` as a real filter.

**One refinement needed:** When the current URL already has a city in the **path**
(`/city/<old_slug>/`), `?city=` would be ignored (path param wins over query param
in `listings()` L293–294). The JS must detect this case and replace the path segment
instead of appending a query param.

---

## 2. HTMX-Native vs. Vanilla JS: Why `window.location.href` is correct here

### 2.1 HTMX URL management API (v2.0.10)

The project uses **HTMX 2.0.10** (loaded via CDN in `list.html` L17, `detail.html`
L22, cabinet templates). Research of the HTMX public API yields:

| API surface | Status | Usable here? |
|-------------|--------|--------------|
| `htmx.ajax(method, url, config)` | Public | ⚠️ Overkill — triggers AJAX + DOM swap |
| `htmx.swap(target, content, opts)` | Public | ❌ Wrong — only swaps DOM, no URL change |
| `htmx.trigger()` / `htmx.process()` | Public | ❌ Not URL-related |
| `hx-push-url` / `hx-replace-url` attributes | Public (HTML) | ⚠️ Declarative only — requires an element to trigger a request |
| `htmx.pushURL()` / `htmx.replaceURL()` | **Not exposed in v2.0.10** | ❌ Internal functions only (`pushUrlIntoHistory`/`replaceUrlInHistory`) |

The project already uses `htmx.ajax()` at `header_catalog.html` L601 (favorites badge
refresh):

```javascript
htmx.ajax('GET', '{% url "cabinet:favorites_count" %}', {
    target: badge,
    swap: 'outerHTML'
});
```

### 2.2 Why NOT use `htmx.ajax()` for city selection

City selection is a **primary filter change** — analogous to clicking a category
link or submitting the header search form. The current behavior is a **full-page
navigation**. Using `htmx.ajax()` to do a partial update would require:

1. An AJAX GET to the new URL (e.g., `/category/electronics/?city=budva`)
2. Swapping the `#ad-list` partial (already handled by the view's HTMX branch)
3. **Re-rendering the entire header** (including the city badge, breadcrumbs, category
   label) — because the header is outside `#ad-list` in `list.html` L23–36

Step 3 is the blocker. The header is included as a full template at L23 (not inside
`#ad-list` at L36), so an HTMX partial swap of `#ad-list` **cannot** update the
header's city badge or breadcrumb. The header would show stale state (the exact
Problem-04 off-by-one the context processor at `context_processors.py` L52–62 was
designed to fix).

This is the same staleness issue identified in Problem 05 (`.ai/problems/05_filter-regression_spec.md`
§2.4): HTMX partial updates don't re-render the header. The cleanest solution for a
primary filter change is a **full-page navigation** that re-renders the entire page.

### 2.3 Constraints confirmed by spec

- **C3 (vanilla JS only):** "No new frontend framework (vanilla JS only). All JS
  changes use existing inline `<script>` patterns (T5, T6)."
- `URLSearchParams` is a vanilla JS browser API (no framework, no new dependency).
- The existing inline `<script>` block in `header_catalog.html` (L216–614) already
  uses vanilla JS throughout — no HTMX functions are called for URL navigation
  (only `htmx.ajax()` for the favorites badge at L601).

---

## 3. The Fix: `URLSearchParams` + `window.location.href`

### 3.1 City selection (L340 and L562) — with path-segment detection

```javascript
// Common helper for city selection
function selectCity(slug) {
    var url = new URL(window.location.href);
    // If currently on a /city/<slug>/ path, replace the path segment.
    // Otherwise, set city as a query param alongside the current path.
    var cityPathMatch = url.pathname.match(/^\/city\/[^/]+\/$/);
    if (cityPathMatch) {
        url.pathname = '/city/' + encodeURIComponent(slug) + '/';
    } else {
        url.searchParams.set('city', slug);
    }
    window.location.href = url.toString();
}
```

**Why the path detection is necessary:**

`listings()` resolves city with priority (L293–320):
1. `city_slug` (path param) → wins, real filter
2. `request.GET.get("city")` (query param) → real filter
3. preferred city fallback

If the user is on `/city/budva/` (path param = "budva") and selects Podgorica,
`URLSearchParams.set('city', 'podgorica')` would produce
`/city/budva/?city=podgorica`. The path param (`city_slug="budva"`) takes priority
over the query param, so the city would **not change** — the user stays on Budva.

By detecting the `/city/<slug>/` path and replacing the segment, we produce
`/city/podgorica/` which correctly filters to Podgorica.

### 3.2 "Entire country" clear (L552) — with path-segment detection

```javascript
function clearCity() {
    var url = new URL(window.location.href);
    var cityPathMatch = url.pathname.match(/^\/city\/[^/]+\/$/);
    if (cityPathMatch) {
        // On a /city/<slug>/ path: clear by navigating to root (category is
        // also in the path, so /city/<slug>/ means no category).
        url.pathname = '/';
        url.search = '';
    } else {
        // On any other path: just remove the city query param.
        url.searchParams.delete('city');
    }
    window.location.href = url.toString();
}
```

**Rationale for the two branches:**
- On `/city/budva/`: there is no category in the path. Clearing city means returning
  to the root catalog (`/`). The current code does `window.location.href = '/'` which
  is correct for this case.
- On `/category/electronics/?city=budva` (after the fix) or `/category/electronics/`:
  removing the `city` param keeps the user on the category page, just without city
  filtering. Navigating to `/` would also discard the category, which is wrong.

### 3.3 Edge-case verification table

| Current URL | Action | New URL | Category preserved? | City filter applied? |
|-------------|--------|---------|---------------------|----------------------|
| `/category/electronics/` | Select "Budva" | `/category/electronics/?city=budva` | ✅ (path) | ✅ (?city=) |
| `/search/?q=shoes` | Select "Budva" | `/search/?q=shoes&city=budva` | ✅ (via hidden input) | ✅ (?city=) |
| `/` | Select "Budva" | `/?city=budva` | n/a (no category) | ✅ (?city=) |
| `/city/budva/` | Select "Podgorica" | `/city/podgorica/` | n/a (no category) | ✅ (path) |
| `/category/electronics/?sort=price_asc` | Select "Budva" | `/category/electronics/?sort=price_asc&city=budva` | ✅ (path) | ✅ (?city=) |
| `/category/electronics/?city=budva` | Clear city | `/category/electronics/` | ✅ (path) | cleared |
| `/city/budva/` | Clear city | `/` | n/a | cleared |
| `/category/electronics/?features=delivery` | Select "Budva" | `/category/electronics/?features=delivery&city=budva` | ✅ (path) | ✅ (?city=) |

All cases verified against the `listings()` view logic:
- `category_slug` from path → real filter (L263–275)
- `city_slug` from path → real filter (L293–300)
- `?city=` query param → real filter (L302–309)
- All other query params (sort, features, min_price, etc.) are read from `request.GET`
  independently and are unaffected by the city param manipulation.

---

## 4. No Server-Side Changes Required

### 4.1 `listings()` already handles `?city=` correctly

`listings.py` L293–325:

```python
if city_slug:                          # path param (e.g., /city/budva/)
    effective_city = city_slug
    ...ads.filter(city_id=city.id)...
elif request.GET.get("city"):          # query param (e.g., ?city=budva)
    effective_city = request.GET["city"]
    ...ads.filter(city_id=city.id)...
else:                                  # preferred city fallback
    preferred_city = getattr(request, "preferred_city", None)
    ...

request.current_city = effective_city   # exposed to header badge
```

When navigating to `/category/electronics/?city=budva`:
- `category_slug = "electronics"` (path) → real category filter ✓
- `city_slug = None` (no city in path) → falls to `elif request.GET.get("city")`
- `effective_city = "budva"` → real city filter ✓
- `context["current_city"] = effective_city` → header badge shows Budva ✓

### 4.2 `current_city` context variable is already query-param-aware

`listings.py` L453:
```python
"current_city": effective_city,
```

Since `effective_city` is set from the query param (L303), `current_city` correctly
reflects the query-param city. The `filter_form.html` hidden input (L132)
`<input type="hidden" name="city" value="{{ current_city }}">` will re-emit this
on HTMX form submissions, preserving it across filter refinements.

### 4.3 `current_category` context variable is path-only — this is correct

`listings.py` L452:
```python
"current_category": category_slug,
```

`category_slug` comes from the URL path parameter, not `request.GET.get("category")`.
This means when the user is on `/category/electronics/?city=budva`,
`current_category = "electronics"` (from the path), and the filter form's hidden
input sends `?category=electronics`. On the listings page this query param is
suggestion-only (L282–285, the `elif` branch never fires because `category_slug`
truthy), so it's harmless. On the search page, it becomes a real filter. No change
needed.

### 4.4 `search()` (header search form submission) already handles both as query params

The header search form (`header_catalog.html` L127–154) has:
```html
{% if current_category %}<input type="hidden" name="category" value="{{ current_category }}">{% endif %}
{% if current_city %}<input type="hidden" name="city" value="{{ current_city }}">{% endif %}
```

When the user submits a search query, both are sent as query params to `/search/`.
`search.py` treats both `?category=` (L65) and `?city=` (L81) as real filters.
This already works correctly and is **not affected** by the city-selection fix.

---

## 5. Spec Deviation: `filter-ui.md` L410–411

> "Category and city are **path parameters** (in the URL path, not query string) and
> are naturally preserved."

### 5.1 This statement is **incorrect on two counts**:

1. **City is NOT exclusively a path parameter.** `listings()` supports `?city=` as a
   real filter (L302–309, the `elif` branch). The spec's own resolution-priority
   section (`search-patterns.md` L143–146) states "Explicit URL path (`/city/<slug>/`)
   and `city` query parameter **always take precedence** over the stored preference"
   — acknowledging that `?city=` is a first-class filter, not just a path param.

2. **"Naturally preserved" is false for header-initiated navigation.** When a user
   clicks a city in the header dropdown, the JS executes
   `window.location.href = '/city/' + slug + '/'` (L562), which replaces the entire
   path — from `/category/electronics/` to `/city/budva/`, **discarding the category
   path segment**. They are NOT naturally preserved; the hardcoded navigation actively
   destroys the category context.

### 5.2 What "naturally preserved" would actually require

The only mechanism by which category and city are "naturally preserved" is the
**HTMX filter form** (`filter_form.html`):
- It submits to `hx-get="{{ request.path }}"` (L5), so the category path is preserved.
- It includes a hidden `city` input (L132), so `?city=` is round-tripped.

The **header city dropdown** and **autocomplete city suggestion** bypass this
mechanism entirely with hardcoded `/city/<slug>/` paths. The spec's claim of
"natural preservation" applies only to the HTMX filter form, not to all city-selection
UI paths.

### 5.3 Recommended doc update

`filter-ui.md` L410–411 should be revised to:

> "Category is a URL path parameter (`/category/<slug>/`) and is preserved by the
> HTMX filter form (which submits to `request.path`). City is a path-or-query
> parameter: `/city/<slug>/` (path) or `?city=<slug>` (query) both apply the filter.
> The header city dropdown and autocomplete suggestion currently use the `/city/`
> path form, which discards the category path segment; this is documented as a
> known issue (Problem 04 #4) and the fix uses `?city=<slug>` alongside the current
> path instead."

---

## 6. Alternative Approaches Considered

### 6.1 Option B: `/city/<slug>/?category=<cat>` (category as query param)

**Rejected** — PO-Q2=A explicitly chose Option A. Rationale: `listings()` treats
`?category=` as suggestion-only (L282–285, the `elif` branch), NOT as a filter.
Using `?category=` alongside `/city/<slug>/` would not filter by category. The
asymmetry (city query param works, category query param doesn't on listings) makes
this option non-viable.

### 6.2 Option C: New combined path pattern `/category/<cat>/city/<city>/`

**Rejected** — highest risk, biggest change. Would require:
- New URL pattern in `urls.py` (L26–27)
- Path matching logic: which segment is first? (category or city?)
- View refactoring: both `category_slug` and `city_slug` path params
- HTMX form/pagination/chips URL construction updates
- Potential routing conflicts with `<int:ad_id>/` (L28)

The spec doc marks this as the "highest risk" option (Q2=A rationale). Not recommended
for the regression fix.

### 6.3 HTMX-native approach: `htmx.ajax()` + header re-render

**Rejected** — would require moving the header inside the `#ad-list` HTMX swap
target (the exact problem identified in Problem 05 / regression spec §2.4). The
header is used on `list.html`, `detail.html`, and other templates; moving it into
the swap target is architecturally awkward and risks side effects on non-catalog
pages. The spec doc T6 explicitly evaluates this for the language-switcher and
recommends it as a last resort ("If that causes rendering issues... use Approach B").

### 6.4 `history.pushState` + `htmx.ajax()` (hybrid)

**Considered but rejected** — would push a new URL (`?city=<slug>`) and trigger an
AJAX GET, swapping only `#ad-list`. The header would remain stale (city badge,
breadcrumbs not updated). This recreates the Problem-04 off-by-one. A full
`window.location.href` navigation re-renders the header correctly via the view's
context processor chain.

---

## 7. Implementation Checklist

### 7.1 JS changes (`header_catalog.html`)

| Target | Current code | New approach |
|--------|-------------|--------------|
| L340 (autocomplete city click) | `window.location.href = '/city/' + encodeURIComponent(slug) + '/'` | `selectCity(slug)` — URLSearchParams on current URL, with `/city/` path detection |
| L552 ("Entire country" clear) | `window.location.href = '/'` | `clearCity()` — delete `city` param unless on `/city/<slug>/` path (then go to `/`) |
| L562 (city dropdown selection) | `window.location.href = '/city/' + encodeURIComponent(slug) + '/'` | `selectCity(slug)` — same helper as L340 |

All three share the same logic — extract a `selectCity()` and `clearCity()` helper
function at the top of the inline `<script>` block (L217–218 area) to avoid
duplication.

### 7.2 Template changes (`ad_list.html`) — did-you-mean city suggestion

`ad_list.html` L27–28 currently links to `{% url 'ads:listings_city' suggested_city %}`
(`/city/<slug>/`), which discards the category path just like the header JS. Update
to preserve the current path:

```html
<a href="?city={{ suggested_city }}{% if current_category %}&category={{ current_category }}{% endif %}{% if LANGUAGE_CODE %}&lang={{ LANGUAGE_CODE }}{% endif %}" ...>
```

Or use `URL.searchParams` construction via a small JS handler. The spec doc T5
explicitly scopes the fix to `header_catalog.html` L340/L562 — the did-you-mean
link is a **follow-up** but should be tracked.

### 7.3 Category link backward-compatibility (`header_catalog.html` L97, L180)

The category dropdown links (`{% url 'ads:listings_category' cat.slug %}`) also
discard `?city=`. The spec doc T5 does not include this (it only addresses city
selection). The regression spec §9 Risk #4 notes: "City navigation JS change may
break autocomplete city selection on search page." The category-link reverse case
is lower priority but should be tracked as a follow-up.

### 7.4 No server-side changes needed

- `listings.py` L293–309: already handles `?city=` as a real filter
- `listings.py` L453: `current_city` already set from query param
- `filter_form.html` L132: hidden `city` input already round-trips the param
- `context_processors.py` L64–66: badge already reads `request.current_city`
- `search.py` L81–89: `?city=` already a real filter (unaffected by change)

### 7.5 Tests to add/update

| Test target | What to verify |
|-------------|----------------|
| `test_listings_context.py` | `/category/electronics/?city=budva` → `current_city == "budva"`, `current_category == "electronics"` (path) |
| `test_preferred_city_readback.py` | `/category/electronics/?city=budva` → both city and category filters applied (integration test with real DB) |
| `test_catalog_filters.py` | Header city dropdown JS produces `?city=` not `/city/` — requires Playwright/browser test (JS is not exercised by Django tests) |
| `test_catalog_filters.py` (L647–654) | The `9 hx-push-url` count stays the same (JS change doesn't add template links) |
| `test_autocomplete_template.py` | Verify `header_catalog.html` retains `htmx:afterRequest` listener (already asserted at L122–123) |

### 7.6 Spec/doc updates

- `filter-ui.md` L410–411: Revise the "path parameters, naturally preserved" claim
- `search-patterns.md` L316–318: Update the autocomplete city recommendation to use
  `?city=` alongside current path (not `/city/<slug>/`)
- `search-journeys.md` Q3 (L268–270): Mark as resolved (Option A, implemented)

---

## 8. Conclusions

1. **Option A is correct** — `URLSearchParams` + `window.location.href` to set
   `?city=<slug>` alongside the current path. No server-side changes needed.

2. **One edge-case refinement** — when the current path is `/city/<old_slug>/`,
   the JS must replace the path segment rather than appending a query param (path
   param takes priority over query param in the view).

3. **The `/city/<slug>/` URL pattern remains valid** — it's still reachable via
   direct navigation/bookmark, and the view still handles `city_slug` path param.
   No URL pattern changes needed.

4. **"Natural preservation" claim in spec is incorrect** — city selection via
   header JS actively destroys the category path. The spec deviation should be
   documented and corrected.

5. **HTMX AJAX approach is not suitable** — would require header re-rendering
   (the Problem-05 staleness issue). Full-page navigation is the correct
   behavior for a primary filter change.
