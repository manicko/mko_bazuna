---
id: research_001_query_translator_timeout
domain: research
tags:
  - search
  - translation
  - timeout
  - deep-translator
related:
  - architecture-testing-plan
---

# Research: Query Translator Timeout

**Source:** `.ai/tasks/done/TASK_001_research_query_translator_timeout_DONE.yaml`  
**Source Section:** Part 7 — Query Translation Pipeline Resilience (P7.6 CRITICAL risk)  
**Status:** Complete  
**Date:** 2026-07-20

---

## 1. Call Sites Enumeration

### `translate_query_bs_to_ru`
| Location | Context | Notes |
|----------|---------|-------|
| `src/backend/apps/search/views/search.py:52` | Sync WSGI (gunicorn) | Called inside `search()` view with query string |

### `translate_cached`
| Location | Context | Notes |
|----------|---------|-------|
| `src/backend/apps/search/services/query_translator.py:37` | Called by `translate_query_bs_to_ru` | Internal call within same module |

**Note:** The bot (`src/telegram_bot/handlers/ad_create.py:468-482`) has its own separate `translate_to_russian()` function that calls `GoogleTranslator` directly. This is **ENT-004** (blocking network IO on async bot event loop) - a separate bug.

---

## 2. deep-translator GoogleTranslator Analysis

Per Context7 documentation, `GoogleTranslator.translate()`:
- Uses `requests` under the hood (no default timeout specified)
- Raises `RequestError` on connection errors
- Raises `TranslationNotFound` on empty/input errors
- Has no built-in socket timeout configuration
- Does NOT support async by default

**Key finding:** No timeout mechanism exists - network calls can block indefinitely.

---

## 3. Recommended Timeout Mechanism

### For Sync Gunicorn WSGI (web search view):

**`concurrent.futures.ThreadPoolExecutor` + `future.result(timeout=0.5)`** is the recommended approach because:
1. Works in sync context without requiring async loop
2. Standard library solution (no new dependencies)
3. `TimeoutError` raised on timeout can be caught for fallback
4. Minimal code change

### For Async Bot Context (separate issue - ENT-004):
- `sync_to_async` wrapper + timeout is needed
- This is tracked separately in ENT-004 bug report

---

## 4. Off-Request-Path Assessment

### In-Request Timeout (Recommended for immediate fix)
**Pros:**
- Minimal code change
- Preserves existing flow
- Bounded latency guaranteed

**Cons:**
- Under burst traffic, all workers can still block (up to 0.5s each)
- No proactive caching

### Off-Request-Path Options (Future enhancement)
**Pros:**
- Proactive translation warming
- Zero request-latency impact

**Cons:**
- Significant architectural change
- Requires background worker/process
- Cache warming strategy needed
- Not required for immediate SLO fix

**Recommendation:** Implement in-request timeout first (TASK_002), then consider off-request-path as future optimization if needed.

---

## 5. lru_cache Interaction Analysis

**Current structure:**
```
translate_query_bs_to_ru(query) -> translate_cached(query) [lru_cache] -> GoogleTranslator.translate()
```

**Problem:** `lru_cache` wraps the function, so the timeout must NOT be inside the cached function - otherwise the timeout wrapper is cached and subsequent calls bypass timeout logic.

**Correct insertion point:**
The timeout wrapper must be placed in `translate_query_bs_to_ru` around the `translate_cached()` call, NOT inside `translate_cached` itself.

**Proposed pattern:**
```python
def translate_query_bs_to_ru(query: str) -> str:
    if not query or not query.strip():
        return query
    
    try:
        # Timeout wrapper HERE, around cached call
        with ThreadPoolExecutor() as executor:
            future = executor.submit(translate_cached, query)
            result = future.result(timeout=TRANSLATION_TIMEOUT_SECONDS)
        # ...
```

The cache will still work because:
1. First call (cache miss) -> network with timeout -> result cached
2. Subsequent calls (cache hit) -> return immediately from cache -> no timeout needed

---

## 6. Recommendation

### Verdict: **GO** - Implement in-request timeout

### Exact Insertion Point
- **File:** `src/backend/apps/search/services/query_translator.py`
- **Function:** `translate_query_bs_to_ru`
- **Location:** Replace line 37 `result = translate_cached(query)` with timeout-wrapped call

### Mechanism
```python
from concurrent.futures import ThreadPoolExecutor, TimeoutError

def translate_query_bs_to_ru(query: str) -> str:
    if not query or not query.strip():
        return query

    try:
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(translate_cached, query)
            result = future.result(timeout=TRANSLATION_TIMEOUT_SECONDS)
        # ... rest of existing logic
    except (TimeoutError, RequestException, Exception) as e:
        # ... fallback logic
        return query
```

### Call Sites Requiring No Change
- `src/backend/apps/search/views/search.py:52` - No change needed; just catches fallback

### Separate Off-Request-Path Task Required
**No** - In-request timeout is sufficient for immediate SLO compliance. Off-request-path translation can be considered later if latency/burst testing shows further optimization needed.

---

## 7. Implementation Sketch

The fix requires:
1. Import `ThreadPoolExecutor`, `TimeoutError` from `concurrent.futures`
2. Wrap `translate_cached(query)` call in executor with `timeout=TRANSLATION_TIMEOUT_SECONDS`
3. Catch `TimeoutError` in addition to existing `RequestException` for fallback

**No changes needed to:**
- `translate_cached` function signature or cache behavior
- `search.py` view
- Any other call sites