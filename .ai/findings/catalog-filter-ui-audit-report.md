# Audit Report: Catalog Filter UI — Chips Block, Clear-All, and Price Summary

**Date:** 2026-09-03
**Scope:** `src/backend/templates/ads/partials/ad_list.html`, `src/backend/apps/ads/views/listings.py`, `src/backend/apps/search/views/search.py`
**Classification:** Evidence-gathering audit (current-state structure). No changes made.

**Status legend:** This report describes *current reality* (code + template).
Where the code diverges from the intended spec, that is flagged as `[SPEC-DEVIATION]`
with the governing requirement reference. Findings reflect the state at commit head;
the template-count gates are in `test_catalog_filters.py` (L647–L687).

---

## 0. Executive summary

The catalog filter UI is rendered by a single shared partial
`ads/partials/ad_list.html`, used by two views — `ads.views.listings.listings` and
`search.views.search.search` — both of which render the same partial for HTMX
requests (listings.py L471–472; search.py L303–304). The filter "active state" is
communicated through a flat dict of `*_listing_purpose`, `*_features`,
`*_condition`, `*_price*`, `*_price_min/max`, and `query` context keys.

The template contains **three distinct, independently-gated regions** for
communicating active filters:

1. **Price summary** (`active_price_min`/`active_price_max`) — L32–37: a plain
   `<div class="filter-summary">` block, **unguarded by any condition on chip
   visibility** and **outside** the chips container.
2. **Chips block** (`current_listing_purpose`/`current_features`/`current_condition`)
   — L39–76: wrapped in `{% if current_listing_purpose or current_features or
   current_condition %}`.
3. **Clear-all link** — L77–83: **completely unguarded** (renders unconditionally).

The price *range display* (region 1) is structurally **not a chip** (no `×`
removal link, not `inline-flex … rounded-full`, no `href`), yet the chips-block
*visibility condition* (region 2) does not include the price variables, and the
clear-all guard (region 3) is absent. These three are inconsistent with one
another and with spec `filter-ui.md` (R-FR-01, R-FR-02, §"Price-Range Summary").

---

## 1. Chips-block conditional (ad_list.html L39)

### The condition

```django
{# ad_list.html L39 #}
{% if current_listing_purpose or current_features or current_condition %}
    <div class="flex flex-wrap gap-2 mb-4">
        ...purpose / condition / features chips...
    </div>
{% endif %}
```

### Context variables consumed by the chips block

| Variable | Type | Source (listings.py) | Source (search.py) | GET param |
|---|---|---|---|---|
| `current_listing_purpose` | `str \| None` | L459 ← `listing_purpose_slug` (L362: `request.GET.get("listing_purpose")`) | L285 ← `listing_purpose_slug` (L125: `request.GET.get("listing_purpose")`) | `listing_purpose` |
| `current_features` | `list[str]` | L460 ← `feature_slugs` (L378: `request.GET.getlist("features") or []`) | L286 ← `feature_slugs` (L139: `request.GET.getlist("features") or []`) | `features` (repeated) |
| `current_condition` | `str \| None` | L461 ← `condition_slug` (L368: `request.GET.get("condition")`) | L287 ← `condition_slug` (L130: `request.GET.get("condition")`) | `condition` |

Both views also expose (not in the chips-block condition):

| Variable | Type | listings.py | search.py |
|---|---|---|---|
| `resolved_purposes` | QuerySet of `LookupItem` | L462 | L288 |
| `resolved_features` | QuerySet of `LookupItem` | L463 | L289 |
| `resolved_conditions` | QuerySet of `LookupItem` | L464 | L290 |
| `active_price_min` | `Decimal \| None` | L457 (parse L347–359) | L283 (parse L110–122) |
| `active_price_max` | `Decimal \| None` | L458 (parse L347–359) | L284 (parse L110–122) |
| `min_price` | `str \| None` (raw) | L455 (raw L329–331) | L281 (raw L97–98) |
| `max_price` | `str \| None` (raw) | L456 (raw L329–331) | L282 (raw L97–98) |

### Chips rendered (L41–74)

Three sub-loops, each gated by an inner `{% if %}` matching the active value:

1. **Purpose chip** — L41–52: iterates `resolved_purposes`; matches
   `p.slug == current_listing_purpose` (L42). Styled
   `inline-flex items-center px-3 py-1 bg-blue-100 text-blue-800 rounded-full`.
   Label via `{% trans "Purpose:" %} {{ p|get_lookup_name:LANGUAGE_CODE }}` (L44).
   Removal `<a>`: L45 (href) + L46 (`hx-get`), removing `listing_purpose` by
   omission; preserves condition + all features.

2. **Condition chip** — L54–66: iterates `resolved_conditions`; matches
   `c.slug == current_condition` (L55). Styled `… bg-purple-100 text-purple-800 …`.
   Label `{% trans "Condition:" %}` (L57). Removal `<a>`: L58 (href) + L59
   (`hx-get`), removing `condition` by omission; preserves purpose + all features.

3. **Features chips** (plural) — L67–74: iterates `resolved_features`; matches
   `f.slug in current_features` (L68). Styled `… bg-green-100 text-green-800 …`.
   Label `{% trans "Feature:" %}` (L70). Removal `<a>` (single line L71): omits
   only `f.slug` from the `features` list via
   `{% for keep in current_features %}{% if keep != f.slug %}&features={{ keep }}{% endif %}{% endfor %}`;
   preserves purpose + condition + remaining features.

### `[SPEC-DEVIATION]` — Price is absent from the chips-block condition

The condition `current_listing_purpose or current_features or current_condition`
excludes `active_price_min` / `active_price_max`. Per `filter-ui.md` R-FR-02 /
requirement CR-2, price range **must** count as a "chip" for visibility: the
chip container should activate when a price filter is set even if no purpose,
condition, or feature is active. Currently, setting only a price range yields
**no chip container and no clear-all button**.

---

## 2. Clear-all link (ad_list.html L77–83)

### Structure

```django
{# ad_list.html L77-83 — OUTSIDE the chips-block {% if %} at L39 #}
<a href="?page=1{% if LANGUAGE_CODE %}&lang={{ LANGUAGE_CODE }}{% endif %}"
   hx-get="?page=1{% if LANGUAGE_CODE %}&lang={{ LANGUAGE_CODE }}{% endif %}"
   hx-push-url="true"
   hx-target="#ad-list"
   hx-swap="innerHTML"
   class="text-sm text-blue-600 hover:underline">{% trans "Clear all filters" %}</a>
```

### Key properties

- **No visibility guard.** Unlike the chips block (L39), this `<a>` is rendered
  unconditionally on every response. The spec (`filter-ui.md` L396) calls for
  `{% if has_active_filters %}` wrapping; that guard was never implemented.
  — `[SPEC-DEVIATION]` vs R-FR-01 / CR-1 / CR-2.

- **HTMX attributes** (every instance is the canonical triple):
  `hx-get`, `hx-push-url="true"`, `hx-target="#ad-list"`, `hx-swap="innerHTML"`.

- **URL construction.** The reset URL is the *minimal* form — only
  `?page=1` + optional `&lang=…`. It does **not** use the full
  param-reconstruction idiom used by chips and pagination (see §4). This
  intentionally drops `q`, `sort`, `min_price`, `max_price`,
  `listing_purpose`, `condition`, and `features`.

- **Category/city preservation** is by URL-path design, not URL construction:
  `listings()` takes `category_slug` and `city_slug` as **path parameters**
  (listings.py L190–194; urls.py). The relative `?page=1&lang=…` URL keeps the
  path intact, so path-param filters survive. Query-string-only params are all
  dropped. — aligns with R-FR-03 / CR-5 *by construction*.

### `[SPEC-DEVIATION]` — Search-page clear-all drops `q`

Per `filter-ui.md` L414–416 / requirement CR-4, on the search results page the
clear-all link must **preserve `q`** while resetting the other filter params.
The current template (L78–79) emits only `?page=1&lang=…` and therefore
**discards the search query**, navigating the user away from their search into
the unfiltered catalog. The comment at L77 states the intent
("resets all query params (q, sort, …)") — matching the listings/clear-everything
behavior but *not* the search-page `q`-preservation requirement.

The mechanism to distinguish the two pages already exists: `query` is set by
`search()` (search.py L276) and **not** by `listings()` (see §6). A conditional
on `{% if query %}` would let one template serve both behaviors.

### Comment vs. reality (L77)

The comment at L77 says: *"resets all query params (q, sort, price, purpose,
condition, features); category/city are path params, naturally preserved."*
This is **accurate for the listings page** but **incorrect for the search page**,
which should preserve `q`. The comment documents the current (divergent)
behavior rather than the spec'd behavior.

---

## 3. Price range summary (ad_list.html L32–37) vs. chip pattern (L41–74)

### Current price summary (L32–37)

```django
{# ad_list.html L32-37 #}
{% if active_price_min or active_price_max %}
    <div class="filter-summary">
        {% blocktrans with min=active_price_min max=active_price_max %}Price: {{ min }}–{{ max }}{% endblocktrans %}
    </div>
{% endif %}
```

### Differences from the chip pattern (L41–74)

| Aspect | Price summary (L32–37) | Chips (L41–74) |
|---|---|---|
| **Element** | `<div class="filter-summary">` | `<span class="inline-flex items-center px-3 py-1 … rounded-full">` |
| **Removal link** | None — static text only | `&times;` `<a>` with `hx-get` + `hx-push-url` |
| **Placement** | **Outside** chips container; its own `{% if %}` | Inside `<div class="flex flex-wrap gap-2 mb-4">` (L40) |
| **Chips-block condition** | `{% if active_price_min or active_price_max %}` (independent) | `{% if current_listing_purpose or current_features or current_condition %}` (L39) |
| **i18n** | `{% blocktrans with min=… max=… %}` (variable interpolation) | `{% trans "Purpose:" %}` etc. (static label) + `get_lookup_name` for the value |
| **Data type used** | Parsed `Decimal` values: `active_price_min` / `active_price_max` | Raw `str` values: `min_price` / `max_price` |
| **URL reconstruction** | N/A (not a link) | Full reconstruction via `{% if min_price %}&min_price={{ min_price }}{% endif %}` |

### `[SPEC-DEVIATION]` — Price is a plain text div, not a removable chip

Per `filter-ui.md` R-FR-02 / CR-6 / CR-7, the price range must render as a
**clickable chip** with a `×` removal link matching the purpose/condition/features
pattern. The current implementation is a non-interactive `<div>`, cannot be
dismissed individually, and is decoupled from the chips-block visibility
condition (so the chips container does not open when *only* price is set).

### `[ARCHITECTURAL]` — Two representations of the same price filter

The same underlying `min_price` / `max_price` GET parameters appear under
**two different variable names** with **different types**:

- `min_price` / `max_price` — raw `str` (or `None`), used for URL reconstruction
  in chip/pagination links and for the `filter_form.html` input `value` attrs
  (filter_form.html L55, L65).
- `active_price_min` / `active_price_max` — parsed `Decimal` (or `None`), used
  only in the price-summary `blocktrans`.

Both views parse the raw string into a `Decimal` identically (listings.py
L347–359; search.py L110–122), then expose both forms separately in context.
This duplication is harmless today but is a maintenance smell: a future price
param rename or validation change must be applied in two parallel code paths
per view.

---

## 4. URL construction pattern — chip removal links & HTMX link inventory

### The canonical reconstruction idiom

Every chip-removal and pagination link (except the clear-all link) reconstructs
the URL by conditionally appending the **currently-active** params in a fixed
order:

```
?{page}&q={query}&category={current_category}&city={current_city}
  &sort={current_sort}&min_price={min_price}&max_price={max_price}
  &listing_purpose={current_listing_purpose}&condition={current_condition}
  &features={fslug}×N&lang={LANGUAGE_CODE}
```

Concrete template expression (ad_list.html, e.g. L46):

```django
hx-get="?page=1{% if query %}&q={{ query|urlencode }}{% endif %}
{% if current_category %}&category={{ current_category }}{% endif %}
{% if current_city %}&city={{ current_city }}{% endif %}
{% if current_sort %}&sort={{ current_sort }}{% endif %}
{% if min_price %}&min_price={{ min_price }}{% endif %}
{% if max_price %}&max_price={{ max_price }}{% endif %}
{% if current_condition %}&condition={{ current_condition }}{% endif %}
{% for fslug in current_features %}&features={{ fslug }}{% endfor %}
{% if LANGUAGE_CODE %}&lang={{ LANGUAGE_CODE }}{% endif %}"
```

Each link also carries a **separate** `href="…"` with the identical expression
(the `href` is for no-JS / initial load; `hx-get` is for the HTMX swap). This
duplicates the entire expression per anchor.

### Per-link param-preservation matrix

| Link | Drops | Preserves (always) | Conditional on active |
|---|---|---|---|
| **Purpose chip ×** (L45–46) | `listing_purpose` (omitted) | `page=1`, `q`, `city`, `sort`, `min_price`, `max_price`, `condition`, `features`×N, `lang` | `category` only if `current_category` |
| **Condition chip ×** (L58–59) | `condition` (omitted) | `page=1`, `q`, `city`, `sort`, `min_price`, `max_price`, `listing_purpose`, `features`×N, `lang` | `category` only if `current_category` |
| **Feature chip ×** (L71) | one `features=<f.slug>` (excluded via `keep != f.slug`) | `page=1`, `q`, `city`, `sort`, `min_price`, `max_price`, `listing_purpose`, `condition`, other `features`, `lang` | `category` only if `current_category` |
| **Clear-all** (L78–79) | `q`, `sort`, `min_price`, `max_price`, `listing_purpose`, `condition`, `features` | only `page=1` + `lang` (path `category`/`city` preserved) | — |
| **Pagination** (L144–178) | nothing (all active params preserved, only `page` changes) | `q`, `category`, `city`, `sort`, `min_price`, `max_price`, `listing_purpose`, `condition`, `features`×N, `lang` | — |

Note: pagination links preserve `current_category` as a **query param**
(`&category={{ current_category }}`), even though on the *listings* page the
category is actually a path parameter. This is harmless (the path param wins;
the `?category=` query param is suggestion-only on listings.py L282–285) but
is semantically inconsistent — it sends a param the listings view ignores for
filtering.

### `[MAINTAINABILITY]` — Manual URL reconstruction duplicated 9×

The full param-reconstruction expression is hand-written **9 times** in
`ad_list.html` (3 chip ×-links + 5 pagination links + 1 clear-all uses the
minimal form). Every edit to the param set (add a param, rename one, change
ordering) must be repeated identically in 8 places. The existing test
`test_all_htmx_links_have_push_url` (test_catalog_filters.py L647–654)
**hard-codes the count at 9**, so any structural deduplication (e.g. a
template include/partial for the query-string, or a `query_replace`-based
approach already used by `language_switcher.html` via `dict_tags.py`
L47–69) would force a test update — see §8.

### HTMX attribute inventory (grep-verified counts)

| Attribute | Count in ad_list.html | Locations |
|---|---|---|
| `hx-get=` | **9** | L46 (purpose), L59 (condition), L71 (feature), L79 (clear-all), L145 (««), L151 («), L162 (page), L171 (»), L177 (»») |
| `hx-push-url="true"` | **9** | L47, L60, L71, L80, L146, L152, L163, L172, L178 |
| `hx-target="#ad-list"` | 9 | same locations |
| `hx-swap="innerHTML"` | 9 | same locations |
| plain `href="…"` (parallel) | 9 | L45, L58, L71, L78, L144, L150, L161, L170, L176 |

Verified via `Select-String`: `hx-get=` count = 9, `hx-push-url="true"` count = 9.
The test `test_all_htmx_links_have_push_url` (L653–654) asserts exactly these
counts; `test_lang_param_in_all_htmx_urls` (L656–663) asserts `≥ 18`
occurrences of `LANGUAGE_CODE` (9 links × 2 attrs = 18; clear-all contributes 2,
each chip contributes 2, each pagination link contributes 2).

---

## 5. `active_price_min` / `active_price_max` — exposed by both views

### listings.py

```python
# listings.py L347-359 (parsing)
active_price_min: Decimal | None = None
active_price_max: Decimal | None = None
if min_price:
    try:
        active_price_min = Decimal(min_price)
    except (ValueError, TypeError):
        pass
if max_price:
    try:
        active_price_max = Decimal(max_price)
    except (ValueError, TypeError):
        pass
```
Exposed at L457–458:
```python
"active_price_min": active_price_min,
"active_price_max": active_price_max,
```

### search.py

```python
# search.py L110-122 (parsing) — identical logic
active_price_min: Decimal | None = None
active_price_max: Decimal | None = None
if min_price:
    try:
        active_price_min = Decimal(min_price)
    except (ValueError, TypeError):
        pass
if max_price:
    try:
        active_price_max = Decimal(max_price)
    except (ValueError, TypeError):
        pass
```
Exposed at L283–284:
```python
"active_price_min": active_price_min,
"active_price_max": active_price_max,
```

### Consumers

`active_price_min` / `active_price_max` are consumed **only** by the price
summary `{% blocktrans %}` at ad_list.html L35. They are **not** used in any
`hx-get` URL reconstruction (the URL builders use the raw `min_price` /
`max_price` strings — see §4). So the parsed-Decimal view of the price exists
purely for human-readable display; the machine URL uses the original strings.

Both views parse price identically and independently (no shared helper), so
the two code paths can drift. No view references `active_price_min`/`active_price_max`
to influence query filtering — filtering is done on the raw `min_price`/`max_price`
ints (listings.py L333–345; search.py L99–108), separate from the Decimal
display variables.

---

## 6. `query` context variable — search.py vs. listings.py

### search.py — **sets** `query`

```python
# search.py L57
query = (request.GET.get("q") or "").strip()
...
# search.py L276 (context)
"query": query,
```

`query` is a non-empty stripped string when `q` is present; `""` otherwise.

### listings.py — **does not set** `query`

The `listings()` context dict (L447–467) contains **no** `query` key. Grep for
`query` in listings.py returns only two hits, both in docstring/comments
(L207 "Price range: min_price and max_price query params", L233 "HTTP request
with optional query params"). There is no `request.GET.get("q")` call and no
`"query":` assignment.

### Template consequence (T4 relevance)

The shared partial `ad_list.html` references `query` in its URL reconstruction
**8 times** (every chip-removal href/hx-get at L45, L46, L58, L59, L71, and
pagination at L144–177). The idiom is:

```django
{% if query %}&q={{ query|urlencode }}{% endif %}
```

- On the **search page** (`search()`): `query` is the user's search term, so
  `&q=<term>` is appended to chip-removal and pagination URLs → the search
  query **survives** chip removal and pagination. ✓ (matches PO-Q3=A / CR-4
  for chip/pagination behavior)

- On the **listings page** (`listings()`): `query` is **undefined**, so Django's
  template engine treats it as an empty/falsy value → `{% if query %}` is
  always False → `&q=` is never appended. This is correct *by accident*, since
  the listings page has no search term. However it means the partial
  silently depends on a variable that only one of its two callers provides.

### `[SPEC-DEVIATION]` — Clear-all does not conditionally preserve `q`

Because `query` is set by `search()` and unset by `listings()`, the template
*can* distinguish the two pages via `{% if query %}`. The clear-all link (L78–79)
does **not** use this conditional: it always emits the minimal
`?page=1&lang=…`, so on the search page it drops `q` — contradicting CR-4 ("On
the search results page, clear-all … **preserves** the search query `q`").

This is the root defect behind T4 in
`.ai/problems/05_filter-regression_spec.md` (T4, L129–136). The required fix
shape is: make the clear-all `hx-get` URL conditional on `{% if query %}` so
that — only on the search page — it emits `?page=1&q={{ query|urlencode }}&lang=…`
instead of the bare `?page=1&lang=…`.

---

## 7. Partial inclusion & rendering context

`ad_list.html` is rendered **twice** by each view:

1. **Full page** (`ads/list.html`, L36): `<div id="ad-list">{% include "ads/partials/ad_list.html" %}</div>` — renders inside `#ad-list`, with the full context dict from the view.
2. **HTMX partial** (listings.py L471–472 / search.py L303–304): when `HX-Request`
   header present, `render(request, "ads/partials/ad_list.html", context)` —
   returns only the partial, swapped into `#ad-list` via `hx-target="#ad-list"`.

Because the partial is re-rendered server-side on every HTMX navigation
(chip removal, pagination, clear-all, filter-form submit), the `{% include
"ads/partials/filter_form.html" %}` at ad_list.html L12–14 is also
re-rendered each time — preventing stale checkbox/select state (per the
template's own header comment L5–11). The `show_filters` guard (L12 /
listings.py L466 / search.py L299) exempts the favorites page, which also
includes this partial (list.html-style wrapper) but without the filter form.

---

## 8. Test coverage (current) that constrains this code

From `src/backend/apps/ads/tests/test_catalog_filters.py`:

| Test | Lines | What it asserts | Blind spot |
|---|---|---|---|
| `test_all_htmx_links_have_push_url` | L647–654 | `hx-get=` count == 9; `hx-push-url="true"` count == 9 | Does not check URL *content*; breaks if a price-chip link is added (9→10) |
| `test_lang_param_in_all_htmx_urls` | L656–663 | `LANGUAGE_CODE` occurrences ≥ 18 | Same brittleness; a new chip link adds 2 |
| `test_clear_all_filters_has_push_url` | L665–687 | Clear-all `hx-get` is `?page=1{% if LANGUAGE_CODE %}…`; asserts `q` and `sort` are **absent** from reset URL; `hx-push-url="true"` present | **Asserts the divergent behavior** — it hard-codes that clear-all *drops* `q`, which is wrong for the search page (CR-4). Does **not** assert the clear-all link is hidden when no chips are active. |

`test_clear_all_filters_has_push_url` (L665–687) currently encodes the
*spec-deviant* behavior (clear-all drops `q` unconditionally). Per AGENTS.md
rule #2 "Production Code is King … never distort production code for tests,"
updating this test to assert `q`-preservation on the search path is part of
aligning tests to correct behavior (see `.ai/problems/05_filter-regression_spec.md`
T4 / T7, L136 / L166–169).

---

## 9. Summary of findings

### `[SPEC-DEVIATION]` — mandatory (correctness/UX)

1. **Clear-all is unconditionally rendered** (ad_list.html L77–83) with no
   visibility guard. Spec R-FR-01/CR-1/CR-2 require it only when a chip
   (purpose/condition/features/**price**) is active. (listings.py L447–467;
   search.py L274–300 both pass no `has_active_filters`.)

2. **Chips-block condition excludes price** (ad_list.html L39):
   `{% if current_listing_purpose or current_features or current_condition %}`.
   Price (`active_price_min`/`active_price_max`) is exposed by both views
   (L457–458 / L283–284) but is not in the condition → no chips and no
   clear-all when only a price range is active. (CR-2.)

3. **Price summary is a non-interactive `<div>`, not a removable chip**
   (ad_list.html L32–37): no `×` link, not `inline-flex … rounded-full`,
   outside the chips container. Spec R-FR-02/CR-6/CR-7 require a chip with a
   removal link preserving all other filters.

4. **Search-page clear-all drops `q`** (ad_list.html L78–79): the minimal
   `?page=1&lang=…` URL discards the search term, contradicting CR-4
   (filter-ui.md L414–416 / PO-Q3=A). The distinguishing `query` variable
   exists in `search.py` (L276) but is absent from `listings.py`, and the
   template does not branch on it.

### `[BEST-PRACTICE]` — advisory (maintainability)

5. **URL reconstruction duplicated 9×** (ad_list.html L45–79, L144–177): the
   identical param-reconstruction expression is hand-written in each `href`
   and `hx-get`. A single template fragment (or reuse of the existing
   `query_replace` tag from `dict_tags.py` L47–69, already used by
   `language_switcher.html`) would eliminate drift risk and shrink the file
   from ~8 KB of repetitive markup. Constraint: the hard-count tests
   (test_catalog_filters.py L653–654, L662) would need to move from counting
   literal `hx-get=` occurrences to asserting structure.

6. **Two parallel representations of price** (`min_price`/`max_price` raw
   strings vs. `active_price_min`/`active_price_max` Decimals) parsed
   independently in both views (listings.py L333–359 vs. search.py L99–122).
   No functional defect, but the duplication is a latent drift point.

7. **Pagination carries `category` as a query string** (ad_list.html L144 etc.)
   even on the listings page where it is a path parameter and
   `?category=` is suggestion-only (listings.py L282–285). Harmless
   (path param wins) but semantically misleading and inconsistent.

### `[DOC-UPDATE]` — documentation

8. The inline comment at ad_list.html L77 documents the *current* (divergent)
   clear-all behavior ("resets all query params (q, sort, …)") rather than the
   spec'd per-page behavior (preserve `q` on search). Should state: "On the
   search page, preserves `q`; on other pages, resets all query params."
