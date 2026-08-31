---
id: search-journeys-spec
domain: search
tags:
  - search
  - ux
  - specification
  - validation
related:
  - search-patterns
  - filter-ui
  - buyer-stories
---

# Search User Journeys — Final Specification

> **Purpose:** Concise specification of recommended search user journeys for Mko Bazuna, adapted to our architecture and ready for implementation + validation.
>
> **Derived from:**
> - OLX.kz research (`olx-search-journeys.md`)
> - Avito.ru research (`avito-search-journeys.md`)
> - OLX vs Avito comparison (`olx-vs-avito-comparison.md`)
> - Architecture mapping (`search-journeys-our-architecture.md`)
> - Validation criteria (`search-journeys-validation.md`)
>
> **Date:** 2026-08-29

---

## 1. Summary of Findings

### Common Patterns (OLX + Avito)
1. **Hero search in persistent header** — visible on every page.
2. **All state in the URL** — query, category, city, filters, sort, page all URL-addressable.
3. **Back/Forward preserves state** — SPA or full-page navigation, state survives browser history.
4. **Autocomplete on focus + as-you-type** — recent searches, popular queries, matching categories/cities.
5. **Price range + photo-only filters** — auto-applied (debounced).
6. **Multi-select (checkbox) + single-select (dropdown) filters** — combinable.
7. **Active filter chips** — removable individually; "clear all" resets.
8. **Save search / alerts** — for logged-in users.
9. **Sort by date or price** — default = newest first (Avito) or relevance (OLX).

### Key Differences
| Concern | OLX | Avito | **Mko Bazuna decision** |
|---------|-----|-------|------------------------|
| Query in URL | Path (`/q-{query}/`) | Param (`?q=query`) | **Param** (`?q=`) — simpler, matches our `search.py` |
| City in URL | Combobox (not reliably URL-encoded) | Path segment (`/moskva/`) | **Path** (`/city/<slug>/`) — our current design, Avito-style |
| Sort encoding | Readable (`field:direction`) | Numeric (`s=104`) | **Readable** (`sort=date_desc`) — our `AdSort` StrEnum |
| Default sort | "Recommended" (relevance) | "Newest" (date + boosts) | **Newest first** (`date_desc`) — no ML ranking in phase 1 |
| Language | Multi (`ru`, `/kk/`) | **No switcher** (RU-only) | **Keep switcher** (`?lang=ru|bs|en`) — we are multilingual |
| Results/page | ~30 | 50 | **24** — keep current |

### Two Bugs Identified (Problem_01.md)
1. **Autocomplete regression:** On repeat/empty query, only history shown (no suggestions). Root cause: popular-search suggestions gated by `hit_count >= 10` (empty on low-traffic instances); anonymous history stored in Django session (`sessionid` cookie). Needs runtime investigation.
2. **Clear (X) button does nothing:** The search input is `<input type="search">` — browsers render a native clear-X that only clears the field without navigating. **No explicit wired clear button exists.** Needs an explicit control that returns to pre-search state.

---

## 2. Architecture Quick Reference

### URL Map (actual implementation)
| Method | URL | View | Name |
|--------|-----|------|------|
| GET | `/` | `listings` | `ads:listings` |
| GET | `/category/<slug>/` | `listings` | `ads:listings_category` |
| GET | `/city/<slug>/` | `listings` | `ads:listings_city` |
| GET | `/<int:ad_id>/` | `ad_detail` | `ads:detail` |
| GET | `/search/?q=…&[filters]` | `search` | `search:search` |
| GET | `/api/search/autocomplete?q=` | `autocomplete` | `search:autocomplete` |
| POST | `/api/preferred-city/` | `set_preferred_city` | `search:preferred_city` |
| GET | `/cabinet/search-history/` | `search_history_list` | `cabinet:search-history` |

### Concrete Filter Values
| Dimension | URL param | Values | Type |
|-----------|-----------|--------|------|
| Search query | `q` | free text | FTS |
| Category | path: `/category/<slug>/` or `?category=<slug>` | category slugs | subtree match |
| City | path: `/city/<slug>/` or `?city=<slug>` | city slugs | exact match |
| Sort | `sort` | `date_desc`, `date_asc`, `price_asc`, `price_desc` | single-select |
| Min price | `min_price` | integer (EUR-normalized) | range |
| Max price | `max_price` | integer (EUR-normalized) | range |
| Listing purpose | `listing_purpose` | `sell`, `give-away`, `rent`, `rent-short`, `lost`, `found`, `offer-service`, `seek-service`, `job-offer`, `job-seek` | single-select dropdown |
| Condition | `condition` | `new`, `used` | single-select dropdown |
| Features | `features` (repeated) | `delivery`, `pickup`, `negotiable`, `credit`, `exchange`, `installment`, `urgent`, `luxury`, `eco`, `handmade`, `branded`, `custom`, `warranty`, `packaging`, `import`, `local`, `smart-home` | multi-select checkboxes (AND) |
| Page | `page` | integer (1-based) | pagination |
| Language | `lang` (query) or `lang_pref` (cookie) | `ru`, `bs`, `en` | switcher |

### Sorting (`AdSort` StrEnum)
| Value | Effect (listings / no-`q`) | Effect (search with `q`) |
|-------|---------------------------|--------------------------|
| `date_desc` (default) | `-published_at` | Overridden by FTS rank |
| `date_asc` | `published_at` | Overridden by FTS rank |
| `price_asc` | `price_normalized_eur` ASC, NULLS LAST | Overridden by FTS rank |
| `price_desc` | `price_normalized_eur` DESC, NULLS LAST | Overridden by FTS rank |

**FTS ordering** (when `q` present): `-rank, -published_at, -id` (relevance first, then newest, then stable id tiebreaker).

### HTMX Contract
- Filter form: `hx-get="{{ request.path }}"`, `hx-target="#ad-list"`, `hx-swap="innerHTML"`, `hx-push-url="true"`
- Pagination links: same contract, full param set preserved
- Chip removal: `hx-get` + `hx-push-url="true"` + `hx-target="#ad-list"`
- Non-HTMX → full page (`ads/list.html`); HTMX → fragment (`ads/partials/ad_list.html`)

### Known Implementation Gaps (must fix)
1. **Header search drops category/city/filters** — the header `<form>` (`header_catalog.html:114-132`) submits only `q`. Users entering a search from a category page lose the category context.
2. **Sort dropdown hidden on FTS results** — `{% if not query %}` gates the sort `<select>` in `filter_form.html:103-125`; `search()` ignores `sort=` when `q` is present.
3. **Clear (X) button is native** — no wired handler; does nothing useful.
4. **`lang=` may drop on HTMX transitions** — auto-applied only via cookie on next full reload.

---

## 3. Final Journey Specification

### Legend
- **Action** — what the user does
- **Intermediate Results** — what the user sees at each stage
- **Validation** — how to verify (test type + assertions)

---

### Scenario 1 — Homepage → enter search query → search results

| Step | User Action | Intermediate Results | Validation |
|------|------------|---------------------|------------|
| 1 | Land on `/`. | Header with city button ("Вся страна" or preferred city), "All Categories" dropdown, empty search bar. Full-page `ads/list.html` → `#ad-list` → `ad_list.html` with filter form (purpose/condition/price/features/sort all visible since no `q`), 24-card grid sorted newest-first. | **Integration** (`make test`): `Client().get("/")` → 200. Assert `response.context["query"]` is empty/None, `current_sort == "date_desc"`. Assert HTML has `id="search-input"` (empty value), `<form>` with `name="q"` only. Assert no hidden `name="category"`/`name="city"` in header form. Assert sort `<select name="sort">` present. |
| 2 | Focus the search bar. | Autocomplete dropdown (`#autocomplete-dropdown`) opens: "Show all results" link + Cities/Categories/Popular/History sections (all may be empty on first visit). | **Template-source** (`test_autocomplete_template.py`): assert `input#search-input` has `hx-get`, `hx-trigger="input delay:300ms"`, `hx-target="#autocomplete-dropdown"`, `hx-swap="none"`. **Integration** (`test_autocomplete.py`): `GET /api/search/autocomplete?q=""` → 200, `{"suggestions": [], "query": ""}`. |
| 3 | Type `ноутбук`, select a suggestion or press Enter. | Dropdown refines per prefix. "Show all results" link → `/search/?q=ноутбук`. Category "Ноутбуки" shown if it matches. | **Integration**: `GET /api/search/autocomplete?q=ну` → 200. Assert JSON has `suggestions` array; each item has `text`, `source`, `type`. Assert category suggestions include `category_path` + `slug` (`test_autocomplete.py::TestEntitySuggestionsService`). |
| 4 | Press Enter (or click "Show all results"). | Full-page nav to `/search/`. Header input shows "ноутбук". `#ad-list` shows `ad_list.html` — filter form still present (no sort dropdown now), but no `q` hidden input needed. Grid shows FTS-ranked results. | **Integration**: `Client().get("/search/?q=ноутбук")` → 200. Assert `response.context["query"] == "ноутбук"`, `response.context["current_category"] is None` (not carried). Assert HTML has **no** `<select name="sort"` (hidden when `query` truthy). Assert ordering is `-rank, -published_at, -id`. Assert `AnalyticsEvent.objects.filter(event_type="search_performed").exists()`. Assert `PopularSearch` incremented; `SearchHistory` or session history recorded. |
| 5 | Click page 2. | HTMX `hx-get`?page=2&q=ноутбук` → swap `#ad-list`, push URL. Header intact. Results show ads 25–48. | **Integration + HTMX**: `Client().get("/search/?q=ноутбук&page=2", headers={"HX-Request":"true"})` → 200, fragment. Assert `response.context["page_obj"].number == 2`. Assert pagination links carry `q=ноутбук&page=2` + `hx-push-url="true"`. Assert `content.count("hx-push-url=\"true\"") == 9` for pagination. |

**Test data needed:** Category "Ноутбуки" (slug `noutbuki`) under "Электроника"; 25+ PUBLISHED ads with "ноутбук" in title/description.

---

### Scenario 2 — Homepage → select category → apply filters → enter search query → results

| Step | User Action | Intermediate Results | Validation |
|------|------------|---------------------|------------|
| 1 | On `/`. Open "All Categories" dropdown. | Category panel slides down; root categories listed (Транспорт, Товары, etc.); submenus lazy-load via `fetch('/categories/<slug>/submenu/')`. | **Template-source**: assert `data-categories-toggle`, `data-categories-panel`, `data-category-link` present. **Integration**: `GET /` → HTML has `data-category-slug="..."` items and `<a href="/category/transport/">` links. |
| 2 | Click "Транспорт". | Full-page nav to `/category/transport/`. Breadcrumb: `Home › Транспорт`. Filter form options now constrained: purpose = sell/rent only; features = transport set; conditions = new/used. Grid shows transport ads. | **Integration**: `Client().get("/category/transport/")` → 200. Assert `response.context["current_category"] == "transport"`, `breadcrumb_category.slug == "transport"`. Assert `resolved_purposes` excludes `give-away` etc. |
| 3 | Pick `listing_purpose=rent`, feature `delivery`, `min_price=1000`. Click "Apply filters". | Form re-renders with sticky selections. Active chips appear (blue for purpose, green for features). Grid updates to matching ads. | **Integration + HTMX**: `Client().get("/category/transport/?listing_purpose=rent&features=delivery&min_price=1000", headers={"HX-Request":"true"})` → 200. Assert context vars match. Assert HTML has `bg-blue-100` purpose chip, `bg-green-100` feature chip with `×` removal links (`hx-push-url="true"`). Assert `page_obj` ads: `listing_purpose.slug == "rent"`, `features__slug="delivery"`, `price_normalized_eur >= 1000`. |
| 4 | Type `iphone` in header search; press Enter. | Full-page nav to `/search/?q=iphone`. **Category `transport` and all filters are dropped** (header form sends only `q`). | **Template-source + integration**: Assert header `<form>` (`header_catalog.html:114-132`) has only `name="q"` + `csrfmiddlewaretoken`. `Client().get("/search/?q=iphone")` → assert `current_category is None`, `current_listing_purpose is None`, `current_features == []`. FTS rank-ordered. |
| 5 | Re-apply filters: `listing_purpose=rent`, feature `credit`. Click "Apply filters". | Filter form on `/search/` now has hidden `q=iphone` (`filter_form.html:11`). No category input available. Results re-filtered by FTS + new filters. | **Integration + HTMX**: `Client().get("/search/?q=iphone&listing_purpose=rent&features=credit", headers={"HX-Request":"true"})` → 200. Assert `query == "iphone"`, `current_category is None`, `current_listing_purpose == "rent"`, `current_features == ["credit"]`. Assert filter form has hidden `<input name="q" value="iphone">`. |

**Gap:** Category context is lost on header search. Fix: carry `?category=` when submitting from a `/category/` page.

---

### Scenario 3 — Homepage → enter query → apply filters → results

| Step | User Action | Intermediate Results | Validation |
|------|------------|---------------------|------------|
| 1 | On `/`. Type `авто` in header search; press Enter. | Full-page nav to `/search/?q=авто`. Header input pre-filled. `#ad-list` renders with filter form (no sort dropdown) + grid. FTS rank-ordered. | **Integration**: `Client().get("/search/?q=авто")` → 200. Assert `query == "авто"`, no `<select name="sort"`. Assert `PopularSearch.objects.filter(query_normalized="авто").exists()`. For anon: `client.session["search_history"]` populated. |
| 2 | Set `min_price=500`, `max_price=5000`, `listing_purpose=sell`, feature `negotiable`. Click "Apply filters". | Hidden `q=авто` input preserves query. Chips update (blue/purple/green). Grid re-ranks within narrowed set. | **Integration + HTMX**: `Client().get("/search/?q=авто&min_price=500&max_price=5000&listing_purpose=sell&features=negotiable", headers={"HX-Request":"true"})` → 200. Assert all context vars. Assert chips with correct colors. Assert `page_obj` ads: `price_normalized_eur >= 500 AND <= 5000`, `listing_purpose.slug == "sell"`, `features__slug="negotiable"`. |
| 3 | Remove `negotiable` chip (×). | Chip disappears. Grid re-renders with feature constraint lifted. | **Template-source + integration**: Assert chip `×` link (`ad_list.html:64-65`) includes `q=авто`, `min_price=500`, `max_price=5000`, `listing_purpose=sell` but omits `features=negotiable`. `Client().get` that URL → assert `current_features == []`, `query == "авто"`, purpose still `sell`. |
| 4 | Click "Clear all filters". | Chips vanish. Form resets. Grid re-renders (still FTS-ranked since `q=авто` retained). | **Template-source + integration**: Assert "Clear all filters" href (`ad_list.html:71-74`) = `?page=1&q=авто&sort=<current>` — drops `city`/`category`/`condition`/`features`/`min_price`/`max_price`/`listing_purpose`. `Client().get` → assert `current_features == []`, `current_listing_purpose is None`, `min_price is None`, `max_price is None`, `query == "авто"`, `page_obj.number == 1`. |

**Test data needed:** Ads with "авто" in title/description, varying prices (some <500, some 500–5000, some >5000), purpose sell/rent, with/without `negotiable` feature.

---

### Scenario 4 — Category page → enter search query → results

| Step | User Action | Intermediate Results | Validation |
|------|------------|---------------------|------------|
| 1 | Navigate to `/category/electronics/`. | Breadcrumb `Home › Товары > Электроника`. Filter form shows electronics-resolved options (purpose=sell, condition=new/used, features=electronics set). Grid shows electronics ads. | **Integration**: `Client().get("/category/electronics/")` → 200. Assert `current_category == "electronics"`, `breadcrumb_category.slug == "electronics"`. Assert filter options match resolver output for electronics. |
| 2 | Type `macbook` in header search; press Enter. | Full-page nav to `/search/?q=macbook`. **Category `electronics` dropped** (header form). `|macbook` is single-word; `_fuzzy_category_match` checks slug + exact name + difflib(0.8) — no "macbook" category exists, so no subtree auto-constraint. Results = site-wide FTS. | **Integration**: `Client().get("/search/?q=macbook")` → 200. Assert `current_category is None`. Assert `query == "macbook"`, rank ordering. **Template-source**: assert header form has no `name="category"` hidden input. |
| 3 | Use autocomplete category suggestion instead. | Type `электроника` → category "Электроника" appears in dropdown. Click → full-page nav to `/category/electronics/`. | **Template-source + service**: `header_catalog.html:275-277` click handler for category does `window.location.href = '/category/' + slug + '/'`. **Integration** (`test_autocomplete.py::TestEntitySuggestionsService`): category suggestion includes `slug`, `category_path`, `type="category"`. |
| 3b | No category control on `/search/` page. | The on-page filter form has no category dropdown or hidden input — only purpose/condition/price/features/sort. | **Template-source**: Read `filter_form.html` — assert **no** `<select name="category">` or `<input name="category">`. Category can only be scoped via the URL path or autocomplete suggestion. |

---

### Scenario 5 — Category page → apply filters → results

| Step | User Action | Intermediate Results | Validation |
|------|------------|---------------------|------------|
| 1 | On `/category/transport/`. | Filter form options constrained: purpose = sell/rent, features = `{delivery, pickup, negotiable, credit, exchange, urgent, warranty}`, condition = new/used. | **Integration**: `Client().get("/category/transport/")` → 200. Assert `resolved_purposes` excludes `give-away`, `lost`, `found`, etc. Assert `resolved_features` matches transport set. |
| 2 | Pick `listing_purpose=rent`, features `credit` + `urgent`, `min_price=200`, `sort=price_desc`. Click "Apply filters". | Sticky selections in form. Chips for purpose + 2 features. Grid sorted by price descending (NULLs last). | **Integration + HTMX**: `Client().get("/category/transport/?listing_purpose=rent&features=credit&features=urgent&min_price=200&sort=price_desc", headers={"HX-Request":"true"})` → 200. Assert `current_sort == "price_desc"`, `current_features == ["credit", "urgent"]`, `current_listing_purpose == "rent"`, `min_price == "200"`. Assert `page_obj` ordered `price_normalized_eur DESC` (nulls last). Assert all ads: purpose=rent, has both credit+urgent, price ≥ 200. |
| 3 | Click `urgent` chip ×. | `urgent` chip removed; `credit` retained; grid re-renders. Path stays `/category/transport/`. | **Template-source + integration**: Assert chip `×` link (`ad_list.html:64-65`) includes `features=credit`, `sort=price_desc`, `min_price=200`, `listing_purpose=rent` but omits `features=urgent`. `Client().get` → assert `current_features == ["credit"]`, `current_sort == "price_desc"`, `current_listing_purpose == "rent"`. |
| 3b | Click "Clear all filters". | Resets to base transport page (page 1, no filters). Sort is **retained** (clear-link re-emits only `page=1` + `sort`). | **Template-source**: Assert `ad_list.html:71-74` href = `?page=1{% if query %}&q=...{% endif %}{% if current_sort %}&sort=...{% endif %}`. **Integration**: `Client().get("/category/transport/?page=1&sort=price_desc")` → assert `current_features == []`, `current_listing_purpose is None`, `min_price is None`, `current_sort == "price_desc"`, `page_obj.number == 1`. |

**Test data needed:** Transport category with resolver overrides; features `credit`, `urgent`, `delivery`, etc.; conditions new/used; 5+ ads with varying combinations including some with NULL price.

---

### Scenario 6 — Product/ad detail → initiate a new search → results

| Step | User Action | Intermediate Results | Validation |
|------|------------|---------------------|------------|
| 1 | Open `/<ad_id>/`. | Full page `ads/detail.html`: header with search bar + category dropdown + city selector; ad article with gallery, title, price (original currency), description (localized), feature chips, breadcrumbs, "Contact Seller" Telegram deep-link, "← Back to listings" (`javascript:history.back()`). | **Integration** (`test_detail_context.py`, `test_ad_detail_queries.py`): `Client().get(f"/{ad.id}/")` → 200. Assert `response.context["ad"] == ad`. Assert HTML has `href="https://t.me/{bot_username}?start=contact_{ad.id}"` and `href="javascript:history.back()"`. Assert `AnalyticsEvent.objects.filter(event_type="ad_viewed", ad_id=ad.id).exists()`. Assert `display_features` only shows category-appropriate features. |
| 2 | Type `ноутбук` in header search; press Enter. | Full-page nav to `/search/?q=ноутбук`. Only `q` is submitted (no `category`/`city`/`features`). FTS on Russian vector. Single-word → fuzzy category match may constrain to "Ноутбуки" subtree. New history/popular entry. | **Integration**: `Client().get("/search/?q=ноутбук")` → 200. Assert `query == "ноутбук"`, `current_category is None`. Assert `PopularSearch` record exists; `SearchHistory`/session populated; `AnalyticsEvent` search_performed recorded. |
| 3 | Browser Back. | Returns to the ad detail page (`/<ad_id>/`). Full page re-rendered. | **Playwright e2e only** (native browser Back). Django-level proxy: `Client().get(f"/{ad.id}/")` → 200, `response.context["ad"]` is the original ad. Document as `manual=True`. |

---

## 4. Cross-Cutting Behaviors

### 4.1 Sorting
- **URL encoding:** `?sort=date_desc` (default), `date_asc`, `price_asc`, `price_desc`.
- **Listings pages** (`/`, `/category/…`, `/city/…`): `sort` param honored via explicit branch. Sort dropdown always visible.
- **Search page** (`/search/?q=…`): sort dropdown **hidden** (`{% if not query %}`); `sort=` param **ignored** — FTS rank order always. **Bug/gap:** spec says sort should be available on results; implementation hides it.
- **FTS ordering:** `-rank, -published_at, -id` (relevance, then newest, then stable id).
- **Price sort:** `price_normalized_eur` ASC/DESC with `NULLS LAST`.

**Validation:** `test_listings_sort.py`, `test_catalog_filters.py::TestPriceNullSort`.

### 4.2 Language Selection
- **Priority:** `?lang=X` > `lang_pref` cookie > `Accept-Language` > default `ru` (`LanguagePreMiddleware`).
- **Persistence:** `?lang=` writes `lang_pref` cookie (1-year, SameSite=Lax); session `django_language` for auth.
- **UI:** `components/language_switcher.html` dropdown with `ru/Russian`, `bs/Bosnian`, `en/English`.
- **FTS:** locale selects per-language vector (`search_vector_ru/bs/en` with configs `russian`/`simple`/`english`).

**Validation:** `test_language_locale.py`, `test_language_end_to_end.py`.

### 4.3 City Selection
- **Default:** preferred-city middleware — `User.preferred_city` FK (auth) wins over `preferred_city` cookie (guest, consent-gated) → "Вся страна" if none.
- **Choosing:** header city button → dropdown → click city → POST to `preferred_city` then full-page nav to `/city/<slug>/`.
- **Did-you-mean:** on listings, invalid `?city=` or `/city/<slug>/` → difflib suggestion banner. On search, invalid `?city=` → echo only (no fuzzy match).

**Validation:** `test_preferred_city.py`, `test_preferred_city_readback.py`.

### 4.4 Search History
- **Recording:** After successful FTS with non-empty `q`: `increment_popular_search(query)` + `record_search_history(user_id, query, session)`.
- **Auth:** `SearchHistory` DB rows (deduped by `query_normalized`, capped at 50).
- **Anonymous:** `session['search_history']` (deduped, capped at 50) — stored in Django session table via `sessionid` cookie.
- **Display:** autocomplete `user_history` suggestions (limit 5) + cabinet page `/cabinet/search-history/` (auth only, 100 entries listed).

**Validation:** `test_search_view.py::test_search_anonymous_records_session_history`, `test_autocomplete.py::TestSearchHistoryService`.

### 4.5 Autocomplete Suggestions
- **Endpoint:** `GET /api/search/autocomplete?q=<text>` → 200 JSON `{"query": <q>, "suggestions": [...]}`.
- **Sanitization:** stripped, 2–100 chars, quotes/backslashes removed → empty if invalid.
- **Rate limit:** 30 req/min/IP → 31st = 429.
- **Sources (merged, deduped by `text`, capped at 10):**
  1. `user_history` — DB (auth) or session (anon)
  2. `category` + `city` — entity prefix match, localized
  3. `popular_search` — prefix match, `hit_count >= 10`
- **Click outcomes:** city → POST + nav `/city/<slug>/`; category → nav `/category/<slug>/`; text → populate input + submit → `/search/?q=<text>`.

**Validation:** `test_autocomplete.py`, `test_autocomplete_template.py`.

### 4.6 Save Search (FT-002)
- **URL:** `POST /save-search/` (`search:save-search`).
- **Auth required:** unauth → redirect to login.
- **Creates `SavedSearch`** with `query`, `city_id`, `category_id`, `min_price`, `max_price`, `language=LANGUAGE_CODE`, `is_active=True`.
- **UI:** "Save search" button + modal visible on `/search/` page when `request.user.is_authenticated and cities` (`list.html:23-32`).

**Validation:** `test_saved_search_create.py`.

### 4.7 Analytics Events
- **`SEARCH_PERFORMED`:** recorded after FTS run with non-empty `q` (`search.py:185-188`).
- **`AD_VIEWED`:** recorded on `ad_detail` for the seller (`listings.py:68-72`).

---

## 5. Bug Fixes Required (Problem_01.md)

| Bug | Required Fix | Priority |
|-----|-------------|----------|
| **#1 — Autocomplete shows only history on repeat** | Investigate root cause. Likely: (a) `PopularSearch` `hit_count >= 10` gate returns empty on low-traffic instance, making the dropdown appear history-only; or (b) client-side `htmx:afterRequest` handler fails to re-render all sections on repeat XHR. **Fix:** ensure all 4 sections always render; consider lowering `min_hit_count` or seeding popular queries for dev. | High |
| **#2 — Clear (X) button does nothing** | The search input is `type="search"` with a native browser clear-X. Add an explicit, wired clear control (e.g., a custom `×` button with `onclick="window.location.href='/';"` or `history.back()`) that returns to the pre-search browsing state. | High |
| **Gap — Header search drops category/city** | Wire the header search form to carry `?category=<slug>` when submitting from a `/category/` page, and `?city=<slug>` when submitting from a `/city/` page. Use hidden inputs populated by the current URL context. | Medium |
| **Gap — Sort hidden on FTS results** | Decide: should `/search/?q=…` honor `?sort=` with a relevance-first default? If yes, remove the `{% if not query %}` gate in `filter_form.html` and add a sort branch in `search.py` for FTS results. | Product decision |
| **Gap — `lang=` drops on HTMX transitions** | Append `?lang=` to HTMX `hx-get` URLs, or ensure the form hrefs include the language param. Low severity (cookie re-applies on reload). | Low |

---

## 6. Validation Summary Table

| Scenario | Test Strategy | Key Test Files | Test Data |
|----------|---------------|----------------|-----------|
| 1. Home → query → results | Integration (Django client) + HTMX + template-source | `test_search_view.py`, `test_autocomplete.py`, `test_autocomplete_template.py` | Category "Ноутбуки", 25+ ads with "ноутбук" |
| 2. Home → category → filters → query | Integration + HTMX + template-source | `test_catalog_filters.py`, `test_listings_context.py` | Transport category + lookups, ads with purpose/features/price |
| 3. Home → query → filters | Integration + HTMX + template-source | `test_catalog_filters.py::TestFilterAndSearchCombine` | Ads with "авто", varying prices/purposes/features |
| 4. Category → query | Integration + template-source + service | `test_search_view.py::TestSearchViewDescendantCategories`, `test_autocomplete.py::TestEntitySuggestionsService` | Electronics category, ads with "macbook" in/out of category |
| 5. Category → filters | Integration + HTMX + template-source | `test_listings_sort.py`, `test_catalog_filters.py` | Transport category + resolver lookups, 5+ ads w/ NULL price |
| 6. Detail → search | Integration + Playwright (Back button) | `test_detail_context.py`, `test_ad_detail_queries.py`, `test_search_view.py` | Published ad with "ноутбук" in title, category with "Ноутбки" child |

**Test commands:**
- Fast gate: `make test` (skips `seed`)
- Run specific: `docker compose --project-name mko-bazuna-test -f docker-compose.yml -f docker-compose.test.yml run --rm -e PYTEST_OPTS="<opts>" test`
- Fresh schema after migrations: `make test-recreate`
- Linting: `uv run ruff check <path>` · `uv run basedpyright <path>`

---

## 7. Open Product Decisions

1. **Sort on FTS results** — Should `/search/?q=…` honor `?sort=` with relevance-first default, or stay rank-only? (Templates currently hide sort on search results.)
2. **Clear-X behavior** — Return to `/` (homepage) or `history.back()` (last browsing state)? Recommendation: `history.back()` to match OLX/Avito "return to pre-search state."
3. **Header-search context preservation** — Wire header form to carry active category + city when navigating from `/category/` or `/city/` pages? (Currently dropped.)
4. **Autocomplete popular gate** — Keep `min_hit_count=10` for MVP, or seed popular queries / lower threshold so the dropdown never reads as "only history"?

---

*This completes the search user journeys specification: six scenarios adapted to the Mko Bazuna architecture, each with concrete User Actions, Intermediate Results, and Validation criteria. Ready for implementation and testing.*
