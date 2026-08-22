---
id: search-patterns
domain: spec
tags:
  - search
  - ui
  - patterns
  - fts
related:
  - technical-specification
  - buyer-stories
  - architecture-structure
---

## Purpose

Document search UI patterns and implementation strategies for the Mko Bazuna classifieds board. Ads are translated once per language at publication; search runs in the buyer's language against per-language FTS vectors.

## Main Concepts

- **Search-first architecture:** 70%+ of platform traffic originates from search
- **Language-aware search:** Russian, Bosnian, and English queries search their matching per-language vector — no query-time translation
- **Native PostgreSQL FTS:** No external search engine; uses per-language `tsvector` + GIN indexes
- **Empty state handling:** Friendly guidance when no results found

## Hero Search with Location

The homepage search combines keyword input with city selection for local discovery.

### Structure

```html
<div class="bg-white rounded-lg shadow p-6 mb-8">
    <h2 class="text-xl font-semibold mb-4">Find what you need</h2>
    <form method="get" class="flex flex-col sm:flex-row gap-4">
        <input type="text" name="q" placeholder="Search ads..."
               class="flex-1 px-4 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500">
        <select name="city" class="sm:w-48 px-4 py-2 border rounded-lg">
            <option value="">All cities</option>
            {% for city in cities %}
                <option value="{{ city.id }}">{{ city.get_name }}</option>
            {% endfor %}
        </select>
        <button type="submit" class="px-6 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700">
            Search
        </button>
    </form>
</div>
```

### Search Input Specifications

| Property | Value |
|----------|-------|
| Placeholder | "Search ads..." or localized equivalent |
| Minimum width | 27 characters (recommended) |
| Submission | Form submit or HTMX `hx-get` |
| Autocomplete | HTMX-driven, `delay:300ms`, 10-item cap, 429 on rate limit |

Related user stories: US-B2, US-B3, US-B7

## Multi-Language Search Flow

Ads are translated once at publication time into Russian, Bosnian, and English
and stored per-language. Search runs **in the buyer's language** against a
per-language FTS vector column — no external translator is called on the search
critical path.

### Process

1. User enters query in search input (Russian, Bosnian, or English)
2. The `search` view resolves the locale from `request.LANGUAGE_CODE` via
   `LanguageLocale.from_code()` and picks the matching per-language vector
   column (`search_vector_ru/bs/en`) and FTS config (`russian`/`simple`/`english`)
3. PostgreSQL FTS runs the original query against the matching vector **without
   translation**
4. Single-word queries trigger locale-aware fuzzy category detection against the
   locale-appropriate category name (`Category.get_name(locale)`)

### Implementation

Ads store per-language `TSVECTOR` columns maintained by the `ads_search_vector_fn`
trigger at publication time. The publication-time translator
(`translate_all_languages` in `telegram_bot/handlers/ad_create.py`) remains the only
use of `deep-translator` — content is translated once when the ad is created.

Saved search alerts search the persisted `SavedSearch.language` field (the alert
command runs without a request), falling back to `ru` for legacy rows.

### Privacy Note

Only ad title/description content is sent to translation API; no user PII (telegram_id, username, IP) is included. See decision G and privacy policy documentation. Translation uses Russian, Bosnian, and English multi-language support for Russian content access.

Related user stories: US-B2

## Did-You-Mean Patterns

City name typos show suggestions using Python's `difflib` module.

### Implementation

```python
# Implemented in views/listing.py
from difflib import get_close_matches

def get_city_suggestion(input_city: str, valid_cities: list[str]) -> str | None:
    """Find close city match for typo correction."""
    matches = get_close_matches(input_city, valid_cities, n=1, cutoff=0.6)
    return matches[0] if matches else None
```

### UI Pattern

```html
{% if suggested_city %}
    <div class="mb-4 p-3 bg-blue-50 rounded-lg">
        <p class="text-sm text-blue-800">
            Did you mean: <a href="{% url 'ads:list' %}?city={{ suggested_city.id }}"
                           class="underline font-medium">{{ suggested_city.get_name }}</a>?
        </p>
    </div>
{% endif %}
```

Related user stories: US-B7

## Preferred City Default & Precedence

When a buyer visits a listing or search page **without** an explicit city in the URL
(`?city=` query or `/city/<slug>/` path), the listings/search view applies the preferred
city resolved by `PreferredCityMiddleware` as the default city filter (see
[architecture-structure.md](architecture-structure.md#middleware--context-processors)).

### Resolution priority

1. **Authenticated buyer** with `User.preferred_city` set → database FK value (wins;
   never overridden by the cookie).
2. **Otherwise** → the `preferred_city` cookie (city slug), validated against the `City`
   table. A stale/unknown slug is ignored (and the cookie deleted in `process_response`).
3. **None** → country-wide ("Вся страна", no city filter applied).

Explicit URL path (`/city/<slug>/`) and `city` query parameter **always take
precedence** over the stored preference — the preference is only a fallback when no
city is specified. Example: `listings.py` does `effective_city = preferred_city` when
no path/query city is present; `search.py` does `current_city = explicit_city or request.preferred_city`.

### Consent gating & login reconciliation

- The `preferred_city` **cookie** is written only when the `consent_preferences` cookie
  is present (source-gated in `set_preferred_city` — see Decision F). The authenticated
  `User.preferred_city` FK is written regardless of cookie consent.
- On login, a guest's `preferred_city` cookie is reconciled into `User.preferred_city`
  (unless the user already has one) so the preference persists across devices/sessions.
- Stale cookies (slug no longer in `cities`) are deleted in `process_response`.

The header city button shows `preferred_city_display` ("Вся страна" or the localized city
name), sourced from `header_context`.

Related user stories: US-B3, US-B7. Source: `apps/core/middleware/preferred_city.py`.

Buyers can sort search results by date (newest first) or price.

### Implementation

```python
# apps/ads/enums.py
class AdSort(StrEnum):
    DATE_NEWEST = "date_newest"
    PRICE_LOW = "price_low"
    PRICE_HIGH = "price_high"
```

### Sort Selector UI

```html
<div class="flex items-center gap-4 mb-4">
    <span class="text-sm text-gray-600">Sort by:</span>
    <select name="sort" onchange="this.form.submit()"
            class="px-3 py-1 border rounded text-sm">
        <option value="date_newest">Newest first</option>
        <option value="price_low">Price: Low to High</option>
        <option value="price_high">Price: High to Low</option>
    </select>
</div>
```

Related user stories: US-B2

## Empty State Patterns

When no results match, show clear guidance to help users refine their search.

### Implementation

```html
<div class="text-center py-12 bg-white rounded-lg">
    <svg class="w-16 h-16 mx-auto text-gray-300 mb-4" fill="none" stroke="currentColor">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
              d="M21 21l-6-6m2-5a7 7 0 1114 14 7 7 0 01-14-14z"></path>
    </svg>
    <p class="text-gray-600 text-lg">No ads found</p>
    <p class="text-gray-500 mt-2">Try adjusting your search or filters</p>
    <a href="{% url 'ads:list' %}" class="inline-block mt-4 px-4 py-2 bg-gray-100 rounded-lg hover:bg-gray-200">
        Clear all filters
    </a>
</div>
```

Related user stories: US-B2, US-B3, US-B6

## Search Autocomplete

## Search Autocomplete

HTMX-driven autocomplete dropdown wired into the catalog header search bar
(`components/header_catalog.html`). Typing triggers `GET search:autocomplete`
with a 300ms delay; the JSON response is rendered by inline vanilla JS.

### Endpoint

| Property | Value |
|----------|-------|
| URL name | `search:autocomplete` |
| Method | `GET` |
| Query param | `q` (sanitized: stripped, non-empty, max 255 chars) |
| Rate limit | 30 req/min per IP (cache-based); HTTP 429 on overflow |
| Response | `application/json` |

### Response Format

```json
{
  "query": "tele",
  "suggestions": [
    {
      "text": "Телефоны",
      "type": "category",
      "source": "category",
      "slug": "telefony",
      "category_path": "Товары > Электроника > Телефоны"
    },
    {
      "text": "Сараево",
      "type": "city",
      "source": "city",
      "slug": "saraevo"
    },
    {
      "text": "терминал",
      "source": "user_history",
      "type": "popular_search"
    }
  ]
}
```

### Suggestion Sources

Suggestions are merged in priority order (user history first), deduplicated by
`text`, and capped at 10 total:

| Source | `source` value | `type` value | Fields | Description |
|--------|----------------|--------------|--------|-------------|
| User history | `user_history` | `user_history` | `text`, `source`, `type` | Authenticated user's recent queries; session-based for anonymous |
| Categories | `category` | `category` | `text`, `source`, `type`, `slug`, `category_path` | Active categories with name prefix match |
| Cities | `city` | `city` | `text`, `source`, `type`, `slug` | City prefix match |
| Popular searches | `popular_search` | `popular_search` | `text`, `source`, `type` | Frequently searched terms |

### Frontend Behavior

The inline JS in `header_catalog.html` renders suggestions grouped by section
(Cities, Categories, Popular, History), each with appropriate SVG icons. Clicking
a suggestion:

- **City** (`type=city`): POSTs to `search:preferred_city` to persist the city,
  then navigates to `/city/<slug>/`.
- **Category** (`type=category`): navigates to `/category/<slug>/`.
- **Text** (popular/history): populates the search input and submits the form
  to `search:search`.

Rate-limit responses (HTTP 429) hide the dropdown. Arrow-key navigation and
Escape-to-close are handled client-side.

Category names are searchable via per-language fields in the search vectors.

### Implementation Notes

- `category_name` is denormalized into `ads.category_name` (Russian)
- The trigger indexes the Russian name in `search_vector_ru`, and the localized
  `name_i18n->>'bs'` / `->>'en'` names (falling back to the Russian name) in
  `search_vector_bs` / `search_vector_en`, at weight 'C'
- Single-word queries matching category names set `category_id` filter
  (locale-aware via `Category.get_name(locale)`)

Related user stories: US-B3, US-B6

## Search Response Performance

Target response time: ≤2 seconds for search queries.

### Optimization Strategies

- `GinIndex IX_ads_search_gin_ru`, `IX_ads_search_gin_bs`, `IX_ads_search_gin_en`
  on the per-language `search_vector_*` columns (built with `CONCURRENTLY`)
- Database indexes on filtered columns (city, category, status)
- Pagination limits (standard page size = 24 ads)

Related user stories: US-B2
