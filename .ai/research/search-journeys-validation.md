# Search Journeys — Validation Criteria

> **Purpose:** Add a **Validation** column to each of the six search journey scenarios from `search-journeys-our-architecture.md`, specifying exactly how an agent or automated test can verify each step. Every assertion below is grounded in the live source code and the existing test files.
>
> **Method:** Validation criteria reference concrete template fragments, context variables, URL patterns, and ORM state. Source-of-truth citations use `file:line` from the architecture doc and the test files I have read.
>
> **Test environment:** All DB-backed validations run in Docker via `make test` (fast gate, skips `seed`) or `make test-all` (full suite). Template-source assertions (no DB) run anywhere.

---

## Notation

- **UI** = expected HTML/template fragment in the rendered response body.
- **URL** = exact browser URL (or expected `response.url` / `response.context` for non-HTMX; `hx-push-url` value for HTMX).
- **Backend state** = effective filter/sort/page state the view applies.
- **Results** = what ads/empty-state should be visible.
- **Back/Fwd** = browser history behavior.
- **Side effects** = search history, preferred city, language, analytics.

Test conventions:
- `from conftest import create_test_ad` (root `conftest.py` at `src/backend/conftest.py`; `pythonpath = ["src", "src/backend"]`).
- `pytestmark = [pytest.mark.django_db, pytest.mark.integration]` for DB-backed tests.
- `from django.test import Client`; `headers={"HX-Request": "true"}` for HTMX partial assertions.
- `response.context["page_obj"]` for ads; `response.content.decode()` for HTML; `response.json()` for autocomplete.
- Fast gate: `make test` (sets `PYTEST_SKIP_MARKERS=seed`).

---

## Scenario 1 — Homepage → enter search query → search results

*(US-B2, US-B9, US-B10)*

| Step | User Action | Intermediate UI State | URL / State Change | Resulting Filter/Sort/Page | **Validation** |
|---|---|---|---|---|---|
| 1 | Land on `/` (no auth). | Full page: `components/header_catalog.html` (city button label = `preferred_city_display`; "All Categories" dropdown; empty search bar) + `ads/list.html` → `#ad-list` → `ads/partials/ad_list.html` (`filter_form.html`: purpose/condition/price/features/sort controls; no `q`/`category`/`city` hidden inputs). 24-card grid, newest-first. | `GET /` | `query=None`; list view. `current_sort=date_desc` (default). No city filter → preferred city applies (or none). Ads = all `PUBLISHED`, ordered `-published_at`, page 1 of 24. | **HTTP 200** on `Client().get("/")`. Assert `response.context["query"] == ""` (empty/None), `response.context["current_sort"] == "date_desc"`, `response.context["has_results"]` reflects seeded ads. Assert HTML contains `id="search-input"` with empty `value`, `<form method="get" action` containing `search:search`, `name="q"`, **no** hidden `name="category"` or `name="city"` inputs in the header form. Assert `filter_form.html` renders the sort `<select name="sort">` (visible because `{% if not query %}`). Assert `<div id="autocomplete-dropdown"` is empty/hidden initially. |
| 2 | Focus the search bar. | Autocomplete dropdown opens (`ul#autocomplete-dropdown`): "Show all results" link + sections Cities/Categories/Popular/History. | No URL change (XHR to `search:autocomplete`). | Read-only suggestion query. | **Client-side / unit:** Assert via `test_autocomplete_template.py` pattern that `input#search-input` has `hx-get`, `hx-trigger="input delay:300ms"`, `hx-target="#autocomplete-dropdown"`, `hx-swap="none"`. **Integration (`test_autocomplete.py`):** `Client().get("/api/search/autocomplete", {"q": ""})` returns 200 with `{"suggestions": [], "query": ""}` (sanitize rejects <2 chars). Assert empty query → empty list. |
| 3 | Type query e.g. `ноутбук`. | Autocomplete refines per prefix (`input` 300ms → `GET /api/search/autocomplete?q=ноутбук`). "Show all results" link points to `/search/?q=ноутбук`. Entity matches may include category "Ноутбуки". | No URL change; XHR only. | No filter/sort state change. | **Integration:** `Client().get("/api/search/autocomplete", {"q": "ну"})` — assert 200, `data["query"] == "ну"`, JSON contains `suggestions` array. Assert each suggestion has `text`, `source`, `type` keys. Assert city suggestions come from `get_entity_suggestions` (prefix match `istartswith`). Popular suggestions require `hit_count >= 10`. Assert rate limit: 31st request → 429 (`test_autocomplete.py::TestAutocompleteEndpoint::test_autocomplete_rate_limit`). |
| 4 | Press Enter / click "Show all results". | Full-page form submit (`data-search-form`, `action=search:search`). On load header re-renders with `query="ноутбук"` pre-filled. `#ad-list` shows `ad_list.html` **without** `filter_form.html`'s sort block (`{% if not query %}` hides it); purpose/condition/price/features still present. | `GET /search/?q=ноутбук` (only `q`; **category & city dropped** — header form has no hidden category/city, `header_catalog.html:114-132`). | FTS on `search_vector_<locale>` (Russian vector, `LANGUAGE_CODE` defaults `ru`, `search.py:162-164`). Single-word `ноутбук` triggers `_fuzzy_category_match` (`search.py:167-174`) → may constrain to "Ноутбуки" subtree. Ordering: `-rank, -published_at, -id` (`search.py:180-182`). `page=1` implicit. `SEARCH_PERFORMED` event recorded (`search.py:185-188`); `ноутбук` written to history — DB for auth, session for anon (`search.py:192-197`). | **Integration:** `Client().get("/search/?q=ноутбук")` → 200. Assert `response.context["query"] == "ноутбук"`, `response.context["breadcrumb_category"]` is the fuzzy-matched category (if `ноутбук` matches a category name) or `None`. Assert HTML does **not** contain `<select name="sort"` (sort dropdown hidden when `query` is truthy, `filter_form.html:103`). Assert `AnalyticsEvent.objects.filter(event_type="search_performed").exists()` (records `SEARCH_PERFORMED`). Assert `PopularSearch.objects.filter(query_normalized="ноутбук", hit_count=1).exists()`. For auth: `SearchHistory.objects.filter(user=..., query_normalized="ноутбук").exists()` (`test_search_view.py::TestSearchViewRecordsAutocompleteData`). |
| 5 | Scroll / click page 2. | HTMX `hx-get...?page=2&q=ноутбук` → target `#ad-list` → innerHTML swap + `hx-push-url` updates browser URL. Header stays intact. | `GET /search/?q=ноутбук&page=2` (pushed to history). | Page advances to ads 25–48; rank ordering preserved; `q` preserved. | **Integration + HTMX:** `Client().get("/search/?q=ноутбук&page=2", headers={"HX-Request": "true"})` → 200, content is `#ad-list` fragment only. Assert `response.context["page_obj"].number == 2`. **Full-page:** `Client().get("/search/?q=ноутбук&page=2")` → assert HTML has `page_obj` page 2. Assert pagination links in `ad_list.html:142-169` carry `q=ноутбук` + `page=2` + `hx-push-url="true"`. Assert page 1 link omits `page=1` (implied). |

**Sorting note:** Not selectable on the FTS results page — dropdown hidden (`filter_form.html:103`); `sort=` param ignored by `search()` when `q` is present (`search.py:176-182`).

### Test strategy (Scenario 1)
- **Step 1–2, 4–5:** Django test client integration tests (`django.test.Client`) against the real PostgreSQL test DB. Assert on `response.context` (context vars) and `response.content.decode()` (HTML fragments). Reference: `test_listings_context.py`, `test_search_view.py`.
- **Step 3:** Integration test against `/api/search/autocomplete` + `test_autocomplete.py` patterns. Also a **template-source unit test** (`test_autocomplete_template.py`) verifying `hx-get`, `hx-trigger`, `hx-target`, `hx-swap`, `id="search-input"`, `id="autocomplete-dropdown"` attributes — no DB needed.
- **HTMX variants:** Pass `headers={"HX-Request": "true"}` and assert the response is the `ad_list.html` fragment (not the full `list.html` shell) — see `test_catalog_filters.py::TestFilterUrlReset`.

### Test data setup (Scenario 1)
- **Categories:** Need a category named "Ноутбуки" (slug `noutbuki` or similar) under "Электроника" to exercise single-word fuzzy category match → subtree constraint. Use `Category.objects.create(name="Ноутбуки", slug="noutbuki", parent=<electronics>)`.
- **Cities:** `City.objects.create(name="Тестград", slug="test-grad", country_code="ME")` (provided by `city` fixture).
- **Ads:** PUBLISHED ads with title/description containing "ноутбук" (for FTS match), some in the "Ноутбуки" category subtree, some outside it. Use `create_test_ad(seller, category, city, title="Продам ноутбук Dell", description="Отличный ноутбук для работы", status=AdStatus.PUBLISHED)`.
- **25+ ads** across 2 pages to test pagination (24 per page).

### Edge cases (Scenario 1)
| Edge case | How to verify |
|---|---|
| Empty query (`q=""`) | `Client().get("/search/")` → 200, falls to no-query branch (`search.py:198-208`), `sort` param honored. Assert `response.context["query"] == ""` and no `AnalyticsEvent` of type `search_performed` created (only recorded when `query` is truthy, `search.py:184-197`). |
| Single-word query matching a category name | Query `Транспорт` → `_fuzzy_category_match` finds the category by exact name match (`search.py:288-294`) → subtree filter applied. Assert `response.context["breadcrumb_category"]` is the matched Category. Reference: `test_search_view.py::TestSearchViewDescendantCategories`. |
| Multi-word query | Query `красный велосипед` → `_is_single_word` returns False (`search.py:256-270`) → no fuzzy category expansion; FTS only on `-rank, -published_at, -id`. Assert ads from any category can match. |
| No results | Query `zzzzznotfound` → 200, `has_results=False`, HTML renders `{% blocktrans %}No results found for "{{ query }}"{% endblocktrans %}` (`ad_list.html:175-179`). |
| Query with special chars | Query `'; DROP TABLE--` → sanitized by `sanitize_autocomplete_query` (autocomplete); for `/search/` the `SearchQuery` websearch config tokenizes safely. Assert no 500. |
| Invalid `page` param | `?page=abc` → `Paginator.get_page` falls back to page 1 (`test_search_view.py::test_invalid_page_returns_first_page`). `?page=99` → last page. |

---

## Scenario 2 — Homepage → select category → filters → enter search query → results

*(US-B2, US-B3, US-B6, US-B10)*

| Step | User Action | Intermediate UI State | URL / State Change | Resulting Filter/Sort/Page | **Validation** |
|---|---|---|---|---|---|
| 1 | On `/`. Open "All Categories" dropdown (desktop). | `components/header_catalog.html` categories panel; root categories from `root_categories` (context proc `context_processors.py:72-73`). Submenus lazy-loaded via `fetch('/categories/<slug>/submenu/')` (`header_catalog.html:318-336`). | No URL change (client panel). | — | **Unit/template:** Assert `header_catalog.html` contains `data-categories-toggle`, `data-categories-panel`, `data-category-link`, and root categories are rendered via `{% for cat in root_categories %}`. Assert submenu fetch URL `{% url 'categories:category_submenu' %}` pattern. Reference: `test_autocomplete_template.py`. **Integration:** `GET /` → HTML contains category slugs as `data-category-slug="..."` and `<a href="/category/transport/"`. |
| 2 | Click category `transport`. | Full-page navigation. Header "All Categories" button now = "Транспорт". Breadcrumb `Home › Транспорт` (`breadcrumb.html`). `#ad-list` = `ad_list.html` for transport subtree. Purpose/condition/features constrained via resolver. | `GET /category/transport/` (named `ads:listings_category`) | `query=None`; `category=transport` (path). `listing_purpose`/`features`/`condition` resolved via `CategoryLookupResolver` (`listings.py:367-386`). `sort=date_desc` default. Ads = `PUBLISHED` where `category_id IN (descendants of transport)`. | **Integration:** `Client().get("/category/transport/")` → 200. Assert `response.context["current_category"] == "transport"`, `response.context["breadcrumb_category"]` is the Category with slug `transport`. Assert `filter_form.html` purpose `<select>` options match `resolved_purposes` (filtered by ancestor-walk). Assert ads in `page_obj` all have `ad.category` in transport subtree. Reference: `test_catalog_filters.py` resolver pattern, `test_listings_context.py::test_path_slugs_populate_current_category_and_city`. |
| 3 | In filter form, pick `listing_purpose=rent`, `features=delivery`, `min_price=1000`. Click "Apply filters". | `filter_form.html` re-renders (server-validated selects/checkboxes sticky). Active chips for Purpose + features appear in `ad_list.html:35-76`. Grid updates. | HTMX `GET /category/transport/?listing_purpose=rent&features=delivery&min_price=1000&page=1` → `hx-push-url`, swap `#ad-list`. | `current_category=transport`; `listing_purpose=rent`; `feature_slugs=[delivery]`; `min_price=1000`; `sort=date_desc`; page 1. Results = transport subtree ∩ purpose ∩ features ∩ `price_normalized_eur >= 1000`. | **Integration + HTMX:** `Client().get("/category/transport/?listing_purpose=rent&features=delivery&min_price=1000", headers={"HX-Request": "true"})` → 200, fragment. Assert `response.context["current_listing_purpose"] == "rent"`, `response.context["current_features"] == ["delivery"]`, `response.context["min_price"] == "1000"`. Assert HTML contains `bg-blue-100` chip with purpose text, `bg-green-100` chip with feature text, `×` removal links with `hx-push-url="true"`. Assert `page_obj` ads all have `listing_purpose.slug == "rent"`, `features` includes `delivery`, `price_normalized_eur >= 1000`. Reference: `test_catalog_filters.py::TestListingPurposeFilter::test_listings_filters_by_purpose`, `TestFeaturesFilter::test_all_selected_features_required`. |
| 4 | Type `iphone` in the header search bar; press Enter. | Header search is a full-page `<form>` submit → server renders `/search/`. | `GET /search/?q=iphone` (**category `transport` and filters are dropped** — `header_catalog.html:114-132` has no hidden category/city; `filter_form.html` hidden inputs are scoped to `request.path`, not the header form). | `search()` runs FTS. `iphone` is not a category fuzzy match → no subtree constraint. Results = FTS rank order, page 1. | **Integration:** Assert the header `<form>` in `header_catalog.html:114-132` contains only `<input name="q">` and `{% csrf_token %}` — no hidden `category`/`city`/`listing_purpose`/`features` inputs. `Client().get("/search/?q=iphone")` → assert `response.context["current_category"] is None` (header submit drops category). Assert `response.context["query"] == "iphone"`, `current_listing_purpose` is None, `current_features` is empty. Reference: architecture doc §3.1. |
| 5 | Refine: open on-page filter form, pick `listing_purpose=rent`, add feature `credit`. Click "Apply filters". | Filter form (targeting `/search/` because `request.path=/search/`) has hidden `q=iphone` (`filter_form.html:11`). No `category` hidden input (dropped in step 4). | HTMX `GET /search/?q=iphone&listing_purpose=rent&features=credit&page=1` → pushUrl, swap `#ad-list`. | `q=iphone`; `listing_purpose=rent`; `features=[credit]`; `current_category=None`. FTS results constrained by new filters. "Save search" button visible (auth + `cities` in context, `list.html:23`). | **Integration + HTMX:** `Client().get("/search/?q=iphone&listing_purpose=rent&features=credit", headers={"HX-Request": "true"})` → 200, fragment. Assert `response.context["query"] == "iphone"`, `current_category is None`, `current_listing_purpose == "rent"`, `current_features == ["credit"]`. Assert `filter_form.html` hidden `<input name="q" value="iphone">` is present (`filter_form.html:11`). Assert ads in page match FTS for "iphone" AND have `listing_purpose.slug == "rent"` AND `credit` in features. Assert `cities` is in context (from `search.py:242`) for authenticated users. |

**Observation vs. research:** OLX preserves category+filter context when refining query; our header form carries only `q`. To keep category scope, the user must re-select via autocomplete → `/category/<slug>/`, or rely on single-word fuzzy detection.

### Test strategy (Scenario 2)
- **Steps 1–3:** Django test client against `/category/<slug>/` with HTMX headers. Assert on context vars (`current_category`, `current_listing_purpose`, `current_features`, `current_city`) and rendered HTML (chips with `bg-blue-100`/`bg-green-100`, removal `×` links with `hx-push-url="true"`). Reference: `test_catalog_filters.py`, `test_listings_context.py`.
- **Step 4:** Assert template source of `header_catalog.html:114-132` has only `name="q"` (no category/city hidden inputs) — `test_autocomplete_template.py` pattern.
- **Step 5:** Integration + HTMX against `/search/?q=iphone&...` asserting context and rendered chip/form state.

### Test data setup (Scenario 2)
- Categories: `transport` root with child categories; `electronics` separate root. Use the `category` fixture (creates "Транспорт", slug `transport`) plus a child category.
- Cities: `city` fixture.
- Feature lookups: create `LookupGroup(code="listing_feature")` + `LookupItem` slugs `delivery`, `credit` (reference: `test_catalog_filters.py::feature_lookup`).
- Purpose lookups: `LookupGroup(code="listing_purpose")` + `LookupItem` slugs `sell`, `rent` (reference: `test_catalog_filters.py::purpose_lookup`).
- Ads: PUBLISHED ads in transport subtree with `listing_purpose=sell`/`rent`, some with `delivery`/`credit` features, varying `price_normalized_eur`. Plus ads titled "iphone" in transport and outside.

### Edge cases (Scenario 2)
| Edge case | How to verify |
|---|---|
| Category that doesn't exist in path | `GET /category/nonexistent/` → 404 (`listings.py` — `Category.DoesNotExist` raises; actually it sets `suggested_category`, no 404). **Verify:** `suggested_category` is set; "Did you mean:" banner renders (`ad_list.html:18-24`); all ads shown unfiltered. |
| Filter form on `/search/` has no category control | Assert `filter_form.html:28` — `#current_category` is **not** emitted as a hidden input (form has `q`, `city`, but not `category`). Confirm the only way to scope category on `/search/` is the `?category=` query param (which header submit never sets). |
| Repeated `features=` params | `?features=credit&features=urgent` → `request.GET.getlist("features")` returns both (`search.py:112`, `listings.py:358`); AND semantics. Assert both features required in results. Reference: `test_catalog_filters.py::TestFeaturesFilter::test_all_selected_features_required`. |
| Invalid `min_price` (non-integer) | `?min_price=abc` → `int("abc")` raises `ValueError` → caught, filter ignored (`listings.py:327-332`, `search.py:86-90`). Assert 200, all prices shown. |

---

## Scenario 3 — Homepage → enter query → apply filters → results

*(US-B2, US-B3, US-B10)*

| Step | User Action | Intermediate UI State | URL / State Change | Resulting Filter/Sort/Page | **Validation** |
|---|---|---|---|---|---|
| 1 | On `/`. Type `авто` in the header search; press Enter. | Full-page nav to `/search/`. Header input pre-filled with `авто` (`header_catalog.html:118`: `value="{{ query|default:'' }}"`). `#ad-list` renders `ad_list.html` with filter form (no sort dropdown, `{% if not query %}`) + grid. | `GET /search/?q=авто` | FTS on Russian vector (`search_vector_ru`, config `russian`, `search.py:162-164`). Rank-ordered `-rank, -published_at, -id`. `page=1` implicit. History + popular hit incremented. | **Integration:** `Client().get("/search/?q=авто")` → 200. Assert `response.context["query"] == "авто"`. Assert HTML `value="авто"` on `id="search-input"`. Assert HTML has **no** `<select name="sort"` (hidden when `query` truthy). Assert `PopularSearch.objects.filter(query_normalized="авто").exists()`. Assert for anon: `client.session["search_history"]` contains an entry with `query_normalized == "авто"` (`search.py:192-197`, `record_search_history`). |
| 2 | Set `min_price=500`, `max_price=5000`, `listing_purpose=sell`, feature `negotiable`. Click "Apply filters". | Filter form's hidden `q=авто` input preserves query (`filter_form.html:11`). Selects/inputs sticky. Chips update. Grid re-ranks by FTS within narrowed set. | HTMX `GET /search/?q=авто&min_price=500&max_price=5000&listing_purpose=sell&features=negotiable&page=1` → pushUrl, swap `#ad-list`. | `q=авто`; `min_price=500`/`max_price=5000` (on `price_normalized_eur`); `listing_purpose=sell`; `features=[negotiable]`; rank order preserved; page 1. | **Integration + HTMX:** `Client().get("/search/?q=авто&min_price=500&max_price=5000&listing_purpose=sell&features=negotiable", headers={"HX-Request": "true"})` → 200, fragment. Assert all context vars match. Assert HTML chips: purpose chip (`bg-blue-100`, text "Продажа"/"sell"), feature chip (`bg-green-100`, text for "negotiable"). Assert `page_obj` ads: `price_normalized_eur >= 500`, `price_normalized_eur <= 5000`, `listing_purpose__slug == "sell"`, `features__slug contains "negotiable"`. |
| 3 | Remove the `negotiable` chip (×). | Chip disappears; grid re-renders. | HTMX `GET /search/?q=авто&min_price=500&max_price=5000&listing_purpose=sell&page=1` (chip link omits that feature but keeps `q`, `sort`, price, purpose) → pushUrl. | `features` now empty; all other filters retained. | **Template source + integration:** Assert the feature chip `×` link in `ad_list.html:64-65` omits `features=negotiable` but preserves `q={{ query }}`, `min_price`, `max_price`, `listing_purpose`, `sort`. **Integration:** Request the chip-removal URL; assert `response.context["current_features"] == []`, `current_listing_purpose == "sell"`, `query == "авто"`. Assert the removed feature's ads may reappear. |
| 4 | Click "Clear all filters" (top-right of chip bar). | Chips vanish; form resets to any/empty. Full grid re-renders (still FTS-ranked). | HTMX `GET /search/?q=авто&page=1` (drops city/category/condition/features/price/purpose; **keeps `q`** per `ad_list.html:71-74`) → pushUrl. | Back to plain `/search/?q=авто` (page 1). `q` retained; all other filters dropped. | **Template source + integration:** Assert `ad_list.html:71-74` "Clear all filters" `href` includes `?page=1&q={{ query }}` (if query) + `&sort={{ current_sort }}` but does **not** include `min_price`, `max_price`, `listing_purpose`, `features`, `condition`, `city`, `category`. **Integration:** Request the clear-URL; assert `response.context["current_features"] == []`, `current_listing_purpose is None`, `min_price is None`, `max_price is None`, `query == "авто"`, `page_obj.number == 1`. |

### Test strategy (Scenario 3)
- **Steps 1–2:** Django test client with `HX-Request` header for HTMX fragment assertions; also full-page requests to verify `header_catalog.html` re-render. Assert on context vars + rendered chips + `page_obj` filtering. Reference: `test_catalog_filters.py::TestFilterAndSearchCombine::test_q_purpose_and_feature_combine`, `TestRelevanceTiebreaker::test_rank_tie_breaks_by_published_at`.
- **Step 3:** Template-source assertion (`ad_list.html` chip `×` link URL construction) + integration test on the chip-removal URL.
- **Step 4:** Template-source assertion on the "Clear all filters" href composition + integration test on the clear URL.

### Test data setup (Scenario 3)
- Categories/lookup fixtures as in Scenario 2.
- Ads with title/description containing "авто", varying prices (some <500, some 500–5000, some >5000), purpose `sell`/`rent`, with/without `negotiable` feature. Use `create_test_ad` with `price=Decimal(...)`, `price_normalized_eur=...` (note: `create_test_ad` sets `price_normalized_eur == price` by default).
- At least 2 pages of ads (25+) to verify pagination preserves `q`.

### Edge cases (Scenario 3)
| Edge case | How to verify |
|---|---|
| Clear all filters on `/search/` without `q` | `GET /search/?listing_purpose=sell` → click clear → `GET /search/?page=1&sort=date_desc`. Assert `query` stays empty (no `q`), all other params dropped. |
| Chip removal preserves `page=1` | Assert chip `×` link includes `page=1` (reset), not the current page number. |
| Search with `q` + invalid price | `?q=авто&min_price=abc&max_price=xyz` → both invalid → ignored; valid ads returned. Assert `response.context["min_price"] == "abc"` (echoed in input value) but `page_obj` includes all prices. |
| Repeat query after clear | After clearing filters, re-submitting the same `q=авто` via the filter form → same FTS results, `page=1`. |
| Anonymous session history persists | `Client().get("/search/?q=авто")` → check `client.session["search_history"]` is populated; subsequent autocomplete for "ав" returns "авто" in `user_history` suggestions. |

---

## Scenario 4 — Category page → enter search query → results

*(US-B2, US-B6, US-B10)*

| Step | User Action | Intermediate UI State | URL / State Change | Resulting Filter/Sort/Page | **Validation** |
|---|---|---|---|---|---|
| 1 | Navigate to `/category/electronics/` (via header dropdown). | Breadcrumb `Home › Товары > Электроника` (`breadcrumb.html` with ancestor chain). Header "All Categories" = "Электроника". Filter form shows electronics-resolved purposes (`sell`) + features + conditions (`new/used`). | `GET /category/electronics/` | `current_category=electronics`; subtree filter; `sort=date_desc`; page 1. | **Integration:** `Client().get("/category/electronics/")` → 200. Assert `response.context["current_category"] == "electronics"`, `response.context["breadcrumb_category"].slug == "electronics"`. Assert HTML breadcrumb contains category display name. Assert `filter_form.html` resolved purpose/feature/condition sets match `CategoryLookupResolver.get_resolved_purposes(breadcrumb_category)`. |
| 2 | Type `macbook` in the header search; press Enter. | Full-page submit of header form (carries `q` only). | `GET /search/?q=macbook` (**category `electronics` NOT carried** — header form has no category hidden input, `header_catalog.html:114-132`). | FTS on Russian vector. `macbook` is single-word; `_fuzzy_category_match` checks slug + exact `get_name` + difflib(0.8) — no category named "macbook" → **no subtree auto-constraint**. Results = site-wide FTS, rank-ordered. | **Integration:** `Client().get("/search/?q=macbook")` → 200. Assert `response.context["current_category"] is None` (no `?category=` param). Assert `response.context["query"] == "macbook"`. Assert FTS ordering `-rank, -published_at, -id` (no `sort` applied). Assert HTML does not show `sort` dropdown (`{% if not query %}` gated). **Template source:** assert header `<form>` has no hidden `category` input. |
| 3 | Use autocomplete category suggestion instead. | Type `электроника` → dropdown shows category suggestion "Электроника" with `category_path`. Click it. | Click → `header_catalog.html:275-277` navigates `window.location.href = '/category/electronics/'`. | Lands on `/category/electronics/` (listings view, no `q`). | **Unit/template:** `test_autocomplete.py::TestEntitySuggestionsService::test_category_suggestion_has_category_path` asserts category suggestions include `category_path`, `slug`, `type="category"`. **Template source:** `header_catalog.html:275-277` — assert the click handler for `type === 'category'` does `window.location.href = '/category/' + slug + '/'`. |
| 3b | No UI to add `category=` to `/search/?q=…`. | On-page filter form (`filter_form.html`) exposes purpose/condition/price/features/sort — **not** category. | — | **Gap:** once on `/search/?q=`, category scope can only be re-established by leaving the page (autocomplete category link → `/category/<slug>/`) or single-word fuzzy detection. | **Template source assertion:** Read `filter_form.html` — assert **no** `<select name="category">` or hidden `<input name="category">` element exists in the form markup. Only `q` (hidden, if query), `city` (hidden, if current_city), and the purpose/condition/price/features/sort controls are present. |

**Cross-cutting:** Switching language (`?lang=bs`) on `/search/?q=macbook` re-runs FTS against `search_vector_bs` (`search.py:162-164`); city defaults to preferred-city middleware; no "Save search" button on category listing page (only `/search/` exposes it, `list.html:23`).

### Test strategy (Scenario 4)
- **Step 1:** Integration test `Client().get("/category/electronics/")`; assert context + rendered breadcrumb + filter form option sets.
- **Step 2:** Integration test `Client().get("/search/?q=macbook")`; assert `current_category is None`, FTS ordering, sort dropdown hidden. **Template source:** assert header form has no `name="category"` hidden input.
- **Step 3:** Template-source + service-level test (`test_autocomplete.py::TestEntitySuggestionsService`) asserting category suggestion structure (`slug`, `category_path`, `type`).
- **Step 3b:** Template-source assertion reading `filter_form.html` to confirm no category control.

### Test data setup (Scenario 4)
- Category hierarchy: root "Товары" → child "Электроника" (slug `electronics`). Ads in electronics subtree titled with "macbook", ads outside electronics also titled "macbook".
- Cities: `city` fixture.
- Ad titled "Ноутбук Macbook" in electronics; ad titled "Macbook Pro" in a non-electronics category (e.g., "Компьютеры") to verify it's NOT filtered out (since no category is carried).
- At least one ad in "Электроника" whose title contains "macbook" to verify FTS rank ordering on the search page.

### Edge cases (Scenario 4)
| Edge case | How to verify |
|---|---|
| Single-word query "электроника" on `/search/` | `_fuzzy_category_match` finds category by exact name → subtree constraint applied. Assert `response.context["breadcrumb_category"].slug == "electronics"`. |
| Single-word query that's a category **slug** | Query `electronics` → `_fuzzy_category_match` first checks `Category.slug__iexact` → matches. Assert subtree applied. Reference: `test_search_view.py::TestSearchViewDescendantCategories`. |
| Multi-word query on `/search/` | `?q=macbook pro` → `_is_single_word` returns False → no fuzzy category match, site-wide FTS only. Assert `breadcrumb_category is None`. |
| Category page with invalid slug in path | `GET /category/elecronics/` (typo) → `Category.DoesNotExist` → `suggested_category` set → "Did you mean:" banner (`listings.py:279`, `ad_list.html:18-24`). Assert suggestion points to `/category/electronics/`. |
| Search results with no matches in electronics subtree | All ads with "macbook" in non-electronics categories → results still show them (site-wide, since header drops category). Assert non-empty results if any ad matches FTS globally. |

---

## Scenario 5 — Category page → apply filters → results

*(US-B3, US-B6)*

| Step | User Action | Intermediate UI State | URL / State Change | Resulting Filter/Sort/Page | **Validation** |
|---|---|---|---|---|---|
| 1 | On `/category/transport/`. | Filter form options constrained to transport: purposes `sell/rent`, features `{delivery, pickup, negotiable, credit, exchange, urgent, warranty}`, conditions `{new, used}`. | `GET /category/transport/` | `current_category=transport`; purpose/feature/condition sets resolver-derived; `sort=date_desc`; page 1. | **Integration:** `Client().get("/category/transport/")` → 200. Assert `response.context["current_category"] == "transport"`. Assert `resolved_purposes` excludes `give-away` etc. (resolver applies ancestor-walk — `categories.yaml`/`categories.yaml:147-152` for transport). Assert HTML filter form `<select>` options match resolved sets only. |
| 2 | Pick `listing_purpose=rent`, features `credit` + `urgent`, `min_price=200`, `sort=price_desc`. Click "Apply filters". | Form re-renders with sticky selections. Chips for Purpose + 2 features. Grid re-sortable by price. | HTMX `GET /category/transport/?listing_purpose=rent&features=credit&features=urgent&min_price=200&sort=price_desc&page=1` → pushUrl, swap `#ad-list`. | `current_category=transport`; `listing_purpose=rent`; `feature_slugs=[credit,urgent]`; `min_price=200`; `current_sort=price_desc`; page 1. DB: `features__slug IN (credit,urgent)` AND + `.distinct()` (`listings.py:358-363`). Ordering: `price_normalized_eur DESC, NULLS LAST` (`listings.py:399`). | **Integration + HTMX:** `Client().get("/category/transport/?listing_purpose=rent&features=credit&features=urgent&min_price=200&sort=price_desc", headers={"HX-Request": "true"})` → 200, fragment. Assert `response.context["current_listing_purpose"] == "rent"`, `current_features == ["credit", "urgent"]`, `current_sort == "price_desc"`, `min_price == "200"`. Assert `page_obj` ads ordered by `price_normalized_eur DESC`. Assert all ads have `listing_purpose.slug == "rent"` AND both `credit` and `urgent` features AND `price_normalized_eur >= 200`. Assert `page_obj[0].price_normalized_eur >= page_obj[1].price_normalized_eur` (descending). |
| 3 | Click feature chip × for `urgent`. | `urgent` chip removed; `credit` retained; grid re-renders. | HTMX `GET /category/transport/?features=credit&...page=1` (chip link preserves `q`(none), `sort`, purpose, price, min/max, but omits `urgent`; **does not** re-emit `category` because on listings path it's in the URL path, not a param) → pushUrl. | `features=[credit]`; `listing_purpose=rent`, `min_price=200`, `sort=price_desc` retained. Path still `/category/transport/`. | **Template source + integration:** Assert `ad_list.html:64-65` feature chip `×` link includes `features=credit` but omits `features=urgent`, while preserving `listing_purpose`, `min_price`, `max_price`, `sort`. **Integration:** Request the chip-removal URL; assert `response.context["current_features"] == ["credit"]` (urgent dropped), `current_listing_purpose == "rent"`, `current_sort == "price_desc"`. |
| 3b | "Clear all filters" chip. | Resets to base category page. | HTMX `GET /category/transport/?page=1&sort=price_desc` → pushUrl. | Page 1, no purpose/condition/features/price; sort **retained** (clear-link re-emits only `page=1`, `q`(none), `sort`). | **Template source:** Assert `ad_list.html:71-74` "Clear all filters" `href` = `?page=1{% if query %}&q=...{% endif %}{% if current_sort %}&sort=...{% endif %}` — no `listing_purpose`, `features`, `condition`, `min_price`, `max_price`, `city`, `category`. **Integration:** `Client().get("/category/transport/?page=1&sort=price_desc", headers={"HX-Request": "true"})` → assert `current_features == []`, `current_listing_purpose is None`, `min_price is None`, `max_price is None`, `current_sort == "price_desc"`, `page_obj.number == 1`. |

### Test strategy (Scenario 5)
- **All steps:** Django test client with `HX-Request` header for HTMX fragment assertions; full-page requests for context verification. Assert on context vars (`current_sort`, `current_features`, etc.), `page_obj` ordering by `price_normalized_eur`, and rendered HTML chips. Reference: `test_listings_sort.py`, `test_catalog_filters.py::TestPriceNullSort`, `TestFilterUrlReset`.

### Test data setup (Scenario 5)
- Category hierarchy: root "Транспорт" (slug `transport`) with `categories.yaml` override for transport purposes/features/conditions (`categories.yaml:147-152`).
- Lookup fixtures: purpose `sell`/`rent`, features `credit`/`urgent`/`delivery`/`pickup`/etc., condition `new`/`used` — matching the transport resolver output.
- Ads: 5+ PUBLISHED ads in transport subtree with varying `listing_purpose` (sell/rent), varying feature sets (credit, urgent, both, neither), varying `price_normalized_eur` (including some with `None` price to test NULLS LAST).
- City: `city` fixture.

### Edge cases (Scenario 5)
| Edge case | How to verify |
|---|---|
| NULL price with `price_desc` sort | Ads with `price_normalized_eur IS NULL` appear last. Assert `page_obj` ordering: non-null prices first (descending), nulls at the end. Reference: `test_catalog_filters.py::TestPriceNullSort::test_price_desc_places_nulls_last`. |
| Invalid `sort` param | `?sort=invalid` → `listings.py:390-402` falls through to `else` branch (default `date_desc`). Assert `response.context["current_sort"] == "invalid"` but ordering is `-published_at`. |
| Chip removal preserves path-based category | From `/category/transport/?features=credit&features=urgent&sort=price_desc`, remove `urgent` chip → URL stays `/category/transport/?features=credit&sort=price_desc` (path unchanged, only query string). Assert path component is `/category/transport/`. |
| No results after filter | All ads in transport are `sell` → filter `listing_purpose=rent` → empty. Assert 200, `has_results=False`, HTML renders "No ads available" (`ad_list.html:180-184`). |
| Clear all resets page to 1 | With `?page=3&listing_purpose=rent&...`, click clear → URL has `page=1` (not `page=3`). Assert `page_obj.number == 1`. |

---

## Scenario 6 — Product/ad detail page → initiate a new search → results

*(US-B2, US-B4, US-B10)*

| Step | User Action | Intermediate UI State | URL / State Change | Resulting Filter/Sort/Page | **Validation** |
|---|---|---|---|---|---|
| 1 | Open `/<ad_id>/` (e.g. from any result grid). | Full page `ads/detail.html`: `components/header_catalog.html` (same search bar) + `<article>`: gallery (GLightbox), title, price (`format_price`), description (localized), resolved features chips, location/category breadcrumbs, "Contact Seller" deep-link `t.me/<bot>?start=contact_<ad_id>`, "← Back to listings" = `javascript:history.back()` (`detail.html:183`). | `GET /<ad_id>/` | Single ad view. No filter/sort state. `AnalyticsEvent` `AD_VIEWED` for the seller recorded (`listings.py:68-72`). | **Integration:** `Client().get(f"/{ad.id}/")` → 200. Assert `response.context["ad"] == ad`, `response.context["bot_username"]` matches `settings.BOT_USERNAME`. Assert HTML contains `href="https://t.me/{bot_username}?start=contact_{ad.id}"`. Assert `href="javascript:history.back()"` back-link (`detail.html:183`). Assert `AnalyticsEvent.objects.filter(event_type="ad_viewed", ad_id=ad.id).exists()`. Assert resolved features only show category-appropriate ones (`listings.py:79-84`, `display_features` in context). |
| 2 | Type `ноутбук` in the header search; press Enter. | Header form full-page submit. | `GET /search/?q=ноутбук` (only `q` — ad's category/city **not** carried, `header_catalog.html:114-132`). | FTS on active locale vector (`search_vector_ru` for `ru`). Single-word `ноутбук` → `_fuzzy_category_match` may constrain to "Ноутбуки" subtree. Rank ordering, page 1. New history/popular entry recorded. | **Integration:** `Client().get("/search/?q=ноутбук")` → 200. Assert `response.context["query"] == "ноутбук"`, `response.context["current_category"] is None`. Assert `PopularSearch.objects.filter(query_normalized="ноутбук").exists()`. Assert `SearchHistory`/`session["search_history"]` contains "ноутбук" (if anon). Assert `AnalyticsEvent.objects.filter(event_type="search_performed").exists()`. |
| 3 | Browser Back. | Returns to the ad detail page (history entry intact). | Browser Back → `GET /<ad_id>/`. | Pre-search state restored via native Back stack. Because header search is a full-page `<form method="get">` submit (not HTMX), it pushes a standard history entry; Back pops correctly. | **Manual/e2e only (native browser):** Verify that pressing browser Back from `/search/?q=ноутбук` returns to `/<ad_id>/` with the ad detail page fully rendered (title, price, contact button). **In Django test client:** `Client`'s `back()` method simulates `HTTP_REFERER`-based navigation. Assert `response = client.get("/<ad_id>/")` → 200, `response.context["ad"]` is the original ad. This verifies the detail page is independently navigable/renderable (the actual browser Back is a client-side history-stack behavior, not testable via Django client — note as a Playwright-only check). |

**Back-button behavior:** The header search is a full-page `<form method="get">` submit, so it always pushes a standard history entry. Back reliably returns to the pre-search page. The Problem_01.md bug #2 is about the **X clear button** in the search input (native `type=search` clear-X does nothing), not the Back button.

### Test strategy (Scenario 6)
- **Step 1:** Integration test `Client().get(f"/{ad.id}/")`; assert context (`ad`, `bot_username`, `display_features`) + rendered HTML (Telegram deep-link, `javascript:history.back()` link, trust badge) + `AnalyticsEvent.AD_VIEWED`. Reference: `test_detail_context.py` (unit, mocked) + `test_ad_detail_queries.py` (integration).
- **Step 2:** Integration test `Client().get("/search/?q=...")` on the search view; assert FTS query, context, popular/history recording. Reference: `test_search_view.py`, `test_autocomplete.py::TestSearchViewRecordsAutocompleteData`.
- **Step 3:** **Playwright end-to-end** only — native browser Back-button behavior is outside Django's test client scope. Document as `manual=True` in test annotations. A Django-level proxy assertion: `Client().get(f"/{ad.id}/")` independently renders the detail page (200).

### Test data setup (Scenario 6)
- A PUBLISHED ad with a unique title (e.g., "Продам ноутбук Apple Macbook Pro"), description, price, at least one image, in a known category/city.
- The ad's category should have a child named "Ноутбуки" (slug `noutbuki`) to exercise the fuzzy single-word match in step 2.
- City: `city` fixture.
- Seller: `seller` fixture.
- At least one other ad with "ноутбук" in title to ensure search results are non-empty.

### Edge cases (Scenario 6)
| Edge case | How to verify |
|---|---|
| Ad not found / not published | `GET /<draft_ad_id>/` → 404 (`listings.py:64-65`, `Ad.DoesNotExist` → `raise Http404`). Assert 404 for a DRAFT ad. |
| Searching from detail with empty query | Header form with empty `q` → `GET /search/?q=` (empty string). `query = (request.GET.get("q") or "").strip()` → `""` (falsy). Falls to no-query branch (`search.py:198-208`), `sort` param honored. Assert `response.context["query"] == ""`. |
| Detail page contact button gated | Ad by a deleted/banned seller → `can_contact` template tag returns False → disabled button (`detail.html:160-178`). Assert HTML contains `cursor-not-allowed` and `disabled` attribute when `can_contact` is False. Reference: contact tags (`{% load contact_tags %}`). |
| Back from search to detail restores scroll | Not testable in Django client — Playwright only. Document as e2e test. |
| Category subtree match from ad's own category | If the ad is in "Ноутбуки" and the query is "ноутбук", `_fuzzy_category_match` constrains to the "Ноутбуки" subtree — the ad itself is in that subtree. Assert it appears in results. |

---

## Cross-Cutting Validation: Autocomplete Endpoint (`GET /api/search/autocomplete`)

| Behavior | Validation |
|---|---|
| Query sanitization | `q=""` → 200, `{"suggestions": [], "query": ""}`. `q="a"` (<2 chars) → same. `q="'; DROP TABLE--"` → empty (quotes/backslashes stripped, `sanitize.py:39-43`). Reference: `test_autocomplete.py::test_autocomplete_empty_query_returns_empty`, `test_autocomplete_malicious_query_sanitized`. |
| Rate limiting | 30 requests/min/IP → 31st returns 429 `{"error": "rate_limit"}` (`rate_limit.py:17-58`). Reference: `test_autocomplete.py::test_autocomplete_rate_limit`. |
| Merge + dedup sources | Response `{"query": <q>, "suggestions": [{text, source, type}]}`. Sources: `user_history`, `category`, `city`, `popular_search`. Deduplicated by `text`, capped at 10 (`autocomplete.py:80-90`). Reference: `test_autocomplete.py::test_autocomplete_deduplication`. |
| Popular gate | `hit_count >= 10` required (`popular_search.py:19`). Reference: `test_autocomplete.py::TestPopularSearchService::test_get_popular_suggestions_returns_matching_queries` (asserts `hit_count >= 10`). |
| Entity localization | `get_entity_suggestions(query, locale=...)` prefix-matches (`istartswith`) on `get_name(locale)`; cities not filtered by `is_active`. Reference: `test_autocomplete.py::TestEntitySuggestionsService::test_entity_suggestions_localized_bs`. |
| Anonymous session history | `GET /search/?q=велосипед` (anon) → then `GET /api/search/autocomplete?q=вел` → `user_history` suggestion "велосипед" in response. Reference: `test_autocomplete.py::test_autocomplete_anonymous_user_returns_session_history`. |
| Client render | `header_catalog.html:210-242` `render()` function processes `json.suggestions`, filters by `s.type === section || s.source === section`, renders up to 4 sections. `htmx:afterRequest` listener (`header_catalog.html:244-254`). Reference: `test_autocomplete_template.py::test_inline_script_follows_htmx`. |

## Cross-Cutting Validation: Preferred City (`POST /api/preferred-city/`)

| Behavior | Validation |
|---|---|
| Valid slug (guest, consented) | `POST /api/preferred-city/` body `slug=podgorica`, cookie `consent_preferences=true` → 200 `{"ok":true}`, `response.cookies["preferred_city"].value == "podgorica"`, `max-age=31536000`, `httponly=True`, `samesite="Lax"`. Reference: `test_preferred_city.py::test_post_with_valid_slug_sets_cookie`. |
| Valid slug (guest, no consent) | No `consent_preferences=true` cookie → 200 `{"ok":true}` but `preferred_city` NOT in `response.cookies`. Reference: `test_preferred_city.py::test_post_without_preferences_consent_sets_no_cookie`. |
| Valid slug (authenticated) | `POST` with `slug=budva`, auth user → `User.preferred_city` set to Budva City object. Reference: `test_preferred_city.py::test_post_with_valid_slug_persists_db_for_authenticated`. |
| Unknown slug | `POST slug=nowhere` → 400 `{"error":"invalid_city"}`. Reference: `test_preferred_city.py::test_post_with_unknown_slug_returns_400`. |
| Clear | `POST action=clear` or `POST slug=""` → 200 `{"ok":true}`, cookie deleted (value `""`), DB nulled for auth. Reference: `test_preferred_city.py::TestReset`. |
| Read-back (search view) | Cookie `preferred_city=podgorica` → `GET /search/?q=Велосипед` → only Podgorica ads; `response.context["current_city"] == "podgorica"`. Explicit `?city=budva` overrides cookie. DB wins over cookie for auth. Reference: `test_preferred_city_readback.py::TestSearchPreferredCityReadback`. |
| Read-back (listings path) | `GET /city/budva/` overrides preferred default; `GET /?city=budva` is a real filter; invalid `?city=budv` → did-you-mean banner. Reference: `test_preferred_city_readback.py::TestListingsPreferredCityReadback`. |
| Header badge | `GET /` with `preferred_city` cookie → header badge shows localized city name (`data-preferred-city-label`), dropdown lists city as `data-city-option="podgorica"`, "Entire country" clear item (`data-city-clear`). Reference: `test_preferred_city.py::TestHeaderCityBadge`. |

## Cross-Cutting Validation: Language Switching (`?lang=X`)

| Behavior | Validation |
|---|---|
| Priority | `?lang=bs` > `lang_pref` cookie > `Accept-Language` > default `ru` (`language.py:57-74`). |
| Activation | `translation.activate(lang)` + `request.LANGUAGE_CODE` set in `process_request` (`language.py:120-129`). |
| Persistence | `?lang=bs` writes `lang_pref` cookie (1 year, `SameSite=Lax`); session `django_language` for auth (`language.py:96-118`). |
| UI switcher | `components/language_switcher.html` dropdown: `ru/Russian`, `bs/Bosnian`, `en/English` via `{% get_available_languages %}`, each link `?lang=<code>`; current shown as upper-cased `LANGUAGE_CODE`. |
| FTS language | `?lang=bs` on `/search/?q=...` → `LanguageLocale.from_code(request.LANGUAGE_CODE)` → `search_vector_bs` (config `simple`). Reference: `search.py:162-164`. |
| Known gap | `?lang=` not re-emitted on HTMX GET to `request.path`; cookie re-establishes language on next full-page load. |

## Cross-Cutting Validation: Search History

| Behavior | Validation |
|---|---|
| Recording (auth) | `search.py:192-197` calls `increment_popular_search(query)` + `record_search_history(user_id, query, session)`. `SearchHistory` DB row created, deduped by `query_normalized`, pruned to 50 (`search/services/search_history.py:42-88`). Reference: `test_autocomplete.py::TestSearchHistoryService`. |
| Recording (anon) | Session `session['search_history']` (deduped, capped 50). No DB row. Reference: `test_search_view.py::test_search_anonymous_records_session_history`. |
| Display (autocomplete) | `GET /api/search/autocomplete?q=<prefix>` → `user_history` suggestions from `get_user_search_history` (auth: DB; anon: session). Limited to 5. Reference: `test_autocomplete.py::TestAutocompleteEndpoint`. |
| Display (cabinet) | `GET /cabinet/search-history/` → auth-only; lists DB `SearchHistory` rows, each links to `/search/?q=<query>`. `POST /cabinet/search-history/clear/` wipes all rows for user (302 redirect). |

## Cross-Cutting Validation: Analytics (`AnalyticsEvent`)

| Behavior | Validation |
|---|---|
| `SEARCH_PERFORMED` | Recorded after successful FTS run with non-empty query (`search.py:185-188`). Assert `AnalyticsEvent.objects.filter(event_type="search_performed").exists()` after `Client().get("/search/?q=...")`. Reference: `test_search_view.py::TestSearchViewRecordsAutocompleteData::test_search_records_popular_search`. |
| `AD_VIEWED` | Recorded on `ad_detail` for the seller (`listings.py:68-72`). Assert `AnalyticsEvent.objects.filter(event_type="ad_viewed", ad_id=ad.id).exists()` after `Client().get(f"/{ad.id}/")`. |

## Cross-Cutting Validation: HTMX Contract

| Behavior | Validation |
|---|---|
| HTMX vs full-page | Non-HTMX request → renders `ads/list.html` (full page). `HX-Request: true` → renders `ads/partials/ad_list.html` (fragment only, `listings.py:449-450`, `search.py:250-251`). Reference: `test_catalog_filters.py::test_form_renders_path_only_hx_get`. |
| Filter form `hx-get` | `filter_form.html:5-9` — `hx-get="{{ request.path }}"`, `hx-target="#ad-list"`, `hx-swap="innerHTML"`, `hx-push-url="true"`. Re-renders form on every swap to prevent stale state. Reference: `test_catalog_filters.py::TestFilterUrlReset::test_form_uses_request_path_not_empty`. |
| Pagination links | Every pagination link in `ad_list.html:142-169` carries full active param set + `page=N` + `hx-push-url="true"`. Reference: `test_catalog_filters.py::test_pagination_links_have_push_url_in_rendered_output` (asserts count `content.count("hx-push-url=\"true\"") == 9`). |
| Chip removal | Each chip `×` link (`ad_list.html:35-69`) is `hx-get` + `hx-push-url="true"` + `hx-target="#ad-list"`. Reference: `test_catalog_filters.py::test_chip_link_has_push_url_in_rendered_output`. |
| "Clear all filters" | `ad_list.html:71-74` — `hx-get="?page=1&q=...&sort=..."` + `hx-push-url="true"`; keeps `q` + `sort`, drops the rest. Reference: `test_catalog_filters.py::test_clear_all_filters_has_push_url`. |

## Cross-Cutting Validation: Save Search Modal (FT-002)

| Behavior | Validation |
|---|---|
| URL resolves | `reverse("search:save-search")` == `/save-search/`. Reference: `test_saved_search_create.py::test_save_search_url_resolves`. |
| Auth required | Unauth POST → 301/302 redirect to login. Reference: `test_saved_search_create.py::test_requires_login`. |
| Creates SavedSearch | Auth POST with `query`, `city_id`, `category_id`, `min_price`, `max_price` → `SavedSearch` row with `is_active=True`, `language=request.LANGUAGE_CODE`. Reference: `test_saved_search_create.py::test_create_saved_search_with_filters_and_language`. |
| Modal renders on `/search/` | `list.html:23-32` — "Save search" button + modal include visible when `request.user.is_authenticated and cities` (search view sets `cities` in context, `search.py:242`). Assert HTML contains `id="save-search-modal"`. |

---

## Appendix: Source Code Reference Map

| Component | Files |
|---|---|
| Listings view + ad detail | `apps/ads/views/listings.py:189-506` (listings), `:44-98` (ad_detail) |
| Search view (FTS) | `apps/search/views/search.py:33-253` |
| Autocomplete view | `apps/search/views/autocomplete.py:26-92` |
| Preferred city view | `apps/search/views/preferred_city.py:25-87` |
| Save search view | `apps/search/views/save_search.py:20-63` |
| Enums (AdSort, AdStatus, LanguageLocale, etc.) | `apps/core/enums.py:14-274` |
| PreferredCityMiddleware | `apps/core/middleware/preferred_city.py:33-79` |
| LanguagePreMiddleware | `apps/core/middleware/language.py:38-148` |
| Context processors | `apps/core/context_processors.py:27-87` |
| FTS trigger (per-language vectors) | Migration `0007_search_vector_i18n`; models `ads/models.py:210-268` |
| Filter form template | `templates/ads/partials/filter_form.html:5-127` |
| Ad list partial (chips, grid, pagination) | `templates/ads/partials/ad_list.html:1-193` |
| Header catalog (search bar, autocomplete, city) | `templates/components/header_catalog.html:113-549` |
| Detail template | `templates/ads/detail.html` |
| Breadcrumb | `templates/components/breadcrumb.html` |
| Root conftest (fixtures + `create_test_ad`) | `src/backend/conftest.py:105-211` |
| Catalog YAML (lookup overrides) | `apps/categories/catalog/categories.yaml` |
| CategoryLookupResolver | `apps/categories/services/lookup_resolution.py:140-194` |
