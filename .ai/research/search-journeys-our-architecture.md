# Search Journeys — Mapped to the Mko Bazuna Architecture

> **Purpose:** Map the six researched OLX/Avito search user journeys to the **actual**
> Mko Bazuna implementation (Django 5.2 HTMX MPA + PostgreSQL FTS), defining concrete
> filters, sorting, URL/state changes, and intermediate UI states.
>
> **Method:** Every claim below is grounded in the live source code (views, templates,
> models, middleware, enums, `categories.yaml`). Where the spec documents
> (`docs/01-spec/filter-ui.md`, `docs/01-spec/search-patterns.md`) drift from the
> implemented code, the **implementation** is treated as the source of truth and the
> drift is flagged explicitly (see §0).
>
> **Confidence:** HIGH for all mappings that cite a concrete file:line. Confidence is
> marked per section where static analysis is inconclusive.

---

## 0. Source of Truth & Spec-vs-Implementation Drift

The authoritative implementation lives in `src/backend/apps/`. The spec docs in
`docs/01-spec/` describe the intended UX but **diverge** from the code in a few
parameter names. These matter for journey mapping, so they are listed once here.

| Concept | Doc says (`filter-ui.md`) | **Actually implemented** | Files |
|---|---|---|---|
| Min price param | `price_min` / `price_max` | `min_price` / `max_price` | `ads/views/listings.py:323-339`, `search/views/search.py:84-95`, `ads/partials/filter_form.html:48-59` |
| Condition param | `listing_condition` | `condition` | `ads/views/listings.py:348-351`, `search/views/search.py:103-105`, `filter_form.html:37` |
| Condition chip slug `condition` | `current_condition` | `current_condition` (in `ad_list.html` chips) | `ad_list.html:53-54` |
| Features AND-semantics impl | "annotate with count of matching feature through-rows" | Chained `.filter(features__slug=<slug>)` + `.distinct()` | `ads/views/listings.py:353-363`, `search/views/search.py:107-117` |
| "Clear all filters" | drops all params incl. `q` | keeps `q` + `sort` + `page=1`, drops the rest | `ad_list.html:71-74` |

**Takeaway:** The implementation is the truth. `categories.yaml` is the canonical
catalog config (`src/backend/apps/categories/catalog/categories.yaml`); the runtime
lookup-option sets are derived from it via `CategoryLookupResolver`
(`apps/categories/services/lookup_resolution.py`) which walks the MPTT ancestor chain
(nearest-explicit-ancestor-wins) and caches 300s (`categories/services/lookup_resolution.py:140-194`).

---

## 1. Architecture Quick Reference

### Stack & processes
- Python 3.14 · Django 5.2 LTS · PostgreSQL 18 · HTMX 1.9.12 (MPA, server-rendered) · aiogram 3.x bot
- Two processes, one DB: **web** (gunicorn sync WSGI) + **bot** (aiogram, `django.setup()` + shared ORM). Migrations run exactly once before both start.
- Cache: Redis (`django_redis`) shared across workers/bot; dev/test use `LocMemCache`. Anonymous search history is stored in the **Django session** (default `db` engine → `sessionid` cookie references a `django_session` row), **not** literally in a cookie — see §3.5.

### URL map (actual)

| Method | URL | View | Name |
|---|---|---|---|
| GET | `/` | `ads.views.listings.listings` | `ads:listings` |
| GET | `/category/<slug:category_slug>/` | `listings` | `ads:listings_category` |
| GET | `/city/<slug:city_slug>/` | `listings` | `ads:listings_city` |
| GET | `/<int:ad_id>/` | `listings.ad_detail` | `ads:detail` |
| GET | `/search/?q=…&[filters]` | `search.views.search.search` | `search:search` |
| GET | `/api/search/autocomplete?q=` | `search.views.autocomplete.autocomplete` | `search:autocomplete` |
| POST | `/api/preferred-city/` | `search.views.preferred_city.set_preferred_city` | `search:preferred_city` |
| POST | `/save-search/` | `search.views.save_search.save_search` | `search:save-search` |
| GET | `/cabinet/search-history/` | `cabinet.views.search_history.search_history_list` | `cabinet:search-history` |
| POST | `/cabinet/search-history/clear/` | `search_history_clear` | `cabinet:search-history-clear` |
| GET | `/cabinet/saved-searches/` | `cabinet.views.saved_searches.saved_searches_list` | `cabinet:saved-searches` |
| GET | `/categories/<slug>/submenu/` | `categories.views.category_submenu` (lazy submenu) | `categories:category_submenu` |

### Two listing views
1. **`listings()`** (`apps/ads/views/listings.py:189`) — handles `/`, `/category/<slug>/`, `/city/<slug>/`. No `q`.
2. **`search()`** (`apps/search/views/search.py:33`) — identical filter set **plus** `q` (PostgreSQL FTS). Records `SEARCH_PERFORMED` analytics + popular-search hit + search history after a successful run.

Both render `ads/list.html`, which includes:
- `components/header_catalog.html` (shared Avito-style header: brand, place-an-ad CTA, All-Categories dropdown, **preferred-city selector**, **search bar + autocomplete**, breadcrumb, auth/favorites).
- `<div id="ad-list">` → `ads/partials/ad_list.html` (filter form + did-you-mean + chip bar + grid + pagination + empty states).

### HTMX contract (both views)
- The filter form is `hx-get="{{ request.path }}"` targeting `#ad-list` with `hx-push-url="true"` (`ad_list.html` re-renders the whole form on every swap so DOM state never goes stale — `filter_form.html:5-12`).
- Pagination links carry the **full** active param set and use `hx-push-url="true"` so Back/Forward preserves state (`ad_list.html:142-169`).
- Removing a chip or "Clear all filters" uses `hx-push-url="true"` → `#ad-list`.
- A non-HTMX request renders the full `ads/list.html`; an `HX-Request` renders only the `#ad-list` fragment (`listings.py:449-452`, `search.py:250-253`).

### Key architectural realities (not assumptions)
- **The header search bar submits only `q`.** `<form method="get" action="{% url 'search:search' %}">` contains `name="q"` and (for CSRF) `csrfmiddlewaretoken` — **no hidden `category`/`city`/filter inputs** (`header_catalog.html:114-132`). Submitting the header search therefore **drops the current category, city, and filter context** and lands on `/search/?q=<text>`. Category scoping on the search page only happens via the single-word fuzzy category detection in `search()` (`search/views/search.py:167-174`), not via carried-over context. This is the central divergence from the OLX/Avito "preserve context" recommendation (see §4 scenarios 2 & 4, and §6 gap list).
- **Sort on the search page is relevance, not the `sort` param.** When `q` is present, `search()` orders by `order_by("-rank", "-published_at", "-id")` (`search.py:178-182`); the `sort` param is parsed into context only. The sort dropdown in `filter_form.html` is wrapped in `{% if not query %}` (`filter_form.html:103-125`), so it is **hidden on `/search/?q=...`** — buyers cannot pick a sort on FTS results, only by date/price on non-FTS list views.
- **Price filtering is EUR-normalized.** Filters read `min_price`/`max_price` and filter `price_normalized_eur` (`ads/models.py:97-103`). Sellers enter `price_amount` + `price_currency` (EUR/RSD/BAM); the derived `price_normalized_eur` is what is filtered/sorted. Display keeps the seller's original currency via `format_price` (`price_tags.py:59-75`). So "Price: low to high" = `price_normalized_eur` ascending with `NULLS LAST`.

---

## 2. Concrete Filter Values & Sort Options

### Sorting (`AdSort` StrEnum in `apps/core/enums.py:14-20`)

| Enum member | URL value | Effect (listings / no-`q`) | Effect (`search` with `q`) |
|---|---|---|---|
| `AdSort.DATE_NEW` | `date_desc` | `-published_at` (default) | N/A — overridden by FTS rank |
| `AdSort.DATE_OLD` | `date_asc` | `published_at` | N/A |
| `AdSort.PRICE_LOW` | `price_asc` | `price_normalized_eur` ASC, `NULLS LAST` | N/A |
| `AdSort.PRICE_HIGH` | `price_desc` | `price_normalized_eur` DESC, `NULLS LAST` | N/A |

Search relevance order (with `q`): `-rank, -published_at, -id` (`search.py:180-182`).

### Listing Purposes (`listing_purpose`, single-select dropdown) — `categories.yaml:6-36`
`sell`, `give-away`, `rent`, `rent-short`, `lost`, `found`, `offer-service`, `seek-service`, `job-offer`, `job-seek` (10 values).

### Listing Conditions (`condition`, single-select dropdown) — `categories.yaml:38-44`
`new`, `used` (2 values).

### Features (`features`, multi-select checkboxes, AND-semantics) — `categories.yaml:45-96`
`delivery`, `pickup`, `negotiable`, `credit`, `exchange`, `installment`, `urgent`, `luxury`, `eco`, `handmade`, `branded`, `custom`, `warranty`, `packaging`, `import`, `local`, `smart-home` (17 values).

### Category-constrained option sets
`CategoryLookupResolver` resolves the **active** purpose/condition/feature set for the current category via ancestor-walk (nearest explicit ancestor wins), cached 300s (`lookup_resolution.py:140-194`). Overrides per category are declared in `categories.yaml` (e.g. `services-jobs` exposes only `job-seek/job-offer/seek-service/offer-service`; `charity` exposes only `give-away` with `[]` features). When **no** category is active, the full active `LookupItem` sets (ordered by `sort_order`) are shown (`listings.py:377-386`, `search.py:131-140`). Ad-display (detail) uses the same resolved set to hide mismatched features (`listings.py:79-84`).

### Price handling
- Sellers enter `price_amount` + `price_currency` ∈ {EUR, RSD, BAM} (`currencies/enum.py:11-20`).
- `price_normalized_eur` is derived and indexed (`IX_ads_price_normalized_eur`, conditional on non-null) — used for all filtering/sorting.
- Filter params `min_price`/`max_price` are parsed via `int(...)` (so EUR-equivalent integers) with `ValueError` → ignored (`listings.py:327-339`, `search.py:86-95`).

### Cities
Closed preset of Montenegro cities; Russian base name + i18n (`bs`/`en`) (`locations/models.py:11-57`). Resolved via preferred-city middleware (see §3.3). Default display: "Вся страна" (`gettext("Entire country")`) when no preferred city (`context_processors.py:52`).

### Languages
`ru` (primary), `bs` (Bosnian, latin), `en` — `LanguageLocale` enum (`core/enums.py:187-237`). FTS uses per-language vectors:
`search_vector_ru` (config `russian`), `search_vector_bs` (config `simple`), `search_vector_en` (config `english`) plus generic `search_vector`; all GIN-indexed (`ads/models.py:210-268`). No query-time translation (decision G).

---

## 3. Cross-Cutting Behaviors

### 3.1 Sorting application & URL encoding
- **Encoding:** `?sort=<value>` where value ∈ `AdSort` (`date_desc|date_asc|price_asc|price_desc`). Absent → default `date_desc` (`listings.py:390`, `search.py:156`).
- **Listings pages (`/`, `/category/…`, `/city/…`):** `sort` is honored by an explicit branch (`listings.py:390-402`). The sort `<select>` is always present in `filter_form.html` (rendered unconditionally there — note the `{% if not query %}` is on the listings path because `query` is unset).
- **Search page (`/search/?q=…`):** the sort dropdown is **hidden** (`filter_form.html:103`), and even if `sort=` is supplied it is ignored — results come back ranked by FTS `rank` (`search.py:178-182`). The spec doc `search-patterns.md:165` describes a sort selector on search results, but the implemented template gates it behind `{% if not query %}`, so in practice **FTS results are relevance-sorted only**. (Gap/DoD item.)
- **Preservation:** every pagination link and chip-removal link re-emits the current `sort` (and `q` if present) so the chosen sort survives paging (`ad_list.html`).

### 3.2 Language selection
- **Resolution priority** (`LanguagePreMiddleware`, `core/middleware/language.py:38-74`): `?lang=X` query param → `lang_pref` cookie → `Accept-Language` → default `ru`.
- **Activation:** `translation.activate(lang)` + `request.LANGUAGE_CODE` set in `process_request` (`language.py:128-129`). `LANGUAGE_CODE` exposed to templates via context processor (`context_processors.py:22-24`).
- **Persistence:** `?lang=` writes the `lang_pref` cookie (1 year, `SameSite=Lax`); for authenticated users it is also stored in the session (`django_language`) (`language.py:96-118`).
- **UI:** `components/language_switcher.html` — a dropdown of `ru/Russian`, `bs/Bosnian`, `en/English` (via `{% get_available_languages %}`), each link `?lang=<code>`. Current language shown as the upper-cased `LANGUAGE_CODE` (`language_switcher.html:23`, `:38-47`).
- **FTS language:** `search()` resolves the locale via `LanguageLocale.from_code(request.LANGUAGE_CODE)` and searches the matching per-language vector (`search.py:162-164`) — no translation on the search path (decision G).

> **Implementation note / drift:** `search-patterns.md:14` and the comparison doc mention `lang=X` carrying across navigation. The `?lang=` param is preserved only if the navigating link includes it; HTMX GETs to `request.path` do **not** automatically re-append `lang=`, so a filter change on `?lang=bs` will drop the `lang=` from the URL unless the form/href re-emits it. The `lang_pref` cookie re-establishes the language on the next full-page load, so the *display* stays correct — only the URL query param may drop on an HTMX transition. Flagged as a minor URL-canonicality gap.

### 3.3 City selection
- **Default (no city in URL):** `PreferredCityMiddleware.process_request` resolves `request.preferred_city` — `User.preferred_city` FK wins for authenticated users; the `preferred_city` cookie (1-year, HttpOnly, **consent-gated** on `consent_preferences=true`) for guests; stale/unknown slugs are ignored and the cookie deleted on response (`core/middleware/preferred_city.py:33-78`).
- **Headers apply it:** `listings()` falls back to `request.preferred_city` only when no path `?city=` is present (`listings.py:309-319`); `search()` does `current_city = explicit_city or getattr(request, 'preferred_city', None)` (`search.py:72-74`). So explicit `city` (path or query) wins over the preference.
- **Choosing a city:** header city button → dropdown (`header_catalog.html:43-72`). Clicking a city POSTs `slug` to `search:preferred_city` (sets cookie + DB for auth) then does a **full-page** `window.location.href = '/city/<slug>/'` (`header_catalog.html:497`). "Entire country" = clear (POST `action=clear` → cookie deleted + DB nulled for auth) then `window.location.href = '/'` (`header_catalog.html:485-488`).
- **Display:** header button label = `preferred_city_display` from `header_context` (localized name or "Вся страна") (`context_processors.py:52-59`).
- **Invalid city slug (did-you-mean):** on listings, an unknown `?city=` or `/city/<slug>/` path triggers `_suggest_city()` (difflib, cutoff 0.6) and a "Did you mean:" banner linking to `ads:listings_city` with the suggested slug (`listings.py:286-308`, `ad_list.html:26-32`). On search, an invalid `?city=` sets `suggested_city` (echo) but there is **no fuzzy match** — it only echoes the slug (`search.py:80-81`); the banner then links to `ads:listings_city` with the (still-invalid) slug (`ad_list.html:29`). Gap: search's city did-you-mean is echo-only, not fuzzy (unlike listings).

### 3.4 Search history (recorded & displayed)
- **Recording:** after a successful FTS run with a non-empty query, `search()` calls `increment_popular_search(query)` and `record_search_history(user_id, query, session=request.session)` (`search.py:192-197`).
- **Authenticated:** `SearchHistory` rows in `search_history` table, deduped by `query_normalized` (delete-then-create), pruned to 50 per user (`search/services/search_history.py:42-88`).
- **Anonymous:** stored in `session['search_history']` (deduped, capped 50) — i.e. in the DB session table referenced by the `sessionid` cookie, **not** as a standalone cookie. This is the mechanism behind Problem_01.md bug #1 ("it's apparently stored at the cookie level") — the sessionid cookie keeps the anonymous history alive across the browser session.
- **Display:** surfaced as autocomplete `user_history` suggestions (limit 5) and in the authenticated-only cabinet page `/cabinet/search-history/` (`cabinet/views/search_history.py:23-35`, `templates/cabinet/search_history.html`). Each history row links to `/search/?q=<query>` (re-run); "Clear history" POSTs to `cabinet:search-history-clear` (wipes all rows for that user).

### 3.5 Autocomplete suggestions (behavior)
- **Endpoint:** `GET /api/search/autocomplete?q=<text>` → `search:autocomplete`. Sanitized (`sanitize_autocomplete_query`: stripped, min 2 / max 100 chars, quotes/backslashes removed → returns empty list if invalid) (`core/utils/sanitize.py:39-43`, `autocomplete.py:53-55`).
- **Rate limit:** 30 req/min per IP via Redis cache atomic-incr; HTTP 429 on overflow (`rate_limit.py:17-58`).
- **Sources merged & deduped by `text`, capped at 10:**
  1. `user_history` — `get_user_search_history` (auth: DB `SearchHistory` order `-created_at`[:5]; anon: session `search_history`[:5]) (`autocomplete.py:64-69`).
  2. `category` + `city` — `get_entity_suggestions`: case-insensitive prefix match on `name__istartswith`, localized via `get_name(locale)`, cities NOT filtered by `is_active` (`entity_suggestions.py:36-90`).
  3. `popular_search` — `get_popular_suggestions`: `query_normalized__startswith` prefix match, `hit_count >= 10`, ordered by `-hit_count`[:5] (`popular_search.py:48-79`). **Important:** popular suggestions require MIN_HIT_COUNT = 10, so on a low-traffic/seed instance the popular section is empty by design.
- **Response shape** (`autocomplete.py:89-92`): `{"query": <q>, "suggestions": [{text, source, type, ...}]}`.
- **Client render** (inline JS in `header_catalog.html:180-312`): dropdown opens on `input` (300ms debounce). Renders "Show all results" link first, then up to 4 sections — Cities, Categories, Popular, History — each with an SVG icon. The handler is bound to the global `htmx:afterRequest` event and filters on `detail.target === #autocomplete-dropdown` (because `hx-swap="none"`) (`header_catalog.html:244-254`).
- **Click handlers** (`header_catalog.html:262-283`): city → POST preferred-city then full-page nav to `/city/<slug>/`; category → full-page nav to `/category/<slug>/`; text (popular/history) → populate input + `searchForm.submit()` → `/search/?q=<text>`.
- **Keyboard:** Escape hides; ArrowUp/Down cycles suggestions; Enter submits the form (`header_catalog.html:285-305`).

> **Bug #1 status (Problem_01.md #1):** The endpoint already returns all sources unconditionally and `render()` iterates all four sections. Static analysis does **not** reveal a code path that suppresses non-history sections, so the root cause is **not determinable from source alone** — it must be investigated at runtime (e.g. the `popular_search` `hit_count>=10` gate is empty on a quiet instance, masking itself as "only history"; or a stale signed-cookie session / `htmx:afterRequest` target mismatch on repeat XHRs). Confidence: LOW on root cause; HIGH that the intended design merges all sources.

---

## 4. The Six Journey Scenarios

Notation for each step: **Action** (user does X) → **UI State** (what renders) → **URL/State** (browser URL + HTMX push) → **Filter/Sort/Page** (effective backend state).

### Scenario 1 — Homepage → enter search query → search results
(US-B2, US-B9, US-B10)

| Step | User Action | Intermediate UI State (template fragment) | URL / State Change | Resulting Filter/Sort/Page State |
|---|---|---|---|---|
| 1 | Land on `/` (no auth). | Full page: `components/header_catalog.html` (city button label = preferred_city_display, e.g. "Вся страна"; All-Categories dropdown; empty search bar) + `ads/list.html` → `#ad-list` → `ads/partials/ad_list.html` (`filter_form.html`: purpose/condition/price/features/sort controls, hidden `min_price`/`max_price`, **no** `q`/`category`/`city` hidden inputs since none set). 24-card grid, newest-first. | `GET /` | `query=None`; list view. `current_sort=date_desc` (default). No city filter → preferred city applies (or none). Ads = all `PUBLISHED`, ordered `-published_at`, page 1 of 24. |
| 2 | Focus the search bar. | Autocomplete dropdown opens (`ul#autocomplete-dropdown`): "Show all results" link + sections Cities/Categories/Popular/History (history empty for first visit; popular likely empty if `<10` hits; entity matches depend on keystroke prefix). | No URL change (XHR to `search:autocomplete`). | No filter/sort state change — read-only suggestion query. |
| 3 | Type query e.g. `ноутбук`. | Autocomplete refines per prefix (`input` 300ms → `GET /api/search/autocomplete?q=ноутбук`). For the single-word `ноутбук`, the dropdown's "Show all results" link points to `/search/?q=ноутбук`; entity matches may include category `Ноутбуки`. | No URL change yet; XHR only. | No filter/sort state change. |
| 4 | Press Enter / click "Show all results". | Full-page form submit (`data-search-form`, `action=search:search`). Browser navigates; on load the header re-renders with `query="ноутбук"` pre-filled in the input. `#ad-list` shows `ad_list.html` **without** `filter_form.html`'s sort block (`{% if not query %}` hides it); purpose/condition/price/features still present but no `q` hidden input is needed here (the form posts to `/search/` directly). | `GET /search/?q=ноутбук` (only `q`; **category & city dropped** because the header form has no hidden category/city). | `search()` runs FTS on `search_vector_<locale>` (Russian vector, since LANGUAGE_CODE defaults `ru`). Single-word `ноутбук` also triggers `_fuzzy_category_match` → may constrain to the `Ноутбуки` subtree (`search.py:167-174`). Ordering: `-rank, -published_at, -id`. `page=1` implicit. `SEARCH_PERFORMED` event recorded; `ноутбук` written to history (DB for auth, session for anon). |
| 5 | Scroll / click page 2. | HTMX `hx-get`?page=2&q=ноутбук` → target `#ad-list` → `innerHTML` swap + `hx-push-url` updates browser URL. Header stays intact. | `GET /search/?q=ноутбук&page=2` (pushed to history). | Page advances to 24–48; rank ordering preserved; `q` preserved. |

**Sorting note:** not selectable on the FTS results page — the dropdown is hidden (`filter_form.html:103`); `sort` param is ignored by `search()` when `q` is present.

### Scenario 2 — Homepage → select category → filters → enter search query → results
(US-B2, US-B3, US-B6, US-B10)

| Step | User Action | Intermediate UI State | URL / State Change | Resulting Filter/Sort/Page |
|---|---|---|---|---|
| 1 | On `/`. Open "All Categories" dropdown (desktop) or mobile hamburger. | `components/header_catalog.html` categories panel; root categories rendered from `root_categories` (context proc). Expands submenus lazily via `fetch('/categories/<slug>/submenu/')` (`header_catalog.html:318-336`). | No URL change (client panel). | — |
| 2 | Click category `transport`. | Full-page navigation. Header "All Categories" button label now = "Транспорт" (`current_cat`). Breadcrumb trail `Home › Транспорт` (`breadcrumb.html`). `#ad-list` = `ad_list.html` for the transport subtree (purpose options now constrained to `sell/rent` via resolver; features constrained to the transport set). | `GET /category/transport/` | `query=None`. `category=transport` (path). `listing_purpose`/`features`/`condition` resolved for transport. `sort=date_desc` default. Ads = `PUBLISHED` where category ∈ transport subtree, page 1. |
| 3 | In the filter form, pick `listing_purpose=rent`, add features `delivery`+`price_min=1000`. Click "Apply filters". | `filter_form.html` re-renders (server-validated selects/checkboxes reflect new state); active chips for Purpose + the two features appear; grid updates. | HTMX `GET /category/transport/?listing_purpose=rent&features=delivery&min_price=1000&page=1` → `hx-push-url`, swap `#ad-list`. | `current_category=transport`; `listing_purpose=rent`; `feature_slugs=[delivery]`; `min_price=1000`; `sort=date_desc`; page 1. Results filter on transport subtree ∩ purpose ∩ features ∩ price≥1000. |
| 4 | Type `iphone` in the header search bar; press Enter. | Header search is a full-page `<form>` submit → server renders `/search/`. | `GET /search/?q=iphone` (**category `transport` and the rent/delivery/price filters are dropped** — see §1 architectural reality). | `search()` runs FTS. `iphone` is not a category-name fuzzy match, so no subtree constraint is auto-applied despite having come from `/category/transport/`. Results = FTS rank order, page 1. |
| 5 | Refine: open the on-page filter form, pick `listing_purpose=rent`, add feature `credit`. Click "Apply filters". | Filter form (now targeting `/search/` because `request.path=/search/`) has hidden `q=iphone` + hidden `category` only if `current_category` were set — it is **not** (header submit dropped it). | HTMX `GET /search/?q=iphone&listing_purpose=rent&features=credit&page=1` → pushUrl, swap `#ad-list`. | `q=iphone`; `listing_purpose=rent`; `features=[credit]`; `current_category=None`. FTS results constrained by the new filters. "Save search" button visible (auth + `cities` in context). |

**Observation vs. research:** OLX/Avito preserve category+filter context when refining query; our header form carries only `q`. To keep category scope, the user must either re-select the category via the autocomplete suggestion (→ `/category/transport/`) or rely on single-word fuzzy detection. Flagged in §6.

### Scenario 3 — Homepage → enter query → apply filters → results
(US-B2, US-B3, US-B10)

| Step | User Action | Intermediate UI State | URL / State Change | Resulting Filter/Sort/Page |
|---|---|---|---|---|
| 1 | On `/`. Type `авто` in the header search; press Enter. | Full-page nav to `/search/`. Header input pre-filled with `авто`. `#ad-list` renders `ad_list.html` with the filter form (no sort dropdown, since `query` is truthy) + grid. | `GET /search/?q=авто` | FTS on Russian vector for `авто`; rank-ordered. `page=1` implicit. (History + popular hit incremented.) |
| 2 | Set `min_price=500`, `max_price=5000`, `listing_purpose=sell`, feature `negotiable`. Click "Apply filters". | Filter form's `q` hidden input preserves `авто`; selects/inputs reflect new values; chips update; grid re-ranks by FTS within the narrowed set. | HTMX `GET /search/?q=авто&min_price=500&max_price=5000&listing_purpose=sell&features=negotiable&page=1` → pushUrl, swap `#ad-list`. | `q=авто`; `min_price=500`/`max_price=5000` (on `price_normalized_eur`); `listing_purpose=sell`; `features=[negotiable]`; rank order preserved; page 1. |
| 3 | Remove the `negotiable` chip (×). | Chip disappears; grid re-renders. | HTMX `GET /search/?q=авто&min_price=500&max_price=5000&listing_purpose=sell&page=1` (chip link omits that feature but keeps `q`, `sort`, price, purpose) → pushUrl. | `features` now empty; all other filters retained. |
| 4 | Click "Clear all filters" (top-right of chip bar). | Chips vanish; form resets to any/empty; full grid re-renders (still FTS-ranked because `q=авто` retained). | HTMX `GET /search/?q=авто&page=1&sort=<current_sort>` (drops city/category/condition/features/price/purpose) → pushUrl. | Back to plain `/search/?q=авто` (page 1). Note: `q` and `sort` are kept by the "Clear all filters" link (`ad_list.html:71-74`) — this clears *filters*, not the query. |

### Scenario 4 — Category page → enter search query → results
(US-B2, US-B6, US-B10)

| Step | User Action | Intermediate UI State | URL / State Change | Resulting Filter/Sort/Page |
|---|---|---|---|---|
| 1 | Navigate to `/category/electronics/` (via header dropdown or catalog grid). | Breadcrumb `Home › Товары > Электроника`; header "All Categories" = "Электроника"; filter form shows electronics-resolved purposes (`sell`) + features (`delivery/pickup/negotiable/credit/exchange/urgent/warranty/packaging/branded/import/local`) + conditions (`new/used`). | `GET /category/electronics/` | `current_category=electronics`; subtree filter; `sort=date_desc`; page 1. |
| 2 | Type `macbook` in the header search; press Enter. | Full-page submit of the header form (carries `q` only). | `GET /search/?q=macbook` (**category `electronics` is NOT carried** — header form has no category hidden input). | FTS on the resolved locale vector. `macbook` is single-word; `_fuzzy_category_match` checks slug + exact `get_name` + difflib(0.8) — `macbook` ~ "Macbook"? no category is named that, so **no subtree auto-constraint**. Results are site-wide FTS, rank-ordered. |
| 3 | To keep electronics scope, use the autocomplete category suggestion instead. | Type `mac` → dropdown shows category "MacOS??" not present; typing the category name e.g. `электроника` → category suggestion appears. Click it. | Click → `header_catalog.html:278` navigates `window.location.href = '/category/electronics/'`. | Lands on `/category/electronics/` (listings view, no `q`).  |
| 3b | Alternatively, from step 2's `/search/?q=macbook`, manually add category via autocomplete by searching a category name, or re-apply category scope. | The on-page filter form has **no category control** (`filter_form.html` exposes purpose/condition/price/features/sort, not category). So there is no UI to add `category=` to `/search/?q=…`. | — | **Gap:** once on `/search/?q=`, category scope can only be re-established by leaving the page (autocomplete category link → `/category/<slug>/`) or by exploiting the single-word fuzzy detection. The comparison doc §3.2/§3.5 expects context preservation; the implementation does not. |

**Cross-cutting:** switching language (`?lang=bs`) on `/search/?q=macbook` re-runs FTS against `search_vector_bs`; the city defaults to preferred-city (or "Вся страна"); no "Save search" button on the category listing page (only `/search/` exposes it, because `listings()` does not add `cities` to context — `ad_list.html`/`list.html:23`).

### Scenario 5 — Category page → apply filters → results
(US-B3, US-B6)

| Step | User Action | Intermediate UI State | URL / State Change | Resulting Filter/Sort/Page |
|---|---|---|---|---|
| 1 | On `/category/transport/`. | Filter form options constrained to transport: purposes `sell/rent`, features `{delivery, pickup, negotiable, credit, exchange, urgent, warranty}`, conditions (transport has no `listing_condition_override` in `categories.yaml:147-152` → so conditions resolve from nearest ancestor with an override; transport itself sets `listing_condition_override: [new, used]`, so `new/used` shown). | `GET /category/transport/` | `current_category=transport`; purpose/feature/condition sets resolver-derived; `sort=date_desc`; page 1. |
| 2 | Pick `listing_purpose=rent`, feature `credit` + `urgent`, `min_price=200`, sort `price_desc`. Click "Apply filters". | Form re-renders with sticky selections; chips for Purpose + 2 features; grid re-sortable by price. | HTMX `GET /category/transport/?listing_purpose=rent&features=credit&features=urgent&min_price=200&sort=price_desc&page=1` → pushUrl, swap `#ad-list`. (Repeated `features=` params carry AND-semantics per `request.GET.getlist`.) | `current_category=transport`; `listing_purpose=rent`; `feature_slugs=[credit,urgent]`; `min_price=200`; `current_sort=price_desc`; page 1. DB: `features__slug IN (credit,urgent)` with all required (AND) + `.distinct()` (`listings.py:358-363`). |
| 3 | Click feature chip × for `urgent`. | `urgent` chip removed; `credit` retained; grid re-renders. | HTMX `GET /category/transport/?features=credit&...page=1` (chip link preserves `q`(none), `category`? — note the chip links do **not** re-emit `category` because on a listings path the category is in the *path*, not a param; the chip hrefs are relative `?page=1&...` so the path `/category/transport/` is retained) → pushUrl. | `features=[credit]`; `listing_purpose=rent`, `min_price=200`, `sort=price_desc` retained; path still `/category/transport/`. |
| 3b | "Clear all filters" chip. | Resets to base category page. | HTMX `GET /category/transport/?page=1&sort=price_desc` → pushUrl. | Page 1, no purpose/condition/features/price; sort **retained** (the "Clear all filters" href re-emits only `page=1`, `q`(none), `sort`). |

**Note on chip hrefs & category-in-path:** on `/category/<slug>/`, the chip/pagination links are relative (`?…`) so they ride the current path — category is inherently preserved via the URL path. By contrast on `/search/?q=…`, the category is a *param* (`current_category`) that the header form never sets, so it is lost on a fresh `/search/` entry (see Scenario 4).

### Scenario 6 — Product/ad detail page → initiate a new search → results
(US-B2, US-B4, US-B10)

| Step | User Action | Intermediate UI State | URL / State Change | Resulting Filter/Sort/Page |
|---|---|---|---|---|
| 1 | Open `/<ad_id>/` (e.g. from any result grid). | Full page `ads/detail.html`: `components/header_catalog.html` (same search bar as everywhere) + `<article>`: gallery (GLightbox), title, price `format_price` (original currency), description (localized), resolved features chips, location/category breadcrumbs, "Contact Seller" deep-link `t.me/<bot>?start=contact_<ad_id>`, and a "← Back to listings" link = `javascript:history.back()` (`detail.html:183`). | `GET /<ad_id>/` | Single ad view; no filter/sort state. |
| 2 | Type `ноутбук` in the header search; press Enter. | Header form full-page submit. | `GET /search/?q=ноутбук` (only `q` — the ad's category/city are **not** carried by the header form). | FTS on the active locale vector; `ноутбук` is single-word → `_fuzzy_category_match` may constrain to the "Ноутбуки" subtree. Rank ordering, page 1. New history/popular entry recorded. |
| 3 | Browser Back. | Returns to the ad detail page (history entry intact). | Browser Back → `GET /<ad_id>/`. | Pre-search state (the detail page) restored via the native Back stack — `hx-push-url` was only used for `#ad-list` AJAX swaps earlier, never for the header search, so a full-page nav to `/search/` pushes a normal history entry that Back pops correctly. |

**Back-button behavior:** Because the header search is a full-page `<form method="get">` submit (not HTMX), it always pushes a standard history entry — so "Back" reliably returns to the pre-search page (here, the ad detail). This differs from an HTMX-triggered transition (which also pushes via `hx-push-url`) but the outcome (restorable pre-search state) is the same. The Problem_01.md bug #2 "X button does nothing" is **not** about the Back button — it is about the clear (X) control in the search input itself (see §5).

---

## 5. Bug Status (Problem_01.md) vs. Implementation

| Bug (# in Problem_01.md) | Reported symptom | Actual implementation state | Verdict |
|---|---|---|---|
| **#1** | First autocomplete works; repeat/empty query shows **only history**, no other suggestions; "saved somewhere at cookie level." | Endpoint `search:autocomplete` returns all sources unconditionally (`autocomplete.py:26-92`); client `render()` renders all four sections (`header_catalog.html:217-239`). Anonymous history is kept in the **Django session** (DB `django_session` row keyed by `sessionid` cookie) — explaining the dev's "cookie level" impression. Popular suggestions are gated by `hit_count>=10` (`popular_search.py:19`), so on a quiet/seed instance the popular section is **always empty** and can masquerade as "only history." | **Root cause not determinable from static analysis (LOW confidence).** Intended design is correct; needs runtime debugging (popular-hit gate + signed-cookie session + XHR target-mismatch hypotheses). Not a missing-feature bug. |
| **#2** | Clicking the clear (X) after search does nothing; site should return to pre-search state. | The search input is `<input type="search">` (`header_catalog.html:117`). Browsers render a **native** clear-X for `type=search`; clicking it only clears the field value and fires no submit/navigation, so the URL (`/search/?q=…`) and results are unchanged. There is **no explicit, wired clear button** in the markup. The comparison doc §3.4 & §2.6 recommend: clear should return to the pre-search state. | **Confirmed gap.** Needs an explicit clear control wired to navigate back to the last browsing position (`/` or `history.back()`), plus ideally `?lang=` preservation. |
| **#3** | "Need to verify the current architecture…" (text cut off) | Architecture documented in full above (§1) and in `.ai/research/olx-vs-avito-comparison.md` §3.2–3.5. | **Resolved by this document.** |

### Related implemented-vs-recommended gaps (not in Problem_01.md, but blocking faithful journey coverage)
1. **Sort not available on FTS results.** Spec `search-patterns.md:182` shows a sort selector on search results; the template hides it (`{% if not query %}`) and `search()` ignores `sort=` when `q` is set. **Implemented behavior = relevance-only on `/search/?q=`.**
2. **Header search drops category/city/filters (Scenarios 2, 4, 6).** OLX/Avito preserve context; our header form submits only `q`. **Implemented behavior = context loss; must re-scope via autocomplete/fuzzy.**
3. **Search `condition` param name vs. spec.** Spec says `listing_condition`; code reads `condition`. Documented in §0.
4. **City did-you-mean is fuzzy on listings but echo-only on search.** (§3.3.)
5. **Sort param + `lang=` can drop on HTMX transitions** because `hx-get` re-serializes form/href fields only (no automatic `lang=` re-emission). Low severity (cookie re-applies on reload).

---

## 6. Journey-to-Architecture Mapping Matrix

| Journey | Entry URL | Exit URL (results) | Engine | Category carried via header search? | City carried via header search? | Sort available? | Search history recorded? |
|---|---|---|---|---|---|---|---|
| 1. Home → query → results | `/` | `/search/?q=<t>` | FTS (`/search/`) | ❌ (header form sends only `q`) | ⚙ Preferred-city **default** survives (middleware fallback); explicit `/city/<s>/` path is dropped | ❌ (FTS rank) | ✅ yes |
| 2. Home → category+filter → query → results | `/` → `/category/<c>/` | `/search/?q=<t>` | FTS (`/search/`) | ❌ lost on header submit | ⚙ Preferred-city **default** survives; category path dropped | ❌ (FTS rank) | ✅ yes |
| 3. Home → query → filters → results | `/` → `/search/?q=<t>` | `/search/?q=<t>&<filters>` | FTS (refine) | n/a (none to carry) | ⚙ Preferred-city default applies (no explicit city to carry) | ❌ (FTS rank) | ✅ yes (recorded on the query step) |
| 4. Category → query → results | `/category/<c>/` | `/search/?q=<t>` | FTS (`/search/`) | ❌ lost | ⚙ Preferred-city **default** survives (middleware); category path dropped | ❌ (FTS rank) | ✅ yes |
| 5. Category → filters → results | `/category/<c>/` | `/category/<c>/?<filters>` | Listings (`/category/`) | ✅ via path | ✅ via path / preferred fallback | ✅ yes (`?sort=`) | n/a (not a search) |
| 6. Detail → query → results | `/<id>/` | `/search/?q=<t>` | FTS (`/search/`) | ❌ lost (ad's category not carried) | ⚙ Preferred-city **default** survives; ad's city not carried | ❌ (FTS rank) | ✅ yes; Back restores detail |

Legend: FTS = PostgreSQL full-text search on per-language `search_vector_*`. "carried via header search?" = preserved when navigating from the entry into `/search/` **via the header search bar** (the shared path for journeys 1, 2, 4, 6). ⚙ = the **preferred-city** preference (cookie/DB) is re-applied by `PreferredCityMiddleware` as a *default* on the search page, so a user's default city is not truly "lost" — but an *explicit* city chosen via the `/city/<slug>/` path, or the ad's own city on the detail page, is **not** carried into the URL and only the stored preference (if any) re-applies. Journey 5 never leaves the listings engine, so category/city are carried natively via the URL path.

**Note on the homepage city hidden input:** on `/`, if the buyer has a preferred city, `listings()` sets `current_city=effective_city` and `filter_form.html` emits a hidden `<input name="city" value="<preferred>">` for filter submits — but the **header** search bar does not read this and always submits only `q`.

---

## 7. Concrete URL/State Templates (copy-paste ready for verification)

Filter form (on a category listings page, HTMX):
```
GET /category/transport/?listing_purpose=rent&features=credit&features=urgent&min_price=200&sort=price_desc&page=1
```
- features repeated (AND), page resets to 1 on every filter change (form sets `page=1` via hidden? — actually the form has no `page` field; htmx serializes only form controls, so `page` is NOT sent unless a control has it → the server default `request.GET.get("page", 1)` ⇒ page 1).

Search results (FTS), no sort honored:
```
GET /search/?q=macbook&listing_purpose=sell&features=credit&min_price=500&max_price=5000&page=2
```
- `sort` omitted/ignored; ordering = `-rank, -published_at, -id`.

Autocomplete:
```
GET /api/search/autocomplete?q=mac   →  200 {"query":"mac","suggestions":[...]}  (429 if rate-limited)
```
- `q` sanitized to 2–100 chars; empty/short → `{"suggestions":[],"query":""}`.

Preferred city:
```
POST /api/preferred-city/  body: slug=Podgorica   →  200 {"ok":true} (+ cookie for guests w/ consent; + User.preferred_city for auth)
POST /api/preferred-city/  body: action=clear     →  200 {"ok":true} (cookie deleted, User.preferred_city=null)
```

Search history cabinet (auth):
```
GET  /cabinet/search-history/
POST /cabinet/search-history/clear/  → 302 → /cabinet/search-history/
```

Saved search (auth, on `/search/` via modal):
```
POST /save-search/  body: query=macbook&city_id=12&category_id=45&min_price=500&max_price=5000&language=ru
```

---

## 8. Decisions Requiring a Product Call (open questions)

1. **Sort on FTS results** — Should `/search/?q=…` honor `?sort=` (with a relevance-first default) or stay rank-only? Spec text implies a sort selector; templates hide it. (Spec `search-patterns.md:182` vs `filter_form.html:103`.)
2. **Clear-X behavior** — Navigate to `/` (last browsing state) or `history.back()`? Recommendation in `olx-vs-avito-comparison.md:80,96` is "return to pre-search state."
3. **Header-search context preservation** — Wire the header search form to carry the active category (path→`?category=`) and city when submitting from a `/category/…` or `/city/…` page, to match OLX/Avito. Currently dropped (Scenarios 2, 4, 6).
4. **Search param naming** — Reconcile spec (`price_min`/`price_max`, `listing_condition`) with implementation (`min_price`/`max_price`, `condition`) in the docs (§0) — cosmetic but confuses implementers.
5. **Autocomplete popular gate** — Is `min_hit_count=10` intended for MVP, or should popular suggestions degrade gracefully (e.g. lower threshold / seed popular queries) so the dropdown never reads as "only history" on low traffic (Problem_01.md #1)?

---

*End of document.*
