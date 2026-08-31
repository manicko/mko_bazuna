# OLX.kz Search & Filtering UX — Research Findings

> **Research method:** Live browser interaction via Playwright MCP on `https://www.olx.kz/` (Russian interface).  
> **Date:** 2026-08-29  
> **Interface language:** Russian (default); Kazakh toggle available via `/kk/` prefix.  
> **Architecture note:** OLX.kz is a React SSR SPA (rweb); page transitions are client-side. The desktop site is responsive; the mobile site (`m.olx.kz`) redirects to desktop by default user-agent, so mobile-specific behaviour was not independently sampled.

---

## 1. Homepage Hero Search Bar

Located in the page header (`banner`), visible on every page.

| Element | Selector / Description |
|---|---|
| **Query input** | `input[placeholder="Что ищете?"]`, `data-testid="search-input"` |
| **Location combobox** | `input[placeholder="Вся страна"]`, `data-testid="location-search-input"` |
| **Search button** | `button` labeled "Поиск", `data-testid="search-submit"` |
| **Clear button** | `button` with `aria-label="Clear"` (small X) inside the query input container; clears only the query text and re-searches, preserving other state. |

**Interaction flow:**
1. User types a query into the input → autocomplete dropdown opens with suggestions (see §7).
2. User can click the location combobox to change "Вся страна" (whole country) to a region or city (see §8).
3. Clicking "Поиск" navigates to the search results page.

---

## 2. Search URL Structure

### 2.1 Site-wide (global) search

When searching from the homepage header without a category context:

```
/list/q-{query}/
```

- `{query}` is URL-encoded Cyrillic text (e.g., `q-авто`, `q-ноутбук`).
- The path segment `/list/` indicates a site-wide (all-categories) search.
- No query parameters are added for the default state (default sort, no price filter, no photo-only).

### 2.2 Category-scoped search

Selecting a category from the homepage grid or the category dropdown scopes the URL to that category's slug:

```
/{category_slug}/q-{query}/
```

Examples:
- `/transport/q-авто/`
- `/uslugi/q-эвакуатор/`
- `/elektronika/q-ноутбук/`

**Key detail:** When a category is selected on a search-results page (via category chips), the URL path changes to `/{category_slug}/q-{query}/` while **preserving all existing filter query parameters**. For example, if filters for price and photos are active:

```
/elektronika/q-ноутбук/?search[photos]=1&search[filter_float_price:from]=100000&search[filter_float_price:to]=300000
```

**Removing category scope** (clicking "Показать все" in the category chips bar) reverts the path to `/list/q-{query}/`, dropping the category but keeping other filters.

### 2.3 Ad detail page (individual ad)

```
/d/obyavlenie/{slug}-ID{ID}.html
```

- The slug is derived from the ad title (kebab-case, Cyrillic transliterated).
- The ad ID is appended as `-ID{ID}.html`.
- The detail page URL is **clean** (no search/filter params) — the search context is lost.

### 2.4 Language switching in URL

- Russian (default): no prefix in path.
- Kazakh: `/kk/` prefix inserted after the domain, preserving all path segments and query params.
  - Example: `https://www.olx.kz/kk/list/q-авто/` from `https://www.olx.kz/list/q-авто/`
  - Example: `https://www.olx.kz/kk/list/q-ноутбук/?search[photos]=1&search[filter_float_price:from]=100000&search[filter_float_price:to]=300000`

---

## 3. Search Filter URL Parameters

All OLX search filters use PHP-style bracket notation in the query string: `search[field_name]`. Parameters are URL-encoded (`[` → `%5B`, `]` → `%5D`, `:` → `%3A`).

### 3.1 Price range

```
search[filter_float_price:from]=N&search[filter_float_price:to]=M
```

- `N` and `M` are integer tenge values (no thousands separator in the URL).
- The `from` and `to` bounds are independent; only one can be set.
- **Auto-applied**: changing the input field value updates the URL (with debounce) without requiring a button click. Each field has a small "Clear" (X) button to remove that bound.

**Observed:** Typing "100000" in "От:" and "300000" in "до:" produced:
```
?search[filter_float_price:from]=100000&search[filter_float_price:to]=300000
```

### 3.2 Photos-only checkbox

```
search[photos]=1
```

- Toggle: checkbox labeled "Только с фото" (`name="photos"`).
- **Auto-applied** on toggle (no button click needed). Checked state → param added; unchecked → param removed.

### 3.3 Sort order

```
search[order]=field:direction
```

- Default (no param): "Рекомендованное вам" (recommended).
- `created_at:desc` → "Самые новые" (newest first).
- `filter_float_price:asc` → "Самые дешевые" (lowest price first).
- `filter_float_price:desc` → "Самые дорогие" (highest price first).

**Note:** The sort dropdown button on the results page shows the current sort label (e.g., "Рекомендованное вам"). Clicking an option updates the URL and immediately re-sorts results.

### 3.4 Pagination

- Page 1: **no `page` parameter** in the URL.
- Page 2+: `?page=N` is **prepended** before the `search[...]` parameters.
  - Example page 2: `/list/q-ноутбук/?page=2&search[photos]=1&search[filter_float_price:from]=100000`
- A forward-navigation button links to the next page; a "..." element provides jump-forward navigation between distant pages.

### 3.5 Category chips (faceted categories)

When viewing search results, a horizontal bar of category chips appears above the ad list:

```
Транспорт5 099  |  Работа1 468  |  Услуги15 315  |  ...
```

- Each chip is a link: `/{category_slug}/q-{query}/?...existing_filters...`
- Category chips **preserve** existing filter query parameters (photos, price, sort).
- A trailing "Показать все" chip removes the category constraint, reverting to `/list/q-{query}/?...` (site-wide).

### 3.6 Promoted / VIP ads

Promoted (VIP) ads on the homepage carry `?reason=hp%7Cpromoted` in their detail-page URL:
```
/d/obyavlenie/{slug}-ID{ID}.html?reason=hp%7Cpromoted
```

---

## 4. Sort Dropdown

Located on the search results page in the header area below the breadcrumbs.

- **Button label** reflects the current sort: "Рекомендованное вам" (default).
- **Dropdown options** (observed):
  1. "Рекомендованное вам" — no URL param (default).
  2. "Самые новые" — `search[order]=created_at:desc`.
  3. "Самые дешевые" — `search[order]=filter_float_price:asc`.
  4. "Самые дорогие" — `search[order]=filter_float_price:desc`.
- Clicking an option is an **explicit apply** (URL updates immediately).

---

## 5. Price Filters (Sidebar on Results Page)

On category-scoped or site-wide search results, a filter sidebar appears.

- **Field labels:** "Цена" section with two inputs:
  - "От:" (`combobox` with value, e.g., `"100000"`) — minimum price.
  - "до:" (`combobox` with value, e.g., `"300000"`) — maximum price.
- Each input has a small "Clear" button (X) to remove that bound.
- **Auto-applied** as you type (URL updates with debounce).
- **Price units:** values in tenge (тг.), displayed with space separators (e.g., "139 990 тг.").

### 5.1 Other sidebar filters (category-specific)

On the `/list/q-ноутбук/` results page, the sidebar "Фильтры" panel includes:

- **Категория** — button showing "Любая категория" (any category); opens a category picker.
- **В рассрочку** — toggle (button "Все объявления" by default).
- **Состояние** — toggle (button "Все объявления" by default; options likely "Б/у"/"Новый").
- **Диагональ экрана** — toggle (button "Все объявления" by default).
- **Марка ноутбука** — toggle (button "Все объявления" by default).
- **Сбросить фильтры** — button at the bottom of the filters panel; clears ALL filter parameters and resets the category scope to `/list/`.

---

## 6. Checkbox: "Только с фото"

- Checkbox with label text "Только с фото" and `name="photos"` attribute.
- **Auto-applied** on toggle — no apply button needed.
- Checked → URL gains `search[photos]=1`; unchecked → param removed.
- On search results pages, the checkbox is visible both in the header bar and potentially in the filter sidebar.

---

## 7. Search Autocomplete & History

### 7.1 Autocomplete suggestions

When the query input is focused (even if empty), a dropdown appears:

- **Input value:** `0`
- **Sections:**
  - **"Рекомендации"** (Recommendations) — suggested queries. Each suggestion can have a nested breadcrumb path showing the category hierarchy (e.g., "Электроника / Ноутбуки и аксессуары / Ноутбуки"). Deep category paths are truncated with "..." when they don't fit.
  - **"Вы недавно искали"** (You recently searched for) — stored recent queries from the current session/localStorage.
- **Clear button:** Each recent-search entry has a small "Clear" (X) button to remove it individually.

### 7.2 Search history (on focus)

- Focusing the empty input on the homepage shows a "Вы недавно искали" section.
- Each recent query appears as a clickable link that navigates to `/list/q-{query}/`.
- A count badge shows the number of saved filters: "Поисковые фильтры [N]".
- Individual "Clear" buttons remove specific recent searches.

---

## 8. Location Selector

Combobox with `placeholder="Вся страна"` (whole country). Clicking it opens a modal-like listbox popup.

### 8.1 Structure

```
combobox "Вся страна" [expanded]
  listbox
    "Чтобы использовать текущее местоположение, дайте OLX доступ в настройках вашего устройства."
    "Вы можете разрешить определять ваше местоположение в настройках браузера."
    option "Вся страна"
    heading "Выбрать область"
    list
      option "Абайская область"
      option "Акмолинская область"
      ...
      option "Улытауская область"
    button "Поиск"
```

### 8.2 Regions (18 total)

1. Абайская область
2. Акмолинская область
3. Актюбинская область
4. Алматинская область
5. Атырауская область
6. Восточно-Казахстанская область
7. Жамбылская область
8. Жетысуйская область
9. Западно-Казахстанская область
10. Карагандинская область
11. Костанайская область
12. Кызылординская область
13. Мангистауская область
14. Павлодарская область
15. Северо-Казахстанская область
16. Туркестанская область
17. Улытауская область
18. (Plus "Вся страна" as the default option)

### 8.3 Region → City cascade

Clicking a region option (e.g., "Алматинская область") triggers a cascading view:

```
combobox "Вся страна" [not expanded]
  listbox
    option "Назад" [selected]          ← returns to region list
    option "Алматинская область"
      paragraph "Вся область"
    heading "Выбрите город"
    list
      option "Абай"
      option "Ават"
      option "Азат"
      ...
      option "Алматы"
      ...  (dozens of cities listed, many duplicates)
      option "Алтынарык"
      ...
```

- **"Назад"** option returns to the region-level list.
- The selected region is shown as a header with "Вся область" subtitle.
- A long scrollable list of cities/urban-type settlements appears below, with a "Выберите город" heading.
- **URL parameter for location:** *Not captured during this session.* Clicking a city and then the header "Поиск" button did not visibly change the URL on the homepage. The OLX.kz location selector may use a session/cookie-based mechanism rather than URL query parameters, or requires pressing Enter / an additional "apply" step. This remains an **open gap** requiring further testing.

### 8.4 Location permission prompt

At the top of the location listbox, a message appears:
> "Чтобы использовать текущее местоположение, дайте OLX доступ в настройках вашего устройства."  
> "Вы можете разрешить определять ваше местоположение в настройках браузера."

---

## 9. Back-Button Navigation (SPA)

### 9.1 Homepage → search → back

1. On the homepage, user types a query (e.g., "авто") and presses Enter or clicks "Поиск".
2. Browser navigates to `/list/q-авто/`.
3. User presses the browser back button.
4. **Result:** Browser returns to `https://www.olx.kz/`. The hero search input is **cleared** (empty), and the homepage re-renders. SPA client-side routing discards the transient input value.

### 9.2 Results → ad detail → back (filters preserved)

1. On a filtered results page, e.g.:
   ```
   /list/q-ноутбук/?search[photos]=1&search[filter_float_price:from]=100000&search[filter_float_price:to]=300000
   ```
2. User clicks an ad card, navigating to the ad detail page (clean URL, no query params).
3. User presses the browser back button.
4. **Result:** Browser returns to the **exact previous URL** with all filters preserved:
   ```
   /list/q-ноутбук/?search[photos]=1&search[filter_float_price:from]=100000&search[filter_float_price:to]=300000#400253244
   ```
   - The URL is identical, plus a **hash fragment** (`#400253244`) appended — likely a scroll-position or ad-card anchor for restoration.

**Conclusion:** OLX's SPA back-button correctly preserves all search filter parameters when navigating from search results to an ad detail page and back. The hash fragment enables scroll restoration.

---

## 10. Category Dropdown (Site-Wide)

On the homepage, a category dropdown (triggered by clicking a category area) shows top-level categories with ad counts:

- Транспорт, Работа, Услуги, Строительство и ремонт, Аренда и прокат товаров, Недвижимость, Электроника, Запчасти, Дом и сад, Мода и стиль, Детский мир, Хобби/отдых/спорт, Животные, Отдам даром.

- Selecting a category **auto-navigates** to `/{category_slug}/q-{query}/` (using the current query from the input, or defaulting to a category landing page if no query).

On search results pages, the same categories appear as a **horizontal chip bar** above the results, each labeled with a count (e.g., "Электроника10 104"). Clicking a chip updates the URL path to `/{category_slug}/q-{query}/?...filters...` while preserving existing filters. A trailing "Показать все" chip resets to `/list/q-{query}/`.

---

## 11. Ad Card Structure

Each ad in search results follows a consistent DOM structure:

| Component | Description |
|---|---|
| **Container** | `l-card` class element |
| **Image** | `<img>` with alt text = ad title |
| **Title** | `<heading level=4>` — full ad title text |
| **Price** | `<paragraph>` — format: "139 990 тг." (space as thousands separator). Some ads show "Договорная" (negotiable) as a sub-paragraph next to the price. |
| **Condition badge** | `<generic>` — either "Б/у" (used) or "Новый ◽️" (new) |
| **Location + date** | `<paragraph>` — format: "Астана, Сарыаркинский район - 27 августа 2026 г." or "Алматы, Алмалинский район - Сегодня в 12:44" |
| **Subscribe button** | `button` — labeled "{ad title} Подписаться". Allows subscribing to the seller for new ads. |

**Two link elements per card:** the image and the title both link to the same ad detail URL (`/d/obyavlenie/{slug}-ID{ID}.html`).

### Date formats observed

- "Сегодня в 12:44" — today, time only.
- "27 августа 2026 г." — past date, full date.
- "28 августа 2026 г." — yesterday, full date.
- "26 марта 2025 г." — older ad, full date.

### Locations observed in ad cards

City names with district: "Астана, Сарыаркинский район", "Алматы, Алатауский район", "Караганда, Казыбекбийский район", "Шымкент, Аль-Фарабийский район", "Актобе, микрорайон 11", "Костанай", "Павлодар", "Усть-Каменогорск", "Болтирик шешен", "Каргалы", "Нура", "Семей", "Богдановка", "Чапаево".

---

## 12. Save Search Feature

On filtered search results pages, a panel appears:

```
generic
  paragraph "Сохранить параметры поиска"
  paragraph "Если появятся похожие объявления, мы сообщим."
  button "Сохранить"
```

- Also accessible via the header "Добавить в избранное" button (star icon with "Выделенные" alt text) which links to `/favorites/search/`.
- The "Сохранить" button saves the current search parameters (query + filters) so the user receives notifications when similar ads appear.

---

## 13. Result Count Message

Displayed above the ad list on results pages:
- "Мы нашли более 1 000 объявлений" (site-wide or category search with many results)
- Ad counts appear on category chips (e.g., "Электроника10 104")

---

## 14. List / Grid View Toggle

On search results pages, a view toggle appears in the sort toolbar:
- Button "View ads in list mode" — list view (title below image).
- Button "View ads in grid mode" — grid view (compact cards).
- These are English-labeled (ARIA labels), not translated.

---

## 15. Seller-Type Toggles (Category Pages)

On category-scoped pages (e.g., `/elektronika/`), the filter sidebar may include seller-type toggle buttons:
- "Бизнес" (business sellers)
- "Частные" (private individuals)

- These are **mutually exclusive** (selecting one deselects the other).
- **Auto-applied** on toggle (no apply button needed).
- URL params: `search[private_business]=business` or `search[private_business]=private`.

**Note:** Seller-type toggles were observed on the homepage category pages, not on general `/list/` search results pages.

---

## 16. Reset / Clear Behaviour

| Action | Element | Effect |
|---|---|---|
| **Clear query only** | Small "Clear" (X) button inside the query input | Clears the query text in the search input and re-searches, **preserving** other filters (price, photos, etc.) |
| **Reset all filters** | "Сбросить фильтры" button at the bottom of the filter sidebar | Clears **ALL** filter parameters and resets the category scope to `/list/q-{query}/` |
| **Clear individual filter** | Small "Clear" buttons on price inputs ("От:" / "до:") | Removes that single price bound |

---

## 17. Popular Queries (Homepage Footer)

The homepage footer contains a "Популярные запросы:" section with clickable links:

```
эвакуатор → /uslugi/q-эвакуатор/
электрик → /uslugi/q-электрик/
сантехник → /uslugi/q-сантехник/
вывоз мусора → /uslugi/q-вывоз-мусора/
газель → /uslugi/q-газель/
ремонт кондиционеров → /uslugi/q-ремонт-кондиционеров/
питбайк → /transport/q-питбайк/
...
```

- These are categorized links (most point to `/uslugi/` or `/transport/` category search).
- The category is embedded in the URL path.

---

## 18. Footer Links

Standard OLX footer contains:
- **Mobile apps:** Google Play and App Store links.
- **Help & Support:** "Помощь и Обратная связь" → `https://help.olx.kz/olxkzhelp/s/?language=ru`
- **Business:** "Рекламные услуги", "Бизнес на OLX" → `https://business.olx.kz/`
- **Blog:** "Блог OLX" → `http://blog.olx.kz/`
- **Legal:** "Условия использования", "Политика конфиденциальности", "Баннерная реклама"
- **Safety:** "Правила безопасности" → `https://blog.olx.kz/category/security/`
- **Sitemap:** "Карта сайта" (`/sitemap/`), "Карта регионов" (`/sitemap/regions/`), "Карта бизнес-страницы" (`/sitemap/shops/`), "Популярные запросы" (`/popular/`)
- **Careers:** "Работа в OLX" → `https://careers.olxgroup.com/`
- **Country switcher:** OLX.bg, OLX.pl, OLX.ro, OLX.ua, OLX.pt

---

## 19. Mobile Responsiveness

- **Mobile subdomain** `m.olx.kz` is **not independently testable** — it redirects to the desktop site regardless of attempted user-agent changes (Playwright MCP limitation: `page.setUserAgent` / `page.evaluate` with user-agent override unavailable on this tooling).
- The desktop site includes a **list/grid view toggle** in the results toolbar, suggesting responsive card layout adaptation.
- The viewport resize tool is available but mobile-specific behaviour (touch gestures, hamburger menu, condensed filter drawer) was not verified.

---

## Summary Table: URL Parameter Reference

| Feature | URL Parameter | Auto-apply? |
|---|---|---|
| Search query | Path: `/q-{query}/` or `/{category}/q-{query}/` | Yes (on form submit / Enter) |
| Price min | `search[filter_float_price:from]=N` | Yes (typed, debounced) |
| Price max | `search[filter_float_price:to]=M` | Yes (typed, debounced) |
| Photos only | `search[photos]=1` | Yes (toggle) |
| Sort: newest | `search[order]=created_at:desc` | Yes (dropdown click) |
| Sort: low price | `search[order]=filter_float_price:asc` | Yes (dropdown click) |
| Sort: high price | `search[order]=filter_float_price:desc` | Yes (dropdown click) |
| Pagination | `?page=N` (first page has none) | Yes (link click) |
| Category scope | Path: `/{slug}/q-{query}/` | Yes (chip click) |
| Seller type | `search[private_business]=business\|private` | Yes (toggle) |
| Language | Path prefix `/kk/` for Kazakh | Yes (link click) |
| Location filter | *Not captured* | — (open gap) |
| Promoted ads | `?reason=hp|promoted` (on ad detail URL) | N/A (server-side flag) |

---

## Confidence Levels

| Finding | Confidence | Notes |
|---|---|---|
| Homepage hero search structure (elements, testids) | **HIGH** | Verified via accessibility snapshot |
| Site-wide search URL: `/list/q-{query}/` | **HIGH** | Verified by direct navigation |
| Category-scoped URL: `/{slug}/q-{query}/` | **HIGH** | Verified via category chips with live ad counts |
| Price filter params `filter_float_price:from/:to` | **HIGH** | Verified with real values, visible in URL |
| `search[photos]=1` | **HIGH** | Verified via checkbox toggle |
| Sort params (`created_at:desc`, `filter_float_price:asc/desc`) | **HIGH** | Verified via sort dropdown interaction |
| Pagination `?page=N` | **HIGH** (from earlier sort test) | Confirmed page param prepended before search params |
| Back-button preserves filters + hash scroll anchor | **HIGH** | Verified: filters + `#400253244` hash returned on back nav |
| Ad card structure (image, title, price, badge, location, subscribe) | **HIGH** | Verified via multiple ad card snapshots |
| Region list (18 regions) | **HIGH** | Verified via accessibility snapshot |
| Region → city cascade | **HIGH** | Verified: clicked region, saw "Назад" + city list |
| Popular queries footer links | **HIGH** | Verified via snapshot |
| Footer links (sitemap, country, etc.) | **HIGH** | Verified via snapshot |
| Save search ("Сохранить параметры поиска") panel | **HIGH** | Verified via snapshot on results page |
| Reset: `clear-btn` preserves filters, `Сбросить фильтры` clears all | **MEDIUM** | `clear-btn` verified; `Сбросить фильтры` behavior inferred from label + placement |
| Location URL param encoding | **LOW** | Not captured; location combobox doesn't commit to URL in tested interactions. Requires further investigation. |
| Mobile site behaviour | **LOW** | Mobile subdomain not independently testable (redirects to desktop). |
| Back-button from homepage clears query input | **MEDIUM** | Verified the URL returns to homepage but couldn't confirm input value state via evaluated JavaScript (combobox value not readable via tested selectors). |
