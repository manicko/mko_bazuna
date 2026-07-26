# Phase 2: Search Autocomplete — Research Report

## 1. Current State Analysis

### Existing Search Infrastructure
Found in `src/backend/apps/search/`:
- `views/search.py` - Implements FTS search with PostgreSQL search_vector
- `services/query_translator.py` - Bosnian→Russian translation with caching and circuit breaker
- `urls.py` - Routes for search endpoint
- `tests/test_query_translator.py` - Translation tests exist

### Analytics Infrastructure
Found in `src/backend/apps/analytics/models.py`:
- `AnalyticsEvent` model exists with event_type, timestamp, user fields
- `AnalyticsEventType` StrEnum in `apps/core/enums.py` with:
  - REGISTRATION_CREATED
  - AD_PUBLISHED
  - SEARCH_PERFORMED
  - CONTACT_INITIATED

### Gap: No Search History Tracking
Current search records `SEARCH_PERFORMED` event but without query text storage, making autocomplete impossible.

## 2. Gap Analysis

### Missing Components
| Component | Location | Status |
|-----------|----------|--------|
| PopularSearch model | apps/analytics/models.py | ❌ Missing |
| SearchHistory model | apps/analytics/models.py | ❌ Missing |
| SearchSuggestionSource enum | apps/core/enums.py | ❌ Missing |
| Rate limiting utility | apps/search/services/rate_limit.py | ❌ Missing |
| Popular search service | apps/search/services/popular_search.py | ❌ Missing |
| Search history service | apps/search/services/search_history.py | ❌ Missing |
| Entity suggestions service | apps/search/services/entity_suggestions.py | ❌ Missing |
| AutocompleteView | apps/search/views/autocomplete.py | ❌ Missing |
| Autocomplete URL route | apps/search/urls.py | ❌ Missing |

## 3. Modern Practices Research (2026)

### Search Autocomplete Patterns
- **Debounced requests**: 300ms delay before API call (prevents excessive requests)
- **Redis caching**: Cache popular terms for 1 hour, user history for 24 hours
- **Trigram indexes**: PostgreSQL `pg_trgm` extension for fast prefix matching
- **Privacy by design**: No user query data exposed to other users

### Implementation Pattern
Following Django + HTMX best practices:
- JSON endpoint: `/api/search/autocomplete?q=<partial>`
- Return structure: `{suggestions: [{query, source, hit_count}]}`
- HTMX integration: `hx-get` with `hx-trigger="input delay:300ms"`

## 4. Implementation Approach

### Recommended Architecture
1. **Create PopularSearch model** - Tracks popular queries with hit counts
2. **Create SearchHistory model** - User-specific query history
3. **Services layer** - Pure functions for each suggestion source
4. **AutocompleteView** - Aggregates and merges suggestions
5. **Update search view** - Record searches after successful execution

### Key Design Decisions
| Decision | Rationale |
|----------|-----------|
| Request-level rate limiting | Prevents abuse without requiring Redis for basic operation |
| Server-side suggestion aggregation | Personalized results (history > popular > entities) |
| Trigram index on category/city names | Fast prefix matching for entity suggestions |
| Cache-aside pattern | Fallback to DB on cache miss |

## 5. Technical Details

### File Changes Required

#### T1: PopularSearch Model
```python
# apps/analytics/models.py
class PopularSearch(models.Model):
    query = models.CharField(max_length=200, db_index=True)
    hit_count = models.PositiveIntegerField(default=1)
    last_searched_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = "popular_searches"
```

#### T2: SearchHistory Model
```python
# apps/analytics/models.py
class SearchHistory(models.Model):
    user = models.ForeignKey("users.User", on_delete=models.CASCADE, null=True, blank=True)
    query = models.CharField(max_length=200)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = "search_history"
        indexes = [models.Index(fields=["user_id", "-created_at"])]
```

#### T3: SearchSuggestionSource Enum
```python
# apps/core/enums.py
class SearchSuggestionSource(StrEnum):
    USER_HISTORY = "user_history"
    POPULAR_SEARCH = "popular_search"
    CATEGORY = "category"
    CITY = "city"
```

#### T5: sanitize_autocomplete_query
```python
# apps/core/utils/sanitize.py
def sanitize_autocomplete_query(query: str) -> str:
    """Sanitize autocomplete query - 2-100 chars, SQL injection safe."""
    if not query or len(query) < 2 or len(query) > 100:
        return ""
    # Remove dangerous patterns
    return re.sub(r"[;'\"]", "", query.strip())
```

#### T6: Rate Limiting
```python
# apps/search/services/rate_limit.py
RATE_LIMIT_KEY_PATTERN = "autocomplete_rl:{ip}"
RATE_LIMIT_REQUESTS = 30
RATE_LIMIT_PERIOD = 60  # seconds

def rate_limit_check(request: HttpRequest) -> bool:
    """Return True if request allowed, False if rate limited."""
```

#### T7: Popular Search Service
```python
# apps/search/services/popular_search.py
def increment_popular_search(query: str) -> None:
    """Increment hit count for query, create if not exists."""

def get_popular_suggestions(prefix: str, limit: int = 5) -> list[str]:
    """Get popular queries matching prefix, ordered by hit_count desc."""
```

#### T8: Search History Service
```python
# apps/search/services/search_history.py
def get_user_search_history(user: User | AnonymousUser, limit: int = 5) -> list[str]:
    """Get recent search queries for authenticated user."""
```

#### T9: Entity Suggestions Service
```python
# apps/search/services/entity_suggestions.py
def get_entity_suggestions(prefix: str, limit: int = 5) -> list[str]:
    """Get matching category and city names for autocomplete."""
```

#### T10: AutocompleteView
```python
# apps/search/views/autocomplete.py
def autocomplete(request: HttpRequest) -> HttpResponse:
    """Return JSON suggestions from all sources merged and deduplicated."""
```

#### T12: Search View Update
```python
# apps/search/views/search.py (post-search)
# After successful search, record:
# 1. PopularSearch increment
# 2. SearchHistory for authenticated users
```