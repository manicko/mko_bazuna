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

Document search UI patterns and implementation strategies for the Mko Bazuna classifieds board. Search is multi-language over Russian content with Russian, Bosnian, and English query translation support.

## Main Concepts

- **Search-first architecture:** 70%+ of platform traffic originates from search
- **Multi-language query translation:** Russian, Bosnian, and English queries translate to Russian before FTS
- **Native PostgreSQL FTS:** No external search engine; uses `tsvector` + GIN index
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
| Autocomplete | Not in phase 1; future enhancement |

Related user stories: US-B2, US-B3, US-B7

## Query Translation Flow

All content is stored in Russian; Russian, Bosnian, and English queries translate to Russian before FTS.

### Process

1. User enters query in search input (Russian, Bosnian, or English)
2. `deep-translator` library translates to Russian via Google Translate
3. Translation passes through request cache to prevent duplicate calls
4. PostgreSQL FTS executes on Russian-translated query
5. Results optionally tagged "translated from Russian"

### Implementation

Documented in `apps/search/services/query_translator.py`

```python
# apps/search/services/query_translator.py
def translate_query(text: str, source_locale: str, target_locale: str) -> str:
    """Translate text from source_locale to target_locale using deep-translator."""
    if not text or not text.strip():
        return text
    
    # ... implements timeout, caching, and circuit-breaker for gracefull degradation
    
    return translated_text

```

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

## Sort Options

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

Related user stories: US-B2

## Category Name Search

Category names are searchable via denormalized field in `search_vector`.

### Implementation Notes

- `category_name` is denormalized into `ads.category_name` field
- Included in `search_vector` with weight 'C'
- Single-word queries matching category names set `category_id` filter
- All queries translate to Russian before matching

Related user stories: US-B3, US-B6

## Search Response Performance

Target response time: ≤2 seconds for search queries.

### Optimization Strategies

- `GinIndex IX_ads_search_gin` on `search_vector` column
- Query cache for translations
- Database indexes on filtered columns (city, category, status)
- Pagination limits (standard page size = 24 ads)

Related user stories: US-B2