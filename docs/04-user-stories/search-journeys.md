---
id: search-journeys
domain: user-stories
tags:
  - user-stories
  - buyer
  - search
  - journeys
  - fts
related:
  - user-stories-index
  - buyer-stories
  - search-patterns
  - filter-ui
  - ui-patterns
  - technical-specification
---

# Search Journeys — Buyer Behavior Variants

This document describes the **distinct search journeys** a buyer can take through the
Mko Bazuna classifieds board, written from the buyer's point of view: "as a user, what
will I see on the screen, and what is the resulting URL + result state." Each journey is a
concrete behavior variant — homepage search, category-scoped search, filter-then-search,
and so on.

It focuses on **user-visible behavior** (screens, URL, result ordering, active filters).
Implementation details — FTS vectors, query params, model fields, index definitions —
live in the single source of truth: [`search-patterns.md`](../01-spec/search-patterns.md)
and [`filter-ui.md`](../01-spec/filter-ui.md). This doc summarizes behavior and links to
those specs rather than duplicating them.

Related research that compared these journeys against OLX/Avito and against the
implemented architecture lives under `../../.ai/research/` (e.g.
`olx-vs-avito-comparison.md`, `search-journeys-our-architecture.md`). Known gaps and bug
specs are tracked in `../../.ai/problems/Problem_01.md`.

## Purpose

Give product, design, and engineering a single place to see **every distinct search path**
a buyer can follow end-to-end, with the exact intermediate UI state and final result state
for each. This is the reference used when validating search behavior against user
expectations and against the OLX/Avito comparison.

## Main Concepts

- **Two engines:** the *listings* engine (no keyword, category/city/sort) and the *FTS*
  engine (`/search/?q=…`, PostgreSQL full-text search, relevance-ranked). See
  [`search-patterns.md > Multi-Language Search Flow`](../01-spec/search-patterns.md#multi-language-search-flow).
- **Header search bar is query-only:** the shared header form submits only `q`. It does
  **not** carry the active category, city, or filters. See [US-B2](buyer-stories.md)
  and the context-preservation gap in [Open Product Questions](#9-open-product-questions).
- **URL state is the source of truth:** every filter, sort, city, and page number is
  reflected in the URL via HTMX `hx-push-url="true"`, so Back/Forward and bookmarks
  restore state.
- **Preferences survive context loss:** a buyer's *preferred city* (cookie for guests,
  `User.preferred_city` for signed-in buyers) is re-applied by middleware as a default,
  even when the header search drops an explicit city.

## Legend (used in the step tables below)

- **User action** — what the buyer clicks/types.
- **What the buyer sees** — the rendered screen or fragment.
- **URL / state** — browser URL after the action; HTMX swaps update this without a full
  reload.
- **Result state** — the effective engine + active filters/sorts + result ordering.

---

## 1. Journey: Homepage → type a query → view results

*[US-B2](buyer-stories.md), [US-B9](buyer-stories.md), [US-B10](buyer-stories.md)*

| Step | User action | What the buyer sees | URL / state | Result state |
|------|-------------|---------------------|-------------|--------------|
| 1 | Land on `/`. | Header with brand, "All Categories" dropdown, city button (e.g. "Вся страна"), and the empty search bar. Below: a 24-card grid of the newest published ads, newest-first. Filter bar shows purpose/condition/price/features controls and a **Sort by** dropdown. | `GET /` | Listings engine. `sort=date_desc` (default). City = preferred (or country-wide). Page 1. |
| 2 | Focus the search bar. | Autocomplete dropdown opens: "Show all results" link, then Cities / Categories / Popular / History sections (History empty on first visit; Popular may be empty on low traffic). | No URL change (XHR to `search:autocomplete`). | No state change. Read-only suggestion query, rate-limited. |
| 3 | Type `ноутбук`. | Dropdown refines per prefix. The "Show all results" link now points to `/search/?q=ноутбук`; category suggestions may include "Ноутбуки". | No URL change (XHR). | No state change. |
| 4 | Press Enter. | Full-page navigation. Header input is now pre-filled with `ноутбук`. The grid shows FTS-ranked results. The **Sort by** dropdown is hidden (see [Sorting (listings only)](#sorting-listings-only)). | `GET /search/?q=ноутбук` | FTS engine, Russian vector. Ordering: `-rank, -published_at, -id`. The single word `ноутбук` also triggers fuzzy category detection, which may auto-scope results to the "Ноутбуки" subtree. `page=1`. Query written to history. |
| 5 | Click "Next" / page 2. | Grid updates to the next 24 cards; header stays intact. | `GET /search/?q=ноутбук&page=2` (pushed to history) | Page advances; rank ordering preserved; `q` preserved. |

**Sorting note:** on FTS results the dropdown is hidden and a `sort=` param is ignored;
results are relevance-ranked only. See [Sorting (listings only)](#sorting-listings-only).

---

## 2. Journey: Homepage → pick a category → apply filters → type a query → results

*[US-B3](buyer-stories.md), [US-B6](buyer-stories.md), [US-B2](buyer-stories.md)*

| Step | User action | What the buyer sees | URL / state | Result state |
|------|-------------|---------------------|-------------|--------------|
| 1 | Open "All Categories" → click `Транспорт`. | Header "All Categories" label becomes "Транспорт". Breadcrumb: `Home › Транспорт`. The filter bar's purpose features now reflect the transport set (e.g. purposes `sell`/`rent`; features `delivery`, `pickup`, …). Grid shows transport ads, newest-first. | `GET /category/transport/` | Listings engine, category subtree = transport. `sort=date_desc`. Page 1. |
| 2 | Pick `listing_purpose=rent`, add feature `delivery`, set price `min_price=1000`. Click "Apply filters". | Chosen values become sticky in the form; chips appear for Purpose and `delivery`; grid narrows to transport ∩ rent ∩ delivery ∩ price≥1000. | HTMX `GET /category/transport/?listing_purpose=rent&features=delivery&min_price=1000&page=1` (URL pushed) | Listings, transport ∩ purpose ∩ features (AND) ∩ price. Page 1. |
| 3 | Type `iphone` in the header search; press Enter. | Full-page navigation to results. **The transport category and the rent/delivery/price filters are dropped** — only `iphone` is searched. | `GET /search/?q=iphone` | FTS engine, site-wide. `iphone` is not a category-name fuzzy match, so no subtree is auto-applied. Results rank by `-rank, -published_at, -id`. |
| 4 | From the results page, open the on-page filter form, pick `listing_purpose=rent` + feature `credit`. Click "Apply filters". | The form now targets `/search/` (the current path) and carries the hidden `q=iphone`. Grid narrows to FTS results ∩ rent ∩ credit. Chips for the new filters appear. | HTMX `GET /search/?q=iphone&listing_purpose=rent&features=credit&page=1` (URL pushed) | FTS results additionally constrained by purpose + features. `q` retained across pages. |

**Observation:** OLX/Avito preserve the category + filter context when refining a query
from a category page. Our header bar carries only `q`, so the buyer must re-scope (via the
autocomplete category suggestion) or rely on single-word fuzzy category detection. This is
the core context-preservation gap — see [Open Product Questions](#9-open-product-questions) and
[`filter-ui.md`](../01-spec/filter-ui.md).

---

## 3. Journey: Homepage → type a query → apply filters → refine

*[US-B2](buyer-stories.md), [US-B3](buyer-stories.md), [US-B7](buyer-stories.md)*

| Step | User action | What the buyer sees | URL / state | Result state |
|------|-------------|---------------------|-------------|--------------|
| 1 | On `/`. Type `авто`; press Enter. | Header input pre-filled. Grid shows FTS-ranked results. No "Sort by" dropdown. | `GET /search/?q=авто` | FTS engine, Russian vector, `-rank, -published_at, -id`. Page 1. |
| 2 | Set `min_price=500`, `max_price=5000`, `listing_purpose=sell`, feature `negotiable`. Click "Apply filters". | Form's hidden `q` input preserves `авто`; selects/inputs reflect new values; feature chips appear; grid stays FTS-ranked but within the narrowed set. | HTMX `GET /search/?q=авто&min_price=500&max_price=5000&listing_purpose=sell&features=negotiable&page=1` (URL pushed) | FTS ∩ price(in EUR) ∩ purpose ∩ feature(AND). Page 1. |
| 3 | Click the `negotiable` chip's ×. | Chip disappears; grid re-renders with `negotiable` removed. | HTMX (chip link omits that feature) pushes `GET /search/?q=авто&min_price=500&max_price=5000&listing_purpose=sell&page=1` | Same as above minus `negotiable`. All other filters retained. |
| 4 | Click "Clear all filters" (top of chip bar). | All chips vanish; form resets; grid re-renders still FTS-ranked (because `q=авто` is kept). | HTMX `GET /search/?q=авто&page=1` (drops city/category/condition/features/price/purpose; keeps `q` + `sort`) | Back to plain `/search/?q=авто`, page 1. |

---

## 4. Journey: Category page → type a query → results

*[US-B2](buyer-stories.md), [US-B3](buyer-stories.md), [US-B6](buyer-stories.md)*

| Step | User action | What the buyer sees | URL / state | Result state |
|------|-------------|---------------------|-------------|--------------|
| 1 | Go to `/category/electronics/`. | Breadcrumb `Home › Товары > Электроника`. Filter bar shows electronics-resolved purposes (`sell`) + features + conditions (`new`/`used`). Grid shows electronics ads. | `GET /category/electronics/` | Listings engine, category = electronics. `sort=date_desc`. Page 1. |
| 2 | Type `macbook` in the header search; press Enter. | Full-page navigation. Only `macbook` is submitted. | `GET /search/?q=macbook` | FTS engine. `macbook` is single-word; fuzzy category detection checks the slug + exact name + difflib(0.8) — there is no category named "macbook", so **no subtree is auto-applied**. Results are site-wide FTS, rank-ordered. |
| 3 | To keep electronics scope, use the autocomplete category suggestion instead. | Type `электроника` → a category suggestion appears. Click it. | Click → full-page nav to `GET /category/electronics/` | Back on the listings engine, no `q`. |

**Gap:** once on `/search/?q=`, there is **no category control** in the filter form, so
category scope can only be re-established by leaving the page (autocomplete category link)
or by triggering the single-word fuzzy detection. The recommended OLX/Avito behavior is
context preservation. See [Open Product Questions](#9-open-product-questions).

---

## 5. Journey: Category page → apply filters → browse

*[US-B3](buyer-stories.md), [US-B6](buyer-stories.md)*

| Step | User action | What the buyer sees | URL / state | Result state |
|------|-------------|---------------------|-------------|--------------|
| 1 | On `/category/transport/`. | Filter bar shows transport-resolved options: purposes `sell`/`rent`, features, conditions `new`/`used`. Grid shows newest transport ads. | `GET /category/transport/` | Listings engine, category = transport. `sort=date_desc`. Page 1. |
| 2 | Pick `listing_purpose=rent`, features `credit` + `urgent`, `min_price=200`, sort "Price: High to Low". Click "Apply filters". | Form goes sticky; chips for Purpose + 2 features appear; grid re-sorts by price descending. Sort dropdown is present (this is a listings page). | HTMX `GET /category/transport/?listing_purpose=rent&features=credit&features=urgent&min_price=200&sort=price_desc&page=1` (URL pushed) | Listings, transport ∩ purpose ∩ features (AND) ∩ price. `sort=price_desc`. Page 1. |
| 3 | Click the `urgent` chip's ×. | `urgent` removed; `credit` retained; grid re-renders. | HTMX chip-link pushes `GET /category/transport/?features=credit&...&page=1` (path stays; category is in the path, not a param) | `features=[credit]`; purpose/price/sort retained. |
| 3b | Click "Clear all filters". | Resets to base category page. | HTMX `GET /category/transport/?page=1&sort=price_desc` (keeps `sort`) | Page 1; no purpose/condition/features/price; sort retained. |

**Note on category-in-path:** on `/category/<slug>/` the chip/pagination links are
relative, so the category is preserved by the URL path itself — unlike `/search/?q=`
where category is only a param the header form never sets.

---

## 6. Journey: Ad detail → start a new search → results

*[US-B2](buyer-stories.md), [US-B4](buyer-stories.md)*

| Step | User action | What the buyer sees | URL / state | Result state |
|------|-------------|---------------------|-------------|--------------|
| 1 | Open `/<ad_id>/`. | Header search bar (same everywhere) + the ad article: gallery, title, price (seller's original currency), description, feature chips, and a "Contact Seller" Telegram deep-link. A "← Back to listings" link at top. | `GET /<ad_id>/` | Single-ad view. No filter/sort state. |
| 2 | Type `ноутбук` in the header search; press Enter. | Full-page navigation to results. Only `q` is sent — the ad's category and city are **not** carried. | `GET /search/?q=ноутбук` | FTS engine. `ноутбук` is single-word → fuzzy category detection may auto-scope to the "Ноутбуки" subtree. Rank ordering, page 1. New history entry recorded. |
| 3 | Press browser Back. | Returns to the ad detail page exactly as left. | Pop `GET /<ad_id>/` | Pre-search state restored — the header search is a normal full-page submit, so it pushed a standard history entry that Back pops cleanly. |

---

## Cross-Cutting Buyer Behaviors

### Sorting (listings only)

- **Listings engine** (`/` and `/category/<slug>/`): the "Sort by" dropdown offers newest/oldest/price-low/price-high. Price sorts use the EUR-normalized `price_normalized_eur` column (`NULLS LAST`). Default = newest (`date_desc`). See [`search-patterns.md > Sort Options`](../01-spec/search-patterns.md#sort-options).
- **FTS engine** (`/search/?q=`): the dropdown is **hidden** and a `sort=` param is ignored. Results are relevance-ranked (`-rank, -published_at, -id`) only. The buyer cannot pick a sort on keyword results.

### Autocomplete suggestions

*[US-B10](buyer-stories.md)*

| Source | What the buyer sees | Notes |
|--------|---------------------|-------|
| History | Buyer's own past queries | Auth: from `SearchHistory` (DB); anonymous: from the Django session keyed by `sessionid`. Max 5 shown. |
| Cities | Matching city names | Prefix match on localized name; cities are not filtered by `is_active`. |
| Categories | Matching category names | Prefix match on the locale-appropriate name. |
| Popular | Frequently searched terms | Only appears once a term reaches `hit_count >= 10` — so on a low-traffic site the Popular section is empty by design. |

The merged list is deduplicated by text and capped at 10. Excess requests are throttled
(30 per minute per IP — the dropdown simply pauses). Clicking a city navigates to `/city/<slug>/`;
a category navigates to `/category/<slug>/`; a text suggestion fills the input and submits
the search.

### City handling as a buyer sees it

*[US-B3](buyer-stories.md), [US-B7](buyer-stories.md)*

- A buyer's **preferred city** (chosen via the header city button) becomes the default city
  filter everywhere — shown as the header button label (e.g. "Podgorica" or "Вся страна").
- An explicit city in a URL (`/city/<slug>/` or `?city=`) always overrides the preference.
- A typo'd city on a **listings** page yields a "Did you mean:" banner (fuzzy, `difflib`
  cutoff 0.6). On the **search** page an unknown `?city=` is echoed back with no fuzzy
  match (gap — see [Open Product Questions](#9-open-product-questions)).

### Search history & saved searches

*[US-B12](buyer-stories.md), [US-B11](buyer-stories.md)*

- Every FTS query with a non-empty `q` is recorded: auth buyers get a `SearchHistory` row
  (deduped by normalized query, capped at 50); anonymous buyers get a session-scoped entry.
- Recorded queries feed the autocomplete "History" section and appear on the
  `/cabinet/search-history/` page (auth only) with a "Clear history" button.
- Buyers can save a search (auth only, button on `/search/?q=`) and get a Telegram
  notification when a new matching ad is published.

### Language

*[US-B9](buyer-stories.md)*

- Choosing `ru`/`bs`/`en` re-runs FTS against the matching per-language vector — no
  query-time translation. Ad content is translated once at publication into Russian.
- Language is re-applied from the `lang_pref` cookie on load, so the *display* stays
  correct even if a filter change momentarily drops `?lang=` from the URL.

### Search-input clear (×) control

*[Problem_01.md #1](../../.ai/problems/Problem_01.md)*

- The header search uses a native `<input type="search">`, so the browser renders its own
  clear-X. Clicking it only empties the field — it does **not** submit or navigate, so the
  URL and results stay on `/search/?q=<old>`. There is no explicit, wired clear control in
  the markup. The expected behavior is to return the buyer to the pre-search state.

---

## 7. Journey Capability Matrix

How each journey behaves at the transition into `/search/?q=` and within it.

| Journey | Entry | Results URL | Engine | Category kept via header search? | City kept via header search? | Sort on results? | History recorded? |
|---------|-------|-------------|--------|----------------------------------|------------------------------|------------------|-------------------|
| 1. Home → query → results | `/` | `/search/?q=<t>` | FTS | No — header sends only `q` | Preferred-city **default** re-applied by middleware; an explicit `/city/<s>/` path is dropped | No (rank only) | Yes |
| 2. Home → category+filter → query → results | `/` → `/category/<c>/` | `/search/?q=<t>` | FTS | No — lost on header submit | Preferred-city **default** re-applied; category path dropped | No (rank only) | Yes |
| 3. Home → query → filters → results | `/` → `/search/?q=<t>` | `/search/?q=<t>&<filters>` | FTS (refine) | None to carry | Preferred-city **default** applies | No (rank only) | Yes (on the query step) |
| 4. Category → query → results | `/category/<c>/` | `/search/?q=<t>` | FTS | No — lost | Preferred-city **default** re-applied; category path dropped | No (rank only) | Yes |
| 5. Category → filters → results | `/category/<c>/` | `/category/<c>/?<filters>` | Listings | Yes — via URL path | Yes — via path / preferred fallback | Yes (`?sort=`) | n/a (not a search) |
| 6. Detail → query → results | `/<id>/` | `/search/?q=<t>` | FTS | No — ad's category not carried | Preferred-city **default** re-applied; ad's city not carried | No (rank only) | Yes |

Legend: **FTS** = PostgreSQL full-text search on per-language `search_vector_*` columns.
"kept via header search?" = whether the value survives the shared header form submission.
Preferred-city re-application is a *default*, not the buyer's explicit choice — an
explicit city (`?city=`/`/city/<s>/`) is dropped by the header search.

---

## 8. URL/State Contract Reference

The exact query-param names, endpoints, and persistence rules (e.g. `min_price`/`max_price`,
`condition`, repeated `features=` for AND-semantics, rate limits, preferred-city persistence)
are specified in the single source of truth — [`search-patterns.md`](../01-spec/search-patterns.md)
and [`filter-ui.md`](../01-spec/filter-ui.md). The URL shapes used in each journey above are
already captured inline in the step tables, so they are not repeated here.

---

## 9. Open Product Questions

1. **Sort on FTS results.** Should `/search/?q=…` honor `?sort=` (with relevance as the
   default) or stay rank-only? The spec implies a sort selector; the templates hide it.
   Cross-ref: [`search-patterns.md`](../01-spec/search-patterns.md) vs.
   [`filter-ui.md`](../01-spec/filter-ui.md).
2. **Search-input clear (×).** Navigate to `/` (last browsing state) or `history.back()`?
   Recommended by the OLX/Avito comparison: return to the pre-search state.
3. **Header-search context preservation.** Should the header bar carry the active category
   (path → `?category=`) and city when submitting from a `/category/…` or `/city/…` page,
   matching OLX/Avito? Currently dropped in journeys 2, 4, and 6.
4. **Autocomplete popular gate.** Is `min_hit_count=10` intended for MVP, or should popular
   suggestions degrade gracefully on low traffic so the dropdown never reads as "only
   history" ([Problem_01.md #1](../../.ai/problems/Problem_01.md))?

---

*End of document.*
