---
name: validated-findings
description: Phase 08 — Search & Full-Text Search (FTS) validated findings
agent: validator
alwaysApply: false
validated: true
---

# Phase 08 Validated Findings — Search & Full-Text Search (FTS)

**Validator:** validator  
**Based on findings:** .ai/audit/08-search-fts/findings.md  
**Validation date:** 2026-07-20

> `problems-only: true` — only problems documented. Validation confirms each finding is technically correct and applicable.

---

## Findings

### SRH-001: 500ms translation timeout does not bound request latency (blocking shutdown)

| Field | Value |
|-------|-------|
| **ID** | SRH-001 |
| **Severity** | HIGH |
| **Type** | SPEC-DEVIATION |
| **Affected Modules** | `src/backend/apps/search/services/query_translator.py` |
| **Validation Status** | **VALIDATED** |

**Description:** The translation step wraps `translate_cached` in a `ThreadPoolExecutor` and calls `future.result(timeout=0.5)` to enforce a ~500ms budget. However the executor is created with a `with` statement, so on `TimeoutError` the block's `__exit__` runs `executor.shutdown(wait=True)`, which blocks until the underlying Google Translate call actually completes. The `future.result` timeout only controls when the exception is raised, not when the request continues.

**Verification Evidence:**
1. Code inspection: `query_translator.py:38-45` shows `with ThreadPoolExecutor(max_workers=1) as executor:` pattern
2. Python documentation: `Executor.shutdown(wait=True)` is the default, blocking until pending futures complete
3. Research file `.ai/researches/query_translator_timeout_research.md:76` assumed timeout returns control (incorrect assumption)
4. `US-B2` requires "response ≤2s" for search

**Validation Note:**
> - **Action:** validated (confirmed)
> - **Detail:** The code correctly implements `future.result(timeout=…)` but the `with` context manager causes `shutdown(wait=True)` to block on timeout. This is a genuine latency-bounding defect affecting availability under translator slowness.

---

### SRH-002: Single-word category match does not expand to descendants (subtree leakage/miss)

| Field | Value |
|-------|-------|
| **ID** | SRH-002 |
| **Severity** | HIGH |
| **Type** | SPEC-DEVIATION |
| **Affected Modules** | `src/backend/apps/search/views/search.py` |
| **Validation Status** | **VALIDATED** |

**Description:** Dimension (e) / Category Tree zone requires parent-category query to expand to all descendants. The public listings view does this correctly via `get_descendants(include_self=True)`. The search view's fuzzy single-word category detection applies an exact `category=category_filter` filter with no subtree expansion.

**Verification Evidence:**
1. `search.py:53-56`: `ads.filter(category=category_filter)` after fuzzy match (no descendants)
2. `listings.py:96-100`: Correct pattern using `category.get_descendants(include_self=True).values_list("id", flat=True)`
3. `US-B6` requires "browse ads by category with hierarchy support"
4. `Category` model inherits from `MPTTModel` providing `get_descendants()` method

**Validation Note:**
> - **Action:** validated (confirmed)
> - **Detail:** Divergent category-tree behavior between listings (correct) and search (incorrect). This violates US-B6's hierarchy support requirement.

---

### SRH-003: No pagination or result limit — unbounded result set (DoS / latency)

| Field | Value |
|-------|-------|
| **ID** | SRH-003 |
| **Severity** | HIGH |
| **Type** | SPEC-DEVIATION |
| **Affected Modules** | `src/backend/apps/search/views/search.py`, `src/backend/apps/ads/views/listings.py`, `src/backend/templates/ads/list.html` |
| **Validation Status** | **VALIDATED** |

**Description:** Neither the search view nor the listings view applies LIMIT, slicing, or Paginator. The full matching queryset is passed to the template, which iterates entirely with no page controls.

**Verification Evidence:**
1. `search.py:60-62`: Queryset annotated and ordered but never sliced
2. `templates/ads/list.html:63-100`: `{% for ad in ads %}` with no pagination controls, no `page_obj`
3. `listings.py:138-146`: Same pattern (ordering only, no Paginator)
4. `US-B2` requires "response ≤2s" for search
5. nginx config `search_limit` (20r/s) bounds request *rate*, not per-request *cost*

**Validation Note:**
> - **Action:** validated (confirmed)
> - **Detail:** No pagination mechanism exists. Both views and the template lack pagination controls. This creates DoS amplification risk under common search terms.

---

### SRH-004: `lru_cache` has no TTL — contradicts documented 5-minute translation cache

| Field | Value |
|-------|-------|
| **ID** | SRH-004 |
| **Severity** | MEDIUM |
| **Type** | DOC-UPDATE |
| **Affected Modules** | `src/backend/apps/search/services/query_translator.py`, `docs/03-packages/packages-list.md` |
| **Validation Status** | **RECLASSIFIED** |

**Description:** The translator docstring and packages spec describe a "5-minute cache" but the implementation uses `functools.lru_cache(maxsize=128)`, which has no time-based expiry.

**Verification Evidence:**
1. `query_translator.py:52`: `@lru_cache(maxsize=128)` decorator
2. `query_translator.py:57-58`: Docstring states "cache is invalidated by clearing on criteria change or after 5 minutes" — no TTL mechanism exists
3. `packages-list.md:35`: References "hard timeout ~500ms + fallback to original query" (no mention of TTL)

**Validation Note:**
> - **Action:** reclassified
> - **Detail:** Changed from `SPEC-DEVIATION` to `DOC-UPDATE`. The in-process LRU cache is acceptable for MVP; the code behavior is valid but documentation claims incorrect TTL behavior. Either update docs or implement Django cache with TTL — docs update is lower-risk for MVP.

---

### SRH-005: Raw buyer query strings written to application logs

| Field | Value |
|-------|-------|
| **ID** | SRH-005 |
| **Severity** | MEDIUM |
| **Type** | BEST-PRACTICE |
| **Affected Modules** | `src/backend/apps/search/views/search.py`, `src/backend/apps/search/services/query_translator.py` |
| **Validation Status** | **VALIDATED** |

**Description:** The search view logs the raw, unbounded buyer query at INFO/WARNING level. Buyer-provided text can contain PII or control characters.

**Verification Evidence:**
1. `search.py:66`: `logger.info(f"Empty search results for query '{query}'")` - logs at INFO level
2. `query_translator.py:42,45,48`: Logs `'{query}'` at debug/warning/info including full failure path
3. Buyers are unauthenticated; query strings are user-controlled input
4. No sanitization of newlines/control characters before logging

**Validation Note:**
> - **Action:** validated (confirmed)
> - **Detail:** Unauthenticated users can inject arbitrary text into logs. PII sink and log-injection risk verified. Recommendation to sanitize or gate behind DEBUG is appropriate.

---

### SRH-006: Overly broad exception handling masks real errors in translation path

| Field | Value |
|-------|-------|
| **ID** | SRH-006 |
| **Severity** | LOW |
| **Type** | BEST-PRACTICE |
| **Affected Modules** | `src/backend/apps/search/services/query_translator.py` |
| **Validation Status** | **VALIDATED** |

**Description:** `except (TimeoutError, RequestException, Exception)` catches all Exceptions, making the two specific types redundant and potentially masking programming errors.

**Verification Evidence:**
1. `query_translator.py:44`: `except (TimeoutError, RequestException, Exception) as e:`
2. The `TimeoutError` imported is from `concurrent.futures`, not builtin (line 9)
3. Broad catch obscures `TypeError`, attribute errors from API changes

**Validation Note:**
> - **Action:** validated (confirmed)
> - **Detail:** Pattern is overly broad for resilience. Catching `Exception` makes specific catches redundant and hides genuine bugs.

---

### SRH-007: Analytics event recorded before search executes / on translation failure

| Field | Value |
|-------|-------|
| **ID** | SRH-007 |
| **Severity** | LOW |
| **Type** | BEST-PRACTICE |
| **Affected Modules** | `src/backend/apps/search/views/search.py` |
| **Validation Status** | **VALIDATED** |

**Description:** `SEARCH_PERFORMED` is recorded unconditionally before translation and FTS execution.

**Verification Evidence:**
1. `search.py:43-47`: `AnalyticsEvent.objects.create(...)` before `translate_query_bs_to_ru` and FTS filter
2. Event is created even if subsequent search errors or returns no results

**Validation Note:**
> - **Action:** validated (confirmed)
> - **Detail:** Metric accuracy concern only. Recording before execution means failed searches still increment the counter. Recommendation to move after search is sound.

---

### SRH-008: `pg_trgm` documented in FTS stack but never installed or used

| Field | Value |
|-------|-------|
| **ID** | SRH-008 |
| **Severity** | MEDIUM |
| **Type** | DOC-UPDATE |
| **Affected Modules** | `src/backend/apps/search/views/search.py`, `docs/02-database/db-schema.md`, `docs/03-packages/packages-list.md`, `docs/01-spec/spec-index.md` |
| **Validation Status** | **RECLASSIFIED** |

**Description:** Documentation specifies "TSVECTOR + GIN + pg_trgm" as the FTS stack, but no `CREATE EXTENSION pg_trgm` exists and fuzzy matching uses Python `difflib` instead.

**Verification Evidence:**
1. No `pg_trgm`, `TrigramExtension`, or trigram similarity patterns in `src/` codebase
2. `search.py:121-126`: Uses `difflib.get_close_matches` with `Category.objects.filter(is_active=True)`
3. `db-schema.md:27`: Claims "pg_trgm" in FTS stack
4. `packages-list.md:30`: Claims "pg_trgm" in FTS stack
5. `spec-index.md:40`: Claims "pg_trgm" in FTS stack
6. `technical-specification.md:63`: Specifies "difflib.get_close_matches" for fuzzy category/city matching
7. `db-schema.md:145,184`: Documents difflib usage for fuzzy matching

**Validation Note:**
> - **Action:** reclassified
> - **Detail:** Changed from `SPEC-DEVIATION` to `DOC-UPDATE`. The implementation follows technical-specification.md which correctly specifies difflib for fuzzy matching. Multiple other docs incorrectly claim pg_trgm. Remove pg_trgm references from db-schema.md, packages-list.md, and spec-index.md to align with actual implementation.

---

### SRH-009: HTMX partial branch is a no-op (both branches render full page)

| Field | Value |
|-------|-------|
| **ID** | SRH-009 |
| **Severity** | LOW |
| **Type** | SPEC-DEVIATION |
| **Affected Modules** | `src/backend/apps/search/views/search.py`, `src/backend/apps/ads/views/listings.py`, `src/backend/templates/ads/list.html` |
| **Validation Status** | **VALIDATED** |

**Description:** Both views branch on `HX-Request` header but render the same full-page template in both cases.

**Verification Evidence:**
1. `search.py:74-78`: Identical `render(request, "ads/list.html", context)` in both branches
2. `listings.py:164-168`: Same duplicated pattern
3. `templates/ads/list.html:1-124`: Single full-document template; no partial template exists
4. `US-B3` claims "filters combinable with no full page reload (HTMX)"

**Validation Note:**
> - **Action:** validated (confirmed)
> - **Detail:** Dead code pattern. The HTMX branch check exists but serves identical output. Either implement partial rendering per US-B3 or remove the dead branch entirely.

---

## Validation Summary

| Action | Count | Details |
|--------|-------|---------|
| Validated (unchanged) | 7 | SRH-001, SRH-002, SRH-003, SRH-005, SRH-006, SRH-007, SRH-009 |
| Reclassified | 2 | SRH-004 (SPEC-DEVIATION → DOC-UPDATE), SRH-008 (SPEC-DEVIATION → DOC-UPDATE) |
| Merged | 0 | — |
| Rejected | 0 | — |
| Total | 9 | SRH-001 through SRH-009 |

---

## Reclassified Findings

| ID | Original Type | New Type | Rationale |
|----|---------------|----------|-----------|
| SRH-004 | SPEC-DEVIATION | DOC-UPDATE | LRU cache behavior is acceptable for MVP; docstring wrongly claims TTL-based invalidation |
| SRH-008 | SPEC-DEVIATION | DOC-UPDATE | Implementation follows technical-specification.md which correctly specifies difflib; docs claiming pg_trgm are misleading |

---

## Rollout Analysis

### Dependency Chain
- SRH-002 depends on django-mptt's `get_descendants()` method (already proven by listings.py)
- SRH-003 requires pagination template changes (list.html)
- SRH-009 overlaps with SRH-003 (both affect list.html rendering)
- SRH-001, SRH-004 can be addressed independently

### Risks
1. **SRH-001 + SRH-003 combined**: Under burst traffic, slow translation + unbounded results can amplify DoS, exhausting gunicorn workers
2. **SRH-002**: Fix must use same pattern as listings.py (descendant_ids) to maintain consistency
3. **SRH-008**: Documentation changes only; no operational risk
4. **SRH-009**: If HTMX partials are implemented, list.html must be split into partial + full template

---

## Required Fixes

| Priority | Finding | Action |
|----------|---------|--------|
| HIGH | SRH-001 | Create module-level `EXECUTOR = ThreadPoolExecutor(max_workers=1)`; call `future.result(timeout=0.5)` without `with` block — on timeout, the translator thread is abandoned but request returns promptly |
| HIGH | SRH-002 | Add `get_descendants(include_self=True)` or factor shared helper with listings |
| HIGH | SRH-003 | Add Django Paginator (20-40 per page) to search and listings views |

---

## Advisory Recommendations

| Priority | Finding | Action |
|----------|---------|--------|
| MEDIUM | SRH-004 | Update docstring to remove "5-minute cache" claim; describe LRU as maxsize=128 in-process cache with no TTL (Django cache with TTL is a future option) |
| MEDIUM | SRH-005 | Sanitize/truncate query strings before logging; gate verbose logging behind DEBUG |
| LOW | SRH-006 | Remove broad `Exception` catch; log at ERROR for genuine bugs |
| LOW | SRH-007 | Move analytics event creation after successful search execution |
| MEDIUM | SRH-008 | Remove `pg_trgm` from FTS stack documentation in db-schema.md, packages-list.md, spec-index.md |
| LOW | SRH-009 | Split list.html: create `ads/partials/ad_list.html` fragment and render partial on `HX-Request` header; remove dead branch after HTMX partial implemented |
