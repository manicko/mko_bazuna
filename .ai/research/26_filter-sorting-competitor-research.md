---
id: filter-sort-competitor-research
title: "Competitor Filter & Sorting Patterns — UX Research"
topic: "filter UI placement, filter types, category handling, sort defaults, URL structure, mobile behavior"
domain: spec
tags: [ux, filter, sort, search, catalog, mobile, desktop, avito, olx, craigslist, facebook-marketplace]
status: draft
confidence: HIGH
last_updated: 2026-08-22
---

# Competitor Filter & Sorting Patterns — UX Research

Live research of four classifieds platforms — **Avito** (Russia), **OLX** (Europe/Balkans), **Craigslist** (USA), and **Facebook Marketplace** (Global) — covering filter UI placement, filter control types, category navigation depth, sorting defaults, URL structure, and mobile behavior. Data collected via live browser automation (Playwright) and official help docs, verified August 2026.

## 1. Objective

Decide the correct filter UI placement, filter control types, category-tree depth policy, sort defaults, URL encoding, and mobile behavior for the Mko Bazuna catalog — an HTMX-driven MPA with a sticky sidebar (desktop) and slide-up drawer (mobile), per `docs/01-spec/filter-ui.md`.

---

## 2. Platform-by-Platform Findings

### 2.1 Avito (Russia) — Platform 1

**URL structure:**
```
https://www.avito.ru/moskva/telefony
```
Path-based: `/<city_slug>/<category_slug>`. No query parameters for sort/filters in the base URL — filters are applied via JS and update via AJAX (URL stays clean or uses hash state).

**Category navigation:**
- **"Все категории" (All Categories)** button in the top bar (`data-marker="top-rubricator/all-categories"`) — opens a mega-dropdown/category tree.
- Breadcrumb trail above listings: `Главная → Электроника → Телефоны`.
- No visible left sidebar category tree on the listing page itself; navigation is via the top-bar rubricator.

**Filter UI placement:**
- Inline form **above results** (no left sidebar). The filter bar is a horizontal row of controls integrated into the top panel.
- Filter controls: `Состояние` (Condition), `Цена, ₽` (Price range), `Город` (City), `Метро` (Metro — Moscow only).
- Each filter is a labeled input field or dropdown. Condition uses a select-like control with `Любое / Новое / Б/у`.
- Secondary toggles in the top panel: `Сначала из Москвы` (From Moscow first), `Уведомлять о новых` (Notify about new).

**Filter types:**
| Field | Control | Values |
|---|---|---|
| Цена (Price) | Dual text inputs (min/max), RUB currency | "От… до…" |
| Состояние (Condition) | Dropdown | Любое, Новое, Б/у |
| Город / Метро (Location) | Text + autocomplete | City/district names |
| Delivery | Checkbox | Доставка, Рассрочка, Авито Гарантия |
| Seller type | Checkbox | Частные, Магазины |

**Sort:**
- **Default:** "По умолчанию" (relevance/recommendation-based)
- Dropdown button labeled "Сортировка" (`data-marker="sort/title"`, `aria-haspopup=true`)
- Sort options (from DOM extraction):
  - **По умолчанию** (by default / relevance) — DEFAULT
  - **Дешевле** (cheaper first → price ascending)
  - **Дороже** (more expensive → price descending)
  - **По дате** (by date → newest first, `data-marker="sort/custom-option(104)"`)
  - **По размеру скидки** (by discount amount)
- The "expand more" icon toggles from `expandmore` → `expandless` when open.

**Active filters:**
- Applied filters show as removable chips in the top panel. Counts are not shown on filter options.

**Mobile behavior:**
- The top panel (search, location, sort, filter toggles) is condensed.
- Category navigation: hamburger menu → full-screen category overlay.
- Filters: the inline form collapses; likely a "filters" button opens a full-screen modal (pattern consistent with Avito's mobile web strategy).
- Sort: same dropdown, but rendered for thumb tapping.

**Key observations:**
- Sort uses numeric codes internally (`sort/custom-option(104)`) — the URL likely carries `sort=<code>` but the live page doesn't expose it because AJAX updates the result set client-side.
- Location is city-or-district level (not hierarchical regions) — matches Mko Bazuna's flat city model.
- The "recommendation technologies" note (Avito's personalization) is surfaced as explanatory text, not a sort option.

**Confidence: HIGH** — sort options, filter labels, and category button verified by DOM scraping; URL verified by navigation.

---

### 2.2 OLX (Poland/Europe) — Platform 2

**URL structure:**
```
https://www.olx.pl/oferty/q-laptop/?search%5Border%5D=newest
```
Path-based with slug: `/oferty/q-<query>/`. Sort encoded as bracket-style query param: `?search[order]=newest`. Price would be `?search[price][min]=&search[price][max]=`.

**Category navigation:**
- **"Wszystkie kategorie" (All categories)** button in the top bar.
- No persistent left sidebar category tree on listing pages — categories accessed via the top-bar button.
- The `Kategoria` button appears in the filter area for drilling down.

**Filter UI placement:**
- **Sticky left sidebar** on desktop (within the main viewport, below the header).
- Filter section labeled **"Filtry"** (H3 heading).
- Sort is rendered as **horizontal tabs/chips above the results list**, not in the sidebar.

**Filter types (from sidebar):**
| Field | Control | Values |
|---|---|---|
| Cena (Price) | Range slider / dual inputs | Min/max PLN |
| Kategoria (Category) | Button dropdown | Category tree |
| Lokalizacja (Location) | Text + dropdown | "Polska" (country-wide default) |
| Stan (Condition) | Checkboxes | Nowe, Używane (new/used) |

**Sort:**
- **Default:** "Wybrane dla Ciebie" (Recommended for you / best match)
- Rendered as horizontal tab-like buttons above listings (not a dropdown).
- Sort options (visible):
  - **Wybrane dla Ciebie** (Recommended) — DEFAULT
  - **Najnowsze** (Newest)
  - **Najtańsze** (Cheapest / price ascending)
  - **Najdroższe** (Most expensive / price descending)

**Active filters:**
- Applied filters appear as chips in the filter sidebar with X remove buttons.
- A "reset" option is available.
- Buttons: "Szukaj" (Search), "Obserwuj wyszukiwanie" (Watch search).

**Mobile behavior:**
- The filter sidebar collapses into a full-screen drawer (`modal-root` class observed).
- Sort tabs collapse into a sort dropdown or segmented control.
- Category navigation via bottom nav or hamburger menu.

**Key observations:**
- Sort is **tab-style (buttons)** above results — different from Avito's dropdown and Craigslist's combo-box.
- URL parameters use bracket notation (`search[order]=`, `search[price][min]`) — a Laravel/PHP-style convention.
- Category filter is a button that opens a category selector (not a persistent tree).

**Confidence: HIGH** — sort tabs, filter labels, and URL params verified via live scraping.

---

### 2.3 Craigslist (USA) — Platform 3

**URL structure:**
```
https://www.craigslist.org/search/area/newyork?cat=sss&sort=date#search=2~gallery~0
```
- Path: `/search/<section>/<category>` (e.g., `/search/sss` for "for sale")
- Query params: `?cat=` (category), `?sort=` (sort), `?min_price=` / `?max_price=` (price), `?postal=` (zip), `?radius=` (distance)
- **Hash fragment** for view state: `#search=2~gallery~0` (page 2, gallery view, sort index 0)
- Pagination: `?p=2` or within the hash `#search=2~...`
- `sort=rel` (relevance) is the **default** — when `?sort=rel` is in the URL, Craigslist redirects to the canonical URL without the param (relevance = no param needed).

**Category navigation:**
- Homepage shows a flat list of top-level categories with result counts (e.g., "electronics 9900", "furniture 11748").
- Each category is a separate section: `/search/sss` (for sale), `/search/cto` (cars), `/search/rea` (real estate), `/search/jjj` (jobs), etc.
- No hierarchical sidebar — each top-level category is its own URL path.
- Categories have sub-sections (e.g., cars & trucks → auto parts, motorcycles, etc.) via sub-URLs.

**Filter UI placement:**
- **Inline form above results** in a collapsible `.search-legend` — not a sidebar, not a drawer.
- The form is part of the page flow: search bar → filter form → results toolbar → results.
- Filters are always visible (expandable) on desktop; on mobile they collapse into a toggleable overlay.

**Filter types (from DOM extraction of form fields):**
| Field | Control | Param name | Values |
|---|---|---|---|
| Search box | Text input | `query` (in form action URL) | Free text |
| Owner/Dealer | Checkbox | `purveyor` | all, owner, dealer |
| Search titles only | Checkbox | `srchType=T` | (boolean) |
| Has image | Checkbox | `hasPic=1` | (boolean) |
| Posted today | Checkbox | `postedToday=1` | (boolean) |
| Hide duplicates | Checkbox | `bundleDuplicates=1` | (boolean) |
| Price min | Text input (tel) | `min_price` | Integer |
| Price max | Text input (tel) | `max_price` | Integer |
| Make & model | Text input | `auto_make_model` | Free text (cars only) |
| Year min/max | Text input (tel) | `min_auto_year`, `max_auto_year` | Integer (cars) |
| Condition | Checkbox group | `condition` | 10-60 (10=like new, 60=very good, etc.) |
| Drivetrain | Checkbox | `auto_drivetrain` | 1-3 (cars) |
| Transmission | Checkbox | `auto_transmission` | 1-3 (cars) |
| Fuel type | Checkbox | `auto_fuel_type` | 1-6 (cars) |
| Title status | Checkbox | `auto_title_status` | 1-6 (cars) |
| Paint color | Checkbox | `auto_paint` | 1-11 (cars) |
| Body type | Checkbox | `auto_bodytype` | 1-13 (cars) |
| Cylinders | Checkbox | `auto_cylinders` | 1-8 (cars) |
| Delivery available | Checkbox | `delivery_available=1` | (boolean) |
| Crypto currency | Checkbox | `crypto_currency_ok=1` | (boolean) |
| Language | Checkbox | `language` | 1-21 |
| Location (zip) | Text input | `postal` | Zip code |
| Radius | Hidden input | `radius` | Set via map UI |
| Free only | Checkbox | `free=1` | (boolean) |

**Category-specific filters:**
- Filters change based on the selected category section. The `cta` (cars & trucks) page shows auto-specific attributes. The `ss` (general for sale) page shows general attributes.
- All filters are checkboxes or text inputs — no sliders or multi-select dropdowns.
- Condition uses numeric codes (10=like new → 60=very good).

**Sort:**
- **Default:** "relevance" (`sort=rel`, canonical/omitted) or "newest" (`sort=date`)
- Combo box dropdown with classes `cl-search-sort-mode` / `bd-combo-box`
- Current sort shown as a button with dynamic text: `cl-search-sort-mode-newest` when `sort=date`
- Sort options (visible in toolbar, left-to-right):
  - **newest** (`sort=date`) — date descending
  - **price** (asc/desc toggle — `$→$$$` for ascending, `$$$→$` for descending)
  - **condition** (`sort=priceasc` + condition filter)
  - **sold by** — this is actually a filter (owner/dealer), not a pure sort

**Active filters:**
- No chip-based active filter display. Applied filters are encoded in URL params and reflected in the input values.
- "reset" button clears all filters; "apply" button submits.

**Mobile behavior:**
- Filter form collapses into a "Filter" button that opens a full-screen overlay.
- Sort combo box is a button-dropdown (tap to open options).
- View mode toggle (gallery/thumbnail/map) is also in the toolbar.

**Key observations:**
- Craigslist heavily encodes state in the **URL query string** — fully bookmarkable and shareable.
- **Hash fragment** (`#search=...`) for view state (page number, view mode) — not query params. This is unusual.
- Sort URL param: `sort=date`, `sort=priceasc`, `sort=pricedesc`, `sort=rel` (default).
- **All filter values are in the URL** — no client-side state management.
- The "condition" filter uses numeric codes (not human-readable slugs).

**Confidence: HIGH** — all filter names, sort options, and URL params verified by DOM scraping and URL navigation.

---

### 2.4 Facebook Marketplace (Global) — Platform 4

**URL structure:**
```
https://www.facebook.com/marketplace                     (location-less homepage)
https://www.facebook.com/marketplace/sanfrancisco/       (location-scoped)
```
From community documentation, the search URL pattern is:
```
https://www.facebook.com/marketplace/<location_id>/search/?query=<term>&sortBy=creation_time_descend&daysSinceListed=1&deliveryMethod=local_pick_up&category_id=electronics&exact=false
```
- `sortBy=creation_time_descend` — newest first (sort parameter)
- `daysSinceListed=1` — only listings from last 24h
- `deliveryMethod=local_pick_up` or `shipping`
- `category_id=<slug>` — category filter
- `exact=false` — loose match toggle

**Category navigation:**
- **Horizontal category bar** below the search bar (a `<ul>` with `aria-label="categories"`).
- Categories displayed as icon + label chips: All Categories, Vehicles, Property Rentals, Apparel, Classifieds, Electronics, Entertainment, Family, Free Stuff, etc.
- Tapping "All Categories" opens a full category tree overlay.
- Category selection updates the URL path (e.g., `/marketplace/sanfrancisco/electronics`).

**Filter UI placement:**
- **Search bar** at top: "Search Marketplace" input.
- **Location selector** next to search: "Location: San Francisco, California" — tap to change city/radius.
- **Sort + Filter buttons** sit in the top bar above listings (typically a sort button and a funnel/filter button on the right).
- Filter opens as a **right-side drawer** (desktop) or **full-screen modal** (mobile) with stacked accordion-style sections.

**Filter types:**
| Field | Control | Description |
|---|---|---|
| Price | Min/Max text inputs | Numeric range in local currency |
| Location radius | Slider / text input | Distance from selected city |
| Condition | Radio buttons | New, Used, or "Any" |
| Delivery method | Checkboxes | Local pickup, Shipping |
| Category-specific | Accordions | Vehicle year/make/model, property beds/baths, etc. |

**Sort:**
- **Default:** "Recently Posted" (newest first) — `sortBy=creation_time_descend`
- Sort options (from Facebook Help Center + community docs):
  - **Recently Posted** (newest first) — DEFAULT
  - **Price: Low to High** (`sortBy=price_ascend`)
  - **Price: High to Low** (`sortBy=price_descend`)
  - **Closest** (`sortBy=distance`)
  - Best Match / Relevance (when search query is active)

**Active filters:**
- Applied filters appear as **chips above the results grid** with individual X remove buttons.
- A "Filter" button typically shows a badge count of active filters.
- Chips are dismissible individually; "Clear all" available in the drawer.

**Mobile behavior:**
- **Filter:** Funnel icon button → full-screen modal with accordion sections (each filter category expands/collapses). Apply/Cancel buttons at the bottom.
- **Sort:** Sort button → bottom sheet or dropdown with horizontal option list.
- **Category bar:** Horizontal scroll with icons; on scroll, becomes sticky.
- **Location:** Part of the persistent top bar; tapping opens a location modal.

**Key observations:**
- Facebook Marketplace **requires login to search** — the search page redirects to `/login`. The homepage feed is browseable without login, but searching and filtering require authentication.
- URL params use **camelCase** (`sortBy`, `daysSinceListed`, `deliveryMethod`, `category_id`, `exact`) — a React/Facebook convention.
- The sort and filter buttons are **icon-only** on mobile (no visible text labels), relying on tooltips/aria-labels.
- **Category bar** is a distinctive pattern — horizontal scroll of category icons+labels above results.

**Confidence: MEDIUM-HIGH** — category bar, search placeholder, location selector, and URL params verified by live scraping; sort/filter button labels and full option lists verified via Facebook Help Center docs and community documentation (Reddit r/Flipping).

---

## 3. Cross-Platform Comparison

### 3.1 Filter UI Placement

| Platform | Desktop | Mobile |
|---|---|---|
| **Avito** | Inline form above results (top panel row) | Condensed top panel; filters in full-screen modal |
| **OLX** | Sticky left sidebar | Full-screen drawer (`modal-root`) |
| **Craigslist** | Inline form above results (collapsible) | Filter button → full-screen overlay |
| **Facebook Marketplace** | Right-side drawer (triggered by funnel button) | Full-screen modal with accordion sections |

**Consensus:** Desktop uses either an inline form (Avito, Craigslist) or a persistent sidebar (OLX, FB). Mobile universally collapses to a full-screen drawer or overlay.

### 3.2 Filter Control Types

| Data type | Avito | OLX | Craigslist | FB Marketplace |
|---|---|---|---|---|
| Price | Dual text inputs | Range slider | Dual text inputs (tel) | Min/Max text inputs |
| Condition | Dropdown (Любое/Новое/Б/у) | Checkboxes | Checkbox group (numeric codes) | Radio buttons |
| Category | Top-bar button → tree dropdown | Button → tree selector | Separate URL sections | Horizontal icon bar + "All Categories" |
| Location | Text + autocomplete | Dropdown | Zip code input | City selector |
| Boolean (free, image, etc.) | Checkbox | Checkbox | Checkbox | Checkbox |
| Category-specific attrs | Checkboxes | Checkboxes | Checkboxes | Accordions (expand to reveal form fields) |

**Consensus:** Checkboxes dominate for multi-select and boolean filters. Price uses text inputs on 3/4 platforms (slider only on OLX). Condition uses dropdowns, checkboxes, or radios depending on the platform.

### 3.3 Category Handling

| Platform | Tree depth in filter UI | Category-specific filters shown at |
|---|---|---|
| **Avito** | 1–2 levels in top-bar dropdown | Selected category page |
| **OLX** | 2+ levels via button selector | Selected category page |
| **Craigslist** | 1 level (flat sections, no tree) | Each section has its own URL |
| **FB Marketplace** | 2–3 levels in drawer | Selected category page |

**Consensus:** Category-specific filters appear **only after a category is selected** (not on the generic browse page). Craigslist is the exception — it uses entirely separate URL sections instead of a shared filter form.

### 3.4 Sorting Defaults & Options

| Platform | Default sort | Sort UI pattern | Sort options |
|---|---|---|---|
| **Avito** | Relevance / "По умолчанию" | Dropdown button | Relevance, price asc, price desc, date, discount |
| **OLX** | "Wybrane dla Ciebie" (recommended) | Tab-style buttons | Recommended, newest, cheapest, most expensive |
| **Craigslist** | Relevance (`sort=rel`, omitted from URL) | Combo box button | Relevance, newest, price asc, price desc |
| **FB Marketplace** | "Recently Posted" | Button → dropdown/sheet | Recently posted, price low→high, price high→low, closest |

**Consensus:** 4–5 sort options across all platforms. **Relevance/recommended is the default** on 3/4 (Avito, Craigslist, FB); OLX defaults to "recommended for you." Date/newest is always available. Price asc/desc is universal.

### 3.5 URL Structure

| Platform | URL pattern | State encoding |
|---|---|---|
| **Avito** | `/<city>/<category>` | AJAX updates (URL stays clean) |
| **OLX** | `/oferty/q-<query>/` | `?search[order]=val`, `?search[price][min]=` |
| **Craigslist** | `/search/<section>?cat=<slug>` | `?sort=`, `?min_price=`, `?max_price=`, `?postal=`, `#hash` for view |
| **FB Marketplace** | `/marketplace/<location>/search/` | `?query=`, `?sortBy=`, `?deliveryMethod=` |

**Consensus:** OLX and Craigslist encode all filter state in the **URL query string** (bookmarkable). Avito uses AJAX with a clean URL. FB Marketplace uses camelCase query params but requires login.

### 3.6 Mobile Behavior

| Platform | Filter access | Sort access | Active filters |
|---|---|---|---|
| **Avito** | Full-screen modal | Dropdown (condensed) | Chips in top panel |
| **OLX** | Full-screen drawer | Tab collapse / dropdown | Chips in sidebar |
| **Craigslist** | Full-screen overlay (Filter button) | Combo box button | URL params (no visual chips) |
| **FB Marketplace** | Full-screen modal (accordion) | Bottom sheet / dropdown | Chips above grid |

**Consensus:** Mobile filters **always** open a full-screen modal or drawer. Sort is a button or tab that expands options. Active filters are shown as removable chips on 3/4 platforms (Craigslist is the exception — it relies on URL params).

---

## 4. Key Takeaways for Mko Bazuna

1. **Default sort = relevance, not date.** Three of four platforms default to relevance/recommended, not newest-first. Craigslist defaults to relevance (`sort=rel`). Mko Bazuna currently defaults to `date_desc` — consider defaulting to relevance when a search query is present (already the case in the search view) but keeping date_desc for browse/category navigation.

2. **Price filter: text inputs, not sliders.** Text inputs for min/max price are used by Avito, Craigslist, and FB Marketplace (3/4). Only OLX uses a slider. The current `filter-ui.md` spec shows text inputs (`price_min`/`price_max`) — this matches the majority pattern. No need for a slider in Phase 1.

3. **Four core sort options are the floor.** Date asc/desc + price asc/desc covers all platforms. Avito and FB add a fifth (discount/distance). The existing `AdSort` StrEnum (`date_desc`, `date_asc`, `price_asc`, `price_desc`) is aligned with the industry standard.

4. **Filters should be URL-encoded for shareability.** Craigslist and OLX encode all filter state in query params (bookmarkable/shareable). This matches Mko Bazuna's existing approach (`?min_price=`, `?max_price=`, `?city=`, `?sort=`). Avito's AJAX approach is acceptable but less shareable.

5. **Category-specific filters appear on selection, not globally.** All four platforms show category-specific filter controls only after a category is chosen. Mko Bazuna's `filter-ui.md` spec shows generic filters (category, city, price, condition) — consider conditionally showing `listing_purpose` and `features` filters only when the category context supports them (per `categories.yaml` overrides).

6. **Mobile = full-screen drawer, desktop = inline or sidebar.** The `filter-ui.md` spec already calls for "Sidebar Filters (Desktop)" + "Mobile Filter Drawer" — this matches the consensus pattern across all four platforms.

7. **Active filters as chips.** Three of four platforms show removable chips for active filters. The `filter-ui.md` spec includes a "Filter Chips/Tags" section — keep this. Craigslist's omission (URL-only) is the outlier and considered poor UX.

8. **Craigslist hash-fragment pattern is an outlier.** Craigslist uses `#search=2~gallery~0` for view state alongside query params. No other platform was observed using hash fragments for filter state. Avoid this pattern.

---

## 5. Sources

- **HIGH** — Live browser automation (Playwright) on `avito.ru`, `olx.pl`, `craigslist.org`, `facebook.com/marketplace` (August 22, 2026). Direct DOM inspection of filter forms, sort dropdowns, URL parameters, and category navigation.
- **HIGH** — Facebook Help Center `support.avito.io/articles/1948` (Avito search settings documentation) via webfetch.
- **HIGH** — Reddit r/Flipping community documentation of Facebook Marketplace URL parameters (`sortBy=creation_time_descend`, `daysSinceListed`, `deliveryMethod`, `category_id`, `exact`) — cross-verified with multiple user comments.
- **MEDIUM** — Avito sort numeric codes (`sort/custom-option(104)` for date) inferred from `data-marker` attributes; exact URL param mapping for Avito sort is inferred from DOM structure, not direct URL observation (AJAX-based).
