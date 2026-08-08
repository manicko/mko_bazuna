# Search Autocomplete — Implementation Plan

## Overview

Implement search autocomplete suggestions via popular searches, user history, and entity matching (categories/cities).

**Research:** `.ai/plans/02/Search Autocomplete/research.md`

---

## Task Execution Order

| Task | Description | Symbol | File | Dependencies |
|------|-------------|--------|------|--------------|
| T1 | Create PopularSearch model | `PopularSearch` | `apps/search/models.py` | None |
| T2 | Create SearchHistory model | `SearchHistory` | `apps/search/models.py` | None |
| T3 | Add SearchSuggestionSource enum | `SearchSuggestionSource` | `apps/core/enums.py` | None |
| T4 | Add sanitize_autocomplete_query | `sanitize_autocomplete_query` | `apps/core/utils/sanitize.py` | None |
| T5 | Create popular_search service | `increment_popular_search`, `get_popular_suggestions` | `apps/search/services/popular_search.py` | T1 |
| T6 | Create search_history service | `get_user_search_history`, `record_search_history` | `apps/search/services/search_history.py` | T2 |
| T7 | Create entity_suggestions service | `get_entity_suggestions` | `apps/search/services/entity_suggestions.py` | None |
| T8 | Create rate_limit utility | `rate_limit_check` | `apps/search/services/rate_limit.py` | None |
| T9 | Create AutocompleteView | `autocomplete` | `apps/search/views/autocomplete.py` | T5, T6, T7, T8 |
| T10 | Add URL route | `api/search/autocomplete` | `apps/search/urls.py` | T9 |
| T11 | Update search view to record | `search` | `apps/search/views/search.py` | T1, T2 |
| T12 | Create database migrations | N/A | `apps/search/migrations/` | T1, T2 |

---

## Task Details

### T1: Create PopularSearch Model

**Symbol:** `PopularSearch`  
**File:** `apps/search/models.py`  
**Priority:** High

Add to existing `apps/search/models.py` (create if doesn't exist) or create new file:

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
**File:** `apps/search/models.py`  
**Priority:** High

Add to the same models file as PopularSearch:

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

    def __str__(self):
        return f"{self.query} (user={self.user_id})"
```

### T3: Add SearchSuggestionSource Enum

**Symbol:** `SearchSuggestionSource`  
**File:** `apps/core/enums.py`  
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
**File:** `apps/core/utils/sanitize.py`  
**Priority:** Medium

```python
def sanitize_autocomplete_query(query: str) -> str:
    """Sanitize autocomplete query - 2-100 chars, SQL injection safe."""
    if not query or len(query) < 2 or len(query) > 100:
        return ""
    return re.sub(r"[;'\"\\]", "", query.strip())
```

### T5: Create popular_search Service

**Symbol:** `increment_popular_search`, `get_popular_suggestions`  
**File:** `apps/search/services/popular_search.py`  
**Priority:** High

```python
def increment_popular_search(query: str) -> None:
    """Increment hit count for query, create if not exists using atomic operation."""
    from django.db.models import F
    from apps.search.models import PopularSearch

    normalized = query.lower().strip()

    try:
        obj = PopularSearch.objects.get(query_normalized=normalized)
        obj.hit_count = F("hit_count") + 1
        obj.save(update_fields=["hit_count"])
    except PopularSearch.DoesNotExist:
        PopularSearch.objects.create(
            query=query,
            query_normalized=normalized,
            hit_count=1
        )

def get_popular_suggestions(prefix: str, limit: int = 5) -> list[dict]:
    """Get popular queries matching prefix, ordered by hit_count desc."""
    from django.db.models import F
    from apps.search.models import PopularSearch

    return list(
        PopularSearch.objects.filter(
            query_normalized__startswith=prefix.lower(),
            hit_count__gt=10
        ).order_by("-hit_count")[:limit].values("query", "hit_count")
    )
```

### T6: Create search_history Service

**Symbol:** `get_user_search_history`, `record_search_history`  
**File:** `apps/search/services/search_history.py`  
**Priority:** High

```python
def record_search_history(user_id: int | None, query: str) -> None:
    """Record a search query for user history (deduped, max 50 per user)."""
    if user_id is None or not query:
        return

    normalized = query.lower().strip()

    # Delete existing entry to avoid duplicates, then create new
    SearchHistory.objects.filter(user_id=user_id, query_normalized=normalized).delete()
    SearchHistory.objects.create(user_id=user_id, query=query, query_normalized=normalized)

    # Prune to keep only last 50 entries per user
    SearchHistory.objects.filter(user_id=user_id).order_by("-created_at")[50:].delete()

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
**File:** `apps/search/services/entity_suggestions.py`  
**Priority:** Medium

```python
def get_entity_suggestions(prefix: str, limit: int = 5) -> list[dict]:
    """Get matching category and city names for autocomplete."""
    from apps.categories.models import Category

    results = []

    # Category suggestions - Category has is_active field
    category_names = Category.objects.filter(
        is_active=True,
        name__istartswith=prefix
    ).values_list("name", flat=True)[:limit]
    for name in category_names:
        results.append({"query": name, "source": SearchSuggestionSource.CATEGORY})

    # City suggestions - City has NO is_active field, removed filter
    from apps.locations.models import City
    city_names = City.objects.filter(
        name__istartswith=prefix
    ).values_list("name", flat=True)[:limit]
    for name in city_names:
        results.append({"query": name, "source": SearchSuggestionSource.CITY})

    return results
```

### T8: Create rate_limit Utility

**Symbol:** `rate_limit_check`  
**File:** `apps/search/services/rate_limit.py`  
**Priority:** Medium

**Fixed race condition: Use atomic increment with proper initialization.**

```python
RATE_LIMIT_KEY_PATTERN = "autocomplete_rl:{ip}"
RATE_LIMIT_REQUESTS = 30
RATE_LIMIT_PERIOD = 60  # seconds

def rate_limit_check(request: HttpRequest) -> bool:
    """Return True if request allowed, False if rate limited. Uses atomic increment."""
    from django.core.cache import cache

    ip = _get_client_ip(request)
    key = RATE_LIMIT_KEY_PATTERN.format(ip=ip)

    # Atomic increment: add() returns the new value after increment
    # If key doesn't exist, it's initialized with value 0, then incremented
    try:
        current = cache.add(key, 0, timeout=RATE_LIMIT_PERIOD)
        if current is False:
            # Key already exists, do atomic increment
            current = cache.incr(key)
        else:
            # Key was just created, count is 1
            current = 1

        if current > RATE_LIMIT_REQUESTS:
            # Reset TTL since we might be in a race
            cache.expire(key, RATE_LIMIT_PERIOD)
            return False
    except ValueError:
        # Key doesn't exist yet, force re-check
        current = cache.get(key, 0) + 1
        cache.set(key, current, timeout=RATE_LIMIT_PERIOD)

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
**File:** `apps/search/views/autocomplete.py`  
**Priority:** High

```python
def autocomplete(request: HttpRequest) -> JsonResponse:
    """Return JSON suggestions from all sources merged and deduplicated."""
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

    # Deduplicate by query, preserving order
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
**File:** `apps/search/urls.py`  
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
**File:** `apps/search/views/search.py`  
**Priority:** Medium

After successful search (post-query execution), add import and recording call:

```python
from apps.search.services.popular_search import increment_popular_search
from apps.search.services.search_history import record_search_history

# Inside search() after AnalyticsEvent.objects.create(...):
if query:
    increment_popular_search(query)
    if request.user.is_authenticated:
        record_search_history(request.user.id, query)
```

### T12: Create Database Migrations

**Priority:** High

After T1 and T2 add models to `apps/search/models.py`, create migrations:

```bash
uv run python manage.py makemigrations apps.search
```

Expected migrations for:
- `popular_searches` table (query, query_normalized, hit_count, last_seen)
- `search_history` table (user_id, query, query_normalized, created_at)

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
| Rate limit bypass | Low | Server-side check with atomic increment, nginx rate limit also |
| Translation overhead | Low | Only record normalized queries, not full text |
| Race condition in rate limit | Low | Fixed: use atomic increment with add()/incr() pattern |