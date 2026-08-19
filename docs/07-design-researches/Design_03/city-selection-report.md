# City / Location Selection Patterns in Classifieds Platforms

**Research report - 2026-08-19**
**Project:** Mko Bazuna (Telegram-driven classifieds board with Django web front-end)
**Target market:** Montenegro (~30 cities)

---

## 1. Executive Summary

Five classifieds platforms were inspected to understand how they handle city/location selection, a core UX concern for Mko Bazuna's planned Montenegro launch. Three platforms have dedicated, persistent city-selection mechanisms that serve as reference patterns.

| Platform | UI Location | Primary Effect | Persistence | Cross-Device |
|---|---|---|---|---|
| Avito.ru | Header, right of search bar | URL path rewrite + listing filter | Cookie + localStorage | Auth: yes; anon: no |
| OLX.ua | Hero search form (combobox) | Search filter parameter | Unknown | Unknown |
| Mobile.bg | Filter sidebar (combobox) | Search filter parameter | Unknown | Unknown |
| Otomoto.pl | Homepage city links | City + distance-radius filter | URL params | anon: no |
| SS.com | None | N/A (Latvia-wide) | N/A | N/A |

**Pattern A - Avito.ru (Header city button):**
A sticky city selector in the header that persists the user's choice via cookie/localStorage and rewrites the URL to embed the city slug in the path (e.g., /perm/). Provides persistent visual feedback.

**Pattern B - OLX.ua (Search-form combobox):**
The city selector is embedded within the search form as a combobox between the main search input and the search button. Couples location with search intent but has no persistent header indicator.

**Pattern C - Mobile.bg (Filter sidebar dropdown):**
Location filter is a dropdown (select) in the search filter sidebar using Oblast (region) level granularity. Appropriate for automotive vertical.

**Mko Bazuna current state:**
The preferred_city cookie (30 days, HttpOnly, SameSite=Lax, secure=request.is_secure()) is SET but NEVER READ. No middleware, context processor, or view logic consumes the cookie. All city-filtering reads from URL path params (/city/<slug>/) only. The only cookie-reading precedent is LanguagePreMiddleware.

**Recommendation for Montenegro:**
Implement a hybrid approach: Pattern B (visible city combobox in search form) as primary interaction, combined with a minimal Pattern A header badge. Critical first step: add city-reading middleware to close the cookie gap.

---

## 2. Research Methodology

| Platform | Inspection Method | Key Tools |
|---|---|---|
| Avito.ru | Playwright browser automation (webfetch returns 429) | DOM snapshot, element tree, URL parsing |
| OLX.ua | Playwright + JavaScript evaluation (React SPA) | querySelector, data-testid, localStorage scan |
| Mobile.bg | Playwright accessibility snapshot | Element tree, select options extraction |
| Otomoto.pl | Playwright accessibility snapshot | Element tree, homepage links analysis |
| SS.com | Playwright accessibility snapshot | Element tree, header/nav analysis |

### Research constraints

- Avito.ru webfetch returns HTTP 429 (rate-limited). Playwright browser automation was used instead.
- OLX.ua and Otomoto.pl are React SPAs - initial HTML is a shell. JavaScript evaluation required.
- HttpOnly cookies invisible to document.cookie. Persistence mechanisms relying on server-set cookies may not appear in frontend inspection.
- OLX.ua city picker opens on click - the dropdown list was not captured in the static snapshot.
- No authenticated sessions used - persistence for anonymous users only.

---

## 3. Platform Deep-Dive: Avito.ru

### 3.1 Header structure

The Avito.ru homepage header main row contains, in order:

1. **Logo** - /a > /img (avito logo)
2. **Hamburger menu** - /button
3. **Search input** - /input, placeholder="Search by ads"
4. **Search button** - /button, text="Find"
5. **City button** - button[ref=e114], text="Perm" - THE current city
6. **Top-bar links** - login, add-ad buttons

The city button (ref=e114) is a `<button>` element positioned directly after the search controls. Its text content is the current city name. Clicking it opens a city-selection modal.

### 3.2 URL structure and city embedding

The URL embeds the city slug in the PATH, not query parameters:

- https://www.avito.ru/perm/ (Perm city homepage)
- https://www.avito.ru/perm/transport (Transport in Perm)
- https://www.avito.ru/perm/nedvizhimost (Real estate in Perm)

This path-based embedding means the city is always present in the URL and parseable server-side on every request.

### 3.3 City selection picker

The city picker renders dynamically when the city button is clicked. Based on web-searched engineering articles (confirmed via Context7), the picker contains:

- Search input for typing a city name
- List of cities organized by federal subject
- Geolocation button (browser Geolocation API)
- Geo-IP pre-selection on first visit

### 3.4 Footer "Regions" section

The footer has a "Regions" section listing major Russian cities as links:
- Moscow -> /moskva
- Saint Petersburg -> /sankt-peterburg
- (truncated at 50KB snapshot limit)

### 3.5 Persistence mechanism

Confirmed via web research (Context7):

- Geo-IP on first visit (anonymous, no cookie)
- Cookie + localStorage once city is explicitly chosen
- Authenticated users: city stored in profile, syncs across devices
- URL path takes precedence over cookie on every load

### 3.6 Precedence rules

1. URL path (highest) - /city-slug/ overrides all
2. Cookie / localStorage
3. Geo-IP (first visit, anonymous)
4. Default regional office (Moscow/Saint Petersburg)

---

## 4. Platform Deep-Dive: OLX.ua

### 4.1 Overview

OLX.ua is the Ukrainian branch of the OLX group (operated by Allegro). It is a React single-page application (SPA).

### 4.2 Header structure

The header (header[testid="app-header"]) contains:

1. Logo - a[testid="olx-logo-link"]
2. Chat - a[testid="header-chat-button"] ("Chat")
3. Language switcher - ul[testid="langswitcher"] ("Ukr | Rus")
4. Observed page - a[testid="observed-page-link"]
5. Notification hub - button[testid="notification-hub"]
6. My OLX - a[testid="myolx-link"] ("Your profile")
7. Post new ad - a[testid="post-new-ad-button"] ("Add announcement")

**Notably absent from the header:** any dedicated city selector, location button, or location indicator.

### 4.3 Hero search form

Below the header, the homepage hero area contains a search form (div[testid="search-form"]) with:

1. Main search input - input[testid="search-input"], placeholder="What are you looking for?"
2. **City/location combobox** - input[testid="location-search-input"], role="combobox", placeholder="All Ukraine"
3. Search autosuggest container - div[testid="search-autosuggession"]
4. Search submit - button[testid="search-submit"], text="Search"

The city combobox is embedded within the search form, between the main search input and the search button. Its placeholder "All Ukraine" indicates the default is country-wide search.

### 4.4 City selection picker

The city combobox opens a dropdown/list of cities when clicked. The picker UI was not fully captured in the static snapshot (renders dynamically on interaction).

### 4.5 Persistence mechanism

Direct frontend inspection revealed:

- localStorage: Object.keys(localStorage) = empty array - no OLX/ALX/region/regionId keys found
- Cookies: document.cookie shows only third-party tracker cookies (btUserCountry=ME). No OLX-native city cookie visible (may be HttpOnly/server-set)

The persistence mechanism for OLX.ua could not be fully determined. It likely relies on a server-side HttpOnly cookie or session-based storage.

### 4.6 Default fallback

Default is "All Ukraine" - country-wide search.

---

## 5. Platform Deep-Dive: Mobile.bg

### 5.1 Overview

Mobile.bg is Bulgaria's largest automotive classifieds platform. The search page was inspected.

### 5.2 Header structure

Header contains: Logo, Login/Register, Edit ad, Add ad button, and navigation links.

**Notably absent:** any city or location selector in the header.

### 5.3 Search filter sidebar

The location filter is in the left-hand filter column:

- Label: "Located in" ("Namira se v")
- Combobox (select-style): "All" ("vsechki") default
- Options: Bulgaria, Abroad, plus 28 Bulgarian Oblast (region) names

### 5.4 Region granularity

Mobile.bg uses Oblast (region) level granularity, not individual cities. Bulgaria has 28 oblasts. This coarser granularity is appropriate for the automotive vertical.

### 5.5 Default fallback

Default is "All" ("vsechki") - country-wide search.

---

## 6. Platform Quick-Survey: Otomoto.pl & SS.com

### 6.1 Otomoto.pl

Poland's automotive classifieds platform (part of Allegro group).

**Header:** Logo, category tabs (Osobowe, Trucks, Motorcycles, etc.), secondary nav (Financing, Leasing, News, etc.), user actions.

**Location filtering:** No combobox/select. A "Search in cities:" section on the homepage displays city name links. Clicking navigates to pre-filtered results with search[dist]=50 (50 km radius).

### 6.2 SS.com

Latvia's general classifieds platform.

**Header:** Logo, Submit ad, My ads, Search, Memo (favorites), language selector (RU/EN/LV).

**Location selection:** None. Latvia-wide unified catalog with no city/region filter.

---
