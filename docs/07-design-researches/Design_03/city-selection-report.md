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
## 7. Cross-Platform Comparison Matrix

### 7.1 UI location

| Platform | UI Location | Element Type | Placement |
|---|---|---|---|
| Avito.ru | Header | <button> (text = city) | Right of search bar, persistent |
| OLX.ua | Hero search form | <input role="combobox"> | Between search input and button |
| Mobile.bg | Filter sidebar | <select> | In left filter column |
| Otomoto.pl | Homepage content | City links | In "Search in cities" section |
| SS.com | None | - | - |

### 7.2 Primary effect

| Platform | URL Change | Page Reload | SPA Nav | Effect |
|---|---|---|---|---|
| Avito.ru | Path rewrite | Full reload | No | Filters all listings by city |
| OLX.ua | SPA state/params | SPA navigation | Yes | Filters search results |
| Mobile.bg | Query param (likely) | Full reload | No | Filters automotive ads by region |
| Otomoto.pl | Path + search[dist]=50 | Full reload | No | Filters by city + radius |
| SS.com | None | None | None | No geographic filtering |

### 7.3 Default fallback

| Platform | Default | UI Text |
|---|---|---|
| Avito.ru | Geo-IP detected city | City name on button |
| OLX.ua | Country-wide | "All Ukraine" |
| Mobile.bg | Country-wide | "All" |
| Otomoto.pl | None (must select) | - |
| SS.com | N/A | - |

### 7.4 Header city indicator

| Platform | Header indicator? |
|---|---|
| Avito.ru | Yes - button with city name |
| OLX.ua | No |
| Mobile.bg | No |
| Otomoto.pl | No |
| SS.com | No |

Only Avito.ru provides persistent city awareness in the header.

---

## 8. Persistence Mechanisms

### 8.1 Avito.ru

| Mechanism | Evidence | Confidence |
|---|---|---|
| Cookie | Confirmed (Context7) | HIGH |
| localStorage | Confirmed (Context7) | HIGH |
| Server-side (auth) | Confirmed (Context7) | HIGH |
| Geo-IP (first visit) | Confirmed | HIGH |

- Anonymous first visit: Geo-IP -> set cookie
- Explicit city choice: cookie + localStorage persisted
- Authenticated: stored in profile, syncs across devices

### 8.2 OLX.ua

| Mechanism | Evidence | Confidence |
|---|---|---|
| Cookie (visible) | Not found | LOW (may be HttpOnly) |
| localStorage | Empty - no city/region keys | HIGH |
| Server-side session | Possible | LOW |

City selection persistence for anonymous users could not be confirmed.

### 8.3 Mobile.bg

| Mechanism | Evidence | Confidence |
|---|---|---|
| URL query params | Likely | MEDIUM |
| Cookie | Not inspected | LOW |

---

## 9. Precedence Rules

### 9.1 Avito.ru

| Priority | Source | Behavior |
|---|---|---|
| 1 (highest) | URL path | /city-slug/ overrides all |
| 2 | Cookie / localStorage | Used when URL has no city segment |
| 3 | Geo-IP | First visit, anonymous |
| 4 | Default | Moscow/Saint Petersburg fallback |

### 9.2 OLX.ua

Could not be fully determined. Likely relies on Geo-IP + SPA state for anonymous users.

---

## 10. Cross-Device Behavior

| Platform | Anonymous cross-device | Authenticated cross-device |
|---|---|---|
| Avito.ru | No (cookie/localStorage device-local) | Yes (profile sync) |
| OLX.ua | Unknown | Likely yes (auth profile) |
| Mobile.bg | Unknown | Unknown |

**Mko Bazuna implication:** Buyers browse without login (anonymous primary). City preference must work via cookie/localStorage for anonymous users.

---

## 11. Mko Bazuna Current State

### 11.1 City selection flow

```
User types in search box
  ->
Autocomplete dropdown appears (city suggestions alongside category/popular)
  ->
User clicks city suggestion [data-type="city"]
  ->
POST /api/preferred-city/ -> sets preferred_city cookie (30d, HttpOnly, SameSite=Lax)
  ->
Redirect to /city/<slug>/
  ->
Search/Listings view reads city from URL PATH (not cookie)
  ->
Listings filtered by city_slug
```

### 11.2 Cookie specification (Decision_018)

File: src/backend/apps/search/views/preferred_city.py

| Property | Value |
|---|---|
| Cookie name | preferred_city (hardcoded string) |
| Value | City slug (e.g., podgorica) |
| max_age | 2592000 (30 days) |
| httponly | True |
| samesite | "Lax" |
| secure | request.is_secure() |
| path | / |

### 11.3 Cookie is NEVER read - evidence

```python
# src/backend/apps/search/views/search.py line 70
current_city = request.GET.get("city")  # URL query param, NOT cookie

# src/backend/apps/ads/views/listings.py line 304
city_slug = ...  # from URL path, NOT cookie
```

No code anywhere reads request.COOKIES.get("preferred_city") or similar.

### 11.4 Only cookie-reading precedent

```python
# src/backend/core/middleware/language.py line 64
class LanguagePreMiddleware:
    """Read LANGUAGE_COOKIE_NAME and set request.LANGUAGE_CODE."""
```

This proves the infrastructure exists. A PreferredCityMiddleware mirroring this pattern can be added.

### 11.5 Header template

File: src/backend/templates/components/header_catalog.html

Current header: Logo + category menu (left), Search input with autocomplete (center), Language/login/profile/add-ad (right).

**No dedicated city button.** City selection only via autocomplete dropdown within search input.

### 11.6 URL structure

Cities are encoded in URL **path**: /city/<slug>/ (e.g., /city/podgorica/).

### 11.7 _suggest_city helper

_suggest_city in the search view uses difflib.get_close_matches() for typo tolerance.

---

## 12. Gap Analysis

### 12.1 Critical gap: Cookie set but never consumed

| Aspect | Current | Expected |
|---|---|---|
| Cookie write | Working (POST /api/preferred-city/) | Keep |
| Cookie read | Nothing reads it | Add middleware |
| Default city | Falls back to whole country | Read cookie -> set default |
| Cross-session | Cookie exists but has no effect | Persist city across sessions |

**Impact:** Returning user with preferred_city=podgorica cookie sees country-wide results when visiting homepage directly. Must re-select city via autocomplete every time.

### 12.2 No persisted city indicator

| Platform | Header city indicator | Mko Bazuna |
|---|---|---|
| Avito.ru | Button with city name | None |
| OLX.ua | None | None |
| Mko Bazuna | - | None |

No visual indicator of current city anywhere on the page.

### 12.3 City selection hidden in autocomplete

OLX.ua combobox is visible on page load. Avito.ru has header button. Mko Bazuna requires typing in search box to see city suggestions.

### 12.4 Code quality gaps

- Cookie name "preferred_city" is a hardcoded string, not a StrEnum constant (violates project rule: "All fixed values must use StrEnum")
- No City model or registry - cities are derived from ad data, not curated

### 12.5 Montenegro-specific

~30 cities/municipalities need to be in autocomplete data. 7 largest should be prioritized. No "whole country" option exists in current data.

---

## 13. Recommendation for Montenegro Launch

### 13.1 Recommended approach: Hybrid (Pattern B + Pattern A header indicator)

| Element | Pattern | Implementation |
|---|---|---|
| City selection interaction | Pattern B (OLX.ua) | Combobox in hero search form, visible on page load |
| Current city indicator | Pattern A (Avito.ru) | Small header badge showing current city or "Tshe tselo" |
| Persistence | Avito.ru model | Cookie-based (Decision_018), ADD middleware to read it |
| Default behavior | OLX.ua model | "Tshe tselo" (whole country) as default |
| URL structure | Avito.ru model | Path-based (/city/<slug>/) - already in place |
| Precedence | Avito.ru model | URL > cookie > default |

### 13.2 Implementation steps

**Phase 1: Close the cookie gap (high priority, low effort)**

1. Create src/backend/apps/search/middleware/preferred_city.py with PreferredCityMiddleware:
   - Reads preferred_city from request.COOKIES
   - Sets request.preferred_city (City object or None)
   - Mirrors LanguagePreMiddleware pattern exactly
2. Register in settings.py (after LanguagePreMiddleware, before views)
3. Update SearchView and ListingsView to use request.preferred_city as fallback when no city in URL
4. Extract cookie name into a StrEnum constant (project rule compliance)

**Phase 2: Visible city combobox (medium priority)**

1. Refactor header to show city combobox in search form (visible on load, not just on typing):
   - Shows current city text or "Tshe tselo" as placeholder
   - Opens dropdown of Montenegro cities on click
   - Persists via existing POST /api/preferred-city/
   - Navigates to /city/<slug>/ after selection
2. Add minimal header badge showing current city (like Avito's "Perm" button)

**Phase 3: Curated city registry (lower priority)**

1. Create a City model or StrEnum-based registry with:
   - Slug, display name (Serbian/Latin), population ranking, oblast grouping
2. Populate with Montenegro's ~30 cities, prioritizing 7 largest:
   - Podgorica
   - Niksic
   - Pljevlja
   - ... etc.
   - "Tshe tselo" (whole country) as last option

### 13.3 Why not copy Avito's header button exactly?

Russia has ~1000+ cities - a header button + modal makes sense. Montenegro has ~30 cities - an inline combobox is simpler and more discoverable.

### 13.4 Why not copy OLX's search-form combobox exactly?

OLX has no persisted city indicator in the header. A returning user lands on the homepage with no awareness of which city's results they will see. Adding a minimal header badge provides persistent awareness.

### 13.5 Default fallback

Default should be "Tshe tselo" (whole country), mirroring OLX's "All Ukraine". Appropriate because:
- Montenegro population ~620K - country-wide results are manageable
- New visitors likely want to browse all ads
- Search autocomplete still surfaces city-specific results via keywords

---

## Appendix F: Evidence Files

**Live DOM snapshots** (stored in .playwright-mcp/):

| File | Platform | Description |
|---|---|---|
| page-2026-08-19T07-59-47-184Z.yml | Avito.ru | Full page DOM (city button "Perm" at ref e114, footer Regions section) |
| olx_full_page.yml | OLX.ua | Full page DOM (header + homepage categories) |
| olx_city_combobox_snapshot.yml | OLX.ua | City combobox element (input[testid="location-search-input"]) |
| mobile_bg_search.yml | Mobile.bg | Search page DOM (location combobox in filter sidebar) |
| otomoto_homepage.yml | Otomoto.pl | Homepage DOM ("Search in cities" city links section) |

**Mko Bazuna codebase files inspected:**

| File | Key finding |
|---|---|
| src/backend/apps/search/views/preferred_city.py | Cookie SET: name="preferred_city", max_age=30d, httponly=True, samesite="Lax", secure=request.is_secure() |
| src/backend/apps/search/views/search.py:70 | current_city = request.GET.get("city") - URL param only |
| src/backend/apps/ads/views/listings.py:304 | Reads city_slug from URL path |
| src/backend/apps/search/views/autocomplete.py:34 | Entity suggestions include matching category and city names |
| src/backend/core/middleware/language.py:64 | Only cookie-reading precedent: LanguagePreMiddleware |
| src/backend/templates/components/header_catalog.html | City click handler: POST /api/preferred-city/ -> redirect /city/<slug>/ |

---

*End of report.*
