# Search Autocomplete — Implementation Plan

## Overview

Implement search autocomplete suggestions via popular searches, user history, and entity matching (categories/cities).

**Research:** `.ai/plans/search-autocomplete/research.md`

---

## Task Execution Order

| Task | Description | Symbol | File | Dependencies |
|------|-------------|--------|------|--------------|
| T1 | Create PopularSearch model | `PopularSearch` | `apps/search/models/popular_search.py` | None |
| T2 | Create SearchHistory model | `SearchHistory` | `apps/search/models/search_history.py` | None |
| T3 | Add SearchSuggestionSource enum | `SearchSuggestionSource` | `apps/core/enums.py` | None |
| T4 | Add sanitize_autocomplete_query | `sanitize_autocomplete_query` | `apps/core/utils/sanitize.py` | None |
| T5 | Create popular_search service | `get_popular_suggestions` | `apps/search/services/popular_search.py` | T1 |
| T6 | Create search_history service | `get_user_search_history` | `apps/search/services/search_history.py` | T2 |
| T7 | Create entity_suggestions service | `get_entity_suggestions` | `apps/search/services/entity_suggestions.py` | None |
| T8 | Create rate_limit utility | `rate_limit_check` | `apps/search/services/rate_limit.py` | None |
| T9 | Create AutocompleteView | `autocomplete` | `apps/search/views/autocomplete.py` | T5, T6, T7, T8 |
| T10 | Add URL route | `api/search/autocomplete` | `apps/search/urls.py` | T9 |
| T11 | Update search view to record | `search` | `apps/search/views/search.py` | T1, T2 |

---

## Task Details

### T1: Create PopularSearch Model

**Symbol:** `PopularSearch`  
**File:** `src/backend/apps/search/models/popular_search.py`  
**Priority:** High

```python
class PopularSearch(models.Model):
    query = models.CharField(max_length=200, db_index=True)
    query_normalized = models.CharField(max_length=200, db_index=True)
    hit_count = models.PositiveIntegerField(default=1)
    last_seen = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "popular_searches"

    def __str__(self):
        return f"{self.query} ({self.hit_count})"
```

### T2: Create SearchHistory Model

**Symbol:** `SearchHistory`  
**File:** `src/backend/apps/search/models/search_history.py`  
**Priority:** High

```python
class SearchHistory(models.Model):
    user = models.ForeignKey(
        "users.User",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="search_history"
    )
    query = models.CharField(max_length=200)
    query_normalized = models.CharField(max_length=200, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "search_history"
        indexes = [
            models.Index(fields=["user_id", "-created_at"]),
        ]
```

### T3: Add SearchSuggestionSource Enum

**Symbol:** `SearchSuggestionSource`  
**File:** `src/backend/apps/core/enums.py`  
**Priority:** Medium

```python
class SearchSuggestionSource(StrEnum):
    USER_HISTORY = "user_history"
    POPULAR_SEARCH = "popular_search"
    CATEGORY = "category"
    CITY = "city"
```

### T4: Add sanitize_autocomplete_query

**Symbol:** `sanitize_autocomplete_query`  
**File:** `src/backend/apps/core/utils/sanitize.py`  
**Priority:** Medium

```python
def sanitize_autocomplete_query(query: str) -> str:
    """Sanitize autocomplete query - 2-100 chars, SQL injection safe."""
    if not query or len(query) < 2 or len(query) > 100:
        return ""
    return re.sub(r"[;'\"]", "", query.strip())
```

### T5: Create popular_search Service

**Symbol:** `increment_popular_search`, `get_popular_suggestions`  
**File:** `src/backend/apps/search/services/popular_search.py`  
**Priority:** High

```python
def increment_popular_search(query: str) -> None:
    """Increment hit count for query, create if not exists."""
    normalized = query.lower().strip()
    PopularSearch.objects.update_or_create(
        query_normalized=normalized,
        defaults={"query": query, "hit_count": F("hit_count") + 1}
    )

def get_popular_suggestions(prefix: str, limit: int = 5) -> list[dict]:
    """Get popular queries matching prefix, ordered by hit_count desc."""
    from django.db.models import F
    from ..models.popular_search import PopularSearch

    return list(
        PopularSearch.objects.filter(
            query_normalized__startswith=prefix.lower(),
            hit_count__gt=10
        ).order_by("-hit_count")[:limit].values("query", "hit_count")
    )
```

### T6: Create search_history Service

**Symbol:** `get_user_search_history`  
**File:** `src/backend/apps/search/services/search_history.py`  
**Priority:** High

```python
def get_user_search_history(user_id: int | None, limit: int = 5) -> list[str]:
    """Get recent search queries for authenticated user."""
    if user_id is None:
        return []
    return list(
        SearchHistory.objects.filter(user_id=user_id)
        .order_by("-created_at")[:limit]
        .values_list("query", flat=True)
    )
```

### T7: Create entity_suggestions Service

**Symbol:** `get_entity_suggestions`  
**File:** `src/backend/apps/search/services/entity_suggestions.py`  
**Priority:** Medium

```python
def get_entity_suggestions(prefix: str, limit: int = 5) -> list[dict]:
    """Get matching category and city names for autocomplete."""
    from apps.categories.models import Category
    from apps.locations.models import City

    results = []

    # Category suggestions
    category_names = Category.objects.filter(
        is_active=True,
        name__istartswith=prefix
    ).values_list("name", flat=True)[:limit]
    for name in category_names:
        results.append({"query": name, "source": SearchSuggestionSource.CATEGORY})

    # City suggestions
    city_names = City.objects.filter(
        is_active=True,
        name__istartswith=prefix
    ).values_list("name", flat=True)[:limit]
    for name in city_names:
        results.append({"query": name, "source": SearchSuggestionSource.CITY})

    return results
```

### T8: Create rate_limit Utility

**Symbol:** `rate_limit_check`  
**File:** `src/backend/apps/search/services/rate_limit.py`  
**Priority:** Medium

```python
RATE_LIMIT_KEY_PATTERN = "autocomplete_rl:{ip}"
RATE_LIMIT_REQUESTS = 30
RATE_LIMIT_PERIOD = 60  # seconds

def rate_limit_check(request: HttpRequest) -> bool:
    """Return True if request allowed, False if rate limited."""
    from django.core.cache import cache

    ip = _get_client_ip(request)
    key = RATE_LIMIT_KEY_PATTERN.format(ip=ip)

    current = cache.get(key, 0)
    if current >= RATE_LIMIT_REQUESTS:
        return False

    cache.incr(key)
    cache.expire(key, RATE_LIMIT_PERIOD)
    return True

def _get_client_ip(request: HttpRequest) -> str:
    """Extract client IP from request."""
    x_forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded:
        return x_forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "unknown")
```

### T9: Create AutocompleteView

**Symbol:** `autocomplete`  
**File:** `src/backend/apps/search/views/autocomplete.py`  
**Priority:** High

```python
def autocomplete(request: HttpRequest) -> HttpResponse:
    """Return JSON suggestions from all sources merged and deduplicated."""
    import json

    query = sanitize_autocomplete_query(request.GET.get("q", ""))
    if not query:
        return JsonResponse({"suggestions": []})

    if not rate_limit_check(request):
        return JsonResponse(
            {"suggestions": [], "error": "rate_limited"},
            status=429
        )

    suggestions = []

    # User history (highest priority)
    user_history = get_user_search_history(
        request.user.id if request.user.is_authenticated else None
    )
    for item in user_history:
        suggestions.append({"query": item, "source": SearchSuggestionSource.USER_HISTORY})

    # Entity suggestions
    entity_suggestions = get_entity_suggestions(query, limit=5)
    suggestions.extend(entity_suggestions)

    # Popular searches
    popular = get_popular_suggestions(query, limit=3)
    for item in popular:
        suggestions.append({
            "query": item["query"],
            "source": SearchSuggestionSource.POPULAR_SEARCH,
            "hit_count": item["hit_count"]
        })

    # Deduplicate by query
    seen = set()
    unique = []
    for s in suggestions:
        if s["query"] not in seen:
            seen.add(s["query"])
            unique.append(s)

    return JsonResponse({"suggestions": unique[:10]})
```

### T10: Add URL Route

**Symbol:** `api/search/autocomplete`  
**File:** `src/backend/apps/search/urls.py`  
**Priority:** Medium

```python
from apps.search.views.autocomplete import autocomplete

urlpatterns = [
    # ... existing routes ...
    path("api/search/autocomplete", autocomplete, name="autocomplete"),
]
```

### T11: Update Search View to Record

**Symbol:** `search`  
**File:** `src/backend/apps/search/views/search.py`  
**Priority:** Medium

After successful search (post-query execution):
```python
from apps.search.services.popular_search import increment_popular_search
from apps.search.services.search_history import record_search_history

# Record search in both systems
if query:
    increment_popular_search(query)
    if request.user.is_authenticated:
        record_search_history(request.user.id, query)
```

---

## Verification Commands

```bash
uv run basedpyright src/backend/apps/search/
uv run ruff check src/backend/apps/search/
uv run pytest src/backend/apps/search/tests/test_autocomplete.py -v
```

---

## Risk Assessment

| Risk | Level | Mitigation |
|------|-------|------------|
| Privacy leak | Medium | User history only returns for authenticated user |
| Rate limit bypass | Low | Server-side check, nginx rate limit also |
| Translation overhead | Low | Only record normalized queries, not full text |