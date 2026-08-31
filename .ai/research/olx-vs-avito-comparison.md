# OLX vs Avito Search UX — Comparison & Unified Flow Recommendation

> **Date:** 2026-08-29  
> **Purpose:** Compare the two research agents' findings (OLX.kz vs Avito.ru), distill common patterns, identify key differences, and propose a unified search flow for Mko Bazuna.

---

## 1. Common Patterns (Both Platforms)

| # | Pattern | OLX Behavior | Avito Behavior |
|---|---------|--------------|----------------|
| 1 | **Hero search in persistent header** | Always-visible header on all pages; query input + location combobox + submit button + X clear button | Always-visible header search field on all pages; focused opens suggestion panel |
| 2 | **URL carries all state** | `/list/q-{query}/?...filters...` or `/{category}/q-{query}/?...filters...` — query in path, filters in query params | `/{region}/{category}?q=...&pmin=...&pmax=...&...` — query in param, city+category in path |
| 3 | **Back/Forward preserves all state** | SPA back-button preserves all filter params (+ hash for scroll anchor); back from search to homepage clears input | SPA `pushState` preserves region+category+query+filters+sort across Back/Forward |
| 4 | **Autocomplete on focus + as-you-type** | Dropdown on focus shows recent searches ("Вы недавно искали") + recommendations; updates as-you-type | Dropdown on focus shows recent + popular; live suggestions from ~2-3 chars |
| 5 | **Search history in autocomplete** | Recent searches stored in localStorage/session; each has individual × clear button | Recent searches shown on focus; clicking re-runs the search |
| 6 | **Price range filter** | Two inputs (`search[filter_float_price:from]` / `:to]`); auto-applied with debounce | Two inputs `pmin`/`pmax`; auto-applied |
| 7 | **Photo-only filter** | Checkbox `search[photos]=1`; auto-applied | Checkbox `cd=1`; auto-applied |
| 8 | **Multi-select filters (checkboxes)** | Category-specific attributes (e.g. "В рассрочку", "Состояние") with toggle buttons | `sids=<id1>,<id2>` comma-joined checkbox IDs |
| 9 | **Sort dropdown** | 4 options: "Рекомендованное" (default), "Самые новые", "Самые дешевые", "Самые дорогие" | 4 options: "По дате" (default), "По цене" (asc), "По убыванию цены" (desc), "По релевантности" |
| 10 | **Category-scoped search** | Category chips above results (with counts); clicking → `/{category}/q-{query}/?...filters...` | Category is in the URL path; selecting category rewrites path root |
| 11 | **Active filter chips** | Filter chips shown above results; each has × to remove individually; "Показать все" resets category | Individual × on active price inputs; "Сбросить" clears all |
| 12 | **Clear/reset** | X in query input clears query only (preserves filters); "Сбросить фильтры" clears all + resets to `/list/` | × on price removes bound; "Сбросить" clears all filters, returns to region+category+query |
| 13 | **Save search / alerts** | "Сохранить параметры поиска" panel with "Сохранить" button | "Сохранить поиск" button for logged-in users |
| 14 | **Pagination preserves state** | `?page=N` prepended; all filters + sort preserved on pagination | `p=N` (1-based); all params preserved |
| 15 | **Empty/recent query behavior** | Focusing empty input shows history + recommendations; repeat query re-runs search | Re-submitting same term re-runs search, preserves filters, resets to page 1 |

---

## 2. Key Differences

### 2.1 Query in URL

| Aspect | OLX | Avito |
|--------|-----|-------|
| **Query placement** | In the **path** (`q-{query}`) | In a **query param** (`?q=query`) |
| **Implication** | Path-based is cleaner/SEO-friendlier but harder to parse programmatically | Query param is traditional; easy to construct/parse |
| **Mko recommendation** | Use query param (`?q=`, like Avito) — simpler, consistent with existing `listings.py`/`search.py` architecture |

### 2.2 City/Location in URL

| Aspect | OLX | Avito |
|--------|-----|-------|
| **City placement** | Combobox; URL param encoding **not captured** (may be session/cookie-based) | **Path segment** (`/moskva/` as URL root) — first-class, always in URL |
| **City selector** | Modal-like listbox with region→city cascade (18 regions → cities) | Header region label; city picker rewrites path root |
| **Implication** | OLX city is not reliably URL-addressable; state may be lost on refresh | Avito city is always shareable/bookmarkable |
| **Mko recommendation** | Our current architecture uses `/city/<slug>/` path + `?city=` param — **adopt Avito's path-first approach** (city in URL path, always shareable) |

### 2.3 Sort Encoding

| Aspect | OLX | Avito |
|--------|-----|-------|
| **Sort param** | Readable: `search[order]=created_at:desc` | Opaque numeric: `s=104` |
| **Default sort** | "Рекомендованное вам" (relevance/recommended) | "По дате" (newest first + boosted ads) |
| **Implication** | Readable values are maintainable but verbose | Numeric codes are compact but require a mapping table |
| **Mko recommendation** | Use readable string values (`?sort=date_desc` etc.) — already our `AdSort` StrEnum; keep as-is |

### 2.4 Language Switching

| Aspect | OLX | Avito |
|--------|-----|-------|
| **Language switcher** | Yes — Kazakh via `/kk/` prefix (preserves query + filters) | **No** — RU-only UI; relies on browser auto-translate |
| **Implication** | OLX is multilingual; Avito is monolingual | Mko Bazuna supports `ru`/`en`/`bs` — **keep the language switcher** (do not follow Avito's no-switcher approach) |

### 2.5 Filter Apply Model

| Aspect | OLX | Avito |
|--------|-----|-------|
| **Light filters** (price, photos) | Auto-applied with debounce | Auto-applied |
| **Heavy/category-specific filters** | Toggle buttons ("Все объявления" by default) | "Фильтры" panel with explicit apply |
| **Both** | Some filters are explicit-apply (sort dropdown) | Same split |
| **Mko recommendation** | Our filter form already uses a submit button ("Apply filters") with HTMX — **consider auto-apply for price inputs** but keep explicit apply for category-specific attribute filters |

### 2.6 Clear Behavior

| Aspect | OLX | Avito |
|--------|-----|-------|
| **Clear query (X in input)** | Clears query text only, re-searches, preserves filters | Clearing query removes `q=`, keeps path (region+category) |
| **Reset all** | "Сбросить фильтры" → `/list/q-{query}/` (clears all filters, resets category to site-wide) | "Сбросить" → region+category+query retained, all other filters cleared |
| **Mko recommendation** | Clear should return to pre-search state (address Problem_01.md bug #2) |

---

## 3. Unified Search Flow Recommendation for Mko Bazuna

Based on the comparison, here is the proposed unified search flow that combines the best of both platforms and aligns with our existing architecture:

### 3.1 Core Principles

1. **All state in the URL** — query, category, city, filters, sorting, page, language — everything must be URL-addressable and shareable (Avito's strongest pattern).
2. **City as path-first** — `/city/<slug>/` is the primary city mechanism; `?city=` as a query param is secondary (already our architecture).
3. **Readable sort values** — `?sort=date_desc|date_asc|price_asc|price_desc` (our existing `AdSort` StrEnum).
4. **Auto-apply light filters** (price inputs, photo-only) with debounce; explicit "Apply" for attribute filters.
5. **Back/Forward preserves everything** — leverage `hx-push-url="true"` (already used) and ensure the full filter/sort/page state is in the URL.
6. **Keep language switcher** (`?lang=ru|bs|en` or cookie) — unlike Avito, we are multilingual.
7. **Clear resets to pre-search state** — the X button in the search bar should return to the last browsing state (homepage or category page), not just clear the query field. This directly fixes Problem_01.md bug #2.

### 3.2 Entry Points

| Entry Point | URL | Behavior |
|-------------|-----|----------|
| **Homepage** | `/` | Shows all published ads (default city filter from preferred-city middleware + default sort) |
| **Header search** | `/search/?q=...&category=...&city=...&sort=...&...filters` | FTS search; preserves filters via hidden inputs + query params |
| **Category nav** | `/category/<slug>/` | Category-subtree listing; search from header adds `?q=...` |
| **City nav** | `/city/<slug>/` | City-filtered listing; search from header adds `?q=...` |
| **Autocomplete → category** | `/category/<slug>/` | Navigate to category page |
| **Autocomplete → city** | `/city/<slug>/` | Navigate to city listing (sets preferred city) |
| **Autocomplete → text** | `/search/?q=<text>` | Populate input, submit search form |

### 3.3 State Management Rules

| State Element | URL Representation | Preserved On |
|---------------|-------------------|--------------|
| Search query | `?q=<text>` on `/search/` | All navigation within search results |
| Category | `?category=<slug>` on `/search/`; `/category/<slug>/` path on listings | Pagination, sort change, filter change |
| City | `?city=<slug>` on `/search/`; `/city/<slug>/` path on listings | Pagination, sort change, filter change |
| Sort | `?sort=<AdSort value>` | Pagination, filter change |
| Page | `?page=N` | Sort change resets to page 1; filter change resets to page 1 |
| Price min/max | `?min_price=N` / `?max_price=N` | All navigation |
| Listing purpose | `?listing_purpose=<slug>` | All navigation |
| Condition | `?condition=<slug>` | All navigation |
| Features | `?features=<slug>` (repeated) | All navigation |
| Language | `?lang=<code>` query param or `lang_pref` cookie | All navigation |

### 3.4 Clear/Reset Behavior (Fix for Problem_01.md)

- **Clear search (X button in search bar):** Navigate to the referer or last browsing position (homepage `/` or current category page `/category/<slug>/`). Drop `?q=` and all filter params. This returns the user to the **state before search was initiated** — fixing bug #2.
- **Clear individual filter:** Remove just that param, reset to page 1, preserve all other params.
- **Clear all filters:** Reset to the base listing page (homepage or current category), drop all params except language.

### 3.5 Autocomplete Behavior (Fix for Problem_01.md)

- **Problem:** First search shows autocomplete; second search only shows history (no suggestions), persisted in cookies.
- **Fix:** Always show the full merged suggestion set (user history + entity suggestions + popular searches) on every focus + keystroke. Do **not** persist "only history" state — the autocomplete endpoint already supports all sources; the issue is client-side (likely a cookie-based flag or stale state). Ensure the dropdown always re-queries the autocomplete endpoint.

---

## 4. Scenarios to Model

The following six scenarios must be covered in the detailed specification:

1. **Homepage → enter search query → search results**
2. **Homepage → select category/filters → enter search query → results**
3. **Homepage → enter query → apply filters → results**
4. **Category page → enter search query → results**
5. **Category page → apply filters → results**
6. **Product/ad detail page → initiate a new search → results**

Plus cross-cutting state interactions:
- Sorting selection & URL encoding
- Language selection
- City selection
- Search history
- Different autocomplete suggestion types

---

## 5. Recommended Unified Approach (Decision Matrix)

| Concern | OLX pattern | Avito pattern | **Recommended for Mko Bazuna** | Rationale |
|---------|-------------|---------------|-------------------------------|-----------|
| Query in URL | Path: `/q-{query}/` | Param: `?q=query` | `?q=<text>` (param) | Simpler, consistent with existing search.py; avoids URL path parsing complexity |
| City in URL | Combo-box (unreliable in URL) | Path: `/moskva/` | `/city/<slug>/` path (already exists) | Path-first is shareable/SEO-friendly; matches our current architecture |
| Category in URL | Path: `/{slug}/q-{query}/` | Path: `/{region}/{category}/` | `/category/<slug>/` path (already exists) | Consistent with our listings view |
| Sort encoding | Readable: `field:direction` | Numeric: `s=104` | Readable StrEnum: `sort=date_desc` | Already our AdSort; self-documenting, maintainable |
| Default sort | "Recommended" (relevance) | "Newest" (date + boosts) | **Newest first** (`date_desc`) | Simpler to explain; no ML ranking in phase 1 |
| Filter apply | Mixed (some auto, some explicit) | Mixed (light auto, heavy panel) | **Explicit "Apply filters"** (current behavior) | Predictable; no surprises from auto-navigation. Consider auto-apply for price inputs only. |
| Clear query | X clears query only, preserves filters | Removes `q=`, keeps path | **X returns to pre-search state** | Fixes Problem_01.md bug #2 |
| Language | Switcher with path prefix (`/kk/`) | No switcher (RU-only) | **Keep switcher** (`?lang=` or cookie) | We are multilingual |
| Autocomplete | Always show on focus + type | Always show on focus + type | Always show full merged set | Fixes Problem_01.md bug #1 |
| Results per page | ~30 | 50 | 24 (current) | Keep current; can revisit |
| Back/Forward | Preserve all state + scroll anchor | Preserve all state via pushState | Preserve all state | Already using `hx-push-url="true"` |

*End of comparison document.*
