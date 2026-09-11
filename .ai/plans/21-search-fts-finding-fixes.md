---
id: search-fts-finding-fixes
domain: plan
tags:
  - search-fts
  - srh-001
  - srh-002
  - srh-003
  - srh-004
  - input-validation
  - docs
  - phase-3-tracking
related:
  - .ai/audit/99-validation/08-search-fts-validated-findings.md
  - docs/97-plans/01-phase-plan-highlevel.md
  - docs/02-database/db-schema.md
  - docs/02-database/db-indexes.md
  - docs/01-spec/i18n-spec.md
  - docs/01-spec/spec-index.md
  - docs/03-packages/packages-list.md
  - docs/03-packages/dependency-collisions.md
  - docs/07-design-researches/migration_patterns.md
  - src/backend/apps/search/views/search.py
  - src/backend/apps/search/services/popular_search.py
  - src/backend/apps/search/services/search_history.py
  - src/backend/apps/search/models.py
  - src/backend/apps/search/tests/test_search_view.py
  - src/backend/apps/ads/models.py
  - src/backend/apps/ads/migrations/0001_initial.py
  - src/backend/apps/ads/management/commands/setup_search_triggers.py
  - src/backend/apps/ads/tests/test_search_triggers.py
---

# Search FTS Finding Fixes — Execution Plan (Phase 08)

**Plan ID:** `21-search-fts-finding-fixes`
**Source:** `.ai/audit/99-validation/08-search-fts-validated-findings.md` (validated 2026-09-05)
**Status:** 4 findings — 1 HIGH mandatory (atomic with tests), 1 LOW advisory (tests), 1 MEDIUM (docs), 1 MEDIUM (Phase-3 tracking)

---

## 1. Baseline — What Is Already Done

All four findings were validated in static analysis (2026-09-05). No implementation work has been performed. The findings describe the current state of the codebase:

| Finding | Severity | Implementation Status |
|---------|----------|----------------------|
| SRH-001 | HIGH | Not implemented — `search()` in `search/views/search.py` still reads `q` with only `.strip()`, no length bound; `increment_popular_search`/`record_search_history` receive the uncapped value |
| SRH-004 | LOW | Not implemented — `test_search_view.py` has no input-robustness tests for hostile/malformed/long `q` values |
| SRH-002 | MEDIUM | Not implemented — `packages-list.md` line 35 and `dependency-collisions.md` lines 32/60 describe a search-time Montenegrin→Russian translation bridge that the code removed; only docs are stale, code is correct |
| SRH-003 | MEDIUM | Not implemented — generic `search_vector` column + `IX_ads_search_gin` GIN index maintained on every ad write (7 of 16 trigger `to_tsvector` calls) but never read; gated on Phase 3 removal, tracked only |

---

## 2. Remaining Work Summary

| # | Finding | Severity | Scope | Agent needed |
|---|---------|----------|-------|--------------|
| 1 | **SRH-001 + SRH-004 (atomic)** | HIGH + LOW | Bound `q` at the `/search/` input edge with a named constant; add input-robustness regression tests | Planner, Validator |
| 2 | **SRH-002** | MEDIUM | Doc-only fixes across `packages-list.md` and `dependency-collisions.md` | Planner |
| 3 | **SRH-003** | MEDIUM | Phase-3 tracking doc update (no code change; gated) | Planner, Validator |

**Key constraint:** SRH-001 and SRH-004 must be delivered as a single atomic commit — the >200-char regression test pins SRH-001's fix, and shipping one without the other leaves the input boundary unguarded.

---

## 3. Dependency DAG

```
Block 1  SRH-001 + SRH-004 (atomic)          ⏳ (Implementor: Planner + Validator)
         Bound q at input edge in search()   →  add regression tests
         + write-amplification tracked (Phase 3 only)  │
                                                        │
Block 2  SRH-002 (docs)                      ⏳ (Implementor: Planner)
         Fix stale doc references                          │
                                                        │
Block 3  SRH-003 (tracking)                  ⏳ (Implementor: Planner + Validator)
         Doc update to Phase-3 plan                          │
                                                        │
         └────────────────────────────────────────────────┘
         All three blocks touch disjoint files — parallel-safe.
         "Only one Implementor at a time" → sequential execution,
         but no ordering constraint between blocks.
```

**Within Block 1 (SRH-001 + SRH-004):** The `q` cap is applied at the input edge in `search()'s query parsing line, before the `if query:` branch that calls `increment_popular_search` / `record_search_history`. The regression tests are appended to `test_search_view.py` and verify the cap. Code and tests are in one commit.

**Cross-block ordering:** None. Blocks 1, 2, and 3 touch completely disjoint file sets:
- Block 1: `apps/search/views/search.py` + `apps/search/tests/test_search_view.py`
- Block 2: `docs/03-packages/packages-list.md` + `docs/03-packages/dependency-collisions.md`
- Block 3: `docs/97-plans/01-phase-plan-highlevel.md`

**Parallel-safe pairs:**
- Block 1 (code) ∥ Block 2 (docs) — no shared files
- Block 1 (code) ∥ Block 3 (Phase-3 doc) — no shared files
- Block 2 (docs) ∥ Block 3 (Phase-3 doc) — different doc files, no overlap

---

## 4. Rollout Sequence

| Step | Block | Parallel with | Notes |
|------|-------|---------------|-------|
| 1 | **Block 1** (SRH-001 + SRH-004) | Block 2, Block 3 | Atomic commit: cap `q` + regression tests. Backward-compatible; no migration. |
| 2 | **Block 2** (SRH-002 docs) | Block 1, Block 3 | Doc-only; zero rollout risk; can be parallel. |
| 3 | **Block 3** (SRH-003 tracking) | Block 1, Block 2 | Doc-only; records write-amp cost as Phase-3 milestone item. |

**PR grouping recommendation:**
- **PR A:** Block 1 (SRH-001 + SRH-004) — code + tests, atomic, backward-compatible
- **PR B:** Block 2 (SRH-002) — doc fixes only
- **PR C:** Block 3 (SRH-003) — Phase-3 tracking doc update

PRs A, B, and C are fully independent (disjoint files). Any ordering or all-in-one is acceptable.

---

## 5. Execution Blocks

<!-- TASK_START: srh001_srh004_query_bound -->

### Block 1: SRH-001 + SRH-004 — Bound `q` at input edge + input-robustness regression tests

```yaml
id: srh001_srh004_query_bound
title: "SRH-001 + SRH-004: Bound q at /search/ input edge + add input-robustness regression tests"
source_reference: .ai/plans/21-search-fts-finding-fixes.md
source_section: "Block 1: SRH-001 + SRH-004"
priority: high
depends_on: []                         # SRH-004 depends on SRH-001's fix, but both
                                        # are delivered in one atomic commit
classification: mandatory               # SRH-001 is HIGH/mandatory; SRH-004 is its
                                        # verification half
risk: low                               # truncate is backward-compatible; no migration;
                                        # matches autocomplete's silent normalization
replaces_pattern: "query = (request.GET.get(\"q\") or \"\").strip()"
```

**Description:**
The `/search/` view reads `q` with only `.strip()` and enforces no length bound. The uncapped query flows to `increment_popular_search(query)` and `record_search_history(query)`, both of which persist into `PopularSearch.query` / `SearchHistory.query` — `CharField(max_length=200)`. Any `q` exceeding 200 characters triggers a PostgreSQL `DataError` on `INSERT` into `varchar(200)`, which propagates unhandled through the view → HTTP 500. This is a public anonymous DoS (PopularSearch is hit on every non-empty query, for anonymous buyers too).

**Viable implementation paths:**

1. **Truncate-at-input-edge (RECOMMENDED):** `query = query[:MAX_SEARCH_QUERY_LENGTH]` — silently bound the raw `q` before any service call. Backward-compatible: legitimate ≤200-char queries are unaffected; hostile >200-char queries no longer raise `DataError`. No migration, no new user-facing strings, no i18n impact.
2. **Reject-with-message:** Validate `q` length and return an error response/message for >200 chars. Requires new translated user-facing strings (`{% trans %}` + `makemessages`/`compilemessages`), changes UX for the edge case, and adds a validation branch to the view.

**Decision:** Path 1 (truncate-at-input-edge) is preferred per project conventions:
- The autocomplete path (`sanitize_autocomplete_query` in `core/utils/sanitize.py`) already silently normalizes (caps to 100 chars, strips SQL metacharacters) without user-facing rejection
- The spec §4.5/§7 states "Very long / many-token query → bounded or rejected" — truncation satisfies "bounded"
- The validated findings explicitly call truncation backward-compatible with no migration
- No i18n DoD impact — truncation introduces zero new user-visible strings (project rule #16: wrap only user-visible strings; this changes none)

**Implementation scope:**

1. **`apps/search/views/search.py`** — `search()` function, query-parsing line:
   - Add a module-level constant: `MAX_SEARCH_QUERY_LENGTH: Final[int] = 200` (aligned to `PopularSearch.query` and `SearchHistory.query` `CharField(max_length=200)`). Add `from typing import Final` import if not present.
   - Modify the query parsing from `query = (request.GET.get("q") or "").strip()` to `query = (request.GET.get("q") or "").strip()[:MAX_SEARCH_QUERY_LENGTH]`.
   - The truncation must occur **before** the `if query:` block (which gates `increment_popular_search` and `record_search_history`), ensuring the bounded value is what reaches the services.

2. **`apps/search/services/popular_search.py`** — no change required. The service already receives the truncated value from the view; its `get_or_create`/`update` calls will never see >200 chars. (Defense-in-depth note: the model `max_length=200` remains the last line of defense; the view cap is the primary boundary.)

3. **`apps/search/services/search_history.py`** — no change required. Same reasoning as above.

4. **`apps/search/tests/test_search_view.py`** — add `TestSearchViewInputRobustness` test class (see Tests below).

**Architectural constraints:**
- The cap must be `200` (not `199` or `201`) to match both `PopularSearch.query` and `SearchHistory.query` `CharField(max_length=200)` exactly. Truncating to exactly `max_length` guarantees no `DataError` regardless of database backend behavior at the boundary.
- The named constant (`MAX_SEARCH_QUERY_LENGTH`) must be module-level in `search.py`, not a magic number inline. This makes the 200-char bound self-documenting and visible to future maintainers.
- `from typing import Final` must be added if not already imported (matching `popular_search.py`'s usage of `Final`).

**Tests to add (in `TestSearchViewInputRobustness` class within `test_search_view.py`):**

| Test | Description | Acceptance |
|------|-------------|------------|
| `test_query_exceeding_max_length_returns_200` | `q` = 300 ASCII chars → HTTP 200 (not 500); pins SRH-001's fix | `response.status_code == 200` |
| `test_sql_injection_query_returns_200` | `q` = SQL-injection payload (`'; DROP TABLE ads; --`) → HTTP 200, DB intact | `response.status_code == 200`; `Ad.objects.filter(...).exists()` still true |
| `test_homoglyph_and_control_chars_query_returns_200` | `q` with Cyrillic + zero-width char + HTML-like payload → HTTP 200 | `response.status_code == 200` |
| `test_empty_query_graceful` | No `q` param → falls to non-FTS branch, returns 200 | `response.status_code == 200` (already covered by `test_empty_search_returns_all_published`; listed for completeness) |

All tests follow the existing fixture pattern: `seller`, `root_category`, `city` from `conftest.py`; `create_test_ad` helper with `status=AdStatus.PUBLISHED` to exercise the FTS branch; `Client()` for the HTTP request.

**Run command:**
```powershell
$dc run --rm -e PYTEST_OPTS="-k 'test_query_exceeding_max_length_returns_200 or test_sql_injection_query_returns_200 or test_homoglyph'" test
```

<!-- TASK_END: srh001_srh004_query_bound -->

---

<!-- TASK_START: srh002_doc_fixes -->

### Block 2: SRH-002 — Fix stale documentation references to query-time translation

```yaml
id: srh002_doc_stale_translation_refs
title: "SRH-002: Align packages-list.md and dependency-collisions.md with no-query-time-translation spec"
source_reference: .ai/plans/21-search-fts-finding-fixes.md
source_section: "Block 2: SRH-002"
priority: medium
depends_on: []
classification: advisory
risk: low                               # doc-only; no code, no i18n, no runtime impact
```

**Description:**
The implemented search path no longer performs query-time translation. `apps/core/services/translation` is used only at ad-publication time. The `/search/` view resolves the buyer's locale to a per-language vector column (`search_vector_ru/bs/en`) with no external translator on the search critical path. However, two docs files still describe the old bridge:

1. **`docs/03-packages/packages-list.md`** (line 35, in the Stack Summary bullet list): States "deep-translator (Montenegrin → Russian at search time; hard timeout ~500ms + fallback to original query)." This is stale — the same file's line 50 already states the correct position ("NOT used for search queries (search is per-language FTS, no query-time translation)"). Fix: align line 35 with line 50.

2. **`docs/03-packages/dependency-collisions.md`** (line 60, in the Residual Risks table): States "governing both search-side query translation and bot-side ad-creation translation." The "search-side" clause is stale — search-side translation does not exist. Fix: strip "both search-side query translation and " → "governing bot-side ad-creation translation".

3. **`docs/03-packages/dependency-collisions.md`** (line 32, in the deep-translator coupling matrix row's Evidence column): Cross-references "spec-index.md line 32 (Montenegrin→Russian query translation)." Line 32 of `spec-index.md` is now generic prose; the correct statement is at `spec-index.md:47` ("deep-translator (Bosnian→Russian at ad publication only; search is per-language FTS, no query-time translation)"). Fix: change the cross-reference from "spec-index.md line 32" to "spec-index.md line 47".

**Implementation scope (doc-only):**

| File | Change | Semantic target |
|------|--------|-----------------|
| `docs/03-packages/packages-list.md` | Replace the "Query translation" bullet item's description of Montenegrin→Russian-at-search-time with Bosnian→Russian-at-publication-only + "NOT used for search queries" clause | Stack Summary bullet list, "Query translation" item |
| `docs/03-packages/dependency-collisions.md` | Strip "both search-side query translation and " from the deep-translator residual-risk row, leaving only "governing bot-side ad-creation translation" | Residual Risks table, deep-translator row |
| `docs/03-packages/dependency-collisions.md` | Change "spec-index.md line 32 (Montenegrin→Russian query translation)" → "spec-index.md line 47 (Bosnian→Russian at ad publication only; search is per-language FTS, no query-time translation)" | Version-Coupling Matrix, deep-translator row, Evidence column |

**Exact replacement text:**

For `packages-list.md` line 35, the current line:
```
- **Query translation:** deep-translator (Montenegrin → Russian at search time; hard timeout ~500ms + fallback to original query).
```
Replace with (aligned with line 50 and `spec-index.md:47`):
```
- **Query translation:** deep-translator (Bosnian→Russian title/description translation at ad publication time; hard timeout ~500ms + fallback to original query). NOT used for search queries (search is per-language FTS, no query-time translation).
```

For `dependency-collisions.md` line 60, the current text:
```
Hard timeout ~500ms + circuit breaker (3 failures → 60s cooldown) + LRU cache, governing both search-side query translation and bot-side ad-creation translation. Mandatory fallback to original text/query on failure.
```
Replace `governing both search-side query translation and bot-side ad-creation translation` with `governing bot-side ad-creation translation`.

For `dependency-collisions.md` line 32, the current cross-reference:
```
`spec-index.md` line 32 (Montenegrin→Russian query translation)
```
Replace with:
```
`spec-index.md` line 47 (Bosnian→Russian at ad publication only; search is per-language FTS, no query-time translation)
```

**Acceptance criteria:**
1. `packages-list.md` line 35 no longer mentions "search time" translation
2. `packages-list.md` line 35 uses "Bosnian→Russian at ad publication time" (matching line 50 and spec-index.md:47)
3. `dependency-collisions.md` line 60 no longer mentions "search-side query translation"
4. `dependency-collisions.md` line 32 cross-references `spec-index.md` line 47 (not line 32)
5. All three files still have valid YAML frontmatter and pass markdown lint
6. Cross-reference to `spec-index.md:47` is verified accurate by reading that line

**Run command:** (doc-only — no test/lint commands needed; verify by reading the changed lines)
```powershell
# Verify the changes
git diff docs/03-packages/packages-list.md docs/03-packages/dependency-collisions.md
```

<!-- TASK_END: srh002_doc_fixes -->

---

<!-- TASK_START: srh003_phase3_tracking -->

### Block 3: SRH-003 — Track `search_vector` write-amplification as Phase-3 milestone

```yaml
id: srh003_phase3_tracking
title: "SRH-003: Document write-amplification tracking for Phase 3 (no code change)"
source_reference: .ai/plans/21-search-fts-finding-fixes.md
source_section: "Block 3: SRH-003"
priority: medium
depends_on: []
classification: advisory
risk: low                               # doc-only tracking; NO code/schema change now
                                       # removal is explicitly gated on Phase 3
```

**Description:**
The generic `search_vector` column (`Ad.search_vector`, `SearchVectorField`) and its GIN index (`IX_ads_search_gin`) are maintained on every ad INSERT/UPDATE by the `ads_search_vector_fn` trigger — consuming 7 of 16 `to_tsvector` calls (44% of trigger CPU on every ad write). However, no production query reads this generic column: both the web search view (`search()` function in `apps/search/views/search.py`) and `alert_query.find_matching_ads` select the per-language vector exclusively via `LanguageLocale.fts_vector_field` (`search_vector_ru`/`_bs`/`_en`).

**This finding's recommendation is NOT to remove the column now.** The validated findings confirm the column is a documented legacy-dual-write transitional artifact, explicitly slated for Phase 3 removal across five documentation files. Removing it out-of-band would diverge the schema from the documented migration trajectory (`docs/07-design-researches/migration_patterns.md` dual-write design). The correct action is to **track** the write-amplification cost as a Phase-3 milestone item.

**Decision on doc update target:** YES — SRH-003 tracking requires a doc update to a Phase-3 file. The target is `docs/97-plans/01-phase-plan-highlevel.md` (Phase 3 section). There is currently no dedicated Phase-3 detailed plan file; the high-level plan is the only Phase-3 artifact. Adding a tracked item there ensures visibility when Phase 3 planning is refined.

**Implementation scope (doc-only tracking):**

Add a new sub-item to the Phase 3 section of `docs/97-plans/01-phase-plan-highlevel.md`, under a "Technical Debt / Infrastructure" heading in the Analytics or Infrastructure portion:

```markdown
#### Phase 3 Technical Debt: Search Vector Cleanup (tracked from Phase 08 SRH-003)

**SRH-003 (MEDIUM, BEST-PRACTICE):** Drop legacy `search_vector` column + `IX_ads_search_gin`.

The generic `search_vector` column and its `IX_ads_search_gin` GIN index on `ads` are
maintained on every ad INSERT/UPDATE by the `ads_search_vector_fn` trigger — consuming
7 of 16 `to_tsvector` calls (44% of trigger CPU) — but are never read by any production
query. Both the web search view (`search()/increment_popular_search`/`record_search_history`)
and `alert_query.find_matching_ads` use only the per-language vectors
(`search_vector_ru`/`_bs`/`_en`) via `LanguageLocale.fts_vector_field`.

**Status:** Tracked only. Do NOT remove out-of-band.

**Gating:** This cleanup must execute within Phase 3's schema-maintenance window, sequenced
with the dual-write migration plan in `docs/07-design-researches/migration_patterns.md`.

**Implementation footprint (for Phase 3 execution — NOT to be executed in this phase):**

1. **New migration** — `DROP INDEX IF EXISTS IX_ads_search_gin` then
   `ALTER TABLE ads DROP COLUMN IF EXISTS search_vector` then
   `CREATE OR REPLACE FUNCTION ads_search_vector_fn()` with the 7 `to_tsvector` assignments
   to `NEW.search_vector` removed. No separate backfill `RunSQL` required (the
   `migration_patterns.md` backfill note concerns per-language-vector population for seed rows,
   not the generic column being dropped).

2. **`setup_search_triggers.py`** — remove the `NEW.search_vector :=` block (7 `to_tsvector`
   calls) from `SEARCH_VECTOR_FN_SQL` in the management command. Must stay in lockstep with
   the function-body copy embedded in the squashed `ads/migrations/0001_initial.py` trigger
   DDL — these are the live copies of this function body.

3. **`ads/models.py`** — remove the `search_vector = SearchVectorField(...)` field and the
   `GinIndex(name="IX_ads_search_gin", fields=["search_vector"])` from `Ad.Meta.indexes`.

4. **`test_search_triggers.py`** — `TestSearchVectorTrigger.test_insert_populates_all_search_vectors`
   and `test_title_update_refreshes_all_search_vectors` assert only the three per-language
   vectors (never the generic column). Rename method names and docstrings containing
   "all_search_vectors" to "per_language_vectors" to avoid post-removal confusion.

**Cross-references (documented legacy-transitional artifact):**
- `docs/02-database/db-schema.md` (Search section: "Legacy `search_vector` retained during dual-write transition (to be dropped in Phase 3)")
- `docs/02-database/db-indexes.md` (`IX_ads_search_gin` on `search_vector`: "# legacy concatenated vector (to be dropped)"; trigger dual-writes note)
- `docs/01-spec/i18n-spec.md` ("plus a legacy `search_vector` during the dual-write transition, not yet dropped; see db-schema.md > Search")
```

**Acceptance criteria:**
1. Phase-3 tracking note added to `docs/97-plans/01-phase-plan-highlevel.md` under Phase 3
2. The note quantifies the cost (7/16 = 44% of trigger `to_tsvector` CPU; zero reads)
3. The note explicitly states "do NOT remove out-of-band" and "gated on Phase 3"
4. The note documents the full implementation footprint (4 surfaces: migration, setup command, model, tests)
5. The note cross-references all five documentation files that document the legacy column
6. No production code or migration files are modified

**Run command:** (doc-only — verification by reading the updated Phase-3 plan section)

<!-- TASK_END: srh003_phase3_tracking -->

---

## 6. Verification Matrix

| Block | Finding | Test file(s) | Verification command | Marker |
|-------|---------|-------------|---------------------|--------|
| 1 | SRH-001 | `apps/search/tests/test_search_view.py` (`TestSearchViewInputRobustness`) | `$dc run --rm -e PYTEST_OPTS="-k 'test_query_exceeding_max_length_returns_200'" test` | `django_db slow integration` |
| 1 | SRH-004 | `apps/search/tests/test_search_view.py` (`TestSearchViewInputRobustness`) | `$dc run --rm -e PYTEST_OPTS="-k 'test_sql_injection_query_returns_200 or test_homoglyph'" test` | `django_db slow integration` |
| 2 | SRH-002 | Manual doc verification | `git diff docs/03-packages/packages-list.md docs/03-packages/dependency-collisions.md` | N/A (doc-only) |
| 3 | SRH-003 | Manual doc verification | `git diff docs/97-plans/01-phase-plan-highlevel.md` | N/A (tracking-only) |

**Fast-gate coverage (Block 1):**
The SRH-001/SRH-004 tests must pass on `make test` (Docker Compose fast gate, skips nightly `seed` suite ~300s). The tests use real PostgreSQL FTS (requires Docker test DB). Run command:
```powershell
$dc run --rm -e PYTEST_OPTS="-k 'TestSearchViewInputRobustness'" test
```

**Lint + typecheck (Block 1):**
```powershell
uv run ruff check src/backend/apps/search/views/search.py src/backend/apps/search/tests/test_search_view.py
uv run ruff format --check src/backend/apps/search/views/search.py src/backend/apps/search/tests/test_search_view.py
uv run basedpyright src/backend/apps/search/views/search.py
```

**Full suite (regression safety after all blocks):**
```powershell
$dc run --rm test
```
> All 4 findings are in the fast-gate scope (SRH-001 search view, SRH-002 docs, SRH-003 no code). No `make test-all` required — no changes to seed/image pipelines or FTS schema.

---

## 7. Risk Assessment

| Block | Finding | Risk | Mitigation |
|-------|---------|------|------------|
| 1 | SRH-001 | **Low** — truncate is backward-compatible; queries ≤200 chars are unaffected; no migration; no i18n impact | Named constant `MAX_SEARCH_QUERY_LENGTH = 200` aligned to model `max_length`; regression tests pin the fix; `varchar(200)` is the last-line defense |
| 1 | SRH-004 | **Low** — tests only; no production behavior change | Tests follow existing fixture pattern (`seller`/`category`/`city` from `conftest.py`, `create_test_ad` helper, `Client()`); no new fixtures needed |
| 2 | SRH-002 | **Low** — doc-only; zero runtime/code impact | Changes are text-only in markdown; cross-references verified by reading target lines; no i18n `.po`/`.mo` changes (user-visible strings in code are untouched) |
| 3 | SRH-003 | **Low** — doc-only tracking; NO code/schema change | Explicitly gated: "do NOT remove out-of-band"; Phase-3 planning must authorize the migration; tracking note records the full footprint to prevent ad-hoc execution |

**Agent intervention summary:**
- **Block 1 (SRH-001 + SRH-004):** Planner (task creation) + Validator (confirm truncate-vs-reject decision and regression test coverage). No Auditor/Researcher needed — findings already validated; implementation path (truncate) decided in this plan.
- **Block 2 (SRH-002):** Planner only — doc-only, trivial, no review risk.
- **Block 3 (SRH-003):** Planner (task creation) + Validator (verify doc accurately captures the write-amp cost and Phase-3 gating). No Implementor code change.

---

## 8. Implementation Path Decision: Truncate vs Reject (SRH-001)

The validated findings offer two options: "Bound `q` at the input edge — e.g. `query = query[:200]` ... and/or validate and reject >200 chars with a user-facing message."

**Chosen path: Truncate-at-input-edge.**

| Criterion | Truncate | Reject-with-message | Verdict |
|-----------|----------|---------------------|---------|
| Backward compatibility | ✅ ≤200-char queries unaffected | ❌ Changes behavior (new error path) | Truncate |
| Migration required | ✅ No | ✅ No | Tie |
| i18n / DoD impact | ✅ No new user-facing strings | ❌ Requires `{% trans %}` + `makemessages`/`compilemessages` | Truncate |
| Project convention alignment | ✅ Matches `sanitize_autocomplete_query` (silent cap at 100 chars) | ❌ No analogous pattern | Truncate |
| Spec compliance | ✅ §4.5/§7 "bounded or rejected" — "bounded" satisfied | ✅ §4.5/§7 "bounded or rejected" — "rejected" satisfied | Tie |
| UX impact | ✅ None for legitimate users | ❌ User sees error on >200-char query | Truncate |
| Effort | Trivial | Small (validation + message + i18n) | Truncate |

**Reject-with-message is preserved as a future option** if the owner later wants explicit feedback for abnormally long queries, but it is not recommended for this phase: it requires new translated strings (violating the "no unnecessary i18n churn" principle) and changes the error-timing UX without meaningful benefit (a >200-char search query is almost always accidental or hostile, not a legitimate buyer intent the user needs to be warned about).

---

## 9. SRH-003 Phase-3 Tracking — Doc Update Target Confirmation

**Question:** Does SRH-003 tracking need a doc update to a specific Phase-3 file?

**Decision: YES.** SRH-003 tracking requires a doc update to `docs/97-plans/01-phase-plan-highlevel.md` — the Phase 3 "Seller Experience & Analytics" high-level plan. This is the only Phase-3 planning artifact in the repository (no `phase-03-detailed.md` exists). The current Phase 3 section (lines 215–278) covers Seller Dashboard, Account Management, and Analytics milestones (M3.1–M3.3) but has no schema-cleanup or technical-debt sub-items.

The tracking note (detailed in Block 3 above) should be added as a "Phase 3 Technical Debt: Search Vector Cleanup" sub-item, positioned after the Analytics section (item 8) and before the Dependencies block. It must:
1. Quantify the cost: 7/16 (44%) of trigger `to_tsvector` CPU on every ad write, zero reads
2. State the gating explicitly: "do NOT remove out-of-band; gated on Phase 3"
3. Document the full implementation footprint (4 surfaces that must be reconciled in lockstep)
4. Cross-reference all 5 documentation files that document the legacy column as transitional
5. Link to `docs/07-design-researches/migration_patterns.md` as the dual-write migration sequencing authority

The `block` 1 baseline note in `db-indexes.md` (`# legacy concatenated vector (to be dropped)`) and `db-schema.md` (`Legacy search_vector retained during dual-write transition (to be dropped in Phase 3)`) both point to Phase 3 — the tracking note in the Phase-3 plan closes the loop by making the cleanup a concrete, sequenced Phase-3 milestone rather than an undocumented "to be dropped" aspiration.
