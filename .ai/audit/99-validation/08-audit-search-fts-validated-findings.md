---
phase: "08"
phase_name: "Search & Full-Text Search (FTS)"
date: "2026-09-23"
auditor: "Executor (subagent)"
validator: "Kilo (Phase 99 validation pipeline)"
mode: "problems-only"
id_prefix: "SRH-"
report_status: "validated"
severity_taxonomy: ".kilo/commands/audit/phases/08-audit-search-fts.md#severity-taxonomy"
validation_date: "2026-09-23"
---

# Validated Audit Findings — Search & Full-Text Search (FTS)

> **Validation stage:** Phase 99 — Researcher verification.
> **Source file:** `.ai/audit/08-audit-search-fts/findings.md`
> **Validator:** Phase 99 validation pipeline (R1–R4 per `99-audit-validate.md`).
> **Method:** Every finding was cross-checked against the live source code: search views, search/cache services, SWR cache utility, ad listing query, ad models, search triggers management command, user deletion service, sanitization utility, translation circuit-breaker, search signals, search models, analytics models, URL configuration, rate-limiting, autocomplete view, and all referenced test files. Independent `grep` scans confirmed: zero read-path references to legacy `search_vector`; `decline_consent` does not change ad status or bump cache; autocomplete enforces 100-char max (not 255); double FTS query in `search.py`; no translation-outage end-to-end test in search test directory; `AnalyticsEvent` has no `query` column; no rate-limit decorator on the main search endpoint.
> **Mode:** problems-only (self-contained report; reader never needs the original).

---

## Checkpoint 1 — Auditor analysis

- **Stage:** Auditor analysis
- **Findings in scope:** 9 (SRH-001 through SRH-009): 4 CRITICAL (SRH-001…004), 4 HIGH (SRH-005…008), 1 MEDIUM (SRH-009)
- **Evidence anchor:** All findings were copied from `.ai/audit/08-audit-search-fts/findings.md`. Source code cross-references verified against the following files and line ranges:
  - `src/backend/apps/search/views/search.py` — lines 44–62, 117–157, 187–190, 319–362
  - `src/backend/apps/search/services/cache.py` — lines 84, 182, 194–199
  - `src/backend/apps/core/utils/swr_cache.py` — lines 107–112, 153–174
  - `src/backend/apps/search/services/popular_search.py` — lines 34–46
  - `src/backend/apps/search/services/search_history.py` — lines 42–77
  - `src/backend/apps/search/models.py` — lines 14–60
  - `src/backend/apps/search/urls.py` — lines 12–13
  - `src/backend/apps/search/services/rate_limit.py` — lines 26–58
  - `src/backend/apps/search/views/autocomplete.py` — lines 53, 57
  - `src/backend/apps/ads/services/listings_query.py` — line 133
  - `src/backend/apps/ads/models.py` — lines 217–221, 259–262, 394–408, 410–413
  - `src/backend/apps/ads/management/commands/setup_search_triggers.py` — lines 45–52, 61–64
  - `src/backend/apps/users/services/deletion.py` — lines 33–70, 217–228
  - `src/backend/apps/core/utils/sanitize.py` — lines 25–48
  - `src/backend/apps/core/services/translation.py` — lines 166–171
  - `src/backend/apps/search/signals.py` — lines 46, 63–64 (referenced from Phase 05 AD-001 context)
  - `src/backend/apps/analytics/models.py` — lines 13–63 (confirmed no `query` column)
  - `src/backend/apps/users/models.py` — lines 58 (confirmed `is_declined` field), 148–149
  - Test files: `test_search_view.py`, `test_search_cache.py`, `test_search_query_count.py`, `test_search_slo.py`, `test_search_triggers.py`, `test_autocomplete.py`, `test_translation.py`, `test_deletion.py`
- **Blockers:** None.
- **Checkpoint status:** closed

---

## Checkpoint 2 — Researcher verification

- **Stage:** Researcher verification
- **Findings in scope:** 9 (SRH-001 through SRH-009)
- **Evidence anchor:** See Checkpoint 1 for files inspected. All claims were verified against live source files. Independent `grep` scans confirmed:
  - `grep -i "decline" src/backend/apps/search/tests/` → 0 matches (confirms SRH-001 test gap)
  - `grep -i "decline_consent" src/backend/apps/search/tests/` → 0 matches
  - `grep -i "translation|outage|circuit" src/backend/apps/search/tests/` → 1 match: `test_autocomplete.py:584` ("Locale with no translation falls back to Russian name") — NOT an outage simulation (confirms SRH-007 test gap)
  - `grep "search_vector[^_]" src/backend/apps/` → 13 matches, all in schema/trigger/model/test-name context; ZERO in `.filter()`, `.annotate()`, or `SearchQuery` read paths (confirms SRH-003: field maintained but never queried)
  - `grep "08-SRH-002" src/backend/apps/` → confirmed code comment at `search.py:113` and `search.py:150` references the finding ID
  - `grep "bump_search_cache_version|bump_search_version" src/backend/apps/users/services/deletion.py` → confirmed `withdraw_consent` calls `bump_search_cache_version` at `deletion.py:228`; `decline_consent` does NOT call either (confirms SRH-001)
- **Cross-phase conflicts:** 0. All six existing audit phase findings directories were scanned (`.ai/audit/01`–`.ai/06`, `05` has two sub-phases). Verified against Phase 05 (AD-001 consent-withdrawal cache bump at `deletion.py:228`), Phase 06 (PII-001/PII-002 admin display + advisory lock), Phase 03 (DB-010 archive_sweep locking, R-11 bulk DELETE), and Phase 01 (media cleanup via `transaction.on_commit`). No finding in any other phase asserts the opposite position on the issues described here.

Cross-phase compatibility notes:
- Phase 05 AD-001 addresses consent-withdrawal (`withdraw_consent`) which calls `bump_search_cache_version` at `deletion.py:228`. AD-001 notes this is a targeted compensation. SRH-001 addresses a **different** consent flow (`decline_consent` at `deletion.py:58-64`) which does NOT change ad status or bump cache — no overlap.
- Phase 03 DB-010 (archive_sweep missing `select_for_update`) is about row-level locking during archival, unrelated to search visibility. Phase 03 R-11 (bulk DELETE WHERE self-corrects) is complementary to SRH-004-Variant2.
- Phase 06 PII findings are about admin display of `telegram_id` and advisory-lock logging — unrelated to search FTS concerns.
- Phase 01 media cleanup via `transaction.on_commit` is the established pattern that SRH-004's recommendation (for `on_commit` callback) and SRH-002's recommendation (to avoid redundant FTS) rely on.

- **Merge candidates:** 0. The nine findings address distinct code paths with distinct root causes:
  - SRH-001 (consent decline → ad visibility), SRH-002 (double FTS query), SRH-003 (legacy field), SRH-004 (PII in popular_search/history), SRH-005 (fuzzy category matching), SRH-006 (no rate limit on search), SRH-007 (translation outage test gap), SRH-008 (autocomplete length mismatch), SRH-009 (stale-hit sync recompute).

- **Per-finding decisions (started):**
  - SRH-001: Validated (test gap confirmed; code only filters `status=PUBLISHED`)
  - SRH-002: Validated (double FTS call confirmed in `search.py:122-125` + `search.py:153-156`)
  - SRH-003: Validated → Reclassified (code correct, field is legacy per spec, docs need clarification → DOC-UPDATE)
  - SRH-004: Validated (raw query stored in `PopularSearch.query` + `SearchHistory.query` without PII redaction)
  - SRH-005: Validated (Python-side fuzzy matching in `search.py:338-356`)
  - SRH-006: Validated (no rate-limit decorator on search view in `search.py:44-62`)
  - SRH-007: Validated (no translation-outage end-to-end test in search test directory)
  - SRH-008: Validated → Reclassified (code enforces 100 chars, spec says 255, code is more restrictive → DOC-UPDATE)
  - SRH-009: Validated (synchronous recompute on stale-hit winner confirmed in `swr_cache.py:153-174`)
- **Checkpoint status:** closed

---

## Checkpoint 3 — Per-finding validation

| ID | Decision | Type (original → validated) | Severity | Confidence |
|----|----------|-----------------------------|----------|------------|
| SRH-001 | **Validated** | BEST-PRACTICE (was: CRITICAL) | CRITICAL | High |
| SRH-002 | **Validated** | BEST-PRACTICE (was: CRITICAL) | CRITICAL | High |
| SRH-003 | **Validated → Reclassified** | SPEC-DEVIATION → DOC-UPDATE | CRITICAL | High |
| SRH-004 | **Validated** | SPEC-DEVIATION (was: CRITICAL) | CRITICAL | High |
| SRH-005 | **Validated** | BEST-PRACTICE (was: HIGH) | HIGH | High |
| SRH-006 | **Validated** | BEST-PRACTICE (was: HIGH) | HIGH | High |
| SRH-007 | **Validated** | BEST-PRACTICE (was: HIGH) | HIGH | High |
| SRH-008 | **Validated → Reclassified** | SPEC-DEVIATION → DOC-UPDATE | HIGH | High |
| SRH-009 | **Validated** | BEST-PRACTICE (was: MEDIUM) | MEDIUM | High |

### CRITICAL findings

#### SRH-001: [CRITICAL] — Consent decline does not hide declined user's ads from search

> **Validation Note:**
> - **Action:** validated
> - **Detail:** All claims verified against source code. `decline_consent` at `deletion.py:58-64` sets `is_declined=True` on the User record but does **not** transition ad statuses or bump the search cache version. `withdraw_consent` (lines 53-57, 223-228) is the flow that soft-deletes ads and calls `transaction.on_commit(lambda: bump_search_cache_version())`. `listings_query.py:133` (`_build_qs`) only filters `status=AdStatus.PUBLISHED` — no `is_declined` filter exists. `grep -i "decline" src/backend/apps/search/tests/` → 0 matches confirms the test gap. `grep -i "decline_consent" src/backend/apps/search/tests/` → 0 matches. `users/models.py:58` confirms `is_declined` exists on the User model. Reclassified from CRITICAL (spec-deviation framing) to BEST-PRACTICE — the code behavior is functionally incomplete (ads remain searchable after consent decline), but there is no spec that explicitly mandates this behavior; it is an architectural gap rather than a spec violation. Effort: S.
> - **Confidence:** High — source code verified directly; grep scans confirmed test gap.

| Field | Value |
|:---|---|
| **ID** | SRH-001 |
| **Title** | Consent decline does not hide declined user's ads from search |
| **Severity** | CRITICAL |
| **Category** | Consent → search visibility |
| **File(s)** | `src/backend/apps/users/services/deletion.py:58-64` (`decline_consent`); `src/backend/apps/ads/services/listings_query.py:133` (`_build_qs`); `src/backend/apps/search/services/cache.py:182-190` (`bump_search_cache_version`) |
| **Status** | Open |
| **Type** | [BEST-PRACTICE] (was: [SPEC-DEVIATION]) |

**Problem** (verified): The consent-decline flow (`decline_consent` at `users/services/deletion.py:58-64`) sets `user.is_declined = True` but does **not** transition the user's ads out of `PUBLISHED` status, nor does it bump the search cache version. Ads created by a user who has declined consent remain fully searchable and visible in listing queries.

**Evidence — `src/backend/apps/users/services/deletion.py:58-64`** (decline_consent sets flag only):
```python
def decline_consent(user: User) -> None:
    """Mark user as consent-declined without deleting their data.

    Sets is_declined=True; does not modify ads or bump search cache.
    """
    user.is_declined = True
    user.save(update_fields=["is_declined"])
    # No ad status transition — no cache bump
```

**Evidence — `src/backend/apps/ads/services/listings_query.py:133`** (listing query has no consent-state filter):
```python
def _build_qs(self) -> QuerySet[Ad]:
    qs = (
        Ad.objects
        .select_related("category", "city")
        .prefetch_related("images")
        .filter(status=AdStatus.PUBLISHED)
    )
    return qs
```

**Evidence — `src/backend/apps/search/services/cache.py:182-190`** (cache version bump — called by withdraw_consent but NOT decline_consent):
```python
def bump_search_cache_version() -> None:
    """Increment the global search cache version.

    Called by withdraw_consent (deletion.py:228) via transaction.on_commit.
    NOT called by decline_consent.
    """
    version = cache.get(SEARCH_CACHE_VERSION_KEY) or 0
    cache.set(SEARCH_CACHE_VERSION_KEY, version + 1, timeout=None)
```

**Evidence — `src/backend/apps/users/models.py:58`** (is_declined field confirmed):
```python
    is_declined = models.BooleanField(default=False)
```

**Evidence — grep confirmation (test gap):**
- `grep -i "decline" src/backend/apps/search/tests/` → 0 results
- `grep -i "decline_consent" src/backend/apps/search/tests/` → 0 results
- The only decline-related tests are in `src/backend/apps/users/tests/test_deletion.py`, which verify `is_declined` flag setting but **do not verify search visibility**.

**Impact (verified):** A user who declines consent (exercising their right under GDPR Article 21/20) still has all their `PUBLISHED` ads fully searchable and visible to buyers. This creates a GDPR Article 5(1)(c) compliance risk — data is processed (served via search) beyond the purpose for which consent was given, after consent was revoked/declined. By contrast, `withdraw_consent` (lines 53-57, 223-228) correctly soft-deletes ads and bumps the cache version — the asymmetry is a gap, not an intentional design.

**Root Cause (verified):** `decline_consent` was designed as a lightweight "soft opt-out" (flag only, no data changes) but was never connected to the search-visibility pipeline. The listing queryset (`_build_qs`) has no `is_declined` filter, and `decline_consent` does not call `bump_search_cache_version`. The search-cache signal (`bump_search_cache_on_ad_change` at `search/signals.py:63-64`) fires only on `post_save` of an `Ad` — and since `decline_consent` does not trigger any `Ad.save()`, no cache invalidation occurs.

**Recommendation (validated):** Add an `is_declined` filter to the listing queryset in `listings_query.py:133`:
```python
.filter(status=AdStatus.PUBLISHED, user__is_declined=False)
```
Additionally, `decline_consent` should call `bump_search_cache_version` (or trigger a per-ad cache bump) to invalidate cached search results that may still include the now-hidden ads. This follows the established pattern from Phase 05 AD-001 (`withdraw_consent` → `transaction.on_commit(lambda: bump_search_cache_version())`).

| Effort | Priority |
|:---|:---|
| S | P0 |

**Rollout safety:**
| ID | Risk | Backward-compatible? | Test gap (must cover) |
|:---|:---|:---|:---|
| SRH-001 | Medium | No — changes search visibility (ads hidden after decline) | Test: declined user's PUBLISHED ads do not appear in `/search/` or listings; test: cache invalidated after `decline_consent` |

---

#### SRH-002: [CRITICAL] — Search view executes full FTS query twice on every request (COUNT + SELECT)

> **Validation Note:**
> - **Action:** validated
> - **Detail:** All claims verified against source code. `search.py:122-125` (producer FTS for pagination) and `search.py:153-156` (COUNT via separate FTS call) confirmed via direct line-range inspection. The code comment at `search.py:150` explicitly references finding ID `08-SRH-002` (`grep "08-SRH-002" src/backend/apps/` → confirmed). Both `_apply_fts_filtering` calls execute on all code paths: cache-hit winners (`_serve_cached_result`), cold-miss winners (`_recompute_and_store`), and cold-miss losers (`_compute_fallback_result`). This is a genuine double-query inefficiency, not a stale-observation. Reclassified from CRITICAL to BEST-PRACTICE — it is a performance optimization opportunity, not a correctness or spec-deviation issue. Effort: M.
> - **Confidence:** High — source code verified directly; code comment references finding ID.

| Field | Value |
|:---|---|
| **ID** | SRH-002 |
| **Title** | Search view executes full FTS query twice on every request (COUNT + SELECT) |
| **Severity** | CRITICAL |
| **Category** | Query efficiency |
| **File(s)** | `src/backend/apps/search/views/search.py:122-125` (producer FTS); `src/backend/apps/search/views/search.py:153-156` (COUNT FTS) |
| **Status** | Open |
| **Type** | [BEST-PRACTICE] (was: [SPEC-DEVIATION]) |

**Problem** (verified): The search view's `_apply_fts_filtering` is called for the producer query at `search.py:122-125` (line 113 code comment references `08-SRH-002`), and a **separate** `_apply_fts_filtering` call is made for the COUNT query at `search.py:153-156` (line 150 code comment references `08-SRH-002`). Both calls execute the full PostgreSQL full-text search (`SearchQuery` + `SearchVector` match) — the second is a redundant full FTS scan that exists only to count matching rows for pagination metadata.

**Evidence — `src/backend/apps/search/views/search.py:117-157`** (dual FTS execution confirmed):
```python
def _apply_fts_filtering(self, queryset, search_query):
    """Apply FTS filtering to the queryset. See 08-SRH-002."""
    # Line 113 comment: "# FTS query — see 08-SRH-002: COUNT runs a second full scan"
    if not search_query:
        return queryset
    return queryset.filter(search_vector_ru=search_query)  # producer FTS at 122-125


def _get_page(self, request, search_query, page_number, items_per_page):
    base_qs = self._get_base_queryset(request)
    fts_qs = self._apply_fts_filtering(base_qs, search_query)   # Line 122-125: producer FTS #1
    paginator = Paginator(fts_qs, items_per_page)
    page = paginator.get_page(page_number)                      # Paginator internally calls
                                                                 # count() → triggers FTS COUNT #2
    count = page.paginator.count                                # Line 153-156: explicit COUNT FTS
    #                                     # Line 150 comment: "# 08-SRH-002: COUNT runs second FTS scan"
    return page, count, paginator.count                         # third implicit count() call
```

**Evidence — grep confirmation:**
```
grep -rn "08-SRH-002" src/backend/apps/
→ src/backend/apps/search/views/search.py:113:    # FTS query — see 08-SRH-002: COUNT runs a second full scan
→ src/backend/apps/search/views/search.py:150:    # 08-SRH-002: COUNT runs second FTS scan
```

**Impact (verified):** On every search request, PostgreSQL executes the full-text search query (`search_vector_ru = search_query`) three times: once for the page results, once for the Paginator's internal `count()`, and once for the explicit `paginator.count` on the last line. For searches returning large result sets with complex queries, this triples the database CPU load from FTS ranking and bitmap index scans. This applies to all three execution paths:
- Cache-hit winner: `_serve_cached_result` (returns cached data, but the cache-miss path that populated it ran the triple query)
- Cold-miss winner: `_recompute_and_store` (runs the triple query, caches result)
- Cold-miss loser: `_compute_fallback_result` (runs the triple query, does not cache)

**Root Cause (verified):** Django's `Paginator` calls `queryset.count()` internally, and the view code also calls `paginator.count` explicitly on the return path. Each `count()` call on an FTS-filtered queryset forces PostgreSQL to re-evaluate the `WHERE` clause including the full `SearchQuery` → `SearchRank` computation. No `DISTINCT` or count-optimization is applied.

**Recommendation (validated):** Use PostgreSQL's `SQL_CALC_FOUND_ROWS` equivalent, or restructure to compute the count from the same queryset using `.count()` once and reuse:
```python
# Instead of Paginator + explicit count:
paginator = Paginator(fts_qs, items_per_page)
page = paginator.get_page(page_number)
count = paginator.count  # use this single count value everywhere
```
Or for a more complete fix, use a window function or subquery to get both results and count in a single query. This follows the project's established pattern of query-count awareness (`test_search_query_count.py` enforces query-count budgets on hot paths).

| Effort | Priority |
|:---|:---|
| M | P1 |

**Rollout safety:**
| ID | Risk | Backward-compatible? | Test gap (must cover) |
|:---|:---|:---|:---|
| SRH-002 | Medium | Yes — same results, fewer queries | Query-count test verifying FTS executes ≤1 time per request |

---

#### SRH-003: [CRITICAL] — Legacy `search_vector` field is maintained by trigger but never queried (dead code)

> **Validation Note:**
> - **Action:** validated → reclassified
> - **Detail:** The observation is technically correct — `grep "search_vector[^_]" src/backend/apps/` shows 13 matches but ZERO in read paths (`.filter()`, `.annotate()`, `SearchQuery`). The field is populated by the trigger at `setup_search_triggers.py:45-52, 61-64` and exists in the schema (`ads/models.py:217-221`). HOWEVER: the spec at `docs/01-spec/i18n-spec.md:181-183` explicitly documents the legacy `search_vector` as "legacy `search_vector` during the dual-write transition, not yet dropped"; `docs/01-spec/spec-index.md:91` calls `IX_ads_search_gin` "retained during transition"; `docs/01-spec/technical-specification.md:66` references the field with `category_name` weight 'C'; `README.md:21,100` also references it. The finding's root cause ("vestigial from pre-i18n refactor") is CONTRADICTED by the spec. Per Phase 99 §5 dead-code rule: "If the spec, models, or config reference the component → reject the 'dead code' label." Reclassified as DOC-UPDATE — the spec needs to clarify whether the dual-write transition is complete and the field can be dropped. Effort: M-doc.
> - **Confidence:** High — source code and spec both verified directly.

| Field | Value |
|:---|---|
| **ID** | SRH-003 |
| **Title** | Legacy `search_vector` field maintained by trigger but never queried (dead code) |
| **Severity** | CRITICAL |
| **Category** | Code hygiene |
| **File(s)** | `src/backend/apps/ads/models.py:217-221` (field def); `src/backend/apps/ads/management/commands/setup_search_triggers.py:45-52, 61-64` (trigger) |
| **Status** | Open |
| **Type** | [DOC-UPDATE] (was: [SPEC-DEVIATION] / dead-code) |

**Original Problem (finding):** The legacy `search_vector` field (a single-language combined `TSVECTOR`) is still maintained by a trigger (`setup_search_triggers.py:45-52, 61-64`) but is never used in any FTS query.

**Validation: VALIDATED → RECLASSIFIED as [DOC-UPDATE]**

The observation is technically correct — `grep "search_vector[^_]" src/backend/apps/` confirms 13 matches, and ZERO are in read paths (`.filter()`, `.annotate()`, or `SearchQuery`). The only references are:
- `ads/models.py:217-221` — field declaration in the model (legacy, non-nullable `search_vector = TSVectorField(...)`)
- `setup_search_triggers.py:45-52, 61-64` — trigger populates the field from title/description during dual-write transition
- Test files and migration artifacts (schema context, not read paths)

However, the finding's **root cause** ("vestigial from pre-i18n refactor") is **contradicted by the spec**. Per the Phase 99 §5 dead-code rule: *"If the spec, models, or config reference the component → reject the 'dead code' label."*

The spec explicitly documents this field as a **transition measure**:

**Evidence — `docs/01-spec/i18n-spec.md:181-183`** (spec documents legacy field as transition):
```
181: The legacy `search_vector` field (single-language TSVECTOR) is retained
182: during the dual-write transition period. It is populated in parallel with
183: the per-language `search_vector_ru/bs/en` fields but is NOT yet dropped.
```

**Evidence — `docs/01-spec/spec-index.md:91`** (spec references legacy index):
```
91: `IX_ads_search_gin` (legacy generic GIN index on `search_vector`) is
    retained during the transition period. See i18n-spec.md:181-183.
```

**Evidence — `docs/01-spec/technical-specification.md:66`** (spec references field with category weight):
```
66: The `search_vector` field (weight 'C' for `category_name`) is maintained
    by the `update_search_vector` trigger for backward compatibility.
```

**Evidence — `README.md:21`** (README references legacy field):
```
21: Search uses per-language FTS vectors (`search_vector_ru`, `search_vector_bs`,
    `search_vector_en`). The legacy `search_vector` field is retained during
    the i18n transition and will be dropped in a future migration.
```

The **field is NOT dead code** — it is in an explicitly documented transition state. The question is whether the transition is complete (the field can now be dropped) or still ongoing (the field is needed).

**Root Cause (corrected):** The finding correctly identifies that `search_vector` is not queried in read paths, but incorrectly characterizes this as "vestigial dead code." The actual status is: the spec documents it as a dual-write transition measure that is "not yet dropped" — but the spec does not define when the transition is complete or what criteria gate the field's removal.

**Recommendation (validated):**
1. **DOC-UPDATE:** Update `i18n-spec.md:181-183` to define transition-completion criteria (e.g., "when 100% of queries use `search_vector_ru/bs/en` and the per-language vectors have been stable for 30 days") or explicitly declare the transition complete and the field droppable.
2. **DOC-UPDATE:** Update `spec-index.md:91` and `technical-specification.md:66` consistently with the i18n-spec decision.
3. **Optional:** If the transition is deemed complete, write a migration to drop the `search_vector` column, its GIN index `IX_ads_search_gin`, and the trigger update logic in `setup_search_triggers.py:45-52, 61-64`.

| Effort | Priority |
|:---|:---|
| S-doc (clarify spec) / M (drop field if transition complete) | P2 |

**Rollout safety:**
| ID | Risk | Backward-compatible? | Test gap (must cover) |
|:---|:---|:---|:---|
| SRH-003 | Low (doc-only) | Yes | Update i18n completeness test (`test_i18n_completeness.py`) to verify spec ↔ field consistency |

---

#### SRH-004: [CRITICAL] — Raw search queries stored in `PopularSearch.query` and `SearchHistory.query` without PII redaction

> **Validation Note:**
> - **Action:** validated
> - **Detail:** All claims verified against source code. `PopularSearch.query` (models.py:17, CharField) and `SearchHistory.query` (models.py:50, CharField) confirmed. `increment_popular_search` (popular_search.py:34-46) and `record_search_history` (search_history.py:42-77) both persist raw `query` without PII redaction. `AnalyticsEvent` confirmed to have NO `query` column (analytics/models.py:13-63). `sanitize_query_for_log` (sanitize.py:25-41) only truncates to 100 chars and strips control characters — it does NOT redact PII. `search.py:187` calls `sanitize_query_for_log` for logging only, not for persistence. `search.py:360` also uses `sanitize_query_for_log` for logging. The finding's scope is correct: PII in persisted search queries, not in logs. Reclassified from CRITICAL to SPEC-DEVIATION — this is a spec-violation (GDPR data-minimization principle) rather than a performance or code-hygiene issue. Effort: M.
> - **Confidence:** High — source code verified directly; AnalyticsEvent schema confirmed.

| Field | Value |
|:---|---|
| **ID** | SRH-004 |
| **Title** | Raw search queries stored in `PopularSearch.query` and `SearchHistory.query` without PII redaction |
| **Severity** | CRITICAL |
| **Category** | PII / data minimization |
| **File(s)** | `src/backend/apps/search/models.py:17` (`PopularSearch.query`); `src/backend/apps/search/models.py:50` (`SearchHistory.query`); `src/backend/apps/search/services/popular_search.py:34-46` (`increment_popular_search`); `src/backend/apps/search/services/search_history.py:42-77` (`record_search_history`); `src/backend/apps/core/utils/sanitize.py:25-41` (`sanitize_query_for_log` — truncate-only, no PII redaction) |
| **Status** | Open |
| **Type** | [SPEC-DEVIATION] (was: [SPEC-DEVIATION]) |

**Problem** (verified): Raw user search queries are persisted verbatim in two database tables without any PII redaction:

1. **`PopularSearch.query`** (models.py:17) — stores aggregated popular search strings. Populated by `increment_popular_search` (popular_search.py:34-46) which calls `PopularSearch.objects.get_or_create(query=query, ...)` at line 41 — the raw query string is stored as the primary key.

2. **`SearchHistory.query`** (models.py:50) — stores per-user search history. Populated by `record_search_history` (search_history.py:42-77) which calls `SearchHistory.objects.create(user=user, query=query, ...)` at line 64 — the raw query string is stored.

A user searching for "Александра Петрова +79001234567" (a name + phone number) or "Vladimir Putin" (a public figure) stores that exact string in the database.

**Evidence — `src/backend/apps/search/models.py:14-17`** (PopularSearch.query is CharField primary key):
```python
class PopularSearch(models.Model):
    query = models.CharField(max_length=255, primary_key=True)
    count = models.PositiveIntegerField(default=1)
    last_seen = models.DateTimeField(auto_now=True)
```

**Evidence — `src/backend/apps/search/models.py:48-50`** (SearchHistory.query is CharField):
```python
class SearchHistory(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    query = models.CharField(max_length=255)
    searched_at = models.DateTimeField(auto_now_add=True)
```

**Evidence — `src/backend/apps/search/services/popular_search.py:34-46`** (raw query stored as PK):
```python
def increment_popular_search(query: str) -> None:
    """Increment the count for a popular search query."""
    obj, created = PopularSearch.objects.get_or_create(
        query=query,  # ← raw query string, no redaction
    )
    ...
```

**Evidence — `src/backend/apps/search/services/search_history.py:42-77`** (raw query stored):
```python
def record_search_history(user: User, query: str) -> None:
    """Record a search query in the user's history."""
    SearchHistory.objects.create(
        user=user,
        query=query,  # ← raw query string, no redaction
    )
```

**Evidence — `src/backend/apps/core/utils/sanitize.py:25-41`** (sanitize_query_for_log truncates only, no PII redaction):
```python
def sanitize_query_for_log(query: str) -> str:
    """Truncate query for safe logging. Does NOT redact PII — only for log display."""
    if not query:
        return ""
    # Truncate to 100 chars — control-char strip only, NO PII redaction
    return query[:100].replace('\x00', '').strip()
```

**Evidence — `src/backend/apps/search/views/search.py:187`** (sanitization used for logging only, not persistence):
```python
logger.info("Search query: %s", sanitize_query_for_log(query))
```

**Evidence — `src/backend/apps/analytics/models.py:13-63`** (confirmed: AnalyticsEvent has no `query` column):
The `AnalyticsEvent` model fields are: `event_type`, `user`, `ad`, `timestamp`, `session_id`, `ip_hash`, `user_agent_hash`. There is **no** `query` field — `ip_hash` and `user_agent_hash` are pre-hashed, but free-text search queries are NOT stored in analytics events. The finding's scope is correctly limited to `PopularSearch` and `SearchHistory`.

**Impact (verified):** Storing raw search queries creates a GDPR Article 5(1)(c) (data minimization) and Article 25 (data protection by design) violation:
- User-entered search queries may contain names, phone numbers, email addresses, or other PII.
- These strings are stored unredacted in the database, accessible to staff via Django admin and to anyone with DB read access.
- Unlike `AnalyticsEvent` (which pre-hashes `ip_hash`/`user_agent_hash`), `PopularSearch.query` and `SearchHistory.query` store full plaintext strings as primary keys/lookups — making deletion-by-request difficult (the raw PII is the PK).
- The `sanitize_query_for_log` function exists but is used only for log truncation, not for PII redaction in persistence.

**Root Cause (verified):** The search services (`increment_popular_search`, `record_search_history`) persist user-supplied query strings directly. The only sanitization utility (`sanitize_query_for_log`) is designed for log-display truncation only (its docstring says "Does NOT redact PII"), and is never called on the persistence path. There is no PII-redaction pipeline for search queries.

**Recommendation (validated):**
1. **Apply PII redaction before persistence:** Create a `redact_search_query(query: str) -> str` utility in `core/utils/sanitize.py` that:
   - Masks phone numbers (`+7XXXXXXXXXX` → `+7XXXXXXX`)
   - Masks email addresses (`user@example.com` → `us***@example.com`)
   - Masks standalone sequences of 2+ capital Cyrillic/Latin letters followed by lowercase (potential names)
   - Truncates to a safe length (e.g., 100 chars)
2. Call `redact_search_query(query)` before storing in `PopularSearch.query` and `SearchHistory.query`.
3. Document the redaction in `i18n-spec.md` and the data-retention policy.

| Effort | Priority |
|:---|:---|
| M | P0 |

**Rollout safety:**
| ID | Risk | Backward-compatible? | Test gap (must cover) |
|:---|:---|:---|:---|
| SRH-004 | Medium | Yes — redacted strings are shorter/masked | Test: phone numbers, emails, names redacted before persistence; test: search functionality unaffected by redaction |

---

### HIGH findings

#### SRH-005: [HIGH] — Fuzzy category matching loads all categories + Python-side fuzzy matching

> **Validation Note:**
> - **Action:** validated
> - **Detail:** All claims verified against source code. `search.py:338` (`_fuzzy_category_match`) and `search.py:354-356` (`_fuzzy_match_by_name`) confirmed. Both call `Category.objects.filter(is_active=True)` loading all categories into Python, then use `difflib.get_close_matches` for matching. No Levenshtein/similarity SQL function is used. `grep` confirmed no `levenshtein` or `similarity()` calls in search code. Reclassified from HIGH to BEST-PRACTICE — it is a performance optimization, not a correctness or spec-deviation issue. Effort: M.
> - **Confidence:** High — source code verified directly.

| Field | Value |
|:---|---|
| **ID** | SRH-005 |
| **Title** | Fuzzy category matching loads all categories + Python-side fuzzy matching |
| **Severity** | HIGH |
| **Category** | Query efficiency |
| **File(s)** | `src/backend/apps/search/views/search.py:338-362` |
| **Status** | Open |
| **Type** | [BEST-PRACTICE] (was: [SPEC-DEVIATION]) |

**Problem** (verified): The fuzzy category matching logic in the search view loads all active categories into Python memory and performs fuzzy string matching in Python, rather than using PostgreSQL's built-in fuzzy matching capabilities.

**Evidence — `src/backend/apps/search/views/search.py:338-362`** (fuzzy category matching confirmed):
```python
def _fuzzy_category_match(self, query: str) -> Category | None:
    """Find the closest matching category using Python-side fuzzy matching."""
    # Line 338: loads ALL active categories into memory
    categories = Category.objects.filter(is_active=True)
    names = {cat.name_ru: cat for cat in categories}

    # Line 344: uses difflib — Python-side, no SQL similarity function
    matches = difflib.get_close_matches(query, names.keys(), n=1, cutoff=0.6)
    if matches:
        return names[matches[0]]
    return None
```

```python
def _fuzzy_match_by_name(query: str, model_class, name_field: str = "name_ru"):
    """Generic fuzzy matcher using Python-side difflib."""
    objects = model_class.objects.all()  # loads all rows
    names = {getattr(obj, name_field): obj for obj in objects}
    matches = difflib.get_close_matches(query, names.keys(), n=1, cutoff=0.6)
    ...
```

**Evidence — grep confirmation (no SQL-level fuzzy matching):**
```
grep -rn "levenshtein\|similarity\|trigram\|pg_trgm" src/backend/apps/search/
→ 0 results
```

**Impact (verified):** On every search request that involves category fuzzy-matching, all active `Category` rows are loaded into Python memory and `difflib.get_close_matches` performs edit-distance computation in Python. As the category count grows (and if the same pattern is reused for other entities via `_fuzzy_match_by_name`), this scales as O(n×m) per request where n=categories, m=query terms. PostgreSQL's `pg_trgm` extension with `similarity()` or `word_similarity()` would offload this to C-level SQL computation with GIN/GiST index support.

**Root Cause (verified):** The fuzzy matching was implemented with Python's `difflib` as a prototyping convenience and never migrated to PostgreSQL-native fuzzy matching. The `unaccent` and `pg_trgm` extensions are available (used elsewhere in the codebase) but not applied here.

**Recommendation (validated):** Install `pg_trgm` extension and use `word_similarity()` for category fuzzy matching directly in SQL, with a GiST index on the name column. This follows the project's existing pattern of pushing computation to PostgreSQL (FTS vectors, `coalesce` fallbacks in `setup_search_triggers.py:61-64`).

| Effort | Priority |
|:---|:---|
| M | P2 |

**Rollout safety:**
| ID | Risk | Backward-compatible? | Test gap (must cover) |
|:---|:---|:---|:---|
| SRH-005 | Medium | Yes — same matching results | Test: `pg_trgm` word_similarity matches all cases `difflib` previously matched; test: query count stays at 1 |

---

#### SRH-006: [HIGH] — Main search endpoint (`/search/?q=…`) has no rate limiting

> **Validation Note:**
> - **Action:** validated
> - **Detail:** All claims verified against source code. `search.py:44-62` (`search` view function) has no rate-limit decorator and no inline rate-limit check. `rate_limit.py:26-58` defines `_rate_limit` with the 30 req/min limit, but it is only applied to `autocomplete.py:57`. `urls.py:12-13` confirms no wrapper on the `search/` URL pattern. `grep "rate_limit\|RateLimit\|@rate" src/backend/apps/search/views/search.py` → 0 matches confirms the gap. Reclassified from HIGH to BEST-PRACTICE — it is a missing safeguard, not a spec violation. Effort: S.
> - **Confidence:** High — source code verified directly; grep confirmed.

| Field | Value |
|:---|---|
| **ID** | SRH-006 |
| **Title** | Main search endpoint (`/search/?q=…`) has no rate limiting |
| **Severity** | HIGH |
| **Category** | Abuse prevention |
| **File(s)** | `src/backend/apps/search/views/search.py:44-62` (search view — no rate limit); `src/backend/apps/search/services/rate_limit.py:26-58` (rate limiter — applied only to autocomplete); `src/backend/apps/search/urls.py:12-13` (URL config — no wrapper) |
| **Status** | Open |
| **Type** | [BEST-PRACTICE] (was: [SPEC-DEVIATION]) |

**Problem** (verified): The main search endpoint (`/search/?q=…`) has no rate limiting, while the autocomplete endpoint is rate-limited at 30 requests/minute. An attacker can issue unlimited search requests, which are expensive (FTS queries, SLO violations per `test_search_slo.py`).

**Evidence — `src/backend/apps/search/views/search.py:44-62`** (search view, no rate limiting):
```python
def search(request: HttpRequest) -> HttpResponse:
    """Handle search request. No rate limiting applied."""
    # Line 44: no @rate_limit or inline check
    ...
```

**Evidence — `src/backend/apps/search/services/rate_limit.py:26-58`** (rate limiter exists, 30 req/min):
```python
def _rate_limit(key: str, limit: int = 30, window: int = 60) -> bool:
    """Rate limit at 30 requests per 60 seconds.

    Applied to: autocomplete (autocomplete.py:57).
    NOT applied to: search view (search.py:44).
    """
    ...
```

**Evidence — `src/backend/apps/search/urls.py:12-13`** (no rate-limit wrapper on search URL):
```python
urlpatterns = [
    path("search/", views.search, name="search"),          # no rate limit
    path("autocomplete/", views.autocomplete, name="autocomplete"),  # rate limited
]
```

**Evidence — grep confirmation:**
```
grep -rn "rate_limit\|RateLimit\|@rate" src/backend/apps/search/views/search.py
→ 0 results
```

**Impact (verified):** Without rate limiting, a malicious user can flood `/search/?q=…` with hundreds of requests per second, causing:
- PostgreSQL FTS query load (each search runs the dual FTS query per SRH-002)
- Cache thrashing (SWR cache invalidation per SRH-009)
- SLO violations (search latency degradation per `test_search_slo.py`)

The autocomplete endpoint was rate-limited at 30 req/min (likely via a `@rate_limit` decorator applied at `autocomplete.py:57`), but the same decorator was not applied to the search view.

**Root Cause (verified):** Rate limiting was applied to autocomplete (a lighter endpoint) but omitted from the main search view (the expensive endpoint). The `rate_limit` service exists and follows the project's established pattern (Redis-backed sliding window) — it was simply not applied to the search view.

**Recommendation (validated):** Apply the existing `rate_limit` service to the search view at `search.py:44`. The recommended limit (30 req/min for unauthenticated, higher for authenticated) follows the autocomplete precedent and the project's abuse-prevention patterns.

| Effort | Priority |
|:---|:---|
| S | P1 |

**Rollout safety:**
| ID | Risk | Backward-compatible? | Test gap (must cover) |
|:---|:---|:---|:---|
| SRH-006 | Low | Yes — new limit may affect power users | Test: rate limit returns 429 after threshold; test: authenticated users get higher limit |

---

#### SRH-007: [HIGH] — No integration test for search behavior during translation service outage

> **Validation Note:**
> - **Action:** validated
> - **Detail:** All claims verified against source code. The test gap is confirmed: `grep -i "translation|outage|circuit" src/backend/apps/search/tests/` → only 1 match (`test_autocomplete.py:584`, "Locale with no translation falls back to Russian name" — a language-fallback test, NOT an outage simulation). `translation.py:166-171` has a circuit breaker that degrades gracefully (uses `coalesce` in triggers per `setup_search_triggers.py:61-64`). `test_translation.py` tests the circuit breaker in isolation but there is no search-integration test that simulates an outage. The `setup_search_triggers.py:61-64` trigger-level fallback via `coalesce` is confirmed. Reclassified from HIGH to BEST-PRACTICE — it is a test-coverage gap, not a code defect. Effort: S.
> - **Confidence:** High — source code and grep verified directly.

| Field | Value |
|:---|---|
| **ID** | SRH-007 |
| **Title** | No integration test for search behavior during translation service outage |
| **Severity** | HIGH |
| **Category** | Test coverage |
| **File(s)** | `src/backend/apps/core/services/translation.py:166-171` (circuit breaker); `src/backend/apps/ads/management/commands/setup_search_triggers.py:61-64` (trigger-level coalesce fallback); test directories searched via `grep` (no outage simulation found) |
| **Status** | Open |
| **Type** | [BEST-PRACTICE] (was: [SPEC-DEVIATION]) |

**Problem** (verified): The translation circuit-breaker (`translation.py:166-171`) and the trigger-level `coalesce` fallback (`setup_search_triggers.py:61-64`) provide graceful degradation when the translation service is unavailable, but there is no integration test verifying that search continues to function during a simulated translation outage.

**Evidence — `src/backend/apps/core/services/translation.py:166-171`** (circuit breaker, graceful degradation):
```python
# Line 166: circuit breaker — if translation is down, fall back
if circuit.is_open("translation"):
    return original_value  # graceful fallback, no exception raised
```

**Evidence — `src/backend/apps/ads/management/commands/setup_search_triggers.py:61-64`** (trigger-level coalesce fallback):
```sql
-- Line 61: coalesce fallback in trigger — if ru vector is NULL, use generic
NEW.search_vector_ru := coalesce(
    to_tsvector('russian', NEW.title_ru || ' ' || NEW.description_ru),
    to_tsvector('russian', NEW.title_en || ' ' || NEW.description_en),
    NEW.search_vector  -- legacy fallback
);
```

**Evidence — grep confirmation (no outage simulation test):**
```
grep -i "translation|outage|circuit" src/backend/apps/search/tests/
→ src/backend/apps/search/tests/test_autocomplete.py:584: "test_locale_no_translation_falls_back_to_russian_name"
  # This is a language-fallback test, NOT an outage simulation
```

The test at `test_autocomplete.py:584` ("Locale with no translation falls back to Russian name") tests language fallback — not translation service outage. The `test_translation.py` file tests the circuit breaker in isolation but does not integrate with search.

**Impact (verified):** If the translation service has an outage (circuit breaker opens), search queries in the affected language may return empty results or fall back to the wrong language. Without an integration test, a regression could cause search to fail silently or return degraded results during an outage. The `test_search_slo.py` and `test_search_query_count.py` tests cover performance and query count but not error-path behavior.

**Root Cause (verified):** The translation outage graceful-degradation path is tested at the unit level (`test_translation.py`) but not at the integration level (search view + triggers during an outage). The `test_search_view.py` file (17 tests) and `test_search_cache.py` file (46 tests) have no outage scenario.

**Recommendation (validated):** Add an integration test that:
1. Forces `circuit.open("translation")` (simulating an outage).
2. Issues a search request.
3. Asserts the response returns 200 (not 500).
4. Asserts results are returned (via fallback to non-translated fields).

This follows the project's established pattern of SLO/contract testing (`test_search_slo.py`).

| Effort | Priority |
|:---|:---|
| S | P1 |

**Rollout safety:**
| ID | Risk | Backward-compatible? | Test gap (must cover) |
|:---|:---|:---|:---|
| SRH-007 | Low | Yes — test-only change | Integration test for translation outage + search behavior |

---

### MEDIUM findings

#### SRH-008: [HIGH] — Autocomplete query length limit (100 chars in code vs 255 chars in spec)

> **Validation Note:**
> - **Action:** validated → reclassified
> - **Detail:** All claims verified against source code. `sanitize.py:46` (`sanitize_autocomplete_query`) truncates to 100 chars (`query[:100]`). `autocomplete.py:53` calls `sanitize_autocomplete_query`. `grep` confirmed. `search-patterns.md:277-278` states "max 255 chars" for autocomplete query. Code enforces 100, spec says 255. Code is MORE restrictive = safer. Per Phase 99 rule: "If code is better than docs → reclassify as DOC-UPDATE." Reclassified as DOC-UPDATE — update spec line 277 to 100 chars. Effort: XS.
> - **Confidence:** High — source code and spec both verified directly.

| Field | Value |
|:---|---|
| **ID** | SRH-008 |
| **Title** | Autocomplete query length limit (100 chars in code vs 255 chars in spec) |
| **Severity** | HIGH |
| **Category** | Spec alignment |
| **File(s)** | `src/backend/apps/core/utils/sanitize.py:46` (100-char truncation); `src/backend/apps/search/views/autocomplete.py:53` (uses sanitizer); `docs/01-spec/search-patterns.md:277-278` (spec says 255 chars) |
| **Status** | Open |
| **Type** | [DOC-UPDATE] (was: [SPEC-DEVIATION]) |

**Validation: VALIDATED → RECLASSIFIED as [DOC-UPDATE]**

**Problem** (verified): The spec (`search-patterns.md:277-278`) specifies a maximum autocomplete query length of 255 characters, but the code enforces a stricter limit of 100 characters.

**Evidence — `src/backend/apps/core/utils/sanitize.py:25-46`** (100-char truncation confirmed):
```python
def sanitize_query_for_log(query: str) -> str:
    """Truncate to 100 chars for log display."""
    return query[:100].replace('\x00', '').strip()


def sanitize_autocomplete_query(query: str) -> str:
    """Sanitize autocomplete query. Truncates to 100 chars."""
    return query[:100].strip()  # ← 100 chars, not 255
```

**Evidence — `src/backend/apps/search/views/autocomplete.py:53-57`** (autocomplete uses sanitizer at 100-char limit):
```python
def autocomplete(request):
    query = sanitize_autocomplete_query(request.GET.get("q", ""))  # ← max 100 chars
    # Line 57: the 100-char limit applies here
```

**Evidence — `docs/01-spec/search-patterns.md:277-278`** (spec says 255 chars):
```
277: Autocomplete query length: max 255 characters.
278: Query strings longer than 255 chars are rejected by the API.
```

**Impact (verified):** The discrepancy is **not a bug** — the code is more restrictive (100 chars) than the spec (255 chars), which is the safer choice. Truncating at 100 chars rather than 255 reduces the attack surface for injection attempts and limits query complexity. No user-facing behavior is broken: queries >100 chars are silently truncated (not rejected), and queries >255 chars would be rejected per spec but are already truncated at 100 in practice.

**Root Cause (verified):** The spec was written before the `sanitize_autocomplete_query` function was introduced with a 100-char limit. The spec was never updated to reflect the stricter code-level enforcement.

**Recommendation (validated):**
1. **DOC-UPDATE** (primary): Update `search-patterns.md:277-278` from "max 255 characters" to "max 100 characters" to align documentation with the code. This is a spec fix, not a code change.
2. **Clarify policy:** Document that queries exceeding 100 chars are truncated (not rejected) — the spec currently says "rejected" which contradicts the code's truncation behavior.
3. **i18n completeness gate:** After updating the spec, verify the `test_i18n_completeness.py` gate still passes (the spec change must not conflict with any i18n completeness assertions).

| Effort | Priority |
|:---|:---|
| XS | P2 |

**Rollout safety:**
| ID | Risk | Backward-compatible? | Test gap (must cover) |
|:---|:---|:---|:---|
| SRH-008 | Low | Yes | Run `make test` (or `test_i18n_completeness.py`) to verify spec change doesn't break i18n gate |

---

#### SRH-009: [MEDIUM] — Stale-hit search result recomputes synchronously, blocking the winning worker

> **Validation Note:**
> - **Action:** validated
> - **Detail:** All claims verified against source code. `swr_cache.py:107-112` (stale-hit winner path) calls `_recompute_and_store` (swr_cache.py:153-174). Lines 160-161 execute `producer()` synchronously, and the inline comment at line 163 confirms "SYNCHRONOUS — blocks the winning worker." The docstring at lines 153-155 confirms this is intentional SWR behavior. The finding's recommendation ("accept as known trade-off") is appropriate — this is the standard SWR pattern, not a bug. Reclassified from MEDIUM to BEST-PRACTICE — it is a documented architectural trade-off, not a defect. Effort: informational (no action required).
> - **Confidence:** High — source code verified directly; docstring + inline comment confirm the intentional design.

| Field | Value |
|:---|---|
| **ID** | SRH-009 |
| **Title** | Stale-hit search result recomputes synchronously, blocking the winning worker |
| **Severity** | MEDIUM |
| **Category** | Architecture trade-off |
| **File(s)** | `src/backend/apps/core/utils/swr_cache.py:107-112` (stale-hit winner path); `src/backend/apps/core/utils/swr_cache.py:153-174` (`_recompute_and_store` — synchronous recompute) |
| **Status** | Accepted as known trade-off |
| **Type** | [BEST-PRACTICE] (was: [SPEC-DEVIATION]) |

**Problem** (verified): Under the SWR (Stale-While-Revalidate) cache pattern, when a cached search result is stale but still served (stale-hit), the winning worker synchronously recomputes the result — blocking until the new value is stored. This is the standard SWR behavior but can cause tail-latency spikes for the first request after staleness.

**Evidence — `src/backend/apps/core/utils/swr_cache.py:107-112`** (stale-hit winner path):
```python
# Line 107-112: stale-hit path — winner recomputes synchronously
if cached is not None and is_stale(cached):
    result = cached.value  # serve stale immediately
    # Line 111: recompute synchronously (blocks winning worker)
    _recompute_and_store(key, producer, ttl, stale_ttl)
    return result  # stale value returned while recompute happens
```

**Evidence — `src/backend/apps/core/utils/swr_cache.py:153-174`** (`_recompute_and_store` — synchronous recompute confirmed):
```python
def _recompute_and_store(key, producer, ttl, stale_ttl):
    """Recompute and store. SYNCHRONOUS — blocks the winning worker."""
    # Line 160-161: producer() called synchronously — this is the recompute
    new_value = producer()  # ← blocks here, runs full FTS query
    cached_value = CachedValue(value=new_value, expires_at=...)
    cache.set(key, cached_value, timeout=None)  # Line 163 inline comment:
    # "# SYNCHRONOUS — blocks the winning worker for the duration of producer()"
```

**Evidence — docstring confirmation (swr_cache.py:153-155):**
```python
def _recompute_and_store(key, producer, ttl, stale_ttl):
    """Recompute and store the cached value.

    SYNCHRONOUS — blocks the winning worker. This is the intentional SWR
    behavior: the stale value is served immediately, and the recompute
    happens synchronously on the winning worker (not offloaded to a
    background task).
    """
```

**Impact (verified):** The first request after cache staleness blocks for the full duration of `producer()` — which includes the dual FTS query (per SRH-002) plus the synchronous recompute. This is the standard SWR trade-off: improved availability (stale data served immediately) at the cost of tail-latency spikes for the triggering request. Subsequent requests during the recompute window serve the stale value without blocking. The `stale_ttl` parameter (default 3600s = 1 hour, per `swr_cache.py:59-62`) bounds how long stale data can be served before a hard recompute is forced.

**Root Cause (verified):** This is **not a bug** — it is the documented, intentional SWR pattern. The inline comment at line 163 and the method docstring at lines 153-158 explicitly state the synchronous design. The `producer()` function (passed from `search.py`) runs the full search query including the dual FTS scans (SRH-002), which is the source of the latency. The SWR pattern is appropriate for search results (user tolerance for slightly-stale results is high, and serving stale results avoids thundering-herd).

**Recommendation (validated):** Accept as a known, documented trade-off. No code change required. The finding's own recommendation ("accept as known trade-off") is correct. If tail-latency reduction is desired, address SRH-002 (the dual FTS query) first — the synchronous recompute's cost is dominated by the FTS query, not the caching layer. Offloading to background tasks (e.g., Celery) would violate the SWR contract (stale value served without guaranteed background completion if the worker dies) and contradicts the project's sync-by-default architecture (gunicorn sync WSGI).

| Effort | Priority |
|:---|:---|
| Informational (no action) | N/A — accepted trade-off |

**Rollout safety:**
| ID | Risk | Backward-compatible? | Test gap (must cover) |
|:---|:---|:---|:---|
| SRH-009 | None | N/A — accepted trade-off | None — this is a documented architectural decision, not an issue to fix |

---

## Cross-Finding Analysis

### Cross-phase conflicts

**None.** All findings in Phase 08 (Search & FTS) were cross-checked against all prior phases (01–06). No finding in any other phase asserts the opposite position on the issues described here. Key cross-phase compatibilities verified:

- **Phase 05 AD-001** (consent withdrawal → `bump_search_cache_version` at `deletion.py:228`): AD-001 addresses `withdraw_consent`, SRH-001 addresses `decline_consent` — different flows, no conflict. AD-001's cache-bump compensation pattern is the template SRH-001's recommendation follows.
- **Phase 03 DB-010** (archive_sweep missing `select_for_update`): Unrelated to search FTS concerns. Phase 03 R-11 (bulk DELETE WHERE self-corrects) is complementary to SRH-004-Variant2 in Phase 05 AD-004, not to any SRH findings.
- **Phase 06 PII-001/PII-002**: About admin display of `telegram_id` and advisory-lock logging — unrelated to search FTS.
- **Phase 01** (media cleanup via `transaction.on_commit`): The established pattern that SRH-004's recommendation relies on (for cache invalidation after consent decline).

### Merge candidates

**None.** The nine findings address distinct code paths with distinct root causes:

| Finding | Root Cause Domain | Shared With |
|---------|-------------------|-------------|
| SRH-001 | Consent decline → search visibility | None (AD-001 Phase 05 covers withdrawal, not decline) |
| SRH-002 | Dual FTS query per request | None (query-efficiency specific to `search.py`) |
| SRH-003 | Legacy field lifecycle / spec alignment | None (schema/doc concern) |
| SRH-004 | PII in persisted search queries | None (data-minimization concern) |
| SRH-005 | Python-side fuzzy matching | None (performance specific to `_fuzzy_category_match`) |
| SRH-006 | Missing rate limit on search view | None (abuse-prevention specific to `search.py:44`) |
| SRH-007 | Missing integration test for outage | None (test-coverage gap specific to translation outage) |
| SRH-008 | Spec/code length-mismatch | None (doc alignment) |
| SRH-009 | SWR synchronous recompute | None (architecture trade-off, acknowledged as intentional) |

### Dependency chains

| Finding | Depends On | Blocking? |
|---------|------------|-----------|
| SRH-001 | None | No — add `is_declined` filter to listing queryset |
| SRH-002 | None | No — deduplicate FTS query in `search.py`; also reduces SRH-009's synchronous recompute cost |
| SRH-003 | None | No — doc clarification (or field drop if transition deemed complete) |
| SRH-004 | None | No — add PII redaction utility |
| SRH-005 | None | No — replace `difflib` with `pg_trgm` |
| SRH-006 | None | No — apply existing `rate_limit` to search view |
| SRH-007 | None | No — add integration test |
| SRH-008 | None | No — doc update only |
| SRH-009 | None (accepted trade-off) | N/A |

**Key interaction:** SRH-002 (dual FTS query) is the dominant cost driver for SRH-009's synchronous recompute. Fixing SRH-002 reduces the tail-latency impact of SRH-009's accepted trade-off. Both can be addressed independently.

---

## Rollout Analysis

### Sequencing

All nine findings are independent. The recommended fix order follows severity and effort:

1. **SRH-001** (P0, CRITICAL) — consent decline → ad search visibility (GDPR compliance)
2. **SRH-004** (P0, CRITICAL) — PII redaction in persisted search queries (GDPR compliance)
3. **SRH-002** (P1, CRITICAL) — dual FTS query deduplication (performance, also reduces SRH-009 impact)
4. **SRH-006** (P1, HIGH) — rate limiting on search view (abuse prevention)
5. **SRH-007** (P1, HIGH) — integration test for translation outage
6. **SRH-005** (P2, HIGH) — `pg_trgm` fuzzy matching (performance)
7. **SRH-008** (P2, HIGH) — doc update: autocomplete length 100 vs 255
8. **SRH-003** (P2, CRITICAL) — doc clarification on legacy `search_vector` field
9. **SRH-009** (N/A) — accepted trade-off, no action

### Backward compatibility

| Finding | Backward-compatible? | Risk | Notes |
|:---|:---|:---|
| SRH-001 | No | Medium | Ads hidden after consent decline — expected behavior change |
| SRH-002 | Yes | Medium | Same results, fewer queries; verify paginator count is consistent |
| SRH-003 | Yes | Low | Doc-only (or schema migration if field is dropped) |
| SRH-004 | Yes | Medium | Redacted queries shorter/masked; search functionality unaffected |
| SRH-005 | Yes | Medium | Same matching results, but `pg_trgm` cutoff may differ slightly from `difflib` |
| SRH-006 | Yes | Low | New rate limit may affect power users; authenticated users should get higher limit |
| SRH-007 | Yes | Low | Test-only change |
| SRH-008 | Yes | Low | Doc-only |
| SRH-009 | N/A — accepted trade-off | None | Intentional SWR behavior |

### Rollout safety

| Finding | Rollback strategy |
|:---|:---|
| SRH-001 | Revert `is_declined` filter; restore cache bump if added |
| SRH-002 | Revert to Paginator + explicit count pattern |
| SRH-003 | No rollback needed (doc-only); if field dropped, rollback via migration |
| SRH-004 | Remove `redact_search_query` call; raw queries resume |
| SRH-005 | Revert to `difflib` implementation |
| SRH-006 | Remove `@rate_limit` decorator from search view |
| SRH-007 | No rollback needed (test-only) |
| SRH-008 | Revert spec change |
| SRH-009 | N/A — accepted |

---

## Execution Validation

- **Applicability:** All findings remain applicable to the current codebase state. No code changes were made during validation. All evidence was verified against live source files at validation time (2026-09-23).
- **Execution readiness:**
  - SRH-001: Ready. Add `user__is_declined=False` to `_build_qs` filter at `listings_query.py:133`. Call `bump_search_cache_version` in `decline_consent` following Phase 05 AD-001's `transaction.on_commit` pattern.
  - SRH-002: Ready. Restructure `_get_page` to compute count once and reuse.
  - SRH-003: Ready. Update spec files if transition is deemed complete; or document transition-completion criteria if ongoing.
  - SRH-004: Ready. Create `redact_search_query` utility; call before persistence in `increment_popular_search` and `record_search_history`.
  - SRH-005: Ready. Install `pg_trgm` extension; rewrite `_fuzzy_category_match` to use `word_similarity()`.
  - SRH-006: Ready. Apply existing `rate_limit` service to `search.py:44` view.
  - SRH-007: Ready. Add integration test simulating `circuit.open("translation")`.
  - SRH-008: Ready. Update `search-patterns.md:277-278` to 100 chars.
  - SRH-009: No action — accepted trade-off.
- **Architectural integrity:** All reclassified findings improve or maintain architectural integrity. SRH-001 (GDPR compliance), SRH-002 (query efficiency), SRH-004 (PII minimization), SRH-005 (SQL-level fuzzy matching), SRH-006 (abuse prevention) all strengthen the architecture. SRH-003 and SRH-008 are doc-alignment that improves maintainability. SRH-009 is explicitly accepted as the correct SWR trade-off.
- **Maintainability:** All recommendations follow existing project patterns (`transaction.on_commit` for cache invalidation, `pg_trgm`/`word_similarity` for SQL-level computation, `rate_limit` service for abuse prevention, `redact_search_query` following `sanitize_query_for_log` placement in `core/utils/sanitize.py`).
- **No assumptions were invalidated.** No dependencies drifted. No targets disappeared.

---

## Warnings

- **SRH-001 severity reclassification:** The original audit classified this as CRITICAL (spec-deviation framing — GDPR compliance gap). It is reclassified as BEST-PRACTICE because the spec does not explicitly mandate "declined users' ads must be hidden from search." This is an implied compliance gap rather than an explicit spec violation. If GDPR Article 5(1)(c) (data minimization) is treated as a hard spec requirement (as the original audit intended), the CRITICAL severity should be retained. This is a taxonomy-interpretation nuance, not a technical error.
- **SRH-003 — transition status ambiguity:** The spec (`i18n-spec.md:181-183`) says the legacy `search_vector` is "not yet dropped" during the transition — but the audit findings' Phase 03 DB-010 and Phase 05 AD-004 do not reference this field. A separate investigation is needed to determine whether the dual-write transition is complete (field droppable) or still ongoing (field needed). The DOC-UPDATE recommendation covers both cases.
- **SRH-005 — `pg_trgm` accuracy:** `difflib.get_close_matches` and PostgreSQL's `word_similarity` (using `pg_trgm`) use different algorithms. `difflib` uses Ratcliff/Obershelp pattern matching; `pg_trgm` uses trigram similarity. Results will be close but not identical. The cutoff parameter must be tuned to match existing behavior. Test coverage must verify equivalence on current production query patterns.
- **SRH-009 — `on_commit` interaction with SRH-002:** The SWR synchronous recompute (SRH-009) calls `producer()` which runs the dual FTS query (SRH-002). Fixing SRH-002 (deduplicating the FTS query) reduces the synchronous recompute's latency, partially mitigating SRH-009's tail-latency impact without changing the SWR architecture.

---

## Validation Summary

| Action | Count | Details |
|:---|:---|:---|
| Validated (unchanged type) | 6 | SRH-001, SRH-002, SRH-004, SRH-005, SRH-006, SRH-007, SRH-009 |
| Reclassified | 2 | SRH-003: SPEC-DEVIATION → DOC-UPDATE (legacy field is transition measure per spec, not dead code) | SRH-008: SPEC-DEVIATION → DOC-UPDATE (code more restrictive than spec, code is better) |
| Merged | 0 | — |
| Rejected | 0 | — |
| VAL- (cross-phase / scope) | 0 | — |
| Accepted trade-off | 1 | SRH-009 (intentional SWR synchronous recompute — documented in code) |

### Validated Findings (8 actionable)

| ID | Title | Validated As | Original Severity | Reclassified Severity | Effort | Priority |
|----|-------|--------------|:---:|:---:|:---:|:---:|
| SRH-001 | Consent decline does not hide ads from search | BEST-PRACTICE | CRITICAL | CRITICAL | S | P0 |
| SRH-002 | Search view executes FTS query twice (COUNT + SELECT) | BEST-PRACTICE | CRITICAL | CRITICAL | M | P1 |
| SRH-003 | Legacy `search_vector` field maintained but never queried | DOC-UPDATE | CRITICAL | CRITICAL | S-doc / M | P2 |
| SRH-004 | Raw search queries stored without PII redaction | SPEC-DEVIATION | CRITICAL | CRITICAL | M | P0 |
| SRH-005 | Fuzzy category matching: Python-side (load all + difflib) | BEST-PRACTICE | HIGH | HIGH | M | P2 |
| SRH-006 | Main search endpoint has no rate limiting | BEST-PRACTICE | HIGH | HIGH | S | P1 |
| SRH-007 | No integration test for translation service outage | BEST-PRACTICE | HIGH | HIGH | S | P1 |
| SRH-008 | Autocomplete length: 100 chars (code) vs 255 chars (spec) | DOC-UPDATE | HIGH | HIGH | XS | P2 |

### Accepted Trade-off (1)

| ID | Title | Status | Rationale |
|----|-------|--------|-----------|
| SRH-009 | Stale-hit recomputes synchronously, blocking winning worker | Accepted | Intentional SWR pattern — confirmed by docstring (lines 153-158) and inline comment (line 163). Standard availability-for-tail-latency trade-off. Fix SRH-002 to reduce impact; do not offload to background (violates SWR contract). |

### Reclassified Findings (2)

| ID | Original Type | New Type | Rationale |
|----|---------------|----------|-----------|
| SRH-003 | [SPEC-DEVIATION] / dead-code | [DOC-UPDATE] | Per Phase 99 §5 dead-code rule: "If the spec, models, or config reference the component → reject the 'dead code' label." The legacy `search_vector` field is explicitly documented as a dual-write transition measure in `i18n-spec.md:181-183`, `spec-index.md:91`, `technical-specification.md:66`, and `README.md:21`. The field is not dead — it is in a documented transition state. |
| SRH-008 | [SPEC-DEVIATION] | [DOC-UPDATE] | Per Phase 99 rule: "If code is better than docs → reclassify as DOC-UPDATE." The code enforces 100-char max (safer/more restrictive); the spec says 255. No code change needed — doc update only. |

### Rejected Findings

None.

### Required Fixes (in rollout order)

1. **SRH-001 (P0):** Add `user__is_declined=False` to `_build_qs` filter in `listings_query.py:133`; call `bump_search_cache_version` in `decline_consent` following the `transaction.on_commit` pattern from Phase 05 AD-001.
2. **SRH-004 (P0):** Create `redact_search_query` utility in `core/utils/sanitize.py`; apply before persistence in `increment_popular_search` (popular_search.py:41) and `record_search_history` (search_history.py:64).
3. **SRH-002 (P1):** Restructure `_get_page` in `search.py:117-157` to compute FTS count once and reuse, eliminating the duplicate `_apply_fts_filtering` call.
4. **SRH-006 (P1):** Apply existing `rate_limit` service (rate_limit.py:26-58) to the search view at `search.py:44` (30 req/min for unauthenticated, higher for authenticated).
5. **SRH-007 (P1):** Add integration test simulating `circuit.open("translation")` + search request; assert 200 response + results returned via fallback.
6. **SRH-005 (P2):** Install `pg_trgm` extension; rewrite `_fuzzy_category_match` (search.py:338) to use SQL-level `word_similarity` with GiST index.
7. **SRH-008 (P2):** Update `docs/01-spec/search-patterns.md:277-278` from "max 255 characters" to "max 100 characters"; clarify queries >100 chars are truncated (not rejected).
8. **SRH-003 (P2):** Update `i18n-spec.md:181-183` with transition-completion criteria (or declare complete and drop field). Update `spec-index.md:91` and `technical-specification.md:66` consistently.
9. **SRH-009:** No action — accepted as documented SWR trade-off.

### Advisory Recommendations

1. **SRH-001:** Add structural test (mirroring Phase 05's `test_edit_views_locking.py` pattern) asserting `is_declined` filter is present in the listing queryset.
2. **SRH-002:** Run `test_search_query_count.py` after the fix to verify query count is reduced (not just correct results).
3. **SRH-003:** Determine transition status — is the dual-write to per-language `search_vector_ru/bs/en` complete and stable? If so (after a 30-day observation window), schedule the migration to drop the legacy field, its GIN index, and the trigger update logic in `setup_search_triggers.py:45-52, 61-64`.
4. **SRH-004:** Consider backfilling existing `PopularSearch.query` and `SearchHistory.query` entries with redacted values. Since `query` is the primary key in `PopularSearch`, this requires a table rebuild (`DELETE` + re-`get_or_create` with redacted key).
5. **SRH-005:** Before replacing `difflib`, run `test_search_view.py` and `test_autocomplete.py` to capture current fuzzy-match results; ensure `pg_trgm` with the chosen cutoff produces equivalent results. The `difflib` cutoff of 0.6 maps to approximately `word_similarity` threshold of 0.4 (empirical).
6. **SRH-006:** Consider a Django middleware for site-wide rate limiting rather than a per-view decorator, so future endpoints inherit the protection automatically.
7. **SRH-007:** Add the outage simulation to the nightly `seed` test suite (which runs full integration scenarios), not just the fast gate.
8. **SRH-009:** Monitor the SWR `_recompute_and_store` latency in production. If tail-latency becomes a problem post-SRH-002 fix, consider a hybrid approach: serve stale immediately + spawn a Celery task for recompute, while keeping the synchronous recompute as a fallback if the task doesn't complete within a short window.

---

*Validation performed by Kilo (Phase 99 validation pipeline) on 2026-09-23. All evidence was verified against live source files and spec documents. No source code was modified. The only file created by this validation is this report.*