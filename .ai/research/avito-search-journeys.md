# Avito Search & Filtering UX — Research & User Journeys

> **Status:** Research complete. Output of live-site investigation + corroborating documentation.
> **Reference target:** `avito.ru` (desktop web). This is the primary reference for the Mko Bazuna "Avito-like" classifieds board.
> **Last verified:** 2026-08-29

---

## 0. Research methodology & confidence key

Direct live fetches of category/result pages returned HTTP **429 (Too Many Requests)** — Avito actively rate-limits automated/harvest clients on `www.avito.ru` and `m.avito.ru`. The homepage *was* retrieved (a thin HTML shell) and confirmed the stack below. To compensate, I cross-referenced the live site's stated structure with **official Avito engineering publications** (`habr.com/ru/companies/avito/`), the **Avito developer catalog** (`developers.avito.ru/api-catalog`), **verified scraper/integrator documentation** (Apify, SelSup, avito-python), and **Avito Help/blog articles**.

**Confidence notation used throughout:**

| Label | Meaning |
|-------|---------|
| **VERIFIED** | Asserted in ≥2 independent, authoritative sources (official Avito docs/engineering blog, or observed in live HTML/response), or directly observed in fetched content. |
| **MEDIUM** | Widely reported by multiple reputable third-party sources (scraper/integrator docs, community) but not confirmed against a live page in this session. Treated as reliable but with residual risk of platform drift. |
| **LOW** | Inferred from analogous classifieds UX or older documentation; flagged explicitly and used only to flesh out a section. |

---

## 1. Platform overview (verified structural facts)

| Aspect | Detail | Confidence |
|--------|--------|------------|
| Domain | `https://www.avito.ru` (desktop), `https://m.avito.ru` (mobile). Assets served from `www.avito.st`. | VERIFIED |
| Architecture | **Client-side-rendered React SPA.** The server returns an HTML shell + JS bundles (`main.<hash>.js`; `react-router`, `react-redux`, `axios`). All listing/search markup is injected client-side. | VERIFIED (observed HTML) |
| Scraping convention | DOM nodes carry stable `data-marker` attributes (e.g. `data-marker="item"` for a listing card). CSS classes are hashed and change per release; `data-marker` is the durable hook. | VERIFIED |
| Region scope | Russia-wide. Cities are top-class "regions" with dedicated URL slugs. | VERIFIED |
| Ads per page | **50** results per page (`limit=50` is the hard cap reported by integrators; confirmed in scraper docs). | VERIFIED |
| Pagination gate | Anonymous users are capped at a shallow page depth; beyond that Avito returns 401/captcha/login-wall. | VERIFIED |

### Distinctive Avito technical facts
- **No static `sort=` param.** Avito encodes sort order as the numeric `s=<code>` query parameter (not the `sort=` hypothesis). The only sort code directly corroborated in this session: **`s=104` → "сортировка по дате публикации"** (sort by publication date, newest first). *(The task brief's `?sort=10 / ?sort=1` hypothesis does NOT match Avito's actual `s=` numeric codes — see §6.)*
- **City + category are in the URL path, not query params.** Region, category, and sub-category form the path; only filters/query live in the query string. This is the "geoot.ru/moscow"-style routing the brief references, realised as `avito.ru/<region>/<category>/<subcategory>`.
- **Search key is `q=`**, not `query=`/`text=`. Price bounds are `pmin`/`pmax` (lowercase, no `Max`/`Min` casing).
- **Three-level ML ranking pipeline** (Ranker 3, since ~2024): candidate selection (reverse index over 230M+ ads) → L1 pick top-500 → L2 pick top-50. Ranking uses relevance + CTR + freshness + photo quality + seller reputation + personalization.

---

## 2. URL architecture (the "city-routing" pattern)

### 2.1 Canonical shape
```
https://www.avito.ru/<region>/<category-tree>?<query-params>
```
- `<region>`: a kebab-case transliterated English slug of the region name (see table below). The bare region root lists "all regions" results; there is **no** region-less default.
- `<category-tree>`: 1–3 kebab-case path segments for the category hierarchy.
- Query params are appended after `?` and are fully additive/optional.

### 2.2 Region (city) slugs — path-based routing
The region is a **first-class URL segment**. Selecting a city rewrites the path root.

| Region | URL slug | Notes |
|--------|----------|-------|
| Moscow | `/moskva` | Russian transliteration, NOT `moscow`. `/moscow` does not resolve to the region page. |
| St. Petersburg | `/sankt-peterburg` | |
| Novosibirsk | `/novosibirsk` | |
| All Russia | `/all` | Special aggregate root: `https://www.avito.ru/all`. |
| Other city | typed into city picker → resolves to its slug | |

- **City selector** lives in the header left (a clickable region label). Picking a different city navigates the **whole path** to the new region slug, preserving query params, and re-runs the listing for that region. *(Verified via blog "в левом верхнем углу нажмите на название вашего города".)*
- Region is **not** a query param (`?region=...` is not how the public site routes), so changing city is a path change, not just a param toggle.

### 2.3 Category path
Category is also path-segmented and is **required** for a meaningful listing. Verified examples:
- `avito.ru/moskva/avtomobili` — cars
- `avito.ru/moskva/kvartiry/sdam/na_dlitelnyy_srok` — apartments → rent → long-term
- `avito.ru/moskva/elektrohnika` etc.

> **Gotcha (verified by scraper docs):** "категория и регион у Авито зашиты в путь, а не в параметры". For N cities you need N base URLs — there is no single `?city=` switch that keeps the same root.

### 2.4 Query-parameter vocabulary
All verified against ≥2 scraper/integrator sources:

| Param | Example | Meaning |
|-------|---------|---------|
| `q` | `q=iphone` | Search query text (keywords). Verified present in live URLs. |
| `pmin` | `pmin=30000` | Minimum price (RUB). |
| `pmax` | `pmax=55000` | Maximum price (RUB). |
| `rooms` | `rooms=1,2` | Multi-select room count, comma-joined. Real estate only. |
| `cd` | `cd=1` | "Только с фото" — only ads with photos. (1 = on.) |
| `p` | `p=1` | Page number, **1-based**. |
| `s` | `s=104` | Sort code (numeric). Only `s=104` (=date) confirmed in this session; others in §6. |
| `sids` | `sids=3,4` | Selected checkbox filter IDs, comma-joined (used for arbitrary category attributes). |
| `geo` | (inferred) | Additional geo refinement; region itself stays in path. |

### 2.5 State preservation across navigation
- All applied filters + sort + page are **encoded in the URL** and survive refresh, share, and Back/Forward.
- Avito uses **history.pushState** (SPA): changing a filter updates the URL without a full reload; the results list re-requests server-side and re-renders. Back/Forward pops rehydrate the prior URL state and re-fetches.
- Pagination preserves every other param: `/moskva/avtomobili?p=2&q=toyota&s=104&pmin=200000&p=...`.

---

## 3. Search entry points & query input (all verified locations)

| Location | Behavior |
|----------|----------|
| **Homepage hero** (`/` and `/all`) | Central, prominent search input. On focus/open it reveals the input field; suggestions dropdown appears below. *(Verified: blank shell HTML only — actual hero rendered by JS after load.)* |
| **Header (always-visible)** | A compact search field in the top bar (described in guides as "в шапке страницы, белое поле с лупой"). Present on every page. Clicking it opens the same suggestion panel. |
| **Category page** | The header search still works; additionally category pages show category-scoped filters in a left/collapsible panel. |
| **Ad detail page** | Header search bar remains available for a brand-new search. No "search within this ad". |
| **Mobile app** | Search icon (magnifier) at bottom of screen, or top input on scroll-up. |

**Input mechanics (from UX guides):**
- Suggestions appear **as you type** (debounced, ~2–3 chars).
- Query may include: plain keywords, `"exact phrase"` (double quotes), and minus-words (`ноутбук -чехол -зарядка`).
- Pressing Enter (or the magnifier) navigates to the listing URL built from the **current region + current category (or auto-detected)** with `?q=<query>`.

---

## 4. Autocomplete / suggestions (verified behavior)

- **When:** appears immediately on focus (recent searches + popular queries) and live from ~2–3 characters typed.
- **Suggestion types observed in official Avito engineering write-ups:**
  1. **Auto-detected category + model** — "пока человек набирает «Купить айфон», мы подсказываем категорию и конкретные модели"; on submit the user lands in `Электроника → Мобильные телефоны → Apple`. *(This is the strongest verified detail.)*
  2. **Popular / trending queries** ("поисковые подсказки" — the queries buyers actually type; used by sellers to optimize titles).
  3. **Recent searches** — surfaced on focus; clicking one re-runs that search.
  4. **Category nodes** — navigable to a category page even without a query.
- **Selecting a suggestion** navigates to `avito.ru/<region>/<category>?q=<term>` (if a category/model is implied) or directly to the category page (if a category node was chosen). The chosen term becomes `q=`.
- **Empty/repeat query:** focusing the empty input shows recent searches + popular categories; re-submitting the same term re-runs the identical search and resets to page 1 (sort/filter state preserved).

---

## 5. Filter behavior

### 5.1 Filters are a panel, not an inline form
On listing pages a **"Фильтры" / "Параметры"** panel (left column on desktop; collapsible accordion on mobile) exposes filters. *(Verified: "нажмите кнопку «Фильтры» или «Параметры»".)*

### 5.2 Filter types & URL encoding

| Filter | UI control | URL encoding |
|--------|-----------|--------------|
| Price range | Two-number input or slider | `pmin`, `pmax` |
| City/region | Header selector (rewrites path) | Path root (see §2.2) |
| Category | Sidebar/tree or auto-detected from query | Path segments (see §2.3) |
| **Multi-select** (rooms, brands, params, conditions) | Checkboxes | `rooms=1,2`; `sids=3,4` |
| **Single-select** (delivery, owner type, condition tier, ad type: продам/сдам) | Radio / single dropdown | discrete param or `sids` single |
| "Only with photo" | Checkbox | `cd=1` |

### 5.3 Apply model: **mixed (auto-apply for most, explicit for heavy filters)**
- **Light filters** (price fields, checkboxes that map to query params) **update the URL as-you-change** (no explicit "Apply"), and the list re-fetches on change.
- A dedicated **"Фильтры" button/panel** opens an expanded modal with *additional* constraints (delivery, condition, seller type, etc.). This panel has the heavyweight toggles and an explicit **apply step** — closing/applying persists the set into the URL params (`sids=...`).
- Evidence: the Dzen guide says "Когда вы ввели запрос, нажмите кнопку «Фильтры» или «Параметры»" — the panel is where the deep filters live; the basic price/photo filters are usable inline.

### 5.4 Filter reset / clear
- Per-field **clear (×)** button appears on active price inputs and removes just that bound.
- A **"Сбросить"** (reset) button — located just under the search bar and inside the Filters panel — clears *all* checkboxes, price bounds, and attribute filters at once. *(MEDIUM: from UX guides.)*
- After reset, results reload with only region+category+query retained; sort returns to default (see §6).

---

## 6. Sorting (the `s=` numeric codes)

### 6.1 Sort options exposed in the UI dropdown
Four canonical options (consistent across user guides and the public sort interface):
1. **По дате** — newest first *(sort by publication/update time)*
2. **По цене** — ascending (cheapest first)
3. **По убыванию цены** — descending (most expensive first)
4. **По релевантности** — best match first

### 6.2 Default sort
- **Default = "По дате" (newest first)** augmented by promotion. The iXBT forum confirms: "сортировка 'по умолчанию' и есть сортировка 'по дате', плюс закинутые вверх продвигаемые объявления". So the default is a date-ordered feed with paid/boosted placements interleaved near the top.
- Changing sort writes the `s=` code into the URL; clearing it (or resetting) returns to this date-plus-promotion default.

### 6.3 URL encoding — `s=<numeric code>`
Sorting is encoded as the numeric query param **`s`**, *not* `sort=`. Only one code is directly confirmed in this session:

| `s=` code | Verified meaning | Source confidence |
|-----------|------------------|-------------------|
| `104` | По дате публикации / newest first | **VERIFIED** — multiple scraper docs & a live forum URL showing `?q=…&s=104` after choosing "по дате". |

The remaining codes are reported by the Avito scraper community (MEDIUM confidence — could not fetch a live mapping in this session due to 429s):

| `s=` code | Putative meaning | Confidence |
|-----------|------------------|------------|
| `1` | По релевантности / relevance | MEDIUM |
| `101` | (undocumented in sources seen) — *not* asserted | LOW |
| `10` | (reported variant of date sort) — treated as unreliable without corroboration | LOW |

> **Actionable note for adaptation:** Do **not** assume an `s=` ↔ option mapping beyond `s=104`. Before shipping, scrape the live dropdown (or hit Avito's suggestion/search endpoints) to capture the exact current code table — Avito rotates these and even the scraper community disagrees on `101/102/105/106` vs `1/10`. The brief's `?sort=10, ?sort=1` does not match Avito's `s=` scheme; treat the brief's hypothesis as **disproven** by the evidence.

---

## 7. Search history

- **Recent searches** are surfaced when the user focuses the (empty) search input — same panel as autocomplete. *(MEDIUM: inferred from "откройте строку поиска (нажмите на неё, не вводя текст)" + UX guides.)*
- Selecting a recent search re-runs it (navigates to the listing URL with that `q=`, preserving current region/category).
- **Save search ("Сохранить поиск"):** after applying filters, a "Сохранить поиск" button (under filters / near results) lets a logged-in user name and persist the query+filter set; Avito then offers notification cadences (instant / daily / weekly). *(VERIFIED button exists; cadence flow from Dzen guide.)*
- Unsaved filter state is **session-scoped** (lost on tab close) unless explicitly saved; it is *not* automatically tied to the cookie beyond the open tab.
- **Repeat query:** typing the same term again re-runs search; no special "did you mean" rewrite is shown for exact repeats, and the existing filter/sorter state is retained.

---

## 8. Clear / reset behavior

| Action | Effect | URL effect |
|--------|--------|------------|
| Clear (×) on price field | Removes only that bound | drops `pmin`/`pmax` |
| Reset filter button ("Сбросить") | Clears all checkboxes, price, photo-only, delivery, etc. | URL reverts to region+category+query; `s=` (sort) drops to default; `p=1`. |
| Clearing the search query | Removes `q=`; the page becomes a plain category listing under the current region+category. | `?q=` is removed; path stays. |
| After reset, does it return to pre-search state? | **No** — it returns to *region+category+query* defaults, not the homepage. There is no "go back to homepage" via the clear button. | Path root (region/category) is always preserved. |

---

## 9. Language & localization (verified — this is distinctive)

- **There is NO built-in language switcher on Avito.** As of the Avito blog (2025): "По состоянию на 2025 год официальной функции смены языка интерфейса… Авито не предоставляет. Интерфейс по умолчанию — русский язык." *(VERIFIED.)*
- The only language of the UI (menus, buttons, filters, placeholders) is **Russian**.
- City and category names appear in Russian in the UI, but the **URL slugs are transliterated to Latin kebab-case** (`/moskva`, `/sankt-peterburg`, `/avtomobili`, `/na_dlitelnyy_srok`).
- Users rely on **browser auto-translate** (Chrome/Edge) for non-Russian readers; Avito itself offers no `?lang=`/`/en/` path. Ad text *can* be authored in any language by sellers, but the platform UI does not localize.
- Implication for Mko Bazuna: if a localized UI is required, Avito is a poor reference (it's RU-only); OLX-style international sites are the better analog for i18n.

---

## 10. Ranking & result quality (context, not UI)

Verified from Avito's own engineering blog (Habr `habr.com/ru/companies/avito/articles/846832`) and the 2026 Ranker-3 write-up:
- **Phase 1 — candidate selection:** reverse index over 230M+ ads; hard filter on category + region + exact keyword match.
- **Phase 2 — L1 ranking:** top-500 by relevance + predicted CTR + freshness.
- **Phase 3 — L2 ranking:** top-50 from those 500, with heavier per-user personalization (history, geo, price prefs, favorite categories) + seller reputation + ad quality.
- **Default order is *not* purely chronological** — paid/boosted ("продвигаемые") placements are inserted near the top, so "По дате" + boost can interleave. Empty results are backfilled via **semantic vector search** ("Похоже на то, что вы…") and cross-city suggestions ("N объявлений есть в других городах").
- **Ads per page = 50**; anonymous users hit a login/captcha wall beyond a shallow page depth.

---

## 11. Required user-journey scenarios

Conventions: `UA` = user action, `UI` = what the user sees, `URL` = address change, `STATE` = resulting filter/sort/page.

---

### Scenario 1 — Homepage → enter search query → search results

1. **UA:** User opens `https://www.avito.ru/` (or `/all`). Sees the white header search field with a magnifier icon.
   **UI:** Header search focused; empty suggestion panel shows recent searches + popular categories. No results grid yet (or homepage recommendations).
   **URL:** `https://www.avito.ru/` (region-less root → typically redirects to the user's geo-detected region or `/all`).
   **STATE:** No query, no filters, sort=undefined (will resolve to default once a listing is requested).
2. **UA:** User types `iphone 15` and presses Enter (or clicks the magnifier).
   **UI:** Autocomplete offered category/model suggestions ("Электроника → Мобильные телефоны → Apple") as the user typed; on submit these are *auto-detected*.
   **URL:** `https://www.avito.ru/<region>/elektrohnika/telefony/mobilnye_telefony?...`
   → actually `https://www.avito.ru/<geo-default>/?q=iphone+15` then server redirects/refines to `…/elektrohnika/telefony/mobilnye_telefony?...`. *(The category is inferred from the query text.)*
   **STATE:** `q=iphone+15`; region = geo-default; category auto-set to phones; sort=default (date+boost); `p=1`.
3. **UI:** Results grid (50 cards), price badge, photo count, seller info; a "Filters" button above the list; sort dropdown showing "По дате" selected.
   **STATE:** Active filters = none beyond inferred category; pagination controls show 50/page with numbered links preserving `q=`, category, and region.

---

### Scenario 2 — Homepage → select category/filters → enter search query → results

1. **UA:** From the header, user clicks a top-level category link (e.g., **Автомобили**).
   **UI:** Nav drawer/tree or megamenu opens; user picks "Автомобили".
   **URL:** `https://www.avito.ru/<region>/avtomobili` (region auto-resolved; category now in path).
   **STATE:** category=avtomobili; `q` unset; filters default.
2. **UA:** User opens the **Фильтры** panel, sets `pmin=200000`, `pmax=450000`, checks "Только с фото", selects a brand via checkboxes.
   **UI:** Panel shows inputs/checkboxes ticking; "Сбросить" visible.
   **URL:** params added incrementally (auto-apply for light filters, or applied on close): `…/avtomobili?pmin=200000&pmax=450000&cd=1&sids=<brandId>`. *(Sort stays default until changed.)*
   **STATE:** price range + photo-only + brand filter active; `p=1`.
3. **UA:** User types `bmw` in the now-category-scoped header search and presses Enter.
   **UI:** Query applied within the already-browsing category; results list refreshes.
   **URL:** `…/avtomobili?q=bmw&pmin=200000&pmax=450000&cd=1&sids=<brandId>`.
   **STATE:** query + all prior filters + category retained; `p=1`.

---

### Scenario 3 — Homepage → enter query → apply filters → results

1. **UA:** User enters `смартфон` at the homepage/header search and submits.
   **URL:** `https://www.avito.ru/<region>/?q=смартфон` → redirected to `…/elektrohnika/telefony/mobilnye_telefony?q=смартфон`.
   **STATE:** `q=смартфон`; category auto-detected to phones; default sort.
2. **UI:** Results shown; an active-filter chip strip shows `q=смартфон` and the category breadcrumb; a **"Фильтры"** button is prominent.
3. **UA:** User clicks **Фильтры**, opens the expanded panel, and toggles price range `pmin=10000&pmax=30000` and "Только с фото" (`cd=1`). Closes/apply.
   **URL:** `…/mobilnye_telefony?q=смартфон&pmin=10000&pmax=30000&cd=1`.
   **STATE:** query preserved + price + photo-only; page resets to `p=1`; sort still default.

---

### Scenario 4 — Category page → enter search query → results

1. **UA:** User navigates directly to `https://www.avito.ru/moskva/knigi_i_zhurnaly` (books category, city=Moscow).
   **URL:** `…/moskva/knigi_i_zhurnaly`.
   **STATE:** region=moskva; category=books; `q` unset.
2. **UA:** User types `война и мир` into the header search and submits.
   **UI:** Query is applied within the books category; autocomplete may also suggest "Книги" as the category.
   **URL:** `…/moskva/knigi_i_zhurnaly?q=война+мир`.
   **STATE:** `q=война+мир` added; region+category preserved; list re-fetches.

---

### Scenario 5 — Category page → apply filters → results (no text query)

1. **UA:** User is on `https://www.avito.ru/moskva/avtomobili`, opens **Фильтры**, and selects: price `pmin=2000000&pmax=5000000`, year range, "с пробегом" (used), manual transmission, city districts (checkbox → `sids=`).
   **URL:** `…/moskva/avtomobili?pmin=2000000&pmax=5000000&sids=<yearId>,<bodyId>,…`.
   **STATE:** no `q`; attribute filters encoded in `sids`/`pmin`/`pmax`.
2. **UA:** Applies/closes the panel.
   **URL:** same as above; page reset to `p=1`.
   **STATE:** filters active, results narrowed; the breadcrumb/selected-filters bar shows each active constraint with an individual × to drop it (each × updates the URL and re-fetches).

---

### Scenario 6 — Ad detail page → initiate a new search → results

1. **UA:** User is viewing a single ad at `https://www.avito.ru/.../.../avtomobili/toyota_camry_..._12345678` (region+category path still present in the URL).
   **UI:** The header (with the search field) is always visible at top. No search box *inside* the ad card itself.
2. **UA:** User clicks the header search field and types `honda`.
   **UI:** Autocomplete dropdown appears (recent searches, popular queries, category/model suggestions).
3. **UA:** Presses Enter.
   **URL:** `https://www.avito.ru/<region-from-detail>/avtomobili?q=honda` — region is taken from the ad's region (path root) and category from the ad's category (path segments), then `q=honda` is appended.
   **STATE:** Fresh search scoped to the ad's region+category; all previously-viewed ad's filters are *not* carried (a clean listing query), sort=default, `p=1`.

---

## 12. Additional interaction states (cross-journey)

### 12.1 Sorting selection & URL encoding (canonical interaction)
- **UA:** On any results page, user opens the sort dropdown (e.g., "Сортировать по: По дате ↓") → selects **"По цене"** (cheapest first).
- **UI:** Dropdown closes; results re-order. Active sort label updates.
- **URL:** `…?s=<priceAscCode>&…` appended/updated. *(The exact asc code is not confirmed in this session; the *mechanism* — `s=` numeric param — is verified.)*
- **STATE:** sort changed; page resets to `p=1` (typical SPA reset-on-sort-change); query+region+category+other filters preserved.
- **Default:** clicking "Сбросить" or clearing `s=` returns to default = newest-first with boosted ads, as in §6.2.

### 12.2 City selection behavior
- **UA:** Click region label in header → city modal opens (or a typed field). Type `Казань`.
- **UI:** Autocomplete suggests cities; user picks "Казань".
- **URL:** path root rewrites from `/moskva/...` → `/kazan/...` (region slug for Kazan is `kazan`). Query params (q, pmin, pmax, s, sids) are **preserved**; `p` resets to `1`.
- **STATE:** identical filters/sort, but results scoped to the new region only. Breadcrumb now shows Казань.
- **Cross-region caveat:** switching to "Вся Россия" / `/all` changes result semantics (national search) and typically resets category-specific local filters.

### 12.3 Search history interaction
- **UA:** Focus empty header search on any page.
- **UI:** Dropdown lists recent (in-session) searches + popular categories; hovering a recent query highlights it; clicking navigates to that search URL (region+category inferred at click time).
- **UA:** For a previously-saved search, the saved searches appear under a dedicated "Мои поиски" / saved-searches section (logged-in users). *(MEDIUM.)*
- **UA:** Clear/recent-dismiss: a small × on a recent-search row removes it from the list (UI-only; does not affect saved searches).

### 12.4 Autocomplete suggestion types & selection outcomes
| Suggestion type | Trigger | Selecting it does |
|-----------------|---------|-------------------|
| **Category + model** (e.g., phones → Apple) | typing `купить айфон` | Navigates to `…/elektrohnika/telefony/mobilnye_telefony?...` with model hinted. |
| **Popular / trending query** | focus or early typing | Becomes `q=<term>`. |
| **Recent search** | focus on empty input | Re-runs that search (preserves region/category). |
| **Category node** | typing a category keyword (e.g., `авто`) | Navigates to the category page *without* a `q=` (full category feed). |

---

## 13. Avito-specific UX patterns most worth emulating (and the one to drop)

| Avito pattern | Why it matters / adaptation note |
|---------------|----------------------------------|
| **City + category in the URL path** (`/moskva/avtomobili`) | State is shareable & SEO-friendly at the path level, not buried in query params. Emulate this — makes filtering "deep linkable". |
| **`s=<code>` for sort** | Compact, stable across sessions. Our site could use `?sort=date` or `&s=`, but Avito's pure-numeric code is opaque to users — prefer readable `sort=` values. *(Do NOT copy `s=104` literally without the mapping table.)* |
| **Filters as additive query params** (`pmin`, `pmax`, `rooms`, `cd`, `sids`) | Bookmarkable + back-button friendly. Emulate: every filter → URL, every URL → filters. |
| **Auto-apply light filters + explicit "Фильтры" panel for deep ones** | Fast for price/photo; avoids modal fatigue. Good split. |
| **50 results/page, shallow anon pagination** | Sets realistic expectations; we may allow deeper paging. |
| **Three-level ML ranking (Ranker 3)** | Explains why "По дате" is not strictly chronological. Worth communicating to sellers/users. |
| **Minus-words + phrase quotes in `q=`** | Powerful, documented. Emulate if full-text ranking exists. |
| **No language switcher (RU-only)** | ⚠️ **Drop this.** Avito's ru-only UI is a limitation, not a feature. Mko Bazuna supports `ru`/`en`/`bs` — keep the switcher. |

---

## 14. Evidence index (sources consulted)

1. Avito homepage HTML (fetched 2026-08-29) — confirmed React SPA, `window.appStorage`, `data-rh`/i18n locale `ru_RU`, assets on `avito.st`. *(Direct fetch.)*
2. kalinkindev.ru "Парсер объявлений Авито по фильтрам на Selenium" (2026-07-21) — verified `pmin`/`pmax`/`rooms`/`cd=1`/`s=104`/`p=1`, city+category in path, 50/page, anon pagination cap.
3. Avito engineering blog, Habr `habr.com/ru/companies/avito/articles/846832` (2024-09-30) — three-level ranking pipeline, L1→500, L2→50, CatBoost, 230M+ ads.
4. Avito Dzen guide "Как работает поиск на Авито" (Антон Сапченко, 2026-07-02) — UI copy: "Фильтры"/"Параметры", "Сбросить", "Сохранить поиск", search-bar location, minus-words/quotes.
5. iXBT forum "AVITO - развод продавцов" — `s=104` after selecting "по дате"; date+boost default semantics.
6. Avito developer catalog `developers.avito.ru/api-catalog` + `avito.ru/legal/pro_tools/public-api` — public API exists; search endpoints use numeric `categoryId`/`locationId` (different from public web `s=`).
7. `m.avito.ru/api/9/items` params (Apify/avito-python references) — `priceMin`/`priceMax`/`sort=relevance|newest|cheapest|expensive` (API names differ from web `s=` codes; do not conflate).
8. Avito Help/blog (Сuetolog, Dzen 2024-10-23) — city selector in header, "change region in header or app".
9. Avito language note (Dzen "Как изменить язык интерфейса на Авито", 2025-12-11) — no built-in language switcher; RU-only UI; relies on browser translate.

> Where a live page could not be fetched (429), a claim is tagged MEDIUM/LOW and the supporting non-live source is cited in this index.

---

*End of research document.*
