# Search Autocomplete — Implementation Verification Report

**Plan file:** `.ai/plans/02/Search Autocomplete/plan.md`
**Date:** 2026-07-29
**Scope:** Verification of all 12 tasks (T1–T12) against actual code in `src/backend/apps/`.

---

## Summary

| Task | Status | Notes |
|------|--------|-------|
| T1 — PopularSearch model | **Implemented** | Missing `__str__` method |
| T2 — SearchHistory model | **Implemented** | Missing `__str__`, `related_name`, and Meta `indexes` |
| T3 — SearchSuggestionSource enum | **Implemented** | Exact match |
| T4 — sanitize_autocomplete_query | **Implemented** | Exact match |
| T5 — popular_search service | **Implemented** | Different dict keys (`text` vs `query`); `gte` vs `gt` threshold |
| T6 — search_history service | **Implemented** | Different pruning strategy; different empty-check order |
| T7 — entity_suggestions service | **Implemented** | `icontains` vs `istartswith`; extra `type` field; `text` vs `query` key |
| T8 — rate_limit utility | **Implemented** | Cleaner atomic increment; public/private key constant differs |
| T9 — AutocompleteView | **Implemented** | Different error key (`rate_limit` vs `rate_limited`); `text` vs `query` key; extra `query` in response |
| T10 — URL route | **Not implemented** | Route `api/search/autocomplete` absent from `apps/search/urls.py` |
| T11 — Search view recording | **Not implemented** | `increment_popular_search` / `record_search_history` not called in search view |
| T12 — Database migrations | **Implemented** | Migration exists; missing SearchHistory index |

**Key findings:**
- T10 and T11 are **not implemented** — the autocomplete endpoint is not wired into URLs, and the search view does not record popular searches or user history.
- The suggestion dict key naming is inconsistent: the plan uses `"query"`, the implementation uses `"text"`.
- The entity suggestions service uses `icontains` (contains match) instead of the plan's `istartswith` (prefix match), broadening the match scope.
- The popular search threshold uses `gte` (≥10) instead of the plan's `gt` (>10).
- No `test_autocomplete.py` test file exists, despite being referenced in the plan's verification commands.

---

## Task-by-Task Detail

### T1: Create PopularSearch Model

**Plan target:** `apps/search/models.py` — `PopularSearch` class
**Actual file:** `src/backend/apps/search/models.py` (lines 10–19)

**Evidence:**

```python
class PopularSearch(models.Model):
    """Stores popular search queries for autocomplete suggestions."""

    query = models.CharField(max_length=200, db_index=True)
    query_normalized = models.CharField(max_length=200, db_index=True)
    hit_count = models.PositiveIntegerField(default=1)
    last_seen = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "popular_searches"
```

**Assessment:** Implemented. All fields match the plan (`query`, `query_normalized`, `hit_count`, `last_seen`). `db_table = "popular_searches"` matches.

**Deviation:** The plan specifies a `__str__` method (`return f"{self.query} ({self.hit_count})"`). The implementation does not include it.

### T2: Create SearchHistory Model

**Plan target:** `apps/search/models.py` — `SearchHistory` class
**Actual file:** `src/backend/apps/search/models.py` (lines 21–35)

**Evidence:**

```python
class SearchHistory(models.Model):
    """Stores user search queries for personalized autocomplete."""

    user = models.ForeignKey(
        "users.User",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
    )
    query = models.CharField(max_length=200)
    query_normalized = models.CharField(max_length=200, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "search_history"
```

**Assessment:** Implemented. All fields match the plan. `db_table = "search_history"` matches.

**Deviations:**
1. Missing `__str__` method (plan specifies `return f"{self.query} (user={self.user_id})"`).
2. Missing `related_name="search_history"` on the `user` ForeignKey (plan specifies it).
3. Missing `indexes` in `Meta` (plan specifies `models.Index(fields=["user_id", "-created_at"])`).

### T3: Add SearchSuggestionSource Enum

**Plan target:** `apps/core/enums.py` — `SearchSuggestionSource`
**Actual file:** `src/backend/apps/core/enums.py` (lines 135–141)

**Evidence:**

```python
class SearchSuggestionSource(StrEnum):
    """Source types for search autocomplete suggestions."""

    USER_HISTORY = "user_history"
    POPULAR_SEARCH = "popular_search"
    CATEGORY = "category"
    CITY = "city"
```

**Assessment:** Implemented — exact match. The enum is also exported in `__all__` (line 177).

### T4: Add sanitize_autocomplete_query

**Plan target:** `apps/core/utils/sanitize.py` — `sanitize_autocomplete_query`
**Actual file:** `src/backend/apps/core/utils/sanitize.py` (lines 39–43)

**Evidence:**

```python
def sanitize_autocomplete_query(query: str) -> str:
    """Sanitize autocomplete query — 2–100 chars, SQL injection safe."""
    if not query or len(query) < 2 or len(query) > 100:
        return ""
    return re.sub(r"[;'\"\\]", "", query.strip())
```

**Assessment:** Implemented — exact match. The function enforces 2–100 character length and strips `;'\"\` characters.

### T5: Create popular_search Service

**Plan target:** `apps/search/services/popular_search.py` — `increment_popular_search`, `get_popular_suggestions`
**Actual file:** `src/backend/apps/search/services/popular_search.py` (80 lines)

**Evidence — `increment_popular_search`:**

```python
def increment_popular_search(query: str) -> None:
    normalized = query.strip().lower()
    if not normalized:
        return
    obj, created = PopularSearch.objects.update_or_create(
        query_normalized=normalized,
        defaults={"query": query, "hit_count": 1},
    )
    if not created:
        PopularSearch.objects.filter(pk=obj.pk).update(
            hit_count=F("hit_count") + 1,
            query=query,
        )
```

**Assessment:** Implemented. The plan uses a `try/except DoesNotExist` pattern; the implementation uses `update_or_create` + `F()` increment. Both achieve atomic increment, but the implementation's approach is cleaner (single query for insert, atomic `F()` for increment).

**Evidence — `get_popular_suggestions`:**

```python
def get_popular_suggestions(prefix: str, limit: int = 5) -> list[dict]:
    normalized_prefix = prefix.strip().lower()
    if not normalized_prefix:
        return []
    qs = PopularSearch.objects.filter(
        query_normalized__startswith=normalized_prefix,
        hit_count__gte=_MIN_HIT_COUNT,  # _MIN_HIT_COUNT = 10
    ).order_by("-hit_count")[:limit]
    return [
        {
            "text": obj.query,
            "source": SearchSuggestionSource.POPULAR_SEARCH.value,
            "hit_count": obj.hit_count,
        }
        for obj in qs
    ]
```

**Deviations:**
1. **Dict key naming:** Plan returns `{"query": ..., "hit_count": ...}`. Implementation returns `{"text": ..., "source": ..., "hit_count": ...}`. The key is `"text"` instead of `"query"`, and an extra `"source"` field is added.
2. **Threshold comparison:** Plan uses `hit_count__gt=10` (strictly greater than 10). Implementation uses `hit_count__gte=_MIN_HIT_COUNT` where `_MIN_HIT_COUNT = 10` (greater than or equal to 10). This means a query with exactly 10 hits would be included in the implementation but excluded in the plan.
3. **Constant naming:** Plan hardcodes `10`; implementation uses a named constant `_MIN_HIT_COUNT`.

### T6: Create search_history Service

**Plan target:** `apps/search/services/search_history.py` — `get_user_search_history`, `record_search_history`
**Actual file:** `src/backend/apps/search/services/search_history.py` (89 lines)

**Evidence — `record_search_history`:**

```python
def record_search_history(user_id: int | None, query: str) -> None:
    if user_id is None:
        return
    normalized = query.strip().lower()
    if not normalized:
        return
    SearchHistory.objects.filter(
        user_id=user_id,
        query_normalized=normalized,
    ).delete()
    SearchHistory.objects.create(
        user_id=user_id,
        query=query,
        query_normalized=normalized,
    )
    total = SearchHistory.objects.filter(user_id=user_id).count()
    if total > _MAX_HISTORY:
        excess = total - _MAX_HISTORY
        ids_to_delete = (
            SearchHistory.objects.filter(user_id=user_id)
            .order_by("created_at")
            .values_list("pk", flat=True)[:excess]
        )
        SearchHistory.objects.filter(pk__in=list(ids_to_delete)).delete()
```

**Assessment:** Implemented. Deduplication and pruning logic is present.

**Deviations:**
1. **Pruning strategy:** Plan uses `SearchHistory.objects.filter(user_id=user_id).order_by("-created_at")[50:].delete()` (slice-based deletion of all entries beyond 50). Implementation uses a count-based approach: counts total, calculates excess, then deletes the oldest `excess` entries by `pk`. Both achieve the same result (keep last 50), but the implementation's approach is more explicit.
2. **Empty check order:** Plan checks `if not query:` first (before normalization). Implementation checks `if user_id is None:` first, then normalizes, then checks `if not normalized:`.
3. **Constant naming:** Plan hardcodes `50`; implementation uses `_MAX_HISTORY = 50`.

**Evidence — `get_user_search_history`:**

```python
def get_user_search_history(user_id: int | None, limit: int = 5) -> list[str]:
    if user_id is None:
        return []
    qs = (
        SearchHistory.objects.filter(user_id=user_id)
        .order_by("-created_at")
        .values_list("query", flat=True)[:limit]
    )
    return list(qs)
```

**Assessment:** Implemented — functionally matches the plan.

### T7: Create entity_suggestions Service

**Plan target:** `apps/search/services/entity_suggestions.py` — `get_entity_suggestions`
**Actual file:** `src/backend/apps/search/services/entity_suggestions.py` (66 lines)

**Evidence:**

```python
def get_entity_suggestions(prefix: str, limit: int = 5) -> list[dict]:
    normalized = prefix.strip()
    if not normalized:
        return []
    categories = Category.objects.filter(
        name__icontains=normalized,
        is_active=True,
    ).order_by("name")[:limit]
    cities = City.objects.filter(
        name__icontains=normalized,
    ).order_by("name")[:limit]
    suggestions = [
        {
            "text": cat.name,
            "source": SearchSuggestionSource.CATEGORY.value,
            "type": "category",
        }
        for cat in categories
    ]
    suggestions.extend(
        {
            "text": city.name,
            "source": SearchSuggestionSource.CITY.value,
            "type": "city",
        }
        for city in cities
    )
    return suggestions
```

**Assessment:** Implemented — the function exists and queries both `Category` (with `is_active=True`) and `City` (without `is_active` filter, since the `City` model has no such field).

**Deviations:**
1. **Match type:** Plan uses `name__istartswith=prefix` (prefix match). Implementation uses `name__icontains=normalized` (contains match). This is a semantic difference — `icontains` matches anywhere in the name, not just at the beginning. For autocomplete, prefix matching is typically preferred to avoid irrelevant matches.
2. **Dict key naming:** Plan returns `{"query": name, "source": ...}`. Implementation returns `{"text": name, "source": ..., "type": "category"/"city"}`. The key is `"text"` instead of `"query"`, and an extra `"type"` field is added.
3. **Ordering:** Plan does not specify ordering; implementation adds `.order_by("name")`.

### T8: Create rate_limit Utility

**Plan target:** `apps/search/services/rate_limit.py` — `rate_limit_check`, `_get_client_ip`
**Actual file:** `src/backend/apps/search/services/rate_limit.py` (77 lines)

**Evidence:**

```python
RATE_LIMIT_REQUESTS: Final[int] = 30
RATE_LIMIT_PERIOD: Final[int] = 60
_RATE_LIMIT_KEY_PATTERN: Final[str] = "autocomplete_rl:{ip}"

def rate_limit_check(request: HttpRequest) -> bool:
    ip = _get_client_ip(request)
    key = _RATE_LIMIT_KEY_PATTERN.format(ip=ip)
    try:
        added = cache.add(key, 1, timeout=RATE_LIMIT_PERIOD)
        if added:
            current = 1
        else:
            current = cache.incr(key)
        return current <= RATE_LIMIT_REQUESTS
    except ValueError:
        cache.set(key, 1, timeout=RATE_LIMIT_PERIOD)
        return True
```

**Assessment:** Implemented — the function exists with atomic increment logic.

**Deviations:**
1. **Initial value:** Plan initializes the counter with `cache.add(key, 0, ...)` (value 0), then increments to 1. Implementation initializes with `cache.add(key, 1, ...)` (value 1 directly). The implementation's approach is cleaner and avoids the off-by-one in the plan's logic.
2. **Key constant visibility:** Plan defines `RATE_LIMIT_KEY_PATTERN` as a public module-level constant. Implementation defines `_RATE_LIMIT_KEY_PATTERN` (private, prefixed with underscore).
3. **Rate-limited branch:** Plan calls `cache.expire(key, RATE_LIMIT_PERIOD)` when the limit is exceeded. Implementation does not reset the TTL on rate-limit rejection.
4. **Error handling:** Plan has a `ValueError` handler that falls back to `cache.get(key, 0) + 1` and `cache.set`. Implementation's `ValueError` handler simply does `cache.set(key, 1, ...)` and returns `True`.

### T9: Create AutocompleteView

**Plan target:** `apps/search/views/autocomplete.py` — `autocomplete`
**Actual file:** `src/backend/apps/search/views/autocomplete.py` (91 lines)

**Evidence:**

```python
def autocomplete(request: HttpRequest) -> JsonResponse:
    query = sanitize_autocomplete_query(request.GET.get("q", ""))
    if not query:
        return JsonResponse({"suggestions": [], "query": ""})
    if not rate_limit_check(request):
        return JsonResponse({"error": "rate_limit"}, status=429)
    suggestions: list[dict[str, Any]] = []
    user_id = request.user.id if request.user.is_authenticated else None
    user_history = get_user_search_history(user_id)
    for item in user_history:
        suggestions.append({
            "text": item,
            "source": SearchSuggestionSource.USER_HISTORY.value,
        })
    entity_suggestions = get_entity_suggestions(query)
    suggestions.extend(entity_suggestions)
    popular = get_popular_suggestions(query)
    suggestions.extend(popular)
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for item in suggestions:
        text = item.get("text", "")
        if text and text not in seen:
            seen.add(text)
            unique.append(item)
    return JsonResponse({
        "suggestions": unique[:_MAX_SUGGESTIONS],
        "query": query,
    })
```

**Assessment:** Implemented — the view exists and merges suggestions from all three sources (user history, entity suggestions, popular searches), deduplicates, and limits to 10.

**Deviations:**
1. **Empty query response:** Plan returns `{"suggestions": []}`. Implementation returns `{"suggestions": [], "query": ""}` (adds `"query"` key).
2. **Rate limit error key:** Plan returns `{"suggestions": [], "error": "rate_limited"}`. Implementation returns `{"error": "rate_limit"}` (different error string, and does not include `"suggestions"` key).
3. **Dict key naming:** Plan uses `"query"` key in suggestion dicts. Implementation uses `"text"` key. The deduplication also uses `item.get("text", "")` instead of `s["query"]`.
4. **Response includes `query`:** Implementation includes `"query": query` in the final response. Plan does not.
5. **Entity suggestions call:** Plan calls `get_entity_suggestions(query, limit=5)` with explicit limit. Implementation calls `get_entity_suggestions(query)` without explicit limit (uses default of 5).
6. **Popular suggestions call:** Plan calls `get_popular_suggestions(query, limit=3)`. Implementation calls `get_popular_suggestions(query)` without explicit limit (uses default of 5).

### T10: Add URL Route

**Plan target:** `apps/search/urls.py` — `api/search/autocomplete`
**Actual file:** `src/backend/apps/search/urls.py`

**Evidence:**

```python
"""Search app URLs."""

from apps.search.views.search import search
from django.urls import path

app_name = "search"

urlpatterns = [
    path("search/", search, name="search"),
]
```

**Assessment:** **NOT IMPLEMENTED.** The URL route `api/search/autocomplete` is absent. The `autocomplete` view is not imported, and no `path()` entry exists for it. The project-level URL config (`src/backend/config/urls.py`, line 17) includes `apps.search.urls`, so the route would need to be added here.

**Impact:** The autocomplete endpoint is unreachable. Even though the view and all services exist, no HTTP request can reach them.

### T11: Update Search View to Record

**Plan target:** `apps/search/views/search.py` — `search` function
**Actual file:** `src/backend/apps/search/views/search.py` (152 lines)

**Evidence (search view, lines 47–75):**

```python
if query:
    # ... FTS search logic ...
    AnalyticsEvent.objects.create(
        event_type=AnalyticsEventType.SEARCH_PERFORMED,
        user_id=request.user.id if request.user.is_authenticated else None,
    )
```

**Assessment:** **NOT IMPLEMENTED.** The search view records an `AnalyticsEvent` but does NOT call `increment_popular_search(query)` or `record_search_history(request.user.id, query)`. The imports for these functions are not present in the file. The plan specifies adding these calls after the `AnalyticsEvent.objects.create(...)` line.

**Impact:** Popular search counts and user search history will never be populated, so the autocomplete endpoint (if it were reachable) would return empty results for those sources.

### T12: Create Database Migrations

**Plan target:** `apps/search/migrations/` — migrations for `popular_searches` and `search_history` tables
**Actual file:** `src/backend/apps/search/migrations/0001_initial.py` (76 lines)

**Evidence:**

```python
class Migration(migrations.Migration):
    initial = True
    dependencies = [
        ("ads", "0001_initial"),
        ("categories", "0001_initial"),
        ("locations", "0001_initial"),
        ("users", "0001_initial"),
    ]
    operations = [
        migrations.CreateModel(name="PopularSearch", ...),
        migrations.CreateModel(name="SearchHistory", ...),
        migrations.CreateModel(name="SavedSearch", ...),
        migrations.CreateModel(name="SavedSearchNotification", ...),
        migrations.AddConstraint(...),
    ]
```

**Assessment:** Implemented. The migration creates both `PopularSearch` and `SearchHistory` tables with the correct fields.

**Deviation:** The `SearchHistory` migration does not include the `indexes` specified in the plan (`models.Index(fields=["user_id", "-created_at"])`). This is consistent with the model's `Meta` class not having the `indexes` option (see T2 deviation).

---

## Cross-Cutting Issues

### 1. Inconsistent suggestion dict key naming (`"query"` vs `"text"`)

The plan consistently uses `"query"` as the key for the suggestion text in all service return values and the view's deduplication logic. The implementation uses `"text"` instead. This affects:

- `get_popular_suggestions` — returns `{"text": ..., "source": ..., "hit_count": ...}` (plan: `{"query": ..., "hit_count": ...}`)
- `get_entity_suggestions` — returns `{"text": ..., "source": ..., "type": ...}` (plan: `{"query": ..., "source": ...}`)
- `autocomplete` view — deduplicates by `item.get("text", "")` (plan: `s["query"]`)

This is an internal consistency issue within the implementation (it is self-consistent), but it diverges from the plan's specified contract.

### 2. Missing test file

The plan's verification commands reference:

```bash
uv run pytest src/backend/apps/search/tests/test_autocomplete.py -v
```

No `test_autocomplete.py` file exists in `src/backend/apps/search/tests/`. The only test files present are:
- `src/backend/apps/search/tests.py` (search view tests)
- `src/backend/apps/search/tests/test_query_translator.py` (query translator tests)

### 3. SearchHistory missing `related_name` and indexes

The `SearchHistory` model is missing:
- `related_name="search_history"` on the `user` ForeignKey (plan specifies it)
- `indexes = [models.Index(fields=["user_id", "-created_at"])]` in `Meta` (plan specifies it)

The corresponding migration also omits these.

### 4. Entity suggestions match type (`icontains` vs `istartswith`)

The plan specifies prefix matching (`name__istartswith=prefix`) for both categories and cities. The implementation uses contains matching (`name__icontains=normalized`). For autocomplete, prefix matching is the expected behavior — contains matching would return irrelevant suggestions (e.g., searching "тран" would match "контран" in addition to "транспорт").

### 5. Popular search threshold (`gte` vs `gt`)

The plan specifies `hit_count__gt=10` (strictly greater than 10). The implementation uses `hit_count__gte=10` (greater than or equal to 10). This means queries with exactly 10 hits are included in the implementation but would be excluded per the plan.

---

## Rollout Analysis

### Blocking issues (must be fixed before the feature is usable)

1. **T10 not implemented** — The autocomplete URL route is missing. The endpoint is unreachable. This is a critical blocker.
2. **T11 not implemented** — The search view does not record popular searches or user history. Without this, the autocomplete endpoint would return empty results for the popular search and user history sources. This is a critical blocker for the feature's core functionality.

### Non-blocking deviations (implementation works but differs from plan)

3. Suggestion dict key naming (`"text"` vs `"query"`) — self-consistent within the implementation; no runtime error.
4. Entity suggestions match type (`icontains` vs `istartswith`) — broader matching; functional but semantically different.
5. Popular search threshold (`gte` vs `gt`) — minor semantic difference; one extra query included at the boundary.
6. Missing `__str__`, `related_name`, and `indexes` on `SearchHistory` — cosmetic / performance; no functional impact.
7. Rate limit key constant visibility (`_RATE_LIMIT_KEY_PATTERN` vs `RATE_LIMIT_KEY_PATTERN`) — cosmetic.

### Dependencies

- T9 (AutocompleteView) depends on T5, T6, T7, T8 — all implemented.
- T10 (URL route) depends on T9 — T9 is implemented but T10 is not.
- T11 (search view recording) depends on T1, T2 — both implemented but T11 is not wired up.
- T12 (migrations) depends on T1, T2 — implemented.

The dependency chain is intact for implemented tasks. The two unimplemented tasks (T10, T11) are leaf tasks that depend only on already-implemented tasks.

---

## Conclusion

The Search Autocomplete plan is **partially implemented**. The core infrastructure (models, services, view, enum, sanitization utility, rate limiting, and migrations) is present and functional. However, two critical tasks remain unimplemented:

- **T10 (URL route):** The `api/search/autocomplete` endpoint is not registered in `apps/search/urls.py`, making the entire autocomplete feature unreachable via HTTP.
- **T11 (search view recording):** The search view does not call `increment_popular_search` or `record_search_history`, so the data sources for the autocomplete endpoint would remain empty.

Additionally, several deviations from the plan exist in the implemented code, primarily around dict key naming (`"text"` vs `"query"`), entity suggestion match type (`icontains` vs `istartswith`), and the popular search threshold (`gte` vs `gt`). These deviations do not prevent the feature from functioning but represent a divergence from the specified contract.

No code changes were made during this verification.
