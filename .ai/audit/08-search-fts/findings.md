---
name: audit-findings
description: Structured findings for audit phase 08 — Search & Full-Text Search (FTS)
agent: auditor
phase: 08-audit-search-fts
alwaysApply: false
---

# Phase 08 Audit Findings — Search & Full-Text Search (FTS)

**Executor:** auditor
**Template:** .kilo/commands/audit/phases/08-audit-search-fts.md
**Status:** complete
**Validated:** no
**Output mode:** problems-only

Scope audited: `apps/search` (view + query translator), `ads.search_vector`
trigger (`ads/migrations/0002_search_vector_triggers.py`), category-tree
expansion vs. `ads/views/listings.py`, visibility gating vs. consent semantics
(`users/services/deletion.py`, `users/views/consent.py`), analytics/logging PII,
pagination/limits (`templates/ads/list.html`), and nginx rate limiting.

Runtime verification (§4) could not be executed to completion: the DB-backed
search suite requires a live PostgreSQL (`russian` FTS config is PG-only) and the
test run exceeded the tool timeout with no local DB up. Findings below are
evidence-based from static analysis of source, migrations, templates, and docs.

---

## Findings

### SRH-001: 500ms translation timeout does not bound request latency (blocking shutdown)

| Field | Value |
|-------|-------|
| **ID** | SRH-001 |
| **Severity** | HIGH |
| **Type** | RUNTIME-ERROR |
| **Affected Modules** | `src/backend/apps/search/services/query_translator.py` |
| **Classification** | mandatory |

**Description:** The translation step wraps `translate_cached` in a
`ThreadPoolExecutor` and calls `future.result(timeout=0.5)` to enforce a ~500ms
budget (Translation Bridge zone; dimension (c)). However the executor is created
with a `with` statement, so on `TimeoutError` the block's `__exit__` runs
`executor.shutdown(wait=True)`, which blocks until the underlying Google
Translate call actually completes. The `future.result` timeout therefore only
controls *when the exception is raised*, not *when the request continues*: the
request thread still waits for the full (possibly multi-second) network call
before falling back. Under translator slowness/outage this fails the bounded-
latency requirement (US-B2 ≤2s; §4.2 "bounded latency") and, on sync WSGI, ties
up a gunicorn worker for the entire upstream call — a search-availability DoS
amplifier under burst.

**Evidence:**
- `query_translator.py:38-45`:
  ```python
  with ThreadPoolExecutor(max_workers=1) as executor:
      future = executor.submit(translate_cached, query)
      result = future.result(timeout=TRANSLATION_TIMEOUT_SECONDS)
  ...
  except (TimeoutError, RequestException, Exception) as e:
  ```
  `with ... as executor` → `shutdown(wait=True)` on exit blocks on the still-
  running thread. A per-request executor also cannot be cancelled (no
  `cancel_futures` before Python 3.9 `shutdown`, and even then a running thread
  is not interruptible).
- Confirmed intent vs. behavior gap: `.ai/researches/query_translator_timeout_research.md:76`
  ("Under burst traffic, all workers can still block (up to 0.5s each)") assumes
  the timeout returns control; the `with`-block shutdown breaks that assumption.

**Recommendation:** Do not use a `with`-managed executor for the timeout path.
Either (a) use a module-level shared executor and call `future.result(timeout=…)`
without shutting it down on timeout (accept the orphaned thread finishing in the
background, cache still populated), or (b) move translation off the request
critical path. Add a regression test that patches `translate_cached` to sleep >2s
and asserts `translate_query_bs_to_ru` returns the original query within the
timeout budget. Effort: small. Priority: recommended (mandatory — latency SLO).

---

### SRH-002: Single-word category match does not expand to descendants (subtree leakage/miss)

| Field | Value |
|-------|-------|
| **ID** | SRH-002 |
| **Severity** | HIGH |
| **Type** | SPEC-DEVIATION |
| **Affected Modules** | `src/backend/apps/search/views/search.py` |
| **Classification** | mandatory |

**Description:** Dimension (e) / Category Tree zone requires a parent-category
query to expand to all descendants (US-B6, django-mptt subtree). The public
listings view does this correctly via `category.get_descendants(include_self=True)`
(`listings.py:97-100`). The search view's fuzzy single-word category detection
instead applies an *exact* `category=category_filter` filter with no subtree
expansion, so a single-word query matching a parent category returns only ads
attached directly to that parent and silently excludes every descendant ad. This
is divergent gating between two entry points that should share behavior (§6:
category expansion must not be re-implemented divergently).

**Evidence:**
- `search.py:53-56`:
  ```python
  if _is_single_word(query):
      category_filter = _fuzzy_category_match(translated_query)
      if category_filter:
          ads = ads.filter(category=category_filter)   # no get_descendants()
  ```
- Contrast `listings.py:96-100` (correct subtree expansion).

**Recommendation:** Reuse the descendants expansion (`get_descendants(include_self=True)`)
for the search-view category filter, or factor a shared helper used by both
`listings` and `search` so category-tree semantics have a single source of truth.
Effort: small. Priority: recommended (mandatory — correctness of results).

---

### SRH-003: No pagination or result limit — unbounded result set (DoS / latency)

| Field | Value |
|-------|-------|
| **ID** | SRH-003 |
| **Severity** | HIGH |
| **Type** | SPEC-DEVIATION |
| **Affected Modules** | `src/backend/apps/search/views/search.py`, `src/backend/apps/ads/views/listings.py`, `src/backend/templates/ads/list.html` |
| **Classification** | mandatory |

**Description:** Dimension (f) / Ranking-Pagination zone requires bounded result
sets to prevent DoS. Neither the search view nor the listings view applies any
`LIMIT`, slicing, or `Paginator`; the full matching queryset is passed to the
template, which iterates it entirely (`{% for ad in ads %}`) with no `page_obj`
or `is_paginated`. A common search term over seeded volume (e.g. 100k PUBLISHED
ads) will build/serialize/render the entire result set in one request, blowing
the US-B2 ≤2s budget and enabling a cheap amplification DoS. Only nginx IP rate
limiting (`search_limit` 20r/s) bounds request *rate*, not per-request cost.

**Evidence:**
- `search.py:60-72` — queryset annotated/ordered but never sliced; passed as
  `context["ads"]` directly.
- `templates/ads/list.html:63-100` — `{% if ads %}` / `{% for ad in ads %}` with
  no pagination controls, no `page_obj`, no `is_paginated`.
- `listings.py:138-168` — same pattern (ordering only, no `Paginator`).
- Spec expectation: `docs/04-user-stories/buyer-stories.md:26` ("response ≤2s").

**Recommendation:** Add server-side pagination (Django `Paginator`, e.g. 20-40
per page) or a hard `[:N]` cap on both search and listings querysets, and render
page controls in `list.html`. Effort: small. Priority: recommended (mandatory —
DoS/latency).

---

### SRH-004: `lru_cache` has no TTL — contradicts documented 5-minute translation cache

| Field | Value |
|-------|-------|
| **ID** | SRH-004 |
| **Severity** | MEDIUM |
| **Type** | SPEC-DEVIATION |
| **Affected Modules** | `src/backend/apps/search/services/query_translator.py`, `docs/03-packages/packages-list.md` |
| **Classification** | advisory |

**Description:** The translator docstring and the packages spec describe a
"5-minute cache" / request cache for translations, but the implementation uses
`functools.lru_cache(maxsize=128)`, which has NO time-based expiry. Entries are
evicted only by LRU pressure at 128 keys, never by age. Two consequences: (1) a
translation is cached indefinitely for the process lifetime, so a corrected
Google result (or a transiently-wrong fallback that got cached) is never
refreshed within the intended 5 minutes; (2) the cache is per-process (per
gunicorn worker), so hit rate and memory are inconsistent with a shared/expiring
cache. Also note SRH-001 interaction: on timeout the *original* query is
returned by `translate_query_bs_to_ru` but `translate_cached` itself is not what
fails — a slow-but-successful call still populates the cache.

**Evidence:**
- `query_translator.py:52-58` — `@lru_cache(maxsize=128)`; docstring claims
  "invalidated ... after 5 minutes" but no TTL mechanism exists.
- `docs/03-packages/packages-list.md:35` — "hard timeout ~500ms + fallback";
  spec/tech-spec references a request cache.

**Recommendation:** Either (a) use Django's cache framework with an explicit
`timeout=300` (shared across workers, real TTL), or (b) update the docstring/doc
to state the cache is an in-process LRU with no expiry if that is acceptable for
MVP. Prefer (a) for correctness/consistency; it also removes per-worker
duplication. Effort: small. Priority: recommended. `[DOC-UPDATE]` if (b) chosen.

---

### SRH-005: Raw buyer query strings written to application logs

| Field | Value |
|-------|-------|
| **ID** | SRH-005 |
| **Severity** | MEDIUM |
| **Type** | BEST-PRACTICE |
| **Affected Modules** | `src/backend/apps/search/views/search.py`, `src/backend/apps/search/services/query_translator.py` |
| **Classification** | advisory |

**Description:** Dimension (h) requires no identity values in logged query
strings. The search view and translator log the raw, unbounded, buyer-controlled
query string at INFO/WARNING/DEBUG level. While the analytics *table* correctly
stores only `event_type` + nullable `user_id` (no query text — good), the free-
text query is a channel through which a buyer can type PII (their own phone,
name, or a seller's) that then persists in log aggregation. Because buyers are
unauthenticated this is not the auditor's canonical "identity value", but it is
an uncontrolled PII sink and also a log-injection vector (newlines/control chars
in `q` are logged verbatim).

**Evidence:**
- `search.py:66` — `logger.info(f"Empty search results for query '{query}'")`.
- `query_translator.py:42,45,48` — logs `'{query}'` at debug/warning/info incl.
  the full failure path.

**Recommendation:** Do not log raw query text at INFO/WARNING in production. Log
a hash, length, or truncated/sanitized token, or gate verbose query logging
behind DEBUG only. Strip control characters before logging. Effort: trivial.
Priority: recommended.

---

### SRH-006: Overly broad exception handling masks real errors in translation path

| Field | Value |
|-------|-------|
| **ID** | SRH-006 |
| **Severity** | LOW |
| **Type** | BEST-PRACTICE |
| **Affected Modules** | `src/backend/apps/search/services/query_translator.py` |
| **Classification** | advisory |

**Description:** `except (TimeoutError, RequestException, Exception)` catches the
base `Exception`, making the two preceding, more-specific types redundant and
swallowing *all* programming errors (e.g. `TypeError`, attribute errors from a
changed `deep_translator` API) as "translation failure → fallback". This hides
real defects behind a silent degraded-recall path and complicates diagnosing why
search quietly stopped translating. It also imports `TimeoutError` from
`concurrent.futures`, which shadows the builtin — acceptable but worth an explicit
alias for clarity.

**Evidence:**
- `query_translator.py:44` — `except (TimeoutError, RequestException, Exception) as e:`.

**Recommendation:** Catch only the expected failure types
(`concurrent.futures.TimeoutError`, `RequestException`, and any specific
translator exception). If a broad catch is deliberately kept for resilience, log
it at ERROR (not warning) with a distinct message so genuine bugs surface.
Effort: trivial. Priority: recommended.

---

### SRH-007: Analytics event recorded before search executes / on translation failure

| Field | Value |
|-------|-------|
| **ID** | SRH-007 |
| **Severity** | LOW |
| **Type** | BEST-PRACTICE |
| **Affected Modules** | `src/backend/apps/search/views/search.py` |
| **Classification** | advisory |

**Description:** `SEARCH_PERFORMED` is written unconditionally at the top of the
`if query:` block, before translation and FTS execution. A DB write occurs on
every keystroke-driven request (the form uses `type="search"` with a submit
button so this is bounded, but still one INSERT per query request) and is
recorded even if the subsequent search errors. Minor metric-accuracy and write-
amplification concern; the event carries no query text so there is no PII
leakage here.

**Evidence:**
- `search.py:43-47` — `AnalyticsEvent.objects.create(...)` before
  `translate_query_bs_to_ru` and before the FTS filter.

**Recommendation:** Consider recording the event after a successful search, and/
or batching/deferring analytics writes off the request path if search volume
grows. Effort: trivial. Priority: optional.

---

### SRH-008: `pg_trgm` documented in FTS stack but never installed or used

| Field | Value |
|-------|-------|
| **ID** | SRH-008 |
| **Severity** | MEDIUM |
| **Type** | SPEC-DEVIATION |
| **Affected Modules** | `src/backend/apps/ads/migrations/`, `src/backend/apps/search/views/search.py`, `docs/02-database/db-schema.md`, `docs/03-packages/packages-list.md`, `docs/01-spec/spec-index.md` |
| **Classification** | advisory |

**Description:** Docs repeatedly specify the search stack as "TSVECTOR + GIN +
**pg_trgm**, russian config" (db-schema.md:27, packages-list.md:30/71,
spec-index.md:40, technical-specification). There is no `CREATE EXTENSION
pg_trgm` (no `TrigramExtension`/`CreateExtension` migration operation anywhere)
and no trigram similarity is used at query time. The actual fuzzy/typo behavior
for single-word category detection is Python `difflib.get_close_matches`
(`search.py:121-126`), which loads *all* active category names into the app on
every single-word query and does the matching in Python — not in the DB, not via
pg_trgm. Consequences: (1) the documented perf/scale story (dimension (g),
"GIN/trigram effectiveness") is not what runs; (2) the difflib path is O(n
categories) per query with a full-table read; (3) any future `%`/`similarity()`
query relying on pg_trgm would fail at runtime because the extension is absent.

**Evidence:**
- No matches for `pg_trgm | CreateExtension | TrigramExtension | TrigramSimilarity`
  under `src/`.
- `search.py:121-126` — `from difflib import get_close_matches` +
  `Category.objects.filter(is_active=True).values_list("name", flat=True)` loads
  all names, matches in Python (`cutoff=0.8`).
- Docs assert pg_trgm is part of the stack: `db-schema.md:27`,
  `packages-list.md:30`, `spec-index.md:40`.

**Recommendation:** Decide the intended design and align code+docs: either
(a) add the `pg_trgm` extension migration and move fuzzy category/city matching
to DB-side `TrigramSimilarity` (scales, single source, no full-table Python
load), or (b) if difflib is intentionally sufficient for ~30-50 categories,
remove pg_trgm from the FTS-stack docs to avoid a false operational assumption.
Effort: (a) medium / (b) trivial. Priority: recommended. `[DOC-UPDATE]` under (b).

---

### SRH-009: HTMX partial branch is a no-op (both branches render full page)

| Field | Value |
|-------|-------|
| **ID** | SRH-009 |
| **Severity** | LOW |
| **Type** | SPEC-DEVIATION |
| **Affected Modules** | `src/backend/apps/search/views/search.py`, `src/backend/apps/ads/views/listings.py`, `src/backend/templates/ads/list.html` |
| **Classification** | advisory |

**Description:** Both the search and listings views branch on
`request.headers.get("HX-Request")` but render the *same* full-page template
(`ads/list.html`, a complete `<!DOCTYPE html>` document) in both the HTMX and
non-HTMX branch. So an HTMX request receives an entire HTML page (with `<head>`,
scripts, consent banner) injected into a fragment target instead of a partial.
The intended "no full page reload (HTMX)" behavior (US-B3) is not achieved and
the branch is dead code. Not a security issue, but a correctness/UX and
maintainability gap in the search results zone.

**Evidence:**
- `search.py:74-78` — identical `render(request, "ads/list.html", context)` in
  both branches.
- `listings.py:164-168` — same duplicated pattern.
- `templates/ads/list.html:1-124` — single full-document template; no partial.

**Recommendation:** Extract the results grid into a partial
(e.g. `ads/_results.html`) and return it for `HX-Request`, keeping the full page
for normal requests; or remove the dead branch if HTMX partials are out of scope
for this phase (investigate intended behavior before deleting, per dead-code
policy). Effort: small. Priority: recommended.

---

## Summary

| Severity | Count |
|----------|-------|
| CRITICAL | 0 |
| HIGH | 3 |
| MEDIUM | 3 |
| LOW | 3 |

**Total findings:** 9 (SRH-001 .. SRH-009)

### Positive observations (not findings, context for validator)
- **Visibility gating is correct (dimension a).** Search filters on
  `status=AdStatus.PUBLISHED`, the same predicate as public listings. Withdrawal
  (`users/services/deletion.py:soft_delete_user_ads`) sets ads to `DELETED`, so
  withdrawn sellers' ads drop out via status. DECLINE
  (`users/services/consent.py` / `decline_consent`) only sets
  `ads_auto_publish=False` and never touches ads or sets `consent_revoked_at`, so
  DECLINEd sellers' PUBLISHED ads remain searchable — exactly as required. No
  separate consent filter exists in the search path.
- **Injection safety is sound (dimension d).** Query reaches the engine only via
  `SearchQuery(translated_query, search_type="websearch", config="russian")` and
  the ORM `filter(search_vector=search_query)`; no raw SQL, `.extra()`,
  `.raw()`, or string interpolation in the search path.
- **Index maintenance/freshness (dimension b)** is handled by the BEFORE
  INSERT/UPDATE trigger `ads_search_vector_fn` and category-rename propagation
  `categories_name_propagate`, with a backfill in migration 0002; covered by
  `apps/ads/tests/test_search_triggers.py` (insert/update/rename/rank/exclude).

## Mandatory Fixes
- **SRH-001** (HIGH) — Translation timeout does not bound request latency;
  `with`-managed executor blocks on shutdown. Latency SLO / availability.
- **SRH-002** (HIGH) — Single-word category match omits descendants; divergent
  from listings subtree expansion. Result correctness.
- **SRH-003** (HIGH) — No pagination/limit; unbounded result set. DoS / latency.

## Advisory Recommendations
- **SRH-004** (MEDIUM) — `lru_cache` has no TTL vs. documented 5-min cache.
- **SRH-005** (MEDIUM) — Raw buyer query logged (PII sink / log injection).
- **SRH-006** (LOW) — Overly broad `except Exception` in translation path.
- **SRH-007** (LOW) — Analytics event written before search runs.
- **SRH-008** (MEDIUM) — pg_trgm documented but never installed/used (difflib).
- **SRH-009** (LOW) — HTMX branch renders full page (no-op partial).

## Doc Updates Needed
- **SRH-004** — If in-process LRU-without-TTL is accepted, update translator
  docstring + `packages-list.md` to stop claiming a 5-minute cache.
- **SRH-008** — If difflib is the intended fuzzy mechanism, remove `pg_trgm`
  from the FTS-stack description in `db-schema.md`, `packages-list.md`, and
  `spec-index.md`; otherwise add the extension migration and use it.

## Runtime Verification Status
Runtime checks (§4) were NOT completed: DB-backed search tests require a live
PostgreSQL (`russian` FTS config is PG-only) and the `uv run pytest` invocation
for `test_search_triggers.py` exceeded the 180s tool timeout with no local DB
brought up in this environment. All findings above are grounded in static
evidence (source, migrations, templates, docs). Recommended follow-up for the
validator: bring up `docker compose` (web+bot+db), seed synthetic PII-free ads
across statuses/categories, and execute §4 items 1-9, with particular attention
to SRH-001 (patch translator to sleep, assert bounded latency) and SRH-003
(seed volume, assert bounded/paginated results).
